"""Chat use cases and minimal roleplay orchestration."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from time import perf_counter

from haruhi_roleplay_api.application.errors import (
    AppError,
    ErrorCode,
    app_error_from_exception,
)
from haruhi_roleplay_api.application.agent import DeterministicAgentContextPlanner
from haruhi_roleplay_api.application.memory import DefaultMemoryPolicyEngine
from haruhi_roleplay_api.application.rag_query import build_roleplay_rag_query
from haruhi_roleplay_api.domain import (
    ChatInput,
    ChatOutput,
    ChatStreamEvent,
    BackendContextFact,
    BackendContextRequest,
    CharacterId,
    ContextPlan,
    DebugTrace,
    DTOValidationError,
    MemoryItem,
    MemoryQuery,
    MemoryReadPolicyInput,
    MemoryType,
    MemoryWriteCandidate,
    MemoryWriteCommand,
    MemoryWritePolicyInput,
    ModelMessage,
    ModelResponse,
    ModelStreamEvent,
    PersonaPreset,
    PersonaModeId,
    PromptBuildInput,
    RagChunk,
    RagRetrieveFilters,
    RagRetrieveInput,
    RagRetrieveOutput,
    RequestId,
    Session,
    SessionMessage,
    Visibility,
    model_messages_from_prompt,
)
from haruhi_roleplay_api.ports import (
    AgentContextPlanner,
    BackendContextProvider,
    BatchRagService,
    ChatModelRouter,
    MemoryPolicyEngine,
    MemoryStore,
    PersonaRepository,
    PromptBuilder,
    RagService,
    SessionStore,
)


class SendChatMessageUseCase:
    def __init__(self, orchestrator: "RoleplayOrchestrator") -> None:
        self._orchestrator = orchestrator

    def execute(self, chat_input: ChatInput) -> ChatOutput:
        return self._orchestrator.run(chat_input)

    def stream(self, chat_input: ChatInput) -> Iterable[ChatStreamEvent]:
        return self._orchestrator.stream(chat_input)


@dataclass(kw_only=True)
class _PreparedChat:
    started_at: float
    events: list[str]
    persona: PersonaPreset
    session: Session | None
    recent_messages: tuple[SessionMessage, ...]
    memory_items: tuple[MemoryItem, ...]
    rag_output: RagRetrieveOutput | None
    backend_context_facts: tuple[BackendContextFact, ...]
    context_plan: ContextPlan
    model_messages: tuple[ModelMessage, ...]


class RoleplayOrchestrator:
    def __init__(
        self,
        *,
        persona_repository: PersonaRepository,
        prompt_builder: PromptBuilder,
        model_router: ChatModelRouter,
        session_store: SessionStore | None = None,
        memory_store: MemoryStore | None = None,
        memory_policy_engine: MemoryPolicyEngine | None = None,
        rag_service: RagService | None = None,
        backend_context_provider: BackendContextProvider | None = None,
        agent_context_planner: AgentContextPlanner | None = None,
        recent_message_limit: int = 12,
        memory_read_limit: int = 5,
        rag_top_k: int = 5,
        rag_min_relevance_score: float = 0.2,
        debug_trace_enabled: bool = True,
    ) -> None:
        self._persona_repository = persona_repository
        self._prompt_builder = prompt_builder
        self._model_router = model_router
        self._session_store = session_store
        self._memory_store = memory_store
        self._memory_policy_engine = memory_policy_engine or DefaultMemoryPolicyEngine()
        self._rag_service = rag_service
        self._backend_context_provider = backend_context_provider
        self._agent_context_planner = (
            agent_context_planner or DeterministicAgentContextPlanner()
        )
        self._recent_message_limit = recent_message_limit
        self._memory_read_limit = memory_read_limit
        self._rag_top_k = rag_top_k
        if (
            isinstance(rag_min_relevance_score, bool)
            or not isinstance(rag_min_relevance_score, int | float)
            or not 0.0 <= rag_min_relevance_score <= 1.0
        ):
            raise ValueError("rag_min_relevance_score must be between 0 and 1")
        self._rag_min_relevance_score = float(rag_min_relevance_score)
        self._debug_trace_enabled = debug_trace_enabled

    def run(self, chat_input: ChatInput) -> ChatOutput:
        prepared = self._prepare_chat(chat_input, allow_stream=False)
        _record_event(prepared.events, "generate_model")
        model_response = self._model_router.generate(
            prepared.model_messages,
            chat_input.generation,
        )
        return self._complete_chat(chat_input, prepared, model_response)

    def stream(self, chat_input: ChatInput) -> Iterable[ChatStreamEvent]:
        prepared = self._prepare_chat(chat_input, allow_stream=True)
        yield _start_stream_event(chat_input, prepared.session)
        yield from _source_stream_events(prepared.rag_output)

        model_response: ModelResponse | None = None
        try:
            _record_event(prepared.events, "stream_model")
            for model_event in self._model_router.stream(
                prepared.model_messages,
                chat_input.generation,
            ):
                if model_event.event == "delta":
                    yield ChatStreamEvent(
                        event="delta",
                        data={"text": model_event.delta},
                    )
                elif model_event.event == "done":
                    model_response = _model_response_from_stream_event(model_event)
        except Exception as exc:
            _record_event(prepared.events, "stream_error")
            yield _error_stream_event(chat_input, exc)
            return

        if model_response is None:
            yield _error_stream_event(
                chat_input,
                AppError(
                    code=ErrorCode.MODEL_PROVIDER_ERROR,
                    message="Model provider stream ended without final response.",
                ),
            )
            return

        chat_output = self._complete_chat(chat_input, prepared, model_response)
        yield ChatStreamEvent(
            event="usage",
            data=dict(chat_output.usage or {}),
        )
        yield ChatStreamEvent(
            event="done",
            data=_chat_output_to_stream_done_data(chat_output),
        )

    def _prepare_chat(
        self,
        chat_input: ChatInput,
        *,
        allow_stream: bool,
    ) -> _PreparedChat:
        started_at = perf_counter()
        events: list[str] = []
        _record_event(events, "validate_capabilities")
        _ensure_v1_capabilities(chat_input, allow_stream=allow_stream)
        if chat_input.requestId is None:
            raise DTOValidationError("requestId is required")

        _record_event(events, "load_character")
        character = _find_public_character(self._persona_repository, chat_input)
        _record_event(events, "load_persona")
        persona = _find_public_persona(
            self._persona_repository,
            chat_input,
        )
        _record_event(events, "plan_context")
        context_plan = self._agent_context_planner.plan(
            chat_input=chat_input,
            persona=persona,
        )
        if (
            context_plan.retrieveRag
            and self._rag_service is None
            and not chat_input.capabilities.ragConfigured
        ):
            context_plan = replace(
                context_plan,
                retrieveRag=False,
                notes=(*context_plan.notes, "rag-provider-unavailable"),
            )
        if (
            context_plan.readMemory
            and self._memory_store is None
            and not chat_input.capabilities.memoryConfigured
        ):
            context_plan = replace(
                context_plan,
                readMemory=False,
                notes=(*context_plan.notes, "memory-store-unavailable"),
            )
        _record_event(events, "load_session")
        session = self._session_for_chat(chat_input, context_plan)
        _record_event(events, "read_session_messages")
        recent_messages = self._recent_messages(chat_input, context_plan)
        _record_event(events, "read_memory")
        memory_items = self._memory_for_chat(chat_input, persona, context_plan)
        _record_event(events, "retrieve_rag")
        rag_output = self._rag_for_chat(
            chat_input,
            persona,
            context_plan,
            recent_messages,
        )
        _record_event(events, "read_backend_context")
        backend_context_facts = self._backend_context_for_chat(
            chat_input,
            context_plan,
        )
        _record_event(events, "build_prompt")
        prompt_output = self._prompt_builder.build(
            PromptBuildInput(
                character=character,
                persona=persona,
                userMessage=chat_input.message,
                capabilities=chat_input.capabilities,
                generation=chat_input.generation,
                recentMessages=recent_messages,
                memoryItems=memory_items,
                ragChunks=rag_output.chunks if rag_output is not None else (),
                backendContextFacts=backend_context_facts,
            )
        )
        return _PreparedChat(
            started_at=started_at,
            events=events,
            persona=persona,
            session=session,
            recent_messages=recent_messages,
            memory_items=memory_items,
            rag_output=rag_output,
            backend_context_facts=backend_context_facts,
            context_plan=context_plan,
            model_messages=model_messages_from_prompt(prompt_output.messages),
        )

    def _complete_chat(
        self,
        chat_input: ChatInput,
        prepared: _PreparedChat,
        model_response: ModelResponse,
    ) -> ChatOutput:
        if prepared.session is not None:
            _record_event(prepared.events, "write_session_messages")
            self._write_session_messages(chat_input, model_response.reply)
        _record_event(prepared.events, "write_memory")
        written_memories = self._write_memory_for_chat(
            chat_input,
            prepared.persona,
            prepared.context_plan,
        )
        _record_event(prepared.events, "build_response")

        return ChatOutput(
            requestId=RequestId(str(chat_input.requestId)),
            characterId=chat_input.characterId,
            personaMode=chat_input.personaMode,
            reply=model_response.reply,
            sessionId=chat_input.sessionId if prepared.session is not None else None,
            usage={
                **model_response.usage.to_mapping(),
                "provider": model_response.provider,
                "model": model_response.model,
            },
            rag=_rag_output_to_chat_metadata(prepared.rag_output),
            memory=_memory_output_to_chat_metadata(
                prepared.memory_items,
                written_memories,
                enabled=prepared.context_plan.readMemory,
            ),
            safety={
                "enabled": chat_input.capabilities.safetyFilter,
                "blocked": False,
            },
            debug=_debug_trace_for_chat(
                chat_input=chat_input,
                model_response=model_response,
                persona_source=_persona_source(self._persona_repository),
                session_read_count=len(prepared.recent_messages),
                memory_read_count=len(prepared.memory_items),
                memory_write_count=len(written_memories),
                rag_output=prepared.rag_output,
                backend_context_facts=prepared.backend_context_facts,
                context_plan=prepared.context_plan,
                started_at=prepared.started_at,
                events=tuple(prepared.events),
                enabled=self._debug_trace_enabled,
            ),
        )

    def _session_for_chat(
        self,
        chat_input: ChatInput,
        context_plan: ContextPlan,
    ) -> Session | None:
        if not context_plan.readSession:
            return None
        if self._session_store is None:
            raise DTOValidationError("sessionStore is required for continuous session")
        if chat_input.sessionId is None:
            raise DTOValidationError("sessionId is required for continuous session")

        session = self._session_store.get_session(chat_input.sessionId)
        _ensure_session_scope(session, chat_input)
        return session

    def _recent_messages(
        self,
        chat_input: ChatInput,
        context_plan: ContextPlan,
    ):
        if not context_plan.readSession:
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

    def _memory_for_chat(
        self,
        chat_input: ChatInput,
        persona: PersonaPreset,
        context_plan: ContextPlan,
    ) -> tuple[MemoryItem, ...]:
        if not context_plan.readMemory:
            return ()
        if self._memory_store is None:
            raise DTOValidationError("memoryStore is required for memory")

        policy_input = MemoryReadPolicyInput(
            appId=chat_input.appId,
            userId=chat_input.userId,
            characterId=chat_input.characterId,
            personaMode=chat_input.personaMode,
            enabled=context_plan.readMemory,
            allowedTypes=_memory_types_for_persona(persona),
            maxItems=self._memory_read_limit,
        )
        if not self._memory_policy_engine.should_read(policy_input):
            return ()
        return self._memory_store.list_memories(
            MemoryQuery(
                appId=policy_input.appId,
                userId=policy_input.userId,
                characterId=policy_input.characterId,
                personaMode=policy_input.personaMode,
                memoryTypes=policy_input.allowedTypes,
                limit=policy_input.maxItems,
            )
        )

    def _write_memory_for_chat(
        self,
        chat_input: ChatInput,
        persona: PersonaPreset,
        context_plan: ContextPlan,
    ) -> tuple[MemoryItem, ...]:
        if not context_plan.readMemory:
            return ()
        if self._memory_store is None:
            raise DTOValidationError("memoryStore is required for memory")

        candidates = _memory_write_candidates(chat_input)
        if not candidates:
            return ()

        written: list[MemoryItem] = []
        allowed_types = _memory_types_for_persona(persona)
        for candidate in candidates:
            policy_input = MemoryWritePolicyInput(
                appId=chat_input.appId,
                userId=chat_input.userId,
                characterId=chat_input.characterId,
                personaMode=chat_input.personaMode,
                enabled=context_plan.readMemory,
                allowedTypes=allowed_types,
                candidate=candidate,
            )
            if not self._memory_policy_engine.should_write(policy_input):
                continue
            written.append(
                self._memory_store.add_memory(
                    MemoryWriteCommand(
                        appId=chat_input.appId,
                        userId=chat_input.userId,
                        characterId=chat_input.characterId,
                        personaMode=chat_input.personaMode,
                        candidate=candidate,
                    )
                )
            )
        return tuple(written)

    def _rag_for_chat(
        self,
        chat_input: ChatInput,
        persona: PersonaPreset,
        context_plan: ContextPlan,
        recent_messages: tuple[SessionMessage, ...],
    ) -> RagRetrieveOutput | None:
        if not context_plan.retrieveRag:
            return None
        if self._rag_service is None:
            raise DTOValidationError("ragService is required for RAG")
        query = build_roleplay_rag_query(
            character_id=str(chat_input.characterId),
            persona_mode=str(chat_input.personaMode),
            timeline=persona.timeline,
            current_message=chat_input.message,
            recent_messages=(
                (message.role, message.content) for message in recent_messages
            ),
        )
        base_filters = _rag_filters_for_chat(chat_input, persona)
        actor_input = RagRetrieveInput(
            appId=chat_input.appId,
            userId=chat_input.userId,
            characterId=chat_input.characterId,
            personaMode=chat_input.personaMode,
            query=query,
            topK=self._rag_top_k,
            filters=base_filters,
            debug=chat_input.capabilities.debugTrace,
        )
        director_input = RagRetrieveInput(
            appId=chat_input.appId,
            userId=chat_input.userId,
            characterId=CharacterId("kyon"),
            personaMode=_director_persona_mode(persona),
            query=query,
            topK=self._rag_top_k,
            filters=replace(
                base_filters,
                recordKinds=("scene_memory",),
                retrievalChannels=("canonical_memory",),
                knowledgeOwners=("kyon",),
            ),
            debug=chat_input.capabilities.debugTrace,
        )
        if isinstance(self._rag_service, BatchRagService):
            actor_output, director_output = self._rag_service.retrieve_many(
                (actor_input, director_input)
            )
        else:
            with ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="roleplay-rag",
            ) as executor:
                actor_future = executor.submit(
                    self._rag_service.retrieve,
                    actor_input,
                )
                director_future = executor.submit(
                    self._rag_service.retrieve,
                    director_input,
                )
                actor_output = actor_future.result()
                director_output = director_future.result()
        actor_output = replace(
            actor_output,
            chunks=tuple(
                chunk
                for chunk in actor_output.chunks
                if chunk.metadata.extra.get("record_kind") != "scene_memory"
            ),
        )
        actor_output = _filter_rag_output_by_relevance(
            actor_output,
            minimum_score=self._rag_min_relevance_score,
        )
        director_output = _filter_rag_output_by_relevance(
            director_output,
            minimum_score=self._rag_min_relevance_score,
        )
        return _merge_roleplay_rag_outputs(
            actor_output,
            director_output,
            top_k=self._rag_top_k,
        )

    def _backend_context_for_chat(
        self,
        chat_input: ChatInput,
        context_plan: ContextPlan,
    ) -> tuple[BackendContextFact, ...]:
        if not context_plan.backendFetches:
            return ()
        if self._backend_context_provider is None:
            raise DTOValidationError(
                "backendContextProvider is required for backend context"
            )
        return self._backend_context_provider.fetch(
            BackendContextRequest(
                appId=chat_input.appId,
                userId=chat_input.userId,
                characterId=chat_input.characterId,
                personaMode=chat_input.personaMode,
                sources=context_plan.backendFetches,
            )
        )


def _ensure_v1_capabilities(chat_input: ChatInput, *, allow_stream: bool) -> None:
    if chat_input.capabilities.stream and not allow_stream:
        raise DTOValidationError("capabilities.stream is not supported by /v1/chat")


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
    memory_read_count: int,
    memory_write_count: int,
    rag_output: RagRetrieveOutput | None,
    backend_context_facts: tuple[BackendContextFact, ...],
    context_plan: ContextPlan,
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
        memoryReadCount=memory_read_count,
        memoryWriteCount=memory_write_count,
        ragProvider=rag_output.provider if rag_output is not None else None,
        ragRawHitCount=rag_output.rawHitCount if rag_output is not None else 0,
        ragFilteredHitCount=(
            rag_output.filteredHitCount if rag_output is not None else 0
        ),
        backendContextFactCount=len(backend_context_facts),
        backendContextSources=_backend_context_sources(backend_context_facts),
        modelProvider=model_response.provider,
        modelRoute=model_response.model,
        safetyAction="allow",
        latencyMs=_elapsed_ms(started_at),
        capabilities=_capability_trace(chat_input, context_plan),
        events=events,
        modelDebug=model_response.debug,
        contextPlan=context_plan.to_debug_mapping(),
    ).to_mapping()


def _backend_context_sources(
    facts: tuple[BackendContextFact, ...],
) -> tuple[str, ...]:
    return tuple(dict.fromkeys(fact.source for fact in facts))


def _capability_trace(
    chat_input: ChatInput,
    context_plan: ContextPlan,
) -> dict[str, bool]:
    capabilities = chat_input.capabilities
    return {
        "rag": context_plan.retrieveRag,
        "memory": context_plan.readMemory,
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


def _rag_filters_for_chat(
    chat_input: ChatInput,
    persona: PersonaPreset,
) -> RagRetrieveFilters:
    return RagRetrieveFilters(
        sourceTypes=tuple(str(item) for item in persona.ragPolicy.get("sourceTypes", ())),
        timelines=persona.knowledgeBoundary.allowedTimelines,
        spoilerLevelMax=persona.knowledgeBoundary.spoilerLevel,
        language=chat_input.language,
    )


def _director_persona_mode(persona: PersonaPreset) -> PersonaModeId:
    if persona.timeline == "mid_late":
        return PersonaModeId("default_kyon")
    return PersonaModeId(f"{persona.timeline}_kyon")


def _filter_rag_output_by_relevance(
    output: RagRetrieveOutput,
    *,
    minimum_score: float,
) -> RagRetrieveOutput:
    return replace(
        output,
        chunks=tuple(
            chunk
            for chunk in output.chunks
            if _rag_chunk_relevance(chunk) >= minimum_score
        ),
    )


def _rag_chunk_relevance(chunk: RagChunk) -> float:
    internal_score = chunk.metadata.extra.get("_retrieval_relevance")
    if (
        isinstance(internal_score, int | float)
        and not isinstance(internal_score, bool)
    ):
        return float(internal_score)
    return chunk.score


def _merge_roleplay_rag_outputs(
    actor_output: RagRetrieveOutput,
    director_output: RagRetrieveOutput,
    *,
    top_k: int,
) -> RagRetrieveOutput:
    actor_chunks = tuple(
        _with_prompt_channel(chunk, "actor_reference")
        for chunk in actor_output.chunks
    )
    director_chunks = tuple(
        _with_prompt_channel(chunk, "director_bridge")
        for chunk in director_output.chunks
    )
    director_budget = min(2, top_k // 2)
    actor_budget = top_k - director_budget
    selected: list[RagChunk] = []
    used_documents: set[str] = set()
    used_chunks: set[str] = set()
    used_contents: set[str] = set()

    def add(chunk: RagChunk) -> None:
        document_id = str(chunk.documentId)
        chunk_id = str(chunk.chunkId)
        normalized_content = " ".join(chunk.content.split()).casefold()
        if (
            document_id in used_documents
            or chunk_id in used_chunks
            or normalized_content in used_contents
            or len(selected) >= top_k
        ):
            return
        selected.append(chunk)
        used_documents.add(document_id)
        used_chunks.add(chunk_id)
        used_contents.add(normalized_content)

    for chunk in actor_chunks[:actor_budget]:
        add(chunk)
    for chunk in director_chunks[:director_budget]:
        add(chunk)
    for chunk in actor_chunks[actor_budget:]:
        add(chunk)

    provider = actor_output.provider
    if director_output.provider != provider:
        provider = f"{provider}+{director_output.provider}"
    return RagRetrieveOutput(
        chunks=tuple(selected),
        provider=provider,
        rawHitCount=actor_output.rawHitCount + director_output.rawHitCount,
        filteredHitCount=(
            actor_output.filteredHitCount + director_output.filteredHitCount
        ),
        rerankApplied=(
            actor_output.rerankApplied or director_output.rerankApplied
        ),
    )


def _with_prompt_channel(chunk: RagChunk, channel: str) -> RagChunk:
    return replace(
        chunk,
        metadata=replace(
            chunk.metadata,
            extra={**dict(chunk.metadata.extra), "prompt_channel": channel},
        ),
    )


def _memory_types_for_persona(persona: PersonaPreset) -> tuple[MemoryType, ...]:
    raw_types = persona.memoryPolicy.get("allowedTypes", ())
    try:
        return tuple(MemoryType(str(item)) for item in raw_types)
    except ValueError as exc:
        raise DTOValidationError(
            "memoryPolicy.allowedTypes contains unsupported memory type"
        ) from exc


def _memory_write_candidates(chat_input: ChatInput) -> tuple[MemoryWriteCandidate, ...]:
    if not isinstance(chat_input.metadata, Mapping):
        raise DTOValidationError("metadata must be an object")
    raw_candidates = chat_input.metadata.get("memory_write")
    if raw_candidates is None:
        return ()
    if isinstance(raw_candidates, Mapping):
        return (MemoryWriteCandidate.from_mapping(raw_candidates),)
    if isinstance(raw_candidates, (list, tuple)):
        return tuple(
            MemoryWriteCandidate.from_mapping(raw_candidate)
            for raw_candidate in raw_candidates
        )
    raise DTOValidationError("metadata.memory_write must be an object or list")


def _rag_output_to_chat_metadata(
    rag_output: RagRetrieveOutput | None,
) -> dict[str, object]:
    if rag_output is None:
        return {"enabled": False}
    return {
        "enabled": True,
        "provider": rag_output.provider,
        "hit_count": len(rag_output.chunks),
        "raw_hit_count": rag_output.rawHitCount,
        "filtered_hit_count": rag_output.filteredHitCount,
        "sources": [chunk.to_source_mapping() for chunk in rag_output.chunks],
    }


def _memory_output_to_chat_metadata(
    memory_items: tuple[MemoryItem, ...],
    written_memories: tuple[MemoryItem, ...],
    *,
    enabled: bool,
) -> dict[str, object]:
    if not enabled:
        return {"enabled": False}
    return {
        "enabled": True,
        "read_count": len(memory_items),
        "write_count": len(written_memories),
    }


def _start_stream_event(
    chat_input: ChatInput,
    session: Session | None,
) -> ChatStreamEvent:
    return ChatStreamEvent(
        event="start",
        data={
            "request_id": str(chat_input.requestId),
            "session_id": str(chat_input.sessionId) if session is not None else None,
            "character_id": str(chat_input.characterId),
            "persona_mode": str(chat_input.personaMode),
        },
    )


def _source_stream_events(
    rag_output: RagRetrieveOutput | None,
) -> tuple[ChatStreamEvent, ...]:
    if rag_output is None:
        return ()
    return tuple(
        ChatStreamEvent(event="source", data={"source": chunk.to_source_mapping()})
        for chunk in rag_output.chunks
    )


def _error_stream_event(chat_input: ChatInput, exc: Exception) -> ChatStreamEvent:
    app_error = app_error_from_exception(exc)
    return ChatStreamEvent(
        event="error",
        data={
            "request_id": str(chat_input.requestId),
            "error": {
                "code": app_error.code.value,
                "message": app_error.public_message,
            },
        },
    )


def _model_response_from_stream_event(event: ModelStreamEvent) -> ModelResponse:
    if event.response is None:
        raise DTOValidationError("model stream done event must include response")
    return event.response


def _chat_output_to_stream_done_data(output: ChatOutput) -> dict[str, object]:
    return {
        "request_id": str(output.requestId),
        "session_id": str(output.sessionId) if output.sessionId is not None else None,
        "character_id": str(output.characterId),
        "persona_mode": str(output.personaMode),
        "reply": output.reply,
        "rag": dict(output.rag or {}),
        "memory": dict(output.memory or {}),
        "safety": dict(output.safety or {}),
        "debug": dict(output.debug or {}) if output.debug is not None else None,
    }
