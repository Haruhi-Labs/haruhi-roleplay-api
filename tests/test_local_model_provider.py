from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import LocalPersonaRepository  # noqa: E402
from haruhi_roleplay_api.api.chat import post_chat  # noqa: E402
from haruhi_roleplay_api.application import PersonaPromptBuilder  # noqa: E402
from haruhi_roleplay_api.application.errors import AppError, ErrorCode  # noqa: E402
from haruhi_roleplay_api.domain import (  # noqa: E402
    GenerationConfig,
    ModelMessage,
    ModelRequest,
)
from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    ModelProviderSettings,
    build_model_router,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class FakeStreamingHTTPResponse:
    def __init__(self, lines: tuple[dict | str, ...]) -> None:
        self._lines = lines

    def __enter__(self) -> "FakeStreamingHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __iter__(self):
        for line in self._lines:
            if line == "[DONE]":
                yield b"data: [DONE]\n\n"
            else:
                yield f"data: {json.dumps(line, ensure_ascii=False)}\n\n".encode(
                    "utf-8"
                )


def model_messages() -> tuple[ModelMessage, ...]:
    return (
        ModelMessage(role="system", content="系统提示"),
        ModelMessage(role="user", content="今天有什么计划？"),
    )


class LocalModelProviderTests(unittest.TestCase):
    def test_config_selects_fake_model_provider(self) -> None:
        router = build_model_router(
            ModelProviderSettings.from_mapping(
                {
                    "MODEL_PROVIDER": "fake",
                    "MODEL_NAME": "fake-roleplay-model",
                }
            )
        )

        response = router.generate(model_messages(), GenerationConfig())

        self.assertEqual(response.provider, "fake")
        self.assertEqual(response.model, "fake-roleplay-model")

    def test_fake_model_provider_streams_deltas_and_done_response(self) -> None:
        router = build_model_router(
            ModelProviderSettings.from_mapping(
                {
                    "MODEL_PROVIDER": "fake",
                    "MODEL_NAME": "fake-roleplay-model",
                }
            )
        )

        events = list(router.stream(model_messages(), GenerationConfig()))

        self.assertEqual(events[-1].event, "done")
        self.assertEqual(events[-1].response.provider, "fake")
        self.assertEqual(
            "".join(event.delta for event in events if event.event == "delta"),
            events[-1].response.reply,
        )

    def test_config_selects_local_openai_compatible_provider(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeHTTPResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "本地模型回复",
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 4,
                    },
                }
            ),
        ) as urlopen:
            router = build_model_router(
                ModelProviderSettings.from_mapping(
                    {
                        "MODEL_PROVIDER": "local",
                        "MODEL_BASE_URL": "http://localhost:11434/v1",
                        "MODEL_NAME": "qwen3:8b",
                        "MODEL_TIMEOUT_MS": "30000",
                    }
                )
            )
            response = router.generate(
                model_messages(),
                GenerationConfig(model="qwen3:8b", temperature=0.2, maxTokens=64),
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(
            request.full_url,
            "http://localhost:11434/v1/chat/completions",
        )
        self.assertEqual(payload["model"], "qwen3:8b")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["max_tokens"], 64)
        self.assertEqual(response.provider, "local-openai-compatible")
        self.assertEqual(response.model, "qwen3:8b")
        self.assertEqual(response.reply, "本地模型回复")
        self.assertEqual(response.usage.promptTokens, 12)
        self.assertEqual(response.usage.completionTokens, 4)

    def test_local_openai_compatible_provider_streams_sse_deltas(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeStreamingHTTPResponse(
                (
                    {"choices": [{"delta": {"content": "本地"}}]},
                    {"choices": [{"delta": {"content": "流式"}}]},
                    {
                        "choices": [{"delta": {}}],
                        "usage": {
                            "prompt_tokens": 9,
                            "completion_tokens": 2,
                        },
                    },
                    "[DONE]",
                )
            ),
        ) as urlopen:
            router = build_model_router(
                ModelProviderSettings.from_mapping(
                    {
                        "MODEL_PROVIDER": "local",
                        "MODEL_BASE_URL": "http://localhost:11434/v1",
                        "MODEL_NAME": "qwen2.5:7b",
                        "MODEL_TIMEOUT_MS": "30000",
                    }
                )
            )
            events = list(
                router.stream(
                    model_messages(),
                    GenerationConfig(model="qwen2.5:7b", maxTokens=64),
                )
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        done = events[-1].response

        self.assertTrue(payload["stream"])
        self.assertEqual(payload["model"], "qwen2.5:7b")
        self.assertEqual(
            "".join(event.delta for event in events if event.event == "delta"),
            "本地流式",
        )
        self.assertEqual(done.reply, "本地流式")
        self.assertEqual(done.usage.promptTokens, 9)
        self.assertEqual(done.usage.completionTokens, 2)

    def test_chat_api_uses_local_model_provider_full_chain(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeHTTPResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "本地 qwen2.5 回复",
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 128,
                        "completion_tokens": 16,
                    },
                }
            ),
        ) as urlopen:
            response = post_chat(
                {
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
                        "model": "qwen2.5:7b",
                        "temperature": 0.3,
                        "max_tokens": 128,
                        "style_intensity": 0.75,
                        "allow_narration": True,
                    },
                },
                persona_repository=LocalPersonaRepository(ROOT / "personas"),
                prompt_builder=PersonaPromptBuilder(),
                model_router=build_model_router(
                    ModelProviderSettings.from_mapping(
                        {
                            "MODEL_PROVIDER": "local",
                            "MODEL_BASE_URL": "http://localhost:11434/v1",
                            "MODEL_NAME": "qwen2.5:7b",
                            "MODEL_TIMEOUT_MS": "30000",
                        }
                    )
                ),
                request_id="req-local-chat",
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        data = response["data"]

        self.assertTrue(response["ok"])
        self.assertEqual(response["request_id"], "req-local-chat")
        self.assertEqual(data["reply"], "本地 qwen2.5 回复")
        self.assertEqual(data["character_id"], "haruhi")
        self.assertEqual(data["persona_mode"], "mid_late_haruhi")
        self.assertEqual(data["usage"]["provider"], "local-openai-compatible")
        self.assertEqual(data["usage"]["model"], "qwen2.5:7b")
        self.assertEqual(data["debug"]["modelProvider"], "local-openai-compatible")
        self.assertEqual(payload["model"], "qwen2.5:7b")
        self.assertEqual(payload["temperature"], 0.3)
        self.assertEqual(payload["max_tokens"], 128)
        self.assertEqual(payload["messages"][-1]["role"], "user")
        self.assertEqual(payload["messages"][-1]["content"], "今天有什么计划？")

    def test_local_provider_failure_maps_to_app_error(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            router = build_model_router(
                ModelProviderSettings.from_mapping(
                    {
                        "MODEL_PROVIDER": "local",
                        "MODEL_BASE_URL": "http://localhost:11434/v1",
                        "MODEL_NAME": "qwen3:8b",
                    }
                )
            )

            with self.assertRaises(AppError) as context:
                router.generate(model_messages(), GenerationConfig(model="qwen3:8b"))

        self.assertEqual(context.exception.code, ErrorCode.MODEL_PROVIDER_ERROR)
        self.assertEqual(
            context.exception.public_message,
            "Local model provider request failed.",
        )

    def test_local_provider_requires_base_url(self) -> None:
        with self.assertRaises(AppError) as context:
            build_model_router(
                ModelProviderSettings.from_mapping(
                    {
                        "MODEL_PROVIDER": "local",
                        "MODEL_NAME": "qwen3:8b",
                    }
                )
            )

        self.assertEqual(context.exception.code, ErrorCode.MODEL_PROVIDER_ERROR)

    def test_invalid_timeout_config_maps_to_app_error(self) -> None:
        with self.assertRaises(AppError) as context:
            ModelProviderSettings.from_mapping(
                {
                    "MODEL_PROVIDER": "local",
                    "MODEL_TIMEOUT_MS": "not-a-number",
                }
            )

        self.assertEqual(context.exception.code, ErrorCode.MODEL_PROVIDER_ERROR)
        self.assertEqual(
            context.exception.public_message,
            "MODEL_TIMEOUT_MS must be an integer.",
        )


if __name__ == "__main__":
    unittest.main()
