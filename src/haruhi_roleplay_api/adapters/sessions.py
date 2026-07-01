"""In-memory session store for local tests and early MVP work."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import uuid4

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    MessageId,
    PersonaModeId,
    Session,
    SessionId,
    SessionMessage,
    SessionStatus,
    UserId,
)


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._messages: dict[str, list[SessionMessage]] = {}

    def create_session(
        self,
        *,
        app_id: AppId,
        user_id: UserId,
        character_id: CharacterId,
        persona_mode: PersonaModeId,
    ) -> Session:
        now = _now()
        session = Session(
            sessionId=SessionId(f"sess-{uuid4().hex}"),
            appId=app_id,
            userId=user_id,
            characterId=character_id,
            personaMode=persona_mode,
            status=SessionStatus.ACTIVE,
            createdAt=now,
            updatedAt=now,
        )
        self._sessions[str(session.sessionId)] = session
        self._messages[str(session.sessionId)] = []
        return session

    def get_session(self, session_id: SessionId | str) -> Session:
        session = self._sessions.get(str(session_id))
        if session is None:
            raise AppError(
                code=ErrorCode.SESSION_NOT_FOUND,
                message="Session was not found.",
            )
        return session

    def recent_messages(
        self,
        session_id: SessionId | str,
        *,
        limit: int,
    ) -> tuple[SessionMessage, ...]:
        self.get_session(session_id)
        if limit <= 0:
            return ()
        return tuple(self._messages.get(str(session_id), [])[-limit:])

    def append_message(
        self,
        *,
        session_id: SessionId | str,
        role: str,
        content: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> SessionMessage:
        session = self.get_session(session_id)
        now = _now()
        message = SessionMessage(
            messageId=MessageId(f"msg-{uuid4().hex}"),
            sessionId=SessionId(str(session_id)),
            role=role,
            content=content,
            createdAt=now,
            metadata=dict(metadata or {}),
        )
        self._messages[str(session_id)].append(message)
        self._sessions[str(session_id)] = replace(session, updatedAt=now)
        return message


def _now() -> str:
    return datetime.now(UTC).isoformat()

