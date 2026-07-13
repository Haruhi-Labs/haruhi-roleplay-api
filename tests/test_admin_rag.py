from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from haruhi_roleplay_api.infrastructure import RoleplayHttpRuntime


ROOT = Path(__file__).resolve().parents[1]


class AdminRagHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime = RoleplayHttpRuntime.local(
            project_root=ROOT,
            env={
                "ROLEPLAY_API_KEY": "admin-secret",
                "MODEL_PROVIDER": "fake",
                "MODEL_NAME": "fake-roleplay-model",
                "RAG_PROVIDER": "local",
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

    def test_admin_can_ingest_list_search_and_delete_real_rag_document(self) -> None:
        imported = self.request(
            "POST",
            "/v1/admin/rag/documents",
            rag_document_body(),
        )
        listed = self.request("GET", "/v1/admin/rag/documents?app_id=admin-app")
        searched = self.request(
            "POST",
            "/v1/admin/rag/search",
            rag_search_body(),
        )
        deleted = self.request(
            "DELETE",
            "/v1/admin/rag/documents/admin-doc?app_id=admin-app",
        )
        after = self.request("GET", "/v1/admin/rag/documents?app_id=admin-app")

        self.assertEqual(imported.status, 200)
        self.assertEqual(_body(listed)["data"]["count"], 1)
        self.assertEqual(_body(listed)["data"]["items"][0]["title"], "后台知识")
        self.assertEqual(_body(searched)["data"]["hit_count"], 1)
        self.assertGreater(_body(deleted)["data"]["removed_chunks"], 0)
        self.assertEqual(_body(after)["data"]["count"], 0)

    def test_delete_requires_explicit_app_scope(self) -> None:
        self.request("POST", "/v1/admin/rag/documents", rag_document_body())

        response = self.request("DELETE", "/v1/admin/rag/documents/admin-doc")

        self.assertEqual(response.status, 400)
        self.assertEqual(_body(response)["error"]["code"], "VALIDATION_ERROR")

    def test_service_token_cannot_manage_rag_documents(self) -> None:
        issued = self.request(
            "POST",
            "/v1/access-tokens",
            {"app_id": "admin-app", "name": "业务服务", "quota_tokens": 100},
        )
        token = _body(issued)["data"]["token"]

        response = self.runtime.handle(
            method="GET",
            target="/v1/admin/rag/documents",
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


def rag_document_body() -> dict:
    return {
        "app_id": "admin-app",
        "document_id": "admin-doc",
        "title": "后台知识",
        "source_type": "timeline",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "timeline": "mid_late",
        "spoiler_level": 2,
        "language": "zh-CN",
        "content": "后台知识：社团活动将在放学后开始。",
    }


def rag_search_body() -> dict:
    return {
        "app_id": "admin-app",
        "user_id": "admin-user",
        "character_id": "haruhi",
        "persona_mode": "mid_late_haruhi",
        "query": "社团活动",
        "top_k": 5,
        "filters": {
            "source_types": ["timeline"],
            "timelines": ["mid_late"],
            "spoiler_level_max": 2,
            "language": "zh-CN",
        },
    }


def _body(response) -> dict:
    return json.loads(response.body.decode())


if __name__ == "__main__":
    unittest.main()
