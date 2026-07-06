from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.domain import DTOValidationError  # noqa: E402
from haruhi_roleplay_api.infrastructure.env_config_editor import (  # noqa: E402
    ENV_CONFIG_FIELD_BY_KEY,
    EnvConfigEditor,
)


def editor_for(path: Path, env: dict[str, str] | None = None) -> EnvConfigEditor:
    return EnvConfigEditor(base_env=env or {}, config_path=path)


class EnvConfigEditorTests(unittest.TestCase):
    def test_schema_marks_secret_hot_reload_and_restart_fields(self) -> None:
        roleplay_key = ENV_CONFIG_FIELD_BY_KEY["ROLEPLAY_API_KEY"]
        roleplay_port = ENV_CONFIG_FIELD_BY_KEY["ROLEPLAY_PORT"]
        session_provider = ENV_CONFIG_FIELD_BY_KEY["SESSION_PROVIDER"]
        model_provider = ENV_CONFIG_FIELD_BY_KEY["MODEL_PROVIDER"]

        self.assertTrue(roleplay_key.secret)
        self.assertTrue(roleplay_key.hotReload)
        self.assertTrue(roleplay_port.restartRequired)
        self.assertFalse(roleplay_port.hotReload)
        self.assertTrue(session_provider.restartRequired)
        self.assertEqual(model_provider.valueType, "enum")
        self.assertIn("fake", model_provider.enum)

    def test_snapshot_redacts_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "ROLEPLAY_API_KEY=admin-secret",
                        "OPENAI_API_KEY=cloud-secret",
                        "MODEL_PROVIDER=fake",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            snapshot = editor_for(env_path).snapshot()

        values = snapshot["values"]
        serialized = json.dumps(snapshot, ensure_ascii=False)
        self.assertEqual(values["ROLEPLAY_API_KEY"]["status"], "set")
        self.assertEqual(values["OPENAI_API_KEY"]["status"], "set")
        self.assertEqual(values["MODEL_PROVIDER"]["value"], "fake")
        self.assertNotIn("admin-secret", serialized)
        self.assertNotIn("cloud-secret", serialized)

    def test_field_check_validates_field_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            editor = editor_for(Path(temp_dir) / ".env")
            bad_int = editor.check({"key": "MODEL_TIMEOUT_MS", "value": "0"})
            bad_enum = editor.check({"key": "RAG_PROVIDER", "value": "bad"})
            bad_bool = editor.check({"key": "ENABLE_DEBUG_TRACE", "value": "maybe"})
            bad_json = editor.check({"key": "MODEL_PROVIDER_REGISTRY", "value": "{"})
            bad_url = editor.check({"key": "MODEL_BASE_URL", "value": "localhost"})
            path_warning = editor.check({"key": "CHROMA_PERSIST_PATH", "value": "~/.chroma"})
            bad_csv = editor.check(
                {"key": "BACKEND_CONTEXT_SOURCES", "value": "user_profile\ngame_state"}
            )
            bad_identifier = editor.check(
                {"key": "SESSION_POSTGRES_SCHEMA", "value": "bad-name"}
            )

        self.assertFalse(bad_int.valid)
        self.assertIn("MODEL_TIMEOUT_MS must be >= 1", bad_int.errors)
        self.assertFalse(bad_enum.valid)
        self.assertFalse(bad_bool.valid)
        self.assertFalse(bad_json.valid)
        self.assertFalse(bad_url.valid)
        self.assertTrue(path_warning.valid)
        self.assertTrue(path_warning.warnings)
        self.assertFalse(bad_csv.valid)
        self.assertFalse(bad_identifier.valid)

    def test_dependency_check_reports_required_backend_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            editor = editor_for(Path(temp_dir) / ".env")
            postgres = editor.check({"values": {"SESSION_PROVIDER": "postgres"}})
            qdrant = editor.check({"values": {"RAG_PROVIDER": "qdrant"}})
            planner = editor.check({"values": {"AGENT_CONTEXT_PLANNER": "model"}})

        self.assertFalse(postgres.valid)
        self.assertIn(
            "DATABASE_URL is required when SESSION_PROVIDER=postgres",
            postgres.errors,
        )
        self.assertFalse(qdrant.valid)
        self.assertIn("QDRANT_URL is required when RAG_PROVIDER=qdrant", qdrant.errors)
        self.assertTrue(planner.valid)
        self.assertIn(
            "AGENT_CONTEXT_PLANNER=model is reserved and not implemented",
            planner.warnings,
        )

    def test_model_provider_registry_check_requires_resolvable_default_alias(self) -> None:
        registry = {
            "default_alias": "missing",
            "providers": {"fake": {"type": "fake"}},
            "aliases": {"fake-one": {"provider": "fake", "model": "fake-one"}},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            result = editor_for(Path(temp_dir) / ".env").check(
                {
                    "key": "MODEL_PROVIDER_REGISTRY",
                    "value": json.dumps(registry),
                }
            )

        self.assertFalse(result.valid)
        self.assertIn(
            "MODEL_PROVIDER_REGISTRY.default_alias must exist in aliases",
            result.errors,
        )

    def test_commit_preserves_comments_unknown_keys_and_redacts_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "# local config",
                        "UNKNOWN_KEEP=value",
                        "MODEL_PROVIDER=fake",
                        "RAG_PROVIDER=local",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = editor_for(env_path).commit(
                {
                    "values": {
                        "MODEL_NAME": "fake-two",
                        "OPENAI_API_KEY": "secret-value",
                        "RAG_PROVIDER": None,
                    }
                }
            )
            saved = env_path.read_text(encoding="utf-8")
            serialized = json.dumps(result, ensure_ascii=False)

        self.assertIn("# local config", saved)
        self.assertIn("UNKNOWN_KEEP=value", saved)
        self.assertIn("MODEL_NAME=fake-two", saved)
        self.assertIn("OPENAI_API_KEY=secret-value", saved)
        self.assertNotIn("RAG_PROVIDER=local", saved)
        self.assertNotIn("secret-value", serialized)
        self.assertIn("OPENAI_API_KEY", result["applied_keys"])

    def test_commit_rejects_invalid_candidate_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("RAG_PROVIDER=local\n", encoding="utf-8")
            editor = editor_for(env_path)
            with self.assertRaises(DTOValidationError):
                editor.commit({"values": {"RAG_PROVIDER": "qdrant"}})

            saved = env_path.read_text(encoding="utf-8")

        self.assertIn("RAG_PROVIDER=local", saved)


if __name__ == "__main__":
    unittest.main()
