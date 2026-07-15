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
    batch_size: int = 64,
) -> CorpusIngestSummary:
    if not app_id.strip():
        raise ValueError("RAG 语料装载需要非空 app_id")
    resolved_path = path.expanduser().resolve()
    records = load_corpus_records(resolved_path)
    scoped_app_id = AppId(app_id.strip())
    if batch_size <= 0:
        raise ValueError("RAG 语料装载 batch_size 必须为正整数")
    ingest_inputs = tuple(
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
                extra={**record.metadata, "atomic_record": True},
            ),
        )
        for record in records
    )
    chunk_count = 0
    ingest_batch = getattr(rag_service, "ingest_batch", None)
    if callable(ingest_batch):
        for index in range(0, len(ingest_inputs), batch_size):
            inputs = ingest_inputs[index : index + batch_size]
            results = tuple(ingest_batch(inputs))
            if len(results) != len(inputs):
                raise ValueError("RAG 批量装载返回数量与输入不一致")
            chunk_count += sum(result.chunkCount for result in results)
    else:
        for ingest_input in ingest_inputs:
            chunk_count += rag_service.ingest(ingest_input).chunkCount
    return CorpusIngestSummary(
        path=resolved_path,
        appId=scoped_app_id,
        documentCount=len(records),
        chunkCount=chunk_count,
    )
