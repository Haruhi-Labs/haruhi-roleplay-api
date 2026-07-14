"""Local JSON persona repository."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    CharacterId,
    CharacterProfile,
    DTOValidationError,
    PersonaPreset,
)


_SAFE_PERSONA_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


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
        character_dir = self._character_dir(str(character_id))
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

    def admin_catalog(self) -> dict[str, Any]:
        characters: list[dict[str, Any]] = []
        for profile in self.list_characters():
            character_dir = self._character_dir(str(profile.characterId))
            character = dict(self._read_json(character_dir / "character.json"))
            presets = [
                dict(self._read_json(character_dir / f"{mode}.json"))
                for mode in profile.availablePersonaModes
            ]
            characters.append(
                {
                    "character": character,
                    "presets": presets,
                    "updated_at": _latest_modified_at(character_dir),
                }
            )
        return {
            "writable": _directory_writable(self._root),
            "count": len(characters),
            "characters": characters,
        }

    def create_character(
        self,
        character: Mapping[str, Any],
        presets: tuple[Mapping[str, Any], ...],
    ) -> dict[str, Any]:
        profile = CharacterProfile.from_mapping(character)
        character_id = _safe_persona_id(str(profile.characterId), "characterId")
        if not presets:
            raise DTOValidationError("presets must contain at least one persona mode")
        validated_presets = tuple(PersonaPreset.from_mapping(item) for item in presets)
        preset_modes = tuple(str(item.personaMode) for item in validated_presets)
        if any(str(item.characterId) != character_id for item in validated_presets):
            raise DTOValidationError("every preset.characterId must match characterId")
        if set(preset_modes) != {str(mode) for mode in profile.availablePersonaModes}:
            raise DTOValidationError(
                "availablePersonaModes must exactly match the submitted presets"
            )
        character_dir = self._character_dir(character_id)
        if character_dir.exists():
            raise DTOValidationError(f"character already exists: {character_id}")
        character_dir.mkdir(parents=False)
        try:
            _atomic_write_json(character_dir / "character.json", character)
            for preset, raw in zip(validated_presets, presets, strict=True):
                mode = _safe_persona_id(str(preset.personaMode), "personaMode")
                _atomic_write_json(character_dir / f"{mode}.json", raw)
        except Exception:
            shutil.rmtree(character_dir, ignore_errors=True)
            raise
        return self.get_admin_character(character_id)

    def get_admin_character(self, character_id: str) -> dict[str, Any]:
        safe_id = _safe_persona_id(character_id, "characterId")
        character_dir = self._character_dir(safe_id)
        profile = self._load_character(character_dir)
        return {
            "character": dict(self._read_json(character_dir / "character.json")),
            "presets": [
                dict(self._read_json(character_dir / f"{mode}.json"))
                for mode in profile.availablePersonaModes
            ],
            "updated_at": _latest_modified_at(character_dir),
        }

    def update_character(
        self,
        character_id: str,
        character: Mapping[str, Any],
    ) -> dict[str, Any]:
        safe_id = _safe_persona_id(character_id, "characterId")
        profile = CharacterProfile.from_mapping(character)
        if str(profile.characterId) != safe_id:
            raise DTOValidationError("characterId cannot be changed")
        character_dir = self._character_dir(safe_id)
        existing = self._load_character(character_dir)
        if set(profile.availablePersonaModes) != set(existing.availablePersonaModes):
            raise DTOValidationError(
                "use the preset management API to change availablePersonaModes"
            )
        _atomic_write_json(character_dir / "character.json", character)
        return self.get_admin_character(safe_id)

    def create_preset(
        self,
        character_id: str,
        preset: Mapping[str, Any],
    ) -> dict[str, Any]:
        safe_id = _safe_persona_id(character_id, "characterId")
        parsed = PersonaPreset.from_mapping(preset)
        if str(parsed.characterId) != safe_id:
            raise DTOValidationError("preset.characterId must match characterId")
        mode = _safe_persona_id(str(parsed.personaMode), "personaMode")
        character_dir = self._character_dir(safe_id)
        character_path = character_dir / "character.json"
        character = dict(self._read_json(character_path))
        profile = CharacterProfile.from_mapping(character)
        preset_path = character_dir / f"{mode}.json"
        if preset_path.exists() or parsed.personaMode in profile.availablePersonaModes:
            raise DTOValidationError(f"persona preset already exists: {mode}")
        modes = [str(item) for item in profile.availablePersonaModes]
        modes.append(mode)
        character["availablePersonaModes"] = modes
        CharacterProfile.from_mapping(character)
        _atomic_write_json(preset_path, preset)
        try:
            _atomic_write_json(character_path, character)
        except Exception:
            preset_path.unlink(missing_ok=True)
            raise
        return self.get_admin_character(safe_id)

    def update_preset(
        self,
        character_id: str,
        persona_mode: str,
        preset: Mapping[str, Any],
    ) -> dict[str, Any]:
        safe_id = _safe_persona_id(character_id, "characterId")
        safe_mode = _safe_persona_id(persona_mode, "personaMode")
        parsed = PersonaPreset.from_mapping(preset)
        if str(parsed.characterId) != safe_id or str(parsed.personaMode) != safe_mode:
            raise DTOValidationError("characterId and personaMode cannot be changed")
        character_dir = self._character_dir(safe_id)
        profile = self._load_character(character_dir)
        if parsed.personaMode not in profile.availablePersonaModes:
            raise AppError(
                code=ErrorCode.PERSONA_MODE_NOT_FOUND,
                message=f"Persona preset was not found: {safe_id}/{safe_mode}",
            )
        _atomic_write_json(character_dir / f"{safe_mode}.json", preset)
        return self.get_admin_character(safe_id)

    def delete_preset(self, character_id: str, persona_mode: str) -> dict[str, Any]:
        safe_id = _safe_persona_id(character_id, "characterId")
        safe_mode = _safe_persona_id(persona_mode, "personaMode")
        character_dir = self._character_dir(safe_id)
        character_path = character_dir / "character.json"
        character = dict(self._read_json(character_path))
        profile = CharacterProfile.from_mapping(character)
        if str(profile.defaultPersonaMode) == safe_mode:
            raise DTOValidationError("the default persona preset cannot be deleted")
        if safe_mode not in {str(item) for item in profile.availablePersonaModes}:
            raise AppError(code=ErrorCode.PERSONA_MODE_NOT_FOUND)
        preset_path = character_dir / f"{safe_mode}.json"
        previous_character = character_path.read_text(encoding="utf-8")
        character["availablePersonaModes"] = [
            str(item) for item in profile.availablePersonaModes if str(item) != safe_mode
        ]
        CharacterProfile.from_mapping(character)
        _atomic_write_json(character_path, character)
        try:
            preset_path.unlink()
        except Exception:
            character_path.write_text(previous_character, encoding="utf-8")
            raise
        return self.get_admin_character(safe_id)

    def delete_character(self, character_id: str) -> dict[str, Any]:
        safe_id = _safe_persona_id(character_id, "characterId")
        character_dir = self._character_dir(safe_id)
        profile = self._load_character(character_dir)
        for path in character_dir.iterdir():
            if path.is_symlink() or path.is_dir() or path.suffix != ".json":
                raise DTOValidationError(
                    "character directory contains unmanaged files and cannot be deleted"
                )
        shutil.rmtree(character_dir)
        return {"character_id": str(profile.characterId), "deleted": True}

    def _character_dir(self, character_id: str) -> Path:
        safe_id = _safe_persona_id(character_id, "characterId")
        root = self._root.resolve()
        path = (self._root / safe_id).resolve()
        if not path.is_relative_to(root):
            raise DTOValidationError("characterId contains an unsafe path")
        return path

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


def _safe_persona_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _SAFE_PERSONA_ID.fullmatch(value):
        raise DTOValidationError(
            f"{field_name} must contain only letters, digits, underscores, or hyphens"
        )
    return value


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _latest_modified_at(character_dir: Path) -> str:
    latest = max(path.stat().st_mtime for path in character_dir.glob("*.json"))
    return datetime.fromtimestamp(latest, tz=UTC).isoformat()


def _directory_writable(root: Path) -> bool:
    candidate = root if root.exists() else root.parent
    return candidate.is_dir() and os.access(candidate, os.W_OK)
