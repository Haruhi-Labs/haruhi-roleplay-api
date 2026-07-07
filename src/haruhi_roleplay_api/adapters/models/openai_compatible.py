"""OpenAI-compatible chat completions model provider."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import Iterable
from typing import Any, Mapping

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelUsage,
)


class OpenAICompatibleModelProvider:
    provider_name = "local-openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        api_key: str | None = None,
        provider_name: str | None = None,
        chat_completions_path: str | None = None,
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
        self._endpoint = _chat_completions_endpoint(
            base_url,
            chat_completions_path=chat_completions_path,
        )
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key
        if provider_name is not None and provider_name.strip():
            self.provider_name = provider_name.strip()
        self._error_label = _error_label_for_provider(provider_name)

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
                message=f"{self._error_label} timed out.",
            ) from exc
        except urllib.error.HTTPError as exc:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message=f"{self._error_label} failed with HTTP {exc.code}.",
            ) from exc
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message=f"{self._error_label} request failed.",
            ) from exc

        return _response_from_mapping(
            response_data,
            request,
            provider_name=self.provider_name,
            error_label=self._error_label,
        )

    def stream(self, request: ModelRequest) -> Iterable[ModelStreamEvent]:
        payload = {**_request_payload(request), "stream": True}
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
                yield from _stream_response_events(
                    response,
                    request,
                    provider_name=self.provider_name,
                    error_label=self._error_label,
                )
        except (TimeoutError, socket.timeout) as exc:
            raise AppError(
                code=ErrorCode.MODEL_TIMEOUT,
                message=f"{self._error_label} timed out.",
            ) from exc
        except urllib.error.HTTPError as exc:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message=f"{self._error_label} failed with HTTP {exc.code}.",
            ) from exc
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise AppError(
                code=ErrorCode.MODEL_PROVIDER_ERROR,
                message=f"{self._error_label} request failed.",
            ) from exc

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers


LocalOpenAICompatibleModelProvider = OpenAICompatibleModelProvider


def _chat_completions_endpoint(
    base_url: str,
    *,
    chat_completions_path: str | None = None,
) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if chat_completions_path is not None and chat_completions_path.strip():
        return f"{normalized}/{chat_completions_path.strip('/')}"
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _error_label_for_provider(provider_name: str | None) -> str:
    if provider_name is None or not provider_name.strip():
        return "Local model provider"
    return f"{provider_name.strip()} model provider"


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


def _stream_response_events(
    response: Any,
    request: ModelRequest,
    *,
    provider_name: str,
    error_label: str,
) -> Iterable[ModelStreamEvent]:
    deltas: list[str] = []
    usage: ModelUsage | None = None

    for line in _iter_sse_lines(response):
        if line == "[DONE]":
            break
        data = json.loads(line)
        delta = _delta_from_stream_mapping(data)
        if delta:
            deltas.append(delta)
            yield ModelStreamEvent(event="delta", delta=delta)
        if isinstance(data.get("usage"), Mapping):
            usage = _usage_from_mapping(data["usage"], fallback_completion="")

    reply = "".join(deltas)
    if not reply.strip():
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=f"{error_label} response was invalid.",
        )

    final_usage = usage or ModelUsage(
        promptTokens=sum(
            _fake_token_count(message.content) for message in request.messages
        ),
        completionTokens=_fake_token_count(reply),
    )
    yield ModelStreamEvent(
        event="done",
        response=ModelResponse(
            reply=reply,
            provider=provider_name,
            model=request.model,
            usage=final_usage,
            debug={
                "modelProvider": provider_name,
                "model": request.model,
            },
        ),
    )


def _iter_sse_lines(response: Any):
    for raw_line in response:
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        yield line.removeprefix("data:").strip()


def _delta_from_stream_mapping(data: Mapping[str, Any]) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        return ""
    delta = first_choice.get("delta", {})
    if isinstance(delta, Mapping) and delta.get("content") is not None:
        return str(delta["content"])
    message = first_choice.get("message", {})
    if isinstance(message, Mapping) and message.get("content") is not None:
        return str(message["content"])
    return ""


def _response_from_mapping(
    data: Mapping[str, Any],
    request: ModelRequest,
    *,
    provider_name: str,
    error_label: str,
) -> ModelResponse:
    try:
        reply = str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=f"{error_label} response was invalid.",
        ) from exc

    usage_data = data.get("usage", {})
    usage = _usage_from_mapping(usage_data, fallback_completion=reply)
    return ModelResponse(
        reply=reply,
        provider=provider_name,
        model=request.model,
        usage=usage,
        debug={
            "modelProvider": provider_name,
            "model": request.model,
        },
    )


def _usage_from_mapping(
    data: Any,
    *,
    fallback_completion: str,
) -> ModelUsage:
    usage_data = data if isinstance(data, Mapping) else {}
    return ModelUsage(
        promptTokens=int(usage_data.get("prompt_tokens", 0)),
        completionTokens=int(
            usage_data.get("completion_tokens", _fake_token_count(fallback_completion))
        ),
    )


def _fake_token_count(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
