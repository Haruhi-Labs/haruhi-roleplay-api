"""Model provider ports."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from haruhi_roleplay_api.domain import (
    GenerationConfig,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
)


class ChatModelProvider(Protocol):
    @property
    def provider_name(self) -> str:
        """Stable provider name for debug trace."""

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate one non-streaming reply."""

    def stream(self, request: ModelRequest) -> Iterable[ModelStreamEvent]:
        """Generate a reply as provider stream events."""


class ChatModelRouter(Protocol):
    def generate(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ) -> ModelResponse:
        """Route messages to one configured model provider."""

    def stream(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ) -> Iterable[ModelStreamEvent]:
        """Route messages to one configured streaming model provider."""
