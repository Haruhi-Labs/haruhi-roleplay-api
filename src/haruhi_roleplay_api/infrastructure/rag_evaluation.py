"""角色检索金标评测与生产隔离检查。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

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
    characterId: str
    personaMode: str
    topK: int
    filters: RagRetrieveFilters
    relevantDocumentIds: tuple[str, ...]
    minimumRelevantHits: int
    expectedRecordKinds: tuple[str, ...]
    requiredTerms: tuple[str, ...]
    forbiddenDocumentIds: tuple[str, ...]

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
        return cls(
            caseId=_required_text(data, "case_id"),
            query=_required_text(data, "query"),
            characterId=_required_text(data, "character_id"),
            personaMode=_required_text(data, "persona_mode"),
            topK=int(data.get("top_k", 8)),
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
) -> RagEvaluationReport:
    results = tuple(
        _evaluate_case(rag_service, case, app_id=app_id) for case in cases
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
    chunks = output.chunks
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


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError("评测项列表字段必须是数组")
    result = tuple(str(item).strip() for item in value)
    if any(not item for item in result):
        raise ValueError("评测项列表字段不能包含空字符串")
    return result


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None
