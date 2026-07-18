"""Qdrant REST RAG adapter."""

from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Any, Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

from haruhi_roleplay_api.adapters.rag import (
    _ingest_content_chunks,
    _matches_filters,
    _managed_documents,
    _metadata_with_title,
    _scoped_chunk_id,
)
from haruhi_roleplay_api.adapters.embeddings import HashEmbeddingProvider
from haruhi_roleplay_api.adapters.rag_ranking import (
    lexical_overlap_score,
    rank_roleplay_chunks,
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
_CURRENT_INPUT_MARKER = "当前用户输入：\n"
_NON_SEARCH_CHARACTER = re.compile(r"[\W_]+", re.UNICODE)
_RRF_K = 60
_MAX_REQUEST_ATTEMPTS = 4
_RETRY_BACKOFF_SECONDS = (0.5, 1.0, 2.0)
_RETRYABLE_HTTP_STATUS = {408, 409, 429, 500, 502, 503, 504}


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
        hybrid_search: bool = False,
        ingest_batch_size: int = 64,
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
        if ingest_batch_size <= 0:
            raise ValueError("ingest_batch_size must be positive")
        self._base_url = base_url.rstrip("/")
        self._collection = collection.strip()
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._chunk_size = chunk_size
        self._embedding_provider = embedding_provider or HashEmbeddingProvider()
        self._ensure_collection = ensure_collection
        self._hybrid_search = hybrid_search
        self._ingest_batch_size = ingest_batch_size
        self._collection_ready = False

    def ingest(self, ingest_input: RagIngestInput) -> RagIngestResult:
        return self.ingest_batch((ingest_input,))[0]

    def ingest_batch(
        self,
        ingest_inputs: Sequence[RagIngestInput],
    ) -> tuple[RagIngestResult, ...]:
        if not ingest_inputs:
            return ()
        prepared = tuple(self._prepare_ingest(item) for item in ingest_inputs)
        all_chunks = tuple(
            chunk for _, _, chunks in prepared for chunk in chunks
        )
        try:
            if self._ensure_collection and not self._collection_ready:
                self.ensure_collection_schema()
            for chunks in _batched(all_chunks, self._ingest_batch_size):
                vectors = self._embedding_provider.embed_many(
                    tuple(_contextual_embedding_text(chunk) for chunk in chunks)
                )
                if len(vectors) != len(chunks):
                    raise AppError(
                        code=ErrorCode.RAG_INGEST_FAILED,
                        message="批量 embedding 返回数量与输入不一致。",
                    )
                self._request_json(
                    "PUT",
                    f"/collections/{self._collection}/points?wait=true",
                    {
                        "points": [
                            {
                                "id": _point_id(self._collection, chunk.chunkId),
                                "vector": list(vector),
                                "payload": _payload_from_chunk(chunk),
                            }
                            for chunk, vector in zip(chunks, vectors, strict=True)
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
        return tuple(
            RagIngestResult(
                documentId=document_id,
                status="imported",
                chunkCount=len(chunks),
                metadata=metadata,
            )
            for document_id, metadata, chunks in prepared
        )

    def _prepare_ingest(
        self,
        ingest_input: RagIngestInput,
    ) -> tuple[RagDocumentId, RagDocumentMetadata, tuple[RagChunk, ...]]:
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
        return document_id, metadata, chunks

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
        result = response.get("result", []) if response is not None else []
        if not isinstance(result, list):
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="Qdrant RAG response was invalid.",
            )
        dense_chunks = tuple(_chunk_from_qdrant_hit(hit) for hit in result)
        lexical_chunks = self._lexical_candidates(retrieve_input)
        raw_chunks = (
            _reciprocal_rank_fusion(
                dense_chunks,
                lexical_chunks,
                query=retrieve_input.query,
            )
            if lexical_chunks
            else dense_chunks
        )
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
            rawHitCount=len(raw_chunks),
            filteredHitCount=len(filtered),
            rerankApplied=bool(filtered),
        )

    def _lexical_candidates(
        self,
        retrieve_input: RagRetrieveInput,
    ) -> tuple[RagChunk, ...]:
        if not self._hybrid_search:
            return ()
        lexical_query = _lexical_query(retrieve_input.query)
        if not lexical_query:
            return ()
        hard_filter = _qdrant_filter(retrieve_input)
        response = self._request_json(
            "POST",
            f"/collections/{self._collection}/points/scroll",
            {
                "limit": retrieve_input.topK * 8,
                "with_payload": True,
                "with_vector": False,
                "filter": {
                    "must": [
                        *hard_filter["must"],
                        {
                            "key": "content",
                            "match": {"text_any": lexical_query},
                        },
                    ]
                },
            },
            error_code=ErrorCode.RAG_PROVIDER_ERROR,
        )
        result = response.get("result") if response is not None else None
        points = result.get("points") if isinstance(result, Mapping) else None
        if not isinstance(points, list):
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="Qdrant 全文候选响应格式无效。",
            )
        return tuple(_chunk_from_qdrant_hit(point) for point in points)

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

    def list_documents_limited(
        self,
        *,
        app_id: str,
        limit: int,
    ) -> tuple[tuple[RagManagedDocument, ...], bool]:
        """通过 payload facet 只读取有限数量的应用内文档。"""
        facet_response = self._request_json(
            "POST",
            f"/collections/{self._collection}/facet",
            {
                "key": "document_id",
                "limit": limit + 1,
                "exact": True,
                "filter": {
                    "must": [
                        {"key": "app_id", "match": {"value": app_id}}
                    ]
                },
            },
            error_code=ErrorCode.RAG_PROVIDER_ERROR,
        )
        facet_result = (
            facet_response.get("result") if facet_response is not None else None
        )
        facet_hits = (
            facet_result.get("hits")
            if isinstance(facet_result, Mapping)
            else None
        )
        if not isinstance(facet_hits, list):
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="Qdrant 文档分面响应格式无效。",
            )
        selected_hits = facet_hits[:limit]
        document_ids = [
            str(hit["value"])
            for hit in selected_hits
            if isinstance(hit, Mapping) and hit.get("value") is not None
        ]
        if not document_ids:
            return (), False

        all_points: list[Any] = []
        offset: Any = None
        while True:
            payload: dict[str, Any] = {
                "limit": 1000,
                "with_payload": True,
                "with_vector": False,
                "filter": {
                    "must": [
                        {"key": "app_id", "match": {"value": app_id}},
                        {
                            "key": "document_id",
                            "match": {"any": document_ids},
                        },
                    ]
                },
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
                    message="Qdrant 文档列表响应格式无效。",
                )
            all_points.extend(points)
            offset = (
                result.get("next_page_offset")
                if isinstance(result, Mapping)
                else None
            )
            if offset is None:
                break

        documents = _managed_documents(
            tuple(_chunk_from_qdrant_hit(point) for point in all_points),
            provider=self.provider_name,
            app_id=app_id,
        )
        by_document_id = {str(item.documentId): item for item in documents}
        ordered = tuple(
            by_document_id[document_id]
            for document_id in document_ids
            if document_id in by_document_id
        )
        return ordered, len(facet_hits) > limit

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

    def collection_exists(self) -> bool:
        return self._request_json(
            "GET",
            f"/collections/{self._collection}",
            None,
            error_code=ErrorCode.RAG_PROVIDER_ERROR,
            allow_not_found=True,
        ) is not None

    def count_points(self, *, app_id: str | None = None) -> int:
        payload: dict[str, Any] = {"exact": True}
        if app_id is not None:
            payload["filter"] = {
                "must": [{"key": "app_id", "match": {"value": app_id}}]
            }
        response = self._request_json(
            "POST",
            f"/collections/{self._collection}/points/count",
            payload,
            error_code=ErrorCode.RAG_PROVIDER_ERROR,
        )
        result = response.get("result") if response is not None else None
        count = result.get("count") if isinstance(result, Mapping) else None
        if not isinstance(count, int):
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="Qdrant point 计数响应格式无效。",
            )
        return count

    def aliases(self) -> dict[str, str]:
        response = self._request_json(
            "GET",
            "/aliases",
            None,
            error_code=ErrorCode.RAG_PROVIDER_ERROR,
        )
        result = response.get("result") if response is not None else None
        aliases = result.get("aliases") if isinstance(result, Mapping) else None
        if not isinstance(aliases, list):
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message="Qdrant alias 列表响应格式无效。",
            )
        mapped: dict[str, str] = {}
        for item in aliases:
            if not isinstance(item, Mapping):
                continue
            alias_name = item.get("alias_name")
            collection_name = item.get("collection_name")
            if isinstance(alias_name, str) and isinstance(collection_name, str):
                mapped[alias_name] = collection_name
        return mapped

    def switch_alias(self, alias_name: str) -> str | None:
        alias = alias_name.strip()
        if not alias:
            raise ValueError("Qdrant alias 不能为空")
        if alias == self._collection:
            raise ValueError("Qdrant alias 不能与物理集合重名")
        aliases = self.aliases()
        previous_collection = aliases.get(alias)
        if previous_collection == self._collection:
            return previous_collection
        actions: list[dict[str, Any]] = []
        if previous_collection is not None:
            actions.append({"delete_alias": {"alias_name": alias}})
        actions.append(
            {
                "create_alias": {
                    "collection_name": self._collection,
                    "alias_name": alias,
                }
            }
        )
        self._request_json(
            "POST",
            "/collections/aliases",
            {"actions": actions},
            error_code=ErrorCode.RAG_PROVIDER_ERROR,
        )
        return previous_collection

    def delete_collection(self) -> None:
        referenced_by = [
            alias_name
            for alias_name, collection_name in self.aliases().items()
            if collection_name == self._collection
        ]
        if referenced_by:
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message=(
                    f"不能删除仍被 alias 引用的 Qdrant 集合 {self._collection}："
                    + "、".join(sorted(referenced_by))
                ),
            )
        response = self._request_json(
            "DELETE",
            f"/collections/{self._collection}",
            None,
            error_code=ErrorCode.RAG_PROVIDER_ERROR,
            allow_not_found=True,
        )
        if response is None:
            raise AppError(
                code=ErrorCode.RAG_PROVIDER_ERROR,
                message=f"Qdrant 集合不存在：{self._collection}",
            )

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
        raw_body: bytes | None = None
        for attempt in range(_MAX_REQUEST_ATTEMPTS):
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
                break
            except (TimeoutError, socket.timeout) as exc:
                if _retry_request(method, path, attempt):
                    continue
                raise AppError(
                    code=error_code,
                    message="Qdrant RAG provider timed out.",
                ) from exc
            except urllib.error.HTTPError as exc:
                if allow_not_found and exc.code == 404:
                    return None
                if (
                    exc.code in _RETRYABLE_HTTP_STATUS
                    and _retry_request(method, path, attempt)
                ):
                    continue
                raise AppError(
                    code=error_code,
                    message=f"Qdrant RAG provider failed with HTTP {exc.code}.",
                ) from exc
            except (urllib.error.URLError, OSError) as exc:
                if _retry_request(method, path, attempt):
                    continue
                raise AppError(
                    code=error_code,
                    message="Qdrant RAG provider request failed.",
                ) from exc
        if raw_body is None:
            raise AppError(
                code=error_code,
                message="Qdrant RAG provider request failed.",
            )
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


def _retry_request(method: str, path: str, attempt: int) -> bool:
    if attempt >= len(_RETRY_BACKOFF_SECONDS):
        return False
    if not _is_idempotent_request(method, path):
        return False
    time.sleep(_RETRY_BACKOFF_SECONDS[attempt])
    return True


def _is_idempotent_request(method: str, path: str) -> bool:
    normalized_method = method.upper()
    if normalized_method in {"GET", "PUT"}:
        return True
    if normalized_method != "POST":
        return False
    return any(
        marker in path
        for marker in (
            "/points/search",
            "/points/scroll",
            "/points/count",
            "/points/delete",
        )
    )


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


def _batched(
    chunks: tuple[RagChunk, ...],
    batch_size: int,
) -> tuple[tuple[RagChunk, ...], ...]:
    return tuple(
        chunks[index : index + batch_size]
        for index in range(0, len(chunks), batch_size)
    )


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


def _lexical_query(query: str) -> str:
    candidate = (
        query.rsplit(_CURRENT_INPUT_MARKER, maxsplit=1)[-1]
        if _CURRENT_INPUT_MARKER in query
        else query
    )
    normalized = " ".join(candidate.split())[:256]
    searchable = _NON_SEARCH_CHARACTER.sub("", normalized)
    return normalized if len(searchable) >= 2 else ""


def _reciprocal_rank_fusion(
    dense_chunks: tuple[RagChunk, ...],
    lexical_chunks: tuple[RagChunk, ...],
    *,
    query: str,
) -> tuple[RagChunk, ...]:
    lexical_query = _lexical_query(query) or query
    lexical_ranked = sorted(
        lexical_chunks,
        key=lambda chunk: lexical_overlap_score(lexical_query, chunk.content),
        reverse=True,
    )
    chunks_by_id: dict[str, RagChunk] = {}
    scores: dict[str, float] = {}
    relevance: dict[str, float] = {}
    for source, ranked_chunks in (
        ("dense", dense_chunks),
        ("lexical", tuple(lexical_ranked)),
    ):
        for rank, chunk in enumerate(ranked_chunks, start=1):
            key = str(chunk.chunkId)
            chunks_by_id.setdefault(key, chunk)
            scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
            evidence = (
                chunk.score
                if source == "dense"
                else lexical_overlap_score(lexical_query, chunk.content)
            )
            relevance[key] = max(
                relevance.get(key, 0.0),
                min(1.0, max(0.0, evidence)),
            )
    maximum = 2.0 / (_RRF_K + 1)
    return tuple(
        replace(
            chunks_by_id[key],
            score=min(1.0, score / maximum),
            metadata=replace(
                chunks_by_id[key].metadata,
                extra={
                    **dict(chunks_by_id[key].metadata.extra),
                    "_retrieval_relevance": relevance[key],
                },
            ),
        )
        for key, score in sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    )


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
