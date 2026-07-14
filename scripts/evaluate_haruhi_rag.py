#!/usr/bin/env python3
"""在真实 RAG provider 上运行凉宫检索金标评测。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    RagProviderSettings,
    RuntimeConfigStore,
    build_rag_service_from_env,
    evaluate_rag_cases,
    load_rag_evaluation_cases,
)


DEFAULT_ROOT = ROOT / ".data" / "rag-eval" / "haruhi"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="计算 Recall@K、MRR、命中率并检查角色/时间线/persona 隔离。"
    )
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--cases", type=Path, default=DEFAULT_ROOT / "gold.jsonl")
    parser.add_argument("--app-id", default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_ROOT / "report.json")
    parser.add_argument("--minimum-hit-rate", type=float, default=0.90)
    parser.add_argument("--minimum-mrr", type=float, default=0.50)
    args = parser.parse_args()

    env = RuntimeConfigStore(
        base_env=os.environ,
        config_path=args.env_file,
    ).env()
    app_id = args.app_id or env.get("RAG_BOOTSTRAP_APP_ID", "").strip()
    if not app_id:
        parser.error("必须传入 --app-id，或配置 RAG_BOOTSTRAP_APP_ID")
    cases, pending = load_rag_evaluation_cases(args.cases)
    if not cases:
        parser.error("评测集没有 status=ready 的用例")
    service = build_rag_service_from_env(env)
    rag_settings = RagProviderSettings.from_mapping(env)
    report = evaluate_rag_cases(
        service,
        cases,
        app_id=app_id,
        pending_cases=pending,
        minimum_relevance_score=rag_settings.minimumRelevanceScore,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.to_mapping(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    mrr = report.meanReciprocalRank or 0.0
    passed = (
        report.hitRate >= args.minimum_hit_rate
        and mrr >= args.minimum_mrr
        and report.isolationFailureCases == 0
    )
    print(
        json.dumps(
            {
                "状态": "通过" if passed else "失败",
                "已评测": report.evaluatedCases,
                "待标注": report.pendingCases,
                "用例通过率": round(report.hitRate, 6),
                "平均Recall@K": report.meanRecallAtK,
                "MRR": report.meanReciprocalRank,
                "隔离失败用例": report.isolationFailureCases,
                "报告": str(args.output.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
