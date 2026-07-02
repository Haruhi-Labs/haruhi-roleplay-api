"""Debug trace domain objects.

Debug trace objects intentionally carry summaries only. They must not include
full prompts, full model replies, API keys, connection strings, or raw RAG docs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from haruhi_roleplay_api.domain.chat import (
    CharacterId,
    DTOValidationError,
    PersonaModeId,
    RequestId,
)


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True, kw_only=True)
class DebugTrace:
    requestId: RequestId
    characterId: CharacterId
    personaMode: PersonaModeId
    personaSource: str
    sessionReadCount: int = 0
    memoryReadCount: int = 0
    memoryWriteCount: int = 0
    ragProvider: str | None = None
    ragRawHitCount: int = 0
    ragFilteredHitCount: int = 0
    modelProvider: str | None = None
    modelRoute: str | None = None
    safetyAction: str = "allow"
    latencyMs: int = 0
    capabilities: Mapping[str, bool] = field(default_factory=dict)
    events: tuple[str, ...] = ()
    modelDebug: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty(str(self.requestId), "debug.requestId")
        _require_non_empty(str(self.characterId), "debug.characterId")
        _require_non_empty(str(self.personaMode), "debug.personaMode")
        _require_non_empty(self.personaSource, "debug.personaSource")
        _require_non_empty(self.safetyAction, "debug.safetyAction")
        for field_name, value in (
            ("debug.sessionReadCount", self.sessionReadCount),
            ("debug.memoryReadCount", self.memoryReadCount),
            ("debug.memoryWriteCount", self.memoryWriteCount),
            ("debug.ragRawHitCount", self.ragRawHitCount),
            ("debug.ragFilteredHitCount", self.ragFilteredHitCount),
            ("debug.latencyMs", self.latencyMs),
        ):
            if value < 0:
                raise DTOValidationError(f"{field_name} must be >= 0")

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "requestId": str(self.requestId),
            "characterId": str(self.characterId),
            "personaMode": str(self.personaMode),
            "personaSource": self.personaSource,
            "sessionEnabled": bool(
                self.capabilities.get("continuousSession", False)
            ),
            "sessionReadCount": self.sessionReadCount,
            "memoryEnabled": bool(self.capabilities.get("memory", False)),
            "memoryReadCount": self.memoryReadCount,
            "memoryWriteCount": self.memoryWriteCount,
            "ragEnabled": bool(self.capabilities.get("rag", False)),
            "ragProvider": self.ragProvider,
            "ragRawHitCount": self.ragRawHitCount,
            "ragFilteredHitCount": self.ragFilteredHitCount,
            "modelProvider": self.modelProvider,
            "modelRoute": self.modelRoute,
            "model": self.modelRoute,
            "safetyEnabled": bool(self.capabilities.get("safetyFilter", True)),
            "streamEnabled": bool(self.capabilities.get("stream", False)),
            "safetyAction": self.safetyAction,
            "latencyMs": self.latencyMs,
            "events": list(self.events),
        }
        data.update(_safe_model_debug(self.modelDebug))
        return data


def _safe_model_debug(debug: Mapping[str, Any]) -> dict[str, Any]:
    allowed_keys = {"messageCount"}
    safe: dict[str, Any] = {}
    for key in allowed_keys:
        if key in debug:
            safe[key] = debug[key]
    return safe
