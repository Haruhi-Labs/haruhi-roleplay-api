from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.application.errors import AppError, ErrorCode  # noqa: E402
from haruhi_roleplay_api.domain import GenerationConfig, ModelMessage  # noqa: E402
from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    ModelProviderSettings,
    build_model_router,
)


class FakeHTTPResponseForRegistry:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeHTTPResponseForRegistry":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


def model_messages() -> tuple[ModelMessage, ...]:
    return (
        ModelMessage(role="system", content="你正在进行角色扮演。"),
        ModelMessage(role="user", content="请用一句话回应我。"),
    )


def registry_json(*, api_key: str | None = None) -> str:
    ollama_provider: dict[str, object] = {
        "type": "ollama",
        "base_url": "http://localhost:11434/v1",
        "timeout_ms": 60000,
    }
    if api_key is not None:
        ollama_provider["api_key"] = api_key
    return json.dumps(
        {
            "default_alias": "haruhi-ollama",
            "providers": {
                "ollama-local": ollama_provider,
                "fake": {
                    "type": "fake",
                },
            },
            "aliases": {
                "haruhi-ollama": {
                    "provider": "ollama-local",
                    "model": "qwen2.5:7b",
                },
                "haruhi-fake": {
                    "provider": "fake",
                    "model": "fake-roleplay-model",
                },
            },
        }
    )


class ModelProviderRegistryTests(unittest.TestCase):
    def test_alias_routes_to_ollama_provider_model(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeHTTPResponseForRegistry(
                {
                    "choices": [{"message": {"content": "真实模型通路回复"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                }
            ),
        ) as urlopen:
            router = build_model_router(
                ModelProviderSettings.from_mapping(
                    {"MODEL_PROVIDER_REGISTRY": registry_json()}
                )
            )
            response = router.generate(
                model_messages(),
                GenerationConfig(model="haruhi-ollama", temperature=0.2),
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(
            request.full_url,
            "http://localhost:11434/v1/chat/completions",
        )
        self.assertEqual(payload["model"], "qwen2.5:7b")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(response.provider, "ollama")
        self.assertEqual(response.model, "haruhi-ollama")
        self.assertEqual(response.reply, "真实模型通路回复")
        self.assertEqual(response.usage.promptTokens, 10)

    def test_default_alias_is_used_when_generation_model_is_missing(self) -> None:
        router = build_model_router(
            ModelProviderSettings.from_mapping(
                {"MODEL_PROVIDER_REGISTRY": registry_json()}
            )
        )

        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeHTTPResponseForRegistry(
                {
                    "choices": [{"message": {"content": "默认 alias 回复"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                }
            ),
        ) as urlopen:
            response = router.generate(model_messages(), GenerationConfig())

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))

        self.assertEqual(payload["model"], "qwen2.5:7b")
        self.assertEqual(response.provider, "ollama")
        self.assertEqual(response.model, "haruhi-ollama")

    def test_unconfigured_alias_is_rejected(self) -> None:
        router = build_model_router(
            ModelProviderSettings.from_mapping(
                {"MODEL_PROVIDER_REGISTRY": registry_json()}
            )
        )

        with self.assertRaises(AppError) as context:
            router.generate(
                model_messages(),
                GenerationConfig(model="raw-qwen2.5:7b"),
            )

        self.assertEqual(context.exception.code, ErrorCode.MODEL_PROVIDER_ERROR)
        self.assertEqual(
            context.exception.public_message,
            "Model alias is not configured: raw-qwen2.5:7b",
        )

    def test_missing_provider_required_config_is_rejected(self) -> None:
        raw_registry = json.dumps(
            {
                "default_alias": "broken",
                "providers": {
                    "ollama-local": {
                        "type": "ollama",
                    },
                },
                "aliases": {
                    "broken": {
                        "provider": "ollama-local",
                        "model": "qwen2.5:7b",
                    },
                },
            }
        )

        with self.assertRaises(AppError) as context:
            build_model_router(
                ModelProviderSettings.from_mapping(
                    {"MODEL_PROVIDER_REGISTRY": raw_registry}
                )
            )

        self.assertEqual(context.exception.code, ErrorCode.MODEL_PROVIDER_ERROR)
        self.assertIn("MODEL_BASE_URL is required", context.exception.public_message)

    def test_debug_does_not_expose_api_key(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeHTTPResponseForRegistry(
                {
                    "choices": [{"message": {"content": "安全回复"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            ),
        ):
            router = build_model_router(
                ModelProviderSettings.from_mapping(
                    {
                        "MODEL_PROVIDER_REGISTRY": registry_json(
                            api_key="secret-token"
                        )
                    }
                )
            )
            response = router.generate(
                model_messages(),
                GenerationConfig(model="haruhi-ollama"),
            )

        serialized = str(response.debug)

        self.assertEqual(response.provider, "ollama")
        self.assertEqual(response.model, "haruhi-ollama")
        self.assertNotIn("secret-token", serialized)
        self.assertNotIn("apiKey", serialized)


if __name__ == "__main__":
    unittest.main()
