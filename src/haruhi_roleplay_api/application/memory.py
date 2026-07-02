"""Memory use cases."""

from __future__ import annotations

from haruhi_roleplay_api.domain import MemoryDeleteCommand, MemoryItem, MemoryQuery
from haruhi_roleplay_api.ports import MemoryStore


class ListMemoryUseCase:
    def __init__(self, memory_store: MemoryStore) -> None:
        self._memory_store = memory_store

    def execute(self, query: MemoryQuery) -> tuple[MemoryItem, ...]:
        return self._memory_store.list_memories(query)


class DeleteMemoryUseCase:
    def __init__(self, memory_store: MemoryStore) -> None:
        self._memory_store = memory_store

    def execute(self, command: MemoryDeleteCommand) -> MemoryItem:
        return self._memory_store.delete_memory(command)
