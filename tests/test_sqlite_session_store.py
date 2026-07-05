from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import SQLiteSessionStore  # noqa: E402
from haruhi_roleplay_api.application.errors import AppError, ErrorCode  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    DTOValidationError,
    PersonaModeId,
    UserId,
)


def create_store(path: Path) -> SQLiteSessionStore:
    return SQLiteSessionStore(path=path)


class SQLiteSessionStoreTests(unittest.TestCase):
    def test_create_get_append_and_recent_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = create_store(Path(temp_dir) / "sessions.sqlite3")

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
        self.assertGreaterEqual(loaded.updatedAt, loaded.createdAt)
        self.assertEqual([message.messageId for message in recent_one], [second.messageId])
        self.assertEqual(
            [message.messageId for message in recent_all],
            [first.messageId, second.messageId],
        )
        self.assertEqual(recent_all[0].metadata, {"turn": 1})

    def test_recreated_store_reads_existing_session_and_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sessions.sqlite3"
            first_store = create_store(path)
            session = first_store.create_session(
                app_id=AppId("web"),
                user_id=UserId("user-1"),
                character_id=CharacterId("haruhi"),
                persona_mode=PersonaModeId("mid_late_haruhi"),
            )
            first_store.append_message(
                session_id=session.sessionId,
                role="user",
                content="重启前消息",
            )

            second_store = create_store(path)
            loaded = second_store.get_session(session.sessionId)
            recent = second_store.recent_messages(session.sessionId, limit=5)

        self.assertEqual(loaded.sessionId, session.sessionId)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].content, "重启前消息")

    def test_missing_session_returns_stable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = create_store(Path(temp_dir) / "sessions.sqlite3")

            with self.assertRaises(AppError) as raised:
                store.get_session("sess-missing")

        self.assertEqual(raised.exception.code, ErrorCode.SESSION_NOT_FOUND)

    def test_recent_messages_limit_zero_still_validates_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = create_store(Path(temp_dir) / "sessions.sqlite3")
            session = store.create_session(
                app_id=AppId("web"),
                user_id=UserId("user-1"),
                character_id=CharacterId("haruhi"),
                persona_mode=PersonaModeId("mid_late_haruhi"),
            )

            recent = store.recent_messages(session.sessionId, limit=0)

        self.assertEqual(recent, ())

    def test_auto_create_schema_false_requires_existing_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.sqlite3"

            with self.assertRaises(DTOValidationError):
                SQLiteSessionStore(
                    path=missing_path,
                    auto_create_schema=False,
                )

    def test_metadata_must_be_json_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = create_store(Path(temp_dir) / "sessions.sqlite3")
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


if __name__ == "__main__":
    unittest.main()
