#!/usr/bin/env python3
"""构建凉宫系列角色扮演 RAG 语料。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haruhi_roleplay_api.corpus import (  # noqa: E402
    apply_reviewed_dialogue_overlay,
    build_haruhi_corpus,
)


DEFAULT_SOURCE = Path.home() / "Downloads" / "【小説】涼宮春日系列" / "txt"
DEFAULT_OUTPUT = ROOT / ".data" / "rag-corpus" / "haruhi"
DEFAULT_REVIEW_ROOT = ROOT / ".data" / "rag-corpus" / "haruhi-review"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="清洗、标注并分块凉宫系列小说，生成角色视角受限的 JSONL 语料。"
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="小说 txt 目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="生成目录")
    parser.add_argument(
        "--use-agent-review",
        action="store_true",
        help="用 Luna/Sol 逐条审阅结果替换旧的自动台词归因",
    )
    parser.add_argument("--review-root", type=Path, default=DEFAULT_REVIEW_ROOT)
    parser.add_argument(
        "--without-adjudication",
        action="store_true",
        help="只使用完整 Luna 首审，不叠加 Sol 复核结果",
    )
    args = parser.parse_args()

    result = build_haruhi_corpus(args.source, args.output)
    overlay = None
    if args.use_agent_review:
        overlay = apply_reviewed_dialogue_overlay(
            args.output,
            candidates_path=args.review_root / "dialogue_candidates.jsonl",
            luna_review_dir=args.review_root / "reviews" / "luna",
            adjudication_review_dir=(
                None
                if args.without_adjudication
                else args.review_root / "reviews" / "sol"
            ),
        )
    print(
        json.dumps(
            {
                "状态": "完成",
                "记录数": overlay.record_count if overlay else result.record_count,
                "逐条审阅台词数": overlay.dialogue_record_count if overlay else None,
                "语料文件": str(result.records_path),
                "清单文件": str(result.manifest_path),
                "统计": overlay.review_stats if overlay else result.stats,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
