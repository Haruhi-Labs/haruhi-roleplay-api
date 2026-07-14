"""PostgreSQL-backed session store for cloud deployments."""

from __future__ import annotations

import importlib
import json
import re
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Iterator, Mapping
from uuid import uuid4

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    DTOValidationError,
    MessageId,
    PersonaModeId,
    Session,
    SessionAdminItem,
    SessionAdminPage,
    SessionAdminQuery,
    SessionId,
    SessionMessage,
    SessionStatus,
    UserId,
)

ConnectionFactory = Callable[[str], Any]
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PostgresSessionStore:
    def __init__(
        self,
        *,
        database_url: str,
        schema: str = "public",
        table_prefix: str = "roleplay_",
        auto_create_schema: bool = True,
        ttl_seconds: int = 604800,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        if not isinstance(database_url, str) or not database_url.strip():
            raise DTOValidationError("DATABASE_URL is required for postgres session provider")
        self._database_url = database_url.strip()
        self._schema = _identifier(schema, "SESSION_POSTGRES_SCHEMA")
        self._table_prefix = _table_prefix(table_prefix)
        self._ttl_seconds = ttl_seconds
        self._connection_factory = connection_factory or _psycopg_connection_factory()
        self._sessions_table = _qualified_table(
            self._schema,
            f"{self._table_prefix}sessions",
        )
        self._messages_table = _qualified_table(
            self._schema,
            f"{self._table_prefix}session_messages",
        )
        self._sessions_table_name = f"{self._table_prefix}sessions"
        self._messages_table_name = f"{self._table_prefix}session_messages"
        self._sessions_scope_index = _quoted_identifier(
            f"{self._table_prefix}sessions_scope_idx"
        )
        self._sessions_updated_at_index = _quoted_identifier(
            f"{self._table_prefix}sessions_updated_at_idx"
        )
        self._messages_recent_index = _quoted_identifier(
            f"{self._table_prefix}session_messages_recent_idx"
        )
        self._messages_id_index = _quoted_identifier(
            f"{self._table_prefix}session_messages_id_idx"
        )
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
        try:
            with self._connect() as connection:
                connection.execute(
                    f"""
                    INSERT INTO {self._sessions_table} (
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        except Exception as exc:
            _raise_provider_error(exc)
        return session

    def get_session(self, session_id: SessionId | str) -> Session:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"""
                    SELECT
                        session_id,
                        app_id,
                        user_id,
                        character_id,
                        persona_mode,
                        status,
                        created_at,
                        updated_at
                    FROM {self._sessions_table}
                    WHERE session_id = %s
                    """,
                    (str(session_id),),
                ).fetchone()
        except Exception as exc:
            _raise_provider_error(exc)
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
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""
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
                        FROM {self._messages_table}
                        WHERE session_id = %s
                        ORDER BY message_order DESC
                        LIMIT %s
                    ) recent
                    ORDER BY message_order ASC
                    """,
                    (str(session_id), limit),
                ).fetchall()
        except Exception as exc:
            _raise_provider_error(exc)
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
        try:
            with self._connect() as connection:
                connection.execute(
                    f"""
                    INSERT INTO {self._messages_table} (
                        message_id,
                        session_id,
                        role,
                        content,
                        metadata_json,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
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
                    f"""
                    UPDATE {self._sessions_table}
                    SET updated_at = %s
                    WHERE session_id = %s
                    """,
                    (now, str(session_id)),
                )
        except Exception as exc:
            _raise_provider_error(exc)
        return message

    def admin_list_sessions(self, query: SessionAdminQuery) -> SessionAdminPage:
        clauses: list[str] = []
        params: list[object] = []
        for column, value in (
            ("app_id", query.appId),
            ("user_id", query.userId),
            ("character_id", query.characterId),
        ):
            if value is not None:
                clauses.append(f"s.{column} = %s")
                params.append(value)
        if query.status is not None:
            clauses.append("s.status = %s")
            params.append(query.status.value)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            with self._connect() as connection:
                total_row = connection.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM {self._sessions_table} AS s
                    {where_sql}
                    """,
                    tuple(params),
                ).fetchone()
                rows = connection.execute(
                    f"""
                    SELECT
                        s.session_id,
                        s.app_id,
                        s.user_id,
                        s.character_id,
                        s.persona_mode,
                        s.status,
                        s.created_at,
                        s.updated_at,
                        s.expires_at,
                        COUNT(m.message_id) AS message_count
                    FROM {self._sessions_table} AS s
                    LEFT JOIN {self._messages_table} AS m
                        ON m.session_id = s.session_id
                    {where_sql}
                    GROUP BY s.session_id
                    ORDER BY s.updated_at DESC, s.session_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (*params, query.limit, query.offset),
                ).fetchall()
        except Exception as exc:
            _raise_provider_error(exc)
        total = int(_row_value(total_row, "total")) if total_row is not None else 0
        return SessionAdminPage(
            total=total,
            items=tuple(
                SessionAdminItem(
                    session=_session_from_row(row),
                    messageCount=int(_row_value(row, "message_count")),
                    expiresAt=(
                        str(_row_value(row, "expires_at"))
                        if _row_value(row, "expires_at") is not None
                        else None
                    ),
                )
                for row in rows
            ),
        )

    def admin_close_session(self, session_id: SessionId | str) -> Session:
        clean_session_id = str(session_id)
        now = _now()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"""
                    SELECT
                        session_id,
                        app_id,
                        user_id,
                        character_id,
                        persona_mode,
                        status,
                        created_at,
                        updated_at
                    FROM {self._sessions_table}
                    WHERE session_id = %s
                    FOR UPDATE
                    """,
                    (clean_session_id,),
                ).fetchone()
                if (
                    row is not None
                    and str(_row_value(row, "status"))
                    != SessionStatus.CLOSED.value
                ):
                    cursor = connection.execute(
                        f"""
                        UPDATE {self._sessions_table}
                        SET status = %s, updated_at = %s
                        WHERE session_id = %s
                        """,
                        (SessionStatus.CLOSED.value, now, clean_session_id),
                    )
                    if cursor.rowcount != 1:
                        row = None
        except Exception as exc:
            _raise_provider_error(exc)
        if row is None:
            raise AppError(
                code=ErrorCode.SESSION_NOT_FOUND,
                message="Session was not found.",
            )
        if str(_row_value(row, "status")) == SessionStatus.CLOSED.value:
            return _session_from_row(row)
        return Session(
            sessionId=SessionId(clean_session_id),
            appId=AppId(str(_row_value(row, "app_id"))),
            userId=UserId(str(_row_value(row, "user_id"))),
            characterId=CharacterId(str(_row_value(row, "character_id"))),
            personaMode=PersonaModeId(str(_row_value(row, "persona_mode"))),
            status=SessionStatus.CLOSED,
            createdAt=str(_row_value(row, "created_at")),
            updatedAt=now,
        )

    def _initialize_schema(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    f"CREATE SCHEMA IF NOT EXISTS {_quoted_identifier(self._schema)}"
                )
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._sessions_table} (
                        session_id TEXT PRIMARY KEY,
                        app_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        character_id TEXT NOT NULL,
                        persona_mode TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('active', 'closed', 'expired')),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        expires_at TEXT
                    )
                    """
                )
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self._sessions_scope_index}
                    ON {self._sessions_table}(
                        app_id,
                        user_id,
                        character_id,
                        persona_mode,
                        status
                    )
                    """
                )
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self._sessions_updated_at_index}
                    ON {self._sessions_table}(updated_at)
                    """
                )
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._messages_table} (
                        message_order BIGSERIAL PRIMARY KEY,
                        message_id TEXT NOT NULL UNIQUE,
                        session_id TEXT NOT NULL REFERENCES {self._sessions_table}(session_id)
                            ON DELETE CASCADE,
                        role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                        content TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self._messages_recent_index}
                    ON {self._messages_table}(session_id, message_order)
                    """
                )
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self._messages_id_index}
                    ON {self._messages_table}(session_id, message_id)
                    """
                )
        except Exception as exc:
            _raise_provider_error(exc)

    def _validate_existing_schema(self) -> None:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    AND table_name IN (%s, %s)
                    """,
                    (
                        self._schema,
                        self._sessions_table_name,
                        self._messages_table_name,
                    ),
                ).fetchall()
        except Exception as exc:
            _raise_provider_error(exc)
        table_names = {str(_row_value(row, "table_name")) for row in rows}
        missing = {
            self._sessions_table_name,
            self._messages_table_name,
        } - table_names
        if missing:
            raise DTOValidationError(
                "PostgreSQL session schema is missing: "
                + ", ".join(sorted(missing))
            )

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        connection = self._connection_factory(self._database_url)
        try:
            yield connection
            _call_if_present(connection, "commit")
        except Exception:
            _call_if_present(connection, "rollback")
            raise
        finally:
            _call_if_present(connection, "close")


def _psycopg_connection_factory() -> ConnectionFactory:
    try:
        psycopg = importlib.import_module("psycopg")
        rows = importlib.import_module("psycopg.rows")
    except ImportError as exc:
        raise AppError(
            code=ErrorCode.SESSION_PROVIDER_ERROR,
            message=(
                "psycopg is required for SESSION_PROVIDER=postgres. "
                'Install it with: uv run --with "psycopg[binary]" ...'
            ),
        ) from exc

    def connect(database_url: str) -> Any:
        return psycopg.connect(database_url, row_factory=rows.dict_row)

    return connect


def _session_from_row(row: Mapping[str, Any]) -> Session:
    return Session(
        sessionId=SessionId(str(_row_value(row, "session_id"))),
        appId=AppId(str(_row_value(row, "app_id"))),
        userId=UserId(str(_row_value(row, "user_id"))),
        characterId=CharacterId(str(_row_value(row, "character_id"))),
        personaMode=PersonaModeId(str(_row_value(row, "persona_mode"))),
        status=SessionStatus(str(_row_value(row, "status"))),
        createdAt=str(_row_value(row, "created_at")),
        updatedAt=str(_row_value(row, "updated_at")),
    )


def _message_from_row(row: Mapping[str, Any]) -> SessionMessage:
    return SessionMessage(
        messageId=MessageId(str(_row_value(row, "message_id"))),
        sessionId=SessionId(str(_row_value(row, "session_id"))),
        role=str(_row_value(row, "role")),
        content=str(_row_value(row, "content")),
        createdAt=str(_row_value(row, "created_at")),
        metadata=_metadata_from_json(str(_row_value(row, "metadata_json"))),
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


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty identifier")
    normalized = value.strip()
    if not _IDENTIFIER_RE.fullmatch(normalized):
        raise DTOValidationError(f"{field_name} must be a safe identifier")
    return normalized


def _table_prefix(value: str) -> str:
    if value == "":
        return ""
    if not isinstance(value, str):
        raise DTOValidationError("SESSION_POSTGRES_TABLE_PREFIX must be a string")
    normalized = value.strip()
    if not normalized:
        return ""
    if not re.fullmatch(r"^[A-Za-z_][A-Za-z0-9_]*$", normalized):
        raise DTOValidationError(
            "SESSION_POSTGRES_TABLE_PREFIX must be a safe identifier prefix"
        )
    return normalized


def _qualified_table(schema: str, table_name: str) -> str:
    return f"{_quoted_identifier(schema)}.{_quoted_identifier(table_name)}"


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _row_value(row: Mapping[str, Any], key: str) -> Any:
    return row[key]


def _call_if_present(target: Any, method_name: str) -> None:
    method = getattr(target, method_name, None)
    if callable(method):
        method()


def _raise_provider_error(exc: Exception) -> None:
    if isinstance(exc, (AppError, DTOValidationError)):
        raise exc
    raise AppError(
        code=ErrorCode.SESSION_PROVIDER_ERROR,
        message="PostgreSQL session provider failed.",
    ) from exc
