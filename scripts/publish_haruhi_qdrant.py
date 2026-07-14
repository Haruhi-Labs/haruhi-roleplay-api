#!/usr/bin/env python3
"""发布、回滚或清理 Qdrant 中的凉宫角色语料版本。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haruhi_roleplay_api.adapters import QdrantRagService  # noqa: E402
from haruhi_roleplay_api.infrastructure import (  # noqa: E402
    RuntimeConfigStore,
    activate_qdrant_collection,
    build_rag_service_from_env,
    corpus_version_from_file,
    publish_qdrant_corpus,
    versioned_collection_name,
)


DEFAULT_CORPUS = ROOT / ".data" / "rag-corpus" / "haruhi" / "records.jsonl"


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    env = RuntimeConfigStore(
        base_env=os.environ,
        config_path=args.env_file,
    ).env()
    _require_qdrant(parser, env)
    alias = args.alias or _configured_collection(env)
    if not alias:
        parser.error("必须通过 --alias、RAG_INDEX 或 QDRANT_COLLECTION 指定稳定 alias")

    if args.command == "publish":
        app_id = args.app_id or env.get("RAG_BOOTSTRAP_APP_ID", "").strip()
        if not app_id:
            parser.error("publish 必须传入 --app-id，或配置 RAG_BOOTSTRAP_APP_ID")
        corpus_version = corpus_version_from_file(args.corpus)
        collection = versioned_collection_name(
            prefix=args.collection_prefix or alias,
            corpus_version=corpus_version,
        )
        service = _service_for_collection(env, collection)
        summary = publish_qdrant_corpus(
            service,
            path=args.corpus,
            app_id=app_id,
            alias=alias,
        )
        _print_json(
            {
                "状态": "已发布",
                "corpus_version": summary.corpusVersion,
                "物理集合": summary.collection,
                "稳定_alias": summary.alias,
                "上一个集合": summary.previousCollection,
                "文档数": summary.ingest.documentCount,
                "point数": summary.pointCount,
            }
        )
        return 0

    collection = args.collection.strip()
    service = _service_for_collection(env, collection)
    if args.command == "activate":
        previous = activate_qdrant_collection(service, alias=alias)
        _print_json(
            {
                "状态": "已切换",
                "稳定_alias": alias,
                "当前集合": collection,
                "上一个集合": previous,
            }
        )
        return 0

    if args.confirm != collection:
        parser.error("delete 必须传入与 --collection 完全相同的 --confirm")
    service.delete_collection()
    _print_json({"状态": "已删除", "物理集合": collection})
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="以版本化物理集合和原子 alias 切换管理凉宫 Qdrant 语料。"
    )
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    subparsers = parser.add_subparsers(dest="command", required=True)

    publish = subparsers.add_parser("publish", help="导入新集合并原子切换 alias")
    publish.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    publish.add_argument("--app-id", default=None)
    publish.add_argument("--alias", default=None)
    publish.add_argument("--collection-prefix", default=None)

    activate = subparsers.add_parser("activate", help="切换到已存在的集合，用于回滚")
    activate.add_argument("--collection", required=True)
    activate.add_argument("--alias", default=None)

    delete = subparsers.add_parser("delete", help="删除未被 alias 引用的旧集合")
    delete.add_argument("--collection", required=True)
    delete.add_argument("--alias", default=None)
    delete.add_argument("--confirm", required=True)
    return parser


def _require_qdrant(
    parser: argparse.ArgumentParser,
    env: Mapping[str, str],
) -> None:
    provider = env.get("RAG_API_TYPE", env.get("RAG_PROVIDER", "local"))
    if provider.strip().lower().replace("-", "_") not in {"qdrant", "cloud_rag"}:
        parser.error("该脚本要求 RAG_API_TYPE 或 RAG_PROVIDER 为 qdrant")


def _configured_collection(env: Mapping[str, str]) -> str:
    return env.get("RAG_INDEX", env.get("QDRANT_COLLECTION", "")).strip()


def _service_for_collection(
    env: Mapping[str, str],
    collection: str,
) -> QdrantRagService:
    scoped_env = dict(env)
    scoped_env["QDRANT_COLLECTION"] = collection
    if scoped_env.get("RAG_API_TYPE", "").strip():
        scoped_env["RAG_INDEX"] = collection
    scoped_env["QDRANT_ENSURE_COLLECTION"] = "false"
    scoped_env.pop("RAG_BOOTSTRAP_CORPUS_PATH", None)
    scoped_env.pop("RAG_BOOTSTRAP_APP_ID", None)
    service = build_rag_service_from_env(scoped_env)
    if not isinstance(service, QdrantRagService):
        raise RuntimeError("当前配置没有构建出 QdrantRagService")
    return service


def _print_json(value: Mapping[str, object]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
