"""角色检索金标评测与生产隔离检查。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from haruhi_roleplay_api.application.rag_query import build_roleplay_rag_query
from haruhi_roleplay_api.domain import (
    AppId,
    CharacterId,
    PersonaModeId,
    RagChunk,
    RagRetrieveFilters,
    RagRetrieveInput,
    UserId,
)
from haruhi_roleplay_api.ports import RagService


@dataclass(frozen=True, kw_only=True)
class RagEvaluationCase:
    caseId: str
    query: str
    retrievalChannel: str
    targetCharacterId: str
    targetPersonaMode: str
    timeline: str
    characterId: str
    personaMode: str
    topK: int
    filters: RagRetrieveFilters
    relevantDocumentIds: tuple[str, ...]
    minimumRelevantHits: int
    expectedRecordKinds: tuple[str, ...]
    requiredTerms: tuple[str, ...]
    forbiddenDocumentIds: tuple[str, ...]
    maximumRetrievedHits: int

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RagEvaluationCase":
        status = str(data.get("status", "ready"))
        if status != "ready":
            raise ValueError("只有 status=ready 的评测项才能执行")
        relevant = _string_tuple(data.get("relevant_document_ids", ()))
        minimum_hits = int(data.get("minimum_relevant_hits", 1 if relevant else 0))
        if minimum_hits < 0 or minimum_hits > len(relevant):
            raise ValueError("minimum_relevant_hits 超出 relevant_document_ids 范围")
        filters = data.get("filters", {})
        if not isinstance(filters, Mapping):
            raise ValueError("评测项 filters 必须是对象")
        retrieval_channel = str(data.get("retrieval_channel", "actor_reference"))
        if retrieval_channel not in {"actor_reference", "director_bridge"}:
            raise ValueError(
                "retrieval_channel 必须是 actor_reference 或 director_bridge"
            )
        target_character_id = _required_text(
            data,
            (
                "target_character_id"
                if "target_character_id" in data
                else "character_id"
            ),
        )
        target_persona_mode = _required_text(data, "persona_mode")
        timelines = _string_tuple(filters.get("timelines", ()))
        timeline = str(data.get("timeline") or (timelines[0] if timelines else ""))
        if not timeline:
            raise ValueError("评测项 timeline 必须是非空字符串")
        query_value = str(data.get("query", "")).strip()
        if not query_value:
            query_value = build_roleplay_rag_query(
                character_id=target_character_id,
                persona_mode=target_persona_mode,
                timeline=timeline,
                current_message=_required_text(data, "current_input"),
                recent_messages=_conversation(data.get("conversation", ())),
            )
        character_id = (
            "kyon" if retrieval_channel == "director_bridge" else target_character_id
        )
        persona_mode = (
            _director_persona_mode(timeline)
            if retrieval_channel == "director_bridge"
            else target_persona_mode
        )
        top_k = int(data.get("top_k", 8))
        maximum_hits = int(data.get("maximum_retrieved_hits", top_k))
        if maximum_hits < 0 or maximum_hits > top_k:
            raise ValueError("maximum_retrieved_hits 必须介于 0 和 top_k 之间")
        return cls(
            caseId=_required_text(data, "case_id"),
            query=query_value,
            retrievalChannel=retrieval_channel,
            targetCharacterId=target_character_id,
            targetPersonaMode=target_persona_mode,
            timeline=timeline,
            characterId=character_id,
            personaMode=persona_mode,
            topK=top_k,
            filters=RagRetrieveFilters(
                sourceTypes=_string_tuple(filters.get("source_types", ())),
                timelines=_string_tuple(filters.get("timelines", ())),
                recordKinds=_string_tuple(filters.get("record_kinds", ())),
                perspectives=_string_tuple(filters.get("perspectives", ())),
                corpusVersions=_string_tuple(filters.get("corpus_versions", ())),
                retrievalChannels=_string_tuple(
                    filters.get("retrieval_channels", ())
                ),
                knowledgeOwners=_string_tuple(filters.get("knowledge_owners", ())),
                usages=_string_tuple(filters.get("usages", ())),
                spoilerLevelMax=(
                    int(filters["spoiler_level_max"])
                    if filters.get("spoiler_level_max") is not None
                    else None
                ),
                language=(
                    str(filters["language"])
                    if filters.get("language") is not None
                    else None
                ),
            ),
            relevantDocumentIds=relevant,
            minimumRelevantHits=minimum_hits,
            expectedRecordKinds=_string_tuple(
                data.get("expected_record_kinds", ())
            ),
            requiredTerms=_string_tuple(data.get("required_terms", ())),
            forbiddenDocumentIds=_string_tuple(
                data.get("forbidden_document_ids", ())
            ),
            maximumRetrievedHits=maximum_hits,
        )


@dataclass(frozen=True, kw_only=True)
class RagEvaluationCaseResult:
    caseId: str
    passed: bool
    recallAtK: float | None
    reciprocalRank: float | None
    relevantHits: int
    retrievedDocumentIds: tuple[str, ...]
    failures: tuple[str, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "case_id": self.caseId,
            "passed": self.passed,
            "recall_at_k": self.recallAtK,
            "reciprocal_rank": self.reciprocalRank,
            "relevant_hits": self.relevantHits,
            "retrieved_document_ids": list(self.retrievedDocumentIds),
            "failures": list(self.failures),
        }


@dataclass(frozen=True, kw_only=True)
class RagEvaluationReport:
    evaluatedCases: int
    pendingCases: int
    passedCases: int
    hitRate: float
    meanRecallAtK: float | None
    meanReciprocalRank: float | None
    isolationFailureCases: int
    results: tuple[RagEvaluationCaseResult, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "evaluated_cases": self.evaluatedCases,
            "pending_cases": self.pendingCases,
            "passed_cases": self.passedCases,
            "hit_rate": self.hitRate,
            "mean_recall_at_k": self.meanRecallAtK,
            "mean_reciprocal_rank": self.meanReciprocalRank,
            "isolation_failure_cases": self.isolationFailureCases,
            "results": [result.to_mapping() for result in self.results],
        }


def load_rag_evaluation_cases(
    path: Path,
) -> tuple[tuple[RagEvaluationCase, ...], int]:
    ready: list[RagEvaluationCase] = []
    pending = 0
    with path.expanduser().open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"评测 JSONL 第 {line_number} 行无法解析") from exc
            if not isinstance(value, Mapping):
                raise ValueError(f"评测 JSONL 第 {line_number} 行必须是对象")
            if value.get("status", "ready") != "ready":
                pending += 1
                continue
            ready.append(RagEvaluationCase.from_mapping(value))
    return tuple(ready), pending


def evaluate_rag_cases(
    rag_service: RagService,
    cases: Sequence[RagEvaluationCase],
    *,
    app_id: str,
    pending_cases: int = 0,
    minimum_relevance_score: float = 0.2,
) -> RagEvaluationReport:
    if (
        isinstance(minimum_relevance_score, bool)
        or not isinstance(minimum_relevance_score, int | float)
        or not 0.0 <= minimum_relevance_score <= 1.0
    ):
        raise ValueError("minimum_relevance_score 必须介于 0 和 1 之间")
    results = tuple(
        _evaluate_case(
            rag_service,
            case,
            app_id=app_id,
            minimum_relevance_score=minimum_relevance_score,
        )
        for case in cases
    )
    recalls = [
        result.recallAtK for result in results if result.recallAtK is not None
    ]
    reciprocal_ranks = [
        result.reciprocalRank
        for result in results
        if result.reciprocalRank is not None
    ]
    isolation_failures = sum(
        any(failure.startswith("隔离失败：") for failure in result.failures)
        for result in results
    )
    return RagEvaluationReport(
        evaluatedCases=len(results),
        pendingCases=pending_cases,
        passedCases=sum(result.passed for result in results),
        hitRate=(sum(result.passed for result in results) / len(results) if results else 0.0),
        meanRecallAtK=_mean(recalls),
        meanReciprocalRank=_mean(reciprocal_ranks),
        isolationFailureCases=isolation_failures,
        results=results,
    )


def _evaluate_case(
    rag_service: RagService,
    case: RagEvaluationCase,
    *,
    app_id: str,
    minimum_relevance_score: float,
) -> RagEvaluationCaseResult:
    output = rag_service.retrieve(
        RagRetrieveInput(
            appId=AppId(app_id),
            userId=UserId(f"rag-eval:{case.caseId}"),
            characterId=CharacterId(case.characterId),
            personaMode=PersonaModeId(case.personaMode),
            query=case.query,
            topK=case.topK,
            filters=case.filters,
        )
    )
    chunks = tuple(
        chunk
        for chunk in output.chunks
        if _chunk_relevance(chunk) >= minimum_relevance_score
    )
    retrieved_ids = tuple(str(chunk.documentId) for chunk in chunks)
    relevant_ranks = [
        rank
        for rank, document_id in enumerate(retrieved_ids, start=1)
        if document_id in case.relevantDocumentIds
    ]
    relevant_hits = len(set(retrieved_ids) & set(case.relevantDocumentIds))
    recall = (
        relevant_hits / len(case.relevantDocumentIds)
        if case.relevantDocumentIds
        else None
    )
    reciprocal_rank = (
        (1.0 / min(relevant_ranks) if relevant_ranks else 0.0)
        if case.relevantDocumentIds
        else None
    )
    failures: list[str] = []
    if relevant_hits < case.minimumRelevantHits:
        failures.append(
            f"相关文档命中 {relevant_hits}，低于要求 {case.minimumRelevantHits}"
        )
    if len(chunks) > case.maximumRetrievedHits:
        failures.append(
            f"检索结果 {len(chunks)} 条，超过上限 {case.maximumRetrievedHits}"
        )
    returned_kinds = {
        str(chunk.metadata.extra.get("record_kind", "")) for chunk in chunks
    }
    missing_kinds = set(case.expectedRecordKinds) - returned_kinds
    if missing_kinds:
        failures.append("缺少记录类型：" + "、".join(sorted(missing_kinds)))
    combined_content = "\n".join(chunk.content for chunk in chunks)
    missing_terms = [term for term in case.requiredTerms if term not in combined_content]
    if missing_terms:
        failures.append("缺少必需词：" + "、".join(missing_terms))
    forbidden_hits = set(retrieved_ids) & set(case.forbiddenDocumentIds)
    if forbidden_hits:
        failures.append("命中禁止文档：" + "、".join(sorted(forbidden_hits)))
    failures.extend(
        f"隔离失败：{message}"
        for chunk in chunks
        for message in _scope_violations(chunk, case=case, app_id=app_id)
    )
    return RagEvaluationCaseResult(
        caseId=case.caseId,
        passed=not failures,
        recallAtK=recall,
        reciprocalRank=reciprocal_rank,
        relevantHits=relevant_hits,
        retrievedDocumentIds=retrieved_ids,
        failures=tuple(failures),
    )


def _scope_violations(
    chunk: RagChunk,
    *,
    case: RagEvaluationCase,
    app_id: str,
) -> tuple[str, ...]:
    metadata = chunk.metadata
    violations: list[str] = []
    if str(metadata.appId or "") != app_id:
        violations.append(f"{chunk.documentId} 跨 app_id")
    if str(metadata.characterId) != case.characterId:
        violations.append(f"{chunk.documentId} 跨角色")
    if case.filters.timelines and metadata.timeline not in case.filters.timelines:
        violations.append(f"{chunk.documentId} 跨时间线")
    if (
        case.filters.spoilerLevelMax is not None
        and metadata.spoilerLevel > case.filters.spoilerLevelMax
    ):
        violations.append(f"{chunk.documentId} 剧透等级越界")
    allowed_modes = metadata.extra.get("allowed_persona_modes")
    if isinstance(allowed_modes, list | tuple) and allowed_modes:
        if "*" not in allowed_modes and case.personaMode not in allowed_modes:
            violations.append(f"{chunk.documentId} persona 越界")
    return tuple(violations)


def _required_text(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"评测项 {field} 必须是非空字符串")
    return value.strip()


def _conversation(value: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list | tuple):
        raise ValueError("评测项 conversation 必须是数组")
    messages: list[tuple[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(f"评测项 conversation[{index}] 必须是对象")
        role = str(item.get("role", ""))
        if role not in {"user", "assistant"}:
            raise ValueError(f"评测项 conversation[{index}].role 不受支持")
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"评测项 conversation[{index}].content 不能为空")
        messages.append((role, content.strip()))
    return tuple(messages)


def _director_persona_mode(timeline: str) -> str:
    return "default_kyon" if timeline == "mid_late" else f"{timeline}_kyon"


def _chunk_relevance(chunk: RagChunk) -> float:
    internal = chunk.metadata.extra.get("_retrieval_relevance")
    if isinstance(internal, int | float) and not isinstance(internal, bool):
        return float(internal)
    return chunk.score


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError("评测项列表字段必须是数组")
    result = tuple(str(item).strip() for item in value)
    if any(not item for item in result):
        raise ValueError("评测项列表字段不能包含空字符串")
    return result


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None
