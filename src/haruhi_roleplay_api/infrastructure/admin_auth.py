"""后台管理会话认证与登录防暴力破解。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import RLock
from typing import Callable

from haruhi_roleplay_api.application.errors import AppError, ErrorCode


ADMIN_SESSION_COOKIE = "roleplay_admin_session"


@dataclass(frozen=True, kw_only=True)
class IssuedAdminSession:
    secret: str
    csrf_token: str
    expires_in: int


@dataclass(kw_only=True)
class _AdminSession:
    csrf_token: str
    created_at: float
    last_seen_at: float
    expires_at: float


class AdminSessionManager:
    """保存短期后台会话；浏览器只持有不可恢复的随机密钥。"""

    def __init__(
        self,
        *,
        password: str | None,
        ttl_seconds: int = 28_800,
        idle_timeout_seconds: int = 1_800,
        attempt_limit: int = 5,
        attempt_window_seconds: int = 300,
        maximum_sessions: int = 100,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0 or idle_timeout_seconds <= 0:
            raise ValueError("后台会话有效期必须大于 0")
        if idle_timeout_seconds > ttl_seconds:
            raise ValueError("后台会话空闲有效期不能大于总有效期")
        if attempt_limit <= 0 or attempt_window_seconds <= 0:
            raise ValueError("后台登录限制必须大于 0")
        if maximum_sessions <= 0:
            raise ValueError("后台会话数量上限必须大于 0")
        self._password = password
        self._ttl_seconds = ttl_seconds
        self._idle_timeout_seconds = idle_timeout_seconds
        self._attempt_limit = attempt_limit
        self._attempt_window_seconds = attempt_window_seconds
        self._maximum_sessions = maximum_sessions
        self._clock = clock
        self._sessions: dict[str, _AdminSession] = {}
        self._failed_attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    def login(self, *, password: str, client_id: str) -> IssuedAdminSession:
        now = self._clock()
        normalized_client = client_id.strip() or "unknown"
        with self._lock:
            self._purge(now)
            attempts = self._failed_attempts[normalized_client]
            self._trim_attempts(attempts, now)
            if len(attempts) >= self._attempt_limit:
                raise AppError(
                    code=ErrorCode.RATE_LIMIT_EXCEEDED,
                    message="后台登录尝试过于频繁，请稍后再试。",
                )
            if not self._password or not _secret_equals(password, self._password):
                attempts.append(now)
                raise AppError(
                    code=ErrorCode.AUTH_INVALID_API_KEY,
                    message="管理员密码不正确。",
                )
            self._failed_attempts.pop(normalized_client, None)
            self._evict_for_capacity()
            secret = f"adm_{secrets.token_urlsafe(32)}"
            csrf_token = secrets.token_urlsafe(24)
            self._sessions[_secret_hash(secret)] = _AdminSession(
                csrf_token=csrf_token,
                created_at=now,
                last_seen_at=now,
                expires_at=now + self._ttl_seconds,
            )
            return IssuedAdminSession(
                secret=secret,
                csrf_token=csrf_token,
                expires_in=self._ttl_seconds,
            )

    def authenticate(self, secret: str | None) -> _AdminSession | None:
        if not secret or not secret.startswith("adm_"):
            return None
        now = self._clock()
        with self._lock:
            self._purge(now)
            session = self._sessions.get(_secret_hash(secret))
            if session is None:
                return None
            if now - session.last_seen_at > self._idle_timeout_seconds:
                self._sessions.pop(_secret_hash(secret), None)
                return None
            session.last_seen_at = now
            return session

    def verify_csrf(self, session: _AdminSession, candidate: str | None) -> bool:
        return _secret_equals(candidate, session.csrf_token)

    def logout(self, secret: str | None) -> None:
        if not secret:
            return
        with self._lock:
            self._sessions.pop(_secret_hash(secret), None)

    def _purge(self, now: float) -> None:
        expired = [
            key
            for key, session in self._sessions.items()
            if session.expires_at <= now
            or now - session.last_seen_at > self._idle_timeout_seconds
        ]
        for key in expired:
            self._sessions.pop(key, None)
        stale_clients = []
        for client_id, attempts in self._failed_attempts.items():
            self._trim_attempts(attempts, now)
            if not attempts:
                stale_clients.append(client_id)
        for client_id in stale_clients:
            self._failed_attempts.pop(client_id, None)

    def _trim_attempts(self, attempts: deque[float], now: float) -> None:
        cutoff = now - self._attempt_window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

    def _evict_for_capacity(self) -> None:
        overflow = len(self._sessions) - self._maximum_sessions + 1
        if overflow <= 0:
            return
        oldest = sorted(
            self._sessions,
            key=lambda key: self._sessions[key].last_seen_at,
        )[:overflow]
        for key in oldest:
            self._sessions.pop(key, None)


def _secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _secret_equals(candidate: str | None, expected: str) -> bool:
    if candidate is None:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))
