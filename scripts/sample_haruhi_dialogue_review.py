#!/usr/bin/env python3
"""按卷和风险类型生成可复现的引语审阅抽查包。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haruhi_roleplay_api.corpus.dialogue_review import (  # noqa: E402
    TARGET_SPEAKER_IDS,
    load_dialogue_review_index,
    load_dialogue_review_units,
)


DEFAULT_ROOT = ROOT / ".data" / "rag-corpus" / "haruhi-review"
_CATEGORY_PRIORITY = (
    "疑难",
    "嵌套或配对异常",
    "旧规则冲突",
    "非台词",
    "目标probable",
    "NPC台词",
    "目标certain",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成逐条引语审阅分层抽查包。")
    parser.add_argument(
        "--candidates",
        type=Path,
        default=DEFAULT_ROOT / "dialogue_candidates.jsonl",
    )
    parser.add_argument(
        "--review",
        type=Path,
        default=DEFAULT_ROOT / "reviews" / "luna",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ROOT / "audit_samples.json",
    )
    parser.add_argument("--per-book", type=int, default=4)
    parser.add_argument("--seed", default="haruhi-dialogue-manual-audit-v1")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    if args.per_book < 1:
        parser.error("--per-book 必须大于 0")

    units = load_dialogue_review_units(args.candidates)
    index = load_dialogue_review_index(
        args.review,
        units=units,
        require_complete=args.require_complete,
    )
    groups: dict[tuple[str, str], list[tuple[str, Any, Any, Any, Any]]] = defaultdict(list)
    book_counts: Counter[str] = Counter()
    for unit in units:
        automatic = unit.automatic_attribution.get("speaker_id")
        for span in unit.spans:
            reviewed = index.spans.get(span.span_id)
            if reviewed is None:
                continue
            annotation = reviewed.annotation
            book_id = str(unit.source["book_id"])
            book_counts[book_id] += 1
            for category in _categories(unit, span, annotation, automatic):
                groups[(book_id, category)].append(
                    (span.span_id, unit, span, annotation, automatic)
                )

    for items in groups.values():
        items.sort(key=lambda item: _rank(item[0], seed=args.seed))
    samples: list[dict[str, Any]] = []
    for book_id in sorted(book_counts):
        selected_span_ids: set[str] = set()
        for category in _CATEGORY_PRIORITY:
            items = groups.get((book_id, category), [])
            candidate = next(
                (item for item in items if item[0] not in selected_span_ids),
                None,
            )
            if candidate is None:
                continue
            span_id, unit, span, annotation, automatic = candidate
            selected_span_ids.add(span_id)
            samples.append(
                {
                    "book_id": book_id,
                    "category": category,
                    "section": unit.source["section_title"],
                    "line": unit.source["line"],
                    "context_before": list(unit.context_before[-2:]),
                    "text": unit.text,
                    "span": span.to_mapping(),
                    "context_after": list(unit.context_after[:2]),
                    "automatic_speaker": automatic,
                    "review": annotation.to_mapping(),
                    "audit": {
                        "status": "pending",
                        "correct": None,
                        "notes": "",
                    },
                }
            )
            if len(selected_span_ids) >= args.per_book:
                break

    output = {
        "schema_version": "dialogue-review-audit-sample.v1",
        "seed": args.seed,
        "per_book": args.per_book,
        "review_coverage": index.stats["coverage"],
        "reviewed_by_book": dict(sorted(book_counts.items())),
        "sample_count": len(samples),
        "samples": samples,
    }
    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "状态": "完成",
                "审阅覆盖率": index.stats["coverage"],
                "样本数": len(samples),
                "已覆盖卷册": len(book_counts),
                "抽查包": str(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _categories(unit: Any, span: Any, annotation: Any, automatic: Any) -> tuple[str, ...]:
    categories: list[str] = []
    if (
        annotation.certainty == "uncertain"
        or annotation.speaker == "unknown"
        or annotation.word_owner == "unknown"
    ):
        categories.append("疑难")
    if span.depth > 0 or unit.parse_warnings:
        categories.append("嵌套或配对异常")
    if (
        span.depth == 0
        and span.start == 0
        and automatic is not None
        and annotation.function == "speech"
        and annotation.scope == "current_scene"
        and automatic != annotation.speaker
    ):
        categories.append("旧规则冲突")
    if annotation.function != "speech":
        categories.append("非台词")
    elif annotation.speaker in TARGET_SPEAKER_IDS and annotation.certainty == "probable":
        categories.append("目标probable")
    elif annotation.speaker in TARGET_SPEAKER_IDS:
        categories.append("目标certain")
    else:
        categories.append("NPC台词")
    return tuple(categories)


def _rank(span_id: str, *, seed: str) -> str:
    return hashlib.sha256(f"{seed}\0{span_id}".encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
