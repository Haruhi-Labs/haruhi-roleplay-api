#!/usr/bin/env python3
"""计算 Luna/Sol 一致率、目标台词精确率代理指标与置信区间。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haruhi_roleplay_api.corpus.dialogue_review import (  # noqa: E402
    ReviewAnnotation,
    TARGET_SPEAKER_IDS,
    load_dialogue_review_index,
    load_dialogue_review_units,
)


DEFAULT_ROOT = ROOT / ".data" / "rag-corpus" / "haruhi-review"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成逐条引语审阅质量报告。")
    parser.add_argument(
        "--candidates",
        type=Path,
        default=DEFAULT_ROOT / "dialogue_candidates.jsonl",
    )
    parser.add_argument(
        "--luna-review",
        type=Path,
        default=DEFAULT_ROOT / "reviews" / "luna",
    )
    parser.add_argument(
        "--sol-review",
        type=Path,
        default=DEFAULT_ROOT / "reviews" / "sol",
    )
    parser.add_argument(
        "--selection-manifest",
        type=Path,
        default=DEFAULT_ROOT / "adjudication_selection.manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ROOT / "quality_report.json",
    )
    args = parser.parse_args()

    units = load_dialogue_review_units(args.candidates)
    luna = load_dialogue_review_index(args.luna_review, units=units, require_complete=True)
    sol = load_dialogue_review_index(args.sol_review, units=units, require_complete=False)
    selection = json.loads(args.selection_manifest.read_text(encoding="utf-8"))
    reasons_by_span = selection.get("reasons_by_span", {})
    if not isinstance(reasons_by_span, Mapping):
        raise ValueError("复核选择 manifest 缺少 reasons_by_span")
    selected_ids = {str(span_id) for span_id in reasons_by_span}
    missing_selected = selected_ids - set(sol.spans)
    if missing_selected:
        raise ValueError(f"Sol 结果缺少 {len(missing_selected)} 个已选择 span")
    random_sample_ids = {
        str(span_id)
        for span_id, reasons in reasons_by_span.items()
        if isinstance(reasons, list) and "quality_sample" in reasons
    }
    missing_sample = random_sample_ids - set(sol.spans)
    if missing_sample:
        raise ValueError(f"Sol 结果缺少 {len(missing_sample)} 个随机样本")

    all_pairs = [
        (span_id, luna.spans[span_id].annotation, reviewed.annotation)
        for span_id, reviewed in sol.spans.items()
    ]
    sample_pairs = [pair for pair in all_pairs if pair[0] in random_sample_ids]
    exact_agreement = sum(_exact_match(first, second) for _, first, second in all_pairs)
    sample_exact = sum(_exact_match(first, second) for _, first, second in sample_pairs)

    luna_positive = [pair for pair in sample_pairs if _target_speaker(pair[1]) is not None]
    sol_positive = [pair for pair in sample_pairs if _target_speaker(pair[2]) is not None]
    true_positive_for_precision = sum(
        _target_speaker(first) == _target_speaker(second)
        for _, first, second in luna_positive
    )
    true_positive_for_recall = sum(
        _target_speaker(first) == _target_speaker(second)
        for _, first, second in sol_positive
    )
    precision = _rate(true_positive_for_precision, len(luna_positive))
    recall = _rate(true_positive_for_recall, len(sol_positive))
    changes_by_field = Counter()
    for _, first, second in all_pairs:
        for field in ("function", "scope", "speaker", "word_owner", "certainty"):
            if getattr(first, field) != getattr(second, field):
                changes_by_field[field] += 1

    report: dict[str, Any] = {
        "schema_version": "dialogue-review-quality.v1",
        "reference_policy": (
            "Sol 不读取 Luna 答案的盲审复核作为模型质量代理，不等同于人工金标准确率；"
            "所有疑难项由 Sol 覆盖，随机样本只估计其余常规项。"
        ),
        "candidate_spans": luna.expected_span_count,
        "luna_coverage": luna.stats["coverage"],
        "sol_reviewed_spans": len(sol.spans),
        "selection": {
            "requested_spans": len(selected_ids),
            "covered_spans": len(selected_ids),
            "coverage": 1.0,
        },
        "all_sol_exact_agreement": _rate(exact_agreement, len(all_pairs)),
        "all_sol_changes_by_field": dict(sorted(changes_by_field.items())),
        "random_sample": {
            "size": len(sample_pairs),
            "exact_agreement": _rate(sample_exact, len(sample_pairs)),
            "luna_target_positive": len(luna_positive),
            "sol_target_positive": len(sol_positive),
            "target_speaker_precision_proxy": precision,
            "target_speaker_precision_proxy_wilson_95": _wilson_interval(
                true_positive_for_precision,
                len(luna_positive),
            ),
            "target_speaker_recall_proxy": recall,
            "target_speaker_recall_proxy_wilson_95": _wilson_interval(
                true_positive_for_recall,
                len(sol_positive),
            ),
        },
    }
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _target_speaker(annotation: ReviewAnnotation) -> str | None:
    if (
        annotation.function == "speech"
        and annotation.scope == "current_scene"
        and annotation.speaker in TARGET_SPEAKER_IDS
        and annotation.certainty in {"certain", "probable"}
    ):
        return annotation.speaker
    return None


def _exact_match(first: ReviewAnnotation, second: ReviewAnnotation) -> bool:
    return (
        first.function,
        first.scope,
        first.speaker,
        first.word_owner,
    ) == (
        second.function,
        second.scope,
        second.speaker,
        second.word_owner,
    )


def _rate(successes: int, total: int) -> float | None:
    return round(successes / total, 6) if total else None


def _wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> list[float] | None:
    if total == 0:
        return None
    probability = successes / total
    denominator = 1 + z * z / total
    center = (probability + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            probability * (1 - probability) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return [round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6)]


if __name__ == "__main__":
    raise SystemExit(main())
