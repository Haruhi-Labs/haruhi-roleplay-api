"""Concrete embedding provider adapters."""

from haruhi_roleplay_api.adapters.embeddings.hash import HashEmbeddingProvider
from haruhi_roleplay_api.adapters.embeddings.ollama import OllamaEmbeddingProvider
from haruhi_roleplay_api.adapters.embeddings.openai import OpenAIEmbeddingProvider
from haruhi_roleplay_api.adapters.embeddings.openai_compatible import (
    LocalOpenAICompatibleEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)

__all__ = [
    "HashEmbeddingProvider",
    "LocalOpenAICompatibleEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "OpenAICompatibleEmbeddingProvider",
    "OpenAIEmbeddingProvider",
]
