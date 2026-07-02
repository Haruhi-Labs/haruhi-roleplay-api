"""Model routing use cases."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    GenerationConfig,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
)
from haruhi_roleplay_api.ports import ChatModelProvider


@dataclass(frozen=True, kw_only=True)
class ModelRouteDecision:
    provider: str
    model: str

    def to_debug_trace(self) -> dict[str, str]:
        return {
            "modelProvider": self.provider,
            "model": self.model,
        }


class ModelRouter:
    def __init__(
        self,
        provider: ChatModelProvider,
        *,
        default_model: str = "fake-roleplay-model",
        allowed_models: tuple[str, ...] = ("fake-roleplay-model",),
    ) -> None:
        self._provider = provider
        self._default_model = default_model
        self._allowed_models = allowed_models

    def route(
        self,
        generation: GenerationConfig | None = None,
    ) -> ModelRouteDecision:
        selected_model = (
            generation.model if generation and generation.model else self._default_model
        )
        if selected_model not in self._allowed_models:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message=f"Model alias is not configured: {selected_model}",
            )
        return ModelRouteDecision(
            provider=self._provider.provider_name,
            model=selected_model,
        )

    def generate(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ) -> ModelResponse:
        decision = self.route(generation)
        return self._provider.generate(
            ModelRequest(
                messages=messages,
                model=decision.model,
                generation=generation,
            )
        )

    def stream(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ) -> Iterable[ModelStreamEvent]:
        decision = self.route(generation)
        return self._provider.stream(
            ModelRequest(
                messages=messages,
                model=decision.model,
                generation=generation,
            )
        )
