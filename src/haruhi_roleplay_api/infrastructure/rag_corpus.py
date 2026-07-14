"""把离线构建的 JSONL 语料装载到实际 RAG provider。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from haruhi_roleplay_api.corpus import load_corpus_records
from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    RagDocumentId,
    RagDocumentMetadata,
    RagIngestInput,
)
from haruhi_roleplay_api.ports import RagIngestService


@dataclass(frozen=True, kw_only=True)
class CorpusIngestSummary:
    path: Path
    appId: AppId
    documentCount: int
    chunkCount: int


def ingest_corpus_file(
    rag_service: RagIngestService,
    *,
    path: Path,
    app_id: str,
) -> CorpusIngestSummary:
    if not app_id.strip():
        raise ValueError("RAG 语料装载需要非空 app_id")
    resolved_path = path.expanduser().resolve()
    records = load_corpus_records(resolved_path)
    scoped_app_id = AppId(app_id.strip())
    chunk_count = 0
    for record in records:
        result = rag_service.ingest(
            RagIngestInput(
                appId=scoped_app_id,
                documentId=RagDocumentId(record.document_id),
                title=record.title,
                content=record.content,
                metadata=RagDocumentMetadata(
                    appId=scoped_app_id,
                    characterId=CharacterId(record.character_id),
                    personaMode=None,
                    timeline=record.timeline,
                    spoilerLevel=record.spoiler_level,
                    language=record.language,
                    sourceType=record.source_type,
                    trustLevel=record.trust_level,
                    extra=dict(record.metadata),
                ),
            )
        )
        chunk_count += result.chunkCount
    return CorpusIngestSummary(
        path=resolved_path,
        appId=scoped_app_id,
        documentCount=len(records),
        chunkCount=chunk_count,
    )
