"""OpenAI-compatible embeddings provider."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Mapping

from haruhi_roleplay_api.application.errors import AppError, ErrorCode


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
        payload = {
            "model": self._model,
            "input": text,
            "dimensions": self._dimensions,
            "encoding_format": "float",
        }
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
        except (TimeoutError, socket.timeout) as exc:
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message=f"{self._error_label} timed out.",
            ) from exc
        except urllib.error.HTTPError as exc:
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message=f"{self._error_label} failed with HTTP {exc.code}.",
            ) from exc
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message=f"{self._error_label} request failed.",
            ) from exc

        return _embedding_from_mapping(
            response_data,
            dimensions=self._dimensions,
            error_label=self._error_label,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers


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
