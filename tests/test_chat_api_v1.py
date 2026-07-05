from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import (  # noqa: E402
    FakeModelProvider,
    LocalPersonaRepository,
)
from haruhi_roleplay_api.api.chat import post_chat  # noqa: E402
from haruhi_roleplay_api.application import (  # noqa: E402
    ModelAliasRoute,
    ModelProviderRegistryRouter,
    PersonaPromptBuilder,
)


ROOT = Path(__file__).resolve().parents[1]


def minimal_chat_body() -> dict:
    return {
        "app_id": "web",
        "user_id": "user-1",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "message": "今天有什么计划？",
        "language": "zh-CN",
        "capabilities": {
            "rag": False,
            "memory": False,
            "continuous_session": False,
            "safety_filter": True,
            "debug_trace": True,
            "stream": False,
        },
        "generation": {
            "model": "fake-roleplay-model",
            "style_intensity": 0.75,
            "allow_narration": True,
        },
    }


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


def call_chat(body: dict, request_id: str = "req-chat") -> dict:
    return post_chat(
        body,
        persona_repository=LocalPersonaRepository(ROOT / "personas"),
        prompt_builder=PersonaPromptBuilder(),
        model_router=fake_model_router(),
        request_id=request_id,
    )


class ChatApiV1Tests(unittest.TestCase):
    def test_valid_chat_request_returns_reply(self) -> None:
        response = call_chat(minimal_chat_body(), request_id="req-chat-1")

        self.assertTrue(response["ok"])
        self.assertEqual(response["request_id"], "req-chat-1")

        data = response["data"]
        self.assertEqual(data["request_id"], "req-chat-1")
        self.assertEqual(data["character_id"], "haruhi")
        self.assertEqual(data["persona_mode"], "mid_late_haruhi")
        self.assertEqual(data["reply"], "[fake:fake-roleplay-model] 今天有什么计划？")
        self.assertEqual(data["usage"]["provider"], "fake")
        self.assertEqual(data["usage"]["model"], "fake-roleplay-model")
        self.assertEqual(data["debug"]["modelProvider"], "fake")

    def test_disabled_capabilities_do_not_enable_session_rag_or_memory(self) -> None:
        response = call_chat(minimal_chat_body())
        data = response["data"]

        self.assertIsNone(data["session_id"])
        self.assertEqual(data["rag"], {"enabled": False})
        self.assertEqual(data["memory"], {"enabled": False})

    def test_body_request_id_is_used_for_envelope_and_data(self) -> None:
        body = minimal_chat_body()
        body["request_id"] = "req-from-body"

        response = call_chat(body, request_id="req-from-header")

        self.assertEqual(response["request_id"], "req-from-body")
        self.assertEqual(response["data"]["request_id"], "req-from-body")

    def test_invalid_character_returns_error_envelope(self) -> None:
        body = minimal_chat_body()
        body["character_id"] = "missing_character"

        response = call_chat(body, request_id="req-missing-character")

        self.assertFalse(response["ok"])
        self.assertEqual(response["request_id"], "req-missing-character")
        self.assertEqual(response["error"]["code"], "PERSONA_NOT_FOUND")

    def test_invalid_persona_preset_returns_error_envelope(self) -> None:
        body = minimal_chat_body()
        body["persona_mode"] = "missing_mode"

        response = call_chat(body, request_id="req-missing-mode")

        self.assertFalse(response["ok"])
        self.assertEqual(response["request_id"], "req-missing-mode")
        self.assertEqual(response["error"]["code"], "PERSONA_MODE_NOT_FOUND")

    def test_unsupported_capability_returns_validation_error(self) -> None:
        body = minimal_chat_body()
        body["capabilities"]["rag"] = True

        response = call_chat(body, request_id="req-rag")

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
