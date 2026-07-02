"""In-memory memory store for local tests and early MVP work."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import uuid4

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    MemoryDeleteCommand,
    MemoryId,
    MemoryItem,
    MemoryQuery,
    MemoryWriteCommand,
)


class InMemoryMemoryStore:
    def __init__(self, items: Iterable[MemoryItem] | None = None) -> None:
        self._items: dict[str, MemoryItem] = {
            str(item.memoryId): item for item in items or ()
        }

    def list_memories(self, query: MemoryQuery) -> tuple[MemoryItem, ...]:
        matches = [
            item for item in self._items.values() if _matches_query(item, query)
        ]
        return tuple(matches[: query.limit])

    def delete_memory(self, command: MemoryDeleteCommand) -> MemoryItem:
        item = self._items.get(str(command.memoryId))
        if item is None or not _matches_delete_command(item, command):
            raise AppError(
                code=ErrorCode.MEMORY_NOT_FOUND,
                message="Memory was not found.",
            )
        del self._items[str(command.memoryId)]
        return item

    def add_memory(self, command: MemoryWriteCommand) -> MemoryItem:
        now = _now()
        item = MemoryItem(
            memoryId=MemoryId(f"mem-{uuid4().hex}"),
            appId=command.appId,
            userId=command.userId,
            characterId=command.characterId,
            personaMode=command.personaMode,
            type=command.candidate.type,
            content=command.candidate.content,
            confidence=command.candidate.confidence,
            reason=command.candidate.reason,
            createdAt=now,
            updatedAt=now,
        )
        self._items[str(item.memoryId)] = item
        return item


def _matches_query(item: MemoryItem, query: MemoryQuery) -> bool:
    if str(item.appId) != str(query.appId):
        return False
    if str(item.userId) != str(query.userId):
        return False
    if str(item.characterId) != str(query.characterId):
        return False
    if _persona_mode_value(item) != _persona_mode_value(query):
        return False
    if query.memoryTypes and item.type not in query.memoryTypes:
        return False
    return True


def _matches_delete_command(
    item: MemoryItem,
    command: MemoryDeleteCommand,
) -> bool:
    if str(item.appId) != str(command.appId):
        return False
    if str(item.userId) != str(command.userId):
        return False
    if str(item.characterId) != str(command.characterId):
        return False
    return _persona_mode_value(item) == _persona_mode_value(command)


def _persona_mode_value(
    value: MemoryItem | MemoryQuery | MemoryDeleteCommand,
) -> str | None:
    return str(value.personaMode) if value.personaMode is not None else None


def _now() -> str:
    return datetime.now(UTC).isoformat()
