"""RAG adapters for local orchestration tests and local MVP."""

from __future__ import annotations

import hashlib
from uuid import uuid4

from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.adapters.rag_ranking import rank_roleplay_chunks
from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    RagChunk,
    RagChunkId,
    RagDocumentId,
    RagDocumentMetadata,
    RagIngestInput,
    RagIngestResult,
    RagManagedDocument,
    RagRetrieveInput,
    RagRetrieveOutput,
    PersonaModeId,
)


_COMMON_QUERY_NGRAMS = frozenset(
    {
        "请告诉",
        "告诉我",
        "你会怎",
        "会怎么",
        "怎么办",
        "怎么样",
        "如果是",
    }
)


class FakeRagService:
    provider_name = "fake-rag"

    def __init__(self, chunks: tuple[RagChunk, ...] | None = None) -> None:
        self._chunks = chunks or _default_chunks()

    def retrieve(self, retrieve_input: RagRetrieveInput) -> RagRetrieveOutput:
        filtered = tuple(
            chunk for chunk in self._chunks if _matches_filters(chunk, retrieve_input)
        )
        ranked = rank_roleplay_chunks(
            filtered,
            query=retrieve_input.query,
            top_k=retrieve_input.topK,
        )
        return RagRetrieveOutput(
            chunks=ranked,
            provider=self.provider_name,
            rawHitCount=len(self._chunks),
            filteredHitCount=len(filtered),
            rerankApplied=bool(filtered),
        )

    def list_documents(
        self,
        *,
        app_id: str | None = None,
    ) -> tuple[RagManagedDocument, ...]:
        return _managed_documents(self._chunks, provider=self.provider_name, app_id=app_id)

    def delete_document(self, *, app_id: str, document_id: str) -> int:
        removed = tuple(
            chunk
            for chunk in self._chunks
            if str(chunk.metadata.appId) == app_id
            and str(chunk.documentId) == document_id
        )
        if not removed:
            raise AppError(code=ErrorCode.RAG_DOCUMENT_NOT_FOUND)
        removed_ids = {str(chunk.chunkId) for chunk in removed}
        self._chunks = tuple(
            chunk for chunk in self._chunks if str(chunk.chunkId) not in removed_ids
        )
        return len(removed)


class LocalRagService:
    provider_name = "local-rag"

    def __init__(
        self,
        *,
        chunk_size: int = 320,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self._chunk_size = chunk_size
        self._chunks: list[RagChunk] = []

    def ingest(self, ingest_input: RagIngestInput) -> RagIngestResult:
        document_id = ingest_input.documentId or RagDocumentId(
            f"ragdoc-{uuid4().hex}"
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
        self._chunks.extend(chunks)
        return RagIngestResult(
            documentId=document_id,
            status="imported",
            chunkCount=len(chunks),
            metadata=metadata,
        )

    def retrieve(self, retrieve_input: RagRetrieveInput) -> RagRetrieveOutput:
        metadata_filtered = tuple(
            chunk for chunk in self._chunks if _matches_filters(chunk, retrieve_input)
        )
        scored = tuple(
            _chunk_with_score(
                chunk,
                _simple_score(retrieve_input.query, chunk),
            )
            for chunk in metadata_filtered
        )
        candidates = tuple(chunk for chunk in scored if chunk.score > 0)
        ranked = rank_roleplay_chunks(
            candidates,
            query=retrieve_input.query,
            top_k=retrieve_input.topK,
        )
        return RagRetrieveOutput(
            chunks=ranked,
            provider=self.provider_name,
            rawHitCount=len(self._chunks),
            filteredHitCount=len(metadata_filtered),
            rerankApplied=bool(candidates),
        )

    def list_documents(
        self,
        *,
        app_id: str | None = None,
    ) -> tuple[RagManagedDocument, ...]:
        return _managed_documents(
            tuple(self._chunks),
            provider=self.provider_name,
            app_id=app_id,
        )

    def delete_document(self, *, app_id: str, document_id: str) -> int:
        removed = [
            chunk
            for chunk in self._chunks
            if str(chunk.metadata.appId) == app_id
            and str(chunk.documentId) == document_id
        ]
        if not removed:
            raise AppError(code=ErrorCode.RAG_DOCUMENT_NOT_FOUND)
        removed_ids = {str(chunk.chunkId) for chunk in removed}
        self._chunks = [
            chunk for chunk in self._chunks if str(chunk.chunkId) not in removed_ids
        ]
        return len(removed)


def _matches_filters(chunk: RagChunk, retrieve_input: RagRetrieveInput) -> bool:
    metadata = chunk.metadata
    filters = retrieve_input.filters
    if metadata.appId != retrieve_input.appId:
        return False
    if metadata.characterId != retrieve_input.characterId:
        return False
    if (
        metadata.personaMode is not None
        and metadata.personaMode != retrieve_input.personaMode
    ):
        return False
    allowed_persona_modes = metadata.extra.get("allowed_persona_modes")
    if allowed_persona_modes:
        if not isinstance(allowed_persona_modes, list | tuple):
            return False
        if str(retrieve_input.personaMode) not in {
            str(item) for item in allowed_persona_modes
        }:
            return False
    if filters.sourceTypes and metadata.sourceType not in filters.sourceTypes:
        return False
    if filters.timelines and metadata.timeline not in filters.timelines:
        return False
    extra_filters = (
        (filters.recordKinds, "record_kind"),
        (filters.perspectives, "perspective"),
        (filters.corpusVersions, "corpus_version"),
        (filters.retrievalChannels, "retrieval_channel"),
        (filters.knowledgeOwners, "knowledge_owner"),
        (filters.usages, "usage"),
    )
    for allowed, field in extra_filters:
        if allowed and str(metadata.extra.get(field, "")) not in allowed:
            return False
    if (
        filters.spoilerLevelMax is not None
        and metadata.spoilerLevel > filters.spoilerLevelMax
    ):
        return False
    if filters.language is not None and metadata.language != filters.language:
        return False
    return True


def _chunk_text(content: str, chunk_size: int) -> tuple[str, ...]:
    normalized = "\n".join(line.strip() for line in content.splitlines())
    paragraphs = tuple(part for part in normalized.split("\n") if part)
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    def flush() -> None:
        nonlocal current, current_length
        if current:
            chunks.append("\n".join(current))
        current = []
        current_length = 0

    for paragraph in paragraphs or (content.strip(),):
        pieces = _split_long_paragraph(paragraph, chunk_size)
        for piece in pieces:
            extra_length = len(piece) + (1 if current else 0)
            if current and current_length + extra_length > chunk_size:
                flush()
            current.append(piece)
            current_length += len(piece) + (1 if len(current) > 1 else 0)
    flush()
    return tuple(chunks)


def _ingest_content_chunks(
    content: str,
    *,
    metadata: RagDocumentMetadata,
    chunk_size: int,
) -> tuple[str, ...]:
    if metadata.extra.get("atomic_record") is True:
        return (content,)
    return _chunk_text(content, chunk_size)


def _split_long_paragraph(paragraph: str, chunk_size: int) -> tuple[str, ...]:
    if len(paragraph) <= chunk_size:
        return (paragraph,)
    pieces: list[str] = []
    remaining = paragraph
    punctuation = "。！？；.!?;"
    while len(remaining) > chunk_size:
        candidate = remaining[:chunk_size]
        split_at = max(candidate.rfind(mark) for mark in punctuation)
        if split_at < chunk_size // 2:
            split_at = chunk_size
        else:
            split_at += 1
        piece = remaining[:split_at].strip()
        if piece:
            pieces.append(piece)
        remaining = remaining[split_at:].strip()
    if remaining:
        pieces.append(remaining)
    return tuple(pieces)


def _metadata_with_title(
    metadata: RagDocumentMetadata,
    title: str,
) -> RagDocumentMetadata:
    return RagDocumentMetadata(
        appId=metadata.appId,
        characterId=metadata.characterId,
        personaMode=metadata.personaMode,
        timeline=metadata.timeline,
        spoilerLevel=metadata.spoilerLevel,
        language=metadata.language,
        sourceType=metadata.sourceType,
        trustLevel=metadata.trustLevel,
        extra={**dict(metadata.extra), "title": title},
    )


def _chunk_with_score(chunk: RagChunk, score: float) -> RagChunk:
    return RagChunk(
        chunkId=chunk.chunkId,
        documentId=chunk.documentId,
        content=chunk.content,
        score=score,
        metadata=chunk.metadata,
    )


def _scoped_chunk_id(
    app_id: AppId,
    document_id: RagDocumentId,
    index: int,
) -> RagChunkId:
    scope = f"{app_id}\0{document_id}\0{index}"
    digest = hashlib.blake2b(scope.encode("utf-8"), digest_size=8).hexdigest()
    return RagChunkId(f"{document_id}-chunk-{index}-{digest}")


def _simple_score(query: str, chunk: RagChunk) -> float:
    contextual_metadata = " ".join(
        str(chunk.metadata.extra.get(field, ""))
        for field in ("book_title", "section_title", "record_kind", "perspective")
    )
    haystack = " ".join(
        (
            chunk.content,
            str(chunk.metadata.extra.get("title", "")),
            contextual_metadata,
            chunk.metadata.sourceType,
            chunk.metadata.timeline,
        )
    ).lower()
    query_focus = _query_focus(query)
    terms = _query_terms(query_focus)
    if not terms:
        return 0.0
    hits = sum(1 for term in terms if term in haystack)
    if hits:
        return hits / len(terms)
    query_ngrams = _text_ngrams(query_focus) - _COMMON_QUERY_NGRAMS
    if not query_ngrams:
        return 0.0
    content_ngrams = _text_ngrams(haystack)
    overlap_count = len(query_ngrams & content_ngrams)
    coverage = overlap_count / len(query_ngrams)
    evidence = min(1.0, overlap_count / 6)
    return max(coverage, evidence)


def _query_terms(query: str) -> tuple[str, ...]:
    return tuple(term for term in query.lower().split() if term)


def _query_focus(query: str) -> str:
    current_marker = "当前用户输入：\n"
    if current_marker not in query:
        return query
    return query.rsplit(current_marker, maxsplit=1)[-1]


def _text_ngrams(text: str) -> set[str]:
    compact = "".join(character for character in text.casefold() if character.isalnum())
    width = 3 if len(compact) >= 3 else 2
    return {
        compact[index : index + width]
        for index in range(len(compact) - width + 1)
    }


def _managed_documents(
    chunks: tuple[RagChunk, ...],
    *,
    provider: str,
    app_id: str | None = None,
) -> tuple[RagManagedDocument, ...]:
    grouped: dict[tuple[str, str], list[RagChunk]] = {}
    for chunk in chunks:
        chunk_app_id = str(chunk.metadata.appId or "")
        if app_id is not None and chunk_app_id != app_id:
            continue
        grouped.setdefault((chunk_app_id, str(chunk.documentId)), []).append(chunk)
    documents: list[RagManagedDocument] = []
    for (_, document_id), document_chunks in grouped.items():
        first = document_chunks[0]
        preview = " ".join(chunk.content for chunk in document_chunks)[:240]
        documents.append(
            RagManagedDocument(
                documentId=RagDocumentId(document_id),
                appId=first.metadata.appId,
                title=str(first.metadata.extra.get("title") or document_id),
                characterId=first.metadata.characterId,
                personaMode=first.metadata.personaMode,
                timeline=first.metadata.timeline,
                sourceType=first.metadata.sourceType,
                language=first.metadata.language,
                spoilerLevel=first.metadata.spoilerLevel,
                trustLevel=first.metadata.trustLevel,
                chunkCount=len(document_chunks),
                contentPreview=preview,
                provider=provider,
            )
        )
    return tuple(
        sorted(
            documents,
            key=lambda item: (str(item.appId or ""), item.title, str(item.documentId)),
        )
    )


def _default_chunks() -> tuple[RagChunk, ...]:
    return (
        _chunk(
            app_id="web",
            chunk_id="chunk-haruhi-mid-late-1",
            document_id="doc-haruhi-timeline",
            character_id="haruhi",
            persona_mode="mid_late_haruhi",
            timeline="mid_late",
            spoiler_level=2,
            source_type="timeline",
            title="中后期春日时间线资料",
            content="中后期的春日仍然主动推动社团活动，但更会维持长期关系。",
            score=0.95,
        ),
        _chunk(
            app_id="web",
            chunk_id="chunk-haruhi-early-1",
            document_id="doc-haruhi-profile",
            character_id="haruhi",
            persona_mode=None,
            timeline="early",
            spoiler_level=1,
            source_type="character_profile",
            title="春日早期角色资料",
            content="早期的春日更直接地寻找异常，会迅速把别人卷入计划。",
            score=0.85,
        ),
        _chunk(
            app_id="web",
            chunk_id="chunk-kyon-default-1",
            document_id="doc-kyon-profile",
            character_id="kyon",
            persona_mode="default_kyon",
            timeline="mid_late",
            spoiler_level=1,
            source_type="character_profile",
            title="阿虚角色资料",
            content="阿虚通常以吐槽和常识视角回应异常事件。",
            score=0.9,
        ),
    )


def _chunk(
    *,
    app_id: str,
    chunk_id: str,
    document_id: str,
    character_id: str,
    persona_mode: str | None,
    timeline: str,
    spoiler_level: int,
    source_type: str,
    title: str,
    content: str,
    score: float,
) -> RagChunk:
    return RagChunk(
        chunkId=RagChunkId(chunk_id),
        documentId=RagDocumentId(document_id),
        content=content,
        score=score,
        metadata=RagDocumentMetadata(
            appId=AppId(app_id),
            characterId=CharacterId(character_id),
            personaMode=PersonaModeId(persona_mode) if persona_mode else None,
            timeline=timeline,
            spoilerLevel=spoiler_level,
            language="zh-CN",
            sourceType=source_type,
            extra={
                "title": title,
                "record_kind": "dialogue_example",
                "retrieval_channel": "dialogue_style",
                "knowledge_owner": character_id,
                "usage": "style_only",
            },
        ),
    )
