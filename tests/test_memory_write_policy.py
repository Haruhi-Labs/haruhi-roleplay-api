from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import (  # noqa: E402
    InMemoryMemoryStore,
    LocalPersonaRepository,
)
from haruhi_roleplay_api.api.chat import post_chat  # noqa: E402
from haruhi_roleplay_api.api.memory import delete_memory, get_memory  # noqa: E402
from haruhi_roleplay_api.application import PersonaPromptBuilder  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    GenerationConfig,
    ModelMessage,
    ModelResponse,
    ModelUsage,
)


ROOT = Path(__file__).resolve().parents[1]


class RecordingModelRouter:
    def __init__(self) -> None:
        self.calls: list[tuple[ModelMessage, ...]] = []

    def generate(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ) -> ModelResponse:
        self.calls.append(messages)
        return ModelResponse(
            reply="memory write reply",
            provider="recording",
            model=generation.model if generation and generation.model else "recording",
            usage=ModelUsage(promptTokens=1, completionTokens=1),
            debug={"modelProvider": "recording"},
        )


def chat_body(memory_write: object | None = None) -> dict:
    body = {
        "app_id": "web",
        "user_id": "user-1",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "message": "请记住这个偏好。",
        "language": "zh-CN",
        "capabilities": {
            "rag": False,
            "memory": True,
            "continuous_session": False,
            "safety_filter": True,
            "debug_trace": True,
            "stream": False,
        },
        "generation": {
            "model": "recording-model",
        },
        "metadata": {},
    }
    if memory_write is not None:
        body["metadata"]["memory_write"] = memory_write
    return body


def stable_preference_candidate() -> dict:
    return {
        "type": "user_preference",
        "content": "用户喜欢先制定社团活动计划",
        "reason": "用户明确表达稳定偏好",
        "confidence": 0.9,
    }


def memory_query() -> dict[str, str]:
    return {
        "app_id": "web",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
    }


def call_chat(body: dict, *, store: InMemoryMemoryStore) -> dict:
    return post_chat(
        body,
        persona_repository=LocalPersonaRepository(ROOT / "personas"),
        prompt_builder=PersonaPromptBuilder(),
        model_router=RecordingModelRouter(),
        memory_store=store,
        request_id="req-memory-write",
    )


class MemoryWritePolicyTests(unittest.TestCase):
    def test_explicit_stable_preference_is_written(self) -> None:
        store = InMemoryMemoryStore()

        response = call_chat(chat_body(stable_preference_candidate()), store=store)
        listed = get_memory(
            "user-1",
            memory_query(),
            memory_store=store,
            request_id="req-memory-list",
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["memory"]["read_count"], 0)
        self.assertEqual(response["data"]["memory"]["write_count"], 1)
        self.assertEqual(response["data"]["debug"]["memoryWriteCount"], 1)
        self.assertEqual(listed["data"]["count"], 1)
        self.assertEqual(
            listed["data"]["items"][0]["content"],
            "用户喜欢先制定社团活动计划",
        )
        self.assertEqual(
            listed["data"]["items"][0]["reason"],
            "用户明确表达稳定偏好",
        )

    def test_temporary_chat_is_not_written(self) -> None:
        store = InMemoryMemoryStore()
        candidate = {
            "type": "user_preference",
            "content": "用户今天有点困",
            "reason": "一次性闲聊内容",
            "confidence": 0.95,
        }

        response = call_chat(chat_body(candidate), store=store)
        listed = get_memory(
            "user-1",
            memory_query(),
            memory_store=store,
            request_id="req-memory-list",
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["memory"]["write_count"], 0)
        self.assertEqual(listed["data"]["count"], 0)

    def test_sensitive_candidate_is_not_written(self) -> None:
        store = InMemoryMemoryStore()
        candidate = {
            "type": "user_preference",
            "content": "用户手机号是 13800000000",
            "reason": "用户明确表达稳定偏好",
            "confidence": 0.95,
        }

        response = call_chat(chat_body(candidate), store=store)
        listed = get_memory(
            "user-1",
            memory_query(),
            memory_store=store,
            request_id="req-memory-list",
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["memory"]["write_count"], 0)
        self.assertEqual(listed["data"]["count"], 0)

    def test_disallowed_type_is_not_written(self) -> None:
        store = InMemoryMemoryStore()
        candidate = {
            "type": "safety_preference",
            "content": "用户希望更保守的安全边界",
            "reason": "用户明确表达稳定偏好",
            "confidence": 0.95,
        }

        response = call_chat(chat_body(candidate), store=store)

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["memory"]["write_count"], 0)

    def test_deleted_written_memory_is_not_read_later(self) -> None:
        store = InMemoryMemoryStore()
        call_chat(chat_body(stable_preference_candidate()), store=store)
        listed = get_memory(
            "user-1",
            memory_query(),
            memory_store=store,
            request_id="req-memory-list",
        )
        memory_id = listed["data"]["items"][0]["memory_id"]

        deleted = delete_memory(
            "user-1",
            memory_id,
            memory_query(),
            memory_store=store,
            request_id="req-memory-delete",
        )
        response = call_chat(chat_body(), store=store)

        self.assertTrue(deleted["ok"])
        self.assertEqual(response["data"]["memory"]["read_count"], 0)


if __name__ == "__main__":
    unittest.main()
