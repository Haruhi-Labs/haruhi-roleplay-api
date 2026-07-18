"""OpenAI-compatible embeddings provider."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Mapping

from haruhi_roleplay_api.application.errors import AppError, ErrorCode


_MAX_REQUEST_ATTEMPTS = 4
_RETRY_BACKOFF_SECONDS = (0.5, 1.0, 2.0)
_RETRYABLE_HTTP_STATUS = {408, 409, 429, 500, 502, 503, 504}


class OpenAICompatibleEmbeddingProvider:
    provider_name = "local-openai-compatible-embedding"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        dimensions: int,
        api_key: str | None = None,
        provider_name: str | None = None,
        embeddings_path: str | None = None,
    ) -> None:
        if not base_url.strip():
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="EMBEDDING_BASE_URL is required.",
            )
        if not model.strip():
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="EMBEDDING_MODEL is required.",
            )
        if timeout_seconds <= 0:
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="EMBEDDING_TIMEOUT_MS must be positive.",
            )
        if dimensions <= 0:
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="EMBEDDING_DIMENSIONS must be positive.",
            )
        self._endpoint = _embeddings_endpoint(
            base_url,
            embeddings_path=embeddings_path,
        )
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key
        self._dimensions = dimensions
        if provider_name is not None and provider_name.strip():
            self.provider_name = provider_name.strip()
        self._error_label = f"{self.provider_name} provider"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        response_data = self._request_embeddings(text)
        return _embedding_from_mapping(
            response_data,
            dimensions=self._dimensions,
            error_label=self._error_label,
        )

    def embed_many(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        response_data = self._request_embeddings(list(texts))
        return _embeddings_from_mapping(
            response_data,
            expected_count=len(texts),
            dimensions=self._dimensions,
            error_label=self._error_label,
        )

    def _request_embeddings(self, input_value: str | list[str]) -> Mapping[str, Any]:
        payload = {
            "model": self._model,
            "input": input_value,
            "dimensions": self._dimensions,
            "encoding_format": "float",
        }
        response_data: Any = None
        for attempt in range(_MAX_REQUEST_ATTEMPTS):
            http_request = urllib.request.Request(
                self._endpoint,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=self._headers(),
                method="POST",
            )
            try:
                with urllib.request.urlopen(
                    http_request,
                    timeout=self._timeout_seconds,
                ) as response:
                    response_data = json.loads(response.read().decode("utf-8"))
                break
            except (TimeoutError, socket.timeout) as exc:
                if _retry_request(attempt):
                    continue
                raise AppError(
                    code=ErrorCode.RAG_PROVIDER_ERROR,
                    message=f"{self._error_label} timed out.",
                ) from exc
            except urllib.error.HTTPError as exc:
                if _retry_http_error(exc.code, attempt):
                    continue
                raise AppError(
                    code=ErrorCode.RAG_PROVIDER_ERROR,
                    message=f"{self._error_label} failed with HTTP {exc.code}.",
                ) from exc
            except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
                if _retry_request(attempt):
                    continue
                raise AppError(
                    code=ErrorCode.RAG_PROVIDER_ERROR,
                    message=f"{self._error_label} request failed.",
                ) from exc

        if not isinstance(response_data, Mapping):
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message=f"{self._error_label} response was invalid.",
            )
        return response_data

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers


def _retry_http_error(status: int, attempt: int) -> bool:
    # DashScope 偶尔会把可恢复的推理失败返回为 400；只额外重放一次，
    # 避免永久参数错误拖成长时间重试。标准限流和服务错误使用完整重试预算。
    if status == 400:
        return attempt == 0 and _retry_request(attempt)
    if status not in _RETRYABLE_HTTP_STATUS:
        return False
    return _retry_request(attempt)


def _retry_request(attempt: int) -> bool:
    if attempt >= len(_RETRY_BACKOFF_SECONDS):
        return False
    time.sleep(_RETRY_BACKOFF_SECONDS[attempt])
    return True


LocalOpenAICompatibleEmbeddingProvider = OpenAICompatibleEmbeddingProvider


def _embeddings_endpoint(
    base_url: str,
    *,
    embeddings_path: str | None = None,
) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/embeddings"):
        return normalized
    if embeddings_path is not None and embeddings_path.strip():
        return f"{normalized}/{embeddings_path.strip('/')}"
    if normalized.endswith("/v1"):
        return f"{normalized}/embeddings"
    return f"{normalized}/v1/embeddings"


def _embedding_from_mapping(
    data: Mapping[str, Any],
    *,
    dimensions: int,
    error_label: str,
) -> tuple[float, ...]:
    try:
        raw_embedding = data["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message=f"{error_label} response was invalid.",
        ) from exc
    if not isinstance(raw_embedding, list):
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message=f"{error_label} response was invalid.",
        )
    embedding = tuple(float(value) for value in raw_embedding)
    if len(embedding) != dimensions:
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message=(
                f"{error_label} returned {len(embedding)} dimensions; "
                f"expected {dimensions}."
            ),
        )
    return embedding


def _embeddings_from_mapping(
    data: Mapping[str, Any],
    *,
    expected_count: int,
    dimensions: int,
    error_label: str,
) -> tuple[tuple[float, ...], ...]:
    raw_items = data.get("data")
    if not isinstance(raw_items, list) or len(raw_items) != expected_count:
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message=f"{error_label} response was invalid.",
        )
    if all(isinstance(item, Mapping) and isinstance(item.get("index"), int) for item in raw_items):
        raw_items = sorted(raw_items, key=lambda item: int(item["index"]))
    embeddings: list[tuple[float, ...]] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message=f"{error_label} response was invalid.",
            )
        embeddings.append(
            _embedding_from_mapping(
                {"data": [item]},
                dimensions=dimensions,
                error_label=error_label,
            )
        )
    return tuple(embeddings)
