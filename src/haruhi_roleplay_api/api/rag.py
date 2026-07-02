"""RAG API handlers."""

from __future__ import annotations

from typing import Any, Mapping

from haruhi_roleplay_api.api.responses import (
    ApiResponse,
    error_response,
    success_response,
)
from haruhi_roleplay_api.application.rag import ValidateRagDocumentMetadata
from haruhi_roleplay_api.domain import (
    AppId,
    DTOValidationError,
    RagDocumentId,
    RagDocumentMetadata,
    RagIngestInput,
    RagIngestResult,
    RequestId,
)
from haruhi_roleplay_api.ports import PersonaRepository


def post_rag_document(
    body: Mapping[str, Any],
    *,
    persona_repository: PersonaRepository,
    request_id: RequestId | str,
    include_error_details: bool = False,
) -> ApiResponse:
    try:
        result = ValidateRagDocumentMetadata(persona_repository).execute(
            _rag_ingest_input_from_body(body)
        )
    except Exception as exc:
        return error_response(
            exc,
            request_id,
            include_details=include_error_details,
        )
    return success_response(_rag_ingest_result_to_data(result), request_id)


def _rag_ingest_input_from_body(body: Mapping[str, Any]) -> RagIngestInput:
    if not isinstance(body, Mapping):
        raise DTOValidationError("request body must be an object")
    document_id = body.get("document_id")
    return RagIngestInput(
        appId=AppId(_require_non_empty(body.get("app_id"), "app_id")),
        documentId=(
            RagDocumentId(_require_non_empty(document_id, "document_id"))
            if document_id is not None
            else None
        ),
        title=_require_non_empty(body.get("title"), "title"),
        content=_require_non_empty(body.get("content"), "content"),
        metadata=RagDocumentMetadata.from_mapping(_metadata_from_body(body)),
    )


def _metadata_from_body(body: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "characterId": body.get("character_id"),
        "personaMode": body.get("persona_mode"),
        "timeline": body.get("timeline"),
        "spoilerLevel": body.get("spoiler_level"),
        "language": body.get("language"),
        "sourceType": body.get("source_type"),
        "trustLevel": body.get("trust_level"),
        "extra": body.get("metadata", {}),
    }


def _rag_ingest_result_to_data(result: RagIngestResult) -> dict[str, Any]:
    return {
        "document_id": str(result.documentId),
        "status": result.status,
        "chunk_count": result.chunkCount,
        "metadata": result.metadata.to_mapping(),
    }


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value
