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


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None or not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value.strip()
