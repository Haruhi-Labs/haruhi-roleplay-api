"""访问令牌管理 API。"""

from __future__ import annotations

from typing import Any, Mapping

from haruhi_roleplay_api.api.responses import ApiResponse, error_response, success_response
from haruhi_roleplay_api.application.access_tokens import (
    CreateAccessToken,
    GetAccessToken,
    ListAccessTokens,
    RevokeAccessToken,
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
            name=_required_text(body.get("name"), "name"),
            quota_tokens=_optional_positive_int(body.get("quota_tokens")),
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


def _required_text(value: Any, field_name: str) -> str:
    if value is None or not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise DTOValidationError("quota_tokens must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError("quota_tokens must be a positive integer") from exc
    if parsed <= 0:
        raise DTOValidationError("quota_tokens must be a positive integer")
    return parsed
