from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path
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


def ingest_input() -> RagIngestInput:
    return RagIngestInput(
        appId=AppId("web"),
        documentId=RagDocumentId("doc-qdrant-haruhi"),
        title="Qdrant 资料",
        content="社团 活动 计划：春日会主动安排调查和招募。",
        metadata=RagDocumentMetadata(
            characterId=CharacterId("haruhi"),
            personaMode=PersonaModeId("mid_late_haruhi"),
            timeline="mid_late",
            spoilerLevel=2,
            language="zh-CN",
            sourceType="timeline",
        ),
    )


def retrieve_input() -> RagRetrieveInput:
    return RagRetrieveInput(
        appId=AppId("web"),
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


def qdrant_hit() -> dict:
    return {
        "id": "point-1",
        "score": 0.91,
        "payload": {
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
        self.assertEqual(point["payload"]["document_id"], "doc-qdrant-haruhi")
        self.assertEqual(point["payload"]["character_id"], "haruhi")
        self.assertGreater(len(point["vector"]), 0)

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
            {"key": "character_id", "match": {"value": "haruhi"}},
        )
        self.assertEqual(output.provider, "qdrant-rag")
        self.assertEqual(output.rawHitCount, 1)
        self.assertEqual(output.filteredHitCount, 1)
        self.assertEqual(output.chunks[0].documentId, "doc-qdrant-haruhi")
        self.assertEqual(output.chunks[0].score, 0.91)

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
        ):
            with self.assertRaises(AppError) as context:
                service.retrieve(retrieve_input())

        self.assertEqual(context.exception.code, ErrorCode.RAG_PROVIDER_ERROR)
        self.assertEqual(
            context.exception.public_message,
            "Qdrant RAG provider failed with HTTP 503.",
        )

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
        ):
            with self.assertRaises(AppError) as context:
                service.ingest(ingest_input())

        self.assertEqual(context.exception.code, ErrorCode.RAG_INGEST_FAILED)
        self.assertEqual(
            context.exception.public_message,
            "Qdrant RAG provider failed with HTTP 500.",
        )

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
