from __future__ import annotations

import json
import socket
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.application.errors import AppError, ErrorCode  # noqa: E402
from haruhi_roleplay_api.domain import GenerationConfig, ModelMessage  # noqa: E402
from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    ModelProviderSettings,
    build_model_router,
)


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


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
                continue
            yield f"data: {json.dumps(line, ensure_ascii=False)}\n\n".encode("utf-8")


class LazyStreamingHTTPResponse(FakeStreamingHTTPResponse):
    def __init__(self, lines: tuple[dict | str, ...]) -> None:
        super().__init__(lines)
        self.consumed = 0
        self.closed = False

    def __enter__(self) -> "LazyStreamingHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True
        return None

    def __iter__(self):
        for line in self._lines:
            self.consumed += 1
            if line == "[DONE]":
                yield b"data: [DONE]\n\n"
                continue
            yield f"data: {json.dumps(line, ensure_ascii=False)}\n\n".encode("utf-8")


def model_messages() -> tuple[ModelMessage, ...]:
    return (
        ModelMessage(role="system", content="你正在进行角色扮演。"),
        ModelMessage(role="user", content="今天有什么计划？"),
    )


def cloud_registry() -> str:
    return json.dumps(
        {
            "default_alias": "haruhi-deepseek",
            "providers": {
                "deepseek-cloud": {
                    "type": "deepseek",
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "timeout_ms": 60000,
                },
                "gemini-cloud": {
                    "type": "gemini",
                    "api_key_env": "GEMINI_API_KEY",
                    "timeout_ms": 60000,
                },
                "openai-cloud": {
                    "type": "openai",
                    "timeout_ms": 60000,
                },
            },
            "aliases": {
                "haruhi-deepseek": {
                    "provider": "deepseek-cloud",
                    "model": "deepseek-chat",
                },
                "haruhi-gemini": {
                    "provider": "gemini-cloud",
                    "model": "gemini-3.5-flash",
                },
                "haruhi-openai": {
                    "provider": "openai-cloud",
                    "model": "gpt-4.1-mini",
                },
            },
        }
    )


def settings() -> ModelProviderSettings:
    return ModelProviderSettings.from_mapping(
        {
            "MODEL_PROVIDER_REGISTRY": cloud_registry(),
            "DEEPSEEK_API_KEY": "deepseek-secret",
            "GEMINI_API_KEY": "gemini-secret",
            "OPENAI_API_KEY": "openai-secret",
        }
    )


class CloudModelProviderTests(unittest.TestCase):
    def test_deepseek_alias_uses_official_openai_compatible_endpoint(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeHTTPResponse(
                {
                    "choices": [{"message": {"content": "DeepSeek 回复"}}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 3},
                }
            ),
        ) as urlopen:
            response = build_model_router(settings()).generate(
                model_messages(),
                GenerationConfig(model="haruhi-deepseek", temperature=0.2),
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(
            request.full_url,
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(request.headers["Authorization"], "Bearer deepseek-secret")
        self.assertEqual(payload["model"], "deepseek-chat")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(response.provider, "deepseek")
        self.assertEqual(response.model, "haruhi-deepseek")
        self.assertEqual(response.reply, "DeepSeek 回复")

    def test_gemini_alias_uses_official_openai_compatible_endpoint(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeHTTPResponse(
                {
                    "choices": [{"message": {"content": "Gemini 回复"}}],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 2},
                }
            ),
        ) as urlopen:
            response = build_model_router(settings()).generate(
                model_messages(),
                GenerationConfig(
                    model="haruhi-gemini",
                    maxTokens=128,
                    frequencyPenalty=0.7,
                    presencePenalty=0.4,
                ),
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(
            request.full_url,
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        )
        self.assertEqual(request.headers["Authorization"], "Bearer gemini-secret")
        self.assertEqual(payload["model"], "gemini-3.5-flash")
        self.assertEqual(payload["max_tokens"], 128)
        self.assertNotIn("frequency_penalty", payload)
        self.assertNotIn("presence_penalty", payload)
        self.assertEqual(response.provider, "gemini")
        self.assertEqual(response.model, "haruhi-gemini")

    def test_openai_alias_uses_official_chat_completions_endpoint(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeHTTPResponse(
                {
                    "choices": [{"message": {"content": "OpenAI 回复"}}],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 3},
                }
            ),
        ) as urlopen:
            response = build_model_router(settings()).generate(
                model_messages(),
                GenerationConfig(model="haruhi-openai", topP=0.8),
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(
            request.full_url,
            "https://api.openai.com/v1/chat/completions",
        )
        self.assertEqual(request.headers["Authorization"], "Bearer openai-secret")
        self.assertEqual(payload["model"], "gpt-4.1-mini")
        self.assertEqual(payload["top_p"], 0.8)
        self.assertEqual(response.provider, "openai")
        self.assertEqual(response.model, "haruhi-openai")
        self.assertEqual(response.reply, "OpenAI 回复")

    def test_deepseek_stream_uses_sse_delta_parser(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeStreamingHTTPResponse(
                (
                    {"choices": [{"delta": {"content": "云端"}}]},
                    {"choices": [{"delta": {"content": "流式"}}]},
                    "[DONE]",
                )
            ),
        ) as urlopen:
            events = tuple(
                build_model_router(settings()).stream(
                    model_messages(),
                    GenerationConfig(model="haruhi-deepseek"),
                )
            )

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        done = events[-1].response

        self.assertTrue(payload["stream"])
        self.assertEqual(
            "".join(event.delta for event in events if event.event == "delta"),
            "云端流式",
        )
        self.assertEqual(done.provider, "deepseek")
        self.assertEqual(done.model, "haruhi-deepseek")

    def test_deepseek_stream_yields_before_full_response_is_consumed(self) -> None:
        response = LazyStreamingHTTPResponse(
            (
                {"choices": [{"delta": {"content": "云端"}}]},
                {"choices": [{"delta": {"content": "流式"}}]},
                "[DONE]",
            )
        )

        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            stream = build_model_router(settings()).stream(
                model_messages(),
                GenerationConfig(model="haruhi-deepseek"),
            )
            iterator = iter(stream)

            self.assertEqual(urlopen.call_count, 0)

            first = next(iterator)

            self.assertEqual(urlopen.call_count, 1)
            self.assertEqual(first.event, "delta")
            self.assertEqual(first.delta, "云端")
            self.assertEqual(response.consumed, 1)
            self.assertFalse(response.closed)

            remaining = tuple(iterator)

        events = (first, *remaining)

        self.assertEqual(response.consumed, 3)
        self.assertTrue(response.closed)
        self.assertEqual(
            "".join(event.delta for event in events if event.event == "delta"),
            "云端流式",
        )
        self.assertEqual(events[-1].event, "done")

    def test_openai_stream_uses_sse_delta_parser(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeStreamingHTTPResponse(
                (
                    {"choices": [{"delta": {"content": "OpenAI"}}]},
                    {"choices": [{"delta": {"content": "流式"}}]},
                    "[DONE]",
                )
            ),
        ) as urlopen:
            events = tuple(
                build_model_router(settings()).stream(
                    model_messages(),
                    GenerationConfig(model="haruhi-openai"),
                )
            )

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        done = events[-1].response

        self.assertTrue(payload["stream"])
        self.assertEqual(
            "".join(event.delta for event in events if event.event == "delta"),
            "OpenAI流式",
        )
        self.assertEqual(done.provider, "openai")
        self.assertEqual(done.model, "haruhi-openai")

    def test_gemini_stream_omits_unsupported_penalty_payload(self) -> None:
        response = LazyStreamingHTTPResponse(
            (
                {"choices": [{"delta": {"content": "Gemini"}}]},
                {"choices": [{"delta": {"content": "流式"}}]},
                "[DONE]",
            )
        )

        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            stream = build_model_router(settings()).stream(
                model_messages(),
                GenerationConfig(
                    model="haruhi-gemini",
                    frequencyPenalty=0.7,
                    presencePenalty=0.4,
                ),
            )
            iterator = iter(stream)
            first = next(iterator)

            self.assertEqual(first.event, "delta")
            self.assertEqual(first.delta, "Gemini")
            self.assertEqual(response.consumed, 1)

            events = (first, *tuple(iterator))

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        done = events[-1].response

        self.assertTrue(payload["stream"])
        self.assertNotIn("frequency_penalty", payload)
        self.assertNotIn("presence_penalty", payload)
        self.assertEqual(response.consumed, 3)
        self.assertTrue(response.closed)
        self.assertEqual(done.provider, "gemini")
        self.assertEqual(done.model, "haruhi-gemini")

    def test_cloud_provider_http_error_maps_to_app_error(self) -> None:
        http_error = urllib.error.HTTPError(
            url="https://api.deepseek.com/chat/completions",
            code=429,
            msg="rate limited",
            hdrs=None,
            fp=None,
        )
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            side_effect=http_error,
        ):
            with self.assertRaises(AppError) as context:
                build_model_router(settings()).generate(
                    model_messages(),
                    GenerationConfig(model="haruhi-deepseek"),
                )

        self.assertEqual(context.exception.code, ErrorCode.MODEL_PROVIDER_ERROR)
        self.assertEqual(
            context.exception.public_message,
            "deepseek model provider failed with HTTP 429.",
        )

    def test_openai_provider_http_error_maps_to_app_error(self) -> None:
        http_error = urllib.error.HTTPError(
            url="https://api.openai.com/v1/chat/completions",
            code=500,
            msg="server error",
            hdrs=None,
            fp=None,
        )
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            side_effect=http_error,
        ):
            with self.assertRaises(AppError) as context:
                build_model_router(settings()).generate(
                    model_messages(),
                    GenerationConfig(model="haruhi-openai"),
                )

        self.assertEqual(context.exception.code, ErrorCode.MODEL_PROVIDER_ERROR)
        self.assertEqual(
            context.exception.public_message,
            "openai model provider failed with HTTP 500.",
        )

    def test_openai_provider_invalid_response_maps_to_app_error(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeHTTPResponse({"choices": [{}]}),
        ):
            with self.assertRaises(AppError) as context:
                build_model_router(settings()).generate(
                    model_messages(),
                    GenerationConfig(model="haruhi-openai"),
                )

        self.assertEqual(context.exception.code, ErrorCode.MODEL_PROVIDER_ERROR)
        self.assertEqual(
            context.exception.public_message,
            "openai model provider response was invalid.",
        )

    def test_cloud_provider_timeout_maps_to_timeout_error(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            side_effect=socket.timeout("timeout"),
        ):
            with self.assertRaises(AppError) as context:
                build_model_router(settings()).generate(
                    model_messages(),
                    GenerationConfig(model="haruhi-gemini"),
                )

        self.assertEqual(context.exception.code, ErrorCode.MODEL_TIMEOUT)
        self.assertEqual(
            context.exception.public_message,
            "gemini model provider timed out.",
        )

    def test_cloud_provider_requires_api_key(self) -> None:
        with self.assertRaises(AppError) as context:
            build_model_router(
                ModelProviderSettings.from_mapping(
                    {"MODEL_PROVIDER_REGISTRY": cloud_registry()}
                )
            )

        self.assertEqual(context.exception.code, ErrorCode.MODEL_PROVIDER_ERROR)
        self.assertIn("DEEPSEEK_API_KEY is required", context.exception.public_message)

    def test_openai_provider_uses_default_api_key_env(self) -> None:
        registry = json.dumps(
            {
                "default_alias": "haruhi-openai",
                "providers": {
                    "openai-cloud": {
                        "type": "openai",
                        "timeout_ms": 60000,
                    }
                },
                "aliases": {
                    "haruhi-openai": {
                        "provider": "openai-cloud",
                        "model": "gpt-4.1-mini",
                    }
                },
            }
        )

        with self.assertRaises(AppError) as context:
            build_model_router(
                ModelProviderSettings.from_mapping(
                    {"MODEL_PROVIDER_REGISTRY": registry}
                )
            )

        self.assertEqual(context.exception.code, ErrorCode.MODEL_PROVIDER_ERROR)
        self.assertIn("OPENAI_API_KEY is required", context.exception.public_message)

    def test_cloud_provider_debug_does_not_expose_secret(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
            return_value=FakeHTTPResponse(
                {
                    "choices": [{"message": {"content": "安全回复"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            ),
        ):
            response = build_model_router(settings()).generate(
                model_messages(),
                GenerationConfig(model="haruhi-gemini"),
            )

        serialized = str(response.debug)

        self.assertEqual(response.provider, "gemini")
        self.assertEqual(response.model, "haruhi-gemini")
        self.assertNotIn("gemini-secret", serialized)
        self.assertNotIn("apiKey", serialized)


if __name__ == "__main__":
    unittest.main()
