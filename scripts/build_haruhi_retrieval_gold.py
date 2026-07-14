#!/usr/bin/env python3
"""从正式语料生成分层人工检索金标模板。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haruhi_roleplay_api.corpus import CorpusRecord, load_corpus_records  # noqa: E402


DEFAULT_CORPUS = ROOT / ".data" / "rag-corpus" / "haruhi" / "records.jsonl"
DEFAULT_OUTPUT = ROOT / ".data" / "rag-eval" / "haruhi" / "gold-template.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按记录类型、角色和时间线分层抽取人工检索标注任务。"
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-size", type=int, default=300)
    args = parser.parse_args()
    if args.sample_size <= 0:
        parser.error("--sample-size 必须为正整数")

    records = load_corpus_records(args.corpus)
    selected = _stratified_sample(records, size=min(args.sample_size, len(records)))
    versions = {str(record.metadata.get("corpus_version", "")) for record in records}
    if len(versions) != 1:
        raise ValueError("正式语料必须且只能包含一个 corpus_version")
    corpus_version = versions.pop()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for index, record in enumerate(selected, start=1):
            kind = str(record.metadata.get("record_kind", ""))
            item = {
                "case_id": f"haruhi-gold-{index:04d}",
                "status": "pending",
                "query": "",
                "character_id": record.character_id,
                "persona_mode": _persona_mode(record.character_id, record.timeline),
                "top_k": 8,
                "filters": {
                    "source_types": [record.source_type],
                    "timelines": [record.timeline],
                    "corpus_versions": [corpus_version],
                    "spoiler_level_max": record.spoiler_level,
                    "language": record.language,
                },
                "relevant_document_ids": [record.document_id],
                "minimum_relevant_hits": 1,
                "expected_record_kinds": [kind],
                "required_terms": [],
                "forbidden_document_ids": [],
                "annotation": {
                    "instruction": (
                        "阅读 source_preview，写出一个不知道原句措辞、但真实用户可能提出的查询；"
                        "确认该记录确实相关后，把 status 改为 ready。"
                    ),
                    "book_title": record.metadata.get("book_title"),
                    "section_title": record.metadata.get("section_title"),
                    "source_line": record.metadata.get(
                        "source_line", record.metadata.get("source_line_start")
                    ),
                    "record_kind": kind,
                    "source_preview": record.content,
                },
            }
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    strata = Counter(
        (
            str(record.metadata.get("record_kind", "")),
            record.character_id,
            record.timeline,
        )
        for record in selected
    )
    manifest_path = args.output.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "haruhi-rag-eval.v1",
                "corpus_version": corpus_version,
                "sample_size": len(selected),
                "strata": {
                    "|".join(key): count for key, count in sorted(strata.items())
                },
                "status": "pending_human_annotation",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "状态": "待人工标注",
                "抽样数": len(selected),
                "分层数": len(strata),
                "模板": str(args.output.resolve()),
                "清单": str(manifest_path.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _stratified_sample(
    records: tuple[CorpusRecord, ...],
    *,
    size: int,
) -> list[CorpusRecord]:
    groups: dict[tuple[str, str, str], list[CorpusRecord]] = defaultdict(list)
    for record in records:
        groups[
            (
                str(record.metadata.get("record_kind", "")),
                record.character_id,
                record.timeline,
            )
        ].append(record)
    for group in groups.values():
        group.sort(key=lambda record: _stable_sample_key(record.document_id))
    offsets = {key: 0 for key in groups}
    selected: list[CorpusRecord] = []
    while len(selected) < size:
        progressed = False
        for key in sorted(groups):
            offset = offsets[key]
            if offset >= len(groups[key]):
                continue
            selected.append(groups[key][offset])
            offsets[key] = offset + 1
            progressed = True
            if len(selected) >= size:
                break
        if not progressed:
            break
    return selected


def _stable_sample_key(document_id: str) -> str:
    return hashlib.sha256(f"haruhi-rag-gold-v1:{document_id}".encode()).hexdigest()


def _persona_mode(character_id: str, timeline: str) -> str:
    if timeline == "mid_late":
        return "mid_late_haruhi" if character_id == "haruhi" else f"default_{character_id}"
    return f"{timeline}_{character_id}"


if __name__ == "__main__":
    raise SystemExit(main())
