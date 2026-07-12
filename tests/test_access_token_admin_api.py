from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from haruhi_roleplay_api.infrastructure import RoleplayHttpRuntime


ROOT = Path(__file__).resolve().parents[1]


def json_body(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def response_json(body: bytes) -> dict:
    return json.loads(body.decode("utf-8"))


class AccessTokenAdminApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime = RoleplayHttpRuntime.local(
            project_root=ROOT,
            env={
                "MODEL_PROVIDER": "fake",
                "MODEL_NAME": "fake-roleplay-model",
                "ROLEPLAY_API_KEY": "admin-secret",
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

    def test_admin_can_create_list_get_and_revoke_token(self) -> None:
        created_response = self.request(
            "POST",
            "/v1/access-tokens",
            body={"name": "订单服务", "quota_tokens": 5000},
        )
        created = response_json(created_response.body)["data"]

        self.assertEqual(created_response.status, 200)
        self.assertTrue(created["token"].startswith("hrt_"))
        self.assertEqual(created["quota_tokens"], 5000)

        listed = response_json(
            self.request("GET", "/v1/access-tokens").body
        )["data"]
        self.assertEqual(listed["count"], 1)
        self.assertNotIn("token", listed["items"][0])

        token_id = created["token_id"]
        fetched = response_json(
            self.request("GET", f"/v1/access-tokens/{token_id}").body
        )["data"]
        self.assertEqual(fetched["token_id"], token_id)
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

    def test_invalid_quota_returns_validation_error(self) -> None:
        response = self.request(
            "POST",
            "/v1/access-tokens",
            body={"name": "服务", "quota_tokens": 0},
        )

        self.assertEqual(response.status, 400)
        self.assertEqual(
            response_json(response.body)["error"]["code"],
            "VALIDATION_ERROR",
        )


if __name__ == "__main__":
    unittest.main()
