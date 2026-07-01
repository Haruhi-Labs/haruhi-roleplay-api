from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters import LocalPersonaRepository  # noqa: E402
from haruhi_roleplay_api.api.personas import get_personas  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


class PersonasCatalogApiTests(unittest.TestCase):
    def test_get_personas_returns_public_catalog(self) -> None:
        response = get_personas(
            LocalPersonaRepository(ROOT / "personas"),
            request_id="req-personas",
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["request_id"], "req-personas")

        characters = response["data"]["characters"]
        character_ids = {character["character_id"] for character in characters}

        self.assertIn("haruhi", character_ids)
        self.assertIn("kyon", character_ids)

        haruhi = next(
            character
            for character in characters
            if character["character_id"] == "haruhi"
        )
        self.assertEqual(haruhi["default_persona_mode"], "mid_late_haruhi")
        self.assertEqual(haruhi["modes"][0]["persona_mode"], "mid_late_haruhi")

    def test_get_personas_does_not_return_draft_presets(self) -> None:
        response = get_personas(
            LocalPersonaRepository(ROOT / "personas"),
            request_id="req-personas",
        )

        kyon = next(
            character
            for character in response["data"]["characters"]
            if character["character_id"] == "kyon"
        )
        modes = {mode["persona_mode"] for mode in kyon["modes"]}

        self.assertEqual(modes, {"default_kyon"})
        self.assertNotIn("narrator_kyon", modes)

    def test_missing_catalog_config_returns_error_envelope(self) -> None:
        response = get_personas(
            LocalPersonaRepository(ROOT / "missing-personas"),
            request_id="req-missing",
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["request_id"], "req-missing")
        self.assertEqual(response["error"]["code"], "PERSONA_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
