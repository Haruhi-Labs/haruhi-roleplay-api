from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.domain import (  # noqa: E402
    CharacterProfile,
    DTOValidationError,
    PersonaModeId,
    PersonaPreset,
    Visibility,
    public_persona_presets,
)


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


class PersonaCatalogSchemaTests(unittest.TestCase):
    def test_all_character_configs_and_declared_presets_pass(self) -> None:
        expected_characters = {"haruhi", "kyon", "mikuru", "yuki", "itsuki"}
        character_dirs = {
            path.name
            for path in (ROOT / "personas").iterdir()
            if path.is_dir()
        }

        self.assertEqual(character_dirs, expected_characters)
        for character_id in expected_characters:
            character = CharacterProfile.from_mapping(
                load_json(f"personas/{character_id}/character.json")
            )
            for mode in character.availablePersonaModes:
                preset = PersonaPreset.from_mapping(
                    load_json(f"personas/{character_id}/{mode}.json")
                )
                self.assertEqual(str(preset.characterId), character_id)
                self.assertEqual(str(preset.personaMode), str(mode))

    def test_disappearance_presets_keep_altered_world_perspective_bounded(self) -> None:
        for character_id in ("haruhi", "mikuru", "yuki", "itsuki"):
            preset = PersonaPreset.from_mapping(
                load_json(
                    f"personas/{character_id}/disappearance_{character_id}.json"
                )
            )

            self.assertEqual(
                preset.knowledgeBoundary.allowedTimelines,
                ("disappearance",),
            )

        kyon = PersonaPreset.from_mapping(
            load_json("personas/kyon/disappearance_kyon.json")
        )
        self.assertIn("melancholy", kyon.knowledgeBoundary.allowedTimelines)
        self.assertIn("disappearance", kyon.knowledgeBoundary.allowedTimelines)

    def test_valid_character_and_preset_config_pass(self) -> None:
        character = CharacterProfile.from_mapping(
            load_json("personas/haruhi/character.json")
        )
        preset = PersonaPreset.from_mapping(
            load_json("personas/haruhi/mid_late_haruhi.json")
        )

        self.assertEqual(character.characterId, "haruhi")
        self.assertEqual(character.defaultPersonaMode, PersonaModeId("mid_late_haruhi"))
        self.assertIn(preset.personaMode, character.availablePersonaModes)
        self.assertEqual(preset.visibility, Visibility.PUBLIC)

    def test_non_haruhi_character_config_passes(self) -> None:
        character = CharacterProfile.from_mapping(load_json("personas/kyon/character.json"))
        preset = PersonaPreset.from_mapping(load_json("personas/kyon/default_kyon.json"))

        self.assertEqual(character.characterId, "kyon")
        self.assertEqual(preset.characterId, "kyon")
        self.assertEqual(character.defaultPersonaMode, PersonaModeId("default_kyon"))

    def test_missing_default_preset_fails(self) -> None:
        data = load_json("personas/kyon/character.json")
        data["defaultPersonaMode"] = "missing_mode"

        with self.assertRaisesRegex(
            DTOValidationError,
            "defaultPersonaMode must be included",
        ):
            CharacterProfile.from_mapping(data)

    def test_draft_preset_is_not_public(self) -> None:
        public_preset = PersonaPreset.from_mapping(
            load_json("personas/kyon/default_kyon.json")
        )
        draft_preset = PersonaPreset.from_mapping(
            load_json("personas/kyon/narrator_kyon.json")
        )

        visible = public_persona_presets([public_preset, draft_preset])

        self.assertEqual(tuple(p.personaMode for p in visible), ("default_kyon",))
        self.assertEqual(draft_preset.visibility, Visibility.DRAFT)

    def test_tone_out_of_range_fails(self) -> None:
        data = load_json("personas/haruhi/mid_late_haruhi.json")
        data["tone"]["energy"] = 2

        with self.assertRaisesRegex(DTOValidationError, "tone.energy"):
            PersonaPreset.from_mapping(data)

    def test_missing_required_preset_section_fails(self) -> None:
        data = load_json("personas/haruhi/mid_late_haruhi.json")
        del data["tone"]

        with self.assertRaisesRegex(DTOValidationError, "tone is required"):
            PersonaPreset.from_mapping(data)


if __name__ == "__main__":
    unittest.main()
