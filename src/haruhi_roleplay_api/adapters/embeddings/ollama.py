"""Ollama embeddings provider via its OpenAI-compatible endpoint."""

from __future__ import annotations

from haruhi_roleplay_api.adapters.embeddings.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
)


class OllamaEmbeddingProvider(OpenAICompatibleEmbeddingProvider):
    provider_name = "ollama-embedding"
    default_base_url = "http://localhost:11434/v1"
    default_model = "nomic-embed-text"
    default_dimensions = 768

    def __init__(
        self,
        *,
        timeout_seconds: float,
        model: str | None = None,
        dimensions: int | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        embeddings_path: str | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url or self.default_base_url,
            model=model or self.default_model,
            timeout_seconds=timeout_seconds,
            dimensions=dimensions or self.default_dimensions,
            api_key=api_key,
            provider_name=self.provider_name,
            embeddings_path=embeddings_path,
        )
