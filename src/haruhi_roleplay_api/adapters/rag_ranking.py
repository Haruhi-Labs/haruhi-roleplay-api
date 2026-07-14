"""角色扮演 RAG 的本地重排、去重和类型配额。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from haruhi_roleplay_api.domain import RagChunk


_TYPE_QUOTAS = {
    "dialogue_example": 2,
    "scene_memory": 2,
    "behavior_observation": 1,
    "inner_monologue": 1,
    "__knowledge__": 2,
}
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, kw_only=True)
class _RankedCandidate:
    chunk: RagChunk
    score: float
    kind: str
    document_key: str
    content_key: str
    scene_key: str | None


def rank_roleplay_chunks(
    chunks: Iterable[RagChunk],
    *,
    query: str,
    top_k: int,
) -> tuple[RagChunk, ...]:
    candidates = sorted(
        (_rank_candidate(chunk, query=query) for chunk in chunks),
        key=lambda item: (item.score, item.chunk.score),
        reverse=True,
    )
    selected: list[_RankedCandidate] = []
    used_documents: set[str] = set()
    used_contents: set[str] = set()
    used_scenes: set[str] = set()
    kind_counts: dict[str, int] = {}

    def add(candidate: _RankedCandidate) -> bool:
        if (
            candidate.document_key in used_documents
            or candidate.content_key in used_contents
        ):
            return False
        selected.append(candidate)
        used_documents.add(candidate.document_key)
        used_contents.add(candidate.content_key)
        if candidate.scene_key:
            used_scenes.add(candidate.scene_key)
        kind_counts[candidate.kind] = kind_counts.get(candidate.kind, 0) + 1
        return True

    for enforce_quota, enforce_scene in (
        (True, True),
        (False, True),
        (False, False),
    ):
        for candidate in candidates:
            if len(selected) >= top_k:
                break
            if enforce_scene and candidate.scene_key in used_scenes:
                continue
            quota = _TYPE_QUOTAS.get(candidate.kind, _TYPE_QUOTAS["__knowledge__"])
            if enforce_quota and kind_counts.get(candidate.kind, 0) >= quota:
                continue
            add(candidate)
        if len(selected) >= top_k:
            break
    return tuple(candidate.chunk for candidate in selected[:top_k])


def _rank_candidate(chunk: RagChunk, *, query: str) -> _RankedCandidate:
    extra = chunk.metadata.extra
    kind = str(extra.get("record_kind") or "__knowledge__")
    scene = extra.get("scene_id") or extra.get("conversation_id")
    lexical = _lexical_overlap(query, chunk.content)
    quality = _quality_score(chunk)
    score = 0.80 * min(1.0, max(0.0, chunk.score)) + 0.15 * lexical + 0.05 * quality
    return _RankedCandidate(
        chunk=chunk,
        score=score,
        kind=kind,
        document_key=str(chunk.documentId),
        content_key=_normalize_text(chunk.content),
        scene_key=str(scene) if scene else None,
    )


def _lexical_overlap(query: str, content: str) -> float:
    query_features = _text_features(query)
    if not query_features:
        return 0.0
    content_features = _text_features(content)
    return len(query_features & content_features) / len(query_features)


def _text_features(text: str) -> set[str]:
    normalized = _normalize_text(text)
    characters = {character for character in normalized if not character.isspace()}
    compact = normalized.replace(" ", "")
    bigrams = {compact[index : index + 2] for index in range(len(compact) - 1)}
    return characters | bigrams


def _normalize_text(text: str) -> str:
    return _SPACE_RE.sub(" ", text.casefold()).strip()


def _quality_score(chunk: RagChunk) -> float:
    extra = chunk.metadata.extra
    confidence = extra.get("confidence")
    if isinstance(confidence, int | float) and not isinstance(confidence, bool):
        confidence_score = min(1.0, max(0.0, float(confidence)))
    else:
        confidence_score = 0.7
    certainty_score = {
        "certain": 1.0,
        "probable": 0.75,
        "uncertain": 0.4,
    }.get(str(extra.get("review_certainty") or ""), 0.7)
    return (confidence_score + certainty_score) / 2
