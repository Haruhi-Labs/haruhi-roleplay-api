from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
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
        issued = self.store.create_token(
            app_id="order-app",
            name="订单服务",
            quota_tokens=1000,
        )

        self.assertTrue(issued.secret.startswith("hrt_"))
        self.assertEqual(issued.token.appId, "order-app")
        self.assertEqual(issued.token.name, "订单服务")
        self.assertEqual(issued.token.quotaTokens, 1000)
        self.assertEqual(issued.token.remainingTokens, 1000)
        self.assertEqual(self.store.authenticate(issued.secret), issued.token)

        with closing(sqlite3.connect(self.path)) as connection, connection:
            row = connection.execute(
                "SELECT app_id, secret_hash, token_prefix FROM access_tokens"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "order-app")
        self.assertNotEqual(row[1], issued.secret)
        self.assertEqual(row[2], issued.secret[:12])
        self.assertNotIn(issued.secret, self.path.read_bytes().decode("latin-1"))

    def test_list_and_get_never_return_secret(self) -> None:
        issued = self.store.create_token(
            app_id="web-app",
            name="前端网关",
            quota_tokens=None,
        )

        listed = self.store.list_tokens()

        self.assertEqual(listed, (issued.token,))
        self.assertNotIn("secret", listed[0].to_mapping())
        self.assertEqual(self.store.get_token(issued.token.tokenId), issued.token)

    def test_revoke_invalidates_secret(self) -> None:
        issued = self.store.create_token(
            app_id="legacy-app",
            name="旧服务",
            quota_tokens=50,
        )

        revoked = self.store.revoke_token(issued.token.tokenId)

        self.assertEqual(revoked.status, AccessTokenStatus.REVOKED)
        self.assertIsNone(self.store.authenticate(issued.secret))

    def test_expired_token_cannot_authenticate(self) -> None:
        expires_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        issued = self.store.create_token(
            app_id="short-lived-app",
            name="短期任务",
            quota_tokens=50,
            expires_at=expires_at,
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
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
            self.store.create_token(app_id="app", name="", quota_tokens=100)
        with self.assertRaises(DTOValidationError):
            self.store.create_token(app_id="", name="服务", quota_tokens=100)
        with self.assertRaises(DTOValidationError):
            self.store.create_token(app_id="app", name="服务", quota_tokens=0)
        with self.assertRaises(DTOValidationError):
            self.store.create_token(
                app_id="app",
                name="服务",
                quota_tokens=100,
                expires_at="2020-01-01T00:00:00+00:00",
            )

    def test_missing_token_has_stable_error(self) -> None:
        with self.assertRaises(AppError) as context:
            self.store.get_token("tok-missing")

        self.assertEqual(context.exception.code, ErrorCode.ACCESS_TOKEN_NOT_FOUND)

    def test_request_logs_are_isolated_by_token(self) -> None:
        first = self.store.create_token(
            app_id="app-one",
            name="服务一",
            quota_tokens=100,
        )
        second = self.store.create_token(
            app_id="app-two",
            name="服务二",
            quota_tokens=100,
        )
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

    def test_request_logs_keep_insertion_order_when_timestamps_match(self) -> None:
        issued = self.store.create_token(
            app_id="audit-app",
            name="审计服务",
            quota_tokens=100,
        )
        for request_id in ("req-first", "req-second"):
            self.store.record_request(
                token_id=issued.token.tokenId,
                request_id=request_id,
                method="GET",
                path="/health",
                status_code=200,
                duration_ms=1,
            )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                """
                UPDATE access_token_request_logs
                SET created_at = '2026-07-14T00:00:00+00:00',
                    log_id = CASE request_id
                        WHEN 'req-first' THEN 'log-z'
                        ELSE 'log-a'
                    END
                WHERE token_id = ?
                """,
                (issued.token.tokenId,),
            )

        logs = self.store.list_request_logs(issued.token.tokenId)

        self.assertEqual(
            [log.requestId for log in logs],
            ["req-second", "req-first"],
        )

    def test_model_usage_is_accumulated_and_quota_is_enforced(self) -> None:
        issued = self.store.create_token(
            app_id="limited-app",
            name="有限服务",
            quota_tokens=10,
        )
        self.store.record_request(
            token_id=issued.token.tokenId,
            request_id="req-usage",
            method="POST",
            path="/v1/chat",
            status_code=200,
            duration_ms=20,
            prompt_tokens=7,
            completion_tokens=3,
        )

        token = self.store.get_token(issued.token.tokenId)
        self.assertEqual(token.promptTokens, 7)
        self.assertEqual(token.completionTokens, 3)
        self.assertEqual(token.totalTokens, 10)
        self.assertEqual(token.remainingTokens, 0)
        with self.assertRaises(AppError) as context:
            self.store.ensure_quota_available(issued.token.tokenId)
        self.assertEqual(
            context.exception.code,
            ErrorCode.ACCESS_TOKEN_QUOTA_EXCEEDED,
        )

        updated = self.store.update_quota(
            issued.token.tokenId,
            quota_tokens=20,
        )
        self.assertEqual(updated.remainingTokens, 10)
        self.store.ensure_quota_available(issued.token.tokenId)

        unlimited = self.store.update_quota(
            issued.token.tokenId,
            quota_tokens=None,
        )
        self.assertIsNone(unlimited.quotaTokens)
        self.assertIsNone(unlimited.remainingTokens)

    def test_period_quotas_can_be_configured_independently_or_together(self) -> None:
        daily_only = self.store.create_token(
            app_id="daily-app",
            name="每日限额服务",
            quota_tokens=None,
            daily_quota_tokens=100,
        ).token
        weekly_only = self.store.create_token(
            app_id="weekly-app",
            name="每周限额服务",
            quota_tokens=None,
            weekly_quota_tokens=700,
        ).token
        combined = self.store.create_token(
            app_id="combined-app",
            name="组合限额服务",
            quota_tokens=3000,
            daily_quota_tokens=200,
            weekly_quota_tokens=1000,
        ).token

        self.assertIsNone(daily_only.quotaTokens)
        self.assertEqual(daily_only.dailyRemainingTokens, 100)
        self.assertIsNone(daily_only.weeklyQuotaTokens)
        self.assertEqual(weekly_only.weeklyRemainingTokens, 700)
        self.assertEqual(combined.remainingTokens, 3000)
        self.assertEqual(combined.dailyRemainingTokens, 200)
        self.assertEqual(combined.weeklyRemainingTokens, 1000)
        self.assertEqual(combined.exhaustedQuotaScopes, ())
        self.assertTrue(combined.dailyResetAt.endswith("00:00:00+00:00"))
        self.assertTrue(combined.weeklyResetAt.endswith("00:00:00+00:00"))

    def test_each_configured_quota_scope_is_enforced_and_can_be_updated(self) -> None:
        issued = self.store.create_token(
            app_id="limited-app",
            name="多周期限额服务",
            quota_tokens=None,
            daily_quota_tokens=10,
            weekly_quota_tokens=20,
        )
        self.store.record_request(
            token_id=issued.token.tokenId,
            request_id="req-usage",
            method="POST",
            path="/v1/chat",
            status_code=200,
            duration_ms=20,
            prompt_tokens=7,
            completion_tokens=3,
        )

        exhausted_daily = self.store.get_token(issued.token.tokenId)
        self.assertEqual(exhausted_daily.dailyTokens, 10)
        self.assertEqual(exhausted_daily.weeklyTokens, 10)
        self.assertEqual(exhausted_daily.exhaustedQuotaScopes, ("daily",))
        with self.assertRaises(AppError):
            self.store.ensure_quota_available(issued.token.tokenId)

        restored = self.store.update_quotas(
            issued.token.tokenId,
            quota_tokens=None,
            daily_quota_tokens=20,
            weekly_quota_tokens=20,
        )
        self.assertEqual(restored.dailyRemainingTokens, 10)
        self.store.ensure_quota_available(issued.token.tokenId)

        exhausted_weekly = self.store.update_quotas(
            issued.token.tokenId,
            quota_tokens=None,
            daily_quota_tokens=20,
            weekly_quota_tokens=10,
        )
        self.assertEqual(exhausted_weekly.exhaustedQuotaScopes, ("weekly",))
        with self.assertRaises(AppError) as context:
            self.store.ensure_quota_available(issued.token.tokenId)
        self.assertEqual(
            context.exception.code,
            ErrorCode.ACCESS_TOKEN_QUOTA_EXCEEDED,
        )

    def test_partial_quota_update_preserves_omitted_scopes(self) -> None:
        issued = self.store.create_token(
            app_id="partial-update-app",
            name="部分额度更新服务",
            quota_tokens=1000,
            daily_quota_tokens=100,
            weekly_quota_tokens=500,
        )

        updated = self.store.update_quotas(
            issued.token.tokenId,
            daily_quota_tokens=200,
        )

        self.assertEqual(updated.quotaTokens, 1000)
        self.assertEqual(updated.dailyQuotaTokens, 200)
        self.assertEqual(updated.weeklyQuotaTokens, 500)

    def test_period_usage_resets_without_losing_lifecycle_usage(self) -> None:
        issued = self.store.create_token(
            app_id="reset-app",
            name="窗口重置服务",
            quota_tokens=100,
            daily_quota_tokens=5,
            weekly_quota_tokens=5,
        )
        self.store.record_request(
            token_id=issued.token.tokenId,
            request_id="req-old",
            method="POST",
            path="/v1/chat",
            status_code=200,
            duration_ms=20,
            prompt_tokens=3,
            completion_tokens=2,
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                """
                UPDATE access_token_request_logs
                SET created_at = ?
                WHERE token_id = ?
                """,
                (
                    (datetime.now(UTC) - timedelta(days=8)).isoformat(),
                    issued.token.tokenId,
                ),
            )

        reset = self.store.get_token(issued.token.tokenId)

        self.assertEqual(reset.totalTokens, 5)
        self.assertEqual(reset.remainingTokens, 95)
        self.assertEqual(reset.dailyTokens, 0)
        self.assertEqual(reset.weeklyTokens, 0)
        self.assertEqual(reset.dailyRemainingTokens, 5)
        self.assertEqual(reset.weeklyRemainingTokens, 5)
        self.store.ensure_quota_available(issued.token.tokenId)

    def test_global_usage_aggregates_daily_service_and_route_metrics(self) -> None:
        first = self.store.create_token(
            app_id="app-one",
            name="服务一",
            quota_tokens=1000,
        )
        second = self.store.create_token(
            app_id="app-two",
            name="服务二",
            quota_tokens=None,
        )
        self.store.record_request(
            token_id=first.token.tokenId,
            request_id="req-chat",
            method="POST",
            path="/v1/chat",
            status_code=200,
            duration_ms=20,
            prompt_tokens=7,
            completion_tokens=3,
        )
        self.store.record_request(
            token_id=second.token.tokenId,
            request_id="req-error",
            method="POST",
            path="/v1/chat",
            status_code=502,
            duration_ms=40,
            error_code="MODEL_PROVIDER_ERROR",
        )

        overview = self.store.usage_overview(days=7)
        logs = self.store.list_all_request_logs(limit=10)

        self.assertEqual(overview.periodDays, 7)
        self.assertEqual(overview.requestCount, 2)
        self.assertEqual(overview.errorCount, 1)
        self.assertEqual(overview.errorRate, 0.5)
        self.assertEqual(overview.totalTokens, 10)
        self.assertEqual(overview.averageDurationMs, 30)
        self.assertEqual(overview.activeServiceCount, 2)
        self.assertEqual(len(overview.daily), 7)
        self.assertEqual(overview.daily[-1].requestCount, 2)
        self.assertEqual({item.appId for item in overview.services}, {"app-one", "app-two"})
        self.assertEqual(overview.routes[0].path, "/v1/chat")
        self.assertEqual(len(logs), 2)

    def test_usage_period_is_bounded(self) -> None:
        with self.assertRaisesRegex(DTOValidationError, "between 1 and 90"):
            self.store.usage_overview(days=0)
        with self.assertRaisesRegex(DTOValidationError, "between 1 and 90"):
            self.store.usage_overview(days=91)

    def test_legacy_database_migration_preserves_token_usage_and_logs(self) -> None:
        self.temp_dir.cleanup()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "legacy-access-tokens.sqlite3"
        secret = "hrt_legacy_secret"
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE access_tokens (
                    token_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    token_prefix TEXT NOT NULL,
                    secret_hash TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    quota_tokens INTEGER,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    revoked_at TEXT,
                    last_used_at TEXT
                );
                CREATE TABLE access_token_request_logs (
                    log_id TEXT PRIMARY KEY,
                    token_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT INTO access_tokens VALUES (
                    ?, ?, ?, ?, 'active', 100, 7, 3, 10, ?, NULL, NULL, ?
                )
                """,
                (
                    "tok-legacy",
                    "旧网关",
                    secret[:12],
                    hashlib.sha256(secret.encode("utf-8")).hexdigest(),
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:01:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO access_token_request_logs VALUES (
                    'log-legacy', 'tok-legacy', 'req-legacy', 'POST', '/v1/chat',
                    200, 12, 7, 3, 10, NULL, '2026-01-01T00:01:00+00:00'
                )
                """
            )

        migrated = SQLiteAccessTokenStore(path=self.path)

        token = migrated.get_token("tok-legacy")
        self.assertIsNone(token.appId)
        self.assertIsNone(token.dailyQuotaTokens)
        self.assertIsNone(token.weeklyQuotaTokens)
        self.assertEqual(token.dailyTokens, 0)
        self.assertEqual(token.weeklyTokens, 0)
        self.assertEqual(token.totalTokens, 10)
        self.assertEqual(migrated.authenticate(secret), token)
        logs = migrated.list_request_logs("tok-legacy")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].requestId, "req-legacy")
        reopened = SQLiteAccessTokenStore(path=self.path)
        self.assertEqual(reopened.get_token("tok-legacy"), token)
        with closing(sqlite3.connect(self.path)) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(access_tokens)")
            }
        self.assertIn("app_id", columns)
        self.assertIn("daily_quota_tokens", columns)
        self.assertIn("weekly_quota_tokens", columns)


if __name__ == "__main__":
    unittest.main()
