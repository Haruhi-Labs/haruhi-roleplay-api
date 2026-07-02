from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import InMemoryMemoryStore  # noqa: E402
from haruhi_roleplay_api.api.memory import delete_memory, get_memory  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    MemoryId,
    MemoryItem,
    MemoryType,
    PersonaModeId,
    UserId,
)


def memory_item(
    memory_id: str,
    *,
    app_id: str = "web",
    user_id: str = "user-1",
    character_id: str = "haruhi",
    persona_mode: str | None = "mid_late_haruhi",
    memory_type: MemoryType = MemoryType.USER_PREFERENCE,
    content: str = "likes mystery club planning",
) -> MemoryItem:
    return MemoryItem(
        memoryId=MemoryId(memory_id),
        appId=AppId(app_id),
        userId=UserId(user_id),
        characterId=CharacterId(character_id),
        personaMode=(
            PersonaModeId(persona_mode) if persona_mode is not None else None
        ),
        type=memory_type,
        content=content,
        confidence=0.9,
        createdAt="2026-07-02T00:00:00+00:00",
        updatedAt="2026-07-02T00:00:00+00:00",
    )


def memory_query(
    *,
    app_id: str = "web",
    character_id: str = "haruhi",
    persona_mode: str | None = "mid_late_haruhi",
) -> dict[str, str]:
    query = {
        "app_id": app_id,
        "character_id": character_id,
    }
    if persona_mode is not None:
        query["persona_mode"] = persona_mode
    return query


class MemoryCrudTests(unittest.TestCase):
    def test_query_memory(self) -> None:
        store = InMemoryMemoryStore([memory_item("mem-1")])

        response = get_memory(
            "user-1",
            memory_query(),
            memory_store=store,
            request_id="req-memory-list",
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["request_id"], "req-memory-list")
        self.assertEqual(response["data"]["count"], 1)
        self.assertEqual(response["data"]["items"][0]["memory_id"], "mem-1")
        self.assertEqual(response["data"]["items"][0]["type"], "user_preference")

    def test_delete_memory_removes_item(self) -> None:
        store = InMemoryMemoryStore([memory_item("mem-delete")])

        deleted = delete_memory(
            "user-1",
            "mem-delete",
            memory_query(),
            memory_store=store,
            request_id="req-memory-delete",
        )
        listed = get_memory(
            "user-1",
            memory_query(),
            memory_store=store,
            request_id="req-memory-list",
        )

        self.assertTrue(deleted["ok"])
        self.assertEqual(deleted["data"], {"memory_id": "mem-delete", "deleted": True})
        self.assertEqual(listed["data"]["count"], 0)

    def test_different_app_is_isolated(self) -> None:
        store = InMemoryMemoryStore([memory_item("mem-app", app_id="admin")])

        response = get_memory(
            "user-1",
            memory_query(app_id="web"),
            memory_store=store,
            request_id="req-memory-app",
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["count"], 0)

    def test_different_user_is_isolated(self) -> None:
        store = InMemoryMemoryStore([memory_item("mem-user", user_id="user-1")])

        response = get_memory(
            "user-2",
            memory_query(),
            memory_store=store,
            request_id="req-memory-user",
        )
        delete_response = delete_memory(
            "user-2",
            "mem-user",
            memory_query(),
            memory_store=store,
            request_id="req-memory-delete-user",
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["count"], 0)
        self.assertFalse(delete_response["ok"])
        self.assertEqual(delete_response["error"]["code"], "MEMORY_NOT_FOUND")

    def test_different_character_is_isolated(self) -> None:
        store = InMemoryMemoryStore(
            [
                memory_item("mem-haruhi", character_id="haruhi"),
                memory_item("mem-kyon", character_id="kyon"),
            ]
        )

        response = get_memory(
            "user-1",
            memory_query(character_id="haruhi"),
            memory_store=store,
            request_id="req-memory-character",
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["count"], 1)
        self.assertEqual(response["data"]["items"][0]["memory_id"], "mem-haruhi")

    def test_different_persona_is_isolated(self) -> None:
        store = InMemoryMemoryStore(
            [
                memory_item("mem-mid", persona_mode="mid_late_haruhi"),
                memory_item("mem-disappearance", persona_mode="disappearance_haruhi"),
            ]
        )

        response = get_memory(
            "user-1",
            memory_query(persona_mode="mid_late_haruhi"),
            memory_store=store,
            request_id="req-memory-persona",
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["count"], 1)
        self.assertEqual(response["data"]["items"][0]["memory_id"], "mem-mid")


if __name__ == "__main__":
    unittest.main()
