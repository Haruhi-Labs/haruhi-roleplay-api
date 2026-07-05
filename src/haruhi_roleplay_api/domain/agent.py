"""Agent planning domain objects."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from haruhi_roleplay_api.domain.chat import DTOValidationError


_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


@dataclass(frozen=True, kw_only=True)
class ContextPlan:
    planner: str
    status: str
    readSession: bool = False
    readMemory: bool = False
    retrieveRag: bool = False
    backendFetches: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_safe_label(self.planner, "contextPlan.planner")
        _require_safe_label(self.status, "contextPlan.status")
        for index, source in enumerate(self.backendFetches):
            _require_safe_label(source, f"contextPlan.backendFetches[{index}]")
        for index, note in enumerate(self.notes):
            _require_safe_label(note, f"contextPlan.notes[{index}]")

    def to_debug_mapping(self) -> dict[str, Any]:
        return {
            "planner": self.planner,
            "status": self.status,
            "readSession": self.readSession,
            "readMemory": self.readMemory,
            "retrieveRag": self.retrieveRag,
            "backendFetches": list(self.backendFetches),
            "notes": list(self.notes),
        }


def _require_safe_label(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DTOValidationError(f"{field_name} must be a non-empty string")
    if not _SAFE_LABEL_RE.fullmatch(value):
        raise DTOValidationError(f"{field_name} contains unsupported characters")
