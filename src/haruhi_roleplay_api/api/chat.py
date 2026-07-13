"""Chat API handlers."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Mapping

from haruhi_roleplay_api.api.responses import (
    ApiResponse,
    error_response,
    success_response,
)
from haruhi_roleplay_api.application.chat import (
    RoleplayOrchestrator,
    SendChatMessageUseCase,
)
from haruhi_roleplay_api.application.errors import app_error_from_exception
from haruhi_roleplay_api.domain import (
    ChatInput,
    ChatOutput,
    ChatStreamEvent,
    DTOValidationError,
    RequestId,
)
from haruhi_roleplay_api.ports import (
    AgentContextPlanner,
    BackendContextProvider,
    ChatModelRouter,
    MemoryPolicyEngine,
    MemoryStore,
    PersonaRepository,
    PromptBuilder,
    RagService,
    SessionStore,
)


_LOGGER = logging.getLogger(__name__)


def post_chat(
    body: Mapping[str, Any],
    *,
    persona_repository: PersonaRepository,
    prompt_builder: PromptBuilder,
    model_router: ChatModelRouter,
    request_id: RequestId | str,
    session_store: SessionStore | None = None,
    memory_store: MemoryStore | None = None,
    memory_policy_engine: MemoryPolicyEngine | None = None,
    rag_service: RagService | None = None,
    backend_context_provider: BackendContextProvider | None = None,
    agent_context_planner: AgentContextPlanner | None = None,
    recent_message_limit: int = 12,
    memory_read_limit: int = 5,
    debug_trace_enabled: bool = True,
    include_error_details: bool = False,
) -> ApiResponse:
    effective_request_id = _effective_request_id(body, request_id)
    try:
        chat_input = ChatInput.from_mapping(
            _chat_body_to_internal(body, effective_request_id)
        )
        chat_output = SendChatMessageUseCase(
            RoleplayOrchestrator(
                persona_repository=persona_repository,
                prompt_builder=prompt_builder,
                model_router=model_router,
                session_store=session_store,
                memory_store=memory_store,
                memory_policy_engine=memory_policy_engine,
                rag_service=rag_service,
                backend_context_provider=backend_context_provider,
                agent_context_planner=agent_context_planner,
                recent_message_limit=recent_message_limit,
                memory_read_limit=memory_read_limit,
                debug_trace_enabled=debug_trace_enabled,
            )
        ).execute(chat_input)
    except Exception as exc:
        _log_chat_error(effective_request_id, exc)
        return error_response(
            exc,
            effective_request_id,
            include_details=include_error_details,
        )
    return success_response(_chat_output_to_data(chat_output), effective_request_id)


def post_chat_stream(
    body: Mapping[str, Any],
    *,
    persona_repository: PersonaRepository,
    prompt_builder: PromptBuilder,
    model_router: ChatModelRouter,
    request_id: RequestId | str,
    session_store: SessionStore | None = None,
    memory_store: MemoryStore | None = None,
    memory_policy_engine: MemoryPolicyEngine | None = None,
    rag_service: RagService | None = None,
    backend_context_provider: BackendContextProvider | None = None,
    agent_context_planner: AgentContextPlanner | None = None,
    recent_message_limit: int = 12,
    memory_read_limit: int = 5,
    debug_trace_enabled: bool = True,
    include_error_details: bool = False,
) -> ApiResponse:
    effective_request_id = _effective_request_id(body, request_id)
    try:
        stream_events = tuple(
            iter_chat_stream_events(
                body,
                persona_repository=persona_repository,
                prompt_builder=prompt_builder,
                model_router=model_router,
                request_id=effective_request_id,
                session_store=session_store,
                memory_store=memory_store,
                memory_policy_engine=memory_policy_engine,
                rag_service=rag_service,
                backend_context_provider=backend_context_provider,
                agent_context_planner=agent_context_planner,
                recent_message_limit=recent_message_limit,
                memory_read_limit=memory_read_limit,
                debug_trace_enabled=debug_trace_enabled,
            )
        )
    except Exception as exc:
        _log_chat_error(effective_request_id, exc)
        return error_response(
            exc,
            effective_request_id,
            include_details=include_error_details,
        )
    return success_response(
        {"events": [_chat_stream_event_to_data(event) for event in stream_events]},
        effective_request_id,
    )


def iter_chat_stream_events(
    body: Mapping[str, Any],
    *,
    persona_repository: PersonaRepository,
    prompt_builder: PromptBuilder,
    model_router: ChatModelRouter,
    request_id: RequestId | str,
    session_store: SessionStore | None = None,
    memory_store: MemoryStore | None = None,
    memory_policy_engine: MemoryPolicyEngine | None = None,
    rag_service: RagService | None = None,
    backend_context_provider: BackendContextProvider | None = None,
    agent_context_planner: AgentContextPlanner | None = None,
    recent_message_limit: int = 12,
    memory_read_limit: int = 5,
    debug_trace_enabled: bool = True,
) -> Iterable[ChatStreamEvent]:
    effective_request_id = _effective_request_id(body, request_id)
    chat_input = ChatInput.from_mapping(
        _chat_body_to_internal(
            body,
            effective_request_id,
            force_stream=True,
        )
    )
    return SendChatMessageUseCase(
        RoleplayOrchestrator(
            persona_repository=persona_repository,
            prompt_builder=prompt_builder,
            model_router=model_router,
            session_store=session_store,
            memory_store=memory_store,
            memory_policy_engine=memory_policy_engine,
            rag_service=rag_service,
            backend_context_provider=backend_context_provider,
            agent_context_planner=agent_context_planner,
            recent_message_limit=recent_message_limit,
            memory_read_limit=memory_read_limit,
            debug_trace_enabled=debug_trace_enabled,
        )
    ).stream(chat_input)


def _effective_request_id(
    body: Mapping[str, Any],
    request_id: RequestId | str,
) -> str:
    if isinstance(body, Mapping) and body.get("request_id") is not None:
        return str(body["request_id"])
    return str(request_id)


def _log_chat_error(request_id: RequestId | str, exc: Exception) -> None:
    app_error = app_error_from_exception(exc)
    _LOGGER.info(
        "chat request failed request_id=%s error_code=%s",
        str(request_id),
        str(app_error.code),
    )


def _chat_body_to_internal(
    body: Mapping[str, Any],
    request_id: RequestId | str,
    *,
    force_stream: bool = False,
) -> dict[str, Any]:
    if not isinstance(body, Mapping):
        raise DTOValidationError("request body must be an object")

    return {
        "requestId": body.get("request_id", str(request_id)),
        "appId": body.get("app_id"),
        "userId": body.get("user_id"),
        "sessionId": body.get("session_id"),
        "characterId": body.get("character_id"),
        "personaMode": body.get("persona_mode"),
        "message": body.get("message"),
        "language": body.get("language"),
        "capabilities": _capabilities_to_internal(
            body.get("capabilities"),
            force_stream=force_stream,
        ),
        "generation": _generation_to_internal(body.get("generation")),
        "metadata": body.get("metadata", {}),
    }


def _capabilities_to_internal(
    value: Any,
    *,
    force_stream: bool = False,
) -> dict[str, Any] | None:
    if value is None:
        return {"stream": True} if force_stream else None
    if not isinstance(value, Mapping):
        raise DTOValidationError("capabilities must be an object")
    return {
        "rag": value.get("rag", False),
        "memory": value.get("memory", False),
        "continuousSession": value.get("continuous_session", False),
        "safetyFilter": value.get("safety_filter", True),
        "debugTrace": value.get("debug_trace", False),
        "stream": True if force_stream else value.get("stream", False),
    }


def _generation_to_internal(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise DTOValidationError("generation must be an object")
    return {
        "model": value.get("model"),
        "temperature": value.get("temperature", 0.8),
        "maxTokens": value.get("max_tokens", 800),
        "topP": value.get("top_p", 1.0),
        "presencePenalty": value.get("presence_penalty", 0.0),
        "frequencyPenalty": value.get("frequency_penalty", 0.0),
        "styleIntensity": value.get("style_intensity", 0.75),
        "allowNarration": value.get("allow_narration", True),
    }


def _chat_output_to_data(output: ChatOutput) -> dict[str, Any]:
    return {
        "request_id": str(output.requestId),
        "session_id": str(output.sessionId) if output.sessionId is not None else None,
        "character_id": str(output.characterId),
        "persona_mode": str(output.personaMode),
        "reply": output.reply,
        "usage": dict(output.usage or {}),
        "rag": dict(output.rag or {}),
        "memory": dict(output.memory or {}),
        "safety": dict(output.safety or {}),
        "debug": dict(output.debug or {}) if output.debug is not None else None,
    }


def _chat_stream_event_to_data(event: ChatStreamEvent) -> dict[str, Any]:
    return event.to_mapping()
