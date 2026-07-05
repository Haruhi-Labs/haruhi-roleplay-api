"""OpenAI embeddings provider preset."""

from __future__ import annotations

from haruhi_roleplay_api.adapters.embeddings.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
)


class OpenAIEmbeddingProvider(OpenAICompatibleEmbeddingProvider):
    provider_name = "openai-embedding"
    default_base_url = "https://api.openai.com/v1"
    default_model = "text-embedding-3-small"
    default_dimensions = 1536
    default_api_key_env = "OPENAI_API_KEY"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        model: str | None = None,
        dimensions: int | None = None,
        base_url: str | None = None,
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
