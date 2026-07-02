"""Memory API handlers."""

from __future__ import annotations

from typing import Any, Mapping

from haruhi_roleplay_api.api.responses import ApiResponse, error_response, success_response
from haruhi_roleplay_api.application.memory import (
    DeleteMemoryUseCase,
    ListMemoryUseCase,
)
from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    DTOValidationError,
    MemoryDeleteCommand,
    MemoryId,
    MemoryItem,
    MemoryQuery,
    MemoryType,
    PersonaModeId,
    RequestId,
    UserId,
)
from haruhi_roleplay_api.ports import MemoryStore


def get_memory(
    user_id: str,
    query: Mapping[str, Any],
    *,
    memory_store: MemoryStore,
    request_id: RequestId | str,
    include_error_details: bool = False,
) -> ApiResponse:
    try:
        memory_query = _memory_query_from_params(user_id, query)
        items = ListMemoryUseCase(memory_store).execute(memory_query)
    except Exception as exc:
        return error_response(
            exc,
            request_id,
            include_details=include_error_details,
        )
    return success_response(_memory_list_to_data(memory_query, items), request_id)


def delete_memory(
    user_id: str,
    memory_id: str,
    query: Mapping[str, Any],
    *,
    memory_store: MemoryStore,
    request_id: RequestId | str,
    include_error_details: bool = False,
) -> ApiResponse:
    try:
        command = _memory_delete_command_from_params(user_id, memory_id, query)
        deleted = DeleteMemoryUseCase(memory_store).execute(command)
    except Exception as exc:
        return error_response(
            exc,
            request_id,
            include_details=include_error_details,
        )
    return success_response(
        {"memory_id": str(deleted.memoryId), "deleted": True},
        request_id,
    )


def _memory_query_from_params(
    user_id: str,
    query: Mapping[str, Any],
) -> MemoryQuery:
    if not isinstance(query, Mapping):
        raise DTOValidationError("query params must be an object")
    return MemoryQuery(
        appId=AppId(_require_non_empty(query.get("app_id"), "app_id")),
        userId=UserId(_require_non_empty(user_id, "user_id")),
        characterId=CharacterId(
            _require_non_empty(query.get("character_id"), "character_id")
        ),
        personaMode=_optional_persona_mode(query.get("persona_mode")),
        memoryTypes=_memory_types_from_params(query.get("type")),
        limit=_limit_from_params(query.get("limit")),
    )


def _memory_delete_command_from_params(
    user_id: str,
    memory_id: str,
    query: Mapping[str, Any],
) -> MemoryDeleteCommand:
    if not isinstance(query, Mapping):
        raise DTOValidationError("query params must be an object")
    return MemoryDeleteCommand(
        memoryId=MemoryId(_require_non_empty(memory_id, "memory_id")),
        appId=AppId(_require_non_empty(query.get("app_id"), "app_id")),
        userId=UserId(_require_non_empty(user_id, "user_id")),
        characterId=CharacterId(
            _require_non_empty(query.get("character_id"), "character_id")
        ),
        personaMode=_optional_persona_mode(query.get("persona_mode")),
    )


def _memory_list_to_data(
    query: MemoryQuery,
    items: tuple[MemoryItem, ...],
) -> dict[str, Any]:
    return {
        "app_id": str(query.appId),
        "user_id": str(query.userId),
        "character_id": str(query.characterId),
        "persona_mode": (
            str(query.personaMode) if query.personaMode is not None else None
        ),
        "count": len(items),
        "items": [item.to_mapping() for item in items],
    }


def _optional_persona_mode(value: str | None) -> PersonaModeId | None:
    if value is None:
        return None
    return PersonaModeId(_require_non_empty(value, "persona_mode"))


def _memory_types_from_params(value: Any) -> tuple[MemoryType, ...]:
    if value is None:
        return ()
    values = value if isinstance(value, (list, tuple)) else (value,)
    return tuple(_memory_type_from_value(raw_value) for raw_value in values)


def _memory_type_from_value(value: Any) -> MemoryType:
    raw_value = _require_non_empty(value, "type")
    try:
        return MemoryType(raw_value)
    except ValueError as exc:
        raise DTOValidationError(f"memory type is not supported: {raw_value}") from exc


def _limit_from_params(value: Any) -> int:
    if value is None:
        return 50
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError("limit must be an integer") from exc
    if limit <= 0:
        raise DTOValidationError("limit must be positive")
    return min(limit, 100)


def _require_non_empty(value: Any, field_name: str) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value
