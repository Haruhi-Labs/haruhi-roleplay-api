"""Local vector RAG adapters with optional Chroma/Faiss backends."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from haruhi_roleplay_api.adapters.embeddings import HashEmbeddingProvider
from haruhi_roleplay_api.adapters.rag import (
    _chunk_text,
    _matches_filters,
    _managed_documents,
    _metadata_with_title,
    _scoped_chunk_id,
)
from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    AppId,
    RagChunk,
    RagChunkId,
    RagDocumentId,
    RagDocumentMetadata,
    RagIngestInput,
    RagIngestResult,
    RagManagedDocument,
    RagRetrieveInput,
    RagRetrieveOutput,
)
from haruhi_roleplay_api.ports import TextEmbeddingProvider


@dataclass(frozen=True, kw_only=True)
class VectorSearchHit:
    chunk: RagChunk
    score: float


class VectorStore(Protocol):
    def upsert(self, chunks: tuple[RagChunk, ...], vectors: tuple[tuple[float, ...], ...]) -> None:
        """Store chunks with already computed vectors."""

    def search(
        self,
        *,
        query_vector: tuple[float, ...],
        retrieve_input: RagRetrieveInput,
    ) -> tuple[VectorSearchHit, ...]:
        """Search and return candidate hits."""

    def list_chunks(self, *, app_id: str | None = None) -> tuple[RagChunk, ...]:
        """List stored chunks for management."""

    def delete_document(self, *, app_id: str, document_id: str) -> int:
        """Delete one app-scoped document."""


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._records: list[tuple[RagChunk, tuple[float, ...]]] = []

    def upsert(
        self,
        chunks: tuple[RagChunk, ...],
        vectors: tuple[tuple[float, ...], ...],
    ) -> None:
        existing = {str(chunk.chunkId): index for index, (chunk, _) in enumerate(self._records)}
        for chunk, vector in zip(chunks, vectors, strict=True):
            record = (chunk, vector)
            index = existing.get(str(chunk.chunkId))
            if index is None:
                self._records.append(record)
            else:
                self._records[index] = record

    def search(
        self,
        *,
        query_vector: tuple[float, ...],
        retrieve_input: RagRetrieveInput,
    ) -> tuple[VectorSearchHit, ...]:
        hits = tuple(
            VectorSearchHit(chunk=chunk, score=_cosine(query_vector, vector))
            for chunk, vector in self._records
            if _matches_filters(chunk, retrieve_input)
        )
        return tuple(
            hit for hit in sorted(hits, key=lambda item: item.score, reverse=True)
            if hit.score > 0
        )

    def list_chunks(self, *, app_id: str | None = None) -> tuple[RagChunk, ...]:
        return tuple(
            chunk
            for chunk, _ in self._records
            if app_id is None or str(chunk.metadata.appId) == app_id
        )

    def delete_document(self, *, app_id: str, document_id: str) -> int:
        before = len(self._records)
        self._records = [
            record
            for record in self._records
            if not (
                str(record[0].metadata.appId) == app_id
                and str(record[0].documentId) == document_id
            )
        ]
        removed = before - len(self._records)
        if removed == 0:
            raise AppError(code=ErrorCode.RAG_DOCUMENT_NOT_FOUND)
        return removed


class FaissVectorStore:
    """Optional local Faiss vector store.

    This backend is intentionally optional. Install `faiss-cpu` in the local
    environment before selecting `RAG_PROVIDER=faiss`.
    """

    def __init__(self, *, dimensions: int) -> None:
        faiss = _optional_module("faiss", package_name="faiss-cpu")
        self._faiss = faiss
        self._index = faiss.IndexFlatIP(dimensions)
        self._chunks: list[RagChunk] = []
        self._vectors: list[tuple[float, ...]] = []

    def upsert(
        self,
        chunks: tuple[RagChunk, ...],
        vectors: tuple[tuple[float, ...], ...],
    ) -> None:
        self._chunks.extend(chunks)
        self._vectors.extend(vectors)
        self._index.add(_float32_matrix(vectors))

    def search(
        self,
        *,
        query_vector: tuple[float, ...],
        retrieve_input: RagRetrieveInput,
    ) -> tuple[VectorSearchHit, ...]:
        if not self._chunks:
            return ()
        scores, indexes = self._index.search(
            _float32_matrix((query_vector,)),
            min(len(self._chunks), retrieve_input.topK * 8),
        )
        hits: list[VectorSearchHit] = []
        for score, index in zip(scores[0], indexes[0], strict=False):
            if index < 0:
                continue
            chunk = self._chunks[int(index)]
            if float(score) > 0 and _matches_filters(chunk, retrieve_input):
                hits.append(VectorSearchHit(chunk=chunk, score=float(score)))
        return tuple(hits)

    def list_chunks(self, *, app_id: str | None = None) -> tuple[RagChunk, ...]:
        return tuple(
            chunk
            for chunk in self._chunks
            if app_id is None or str(chunk.metadata.appId) == app_id
        )

    def delete_document(self, *, app_id: str, document_id: str) -> int:
        kept = [
            (chunk, vector)
            for chunk, vector in zip(self._chunks, self._vectors, strict=True)
            if not (
                str(chunk.metadata.appId) == app_id
                and str(chunk.documentId) == document_id
            )
        ]
        removed = len(self._chunks) - len(kept)
        if removed == 0:
            raise AppError(code=ErrorCode.RAG_DOCUMENT_NOT_FOUND)
        self._chunks = [chunk for chunk, _ in kept]
        self._vectors = [vector for _, vector in kept]
        self._index.reset()
        if self._vectors:
            self._index.add(_float32_matrix(tuple(self._vectors)))
        return removed


class ChromaVectorStore:
    """Optional local Chroma vector store."""

    def __init__(
        self,
        *,
        collection_name: str,
        persist_path: str | None = None,
    ) -> None:
        chromadb = _optional_module("chromadb", package_name="chromadb")
        client = (
            chromadb.PersistentClient(path=persist_path)
            if persist_path
            else chromadb.Client()
        )
        self._collection = client.get_or_create_collection(collection_name)

    def upsert(
        self,
        chunks: tuple[RagChunk, ...],
        vectors: tuple[tuple[float, ...], ...],
    ) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[str(chunk.chunkId) for chunk in chunks],
            embeddings=[list(vector) for vector in vectors],
            documents=[chunk.content for chunk in chunks],
            metadatas=[_payload_from_chunk(chunk) for chunk in chunks],
        )

    def search(
        self,
        *,
        query_vector: tuple[float, ...],
        retrieve_input: RagRetrieveInput,
    ) -> tuple[VectorSearchHit, ...]:
        result = self._collection.query(
            query_embeddings=[list(query_vector)],
            n_results=retrieve_input.topK * 8,
            where={"app_id": str(retrieve_input.appId)},
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        hits: list[VectorSearchHit] = []
        for chunk_id, document, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
            strict=False,
        ):
            chunk = _chunk_from_payload(str(chunk_id), str(document), metadata)
            if _matches_filters(chunk, retrieve_input):
                hits.append(
                    VectorSearchHit(
                        chunk=chunk,
                        score=max(0.0, 1.0 - float(distance)),
                    )
                )
        return tuple(hit for hit in hits if hit.score > 0)

    def list_chunks(self, *, app_id: str | None = None) -> tuple[RagChunk, ...]:
        arguments: dict[str, Any] = {"include": ["documents", "metadatas"]}
        if app_id is not None:
            arguments["where"] = {"app_id": app_id}
        result = self._collection.get(**arguments)
        return tuple(
            _chunk_from_payload(str(chunk_id), str(document), metadata)
            for chunk_id, document, metadata in zip(
                result.get("ids", []),
                result.get("documents", []),
                result.get("metadatas", []),
                strict=False,
            )
        )

    def delete_document(self, *, app_id: str, document_id: str) -> int:
        where = {
            "$and": [
                {"app_id": app_id},
                {"document_id": document_id},
            ]
        }
        result = self._collection.get(where=where, include=[])
        ids = list(result.get("ids", []))
        if not ids:
            raise AppError(code=ErrorCode.RAG_DOCUMENT_NOT_FOUND)
        self._collection.delete(ids=ids)
        return len(ids)


class LocalVectorRagService:
    provider_name = "local-vector-rag"

    def __init__(
        self,
        *,
        chunk_size: int = 320,
        embedding_provider: TextEmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        backend: str = "memory",
        chroma_collection: str = "haruhi_rag",
        chroma_persist_path: str | None = None,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self._chunk_size = chunk_size
        self._embedding_provider = embedding_provider or HashEmbeddingProvider()
        self._vector_store = vector_store or _vector_store_for_backend(
            backend,
            dimensions=self._embedding_provider.dimensions,
            chroma_collection=chroma_collection,
            chroma_persist_path=chroma_persist_path,
        )

    def ingest(self, ingest_input: RagIngestInput) -> RagIngestResult:
        document_id = ingest_input.documentId or RagDocumentId(
            _document_id_for_content(ingest_input.appId, ingest_input.content)
        )
        metadata = _metadata_with_title(ingest_input.metadata, ingest_input.title)
        chunks = tuple(
            RagChunk(
                chunkId=_scoped_chunk_id(ingest_input.appId, document_id, index),
                documentId=document_id,
                content=content,
                score=0.0,
                metadata=metadata,
            )
            for index, content in enumerate(
                _chunk_text(ingest_input.content, self._chunk_size),
                start=1,
            )
        )
        vectors = tuple(
            _normalize_embedding(self._embedding_provider.embed(chunk.content))
            for chunk in chunks
        )
        self._vector_store.upsert(chunks, vectors)
        return RagIngestResult(
            documentId=document_id,
            status="imported",
            chunkCount=len(chunks),
            metadata=metadata,
        )

    def retrieve(self, retrieve_input: RagRetrieveInput) -> RagRetrieveOutput:
        query_vector = _normalize_embedding(
            self._embedding_provider.embed(retrieve_input.query)
        )
        hits = self._vector_store.search(
            query_vector=query_vector,
            retrieve_input=retrieve_input,
        )
        chunks = tuple(
            _chunk_with_score(hit.chunk, hit.score)
            for hit in sorted(hits, key=lambda item: item.score, reverse=True)[
                : retrieve_input.topK
            ]
        )
        return RagRetrieveOutput(
            chunks=chunks,
            provider=self.provider_name,
            rawHitCount=len(hits),
            filteredHitCount=len(chunks),
            rerankApplied=False,
        )

    def list_documents(
        self,
        *,
        app_id: str | None = None,
    ) -> tuple[RagManagedDocument, ...]:
        return _managed_documents(
            self._vector_store.list_chunks(app_id=app_id),
            provider=self.provider_name,
            app_id=app_id,
        )

    def delete_document(self, *, app_id: str, document_id: str) -> int:
        return self._vector_store.delete_document(
            app_id=app_id,
            document_id=document_id,
        )


def _vector_store_for_backend(
    backend: str,
    *,
    dimensions: int,
    chroma_collection: str,
    chroma_persist_path: str | None,
) -> VectorStore:
    normalized = backend.strip().lower().replace("-", "_")
    if normalized in {"memory", "in_memory"}:
        return InMemoryVectorStore()
    if normalized == "faiss":
        return FaissVectorStore(dimensions=dimensions)
    if normalized == "chroma":
        return ChromaVectorStore(
            collection_name=chroma_collection,
            persist_path=chroma_persist_path,
        )
    raise AppError(
        code=ErrorCode.RAG_PROVIDER_ERROR,
        message=f"Local vector RAG backend is not supported: {backend}",
    )


def _normalize_embedding(vector: tuple[float, ...]) -> tuple[float, ...]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return tuple(value / magnitude for value in vector)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _chunk_with_score(chunk: RagChunk, score: float) -> RagChunk:
    return RagChunk(
        chunkId=chunk.chunkId,
        documentId=chunk.documentId,
        content=chunk.content,
        score=score,
        metadata=chunk.metadata,
    )


def _payload_from_chunk(chunk: RagChunk) -> dict[str, Any]:
    return {
        "app_id": (
            str(chunk.metadata.appId)
            if chunk.metadata.appId is not None
            else ""
        ),
        "document_id": str(chunk.documentId),
        "character_id": str(chunk.metadata.characterId),
        "persona_mode": (
            str(chunk.metadata.personaMode)
            if chunk.metadata.personaMode is not None
            else ""
        ),
        "timeline": chunk.metadata.timeline,
        "spoiler_level": chunk.metadata.spoilerLevel,
        "language": chunk.metadata.language,
        "source_type": chunk.metadata.sourceType,
        "trust_level": chunk.metadata.trustLevel or "",
        "title": str(chunk.metadata.extra.get("title", "")),
        "metadata_json": json.dumps(dict(chunk.metadata.extra), ensure_ascii=False),
    }


def _chunk_from_payload(
    chunk_id: str,
    content: str,
    payload: Mapping[str, Any],
) -> RagChunk:
    extra = _metadata_extra_from_payload(payload)
    return RagChunk(
        chunkId=RagChunkId(chunk_id),
        documentId=RagDocumentId(str(payload["document_id"])),
        content=content,
        score=0.0,
        metadata=RagDocumentMetadata(
            appId=(
                AppId(str(payload["app_id"]))
                if payload.get("app_id")
                else None
            ),
            characterId=str(payload["character_id"]),
            personaMode=str(payload["persona_mode"]) or None,
            timeline=str(payload["timeline"]),
            spoilerLevel=int(payload["spoiler_level"]),
            language=str(payload["language"]),
            sourceType=str(payload["source_type"]),
            trustLevel=str(payload["trust_level"]) or None,
            extra=extra,
        ),
    )


def _metadata_extra_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = payload.get("metadata_json")
    if isinstance(raw, str) and raw:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {}
        if isinstance(value, Mapping):
            return dict(value)
    title = payload.get("title")
    return {"title": title} if title else {}


def _document_id_for_content(app_id: AppId, content: str) -> str:
    scoped_content = f"{app_id}\0{content}"
    digest = hashlib.blake2b(
        scoped_content.encode("utf-8"),
        digest_size=8,
    ).hexdigest()
    return f"ragdoc-{digest}"


def _optional_module(module_name: str, *, package_name: str):
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message=(
                f"{package_name} is required for this local vector RAG backend."
            ),
        ) from exc


def _float32_matrix(vectors: tuple[tuple[float, ...], ...]):
    numpy = _optional_module("numpy", package_name="numpy")
    return numpy.asarray(vectors, dtype="float32")
