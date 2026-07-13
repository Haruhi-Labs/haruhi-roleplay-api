"""RAG 后台文档管理 API。"""

from __future__ import annotations

from typing import Any, Mapping

from haruhi_roleplay_api.api.responses import ApiResponse, error_response, success_response
from haruhi_roleplay_api.domain import DTOValidationError, RequestId
from haruhi_roleplay_api.ports import RagAdminService


def get_admin_rag_documents(
    query: Mapping[str, Any],
    *,
    service: RagAdminService,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        app_id = _optional_text(query.get("app_id"), "app_id")
        items = service.list_documents(app_id=app_id)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {
            "provider": str(getattr(service, "provider_name", "unknown")),
            "app_id": app_id,
            "count": len(items),
            "items": [item.to_mapping() for item in items],
        },
        request_id,
    )


def delete_admin_rag_document(
    document_id: str,
    query: Mapping[str, Any],
    *,
    service: RagAdminService,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        app_id = _required_text(query.get("app_id"), "app_id")
        clean_document_id = _required_text(document_id, "document_id")
        removed_chunks = service.delete_document(
            app_id=app_id,
            document_id=clean_document_id,
        )
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {
            "app_id": app_id,
            "document_id": clean_document_id,
            "removed_chunks": removed_chunks,
            "deleted": True,
        },
        request_id,
    )


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)
