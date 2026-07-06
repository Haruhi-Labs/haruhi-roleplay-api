"""SQLite-backed session store for local persistence."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Mapping
from uuid import uuid4

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    DTOValidationError,
    MessageId,
    PersonaModeId,
    Session,
    SessionId,
    SessionMessage,
    SessionStatus,
    UserId,
)


class SQLiteSessionStore:
    def __init__(
        self,
        *,
        path: str | Path,
        auto_create_schema: bool = True,
        busy_timeout_ms: int = 5000,
        ttl_seconds: int = 604800,
    ) -> None:
        self._path = _sqlite_path(path)
        self._busy_timeout_ms = busy_timeout_ms
        self._ttl_seconds = ttl_seconds
        if auto_create_schema:
            self._initialize_schema()
        else:
            self._validate_existing_schema()

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
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id,
                    app_id,
                    user_id,
                    character_id,
                    persona_mode,
                    status,
                    created_at,
                    updated_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(session.sessionId),
                    str(session.appId),
                    str(session.userId),
                    str(session.characterId),
                    str(session.personaMode),
                    session.status.value,
                    session.createdAt,
                    session.updatedAt,
                    _expires_at(now, self._ttl_seconds),
                ),
            )
        return session

    def get_session(self, session_id: SessionId | str) -> Session:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    session_id,
                    app_id,
                    user_id,
                    character_id,
                    persona_mode,
                    status,
                    created_at,
                    updated_at
                FROM sessions
                WHERE session_id = ?
                """,
                (str(session_id),),
            ).fetchone()
        if row is None:
            raise AppError(
                code=ErrorCode.SESSION_NOT_FOUND,
                message="Session was not found.",
            )
        return _session_from_row(row)

    def recent_messages(
        self,
        session_id: SessionId | str,
        *,
        limit: int,
    ) -> tuple[SessionMessage, ...]:
        self.get_session(session_id)
        if limit <= 0:
            return ()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    message_id,
                    session_id,
                    role,
                    content,
                    metadata_json,
                    created_at
                FROM (
                    SELECT
                        message_order,
                        message_id,
                        session_id,
                        role,
                        content,
                        metadata_json,
                        created_at
                    FROM session_messages
                    WHERE session_id = ?
                    ORDER BY message_order DESC
                    LIMIT ?
                )
                ORDER BY message_order ASC
                """,
                (str(session_id), limit),
            ).fetchall()
        return tuple(_message_from_row(row) for row in rows)

    def append_message(
        self,
        *,
        session_id: SessionId | str,
        role: str,
        content: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> SessionMessage:
        self.get_session(session_id)
        now = _now()
        message = SessionMessage(
            messageId=MessageId(f"msg-{uuid4().hex}"),
            sessionId=SessionId(str(session_id)),
            role=role,
            content=content,
            createdAt=now,
            metadata=dict(metadata or {}),
        )
        metadata_json = _metadata_json(message.metadata)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO session_messages (
                    message_id,
                    session_id,
                    role,
                    content,
                    metadata_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(message.messageId),
                    str(message.sessionId),
                    message.role,
                    message.content,
                    metadata_json,
                    message.createdAt,
                ),
            )
            connection.execute(
                """
                UPDATE sessions
                SET updated_at = ?
                WHERE session_id = ?
                """,
                (now, str(session_id)),
            )
        return message

    def _initialize_schema(self) -> None:
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA_SQL)

    def _validate_existing_schema(self) -> None:
        if self._path != ":memory:" and not Path(self._path).exists():
            raise DTOValidationError(
                "SESSION_SQLITE_PATH database does not exist and "
                "SESSION_AUTO_CREATE_SCHEMA=false"
            )
        with self._connect() as connection:
            table_names = {
                row["name"]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                ).fetchall()
            }
        missing = {"sessions", "session_messages"} - table_names
        if missing:
            raise DTOValidationError(
                "SQLite session schema is missing: " + ", ".join(sorted(missing))
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self._path,
            timeout=self._busy_timeout_ms / 1000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    persona_mode TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'closed', 'expired')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_scope
ON sessions(app_id, user_id, character_id, persona_mode, status);

CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
ON sessions(updated_at);

CREATE TABLE IF NOT EXISTS session_messages (
    message_order INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_session_messages_recent
ON session_messages(session_id, message_order);

CREATE INDEX IF NOT EXISTS idx_session_messages_session_id_message_id
ON session_messages(session_id, message_id);
"""


def _session_from_row(row: sqlite3.Row) -> Session:
    return Session(
        sessionId=SessionId(str(row["session_id"])),
        appId=AppId(str(row["app_id"])),
        userId=UserId(str(row["user_id"])),
        characterId=CharacterId(str(row["character_id"])),
        personaMode=PersonaModeId(str(row["persona_mode"])),
        status=SessionStatus(str(row["status"])),
        createdAt=str(row["created_at"]),
        updatedAt=str(row["updated_at"]),
    )


def _message_from_row(row: sqlite3.Row) -> SessionMessage:
    return SessionMessage(
        messageId=MessageId(str(row["message_id"])),
        sessionId=SessionId(str(row["session_id"])),
        role=str(row["role"]),
        content=str(row["content"]),
        createdAt=str(row["created_at"]),
        metadata=_metadata_from_json(str(row["metadata_json"])),
    )


def _metadata_json(metadata: Mapping[str, Any]) -> str:
    try:
        return json.dumps(dict(metadata), ensure_ascii=False, sort_keys=True)
    except TypeError as exc:
        raise DTOValidationError(
            "session message metadata must be JSON serializable"
        ) from exc


def _metadata_from_json(value: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise DTOValidationError("session message metadata_json is invalid") from exc
    if not isinstance(parsed, Mapping):
        raise DTOValidationError("session message metadata_json must be an object")
    return dict(parsed)


def _expires_at(now: str, ttl_seconds: int) -> str | None:
    if ttl_seconds <= 0:
        return None
    return (
        datetime.fromisoformat(now)
        + timedelta(seconds=ttl_seconds)
    ).isoformat()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sqlite_path(path: str | Path) -> str:
    raw_path = str(path).strip()
    if not raw_path:
        raise DTOValidationError("SESSION_SQLITE_PATH must not be empty")
    return raw_path
