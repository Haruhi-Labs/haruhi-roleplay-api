from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import (  # noqa: E402
    FakeModelProvider,
    FakeRagService,
    InMemoryMemoryStore,
    InMemorySessionStore,
    LocalPersonaRepository,
)
from haruhi_roleplay_api.api.chat import post_chat  # noqa: E402
from haruhi_roleplay_api.application import (  # noqa: E402
    ModelAliasRoute,
    ModelProviderRegistryRouter,
    PersonaPromptBuilder,
)
from haruhi_roleplay_api.application.errors import AppError, ErrorCode  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    ChatInput,
    PersonaModeId,
    UserId,
)
from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    build_agent_context_planner_from_env,
)


ROOT = Path(__file__).resolve().parents[1]


def fake_model_router() -> ModelProviderRegistryRouter:
    return ModelProviderRegistryRouter(
        providers={"fake": FakeModelProvider()},
        aliases={
            "fake-roleplay-model": ModelAliasRoute(
                alias="fake-roleplay-model",
                provider_id="fake",
                provider_model="fake-roleplay-model",
            )
        },
        default_alias="fake-roleplay-model",
    )


def chat_body(
    *,
    rag: bool = False,
    memory: bool = False,
    continuous_session: bool = False,
    session_id: str | None = None,
) -> dict:
    return {
        "app_id": "web",
        "user_id": "user-1",
        "session_id": session_id,
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "message": "社团 活动 怎么安排？ secret-token http://internal",
        "language": "zh-CN",
        "capabilities": {
            "rag": rag,
            "memory": memory,
            "continuous_session": continuous_session,
            "safety_filter": True,
            "debug_trace": True,
            "stream": False,
        },
        "generation": {"model": "fake-roleplay-model"},
    }


def call_chat(
    body: dict,
    *,
    session_store: InMemorySessionStore | None = None,
    memory_store: InMemoryMemoryStore | None = None,
    rag_service: FakeRagService | None = None,
) -> dict:
    return post_chat(
        body,
        persona_repository=LocalPersonaRepository(ROOT / "personas"),
        prompt_builder=PersonaPromptBuilder(),
        model_router=fake_model_router(),
        session_store=session_store,
        memory_store=memory_store,
        rag_service=rag_service,
        request_id="req-agent-plan",
        debug_trace_enabled=True,
    )


class AgentContextPlanTests(unittest.TestCase):
    def test_default_plan_disables_optional_context_reads(self) -> None:
        response = call_chat(chat_body())

        self.assertTrue(response["ok"])
        plan = response["data"]["debug"]["contextPlan"]
        serialized_plan = str(plan)

        self.assertEqual(plan["planner"], "deterministic")
        self.assertEqual(plan["status"], "ready")
        self.assertFalse(plan["readSession"])
        self.assertFalse(plan["readMemory"])
        self.assertFalse(plan["retrieveRag"])
        self.assertEqual(plan["backendFetches"], [])
        self.assertNotIn("社团 活动", serialized_plan)
        self.assertNotIn("secret-token", serialized_plan)
        self.assertNotIn("http://internal", serialized_plan)

    def test_rag_plan_enables_rag_retrieve(self) -> None:
        response = call_chat(chat_body(rag=True), rag_service=FakeRagService())

        self.assertTrue(response["ok"])
        debug = response["data"]["debug"]

        self.assertTrue(debug["contextPlan"]["retrieveRag"])
        self.assertEqual(debug["ragProvider"], "fake-rag")

    def test_persona_policy_enables_rag_when_client_omits_override(self) -> None:
        body = chat_body()
        body["capabilities"].pop("rag")

        response = call_chat(body, rag_service=FakeRagService())

        self.assertTrue(response["ok"])
        debug = response["data"]["debug"]
        self.assertTrue(debug["contextPlan"]["retrieveRag"])
        self.assertTrue(debug["ragEnabled"])

    def test_persona_default_rag_safely_degrades_without_provider(self) -> None:
        body = chat_body()
        body["capabilities"].pop("rag")

        response = call_chat(body)

        self.assertTrue(response["ok"])
        debug = response["data"]["debug"]
        self.assertFalse(debug["contextPlan"]["retrieveRag"])
        self.assertFalse(debug["ragEnabled"])

    def test_memory_plan_enables_memory_read(self) -> None:
        response = call_chat(
            chat_body(memory=True),
            memory_store=InMemoryMemoryStore(),
        )

        self.assertTrue(response["ok"])
        debug = response["data"]["debug"]

        self.assertTrue(debug["contextPlan"]["readMemory"])
        self.assertTrue(debug["memoryEnabled"])
        self.assertEqual(debug["memoryReadCount"], 0)

    def test_persona_policy_enables_memory_when_client_omits_override(self) -> None:
        body = chat_body()
        body["capabilities"].pop("memory")

        response = call_chat(body, memory_store=InMemoryMemoryStore())

        self.assertTrue(response["ok"])
        debug = response["data"]["debug"]
        self.assertTrue(debug["contextPlan"]["readMemory"])
        self.assertTrue(debug["memoryEnabled"])

    def test_persona_default_memory_safely_degrades_without_store(self) -> None:
        body = chat_body()
        body["capabilities"].pop("memory")

        response = call_chat(body)

        self.assertTrue(response["ok"])
        debug = response["data"]["debug"]
        self.assertFalse(debug["contextPlan"]["readMemory"])
        self.assertFalse(debug["memoryEnabled"])

    def test_session_plan_enables_session_read(self) -> None:
        session_store = InMemorySessionStore()
        session = session_store.create_session(
            app_id=AppId("web"),
            user_id=UserId("user-1"),
            character_id=CharacterId("haruhi"),
            persona_mode=PersonaModeId("mid_late_haruhi"),
        )
        session_store.append_message(
            session_id=session.sessionId,
            role="user",
            content="之前说过的活动安排",
        )

        response = call_chat(
            chat_body(
                continuous_session=True,
                session_id=str(session.sessionId),
            ),
            session_store=session_store,
        )

        self.assertTrue(response["ok"])
        debug = response["data"]["debug"]

        self.assertTrue(debug["contextPlan"]["readSession"])
        self.assertTrue(debug["sessionEnabled"])
        self.assertEqual(debug["sessionReadCount"], 1)

    def test_model_backed_planner_is_configurable_but_not_implemented(self) -> None:
        planner = build_agent_context_planner_from_env(
            {"AGENT_CONTEXT_PLANNER": "model"}
        )
        persona = LocalPersonaRepository(ROOT / "personas").list_presets("haruhi")[0]
        chat_input = ChatInput.from_mapping(
            {
                "requestId": "req-agent-plan",
                "appId": "web",
                "userId": "user-1",
                "characterId": "haruhi",
                "personaMode": "mid_late_haruhi",
                "message": "今天去哪？",
                "language": "zh-CN",
                "capabilities": {
                    "rag": False,
                    "memory": False,
                    "continuousSession": False,
                    "safetyFilter": True,
                    "debugTrace": True,
                    "stream": False,
                },
            }
        )

        with self.assertRaises(AppError) as raised:
            planner.plan(chat_input=chat_input, persona=persona)

        self.assertEqual(raised.exception.code, ErrorCode.MODEL_PROVIDER_ERROR)
        self.assertIn("not implemented", raised.exception.public_message)


if __name__ == "__main__":
    unittest.main()
