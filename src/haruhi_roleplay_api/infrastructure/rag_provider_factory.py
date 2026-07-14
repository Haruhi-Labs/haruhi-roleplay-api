"""RAG provider factory wiring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from haruhi_roleplay_api.adapters import (
    FakeRagService,
    HashEmbeddingProvider,
    LocalRagService,
)
from haruhi_roleplay_api.adapters.rag_qdrant import QdrantRagService
from haruhi_roleplay_api.adapters.rag_vector import LocalVectorRagService
from haruhi_roleplay_api.infrastructure.embedding_provider_factory import (
    EmbeddingProviderSettings,
    build_embedding_provider,
)
from haruhi_roleplay_api.infrastructure.provider_config_facade import (
    apply_provider_config_facade,
)
from haruhi_roleplay_api.infrastructure.rag_corpus import ingest_corpus_file
from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.ports import TextEmbeddingProvider


@dataclass(frozen=True, kw_only=True)
class RagProviderSettings:
    provider: str = "local"
    chunkSize: int = 320
    embeddingDimensions: int = 384
    localVectorBackend: str = "memory"
    chromaCollection: str = "haruhi_rag"
    chromaPersistPath: str | None = None
    qdrantUrl: str | None = None
    qdrantCollection: str = "haruhi_rag"
    qdrantApiKey: str | None = None
    qdrantTimeoutMs: int = 10000
    qdrantEnsureCollection: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, str]) -> "RagProviderSettings":
        data = apply_provider_config_facade(data)
        return cls(
            provider=data.get("RAG_PROVIDER", "local"),
            chunkSize=_int_from_mapping(data, "RAG_CHUNK_SIZE", default=320),
            embeddingDimensions=_int_from_mapping(
                data,
                "RAG_EMBEDDING_DIMENSIONS",
                default=384,
            ),
            localVectorBackend=data.get(
                "LOCAL_VECTOR_RAG_BACKEND",
                data.get("RAG_VECTOR_BACKEND", "memory"),
            ),
            chromaCollection=data.get("CHROMA_COLLECTION", "haruhi_rag"),
            chromaPersistPath=data.get("CHROMA_PERSIST_PATH"),
            qdrantUrl=data.get("QDRANT_URL"),
            qdrantCollection=data.get("QDRANT_COLLECTION", "haruhi_rag"),
            qdrantApiKey=data.get("QDRANT_API_KEY"),
            qdrantTimeoutMs=_int_from_mapping(
                data,
                "QDRANT_TIMEOUT_MS",
                default=10000,
            ),
            qdrantEnsureCollection=_bool_from_mapping(
                data.get("QDRANT_ENSURE_COLLECTION", "false")
            ),
        )


def build_rag_service(
    settings: RagProviderSettings,
    *,
    embedding_provider: TextEmbeddingProvider | None = None,
):
    provider = settings.provider.strip().lower().replace("-", "_")
    if settings.chunkSize <= 0:
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message="RAG_CHUNK_SIZE must be positive.",
        )
    if settings.embeddingDimensions <= 0:
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message="RAG_EMBEDDING_DIMENSIONS must be positive.",
        )
    if provider in {"fake", "fake_rag"}:
        return FakeRagService()
    if provider in {"local", "local_rag"}:
        return LocalRagService(chunk_size=settings.chunkSize)
    if provider in {"local_vector", "local_vector_rag"}:
        return _local_vector_service(
            settings,
            backend=settings.localVectorBackend,
            embedding_provider=embedding_provider,
        )
    if provider in {"chroma", "chromadb"}:
        return _local_vector_service(
            settings,
            backend="chroma",
            embedding_provider=embedding_provider,
        )
    if provider == "faiss":
        return _local_vector_service(
            settings,
            backend="faiss",
            embedding_provider=embedding_provider,
        )
    if provider in {"qdrant", "cloud_rag"}:
        if not settings.qdrantUrl:
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="QDRANT_URL is required for qdrant RAG provider.",
            )
        return QdrantRagService(
            base_url=settings.qdrantUrl,
            collection=settings.qdrantCollection,
            api_key=settings.qdrantApiKey,
            timeout_seconds=settings.qdrantTimeoutMs / 1000,
            chunk_size=settings.chunkSize,
            embedding_provider=embedding_provider or _hash_embedding(settings),
            ensure_collection=settings.qdrantEnsureCollection,
        )
    raise AppError(
        code=ErrorCode.RAG_PROVIDER_ERROR,
        message=f"RAG_PROVIDER is not supported: {settings.provider}",
    )


def build_rag_service_from_env(env: Mapping[str, str]):
    env = apply_provider_config_facade(env)
    settings = RagProviderSettings.from_mapping(env)
    provider = settings.provider.strip().lower().replace("-", "_")
    embedding_provider = (
        build_embedding_provider(EmbeddingProviderSettings.from_mapping(env))
        if _requires_embedding_provider(provider)
        else None
    )
    service = build_rag_service(settings, embedding_provider=embedding_provider)
    corpus_path = env.get("RAG_BOOTSTRAP_CORPUS_PATH", "").strip()
    if corpus_path:
        corpus_app_id = env.get("RAG_BOOTSTRAP_APP_ID", "").strip()
        if not corpus_app_id:
            raise AppError(
                code=ErrorCode.RAG_INGEST_FAILED,
                message=(
                    "配置 RAG_BOOTSTRAP_CORPUS_PATH 时必须同时配置 "
                    "RAG_BOOTSTRAP_APP_ID。"
                ),
            )
        if not hasattr(service, "ingest"):
            raise AppError(
                code=ErrorCode.RAG_INGEST_FAILED,
                message="当前配置的 RAG provider 不支持装载启动语料。",
            )
        try:
            ingest_corpus_file(
                service,
                path=Path(corpus_path),
                app_id=corpus_app_id,
            )
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                code=ErrorCode.RAG_INGEST_FAILED,
                message=f"装载 RAG 启动语料失败：{corpus_path}",
            ) from exc
    return service


def _requires_embedding_provider(provider: str) -> bool:
    return provider in {
        "local_vector",
        "local_vector_rag",
        "chroma",
        "chromadb",
        "faiss",
        "qdrant",
        "cloud_rag",
    }


def _local_vector_service(
    settings: RagProviderSettings,
    *,
    backend: str,
    embedding_provider: TextEmbeddingProvider | None,
) -> LocalVectorRagService:
    return LocalVectorRagService(
        chunk_size=settings.chunkSize,
        embedding_provider=embedding_provider or _hash_embedding(settings),
        backend=backend,
        chroma_collection=settings.chromaCollection,
        chroma_persist_path=settings.chromaPersistPath,
    )


def _hash_embedding(settings: RagProviderSettings) -> HashEmbeddingProvider:
    return HashEmbeddingProvider(dimensions=settings.embeddingDimensions)


def _int_from_mapping(
    data: Mapping[str, str],
    key: str,
    *,
    default: int,
) -> int:
    value = data.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message=f"{key} must be an integer.",
        ) from exc


def _bool_from_mapping(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "no", "off"}
