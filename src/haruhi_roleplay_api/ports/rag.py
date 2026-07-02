"""RAG service port."""

from __future__ import annotations

from typing import Protocol

from haruhi_roleplay_api.domain import RagRetrieveInput, RagRetrieveOutput


class RagService(Protocol):
    def retrieve(self, retrieve_input: RagRetrieveInput) -> RagRetrieveOutput:
        """Retrieve RAG chunks using already-built metadata filters."""
