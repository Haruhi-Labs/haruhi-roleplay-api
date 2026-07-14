"""Qdrant REST RAG adapter."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

from haruhi_roleplay_api.adapters.rag import (
    _ingest_content_chunks,
    _matches_filters,
    _managed_documents,
    _metadata_with_title,
    _scoped_chunk_id,
)
from haruhi_roleplay_api.adapters.embeddings import HashEmbeddingProvider
from haruhi_roleplay_api.adapters.rag_ranking import rank_roleplay_chunks
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


_QDRANT_PAYLOAD_INDEXES: tuple[tuple[str, str | Mapping[str, Any]], ...] = (
    ("app_id", {"type": "keyword", "is_tenant": True}),
    ("character_id", "keyword"),
    ("persona_mode", "keyword"),
    ("allowed_persona_modes", "keyword"),
    ("language", "keyword"),
    ("source_type", "keyword"),
    ("timeline", "keyword"),
    ("record_kind", "keyword"),
    ("perspective", "keyword"),
    ("corpus_version", "keyword"),
    ("retrieval_channel", "keyword"),
    ("knowledge_owner", "keyword"),
    ("subject_character_id", "keyword"),
    ("usage", "keyword"),
    ("document_id", "keyword"),
    ("scene_id", "keyword"),
    ("conversation_id", "keyword"),
    ("spoiler_level", "integer"),
    (
        "content",
        {
            "type": "text",
            "tokenizer": "multilingual",
            "lowercase": True,
        },
    ),
)


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
                _ingest_content_chunks(
                    ingest_input.content,
                    metadata=metadata,
                    chunk_size=self._chunk_size,
                ),
                start=1,
            )
        )
        try:
            if self._ensure_collection and not self._collection_ready:
                self.ensure_collection_schema()
            self._request_json(
                "PUT",
                f"/collections/{self._collection}/points?wait=true",
                {
                    "points": [
                        {
                            "id": _point_id(self._collection, chunk.chunkId),
                            "vector": list(
                                self._embedding_provider.embed(
                                    _contextual_embedding_text(chunk)
                                )
                            ),
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
        ranked = rank_roleplay_chunks(
            filtered,
            query=retrieve_input.query,
            top_k=retrieve_input.topK,
        )
        return RagRetrieveOutput(
            chunks=ranked,
            provider=self.provider_name,
            rawHitCount=len(result),
            filteredHitCount=len(filtered),
            rerankApplied=bool(filtered),
        )

    def list_documents(
        self,
        *,
        app_id: str | None = None,
    ) -> tuple[RagManagedDocument, ...]:
        all_points: list[Any] = []
        offset: Any = None
        while True:
            payload: dict[str, Any] = {
                "limit": 1000,
                "with_payload": True,
                "with_vector": False,
            }
            if app_id is not None:
                payload["filter"] = {
                    "must": [{"key": "app_id", "match": {"value": app_id}}]
                }
            if offset is not None:
                payload["offset"] = offset
            response = self._request_json(
                "POST",
                f"/collections/{self._collection}/points/scroll",
                payload,
                error_code=ErrorCode.RAG_PROVIDER_ERROR,
            )
            result = response.get("result", {})
            points = result.get("points", []) if isinstance(result, Mapping) else []
            if not isinstance(points, list):
                raise AppError(
                    code=ErrorCode.RAG_PROVIDER_ERROR,
                    message="Qdrant RAG management response was invalid.",
                )
            all_points.extend(points)
            offset = (
                result.get("next_page_offset")
                if isinstance(result, Mapping)
                else None
            )
            if offset is None:
                break
        chunks = tuple(_chunk_from_qdrant_hit(point) for point in all_points)
        return _managed_documents(
            chunks,
            provider=self.provider_name,
            app_id=app_id,
        )

    def delete_document(self, *, app_id: str, document_id: str) -> int:
        documents = self.list_documents(app_id=app_id)
        document = next(
            (item for item in documents if str(item.documentId) == document_id),
            None,
        )
        if document is None:
            raise AppError(code=ErrorCode.RAG_DOCUMENT_NOT_FOUND)
        self._request_json(
            "POST",
            f"/collections/{self._collection}/points/delete?wait=true",
            {
                "filter": {
                    "must": [
                        {"key": "app_id", "match": {"value": app_id}},
                        {
                            "key": "document_id",
                            "match": {"value": document_id},
                        },
                    ]
                }
            },
            error_code=ErrorCode.RAG_PROVIDER_ERROR,
        )
        return document.chunkCount

    @property
    def collection(self) -> str:
        return self._collection

    def ensure_collection_schema(self) -> None:
        """先创建过滤索引，再允许语料写入集合。"""

        if self._collection_ready:
            return
        collection_info = self._request_json(
            "GET",
            f"/collections/{self._collection}",
            None,
            error_code=ErrorCode.RAG_PROVIDER_ERROR,
            allow_not_found=True,
        )
        if collection_info is None:
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
            indexed_fields: set[str] = set()
        else:
            self._validate_collection_dimensions(collection_info)
            indexed_fields = _indexed_payload_fields(collection_info)

        for field_name, field_schema in _QDRANT_PAYLOAD_INDEXES:
            if field_name in indexed_fields:
                continue
            self._request_json(
                "PUT",
                f"/collections/{self._collection}/index?wait=true",
                {
                    "field_name": field_name,
                    "field_schema": field_schema,
                },
                error_code=ErrorCode.RAG_PROVIDER_ERROR,
            )
        self._collection_ready = True

    def _validate_collection_dimensions(
        self,
        collection_info: Mapping[str, Any],
    ) -> None:
        configured_size = _collection_vector_size(collection_info)
        if (
            configured_size is not None
            and configured_size != self._embedding_provider.dimensions
        ):
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message=(
                    f"Qdrant 集合 {self._collection} 的向量维度为 "
                    f"{configured_size}，当前 embedding provider 输出维度为 "
                    f"{self._embedding_provider.dimensions}。"
                ),
            )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None,
        *,
        error_code: ErrorCode,
        allow_not_found: bool = False,
    ) -> Mapping[str, Any] | None:
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=(
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
                if payload is not None
                else None
            ),
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
            if allow_not_found and exc.code == 404:
                return None
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
        {"key": "character_id", "match": {"value": str(retrieve_input.characterId)}},
        {
            "should": [
                {"key": "allowed_persona_modes", "match": {"value": "*"}},
                {
                    "key": "allowed_persona_modes",
                    "match": {"value": str(retrieve_input.personaMode)},
                },
                {"is_empty": {"key": "allowed_persona_modes"}},
            ]
        },
    ]
    if filters.language is not None:
        must.append({"key": "language", "match": {"value": filters.language}})
    if filters.spoilerLevelMax is not None:
        must.append({"key": "spoiler_level", "range": {"lte": filters.spoilerLevelMax}})
    if len(filters.sourceTypes) == 1:
        must.append({"key": "source_type", "match": {"value": filters.sourceTypes[0]}})
    elif filters.sourceTypes:
        must.append({"key": "source_type", "match": {"any": list(filters.sourceTypes)}})
    if len(filters.timelines) == 1:
        must.append({"key": "timeline", "match": {"value": filters.timelines[0]}})
    elif filters.timelines:
        must.append({"key": "timeline", "match": {"any": list(filters.timelines)}})
    for values, field in (
        (filters.recordKinds, "record_kind"),
        (filters.perspectives, "perspective"),
        (filters.corpusVersions, "corpus_version"),
        (filters.retrievalChannels, "retrieval_channel"),
        (filters.knowledgeOwners, "knowledge_owner"),
        (filters.usages, "usage"),
    ):
        if len(values) == 1:
            must.append({"key": field, "match": {"value": values[0]}})
        elif values:
            must.append({"key": field, "match": {"any": list(values)}})
    return {"must": must}


def _payload_from_chunk(chunk: RagChunk) -> dict[str, Any]:
    allowed_persona_modes = chunk.metadata.extra.get("allowed_persona_modes")
    payload = {
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
        "allowed_persona_modes": (
            list(allowed_persona_modes)
            if isinstance(allowed_persona_modes, list | tuple)
            else ["*"]
        ),
        "metadata": dict(chunk.metadata.extra),
    }
    for field in (
        "record_kind",
        "perspective",
        "corpus_version",
        "retrieval_channel",
        "knowledge_owner",
        "subject_character_id",
        "usage",
        "scene_id",
        "conversation_id",
    ):
        value = chunk.metadata.extra.get(field)
        if value is not None:
            payload[field] = value
    return payload


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
    for field in (
        "record_kind",
        "perspective",
        "corpus_version",
        "retrieval_channel",
        "knowledge_owner",
        "subject_character_id",
        "usage",
        "scene_id",
        "conversation_id",
    ):
        if field in payload and field not in metadata_extra:
            metadata_extra = {**dict(metadata_extra), field: payload[field]}
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


def _indexed_payload_fields(collection_info: Mapping[str, Any]) -> set[str]:
    result = collection_info.get("result")
    if not isinstance(result, Mapping):
        return set()
    payload_schema = result.get("payload_schema")
    if not isinstance(payload_schema, Mapping):
        return set()
    return {str(field_name) for field_name in payload_schema}


def _collection_vector_size(collection_info: Mapping[str, Any]) -> int | None:
    result = collection_info.get("result")
    if not isinstance(result, Mapping):
        return None
    config = result.get("config")
    if not isinstance(config, Mapping):
        return None
    params = config.get("params")
    if not isinstance(params, Mapping):
        return None
    vectors = params.get("vectors")
    if not isinstance(vectors, Mapping):
        return None
    size = vectors.get("size")
    return size if isinstance(size, int) else None


def _contextual_embedding_text(chunk: RagChunk) -> str:
    context = "；".join(
        str(value)
        for value in (
            chunk.metadata.extra.get("title"),
            chunk.metadata.extra.get("book_title"),
            chunk.metadata.extra.get("section_title"),
            chunk.metadata.extra.get("record_kind"),
            chunk.metadata.extra.get("perspective"),
        )
        if value
    )
    return f"{context}\n{chunk.content}" if context else chunk.content
