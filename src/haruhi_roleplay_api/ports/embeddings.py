"""Embedding provider ports."""

from __future__ import annotations

from typing import Protocol


class TextEmbeddingProvider(Protocol):
    @property
    def provider_name(self) -> str:
        """Stable provider name for debug and wiring."""

    @property
    def dimensions(self) -> int:
        """Expected embedding vector dimensions."""

    def embed(self, text: str) -> tuple[float, ...]:
        """Embed one text into a vector."""
