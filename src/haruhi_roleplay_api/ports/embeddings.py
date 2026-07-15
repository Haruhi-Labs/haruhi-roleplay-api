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

    def embed_many(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        """一次嵌入多段文本，并保持输入顺序。"""
