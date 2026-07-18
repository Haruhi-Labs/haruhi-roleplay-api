from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    HttpRuntimeSettings,
    HttpRuntimeStreamResponse,
    RoleplayHttpRuntime,
    RuntimeConfigStore,
)
from haruhi_roleplay_api.domain.request_limits import (  # noqa: E402
    MAX_HTTP_BODY_BYTES,
)


ROOT = Path(__file__).resolve().parents[1]


def runtime(env: dict[str, str] | None = None) -> RoleplayHttpRuntime:
    merged_env = {
        "MODEL_PROVIDER": "fake",
        "MODEL_NAME": "fake-roleplay-model",
        **(env or {}),
    }
    return RoleplayHttpRuntime.local(project_root=ROOT, env=merged_env)


def json_response(body: bytes) -> dict:
    return json.loads(body.decode("utf-8"))


def json_body(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def auth_headers() -> dict[str, str]:
    return {
        "content-type": "application/json",
        "Authorization": "Bearer secret",
    }


def chat_body(
    *,
    rag: bool = False,
    memory: bool = False,
    memory_write: dict | None = None,
    stream: bool = False,
    session_id: str | None = None,
    continuous_session: bool = False,
    user_id: str = "user-1",
) -> dict:
    body = {
        "app_id": "web",
        "user_id": user_id,
        "session_id": session_id,
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "message": "社团 活动 怎么安排？",
        "language": "zh-CN",
        "capabilities": {
            "rag": rag,
            "memory": memory,
            "continuous_session": continuous_session,
            "safety_filter": True,
            "debug_trace": True,
            "stream": stream,
        },
        "generation": {
            "model": "fake-roleplay-model",
        },
    }
    if memory_write is not None:
        body["metadata"] = {"memory_write": memory_write}
    return body


def rag_document_body() -> dict:
    return {
        "app_id": "web",
        "document_id": "doc-http-rag",
        "title": "HTTP 本地 RAG 资料",
        "source_type": "timeline",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "timeline": "mid_late",
        "spoiler_level": 2,
        "language": "zh-CN",
        "content": "社团 活动 计划：春日会主动安排调查和招募。",
    }


def session_body() -> dict:
    return {
        "app_id": "web",
        "user_id": "user-1",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
    }


class HttpRuntimeAdapterTests(unittest.TestCase):
    def test_oversized_body_returns_413(self) -> None:
        response = runtime().handle(
            method="POST",
            target="/v1/chat",
            headers={"X-Request-Id": "req-body-limit"},
            body=b"x" * (MAX_HTTP_BODY_BYTES + 1),
        )
        body = json_response(response.body)

        self.assertEqual(response.status, 413)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "REQUEST_BODY_TOO_LARGE")
        self.assertEqual(body["request_id"], "req-body-limit")

    def test_http_runtime_settings_reads_configured_bind_address(self) -> None:
        settings = HttpRuntimeSettings.from_env(
            {
                "ROLEPLAY_HOST": "0.0.0.0",
                "ROLEPLAY_PORT": "8123",
                "ROLEPLAY_CORS_ORIGINS": (
                    "https://app.example.com,http://127.0.0.1:5173"
                ),
            }
        )

        self.assertEqual(settings.host, "0.0.0.0")
        self.assertEqual(settings.port, 8123)
        self.assertEqual(
            settings.cors_allowed_origins,
            ("https://app.example.com", "http://127.0.0.1:5173"),
        )

    def test_http_runtime_settings_rejects_wildcard_cors_origin(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not contain"):
            HttpRuntimeSettings.from_env({"ROLEPLAY_CORS_ORIGINS": "*"})

    def test_local_runtime_rejects_weak_key_on_public_bind(self) -> None:
        with self.assertRaisesRegex(ValueError, "Non-loopback"):
            runtime(
                {
                    "ROLEPLAY_HOST": "0.0.0.0",
                    "ROLEPLAY_API_KEY": "change-me",
                }
            )

    def test_http_runtime_settings_reads_port_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            env_path = project_root / ".env"
            env_path.write_text(
                "ROLEPLAY_HOST=127.0.0.1\nROLEPLAY_PORT=8124\n",
                encoding="utf-8",
            )
            config_store = RuntimeConfigStore.env_file(
                project_root=project_root,
                env={},
            )
            settings = HttpRuntimeSettings.from_env(config_store.env())

        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 8124)

    def test_get_personas_returns_catalog_over_http_shape(self) -> None:
        response = runtime().handle(
            method="GET",
            target="/v1/personas",
            headers={"X-Request-Id": "req-http-personas"},
        )
        body = json_response(response.body)

        self.assertEqual(response.status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["request_id"], "req-http-personas")
        self.assertIn("characters", body["data"])
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)
        self.assertEqual(response.headers["Vary"], "Origin")

    def test_same_origin_request_receives_exact_cors_origin(self) -> None:
        response = runtime().handle(
            method="GET",
            target="/v1/personas",
            headers={
                "Host": "127.0.0.1:8000",
                "Origin": "http://127.0.0.1:8000",
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"],
            "http://127.0.0.1:8000",
        )

    def test_allowed_cross_origin_is_reflected_without_wildcard(self) -> None:
        app = runtime(
            {
                "ROLEPLAY_API_KEY": "secret",
                "ROLEPLAY_CORS_ORIGINS": "https://admin.example.com",
            }
        )
        response = app.handle(
            method="GET",
            target="/v1/runtime-config",
            headers={
                **auth_headers(),
                "Host": "api.example.com",
                "Origin": "https://admin.example.com",
            },
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"],
            "https://admin.example.com",
        )
        self.assertNotEqual(response.headers["Access-Control-Allow-Origin"], "*")

        preflight = app.handle(
            method="OPTIONS",
            target="/v1/runtime-config",
            headers={
                "Host": "api.example.com",
                "Origin": "https://admin.example.com",
            },
        )
        self.assertEqual(preflight.status, 204)
        self.assertEqual(
            preflight.headers["Access-Control-Allow-Origin"],
            "https://admin.example.com",
        )

    def test_disallowed_cross_origin_is_rejected_before_management_api(self) -> None:
        response = runtime({"ROLEPLAY_API_KEY": "secret"}).handle(
            method="GET",
            target="/v1/runtime-config",
            headers={
                **auth_headers(),
                "Host": "api.example.com",
                "Origin": "https://untrusted.example.com",
            },
        )
        body = json_response(response.body)

        self.assertEqual(response.status, 403)
        self.assertEqual(body["error"]["code"], "AUTH_PERMISSION_DENIED")
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_post_chat_returns_fake_model_reply(self) -> None:
        response = runtime().handle(
            method="POST",
            target="/v1/chat",
            headers={"content-type": "application/json"},
            body=json_body(chat_body()),
        )
        body = json_response(response.body)

        self.assertEqual(response.status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(
            body["data"]["reply"],
            "[fake:fake-roleplay-model] 社团 活动 怎么安排？",
        )
        self.assertEqual(body["data"]["usage"]["provider"], "fake")

    def test_post_chat_accepts_minimal_frontend_body(self) -> None:
        request_body = chat_body()
        request_body.pop("capabilities")
        request_body.pop("generation")

        response = runtime().handle(
            method="POST",
            target="/v1/chat",
            headers={"content-type": "application/json"},
            body=json_body(request_body),
        )
        body = json_response(response.body)

        self.assertEqual(response.status, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["data"]["rag"]["enabled"])
        self.assertEqual(body["data"]["rag"]["hit_count"], 0)
        self.assertTrue(body["data"]["memory"]["enabled"])
        self.assertEqual(body["data"]["memory"]["read_count"], 0)
        self.assertIsNone(body["data"]["debug"])

    def test_post_chat_stream_returns_sse_events(self) -> None:
        response = runtime().handle(
            method="POST",
            target="/v1/chat/stream",
            headers={"content-type": "application/json"},
            body=json_body(chat_body(stream=True)),
        )
        self.assertIsInstance(response, HttpRuntimeStreamResponse)
        events = tuple(response.events)
        event_names = [event["event"] for event in events]

        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.headers["Content-Type"],
            "text/event-stream; charset=utf-8",
        )
        self.assertEqual(event_names[0], "start")
        self.assertIn("delta", event_names)
        self.assertIn("usage", event_names)
        self.assertEqual(event_names[-1], "done")

    def test_post_chat_stream_validation_error_returns_json_envelope(self) -> None:
        invalid_body = chat_body(stream=True)
        invalid_body.pop("character_id")

        response = runtime().handle(
            method="POST",
            target="/v1/chat/stream",
            headers={"content-type": "application/json"},
            body=json_body(invalid_body),
        )
        body = json_response(response.body)

        self.assertNotIsInstance(response, HttpRuntimeStreamResponse)
        self.assertEqual(
            response.headers["Content-Type"],
            "application/json; charset=utf-8",
        )
        self.assertEqual(response.status, 400)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")

    def test_rag_ingest_and_chat_share_local_runtime_state(self) -> None:
        app = runtime()
        ingest_response = app.handle(
            method="POST",
            target="/v1/rag/documents",
            headers={"content-type": "application/json"},
            body=json_body(rag_document_body()),
        )
        chat_response = app.handle(
            method="POST",
            target="/v1/chat",
            headers={"content-type": "application/json"},
            body=json_body(chat_body(rag=True)),
        )
        ingest_body = json_response(ingest_response.body)
        chat_result = json_response(chat_response.body)

        self.assertEqual(ingest_response.status, 200)
        self.assertTrue(ingest_body["ok"])
        self.assertEqual(ingest_body["data"]["status"], "imported")
        self.assertEqual(chat_response.status, 200)
        self.assertTrue(chat_result["ok"])
        self.assertTrue(chat_result["data"]["rag"]["enabled"])
        self.assertEqual(chat_result["data"]["rag"]["provider"], "local-rag")
        self.assertEqual(
            chat_result["data"]["rag"]["sources"][0]["document_id"],
            "doc-http-rag",
        )
        self.assertIn(
            "春日会主动安排调查和招募",
            chat_result["data"]["rag"]["sources"][0]["content"],
        )

    def test_rag_search_uses_runtime_provider(self) -> None:
        app = runtime({"RAG_PROVIDER": "local_vector", "RAG_CHUNK_SIZE": "24"})
        app.handle(
            method="POST",
            target="/v1/rag/documents",
            headers={"content-type": "application/json"},
            body=json_body(rag_document_body()),
        )
        search_response = app.handle(
            method="POST",
            target="/v1/rag/search",
            headers={"content-type": "application/json"},
            body=json_body(
                {
                    "app_id": "web",
                    "user_id": "user-1",
                    "character_id": "haruhi",
                    "persona_mode": "mid_late_haruhi",
                    "query": "社团 活动",
                    "top_k": 3,
                    "filters": {
                        "source_types": ["timeline"],
                        "timelines": ["mid_late"],
                        "spoiler_level_max": 2,
                        "language": "zh-CN",
                    },
                }
            ),
        )
        body = json_response(search_response.body)

        self.assertEqual(search_response.status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["provider"], "local-vector-rag")
        self.assertEqual(body["data"]["chunks"][0]["document_id"], "doc-http-rag")

    def test_api_key_can_guard_runtime(self) -> None:
        app = runtime({"ROLEPLAY_API_KEY": "secret"})
        denied = app.handle(method="GET", target="/v1/personas", headers={})
        allowed = app.handle(
            method="GET",
            target="/v1/personas",
            headers={"Authorization": "Bearer secret"},
        )
        denied_body = json_response(denied.body)

        self.assertEqual(denied.status, 401)
        self.assertEqual(denied_body["error"]["code"], "AUTH_INVALID_API_KEY")
        self.assertEqual(allowed.status, 200)

    def test_unknown_route_returns_json_404(self) -> None:
        response = runtime().handle(method="GET", target="/v1/missing", headers={})
        body = json_response(response.body)

        self.assertEqual(response.status, 404)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "NOT_FOUND")

    def test_demo_index_is_served_without_api_auth(self) -> None:
        app = runtime({"ROLEPLAY_API_KEY": "secret"})
        response = app.handle(method="GET", target="/demo", headers={})
        body = response.body.decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("Haruhi Roleplay Demo", body)
        self.assertIn('<details class="chat-advanced">', body)
        self.assertIn('placeholder="Server default"', body)

    def test_demo_static_asset_is_served(self) -> None:
        response = runtime().handle(method="GET", target="/demo/app.js", headers={})
        body = response.body.decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.headers["Content-Type"],
            "text/javascript; charset=utf-8",
        )
        self.assertIn("loadCatalog", body)
        self.assertIn("buildChatRequest", body)
        self.assertIn("await reader.cancel()", body)
        self.assertNotIn("fake-roleplay-model", body)

    def test_demo_static_route_rejects_path_traversal(self) -> None:
        response = runtime().handle(
            method="GET",
            target="/demo/../README.md",
            headers={},
        )

        self.assertEqual(response.status, 404)

    def test_public_chat_page_is_served_without_api_auth(self) -> None:
        app = runtime({"ROLEPLAY_API_KEY": "secret"})
        response = app.handle(method="GET", target="/chat/", headers={})
        body = response.body.decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("Roleplay 服务调试工作台", body)
        self.assertIn("展示并测试 Roleplay 服务的完整能力", body)
        self.assertNotIn('href="/admin/"', body)
        self.assertIn('src="/chat/chat.js"', body)
        self.assertNotIn("Authorization", body)
        self.assertNotIn("API Key", body)

    def test_root_redirects_to_public_chat(self) -> None:
        response = runtime({"ROLEPLAY_API_KEY": "secret"}).handle(
            method="GET",
            target="/",
            headers={},
        )

        self.assertEqual(response.status, 302)
        self.assertEqual(response.headers["Location"], "/chat/")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_public_chat_assets_use_server_side_demo_proxy(self) -> None:
        script = runtime().handle(method="GET", target="/chat/chat.js", headers={})
        script_body = script.body.decode("utf-8")
        stylesheet = runtime().handle(
            method="GET",
            target="/chat/chat.css",
            headers={},
        )

        self.assertEqual(script.status, 200)
        self.assertEqual(
            script.headers["Content-Type"],
            "text/javascript; charset=utf-8",
        )
        self.assertEqual(stylesheet.status, 200)
        self.assertEqual(stylesheet.headers["Content-Type"], "text/css; charset=utf-8")
        self.assertIn('const API_ROOT = "/v1/demo";', script_body)
        self.assertIn('const APP_ID = "roleplay-prod";', script_body)
        self.assertIn("scheduleStreamingMessage(assistant, reply)", script_body)
        self.assertIn("STREAM_RENDER_INTERVAL_MS = 50", script_body)
        self.assertIn('content.className = "source-content"', script_body)
        self.assertIn("展开完整语料", script_body)
        self.assertNotIn(
            'updateMessage(assistant, { pending: true, content: reply })',
            script_body,
        )
        self.assertNotIn("Bearer ", script_body)
        self.assertNotIn("X-API-Key", script_body)

    def test_public_chat_static_route_rejects_path_traversal(self) -> None:
        response = runtime().handle(
            method="GET",
            target="/chat/../README.md",
            headers={},
        )

        self.assertEqual(response.status, 404)

    def test_public_demo_aliases_safe_runtime_routes(self) -> None:
        app = runtime({"ROLEPLAY_API_KEY": "secret"})
        health = app.handle(
            method="GET",
            target="/v1/demo/health",
            headers=auth_headers(),
        )
        personas = app.handle(
            method="GET",
            target="/v1/demo/personas",
            headers=auth_headers(),
        )
        demo_chat_body = chat_body(user_id="demo-browser-user")
        chat = app.handle(
            method="POST",
            target="/v1/demo/chat",
            headers=auth_headers(),
            body=json_body(demo_chat_body),
        )

        self.assertEqual(health.status, 200)
        self.assertEqual(json_response(health.body)["data"]["status"], "ok")
        self.assertEqual(personas.status, 200)
        self.assertIn("characters", json_response(personas.body)["data"])
        self.assertEqual(chat.status, 200)
        self.assertEqual(json_response(chat.body)["data"]["character_id"], "haruhi")

    def test_public_demo_rejects_non_demo_user_scope(self) -> None:
        app = runtime({"ROLEPLAY_API_KEY": "secret"})
        chat = app.handle(
            method="POST",
            target="/v1/demo/chat",
            headers=auth_headers(),
            body=json_body(chat_body(user_id="production-user")),
        )
        memory = app.handle(
            method="GET",
            target=(
                "/v1/demo/memory/production-user"
                "?app_id=web&character_id=haruhi&persona_mode=mid_late_haruhi"
            ),
            headers=auth_headers(),
        )

        self.assertEqual(chat.status, 403)
        self.assertEqual(
            json_response(chat.body)["error"]["code"],
            "AUTH_PERMISSION_DENIED",
        )
        self.assertEqual(memory.status, 403)

    def test_public_demo_rejects_rag_ingest_and_admin_routes(self) -> None:
        app = runtime({"ROLEPLAY_API_KEY": "secret"})
        ingest = app.handle(
            method="POST",
            target="/v1/demo/rag/documents",
            headers=auth_headers(),
            body=json_body(rag_document_body()),
        )
        admin = app.handle(
            method="GET",
            target="/v1/demo/admin/usage",
            headers=auth_headers(),
        )

        self.assertEqual(ingest.status, 403)
        self.assertEqual(admin.status, 403)

    def test_config_editor_page_is_served_without_api_auth(self) -> None:
        app = runtime({"ROLEPLAY_API_KEY": "secret"})
        response = app.handle(method="GET", target="/config", headers={})
        body = response.body.decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("Haruhi Env Config", body)

        script = app.handle(method="GET", target="/config/config.js", headers={})
        script_body = script.body.decode("utf-8")

        self.assertEqual(script.status, 200)
        self.assertIn("advancedVisible: false", script_body)
        self.assertIn("simple_presets", script_body)
        self.assertIn("field.advanced", script_body)
        self.assertIn("effectiveValue(field.key)", script_body)

    def test_env_config_requires_api_key(self) -> None:
        response = runtime().handle(
            method="GET",
            target="/v1/env-config/schema",
            headers={"content-type": "application/json"},
        )
        body = json_response(response.body)

        self.assertEqual(response.status, 403)
        self.assertEqual(body["error"]["code"], "AUTH_PERMISSION_DENIED")

    def test_env_config_schema_snapshot_check_and_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "ROLEPLAY_API_KEY=secret",
                        "OPENAI_API_KEY=cloud-secret",
                        "MODEL_PROVIDER=fake",
                        "MODEL_NAME=fake-one",
                        "MODEL_ALIAS=fake-one",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            app = RoleplayHttpRuntime.from_env_file(
                project_root=ROOT,
                env={"ROLEPLAY_CONFIG_FILE": str(env_path)},
            )
            schema = app.handle(
                method="GET",
                target="/v1/env-config/schema",
                headers=auth_headers(),
            )
            snapshot = app.handle(
                method="GET",
                target="/v1/env-config",
                headers=auth_headers(),
            )
            check = app.handle(
                method="POST",
                target="/v1/env-config/check",
                headers=auth_headers(),
                body=json_body({"key": "MODEL_TIMEOUT_MS", "value": "0"}),
            )
            patch = app.handle(
                method="PATCH",
                target="/v1/env-config",
                headers=auth_headers(),
                body=json_body(
                    {
                        "values": {
                            "MODEL_NAME": "fake-two",
                            "MODEL_ALIAS": "fake-two",
                        }
                    }
                ),
            )
            chat = app.handle(
                method="POST",
                target="/v1/chat",
                headers=auth_headers(),
                body=json_body(
                    {
                        **chat_body(),
                        "generation": {"model": "fake-two"},
                    }
                ),
            )

        schema_body = json_response(schema.body)
        snapshot_body = json_response(snapshot.body)
        check_body = json_response(check.body)
        patch_body = json_response(patch.body)
        chat_body_data = json_response(chat.body)
        serialized_snapshot = json.dumps(snapshot_body, ensure_ascii=False)

        self.assertEqual(schema.status, 200)
        self.assertTrue(
            any(
                field["key"] == "ROLEPLAY_API_KEY" and field["secret"]
                for field in schema_body["data"]["fields"]
            )
        )
        self.assertEqual(snapshot.status, 200)
        self.assertEqual(
            snapshot_body["data"]["values"]["OPENAI_API_KEY"]["status"],
            "set",
        )
        self.assertNotIn("cloud-secret", serialized_snapshot)
        self.assertEqual(check.status, 200)
        self.assertFalse(check_body["data"]["valid"])
        self.assertEqual(patch.status, 200)
        self.assertEqual(patch_body["data"]["hot_reload"]["status"], "applied")
        self.assertEqual(
            patch_body["data"]["applied_keys"],
            ["MODEL_NAME", "MODEL_ALIAS"],
        )
        self.assertEqual(chat.status, 200)
        self.assertEqual(
            chat_body_data["data"]["reply"],
            "[fake:fake-two] 社团 活动 怎么安排？",
        )

    def test_runtime_config_requires_api_key_even_in_local_runtime(self) -> None:
        response = runtime().handle(
            method="GET",
            target="/v1/runtime-config",
            headers={"content-type": "application/json"},
        )
        body = json_response(response.body)

        self.assertEqual(response.status, 403)
        self.assertEqual(body["error"]["code"], "AUTH_PERMISSION_DENIED")

    def test_runtime_config_reads_env_file_and_redacts_registry(self) -> None:
        registry = {
            "default_alias": "fake-one",
            "providers": {"fake": {"type": "fake"}},
            "aliases": {"fake-one": {"provider": "fake", "model": "fake-one"}},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "APP_ENV=local",
                        "ROLEPLAY_API_KEY=secret",
                        "OPENAI_API_KEY=server-secret",
                        f"MODEL_PROVIDER_REGISTRY={json.dumps(registry)}",
                        "RAG_PROVIDER=local",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            app = RoleplayHttpRuntime.from_env_file(
                project_root=ROOT,
                env={"ROLEPLAY_CONFIG_FILE": str(env_path)},
            )

            response = app.handle(
                method="GET",
                target="/v1/runtime-config",
                headers=auth_headers(),
            )
            body = json_response(response.body)

        values = body["data"]["values"]
        registry_summary = values["MODEL_PROVIDER_REGISTRY"]
        self.assertEqual(response.status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["source"], str(env_path))
        self.assertTrue(registry_summary["configured"])
        self.assertEqual(registry_summary["default_alias"], "fake-one")
        self.assertNotIn("ROLEPLAY_API_KEY", values)
        self.assertNotIn("OPENAI_API_KEY", values)

    def test_runtime_config_snapshot_includes_session_config_boundary(self) -> None:
        api_key = "a" * 32
        app = runtime(
            {
                "ROLEPLAY_API_KEY": api_key,
                "ROLEPLAY_HOST": "0.0.0.0",
                "ROLEPLAY_PORT": "8125",
                "SESSION_PROVIDER": "memory",
                "SESSION_RECENT_LIMIT": "4",
                "SESSION_SQLITE_PATH": ".data/sessions.sqlite3",
            }
        )

        response = app.handle(
            method="GET",
            target="/v1/runtime-config",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        body = json_response(response.body)

        self.assertEqual(response.status, 200)
        self.assertEqual(body["data"]["values"]["ROLEPLAY_HOST"], "0.0.0.0")
        self.assertEqual(body["data"]["values"]["ROLEPLAY_PORT"], "8125")
        self.assertEqual(body["data"]["values"]["SESSION_PROVIDER"], "memory")
        self.assertEqual(body["data"]["values"]["SESSION_RECENT_LIMIT"], "4")
        self.assertIn("SESSION_RECENT_LIMIT", body["data"]["configurable_keys"])
        self.assertIn("ROLEPLAY_PORT", body["data"]["restart_required_keys"])
        self.assertIn("SESSION_PROVIDER", body["data"]["restart_required_keys"])

    def test_runtime_config_patch_rebuilds_model_without_restart(self) -> None:
        app = runtime(
            {
                "ROLEPLAY_API_KEY": "secret",
                "MODEL_PROVIDER": "fake",
                "MODEL_NAME": "fake-one",
                "MODEL_ALIAS": "fake-one",
            }
        )
        before = app.handle(
            method="POST",
            target="/v1/chat",
            headers=auth_headers(),
            body=json_body(
                {
                    **chat_body(),
                    "generation": {"model": "fake-one"},
                }
            ),
        )
        patch = app.handle(
            method="PATCH",
            target="/v1/runtime-config",
            headers=auth_headers(),
            body=json_body(
                {
                    "values": {
                        "MODEL_PROVIDER": "fake",
                        "MODEL_NAME": "fake-two",
                        "MODEL_ALIAS": "fake-two",
                    }
                }
            ),
        )
        after = app.handle(
            method="POST",
            target="/v1/chat",
            headers=auth_headers(),
            body=json_body(
                {
                    **chat_body(),
                    "generation": {"model": "fake-two"},
                }
            ),
        )
        before_body = json_response(before.body)
        patch_body = json_response(patch.body)
        after_body = json_response(after.body)

        self.assertEqual(before_body["data"]["reply"], "[fake:fake-one] 社团 活动 怎么安排？")
        self.assertEqual(patch.status, 200)
        self.assertEqual(
            patch_body["data"]["applied_keys"],
            ["MODEL_PROVIDER", "MODEL_NAME", "MODEL_ALIAS"],
        )
        self.assertEqual(after_body["data"]["reply"], "[fake:fake-two] 社团 活动 怎么安排？")

    def test_runtime_config_patch_updates_session_recent_limit_without_replacing_store(
        self,
    ) -> None:
        app = runtime(
            {
                "ROLEPLAY_API_KEY": "secret",
                "SESSION_PROVIDER": "memory",
                "SESSION_RECENT_LIMIT": "2",
            }
        )
        session_response = app.handle(
            method="POST",
            target="/v1/sessions",
            headers=auth_headers(),
            body=json_body(session_body()),
        )
        session_id = json_response(session_response.body)["data"]["session_id"]

        app.handle(
            method="POST",
            target="/v1/chat",
            headers=auth_headers(),
            body=json_body(
                chat_body(
                    session_id=session_id,
                    continuous_session=True,
                )
            ),
        )
        patch = app.handle(
            method="PATCH",
            target="/v1/runtime-config",
            headers=auth_headers(),
            body=json_body({"values": {"SESSION_RECENT_LIMIT": "1"}}),
        )
        second = app.handle(
            method="POST",
            target="/v1/chat",
            headers=auth_headers(),
            body=json_body(
                chat_body(
                    session_id=session_id,
                    continuous_session=True,
                )
            ),
        )
        patch_body = json_response(patch.body)
        second_body = json_response(second.body)

        self.assertEqual(patch.status, 200)
        self.assertEqual(patch_body["data"]["applied_keys"], ["SESSION_RECENT_LIMIT"])
        self.assertEqual(second.status, 200)
        self.assertEqual(second_body["data"]["session_id"], session_id)
        self.assertEqual(second_body["data"]["debug"]["sessionReadCount"], 1)

    def test_sqlite_session_provider_persists_across_runtime_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "ROLEPLAY_API_KEY": "secret",
                "SESSION_PROVIDER": "sqlite",
                "SESSION_SQLITE_PATH": str(Path(temp_dir) / "sessions.sqlite3"),
            }
            first_app = runtime(env)
            session_response = first_app.handle(
                method="POST",
                target="/v1/sessions",
                headers=auth_headers(),
                body=json_body(session_body()),
            )
            session_id = json_response(session_response.body)["data"]["session_id"]
            first_app.handle(
                method="POST",
                target="/v1/chat",
                headers=auth_headers(),
                body=json_body(
                    chat_body(
                        session_id=session_id,
                        continuous_session=True,
                    )
                ),
            )

            second_app = runtime(env)
            second = second_app.handle(
                method="POST",
                target="/v1/chat",
                headers=auth_headers(),
                body=json_body(
                    chat_body(
                        session_id=session_id,
                        continuous_session=True,
                    )
                ),
            )
            second_body = json_response(second.body)

        self.assertEqual(second.status, 200)
        self.assertEqual(second_body["data"]["session_id"], session_id)
        self.assertEqual(second_body["data"]["debug"]["sessionReadCount"], 2)

    def test_sqlite_session_provider_keeps_scope_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = runtime(
                {
                    "ROLEPLAY_API_KEY": "secret",
                    "SESSION_PROVIDER": "sqlite",
                    "SESSION_SQLITE_PATH": str(Path(temp_dir) / "sessions.sqlite3"),
                }
            )
            session_response = app.handle(
                method="POST",
                target="/v1/sessions",
                headers=auth_headers(),
                body=json_body(session_body()),
            )
            session_id = json_response(session_response.body)["data"]["session_id"]
            response = app.handle(
                method="POST",
                target="/v1/chat",
                headers=auth_headers(),
                body=json_body(
                    chat_body(
                        session_id=session_id,
                        continuous_session=True,
                        user_id="user-2",
                    )
                ),
            )
            body = json_response(response.body)

        self.assertEqual(response.status, 404)
        self.assertEqual(body["error"]["code"], "SESSION_NOT_FOUND")

    def test_sqlite_memory_provider_persists_across_runtime_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "ROLEPLAY_API_KEY": "secret",
                "MEMORY_PROVIDER": "sqlite",
                "MEMORY_SQLITE_PATH": str(Path(temp_dir) / "memories.sqlite3"),
            }
            first_app = runtime(env)
            chat = first_app.handle(
                method="POST",
                target="/v1/chat",
                headers=auth_headers(),
                body=json_body(
                    chat_body(
                        memory=True,
                        memory_write={
                            "type": "user_preference",
                            "content": "用户喜欢先制定社团活动计划",
                            "reason": "用户明确表达稳定偏好",
                            "confidence": 0.9,
                        },
                    )
                ),
            )

            second_app = runtime(env)
            listed = second_app.handle(
                method="GET",
                target=(
                    "/v1/memory/user-1"
                    "?app_id=web"
                    "&character_id=haruhi"
                    "&persona_mode=mid_late_haruhi"
                ),
                headers=auth_headers(),
            )
            chat_body_data = json_response(chat.body)
            listed_body = json_response(listed.body)

        self.assertEqual(chat.status, 200)
        self.assertEqual(chat_body_data["data"]["memory"]["write_count"], 1)
        self.assertEqual(listed.status, 200)
        self.assertEqual(listed_body["data"]["count"], 1)
        self.assertEqual(
            listed_body["data"]["items"][0]["content"],
            "用户喜欢先制定社团活动计划",
        )

    def test_runtime_config_patch_can_select_model_backed_agent_planner_placeholder(
        self,
    ) -> None:
        app = runtime({"ROLEPLAY_API_KEY": "secret"})
        patch = app.handle(
            method="PATCH",
            target="/v1/runtime-config",
            headers=auth_headers(),
            body=json_body({"values": {"AGENT_CONTEXT_PLANNER": "model"}}),
        )
        chat = app.handle(
            method="POST",
            target="/v1/chat",
            headers=auth_headers(),
            body=json_body(chat_body()),
        )
        patch_body = json_response(patch.body)
        chat_body_data = json_response(chat.body)

        self.assertEqual(patch.status, 200)
        self.assertEqual(patch_body["data"]["applied_keys"], ["AGENT_CONTEXT_PLANNER"])
        self.assertEqual(chat.status, 502)
        self.assertEqual(chat_body_data["error"]["code"], "MODEL_PROVIDER_ERROR")
        self.assertIn("not implemented", chat_body_data["error"]["message"])

    def test_runtime_config_patch_rejects_sensitive_key(self) -> None:
        app = runtime({"ROLEPLAY_API_KEY": "secret"})
        response = app.handle(
            method="PATCH",
            target="/v1/runtime-config",
            headers=auth_headers(),
            body=json_body({"values": {"OPENAI_API_KEY": "secret-value"}}),
        )
        body = json_response(response.body)

        self.assertEqual(response.status, 400)
        self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")

    def test_runtime_config_patch_rejects_session_provider_hot_switch(self) -> None:
        app = runtime({"ROLEPLAY_API_KEY": "secret"})
        response = app.handle(
            method="PATCH",
            target="/v1/runtime-config",
            headers=auth_headers(),
            body=json_body({"values": {"SESSION_PROVIDER": "sqlite"}}),
        )
        body = json_response(response.body)

        self.assertEqual(response.status, 400)
        self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")

    def test_runtime_config_patch_rejects_http_port_hot_switch(self) -> None:
        app = runtime({"ROLEPLAY_API_KEY": "secret"})
        response = app.handle(
            method="PATCH",
            target="/v1/runtime-config",
            headers=auth_headers(),
            body=json_body({"values": {"ROLEPLAY_PORT": "8126"}}),
        )
        body = json_response(response.body)

        self.assertEqual(response.status, 400)
        self.assertEqual(body["error"]["code"], "VALIDATION_ERROR")

    def test_runtime_config_patch_does_not_commit_invalid_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "ROLEPLAY_API_KEY=secret",
                        "MODEL_PROVIDER=fake",
                        "MODEL_NAME=fake-roleplay-model",
                        "RAG_PROVIDER=local",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            app = RoleplayHttpRuntime.from_env_file(
                project_root=ROOT,
                env={"ROLEPLAY_CONFIG_FILE": str(env_path)},
            )
            response = app.handle(
                method="PATCH",
                target="/v1/runtime-config",
                headers=auth_headers(),
                body=json_body({"values": {"RAG_PROVIDER": "qdrant"}}),
            )
            saved = env_path.read_text(encoding="utf-8")
        body = json_response(response.body)

        self.assertEqual(response.status, 502)
        self.assertEqual(body["error"]["code"], "RAG_PROVIDER_ERROR")
        self.assertIn("RAG_PROVIDER=local", saved)
        self.assertNotIn("RAG_PROVIDER=qdrant", saved)


if __name__ == "__main__":
    unittest.main()
