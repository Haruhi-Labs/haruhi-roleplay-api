"""RAG 后台文档管理 API。"""

from __future__ import annotations

from typing import Any, Mapping

from haruhi_roleplay_api.api.responses import ApiResponse, error_response, success_response
from haruhi_roleplay_api.domain import DTOValidationError, RequestId
from haruhi_roleplay_api.ports import RagAdminService


_MAX_DOCUMENT_LIST_LIMIT = 200


def get_admin_rag_documents(
    query: Mapping[str, Any],
    *,
    service: RagAdminService,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        app_id = _optional_text(query.get("app_id"), "app_id")
        if _optional_bool(query.get("summary"), "summary"):
            point_counter = getattr(service, "count_points", None)
            if callable(point_counter):
                chunk_count = point_counter(app_id=app_id)
            else:
                documents = service.list_documents(app_id=app_id)
                chunk_count = sum(item.chunkCount for item in documents)
            return success_response(
                {
                    "provider": str(getattr(service, "provider_name", "unknown")),
                    "app_id": app_id,
                    "chunk_count": chunk_count,
                    "summary": True,
                },
                request_id,
            )

        limit = _optional_int(
            query.get("limit"),
            "limit",
            minimum=1,
            maximum=_MAX_DOCUMENT_LIST_LIMIT,
        )
        truncated = False
        if limit is None:
            items = service.list_documents(app_id=app_id)
        else:
            scoped_app_id = _required_text(app_id, "app_id")
            limited_listing = getattr(service, "list_documents_limited", None)
            if callable(limited_listing):
                items, truncated = limited_listing(
                    app_id=scoped_app_id,
                    limit=limit,
                )
            else:
                all_items = service.list_documents(app_id=scoped_app_id)
                items = all_items[:limit]
                truncated = len(all_items) > limit
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {
            "provider": str(getattr(service, "provider_name", "unknown")),
            "app_id": app_id,
            "count": len(items),
            "items": [item.to_mapping() for item in items],
            "limit": limit,
            "truncated": truncated,
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


def _optional_bool(value: Any, field_name: str) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "1"}:
        return True
    if isinstance(value, str) and value.strip().lower() in {"false", "0"}:
        return False
    raise DTOValidationError(f"{field_name} 必须是布尔值")


def _optional_int(
    value: Any,
    field_name: str,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise DTOValidationError(f"{field_name} 必须是整数")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError(f"{field_name} 必须是整数") from exc
    if parsed < minimum or parsed > maximum:
        raise DTOValidationError(
            f"{field_name} 必须介于 {minimum} 和 {maximum} 之间"
        )
    return parsed
