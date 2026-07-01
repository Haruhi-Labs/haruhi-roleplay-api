"""Persona catalog API handlers."""

from __future__ import annotations

from haruhi_roleplay_api.api.responses import (
    ApiResponse,
    error_response,
    success_response,
)
from haruhi_roleplay_api.application.personas import ListPublicPersonas
from haruhi_roleplay_api.domain import RequestId
from haruhi_roleplay_api.ports import PersonaRepository


def get_personas(
    repository: PersonaRepository,
    request_id: RequestId | str,
    *,
    include_error_details: bool = False,
) -> ApiResponse:
    try:
        data = ListPublicPersonas(repository).execute()
    except Exception as exc:
        return error_response(
            exc,
            request_id,
            include_details=include_error_details,
        )
    return success_response(data, request_id)
