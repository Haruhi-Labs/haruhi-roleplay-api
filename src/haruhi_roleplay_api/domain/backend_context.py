"""Backend context domain objects."""

from __future__ import annotations

import re
from dataclasses import dataclass

from haruhi_roleplay_api.domain.chat import (
    AppId,
    CharacterId,
    DTOValidationError,
    PersonaModeId,
    UserId,
)


_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


@dataclass(frozen=True, kw_only=True)
class BackendContextRequest:
    appId: AppId
    userId: UserId
    characterId: CharacterId
    personaMode: PersonaModeId
    sources: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(str(self.appId), "backendContext.appId")
        _require_non_empty(str(self.userId), "backendContext.userId")
        _require_non_empty(str(self.characterId), "backendContext.characterId")
        _require_non_empty(str(self.personaMode), "backendContext.personaMode")
        for index, source in enumerate(self.sources):
            _require_safe_label(source, f"backendContext.sources[{index}]")


@dataclass(frozen=True, kw_only=True)
class BackendContextFact:
    source: str
    key: str
    content: str
    confidence: float
    ttlSeconds: int

    def __post_init__(self) -> None:
        _require_safe_label(self.source, "backendContextFact.source")
        _require_safe_label(self.key, "backendContextFact.key")
        _require_non_empty(self.content, "backendContextFact.content")
        if not 0.0 <= self.confidence <= 1.0:
            raise DTOValidationError(
                "backendContextFact.confidence must be between 0 and 1"
            )
        if self.ttlSeconds < 0:
            raise DTOValidationError("backendContextFact.ttlSeconds must be >= 0")


def _require_non_empty(value: str | None, field_name: str) -> None:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")


def _require_safe_label(value: str, field_name: str) -> None:
    _require_non_empty(value, field_name)
    if not _SAFE_LABEL_RE.fullmatch(value):
        raise DTOValidationError(f"{field_name} contains unsupported characters")
