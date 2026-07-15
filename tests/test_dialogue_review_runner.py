from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from haruhi_roleplay_api.corpus.dialogue_review import (  # noqa: E402
    DialogueReviewUnit,
    QuoteSpan,
    ReviewAnnotation,
    compact_review_units,
)
from run_haruhi_dialogue_review import _extract_usage, _make_batches  # noqa: E402


def _unit(index: int, span_count: int) -> DialogueReviewUnit:
    text = "「测试」" * span_count
    spans = tuple(
        QuoteSpan(
            span_id=f"span-{index}-{span_index}",
            start=span_index * 4,
            end=span_index * 4 + 4,
            text="「测试」",
            opener="「",
            closer="」",
            depth=0,
            parent_span_id=None,
            closed=True,
        )
        for span_index in range(span_count)
    )
    return DialogueReviewUnit(
        review_unit_id=f"unit-{index}",
        source={
            "book_title": "测试卷",
            "section_title": "测试章",
            "line": index,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        },
        text=text,
        context_before=(),
        context_after=(),
        spans=spans,
        parse_warnings=(),
        automatic_attribution={},
    )


class DialogueReviewRunnerTests(unittest.TestCase):
    def test_batches_keep_units_whole_and_respect_span_limit(self) -> None:
        batches = _make_batches((_unit(1, 2), _unit(2, 2), _unit(3, 1)), max_spans=3)

        self.assertEqual([len(batch.span_ids) for batch in batches], [2, 3])
        self.assertEqual(len(batches[1].units), 2)
        self.assertEqual(batches[0].model_span_ids, ("s001", "s002"))

    def test_usage_parser_reads_last_codex_usage_event(self) -> None:
        events = "\n".join(
            [
                json.dumps({"type": "start", "usage": {"input_tokens": 10}}),
                json.dumps(
                    {
                        "type": "complete",
                        "result": {
                            "usage": {"input_tokens": 120, "output_tokens": 30}
                        },
                    }
                ),
            ]
        )

        self.assertEqual(
            _extract_usage(events),
            {"input_tokens": 120, "output_tokens": 30},
        )

    def test_adjudication_batch_embeds_prior_review_under_short_span_id(self) -> None:
        unit = _unit(1, 1)
        span_id = unit.spans[0].span_id
        prior = ReviewAnnotation(
            span_id=span_id,
            function="speech",
            scope="current_scene",
            speaker="haruhi",
            word_owner="same",
            certainty="probable",
            evidence=("turn_continuity",),
            rationale="首审结果",
        )

        batch = _make_batches(
            (unit,),
            max_spans=10,
            batch_prefix="sol-v1",
            prior_annotations={span_id: prior},
        )[0]
        compact = compact_review_units(
            batch.units,
            span_aliases=batch.span_aliases,
            unit_aliases=batch.unit_aliases,
            prior_reviews=batch.prior_annotations,
        )

        self.assertTrue(batch.batch_id.startswith("sol-v1-"))
        self.assertEqual(compact[0]["spans"][0]["span_id"], "s001")
        self.assertEqual(compact[0]["spans"][0]["prior"]["speaker"], "haruhi")


if __name__ == "__main__":
    unittest.main()
