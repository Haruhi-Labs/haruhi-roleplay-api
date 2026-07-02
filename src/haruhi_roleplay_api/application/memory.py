"""Memory use cases."""

from __future__ import annotations

from haruhi_roleplay_api.domain import (
    MemoryDeleteCommand,
    MemoryItem,
    MemoryQuery,
    MemoryReadPolicyInput,
    MemoryWritePolicyInput,
)
from haruhi_roleplay_api.ports import MemoryStore


MIN_WRITE_CONFIDENCE = 0.7
STABLE_REASON_KEYWORDS = ("稳定", "偏好", "长期", "关系", "约定", "明确")
TEMPORARY_KEYWORDS = ("临时", "一次性", "今天", "现在", "刚才", "这次", "心情")
SENSITIVE_KEYWORDS = (
    "api key",
    "apikey",
    "password",
    "token",
    "住址",
    "身份证",
    "手机号",
    "银行卡",
    "密码",
)


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

    def should_write(self, policy_input: MemoryWritePolicyInput) -> bool:
        candidate = policy_input.candidate
        text = f"{candidate.content}\n{candidate.reason}".casefold()
        return (
            policy_input.enabled
            and candidate.type in policy_input.allowedTypes
            and candidate.confidence >= MIN_WRITE_CONFIDENCE
            and _contains_any(candidate.reason, STABLE_REASON_KEYWORDS)
            and not _contains_any(text, TEMPORARY_KEYWORDS)
            and not _contains_any(text, SENSITIVE_KEYWORDS)
        )


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(keyword.casefold() in lowered for keyword in keywords)
