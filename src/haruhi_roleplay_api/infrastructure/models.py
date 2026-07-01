"""Model provider configuration and factories."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from haruhi_roleplay_api.adapters import (
    FakeModelProvider,
    LocalOpenAICompatibleModelProvider,
)
from haruhi_roleplay_api.application import ModelRouter
from haruhi_roleplay_api.application.errors import AppError, ErrorCode


@dataclass(frozen=True, kw_only=True)
class ModelProviderSettings:
    provider: str = "fake"
    model: str = "fake-roleplay-model"
    baseUrl: str | None = None
    timeoutMs: int = 60000
    apiKey: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, str]) -> "ModelProviderSettings":
        provider = data.get("MODEL_PROVIDER", "fake")
        default_model = "fake-roleplay-model" if provider == "fake" else ""
        timeout_raw = data.get("MODEL_TIMEOUT_MS", "60000")
        try:
            timeout_ms = int(timeout_raw)
        except ValueError as exc:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message="MODEL_TIMEOUT_MS must be an integer.",
            ) from exc
        return cls(
            provider=provider,
            model=data.get("MODEL_NAME", default_model),
            baseUrl=data.get("MODEL_BASE_URL"),
            timeoutMs=timeout_ms,
            apiKey=data.get("MODEL_API_KEY"),
        )

    @classmethod
    def from_env(cls) -> "ModelProviderSettings":
        return cls.from_mapping(os.environ)


def build_model_router(settings: ModelProviderSettings) -> ModelRouter:
    if settings.provider == "fake":
        return ModelRouter(
            provider=FakeModelProvider(),
            default_model=settings.model,
            allowed_models=(settings.model,),
        )
    if settings.provider in {"local", "openai_compatible"}:
        if not settings.baseUrl:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message="MODEL_BASE_URL is required for local model provider.",
            )
        if not settings.model:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message="MODEL_NAME is required for local model provider.",
            )
        return ModelRouter(
            provider=LocalOpenAICompatibleModelProvider(
                base_url=settings.baseUrl,
                timeout_seconds=settings.timeoutMs / 1000,
                api_key=settings.apiKey,
            ),
            default_model=settings.model,
            allowed_models=(settings.model,),
        )
    raise AppError(
        code=ErrorCode.MODEL_PROVIDER_ERROR,
        message=f"MODEL_PROVIDER is not supported: {settings.provider}",
    )
