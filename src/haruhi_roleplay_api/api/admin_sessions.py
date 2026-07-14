"""运行会话后台管理 API。"""

from __future__ import annotations

from typing import Any, Mapping

from haruhi_roleplay_api.api.responses import (
    ApiResponse,
    error_response,
    success_response,
)
from haruhi_roleplay_api.domain import (
    DTOValidationError,
    RequestId,
    SessionAdminQuery,
    SessionStatus,
)
from haruhi_roleplay_api.ports import SessionStore


def get_admin_sessions(
    query: Mapping[str, Any],
    *,
    session_store: SessionStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        admin_query = SessionAdminQuery(
            appId=_optional_text(query.get("app_id"), "app_id"),
            userId=_optional_text(query.get("user_id"), "user_id"),
            characterId=_optional_text(query.get("character_id"), "character_id"),
            status=_optional_status(query.get("status")),
            limit=_integer(query.get("limit"), "limit", default=100),
            offset=_integer(query.get("offset"), "offset", default=0),
        )
        page = session_store.admin_list_sessions(admin_query)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {
            "provider": _provider_name(session_store),
            "total": page.total,
            "count": len(page.items),
            "limit": admin_query.limit,
            "offset": admin_query.offset,
            "items": [item.to_mapping() for item in page.items],
        },
        request_id,
    )


def delete_admin_session(
    session_id: str,
    *,
    session_store: SessionStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        clean_session_id = _required_text(session_id, "session_id")
        session = session_store.admin_close_session(clean_session_id)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {
            "session_id": str(session.sessionId),
            "status": session.status.value,
            "closed": True,
            "updated_at": session.updatedAt,
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


def _optional_status(value: Any) -> SessionStatus | None:
    if value is None:
        return None
    raw_value = _required_text(value, "status")
    try:
        return SessionStatus(raw_value)
    except ValueError as exc:
        raise DTOValidationError(f"session status is not supported: {raw_value}") from exc


def _integer(value: Any, field_name: str, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError(f"{field_name} must be an integer") from exc


def _provider_name(session_store: SessionStore) -> str:
    return {
        "InMemorySessionStore": "memory",
        "SQLiteSessionStore": "sqlite",
        "PostgresSessionStore": "postgres",
    }.get(type(session_store).__name__, type(session_store).__name__)
