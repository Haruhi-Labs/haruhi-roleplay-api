"""Memory store factory wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from haruhi_roleplay_api.adapters.memory import InMemoryMemoryStore
from haruhi_roleplay_api.adapters.memory_sqlite import SQLiteMemoryStore
from haruhi_roleplay_api.domain import DTOValidationError
from haruhi_roleplay_api.ports import MemoryStore


@dataclass(frozen=True, kw_only=True)
class MemoryStoreSettings:
    provider: str = "memory"
    sqlitePath: str = ".data/memories.sqlite3"
    sqliteBusyTimeoutMs: int = 5000

    @classmethod
    def from_mapping(cls, data: Mapping[str, str]) -> "MemoryStoreSettings":
        return cls(
            provider=data.get("MEMORY_PROVIDER", "memory"),
            sqlitePath=data.get("MEMORY_SQLITE_PATH", ".data/memories.sqlite3"),
            sqliteBusyTimeoutMs=_positive_int(
                data,
                "MEMORY_SQLITE_BUSY_TIMEOUT_MS",
                default=5000,
            ),
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "MemoryStoreSettings":
        return cls.from_mapping(env)


def build_memory_store(settings: MemoryStoreSettings) -> MemoryStore:
    provider = settings.provider.strip().lower().replace("-", "_")
    if provider in {"", "memory", "in_memory", "inmemory"}:
        return InMemoryMemoryStore()
    if provider == "sqlite":
        return SQLiteMemoryStore(
            path=settings.sqlitePath,
            busy_timeout_ms=settings.sqliteBusyTimeoutMs,
        )
    raise DTOValidationError("MEMORY_PROVIDER must be memory or sqlite")


def build_memory_store_from_env(env: Mapping[str, str]) -> MemoryStore:
    return build_memory_store(MemoryStoreSettings.from_mapping(env))


def _positive_int(
    data: Mapping[str, str],
    key: str,
    *,
    default: int,
) -> int:
    value = data.get(key)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise DTOValidationError(f"{key} must be an integer") from exc
    if parsed <= 0:
        raise DTOValidationError(f"{key} must be positive")
    return parsed
