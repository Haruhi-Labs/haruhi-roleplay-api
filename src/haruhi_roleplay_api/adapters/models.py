"""Fake model provider for tests and local orchestration checks."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Mapping

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
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


class LocalOpenAICompatibleModelProvider:
    provider_name = "local-openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        api_key: str | None = None,
    ) -> None:
        if not base_url.strip():
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message="MODEL_BASE_URL is required for local model provider.",
            )
        if timeout_seconds <= 0:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message="MODEL_TIMEOUT_MS must be positive.",
            )
        self._endpoint = _chat_completions_endpoint(base_url)
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key

    def generate(self, request: ModelRequest) -> ModelResponse:
        payload = _request_payload(request)
        http_request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                http_request,
                timeout=self._timeout_seconds,
            ) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, socket.timeout) as exc:
            raise AppError(
                code=ErrorCode.MODEL_TIMEOUT,
                message="Local model provider timed out.",
            ) from exc
        except urllib.error.HTTPError as exc:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message=f"Local model provider failed with HTTP {exc.code}.",
            ) from exc
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message="Local model provider request failed.",
            ) from exc

        return _response_from_mapping(response_data, request)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers


def _chat_completions_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _request_payload(request: ModelRequest) -> dict[str, Any]:
    generation = request.generation
    payload: dict[str, Any] = {
        "model": request.model,
        "messages": [message.to_mapping() for message in request.messages],
    }
    if generation is not None:
        payload.update(
            {
                "temperature": generation.temperature,
                "max_tokens": generation.maxTokens,
                "top_p": generation.topP,
                "presence_penalty": generation.presencePenalty,
                "frequency_penalty": generation.frequencyPenalty,
            }
        )
    return payload


def _response_from_mapping(
    data: Mapping[str, Any],
    request: ModelRequest,
) -> ModelResponse:
    try:
        reply = str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message="Local model provider response was invalid.",
        ) from exc

    usage_data = data.get("usage", {})
    usage = ModelUsage(
        promptTokens=int(usage_data.get("prompt_tokens", 0)),
        completionTokens=int(
            usage_data.get("completion_tokens", _fake_token_count(reply))
        ),
    )
    return ModelResponse(
        reply=reply,
        provider=LocalOpenAICompatibleModelProvider.provider_name,
        model=request.model,
        usage=usage,
        debug={
            "modelProvider": LocalOpenAICompatibleModelProvider.provider_name,
            "model": request.model,
        },
    )
