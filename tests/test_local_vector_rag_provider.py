from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import LocalVectorRagService  # noqa: E402
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


def ingest_input(
    *,
    document_id: str = "doc-vector-haruhi",
    character_id: str = "haruhi",
    persona_mode: str = "mid_late_haruhi",
    content: str = (
        "社团 活动 计划：春日会主动安排调查和招募。"
        "\n长期互动中，她会更注意维持 SOS 团成员之间的关系。"
    ),
) -> RagIngestInput:
    return RagIngestInput(
        appId=AppId("web"),
        documentId=RagDocumentId(document_id),
        title="本地向量资料",
        content=content,
        metadata=RagDocumentMetadata(
            characterId=CharacterId(character_id),
            personaMode=PersonaModeId(persona_mode),
            timeline="mid_late",
            spoilerLevel=2,
            language="zh-CN",
            sourceType="timeline",
        ),
    )


def retrieve_input(*, character_id: str = "haruhi") -> RagRetrieveInput:
    return RagRetrieveInput(
        appId=AppId("web"),
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


class LocalVectorRagProviderTests(unittest.TestCase):
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
