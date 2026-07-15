#!/usr/bin/env python3
"""导出凉宫小说的逐条引语审阅候选。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haruhi_roleplay_api.corpus import export_dialogue_review_candidates  # noqa: E402


DEFAULT_SOURCE = Path.home() / "Downloads" / "【小説】涼宮春日系列" / "txt"
DEFAULT_OUTPUT = ROOT / ".data" / "rag-corpus" / "haruhi-review"


def main() -> int:
    parser = argparse.ArgumentParser(description="导出全部引语 span 和紧邻上下文。")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--context-radius", type=int, default=3)
    parser.add_argument("--context-max-chars", type=int, default=260)
    args = parser.parse_args()

    result = export_dialogue_review_candidates(
        args.source,
        args.output,
        context_radius=args.context_radius,
        context_max_chars=args.context_max_chars,
    )
    print(
        json.dumps(
            {
                "状态": "完成",
                "审阅单元数": result.unit_count,
                "引语 span 数": result.span_count,
                "候选文件": str(result.candidates_path),
                "清单文件": str(result.manifest_path),
                "统计": result.stats,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
