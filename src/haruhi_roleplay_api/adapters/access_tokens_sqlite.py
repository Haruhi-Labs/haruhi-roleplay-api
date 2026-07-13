"""SQLite 访问令牌存储。"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import DTOValidationError
from haruhi_roleplay_api.domain.access_token import (
    AccessToken,
    AccessTokenRequestLog,
    AccessTokenStatus,
    IssuedAccessToken,
)


class SQLiteAccessTokenStore:
    def __init__(
        self,
        *,
        path: str | Path,
        busy_timeout_ms: int = 5000,
    ) -> None:
        self._path = _sqlite_path(path)
        self._busy_timeout_ms = busy_timeout_ms
        self._initialize_schema()

    def create_token(
        self,
        *,
        app_id: str,
        name: str,
        quota_tokens: int | None,
        expires_at: str | None = None,
    ) -> IssuedAccessToken:
        clean_app_id = _required_text(app_id, "app_id")
        clean_name = _required_text(name, "name")
        clean_quota = _optional_positive_int(quota_tokens, "quota_tokens")
        clean_expires_at = _optional_future_timestamp(expires_at)
        token_id = f"tok-{uuid4().hex}"
        secret = f"hrt_{secrets.token_urlsafe(32)}"
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO access_tokens (
                    token_id,
                    app_id,
                    name,
                    token_prefix,
                    secret_hash,
                    status,
                    quota_tokens,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    created_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
                """,
                (
                    token_id,
                    clean_app_id,
                    clean_name,
                    secret[:12],
                    _secret_hash(secret),
                    AccessTokenStatus.ACTIVE.value,
                    clean_quota,
                    now,
                    clean_expires_at,
                ),
            )
        return IssuedAccessToken(token=self.get_token(token_id), secret=secret)

    def authenticate(self, secret: str) -> AccessToken | None:
        if not isinstance(secret, str) or not secret.startswith("hrt_"):
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM access_tokens WHERE secret_hash = ?",
                (_secret_hash(secret),),
            ).fetchone()
        if row is None:
            return None
        token = _token_from_row(row)
        if token.status is not AccessTokenStatus.ACTIVE:
            return None
        if token.expiresAt is not None and _parse_timestamp(token.expiresAt) <= _utc_now():
            return None
        return token

    def list_tokens(self) -> tuple[AccessToken, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM access_tokens ORDER BY created_at DESC, token_id DESC"
            ).fetchall()
        return tuple(_token_from_row(row) for row in rows)

    def get_token(self, token_id: str) -> AccessToken:
        clean_token_id = _required_text(token_id, "token_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM access_tokens WHERE token_id = ?",
                (clean_token_id,),
            ).fetchone()
        if row is None:
            raise AppError(
                code=ErrorCode.ACCESS_TOKEN_NOT_FOUND,
                message="Access token was not found.",
            )
        return _token_from_row(row)

    def revoke_token(self, token_id: str) -> AccessToken:
        existing = self.get_token(token_id)
        if existing.status is AccessTokenStatus.REVOKED:
            return existing
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE access_tokens
                SET status = ?, revoked_at = ?
                WHERE token_id = ?
                """,
                (AccessTokenStatus.REVOKED.value, _now(), token_id),
            )
        return self.get_token(token_id)

    def update_quota(
        self,
        token_id: str,
        *,
        quota_tokens: int | None,
    ) -> AccessToken:
        self.get_token(token_id)
        clean_quota = _optional_positive_int(quota_tokens, "quota_tokens")
        with self._connect() as connection:
            connection.execute(
                "UPDATE access_tokens SET quota_tokens = ? WHERE token_id = ?",
                (clean_quota, token_id),
            )
        return self.get_token(token_id)

    def ensure_quota_available(self, token_id: str) -> AccessToken:
        token = self.get_token(token_id)
        if token.quotaTokens is not None and token.totalTokens >= token.quotaTokens:
            raise AppError(code=ErrorCode.ACCESS_TOKEN_QUOTA_EXCEEDED)
        return token

    def record_request(
        self,
        *,
        token_id: str,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        duration_ms: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        error_code: str | None = None,
    ) -> AccessTokenRequestLog:
        self.get_token(token_id)
        log = AccessTokenRequestLog(
            logId=f"log-{uuid4().hex}",
            tokenId=token_id,
            requestId=_required_text(request_id, "request_id"),
            method=_required_text(method, "method").upper(),
            path=_required_text(path, "path"),
            statusCode=int(status_code),
            durationMs=int(duration_ms),
            promptTokens=int(prompt_tokens),
            completionTokens=int(completion_tokens),
            totalTokens=int(prompt_tokens) + int(completion_tokens),
            errorCode=error_code,
            createdAt=_now(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO access_token_request_logs (
                    log_id,
                    token_id,
                    request_id,
                    method,
                    path,
                    status_code,
                    duration_ms,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    error_code,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.logId,
                    log.tokenId,
                    log.requestId,
                    log.method,
                    log.path,
                    log.statusCode,
                    log.durationMs,
                    log.promptTokens,
                    log.completionTokens,
                    log.totalTokens,
                    log.errorCode,
                    log.createdAt,
                ),
            )
            connection.execute(
                """
                UPDATE access_tokens
                SET
                    prompt_tokens = prompt_tokens + ?,
                    completion_tokens = completion_tokens + ?,
                    total_tokens = total_tokens + ?,
                    last_used_at = ?
                WHERE token_id = ?
                """,
                (
                    log.promptTokens,
                    log.completionTokens,
                    log.totalTokens,
                    log.createdAt,
                    token_id,
                ),
            )
        return log

    def list_request_logs(
        self,
        token_id: str,
        *,
        limit: int = 50,
    ) -> tuple[AccessTokenRequestLog, ...]:
        self.get_token(token_id)
        clean_limit = _bounded_limit(limit)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM access_token_request_logs
                WHERE token_id = ?
                ORDER BY created_at DESC, log_id DESC
                LIMIT ?
                """,
                (token_id, clean_limit),
            ).fetchall()
        return tuple(_request_log_from_row(row) for row in rows)

    def _initialize_schema(self) -> None:
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA_SQL)
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(access_tokens)")
            }
            if "app_id" not in columns:
                connection.execute(
                    """
                    ALTER TABLE access_tokens
                    ADD COLUMN app_id TEXT
                    CHECK (app_id IS NULL OR length(trim(app_id)) > 0)
                    """
                )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self._path,
            timeout=self._busy_timeout_ms / 1000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS access_tokens (
    token_id TEXT PRIMARY KEY,
    app_id TEXT CHECK (app_id IS NULL OR length(trim(app_id)) > 0),
    name TEXT NOT NULL,
    token_prefix TEXT NOT NULL,
    secret_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
    quota_tokens INTEGER CHECK (quota_tokens IS NULL OR quota_tokens > 0),
    prompt_tokens INTEGER NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
    completion_tokens INTEGER NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
    total_tokens INTEGER NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    created_at TEXT NOT NULL,
    expires_at TEXT,
    revoked_at TEXT,
    last_used_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_access_tokens_status
ON access_tokens (status);

CREATE TABLE IF NOT EXISTS access_token_request_logs (
    log_id TEXT PRIMARY KEY,
    token_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    prompt_tokens INTEGER NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
    completion_tokens INTEGER NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
    total_tokens INTEGER NOT NULL DEFAULT 0 CHECK (total_tokens >= 0),
    error_code TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (token_id) REFERENCES access_tokens(token_id)
);

CREATE INDEX IF NOT EXISTS idx_access_token_logs_token_created
ON access_token_request_logs (token_id, created_at DESC);
"""


def _token_from_row(row: sqlite3.Row) -> AccessToken:
    return AccessToken(
        tokenId=str(row["token_id"]),
        appId=(str(row["app_id"]) if row["app_id"] is not None else None),
        name=str(row["name"]),
        prefix=str(row["token_prefix"]),
        status=AccessTokenStatus(str(row["status"])),
        quotaTokens=(int(row["quota_tokens"]) if row["quota_tokens"] is not None else None),
        promptTokens=int(row["prompt_tokens"]),
        completionTokens=int(row["completion_tokens"]),
        totalTokens=int(row["total_tokens"]),
        createdAt=str(row["created_at"]),
        expiresAt=(str(row["expires_at"]) if row["expires_at"] is not None else None),
        revokedAt=(str(row["revoked_at"]) if row["revoked_at"] is not None else None),
        lastUsedAt=(str(row["last_used_at"]) if row["last_used_at"] is not None else None),
    )


def _request_log_from_row(row: sqlite3.Row) -> AccessTokenRequestLog:
    return AccessTokenRequestLog(
        logId=str(row["log_id"]),
        tokenId=str(row["token_id"]),
        requestId=str(row["request_id"]),
        method=str(row["method"]),
        path=str(row["path"]),
        statusCode=int(row["status_code"]),
        durationMs=int(row["duration_ms"]),
        promptTokens=int(row["prompt_tokens"]),
        completionTokens=int(row["completion_tokens"]),
        totalTokens=int(row["total_tokens"]),
        errorCode=(str(row["error_code"]) if row["error_code"] is not None else None),
        createdAt=str(row["created_at"]),
    )


def _sqlite_path(path: str | Path) -> str:
    value = str(path)
    if not value.strip():
        raise DTOValidationError("ACCESS_TOKEN_SQLITE_PATH must be non-empty")
    return value


def _required_text(value: str | None, field_name: str) -> str:
    if value is None or not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_positive_int(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise DTOValidationError(f"{field_name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError(f"{field_name} must be a positive integer") from exc
    if parsed <= 0:
        raise DTOValidationError(f"{field_name} must be a positive integer")
    return parsed


def _bounded_limit(value: int) -> int:
    if isinstance(value, bool):
        raise DTOValidationError("limit must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DTOValidationError("limit must be a positive integer") from exc
    if parsed <= 0:
        raise DTOValidationError("limit must be a positive integer")
    return min(parsed, 200)


def _optional_future_timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = _parse_timestamp(_required_text(value, "expires_at"))
    if parsed <= _utc_now():
        raise DTOValidationError("expires_at must be in the future")
    return parsed.isoformat()


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DTOValidationError("expires_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise DTOValidationError("expires_at must include a timezone")
    return parsed.astimezone(UTC)


def _secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _now() -> str:
    return _utc_now().isoformat()
