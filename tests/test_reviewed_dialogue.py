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
                "paragraph_index": 0,
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

    def test_target_response_is_never_truncated_by_long_stimulus(self) -> None:
        previous = _dialogue_item(
            "「" + "很长的上下文。" * 90 + "」",
            speaker="haruhi",
            line=10,
            paragraph_index=0,
            prefix="previous",
        )
        target = _dialogue_item(
            "「是吗？」",
            speaker="kyon",
            line=11,
            paragraph_index=1,
            prefix="target",
        )

        records = _build_records(previous, target)
        record = next(item for item in records if item.character_id == "kyon")

        self.assertIn("【目标角色回答】\n阿虚：「是吗？」", record.content)
        self.assertEqual(record.metadata["target_text"], "「是吗？」")
        self.assertLessEqual(len(record.content), 760)

    def test_conversation_boundary_prevents_cross_scene_context(self) -> None:
        first = _dialogue_item(
            "「先去活动室。」",
            speaker="haruhi",
            line=10,
            paragraph_index=0,
            prefix="first",
        )
        reply = _dialogue_item(
            "「知道了。」",
            speaker="kyon",
            line=11,
            paragraph_index=1,
            prefix="reply",
        )
        later = _dialogue_item(
            "「茶点来了。」",
            speaker="mikuru",
            line=80,
            paragraph_index=20,
            prefix="later",
        )

        records = _build_records(first, reply, later)
        kyon = next(item for item in records if item.character_id == "kyon")
        mikuru = next(item for item in records if item.character_id == "mikuru")

        self.assertIn("凉宫春日：「先去活动室。」", kyon.content)
        self.assertNotIn("知道了", mikuru.content.split("【目标角色回答】", 1)[0])
        self.assertNotEqual(
            kyon.metadata["conversation_id"],
            mikuru.metadata["conversation_id"],
        )

    def test_dialogue_example_uses_only_previous_turns_and_structured_target(self) -> None:
        first = _dialogue_item(
            "「现在开始行动！」",
            speaker="haruhi",
            line=10,
            paragraph_index=0,
            prefix="first-target",
        )
        future = _dialogue_item(
            "「又来了。」",
            speaker="kyon",
            line=11,
            paragraph_index=1,
            prefix="future",
        )

        records = _build_records(first, future)
        haruhi = next(item for item in records if item.character_id == "haruhi")
        kyon = next(item for item in records if item.character_id == "kyon")

        self.assertNotIn("又来了", haruhi.content)
        self.assertEqual(haruhi.metadata["stimulus_turns"], [])
        self.assertEqual(kyon.metadata["stimulus_turns"][0]["speaker_id"], "haruhi")
        self.assertEqual(kyon.metadata["target_turn"]["speaker_id"], "kyon")
        self.assertEqual(kyon.metadata["response_turn"]["speaker_id"], "kyon")
        self.assertEqual(
            kyon.metadata["dialogue_schema_version"],
            "roleplay-dialogue-example.v2",
        )
        self.assertEqual(kyon.metadata["turn_index"], 1)

    def test_unknown_turn_is_omitted_and_target_alias_is_normalized(self) -> None:
        unknown = _dialogue_item(
            "「谁知道呢。」",
            speaker="unknown",
            line=10,
            paragraph_index=0,
            prefix="unknown",
        )
        aliased = _dialogue_item(
            "「请用茶。」",
            speaker="npc:mikuru",
            line=11,
            paragraph_index=1,
            prefix="aliased",
        )
        target = _dialogue_item(
            "「好，出发！」",
            speaker="haruhi",
            line=12,
            paragraph_index=2,
            prefix="alias-target",
        )

        records = _build_records(unknown, aliased, target)
        record = next(item for item in records if item.character_id == "haruhi")

        self.assertNotIn("未确认说话人", record.content)
        self.assertIn("朝比奈实玖瑠：「请用茶。」", record.content)
        self.assertEqual(record.metadata["context_speakers"], ["mikuru", "haruhi"])


def _dialogue_item(
    text: str,
    *,
    speaker: str,
    line: int,
    paragraph_index: int,
    prefix: str,
) -> tuple[DialogueReviewUnit, ReviewedSpan]:
    spans, _ = _quote_spans(text, unit_prefix=prefix)
    span = spans[0]
    unit = DialogueReviewUnit(
        review_unit_id=prefix,
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
            "line": line,
            "paragraph_index": paragraph_index,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        },
        text=text,
        context_before=(),
        context_after=(),
        spans=spans,
        parse_warnings=(),
        automatic_attribution={},
    )
    reviewed = ReviewedSpan(
        annotation=ReviewAnnotation(
            span_id=span.span_id,
            function="speech",
            scope="current_scene",
            speaker=speaker,
            word_owner="same",
            certainty="certain",
            evidence=("explicit_same",),
            rationale="测试台词",
        ),
        batch_id="batch",
        model="gpt-5.6-sol",
        model_reasoning_effort="low",
        prompt_version="v1",
    )
    return unit, reviewed


def _build_records(
    *items: tuple[DialogueReviewUnit, ReviewedSpan],
):
    units = tuple(unit for unit, _ in items)
    reviewed = {
        span.span_id: review
        for unit, review in items
        for span in unit.spans
    }
    return build_reviewed_dialogue_records(
        units,
        reviewed,
        converter=lambda value: value,
    )


if __name__ == "__main__":
    unittest.main()
