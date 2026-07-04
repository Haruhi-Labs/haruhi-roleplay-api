"""Embedding provider factory wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from haruhi_roleplay_api.adapters import (
    HashEmbeddingProvider,
    LocalOpenAICompatibleEmbeddingProvider,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.ports import TextEmbeddingProvider


@dataclass(frozen=True, kw_only=True)
class EmbeddingProviderSettings:
    provider: str = "hash"
    model: str | None = None
    baseUrl: str | None = None
    apiKey: str | None = None
    apiKeyEnv: str | None = None
    timeoutMs: int = 30000
    dimensions: int = 384
    embeddingsPath: str | None = None
    sourceEnv: Mapping[str, str] | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, str]) -> "EmbeddingProviderSettings":
        provider = data.get("EMBEDDING_PROVIDER", "hash")
        api_key_env = data.get("EMBEDDING_API_KEY_ENV")
        return cls(
            provider=provider,
            model=data.get("EMBEDDING_MODEL"),
            baseUrl=data.get("EMBEDDING_BASE_URL"),
            apiKey=data.get("EMBEDDING_API_KEY") or _api_key_from_env(
                api_key_env,
                data,
            ),
            apiKeyEnv=api_key_env,
            timeoutMs=_int_from_mapping(data, "EMBEDDING_TIMEOUT_MS", default=30000),
            dimensions=_int_from_mapping(
                data,
                "EMBEDDING_DIMENSIONS",
                fallback_key="RAG_EMBEDDING_DIMENSIONS",
                default=_default_dimensions(provider),
            ),
            embeddingsPath=data.get("EMBEDDING_PATH"),
            sourceEnv=dict(data),
        )


def build_embedding_provider(
    settings: EmbeddingProviderSettings,
) -> TextEmbeddingProvider:
    provider = _normalized_provider(settings.provider)
    if settings.timeoutMs <= 0:
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message="EMBEDDING_TIMEOUT_MS must be positive.",
        )
    if settings.dimensions <= 0:
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message="EMBEDDING_DIMENSIONS must be positive.",
        )
    if provider in {"hash", "local_hash"}:
        return HashEmbeddingProvider(dimensions=settings.dimensions)
    if provider in {"openai_compatible", "local", "local_openai_compatible"}:
        if not settings.baseUrl:
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="EMBEDDING_BASE_URL is required.",
            )
        return LocalOpenAICompatibleEmbeddingProvider(
            base_url=settings.baseUrl,
            model=_required_model(settings, default="nomic-embed-text"),
            timeout_seconds=settings.timeoutMs / 1000,
            dimensions=settings.dimensions,
            api_key=settings.apiKey,
            embeddings_path=settings.embeddingsPath,
        )
    if provider == "ollama":
        return OllamaEmbeddingProvider(
            base_url=settings.baseUrl,
            model=settings.model,
            timeout_seconds=settings.timeoutMs / 1000,
            dimensions=settings.dimensions,
            api_key=settings.apiKey,
            embeddings_path=settings.embeddingsPath,
        )
    if provider == "openai":
        api_key = _api_key_with_default_env(
            settings,
            default_api_key_env=OpenAIEmbeddingProvider.default_api_key_env,
        )
        if not api_key:
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="OPENAI_API_KEY is required for OpenAI embedding provider.",
            )
        return OpenAIEmbeddingProvider(
            api_key=api_key,
            base_url=settings.baseUrl,
            model=settings.model,
            timeout_seconds=settings.timeoutMs / 1000,
            dimensions=settings.dimensions,
            embeddings_path=settings.embeddingsPath,
        )
    raise AppError(
        code=ErrorCode.RAG_PROVIDER_ERROR,
        message=f"EMBEDDING_PROVIDER is not supported: {settings.provider}",
    )


def build_embedding_provider_from_env(
    env: Mapping[str, str],
) -> TextEmbeddingProvider:
    return build_embedding_provider(EmbeddingProviderSettings.from_mapping(env))


def _normalized_provider(provider: str) -> str:
    return provider.strip().lower().replace("-", "_")


def _required_model(
    settings: EmbeddingProviderSettings,
    *,
    default: str,
) -> str:
    model = settings.model or default
    if not model.strip():
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message="EMBEDDING_MODEL is required.",
        )
    return model


def _api_key_with_default_env(
    settings: EmbeddingProviderSettings,
    *,
    default_api_key_env: str,
) -> str | None:
    if settings.apiKey:
        return settings.apiKey
    env = settings.sourceEnv or {}
    return env.get(settings.apiKeyEnv or default_api_key_env)


def _api_key_from_env(
    env_key: str | None,
    env: Mapping[str, str],
) -> str | None:
    if env_key is None:
        return None
    return env.get(env_key)


def _default_dimensions(provider: str) -> int:
    normalized = _normalized_provider(provider)
    if normalized == "openai":
        return OpenAIEmbeddingProvider.default_dimensions
    if normalized == "ollama":
        return OllamaEmbeddingProvider.default_dimensions
    return 384


def _int_from_mapping(
    data: Mapping[str, str],
    key: str,
    *,
    fallback_key: str | None = None,
    default: int,
) -> int:
    value = data.get(key)
    if value is None and fallback_key is not None:
        value = data.get(fallback_key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message=f"{key} must be an integer.",
        ) from exc
