from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import PostgresSessionStore  # noqa: E402
from haruhi_roleplay_api.application.errors import AppError, ErrorCode  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    DTOValidationError,
    PersonaModeId,
    UserId,
)


class FakeCursor:
    def __init__(self, cursor: sqlite3.Cursor | None = None, rows: list[Any] | None = None) -> None:
        self._cursor = cursor
        self._rows = rows

    def fetchone(self):
        if self._rows is not None:
            return self._rows[0] if self._rows else None
        if self._cursor is None:
            return None
        return self._cursor.fetchone()

    def fetchall(self):
        if self._rows is not None:
            return self._rows
        if self._cursor is None:
            return []
        return self._cursor.fetchall()


class FakePostgresConnection:
    def __init__(self) -> None:
        self._connection = sqlite3.connect(":memory:")
        self._connection.row_factory = sqlite3.Row
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeCursor:
        if "information_schema.tables" in sql:
            return FakeCursor(rows=self._information_schema_tables(params))
        normalized = _sqlite_sql(sql)
        if normalized is None:
            return FakeCursor()
        return FakeCursor(self._connection.execute(normalized, params))

    def commit(self) -> None:
        self.commits += 1
        self._connection.commit()

    def rollback(self) -> None:
        self.rollbacks += 1
        self._connection.rollback()

    def close(self) -> None:
        self.closed += 1

    def _information_schema_tables(self, params: tuple[Any, ...]) -> list[dict[str, str]]:
        expected_names = {str(item) for item in params[1:]}
        rows = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return [
            {"table_name": str(row["name"])}
            for row in rows
            if str(row["name"]) in expected_names
        ]


class FakePostgresDatabase:
    def __init__(self) -> None:
        self.connection = FakePostgresConnection()
        self.urls: list[str] = []

    def connect(self, database_url: str) -> FakePostgresConnection:
        self.urls.append(database_url)
        return self.connection


def create_store(
    database: FakePostgresDatabase,
    *,
    auto_create_schema: bool = True,
) -> PostgresSessionStore:
    return PostgresSessionStore(
        database_url="postgresql://user:password@db.example/roleplay",
        auto_create_schema=auto_create_schema,
        connection_factory=database.connect,
    )


class PostgresSessionStoreTests(unittest.TestCase):
    def test_create_get_append_and_recent_messages(self) -> None:
        database = FakePostgresDatabase()
        store = create_store(database)

        session = store.create_session(
            app_id=AppId("web"),
            user_id=UserId("user-1"),
            character_id=CharacterId("haruhi"),
            persona_mode=PersonaModeId("mid_late_haruhi"),
        )
        first = store.append_message(
            session_id=session.sessionId,
            role="user",
            content="第一轮",
            metadata={"turn": 1},
        )
        second = store.append_message(
            session_id=session.sessionId,
            role="assistant",
            content="记录第一轮",
        )

        loaded = store.get_session(session.sessionId)
        recent_one = store.recent_messages(session.sessionId, limit=1)
        recent_all = store.recent_messages(session.sessionId, limit=10)

        self.assertEqual(loaded.sessionId, session.sessionId)
        self.assertEqual(loaded.appId, AppId("web"))
        self.assertEqual([message.messageId for message in recent_one], [second.messageId])
        self.assertEqual(
            [message.messageId for message in recent_all],
            [first.messageId, second.messageId],
        )
        self.assertEqual(recent_all[0].metadata, {"turn": 1})
        self.assertGreater(database.connection.commits, 0)

    def test_existing_schema_can_be_reused_without_auto_create(self) -> None:
        database = FakePostgresDatabase()
        first_store = create_store(database)
        session = first_store.create_session(
            app_id=AppId("web"),
            user_id=UserId("user-1"),
            character_id=CharacterId("haruhi"),
            persona_mode=PersonaModeId("mid_late_haruhi"),
        )
        first_store.append_message(
            session_id=session.sessionId,
            role="user",
            content="云端消息",
        )

        second_store = create_store(database, auto_create_schema=False)
        recent = second_store.recent_messages(session.sessionId, limit=5)

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].content, "云端消息")

    def test_missing_session_returns_stable_error(self) -> None:
        store = create_store(FakePostgresDatabase())

        with self.assertRaises(AppError) as raised:
            store.get_session("sess-missing")

        self.assertEqual(raised.exception.code, ErrorCode.SESSION_NOT_FOUND)

    def test_provider_errors_are_mapped(self) -> None:
        def failing_factory(_: str) -> object:
            raise RuntimeError("db down")

        with self.assertRaises(AppError) as raised:
            PostgresSessionStore(
                database_url="postgresql://user:password@db.example/roleplay",
                connection_factory=failing_factory,
            )

        self.assertEqual(raised.exception.code, ErrorCode.SESSION_PROVIDER_ERROR)

    def test_unsafe_schema_is_rejected(self) -> None:
        with self.assertRaises(DTOValidationError):
            PostgresSessionStore(
                database_url="postgresql://user:password@db.example/roleplay",
                schema="public;drop",
                connection_factory=FakePostgresDatabase().connect,
            )

    def test_metadata_must_be_json_serializable(self) -> None:
        store = create_store(FakePostgresDatabase())
        session = store.create_session(
            app_id=AppId("web"),
            user_id=UserId("user-1"),
            character_id=CharacterId("haruhi"),
            persona_mode=PersonaModeId("mid_late_haruhi"),
        )

        with self.assertRaises(DTOValidationError):
            store.append_message(
                session_id=session.sessionId,
                role="user",
                content="bad metadata",
                metadata={"bad": object()},
            )


def _sqlite_sql(sql: str) -> str | None:
    if "CREATE SCHEMA" in sql:
        return None
    translated = sql
    translated = translated.replace('"public"."roleplay_sessions"', "roleplay_sessions")
    translated = translated.replace(
        '"public"."roleplay_session_messages"',
        "roleplay_session_messages",
    )
    translated = translated.replace("%s", "?")
    translated = translated.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    return translated


if __name__ == "__main__":
    unittest.main()
