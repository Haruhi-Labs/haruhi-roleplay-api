"""Persona catalog domain schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from haruhi_roleplay_api.domain.chat import (
    CharacterId,
    DTOValidationError,
    PersonaModeId,
)


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    DRAFT = "draft"


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value


def _string_tuple(value: Iterable[Any] | None, field_name: str) -> tuple[str, ...]:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    items = tuple(_require_non_empty(str(item), field_name) for item in value)
    if not items:
        raise DTOValidationError(f"{field_name} must not be empty")
    return items


def _readonly_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, Mapping):
        raise DTOValidationError(f"{field_name} must be an object")
    return value


@dataclass(frozen=True, kw_only=True)
class ToneConfig:
    energy: float
    assertiveness: float
    warmth: float
    directness: float
    randomness: float

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ToneConfig":
        return cls(
            energy=float(data.get("energy", 0.5)),
            assertiveness=float(data.get("assertiveness", 0.5)),
            warmth=float(data.get("warmth", 0.5)),
            directness=float(data.get("directness", 0.5)),
            randomness=float(data.get("randomness", 0.5)),
        )

    def __post_init__(self) -> None:
        for field_name in (
            "energy",
            "assertiveness",
            "warmth",
            "directness",
            "randomness",
        ):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise DTOValidationError(f"tone.{field_name} must be between 0 and 1")


@dataclass(frozen=True, kw_only=True)
class IdentityConfig:
    role: str
    description: str
    coreDrives: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "IdentityConfig":
        return cls(
            role=_require_non_empty(data.get("role"), "identity.role"),
            description=_require_non_empty(
                data.get("description"), "identity.description"
            ),
            coreDrives=_string_tuple(data.get("coreDrives"), "identity.coreDrives"),
        )

    def __post_init__(self) -> None:
        _require_non_empty(self.role, "identity.role")
        _require_non_empty(self.description, "identity.description")
        _string_tuple(self.coreDrives, "identity.coreDrives")


@dataclass(frozen=True, kw_only=True)
class KnowledgeBoundary:
    allowedTimelines: tuple[str, ...]
    forbiddenTimelines: tuple[str, ...] = ()
    spoilerLevel: int = 0

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "KnowledgeBoundary":
        return cls(
            allowedTimelines=_string_tuple(
                data.get("allowedTimelines"), "knowledgeBoundary.allowedTimelines"
            ),
            forbiddenTimelines=tuple(
                str(item) for item in data.get("forbiddenTimelines", ())
            ),
            spoilerLevel=int(data.get("spoilerLevel", 0)),
        )

    def __post_init__(self) -> None:
        _string_tuple(self.allowedTimelines, "knowledgeBoundary.allowedTimelines")
        if self.spoilerLevel < 0:
            raise DTOValidationError("knowledgeBoundary.spoilerLevel must be >= 0")


@dataclass(frozen=True, kw_only=True)
class CharacterProfile:
    characterId: CharacterId
    displayName: str
    description: str
    defaultPersonaMode: PersonaModeId
    availablePersonaModes: tuple[PersonaModeId, ...]
    tags: tuple[str, ...] = ()
    visibility: Visibility = Visibility.PUBLIC

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CharacterProfile":
        return cls(
            characterId=CharacterId(
                _require_non_empty(data.get("characterId"), "characterId")
            ),
            displayName=_require_non_empty(data.get("displayName"), "displayName"),
            description=_require_non_empty(data.get("description"), "description"),
            defaultPersonaMode=PersonaModeId(
                _require_non_empty(data.get("defaultPersonaMode"), "defaultPersonaMode")
            ),
            availablePersonaModes=tuple(
                PersonaModeId(item)
                for item in _string_tuple(
                    data.get("availablePersonaModes"), "availablePersonaModes"
                )
            ),
            tags=tuple(str(tag) for tag in data.get("tags", ())),
            visibility=Visibility(data.get("visibility", Visibility.PUBLIC.value)),
        )

    def __post_init__(self) -> None:
        _require_non_empty(str(self.characterId), "characterId")
        _require_non_empty(self.displayName, "displayName")
        _require_non_empty(self.description, "description")
        _require_non_empty(str(self.defaultPersonaMode), "defaultPersonaMode")
        if not self.availablePersonaModes:
            raise DTOValidationError("availablePersonaModes must not be empty")
        if self.defaultPersonaMode not in self.availablePersonaModes:
            raise DTOValidationError(
                "defaultPersonaMode must be included in availablePersonaModes"
            )


@dataclass(frozen=True, kw_only=True)
class PersonaPreset:
    characterId: CharacterId
    personaMode: PersonaModeId
    displayName: str
    description: str
    timeline: str
    identity: IdentityConfig
    tone: ToneConfig
    speechStyle: tuple[str, ...]
    behaviorRules: tuple[str, ...]
    forbiddenBehaviors: tuple[str, ...]
    knowledgeBoundary: KnowledgeBoundary
    ragPolicy: Mapping[str, Any] = field(default_factory=dict)
    memoryPolicy: Mapping[str, Any] = field(default_factory=dict)
    safetyPolicy: Mapping[str, Any] = field(default_factory=dict)
    visibility: Visibility = Visibility.PUBLIC

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PersonaPreset":
        return cls(
            characterId=CharacterId(
                _require_non_empty(data.get("characterId"), "characterId")
            ),
            personaMode=PersonaModeId(
                _require_non_empty(data.get("personaMode"), "personaMode")
            ),
            displayName=_require_non_empty(data.get("displayName"), "displayName"),
            description=_require_non_empty(data.get("description"), "description"),
            timeline=_require_non_empty(data.get("timeline"), "timeline"),
            identity=IdentityConfig.from_mapping(
                _require_mapping(data.get("identity"), "identity")
            ),
            tone=ToneConfig.from_mapping(_require_mapping(data.get("tone"), "tone")),
            speechStyle=_string_tuple(data.get("speechStyle"), "speechStyle"),
            behaviorRules=_string_tuple(data.get("behaviorRules"), "behaviorRules"),
            forbiddenBehaviors=_string_tuple(
                data.get("forbiddenBehaviors"), "forbiddenBehaviors"
            ),
            knowledgeBoundary=KnowledgeBoundary.from_mapping(
                _require_mapping(data.get("knowledgeBoundary"), "knowledgeBoundary")
            ),
            ragPolicy=_readonly_mapping(_require_mapping(data.get("ragPolicy"), "ragPolicy")),
            memoryPolicy=_readonly_mapping(
                _require_mapping(data.get("memoryPolicy"), "memoryPolicy")
            ),
            safetyPolicy=_readonly_mapping(
                _require_mapping(data.get("safetyPolicy"), "safetyPolicy")
            ),
            visibility=Visibility(data.get("visibility", Visibility.PUBLIC.value)),
        )

    def __post_init__(self) -> None:
        _require_non_empty(str(self.characterId), "characterId")
        _require_non_empty(str(self.personaMode), "personaMode")
        _require_non_empty(self.displayName, "displayName")
        _require_non_empty(self.description, "description")
        _require_non_empty(self.timeline, "timeline")
        if self.timeline not in self.knowledgeBoundary.allowedTimelines:
            raise DTOValidationError("timeline must be allowed by knowledgeBoundary")
        source_types = tuple(
            str(item) for item in (self.ragPolicy.get("sourceTypes") or ())
        )
        if "character_profile" in source_types:
            raise DTOValidationError(
                "ragPolicy.sourceTypes 不能包含 character_profile；"
                "角色身份必须由 Persona 确定。"
            )


def public_persona_presets(
    presets: Iterable[PersonaPreset],
) -> tuple[PersonaPreset, ...]:
    return tuple(preset for preset in presets if preset.visibility is Visibility.PUBLIC)
