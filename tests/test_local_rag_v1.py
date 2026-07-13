from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import LocalPersonaRepository, LocalRagService  # noqa: E402
from haruhi_roleplay_api.api.chat import post_chat  # noqa: E402
from haruhi_roleplay_api.api.rag import post_rag_document  # noqa: E402
from haruhi_roleplay_api.application import PersonaPromptBuilder  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    GenerationConfig,
    ModelMessage,
    ModelResponse,
    ModelUsage,
    PersonaModeId,
    RagRetrieveFilters,
    RagRetrieveInput,
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
            reply="local rag reply",
            provider="recording",
            model=generation.model if generation and generation.model else "recording",
            usage=ModelUsage(promptTokens=1, completionTokens=1),
            debug={"modelProvider": "recording"},
        )


def rag_document_body(
    *,
    app_id: str = "web",
    document_id: str = "doc-local-haruhi",
    character_id: str = "haruhi",
    persona_mode: str = "mid_late_haruhi",
    content: str | None = None,
) -> dict:
    return {
        "app_id": app_id,
        "document_id": document_id,
        "title": "本地社团活动资料",
        "source_type": "timeline",
        "character_id": character_id,
        "persona_mode": persona_mode,
        "timeline": "mid_late",
        "spoiler_level": 2,
        "language": "zh-CN",
        "content": content
        or (
            "社团 活动 计划：春日会主动安排调查和招募。"
            "\n长期互动中，她会更注意维持 SOS 团成员之间的关系。"
        ),
    }


def chat_body(
    *,
    character_id: str = "haruhi",
    persona_mode: str = "mid_late_haruhi",
    message: str = "社团 活动 怎么安排？",
) -> dict:
    return {
        "app_id": "web",
        "user_id": "user-1",
        "character_id": character_id,
        "persona_mode": persona_mode,
        "message": message,
        "language": "zh-CN",
        "capabilities": {
            "rag": True,
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


def ingest_document(service: LocalRagService, body: dict | None = None) -> dict:
    return post_rag_document(
        body or rag_document_body(),
        persona_repository=LocalPersonaRepository(ROOT / "personas"),
        rag_ingest_service=service,
        request_id="req-local-rag-ingest",
    )


def retrieve_local(
    service: LocalRagService,
    *,
    app_id: str = "web",
    character_id: str = "haruhi",
):
    return service.retrieve(
        RagRetrieveInput(
            appId=AppId(app_id),
            userId=UserId("user-1"),
            characterId=CharacterId(character_id),
            personaMode=PersonaModeId("mid_late_haruhi"),
            query="社团 活动",
            topK=5,
            filters=RagRetrieveFilters(
                sourceTypes=("timeline",),
                timelines=("mid_late",),
                spoilerLevelMax=2,
                language="zh-CN",
            ),
        )
    )


class LocalRagV1Tests(unittest.TestCase):
    def test_import_document_chunks_and_preserves_metadata(self) -> None:
        service = LocalRagService(chunk_size=24)

        response = ingest_document(service)

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["status"], "imported")
        self.assertGreaterEqual(response["data"]["chunk_count"], 2)
        self.assertEqual(response["data"]["metadata"]["app_id"], "web")
        self.assertEqual(response["data"]["metadata"]["character_id"], "haruhi")

        retrieve_output = retrieve_local(service)

        self.assertGreaterEqual(len(retrieve_output.chunks), 1)
        self.assertEqual(retrieve_output.provider, "local-rag")
        self.assertEqual(retrieve_output.chunks[0].documentId, "doc-local-haruhi")
        self.assertEqual(
            retrieve_output.chunks[0].metadata.extra["title"],
            "本地社团活动资料",
        )

    def test_retrieve_filter_keeps_character_isolated(self) -> None:
        service = LocalRagService()
        ingest_document(service)

        output = retrieve_local(service, character_id="kyon")

        self.assertGreaterEqual(output.rawHitCount, 1)
        self.assertEqual(output.filteredHitCount, 0)
        self.assertEqual(output.chunks, ())

    def test_retrieve_filter_keeps_apps_isolated(self) -> None:
        service = LocalRagService()
        ingest_document(service, rag_document_body(app_id="app-a"))

        same_app = retrieve_local(service, app_id="app-a")
        other_app = retrieve_local(service, app_id="app-b")

        self.assertGreaterEqual(len(same_app.chunks), 1)
        self.assertTrue(
            all(chunk.metadata.appId == "app-a" for chunk in same_app.chunks)
        )
        self.assertEqual(other_app.filteredHitCount, 0)
        self.assertEqual(other_app.chunks, ())

    def test_chat_uses_local_rag_sources(self) -> None:
        service = LocalRagService()
        router = RecordingModelRouter()
        ingest_document(service)

        response = post_chat(
            chat_body(),
            persona_repository=LocalPersonaRepository(ROOT / "personas"),
            prompt_builder=PersonaPromptBuilder(),
            model_router=router,
            rag_service=service,
            request_id="req-local-rag-chat",
        )

        rag = response["data"]["rag"]
        prompt_text = "\n".join(message.content for message in router.calls[0])

        self.assertTrue(response["ok"])
        self.assertTrue(rag["enabled"])
        self.assertEqual(rag["provider"], "local-rag")
        self.assertEqual(rag["sources"][0]["document_id"], "doc-local-haruhi")
        self.assertIn("检索资料摘要", prompt_text)
        self.assertIn("社团 活动 计划", prompt_text)

    def test_chat_rag_does_not_leak_other_character_document(self) -> None:
        service = LocalRagService()
        router = RecordingModelRouter()
        ingest_document(service)

        response = post_chat(
            chat_body(
                character_id="kyon",
                persona_mode="default_kyon",
                message="社团 活动 怎么看？",
            ),
            persona_repository=LocalPersonaRepository(ROOT / "personas"),
            prompt_builder=PersonaPromptBuilder(),
            model_router=router,
            rag_service=service,
            request_id="req-local-rag-kyon",
        )

        rag = response["data"]["rag"]
        prompt_text = "\n".join(message.content for message in router.calls[0])

        self.assertTrue(response["ok"])
        self.assertTrue(rag["enabled"])
        self.assertEqual(rag["sources"], [])
        self.assertNotIn("社团 活动 计划", prompt_text)


if __name__ == "__main__":
    unittest.main()
