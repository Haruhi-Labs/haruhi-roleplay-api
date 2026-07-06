"""Fake backend context provider for local orchestration tests."""

from __future__ import annotations

from haruhi_roleplay_api.domain import (
    BackendContextFact,
    BackendContextRequest,
    DTOValidationError,
)


class FakeBackendContextProvider:
    def __init__(
        self,
        *,
        allowed_sources: tuple[str, ...] = ("user_profile", "game_state"),
    ) -> None:
        self._allowed_sources = tuple(allowed_sources)

    def fetch(
        self,
        request: BackendContextRequest,
    ) -> tuple[BackendContextFact, ...]:
        for source in request.sources:
            if source not in self._allowed_sources:
                raise DTOValidationError(
                    f"backend context source is not allowed: {source}"
                )
        facts: list[BackendContextFact] = []
        for source in request.sources:
            if source == "user_profile":
                facts.append(
                    BackendContextFact(
                        source=source,
                        key="profile_summary",
                        content="用户偏好轻快推进对话，喜欢直接进入社团行动。",
                        confidence=0.82,
                        ttlSeconds=300,
                    )
                )
            elif source == "game_state":
                facts.append(
                    BackendContextFact(
                        source=source,
                        key="current_activity",
                        content="当前活动进度：准备 SOS 团周末调查。",
                        confidence=0.78,
                        ttlSeconds=120,
                    )
                )
        return tuple(facts)
