"""Model provider ports."""

from __future__ import annotations

from typing import Protocol

from haruhi_roleplay_api.domain import ModelRequest, ModelResponse


class ChatModelProvider(Protocol):
    @property
    def provider_name(self) -> str:
        """Stable provider name for debug trace."""

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate one non-streaming reply."""

