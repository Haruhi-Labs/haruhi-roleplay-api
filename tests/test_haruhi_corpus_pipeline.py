from __future__ import annotations

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
    load_corpus_records,
)


class HaruhiCorpusPipelineTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
