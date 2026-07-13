"""访问令牌领域模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from haruhi_roleplay_api.domain.chat import DTOValidationError


class AccessTokenStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True, kw_only=True)
class AccessToken:
    tokenId: str
    appId: str | None
    name: str
    prefix: str
    status: AccessTokenStatus
    quotaTokens: int | None
    promptTokens: int
    completionTokens: int
    totalTokens: int
    createdAt: str
    expiresAt: str | None = None
    revokedAt: str | None = None
    lastUsedAt: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.tokenId, "accessToken.tokenId")
        if self.appId is not None:
            _require_non_empty(self.appId, "accessToken.appId")
        _require_non_empty(self.name, "accessToken.name")
        _require_non_empty(self.prefix, "accessToken.prefix")
        _require_non_empty(self.createdAt, "accessToken.createdAt")
        if self.quotaTokens is not None and self.quotaTokens <= 0:
            raise DTOValidationError("accessToken.quotaTokens must be positive")
        for field_name, value in (
            ("promptTokens", self.promptTokens),
            ("completionTokens", self.completionTokens),
            ("totalTokens", self.totalTokens),
        ):
            if value < 0:
                raise DTOValidationError(f"accessToken.{field_name} must be >= 0")
        if self.totalTokens != self.promptTokens + self.completionTokens:
            raise DTOValidationError(
                "accessToken.totalTokens must equal promptTokens + completionTokens"
            )

    @property
    def remainingTokens(self) -> int | None:
        if self.quotaTokens is None:
            return None
        return max(self.quotaTokens - self.totalTokens, 0)

    def to_mapping(self) -> dict[str, object]:
        return {
            "token_id": self.tokenId,
            "app_id": self.appId,
            "name": self.name,
            "prefix": self.prefix,
            "status": self.status.value,
            "quota_tokens": self.quotaTokens,
            "prompt_tokens": self.promptTokens,
            "completion_tokens": self.completionTokens,
            "total_tokens": self.totalTokens,
            "remaining_tokens": self.remainingTokens,
            "created_at": self.createdAt,
            "expires_at": self.expiresAt,
            "revoked_at": self.revokedAt,
            "last_used_at": self.lastUsedAt,
        }


@dataclass(frozen=True, kw_only=True)
class IssuedAccessToken:
    token: AccessToken
    secret: str

    def __post_init__(self) -> None:
        _require_non_empty(self.secret, "issuedAccessToken.secret")


@dataclass(frozen=True, kw_only=True)
class AccessTokenRequestLog:
    logId: str
    tokenId: str
    requestId: str
    method: str
    path: str
    statusCode: int
    durationMs: int
    promptTokens: int
    completionTokens: int
    totalTokens: int
    createdAt: str
    errorCode: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("logId", self.logId),
            ("tokenId", self.tokenId),
            ("requestId", self.requestId),
            ("method", self.method),
            ("path", self.path),
            ("createdAt", self.createdAt),
        ):
            _require_non_empty(value, f"accessTokenRequestLog.{field_name}")
        if not 100 <= self.statusCode <= 599:
            raise DTOValidationError(
                "accessTokenRequestLog.statusCode must be a valid HTTP status"
            )
        if self.durationMs < 0:
            raise DTOValidationError("accessTokenRequestLog.durationMs must be >= 0")
        if min(self.promptTokens, self.completionTokens, self.totalTokens) < 0:
            raise DTOValidationError("accessTokenRequestLog token usage must be >= 0")
        if self.totalTokens != self.promptTokens + self.completionTokens:
            raise DTOValidationError(
                "accessTokenRequestLog.totalTokens must equal promptTokens + completionTokens"
            )

    def to_mapping(self) -> dict[str, object]:
        return {
            "log_id": self.logId,
            "token_id": self.tokenId,
            "request_id": self.requestId,
            "method": self.method,
            "path": self.path,
            "status_code": self.statusCode,
            "duration_ms": self.durationMs,
            "prompt_tokens": self.promptTokens,
            "completion_tokens": self.completionTokens,
            "total_tokens": self.totalTokens,
            "error_code": self.errorCode,
            "created_at": self.createdAt,
        }


@dataclass(frozen=True, kw_only=True)
class AccessTokenUsageBucket:
    date: str
    requestCount: int
    errorCount: int
    promptTokens: int
    completionTokens: int
    totalTokens: int
    averageDurationMs: int

    def to_mapping(self) -> dict[str, object]:
        return {
            "date": self.date,
            "request_count": self.requestCount,
            "error_count": self.errorCount,
            "prompt_tokens": self.promptTokens,
            "completion_tokens": self.completionTokens,
            "total_tokens": self.totalTokens,
            "average_duration_ms": self.averageDurationMs,
        }


@dataclass(frozen=True, kw_only=True)
class AccessTokenServiceUsage:
    tokenId: str
    appId: str | None
    name: str
    status: AccessTokenStatus
    requestCount: int
    errorCount: int
    promptTokens: int
    completionTokens: int
    totalTokens: int
    averageDurationMs: int
    lastUsedAt: str | None

    @property
    def errorRate(self) -> float:
        if self.requestCount == 0:
            return 0.0
        return self.errorCount / self.requestCount

    def to_mapping(self) -> dict[str, object]:
        return {
            "token_id": self.tokenId,
            "app_id": self.appId,
            "name": self.name,
            "status": self.status.value,
            "request_count": self.requestCount,
            "error_count": self.errorCount,
            "error_rate": self.errorRate,
            "prompt_tokens": self.promptTokens,
            "completion_tokens": self.completionTokens,
            "total_tokens": self.totalTokens,
            "average_duration_ms": self.averageDurationMs,
            "last_used_at": self.lastUsedAt,
        }


@dataclass(frozen=True, kw_only=True)
class AccessTokenRouteUsage:
    method: str
    path: str
    requestCount: int
    errorCount: int
    totalTokens: int
    averageDurationMs: int

    def to_mapping(self) -> dict[str, object]:
        return {
            "method": self.method,
            "path": self.path,
            "request_count": self.requestCount,
            "error_count": self.errorCount,
            "total_tokens": self.totalTokens,
            "average_duration_ms": self.averageDurationMs,
        }


@dataclass(frozen=True, kw_only=True)
class AccessTokenUsageOverview:
    periodDays: int
    requestCount: int
    errorCount: int
    promptTokens: int
    completionTokens: int
    totalTokens: int
    averageDurationMs: int
    activeServiceCount: int
    daily: tuple[AccessTokenUsageBucket, ...]
    services: tuple[AccessTokenServiceUsage, ...]
    routes: tuple[AccessTokenRouteUsage, ...]

    @property
    def errorRate(self) -> float:
        if self.requestCount == 0:
            return 0.0
        return self.errorCount / self.requestCount

    def to_mapping(self) -> dict[str, object]:
        return {
            "period_days": self.periodDays,
            "request_count": self.requestCount,
            "error_count": self.errorCount,
            "error_rate": self.errorRate,
            "prompt_tokens": self.promptTokens,
            "completion_tokens": self.completionTokens,
            "total_tokens": self.totalTokens,
            "average_duration_ms": self.averageDurationMs,
            "active_service_count": self.activeServiceCount,
            "daily": [item.to_mapping() for item in self.daily],
            "services": [item.to_mapping() for item in self.services],
            "routes": [item.to_mapping() for item in self.routes],
        }


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None or not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value.strip()
