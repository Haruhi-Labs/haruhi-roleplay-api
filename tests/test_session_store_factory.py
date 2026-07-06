from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import InMemorySessionStore, SQLiteSessionStore  # noqa: E402
from haruhi_roleplay_api.domain import DTOValidationError  # noqa: E402
from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    RuntimeConfigStore,
    SessionStoreSettings,
    build_session_store_from_env,
)


class SessionStoreFactoryTests(unittest.TestCase):
    def test_default_provider_builds_in_memory_store(self) -> None:
        store = build_session_store_from_env({})

        self.assertIsInstance(store, InMemorySessionStore)

    def test_settings_parse_session_runtime_options(self) -> None:
        settings = SessionStoreSettings.from_mapping(
            {
                "SESSION_PROVIDER": "memory",
                "SESSION_RECENT_LIMIT": "3",
                "SESSION_TTL_SECONDS": "60",
                "SESSION_AUTO_CREATE_SCHEMA": "false",
                "SESSION_SQLITE_PATH": ".data/test.sqlite3",
                "SESSION_SQLITE_BUSY_TIMEOUT_MS": "250",
                "SESSION_POSTGRES_SCHEMA": "roleplay",
                "SESSION_POSTGRES_TABLE_PREFIX": "rp_",
                "SESSION_POSTGRES_POOL_SIZE": "2",
            }
        )

        self.assertEqual(settings.provider, "memory")
        self.assertIsNone(settings.databaseUrl)
        self.assertEqual(settings.recentMessageLimit, 3)
        self.assertEqual(settings.ttlSeconds, 60)
        self.assertFalse(settings.autoCreateSchema)
        self.assertEqual(settings.sqlitePath, ".data/test.sqlite3")
        self.assertEqual(settings.sqliteBusyTimeoutMs, 250)
        self.assertEqual(settings.postgresSchema, "roleplay")
        self.assertEqual(settings.postgresTablePrefix, "rp_")
        self.assertEqual(settings.postgresPoolSize, 2)

    def test_unknown_provider_returns_validation_error(self) -> None:
        with self.assertRaises(DTOValidationError):
            build_session_store_from_env({"SESSION_PROVIDER": "unknown"})

    def test_sqlite_provider_builds_sqlite_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = build_session_store_from_env(
                {
                    "SESSION_PROVIDER": "sqlite",
                    "SESSION_SQLITE_PATH": str(Path(temp_dir) / "sessions.sqlite3"),
                }
            )

        self.assertIsInstance(store, SQLiteSessionStore)

    def test_postgres_provider_requires_database_url(self) -> None:
        with self.assertRaises(DTOValidationError):
            build_session_store_from_env({"SESSION_PROVIDER": "postgres"})

    def test_postgres_provider_builds_postgres_store(self) -> None:
        with patch(
            "haruhi_roleplay_api.infrastructure.session_store_factory.PostgresSessionStore"
        ) as store_class:
            store = build_session_store_from_env(
                {
                    "SESSION_PROVIDER": "postgres",
                    "DATABASE_URL": "postgresql://user:password@db.example/roleplay",
                    "SESSION_POSTGRES_SCHEMA": "roleplay",
                    "SESSION_POSTGRES_TABLE_PREFIX": "rp_",
                }
            )

        self.assertEqual(store, store_class.return_value)
        store_class.assert_called_once_with(
            database_url="postgresql://user:password@db.example/roleplay",
            schema="roleplay",
            table_prefix="rp_",
            auto_create_schema=True,
            ttl_seconds=604800,
        )

    def test_invalid_recent_limit_returns_validation_error(self) -> None:
        with self.assertRaises(DTOValidationError):
            SessionStoreSettings.from_mapping({"SESSION_RECENT_LIMIT": "0"})

    def test_runtime_config_snapshot_exposes_restart_required_session_keys(self) -> None:
        store = RuntimeConfigStore.in_memory(
            {
                "SESSION_PROVIDER": "memory",
                "SESSION_RECENT_LIMIT": "9",
                "SESSION_SQLITE_PATH": ".data/test.sqlite3",
            }
        )

        snapshot = store.public_snapshot()

        self.assertEqual(snapshot["values"]["SESSION_PROVIDER"], "memory")
        self.assertEqual(snapshot["values"]["SESSION_RECENT_LIMIT"], "9")
        self.assertEqual(
            snapshot["values"]["SESSION_SQLITE_PATH"],
            ".data/test.sqlite3",
        )
        self.assertIn("SESSION_RECENT_LIMIT", snapshot["configurable_keys"])
        self.assertIn("SESSION_PROVIDER", snapshot["restart_required_keys"])

    def test_runtime_config_snapshot_does_not_expose_database_url(self) -> None:
        store = RuntimeConfigStore.in_memory(
            {
                "SESSION_PROVIDER": "postgres",
                "DATABASE_URL": "postgresql://user:password@db.example/roleplay",
            }
        )

        snapshot = store.public_snapshot()

        self.assertEqual(snapshot["values"]["SESSION_PROVIDER"], "postgres")
        self.assertNotIn("DATABASE_URL", snapshot["values"])
        self.assertNotIn("DATABASE_URL", snapshot["configurable_keys"])
        self.assertNotIn("DATABASE_URL", snapshot["restart_required_keys"])

    def test_runtime_config_patch_rejects_session_provider_hot_switch(self) -> None:
        store = RuntimeConfigStore.in_memory({})

        with self.assertRaises(DTOValidationError):
            store.parse_update({"values": {"SESSION_PROVIDER": "sqlite"}})


if __name__ == "__main__":
    unittest.main()
