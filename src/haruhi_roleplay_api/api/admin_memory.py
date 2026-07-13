"""长期记忆后台管理 API。"""

from __future__ import annotations

from typing import Any, Mapping

from haruhi_roleplay_api.api.responses import (
    ApiResponse,
    error_response,
    success_response,
)
from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    DTOValidationError,
    MemoryAdminQuery,
    MemoryId,
    MemoryType,
    MemoryWriteCandidate,
    MemoryWriteCommand,
    PersonaModeId,
    RequestId,
    UserId,
)
from haruhi_roleplay_api.ports import MemoryStore


def get_admin_memories(
    query: Mapping[str, Any],
    *,
    memory_store: MemoryStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        admin_query = MemoryAdminQuery(
            appId=_optional_text(query.get("app_id"), "app_id"),
            userId=_optional_text(query.get("user_id"), "user_id"),
            characterId=_optional_text(query.get("character_id"), "character_id"),
            personaMode=_optional_text(query.get("persona_mode"), "persona_mode"),
            memoryType=_optional_memory_type(query.get("type")),
            limit=_integer(query.get("limit"), "limit", default=100),
            offset=_integer(query.get("offset"), "offset", default=0),
        )
        page = memory_store.admin_list_memories(admin_query)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {
            "provider": _provider_name(memory_store),
            "total": page.total,
            "count": len(page.items),
            "limit": admin_query.limit,
            "offset": admin_query.offset,
            "items": [item.to_mapping() for item in page.items],
        },
        request_id,
    )


def post_admin_memory(
    body: Mapping[str, Any],
    *,
    memory_store: MemoryStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        command = MemoryWriteCommand(
            appId=AppId(_required_text(body.get("app_id"), "app_id")),
            userId=UserId(_required_text(body.get("user_id"), "user_id")),
            characterId=CharacterId(
                _required_text(body.get("character_id"), "character_id")
            ),
            personaMode=PersonaModeId(
                _required_text(body.get("persona_mode"), "persona_mode")
            ),
            candidate=MemoryWriteCandidate.from_mapping(
                {
                    "type": body.get("type"),
                    "content": body.get("content"),
                    "reason": body.get("reason"),
                    "confidence": body.get("confidence"),
                }
            ),
        )
        item = memory_store.add_memory(command)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {"created": True, "item": item.to_mapping()},
        request_id,
    )


def delete_admin_memory(
    memory_id: str,
    *,
    memory_store: MemoryStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        clean_memory_id = _required_text(memory_id, "memory_id")
        deleted = memory_store.admin_delete_memory(MemoryId(clean_memory_id))
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {
            "memory_id": str(deleted.memoryId),
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


def _optional_memory_type(value: Any) -> MemoryType | None:
    if value is None:
        return None
    raw_value = _required_text(value, "type")
    try:
        return MemoryType(raw_value)
    except ValueError as exc:
        raise DTOValidationError(f"memory type is not supported: {raw_value}") from exc


def _integer(value: Any, field_name: str, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError(f"{field_name} must be an integer") from exc


def _provider_name(memory_store: MemoryStore) -> str:
    name = type(memory_store).__name__
    if name == "SQLiteMemoryStore":
        return "sqlite"
    if name == "InMemoryMemoryStore":
        return "memory"
    return name
