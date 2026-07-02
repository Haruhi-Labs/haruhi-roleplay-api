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
from haruhi_roleplay_api.application import PersonaPromptBuilder  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    GenerationConfig,
    MemoryId,
    MemoryItem,
    MemoryType,
    ModelMessage,
    ModelResponse,
    ModelUsage,
    PersonaModeId,
    UserId,
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
            reply="memory reply",
            provider="recording",
            model=generation.model if generation and generation.model else "recording",
            usage=ModelUsage(promptTokens=1, completionTokens=1),
            debug={"modelProvider": "recording"},
        )


class ExplodingMemoryStore:
    def list_memories(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("memory store should not be read")


def memory_item(
    memory_id: str,
    *,
    character_id: str = "haruhi",
    persona_mode: str = "mid_late_haruhi",
    memory_type: MemoryType = MemoryType.USER_PREFERENCE,
    content: str = "用户喜欢先安排社团计划",
) -> MemoryItem:
    return MemoryItem(
        memoryId=MemoryId(memory_id),
        appId=AppId("web"),
        userId=UserId("user-1"),
        characterId=CharacterId(character_id),
        personaMode=PersonaModeId(persona_mode),
        type=memory_type,
        content=content,
        confidence=0.9,
        createdAt="2026-07-02T00:00:00+00:00",
        updatedAt="2026-07-02T00:00:00+00:00",
    )


def chat_body(
    *,
    memory: bool,
    character_id: str = "haruhi",
    persona_mode: str = "mid_late_haruhi",
) -> dict:
    return {
        "app_id": "web",
        "user_id": "user-1",
        "character_id": character_id,
        "persona_mode": persona_mode,
        "message": "今天怎么开始？",
        "language": "zh-CN",
        "capabilities": {
            "rag": False,
            "memory": memory,
            "continuous_session": False,
            "safety_filter": True,
            "debug_trace": True,
            "stream": False,
        },
        "generation": {
            "model": "recording-model",
        },
    }


def call_chat(
    body: dict,
    *,
    model_router: RecordingModelRouter,
    memory_store: object | None,
    memory_read_limit: int = 5,
) -> dict:
    return post_chat(
        body,
        persona_repository=LocalPersonaRepository(ROOT / "personas"),
        prompt_builder=PersonaPromptBuilder(),
        model_router=model_router,
        memory_store=memory_store,
        memory_read_limit=memory_read_limit,
        request_id="req-memory-chat",
    )


class MemoryReadPolicyTests(unittest.TestCase):
    def test_memory_false_does_not_call_memory_store(self) -> None:
        router = RecordingModelRouter()

        response = call_chat(
            chat_body(memory=False),
            model_router=router,
            memory_store=ExplodingMemoryStore(),
        )

        prompt_text = "\n".join(message.content for message in router.calls[0])

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["memory"], {"enabled": False})
        self.assertFalse(response["data"]["debug"]["memoryEnabled"])
        self.assertEqual(response["data"]["debug"]["memoryReadCount"], 0)
        self.assertNotIn("长期记忆摘要", prompt_text)

    def test_memory_true_adds_allowed_items_to_prompt(self) -> None:
        router = RecordingModelRouter()
        store = InMemoryMemoryStore(
            [
                memory_item("mem-allowed"),
                memory_item(
                    "mem-blocked-type",
                    memory_type=MemoryType.SAFETY_PREFERENCE,
                    content="不应该进入当前 persona prompt",
                ),
            ]
        )

        response = call_chat(
            chat_body(memory=True),
            model_router=router,
            memory_store=store,
        )

        prompt_text = "\n".join(message.content for message in router.calls[0])
        memory = response["data"]["memory"]

        self.assertTrue(response["ok"])
        self.assertTrue(memory["enabled"])
        self.assertEqual(memory["read_count"], 1)
        self.assertEqual(response["data"]["debug"]["memoryReadCount"], 1)
        self.assertIn("长期记忆摘要", prompt_text)
        self.assertIn("type=user_preference", prompt_text)
        self.assertIn("confidence=0.90", prompt_text)
        self.assertIn("用户喜欢先安排社团计划", prompt_text)
        self.assertNotIn("不应该进入当前 persona prompt", prompt_text)

    def test_memory_read_limit_is_applied(self) -> None:
        router = RecordingModelRouter()
        store = InMemoryMemoryStore(
            [
                memory_item("mem-1", content="第一条记忆"),
                memory_item("mem-2", content="第二条记忆"),
                memory_item("mem-3", content="第三条记忆"),
            ]
        )

        response = call_chat(
            chat_body(memory=True),
            model_router=router,
            memory_store=store,
            memory_read_limit=2,
        )

        prompt_text = "\n".join(message.content for message in router.calls[0])

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["memory"]["read_count"], 2)
        self.assertIn("第一条记忆", prompt_text)
        self.assertIn("第二条记忆", prompt_text)
        self.assertNotIn("第三条记忆", prompt_text)

    def test_memory_read_keeps_character_isolated(self) -> None:
        router = RecordingModelRouter()
        store = InMemoryMemoryStore(
            [
                memory_item("mem-haruhi", content="春日相关记忆"),
                memory_item(
                    "mem-kyon",
                    character_id="kyon",
                    persona_mode="default_kyon",
                    content="阿虚相关记忆",
                ),
            ]
        )

        response = call_chat(
            chat_body(memory=True),
            model_router=router,
            memory_store=store,
        )

        prompt_text = "\n".join(message.content for message in router.calls[0])

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["memory"]["read_count"], 1)
        self.assertIn("春日相关记忆", prompt_text)
        self.assertNotIn("阿虚相关记忆", prompt_text)

    def test_memory_true_requires_memory_store(self) -> None:
        response = call_chat(
            chat_body(memory=True),
            model_router=RecordingModelRouter(),
            memory_store=None,
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(
            response["error"]["message"],
            "memoryStore is required for memory",
        )


if __name__ == "__main__":
    unittest.main()
