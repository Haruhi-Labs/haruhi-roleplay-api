"""RAG provider factory wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from haruhi_roleplay_api.adapters import FakeRagService, LocalRagService
from haruhi_roleplay_api.adapters.rag_qdrant import QdrantRagService
from haruhi_roleplay_api.adapters.rag_vector import (
    HashEmbeddingProvider,
    LocalVectorRagService,
)
from haruhi_roleplay_api.application.errors import AppError, ErrorCode


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


def build_rag_service(settings: RagProviderSettings):
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
        return _local_vector_service(settings, backend=settings.localVectorBackend)
    if provider in {"chroma", "chromadb"}:
        return _local_vector_service(settings, backend="chroma")
    if provider == "faiss":
        return _local_vector_service(settings, backend="faiss")
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
            embedding_provider=HashEmbeddingProvider(
                dimensions=settings.embeddingDimensions,
            ),
            ensure_collection=settings.qdrantEnsureCollection,
        )
    raise AppError(
        code=ErrorCode.RAG_PROVIDER_ERROR,
        message=f"RAG_PROVIDER is not supported: {settings.provider}",
    )


def build_rag_service_from_env(env: Mapping[str, str]):
    return build_rag_service(RagProviderSettings.from_mapping(env))


def _local_vector_service(
    settings: RagProviderSettings,
    *,
    backend: str,
) -> LocalVectorRagService:
    return LocalVectorRagService(
        chunk_size=settings.chunkSize,
        embedding_provider=HashEmbeddingProvider(
            dimensions=settings.embeddingDimensions,
        ),
        backend=backend,
        chroma_collection=settings.chromaCollection,
        chroma_persist_path=settings.chromaPersistPath,
    )


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
