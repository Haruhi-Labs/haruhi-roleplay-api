"""Session domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, NewType

from haruhi_roleplay_api.domain.chat import (
    AppId,
    CharacterId,
    DTOValidationError,
    PersonaModeId,
    SessionId,
    UserId,
)

MessageId = NewType("MessageId", str)


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value


class SessionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"


@dataclass(frozen=True, kw_only=True)
class Session:
    sessionId: SessionId
    appId: AppId
    userId: UserId
    characterId: CharacterId
    personaMode: PersonaModeId
    status: SessionStatus
    createdAt: str
    updatedAt: str

    def __post_init__(self) -> None:
        _require_non_empty(str(self.sessionId), "sessionId")
        _require_non_empty(str(self.appId), "appId")
        _require_non_empty(str(self.userId), "userId")
        _require_non_empty(str(self.characterId), "characterId")
        _require_non_empty(str(self.personaMode), "personaMode")
        _require_non_empty(self.createdAt, "createdAt")
        _require_non_empty(self.updatedAt, "updatedAt")


@dataclass(frozen=True, kw_only=True)
class SessionMessage:
    messageId: MessageId
    sessionId: SessionId
    role: str
    content: str
    createdAt: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty(str(self.messageId), "messageId")
        _require_non_empty(str(self.sessionId), "sessionId")
        if self.role not in {"user", "assistant"}:
            raise DTOValidationError(f"session message role is not supported: {self.role}")
        _require_non_empty(self.content, "content")
        _require_non_empty(self.createdAt, "createdAt")


@dataclass(frozen=True, kw_only=True)
class SessionAdminQuery:
    appId: str | None = None
    userId: str | None = None
    characterId: str | None = None
    status: SessionStatus | None = None
    limit: int = 100
    offset: int = 0

    def __post_init__(self) -> None:
        for field_name, value in (
            ("appId", self.appId),
            ("userId", self.userId),
            ("characterId", self.characterId),
        ):
            if value is not None:
                _require_non_empty(value, field_name)
        if self.status is not None and not isinstance(self.status, SessionStatus):
            raise DTOValidationError("status must be SessionStatus")
        if not 1 <= self.limit <= 200:
            raise DTOValidationError("limit must be between 1 and 200")
        if self.offset < 0:
            raise DTOValidationError("offset must be >= 0")


@dataclass(frozen=True, kw_only=True)
class SessionAdminItem:
    session: Session
    messageCount: int
    expiresAt: str | None = None

    def __post_init__(self) -> None:
        if self.messageCount < 0:
            raise DTOValidationError("messageCount must be >= 0")

    def to_mapping(self) -> dict[str, object]:
        return {
            "session_id": str(self.session.sessionId),
            "app_id": str(self.session.appId),
            "user_id": str(self.session.userId),
            "character_id": str(self.session.characterId),
            "persona_mode": str(self.session.personaMode),
            "status": self.session.status.value,
            "message_count": self.messageCount,
            "created_at": self.session.createdAt,
            "updated_at": self.session.updatedAt,
            "expires_at": self.expiresAt,
        }


@dataclass(frozen=True, kw_only=True)
class SessionAdminPage:
    total: int
    items: tuple[SessionAdminItem, ...]

    def __post_init__(self) -> None:
        if self.total < 0:
            raise DTOValidationError("total must be >= 0")
