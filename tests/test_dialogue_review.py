from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from haruhi_roleplay_api.corpus.dialogue_review import (  # noqa: E402
    DialogueReviewUnit,
    _quote_spans,
    load_dialogue_review_index,
    normalize_review_output,
    parse_review_annotations,
    validate_review_unit,
)


class DialogueReviewTests(unittest.TestCase):
    def test_quote_spans_preserve_multiple_and_nested_quotes(self) -> None:
        text = "「古泉说过『这是推测』。」我答道：「我知道。」"

        spans, warnings = _quote_spans(text, unit_prefix="test-unit")

        self.assertEqual(warnings, ())
        self.assertEqual([span.text for span in spans], [
            "「古泉说过『这是推测』。」",
            "『这是推测』",
            "「我知道。」",
        ])
        self.assertEqual(spans[1].parent_span_id, spans[0].span_id)
        self.assertEqual(spans[0].depth, 0)
        self.assertEqual(spans[1].depth, 1)

    def test_quote_spans_keep_unclosed_candidate_and_warning(self) -> None:
        spans, warnings = _quote_spans("「没有闭合", unit_prefix="test-unit")

        self.assertEqual(len(spans), 1)
        self.assertFalse(spans[0].closed)
        self.assertTrue(warnings)

    def test_review_unit_rejects_changed_source_text(self) -> None:
        unit = DialogueReviewUnit(
            review_unit_id="unit",
            source={"text_sha256": hashlib.sha256("原文".encode()).hexdigest()},
            text="被修改",
            context_before=(),
            context_after=(),
            spans=(),
            parse_warnings=(),
            automatic_attribution={},
        )

        with self.assertRaisesRegex(ValueError, "正文指纹"):
            validate_review_unit(unit)

    def test_parse_review_annotations_requires_exact_span_coverage(self) -> None:
        good = {
            "annotations": [
                {
                    "span_id": "span-1",
                    "function": "speech",
                    "scope": "current_scene",
                    "speaker": "haruhi",
                    "word_owner": "same",
                    "certainty": "certain",
                    "evidence": ["explicit_next"],
                    "rationale": "下一段明确写明春日说道",
                }
            ]
        }

        annotations = parse_review_annotations(good, expected_span_ids=("span-1",))

        self.assertEqual(annotations[0].speaker, "haruhi")
        with self.assertRaisesRegex(ValueError, "span 不完整"):
            parse_review_annotations(good, expected_span_ids=("span-1", "span-2"))

    def test_certain_style_only_attribution_is_rejected(self) -> None:
        data = {
            "annotations": [
                {
                    "span_id": "span-1",
                    "function": "speech",
                    "scope": "current_scene",
                    "speaker": "haruhi",
                    "word_owner": "same",
                    "certainty": "certain",
                    "evidence": ["style_only"],
                    "rationale": "像春日的口气",
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "certain"):
            parse_review_annotations(data, expected_span_ids=("span-1",))

    def test_non_speech_cannot_claim_a_delivery_speaker(self) -> None:
        data = {
            "annotations": [
                {
                    "span_id": "span-1",
                    "function": "thought",
                    "scope": "not_applicable",
                    "speaker": "kyon",
                    "word_owner": "kyon",
                    "certainty": "certain",
                    "evidence": ["explicit_same"],
                    "rationale": "旁白明确写为阿虚心想",
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "speaker 必须是 none"):
            parse_review_annotations(data, expected_span_ids=("span-1",))

    def test_review_index_reports_complete_coverage(self) -> None:
        text = "「测试」"
        span = _quote_spans(text, unit_prefix="unit")[0][0]
        unit = DialogueReviewUnit(
            review_unit_id="unit",
            source={"text_sha256": hashlib.sha256(text.encode()).hexdigest()},
            text=text,
            context_before=(),
            context_after=(),
            spans=(span,),
            parse_warnings=(),
            automatic_attribution={},
        )
        with tempfile.TemporaryDirectory() as directory:
            review_dir = Path(directory)
            (review_dir / "batches").mkdir()
            (review_dir / "batches" / "batch.json").write_text(
                json.dumps(
                    {
                        "batch_id": "batch",
                        "model": "gpt-5.6-luna",
                        "model_reasoning_effort": "low",
                        "prompt_version": "v1",
                        "annotations": [
                            {
                                "span_id": span.span_id,
                                "function": "speech",
                                "scope": "current_scene",
                                "speaker": "haruhi",
                                "word_owner": "same",
                                "certainty": "certain",
                                "evidence": ["explicit_same"],
                                "rationale": "同段明确归因",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            index = load_dialogue_review_index(review_dir, units=(unit,))

        self.assertTrue(index.complete)
        self.assertEqual(index.stats["coverage"], 1.0)
        self.assertEqual(index.stats["target_current_scene_spans"], 1)

    def test_normalizer_only_fixes_deterministic_cross_field_issues(self) -> None:
        data = {
            "batch_id": "batch",
            "annotations": [
                {
                    "span_id": "span-1",
                    "function": "thought",
                    "scope": "current_scene",
                    "speaker": "kyon",
                    "word_owner": "same",
                    "certainty": "certain",
                    "evidence": ["style_only", "style_only"],
                    "rationale": "阿虚心想",
                }
            ],
        }

        normalized, changes = normalize_review_output(data)
        annotation = normalized["annotations"][0]

        self.assertEqual(annotation["speaker"], "none")
        self.assertEqual(annotation["word_owner"], "kyon")
        self.assertEqual(annotation["scope"], "not_applicable")
        self.assertEqual(annotation["certainty"], "probable")
        self.assertEqual(annotation["evidence"], ["style_only"])
        self.assertGreaterEqual(len(changes), 4)

    def test_normalizer_maps_target_names_and_prefixes_bare_npc_names(self) -> None:
        data = {
            "annotations": [
                {
                    "span_id": "span-1",
                    "function": "speech",
                    "scope": "current_scene",
                    "speaker": "涼宮春日",
                    "word_owner": "三味线",
                    "certainty": "certain",
                    "evidence": ["explicit_same"],
                    "rationale": "测试",
                }
            ]
        }

        normalized, _ = normalize_review_output(data)

        self.assertEqual(normalized["annotations"][0]["speaker"], "haruhi")
        self.assertEqual(normalized["annotations"][0]["word_owner"], "npc:三味线")


if __name__ == "__main__":
    unittest.main()
