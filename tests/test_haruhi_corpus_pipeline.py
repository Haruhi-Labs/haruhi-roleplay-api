from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.adapters.rag import _chunk_text  # noqa: E402
from haruhi_roleplay_api.corpus.pipeline import (  # noqa: E402
    CorpusRecord,
    _clean_source_lines,
    _speaker_candidates,
    finalize_corpus_records,
    load_corpus_records,
)


class HaruhiCorpusPipelineTests(unittest.TestCase):
    def test_loads_tracked_gzip_jsonl_without_manual_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl.gz"
            record = CorpusRecord(
                document_id="doc-gzip",
                title="压缩语料",
                character_id="haruhi",
                timeline="melancholy",
                spoiler_level=1,
                language="zh-CN",
                source_type="scene",
                trust_level="reviewed",
                content="压缩后的正式语料可以直接装载。",
                metadata={},
            )
            with gzip.open(path, mode="wt", encoding="utf-8") as handle:
                handle.write(json.dumps(record.to_mapping(), ensure_ascii=False))
                handle.write("\n")

            loaded = load_corpus_records(path)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].document_id, "doc-gzip")

    def test_cleaner_removes_scan_group_boilerplate_and_control_tokens(self) -> None:
        lines = _clean_source_lines(
            "\ufeff凉宫春日的忧郁\r\n"
            "轻之国度录入组录入\r\n"
            "chapter\r\n"
            "第一章\r\n"
            "　正文段落。\r\n"
        )

        self.assertEqual(
            lines,
            (
                (1, "凉宫春日的忧郁"),
                (4, "第一章"),
                (5, "正文段落。"),
            ),
        )

    def test_speaker_attribution_prefers_syntactic_subject(self) -> None:
        haruhi = _speaker_candidates(
            "春日把朝比奈學姊拉過來說：",
            base_score=0.98,
            reason="test",
        )
        tsuruya = _speaker_candidates(
            "聽到春日的語氣，一旁的鶴屋學姊說道：",
            base_score=0.98,
            reason="test",
        )

        self.assertEqual(haruhi[0][1], "haruhi")
        self.assertEqual(tsuruya, [])

    def test_speaker_attribution_does_not_treat_lexical_shuodao_as_speech(self) -> None:
        candidates = _speaker_candidates(
            "我早就知道結果。",
            base_score=0.93,
            reason="test",
        )

        self.assertEqual(candidates, [])

    def test_chunker_packs_short_paragraphs_and_keeps_newlines(self) -> None:
        chunks = _chunk_text("标题行\n第一句。\n第二句。", 20)

        self.assertEqual(chunks, ("标题行\n第一句。\n第二句。",))

    def test_jsonl_loader_round_trips_record_metadata(self) -> None:
        record = CorpusRecord(
            document_id="haruhi-test-1",
            title="测试语料",
            character_id="haruhi",
            timeline="melancholy",
            spoiler_level=1,
            language="zh-CN",
            source_type="scene",
            trust_level="canonical",
            content="作品：测试。\n春日：「现在开始行动！」",
            metadata={"record_kind": "dialogue_example", "confidence": 0.98},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text(
                json.dumps(record.to_mapping(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            loaded = load_corpus_records(path)

        self.assertEqual(loaded, (record,))

    def test_finalizer_promotes_roleplay_routing_fields_and_versions(self) -> None:
        record = CorpusRecord(
            document_id="haruhi-test-observation",
            title="春日行为观察",
            character_id="haruhi",
            timeline="melancholy",
            spoiler_level=1,
            language="zh-CN",
            source_type="scene",
            trust_level="canonical_heuristic",
            content="作品：测试。\n春日露出不耐烦的表情。",
            metadata={
                "record_kind": "behavior_observation",
                "perspective": "kyon_observation_not_character_memory",
            },
        )

        finalized, corpus_version = finalize_corpus_records(
            (record,),
            pipeline_version="test.v1",
        )
        mapping = finalized[0].to_mapping()

        self.assertEqual(mapping["schema_version"], "haruhi-rag-record.v2")
        self.assertEqual(mapping["corpus_version"], corpus_version)
        self.assertEqual(mapping["retrieval_channel"], "style_observation")
        self.assertEqual(mapping["knowledge_owner"], "kyon")
        self.assertEqual(mapping["subject_character_id"], "haruhi")
        self.assertEqual(mapping["usage"], "style_only")

    def test_finalizer_deduplicates_exact_record_and_keeps_better_review(self) -> None:
        common = {
            "title": "重复台词",
            "character_id": "haruhi",
            "timeline": "melancholy",
            "spoiler_level": 1,
            "language": "zh-CN",
            "source_type": "scene",
            "trust_level": "canonical_agent_reviewed",
            "content": "作品：测试。\n【目标角色回答】\n凉宫春日：「开始吧！」",
        }
        luna = CorpusRecord(
            document_id="haruhi-luna",
            metadata={
                "record_kind": "dialogue_example",
                "perspective": "spoken_by_character",
                "confidence": 0.95,
                "review_method": "luna_first_pass",
                "review_certainty": "certain",
            },
            **common,
        )
        sol = CorpusRecord(
            document_id="haruhi-sol",
            metadata={
                "record_kind": "dialogue_example",
                "perspective": "spoken_by_character",
                "confidence": 0.98,
                "review_method": "sol_adjudication",
                "review_certainty": "certain",
            },
            **common,
        )

        finalized, _ = finalize_corpus_records(
            (luna, sol),
            pipeline_version="test.v1",
        )

        self.assertEqual(len(finalized), 1)
        self.assertEqual(finalized[0].document_id, "haruhi-sol")

    def test_loader_rejects_conflicting_promoted_field(self) -> None:
        record = CorpusRecord(
            document_id="haruhi-test-conflict",
            title="冲突记录",
            character_id="haruhi",
            timeline="melancholy",
            spoiler_level=1,
            language="zh-CN",
            source_type="scene",
            trust_level="canonical",
            content="测试内容",
            metadata={
                "record_kind": "dialogue_example",
                "perspective": "spoken_by_character",
            },
        )
        finalized, _ = finalize_corpus_records(
            (record,),
            pipeline_version="test.v1",
        )
        mapping = finalized[0].to_mapping()
        mapping["record_kind"] = "scene_memory"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text(
                json.dumps(mapping, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "与 metadata 不一致"):
                load_corpus_records(path)


if __name__ == "__main__":
    unittest.main()
