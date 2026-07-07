from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import SQLiteMemoryStore  # noqa: E402
from haruhi_roleplay_api.application.errors import AppError, ErrorCode  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    MemoryDeleteCommand,
    MemoryQuery,
    MemoryType,
    MemoryWriteCandidate,
    MemoryWriteCommand,
    PersonaModeId,
    UserId,
)


def create_store(path: Path) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(path=path)


def write_command(
    *,
    app_id: str = "web",
    user_id: str = "user-1",
    character_id: str = "haruhi",
    persona_mode: str = "mid_late_haruhi",
    memory_type: MemoryType = MemoryType.USER_PREFERENCE,
    content: str = "用户喜欢先制定社团计划",
) -> MemoryWriteCommand:
    return MemoryWriteCommand(
        appId=AppId(app_id),
        userId=UserId(user_id),
        characterId=CharacterId(character_id),
        personaMode=PersonaModeId(persona_mode),
        candidate=MemoryWriteCandidate(
            type=memory_type,
            content=content,
            reason="用户明确表达稳定偏好",
            confidence=0.9,
        ),
    )


def memory_query(
    *,
    app_id: str = "web",
    user_id: str = "user-1",
    character_id: str = "haruhi",
    persona_mode: str = "mid_late_haruhi",
    memory_types: tuple[MemoryType, ...] = (),
) -> MemoryQuery:
    return MemoryQuery(
        appId=AppId(app_id),
        userId=UserId(user_id),
        characterId=CharacterId(character_id),
        personaMode=PersonaModeId(persona_mode),
        memoryTypes=memory_types,
        limit=10,
    )


class SQLiteMemoryStoreTests(unittest.TestCase):
    def test_add_list_and_delete_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = create_store(Path(temp_dir) / "memories.sqlite3")
            item = store.add_memory(write_command())

            listed = store.list_memories(memory_query())
            deleted = store.delete_memory(
                MemoryDeleteCommand(
                    memoryId=item.memoryId,
                    appId=AppId("web"),
                    userId=UserId("user-1"),
                    characterId=CharacterId("haruhi"),
                    personaMode=PersonaModeId("mid_late_haruhi"),
                )
            )
            after_delete = store.list_memories(memory_query())

        self.assertEqual(listed, (item,))
        self.assertEqual(deleted.memoryId, item.memoryId)
        self.assertEqual(after_delete, ())

    def test_recreated_store_reads_existing_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "memories.sqlite3"
            first_store = create_store(path)
            item = first_store.add_memory(write_command(content="重启后仍应存在"))

            second_store = create_store(path)
            listed = second_store.list_memories(memory_query())

        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].memoryId, item.memoryId)
        self.assertEqual(listed[0].content, "重启后仍应存在")
        self.assertEqual(listed[0].reason, "用户明确表达稳定偏好")

    def test_deleted_memory_stays_deleted_after_store_recreation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "memories.sqlite3"
            first_store = create_store(path)
            item = first_store.add_memory(write_command())
            first_store.delete_memory(
                MemoryDeleteCommand(
                    memoryId=item.memoryId,
                    appId=AppId("web"),
                    userId=UserId("user-1"),
                    characterId=CharacterId("haruhi"),
                    personaMode=PersonaModeId("mid_late_haruhi"),
                )
            )

            second_store = create_store(path)
            listed = second_store.list_memories(memory_query())

        self.assertEqual(listed, ())

    def test_scope_and_type_filters_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = create_store(Path(temp_dir) / "memories.sqlite3")
            store.add_memory(write_command(content="目标记忆"))
            store.add_memory(write_command(user_id="user-2", content="其他用户"))
            store.add_memory(write_command(character_id="kyon", content="其他角色"))
            store.add_memory(
                write_command(
                    memory_type=MemoryType.RELATIONSHIP,
                    content="关系记忆",
                )
            )

            listed = store.list_memories(
                memory_query(memory_types=(MemoryType.USER_PREFERENCE,))
            )

        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].content, "目标记忆")

    def test_delete_keeps_scope_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = create_store(Path(temp_dir) / "memories.sqlite3")
            item = store.add_memory(write_command())

            with self.assertRaises(AppError) as raised:
                store.delete_memory(
                    MemoryDeleteCommand(
                        memoryId=item.memoryId,
                        appId=AppId("web"),
                        userId=UserId("user-2"),
                        characterId=CharacterId("haruhi"),
                        personaMode=PersonaModeId("mid_late_haruhi"),
                    )
                )
            listed = store.list_memories(memory_query())

        self.assertEqual(raised.exception.code, ErrorCode.MEMORY_NOT_FOUND)
        self.assertEqual(len(listed), 1)


if __name__ == "__main__":
    unittest.main()
