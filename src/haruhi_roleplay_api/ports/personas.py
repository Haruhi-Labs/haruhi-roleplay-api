"""Persona repository port."""

from __future__ import annotations

from typing import Protocol

from haruhi_roleplay_api.domain import CharacterId, CharacterProfile, PersonaPreset


class PersonaRepository(Protocol):
    def list_characters(self) -> tuple[CharacterProfile, ...]:
        """Return all configured character profiles."""

    def list_presets(self, character_id: CharacterId | str) -> tuple[PersonaPreset, ...]:
        """Return all configured presets for one character."""

