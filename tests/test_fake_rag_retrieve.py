from __future__ import annotations

import sys
import unittest
from pathlib import Path
from threading import Event, Lock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import FakeRagService, LocalPersonaRepository  # noqa: E402
from haruhi_roleplay_api.api.chat import post_chat  # noqa: E402
from haruhi_roleplay_api.application import PersonaPromptBuilder  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    GenerationConfig,
    ModelMessage,
    ModelResponse,
    ModelUsage,
    PersonaModeId,
    RagChunk,
    RagChunkId,
    RagDocumentId,
    RagDocumentMetadata,
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
    def __init__(self, chunks: tuple[RagChunk, ...] | None = None) -> None:
        self.calls: list[object] = []
        self.service = FakeRagService(chunks)

    def retrieve(self, retrieve_input: object):
        self.calls.append(retrieve_input)
        return self.service.retrieve(retrieve_input)


class ParallelRagService(RecordingRagService):
    def __init__(self) -> None:
        super().__init__()
        self._entered = 0
        self._lock = Lock()
        self._both_entered = Event()

    def retrieve(self, retrieve_input: object):
        with self._lock:
            self._entered += 1
            if self._entered == 2:
                self._both_entered.set()
        if not self._both_entered.wait(timeout=1):
            raise AssertionError("目标角色与导演桥段检索没有并行执行")
        return super().retrieve(retrieve_input)


class BatchRecordingRagService(RecordingRagService):
    def retrieve(self, retrieve_input: object):
        raise AssertionError("支持批量检索时不应回退到单条接口")

    def retrieve_many(self, retrieve_inputs: tuple[object, ...]):
        self.calls.extend(retrieve_inputs)
        return tuple(
            self.service.retrieve(retrieve_input)
            for retrieve_input in retrieve_inputs
        )


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
        self.assertNotIn("可借鉴的原作互动素材", prompt_text)

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
        self.assertIn("可借鉴的原作互动素材", prompt_text)
        self.assertIn("中后期的春日仍然主动推动社团活动", prompt_text)
        self.assertEqual(rag["sources"][0]["document_id"], "doc-haruhi-timeline")
        self.assertEqual(rag["sources"][0]["chunk_id"], "chunk-haruhi-mid-late-1")
        self.assertIn("中后期的春日", rag["sources"][0]["content"])

    def test_chat_merges_actor_examples_and_director_bridges(self) -> None:
        router = RecordingModelRouter()
        rag_service = RecordingRagService(
            (
                _rag_chunk(
                    "actor",
                    character_id="haruhi",
                    persona_mode="mid_late_haruhi",
                    record_kind="dialogue_example",
                    retrieval_channel="dialogue_style",
                    knowledge_owner="haruhi",
                    usage="style_only",
                    content="【目标角色回答】凉宫春日：那就去找更有趣的事！",
                ),
                _rag_chunk(
                    "director",
                    character_id="kyon",
                    persona_mode=None,
                    record_kind="scene_memory",
                    retrieval_channel="canonical_memory",
                    knowledge_owner="kyon",
                    usage="knowledge",
                    content="阿虚拒绝普通活动后，春日立刻把抱怨改造成全团调查。",
                ),
            )
        )

        response = call_chat(
            chat_body(rag=True, message="普通活动太无聊了"),
            model_router=router,
            rag_service=rag_service,
        )

        self.assertTrue(response["ok"])
        self.assertEqual(len(rag_service.calls), 2)
        calls_by_character = {
            str(call.characterId): call for call in rag_service.calls
        }
        actor_call = calls_by_character["haruhi"]
        director_call = calls_by_character["kyon"]
        self.assertEqual(str(actor_call.characterId), "haruhi")
        self.assertEqual(actor_call.filters.recordKinds, ())
        self.assertEqual(str(director_call.characterId), "kyon")
        self.assertEqual(director_call.filters.recordKinds, ("scene_memory",))
        self.assertEqual(
            director_call.filters.retrievalChannels,
            ("canonical_memory",),
        )
        self.assertEqual(
            [source["character_id"] for source in response["data"]["rag"]["sources"]],
            ["haruhi", "kyon"],
        )
        prompt_text = "\n".join(message.content for message in router.calls[0])
        self.assertIn("那就去找更有趣的事", prompt_text)
        self.assertIn("春日立刻把抱怨改造成全团调查", prompt_text)

    def test_actor_and_director_retrievals_run_in_parallel(self) -> None:
        response = call_chat(
            chat_body(rag=True),
            model_router=RecordingModelRouter(),
            rag_service=ParallelRagService(),
        )

        self.assertTrue(response["ok"])

    def test_chat_uses_batch_retrieval_when_provider_supports_it(self) -> None:
        rag_service = BatchRecordingRagService()

        response = call_chat(
            chat_body(rag=True),
            model_router=RecordingModelRouter(),
            rag_service=rag_service,
        )

        self.assertTrue(response["ok"])
        self.assertEqual(len(rag_service.calls), 2)

    def test_low_relevance_results_do_not_enter_model_prompt(self) -> None:
        router = RecordingModelRouter()
        rag_service = RecordingRagService(
            (
                _rag_chunk(
                    "low-actor",
                    character_id="haruhi",
                    persona_mode="mid_late_haruhi",
                    record_kind="dialogue_example",
                    retrieval_channel="dialogue_style",
                    knowledge_owner="haruhi",
                    usage="style_only",
                    content="完全不相干的应对片段",
                    score=0.9,
                    retrieval_relevance=0.05,
                ),
                _rag_chunk(
                    "low-director",
                    character_id="kyon",
                    persona_mode=None,
                    record_kind="scene_memory",
                    retrieval_channel="canonical_memory",
                    knowledge_owner="kyon",
                    usage="knowledge",
                    content="完全不相干的桥段",
                    score=0.9,
                    retrieval_relevance=0.05,
                ),
            )
        )

        response = call_chat(
            chat_body(rag=True, message="我们聊点别的吧"),
            model_router=router,
            rag_service=rag_service,
        )

        self.assertTrue(response["ok"])
        self.assertTrue(response["data"]["rag"]["enabled"])
        self.assertEqual(response["data"]["rag"]["hit_count"], 0)
        prompt_text = "\n".join(message.content for message in router.calls[0])
        self.assertNotIn("可借鉴的原作互动素材", prompt_text)
        self.assertNotIn("完全不相干", prompt_text)

    def test_director_bridges_never_exceed_two_prompt_slots(self) -> None:
        router = RecordingModelRouter()
        chunks = tuple(
            _rag_chunk(
                f"director-{index}",
                character_id="kyon",
                persona_mode=None,
                record_kind="scene_memory",
                retrieval_channel="canonical_memory",
                knowledge_owner="kyon",
                usage="knowledge",
                content=f"相似桥段 {index}",
            )
            for index in range(3)
        )

        response = call_chat(
            chat_body(rag=True, message="给我一个类似的互动思路"),
            model_router=router,
            rag_service=RecordingRagService(chunks),
        )

        sources = response["data"]["rag"]["sources"]
        self.assertEqual(len(sources), 2)
        self.assertTrue(
            all(source["record_kind"] == "scene_memory" for source in sources)
        )

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


def _rag_chunk(
    name: str,
    *,
    character_id: str,
    persona_mode: str | None,
    record_kind: str,
    retrieval_channel: str,
    knowledge_owner: str,
    usage: str,
    content: str,
    score: float = 0.9,
    retrieval_relevance: float | None = None,
) -> RagChunk:
    extra = {
        "record_kind": record_kind,
        "retrieval_channel": retrieval_channel,
        "knowledge_owner": knowledge_owner,
        "usage": usage,
    }
    if retrieval_relevance is not None:
        extra["_retrieval_relevance"] = retrieval_relevance
    return RagChunk(
        chunkId=RagChunkId(f"chunk-{name}"),
        documentId=RagDocumentId(f"doc-{name}"),
        content=content,
        score=score,
        metadata=RagDocumentMetadata(
            appId=AppId("web"),
            characterId=CharacterId(character_id),
            personaMode=(
                PersonaModeId(persona_mode) if persona_mode is not None else None
            ),
            timeline="mid_late",
            spoilerLevel=2,
            language="zh-CN",
            sourceType="scene",
            extra=extra,
        ),
    )


if __name__ == "__main__":
    unittest.main()
