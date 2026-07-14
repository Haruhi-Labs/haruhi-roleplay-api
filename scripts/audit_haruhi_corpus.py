#!/usr/bin/env python3
"""审计正式凉宫 RAG 语料并输出机器可读报告。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haruhi_roleplay_api.corpus import audit_haruhi_corpus  # noqa: E402


DEFAULT_ROOT = ROOT / ".data" / "rag-corpus" / "haruhi"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检查语料 schema、路由、视角边界和结构化台词完整性。"
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_ROOT / "records.jsonl")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_ROOT / "manifest.json")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ROOT / "production-audit.json",
    )
    args = parser.parse_args()

    report = audit_haruhi_corpus(args.corpus, manifest_path=args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.to_mapping(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "状态": "通过" if report.passed else "失败",
                "corpus_version": report.corpusVersion,
                "记录数": report.recordCount,
                "错误数": len(report.errors),
                "警告数": len(report.warnings),
                "报告": str(args.output.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
