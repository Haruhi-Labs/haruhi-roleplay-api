"""Memory use cases."""

from __future__ import annotations

from haruhi_roleplay_api.domain import (
    MemoryDeleteCommand,
    MemoryItem,
    MemoryQuery,
    MemoryReadPolicyInput,
)
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


class DefaultMemoryPolicyEngine:
    def should_read(self, policy_input: MemoryReadPolicyInput) -> bool:
        return (
            policy_input.enabled
            and bool(policy_input.allowedTypes)
            and policy_input.maxItems > 0
        )
