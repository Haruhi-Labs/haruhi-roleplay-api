"""Session API handlers."""

from __future__ import annotations

from typing import Any, Mapping

from haruhi_roleplay_api.api.responses import ApiResponse, error_response, success_response
from haruhi_roleplay_api.application.sessions import (
    CreateSessionInput,
    CreateSessionUseCase,
)
from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    DTOValidationError,
    PersonaModeId,
    RequestId,
    Session,
    UserId,
)
from haruhi_roleplay_api.ports import SessionStore


def post_session(
    body: Mapping[str, Any],
    *,
    session_store: SessionStore,
    request_id: RequestId | str,
    include_error_details: bool = False,
) -> ApiResponse:
    try:
        session = CreateSessionUseCase(session_store).execute(
            _session_input_from_body(body)
        )
    except Exception as exc:
        return error_response(
            exc,
            request_id,
            include_details=include_error_details,
        )
    return success_response(_session_to_data(session), request_id)


def _session_input_from_body(body: Mapping[str, Any]) -> CreateSessionInput:
    if not isinstance(body, Mapping):
        raise DTOValidationError("request body must be an object")
    return CreateSessionInput(
        appId=AppId(_require_non_empty(body.get("app_id"), "app_id")),
        userId=UserId(_require_non_empty(body.get("user_id"), "user_id")),
        characterId=CharacterId(
            _require_non_empty(body.get("character_id"), "character_id")
        ),
        personaMode=PersonaModeId(
            _require_non_empty(body.get("persona_mode"), "persona_mode")
        ),
    )


def _session_to_data(session: Session) -> dict[str, str]:
    return {
        "session_id": str(session.sessionId),
        "status": session.status.value,
        "created_at": session.createdAt,
    }


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value

