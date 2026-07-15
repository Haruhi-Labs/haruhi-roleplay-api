"""正式角色语料的确定性生产审计。"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from haruhi_roleplay_api.corpus.pipeline import (
    CORPUS_RECORD_SCHEMA_VERSION,
    MAX_RECORD_CONTENT_CHARS,
    CorpusRecord,
    load_corpus_records,
)


_ROUTING_PROFILES: Mapping[str, Mapping[str, str]] = {
    "scene_memory": {
        "perspective": "kyon_first_person",
        "retrieval_channel": "canonical_memory",
        "knowledge_owner": "kyon",
        "subject_character_id": "kyon",
        "usage": "knowledge",
    },
    "dialogue_example": {
        "perspective": "spoken_by_character",
        "retrieval_channel": "dialogue_style",
        "usage": "style_only",
    },
    "inner_monologue": {
        "perspective": "kyon_inner_monologue",
        "retrieval_channel": "internal_voice",
        "knowledge_owner": "kyon",
        "subject_character_id": "kyon",
        "usage": "style_and_memory",
    },
    "behavior_observation": {
        "perspective": "kyon_observation_not_character_memory",
        "retrieval_channel": "style_observation",
        "knowledge_owner": "kyon",
        "usage": "style_only",
    },
}


@dataclass(frozen=True, kw_only=True)
class CorpusAuditReport:
    passed: bool
    corpusVersion: str | None
    recordCount: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    stats: Mapping[str, Any]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "corpus_version": self.corpusVersion,
            "record_count": self.recordCount,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "stats": dict(self.stats),
        }


def audit_haruhi_corpus(
    path: Path,
    *,
    manifest_path: Path | None = None,
) -> CorpusAuditReport:
    records = load_corpus_records(path.expanduser().resolve())
    errors: list[str] = []
    warnings: list[str] = []
    document_ids = Counter(record.document_id for record in records)
    exact_contents = Counter(record.content for record in records)
    versions = Counter(
        str(record.metadata.get("corpus_version", "")) for record in records
    )
    versions.pop("", None)
    if len(versions) != 1:
        errors.append("全部记录必须且只能使用一个 corpus_version")
    corpus_version = next(iter(versions), None)
    duplicate_ids = sum(count - 1 for count in document_ids.values() if count > 1)
    duplicate_contents = sum(
        count - 1 for count in exact_contents.values() if count > 1
    )
    if duplicate_ids:
        errors.append(f"发现 {duplicate_ids} 条重复 document_id")
    if duplicate_contents:
        errors.append(f"发现 {duplicate_contents} 条完全重复正文")

    kinds: Counter[str] = Counter()
    characters: Counter[str] = Counter()
    timelines: Counter[str] = Counter()
    channels: Counter[str] = Counter()
    dialogue_stats: Counter[str] = Counter()
    max_content_chars = 0
    for record in records:
        max_content_chars = max(max_content_chars, len(record.content))
        kind = str(record.metadata.get("record_kind", ""))
        kinds[kind] += 1
        characters[record.character_id] += 1
        timelines[record.timeline] += 1
        channels[str(record.metadata.get("retrieval_channel", ""))] += 1
        _audit_record(record, errors)
        if kind == "dialogue_example":
            _audit_dialogue(record, errors, dialogue_stats)

    manifest = _load_manifest(manifest_path, errors) if manifest_path else None
    if manifest is not None:
        _audit_manifest(
            manifest,
            record_count=len(records),
            corpus_version=corpus_version,
            kinds=kinds,
            max_content_chars=max_content_chars,
            errors=errors,
            warnings=warnings,
        )

    stats = {
        "records_by_kind": dict(sorted(kinds.items())),
        "records_by_character": dict(sorted(characters.items())),
        "records_by_timeline": dict(sorted(timelines.items())),
        "records_by_retrieval_channel": dict(sorted(channels.items())),
        "max_content_chars": max_content_chars,
        "duplicate_document_ids": duplicate_ids,
        "duplicate_contents": duplicate_contents,
        "dialogue": dict(sorted(dialogue_stats.items())),
    }
    return CorpusAuditReport(
        passed=not errors,
        corpusVersion=corpus_version,
        recordCount=len(records),
        errors=tuple(errors),
        warnings=tuple(warnings),
        stats=stats,
    )


def _audit_record(record: CorpusRecord, errors: list[str]) -> None:
    metadata = record.metadata
    document_id = record.document_id
    kind = str(metadata.get("record_kind", ""))
    profile = _ROUTING_PROFILES.get(kind)
    if profile is None:
        errors.append(f"{document_id} 的 record_kind 不受支持：{kind}")
        return
    if metadata.get("record_schema_version") != CORPUS_RECORD_SCHEMA_VERSION:
        errors.append(f"{document_id} 的记录 schema 版本不正确")
    if metadata.get("dataset_version") != metadata.get("corpus_version"):
        errors.append(f"{document_id} 的 dataset_version 与 corpus_version 不一致")
    if len(record.content) > MAX_RECORD_CONTENT_CHARS:
        errors.append(
            f"{document_id} 正文长度 {len(record.content)} 超过 "
            f"{MAX_RECORD_CONTENT_CHARS}"
        )
    first_line = record.content.splitlines()[0] if record.content else ""
    if not (
        first_line.startswith("作品：")
        and "资料类型：" in first_line
        and "角色：" in first_line
    ):
        errors.append(f"{document_id} 缺少规范的非台本说明头")
    for field, expected in profile.items():
        actual = metadata.get(field)
        if actual != expected:
            errors.append(
                f"{document_id} 的 {field} 应为 {expected}，实际为 {actual}"
            )
    if kind == "dialogue_example":
        for field in ("knowledge_owner", "subject_character_id"):
            if metadata.get(field) != record.character_id:
                errors.append(f"{document_id} 的 {field} 必须等于目标角色")
    if kind == "behavior_observation" and metadata.get(
        "subject_character_id"
    ) != record.character_id:
        errors.append(f"{document_id} 的被观察角色与检索角色不一致")


def _audit_dialogue(
    record: CorpusRecord,
    errors: list[str],
    stats: Counter[str],
) -> None:
    metadata = record.metadata
    document_id = record.document_id
    stats["records"] += 1
    if metadata.get("dialogue_schema_version") != "roleplay-dialogue-example.v2":
        errors.append(f"{document_id} 未使用结构化台词 v2")
    stimulus = metadata.get("stimulus_turns")
    response = metadata.get("response_turn")
    if not isinstance(stimulus, list) or not isinstance(response, Mapping):
        errors.append(f"{document_id} 的 stimulus_turns/response_turn 格式无效")
        return
    stats["stimulus_turns"] += len(stimulus)
    stats["max_stimulus_turns"] = max(stats["max_stimulus_turns"], len(stimulus))
    if len(stimulus) > 2:
        errors.append(f"{document_id} 的前置台词超过两轮")
    response_text = str(response.get("text", ""))
    response_speaker = str(response.get("speaker_id", ""))
    response_turn_index = _integer_or_none(response.get("turn_index"))
    response_paragraph = _integer_or_none(response.get("paragraph_index"))
    if response_speaker != record.character_id or response_speaker.startswith("npc:"):
        errors.append(f"{document_id} 的目标回答说话人不正确")
    if not response_text or metadata.get("target_text") != response_text:
        errors.append(f"{document_id} 的目标回答正文不完整或不一致")
    target_turn = metadata.get("target_turn")
    if not isinstance(target_turn, Mapping) or target_turn.get("text") != response_text:
        errors.append(f"{document_id} 的 target_turn 与 response_turn 不一致")
    marker = "【目标角色回答】\n"
    if marker not in record.content:
        errors.append(f"{document_id} 缺少目标回答分区")
    else:
        response_partition = record.content.split(marker, maxsplit=1)[1]
        expected_suffix = f"{response.get('speaker_label')}：{response_text}"
        if response_partition != expected_suffix:
            errors.append(f"{document_id} 的目标回答在正文中被截断或混入其他文本")

    previous_paragraph: int | None = None
    for turn in stimulus:
        if not isinstance(turn, Mapping):
            errors.append(f"{document_id} 存在无效前置台词")
            continue
        speaker = str(turn.get("speaker_id", ""))
        if not speaker or speaker in {"unknown", "__unknown__"}:
            errors.append(f"{document_id} 的前置台词包含未知说话人")
        turn_index = _integer_or_none(turn.get("turn_index"))
        paragraph = _integer_or_none(turn.get("paragraph_index"))
        if (
            turn_index is None
            or response_turn_index is None
            or turn_index >= response_turn_index
        ):
            errors.append(f"{document_id} 的前置台词位于目标回答之后")
        if (
            paragraph is None
            or response_paragraph is None
            or paragraph > response_paragraph
        ):
            errors.append(f"{document_id} 的前置台词段落位于目标回答之后")
        if previous_paragraph is not None and paragraph is not None:
            if paragraph - previous_paragraph > 5:
                errors.append(f"{document_id} 的同场景相邻台词间隔超过 5 段")
        previous_paragraph = paragraph
    if (
        previous_paragraph is not None
        and response_paragraph is not None
        and response_paragraph - previous_paragraph > 5
    ):
        errors.append(f"{document_id} 的目标回答与前置台词间隔超过 5 段")
    if metadata.get("scene_id") != metadata.get("dialogue_scene_id"):
        errors.append(f"{document_id} 的 scene_id 与 dialogue_scene_id 不一致")
    if metadata.get("conversation_id") != metadata.get("dialogue_scene_id"):
        errors.append(f"{document_id} 的 conversation_id 与 dialogue_scene_id 不一致")
    stats[f"review_method:{metadata.get('review_method')}"] += 1
    stats[f"review_certainty:{metadata.get('review_certainty')}"] += 1


def _load_manifest(path: Path, errors: list[str]) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"无法读取语料 manifest：{exc}")
        return None
    if not isinstance(value, Mapping):
        errors.append("语料 manifest 必须是对象")
        return None
    return value


def _audit_manifest(
    manifest: Mapping[str, Any],
    *,
    record_count: int,
    corpus_version: str | None,
    kinds: Counter[str],
    max_content_chars: int,
    errors: list[str],
    warnings: list[str],
) -> None:
    if manifest.get("corpus_version") != corpus_version:
        errors.append("manifest 的 corpus_version 与记录不一致")
    stats = manifest.get("stats")
    if not isinstance(stats, Mapping):
        errors.append("manifest 缺少 stats")
        return
    if stats.get("records") != record_count:
        errors.append("manifest 的记录总数与 JSONL 不一致")
    if stats.get("records_by_kind") != dict(sorted(kinds.items())):
        errors.append("manifest 的 records_by_kind 与 JSONL 不一致")
    if stats.get("max_content_chars") != max_content_chars:
        errors.append("manifest 的 max_content_chars 与 JSONL 不一致")
    dialogue_review = manifest.get("dialogue_review")
    if isinstance(dialogue_review, Mapping):
        if dialogue_review.get("luna_coverage") != 1.0:
            errors.append("Luna 逐条审阅覆盖率不是 100%")
        anomalies = dialogue_review.get("parse_anomaly_units")
        if isinstance(anomalies, int) and anomalies:
            warnings.append(f"{anomalies} 个引语单元有配对异常，已进入 Sol 复核")


def _integer_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
