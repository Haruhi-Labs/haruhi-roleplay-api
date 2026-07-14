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
CHARACTER_IDS = ("haruhi", "kyon", "mikuru", "yuki", "itsuki")


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
    sample_size = min(args.sample_size, len(records))
    negative_count = max(1, sample_size // 10) if sample_size >= 5 else 0
    positive_count = sample_size - negative_count
    director_count = positive_count // 3
    director_records = tuple(
        record
        for record in records
        if record.metadata.get("record_kind") == "scene_memory"
    )
    actor_records = tuple(
        record
        for record in records
        if record.metadata.get("record_kind") != "scene_memory"
    )
    selected = [
        *_stratified_sample(actor_records, size=positive_count - director_count),
        *_stratified_sample(director_records, size=director_count),
    ]
    versions = {str(record.metadata.get("corpus_version", "")) for record in records}
    if len(versions) != 1:
        raise ValueError("正式语料必须且只能包含一个 corpus_version")
    corpus_version = versions.pop()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for index, record in enumerate(selected, start=1):
            kind = str(record.metadata.get("record_kind", ""))
            retrieval_channel = (
                "director_bridge" if kind == "scene_memory" else "actor_reference"
            )
            target_character_id = (
                _director_target_character(record.document_id)
                if retrieval_channel == "director_bridge"
                else record.character_id
            )
            filters = {
                "source_types": [record.source_type],
                "timelines": [record.timeline],
                "record_kinds": [kind],
                "corpus_versions": [corpus_version],
                "spoiler_level_max": record.spoiler_level,
                "language": record.language,
            }
            if retrieval_channel == "director_bridge":
                filters.update(
                    {
                        "retrieval_channels": ["canonical_memory"],
                        "knowledge_owners": ["kyon"],
                    }
                )
            item = {
                "schema_version": "haruhi-rag-eval.v2",
                "case_id": f"haruhi-gold-{index:04d}",
                "status": "pending",
                "retrieval_channel": retrieval_channel,
                "target_character_id": target_character_id,
                "persona_mode": _persona_mode(
                    target_character_id,
                    record.timeline,
                ),
                "timeline": record.timeline,
                "conversation": [],
                "current_input": "",
                "query": "",
                "top_k": 5,
                "filters": filters,
                "relevant_document_ids": [record.document_id],
                "minimum_relevant_hits": 1,
                "maximum_retrieved_hits": 5,
                "expected_record_kinds": [kind],
                "required_terms": [],
                "forbidden_document_ids": [],
                "annotation": {
                    "instruction": (
                        "把 source_preview 只当桥段答案：编写 2—4 条自然的 user/assistant 前文和一条 current_input，"
                        "让当前对话可能联想到该互动模式，但不要出现作品名、篇章名或照抄原句；"
                        "director_bridge 只评幕后桥段，不把阿虚旁白变成目标角色知识。"
                        "补充所有同样可接受的 relevant_document_ids，确认后把 status 改为 ready。"
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
        for offset in range(negative_count):
            index = len(selected) + offset + 1
            target_character_id = CHARACTER_IDS[offset % len(CHARACTER_IDS)]
            retrieval_channel = (
                "actor_reference" if offset % 2 == 0 else "director_bridge"
            )
            filters = {
                "source_types": ["scene"],
                "timelines": ["mid_late"],
                "record_kinds": [
                    "dialogue_example"
                    if retrieval_channel == "actor_reference"
                    else "scene_memory"
                ],
                "corpus_versions": [corpus_version],
                "spoiler_level_max": 5,
                "language": "zh-CN",
            }
            if retrieval_channel == "director_bridge":
                filters.update(
                    {
                        "retrieval_channels": ["canonical_memory"],
                        "knowledge_owners": ["kyon"],
                    }
                )
            item = {
                "schema_version": "haruhi-rag-eval.v2",
                "case_id": f"haruhi-gold-{index:04d}",
                "status": "pending",
                "retrieval_channel": retrieval_channel,
                "target_character_id": target_character_id,
                "persona_mode": _persona_mode(target_character_id, "mid_late"),
                "timeline": "mid_late",
                "conversation": [],
                "current_input": "",
                "query": "",
                "top_k": 5,
                "filters": filters,
                "relevant_document_ids": [],
                "minimum_relevant_hits": 0,
                "maximum_retrieved_hits": 0,
                "expected_record_kinds": [],
                "required_terms": [],
                "forbidden_document_ids": [],
                "annotation": {
                    "instruction": (
                        "编写 2—4 条自然前文和一条 current_input，内容应是普通寒暄、即时任务或全新话题，"
                        "没有任何原作桥段能真正增强回答；用于验证低相关度时完全不注入。"
                        "确认后把 status 改为 ready。"
                    ),
                    "record_kind": "no_retrieval",
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
                "schema_version": "haruhi-rag-eval.v2",
                "corpus_version": corpus_version,
                "sample_size": len(selected) + negative_count,
                "positive_cases": len(selected),
                "negative_cases": negative_count,
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
                "抽样数": len(selected) + negative_count,
                "无召回用例": negative_count,
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
    return hashlib.sha256(f"haruhi-rag-gold-v2:{document_id}".encode()).hexdigest()


def _director_target_character(document_id: str) -> str:
    digest = hashlib.sha256(f"director-target:{document_id}".encode()).digest()
    return CHARACTER_IDS[int.from_bytes(digest[:2], "big") % len(CHARACTER_IDS)]


def _persona_mode(character_id: str, timeline: str) -> str:
    if timeline == "mid_late":
        return "mid_late_haruhi" if character_id == "haruhi" else f"default_{character_id}"
    return f"{timeline}_{character_id}"


if __name__ == "__main__":
    raise SystemExit(main())
