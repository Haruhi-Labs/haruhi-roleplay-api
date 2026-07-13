from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import LocalVectorRagService  # noqa: E402
from haruhi_roleplay_api.adapters.rag_vector import ChromaVectorStore  # noqa: E402
from haruhi_roleplay_api.api.rag import post_rag_search  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    PersonaModeId,
    RagDocumentId,
    RagDocumentMetadata,
    RagIngestInput,
    RagRetrieveFilters,
    RagRetrieveInput,
    UserId,
)
from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    RagProviderSettings,
    build_rag_service,
)
from haruhi_roleplay_api.domain.request_limits import MAX_RAG_TOP_K  # noqa: E402


def ingest_input(
    *,
    app_id: str = "web",
    document_id: str = "doc-vector-haruhi",
    character_id: str = "haruhi",
    persona_mode: str = "mid_late_haruhi",
    content: str = (
        "社团 活动 计划：春日会主动安排调查和招募。"
        "\n长期互动中，她会更注意维持 SOS 团成员之间的关系。"
    ),
) -> RagIngestInput:
    return RagIngestInput(
        appId=AppId(app_id),
        documentId=RagDocumentId(document_id),
        title="本地向量资料",
        content=content,
        metadata=RagDocumentMetadata(
            appId=AppId(app_id),
            characterId=CharacterId(character_id),
            personaMode=PersonaModeId(persona_mode),
            timeline="mid_late",
            spoilerLevel=2,
            language="zh-CN",
            sourceType="timeline",
        ),
    )


def retrieve_input(
    *,
    app_id: str = "web",
    character_id: str = "haruhi",
) -> RagRetrieveInput:
    return RagRetrieveInput(
        appId=AppId(app_id),
        userId=UserId("user-1"),
        characterId=CharacterId(character_id),
        personaMode=PersonaModeId("mid_late_haruhi"),
        query="社团 活动 招募",
        topK=5,
        filters=RagRetrieveFilters(
            sourceTypes=("timeline",),
            timelines=("mid_late",),
            spoilerLevelMax=2,
            language="zh-CN",
        ),
    )


class FakeChromaCollection:
    def __init__(self) -> None:
        self.upsert_kwargs: dict | None = None
        self.query_kwargs: dict | None = None

    def upsert(self, **kwargs: object) -> None:
        self.upsert_kwargs = dict(kwargs)

    def query(self, **kwargs: object) -> dict:
        self.query_kwargs = dict(kwargs)
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


class ExplodingRagService:
    def retrieve(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("RAG provider should not be called")


class LocalVectorRagProviderTests(unittest.TestCase):
    def test_rag_search_limits_fail_before_provider(self) -> None:
        base = {
            "app_id": "web",
            "user_id": "user-1",
            "character_id": "haruhi",
            "persona_mode": "mid_late_haruhi",
            "query": "社团 活动",
            "top_k": 3,
        }
        for field_name, value, message in (
            ("top_k", MAX_RAG_TOP_K + 1, "topK must be at most"),
            ("debug", "false", "debug must be a boolean"),
        ):
            with self.subTest(field_name=field_name):
                response = post_rag_search(
                    {**base, field_name: value},
                    rag_service=ExplodingRagService(),
                    request_id="req-rag-search-limit",
                )

                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
                self.assertIn(message, response["error"]["message"])

    def test_local_vector_rag_ingests_and_retrieves_chunks(self) -> None:
        service = LocalVectorRagService(chunk_size=24)

        result = service.ingest(ingest_input())
        output = service.retrieve(retrieve_input())

        self.assertEqual(result.status, "imported")
        self.assertGreaterEqual(result.chunkCount, 2)
        self.assertEqual(output.provider, "local-vector-rag")
        self.assertGreaterEqual(len(output.chunks), 1)
        self.assertEqual(output.chunks[0].documentId, "doc-vector-haruhi")
        self.assertGreater(output.chunks[0].score, 0)
        self.assertEqual(output.chunks[0].metadata.extra["title"], "本地向量资料")

    def test_local_vector_rag_keeps_character_isolated(self) -> None:
        service = LocalVectorRagService()
        service.ingest(ingest_input())

        output = service.retrieve(retrieve_input(character_id="kyon"))

        self.assertEqual(output.chunks, ())
        self.assertEqual(output.filteredHitCount, 0)

    def test_local_vector_rag_keeps_same_document_id_isolated_by_app(self) -> None:
        service = LocalVectorRagService(chunk_size=200)
        service.ingest(ingest_input(app_id="app-a"))
        service.ingest(ingest_input(app_id="app-b"))

        app_a = service.retrieve(retrieve_input(app_id="app-a"))
        app_b = service.retrieve(retrieve_input(app_id="app-b"))

        self.assertGreaterEqual(len(app_a.chunks), 1)
        self.assertGreaterEqual(len(app_b.chunks), 1)
        self.assertTrue(all(chunk.metadata.appId == "app-a" for chunk in app_a.chunks))
        self.assertTrue(all(chunk.metadata.appId == "app-b" for chunk in app_b.chunks))
        self.assertNotEqual(app_a.chunks[0].chunkId, app_b.chunks[0].chunkId)

    def test_chroma_payload_and_query_include_app_scope(self) -> None:
        collection = FakeChromaCollection()
        store = object.__new__(ChromaVectorStore)
        store._collection = collection
        service = LocalVectorRagService(vector_store=store)

        service.ingest(ingest_input(app_id="app-a"))
        service.retrieve(retrieve_input(app_id="app-a"))

        self.assertIsNotNone(collection.upsert_kwargs)
        self.assertIsNotNone(collection.query_kwargs)
        assert collection.upsert_kwargs is not None
        assert collection.query_kwargs is not None
        self.assertTrue(
            all(
                metadata["app_id"] == "app-a"
                for metadata in collection.upsert_kwargs["metadatas"]
            )
        )
        self.assertEqual(collection.query_kwargs["where"], {"app_id": "app-a"})

    def test_rag_provider_factory_builds_local_vector_service(self) -> None:
        service = build_rag_service(
            RagProviderSettings(
                provider="local_vector",
                chunkSize=24,
                embeddingDimensions=128,
                localVectorBackend="memory",
            )
        )

        result = service.ingest(ingest_input(document_id="doc-factory-vector"))
        output = service.retrieve(retrieve_input())

        self.assertEqual(result.documentId, "doc-factory-vector")
        self.assertEqual(output.provider, "local-vector-rag")

    def test_rag_search_api_returns_vector_chunks(self) -> None:
        service = LocalVectorRagService(chunk_size=24)
        service.ingest(ingest_input(document_id="doc-search-vector"))

        response = post_rag_search(
            {
                "app_id": "web",
                "user_id": "user-1",
                "character_id": "haruhi",
                "persona_mode": "mid_late_haruhi",
                "query": "社团 活动",
                "top_k": 3,
                "filters": {
                    "source_types": ["timeline"],
                    "timelines": ["mid_late"],
                    "spoiler_level_max": 2,
                    "language": "zh-CN",
                },
            },
            rag_service=service,
            request_id="req-rag-search",
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["provider"], "local-vector-rag")
        self.assertEqual(response["data"]["chunks"][0]["document_id"], "doc-search-vector")
        self.assertIn("content", response["data"]["chunks"][0])


if __name__ == "__main__":
    unittest.main()
