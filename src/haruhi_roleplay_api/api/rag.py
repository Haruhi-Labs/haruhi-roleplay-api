"""RAG API handlers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from haruhi_roleplay_api.api.responses import (
    ApiResponse,
    error_response,
    success_response,
)
from haruhi_roleplay_api.application.rag import ValidateRagDocumentMetadata
from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    DTOValidationError,
    PersonaModeId,
    RagDocumentId,
    RagDocumentMetadata,
    RagIngestInput,
    RagIngestResult,
    RagRetrieveFilters,
    RagRetrieveInput,
    RagRetrieveOutput,
    RequestId,
    UserId,
)
from haruhi_roleplay_api.ports import PersonaRepository
from haruhi_roleplay_api.ports import RagIngestService
from haruhi_roleplay_api.ports import RagService


def post_rag_document(
    body: Mapping[str, Any],
    *,
    persona_repository: PersonaRepository,
    request_id: RequestId | str,
    rag_ingest_service: RagIngestService | None = None,
    include_error_details: bool = False,
) -> ApiResponse:
    try:
        ingest_input = _rag_ingest_input_from_body(body)
        validation = ValidateRagDocumentMetadata(persona_repository).execute(
            ingest_input
        )
        if rag_ingest_service is None:
            result = validation
        else:
            result = rag_ingest_service.ingest(
                replace(ingest_input, documentId=validation.documentId)
            )
    except Exception as exc:
        return error_response(
            exc,
            request_id,
            include_details=include_error_details,
        )
    return success_response(_rag_ingest_result_to_data(result), request_id)


def post_rag_search(
    body: Mapping[str, Any],
    *,
    rag_service: RagService,
    request_id: RequestId | str,
    include_error_details: bool = False,
) -> ApiResponse:
    try:
        retrieve_input = _rag_retrieve_input_from_body(body)
        result = rag_service.retrieve(retrieve_input)
    except Exception as exc:
        return error_response(
            exc,
            request_id,
            include_details=include_error_details,
        )
    return success_response(_rag_retrieve_output_to_data(result), request_id)


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
        "appId": body.get("app_id"),
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


def _rag_retrieve_input_from_body(body: Mapping[str, Any]) -> RagRetrieveInput:
    if not isinstance(body, Mapping):
        raise DTOValidationError("request body must be an object")
    return RagRetrieveInput(
        appId=AppId(_require_non_empty(body.get("app_id"), "app_id")),
        userId=UserId(_require_non_empty(body.get("user_id"), "user_id")),
        characterId=CharacterId(
            _require_non_empty(body.get("character_id"), "character_id")
        ),
        personaMode=PersonaModeId(
            _require_non_empty(body.get("persona_mode"), "persona_mode")
        ),
        query=_require_non_empty(body.get("query"), "query"),
        topK=_top_k(body.get("top_k", 5)),
        filters=_rag_retrieve_filters_from_body(body.get("filters", {})),
        debug=bool(body.get("debug", False)),
    )


def _rag_retrieve_filters_from_body(data: Any) -> RagRetrieveFilters:
    if not isinstance(data, Mapping):
        raise DTOValidationError("filters must be an object")
    return RagRetrieveFilters(
        sourceTypes=_string_tuple(data.get("source_types", ())),
        timelines=_string_tuple(data.get("timelines", ())),
        spoilerLevelMax=(
            int(data["spoiler_level_max"])
            if data.get("spoiler_level_max") is not None
            else None
        ),
        language=data.get("language"),
    )


def _rag_retrieve_output_to_data(result: RagRetrieveOutput) -> dict[str, Any]:
    return {
        "provider": result.provider,
        "hit_count": len(result.chunks),
        "raw_hit_count": result.rawHitCount,
        "filtered_hit_count": result.filteredHitCount,
        "rerank_applied": result.rerankApplied,
        "chunks": [
            {
                **chunk.to_source_mapping(),
                "content": chunk.content,
            }
            for chunk in result.chunks
        ],
    }


def _top_k(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError("top_k must be an integer") from exc


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list | tuple):
        raise DTOValidationError("filter list must be an array")
    return tuple(str(item) for item in value)


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value
