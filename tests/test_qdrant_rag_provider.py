from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from threading import Barrier
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import QdrantRagService  # noqa: E402
from haruhi_roleplay_api.application.errors import AppError, ErrorCode  # noqa: E402
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


class FakeHTTPResponse:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload or {}

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def ingest_input(
    *,
    app_id: str = "web",
    atomic_record: bool = False,
    structured: bool = False,
) -> RagIngestInput:
    return RagIngestInput(
        appId=AppId(app_id),
        documentId=RagDocumentId("doc-qdrant-haruhi"),
        title="Qdrant 资料",
        content="社团 活动 计划：春日会主动安排调查和招募。",
        metadata=RagDocumentMetadata(
            appId=AppId(app_id),
            characterId=CharacterId("haruhi"),
            personaMode=PersonaModeId("mid_late_haruhi"),
            timeline="mid_late",
            spoilerLevel=2,
            language="zh-CN",
            sourceType="timeline",
            extra={
                **({"atomic_record": True} if atomic_record else {}),
                **(
                    {
                        "record_kind": "dialogue_example",
                        "perspective": "spoken_by_character",
                        "corpus_version": "haruhi-rag-test",
                        "retrieval_channel": "dialogue_style",
                        "knowledge_owner": "haruhi",
                        "subject_character_id": "haruhi",
                        "usage": "style_only",
                        "scene_id": "scene-test",
                    }
                    if structured
                    else {}
                ),
            },
        ),
    )


def retrieve_input(*, app_id: str = "web") -> RagRetrieveInput:
    return RagRetrieveInput(
        appId=AppId(app_id),
        userId=UserId("user-1"),
        characterId=CharacterId("haruhi"),
        personaMode=PersonaModeId("mid_late_haruhi"),
        query="社团 活动",
        topK=3,
        filters=RagRetrieveFilters(
            sourceTypes=("timeline",),
            timelines=("mid_late",),
            spoilerLevelMax=2,
            language="zh-CN",
        ),
    )


def qdrant_hit(*, app_id: str = "web") -> dict:
    return {
        "id": "point-1",
        "score": 0.91,
        "payload": {
            "app_id": app_id,
            "document_id": "doc-qdrant-haruhi",
            "chunk_id": "doc-qdrant-haruhi-chunk-1",
            "content": "社团 活动 计划：春日会主动安排调查和招募。",
            "title": "Qdrant 资料",
            "character_id": "haruhi",
            "persona_mode": "mid_late_haruhi",
            "timeline": "mid_late",
            "spoiler_level": 2,
            "language": "zh-CN",
            "source_type": "timeline",
            "trust_level": "",
            "metadata": {"title": "Qdrant 资料"},
        },
    }


class QdrantRagProviderTests(unittest.TestCase):
    def test_qdrant_creates_payload_indexes_before_first_ingest(self) -> None:
        not_found = urllib.error.HTTPError(
            url="https://qdrant.example/collections/haruhi_rag",
            code=404,
            msg="not found",
            hdrs=None,
            fp=None,
        )
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
            ensure_collection=True,
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            side_effect=[not_found]
            + [FakeHTTPResponse({"result": {"status": "ok"}})] * 21,
        ) as urlopen:
            service.ingest(ingest_input())

        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(requests[0].method, "GET")
        self.assertEqual(requests[1].method, "PUT")
        self.assertEqual(
            requests[1].full_url,
            "https://qdrant.example/collections/haruhi_rag",
        )
        index_requests = [
            request for request in requests if request.full_url.endswith("/index?wait=true")
        ]
        schemas = {
            payload["field_name"]: payload["field_schema"]
            for payload in (
                json.loads(request.data.decode("utf-8")) for request in index_requests
            )
        }
        self.assertEqual(schemas["app_id"], {"type": "keyword", "is_tenant": True})
        self.assertEqual(schemas["spoiler_level"], "integer")
        self.assertEqual(schemas["content"]["tokenizer"], "multilingual")
        self.assertTrue(requests[-1].full_url.endswith("/points?wait=true"))

    def test_qdrant_rejects_existing_collection_dimension_mismatch(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
            ensure_collection=True,
        )
        collection_info = {
            "result": {
                "config": {"params": {"vectors": {"size": 768}}},
                "payload_schema": {},
            }
        }
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            return_value=FakeHTTPResponse(collection_info),
        ):
            with self.assertRaises(AppError) as context:
                service.ingest(ingest_input())

        self.assertEqual(context.exception.code, ErrorCode.RAG_PROVIDER_ERROR)
        self.assertIn("向量维度为 768", context.exception.public_message)
        self.assertIn("输出维度为 384", context.exception.public_message)

    def test_qdrant_switches_existing_alias_atomically(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag__v2",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            side_effect=[
                FakeHTTPResponse(
                    {
                        "result": {
                            "aliases": [
                                {
                                    "alias_name": "haruhi_rag_live",
                                    "collection_name": "haruhi_rag__v1",
                                }
                            ]
                        }
                    }
                ),
                FakeHTTPResponse({"result": {"status": "ok"}}),
            ],
        ) as urlopen:
            previous = service.switch_alias("haruhi_rag_live")

        self.assertEqual(previous, "haruhi_rag__v1")
        switch_request = urlopen.call_args_list[1].args[0]
        self.assertEqual(
            switch_request.full_url,
            "https://qdrant.example/collections/aliases",
        )
        self.assertEqual(
            json.loads(switch_request.data.decode("utf-8"))["actions"],
            [
                {"delete_alias": {"alias_name": "haruhi_rag_live"}},
                {
                    "create_alias": {
                        "collection_name": "haruhi_rag__v2",
                        "alias_name": "haruhi_rag_live",
                    }
                },
            ],
        )

    def test_qdrant_counts_points_with_app_scope(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag__v2",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            return_value=FakeHTTPResponse({"result": {"count": 17043}}),
        ) as urlopen:
            count = service.count_points(app_id="web-demo")

        self.assertEqual(count, 17043)
        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertTrue(payload["exact"])
        self.assertEqual(
            payload["filter"]["must"],
            [{"key": "app_id", "match": {"value": "web-demo"}}],
        )

    def test_qdrant_refuses_to_delete_aliased_collection(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag__v2",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            return_value=FakeHTTPResponse(
                {
                    "result": {
                        "aliases": [
                            {
                                "alias_name": "haruhi_rag_live",
                                "collection_name": "haruhi_rag__v2",
                            }
                        ]
                    }
                }
            ),
        ):
            with self.assertRaises(AppError) as context:
                service.delete_collection()

        self.assertIn("仍被 alias 引用", context.exception.public_message)

    def test_qdrant_ingest_upserts_points(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
            api_key="qdrant-secret",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            return_value=FakeHTTPResponse({"result": {"status": "ok"}}),
        ) as urlopen:
            result = service.ingest(ingest_input())

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        point = payload["points"][0]

        self.assertEqual(
            request.full_url,
            "https://qdrant.example/collections/haruhi_rag/points?wait=true",
        )
        self.assertEqual(result.status, "imported")
        self.assertEqual(result.documentId, "doc-qdrant-haruhi")
        self.assertEqual(point["payload"]["app_id"], "web")
        self.assertEqual(point["payload"]["document_id"], "doc-qdrant-haruhi")
        self.assertEqual(point["payload"]["character_id"], "haruhi")
        self.assertGreater(len(point["vector"]), 0)

    def test_qdrant_retries_transient_upsert_gateway_error(self) -> None:
        gateway_error = urllib.error.HTTPError(
            url="https://qdrant.example/collections/haruhi_rag/points",
            code=502,
            msg="bad gateway",
            hdrs=None,
            fp=None,
        )
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            side_effect=(
                gateway_error,
                FakeHTTPResponse({"result": {"status": "ok"}}),
            ),
        ) as urlopen, patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.time.sleep"
        ) as sleep:
            result = service.ingest(ingest_input())

        self.assertEqual(result.status, "imported")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(0.5)

    def test_qdrant_keeps_atomic_corpus_record_in_one_point(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
            chunk_size=8,
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            return_value=FakeHTTPResponse({"result": {"status": "ok"}}),
        ) as urlopen:
            result = service.ingest(ingest_input(atomic_record=True))

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(result.chunkCount, 1)
        self.assertEqual(len(payload["points"]), 1)
        self.assertTrue(payload["points"][0]["payload"]["metadata"]["atomic_record"])

    def test_qdrant_batches_embedding_and_point_upsert(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
            ingest_batch_size=64,
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            return_value=FakeHTTPResponse({"result": {"status": "ok"}}),
        ) as urlopen:
            results = service.ingest_batch(
                (ingest_input(app_id="app-a"), ingest_input(app_id="app-b"))
            )

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(payload["points"]), 2)
        self.assertEqual(
            {point["payload"]["app_id"] for point in payload["points"]},
            {"app-a", "app-b"},
        )

    def test_qdrant_flattens_roleplay_routing_payload(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            return_value=FakeHTTPResponse({"result": {"status": "ok"}}),
        ) as urlopen:
            service.ingest(ingest_input(structured=True))

        request = urlopen.call_args.args[0]
        point = json.loads(request.data.decode("utf-8"))["points"][0]

        self.assertEqual(point["payload"]["record_kind"], "dialogue_example")
        self.assertEqual(point["payload"]["retrieval_channel"], "dialogue_style")
        self.assertEqual(point["payload"]["knowledge_owner"], "haruhi")
        self.assertEqual(point["payload"]["scene_id"], "scene-test")

    def test_qdrant_pushes_roleplay_filters_to_server(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
        )
        scoped_input = RagRetrieveInput(
            appId=AppId("web"),
            userId=UserId("user-1"),
            characterId=CharacterId("haruhi"),
            personaMode=PersonaModeId("mid_late_haruhi"),
            query="社团 活动",
            topK=3,
            filters=RagRetrieveFilters(
                recordKinds=("dialogue_example",),
                perspectives=("spoken_by_character",),
                corpusVersions=("haruhi-rag-test",),
                retrievalChannels=("dialogue_style",),
                knowledgeOwners=("haruhi",),
                usages=("style_only",),
            ),
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            return_value=FakeHTTPResponse({"result": []}),
        ) as urlopen:
            service.retrieve(scoped_input)

        request = urlopen.call_args.args[0]
        must = json.loads(request.data.decode("utf-8"))["filter"]["must"]

        for field, value in (
            ("record_kind", "dialogue_example"),
            ("perspective", "spoken_by_character"),
            ("corpus_version", "haruhi-rag-test"),
            ("retrieval_channel", "dialogue_style"),
            ("knowledge_owner", "haruhi"),
            ("usage", "style_only"),
        ):
            self.assertIn({"key": field, "match": {"value": value}}, must)

    def test_qdrant_hybrid_search_merges_full_text_candidates(self) -> None:
        dense_hit = qdrant_hit()
        dense_hit["payload"] = {
            **dense_hit["payload"],
            "content": "社团活动需要尽快安排。",
        }
        lexical_hit = qdrant_hit()
        lexical_hit["id"] = "point-lexical"
        lexical_hit["payload"] = {
            **lexical_hit["payload"],
            "document_id": "doc-qdrant-tanabata",
            "chunk_id": "doc-qdrant-tanabata-chunk-1",
            "content": "七夕时，春日让大家写下愿望并挂在竹叶上。",
        }
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
            hybrid_search=True,
        )
        scoped_input = RagRetrieveInput(
            appId=AppId("web"),
            userId=UserId("user-1"),
            characterId=CharacterId("haruhi"),
            personaMode=PersonaModeId("mid_late_haruhi"),
            query=(
                "目标角色：haruhi\n最近对话：\nuser: 雪山发生了什么\n"
                "当前用户输入：\n七夕时春日做了什么"
            ),
            topK=3,
            filters=RagRetrieveFilters(
                sourceTypes=("timeline",),
                timelines=("mid_late",),
                spoilerLevelMax=2,
                language="zh-CN",
            ),
        )
        request_barrier = Barrier(2)

        def qdrant_response(request: object, **_: object) -> FakeHTTPResponse:
            request_barrier.wait(timeout=1)
            if request.full_url.endswith("/points/search"):
                return FakeHTTPResponse({"result": [dense_hit]})
            return FakeHTTPResponse({"result": {"points": [lexical_hit]}})

        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            side_effect=qdrant_response,
        ) as urlopen:
            output = service.retrieve(scoped_input)

        lexical_request = next(
            call.args[0]
            for call in urlopen.call_args_list
            if call.args[0].full_url.endswith("/points/scroll")
        )
        lexical_payload = json.loads(lexical_request.data.decode("utf-8"))
        self.assertTrue(lexical_request.full_url.endswith("/points/scroll"))
        self.assertEqual(
            lexical_payload["filter"]["must"][-1],
            {
                "key": "content",
                "match": {"text_any": "七夕时春日做了什么"},
            },
        )
        self.assertEqual(output.rawHitCount, 2)
        self.assertEqual(output.filteredHitCount, 2)
        self.assertEqual(output.chunks[0].documentId, "doc-qdrant-tanabata")
        for chunk in output.chunks:
            relevance = chunk.metadata.extra["_retrieval_relevance"]
            self.assertGreaterEqual(relevance, 0.0)
            self.assertLessEqual(relevance, 1.0)
            self.assertNotIn("_retrieval_relevance", chunk.to_source_mapping())

    def test_qdrant_retrieve_returns_filtered_sources(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            return_value=FakeHTTPResponse({"result": [qdrant_hit()]}),
        ) as urlopen:
            output = service.retrieve(retrieve_input())

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(
            request.full_url,
            "https://qdrant.example/collections/haruhi_rag/points/search",
        )
        self.assertEqual(payload["limit"], 24)
        self.assertEqual(
            payload["filter"]["must"][0],
            {"key": "app_id", "match": {"value": "web"}},
        )
        self.assertEqual(
            payload["filter"]["must"][1],
            {"key": "character_id", "match": {"value": "haruhi"}},
        )
        self.assertEqual(output.provider, "qdrant-rag")
        self.assertEqual(output.rawHitCount, 1)
        self.assertEqual(output.filteredHitCount, 1)
        self.assertEqual(output.chunks[0].documentId, "doc-qdrant-haruhi")
        self.assertEqual(output.chunks[0].score, 0.91)

    def test_qdrant_same_document_id_uses_distinct_points_per_app(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            return_value=FakeHTTPResponse({"result": {"status": "ok"}}),
        ) as urlopen:
            service.ingest(ingest_input(app_id="app-a"))
            service.ingest(ingest_input(app_id="app-b"))

        first = json.loads(urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        second = json.loads(urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertNotEqual(first["points"][0]["id"], second["points"][0]["id"])
        self.assertEqual(first["points"][0]["payload"]["app_id"], "app-a")
        self.assertEqual(second["points"][0]["payload"]["app_id"], "app-b")

    def test_qdrant_client_filter_rejects_cross_app_and_legacy_hits(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
        )
        legacy_hit = qdrant_hit()
        legacy_hit["payload"].pop("app_id")
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            return_value=FakeHTTPResponse(
                {"result": [qdrant_hit(app_id="other-app"), legacy_hit]}
            ),
        ):
            output = service.retrieve(retrieve_input(app_id="web"))

        self.assertEqual(output.rawHitCount, 2)
        self.assertEqual(output.filteredHitCount, 0)
        self.assertEqual(output.chunks, ())

    def test_qdrant_admin_lists_and_deletes_app_scoped_document(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            side_effect=[
                FakeHTTPResponse({"result": {"points": [qdrant_hit()]}}),
                FakeHTTPResponse({"result": {"points": [qdrant_hit()]}}),
                FakeHTTPResponse({"result": {"status": "acknowledged"}}),
            ],
        ) as urlopen:
            documents = service.list_documents(app_id="web")
            removed = service.delete_document(
                app_id="web",
                document_id="doc-qdrant-haruhi",
            )

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].title, "Qdrant 资料")
        self.assertEqual(removed, 1)
        delete_request = urlopen.call_args_list[2].args[0]
        delete_payload = json.loads(delete_request.data.decode("utf-8"))
        self.assertIn("points/delete?wait=true", delete_request.full_url)
        self.assertEqual(
            delete_payload["filter"]["must"][1],
            {"key": "document_id", "match": {"value": "doc-qdrant-haruhi"}},
        )

    def test_qdrant_admin_list_follows_scroll_pagination(self) -> None:
        second_hit = qdrant_hit()
        second_hit["id"] = "point-2"
        second_hit["payload"] = {
            **second_hit["payload"],
            "document_id": "doc-qdrant-kyon",
            "chunk_id": "doc-qdrant-kyon-chunk-1",
            "title": "Qdrant 阿虚资料",
            "metadata": {"title": "Qdrant 阿虚资料"},
        }
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            side_effect=[
                FakeHTTPResponse(
                    {
                        "result": {
                            "points": [qdrant_hit()],
                            "next_page_offset": "point-1",
                        }
                    }
                ),
                FakeHTTPResponse(
                    {"result": {"points": [second_hit], "next_page_offset": None}}
                ),
            ],
        ) as urlopen:
            documents = service.list_documents(app_id="web")

        self.assertEqual(len(documents), 2)
        second_payload = json.loads(
            urlopen.call_args_list[1].args[0].data.decode("utf-8")
        )
        self.assertEqual(second_payload["offset"], "point-1")
        self.assertEqual(
            second_payload["filter"]["must"],
            [{"key": "app_id", "match": {"value": "web"}}],
        )

    def test_qdrant_admin_limited_list_uses_facet_and_scoped_scroll(self) -> None:
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            side_effect=[
                FakeHTTPResponse(
                    {
                        "result": {
                            "hits": [
                                {"value": "doc-qdrant-haruhi", "count": 1},
                                {"value": "doc-next", "count": 1},
                            ]
                        }
                    }
                ),
                FakeHTTPResponse(
                    {
                        "result": {
                            "points": [qdrant_hit()],
                            "next_page_offset": None,
                        }
                    }
                ),
            ],
        ) as urlopen:
            documents, truncated = service.list_documents_limited(
                app_id="web",
                limit=1,
            )

        self.assertEqual(len(documents), 1)
        self.assertTrue(truncated)
        facet_payload = json.loads(urlopen.call_args_list[0].args[0].data.decode())
        self.assertEqual(facet_payload["key"], "document_id")
        self.assertEqual(facet_payload["limit"], 2)
        scroll_payload = json.loads(urlopen.call_args_list[1].args[0].data.decode())
        self.assertEqual(
            scroll_payload["filter"]["must"][1],
            {
                "key": "document_id",
                "match": {"any": ["doc-qdrant-haruhi"]},
            },
        )

    def test_qdrant_retrieve_maps_provider_error(self) -> None:
        http_error = urllib.error.HTTPError(
            url="https://qdrant.example/collections/haruhi_rag/points/search",
            code=503,
            msg="unavailable",
            hdrs=None,
            fp=None,
        )
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            side_effect=http_error,
        ) as urlopen, patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.time.sleep"
        ) as sleep:
            with self.assertRaises(AppError) as context:
                service.retrieve(retrieve_input())

        self.assertEqual(context.exception.code, ErrorCode.RAG_PROVIDER_ERROR)
        self.assertEqual(
            context.exception.public_message,
            "Qdrant RAG provider failed with HTTP 503.",
        )
        self.assertEqual(urlopen.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    def test_qdrant_ingest_maps_provider_error(self) -> None:
        http_error = urllib.error.HTTPError(
            url="https://qdrant.example/collections/haruhi_rag/points",
            code=500,
            msg="failed",
            hdrs=None,
            fp=None,
        )
        service = QdrantRagService(
            base_url="https://qdrant.example",
            collection="haruhi_rag",
        )
        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            side_effect=http_error,
        ) as urlopen, patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.time.sleep"
        ) as sleep:
            with self.assertRaises(AppError) as context:
                service.ingest(ingest_input())

        self.assertEqual(context.exception.code, ErrorCode.RAG_INGEST_FAILED)
        self.assertEqual(
            context.exception.public_message,
            "Qdrant RAG provider failed with HTTP 500.",
        )
        self.assertEqual(urlopen.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    def test_rag_provider_factory_builds_qdrant_service(self) -> None:
        service = build_rag_service(
            RagProviderSettings(
                provider="qdrant",
                qdrantUrl="https://qdrant.example",
                qdrantCollection="haruhi_rag",
            )
        )

        self.assertIsInstance(service, QdrantRagService)

    def test_rag_provider_factory_requires_qdrant_url(self) -> None:
        with self.assertRaises(AppError) as context:
            build_rag_service(RagProviderSettings(provider="qdrant"))

        self.assertEqual(context.exception.code, ErrorCode.RAG_PROVIDER_ERROR)
        self.assertEqual(
            context.exception.public_message,
            "QDRANT_URL is required for qdrant RAG provider.",
        )


if __name__ == "__main__":
    unittest.main()
