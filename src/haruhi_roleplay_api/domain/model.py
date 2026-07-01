"""Model provider domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from haruhi_roleplay_api.domain.chat import DTOValidationError, GenerationConfig
from haruhi_roleplay_api.domain.prompt import PromptMessage


def _require_non_empty(value: str | None, field_name: str) -> str:
    if value is None:
        raise DTOValidationError(f"{field_name} is required")
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True, kw_only=True)
class ModelMessage:
    role: str
    content: str

    @classmethod
    def from_prompt_message(cls, message: PromptMessage) -> "ModelMessage":
        return cls(role=message.role, content=message.content)

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant"}:
            raise DTOValidationError(f"model message role is not supported: {self.role}")
        _require_non_empty(self.content, "model message content")

    def to_mapping(self) -> dict[str, str]:
        return {
            "role": self.role,
            "content": self.content,
        }


@dataclass(frozen=True, kw_only=True)
class ModelRequest:
    messages: tuple[ModelMessage, ...]
    model: str
    generation: GenerationConfig | None = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise DTOValidationError("model request messages must not be empty")
        _require_non_empty(self.model, "model")
        if self.generation is not None and not isinstance(
            self.generation,
            GenerationConfig,
        ):
            raise DTOValidationError("generation must be GenerationConfig")


@dataclass(frozen=True, kw_only=True)
class ModelUsage:
    promptTokens: int
    completionTokens: int

    def __post_init__(self) -> None:
        if self.promptTokens < 0:
            raise DTOValidationError("usage.promptTokens must be >= 0")
        if self.completionTokens < 0:
            raise DTOValidationError("usage.completionTokens must be >= 0")

    @property
    def totalTokens(self) -> int:
        return self.promptTokens + self.completionTokens

    def to_mapping(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.promptTokens,
            "completion_tokens": self.completionTokens,
            "total_tokens": self.totalTokens,
        }


@dataclass(frozen=True, kw_only=True)
class ModelResponse:
    reply: str
    provider: str
    model: str
    usage: ModelUsage
    debug: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty(self.reply, "reply")
        _require_non_empty(self.provider, "provider")
        _require_non_empty(self.model, "model")
        if not isinstance(self.usage, ModelUsage):
            raise DTOValidationError("usage must be ModelUsage")


def model_messages_from_prompt(
    messages: Iterable[PromptMessage],
) -> tuple[ModelMessage, ...]:
    return tuple(ModelMessage.from_prompt_message(message) for message in messages)
