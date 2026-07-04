from __future__ import annotations

import json
import sys
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


def chat_body(*, rag: bool = False, stream: bool = False) -> dict:
    return {
        "app_id": "web",
        "user_id": "user-1",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "message": "社团 活动 怎么安排？",
        "language": "zh-CN",
        "capabilities": {
            "rag": rag,
            "memory": False,
            "continuous_session": False,
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


if __name__ == "__main__":
    unittest.main()
