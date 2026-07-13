"""Gemini model provider via Google's OpenAI compatibility endpoint."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import Iterable
from typing import Any

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.adapters.models.openai_compatible import (
    OpenAICompatibleModelProvider,
    _response_from_mapping,
    _stream_response_events,
)
from haruhi_roleplay_api.domain import ModelRequest, ModelResponse, ModelStreamEvent


class GeminiModelProvider(OpenAICompatibleModelProvider):
    provider_name = "gemini"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
    default_chat_completions_path = "chat/completions"
    default_api_key_env = "GEMINI_API_KEY"

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

    def generate(self, request: ModelRequest) -> ModelResponse:
        payload = _gemini_request_payload(request)
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
        payload = {**_gemini_request_payload(request), "stream": True}
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


def _gemini_request_payload(request: ModelRequest) -> dict[str, Any]:
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
            }
        )
    return payload
