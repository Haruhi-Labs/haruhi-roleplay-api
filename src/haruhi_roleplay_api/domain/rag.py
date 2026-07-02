"""RAG document metadata domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, NewType

from haruhi_roleplay_api.domain.chat import (
    AppId,
    CharacterId,
    DTOValidationError,
    LanguageCode,
    Metadata,
    PersonaModeId,
)


RagDocumentId = NewType("RagDocumentId", str)

SUPPORTED_RAG_LANGUAGES = {"zh-CN", "ja-JP", "en-US"}


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value


def _optional_non_empty(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_non_empty(value, field_name)


@dataclass(frozen=True, kw_only=True)
class RagDocumentMetadata:
    characterId: CharacterId
    timeline: str
    spoilerLevel: int
    language: LanguageCode
    sourceType: str
    personaMode: PersonaModeId | None = None
    trustLevel: str | None = None
    extra: Metadata = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RagDocumentMetadata":
        return cls(
            characterId=CharacterId(
                _require_non_empty(data.get("characterId"), "characterId")
            ),
            personaMode=(
                PersonaModeId(
                    _require_non_empty(data.get("personaMode"), "personaMode")
                )
                if data.get("personaMode") is not None
                else None
            ),
            timeline=_require_non_empty(data.get("timeline"), "timeline"),
            spoilerLevel=_spoiler_level(data.get("spoilerLevel")),
            language=_require_non_empty(data.get("language"), "language"),
            sourceType=_require_non_empty(data.get("sourceType"), "sourceType"),
            trustLevel=_optional_non_empty(data.get("trustLevel"), "trustLevel"),
            extra=data.get("extra", {}),
        )

    def __post_init__(self) -> None:
        _require_non_empty(str(self.characterId), "characterId")
        if self.personaMode is not None:
            _require_non_empty(str(self.personaMode), "personaMode")
        _require_non_empty(self.timeline, "timeline")
        if self.spoilerLevel < 0:
            raise DTOValidationError("spoilerLevel must be >= 0")
        _require_non_empty(self.language, "language")
        if self.language not in SUPPORTED_RAG_LANGUAGES:
            raise DTOValidationError(f"language is not supported: {self.language}")
        _require_non_empty(self.sourceType, "sourceType")
        if not isinstance(self.extra, Mapping):
            raise DTOValidationError("metadata must be an object")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "character_id": str(self.characterId),
            "persona_mode": (
                str(self.personaMode) if self.personaMode is not None else None
            ),
            "timeline": self.timeline,
            "spoiler_level": self.spoilerLevel,
            "language": self.language,
            "source_type": self.sourceType,
            "trust_level": self.trustLevel,
            "metadata": dict(self.extra),
        }


@dataclass(frozen=True, kw_only=True)
class RagIngestInput:
    appId: AppId
    title: str
    content: str
    metadata: RagDocumentMetadata
    documentId: RagDocumentId | None = None

    def __post_init__(self) -> None:
        _require_non_empty(str(self.appId), "appId")
        if self.documentId is not None:
            _require_non_empty(str(self.documentId), "documentId")
        _require_non_empty(self.title, "title")
        _require_non_empty(self.content, "content")
        if not isinstance(self.metadata, RagDocumentMetadata):
            raise DTOValidationError("metadata must be RagDocumentMetadata")


@dataclass(frozen=True, kw_only=True)
class RagIngestResult:
    documentId: RagDocumentId
    status: str
    chunkCount: int
    metadata: RagDocumentMetadata

    def __post_init__(self) -> None:
        _require_non_empty(str(self.documentId), "documentId")
        _require_non_empty(self.status, "status")
        if self.chunkCount < 0:
            raise DTOValidationError("chunkCount must be >= 0")
        if not isinstance(self.metadata, RagDocumentMetadata):
            raise DTOValidationError("metadata must be RagDocumentMetadata")


def _spoiler_level(value: Any) -> int:
    if value is None:
        raise DTOValidationError("spoilerLevel is required")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError("spoilerLevel must be an integer") from exc
