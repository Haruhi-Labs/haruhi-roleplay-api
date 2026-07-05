"""Agent planning ports."""

from __future__ import annotations

from typing import Protocol

from haruhi_roleplay_api.domain import ChatInput, ContextPlan, PersonaPreset


class AgentContextPlanner(Protocol):
    @property
    def planner_name(self) -> str:
        """Stable planner name for debug trace."""

    def plan(
        self,
        *,
        chat_input: ChatInput,
        persona: PersonaPreset,
    ) -> ContextPlan:
        """Return a structured, safe context retrieval plan."""
