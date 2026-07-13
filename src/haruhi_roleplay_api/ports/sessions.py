"""Session store port."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    PersonaModeId,
    Session,
    SessionAdminPage,
    SessionAdminQuery,
    SessionId,
    SessionMessage,
    UserId,
)


class SessionStore(Protocol):
    def create_session(
        self,
        *,
        app_id: AppId,
        user_id: UserId,
        character_id: CharacterId,
        persona_mode: PersonaModeId,
    ) -> Session:
        """Create one active session."""

    def get_session(self, session_id: SessionId | str) -> Session:
        """Return one session or raise a stable application error."""

    def recent_messages(
        self,
        session_id: SessionId | str,
        *,
        limit: int,
    ) -> tuple[SessionMessage, ...]:
        """Return recent messages in chronological order."""

    def append_message(
        self,
        *,
        session_id: SessionId | str,
        role: str,
        content: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> SessionMessage:
        """Append one user or assistant message."""

    def admin_list_sessions(self, query: SessionAdminQuery) -> SessionAdminPage:
        """Return a filtered, paginated session management view."""

    def admin_close_session(self, session_id: SessionId | str) -> Session:
        """Close one session under administrator authority."""
