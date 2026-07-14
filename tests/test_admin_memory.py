from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from haruhi_roleplay_api.adapters.memory import InMemoryMemoryStore
from haruhi_roleplay_api.api.admin_memory import get_admin_memories
from haruhi_roleplay_api.infrastructure import RoleplayHttpRuntime


ROOT = Path(__file__).resolve().parents[1]


class AdminMemoryHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime = RoleplayHttpRuntime.local(
            project_root=ROOT,
            env={
                "ROLEPLAY_API_KEY": "admin-secret",
                "MODEL_PROVIDER": "fake",
                "MODEL_NAME": "fake-roleplay-model",
                "MEMORY_PROVIDER": "sqlite",
                "MEMORY_SQLITE_PATH": str(
                    Path(self.temp_dir.name) / "memories.sqlite3"
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

    def test_admin_can_create_filter_paginate_and_delete_memories(self) -> None:
        first = self.request("POST", "/v1/admin/memories", memory_body())
        self.request(
            "POST",
            "/v1/admin/memories",
            memory_body(
                user_id="user-2",
                memory_type="relationship",
                content="用户与角色约定周末见面",
            ),
        )

        listed = self.request(
            "GET",
            "/v1/admin/memories?app_id=admin-app&user_id=user-1&limit=1&offset=0",
        )
        deleted = self.request(
            "DELETE",
            f"/v1/admin/memories/{_body(first)['data']['item']['memory_id']}",
        )
        after = self.request(
            "GET",
            "/v1/admin/memories?app_id=admin-app&user_id=user-1",
        )

        self.assertEqual(first.status, 200)
        self.assertEqual(_body(listed)["data"]["provider"], "sqlite")
        self.assertEqual(_body(listed)["data"]["total"], 1)
        self.assertEqual(_body(listed)["data"]["count"], 1)
        self.assertEqual(_body(listed)["data"]["limit"], 1)
        self.assertEqual(_body(listed)["data"]["items"][0]["content"], "用户喜欢古典音乐")
        self.assertTrue(_body(deleted)["data"]["deleted"])
        self.assertEqual(_body(after)["data"]["total"], 0)

    def test_admin_memory_filters_validate_type_and_pagination(self) -> None:
        invalid_type = self.request("GET", "/v1/admin/memories?type=unknown")
        invalid_limit = self.request("GET", "/v1/admin/memories?limit=201")
        invalid_offset = self.request("GET", "/v1/admin/memories?offset=-1")

        self.assertEqual(invalid_type.status, 400)
        self.assertEqual(invalid_limit.status, 400)
        self.assertEqual(invalid_offset.status, 400)
        self.assertEqual(_body(invalid_type)["error"]["code"], "VALIDATION_ERROR")

    def test_admin_memory_uses_provider_metadata(self) -> None:
        class CustomMemoryStore(InMemoryMemoryStore):
            provider_name = "custom-memory"

        response = get_admin_memories(
            {},
            memory_store=CustomMemoryStore(),
            request_id="req-provider-metadata",
        )

        self.assertEqual(response["data"]["provider"], "custom-memory")

    def test_service_token_cannot_manage_memories(self) -> None:
        issued = self.request(
            "POST",
            "/v1/access-tokens",
            {"app_id": "admin-app", "name": "业务服务", "quota_tokens": 100},
        )
        token = _body(issued)["data"]["token"]

        response = self.runtime.handle(
            method="GET",
            target="/v1/admin/memories",
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


def memory_body(
    *,
    user_id: str = "user-1",
    memory_type: str = "user_preference",
    content: str = "用户喜欢古典音乐",
) -> dict:
    return {
        "app_id": "admin-app",
        "user_id": user_id,
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "type": memory_type,
        "content": content,
        "reason": "管理员确认这是稳定记忆",
        "confidence": 0.9,
    }


def _body(response) -> dict:
    return json.loads(response.body.decode())


if __name__ == "__main__":
    unittest.main()
