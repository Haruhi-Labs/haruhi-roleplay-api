"""Minimal HTTP runtime adapter for local development and smoke tests."""

from __future__ import annotations

import json
import hmac
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

from haruhi_roleplay_api.adapters import (
    LocalPersonaRepository,
    SQLiteAccessTokenStore,
)
from haruhi_roleplay_api.api.access_tokens import (
    delete_access_token,
    get_access_token,
    get_access_token_logs,
    get_access_tokens,
    patch_access_token,
    post_access_token,
)
from haruhi_roleplay_api.api.chat import iter_chat_stream_events, post_chat
from haruhi_roleplay_api.api.memory import delete_memory, get_memory
from haruhi_roleplay_api.api.personas import get_personas
from haruhi_roleplay_api.api.rag import post_rag_document, post_rag_search
from haruhi_roleplay_api.api.responses import ApiResponse, error_response
from haruhi_roleplay_api.api.sessions import post_session
from haruhi_roleplay_api.application import PersonaPromptBuilder
from haruhi_roleplay_api.application.errors import (
    AppError,
    ERROR_STATUS,
    ErrorCode,
    app_error_from_exception,
)
from haruhi_roleplay_api.domain import DTOValidationError
from haruhi_roleplay_api.infrastructure.agent_planner_factory import (
    build_agent_context_planner_from_env,
)
from haruhi_roleplay_api.infrastructure.backend_context_provider_factory import (
    build_backend_context_provider_from_env,
)
from haruhi_roleplay_api.infrastructure.env_config_editor import EnvConfigEditor
from haruhi_roleplay_api.infrastructure.models import (
    ModelProviderSettings,
    build_model_router,
)
from haruhi_roleplay_api.infrastructure.memory_store_factory import (
    build_memory_store_from_env,
)
from haruhi_roleplay_api.infrastructure.rag_provider_factory import (
    build_rag_service_from_env,
)
from haruhi_roleplay_api.infrastructure.runtime_config import RuntimeConfigStore
from haruhi_roleplay_api.infrastructure.session_store_factory import (
    SessionStoreSettings,
    build_session_store,
)
from haruhi_roleplay_api.ports import (
    AccessTokenStore,
    AgentContextPlanner,
    MemoryStore,
    SessionStore,
)


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class HttpRuntimeResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True, kw_only=True)
class HttpRuntimeStreamResponse:
    status: int
    headers: Mapping[str, str]
    events: Iterable[Mapping[str, Any]]


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
        session_store: SessionStore,
        session_recent_limit: int,
        memory_store: MemoryStore,
        rag_service: object,
        backend_context_provider: object | None,
        agent_context_planner: AgentContextPlanner,
        runtime_config_store: RuntimeConfigStore,
        env_config_editor: EnvConfigEditor,
        access_token_store: AccessTokenStore,
        api_key: str | None = None,
        debug_trace_enabled: bool = True,
    ) -> None:
        self._persona_repository = persona_repository
        self._prompt_builder = prompt_builder
        self._model_router = model_router
        self._session_store = session_store
        self._session_recent_limit = session_recent_limit
        self._memory_store = memory_store
        self._rag_service = rag_service
        self._backend_context_provider = backend_context_provider
        self._agent_context_planner = agent_context_planner
        self._runtime_config_store = runtime_config_store
        self._env_config_editor = env_config_editor
        self._access_token_store = access_token_store
        self._api_key = api_key
        self._debug_trace_enabled = debug_trace_enabled

    @classmethod
    def local(
        cls,
        *,
        project_root: Path,
        env: Mapping[str, str],
        runtime_config_store: RuntimeConfigStore | None = None,
    ) -> "RoleplayHttpRuntime":
        config_store = runtime_config_store or RuntimeConfigStore.in_memory(env)
        runtime_env = config_store.env()
        settings = HttpRuntimeSettings.from_env(runtime_env)
        session_settings = SessionStoreSettings.from_mapping(runtime_env)
        return cls(
            persona_repository=LocalPersonaRepository(project_root / "personas"),
            prompt_builder=PersonaPromptBuilder(),
            model_router=build_model_router(
                ModelProviderSettings.from_mapping(runtime_env)
            ),
            session_store=build_session_store(session_settings),
            session_recent_limit=session_settings.recentMessageLimit,
            memory_store=build_memory_store_from_env(runtime_env),
            rag_service=build_rag_service_from_env(runtime_env),
            backend_context_provider=build_backend_context_provider_from_env(
                runtime_env
            ),
            agent_context_planner=build_agent_context_planner_from_env(runtime_env),
            runtime_config_store=config_store,
            env_config_editor=EnvConfigEditor(
                base_env=env,
                config_path=config_store.config_path,
            ),
            access_token_store=SQLiteAccessTokenStore(
                path=_access_token_path(project_root, runtime_env)
            ),
            api_key=settings.api_key,
            debug_trace_enabled=settings.debug_trace_enabled,
        )

    @classmethod
    def from_env_file(
        cls,
        *,
        project_root: Path,
        env: Mapping[str, str],
    ) -> "RoleplayHttpRuntime":
        return cls.local(
            project_root=project_root,
            env=env,
            runtime_config_store=RuntimeConfigStore.env_file(
                project_root=project_root,
                env=env,
            ),
        )

    def handle(
        self,
        *,
        method: str,
        target: str,
        headers: Mapping[str, str],
        body: bytes = b"",
    ) -> HttpRuntimeResponse | HttpRuntimeStreamResponse:
        normalized_headers = _normalized_headers(headers)
        request_id = _request_id(normalized_headers)
        normalized_headers["x-request-id"] = request_id
        access_token = self._access_token_from_headers(normalized_headers)
        started_at = perf_counter()
        parsed_path = urlparse(target).path
        try:
            if access_token is not None and _consumes_model_tokens(method, parsed_path):
                self._access_token_store.ensure_quota_available(access_token.tokenId)
            response = self._handle_request(
                method=method,
                target=target,
                headers=normalized_headers,
                body=body,
            )
        except AppError as exc:
            response = _json_response(error_response(exc, request_id))
        if access_token is None:
            return response
        if isinstance(response, HttpRuntimeStreamResponse):
            return HttpRuntimeStreamResponse(
                status=response.status,
                headers=response.headers,
                events=self._audited_stream_events(
                    response.events,
                    token_id=access_token.tokenId,
                    request_id=request_id,
                    method=method,
                    path=parsed_path,
                    status_code=response.status,
                    started_at=started_at,
                ),
            )
        self._record_access_token_request(
            token_id=access_token.tokenId,
            request_id=request_id,
            method=method,
            path=parsed_path,
            status_code=response.status,
            started_at=started_at,
            usage=_response_token_usage(response),
            error_code=_response_error_code(response),
        )
        return response

    def _handle_request(
        self,
        *,
        method: str,
        target: str,
        headers: Mapping[str, str],
        body: bytes = b"",
    ) -> HttpRuntimeResponse | HttpRuntimeStreamResponse:
        headers = _normalized_headers(headers)
        request_id = _request_id(headers)
        parsed = urlparse(target)
        static_response = _demo_static_response(method, parsed.path)
        if static_response is not None:
            return static_response
        if method == "OPTIONS":
            return _empty_response(204)
        if not self._is_authorized(headers):
            return _json_response(
                error_response(
                    AppError(code=ErrorCode.AUTH_INVALID_API_KEY),
                    request_id,
                ),
            )

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
        if len(path_parts) >= 2 and path_parts[:2] == ["v1", "env-config"]:
            return self._env_config(method, path_parts, json_body, headers, request_id)
        if len(path_parts) >= 2 and path_parts[:2] == ["v1", "access-tokens"]:
            return self._access_tokens(
                method,
                path_parts,
                query,
                json_body,
                headers,
                request_id,
            )
        if path_parts == ["v1", "runtime-config"]:
            return self._runtime_config(method, json_body, headers, request_id)
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
                    backend_context_provider=self._backend_context_provider,
                    agent_context_planner=self._agent_context_planner,
                    recent_message_limit=self._session_recent_limit,
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
        if method == "POST" and path_parts == ["v1", "rag", "search"]:
            return _json_response(
                post_rag_search(
                    json_body,
                    rag_service=self._rag_service,
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
    ) -> HttpRuntimeResponse | HttpRuntimeStreamResponse:
        try:
            event_iterator = iter(
                iter_chat_stream_events(
                    body,
                    persona_repository=self._persona_repository,
                    prompt_builder=self._prompt_builder,
                    model_router=self._model_router,
                    session_store=self._session_store,
                    memory_store=self._memory_store,
                    rag_service=self._rag_service,
                    backend_context_provider=self._backend_context_provider,
                    agent_context_planner=self._agent_context_planner,
                    recent_message_limit=self._session_recent_limit,
                    request_id=request_id,
                    debug_trace_enabled=self._debug_trace_enabled,
                )
            )
            first_event = next(event_iterator)
        except StopIteration:
            return _json_response(
                error_response(
                    AppError(
                        code=ErrorCode.MODEL_PROVIDER_ERROR,
                        message="Chat stream ended without events.",
                    ),
                    request_id,
                )
            )
        except Exception as exc:
            return _json_response(error_response(exc, request_id))

        return HttpRuntimeStreamResponse(
            status=200,
            headers={
                **_base_headers(),
                "Content-Type": "text/event-stream; charset=utf-8",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
            events=_stream_event_mappings(first_event, event_iterator),
        )

    def _audited_stream_events(
        self,
        events: Iterable[Mapping[str, Any]],
        *,
        token_id: str,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        started_at: float,
    ) -> Iterable[Mapping[str, Any]]:
        usage = (0, 0)
        error_code: str | None = None
        try:
            for event in events:
                if event.get("event") == "usage":
                    data = event.get("data")
                    if isinstance(data, Mapping):
                        usage = _usage_pair(data)
                elif event.get("event") == "error":
                    data = event.get("data")
                    if isinstance(data, Mapping) and data.get("code") is not None:
                        error_code = str(data["code"])
                yield event
        except Exception as exc:
            error_code = app_error_from_exception(exc).code.value
            raise
        finally:
            self._record_access_token_request(
                token_id=token_id,
                request_id=request_id,
                method=method,
                path=path,
                status_code=status_code,
                started_at=started_at,
                usage=usage,
                error_code=error_code,
            )

    def _record_access_token_request(
        self,
        *,
        token_id: str,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        started_at: float,
        usage: tuple[int, int],
        error_code: str | None,
    ) -> None:
        try:
            prompt_tokens, completion_tokens = usage
            self._access_token_store.record_request(
                token_id=token_id,
                request_id=request_id,
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=max(int((perf_counter() - started_at) * 1000), 0),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                error_code=error_code,
            )
        except Exception:
            _LOGGER.exception(
                "access token request log failed token_id=%s",
                token_id,
            )

    def _env_config(
        self,
        method: str,
        path_parts: list[str],
        body: Mapping[str, Any],
        headers: Mapping[str, str],
        request_id: str,
    ) -> HttpRuntimeResponse:
        if not self._is_config_authorized(headers):
            return _json_response(
                error_response(
                    AppError(
                        code=ErrorCode.AUTH_PERMISSION_DENIED,
                        message="Env config API requires ROLEPLAY_API_KEY.",
                    ),
                    request_id,
                )
            )
        try:
            if method == "GET" and path_parts == ["v1", "env-config", "schema"]:
                return _json_response(
                    {
                        "ok": True,
                        "data": self._env_config_editor.schema(),
                        "request_id": request_id,
                    }
                )
            if method == "GET" and path_parts == ["v1", "env-config"]:
                return _json_response(
                    {
                        "ok": True,
                        "data": self._env_config_editor.snapshot(),
                        "request_id": request_id,
                    }
                )
            if method == "POST" and path_parts == ["v1", "env-config", "check"]:
                return _json_response(
                    {
                        "ok": True,
                        "data": self._env_config_editor.check(body).to_data(),
                        "request_id": request_id,
                    }
                )
            if method == "PATCH" and path_parts == ["v1", "env-config"]:
                result = self._env_config_editor.commit(body)
                result["hot_reload"] = self._reload_runtime_after_env_config(
                    result["hot_reload_keys"]
                )
                return _json_response(
                    {
                        "ok": True,
                        "data": result,
                        "request_id": request_id,
                    }
                )
        except Exception as exc:
            return _json_response(error_response(exc, request_id))
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

    def _access_tokens(
        self,
        method: str,
        path_parts: list[str],
        query: Mapping[str, Any],
        body: Mapping[str, Any],
        headers: Mapping[str, str],
        request_id: str,
    ) -> HttpRuntimeResponse:
        if not self._is_config_authorized(headers):
            return _json_response(
                error_response(
                    AppError(
                        code=ErrorCode.AUTH_PERMISSION_DENIED,
                        message="Access token management requires ROLEPLAY_API_KEY.",
                    ),
                    request_id,
                )
            )
        if method == "POST" and path_parts == ["v1", "access-tokens"]:
            return _json_response(
                post_access_token(
                    body,
                    store=self._access_token_store,
                    request_id=request_id,
                )
            )
        if method == "GET" and path_parts == ["v1", "access-tokens"]:
            return _json_response(
                get_access_tokens(
                    store=self._access_token_store,
                    request_id=request_id,
                )
            )
        if method == "GET" and len(path_parts) == 3:
            return _json_response(
                get_access_token(
                    path_parts[2],
                    store=self._access_token_store,
                    request_id=request_id,
                )
            )
        if (
            method == "GET"
            and len(path_parts) == 4
            and path_parts[3] == "logs"
        ):
            return _json_response(
                get_access_token_logs(
                    path_parts[2],
                    query,
                    store=self._access_token_store,
                    request_id=request_id,
                )
            )
        if method == "DELETE" and len(path_parts) == 3:
            return _json_response(
                delete_access_token(
                    path_parts[2],
                    store=self._access_token_store,
                    request_id=request_id,
                )
            )
        if method == "PATCH" and len(path_parts) == 3:
            return _json_response(
                patch_access_token(
                    path_parts[2],
                    body,
                    store=self._access_token_store,
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

    def _reload_runtime_after_env_config(
        self,
        hot_reload_keys: list[str],
    ) -> dict[str, Any]:
        if not hot_reload_keys:
            return {"status": "skipped", "applied_keys": []}
        self._runtime_config_store.refresh()
        env = self._runtime_config_store.env()
        try:
            model_router = build_model_router(ModelProviderSettings.from_mapping(env))
            rag_service = build_rag_service_from_env(env)
            backend_context_provider = build_backend_context_provider_from_env(env)
            agent_context_planner = build_agent_context_planner_from_env(env)
            session_settings = SessionStoreSettings.from_mapping(env)
            settings = HttpRuntimeSettings.from_env(env)
        except Exception as exc:
            app_error = app_error_from_exception(exc)
            return {
                "status": "failed",
                "applied_keys": [],
                "error": {
                    "code": app_error.code.value,
                    "message": app_error.public_message,
                },
            }
        self._model_router = model_router
        self._rag_service = rag_service
        self._backend_context_provider = backend_context_provider
        self._agent_context_planner = agent_context_planner
        self._session_recent_limit = session_settings.recentMessageLimit
        self._api_key = settings.api_key
        self._debug_trace_enabled = settings.debug_trace_enabled
        return {"status": "applied", "applied_keys": list(hot_reload_keys)}

    def _runtime_config(
        self,
        method: str,
        body: Mapping[str, Any],
        headers: Mapping[str, str],
        request_id: str,
    ) -> HttpRuntimeResponse:
        if not self._is_config_authorized(headers):
            return _json_response(
                error_response(
                    AppError(
                        code=ErrorCode.AUTH_PERMISSION_DENIED,
                        message=(
                            "Runtime config API requires ROLEPLAY_API_KEY."
                        ),
                    ),
                    request_id,
                )
            )
        if method == "GET":
            return _json_response(
                {
                    "ok": True,
                    "data": self._runtime_config_store.public_snapshot(),
                    "request_id": request_id,
                }
            )
        if method == "PATCH":
            try:
                update = self._runtime_config_store.parse_update(body)
                candidate_env = self._runtime_config_store.candidate_env(update)
                model_router = build_model_router(
                    ModelProviderSettings.from_mapping(candidate_env)
                )
                rag_service = build_rag_service_from_env(candidate_env)
                backend_context_provider = build_backend_context_provider_from_env(
                    candidate_env
                )
                agent_context_planner = build_agent_context_planner_from_env(
                    candidate_env
                )
                session_settings = SessionStoreSettings.from_mapping(candidate_env)
                settings = HttpRuntimeSettings.from_env(candidate_env)
                applied_keys = self._runtime_config_store.commit(update)
                self._model_router = model_router
                self._rag_service = rag_service
                self._backend_context_provider = backend_context_provider
                self._agent_context_planner = agent_context_planner
                self._session_recent_limit = session_settings.recentMessageLimit
                self._api_key = settings.api_key
                self._debug_trace_enabled = settings.debug_trace_enabled
            except Exception as exc:
                return _json_response(error_response(exc, request_id))
            return _json_response(
                {
                    "ok": True,
                    "data": {
                        "applied_keys": list(applied_keys),
                        "config": self._runtime_config_store.public_snapshot(),
                    },
                    "request_id": request_id,
                }
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

    def _is_authorized(self, headers: Mapping[str, str]) -> bool:
        if not self._api_key:
            return True
        return _has_matching_secret(headers, self._api_key) or (
            self._access_token_from_headers(headers) is not None
        )

    def _is_config_authorized(self, headers: Mapping[str, str]) -> bool:
        if not self._api_key:
            return False
        return _has_matching_secret(headers, self._api_key)

    def _access_token_from_headers(self, headers: Mapping[str, str]):
        for credential in _credentials(headers):
            if not credential.startswith("hrt_"):
                continue
            token = self._access_token_store.authenticate(credential)
            if token is not None:
                return token
        return None


def create_local_runtime(env: Mapping[str, str]) -> RoleplayHttpRuntime:
    return RoleplayHttpRuntime.from_env_file(project_root=_project_root(), env=env)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _access_token_path(project_root: Path, env: Mapping[str, str]) -> Path:
    configured = Path(env.get("ACCESS_TOKEN_SQLITE_PATH", ".data/access-tokens.sqlite3"))
    if configured.is_absolute():
        return configured
    return project_root / configured


def _request_id(headers: Mapping[str, str]) -> str:
    value = headers.get("x-request-id")
    if value and value.strip():
        return value.strip()
    return f"req-{uuid4().hex}"


def _normalized_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def _credentials(headers: Mapping[str, str]) -> tuple[str, ...]:
    values: list[str] = []
    authorization = headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        value = authorization.removeprefix("Bearer ").strip()
        if value:
            values.append(value)
    value = headers.get("x-api-key", "").strip()
    if value and value not in values:
        values.append(value)
    return tuple(values)


def _has_matching_secret(headers: Mapping[str, str], expected: str) -> bool:
    return any(_secret_equals(candidate, expected) for candidate in _credentials(headers))


def _secret_equals(candidate: str | None, expected: str) -> bool:
    if candidate is None:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def _response_error_code(response: HttpRuntimeResponse) -> str | None:
    content_type = response.headers.get("Content-Type", "")
    if "application/json" not in content_type:
        return None
    try:
        data = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, Mapping) or data.get("ok", False):
        return None
    error = data.get("error")
    if not isinstance(error, Mapping):
        return None
    code = error.get("code")
    return str(code) if code is not None else None


def _consumes_model_tokens(method: str, path: str) -> bool:
    return method.upper() == "POST" and path in {"/v1/chat", "/v1/chat/stream"}


def _response_token_usage(response: HttpRuntimeResponse) -> tuple[int, int]:
    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return (0, 0)
        if isinstance(payload, Mapping):
            data = payload.get("data")
            if isinstance(data, Mapping):
                usage = data.get("usage")
                if isinstance(usage, Mapping):
                    return _usage_pair(usage)
        return (0, 0)
    return (0, 0)


def _usage_pair(usage: Mapping[str, Any]) -> tuple[int, int]:
    try:
        prompt_tokens = max(int(usage.get("prompt_tokens", 0)), 0)
        completion_tokens = max(int(usage.get("completion_tokens", 0)), 0)
    except (TypeError, ValueError):
        return (0, 0)
    return (prompt_tokens, completion_tokens)


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


def _demo_static_response(method: str, path: str) -> HttpRuntimeResponse | None:
    if method != "GET":
        return None
    mount = _static_mount(path)
    if mount is None:
        return None
    prefix, index_file = mount
    relative_path = index_file
    if path.startswith(f"{prefix}/") and path != f"{prefix}/":
        relative_path = unquote(path.removeprefix(f"{prefix}/"))
    if not relative_path or relative_path.endswith("/"):
        relative_path = f"{relative_path}{index_file}"
    if "\\" in relative_path:
        return _empty_response(404)
    demo_root = _project_root() / "frontend-demo"
    resolved_root = demo_root.resolve()
    target = (demo_root / relative_path).resolve()
    if not target.is_relative_to(resolved_root) or not target.is_file():
        return _empty_response(404)
    return HttpRuntimeResponse(
        status=200,
        headers={
            **_base_headers(),
            "Content-Type": _content_type(target),
            "Cache-Control": "no-store",
        },
        body=target.read_bytes(),
    )


def _static_mount(path: str) -> tuple[str, str] | None:
    for prefix, index_file in {"/demo": "index.html", "/config": "config.html"}.items():
        if path in {prefix, f"{prefix}/"} or path.startswith(f"{prefix}/"):
            return prefix, index_file
    return None


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".html":
        return "text/html; charset=utf-8"
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix == ".js":
        return "text/javascript; charset=utf-8"
    if suffix == ".json":
        return "application/json; charset=utf-8"
    return "application/octet-stream"


def _base_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, X-API-Key, X-Request-Id",
        "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
    }


def _status_from_response(response: Mapping[str, Any]) -> int:
    if response.get("ok", False):
        return 200
    code = response.get("error", {}).get("code")
    try:
        return ERROR_STATUS[ErrorCode(str(code))]
    except (KeyError, ValueError):
        return 500


def sse_event_bytes(event: Mapping[str, Any]) -> bytes:
    lines: list[str] = []
    event_name = str(event.get("event", "message"))
    data = event.get("data", {})
    lines.append(f"event: {event_name}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _stream_event_mappings(first_event: object, rest: Iterable[object]):
    yield _chat_stream_event_to_mapping(first_event)
    for event in rest:
        yield _chat_stream_event_to_mapping(event)


def _chat_stream_event_to_mapping(event: object) -> Mapping[str, Any]:
    if hasattr(event, "to_mapping"):
        data = event.to_mapping()
        if isinstance(data, Mapping):
            return data
    if isinstance(event, Mapping):
        return event
    raise TypeError("stream event must be a mapping")


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
