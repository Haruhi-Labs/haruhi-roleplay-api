"""角色与 Persona 模式后台管理 API。"""

from __future__ import annotations

from typing import Any, Mapping

from haruhi_roleplay_api.adapters.personas import LocalPersonaRepository
from haruhi_roleplay_api.api.responses import ApiResponse, error_response, success_response
from haruhi_roleplay_api.domain import DTOValidationError, RequestId


def get_admin_personas(
    *,
    repository: LocalPersonaRepository,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        data = repository.admin_catalog()
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(data, request_id)


def get_admin_persona(
    character_id: str,
    *,
    repository: LocalPersonaRepository,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        data = repository.get_admin_character(character_id)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(data, request_id)


def post_admin_persona(
    body: Mapping[str, Any],
    *,
    repository: LocalPersonaRepository,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        character = _mapping(body.get("character"), "character")
        presets = _mapping_tuple(body.get("presets"), "presets")
        data = repository.create_character(character, presets)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(data, request_id)


def patch_admin_persona(
    character_id: str,
    body: Mapping[str, Any],
    *,
    repository: LocalPersonaRepository,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        data = repository.update_character(
            character_id,
            _mapping(body.get("character"), "character"),
        )
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(data, request_id)


def delete_admin_persona(
    character_id: str,
    *,
    repository: LocalPersonaRepository,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        data = repository.delete_character(character_id)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(data, request_id)


def post_admin_persona_preset(
    character_id: str,
    body: Mapping[str, Any],
    *,
    repository: LocalPersonaRepository,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        data = repository.create_preset(
            character_id,
            _mapping(body.get("preset"), "preset"),
        )
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(data, request_id)


def patch_admin_persona_preset(
    character_id: str,
    persona_mode: str,
    body: Mapping[str, Any],
    *,
    repository: LocalPersonaRepository,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        data = repository.update_preset(
            character_id,
            persona_mode,
            _mapping(body.get("preset"), "preset"),
        )
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(data, request_id)


def delete_admin_persona_preset(
    character_id: str,
    persona_mode: str,
    *,
    repository: LocalPersonaRepository,
    request_id: RequestId | str,
) -> ApiResponse:
    try:
        data = repository.delete_preset(character_id, persona_mode)
    except Exception as exc:
        return error_response(exc, request_id)
    return success_response(data, request_id)


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DTOValidationError(f"{field_name} must be an object")
    return value


def _mapping_tuple(value: Any, field_name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise DTOValidationError(f"{field_name} must be an array")
    return tuple(_mapping(item, f"{field_name} item") for item in value)
