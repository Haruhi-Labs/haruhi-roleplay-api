from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import InMemorySessionStore, LocalPersonaRepository  # noqa: E402
from haruhi_roleplay_api.api.chat import post_chat  # noqa: E402
from haruhi_roleplay_api.api.sessions import post_session  # noqa: E402
from haruhi_roleplay_api.application import PersonaPromptBuilder  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    GenerationConfig,
    ModelMessage,
    ModelResponse,
    ModelUsage,
    RagRetrieveOutput,
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
        user_message = next(
            message.content for message in reversed(messages) if message.role == "user"
        )
        return ModelResponse(
            reply=f"recorded: {user_message}",
            provider="recording",
            model=generation.model if generation and generation.model else "recording-model",
            usage=ModelUsage(promptTokens=1, completionTokens=1),
            debug={"modelProvider": "recording"},
        )


class ExplodingSessionStore:
    def get_session(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("session should not be read")

    def recent_messages(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("recent messages should not be read")

    def append_message(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("session should not be written")


class RecordingRagService:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def retrieve(self, retrieve_input: object) -> RagRetrieveOutput:
        self.calls.append(retrieve_input)
        return RagRetrieveOutput(
            chunks=(),
            provider="recording-rag",
            rawHitCount=0,
            filteredHitCount=0,
            rerankApplied=False,
        )


def create_session_body(user_id: str = "user-1") -> dict:
    return {
        "app_id": "web",
        "user_id": user_id,
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
    }


def chat_body(
    *,
    session_id: str | None,
    message: str,
    user_id: str = "user-1",
    continuous_session: bool = True,
    rag: bool = False,
) -> dict:
    return {
        "app_id": "web",
        "user_id": user_id,
        "session_id": session_id,
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "message": message,
        "language": "zh-CN",
        "capabilities": {
            "rag": rag,
            "memory": False,
            "continuous_session": continuous_session,
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
    session_store: object | None,
    model_router: RecordingModelRouter,
    rag_service: object | None = None,
    request_id: str = "req-chat",
) -> dict:
    return post_chat(
        body,
        persona_repository=LocalPersonaRepository(ROOT / "personas"),
        prompt_builder=PersonaPromptBuilder(),
        model_router=model_router,
        session_store=session_store,
        rag_service=rag_service,
        request_id=request_id,
    )


class ContinuousSessionV1Tests(unittest.TestCase):
    def test_create_session(self) -> None:
        store = InMemorySessionStore()

        response = post_session(
            create_session_body(),
            session_store=store,
            request_id="req-session",
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["request_id"], "req-session")
        self.assertEqual(response["data"]["status"], "active")
        self.assertTrue(response["data"]["session_id"].startswith("sess-"))

    def test_two_turn_chat_reads_first_turn_history(self) -> None:
        store = InMemorySessionStore()
        router = RecordingModelRouter()
        session_id = post_session(
            create_session_body(),
            session_store=store,
            request_id="req-session",
        )["data"]["session_id"]

        first = call_chat(
            chat_body(session_id=session_id, message="第一轮"),
            session_store=store,
            model_router=router,
            request_id="req-chat-1",
        )
        second = call_chat(
            chat_body(session_id=session_id, message="第二轮"),
            session_store=store,
            model_router=router,
            request_id="req-chat-2",
        )

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["data"]["session_id"], session_id)

        second_prompt = router.calls[1]

        self.assertEqual(
            [(message.role, message.content) for message in second_prompt[-3:]],
            [
                ("user", "第一轮"),
                ("assistant", "recorded: 第一轮"),
                ("user", "第二轮"),
            ],
        )
        self.assertEqual(len(store.recent_messages(session_id, limit=10)), 4)

    def test_rag_query_uses_recent_dialogue_and_roleplay_scope(self) -> None:
        store = InMemorySessionStore()
        router = RecordingModelRouter()
        rag = RecordingRagService()
        session_id = post_session(
            create_session_body(),
            session_store=store,
            request_id="req-session",
        )["data"]["session_id"]
        call_chat(
            chat_body(session_id=session_id, message="我不想参加普通活动"),
            session_store=store,
            model_router=router,
            request_id="req-chat-1",
        )

        response = call_chat(
            chat_body(
                session_id=session_id,
                message="那你会安排什么？",
                rag=True,
            ),
            session_store=store,
            model_router=router,
            rag_service=rag,
            request_id="req-chat-2",
        )

        self.assertTrue(response["ok"])
        self.assertEqual(len(rag.calls), 2)
        query = rag.calls[0].query
        self.assertEqual(rag.calls[1].query, query)
        self.assertEqual(str(rag.calls[0].characterId), "haruhi")
        self.assertEqual(str(rag.calls[1].characterId), "kyon")
        self.assertIn("目标角色：haruhi", query)
        self.assertIn("角色模式：mid_late_haruhi", query)
        self.assertIn("当前时间线：mid_late", query)
        self.assertIn("user: 我不想参加普通活动", query)
        self.assertIn("assistant: recorded: 我不想参加普通活动", query)
        self.assertTrue(query.endswith("当前用户输入：\n那你会安排什么？"))

    def test_session_is_isolated_by_user(self) -> None:
        store = InMemorySessionStore()
        router = RecordingModelRouter()
        session_id = post_session(
            create_session_body(user_id="user-1"),
            session_store=store,
            request_id="req-session",
        )["data"]["session_id"]

        response = call_chat(
            chat_body(session_id=session_id, message="越权读取", user_id="user-2"),
            session_store=store,
            model_router=router,
            request_id="req-cross-user",
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "SESSION_NOT_FOUND")
        self.assertEqual(router.calls, [])

    def test_missing_session_returns_error_envelope(self) -> None:
        response = call_chat(
            chat_body(session_id="sess-missing", message="继续"),
            session_store=InMemorySessionStore(),
            model_router=RecordingModelRouter(),
            request_id="req-missing",
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["request_id"], "req-missing")
        self.assertEqual(response["error"]["code"], "SESSION_NOT_FOUND")

    def test_continuous_session_false_does_not_read_history(self) -> None:
        response = call_chat(
            chat_body(
                session_id="sess-existing",
                message="单轮请求",
                continuous_session=False,
            ),
            session_store=ExplodingSessionStore(),
            model_router=RecordingModelRouter(),
            request_id="req-no-session",
        )

        self.assertTrue(response["ok"])
        self.assertIsNone(response["data"]["session_id"])


if __name__ == "__main__":
    unittest.main()
