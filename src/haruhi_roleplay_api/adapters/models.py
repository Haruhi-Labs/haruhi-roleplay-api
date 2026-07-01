"""Fake model provider for tests and local orchestration checks."""

from __future__ import annotations

from haruhi_roleplay_api.domain import ModelRequest, ModelResponse, ModelUsage


class FakeModelProvider:
    provider_name = "fake"

    def generate(self, request: ModelRequest) -> ModelResponse:
        last_user_message = _last_user_message(request)
        reply = f"[fake:{request.model}] {last_user_message}"
        usage = ModelUsage(
            promptTokens=sum(
                _fake_token_count(message.content) for message in request.messages
            ),
            completionTokens=_fake_token_count(reply),
        )
        return ModelResponse(
            reply=reply,
            provider=self.provider_name,
            model=request.model,
            usage=usage,
            debug={
                "modelProvider": self.provider_name,
                "model": request.model,
                "messageCount": len(request.messages),
            },
        )


def _last_user_message(request: ModelRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            return message.content
    return request.messages[-1].content


def _fake_token_count(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
