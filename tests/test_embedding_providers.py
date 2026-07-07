from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import HashEmbeddingProvider  # noqa: E402
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
    EmbeddingProviderSettings,
    build_embedding_provider,
)
from haruhi_roleplay_api.infrastructure.rag_provider_factory import (  # noqa: E402
    build_rag_service_from_env,
)


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def embedding_response(vector: list[float]) -> FakeHTTPResponse:
    return FakeHTTPResponse({"data": [{"embedding": vector}]})


def ingest_input() -> RagIngestInput:
    return RagIngestInput(
        appId=AppId("web"),
        documentId=RagDocumentId("doc-embedding-rag"),
        title="Embedding RAG 资料",
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


class EmbeddingProviderTests(unittest.TestCase):
    def test_hash_embedding_is_deterministic(self) -> None:
        provider = HashEmbeddingProvider(dimensions=16)

        first = provider.embed("社团 活动")
        second = provider.embed("社团 活动")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)
        self.assertGreater(sum(abs(value) for value in first), 0)

    def test_openai_embedding_provider_uses_official_endpoint(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.embeddings.openai_compatible.urllib.request.urlopen",
            return_value=embedding_response([0.1, 0.2, 0.3]),
        ) as urlopen:
            provider = build_embedding_provider(
                EmbeddingProviderSettings.from_mapping(
                    {
                        "EMBEDDING_PROVIDER": "openai",
                        "EMBEDDING_MODEL": "text-embedding-3-small",
                        "EMBEDDING_DIMENSIONS": "3",
                        "OPENAI_API_KEY": "openai-secret",
                    }
                )
            )
            embedding = provider.embed("今天有什么计划？")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(request.full_url, "https://api.openai.com/v1/embeddings")
        self.assertEqual(request.headers["Authorization"], "Bearer openai-secret")
        self.assertEqual(payload["model"], "text-embedding-3-small")
        self.assertEqual(payload["input"], "今天有什么计划？")
        self.assertEqual(payload["dimensions"], 3)
        self.assertEqual(provider.provider_name, "openai-embedding")
        self.assertEqual(embedding, (0.1, 0.2, 0.3))

    def test_ollama_embedding_provider_uses_local_openai_endpoint(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.embeddings.openai_compatible.urllib.request.urlopen",
            return_value=embedding_response([0.5, 0.4, 0.3]),
        ) as urlopen:
            provider = build_embedding_provider(
                EmbeddingProviderSettings.from_mapping(
                    {
                        "EMBEDDING_PROVIDER": "ollama",
                        "EMBEDDING_MODEL": "nomic-embed-text",
                        "EMBEDDING_DIMENSIONS": "3",
                    }
                )
            )
            embedding = provider.embed("社团 活动")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(request.full_url, "http://localhost:11434/v1/embeddings")
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual(payload["model"], "nomic-embed-text")
        self.assertEqual(payload["dimensions"], 3)
        self.assertEqual(provider.provider_name, "ollama-embedding")
        self.assertEqual(embedding, (0.5, 0.4, 0.3))

    def test_local_openai_compatible_embedding_provider_supports_base_url(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.embeddings.openai_compatible.urllib.request.urlopen",
            return_value=embedding_response([0.1, 0.0, 0.0]),
        ) as urlopen:
            provider = build_embedding_provider(
                EmbeddingProviderSettings.from_mapping(
                    {
                        "EMBEDDING_PROVIDER": "local_openai_compatible",
                        "EMBEDDING_BASE_URL": "http://localhost:9999/v1",
                        "EMBEDDING_MODEL": "local-embed",
                        "EMBEDDING_DIMENSIONS": "3",
                    }
                )
            )
            provider.embed("本地 embedding")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "http://localhost:9999/v1/embeddings")
        self.assertEqual(payload["dimensions"], 3)

    def test_openai_embedding_provider_requires_api_key(self) -> None:
        with self.assertRaises(AppError) as context:
            build_embedding_provider(
                EmbeddingProviderSettings.from_mapping(
                    {
                        "EMBEDDING_PROVIDER": "openai",
                        "EMBEDDING_DIMENSIONS": "3",
                    }
                )
            )

        self.assertEqual(context.exception.code, ErrorCode.RAG_PROVIDER_ERROR)
        self.assertEqual(
            context.exception.public_message,
            "OPENAI_API_KEY is required for OpenAI embedding provider.",
        )

    def test_embedding_provider_invalid_response_maps_to_app_error(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.embeddings.openai_compatible.urllib.request.urlopen",
            return_value=embedding_response([0.1, 0.2]),
        ):
            provider = build_embedding_provider(
                EmbeddingProviderSettings.from_mapping(
                    {
                        "EMBEDDING_PROVIDER": "ollama",
                        "EMBEDDING_DIMENSIONS": "3",
                    }
                )
            )
            with self.assertRaises(AppError) as context:
                provider.embed("维度不匹配")

        self.assertEqual(context.exception.code, ErrorCode.RAG_PROVIDER_ERROR)
        self.assertIn("expected 3", context.exception.public_message)

    def test_rag_factory_injects_configured_embedding_provider(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.embeddings.openai_compatible.urllib.request.urlopen",
            side_effect=(
                embedding_response([1.0, 0.0, 0.0]),
                embedding_response([1.0, 0.0, 0.0]),
            ),
        ) as urlopen:
            service = build_rag_service_from_env(
                {
                    "RAG_PROVIDER": "local_vector",
                    "RAG_CHUNK_SIZE": "320",
                    "EMBEDDING_PROVIDER": "local_openai_compatible",
                    "EMBEDDING_BASE_URL": "http://embedding.local/v1",
                    "EMBEDDING_MODEL": "local-embed",
                    "EMBEDDING_DIMENSIONS": "3",
                }
            )
            service.ingest(ingest_input())
            output = service.retrieve(retrieve_input())

        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(output.provider, "local-vector-rag")
        self.assertEqual(output.chunks[0].documentId, "doc-embedding-rag")
        self.assertGreater(output.chunks[0].score, 0)

    def test_embedding_provider_http_error_maps_to_app_error(self) -> None:
        http_error = urllib.error.HTTPError(
            url="http://localhost:11434/v1/embeddings",
            code=500,
            msg="failed",
            hdrs=None,
            fp=None,
        )
        with patch(
            "haruhi_roleplay_api.adapters.embeddings.openai_compatible.urllib.request.urlopen",
            side_effect=http_error,
        ):
            provider = build_embedding_provider(
                EmbeddingProviderSettings.from_mapping(
                    {
                        "EMBEDDING_PROVIDER": "ollama",
                        "EMBEDDING_DIMENSIONS": "3",
                    }
                )
            )
            with self.assertRaises(AppError) as context:
                provider.embed("HTTP error")

        self.assertEqual(context.exception.code, ErrorCode.RAG_PROVIDER_ERROR)
        self.assertEqual(
            context.exception.public_message,
            "ollama-embedding provider failed with HTTP 500.",
        )


if __name__ == "__main__":
    unittest.main()
