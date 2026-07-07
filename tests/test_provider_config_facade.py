from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    GenerationConfig,
    ModelMessage,
    PersonaModeId,
    RagRetrieveFilters,
    RagRetrieveInput,
    UserId,
)
from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    EmbeddingProviderSettings,
    ModelProviderSettings,
    RagProviderSettings,
    RoleplayHttpRuntime,
    apply_provider_config_facade,
    build_embedding_provider,
    build_model_router,
)
from haruhi_roleplay_api.infrastructure.env_config_editor import (  # noqa: E402
    ENV_CONFIG_FIELD_BY_KEY,
    EnvConfigEditor,
)
from haruhi_roleplay_api.infrastructure.rag_provider_factory import (  # noqa: E402
    build_rag_service_from_env,
)
from haruhi_roleplay_api.infrastructure.session_store_factory import (  # noqa: E402
    SessionStoreSettings,
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


def model_messages() -> tuple[ModelMessage, ...]:
    return (
        ModelMessage(role="system", content="你正在进行角色扮演。"),
        ModelMessage(role="user", content="请用一句话回应我。"),
    )


class ProviderConfigFacadeTests(unittest.TestCase):
    def test_llm_facade_overrides_legacy_single_provider_defaults(self) -> None:
        env = apply_provider_config_facade(
            {
                "MODEL_PROVIDER": "fake",
                "MODEL_NAME": "fake-roleplay-model",
                "MODEL_ALIAS": "fake-roleplay-model",
                "LLM_API_TYPE": "openai",
                "LLM_BASE_URL": "https://api.openai.com/v1",
                "LLM_MODEL": "gpt-test",
                "LLM_API_KEY": "llm-secret",
            }
        )
        registry = json.loads(env["MODEL_PROVIDER_REGISTRY"])

        self.assertEqual(registry["default_alias"], "gpt-test")
        self.assertEqual(registry["providers"]["llm-main"]["type"], "openai")
        self.assertEqual(
            registry["providers"]["llm-main"]["api_key_env"],
            "LLM_API_KEY",
        )
        self.assertEqual(
            registry["aliases"]["gpt-test"],
            {"provider": "llm-main", "model": "gpt-test"},
        )

    def test_explicit_model_provider_registry_wins_over_llm_facade(self) -> None:
        registry = json.dumps(
            {
                "default_alias": "fake-main",
                "providers": {"fake": {"type": "fake"}},
                "aliases": {
                    "fake-main": {
                        "provider": "fake",
                        "model": "fake-roleplay-model",
                    }
                },
            }
        )
        env = apply_provider_config_facade(
            {
                "MODEL_PROVIDER_REGISTRY": registry,
                "LLM_API_TYPE": "openai",
                "LLM_MODEL": "gpt-test",
                "LLM_API_KEY": "llm-secret",
            }
        )

        self.assertEqual(env["MODEL_PROVIDER_REGISTRY"], registry)

    def test_llm_facade_builds_common_model_providers(self) -> None:
        cases = [
            (
                "openai",
                "https://api.openai.com/v1",
                "gpt-test",
                "https://api.openai.com/v1/chat/completions",
            ),
            (
                "openai_compatible",
                "https://gateway.example/v1",
                "gateway-model",
                "https://gateway.example/v1/chat/completions",
            ),
            (
                "deepseek",
                "https://api.deepseek.com",
                "deepseek-chat",
                "https://api.deepseek.com/chat/completions",
            ),
            (
                "gemini",
                "https://generativelanguage.googleapis.com/v1beta/openai",
                "gemini-test",
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            ),
        ]
        for api_type, base_url, model, expected_url in cases:
            with self.subTest(api_type=api_type):
                with patch(
                    "haruhi_roleplay_api.adapters.models.openai_compatible.urllib.request.urlopen",
                    return_value=FakeHTTPResponse(
                        {
                            "choices": [
                                {"message": {"content": f"{api_type} reply"}}
                            ],
                            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                        }
                    ),
                ) as urlopen:
                    router = build_model_router(
                        ModelProviderSettings.from_mapping(
                            {
                                "LLM_API_TYPE": api_type,
                                "LLM_BASE_URL": base_url,
                                "LLM_MODEL": model,
                                "LLM_API_KEY": "llm-secret",
                            }
                        )
                    )
                    response = router.generate(model_messages(), GenerationConfig())

                request = urlopen.call_args.args[0]
                payload = json.loads(request.data.decode("utf-8"))
                self.assertEqual(request.full_url, expected_url)
                self.assertEqual(request.headers["Authorization"], "Bearer llm-secret")
                self.assertEqual(payload["model"], model)
                self.assertEqual(response.model, model)

    def test_embedding_facade_builds_openai_compatible_provider(self) -> None:
        with patch(
            "haruhi_roleplay_api.adapters.embeddings.openai_compatible.urllib.request.urlopen",
            return_value=FakeHTTPResponse({"data": [{"embedding": [0.1, 0.2]}]}),
        ) as urlopen:
            provider = build_embedding_provider(
                EmbeddingProviderSettings.from_mapping(
                    {
                        "EMBEDDING_API_TYPE": "openai_compatible",
                        "EMBEDDING_BASE_URL": "https://embedding.example/v1",
                        "EMBEDDING_MODEL": "embed-test",
                        "EMBEDDING_API_KEY": "embedding-secret",
                        "EMBEDDING_DIMENSIONS": "2",
                    }
                )
            )
            embedding = provider.embed("社团 活动")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            request.full_url,
            "https://embedding.example/v1/embeddings",
        )
        self.assertEqual(
            request.headers["Authorization"],
            "Bearer embedding-secret",
        )
        self.assertEqual(payload["model"], "embed-test")
        self.assertEqual(embedding, (0.1, 0.2))

    def test_rag_facade_maps_qdrant_fields_and_runs_search(self) -> None:
        env = {
            "RAG_API_TYPE": "qdrant",
            "RAG_BASE_URL": "https://qdrant.example",
            "RAG_INDEX": "haruhi_rag",
            "RAG_API_KEY": "qdrant-secret",
        }
        settings = RagProviderSettings.from_mapping(env)

        self.assertEqual(settings.provider, "qdrant")
        self.assertEqual(settings.qdrantUrl, "https://qdrant.example")
        self.assertEqual(settings.qdrantCollection, "haruhi_rag")
        self.assertEqual(settings.qdrantApiKey, "qdrant-secret")

        with patch(
            "haruhi_roleplay_api.adapters.rag_qdrant.urllib.request.urlopen",
            return_value=FakeHTTPResponse({"result": []}),
        ) as urlopen:
            service = build_rag_service_from_env(env)
            output = service.retrieve(
                RagRetrieveInput(
                    appId=AppId("web"),
                    userId=UserId("user-1"),
                    characterId=CharacterId("haruhi"),
                    personaMode=PersonaModeId("mid_late_haruhi"),
                    query="社团 活动",
                    topK=3,
                    filters=RagRetrieveFilters(),
                )
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://qdrant.example/collections/haruhi_rag/points/search",
        )
        headers = {key.lower(): value for key, value in request.headers.items()}
        self.assertEqual(headers["api-key"], "qdrant-secret")
        self.assertEqual(output.provider, "qdrant-rag")

    def test_simple_config_defaults_session_to_sqlite(self) -> None:
        settings = SessionStoreSettings.from_mapping(
            {
                "LLM_API_TYPE": "fake",
                "LLM_MODEL": "fake-roleplay-model",
            }
        )

        self.assertEqual(settings.provider, "sqlite")
        self.assertEqual(settings.sqlitePath, ".data/sessions.sqlite3")

    def test_env_config_schema_and_check_support_simple_fields(self) -> None:
        self.assertIn("LLM_API_TYPE", ENV_CONFIG_FIELD_BY_KEY)
        self.assertTrue(ENV_CONFIG_FIELD_BY_KEY["LLM_API_KEY"].secret)
        self.assertTrue(ENV_CONFIG_FIELD_BY_KEY["RAG_API_KEY"].secret)

        editor = EnvConfigEditor(base_env={}, config_path=None)
        invalid = editor.check(
            {
                "values": {
                    "LLM_API_TYPE": "openai",
                    "LLM_MODEL": "gpt-test",
                }
            }
        )
        valid = editor.check(
            {
                "values": {
                    "LLM_API_TYPE": "openai",
                    "LLM_MODEL": "gpt-test",
                    "LLM_API_KEY": "llm-secret",
                    "RAG_API_TYPE": "qdrant",
                    "RAG_BASE_URL": "https://qdrant.example",
                    "RAG_INDEX": "haruhi_rag",
                }
            }
        )

        self.assertFalse(invalid.valid)
        self.assertIn(
            "LLM_API_KEY or OPENAI_API_KEY is required for LLM_API_TYPE=openai",
            invalid.errors,
        )
        self.assertTrue(valid.valid)

    def test_http_runtime_runs_chat_with_simple_fake_llm_config(self) -> None:
        runtime = RoleplayHttpRuntime.local(
            project_root=Path(__file__).resolve().parents[1],
            env={
                "ROLEPLAY_API_KEY": "secret",
                "LLM_API_TYPE": "fake",
                "LLM_MODEL": "fake-roleplay-model",
                "SESSION_PROVIDER": "memory",
                "RAG_PROVIDER": "local",
                "ENABLE_DEBUG_TRACE": "true",
            },
        )
        response = runtime.handle(
            method="POST",
            target="/v1/chat",
            headers={
                "Authorization": "Bearer secret",
                "Content-Type": "application/json",
            },
            body=json.dumps(
                {
                    "app_id": "web-demo",
                    "user_id": "user-1",
                    "character_id": "haruhi",
                    "persona_mode": "mid_late_haruhi",
                    "message": "今天社团做什么？",
                    "language": "zh-CN",
                    "capabilities": {"debug_trace": True},
                },
                ensure_ascii=False,
            ).encode("utf-8"),
        )
        body = json.loads(response.body.decode("utf-8"))

        self.assertEqual(response.status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["usage"]["provider"], "fake")
        self.assertEqual(body["data"]["usage"]["model"], "fake-roleplay-model")


if __name__ == "__main__":
    unittest.main()
