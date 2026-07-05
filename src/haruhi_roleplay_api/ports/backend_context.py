"""Backend context provider port."""

from __future__ import annotations

from typing import Protocol

from haruhi_roleplay_api.domain import BackendContextFact, BackendContextRequest


class BackendContextProvider(Protocol):
    def fetch(
        self,
        request: BackendContextRequest,
    ) -> tuple[BackendContextFact, ...]:
        """Return safe facts for the requested backend context sources."""
