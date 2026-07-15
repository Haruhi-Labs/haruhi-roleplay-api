from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.domain import (  # noqa: E402
    AppId,
    CharacterId,
    RagChunk,
    RagChunkId,
    RagDocumentId,
    RagDocumentMetadata,
    RagRetrieveOutput,
)
from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    RagEvaluationCase,
    evaluate_rag_cases,
    load_rag_evaluation_cases,
)


class FixedRagService:
    def __init__(self, chunks: tuple[RagChunk, ...]) -> None:
        self.chunks = chunks
        self.calls: list[object] = []

    def retrieve(self, retrieve_input: object) -> RagRetrieveOutput:
        self.calls.append(retrieve_input)
        return RagRetrieveOutput(
            chunks=self.chunks,
            provider="fixed-rag",
            rawHitCount=len(self.chunks),
            filteredHitCount=len(self.chunks),
        )


class RagEvaluationTests(unittest.TestCase):
    def test_metrics_and_scope_checks_pass_for_relevant_result(self) -> None:
        case = RagEvaluationCase.from_mapping(_case_mapping())
        service = FixedRagService(
            (
                _chunk("irrelevant", content="普通社团活动"),
                _chunk("relevant", content="七夕时大家把愿望挂在竹叶上"),
            )
        )

        report = evaluate_rag_cases(service, (case,), app_id="web-demo")

        self.assertEqual(report.passedCases, 1)
        self.assertEqual(report.hitRate, 1.0)
        self.assertEqual(report.meanRecallAtK, 1.0)
        self.assertEqual(report.meanReciprocalRank, 0.5)
        self.assertEqual(report.isolationFailureCases, 0)

    def test_cross_character_result_fails_isolation(self) -> None:
        case = RagEvaluationCase.from_mapping(_case_mapping())
        service = FixedRagService(
            (
                _chunk(
                    "relevant",
                    content="七夕时大家把愿望挂在竹叶上",
                    character_id="kyon",
                ),
            )
        )

        report = evaluate_rag_cases(service, (case,), app_id="web-demo")

        self.assertEqual(report.passedCases, 0)
        self.assertEqual(report.isolationFailureCases, 1)
        self.assertTrue(
            any("跨角色" in failure for failure in report.results[0].failures)
        )

    def test_loader_skips_pending_annotation(self) -> None:
        ready = _case_mapping()
        pending = {**ready, "case_id": "pending-1", "status": "pending", "query": ""}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "gold.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(item, ensure_ascii=False) for item in (ready, pending)
                )
                + "\n",
                encoding="utf-8",
            )

            cases, pending_count = load_rag_evaluation_cases(path)

        self.assertEqual(len(cases), 1)
        self.assertEqual(pending_count, 1)

    def test_natural_conversation_builds_same_director_query_shape(self) -> None:
        mapping = {
            **_case_mapping(),
            "query": "",
            "retrieval_channel": "director_bridge",
            "target_character_id": "haruhi",
            "timeline": "sigh",
            "conversation": [
                {"role": "user", "content": "今天别安排普通活动了"},
                {"role": "assistant", "content": "那你倒是说说什么才算有趣？"},
            ],
            "current_input": "不如把它变成全团调查？",
            "filters": {
                **_case_mapping()["filters"],
                "record_kinds": ["scene_memory"],
                "retrieval_channels": ["canonical_memory"],
                "knowledge_owners": ["kyon"],
            },
            "expected_record_kinds": [],
            "required_terms": [],
            "relevant_document_ids": [],
            "minimum_relevant_hits": 0,
            "maximum_retrieved_hits": 8,
        }
        case = RagEvaluationCase.from_mapping(mapping)
        service = FixedRagService(())

        report = evaluate_rag_cases(service, (case,), app_id="web-demo")

        self.assertEqual(report.passedCases, 1)
        retrieve_input = service.calls[0]
        self.assertEqual(str(retrieve_input.characterId), "kyon")
        self.assertEqual(str(retrieve_input.personaMode), "sigh_kyon")
        self.assertIn("目标角色：haruhi", retrieve_input.query)
        self.assertIn("user: 今天别安排普通活动了", retrieve_input.query)
        self.assertTrue(retrieve_input.query.endswith("不如把它变成全团调查？"))

    def test_no_retrieval_case_applies_relevance_gate(self) -> None:
        mapping = {
            **_case_mapping(),
            "relevant_document_ids": [],
            "minimum_relevant_hits": 0,
            "maximum_retrieved_hits": 0,
            "expected_record_kinds": [],
            "required_terms": [],
        }
        case = RagEvaluationCase.from_mapping(mapping)
        low_relevance = _chunk("low", content="不相关内容", score=0.05)

        report = evaluate_rag_cases(
            FixedRagService((low_relevance,)),
            (case,),
            app_id="web-demo",
            minimum_relevance_score=0.2,
        )

        self.assertEqual(report.passedCases, 1)
        self.assertEqual(report.results[0].retrievedDocumentIds, ())

    def test_no_retrieval_case_fails_when_relevant_gate_keeps_a_hit(self) -> None:
        mapping = {
            **_case_mapping(),
            "relevant_document_ids": [],
            "minimum_relevant_hits": 0,
            "maximum_retrieved_hits": 0,
            "expected_record_kinds": [],
            "required_terms": [],
        }
        case = RagEvaluationCase.from_mapping(mapping)

        report = evaluate_rag_cases(
            FixedRagService((_chunk("unexpected", content="高相关候选"),)),
            (case,),
            app_id="web-demo",
            minimum_relevance_score=0.2,
        )

        self.assertEqual(report.passedCases, 0)
        self.assertIn("超过上限 0", report.results[0].failures[0])


def _case_mapping() -> dict:
    return {
        "case_id": "tanabata-1",
        "status": "ready",
        "query": "七夕时春日让大家做了什么？",
        "character_id": "haruhi",
        "persona_mode": "sigh_haruhi",
        "top_k": 8,
        "filters": {
            "source_types": ["scene"],
            "timelines": ["sigh"],
            "spoiler_level_max": 2,
            "language": "zh-CN",
        },
        "relevant_document_ids": ["relevant"],
        "minimum_relevant_hits": 1,
        "expected_record_kinds": ["dialogue_example"],
        "required_terms": ["七夕"],
        "forbidden_document_ids": [],
    }


def _chunk(
    document_id: str,
    *,
    content: str,
    character_id: str = "haruhi",
    score: float = 0.8,
) -> RagChunk:
    return RagChunk(
        chunkId=RagChunkId(f"{document_id}-chunk-1"),
        documentId=RagDocumentId(document_id),
        content=content,
        score=score,
        metadata=RagDocumentMetadata(
            appId=AppId("web-demo"),
            characterId=CharacterId(character_id),
            timeline="sigh",
            spoilerLevel=2,
            language="zh-CN",
            sourceType="scene",
            extra={"record_kind": "dialogue_example"},
        ),
    )


if __name__ == "__main__":
    unittest.main()
