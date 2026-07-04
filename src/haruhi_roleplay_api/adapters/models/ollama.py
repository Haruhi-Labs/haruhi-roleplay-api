"""Ollama model provider via its OpenAI-compatible endpoint."""

from __future__ import annotations

from haruhi_roleplay_api.adapters.models.openai_compatible import (
    OpenAICompatibleModelProvider,
)


class OllamaModelProvider(OpenAICompatibleModelProvider):
    provider_name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        api_key: str | None = None,
        chat_completions_path: str | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            api_key=api_key,
            provider_name=self.provider_name,
            chat_completions_path=chat_completions_path,
        )
