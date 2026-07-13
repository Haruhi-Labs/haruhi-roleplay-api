"""Qdrant REST RAG adapter."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

from haruhi_roleplay_api.adapters.rag import (
    _chunk_text,
    _matches_filters,
    _metadata_with_title,
    _scoped_chunk_id,
)
from haruhi_roleplay_api.adapters.embeddings import HashEmbeddingProvider
from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.domain import (
    AppId,
    RagChunk,
    RagChunkId,
    RagDocumentId,
    RagDocumentMetadata,
    RagIngestInput,
    RagIngestResult,
    RagRetrieveInput,
    RagRetrieveOutput,
)
from haruhi_roleplay_api.ports import TextEmbeddingProvider


class QdrantRagService:
    provider_name = "qdrant-rag"

    def __init__(
        self,
        *,
        base_url: str,
        collection: str,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
        chunk_size: int = 320,
        embedding_provider: TextEmbeddingProvider | None = None,
        ensure_collection: bool = False,
    ) -> None:
        if not base_url.strip():
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="QDRANT_URL is required for qdrant RAG provider.",
            )
        if not collection.strip():
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="QDRANT_COLLECTION is required for qdrant RAG provider.",
            )
        if timeout_seconds <= 0:
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="QDRANT_TIMEOUT_MS must be positive.",
            )
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self._base_url = base_url.rstrip("/")
        self._collection = collection.strip()
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._chunk_size = chunk_size
        self._embedding_provider = embedding_provider or HashEmbeddingProvider()
        self._ensure_collection = ensure_collection
        self._collection_ready = False

    def ingest(self, ingest_input: RagIngestInput) -> RagIngestResult:
        document_scope = f"{ingest_input.appId}:{ingest_input.content}"
        document_id = ingest_input.documentId or RagDocumentId(
            f"ragdoc-{uuid5(NAMESPACE_URL, document_scope)}"
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
        try:
            if self._ensure_collection and not self._collection_ready:
                self._create_collection_if_needed()
                self._collection_ready = True
            self._request_json(
                "PUT",
                f"/collections/{self._collection}/points?wait=true",
                {
                    "points": [
                        {
                            "id": _point_id(self._collection, chunk.chunkId),
                            "vector": list(self._embedding_provider.embed(chunk.content)),
                            "payload": _payload_from_chunk(chunk),
                        }
                        for chunk in chunks
                    ]
                },
                error_code=ErrorCode.RAG_INGEST_FAILED,
            )
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                code=ErrorCode.RAG_INGEST_FAILED,
                message="Qdrant RAG ingest failed.",
            ) from exc
        return RagIngestResult(
            documentId=document_id,
            status="imported",
            chunkCount=len(chunks),
            metadata=metadata,
        )

    def retrieve(self, retrieve_input: RagRetrieveInput) -> RagRetrieveOutput:
        query_vector = self._embedding_provider.embed(retrieve_input.query)
        response = self._request_json(
            "POST",
            f"/collections/{self._collection}/points/search",
            {
                "vector": list(query_vector),
                "limit": retrieve_input.topK * 8,
                "with_payload": True,
                "filter": _qdrant_filter(retrieve_input),
            },
            error_code=ErrorCode.RAG_PROVIDER_ERROR,
        )
        result = response.get("result", [])
        if not isinstance(result, list):
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="Qdrant RAG response was invalid.",
            )
        raw_chunks = tuple(_chunk_from_qdrant_hit(hit) for hit in result)
        filtered = tuple(
            chunk for chunk in raw_chunks if _matches_filters(chunk, retrieve_input)
        )
        ranked = tuple(
            sorted(filtered, key=lambda chunk: chunk.score, reverse=True)
        )[: retrieve_input.topK]
        return RagRetrieveOutput(
            chunks=ranked,
            provider=self.provider_name,
            rawHitCount=len(result),
            filteredHitCount=len(filtered),
            rerankApplied=False,
        )

    def _create_collection_if_needed(self) -> None:
        self._request_json(
            "PUT",
            f"/collections/{self._collection}",
            {
                "vectors": {
                    "size": self._embedding_provider.dimensions,
                    "distance": "Cosine",
                }
            },
            error_code=ErrorCode.RAG_PROVIDER_ERROR,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any],
        *,
        error_code: ErrorCode,
    ) -> Mapping[str, Any]:
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self._timeout_seconds,
            ) as response:
                raw_body = response.read()
        except (TimeoutError, socket.timeout) as exc:
            raise AppError(
                code=error_code,
                message="Qdrant RAG provider timed out.",
            ) from exc
        except urllib.error.HTTPError as exc:
            raise AppError(
                code=error_code,
                message=f"Qdrant RAG provider failed with HTTP {exc.code}.",
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise AppError(
                code=error_code,
                message="Qdrant RAG provider request failed.",
            ) from exc
        if not raw_body:
            return {}
        try:
            data = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AppError(
                code=error_code,
                message="Qdrant RAG response was invalid.",
            ) from exc
        if not isinstance(data, Mapping):
            raise AppError(
                code=error_code,
                message="Qdrant RAG response was invalid.",
            )
        return data

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["api-key"] = self._api_key
        return headers


def _qdrant_filter(retrieve_input: RagRetrieveInput) -> dict[str, Any]:
    filters = retrieve_input.filters
    must: list[dict[str, Any]] = [
        {"key": "app_id", "match": {"value": str(retrieve_input.appId)}},
        {"key": "character_id", "match": {"value": str(retrieve_input.characterId)}}
    ]
    if filters.language is not None:
        must.append({"key": "language", "match": {"value": filters.language}})
    if filters.spoilerLevelMax is not None:
        must.append({"key": "spoiler_level", "range": {"lte": filters.spoilerLevelMax}})
    if len(filters.sourceTypes) == 1:
        must.append({"key": "source_type", "match": {"value": filters.sourceTypes[0]}})
    if len(filters.timelines) == 1:
        must.append({"key": "timeline", "match": {"value": filters.timelines[0]}})
    return {"must": must}


def _payload_from_chunk(chunk: RagChunk) -> dict[str, Any]:
    return {
        "app_id": (
            str(chunk.metadata.appId)
            if chunk.metadata.appId is not None
            else ""
        ),
        "document_id": str(chunk.documentId),
        "chunk_id": str(chunk.chunkId),
        "content": chunk.content,
        "title": str(chunk.metadata.extra.get("title", "")),
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
        "metadata": dict(chunk.metadata.extra),
    }


def _chunk_from_qdrant_hit(hit: Mapping[str, Any]) -> RagChunk:
    payload = hit.get("payload")
    if not isinstance(payload, Mapping):
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message="Qdrant RAG response was invalid.",
        )
    metadata_extra = payload.get("metadata", {})
    if not isinstance(metadata_extra, Mapping):
        metadata_extra = {}
    title = payload.get("title")
    if title:
        metadata_extra = {**dict(metadata_extra), "title": str(title)}
    return RagChunk(
        chunkId=RagChunkId(str(payload["chunk_id"])),
        documentId=RagDocumentId(str(payload["document_id"])),
        content=str(payload["content"]),
        score=float(hit.get("score", 0.0)),
        metadata=RagDocumentMetadata(
            appId=(
                AppId(str(payload["app_id"]))
                if payload.get("app_id")
                else None
            ),
            characterId=str(payload["character_id"]),
            personaMode=str(payload.get("persona_mode") or "") or None,
            timeline=str(payload["timeline"]),
            spoilerLevel=int(payload["spoiler_level"]),
            language=str(payload["language"]),
            sourceType=str(payload["source_type"]),
            trustLevel=str(payload.get("trust_level") or "") or None,
            extra=dict(metadata_extra),
        ),
    )


def _point_id(collection: str, chunk_id: RagChunkId) -> str:
    return str(uuid5(NAMESPACE_URL, f"{collection}:{chunk_id}"))
