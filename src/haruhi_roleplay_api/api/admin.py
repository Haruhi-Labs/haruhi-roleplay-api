"""后台总览与全局用量 API。"""

from __future__ import annotations

from typing import Any, Mapping

from haruhi_roleplay_api.api.responses import ApiResponse, error_response, success_response
from haruhi_roleplay_api.application.access_tokens import (
    GetAccessTokenUsageOverview,
    ListAllAccessTokenRequestLogs,
)
from haruhi_roleplay_api.domain import DTOValidationError, RequestId
from haruhi_roleplay_api.ports import AccessTokenStore


def get_admin_usage(
    query: Mapping[str, Any],
    *,
    store: AccessTokenStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        days = _bounded_int(query.get("days"), default=30, minimum=1, maximum=90)
        overview = GetAccessTokenUsageOverview(store).execute(days=days)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(overview.to_mapping(), request_id)


def get_admin_request_logs(
    query: Mapping[str, Any],
    *,
    store: AccessTokenStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        limit = _bounded_int(query.get("limit"), default=50, minimum=1, maximum=200)
        items = ListAllAccessTokenRequestLogs(store).execute(limit=limit)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {
            "count": len(items),
            "items": [item.to_mapping() for item in items],
        },
        request_id,
    )


def get_admin_audit_logs(
    query: Mapping[str, Any],
    *,
    store: AccessTokenStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        limit = _bounded_int(query.get("limit"), default=100, minimum=1, maximum=200)
        items = store.list_admin_events(limit=limit)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {
            "count": len(items),
            "items": [item.to_mapping() for item in items],
        },
        request_id,
    )


def _bounded_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise DTOValidationError(
            f"value must be an integer between {minimum} and {maximum}"
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError(
            f"value must be an integer between {minimum} and {maximum}"
        ) from exc
    if not minimum <= parsed <= maximum:
        raise DTOValidationError(
            f"value must be an integer between {minimum} and {maximum}"
        )
    return parsed
