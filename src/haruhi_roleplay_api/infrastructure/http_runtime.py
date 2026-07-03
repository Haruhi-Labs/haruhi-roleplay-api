"""Minimal HTTP runtime adapter for local development and smoke tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

from haruhi_roleplay_api.adapters import (
    InMemoryMemoryStore,
    InMemorySessionStore,
    LocalPersonaRepository,
    LocalRagService,
)
from haruhi_roleplay_api.api.chat import post_chat, post_chat_stream
from haruhi_roleplay_api.api.memory import delete_memory, get_memory
from haruhi_roleplay_api.api.personas import get_personas
from haruhi_roleplay_api.api.rag import post_rag_document
from haruhi_roleplay_api.api.responses import ApiResponse, error_response
from haruhi_roleplay_api.api.sessions import post_session
from haruhi_roleplay_api.application import PersonaPromptBuilder
from haruhi_roleplay_api.application.errors import AppError, ERROR_STATUS, ErrorCode
from haruhi_roleplay_api.domain import DTOValidationError
from haruhi_roleplay_api.infrastructure.models import (
    ModelProviderSettings,
    build_model_router,
)


@dataclass(frozen=True, kw_only=True)
class HttpRuntimeResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True, kw_only=True)
class HttpRuntimeSettings:
    host: str = "127.0.0.1"
    port: int = 8000
    api_key: str | None = None
    debug_trace_enabled: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "HttpRuntimeSettings":
        return cls(
            host=env.get("HOST", env.get("ROLEPLAY_HOST", "127.0.0.1")),
            port=_int_from_env(env, "PORT", "ROLEPLAY_PORT", default=8000),
            api_key=env.get("ROLEPLAY_API_KEY"),
            debug_trace_enabled=_bool_from_env(
                env.get("ENABLE_DEBUG_TRACE", "true")
            ),
        )


class RoleplayHttpRuntime:
    def __init__(
        self,
        *,
        persona_repository: LocalPersonaRepository,
        prompt_builder: PersonaPromptBuilder,
        model_router: object,
        session_store: InMemorySessionStore,
        memory_store: InMemoryMemoryStore,
        rag_service: LocalRagService,
        api_key: str | None = None,
        debug_trace_enabled: bool = True,
    ) -> None:
        self._persona_repository = persona_repository
        self._prompt_builder = prompt_builder
        self._model_router = model_router
        self._session_store = session_store
        self._memory_store = memory_store
        self._rag_service = rag_service
        self._api_key = api_key
        self._debug_trace_enabled = debug_trace_enabled

    @classmethod
    def local(cls, *, project_root: Path, env: Mapping[str, str]) -> "RoleplayHttpRuntime":
        settings = HttpRuntimeSettings.from_env(env)
        rag_service = LocalRagService()
        return cls(
            persona_repository=LocalPersonaRepository(project_root / "personas"),
            prompt_builder=PersonaPromptBuilder(),
            model_router=build_model_router(ModelProviderSettings.from_mapping(env)),
            session_store=InMemorySessionStore(),
            memory_store=InMemoryMemoryStore(),
            rag_service=rag_service,
            api_key=settings.api_key,
            debug_trace_enabled=settings.debug_trace_enabled,
        )

    def handle(
        self,
        *,
        method: str,
        target: str,
        headers: Mapping[str, str],
        body: bytes = b"",
    ) -> HttpRuntimeResponse:
        headers = _normalized_headers(headers)
        request_id = _request_id(headers)
        if method == "OPTIONS":
            return _empty_response(204)
        if not self._is_authorized(headers):
            return _json_response(
                error_response(
                    AppError(code=ErrorCode.AUTH_INVALID_API_KEY),
                    request_id,
                ),
            )

        parsed = urlparse(target)
        path_parts = _path_parts(parsed.path)
        query = _query_params(parsed.query)
        json_body = _json_body(body, request_id)
        if isinstance(json_body, HttpRuntimeResponse):
            return json_body

        if method == "GET" and path_parts == ["health"]:
            return _json_response(
                {
                    "ok": True,
                    "data": {"status": "ok"},
                    "request_id": request_id,
                }
            )
        if method == "GET" and path_parts == ["v1", "personas"]:
            return _json_response(
                get_personas(self._persona_repository, request_id),
            )
        if method == "POST" and path_parts == ["v1", "sessions"]:
            return _json_response(
                post_session(
                    json_body,
                    session_store=self._session_store,
                    request_id=request_id,
                )
            )
        if method == "POST" and path_parts == ["v1", "chat"]:
            return _json_response(
                post_chat(
                    json_body,
                    persona_repository=self._persona_repository,
                    prompt_builder=self._prompt_builder,
                    model_router=self._model_router,
                    session_store=self._session_store,
                    memory_store=self._memory_store,
                    rag_service=self._rag_service,
                    request_id=request_id,
                    debug_trace_enabled=self._debug_trace_enabled,
                )
            )
        if method == "POST" and path_parts == ["v1", "chat", "stream"]:
            return self._stream_chat(json_body, request_id)
        if method == "POST" and path_parts == ["v1", "rag", "documents"]:
            return _json_response(
                post_rag_document(
                    json_body,
                    persona_repository=self._persona_repository,
                    rag_ingest_service=self._rag_service,
                    request_id=request_id,
                )
            )
        if method == "GET" and len(path_parts) == 3 and path_parts[:2] == ["v1", "memory"]:
            return _json_response(
                get_memory(
                    path_parts[2],
                    query,
                    memory_store=self._memory_store,
                    request_id=request_id,
                )
            )
        if (
            method == "DELETE"
            and len(path_parts) == 4
            and path_parts[:2] == ["v1", "memory"]
        ):
            return _json_response(
                delete_memory(
                    path_parts[2],
                    path_parts[3],
                    query,
                    memory_store=self._memory_store,
                    request_id=request_id,
                )
            )
        return _json_response(
            {
                "ok": False,
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Route was not found.",
                },
                "request_id": request_id,
            },
            status=404,
        )

    def _stream_chat(
        self,
        body: Mapping[str, Any],
        request_id: str,
    ) -> HttpRuntimeResponse:
        response = post_chat_stream(
            body,
            persona_repository=self._persona_repository,
            prompt_builder=self._prompt_builder,
            model_router=self._model_router,
            session_store=self._session_store,
            memory_store=self._memory_store,
            rag_service=self._rag_service,
            request_id=request_id,
            debug_trace_enabled=self._debug_trace_enabled,
        )
        if not response.get("ok", False):
            return _json_response(response)
        events = response.get("data", {}).get("events", [])
        return HttpRuntimeResponse(
            status=200,
            headers={
                **_base_headers(),
                "Content-Type": "text/event-stream; charset=utf-8",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
            body=_sse_body(events),
        )

    def _is_authorized(self, headers: Mapping[str, str]) -> bool:
        if not self._api_key:
            return True
        authorization = headers.get("authorization", "")
        api_key = headers.get("x-api-key", "")
        return authorization == f"Bearer {self._api_key}" or api_key == self._api_key


def create_local_runtime(env: Mapping[str, str]) -> RoleplayHttpRuntime:
    return RoleplayHttpRuntime.local(project_root=_project_root(), env=env)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _request_id(headers: Mapping[str, str]) -> str:
    value = headers.get("x-request-id")
    if value and value.strip():
        return value.strip()
    return f"req-{uuid4().hex}"


def _normalized_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def _path_parts(path: str) -> list[str]:
    return [unquote(part) for part in path.strip("/").split("/") if part]


def _query_params(query: str) -> dict[str, Any]:
    parsed = parse_qs(query, keep_blank_values=True)
    return {
        key: values[0] if len(values) == 1 else values
        for key, values in parsed.items()
    }


def _json_body(body: bytes, request_id: str) -> Mapping[str, Any] | HttpRuntimeResponse:
    if not body:
        return {}
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _json_response(
            error_response(
                DTOValidationError("request body must be valid JSON"),
                request_id,
            )
        )
    if not isinstance(data, Mapping):
        return _json_response(
            error_response(
                DTOValidationError("request body must be an object"),
                request_id,
            )
        )
    return data


def _json_response(
    response: ApiResponse | Mapping[str, Any],
    status: int | None = None,
) -> HttpRuntimeResponse:
    return HttpRuntimeResponse(
        status=status or _status_from_response(response),
        headers={**_base_headers(), "Content-Type": "application/json; charset=utf-8"},
        body=json.dumps(response, ensure_ascii=False).encode("utf-8"),
    )


def _empty_response(status: int) -> HttpRuntimeResponse:
    return HttpRuntimeResponse(status=status, headers=_base_headers(), body=b"")


def _base_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, X-API-Key, X-Request-Id",
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    }


def _status_from_response(response: Mapping[str, Any]) -> int:
    if response.get("ok", False):
        return 200
    code = response.get("error", {}).get("code")
    try:
        return ERROR_STATUS[ErrorCode(str(code))]
    except (KeyError, ValueError):
        return 500


def _sse_body(events: list[Mapping[str, Any]]) -> bytes:
    lines: list[str] = []
    for event in events:
        event_name = str(event.get("event", "message"))
        data = event.get("data", {})
        lines.append(f"event: {event_name}")
        lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
        lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _int_from_env(
    env: Mapping[str, str],
    *keys: str,
    default: int,
) -> int:
    for key in keys:
        value = env.get(key)
        if value is not None:
            return int(value)
    return default


def _bool_from_env(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "no", "off"}
