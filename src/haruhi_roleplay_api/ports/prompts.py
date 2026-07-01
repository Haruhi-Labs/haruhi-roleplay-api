"""Prompt builder port."""

from __future__ import annotations

from typing import Protocol

from haruhi_roleplay_api.domain import PromptBuildInput, PromptBuildOutput


class PromptBuilder(Protocol):
    def build(self, prompt_input: PromptBuildInput) -> PromptBuildOutput:
        """Build provider-ready messages from already prepared context."""

