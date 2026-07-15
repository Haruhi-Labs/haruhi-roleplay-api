from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.corpus import audit_haruhi_corpus  # noqa: E402


class HaruhiCorpusAuditTests(unittest.TestCase):
    def test_valid_structured_dialogue_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            path.write_text(
                json.dumps(_dialogue_record(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            report = audit_haruhi_corpus(path)

        self.assertTrue(report.passed)
        self.assertEqual(report.errors, ())
        self.assertEqual(report.stats["dialogue"]["records"], 1)

    def test_future_dialogue_context_fails(self) -> None:
        record = _dialogue_record()
        record["metadata"]["stimulus_turns"] = [
            {
                "speaker_id": "kyon",
                "speaker_label": "阿虚",
                "text": "「等一下。」",
                "turn_index": 2,
                "paragraph_index": 12,
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            path.write_text(
                json.dumps(record, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            report = audit_haruhi_corpus(path)

        self.assertFalse(report.passed)
        self.assertTrue(any("位于目标回答之后" in error for error in report.errors))

    def test_exact_duplicate_content_fails(self) -> None:
        first = _dialogue_record()
        second = {**first, "document_id": "doc-dialogue-2"}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(record, ensure_ascii=False)
                    for record in (first, second)
                )
                + "\n",
                encoding="utf-8",
            )

            report = audit_haruhi_corpus(path)

        self.assertFalse(report.passed)
        self.assertIn("发现 1 条完全重复正文", report.errors)


def _dialogue_record() -> dict:
    response = {
        "speaker_id": "haruhi",
        "speaker_label": "凉宫春日",
        "text": "「开始社团活动吧！」",
        "turn_index": 1,
        "paragraph_index": 10,
    }
    corpus_version = "haruhi-rag-test-version"
    metadata = {
        "record_schema_version": "haruhi-rag-record.v2",
        "corpus_version": corpus_version,
        "dataset_version": corpus_version,
        "record_kind": "dialogue_example",
        "perspective": "spoken_by_character",
        "retrieval_channel": "dialogue_style",
        "knowledge_owner": "haruhi",
        "subject_character_id": "haruhi",
        "usage": "style_only",
        "dialogue_schema_version": "roleplay-dialogue-example.v2",
        "dialogue_scene_id": "scene-1",
        "scene_id": "scene-1",
        "conversation_id": "scene-1",
        "stimulus_turns": [],
        "response_turn": response,
        "target_turn": response,
        "target_text": response["text"],
        "review_method": "luna_first_pass",
        "review_certainty": "certain",
    }
    return {
        "schema_version": "haruhi-rag-record.v2",
        "corpus_version": corpus_version,
        "document_id": "doc-dialogue-1",
        "title": "测试台词",
        "character_id": "haruhi",
        "timeline": "melancholy",
        "spoiler_level": 1,
        "language": "zh-CN",
        "source_type": "scene",
        "trust_level": "canonical_agent_reviewed",
        "record_kind": "dialogue_example",
        "perspective": "spoken_by_character",
        "retrieval_channel": "dialogue_style",
        "knowledge_owner": "haruhi",
        "subject_character_id": "haruhi",
        "usage": "style_only",
        "content": (
            "作品：测试；资料类型：Agent逐条审阅角色台词；角色：凉宫春日。\n"
            "【目标角色回答】\n凉宫春日：「开始社团活动吧！」"
        ),
        "metadata": metadata,
    }


if __name__ == "__main__":
    unittest.main()
