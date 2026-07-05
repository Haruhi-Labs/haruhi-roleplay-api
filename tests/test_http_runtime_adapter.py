from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.infrastructure import RoleplayHttpRuntime  # noqa: E402


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
    stream: bool = False,
    session_id: str | None = None,
    continuous_session: bool = False,
    user_id: str = "user-1",
) -> dict:
    return {
        "app_id": "web",
        "user_id": user_id,
        "session_id": session_id,
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "message": "社团 活动 怎么安排？",
        "language": "zh-CN",
        "capabilities": {
            "rag": rag,
            "memory": False,
            "continuous_session": continuous_session,
            "safety_filter": True,
            "debug_trace": True,
            "stream": stream,
        },
        "generation": {
            "model": "fake-roleplay-model",
        },
    }


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
        self.assertIn("Access-Control-Allow-Origin", response.headers)

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

    def test_post_chat_stream_returns_sse_events(self) -> None:
        response = runtime().handle(
            method="POST",
            target="/v1/chat/stream",
            headers={"content-type": "application/json"},
            body=json_body(chat_body(stream=True)),
        )
        body = response.body.decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.headers["Content-Type"],
            "text/event-stream; charset=utf-8",
        )
        self.assertIn("event: start", body)
        self.assertIn("event: delta", body)
        self.assertIn("event: usage", body)
        self.assertIn("event: done", body)

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
        app = runtime(
            {
                "ROLEPLAY_API_KEY": "secret",
                "SESSION_PROVIDER": "memory",
                "SESSION_RECENT_LIMIT": "4",
                "SESSION_SQLITE_PATH": ".data/sessions.sqlite3",
            }
        )

        response = app.handle(
            method="GET",
            target="/v1/runtime-config",
            headers=auth_headers(),
        )
        body = json_response(response.body)

        self.assertEqual(response.status, 200)
        self.assertEqual(body["data"]["values"]["SESSION_PROVIDER"], "memory")
        self.assertEqual(body["data"]["values"]["SESSION_RECENT_LIMIT"], "4")
        self.assertIn("SESSION_RECENT_LIMIT", body["data"]["configurable_keys"])
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
