#!/usr/bin/env python3
"""从 Luna 首审中选择疑难项、规则冲突和确定性质量样本。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haruhi_roleplay_api.corpus.dialogue_review import (  # noqa: E402
    TARGET_SPEAKER_IDS,
    load_dialogue_review_index,
    load_dialogue_review_units,
)


DEFAULT_REVIEW_ROOT = ROOT / ".data" / "rag-corpus" / "haruhi-review"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Sol 独立复核 span 清单。")
    parser.add_argument(
        "--candidates",
        type=Path,
        default=DEFAULT_REVIEW_ROOT / "dialogue_candidates.jsonl",
    )
    parser.add_argument(
        "--luna-review",
        type=Path,
        default=DEFAULT_REVIEW_ROOT / "reviews" / "luna",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REVIEW_ROOT / "adjudication_selection.txt",
    )
    parser.add_argument("--sample-rate", type=float, default=0.05)
    parser.add_argument("--sample-seed", default="haruhi-dialogue-audit-v1")
    args = parser.parse_args()
    if not 0 <= args.sample_rate <= 1:
        parser.error("--sample-rate 必须在 0 到 1 之间")

    units = load_dialogue_review_units(args.candidates)
    review = load_dialogue_review_index(
        args.luna_review,
        units=units,
        require_complete=True,
    )
    selected: dict[str, tuple[str, ...]] = {}
    reason_counts: Counter[str] = Counter()
    selected_unit_ids: set[str] = set()
    for unit in units:
        automatic_speaker = unit.automatic_attribution.get("speaker_id")
        for span in unit.spans:
            reviewed = review.spans[span.span_id].annotation
            reasons: set[str] = set()
            if not span.closed or unit.parse_warnings:
                reasons.add("quote_parse_anomaly")
            if span.depth > 0:
                reasons.add("nested_quote")
            if reviewed.certainty == "uncertain":
                reasons.add("uncertain")
            if reviewed.speaker == "unknown" or reviewed.word_owner == "unknown":
                reasons.add("unknown_identity")
            if reviewed.function == "speech" and reviewed.scope != "current_scene":
                reasons.add("noncurrent_speech_scope")
            if (
                reviewed.function == "speech"
                and reviewed.scope == "current_scene"
                and reviewed.speaker in TARGET_SPEAKER_IDS
                and reviewed.certainty == "probable"
            ):
                reasons.add("probable_target_dialogue")
            if (
                span.depth == 0
                and span.start == 0
                and automatic_speaker is not None
                and reviewed.function == "speech"
                and reviewed.scope == "current_scene"
                and automatic_speaker != reviewed.speaker
            ):
                reasons.add("automatic_conflict")
            if not reasons and _sampled(
                span.span_id,
                seed=args.sample_seed,
                rate=args.sample_rate,
            ):
                reasons.add("quality_sample")
            if not reasons:
                continue
            selected[span.span_id] = tuple(sorted(reasons))
            selected_unit_ids.add(unit.review_unit_id)
            reason_counts.update(reasons)

    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(f"{span_id}\n" for span_id in selected), encoding="utf-8")
    manifest = {
        "schema_version": "dialogue-adjudication-selection.v1",
        "candidate_file": str(args.candidates.expanduser().resolve()),
        "luna_review": str(args.luna_review.expanduser().resolve()),
        "sample_rate": args.sample_rate,
        "sample_seed": args.sample_seed,
        "total_spans": review.expected_span_count,
        "selected_spans": len(selected),
        "selected_units": len(selected_unit_ids),
        "reason_counts": dict(sorted(reason_counts.items())),
        "selection_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "reasons_by_span": selected,
    }
    manifest_path = output_path.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "状态": "完成",
                "复核 span 数": len(selected),
                "涉及审阅单元": len(selected_unit_ids),
                "原因统计": dict(sorted(reason_counts.items())),
                "清单": str(output_path),
                "清单元数据": str(manifest_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _sampled(span_id: str, *, seed: str, rate: float) -> bool:
    digest = hashlib.sha256(f"{seed}\0{span_id}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big") / 2**64
    return value < rate


if __name__ == "__main__":
    raise SystemExit(main())
