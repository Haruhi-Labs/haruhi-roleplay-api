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
from haruhi_roleplay_api.application import ModelRouter, PersonaPromptBuilder  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    GenerationConfig,
    ModelMessage,
    ModelResponse,
    ModelUsage,
)


ROOT = Path(__file__).resolve().parents[1]


class SensitiveDebugRouter:
    def generate(
        self,
        messages: tuple[ModelMessage, ...],
        generation: GenerationConfig | None = None,
    ) -> ModelResponse:
        return ModelResponse(
            reply="安全摘要测试回复",
            provider="sensitive-provider",
            model=generation.model if generation and generation.model else "debug-model",
            usage=ModelUsage(promptTokens=10, completionTokens=4),
            debug={
                "messageCount": len(messages),
                "prompt": "完整 prompt 不应返回",
                "apiKey": "secret-token",
                "connectionString": "postgres://secret",
            },
        )


def chat_body(*, debug_trace: bool) -> dict:
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
            "debug_trace": debug_trace,
            "stream": False,
        },
        "generation": {
            "model": "fake-roleplay-model",
        },
    }


def call_chat(
    body: dict,
    *,
    model_router: object | None = None,
    debug_trace_enabled: bool = True,
) -> dict:
    return post_chat(
        body,
        persona_repository=LocalPersonaRepository(ROOT / "personas"),
        prompt_builder=PersonaPromptBuilder(),
        model_router=model_router or ModelRouter(provider=FakeModelProvider()),
        request_id="req-debug",
        debug_trace_enabled=debug_trace_enabled,
    )


class DebugTraceV1Tests(unittest.TestCase):
    def test_debug_trace_false_returns_no_debug(self) -> None:
        response = call_chat(chat_body(debug_trace=False))

        self.assertTrue(response["ok"])
        self.assertIsNone(response["data"]["debug"])

    def test_debug_trace_true_returns_safe_summary(self) -> None:
        response = call_chat(chat_body(debug_trace=True))

        debug = response["data"]["debug"]

        self.assertEqual(debug["requestId"], "req-debug")
        self.assertEqual(debug["characterId"], "haruhi")
        self.assertEqual(debug["personaMode"], "mid_late_haruhi")
        self.assertEqual(debug["personaSource"], "LocalPersonaRepository")
        self.assertEqual(debug["modelProvider"], "fake")
        self.assertEqual(debug["modelRoute"], "fake-roleplay-model")
        self.assertIsInstance(debug["latencyMs"], int)
        self.assertGreaterEqual(debug["latencyMs"], 0)
        self.assertFalse(debug["ragEnabled"])
        self.assertFalse(debug["memoryEnabled"])
        self.assertFalse(debug["sessionEnabled"])
        self.assertEqual(debug["sessionReadCount"], 0)
        self.assertIn("generate_model", debug["events"])

    def test_debug_trace_can_be_disabled_by_service_config(self) -> None:
        response = call_chat(
            chat_body(debug_trace=True),
            debug_trace_enabled=False,
        )

        self.assertTrue(response["ok"])
        self.assertIsNone(response["data"]["debug"])

    def test_debug_trace_cuts_sensitive_provider_debug(self) -> None:
        response = call_chat(
            chat_body(debug_trace=True),
            model_router=SensitiveDebugRouter(),
        )

        debug = response["data"]["debug"]
        serialized_debug = str(debug)

        self.assertEqual(debug["modelProvider"], "sensitive-provider")
        self.assertGreaterEqual(debug["messageCount"], 1)
        self.assertNotIn("prompt", debug)
        self.assertNotIn("apiKey", debug)
        self.assertNotIn("connectionString", debug)
        self.assertNotIn("完整 prompt 不应返回", serialized_debug)
        self.assertNotIn("secret-token", serialized_debug)

    def test_error_path_logs_request_id_without_user_message(self) -> None:
        body = chat_body(debug_trace=True)
        body["character_id"] = "missing_character"
        body["message"] = "不要出现在日志"

        with self.assertLogs("haruhi_roleplay_api.api.chat", level="INFO") as logs:
            response = call_chat(body)

        log_text = "\n".join(logs.output)

        self.assertFalse(response["ok"])
        self.assertIn("request_id=req-debug", log_text)
        self.assertIn("error_code=PERSONA_NOT_FOUND", log_text)
        self.assertNotIn("不要出现在日志", log_text)


if __name__ == "__main__":
    unittest.main()
