"""为逐条 Agent 审阅导出小说引语候选，并校验结构化审阅结果。"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from haruhi_roleplay_api.corpus.haruhi import HARUHI_BOOKS, BookSpec
from haruhi_roleplay_api.corpus.pipeline import (
    DialogueAttribution,
    Paragraph,
    _attribute_dialogue,
    _clean_source_lines,
    _decode_source,
    _split_sections,
)


REVIEW_SCHEMA_VERSION = "dialogue-review-candidates.v1"
REVIEW_PROMPT_VERSION = "dialogue-review-prompt.v1"
TARGET_SPEAKER_IDS = frozenset({"haruhi", "kyon", "mikuru", "yuki", "itsuki"})
QUOTE_PAIRS = {"「": "」", "『": "』", "“": "”", "‘": "’"}
QUOTE_CLOSERS = frozenset(QUOTE_PAIRS.values())

REVIEW_FUNCTIONS = frozenset(
    {"speech", "thought", "written", "term", "title", "sound", "other", "unclear"}
)
REVIEW_SCOPES = frozenset(
    {
        "current_scene",
        "reported_or_recalled",
        "performed_or_scripted",
        "recorded_playback",
        "not_applicable",
        "unclear",
    }
)
REVIEW_CERTAINTIES = frozenset({"certain", "probable", "uncertain"})
REVIEW_EVIDENCE_TYPES = frozenset(
    {
        "explicit_same",
        "explicit_previous",
        "explicit_next",
        "explicit_cross",
        "pronoun",
        "turn_continuity",
        "response_pair",
        "scene_participants",
        "style_only",
        "none",
    }
)


@dataclass(frozen=True, kw_only=True)
class QuoteSpan:
    span_id: str
    start: int
    end: int
    text: str
    opener: str
    closer: str
    depth: int
    parent_span_id: str | None
    closed: bool

    def to_mapping(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "opener": self.opener,
            "closer": self.closer,
            "depth": self.depth,
            "parent_span_id": self.parent_span_id,
            "closed": self.closed,
        }


@dataclass(frozen=True, kw_only=True)
class DialogueReviewUnit:
    review_unit_id: str
    source: Mapping[str, Any]
    text: str
    context_before: tuple[Mapping[str, Any], ...]
    context_after: tuple[Mapping[str, Any], ...]
    spans: tuple[QuoteSpan, ...]
    parse_warnings: tuple[str, ...]
    automatic_attribution: Mapping[str, Any]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "review_unit_id": self.review_unit_id,
            "source": dict(self.source),
            "text": self.text,
            "context_before": [dict(item) for item in self.context_before],
            "context_after": [dict(item) for item in self.context_after],
            "spans": [span.to_mapping() for span in self.spans],
            "parse_warnings": list(self.parse_warnings),
            "automatic_attribution": dict(self.automatic_attribution),
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DialogueReviewUnit":
        if data.get("schema_version") != REVIEW_SCHEMA_VERSION:
            raise ValueError("引语候选 schema_version 不受支持")
        source = data.get("source")
        if not isinstance(source, Mapping):
            raise ValueError("引语候选 source 必须是对象")
        spans_data = data.get("spans")
        if not isinstance(spans_data, list):
            raise ValueError("引语候选 spans 必须是数组")
        spans: list[QuoteSpan] = []
        for raw_span in spans_data:
            if not isinstance(raw_span, Mapping):
                raise ValueError("引语 span 必须是对象")
            spans.append(
                QuoteSpan(
                    span_id=str(raw_span["span_id"]),
                    start=int(raw_span["start"]),
                    end=int(raw_span["end"]),
                    text=str(raw_span["text"]),
                    opener=str(raw_span["opener"]),
                    closer=str(raw_span["closer"]),
                    depth=int(raw_span["depth"]),
                    parent_span_id=(
                        str(raw_span["parent_span_id"])
                        if raw_span.get("parent_span_id") is not None
                        else None
                    ),
                    closed=bool(raw_span["closed"]),
                )
            )
        before = _mapping_sequence(data.get("context_before"), "context_before")
        after = _mapping_sequence(data.get("context_after"), "context_after")
        automatic = data.get("automatic_attribution", {})
        if not isinstance(automatic, Mapping):
            raise ValueError("automatic_attribution 必须是对象")
        warnings = data.get("parse_warnings", [])
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            raise ValueError("parse_warnings 必须是字符串数组")
        unit = cls(
            review_unit_id=str(data["review_unit_id"]),
            source=dict(source),
            text=str(data["text"]),
            context_before=before,
            context_after=after,
            spans=tuple(spans),
            parse_warnings=tuple(warnings),
            automatic_attribution=dict(automatic),
        )
        validate_review_unit(unit)
        return unit


@dataclass(frozen=True, kw_only=True)
class DialogueReviewExportResult:
    candidates_path: Path
    manifest_path: Path
    unit_count: int
    span_count: int
    stats: Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class ReviewAnnotation:
    span_id: str
    function: str
    scope: str
    speaker: str
    word_owner: str
    certainty: str
    evidence: tuple[str, ...]
    rationale: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "function": self.function,
            "scope": self.scope,
            "speaker": self.speaker,
            "word_owner": self.word_owner,
            "certainty": self.certainty,
            "evidence": list(self.evidence),
            "rationale": self.rationale,
        }


@dataclass(frozen=True, kw_only=True)
class ReviewedSpan:
    annotation: ReviewAnnotation
    batch_id: str
    model: str
    model_reasoning_effort: str
    prompt_version: str


@dataclass(frozen=True, kw_only=True)
class DialogueReviewIndex:
    spans: Mapping[str, ReviewedSpan]
    expected_span_count: int
    missing_span_ids: tuple[str, ...]
    stats: Mapping[str, Any]

    @property
    def complete(self) -> bool:
        return not self.missing_span_ids


def export_dialogue_review_candidates(
    source_dir: Path,
    output_dir: Path,
    *,
    context_radius: int = 3,
    context_max_chars: int = 260,
) -> DialogueReviewExportResult:
    """导出所有带成对或异常引号的正文段落，供模型逐 span 审阅。"""

    if context_radius < 0:
        raise ValueError("context_radius 不能小于 0")
    if context_max_chars < 40:
        raise ValueError("context_max_chars 不能小于 40")
    source_dir = source_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    units: list[DialogueReviewUnit] = []
    sources: list[dict[str, Any]] = []
    stats: Counter[str] = Counter()
    by_book_units: Counter[str] = Counter()
    by_book_spans: Counter[str] = Counter()

    for book in HARUHI_BOOKS:
        source_path = source_dir / book.filename
        if not source_path.is_file():
            raise FileNotFoundError(f"缺少小说源文件：{source_path}")
        raw_bytes = source_path.read_bytes()
        source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        sections = _split_sections(book, _clean_source_lines(_decode_source(raw_bytes)))
        sources.append(
            {
                "book_id": book.book_id,
                "volume": book.volume,
                "filename": book.filename,
                "sha256": source_sha256,
                "bytes": len(raw_bytes),
                "sections": len(sections),
            }
        )
        for section in sections:
            attributions = _attribute_dialogue(section.paragraphs)
            for paragraph_index, paragraph in enumerate(section.paragraphs):
                if not _contains_quote_marker(paragraph.text):
                    continue
                unit = _review_unit(
                    book=book,
                    section=section,
                    source_sha256=source_sha256,
                    paragraph_index=paragraph_index,
                    paragraph=paragraph,
                    attribution=attributions.get(paragraph_index),
                    context_radius=context_radius,
                    context_max_chars=context_max_chars,
                )
                units.append(unit)
                stats["units"] += 1
                stats["spans"] += len(unit.spans)
                stats["unclosed_spans"] += sum(not span.closed for span in unit.spans)
                stats["parse_warning_units"] += bool(unit.parse_warnings)
                stats["candidate_text_characters"] += len(unit.text)
                stats["context_characters"] += sum(
                    len(str(item["text"]))
                    for item in (*unit.context_before, *unit.context_after)
                )
                by_book_units[book.book_id] += 1
                by_book_spans[book.book_id] += len(unit.spans)

    units.sort(
        key=lambda item: (
            int(item.source["volume"]),
            int(item.source["section_index"]),
            int(item.source["line"]),
        )
    )
    candidates_path = output_dir / "dialogue_candidates.jsonl"
    with candidates_path.open("w", encoding="utf-8", newline="\n") as handle:
        for unit in units:
            handle.write(json.dumps(unit.to_mapping(), ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    ids = [span.span_id for unit in units for span in unit.spans]
    if len(ids) != len(set(ids)):
        raise ValueError("引语候选 span_id 不唯一")
    final_stats = {
        **dict(stats),
        "books": len(sources),
        "units_by_book": dict(sorted(by_book_units.items())),
        "spans_by_book": dict(sorted(by_book_spans.items())),
    }
    manifest = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "prompt_version": REVIEW_PROMPT_VERSION,
        "source_policy": {
            "generated_output": "本地 .data 目录；不要提交或再分发源文本衍生数据"
        },
        "settings": {
            "context_radius": context_radius,
            "context_max_chars": context_max_chars,
            "quote_pairs": QUOTE_PAIRS,
        },
        "sources": sources,
        "stats": final_stats,
        "candidates_sha256": hashlib.sha256(candidates_path.read_bytes()).hexdigest(),
    }
    manifest_path = output_dir / "dialogue_candidates.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return DialogueReviewExportResult(
        candidates_path=candidates_path,
        manifest_path=manifest_path,
        unit_count=len(units),
        span_count=len(ids),
        stats=final_stats,
    )


def load_dialogue_review_units(path: Path) -> tuple[DialogueReviewUnit, ...]:
    units: list[DialogueReviewUnit] = []
    with path.expanduser().open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"引语候选 JSONL 第 {line_number} 行无法解析") from exc
            if not isinstance(data, Mapping):
                raise ValueError(f"引语候选 JSONL 第 {line_number} 行必须是对象")
            units.append(DialogueReviewUnit.from_mapping(data))
    if not units:
        raise ValueError(f"引语候选文件为空：{path}")
    unit_ids = [unit.review_unit_id for unit in units]
    span_ids = [span.span_id for unit in units for span in unit.spans]
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("引语候选 review_unit_id 不唯一")
    if len(span_ids) != len(set(span_ids)):
        raise ValueError("引语候选 span_id 不唯一")
    return tuple(units)


def load_dialogue_review_index(
    review_dir: Path,
    *,
    units: Sequence[DialogueReviewUnit],
    require_complete: bool = False,
) -> DialogueReviewIndex:
    """读取批次结果，并对候选全集做重复、越界和覆盖校验。"""

    expected_ids = tuple(span.span_id for unit in units for span in unit.spans)
    expected_set = set(expected_ids)
    reviewed: dict[str, ReviewedSpan] = {}
    batch_dir = review_dir.expanduser().resolve() / "batches"
    if not batch_dir.is_dir():
        raise FileNotFoundError(f"审阅批次目录不存在：{batch_dir}")
    for path in sorted(batch_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError(f"审阅批次必须是对象：{path}")
        raw_annotations = data.get("annotations")
        if not isinstance(raw_annotations, list):
            raise ValueError(f"审阅批次缺少 annotations：{path}")
        batch_span_ids = tuple(
            str(item.get("span_id", ""))
            for item in raw_annotations
            if isinstance(item, Mapping)
        )
        annotations = parse_review_annotations(data, expected_span_ids=batch_span_ids)
        for annotation in annotations:
            if annotation.span_id not in expected_set:
                raise ValueError(f"审阅批次包含候选集之外的 span：{annotation.span_id}")
            if annotation.span_id in reviewed:
                raise ValueError(f"同一审阅目录重复覆盖 span：{annotation.span_id}")
            reviewed[annotation.span_id] = ReviewedSpan(
                annotation=annotation,
                batch_id=str(data.get("batch_id", path.stem)),
                model=str(data.get("model", "unknown")),
                model_reasoning_effort=str(
                    data.get("model_reasoning_effort", "unknown")
                ),
                prompt_version=str(data.get("prompt_version", "unknown")),
            )
    missing = tuple(span_id for span_id in expected_ids if span_id not in reviewed)
    if require_complete and missing:
        raise ValueError(f"审阅结果不完整，仍缺少 {len(missing)} 个 span")
    function_counts = Counter(
        reviewed_span.annotation.function for reviewed_span in reviewed.values()
    )
    scope_counts = Counter(
        reviewed_span.annotation.scope for reviewed_span in reviewed.values()
    )
    certainty_counts = Counter(
        reviewed_span.annotation.certainty for reviewed_span in reviewed.values()
    )
    speaker_counts = Counter(
        reviewed_span.annotation.speaker for reviewed_span in reviewed.values()
    )
    target_current_scene = sum(
        reviewed_span.annotation.function == "speech"
        and reviewed_span.annotation.scope == "current_scene"
        and reviewed_span.annotation.speaker in TARGET_SPEAKER_IDS
        for reviewed_span in reviewed.values()
    )
    stats = {
        "expected_spans": len(expected_ids),
        "reviewed_spans": len(reviewed),
        "missing_spans": len(missing),
        "coverage": round(len(reviewed) / len(expected_ids), 6) if expected_ids else 1.0,
        "target_current_scene_spans": target_current_scene,
        "by_function": dict(sorted(function_counts.items())),
        "by_scope": dict(sorted(scope_counts.items())),
        "by_certainty": dict(sorted(certainty_counts.items())),
        "by_speaker": dict(sorted(speaker_counts.items())),
    }
    return DialogueReviewIndex(
        spans=reviewed,
        expected_span_count=len(expected_ids),
        missing_span_ids=missing,
        stats=stats,
    )


def validate_review_unit(unit: DialogueReviewUnit) -> None:
    source_text_hash = hashlib.sha256(unit.text.encode("utf-8")).hexdigest()
    if unit.source.get("text_sha256") != source_text_hash:
        raise ValueError(f"审阅单元 {unit.review_unit_id} 的正文指纹不匹配")
    span_ids = {span.span_id for span in unit.spans}
    for span in unit.spans:
        if span.start < 0 or span.end <= span.start or span.end > len(unit.text):
            raise ValueError(f"span {span.span_id} 的字符范围越界")
        if unit.text[span.start : span.end] != span.text:
            raise ValueError(f"span {span.span_id} 的文本与字符范围不一致")
        if span.parent_span_id is not None and span.parent_span_id not in span_ids:
            raise ValueError(f"span {span.span_id} 引用了不存在的父 span")
    for left_index, left in enumerate(unit.spans):
        for right in unit.spans[left_index + 1 :]:
            overlaps = left.start < right.end and right.start < left.end
            nested = (
                left.start <= right.start and right.end <= left.end
            ) or (
                right.start <= left.start and left.end <= right.end
            )
            if overlaps and not nested:
                raise ValueError(f"span {left.span_id} 与 {right.span_id} 发生交叉")


def parse_review_annotations(
    data: Mapping[str, Any],
    *,
    expected_span_ids: Iterable[str],
) -> tuple[ReviewAnnotation, ...]:
    raw_annotations = data.get("annotations")
    if not isinstance(raw_annotations, list):
        raise ValueError("Luna 输出 annotations 必须是数组")
    expected = tuple(expected_span_ids)
    expected_set = set(expected)
    annotations: list[ReviewAnnotation] = []
    for raw in raw_annotations:
        if not isinstance(raw, Mapping):
            raise ValueError("Luna 输出中的 annotation 必须是对象")
        evidence = raw.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("每条审阅必须至少提供一个 evidence")
        annotation = ReviewAnnotation(
            span_id=str(raw.get("span_id", "")),
            function=str(raw.get("function", "")),
            scope=str(raw.get("scope", "")),
            speaker=str(raw.get("speaker", "")),
            word_owner=str(raw.get("word_owner", "")),
            certainty=str(raw.get("certainty", "")),
            evidence=tuple(str(item) for item in evidence),
            rationale=str(raw.get("rationale", "")).strip(),
        )
        _validate_review_annotation(annotation)
        annotations.append(annotation)
    actual = [annotation.span_id for annotation in annotations]
    if len(actual) != len(set(actual)):
        raise ValueError("Luna 输出包含重复 span_id")
    if set(actual) != expected_set:
        missing = sorted(expected_set - set(actual))
        unexpected = sorted(set(actual) - expected_set)
        raise ValueError(
            f"Luna 输出 span 不完整：缺少 {missing[:5]}，多出 {unexpected[:5]}"
        )
    order = {span_id: index for index, span_id in enumerate(expected)}
    return tuple(sorted(annotations, key=lambda item: order[item.span_id]))


def normalize_review_output(
    data: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """只修正规则可唯一确定的跨字段问题，不改动说话人语义判断。"""

    normalized = dict(data)
    raw_annotations = data.get("annotations")
    if not isinstance(raw_annotations, list):
        return normalized, ()
    annotations: list[Any] = []
    changes: list[str] = []
    weak_evidence = {"style_only", "scene_participants", "none"}
    for raw in raw_annotations:
        if not isinstance(raw, Mapping):
            annotations.append(raw)
            continue
        item = dict(raw)
        span_id = str(item.get("span_id", "未知 span"))
        evidence = item.get("evidence")
        if isinstance(evidence, list):
            deduplicated = list(dict.fromkeys(evidence))
            if deduplicated != evidence:
                item["evidence"] = deduplicated
                changes.append(f"{span_id}: evidence 去重")
            evidence_set = set(str(value) for value in deduplicated)
        else:
            evidence_set = set()
        if item.get("function") != "speech":
            speaker = str(item.get("speaker", ""))
            owner = str(item.get("word_owner", ""))
            if speaker not in {"", "none"}:
                if owner in {"", "same", "none", "unknown"}:
                    item["word_owner"] = speaker
                    changes.append(f"{span_id}: 非台词主体移入 word_owner")
                item["speaker"] = "none"
                changes.append(f"{span_id}: 非台词 speaker 置为 none")
            if item.get("scope") != "not_applicable":
                item["scope"] = "not_applicable"
                changes.append(f"{span_id}: 非台词 scope 置为 not_applicable")
        if item.get("speaker") == "none" and item.get("word_owner") == "same":
            item["word_owner"] = "unknown"
            changes.append(f"{span_id}: 无发声者的 word_owner 改为 unknown")
        for field in ("speaker", "word_owner"):
            value = str(item.get(field, "")).strip()
            normalized_speaker = _normalized_speaker_value(value, allow_same=field == "word_owner")
            if normalized_speaker != value:
                item[field] = normalized_speaker
                changes.append(f"{span_id}: {field} 规范为 {normalized_speaker}")
        if item.get("certainty") == "certain" and evidence_set <= weak_evidence:
            item["certainty"] = "probable"
            changes.append(f"{span_id}: 弱证据 certain 降为 probable")
        annotations.append(item)
    normalized["annotations"] = annotations
    return normalized, tuple(changes)


def _normalized_speaker_value(value: str, *, allow_same: bool) -> str:
    target_names = {
        "凉宫春日": "haruhi",
        "涼宮春日": "haruhi",
        "春日": "haruhi",
        "阿虚": "kyon",
        "阿虛": "kyon",
        "朝比奈实玖瑠": "mikuru",
        "朝比奈實玖瑠": "mikuru",
        "朝比奈": "mikuru",
        "实玖瑠": "mikuru",
        "實玖瑠": "mikuru",
        "长门有希": "yuki",
        "長門有希": "yuki",
        "长门": "yuki",
        "長門": "yuki",
        "古泉一树": "itsuki",
        "古泉一樹": "itsuki",
        "古泉": "itsuki",
    }
    if value in target_names:
        return target_names[value]
    allowed = TARGET_SPEAKER_IDS | {"unknown", "none"}
    if allow_same:
        allowed = allowed | {"same"}
    if value in allowed or value.startswith(("npc:", "group:")):
        return value
    if value:
        return f"npc:{value}"
    return value


def compact_review_units(
    units: Sequence[DialogueReviewUnit],
    *,
    span_aliases: Mapping[str, str] | None = None,
    unit_aliases: Mapping[str, str] | None = None,
    prior_reviews: Mapping[str, ReviewAnnotation] | None = None,
) -> list[dict[str, Any]]:
    """生成发送给模型的紧凑结构，省略可由本地校验恢复的字段。"""

    compact: list[dict[str, Any]] = []
    for unit in units:
        compact.append(
            {
                "unit_id": (
                    unit_aliases.get(unit.review_unit_id, unit.review_unit_id)
                    if unit_aliases is not None
                    else unit.review_unit_id
                ),
                "book": unit.source["book_title"],
                "section": unit.source["section_title"],
                "line": unit.source["line"],
                "before": [dict(item) for item in unit.context_before],
                "text": unit.text,
                "after": [dict(item) for item in unit.context_after],
                "spans": [
                    {
                        "span_id": (
                            span_aliases.get(span.span_id, span.span_id)
                            if span_aliases is not None
                            else span.span_id
                        ),
                        "text": span.text,
                        "depth": span.depth,
                        "parent_span_id": (
                            span_aliases.get(span.parent_span_id, span.parent_span_id)
                            if span_aliases is not None and span.parent_span_id is not None
                            else span.parent_span_id
                        ),
                        "closed": span.closed,
                        **(
                            {
                                "prior": {
                                    "function": prior_reviews[span.span_id].function,
                                    "scope": prior_reviews[span.span_id].scope,
                                    "speaker": prior_reviews[span.span_id].speaker,
                                    "word_owner": prior_reviews[span.span_id].word_owner,
                                    "certainty": prior_reviews[span.span_id].certainty,
                                    "evidence": list(prior_reviews[span.span_id].evidence),
                                }
                            }
                            if prior_reviews is not None and span.span_id in prior_reviews
                            else {}
                        ),
                    }
                    for span in unit.spans
                ],
                "auto": dict(unit.automatic_attribution),
                "warnings": list(unit.parse_warnings),
            }
        )
    return compact


def _review_unit(
    *,
    book: BookSpec,
    section: Any,
    source_sha256: str,
    paragraph_index: int,
    paragraph: Paragraph,
    attribution: DialogueAttribution | None,
    context_radius: int,
    context_max_chars: int,
) -> DialogueReviewUnit:
    text_sha256 = hashlib.sha256(paragraph.text.encode("utf-8")).hexdigest()
    unit_digest = hashlib.blake2b(
        (
            f"{source_sha256}\0{section.index}\0{paragraph.line_number}\0"
            f"{text_sha256}"
        ).encode("utf-8"),
        digest_size=10,
    ).hexdigest()
    review_unit_id = (
        f"{book.book_id}-s{section.index:02d}-l{paragraph.line_number}-{unit_digest}"
    )
    spans, warnings = _quote_spans(
        paragraph.text,
        unit_prefix=review_unit_id,
    )
    before_start = max(0, paragraph_index - context_radius)
    before = tuple(
        _context_line(item, context_max_chars)
        for item in section.paragraphs[before_start:paragraph_index]
    )
    after = tuple(
        _context_line(item, context_max_chars)
        for item in section.paragraphs[
            paragraph_index + 1 : paragraph_index + context_radius + 1
        ]
    )
    automatic = {
        "speaker_id": attribution.speaker_id if attribution else None,
        "confidence": attribution.confidence if attribution else 0.0,
        "reason": attribution.reason if attribution else "not_evaluated",
    }
    return DialogueReviewUnit(
        review_unit_id=review_unit_id,
        source={
            "book_id": book.book_id,
            "volume": book.volume,
            "book_title": book.title,
            "section_index": section.index,
            "section_title": section.spec.title,
            "timeline": section.spec.timeline,
            "spoiler_level": section.spec.spoiler_level,
            "branch": section.spec.branch,
            "source_filename": book.filename,
            "source_sha256": source_sha256,
            "line": paragraph.line_number,
            "paragraph_index": paragraph_index,
            "text_sha256": text_sha256,
        },
        text=paragraph.text,
        context_before=before,
        context_after=after,
        spans=spans,
        parse_warnings=warnings,
        automatic_attribution=automatic,
    )


def _quote_spans(
    text: str,
    *,
    unit_prefix: str,
) -> tuple[tuple[QuoteSpan, ...], tuple[str, ...]]:
    open_stack: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    warnings: list[str] = []
    token_counter = 0
    for index, character in enumerate(text):
        if character in QUOTE_PAIRS:
            token_counter += 1
            open_stack.append(
                {
                    "token": token_counter,
                    "start": index,
                    "opener": character,
                    "closer": QUOTE_PAIRS[character],
                    "depth": len(open_stack),
                    "parent_token": open_stack[-1]["token"] if open_stack else None,
                }
            )
            continue
        if character not in QUOTE_CLOSERS:
            continue
        if open_stack and open_stack[-1]["closer"] == character:
            opened = open_stack.pop()
            completed.append({**opened, "end": index + 1, "closed": True})
            continue
        warnings.append(f"位置 {index} 出现无法配对的闭引号 {character}")
    for opened in open_stack:
        completed.append({**opened, "end": len(text), "closed": False})
        warnings.append(f"位置 {opened['start']} 的开引号 {opened['opener']} 未闭合")

    token_to_id: dict[int, str] = {}
    for item in completed:
        span_text = text[int(item["start"]) : int(item["end"])]
        digest = hashlib.blake2b(
            (
                f"{unit_prefix}\0{item['start']}\0{item['end']}\0{span_text}"
            ).encode("utf-8"),
            digest_size=8,
        ).hexdigest()
        token_to_id[int(item["token"])] = (
            f"{unit_prefix}-q{int(item['start'])}-{int(item['end'])}-{digest}"
        )
    spans = tuple(
        QuoteSpan(
            span_id=token_to_id[int(item["token"])],
            start=int(item["start"]),
            end=int(item["end"]),
            text=text[int(item["start"]) : int(item["end"])],
            opener=str(item["opener"]),
            closer=str(item["closer"]),
            depth=int(item["depth"]),
            parent_span_id=(
                token_to_id.get(int(item["parent_token"]))
                if item["parent_token"] is not None
                else None
            ),
            closed=bool(item["closed"]),
        )
        for item in sorted(completed, key=lambda value: (value["start"], -value["end"]))
    )
    return spans, tuple(warnings)


def _validate_review_annotation(annotation: ReviewAnnotation) -> None:
    if not annotation.span_id:
        raise ValueError("审阅结果缺少 span_id")
    if annotation.function not in REVIEW_FUNCTIONS:
        raise ValueError(f"未知引语 function：{annotation.function}")
    if annotation.scope not in REVIEW_SCOPES:
        raise ValueError(f"未知引语 scope：{annotation.scope}")
    if annotation.certainty not in REVIEW_CERTAINTIES:
        raise ValueError(f"未知 certainty：{annotation.certainty}")
    if not annotation.evidence or any(
        evidence not in REVIEW_EVIDENCE_TYPES for evidence in annotation.evidence
    ):
        raise ValueError(f"未知或空 evidence：{annotation.evidence}")
    _validate_speaker_value(annotation.speaker, field="speaker")
    _validate_speaker_value(annotation.word_owner, field="word_owner", allow_same=True)
    if annotation.function == "speech":
        if annotation.scope == "not_applicable":
            raise ValueError("speech 的 scope 不能是 not_applicable")
    elif annotation.scope != "not_applicable":
        raise ValueError(f"非 speech 的 scope 必须是 not_applicable：{annotation.span_id}")
    elif annotation.speaker != "none":
        raise ValueError(f"非 speech 的 speaker 必须是 none：{annotation.span_id}")
    if annotation.speaker == "none" and annotation.word_owner == "same":
        raise ValueError(f"speaker 为 none 时 word_owner 不能是 same：{annotation.span_id}")
    if len(annotation.evidence) != len(set(annotation.evidence)):
        raise ValueError(f"evidence 不能重复：{annotation.span_id}")
    if annotation.certainty == "certain" and set(annotation.evidence) <= {
        "style_only",
        "scene_participants",
        "none",
    }:
        raise ValueError("certain 不能只依据风格、在场人物或无证据")
    if len(annotation.rationale) > 80:
        raise ValueError("rationale 不能超过 80 个字符")


def _validate_speaker_value(value: str, *, field: str, allow_same: bool = False) -> None:
    allowed_literals = TARGET_SPEAKER_IDS | {"unknown", "none"}
    if allow_same:
        allowed_literals = allowed_literals | {"same"}
    if value in allowed_literals:
        return
    if value.startswith(("npc:", "group:")) and value.split(":", 1)[1].strip():
        return
    raise ValueError(f"{field} 的说话人值不合法：{value}")


def _contains_quote_marker(text: str) -> bool:
    return any(character in QUOTE_PAIRS or character in QUOTE_CLOSERS for character in text)


def _context_line(paragraph: Paragraph, max_chars: int) -> dict[str, Any]:
    text = paragraph.text
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return {"line": paragraph.line_number, "text": text}


def _mapping_sequence(value: Any, field: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"{field} 必须是对象数组")
    return tuple(dict(item) for item in value)
