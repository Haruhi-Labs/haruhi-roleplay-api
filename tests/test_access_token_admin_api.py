from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.infrastructure import (
    HttpRuntimeStreamResponse,
    RoleplayHttpRuntime,
)


ROOT = Path(__file__).resolve().parents[1]


def json_body(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def response_json(body: bytes) -> dict:
    return json.loads(body.decode("utf-8"))


def chat_body(*, stream: bool = False) -> dict:
    return {
        "app_id": "service-app",
        "user_id": "user-1",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "message": "今天安排什么活动？",
        "language": "zh-CN",
        "capabilities": {
            "rag": False,
            "memory": False,
            "continuous_session": False,
            "safety_filter": True,
            "debug_trace": False,
            "stream": stream,
        },
        "generation": {"model": "fake-roleplay-model"},
    }


class FailingStreamingRouter:
    def stream(self, messages, generation=None):
        del messages, generation
        yield from ()
        raise AppError(
            code=ErrorCode.MODEL_PROVIDER_ERROR,
            message="stream provider failed",
        )


class AccessTokenAdminApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.token_db_path = Path(self.temp_dir.name) / "tokens.sqlite3"
        self.runtime = RoleplayHttpRuntime.local(
            project_root=ROOT,
            env={
                "MODEL_PROVIDER": "fake",
                "MODEL_NAME": "fake-roleplay-model",
                "ROLEPLAY_API_KEY": "admin-secret",
                "ACCESS_TOKEN_SQLITE_PATH": str(self.token_db_path),
            },
        )
        self.admin_headers = {
            "Authorization": "Bearer admin-secret",
            "Content-Type": "application/json",
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def request(
        self,
        method: str,
        target: str,
        *,
        body: dict | None = None,
        headers: dict[str, str] | None = None,
    ):
        return self.runtime.handle(
            method=method,
            target=target,
            headers=headers or self.admin_headers,
            body=json_body(body or {}) if body is not None else b"",
        )

    def issue_service_token(
        self,
        *,
        app_id: str = "service-app",
        quota_tokens: int = 5000,
    ) -> dict:
        response = self.request(
            "POST",
            "/v1/access-tokens",
            body={
                "app_id": app_id,
                "name": f"{app_id}-service",
                "quota_tokens": quota_tokens,
            },
        )
        self.assertEqual(response.status, 200)
        return response_json(response.body)["data"]

    def test_admin_can_create_list_get_and_revoke_token(self) -> None:
        created_response = self.request(
            "POST",
            "/v1/access-tokens",
            body={
                "app_id": "order-app",
                "name": "订单服务",
                "quota_tokens": 5000,
            },
        )
        created = response_json(created_response.body)["data"]

        self.assertEqual(created_response.status, 200)
        self.assertTrue(created["token"].startswith("hrt_"))
        self.assertEqual(created["app_id"], "order-app")
        self.assertEqual(created["quota_tokens"], 5000)

        listed = response_json(
            self.request("GET", "/v1/access-tokens").body
        )["data"]
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["items"][0]["app_id"], "order-app")
        self.assertNotIn("token", listed["items"][0])

        token_id = created["token_id"]
        fetched = response_json(
            self.request("GET", f"/v1/access-tokens/{token_id}").body
        )["data"]
        self.assertEqual(fetched["token_id"], token_id)
        self.assertEqual(fetched["app_id"], "order-app")
        self.assertNotIn("token", fetched)

        revoked = response_json(
            self.request("DELETE", f"/v1/access-tokens/{token_id}").body
        )["data"]
        self.assertEqual(revoked["status"], "revoked")

    def test_management_requires_admin_key(self) -> None:
        response = self.request(
            "GET",
            "/v1/access-tokens",
            headers={"Authorization": "Bearer wrong"},
        )

        self.assertEqual(response.status, 401)
        self.assertEqual(
            response_json(response.body)["error"]["code"],
            "AUTH_INVALID_API_KEY",
        )

    def test_either_supported_header_can_carry_valid_admin_key(self) -> None:
        response = self.request(
            "GET",
            "/v1/access-tokens",
            headers={
                "Authorization": "Bearer wrong",
                "X-API-Key": "admin-secret",
            },
        )

        self.assertEqual(response.status, 200)

    def test_invalid_quota_returns_validation_error(self) -> None:
        response = self.request(
            "POST",
            "/v1/access-tokens",
            body={"app_id": "service-app", "name": "服务", "quota_tokens": 0},
        )

        self.assertEqual(response.status, 400)
        self.assertEqual(
            response_json(response.body)["error"]["code"],
            "VALIDATION_ERROR",
        )

    def test_create_requires_app_id(self) -> None:
        response = self.request(
            "POST",
            "/v1/access-tokens",
            body={"name": "无作用域服务", "quota_tokens": 100},
        )

        self.assertEqual(response.status, 400)
        self.assertEqual(
            response_json(response.body)["error"]["code"],
            "VALIDATION_ERROR",
        )

    def test_service_token_can_call_business_api_and_has_request_log(self) -> None:
        created = response_json(
            self.request(
                "POST",
                "/v1/access-tokens",
                body={
                    "app_id": "service-app",
                    "name": "公开网关",
                    "quota_tokens": 5000,
                },
            ).body
        )["data"]
        service_headers = {"Authorization": f"Bearer {created['token']}"}

        response = self.request(
            "GET",
            "/v1/personas",
            headers=service_headers,
        )

        self.assertEqual(response.status, 200)
        logs = response_json(
            self.request(
                "GET",
                f"/v1/access-tokens/{created['token_id']}/logs",
            ).body
        )["data"]
        self.assertEqual(logs["count"], 1)
        self.assertEqual(logs["items"][0]["path"], "/v1/personas")
        self.assertEqual(logs["items"][0]["status_code"], 200)

    def test_service_token_cannot_call_management_api(self) -> None:
        created = response_json(
            self.request(
                "POST",
                "/v1/access-tokens",
                body={
                    "app_id": "service-app",
                    "name": "业务服务",
                    "quota_tokens": 5000,
                },
            ).body
        )["data"]

        response = self.request(
            "GET",
            "/v1/access-tokens",
            headers={"X-API-Key": created["token"]},
        )

        self.assertEqual(response.status, 403)
        self.assertEqual(
            response_json(response.body)["error"]["code"],
            "AUTH_PERMISSION_DENIED",
        )

    def test_revoked_service_token_is_rejected(self) -> None:
        created = response_json(
            self.request(
                "POST",
                "/v1/access-tokens",
                body={
                    "app_id": "service-app",
                    "name": "临时服务",
                    "quota_tokens": 5000,
                },
            ).body
        )["data"]
        self.request("DELETE", f"/v1/access-tokens/{created['token_id']}")

        response = self.request(
            "GET",
            "/v1/personas",
            headers={"Authorization": f"Bearer {created['token']}"},
        )

        self.assertEqual(response.status, 401)

    def test_chat_usage_is_charged_and_exhausted_quota_returns_429(self) -> None:
        created = response_json(
            self.request(
                "POST",
                "/v1/access-tokens",
                body={
                    "app_id": "service-app",
                    "name": "限额服务",
                    "quota_tokens": 1,
                },
            ).body
        )["data"]
        service_headers = {"Authorization": f"Bearer {created['token']}"}

        first = self.request(
            "POST",
            "/v1/chat",
            body=chat_body(),
            headers=service_headers,
        )
        first_data = response_json(first.body)["data"]
        second = self.request(
            "POST",
            "/v1/chat",
            body=chat_body(),
            headers=service_headers,
        )

        self.assertEqual(first.status, 200)
        self.assertGreater(first_data["usage"]["total_tokens"], 0)
        self.assertEqual(second.status, 429)
        self.assertEqual(
            response_json(second.body)["error"]["code"],
            "ACCESS_TOKEN_QUOTA_EXCEEDED",
        )

        token = response_json(
            self.request(
                "GET",
                f"/v1/access-tokens/{created['token_id']}",
            ).body
        )["data"]
        self.assertEqual(token["total_tokens"], first_data["usage"]["total_tokens"])
        self.assertEqual(token["remaining_tokens"], 0)

        logs = response_json(
            self.request(
                "GET",
                f"/v1/access-tokens/{created['token_id']}/logs",
            ).body
        )["data"]["items"]
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["error_code"], "ACCESS_TOKEN_QUOTA_EXCEEDED")
        self.assertEqual(logs[1]["total_tokens"], token["total_tokens"])

    def test_admin_can_change_quota_and_restore_chat_access(self) -> None:
        created = response_json(
            self.request(
                "POST",
                "/v1/access-tokens",
                body={
                    "app_id": "service-app",
                    "name": "可调额度服务",
                    "quota_tokens": 1,
                },
            ).body
        )["data"]
        service_headers = {"X-API-Key": created["token"]}
        self.request(
            "POST",
            "/v1/chat",
            body=chat_body(),
            headers=service_headers,
        )

        updated = response_json(
            self.request(
                "PATCH",
                f"/v1/access-tokens/{created['token_id']}",
                body={"quota_tokens": 10000},
            ).body
        )["data"]
        response = self.request(
            "POST",
            "/v1/chat/stream",
            body=chat_body(stream=True),
            headers=service_headers,
        )

        self.assertEqual(updated["quota_tokens"], 10000)
        self.assertEqual(response.status, 200)
        self.assertIsInstance(response, HttpRuntimeStreamResponse)
        events = tuple(response.events)
        usage = next(event["data"] for event in events if event["event"] == "usage")
        self.assertGreater(usage["total_tokens"], 0)
        token = response_json(
            self.request(
                "GET",
                f"/v1/access-tokens/{created['token_id']}",
            ).body
        )["data"]
        self.assertGreater(token["total_tokens"], updated["total_tokens"])

    def test_stream_provider_error_code_is_recorded_from_nested_event(self) -> None:
        created = self.issue_service_token()
        self.runtime._model_router = FailingStreamingRouter()

        response = self.request(
            "POST",
            "/v1/chat/stream",
            body=chat_body(stream=True),
            headers={"Authorization": f"Bearer {created['token']}"},
        )

        self.assertIsInstance(response, HttpRuntimeStreamResponse)
        events = tuple(response.events)
        self.assertEqual(events[-1]["event"], "error")
        self.assertEqual(
            events[-1]["data"]["error"]["code"],
            "MODEL_PROVIDER_ERROR",
        )

        logs = response_json(
            self.request(
                "GET",
                f"/v1/access-tokens/{created['token_id']}/logs",
            ).body
        )["data"]["items"]
        self.assertEqual(logs[0]["error_code"], "MODEL_PROVIDER_ERROR")

    def test_service_token_rejects_cross_app_body_routes_and_audits_denials(self) -> None:
        created = self.issue_service_token()
        service_headers = {"Authorization": f"Bearer {created['token']}"}
        routes = (
            ("POST", "/v1/sessions"),
            ("POST", "/v1/chat"),
            ("POST", "/v1/rag/documents"),
            ("POST", "/v1/rag/search"),
        )

        for method, path in routes:
            with self.subTest(path=path):
                response = self.request(
                    method,
                    path,
                    body={"app_id": "other-app"},
                    headers=service_headers,
                )
                self.assertEqual(response.status, 403)
                self.assertEqual(
                    response_json(response.body)["error"]["code"],
                    "AUTH_PERMISSION_DENIED",
                )

        logs = response_json(
            self.request(
                "GET",
                f"/v1/access-tokens/{created['token_id']}/logs",
            ).body
        )["data"]["items"]
        self.assertEqual(len(logs), len(routes))
        self.assertTrue(
            all(log["error_code"] == "AUTH_PERMISSION_DENIED" for log in logs)
        )
        self.assertTrue(all("app_id" not in log for log in logs))

    def test_service_token_rejects_cross_app_memory_query(self) -> None:
        created = self.issue_service_token()
        routes = (
            ("GET", "/v1/memory/user-1?app_id=other-app&character_id=haruhi"),
            (
                "DELETE",
                "/v1/memory/user-1/mem-1?app_id=other-app&character_id=haruhi",
            ),
        )

        for method, target in routes:
            with self.subTest(method=method):
                response = self.request(
                    method,
                    target,
                    headers={"X-API-Key": created["token"]},
                )
                self.assertEqual(response.status, 403)
                self.assertEqual(
                    response_json(response.body)["error"]["code"],
                    "AUTH_PERMISSION_DENIED",
                )

    def test_cross_app_stream_is_rejected_before_model_usage(self) -> None:
        created = self.issue_service_token()
        body = chat_body(stream=True)
        body["app_id"] = "other-app"

        response = self.request(
            "POST",
            "/v1/chat/stream",
            body=body,
            headers={"Authorization": f"Bearer {created['token']}"},
        )

        self.assertEqual(response.status, 403)
        self.assertNotIsInstance(response, HttpRuntimeStreamResponse)
        token = response_json(
            self.request(
                "GET",
                f"/v1/access-tokens/{created['token_id']}",
            ).body
        )["data"]
        self.assertEqual(token["total_tokens"], 0)

    def test_legacy_unscoped_token_cannot_call_app_scoped_route(self) -> None:
        created = self.issue_service_token()
        with closing(sqlite3.connect(self.token_db_path)) as connection, connection:
            connection.execute(
                "UPDATE access_tokens SET app_id = NULL WHERE token_id = ?",
                (created["token_id"],),
            )

        response = self.request(
            "POST",
            "/v1/sessions",
            body={
                "app_id": "service-app",
                "user_id": "user-1",
                "character_id": "haruhi",
                "persona_mode": "mid_late_haruhi",
            },
            headers={"Authorization": f"Bearer {created['token']}"},
        )

        self.assertEqual(response.status, 403)
        self.assertEqual(
            response_json(response.body)["error"]["code"],
            "AUTH_PERMISSION_DENIED",
        )

    def test_admin_key_can_call_business_route_for_any_app(self) -> None:
        body = chat_body()
        body["app_id"] = "admin-selected-app"

        response = self.request("POST", "/v1/chat", body=body)

        self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()
