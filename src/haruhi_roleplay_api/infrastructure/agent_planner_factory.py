"""Agent planner factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from haruhi_roleplay_api.application.agent import (
    DeterministicAgentContextPlanner,
    ModelBackedAgentContextPlanner,
)
from haruhi_roleplay_api.domain import DTOValidationError
from haruhi_roleplay_api.ports import AgentContextPlanner


@dataclass(frozen=True, kw_only=True)
class AgentPlannerSettings:
    mode: str = "deterministic"
    backend_context_sources: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "AgentPlannerSettings":
        return cls(
            mode=env.get("AGENT_CONTEXT_PLANNER", "deterministic"),
            backend_context_sources=_csv_tuple(env.get("BACKEND_CONTEXT_SOURCES")),
        )


def build_agent_context_planner(
    settings: AgentPlannerSettings,
) -> AgentContextPlanner:
    mode = settings.mode.strip().lower()
    if mode in {"deterministic", "rules"}:
        return DeterministicAgentContextPlanner(
            backend_context_sources=settings.backend_context_sources
        )
    if mode in {"model", "llm", "model_backed"}:
        return ModelBackedAgentContextPlanner()
    raise DTOValidationError(
        "AGENT_CONTEXT_PLANNER must be deterministic or model"
    )


def build_agent_context_planner_from_env(
    env: Mapping[str, str],
) -> AgentContextPlanner:
    return build_agent_context_planner(AgentPlannerSettings.from_env(env))


def _csv_tuple(value: str | None) -> tuple[str, ...]:
    if value is None or not value.strip():
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())
