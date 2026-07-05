"""OpenAI model provider via the official chat completions endpoint."""

from __future__ import annotations

from haruhi_roleplay_api.adapters.models.openai_compatible import (
    OpenAICompatibleModelProvider,
)


class OpenAIModelProvider(OpenAICompatibleModelProvider):
    provider_name = "openai"
    default_base_url = "https://api.openai.com/v1"
    default_chat_completions_path = "chat/completions"
    default_api_key_env = "OPENAI_API_KEY"

    def __init__(
        self,
        *,
        base_url: str | None,
        timeout_seconds: float,
        api_key: str,
        chat_completions_path: str | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url or self.default_base_url,
            timeout_seconds=timeout_seconds,
            api_key=api_key,
            provider_name=self.provider_name,
            chat_completions_path=(
                chat_completions_path or self.default_chat_completions_path
            ),
        )
