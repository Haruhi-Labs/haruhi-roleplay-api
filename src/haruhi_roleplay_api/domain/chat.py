"""Core chat DTOs.

These DTOs are internal application/domain shapes. HTTP `snake_case` conversion
belongs in the API layer and is intentionally not implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, NewType


RequestId = NewType("RequestId", str)
AppId = NewType("AppId", str)
UserId = NewType("UserId", str)
SessionId = NewType("SessionId", str)
CharacterId = NewType("CharacterId", str)
PersonaModeId = NewType("PersonaModeId", str)

LanguageCode = str
Metadata = Mapping[str, Any]


class DTOValidationError(ValueError):
    """Raised when a DTO cannot be built from the supplied data."""


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True, kw_only=True)
class CapabilityConfig:
    rag: bool = False
    memory: bool = False
    continuousSession: bool = False
    safetyFilter: bool = True
    debugTrace: bool = False
    stream: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "CapabilityConfig":
        if data is None:
            raise DTOValidationError("capabilities is required")
        return cls(
            rag=bool(data.get("rag", False)),
            memory=bool(data.get("memory", False)),
            continuousSession=bool(data.get("continuousSession", False)),
            safetyFilter=bool(data.get("safetyFilter", True)),
            debugTrace=bool(data.get("debugTrace", False)),
            stream=bool(data.get("stream", False)),
        )


@dataclass(frozen=True, kw_only=True)
class GenerationConfig:
    model: str | None = None
    temperature: float = 0.8
    maxTokens: int = 800
    topP: float = 1.0
    presencePenalty: float = 0.0
    frequencyPenalty: float = 0.0
    styleIntensity: float = 0.75
    allowNarration: bool = True

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "GenerationConfig":
        if data is None:
            return cls()
        return cls(
            model=data.get("model"),
            temperature=float(data.get("temperature", 0.8)),
            maxTokens=int(data.get("maxTokens", 800)),
            topP=float(data.get("topP", 1.0)),
            presencePenalty=float(data.get("presencePenalty", 0.0)),
            frequencyPenalty=float(data.get("frequencyPenalty", 0.0)),
            styleIntensity=float(data.get("styleIntensity", 0.75)),
            allowNarration=bool(data.get("allowNarration", True)),
        )

    def __post_init__(self) -> None:
        if self.model is not None:
            _require_non_empty(self.model, "generation.model")
        if not 0.0 <= self.temperature <= 2.0:
            raise DTOValidationError("generation.temperature must be between 0 and 2")
        if self.maxTokens <= 0:
            raise DTOValidationError("generation.maxTokens must be positive")
        if not 0.0 <= self.topP <= 1.0:
            raise DTOValidationError("generation.topP must be between 0 and 1")
        if not 0.0 <= self.styleIntensity <= 1.0:
            raise DTOValidationError("generation.styleIntensity must be between 0 and 1")


@dataclass(frozen=True, kw_only=True)
class ChatInput:
    appId: AppId
    userId: UserId
    characterId: CharacterId
    personaMode: PersonaModeId
    message: str
    language: LanguageCode
    capabilities: CapabilityConfig
    requestId: RequestId | None = None
    sessionId: SessionId | None = None
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    metadata: Metadata = field(default_factory=dict)

    supportedLanguages: ClassVar[set[str]] = {"zh-CN", "ja-JP", "en-US"}

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ChatInput":
        return cls(
            requestId=(
                RequestId(_require_non_empty(data.get("requestId"), "requestId"))
                if data.get("requestId") is not None
                else None
            ),
            appId=AppId(_require_non_empty(data.get("appId"), "appId")),
            userId=UserId(_require_non_empty(data.get("userId"), "userId")),
            sessionId=(
                SessionId(_require_non_empty(data.get("sessionId"), "sessionId"))
                if data.get("sessionId") is not None
                else None
            ),
            characterId=CharacterId(
                _require_non_empty(data.get("characterId"), "characterId")
            ),
            personaMode=PersonaModeId(
                _require_non_empty(data.get("personaMode"), "personaMode")
            ),
            message=_require_non_empty(data.get("message"), "message"),
            language=_require_non_empty(data.get("language"), "language"),
            capabilities=CapabilityConfig.from_mapping(data.get("capabilities")),
            generation=GenerationConfig.from_mapping(data.get("generation")),
            metadata=data.get("metadata", {}),
        )

    def __post_init__(self) -> None:
        _require_non_empty(str(self.appId), "appId")
        _require_non_empty(str(self.userId), "userId")
        _require_non_empty(str(self.characterId), "characterId")
        _require_non_empty(str(self.personaMode), "personaMode")
        _require_non_empty(self.message, "message")
        _require_non_empty(self.language, "language")
        if self.language not in self.supportedLanguages:
            raise DTOValidationError(f"language is not supported: {self.language}")
        if not isinstance(self.capabilities, CapabilityConfig):
            raise DTOValidationError("capabilities must be CapabilityConfig")
        if not isinstance(self.generation, GenerationConfig):
            raise DTOValidationError("generation must be GenerationConfig")


@dataclass(frozen=True, kw_only=True)
class ChatOutput:
    requestId: RequestId
    characterId: CharacterId
    personaMode: PersonaModeId
    reply: str
    sessionId: SessionId | None = None
    usage: Metadata | None = None
    rag: Metadata | None = None
    memory: Metadata | None = None
    safety: Metadata | None = None
    debug: Metadata | None = None

    def __post_init__(self) -> None:
        _require_non_empty(str(self.requestId), "requestId")
        _require_non_empty(str(self.characterId), "characterId")
        _require_non_empty(str(self.personaMode), "personaMode")
        _require_non_empty(self.reply, "reply")

