"""Session use cases."""

from __future__ import annotations

from dataclasses import dataclass

from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    PersonaModeId,
    Session,
    UserId,
)
from haruhi_roleplay_api.ports import SessionStore


@dataclass(frozen=True, kw_only=True)
class CreateSessionInput:
    appId: AppId
    userId: UserId
    characterId: CharacterId
    personaMode: PersonaModeId


class CreateSessionUseCase:
    def __init__(self, session_store: SessionStore) -> None:
        self._session_store = session_store

    def execute(self, session_input: CreateSessionInput) -> Session:
        return self._session_store.create_session(
            app_id=session_input.appId,
            user_id=session_input.userId,
            character_id=session_input.characterId,
            persona_mode=session_input.personaMode,
        )

