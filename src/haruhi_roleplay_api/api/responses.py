"""Framework-agnostic API response envelopes."""

from __future__ import annotations

from typing import Any, Mapping

from haruhi_roleplay_api.application.errors import AppError, app_error_from_exception
from haruhi_roleplay_api.domain import RequestId

ApiResponse = dict[str, Any]


def _request_id_value(request_id: RequestId | str) -> str:
    value = str(request_id)
    if not value.strip():
        raise ValueError("request_id must be a non-empty string")
    return value


def success_response(data: Any, request_id: RequestId | str) -> ApiResponse:
    return {
        "ok": True,
        "data": data,
        "request_id": _request_id_value(request_id),
    }


def error_response(
    error: AppError | Exception,
    request_id: RequestId | str,
    *,
    include_details: bool = False,
) -> ApiResponse:
    app_error = app_error_from_exception(error)
    error_body: dict[str, Any] = {
        "code": app_error.code.value,
        "message": app_error.public_message,
    }
    if include_details and app_error.details:
        error_body["details"] = dict(app_error.details)
    return {
        "ok": False,
        "error": error_body,
        "request_id": _request_id_value(request_id),
    }


def response_status(error: AppError | Exception) -> int:
    return app_error_from_exception(error).http_status


def error_body_from_mapping(body: Mapping[str, Any]) -> Mapping[str, Any]:
    """Small helper for tests and future framework adapters."""

    return body.get("error", {})
