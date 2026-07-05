from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import InMemorySessionStore, LocalPersonaRepository  # noqa: E402
from haruhi_roleplay_api.api.chat import post_chat_stream  # noqa: E402
from haruhi_roleplay_api.api.sessions import post_session  # noqa: E402
from haruhi_roleplay_api.application import PersonaPromptBuilder  # noqa: E402
from haruhi_roleplay_api.application.errors import AppError, ErrorCode  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    GenerationConfig,
    ModelMessage,
    ModelResponse,
    ModelStreamEvent,
    ModelUsage,
)


ROOT = Path(__file__).resolve().parents[1]


class StreamingRouter:
    def __init__(self, reply: str = "流式回复") -> None:
        self.reply = reply
        self.calls: list[tuple[ModelMessage, ...]] = []

    def stream(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ):
        self.calls.append(messages)
        yield ModelStreamEvent(event="delta", delta=self.reply[:2])
        yield ModelStreamEvent(event="delta", delta=self.reply[2:])
        yield ModelStreamEvent(
            event="done",
            response=ModelResponse(
                reply=self.reply,
                provider="streaming",
                model=(
                    generation.model
                    if generation and generation.model
                    else "streaming-model"
                ),
                usage=ModelUsage(promptTokens=3, completionTokens=2),
                debug={"modelProvider": "streaming"},
            ),
        )


class FailingStreamingRouter:
    def stream(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ):
        yield ModelStreamEvent(event="delta", delta="半句")
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message="stream provider failed",
        )


def stream_body(
    *,
    session_id: str | None = None,
    continuous_session: bool = False,
) -> dict:
    return {
        "app_id": "web",
        "user_id": "user-1",
        "session_id": session_id,
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "message": "今天有什么计划？",
        "language": "zh-CN",
        "capabilities": {
            "rag": False,
            "memory": False,
            "continuous_session": continuous_session,
            "safety_filter": True,
            "debug_trace": True,
            "stream": True,
        },
        "generation": {
            "model": "streaming-model",
        },
    }


def call_stream(
    body: dict,
    *,
    model_router: object,
    session_store: object | None = None,
) -> dict:
    return post_chat_stream(
        body,
        persona_repository=LocalPersonaRepository(ROOT / "personas"),
        prompt_builder=PersonaPromptBuilder(),
        model_router=model_router,
        session_store=session_store,
        request_id="req-stream",
    )


class StreamChatTests(unittest.TestCase):
    def test_stream_chat_returns_start_delta_usage_and_done_events(self) -> None:
        response = call_stream(stream_body(), model_router=StreamingRouter())

        self.assertTrue(response["ok"])
        events = response["data"]["events"]
        event_names = [event["event"] for event in events]

        self.assertEqual(event_names, ["start", "delta", "delta", "usage", "done"])
        self.assertEqual(events[0]["data"]["request_id"], "req-stream")
        self.assertEqual(events[1]["data"]["text"] + events[2]["data"]["text"], "流式回复")
        self.assertEqual(events[3]["data"]["provider"], "streaming")
        self.assertEqual(events[-1]["data"]["reply"], "流式回复")
        self.assertTrue(events[-1]["data"]["debug"]["streamEnabled"])

    def test_stream_provider_failure_returns_error_event(self) -> None:
        response = call_stream(stream_body(), model_router=FailingStreamingRouter())

        self.assertTrue(response["ok"])
        events = response["data"]["events"]

        self.assertEqual([event["event"] for event in events], ["start", "delta", "error"])
        self.assertEqual(
            events[-1]["data"]["error"]["code"],
            "MODEL_PROVIDER_ERROR",
        )

    def test_stream_chat_writes_complete_session_messages(self) -> None:
        store = InMemorySessionStore()
        session_id = post_session(
            {
                "app_id": "web",
                "user_id": "user-1",
                "character_id": "haruhi",
                "persona_mode": "mid_late_haruhi",
            },
            session_store=store,
            request_id="req-session",
        )["data"]["session_id"]

        response = call_stream(
            stream_body(session_id=session_id, continuous_session=True),
            model_router=StreamingRouter(reply="完整保存回复"),
            session_store=store,
        )

        messages = store.recent_messages(session_id, limit=10)

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["events"][0]["data"]["session_id"], session_id)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].content, "今天有什么计划？")
        self.assertEqual(messages[1].content, "完整保存回复")


if __name__ == "__main__":
    unittest.main()
