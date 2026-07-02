"""Fake RAG adapter for local orchestration tests."""

from __future__ import annotations

from haruhi_roleplay_api.domain import (
    CharacterId,
    PersonaModeId,
    RagChunk,
    RagChunkId,
    RagDocumentId,
    RagDocumentMetadata,
    RagRetrieveInput,
    RagRetrieveOutput,
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
