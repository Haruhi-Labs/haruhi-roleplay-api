from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import FakeRagService, LocalPersonaRepository  # noqa: E402
from haruhi_roleplay_api.api.chat import post_chat  # noqa: E402
from haruhi_roleplay_api.application import PersonaPromptBuilder  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    GenerationConfig,
    ModelMessage,
    ModelResponse,
    ModelUsage,
)
from haruhi_roleplay_api.domain.request_limits import (  # noqa: E402
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_GENERATION_TOKENS,
    MAX_RAG_QUERY_LENGTH,
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
            reply="recorded rag reply",
            provider="recording",
            model=generation.model if generation and generation.model else "recording",
            usage=ModelUsage(promptTokens=1, completionTokens=1),
            debug={"modelProvider": "recording"},
        )


class ExplodingRagService:
    def retrieve(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("rag service should not be called")


class RecordingRagService:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def retrieve(self, retrieve_input: object):
        self.calls.append(retrieve_input)
        return FakeRagService().retrieve(retrieve_input)


def chat_body(
    *,
    rag: bool,
    character_id: str = "haruhi",
    persona_mode: str = "mid_late_haruhi",
    message: str = "今天有什么资料？",
) -> dict:
    return {
        "app_id": "web",
        "user_id": "user-1",
        "character_id": character_id,
        "persona_mode": persona_mode,
        "message": message,
        "language": "zh-CN",
        "capabilities": {
            "rag": rag,
            "memory": False,
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
    rag_service: object | None,
    request_id: str = "req-rag-chat",
) -> dict:
    return post_chat(
        body,
        persona_repository=LocalPersonaRepository(ROOT / "personas"),
        prompt_builder=PersonaPromptBuilder(),
        model_router=model_router,
        rag_service=rag_service,
        request_id=request_id,
    )


class FakeRagRetrieveTests(unittest.TestCase):
    def test_invalid_resource_limits_do_not_call_model_provider(self) -> None:
        for field_name in ("message", "max_tokens"):
            with self.subTest(field_name=field_name):
                body = chat_body(rag=False)
                if field_name == "message":
                    body["message"] = "x" * (MAX_CHAT_MESSAGE_LENGTH + 1)
                else:
                    body["generation"]["max_tokens"] = (
                        MAX_GENERATION_TOKENS + 1
                    )
                router = RecordingModelRouter()

                response = call_chat(
                    body,
                    model_router=router,
                    rag_service=None,
                )

                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
                self.assertEqual(router.calls, [])

    def test_rag_false_does_not_call_rag_service(self) -> None:
        router = RecordingModelRouter()

        response = call_chat(
            chat_body(rag=False),
            model_router=router,
            rag_service=ExplodingRagService(),
        )

        prompt_text = "\n".join(message.content for message in router.calls[0])

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["rag"], {"enabled": False})
        self.assertNotIn("检索资料摘要", prompt_text)

    def test_rag_true_adds_chunks_to_prompt_and_sources(self) -> None:
        router = RecordingModelRouter()

        response = call_chat(
            chat_body(rag=True),
            model_router=router,
            rag_service=FakeRagService(),
        )

        rag = response["data"]["rag"]
        prompt_text = "\n".join(message.content for message in router.calls[0])

        self.assertTrue(response["ok"])
        self.assertTrue(rag["enabled"])
        self.assertEqual(rag["provider"], "fake-rag")
        self.assertEqual(rag["hit_count"], 2)
        self.assertIn("检索资料摘要", prompt_text)
        self.assertIn("中后期的春日仍然主动推动社团活动", prompt_text)
        self.assertEqual(rag["sources"][0]["document_id"], "doc-haruhi-timeline")
        self.assertEqual(rag["sources"][0]["chunk_id"], "chunk-haruhi-mid-late-1")

    def test_long_current_message_is_bounded_for_retrieval(self) -> None:
        router = RecordingModelRouter()
        rag = RecordingRagService()
        message = "开头主题" + "很长" * 3000 + "结尾问题"

        response = call_chat(
            chat_body(rag=True, message=message),
            model_router=router,
            rag_service=rag,
        )

        self.assertTrue(response["ok"])
        query = rag.calls[0].query
        self.assertLessEqual(len(query), MAX_RAG_QUERY_LENGTH)
        self.assertIn("开头主题", query)
        self.assertIn("……[中间省略]……", query)
        self.assertTrue(query.endswith("结尾问题"))

    def test_rag_filter_keeps_character_isolated(self) -> None:
        router = RecordingModelRouter()

        response = call_chat(
            chat_body(
                rag=True,
                character_id="kyon",
                persona_mode="default_kyon",
            ),
            model_router=router,
            rag_service=FakeRagService(),
        )

        sources = response["data"]["rag"]["sources"]
        prompt_text = "\n".join(message.content for message in router.calls[0])

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["character_id"], "kyon")
        self.assertIn("阿虚通常以吐槽和常识视角回应异常事件", prompt_text)
        self.assertNotIn("中后期的春日", prompt_text)

    def test_rag_true_requires_rag_service(self) -> None:
        response = call_chat(
            chat_body(rag=True),
            model_router=RecordingModelRouter(),
            rag_service=None,
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(response["error"]["message"], "ragService is required for RAG")


if __name__ == "__main__":
    unittest.main()
