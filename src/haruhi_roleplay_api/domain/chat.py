"""Core chat DTOs.

These DTOs are internal application/domain shapes. HTTP `snake_case` conversion
belongs in the API layer and is intentionally not implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, NewType

from haruhi_roleplay_api.domain.request_limits import (
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_GENERATION_TOKENS,
    MAX_ID_LENGTH,
)


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


def _require_non_empty(
    value: Any,
    field_name: str,
    *,
    max_length: int | None = None,
) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    if max_length is not None and len(value) > max_length:
        raise DTOValidationError(
            f"{field_name} must be at most {max_length} characters"
        )
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
        if not isinstance(data, Mapping):
            raise DTOValidationError("capabilities must be an object")
        return cls(
            rag=_boolean(data.get("rag", False), "capabilities.rag"),
            memory=_boolean(data.get("memory", False), "capabilities.memory"),
            continuousSession=_boolean(
                data.get("continuousSession", False),
                "capabilities.continuousSession",
            ),
            safetyFilter=_boolean(
                data.get("safetyFilter", True),
                "capabilities.safetyFilter",
            ),
            debugTrace=_boolean(
                data.get("debugTrace", False),
                "capabilities.debugTrace",
            ),
            stream=_boolean(data.get("stream", False), "capabilities.stream"),
        )

    def __post_init__(self) -> None:
        for field_name, value in (
            ("rag", self.rag),
            ("memory", self.memory),
            ("continuousSession", self.continuousSession),
            ("safetyFilter", self.safetyFilter),
            ("debugTrace", self.debugTrace),
            ("stream", self.stream),
        ):
            _boolean(value, f"capabilities.{field_name}")


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
        if not isinstance(data, Mapping):
            raise DTOValidationError("generation must be an object")
        return cls(
            model=data.get("model"),
            temperature=_float_value(
                data.get("temperature", 0.8),
                "generation.temperature",
            ),
            maxTokens=_integer_value(
                data.get("maxTokens", 800),
                "generation.maxTokens",
            ),
            topP=_float_value(data.get("topP", 1.0), "generation.topP"),
            presencePenalty=_float_value(
                data.get("presencePenalty", 0.0),
                "generation.presencePenalty",
            ),
            frequencyPenalty=_float_value(
                data.get("frequencyPenalty", 0.0),
                "generation.frequencyPenalty",
            ),
            styleIntensity=_float_value(
                data.get("styleIntensity", 0.75),
                "generation.styleIntensity",
            ),
            allowNarration=_boolean(
                data.get("allowNarration", True),
                "generation.allowNarration",
            ),
        )

    def __post_init__(self) -> None:
        if self.model is not None:
            _require_non_empty(self.model, "generation.model")
        for field_name, value in (
            ("temperature", self.temperature),
            ("topP", self.topP),
            ("presencePenalty", self.presencePenalty),
            ("frequencyPenalty", self.frequencyPenalty),
            ("styleIntensity", self.styleIntensity),
        ):
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise DTOValidationError(
                    f"generation.{field_name} must be a number"
                )
        if not 0.0 <= self.temperature <= 2.0:
            raise DTOValidationError("generation.temperature must be between 0 and 2")
        if isinstance(self.maxTokens, bool) or not isinstance(self.maxTokens, int):
            raise DTOValidationError("generation.maxTokens must be an integer")
        if self.maxTokens <= 0:
            raise DTOValidationError("generation.maxTokens must be positive")
        if self.maxTokens > MAX_GENERATION_TOKENS:
            raise DTOValidationError(
                f"generation.maxTokens must be at most {MAX_GENERATION_TOKENS}"
            )
        if not 0.0 <= self.topP <= 1.0:
            raise DTOValidationError("generation.topP must be between 0 and 1")
        if not 0.0 <= self.styleIntensity <= 1.0:
            raise DTOValidationError("generation.styleIntensity must be between 0 and 1")
        _boolean(self.allowNarration, "generation.allowNarration")


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
                RequestId(
                    _require_non_empty(
                        data.get("requestId"),
                        "requestId",
                        max_length=MAX_ID_LENGTH,
                    )
                )
                if data.get("requestId") is not None
                else None
            ),
            appId=AppId(
                _require_non_empty(
                    data.get("appId"), "appId", max_length=MAX_ID_LENGTH
                )
            ),
            userId=UserId(
                _require_non_empty(
                    data.get("userId"), "userId", max_length=MAX_ID_LENGTH
                )
            ),
            sessionId=(
                SessionId(
                    _require_non_empty(
                        data.get("sessionId"),
                        "sessionId",
                        max_length=MAX_ID_LENGTH,
                    )
                )
                if data.get("sessionId") is not None
                else None
            ),
            characterId=CharacterId(
                _require_non_empty(
                    data.get("characterId"),
                    "characterId",
                    max_length=MAX_ID_LENGTH,
                )
            ),
            personaMode=PersonaModeId(
                _require_non_empty(
                    data.get("personaMode"),
                    "personaMode",
                    max_length=MAX_ID_LENGTH,
                )
            ),
            message=_require_non_empty(
                data.get("message"),
                "message",
                max_length=MAX_CHAT_MESSAGE_LENGTH,
            ),
            language=_require_non_empty(data.get("language"), "language"),
            capabilities=CapabilityConfig.from_mapping(data.get("capabilities")),
            generation=GenerationConfig.from_mapping(data.get("generation")),
            metadata=data.get("metadata", {}),
        )

    def __post_init__(self) -> None:
        if self.requestId is not None:
            _require_non_empty(
                str(self.requestId), "requestId", max_length=MAX_ID_LENGTH
            )
        _require_non_empty(str(self.appId), "appId", max_length=MAX_ID_LENGTH)
        _require_non_empty(str(self.userId), "userId", max_length=MAX_ID_LENGTH)
        if self.sessionId is not None:
            _require_non_empty(
                str(self.sessionId), "sessionId", max_length=MAX_ID_LENGTH
            )
        _require_non_empty(
            str(self.characterId), "characterId", max_length=MAX_ID_LENGTH
        )
        _require_non_empty(
            str(self.personaMode), "personaMode", max_length=MAX_ID_LENGTH
        )
        _require_non_empty(
            self.message,
            "message",
            max_length=MAX_CHAT_MESSAGE_LENGTH,
        )
        _require_non_empty(self.language, "language")
        if self.language not in self.supportedLanguages:
            raise DTOValidationError(f"language is not supported: {self.language}")
        if not isinstance(self.capabilities, CapabilityConfig):
            raise DTOValidationError("capabilities must be CapabilityConfig")
        if not isinstance(self.generation, GenerationConfig):
            raise DTOValidationError("generation must be GenerationConfig")


def _boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise DTOValidationError(f"{field_name} must be a boolean")
    return value


def _integer_value(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise DTOValidationError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError(f"{field_name} must be an integer") from exc


def _float_value(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise DTOValidationError(f"{field_name} must be a number")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError(f"{field_name} must be a number") from exc


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


@dataclass(frozen=True, kw_only=True)
class ChatStreamEvent:
    event: str
    data: Metadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event not in {"start", "delta", "source", "usage", "done", "error"}:
            raise DTOValidationError(f"chat stream event is not supported: {self.event}")
        if not isinstance(self.data, Mapping):
            raise DTOValidationError("chat stream event data must be an object")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "data": dict(self.data),
        }

