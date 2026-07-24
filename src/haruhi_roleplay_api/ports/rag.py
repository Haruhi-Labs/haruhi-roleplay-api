"""RAG service port."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from haruhi_roleplay_api.domain import (
    RagIngestInput,
    RagIngestResult,
    RagManagedDocument,
    RagRetrieveInput,
    RagRetrieveOutput,
)


class RagService(Protocol):
    def retrieve(self, retrieve_input: RagRetrieveInput) -> RagRetrieveOutput:
        """Retrieve RAG chunks using already-built metadata filters."""


@runtime_checkable
class BatchRagService(Protocol):
    def retrieve_many(
        self,
        retrieve_inputs: Sequence[RagRetrieveInput],
    ) -> tuple[RagRetrieveOutput, ...]:
        """批量检索，并允许提供方复用同一查询的中间结果。"""


class RagIngestService(Protocol):
    def ingest(self, ingest_input: RagIngestInput) -> RagIngestResult:
        """Store one validated document and return ingest status."""


class RagAdminService(Protocol):
    def list_documents(
        self,
        *,
        app_id: str | None = None,
    ) -> tuple[RagManagedDocument, ...]:
        """List documents available in the actual retrieval backend."""

    def delete_document(self, *, app_id: str, document_id: str) -> int:
        """Delete one app-scoped document and return removed chunk count."""
