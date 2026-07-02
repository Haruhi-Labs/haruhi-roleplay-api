"""RAG adapters for local orchestration tests and local MVP."""

from __future__ import annotations

from uuid import uuid4

from haruhi_roleplay_api.domain import (
    CharacterId,
    RagChunk,
    RagChunkId,
    RagDocumentId,
    RagDocumentMetadata,
    RagIngestInput,
    RagIngestResult,
    RagRetrieveInput,
    RagRetrieveOutput,
    PersonaModeId,
)


class FakeRagService:
    provider_name = "fake-rag"

    def __init__(self, chunks: tuple[RagChunk, ...] | None = None) -> None:
        self._chunks = chunks or _default_chunks()

    def retrieve(self, retrieve_input: RagRetrieveInput) -> RagRetrieveOutput:
        filtered = tuple(
            chunk for chunk in self._chunks if _matches_filters(chunk, retrieve_input)
        )
        ranked = tuple(
            sorted(filtered, key=lambda chunk: chunk.score, reverse=True)
        )[: retrieve_input.topK]
        return RagRetrieveOutput(
            chunks=ranked,
            provider=self.provider_name,
            rawHitCount=len(self._chunks),
            filteredHitCount=len(filtered),
            rerankApplied=False,
        )


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
                chunkId=RagChunkId(f"{document_id}-chunk-{index}"),
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
        ranked = tuple(
            chunk for chunk in sorted(scored, key=lambda item: item.score, reverse=True)
            if chunk.score > 0
        )[: retrieve_input.topK]
        return RagRetrieveOutput(
            chunks=ranked,
            provider=self.provider_name,
            rawHitCount=len(self._chunks),
            filteredHitCount=len(metadata_filtered),
            rerankApplied=False,
        )


def _matches_filters(chunk: RagChunk, retrieve_input: RagRetrieveInput) -> bool:
    metadata = chunk.metadata
    filters = retrieve_input.filters
    if metadata.characterId != retrieve_input.characterId:
        return False
    if (
        metadata.personaMode is not None
        and metadata.personaMode != retrieve_input.personaMode
    ):
        return False
    if filters.sourceTypes and metadata.sourceType not in filters.sourceTypes:
        return False
    if filters.timelines and metadata.timeline not in filters.timelines:
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
    for paragraph in paragraphs or (content.strip(),):
        for start in range(0, len(paragraph), chunk_size):
            chunk = paragraph[start : start + chunk_size].strip()
            if chunk:
                chunks.append(chunk)
    return tuple(chunks)


def _metadata_with_title(
    metadata: RagDocumentMetadata,
    title: str,
) -> RagDocumentMetadata:
    return RagDocumentMetadata(
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


def _simple_score(query: str, chunk: RagChunk) -> float:
    haystack = " ".join(
        (
            chunk.content,
            str(chunk.metadata.extra.get("title", "")),
            chunk.metadata.sourceType,
            chunk.metadata.timeline,
        )
    ).lower()
    terms = _query_terms(query)
    if not terms:
        return 0.0
    hits = sum(1 for term in terms if term in haystack)
    if hits:
        return hits / len(terms)
    query_chars = {char for char in query.lower() if not char.isspace()}
    if not query_chars:
        return 0.0
    overlap = sum(1 for char in query_chars if char in haystack)
    return overlap / len(query_chars)


def _query_terms(query: str) -> tuple[str, ...]:
    return tuple(term for term in query.lower().split() if term)


def _default_chunks() -> tuple[RagChunk, ...]:
    return (
        _chunk(
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
            characterId=CharacterId(character_id),
            personaMode=PersonaModeId(persona_mode) if persona_mode else None,
            timeline=timeline,
            spoilerLevel=spoiler_level,
            language="zh-CN",
            sourceType=source_type,
            extra={"title": title},
        ),
    )
