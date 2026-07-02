"""Long-term memory domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, NewType

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
    reason: str | None = None

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
        if self.reason is not None:
            _require_non_empty(self.reason, "reason")

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
            "reason": self.reason,
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


@dataclass(frozen=True, kw_only=True)
class MemoryWriteCandidate:
    type: MemoryType
    content: str
    reason: str
    confidence: float

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "MemoryWriteCandidate":
        if not isinstance(data, Mapping):
            raise DTOValidationError("memory_write candidate must be an object")
        return cls(
            type=_memory_type_from_value(data.get("type"), "memory_write.type"),
            content=_require_non_empty(data.get("content"), "memory_write.content"),
            reason=_require_non_empty(data.get("reason"), "memory_write.reason"),
            confidence=_confidence_from_value(data.get("confidence")),
        )

    def __post_init__(self) -> None:
        if not isinstance(self.type, MemoryType):
            raise DTOValidationError("type must be MemoryType")
        _require_non_empty(self.content, "content")
        _require_non_empty(self.reason, "reason")
        if not 0 <= self.confidence <= 1:
            raise DTOValidationError("confidence must be between 0 and 1")


@dataclass(frozen=True, kw_only=True)
class MemoryWritePolicyInput:
    appId: AppId
    userId: UserId
    characterId: CharacterId
    personaMode: PersonaModeId
    enabled: bool
    allowedTypes: tuple[MemoryType, ...]
    candidate: MemoryWriteCandidate

    def __post_init__(self) -> None:
        _require_non_empty(str(self.appId), "appId")
        _require_non_empty(str(self.userId), "userId")
        _require_non_empty(str(self.characterId), "characterId")
        _require_non_empty(str(self.personaMode), "personaMode")
        for memory_type in self.allowedTypes:
            if not isinstance(memory_type, MemoryType):
                raise DTOValidationError("allowedTypes must contain MemoryType")
        if not isinstance(self.candidate, MemoryWriteCandidate):
            raise DTOValidationError("candidate must be MemoryWriteCandidate")


@dataclass(frozen=True, kw_only=True)
class MemoryWriteCommand:
    appId: AppId
    userId: UserId
    characterId: CharacterId
    personaMode: PersonaModeId
    candidate: MemoryWriteCandidate

    def __post_init__(self) -> None:
        _require_non_empty(str(self.appId), "appId")
        _require_non_empty(str(self.userId), "userId")
        _require_non_empty(str(self.characterId), "characterId")
        _require_non_empty(str(self.personaMode), "personaMode")
        if not isinstance(self.candidate, MemoryWriteCandidate):
            raise DTOValidationError("candidate must be MemoryWriteCandidate")


def _memory_type_from_value(value: Any, field_name: str) -> MemoryType:
    raw_value = _require_non_empty(value, field_name)
    try:
        return MemoryType(raw_value)
    except ValueError as exc:
        raise DTOValidationError(f"memory type is not supported: {raw_value}") from exc


def _confidence_from_value(value: Any) -> float:
    if value is None:
        raise DTOValidationError("memory_write.confidence is required")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError("memory_write.confidence must be a number") from exc
