"""RAG ingest use cases."""

from __future__ import annotations

from uuid import uuid4

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    DTOValidationError,
    PersonaPreset,
    RagDocumentId,
    RagDocumentMetadata,
    RagIngestInput,
    RagIngestResult,
    Visibility,
    public_persona_presets,
)
from haruhi_roleplay_api.ports import PersonaRepository


class ValidateRagDocumentMetadata:
    def __init__(self, persona_repository: PersonaRepository) -> None:
        self._persona_repository = persona_repository

    def execute(self, ingest_input: RagIngestInput) -> RagIngestResult:
        _ensure_rag_policy(
            ingest_input.metadata,
            self._persona_repository,
        )
        return RagIngestResult(
            documentId=ingest_input.documentId or _new_document_id(),
            status="validated",
            chunkCount=0,
            metadata=ingest_input.metadata,
        )


def _ensure_rag_policy(
    metadata: RagDocumentMetadata,
    repository: PersonaRepository,
) -> None:
    _ensure_character_exists(metadata, repository)
    presets = _policy_presets(metadata, repository)
    allowed_timelines = {
        timeline
        for preset in presets
        for timeline in preset.knowledgeBoundary.allowedTimelines
    }
    if metadata.timeline not in allowed_timelines:
        raise DTOValidationError(
            f"timeline is not allowed by persona policy: {metadata.timeline}"
        )

    spoiler_max = max(preset.knowledgeBoundary.spoilerLevel for preset in presets)
    if metadata.spoilerLevel > spoiler_max:
        raise DTOValidationError(
            f"spoilerLevel exceeds persona policy: {metadata.spoilerLevel}"
        )

    allowed_source_types = {
        str(source_type)
        for preset in presets
        for source_type in preset.ragPolicy.get("sourceTypes", ())
    }
    if metadata.sourceType not in allowed_source_types:
        raise DTOValidationError(
            f"sourceType is not allowed by persona policy: {metadata.sourceType}"
        )


def _ensure_character_exists(
    metadata: RagDocumentMetadata,
    repository: PersonaRepository,
) -> None:
    for character in repository.list_characters():
        if (
            character.characterId == metadata.characterId
            and character.visibility is Visibility.PUBLIC
        ):
            return
    raise AppError(
        code=ErrorCode.PERSONA_NOT_FOUND,
        message=f"Character was not found: {metadata.characterId}",
    )


def _policy_presets(
    metadata: RagDocumentMetadata,
    repository: PersonaRepository,
) -> tuple[PersonaPreset, ...]:
    public_presets = public_persona_presets(
        repository.list_presets(metadata.characterId)
    )
    if metadata.personaMode is None:
        if public_presets:
            return public_presets
        raise AppError(
            code=ErrorCode.PERSONA_MODE_NOT_FOUND,
            message=f"No public persona preset was found: {metadata.characterId}",
        )

    for preset in public_presets:
        if preset.personaMode == metadata.personaMode:
            return (preset,)
    raise AppError(
        code=ErrorCode.PERSONA_MODE_NOT_FOUND,
        message=f"Persona preset was not found: {metadata.personaMode}",
    )


def _new_document_id() -> RagDocumentId:
    return RagDocumentId(f"ragdoc-{uuid4().hex}")
