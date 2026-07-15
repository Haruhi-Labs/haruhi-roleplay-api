"""Deterministic local embedding provider."""

from __future__ import annotations

import hashlib
import math


class HashEmbeddingProvider:
    provider_name = "hash-embedding"

    def __init__(self, *, dimensions: int = 384) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        values = [0.0] * self._dimensions
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            values[bucket] += sign
        return _normalize(values)

    def embed_many(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple(self.embed(text) for text in texts)


def _tokens(text: str) -> tuple[str, ...]:
    normalized = text.lower()
    terms = [term for term in normalized.split() if term]
    chars = [char for char in normalized if not char.isspace()]
    bigrams = ["".join(chars[index : index + 2]) for index in range(len(chars) - 1)]
    return tuple(terms + chars + bigrams)


def _normalize(values: list[float]) -> tuple[float, ...]:
    magnitude = math.sqrt(sum(value * value for value in values))
    if magnitude == 0:
        return tuple(values)
    return tuple(value / magnitude for value in values)
