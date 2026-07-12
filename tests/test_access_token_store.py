from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from haruhi_roleplay_api.adapters.access_tokens_sqlite import SQLiteAccessTokenStore
from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import AccessTokenStatus, DTOValidationError


class SQLiteAccessTokenStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "access-tokens.sqlite3"
        self.store = SQLiteAccessTokenStore(path=self.path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_returns_secret_once_and_persists_only_hash(self) -> None:
        issued = self.store.create_token(name="订单服务", quota_tokens=1000)

        self.assertTrue(issued.secret.startswith("hrt_"))
        self.assertEqual(issued.token.name, "订单服务")
        self.assertEqual(issued.token.quotaTokens, 1000)
        self.assertEqual(issued.token.remainingTokens, 1000)
        self.assertEqual(self.store.authenticate(issued.secret), issued.token)

        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT secret_hash, token_prefix FROM access_tokens"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertNotEqual(row[0], issued.secret)
        self.assertEqual(row[1], issued.secret[:12])
        self.assertNotIn(issued.secret, self.path.read_bytes().decode("latin-1"))

    def test_list_and_get_never_return_secret(self) -> None:
        issued = self.store.create_token(name="前端网关", quota_tokens=None)

        listed = self.store.list_tokens()

        self.assertEqual(listed, (issued.token,))
        self.assertNotIn("secret", listed[0].to_mapping())
        self.assertEqual(self.store.get_token(issued.token.tokenId), issued.token)

    def test_revoke_invalidates_secret(self) -> None:
        issued = self.store.create_token(name="旧服务", quota_tokens=50)

        revoked = self.store.revoke_token(issued.token.tokenId)

        self.assertEqual(revoked.status, AccessTokenStatus.REVOKED)
        self.assertIsNone(self.store.authenticate(issued.secret))

    def test_expired_token_cannot_authenticate(self) -> None:
        expires_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        issued = self.store.create_token(
            name="短期任务",
            quota_tokens=50,
            expires_at=expires_at,
        )
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "UPDATE access_tokens SET expires_at = ? WHERE token_id = ?",
                (
                    (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                    issued.token.tokenId,
                ),
            )

        self.assertIsNone(self.store.authenticate(issued.secret))

    def test_invalid_create_input_is_rejected(self) -> None:
        with self.assertRaises(DTOValidationError):
            self.store.create_token(name="", quota_tokens=100)
        with self.assertRaises(DTOValidationError):
            self.store.create_token(name="服务", quota_tokens=0)
        with self.assertRaises(DTOValidationError):
            self.store.create_token(
                name="服务",
                quota_tokens=100,
                expires_at="2020-01-01T00:00:00+00:00",
            )

    def test_missing_token_has_stable_error(self) -> None:
        with self.assertRaises(AppError) as context:
            self.store.get_token("tok-missing")

        self.assertEqual(context.exception.code, ErrorCode.ACCESS_TOKEN_NOT_FOUND)

    def test_request_logs_are_isolated_by_token(self) -> None:
        first = self.store.create_token(name="服务一", quota_tokens=100)
        second = self.store.create_token(name="服务二", quota_tokens=100)
        self.store.record_request(
            token_id=first.token.tokenId,
            request_id="req-1",
            method="get",
            path="/v1/personas",
            status_code=200,
            duration_ms=12,
        )
        self.store.record_request(
            token_id=second.token.tokenId,
            request_id="req-2",
            method="POST",
            path="/v1/chat",
            status_code=400,
            duration_ms=8,
            error_code="VALIDATION_ERROR",
        )

        logs = self.store.list_request_logs(first.token.tokenId)

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].requestId, "req-1")
        self.assertEqual(logs[0].method, "GET")
        self.assertEqual(logs[0].path, "/v1/personas")
        self.assertNotIn("secret", logs[0].to_mapping())
        self.assertIsNotNone(self.store.get_token(first.token.tokenId).lastUsedAt)


if __name__ == "__main__":
    unittest.main()
