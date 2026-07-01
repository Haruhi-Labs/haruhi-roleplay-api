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

