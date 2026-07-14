"""Agent context planners."""

from __future__ import annotations

from dataclasses import dataclass

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import ChatInput, ContextPlan, PersonaPreset


@dataclass(frozen=True)
class DeterministicAgentContextPlanner:
    backend_context_sources: tuple[str, ...] = ()

    @property
    def planner_name(self) -> str:
        return "deterministic"

    def plan(
        self,
        *,
        chat_input: ChatInput,
        persona: PersonaPreset,
    ) -> ContextPlan:
        capabilities = chat_input.capabilities
        notes = ["capability-gated"]
        if persona.ragPolicy:
            notes.append("persona-rag-policy")
        if persona.memoryPolicy:
            notes.append("persona-memory-policy")
        retrieve_rag = (
            capabilities.rag
            if capabilities.ragConfigured
            else capabilities.rag
            or bool(persona.ragPolicy.get("enabledByDefault", False))
        )
        return ContextPlan(
            planner=self.planner_name,
            status="ready",
            readSession=capabilities.continuousSession,
            readMemory=capabilities.memory,
            retrieveRag=retrieve_rag,
            backendFetches=self.backend_context_sources,
            notes=tuple(notes),
        )


@dataclass(frozen=True)
class ModelBackedAgentContextPlanner:
    @property
    def planner_name(self) -> str:
        return "model"

    def plan(
        self,
        *,
        chat_input: ChatInput,
        persona: PersonaPreset,
    ) -> ContextPlan:
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message=(
                "Model-backed agent context planner is configured but not implemented. "
                "Set AGENT_CONTEXT_PLANNER=deterministic."
            ),
        )
