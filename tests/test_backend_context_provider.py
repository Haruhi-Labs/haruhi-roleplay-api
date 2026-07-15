from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import (  # noqa: E402
    FakeBackendContextProvider,
    LocalPersonaRepository,
)
from haruhi_roleplay_api.api.chat import post_chat  # noqa: E402
from haruhi_roleplay_api.application import (  # noqa: E402
    DeterministicAgentContextPlanner,
    PersonaPromptBuilder,
)
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    BackendContextFact,
    BackendContextRequest,
    CharacterId,
    DTOValidationError,
    GenerationConfig,
    ModelMessage,
    ModelResponse,
    ModelUsage,
    PersonaModeId,
    UserId,
)
from haruhi_roleplay_api.infrastructure import RoleplayHttpRuntime  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


class CapturingRouter:
    def __init__(self) -> None:
        self.messages: tuple[ModelMessage, ...] = ()

    def generate(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ) -> ModelResponse:
        self.messages = messages
        return ModelResponse(
            reply="captured",
            provider="capture",
            model="capture-model",
            usage=ModelUsage(promptTokens=len(messages), completionTokens=1),
        )


class CountingBackendContextProvider:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(
        self,
        request: BackendContextRequest,
    ) -> tuple[BackendContextFact, ...]:
        self.calls += 1
        return ()


def chat_body() -> dict:
    return {
        "app_id": "web",
        "user_id": "user-1",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "message": "社团活动怎么安排？",
        "language": "zh-CN",
        "capabilities": {
            "rag": False,
            "memory": False,
            "continuous_session": False,
            "safety_filter": True,
            "debug_trace": True,
            "stream": False,
        },
        "generation": {"model": "capture-model"},
    }


def post_backend_context_chat(
    *,
    model_router: object,
    backend_context_provider: object | None = None,
    backend_context_sources: tuple[str, ...] = (),
) -> dict:
    return post_chat(
        chat_body(),
        persona_repository=LocalPersonaRepository(ROOT / "personas"),
        prompt_builder=PersonaPromptBuilder(),
        model_router=model_router,
        backend_context_provider=backend_context_provider,
        agent_context_planner=DeterministicAgentContextPlanner(
            backend_context_sources=backend_context_sources
        ),
        request_id="req-backend-context",
        debug_trace_enabled=True,
    )


def json_body(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def json_response(body: bytes) -> dict:
    return json.loads(body.decode("utf-8"))


class BackendContextProviderTests(unittest.TestCase):
    def test_disabled_backend_context_does_not_call_provider(self) -> None:
        provider = CountingBackendContextProvider()
        response = post_backend_context_chat(
            model_router=CapturingRouter(),
            backend_context_provider=provider,
        )

        self.assertTrue(response["ok"])
        self.assertEqual(provider.calls, 0)
        self.assertEqual(
            response["data"]["debug"]["contextPlan"]["backendFetches"],
            [],
        )

    def test_fake_backend_facts_enter_prompt(self) -> None:
        router = CapturingRouter()
        response = post_backend_context_chat(
            model_router=router,
            backend_context_provider=FakeBackendContextProvider(),
            backend_context_sources=("user_profile", "game_state"),
        )
        prompt_text = "\n".join(message.content for message in router.messages)

        self.assertTrue(response["ok"])
        self.assertIn("当前可用的会话背景", prompt_text)
        self.assertNotIn("source=user_profile", prompt_text)
        self.assertNotIn("source=game_state", prompt_text)
        self.assertNotIn("confidence=", prompt_text)
        self.assertNotIn("ttl=", prompt_text)
        self.assertIn("用户偏好轻快推进对话", prompt_text)
        self.assertIn("当前活动进度", prompt_text)

    def test_backend_context_debug_only_returns_count_and_sources(self) -> None:
        response = post_backend_context_chat(
            model_router=CapturingRouter(),
            backend_context_provider=FakeBackendContextProvider(),
            backend_context_sources=("user_profile", "game_state"),
        )
        debug = response["data"]["debug"]
        serialized_debug = str(debug)

        self.assertEqual(debug["backendContextFactCount"], 2)
        self.assertEqual(
            debug["backendContextSources"],
            ["user_profile", "game_state"],
        )
        self.assertNotIn("用户偏好轻快推进对话", serialized_debug)
        self.assertNotIn("当前活动进度", serialized_debug)

    def test_fake_provider_rejects_source_outside_whitelist(self) -> None:
        provider = FakeBackendContextProvider(allowed_sources=("user_profile",))

        with self.assertRaises(DTOValidationError):
            provider.fetch(
                BackendContextRequest(
                    appId=AppId("web"),
                    userId=UserId("user-1"),
                    characterId=CharacterId("haruhi"),
                    personaMode=PersonaModeId("mid_late_haruhi"),
                    sources=("game_state",),
                )
            )

    def test_http_runtime_wires_fake_backend_context_provider(self) -> None:
        app = RoleplayHttpRuntime.local(
            project_root=ROOT,
            env={
                "MODEL_PROVIDER": "fake",
                "MODEL_NAME": "fake-roleplay-model",
                "BACKEND_CONTEXT_PROVIDER": "fake",
                "BACKEND_CONTEXT_SOURCES": "user_profile",
            },
        )
        body = chat_body()
        body["generation"] = {"model": "fake-roleplay-model"}

        response = app.handle(
            method="POST",
            target="/v1/chat",
            headers={"content-type": "application/json"},
            body=json_body(body),
        )
        data = json_response(response.body)["data"]

        self.assertEqual(response.status, 200)
        self.assertEqual(data["debug"]["backendContextFactCount"], 1)
        self.assertEqual(data["debug"]["backendContextSources"], ["user_profile"])


if __name__ == "__main__":
    unittest.main()
