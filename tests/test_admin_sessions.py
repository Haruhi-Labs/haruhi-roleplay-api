from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from haruhi_roleplay_api.infrastructure import RoleplayHttpRuntime


ROOT = Path(__file__).resolve().parents[1]


class AdminSessionHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime = RoleplayHttpRuntime.local(
            project_root=ROOT,
            env={
                "ROLEPLAY_API_KEY": "admin-secret",
                "MODEL_PROVIDER": "fake",
                "MODEL_NAME": "fake-roleplay-model",
                "SESSION_PROVIDER": "sqlite",
                "SESSION_SQLITE_PATH": str(
                    Path(self.temp_dir.name) / "sessions.sqlite3"
                ),
                "ACCESS_TOKEN_SQLITE_PATH": str(
                    Path(self.temp_dir.name) / "tokens.sqlite3"
                ),
            },
        )
        self.headers = {
            "Authorization": "Bearer admin-secret",
            "Content-Type": "application/json",
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_admin_can_filter_and_close_runtime_session(self) -> None:
        created = self.request("POST", "/v1/sessions", session_body())
        self.request("POST", "/v1/sessions", session_body(user_id="user-2"))
        session_id = _body(created)["data"]["session_id"]

        listed = self.request(
            "GET",
            "/v1/admin/sessions?app_id=admin-app&user_id=user-1&status=active",
        )
        closed = self.request("DELETE", f"/v1/admin/sessions/{session_id}")
        after = self.request(
            "GET",
            "/v1/admin/sessions?app_id=admin-app&user_id=user-1&status=closed",
        )

        self.assertEqual(_body(listed)["data"]["provider"], "sqlite")
        self.assertEqual(_body(listed)["data"]["total"], 1)
        self.assertEqual(_body(listed)["data"]["items"][0]["message_count"], 0)
        self.assertEqual(_body(closed)["data"]["status"], "closed")
        self.assertEqual(_body(after)["data"]["total"], 1)
        self.assertEqual(_body(after)["data"]["items"][0]["session_id"], session_id)

    def test_admin_session_filters_validate_status_and_pagination(self) -> None:
        invalid_status = self.request("GET", "/v1/admin/sessions?status=unknown")
        invalid_limit = self.request("GET", "/v1/admin/sessions?limit=201")
        invalid_offset = self.request("GET", "/v1/admin/sessions?offset=-1")

        self.assertEqual(invalid_status.status, 400)
        self.assertEqual(invalid_limit.status, 400)
        self.assertEqual(invalid_offset.status, 400)
        self.assertEqual(_body(invalid_status)["error"]["code"], "VALIDATION_ERROR")

    def test_service_token_cannot_manage_sessions(self) -> None:
        issued = self.request(
            "POST",
            "/v1/access-tokens",
            {"app_id": "admin-app", "name": "业务服务", "quota_tokens": 100},
        )
        token = _body(issued)["data"]["token"]

        response = self.runtime.handle(
            method="GET",
            target="/v1/admin/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status, 403)

    def request(self, method: str, target: str, body: dict | None = None):
        return self.runtime.handle(
            method=method,
            target=target,
            headers=self.headers,
            body=(json.dumps(body, ensure_ascii=False).encode() if body else b""),
        )


def session_body(*, user_id: str = "user-1") -> dict:
    return {
        "app_id": "admin-app",
        "user_id": user_id,
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
    }


def _body(response) -> dict:
    return json.loads(response.body.decode())


if __name__ == "__main__":
    unittest.main()
