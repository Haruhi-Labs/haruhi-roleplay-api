from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.application.errors import AppError, ErrorCode  # noqa: E402
from haruhi_roleplay_api.infrastructure.admin_auth import (  # noqa: E402
    AdminSessionManager,
)
from haruhi_roleplay_api.infrastructure.http_runtime import (  # noqa: E402
    RoleplayHttpRuntime,
)


ROOT = Path(__file__).resolve().parents[1]


class AdminSessionManagerTests(unittest.TestCase):
    def test_session_expires_after_idle_timeout(self) -> None:
        now = [100.0]
        manager = AdminSessionManager(
            password="strong-password",
            ttl_seconds=60,
            idle_timeout_seconds=10,
            clock=lambda: now[0],
        )
        issued = manager.login(password="strong-password", client_id="127.0.0.1")

        self.assertIsNotNone(manager.authenticate(issued.secret))
        now[0] += 11

        self.assertIsNone(manager.authenticate(issued.secret))

    def test_login_is_rate_limited_per_client(self) -> None:
        manager = AdminSessionManager(
            password="strong-password",
            attempt_limit=2,
        )

        for _ in range(2):
            with self.assertRaisesRegex(AppError, "管理员密码不正确"):
                manager.login(password="wrong", client_id="198.51.100.4")

        with self.assertRaises(AppError) as raised:
            manager.login(password="strong-password", client_id="198.51.100.4")

        self.assertEqual(raised.exception.code, ErrorCode.RATE_LIMIT_EXCEEDED)

    def test_csrf_token_is_required_for_session_mutation(self) -> None:
        manager = AdminSessionManager(password="strong-password")
        issued = manager.login(password="strong-password", client_id="127.0.0.1")
        session = manager.authenticate(issued.secret)

        self.assertIsNotNone(session)
        assert session is not None
        self.assertFalse(manager.verify_csrf(session, "wrong"))
        self.assertTrue(manager.verify_csrf(session, issued.csrf_token))


class AdminSessionHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        token_path = Path(self.temp_dir.name) / "access-tokens.sqlite3"
        self.runtime = RoleplayHttpRuntime.local(
            project_root=ROOT,
            env={
                "ROLEPLAY_API_KEY": "local-admin-password",
                "ACCESS_TOKEN_SQLITE_PATH": str(token_path),
                "MODEL_PROVIDER": "fake",
                "MODEL_NAME": "fake-roleplay-model",
            },
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_login_uses_httponly_cookie_and_session_can_read_admin_api(self) -> None:
        login = self._login()
        cookie = login.headers["Set-Cookie"]

        self.assertEqual(login.status, 201)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Path=/", cookie)
        self.assertNotIn("local-admin-password", cookie)

        response = self.runtime.handle(
            method="GET",
            target="/v1/env-config/schema",
            headers={"Cookie": _cookie_pair(cookie)},
        )

        self.assertEqual(response.status, 200)

    def test_admin_session_mutation_requires_csrf_token(self) -> None:
        login = self._login()
        payload = _decode(login.body)
        cookie = _cookie_pair(login.headers["Set-Cookie"])
        token_body = {
            "app_id": "admin-test",
            "name": "后台测试令牌",
            "quota_tokens": 1000,
        }

        rejected = self.runtime.handle(
            method="POST",
            target="/v1/access-tokens",
            headers={"Cookie": cookie},
            body=json.dumps(token_body).encode("utf-8"),
        )
        accepted = self.runtime.handle(
            method="POST",
            target="/v1/access-tokens",
            headers={
                "Cookie": cookie,
                "X-CSRF-Token": payload["data"]["csrf_token"],
            },
            body=json.dumps(token_body).encode("utf-8"),
        )

        self.assertEqual(rejected.status, 403)
        self.assertEqual(accepted.status, 200)
        self.assertTrue(_decode(accepted.body)["ok"])

    def test_logout_invalidates_cookie_session(self) -> None:
        login = self._login()
        payload = _decode(login.body)
        cookie = _cookie_pair(login.headers["Set-Cookie"])

        logout = self.runtime.handle(
            method="DELETE",
            target="/v1/admin/session",
            headers={
                "Cookie": cookie,
                "X-CSRF-Token": payload["data"]["csrf_token"],
            },
        )
        after = self.runtime.handle(
            method="GET",
            target="/v1/admin/session",
            headers={"Cookie": cookie},
        )

        self.assertEqual(logout.status, 200)
        self.assertIn("Max-Age=0", logout.headers["Set-Cookie"])
        self.assertEqual(after.status, 401)

    def test_responses_include_browser_security_headers(self) -> None:
        response = self.runtime.handle(
            method="GET",
            target="/config",
            headers={},
        )

        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_admin_page_is_served_and_session_can_read_safe_overview_routes(self) -> None:
        page = self.runtime.handle(method="GET", target="/admin", headers={})
        login = self._login()
        cookie = _cookie_pair(login.headers["Set-Cookie"])

        health = self.runtime.handle(
            method="GET",
            target="/health",
            headers={"Cookie": cookie},
        )
        personas = self.runtime.handle(
            method="GET",
            target="/v1/personas",
            headers={"Cookie": cookie},
        )

        self.assertEqual(page.status, 200)
        self.assertIn(b"Haruhi Control Room", page.body)
        self.assertEqual(health.status, 200)
        self.assertEqual(personas.status, 200)

    def _login(self):
        return self.runtime.handle(
            method="POST",
            target="/v1/admin/session",
            headers={"X-Roleplay-Client-IP": "127.0.0.1"},
            body=json.dumps({"password": "local-admin-password"}).encode("utf-8"),
        )


def _decode(body: bytes) -> dict:
    return json.loads(body.decode("utf-8"))


def _cookie_pair(set_cookie: str) -> str:
    return set_cookie.split(";", 1)[0]


if __name__ == "__main__":
    unittest.main()
