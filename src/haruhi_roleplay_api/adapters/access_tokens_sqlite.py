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
        name: str,
        quota_tokens: int | None,
        expires_at: str | None = None,
    ) -> IssuedAccessToken:
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
                VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
                """,
                (
                    token_id,
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

    def _initialize_schema(self) -> None:
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA_SQL)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self._path,
            timeout=self._busy_timeout_ms / 1000,
        )
        connection.row_factory = sqlite3.Row
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
"""


def _token_from_row(row: sqlite3.Row) -> AccessToken:
    return AccessToken(
        tokenId=str(row["token_id"]),
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
