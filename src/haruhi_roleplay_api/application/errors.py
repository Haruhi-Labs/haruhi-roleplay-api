"""Stable application errors for API responses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from haruhi_roleplay_api.domain import DTOValidationError


class ErrorCode(StrEnum):
    AUTH_INVALID_API_KEY = "AUTH_INVALID_API_KEY"
    AUTH_PERMISSION_DENIED = "AUTH_PERMISSION_DENIED"
    ACCESS_TOKEN_NOT_FOUND = "ACCESS_TOKEN_NOT_FOUND"
    ACCESS_TOKEN_QUOTA_EXCEEDED = "ACCESS_TOKEN_QUOTA_EXCEEDED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PERSONA_NOT_FOUND = "PERSONA_NOT_FOUND"
    PERSONA_MODE_NOT_FOUND = "PERSONA_MODE_NOT_FOUND"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_PROVIDER_ERROR = "SESSION_PROVIDER_ERROR"
    RAG_DOCUMENT_NOT_FOUND = "RAG_DOCUMENT_NOT_FOUND"
    RAG_PROVIDER_ERROR = "RAG_PROVIDER_ERROR"
    RAG_INGEST_FAILED = "RAG_INGEST_FAILED"
    MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_RATE_LIMIT = "MODEL_RATE_LIMIT"
    MEMORY_NOT_FOUND = "MEMORY_NOT_FOUND"
    MEMORY_ACCESS_DENIED = "MEMORY_ACCESS_DENIED"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


ERROR_STATUS: Mapping[ErrorCode, int] = {
    ErrorCode.AUTH_INVALID_API_KEY: 401,
    ErrorCode.AUTH_PERMISSION_DENIED: 403,
    ErrorCode.ACCESS_TOKEN_NOT_FOUND: 404,
    ErrorCode.ACCESS_TOKEN_QUOTA_EXCEEDED: 429,
    ErrorCode.RATE_LIMIT_EXCEEDED: 429,
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.PERSONA_NOT_FOUND: 404,
    ErrorCode.PERSONA_MODE_NOT_FOUND: 404,
    ErrorCode.SESSION_NOT_FOUND: 404,
    ErrorCode.SESSION_EXPIRED: 410,
    ErrorCode.SESSION_PROVIDER_ERROR: 502,
    ErrorCode.RAG_DOCUMENT_NOT_FOUND: 404,
    ErrorCode.RAG_PROVIDER_ERROR: 502,
    ErrorCode.RAG_INGEST_FAILED: 500,
    ErrorCode.MODEL_PROVIDER_ERROR: 502,
    ErrorCode.MODEL_TIMEOUT: 504,
    ErrorCode.MODEL_RATE_LIMIT: 429,
    ErrorCode.MEMORY_NOT_FOUND: 404,
    ErrorCode.MEMORY_ACCESS_DENIED: 403,
    ErrorCode.SAFETY_BLOCKED: 400,
    ErrorCode.INTERNAL_ERROR: 500,
}

DEFAULT_MESSAGES: Mapping[ErrorCode, str] = {
    ErrorCode.AUTH_INVALID_API_KEY: "Invalid API key.",
    ErrorCode.AUTH_PERMISSION_DENIED: "Permission denied.",
    ErrorCode.ACCESS_TOKEN_NOT_FOUND: "Access token was not found.",
    ErrorCode.ACCESS_TOKEN_QUOTA_EXCEEDED: "Access token quota has been exhausted.",
    ErrorCode.RATE_LIMIT_EXCEEDED: "Rate limit exceeded.",
    ErrorCode.VALIDATION_ERROR: "Request validation failed.",
    ErrorCode.PERSONA_NOT_FOUND: "Character was not found.",
    ErrorCode.PERSONA_MODE_NOT_FOUND: "Persona preset was not found.",
    ErrorCode.SESSION_NOT_FOUND: "Session was not found.",
    ErrorCode.SESSION_EXPIRED: "Session has expired.",
    ErrorCode.SESSION_PROVIDER_ERROR: "Session provider failed.",
    ErrorCode.RAG_DOCUMENT_NOT_FOUND: "RAG document was not found.",
    ErrorCode.RAG_PROVIDER_ERROR: "RAG provider failed.",
    ErrorCode.RAG_INGEST_FAILED: "RAG ingest failed.",
    ErrorCode.MODEL_PROVIDER_ERROR: "Model provider failed.",
    ErrorCode.MODEL_TIMEOUT: "Model provider timed out.",
    ErrorCode.MODEL_RATE_LIMIT: "Model provider rate limit exceeded.",
    ErrorCode.MEMORY_NOT_FOUND: "Memory was not found.",
    ErrorCode.MEMORY_ACCESS_DENIED: "Memory access denied.",
    ErrorCode.SAFETY_BLOCKED: "Request was blocked by safety policy.",
    ErrorCode.INTERNAL_ERROR: "Internal server error.",
}


@dataclass(frozen=True, kw_only=True)
class AppError(Exception):
    code: ErrorCode
    message: str | None = None
    status: int | None = None
    details: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, self.public_message)

    @property
    def public_message(self) -> str:
        return self.message or DEFAULT_MESSAGES[self.code]

    @property
    def http_status(self) -> int:
        return self.status or ERROR_STATUS[self.code]


def validation_error_from_exception(exc: DTOValidationError) -> AppError:
    return AppError(code=ErrorCode.VALIDATION_ERROR, message=str(exc))


def app_error_from_exception(exc: Exception) -> AppError:
    if isinstance(exc, AppError):
        return exc
    if isinstance(exc, DTOValidationError):
        return validation_error_from_exception(exc)
    return AppError(code=ErrorCode.INTERNAL_ERROR)
