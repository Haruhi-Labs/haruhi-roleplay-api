from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import (  # noqa: E402
    InMemoryMemoryStore,
    SQLiteMemoryStore,
)
from haruhi_roleplay_api.domain import DTOValidationError  # noqa: E402
from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    MemoryStoreSettings,
    RuntimeConfigStore,
    build_memory_store_from_env,
)


class MemoryStoreFactoryTests(unittest.TestCase):
    def test_default_provider_builds_in_memory_store(self) -> None:
        store = build_memory_store_from_env({})

        self.assertIsInstance(store, InMemoryMemoryStore)

    def test_settings_parse_sqlite_options(self) -> None:
        settings = MemoryStoreSettings.from_mapping(
            {
                "MEMORY_PROVIDER": "sqlite",
                "MEMORY_SQLITE_PATH": ".data/test-memories.sqlite3",
                "MEMORY_SQLITE_BUSY_TIMEOUT_MS": "250",
            }
        )

        self.assertEqual(settings.provider, "sqlite")
        self.assertEqual(settings.sqlitePath, ".data/test-memories.sqlite3")
        self.assertEqual(settings.sqliteBusyTimeoutMs, 250)

    def test_unknown_provider_returns_validation_error(self) -> None:
        with self.assertRaises(DTOValidationError):
            build_memory_store_from_env({"MEMORY_PROVIDER": "unknown"})

    def test_sqlite_provider_builds_sqlite_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = build_memory_store_from_env(
                {
                    "MEMORY_PROVIDER": "sqlite",
                    "MEMORY_SQLITE_PATH": str(Path(temp_dir) / "memories.sqlite3"),
                }
            )

        self.assertIsInstance(store, SQLiteMemoryStore)

    def test_runtime_config_snapshot_exposes_restart_required_memory_keys(self) -> None:
        store = RuntimeConfigStore.in_memory(
            {
                "MEMORY_PROVIDER": "sqlite",
                "MEMORY_SQLITE_PATH": ".data/memories.sqlite3",
                "MEMORY_SQLITE_BUSY_TIMEOUT_MS": "5000",
            }
        )

        snapshot = store.public_snapshot()

        self.assertEqual(snapshot["values"]["MEMORY_PROVIDER"], "sqlite")
        self.assertEqual(
            snapshot["values"]["MEMORY_SQLITE_PATH"],
            ".data/memories.sqlite3",
        )
        self.assertIn("MEMORY_PROVIDER", snapshot["restart_required_keys"])
        self.assertIn("MEMORY_SQLITE_PATH", snapshot["restart_required_keys"])

    def test_runtime_config_patch_rejects_memory_provider_hot_switch(self) -> None:
        store = RuntimeConfigStore.in_memory({})

        with self.assertRaises(DTOValidationError):
            store.parse_update({"values": {"MEMORY_PROVIDER": "sqlite"}})


if __name__ == "__main__":
    unittest.main()
