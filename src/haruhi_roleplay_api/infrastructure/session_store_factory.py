"""Session store factory wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from haruhi_roleplay_api.adapters.sessions import InMemorySessionStore
from haruhi_roleplay_api.adapters.sessions_postgres import PostgresSessionStore
from haruhi_roleplay_api.adapters.sessions_sqlite import SQLiteSessionStore
from haruhi_roleplay_api.domain import DTOValidationError
from haruhi_roleplay_api.ports import SessionStore


@dataclass(frozen=True, kw_only=True)
class SessionStoreSettings:
    provider: str = "memory"
    recentMessageLimit: int = 12
    ttlSeconds: int = 604800
    autoCreateSchema: bool = True
    databaseUrl: str | None = None
    sqlitePath: str = ".data/sessions.sqlite3"
    sqliteBusyTimeoutMs: int = 5000
    postgresSchema: str = "public"
    postgresTablePrefix: str = "roleplay_"
    postgresPoolSize: int = 5

    @classmethod
    def from_mapping(cls, data: Mapping[str, str]) -> "SessionStoreSettings":
        return cls(
            provider=data.get("SESSION_PROVIDER", "memory"),
            recentMessageLimit=_positive_int(
                data,
                "SESSION_RECENT_LIMIT",
                default=12,
            ),
            ttlSeconds=_non_negative_int(
                data,
                "SESSION_TTL_SECONDS",
                default=604800,
            ),
            autoCreateSchema=_bool_from_mapping(
                data.get("SESSION_AUTO_CREATE_SCHEMA", "true")
            ),
            databaseUrl=_optional_string(data.get("DATABASE_URL")),
            sqlitePath=data.get("SESSION_SQLITE_PATH", ".data/sessions.sqlite3"),
            sqliteBusyTimeoutMs=_positive_int(
                data,
                "SESSION_SQLITE_BUSY_TIMEOUT_MS",
                default=5000,
            ),
            postgresSchema=data.get("SESSION_POSTGRES_SCHEMA", "public"),
            postgresTablePrefix=data.get(
                "SESSION_POSTGRES_TABLE_PREFIX",
                "roleplay_",
            ),
            postgresPoolSize=_positive_int(
                data,
                "SESSION_POSTGRES_POOL_SIZE",
                default=5,
            ),
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "SessionStoreSettings":
        return cls.from_mapping(env)


def build_session_store(settings: SessionStoreSettings) -> SessionStore:
    provider = settings.provider.strip().lower().replace("-", "_")
    if provider in {"", "memory", "in_memory", "inmemory"}:
        return InMemorySessionStore()
    if provider == "sqlite":
        return SQLiteSessionStore(
            path=settings.sqlitePath,
            auto_create_schema=settings.autoCreateSchema,
            busy_timeout_ms=settings.sqliteBusyTimeoutMs,
            ttl_seconds=settings.ttlSeconds,
        )
    if provider in {"postgres", "postgresql"}:
        if not settings.databaseUrl:
            raise DTOValidationError(
                "DATABASE_URL is required for SESSION_PROVIDER=postgres"
            )
        return PostgresSessionStore(
            database_url=settings.databaseUrl,
            schema=settings.postgresSchema,
            table_prefix=settings.postgresTablePrefix,
            auto_create_schema=settings.autoCreateSchema,
            ttl_seconds=settings.ttlSeconds,
        )
    raise DTOValidationError(
        "SESSION_PROVIDER must be memory, sqlite, or postgres"
    )


def build_session_store_from_env(env: Mapping[str, str]) -> SessionStore:
    return build_session_store(SessionStoreSettings.from_mapping(env))


def _positive_int(
    data: Mapping[str, str],
    key: str,
    *,
    default: int,
) -> int:
    value = _int_from_mapping(data, key, default=default)
    if value <= 0:
        raise DTOValidationError(f"{key} must be positive")
    return value


def _non_negative_int(
    data: Mapping[str, str],
    key: str,
    *,
    default: int,
) -> int:
    value = _int_from_mapping(data, key, default=default)
    if value < 0:
        raise DTOValidationError(f"{key} must be non-negative")
    return value


def _int_from_mapping(
    data: Mapping[str, str],
    key: str,
    *,
    default: int,
) -> int:
    value = data.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise DTOValidationError(f"{key} must be an integer") from exc


def _bool_from_mapping(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _optional_string(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()
