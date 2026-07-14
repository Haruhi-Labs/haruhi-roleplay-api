#!/usr/bin/env python3
"""把已构建语料一次性写入 Chroma 或 Qdrant 等持久化 provider。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    RuntimeConfigStore,
    build_rag_service_from_env,
    ingest_corpus_file,
    require_production_embedding,
)


DEFAULT_CORPUS = ROOT / ".data" / "rag-corpus" / "haruhi" / "records.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="将凉宫系列 JSONL 语料写入当前配置的持久化 RAG provider。"
    )
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--app-id", default=None)
    parser.add_argument(
        "--allow-test-embedding",
        action="store_true",
        help="仅供非生产测试显式允许 hash embedding。",
    )
    args = parser.parse_args()

    store = RuntimeConfigStore(
        base_env=os.environ,
        config_path=args.env_file,
    )
    env = store.env()
    app_id = args.app_id or env.get("RAG_BOOTSTRAP_APP_ID", "").strip()
    if not app_id:
        parser.error("必须传入 --app-id，或在环境中配置 RAG_BOOTSTRAP_APP_ID")

    provider = env.get("RAG_PROVIDER", env.get("RAG_API_TYPE", "local")).strip().lower()
    if provider in {"local", "local_rag", "fake", "fake_rag"}:
        parser.error(
            "一次性导入只适用于 Chroma/Qdrant 等持久化 provider；"
            "纯内存 local provider 请使用 RAG_BOOTSTRAP_CORPUS_PATH 随服务启动装载"
        )

    require_production_embedding(
        env,
        allow_test_embedding=args.allow_test_embedding,
    )
    if args.allow_test_embedding:
        env["RAG_ALLOW_TEST_EMBEDDING"] = "true"

    # 避免 factory 先按启动配置自动装载一遍，再由本脚本重复调用。
    env.pop("RAG_BOOTSTRAP_CORPUS_PATH", None)
    env.pop("RAG_BOOTSTRAP_APP_ID", None)
    service = build_rag_service_from_env(env)
    summary = ingest_corpus_file(service, path=args.corpus, app_id=app_id)
    print(
        json.dumps(
            {
                "状态": "完成",
                "provider": provider,
                "app_id": str(summary.appId),
                "文档数": summary.documentCount,
                "分块数": summary.chunkCount,
                "语料文件": str(summary.path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
