"""RAG service port."""

from __future__ import annotations

from typing import Protocol

from haruhi_roleplay_api.domain import (
    RagIngestInput,
    RagIngestResult,
    RagRetrieveInput,
    RagRetrieveOutput,
)


class RagService(Protocol):
    def retrieve(self, retrieve_input: RagRetrieveInput) -> RagRetrieveOutput:
        """Retrieve RAG chunks using already-built metadata filters."""


class RagIngestService(Protocol):
    def ingest(self, ingest_input: RagIngestInput) -> RagIngestResult:
        """Store one validated document and return ingest status."""
