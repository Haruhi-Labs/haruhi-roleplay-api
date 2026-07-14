from __future__ import annotations

import json
import tempfile
import unittest
from http.cookies import SimpleCookie
from pathlib import Path

from haruhi_roleplay_api.infrastructure import RoleplayHttpRuntime


ROOT = Path(__file__).resolve().parents[1]


class AdminAuditHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime = RoleplayHttpRuntime.local(
            project_root=ROOT,
            env={
                "ROLEPLAY_API_KEY": "admin-secret",
                "MODEL_PROVIDER": "fake",
                "MODEL_NAME": "fake-roleplay-model",
                "ACCESS_TOKEN_SQLITE_PATH": str(
                    Path(self.temp_dir.name) / "tokens.sqlite3"
                ),
            },
        )
        self.admin_headers = {
            "Authorization": "Bearer admin-secret",
            "Content-Type": "application/json",
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_admin_key_mutation_is_recorded_without_request_body(self) -> None:
        created = self.request(
            "POST",
            "/v1/access-tokens",
            {"app_id": "audit-app", "name": "审计服务", "quota_tokens": 100},
        )

        logs = self.request("GET", "/v1/admin/audit-logs?limit=20")
        items = _body(logs)["data"]["items"]
        event = next(item for item in items if item["action"] == "service_token.create")
        serialized = json.dumps(items, ensure_ascii=False)

        self.assertEqual(created.status, 200)
        self.assertEqual(event["actor"], "admin_key")
        self.assertEqual(event["resource_type"], "service_token")
        self.assertEqual(event["outcome"], "success")
        self.assertNotIn(_body(created)["data"]["token"], serialized)
        self.assertNotIn("audit-app", serialized)

    def test_browser_session_and_failed_login_are_distinguished(self) -> None:
        failed = self.runtime.handle(
            method="POST",
            target="/v1/admin/session",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"password": "wrong-password"}).encode(),
        )
        login = self.runtime.handle(
            method="POST",
            target="/v1/admin/session",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"password": "admin-secret"}).encode(),
        )
        cookie = _cookie_header(login.headers["Set-Cookie"])
        csrf = _body(login)["data"]["csrf_token"]
        self.runtime.handle(
            method="POST",
            target="/v1/access-tokens",
            headers={
                "Content-Type": "application/json",
                "Cookie": cookie,
                "X-CSRF-Token": csrf,
            },
            body=json.dumps(
                {"app_id": "browser-app", "name": "浏览器服务", "quota_tokens": 100}
            ).encode(),
        )

        logs = self.request("GET", "/v1/admin/audit-logs?limit=20")
        items = _body(logs)["data"]["items"]
        login_events = [item for item in items if item["action"] == "admin.login"]
        browser_create = next(
            item
            for item in items
            if item["action"] == "service_token.create"
            and item["actor"] == "admin_session"
        )

        self.assertEqual(failed.status, 401)
        self.assertEqual({item["outcome"] for item in login_events}, {"success", "failed"})
        self.assertEqual(browser_create["outcome"], "success")

    def test_service_token_cannot_read_admin_audit_log(self) -> None:
        issued = self.request(
            "POST",
            "/v1/access-tokens",
            {"app_id": "audit-app", "name": "业务服务", "quota_tokens": 100},
        )
        token = _body(issued)["data"]["token"]

        response = self.runtime.handle(
            method="GET",
            target="/v1/admin/audit-logs",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status, 403)

    def request(self, method: str, target: str, body: dict | None = None):
        return self.runtime.handle(
            method=method,
            target=target,
            headers=self.admin_headers,
            body=(json.dumps(body, ensure_ascii=False).encode() if body else b""),
        )


def _cookie_header(set_cookie: str) -> str:
    cookie = SimpleCookie()
    cookie.load(set_cookie)
    morsel = next(iter(cookie.values()))
    return f"{morsel.key}={morsel.value}"


def _body(response) -> dict:
    return json.loads(response.body.decode())


if __name__ == "__main__":
    unittest.main()
