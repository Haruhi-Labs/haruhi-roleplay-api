"""Chat use cases and minimal roleplay orchestration."""

from __future__ import annotations

from time import perf_counter

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    ChatInput,
    ChatOutput,
    DebugTrace,
    DTOValidationError,
    ModelResponse,
    PromptBuildInput,
    RequestId,
    Session,
    Visibility,
    model_messages_from_prompt,
)
from haruhi_roleplay_api.ports import (
    ChatModelRouter,
    PersonaRepository,
    PromptBuilder,
    SessionStore,
)


class SendChatMessageUseCase:
    def __init__(self, orchestrator: "RoleplayOrchestrator") -> None:
        self._orchestrator = orchestrator

    def execute(self, chat_input: ChatInput) -> ChatOutput:
        return self._orchestrator.run(chat_input)


class RoleplayOrchestrator:
    def __init__(
        self,
        *,
        persona_repository: PersonaRepository,
        prompt_builder: PromptBuilder,
        model_router: ChatModelRouter,
        session_store: SessionStore | None = None,
        recent_message_limit: int = 12,
        debug_trace_enabled: bool = True,
    ) -> None:
        self._persona_repository = persona_repository
        self._prompt_builder = prompt_builder
        self._model_router = model_router
        self._session_store = session_store
        self._recent_message_limit = recent_message_limit
        self._debug_trace_enabled = debug_trace_enabled

    def run(self, chat_input: ChatInput) -> ChatOutput:
        started_at = perf_counter()
        events: list[str] = []
        _record_event(events, "validate_capabilities")
        _ensure_v1_capabilities(chat_input)
        if chat_input.requestId is None:
            raise DTOValidationError("requestId is required")

        _record_event(events, "load_character")
        character = _find_public_character(self._persona_repository, chat_input)
        _record_event(events, "load_persona")
        persona = _find_public_persona(
            self._persona_repository,
            chat_input,
        )
        _record_event(events, "load_session")
        session = self._session_for_chat(chat_input)
        _record_event(events, "read_session_messages")
        recent_messages = self._recent_messages(chat_input)
        _record_event(events, "build_prompt")
        prompt_output = self._prompt_builder.build(
            PromptBuildInput(
                character=character,
                persona=persona,
                userMessage=chat_input.message,
                capabilities=chat_input.capabilities,
                generation=chat_input.generation,
                recentMessages=recent_messages,
            )
        )
        _record_event(events, "generate_model")
        model_response = self._model_router.generate(
            model_messages_from_prompt(prompt_output.messages),
            chat_input.generation,
        )
        if session is not None:
            _record_event(events, "write_session_messages")
            self._write_session_messages(chat_input, model_response.reply)
        _record_event(events, "build_response")

        return ChatOutput(
            requestId=RequestId(str(chat_input.requestId)),
            characterId=chat_input.characterId,
            personaMode=chat_input.personaMode,
            reply=model_response.reply,
            sessionId=chat_input.sessionId if session is not None else None,
            usage={
                **model_response.usage.to_mapping(),
                "provider": model_response.provider,
                "model": model_response.model,
            },
            rag={"enabled": False},
            memory={"enabled": False},
            safety={
                "enabled": chat_input.capabilities.safetyFilter,
                "blocked": False,
            },
            debug=_debug_trace_for_chat(
                chat_input=chat_input,
                model_response=model_response,
                persona_source=_persona_source(self._persona_repository),
                session_read_count=len(recent_messages),
                started_at=started_at,
                events=tuple(events),
                enabled=self._debug_trace_enabled,
            ),
        )

    def _session_for_chat(self, chat_input: ChatInput) -> Session | None:
        if not chat_input.capabilities.continuousSession:
            return None
        if self._session_store is None:
            raise DTOValidationError("sessionStore is required for continuous session")
        if chat_input.sessionId is None:
            raise DTOValidationError("sessionId is required for continuous session")

        session = self._session_store.get_session(chat_input.sessionId)
        _ensure_session_scope(session, chat_input)
        return session

    def _recent_messages(self, chat_input: ChatInput):
        if not chat_input.capabilities.continuousSession:
            return ()
        if self._session_store is None or chat_input.sessionId is None:
            return ()
        return self._session_store.recent_messages(
            chat_input.sessionId,
            limit=self._recent_message_limit,
        )

    def _write_session_messages(self, chat_input: ChatInput, reply: str) -> None:
        if self._session_store is None or chat_input.sessionId is None:
            return
        self._session_store.append_message(
            session_id=chat_input.sessionId,
            role="user",
            content=chat_input.message,
        )
        self._session_store.append_message(
            session_id=chat_input.sessionId,
            role="assistant",
            content=reply,
        )


def _ensure_v1_capabilities(chat_input: ChatInput) -> None:
    if chat_input.capabilities.stream:
        raise DTOValidationError("capabilities.stream is not supported by /v1/chat")
    if chat_input.capabilities.rag:
        raise DTOValidationError("capabilities.rag is not supported by chat v1")
    if chat_input.capabilities.memory:
        raise DTOValidationError("capabilities.memory is not supported by chat v1")


def _find_public_character(repository: PersonaRepository, chat_input: ChatInput):
    for character in repository.list_characters():
        if character.characterId == chat_input.characterId:
            if character.visibility is Visibility.PUBLIC:
                return character
            break
    raise AppError(
        code=ErrorCode.PERSONA_NOT_FOUND,
        message=f"Character was not found: {chat_input.characterId}",
    )


def _find_public_persona(
    repository: PersonaRepository,
    chat_input: ChatInput,
):
    for preset in repository.list_presets(chat_input.characterId):
        if (
            preset.personaMode == chat_input.personaMode
            and preset.visibility is Visibility.PUBLIC
        ):
            return preset
    raise AppError(
        code=ErrorCode.PERSONA_MODE_NOT_FOUND,
        message=f"Persona preset was not found: {chat_input.personaMode}",
    )


def _ensure_session_scope(session: Session, chat_input: ChatInput) -> None:
    if (
        session.appId != chat_input.appId
        or session.userId != chat_input.userId
        or session.characterId != chat_input.characterId
        or session.personaMode != chat_input.personaMode
    ):
        raise AppError(
            code=ErrorCode.SESSION_NOT_FOUND,
            message="Session was not found.",
        )
    if session.status.value != "active":
        raise AppError(
            code=ErrorCode.SESSION_EXPIRED,
            message="Session is not active.",
        )


def _debug_trace_for_chat(
    *,
    chat_input: ChatInput,
    model_response: ModelResponse,
    persona_source: str,
    session_read_count: int,
    started_at: float,
    events: tuple[str, ...],
    enabled: bool,
) -> dict[str, object] | None:
    if not enabled or not chat_input.capabilities.debugTrace:
        return None
    return DebugTrace(
        requestId=RequestId(str(chat_input.requestId)),
        characterId=chat_input.characterId,
        personaMode=chat_input.personaMode,
        personaSource=persona_source,
        sessionReadCount=session_read_count,
        modelProvider=model_response.provider,
        modelRoute=model_response.model,
        safetyAction="allow",
        latencyMs=_elapsed_ms(started_at),
        capabilities=_capability_trace(chat_input),
        events=events,
        modelDebug=model_response.debug,
    ).to_mapping()


def _capability_trace(chat_input: ChatInput) -> dict[str, bool]:
    capabilities = chat_input.capabilities
    return {
        "rag": capabilities.rag,
        "memory": capabilities.memory,
        "continuousSession": capabilities.continuousSession,
        "safetyFilter": capabilities.safetyFilter,
        "stream": capabilities.stream,
    }


def _persona_source(repository: PersonaRepository) -> str:
    return type(repository).__name__


def _record_event(events: list[str], stage: str) -> None:
    events.append(stage)


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))
