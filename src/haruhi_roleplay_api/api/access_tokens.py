"""访问令牌管理 API。"""

from __future__ import annotations

from typing import Any, Mapping

from haruhi_roleplay_api.api.responses import ApiResponse, error_response, success_response
from haruhi_roleplay_api.application.access_tokens import (
    CreateAccessToken,
    GetAccessToken,
    ListAccessTokens,
    ListAccessTokenRequestLogs,
    RevokeAccessToken,
    UpdateAccessTokenQuota,
)
from haruhi_roleplay_api.domain import DTOValidationError, RequestId
from haruhi_roleplay_api.ports import AccessTokenStore


def post_access_token(
    body: Mapping[str, Any],
    *,
    store: AccessTokenStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        issued = CreateAccessToken(store).execute(
            app_id=_required_text(body.get("app_id"), "app_id"),
            name=_required_text(body.get("name"), "name"),
            quota_tokens=_optional_positive_int(
                body.get("quota_tokens"),
                "quota_tokens",
            ),
            daily_quota_tokens=_optional_positive_int(
                body.get("daily_quota_tokens"),
                "daily_quota_tokens",
            ),
            weekly_quota_tokens=_optional_positive_int(
                body.get("weekly_quota_tokens"),
                "weekly_quota_tokens",
            ),
            expires_at=_optional_text(body.get("expires_at"), "expires_at"),
        )
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {
            **issued.token.to_mapping(),
            "token": issued.secret,
            "token_notice": "令牌明文只显示一次，请立即安全保存。",
        },
        request_id,
    )


def get_access_tokens(
    *,
    store: AccessTokenStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        items = ListAccessTokens(store).execute()
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {"count": len(items), "items": [item.to_mapping() for item in items]},
        request_id,
    )


def get_access_token(
    token_id: str,
    *,
    store: AccessTokenStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        item = GetAccessToken(store).execute(token_id)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(item.to_mapping(), request_id)


def delete_access_token(
    token_id: str,
    *,
    store: AccessTokenStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        item = RevokeAccessToken(store).execute(token_id)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(item.to_mapping(), request_id)


def patch_access_token(
    token_id: str,
    body: Mapping[str, Any],
    *,
    store: AccessTokenStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        quota_fields = (
            "quota_tokens",
            "daily_quota_tokens",
            "weekly_quota_tokens",
        )
        if not any(field in body for field in quota_fields):
            raise DTOValidationError("at least one quota field is required")
        quota_updates = {
            field_name: (
                None
                if body.get(field_name) is None
                else _optional_positive_int(body.get(field_name), field_name)
            )
            for field_name in quota_fields
            if field_name in body
        }
        item = UpdateAccessTokenQuota(store).execute(token_id, **quota_updates)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(item.to_mapping(), request_id)


def get_access_token_logs(
    token_id: str,
    query: Mapping[str, Any],
    *,
    store: AccessTokenStore,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        limit = _optional_positive_int(query.get("limit"), "limit") or 50
        items = ListAccessTokenRequestLogs(store).execute(token_id, limit=limit)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(
        {
            "token_id": token_id,
            "count": len(items),
            "items": [item.to_mapping() for item in items],
        },
        request_id,
    )


def _required_text(value: Any, field_name: str) -> str:
    if value is None or not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _optional_positive_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise DTOValidationError(f"{field_name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError(
            f"{field_name} must be a positive integer"
        ) from exc
    if parsed <= 0:
        raise DTOValidationError(f"{field_name} must be a positive integer")
    return parsed
