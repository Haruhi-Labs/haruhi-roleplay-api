"""Model provider ports."""

from __future__ import annotations

from typing import Protocol

from haruhi_roleplay_api.domain import (
    GenerationConfig,
    ModelMessage,
    ModelRequest,
    ModelResponse,
)


class ChatModelProvider(Protocol):
    @property
    def provider_name(self) -> str:
        """Stable provider name for debug trace."""

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate one non-streaming reply."""


class ChatModelRouter(Protocol):
    def generate(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ) -> ModelResponse:
        """Route messages to one configured model provider."""
