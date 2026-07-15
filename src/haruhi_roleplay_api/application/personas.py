"""Persona catalog use cases."""

from __future__ import annotations

from typing import Any

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import PersonaPreset, Visibility, public_persona_presets
from haruhi_roleplay_api.ports import PersonaRepository


class ListPublicPersonas:
    def __init__(self, repository: PersonaRepository) -> None:
        self._repository = repository

    def execute(self) -> dict[str, Any]:
        characters = []
        for character in self._repository.list_characters():
            if character.visibility is not Visibility.PUBLIC:
                continue

            public_presets = public_persona_presets(
                self._repository.list_presets(character.characterId)
            )
            if not public_presets:
                continue
            if character.defaultPersonaMode not in {
                preset.personaMode for preset in public_presets
            }:
                raise AppError(
                    code=ErrorCode.PERSONA_MODE_NOT_FOUND,
                    message=(
                        "Default persona preset is not public: "
                        f"{character.characterId}/{character.defaultPersonaMode}"
                    ),
                )

            characters.append(
                {
                    "character_id": str(character.characterId),
                    "display_name": character.displayName,
                    "description": character.description,
                    "default_persona_mode": str(character.defaultPersonaMode),
                    "tags": list(character.tags),
                    "modes": [
                        _mode_summary(preset)
                        for preset in sorted_public_presets(public_presets)
                    ],
                }
            )

        return {"characters": characters}


def sorted_public_presets(
    presets: tuple[PersonaPreset, ...],
) -> tuple[PersonaPreset, ...]:
    return tuple(sorted(presets, key=lambda preset: str(preset.personaMode)))


def _mode_summary(preset: PersonaPreset) -> dict[str, Any]:
    return {
        "persona_mode": str(preset.personaMode),
        "display_name": preset.displayName,
        "timeline": preset.timeline,
        "description": preset.description,
        "rag_enabled_by_default": bool(
            preset.ragPolicy.get("enabledByDefault", False)
        ),
        "memory_enabled_by_default": bool(
            preset.memoryPolicy.get("enabledByDefault", False)
        ),
    }
