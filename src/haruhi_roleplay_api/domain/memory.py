"""Long-term memory domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

from haruhi_roleplay_api.domain.chat import (
    AppId,
    CharacterId,
    DTOValidationError,
    PersonaModeId,
    UserId,
)


MemoryId = NewType("MemoryId", str)


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value


class MemoryType(StrEnum):
    USER_PREFERENCE = "user_preference"
    RELATIONSHIP = "relationship"
    ROLEPLAY_FACT = "roleplay_fact"
    SAFETY_PREFERENCE = "safety_preference"
    INTERACTION_SUMMARY = "interaction_summary"


@dataclass(frozen=True, kw_only=True)
class MemoryItem:
    memoryId: MemoryId
    appId: AppId
    userId: UserId
    characterId: CharacterId
    type: MemoryType
    content: str
    confidence: float
    createdAt: str
    updatedAt: str
    personaMode: PersonaModeId | None = None

    def __post_init__(self) -> None:
        _require_non_empty(str(self.memoryId), "memoryId")
        _require_non_empty(str(self.appId), "appId")
        _require_non_empty(str(self.userId), "userId")
        _require_non_empty(str(self.characterId), "characterId")
        if self.personaMode is not None:
            _require_non_empty(str(self.personaMode), "personaMode")
        if not isinstance(self.type, MemoryType):
            raise DTOValidationError("type must be MemoryType")
        _require_non_empty(self.content, "content")
        if not 0 <= self.confidence <= 1:
            raise DTOValidationError("confidence must be between 0 and 1")
        _require_non_empty(self.createdAt, "createdAt")
        _require_non_empty(self.updatedAt, "updatedAt")

    def to_mapping(self) -> dict[str, object]:
        return {
            "memory_id": str(self.memoryId),
            "app_id": str(self.appId),
            "user_id": str(self.userId),
            "character_id": str(self.characterId),
            "persona_mode": (
                str(self.personaMode) if self.personaMode is not None else None
            ),
            "type": self.type.value,
            "content": self.content,
            "confidence": self.confidence,
            "created_at": self.createdAt,
            "updated_at": self.updatedAt,
        }


@dataclass(frozen=True, kw_only=True)
class MemoryQuery:
    appId: AppId
    userId: UserId
    characterId: CharacterId
    personaMode: PersonaModeId | None = None
    memoryTypes: tuple[MemoryType, ...] = ()
    limit: int = 50

    def __post_init__(self) -> None:
        _require_non_empty(str(self.appId), "appId")
        _require_non_empty(str(self.userId), "userId")
        _require_non_empty(str(self.characterId), "characterId")
        if self.personaMode is not None:
            _require_non_empty(str(self.personaMode), "personaMode")
        for memory_type in self.memoryTypes:
            if not isinstance(memory_type, MemoryType):
                raise DTOValidationError("memoryTypes must contain MemoryType")
        if self.limit <= 0:
            raise DTOValidationError("limit must be positive")


@dataclass(frozen=True, kw_only=True)
class MemoryDeleteCommand:
    memoryId: MemoryId
    appId: AppId
    userId: UserId
    characterId: CharacterId
    personaMode: PersonaModeId | None = None

    def __post_init__(self) -> None:
        _require_non_empty(str(self.memoryId), "memoryId")
        _require_non_empty(str(self.appId), "appId")
        _require_non_empty(str(self.userId), "userId")
        _require_non_empty(str(self.characterId), "characterId")
        if self.personaMode is not None:
            _require_non_empty(str(self.personaMode), "personaMode")


@dataclass(frozen=True, kw_only=True)
class MemoryReadPolicyInput:
    appId: AppId
    userId: UserId
    characterId: CharacterId
    personaMode: PersonaModeId
    enabled: bool
    allowedTypes: tuple[MemoryType, ...]
    maxItems: int

    def __post_init__(self) -> None:
        _require_non_empty(str(self.appId), "appId")
        _require_non_empty(str(self.userId), "userId")
        _require_non_empty(str(self.characterId), "characterId")
        _require_non_empty(str(self.personaMode), "personaMode")
        for memory_type in self.allowedTypes:
            if not isinstance(memory_type, MemoryType):
                raise DTOValidationError("allowedTypes must contain MemoryType")
        if self.maxItems <= 0:
            raise DTOValidationError("maxItems must be positive")
