"""Prompt build domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field

from haruhi_roleplay_api.domain.chat import (
    CapabilityConfig,
    DTOValidationError,
    GenerationConfig,
)
from haruhi_roleplay_api.domain.persona import CharacterProfile, PersonaPreset


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True, kw_only=True)
class PromptMessage:
    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant"}:
            raise DTOValidationError(
                f"prompt message role is not supported: {self.role}"
            )
        _require_non_empty(self.content, "prompt message content")

    def to_mapping(self) -> dict[str, str]:
        return {
            "role": self.role,
            "content": self.content,
        }


@dataclass(frozen=True, kw_only=True)
class PromptBuildInput:
    character: CharacterProfile
    persona: PersonaPreset
    userMessage: str
    capabilities: CapabilityConfig = field(default_factory=CapabilityConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)

    def __post_init__(self) -> None:
        if self.character.characterId != self.persona.characterId:
            raise DTOValidationError(
                "character and persona must use the same characterId"
            )
        _require_non_empty(self.userMessage, "userMessage")
        if not isinstance(self.capabilities, CapabilityConfig):
            raise DTOValidationError("capabilities must be CapabilityConfig")
        if not isinstance(self.generation, GenerationConfig):
            raise DTOValidationError("generation must be GenerationConfig")


@dataclass(frozen=True, kw_only=True)
class PromptBuildOutput:
    messages: tuple[PromptMessage, ...]

    def __post_init__(self) -> None:
        if not self.messages:
            raise DTOValidationError("messages must not be empty")

    def to_provider_messages(self) -> list[dict[str, str]]:
        return [message.to_mapping() for message in self.messages]
