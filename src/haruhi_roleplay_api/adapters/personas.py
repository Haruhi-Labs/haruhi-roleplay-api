"""Local JSON persona repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import CharacterId, CharacterProfile, PersonaPreset


class LocalPersonaRepository:
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def list_characters(self) -> tuple[CharacterProfile, ...]:
        if not self._root.is_dir():
            raise AppError(
                code=ErrorCode.PERSONA_NOT_FOUND,
                message="Persona catalog root was not found.",
            )

        characters = []
        for character_dir in sorted(self._root.iterdir(), key=lambda path: path.name):
            if not character_dir.is_dir() or character_dir.name.startswith("."):
                continue
            characters.append(self._load_character(character_dir))
        return tuple(characters)

    def list_presets(self, character_id: CharacterId | str) -> tuple[PersonaPreset, ...]:
        character_dir = self._root / str(character_id)
        character = self._load_character(character_dir)

        presets = []
        for persona_mode in character.availablePersonaModes:
            preset_path = character_dir / f"{persona_mode}.json"
            if not preset_path.is_file():
                raise AppError(
                    code=ErrorCode.PERSONA_MODE_NOT_FOUND,
                    message=(
                        "Persona preset config was not found: "
                        f"{character.characterId}/{persona_mode}"
                    ),
                )
            presets.append(PersonaPreset.from_mapping(self._read_json(preset_path)))
        return tuple(presets)

    def _load_character(self, character_dir: Path) -> CharacterProfile:
        if not character_dir.is_dir():
            raise AppError(
                code=ErrorCode.PERSONA_NOT_FOUND,
                message=(
                    "Character config directory was not found: "
                    f"{character_dir.name}"
                ),
            )

        character_path = character_dir / "character.json"
        if not character_path.is_file():
            raise AppError(
                code=ErrorCode.PERSONA_NOT_FOUND,
                message=f"Character config was not found: {character_dir.name}",
            )
        return CharacterProfile.from_mapping(self._read_json(character_path))

    @staticmethod
    def _read_json(path: Path) -> Mapping[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AppError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Persona config JSON is invalid: {path.name}",
            ) from exc

        if not isinstance(data, Mapping):
            raise AppError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Persona config must be a JSON object: {path.name}",
            )
        return data
