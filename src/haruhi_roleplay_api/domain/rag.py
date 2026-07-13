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
    UserId,
)


RagDocumentId = NewType("RagDocumentId", str)
RagChunkId = NewType("RagChunkId", str)

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
    appId: AppId | None = None
    personaMode: PersonaModeId | None = None
    trustLevel: str | None = None
    extra: Metadata = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RagDocumentMetadata":
        return cls(
            appId=(
                AppId(_require_non_empty(data.get("appId"), "appId"))
                if data.get("appId") is not None
                else None
            ),
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
        if self.appId is not None:
            _require_non_empty(str(self.appId), "appId")
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
            "app_id": str(self.appId) if self.appId is not None else None,
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
        if self.metadata.appId is None:
            raise DTOValidationError("metadata.appId is required")
        if self.metadata.appId != self.appId:
            raise DTOValidationError("metadata.appId must match appId")


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


@dataclass(frozen=True, kw_only=True)
class RagRetrieveFilters:
    sourceTypes: tuple[str, ...] = ()
    timelines: tuple[str, ...] = ()
    spoilerLevelMax: int | None = None
    language: LanguageCode | None = None

    def __post_init__(self) -> None:
        _non_empty_string_tuple(self.sourceTypes, "filters.sourceTypes")
        _non_empty_string_tuple(self.timelines, "filters.timelines")
        if self.spoilerLevelMax is not None and self.spoilerLevelMax < 0:
            raise DTOValidationError("filters.spoilerLevelMax must be >= 0")
        if self.language is not None:
            _require_non_empty(self.language, "filters.language")
            if self.language not in SUPPORTED_RAG_LANGUAGES:
                raise DTOValidationError(f"language is not supported: {self.language}")


@dataclass(frozen=True, kw_only=True)
class RagChunk:
    chunkId: RagChunkId
    documentId: RagDocumentId
    content: str
    score: float
    metadata: RagDocumentMetadata

    def __post_init__(self) -> None:
        _require_non_empty(str(self.chunkId), "chunkId")
        _require_non_empty(str(self.documentId), "documentId")
        _require_non_empty(self.content, "content")
        if self.score < 0:
            raise DTOValidationError("score must be >= 0")
        if not isinstance(self.metadata, RagDocumentMetadata):
            raise DTOValidationError("metadata must be RagDocumentMetadata")

    def to_source_mapping(self) -> dict[str, Any]:
        return {
            "app_id": (
                str(self.metadata.appId)
                if self.metadata.appId is not None
                else None
            ),
            "document_id": str(self.documentId),
            "chunk_id": str(self.chunkId),
            "title": self.metadata.extra.get("title"),
            "source_type": self.metadata.sourceType,
            "character_id": str(self.metadata.characterId),
            "persona_mode": (
                str(self.metadata.personaMode)
                if self.metadata.personaMode is not None
                else None
            ),
            "timeline": self.metadata.timeline,
            "spoiler_level": self.metadata.spoilerLevel,
            "language": self.metadata.language,
            "score": self.score,
        }


@dataclass(frozen=True, kw_only=True)
class RagRetrieveInput:
    appId: AppId
    userId: UserId
    characterId: CharacterId
    personaMode: PersonaModeId
    query: str
    topK: int
    filters: RagRetrieveFilters = field(default_factory=RagRetrieveFilters)
    debug: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(str(self.appId), "appId")
        _require_non_empty(str(self.userId), "userId")
        _require_non_empty(str(self.characterId), "characterId")
        _require_non_empty(str(self.personaMode), "personaMode")
        _require_non_empty(self.query, "query")
        if self.topK <= 0:
            raise DTOValidationError("topK must be positive")
        if not isinstance(self.filters, RagRetrieveFilters):
            raise DTOValidationError("filters must be RagRetrieveFilters")


@dataclass(frozen=True, kw_only=True)
class RagRetrieveOutput:
    chunks: tuple[RagChunk, ...]
    provider: str
    rawHitCount: int
    filteredHitCount: int
    rerankApplied: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.provider, "provider")
        if self.rawHitCount < 0:
            raise DTOValidationError("rawHitCount must be >= 0")
        if self.filteredHitCount < 0:
            raise DTOValidationError("filteredHitCount must be >= 0")
        for chunk in self.chunks:
            if not isinstance(chunk, RagChunk):
                raise DTOValidationError("chunks must contain RagChunk")


def _non_empty_string_tuple(values: tuple[str, ...], field_name: str) -> None:
    for value in values:
        _require_non_empty(value, field_name)
