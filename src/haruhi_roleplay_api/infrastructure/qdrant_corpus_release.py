"""Qdrant 版本化语料发布与回滚。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from haruhi_roleplay_api.adapters.rag_qdrant import QdrantRagService
from haruhi_roleplay_api.application.errors import AppError, ErrorCode
from haruhi_roleplay_api.corpus import audit_haruhi_corpus, load_corpus_records
from haruhi_roleplay_api.infrastructure.embedding_provider_factory import (
    EmbeddingProviderSettings,
)
from haruhi_roleplay_api.infrastructure.rag_corpus import (
    CorpusIngestSummary,
    ingest_corpus_file,
)


_UNSAFE_COLLECTION_CHARACTER = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass(frozen=True, kw_only=True)
class QdrantCorpusReleaseSummary:
    corpusVersion: str
    collection: str
    alias: str
    previousCollection: str | None
    ingest: CorpusIngestSummary
    pointCount: int


def corpus_version_from_file(path: Path) -> str:
    records = load_corpus_records(path.expanduser().resolve())
    versions = {
        str(record.metadata.get("corpus_version", "")).strip()
        for record in records
    }
    versions.discard("")
    if len(versions) != 1:
        raise ValueError("语料文件必须包含且只能包含一个 corpus_version")
    return versions.pop()


def embedding_release_fingerprint(
    env: Mapping[str, str],
    *,
    release_id: str | None = None,
) -> str:
    settings = EmbeddingProviderSettings.from_mapping(env)
    identity = {
        "provider": settings.provider.strip().lower().replace("-", "_"),
        "model": settings.model or "",
        "base_url": settings.baseUrl or "",
        "dimensions": settings.dimensions,
        "embeddings_path": settings.embeddingsPath or "",
        "release_id": (release_id or "").strip(),
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"emb-{digest[:16]}"


def versioned_collection_name(
    *,
    prefix: str,
    corpus_version: str,
    embedding_fingerprint: str,
) -> str:
    normalized_prefix = _normalize_collection_part(prefix)
    normalized_version = _normalize_collection_part(corpus_version)
    normalized_embedding = _normalize_collection_part(embedding_fingerprint)
    if not normalized_prefix or not normalized_version or not normalized_embedding:
        raise ValueError("Qdrant 集合前缀、corpus_version 和 embedding 指纹不能为空")
    suffix = f"{normalized_version}__{normalized_embedding}"
    available_prefix = 255 - len(suffix) - 2
    if available_prefix <= 0:
        raise ValueError("corpus_version 和 embedding 指纹组合过长")
    return f"{normalized_prefix[:available_prefix]}__{suffix}"


def publish_qdrant_corpus(
    service: QdrantRagService,
    *,
    path: Path,
    app_id: str,
    alias: str,
) -> QdrantCorpusReleaseSummary:
    if service.collection_exists():
        raise AppError(
            code=ErrorCode.RAG_INGEST_FAILED,
            message=(
                f"拒绝覆盖已存在的不可变 Qdrant 集合：{service.collection}。"
                "请更换 --release-id，或先显式删除未被 alias 引用的失败集合。"
            ),
        )
    resolved_path = path.expanduser().resolve()
    sibling_manifest = resolved_path.parent / "manifest.json"
    audit = audit_haruhi_corpus(
        resolved_path,
        manifest_path=sibling_manifest if sibling_manifest.exists() else None,
    )
    if not audit.passed or not audit.corpusVersion:
        details = "；".join(audit.errors[:5]) or "缺少 corpus_version"
        raise AppError(
            code=ErrorCode.RAG_INGEST_FAILED,
            message=f"Qdrant 发布前语料审计失败：{details}",
        )
    corpus_version = audit.corpusVersion
    service.ensure_collection_schema()
    ingest = ingest_corpus_file(service, path=resolved_path, app_id=app_id)
    if ingest.documentCount != ingest.chunkCount:
        raise AppError(
            code=ErrorCode.RAG_INGEST_FAILED,
            message=(
                "版本化角色语料必须保持一条记录对应一个 point："
                f"文档 {ingest.documentCount}，point {ingest.chunkCount}。"
            ),
        )
    point_count = service.count_points(app_id=str(ingest.appId))
    if point_count != ingest.documentCount:
        raise AppError(
            code=ErrorCode.RAG_INGEST_FAILED,
            message=(
                f"Qdrant 发布前计数校验失败：语料 {ingest.documentCount} 条，"
                f"集合中 app_id={ingest.appId} 的 point 为 {point_count} 条。"
            ),
        )
    previous_collection = service.switch_alias(alias)
    return QdrantCorpusReleaseSummary(
        corpusVersion=corpus_version,
        collection=service.collection,
        alias=alias,
        previousCollection=previous_collection,
        ingest=ingest,
        pointCount=point_count,
    )


def activate_qdrant_collection(
    service: QdrantRagService,
    *,
    alias: str,
) -> str | None:
    if not service.collection_exists():
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message=f"不能激活不存在的 Qdrant 集合：{service.collection}",
        )
    if service.count_points() <= 0:
        raise AppError(
            code=ErrorCode.RAG_PROVIDER_ERROR,
            message=f"不能激活空 Qdrant 集合：{service.collection}",
        )
    return service.switch_alias(alias)


def _normalize_collection_part(value: str) -> str:
    return _UNSAFE_COLLECTION_CHARACTER.sub("-", value.strip()).strip("-_")
