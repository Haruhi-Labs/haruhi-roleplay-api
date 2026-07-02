"""Memory store port."""

from __future__ import annotations

from typing import Protocol

from haruhi_roleplay_api.domain import (
    MemoryDeleteCommand,
    MemoryItem,
    MemoryQuery,
    MemoryReadPolicyInput,
)


class MemoryStore(Protocol):
    def list_memories(self, query: MemoryQuery) -> tuple[MemoryItem, ...]:
        """Return memories visible to one app/user/character/preset context."""

    def delete_memory(self, command: MemoryDeleteCommand) -> MemoryItem:
        """Delete one visible memory or raise a stable application error."""


class MemoryPolicyEngine(Protocol):
    def should_read(self, policy_input: MemoryReadPolicyInput) -> bool:
        """Return whether chat may read memory for this request."""
