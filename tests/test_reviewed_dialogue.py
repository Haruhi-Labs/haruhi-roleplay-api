from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.corpus.dialogue_review import (  # noqa: E402
    DialogueReviewUnit,
    ReviewAnnotation,
    ReviewedSpan,
    _quote_spans,
)
from haruhi_roleplay_api.corpus.reviewed_dialogue import (  # noqa: E402
    build_reviewed_dialogue_records,
)


class ReviewedDialogueTests(unittest.TestCase):
    def test_only_current_target_speech_becomes_record_and_nested_quote_is_hidden(self) -> None:
        text = "「我听古泉说过『这是我的推测』。」"
        spans, _ = _quote_spans(text, unit_prefix="unit")
        outer, inner = spans
        unit = DialogueReviewUnit(
            review_unit_id="unit",
            source={
                "book_id": "v01-melancholy",
                "volume": 1,
                "book_title": "凉宫春日的忧郁",
                "section_index": 1,
                "section_title": "第一章",
                "timeline": "melancholy",
                "spoiler_level": 1,
                "branch": None,
                "source_filename": "测试.txt",
                "line": 10,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            },
            text=text,
            context_before=(),
            context_after=(),
            spans=spans,
            parse_warnings=(),
            automatic_attribution={},
        )
        reviewed = {
            outer.span_id: ReviewedSpan(
                annotation=ReviewAnnotation(
                    span_id=outer.span_id,
                    function="speech",
                    scope="current_scene",
                    speaker="haruhi",
                    word_owner="same",
                    certainty="certain",
                    evidence=("explicit_next",),
                    rationale="后文明确为春日说道",
                ),
                batch_id="batch",
                model="gpt-5.6-luna",
                model_reasoning_effort="low",
                prompt_version="v1",
            ),
            inner.span_id: ReviewedSpan(
                annotation=ReviewAnnotation(
                    span_id=inner.span_id,
                    function="speech",
                    scope="reported_or_recalled",
                    speaker="none",
                    word_owner="itsuki",
                    certainty="certain",
                    evidence=("explicit_same",),
                    rationale="外层明确说是古泉旧话",
                ),
                batch_id="batch",
                model="gpt-5.6-luna",
                model_reasoning_effort="low",
                prompt_version="v1",
            ),
        }

        records = build_reviewed_dialogue_records(
            (unit,),
            reviewed,
            converter=lambda value: value,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].character_id, "haruhi")
        self.assertIn("『引用内容略』", records[0].content)
        self.assertNotIn("这是我的推测", records[0].content)


if __name__ == "__main__":
    unittest.main()
