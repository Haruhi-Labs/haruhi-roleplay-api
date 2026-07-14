"""把 Luna/Sol 逐条审阅结果覆盖到可检索的角色台本语料。"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from haruhi_roleplay_api.corpus.dialogue_review import (
    DialogueReviewIndex,
    DialogueReviewUnit,
    QuoteSpan,
    ReviewedSpan,
    TARGET_SPEAKER_IDS,
    load_dialogue_review_index,
    load_dialogue_review_units,
)
from haruhi_roleplay_api.corpus.haruhi import CHARACTER_DISPLAY_NAMES
from haruhi_roleplay_api.corpus.pipeline import (
    MAX_RECORD_CONTENT_CHARS,
    PIPELINE_VERSION,
    CorpusRecord,
    SimplifiedChineseConverter,
    finalize_corpus_records,
    load_corpus_records,
)


REVIEWED_PIPELINE_VERSION = f"{PIPELINE_VERSION}+agent-review.v2"
DIALOGUE_SCHEMA_VERSION = "roleplay-dialogue-example.v2"
MAX_DIALOGUE_PARAGRAPH_GAP = 5
MAX_DIALOGUE_STIMULUS_TURNS = 2
_POST_DISAPPEARANCE_PERSONA_MODES: dict[str, tuple[str, ...]] = {
    "haruhi": ("mid_late_haruhi", "surprise_haruhi"),
    "mikuru": ("default_mikuru", "surprise_mikuru"),
    "yuki": ("default_yuki", "surprise_yuki"),
    "itsuki": ("default_itsuki", "surprise_itsuki"),
}


@dataclass(frozen=True, kw_only=True)
class DialogueOverlayResult:
    records_path: Path
    manifest_path: Path
    record_count: int
    dialogue_record_count: int
    review_stats: Mapping[str, Any]


def apply_reviewed_dialogue_overlay(
    corpus_dir: Path,
    *,
    candidates_path: Path,
    luna_review_dir: Path,
    adjudication_review_dir: Path | None = None,
    converter: Callable[[str], str] | None = None,
) -> DialogueOverlayResult:
    """移除旧的自动台词记录，写入完整 Agent 审阅版台词。"""

    corpus_dir = corpus_dir.expanduser().resolve()
    records_path = corpus_dir / "records.jsonl"
    manifest_path = corpus_dir / "manifest.json"
    base_records = load_corpus_records(records_path)
    units = load_dialogue_review_units(candidates_path)
    luna = load_dialogue_review_index(
        luna_review_dir,
        units=units,
        require_complete=True,
    )
    adjudication = (
        load_dialogue_review_index(
            adjudication_review_dir,
            units=units,
            require_complete=False,
        )
        if adjudication_review_dir is not None
        else None
    )
    final_spans = merge_review_spans(luna, adjudication)
    reviewed_records = build_reviewed_dialogue_records(
        units,
        final_spans,
        converter=converter or SimplifiedChineseConverter(),
    )
    records = [
        record
        for record in base_records
        if record.metadata.get("record_kind") != "dialogue_example"
    ]
    records.extend(reviewed_records)
    records.sort(
        key=lambda record: (
            int(record.metadata.get("volume", 0)),
            int(record.metadata.get("section_index", 0)),
            int(record.metadata.get("source_line", record.metadata.get("source_line_start", 0))),
            record.character_id,
            str(record.metadata.get("record_kind", "")),
            record.document_id,
        )
    )
    records, corpus_version = finalize_corpus_records(
        records,
        pipeline_version=REVIEWED_PIPELINE_VERSION,
    )
    with records_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record.to_mapping(), ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    review_stats = _review_stats(
        units=units,
        luna=luna,
        adjudication=adjudication,
        final_spans=final_spans,
        dialogue_records=reviewed_records,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("语料 manifest 必须是对象")
    by_character = Counter(record.character_id for record in records)
    by_kind = Counter(str(record.metadata.get("record_kind")) for record in records)
    by_timeline = Counter(record.timeline for record in records)
    stats = dict(manifest.get("stats", {}))
    stats.update(
        {
            "records": len(records),
            "records_by_character": dict(sorted(by_character.items())),
            "records_by_kind": dict(sorted(by_kind.items())),
            "records_by_timeline": dict(sorted(by_timeline.items())),
            "quotes_total": luna.expected_span_count,
            "quotes_attributed_target": len(reviewed_records),
            "quotes_unattributed_or_nontarget": (
                luna.expected_span_count - len(reviewed_records)
            ),
            "quote_target_attribution_rate": round(
                len(reviewed_records) / luna.expected_span_count,
                6,
            ),
            "quotes_high_confidence": sum(
                record.metadata.get("review_certainty") == "certain"
                for record in reviewed_records
            ),
            "quotes_medium_confidence": sum(
                record.metadata.get("review_certainty") == "probable"
                for record in reviewed_records
            ),
            "max_content_chars": max((len(record.content) for record in records), default=0),
        }
    )
    manifest["pipeline_version"] = REVIEWED_PIPELINE_VERSION
    manifest["schema_version"] = 2
    manifest["record_schema_version"] = "haruhi-rag-record.v2"
    manifest["corpus_version"] = corpus_version
    manifest["stats"] = stats
    manifest["dialogue_review"] = review_stats
    quality = manifest.setdefault("quality", {})
    warnings = [
        warning
        for warning in quality.get("warnings", [])
        if "台词归因率" not in str(warning)
    ]
    if review_stats["parse_anomaly_units"]:
        warnings.append(
            f"{review_stats['parse_anomaly_units']} 个引语单元存在配对异常，已纳入 Sol 复核"
        )
    quality["warnings"] = warnings
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return DialogueOverlayResult(
        records_path=records_path,
        manifest_path=manifest_path,
        record_count=len(records),
        dialogue_record_count=len(reviewed_records),
        review_stats=review_stats,
    )


def merge_review_spans(
    luna: DialogueReviewIndex,
    adjudication: DialogueReviewIndex | None,
) -> dict[str, ReviewedSpan]:
    merged = dict(luna.spans)
    if adjudication is not None:
        merged.update(adjudication.spans)
    return merged


def build_reviewed_dialogue_records(
    units: Sequence[DialogueReviewUnit],
    reviewed_spans: Mapping[str, ReviewedSpan],
    *,
    converter: Callable[[str], str],
) -> list[CorpusRecord]:
    """只把目标角色当前场景真实发言生成台本记录。"""

    section_speech: dict[tuple[str, int], list[tuple[DialogueReviewUnit, QuoteSpan, ReviewedSpan]]] = defaultdict(list)
    for unit in units:
        section_key = (str(unit.source["book_id"]), int(unit.source["section_index"]))
        for span in unit.spans:
            reviewed = reviewed_spans.get(span.span_id)
            if reviewed is None or span.depth != 0 or not span.closed:
                continue
            annotation = reviewed.annotation
            if annotation.function != "speech" or annotation.scope != "current_scene":
                continue
            section_speech[section_key].append((unit, span, reviewed))
    for values in section_speech.values():
        values.sort(
            key=lambda item: (
                int(item[0].source["paragraph_index"]),
                item[1].start,
            )
        )

    records: list[CorpusRecord] = []
    for section_key, speech in section_speech.items():
        conversations = _split_dialogue_conversations(speech)
        for conversation_index, conversation in enumerate(conversations, start=1):
            conversation_id = _conversation_id(
                section_key,
                speech=conversation,
            )
            for position, (unit, span, reviewed) in enumerate(conversation):
                annotation = reviewed.annotation
                if (
                    annotation.speaker not in TARGET_SPEAKER_IDS
                    or annotation.certainty not in {"certain", "probable"}
                ):
                    continue
                stimulus = _stimulus_turns(
                    conversation,
                    position=position,
                    reviewed_spans=reviewed_spans,
                    converter=converter,
                )
                target_text = converter(
                    _sanitize_nested_quotes(unit, span, reviewed_spans)
                )
                target_turn = _dialogue_turn_mapping(
                    unit,
                    span,
                    speaker=annotation.speaker,
                    text=target_text,
                    turn_index=position,
                    certainty=annotation.certainty,
                )
                context_speakers = list(
                    dict.fromkeys(
                        [
                            *(str(turn["speaker_id"]) for turn in stimulus),
                            annotation.speaker,
                        ]
                    )
                )
                character_id = annotation.speaker
                header = (
                    f"作品：{unit.source['book_title']}；"
                    f"篇章：{converter(str(unit.source['section_title']))}；"
                    f"资料类型：Agent逐条审阅角色台词；"
                    f"角色：{CHARACTER_DISPLAY_NAMES[character_id]}。"
                )
                content = _render_dialogue_content(
                    header=header,
                    stimulus=stimulus,
                    target_turn=target_turn,
                )
                digest = hashlib.blake2b(
                    span.span_id.encode("utf-8"), digest_size=10
                ).hexdigest()
                document_id = (
                    f"haruhi-reviewed-{unit.source['book_id']}-"
                    f"s{int(unit.source['section_index']):02d}-{digest}"
                )
                confidence = (
                    0.99
                    if annotation.certainty == "certain" and "sol" in reviewed.model
                    else 0.97
                    if annotation.certainty == "certain"
                    else 0.9
                )
                metadata: dict[str, Any] = {
                    "corpus": "haruhi-novels",
                    "pipeline_version": REVIEWED_PIPELINE_VERSION,
                    "record_kind": "dialogue_example",
                    "dialogue_schema_version": DIALOGUE_SCHEMA_VERSION,
                    "perspective": "spoken_by_character",
                    "confidence": confidence,
                    "book_id": unit.source["book_id"],
                    "volume": unit.source["volume"],
                    "book_title": unit.source["book_title"],
                    "section_index": unit.source["section_index"],
                    "section_title": converter(str(unit.source["section_title"])),
                    "branch": unit.source.get("branch"),
                    "source_filename": unit.source["source_filename"],
                    "source_line": unit.source["line"],
                    "source_char_start": span.start,
                    "source_char_end": span.end,
                    "span_id": span.span_id,
                    "review_method": (
                        "sol_adjudication"
                        if "sol" in reviewed.model
                        else "luna_first_pass"
                    ),
                    "review_model": reviewed.model,
                    "review_batch_id": reviewed.batch_id,
                    "review_prompt_version": reviewed.prompt_version,
                    "review_certainty": annotation.certainty,
                    "review_evidence": list(annotation.evidence),
                    "review_rationale": annotation.rationale,
                    "word_owner": annotation.word_owner,
                    "context_speakers": context_speakers,
                    "conversation_id": conversation_id,
                    "scene_id": conversation_id,
                    "dialogue_scene_id": conversation_id,
                    "scene_break_reason": (
                        "section_start"
                        if conversation_index == 1
                        else "paragraph_gap"
                    ),
                    "scene_start_paragraph_index": int(
                        conversation[0][0].source["paragraph_index"]
                    ),
                    "scene_end_paragraph_index": int(
                        conversation[-1][0].source["paragraph_index"]
                    ),
                    "turn_index": position,
                    "target_turn_index": position,
                    "source_paragraph_index": int(unit.source["paragraph_index"]),
                    "target_span_id": span.span_id,
                    "target_text": target_text,
                    "target_turn": target_turn,
                    "response_turn": target_turn,
                    "stimulus_turns": stimulus,
                }
                allowed_persona_modes = _allowed_persona_modes(unit, character_id)
                if allowed_persona_modes is not None:
                    metadata["allowed_persona_modes"] = list(allowed_persona_modes)
                records.append(
                    CorpusRecord(
                        document_id=document_id,
                        title=(
                            f"{unit.source['book_title']}·"
                            f"{converter(str(unit.source['section_title']))}·"
                            f"{CHARACTER_DISPLAY_NAMES[character_id]}审阅台词"
                        ),
                        character_id=character_id,
                        timeline=str(unit.source["timeline"]),
                        spoiler_level=int(unit.source["spoiler_level"]),
                        language="zh-CN",
                        source_type="scene",
                        trust_level=(
                            "canonical_agent_reviewed"
                            if annotation.certainty == "certain"
                            else "canonical_agent_reviewed_probable"
                        ),
                        content=content,
                        metadata=metadata,
                    )
                )
    return records


def _split_dialogue_conversations(
    speech: Sequence[tuple[DialogueReviewUnit, QuoteSpan, ReviewedSpan]],
) -> tuple[tuple[tuple[DialogueReviewUnit, QuoteSpan, ReviewedSpan], ...], ...]:
    conversations: list[list[tuple[DialogueReviewUnit, QuoteSpan, ReviewedSpan]]] = []
    current: list[tuple[DialogueReviewUnit, QuoteSpan, ReviewedSpan]] = []
    previous_paragraph_index: int | None = None
    for item in speech:
        paragraph_index = int(item[0].source["paragraph_index"])
        if (
            current
            and previous_paragraph_index is not None
            and paragraph_index - previous_paragraph_index > MAX_DIALOGUE_PARAGRAPH_GAP
        ):
            conversations.append(current)
            current = []
        current.append(item)
        previous_paragraph_index = paragraph_index
    if current:
        conversations.append(current)
    return tuple(tuple(conversation) for conversation in conversations)


def _conversation_id(
    section_key: tuple[str, int],
    *,
    speech: Sequence[tuple[DialogueReviewUnit, QuoteSpan, ReviewedSpan]],
) -> str:
    first_unit, _, _ = speech[0]
    paragraph_index = int(first_unit.source["paragraph_index"])
    return (
        f"haruhi-scene-{section_key[0]}-s{section_key[1]:02d}-"
        f"p{paragraph_index:05d}"
    )


def _stimulus_turns(
    conversation: Sequence[tuple[DialogueReviewUnit, QuoteSpan, ReviewedSpan]],
    *,
    position: int,
    reviewed_spans: Mapping[str, ReviewedSpan],
    converter: Callable[[str], str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    target_paragraph_index = int(conversation[position][0].source["paragraph_index"])
    for turn_index, (unit, span, reviewed) in enumerate(conversation[:position]):
        paragraph_index = int(unit.source["paragraph_index"])
        if target_paragraph_index - paragraph_index > MAX_DIALOGUE_PARAGRAPH_GAP:
            continue
        speaker = _canonical_speaker(reviewed.annotation.speaker)
        if speaker in {"unknown", "none"}:
            continue
        text = converter(_sanitize_nested_quotes(unit, span, reviewed_spans))
        candidates.append(
            _dialogue_turn_mapping(
                unit,
                span,
                speaker=speaker,
                text=text,
                turn_index=turn_index,
                certainty=reviewed.annotation.certainty,
            )
        )
    return candidates[-MAX_DIALOGUE_STIMULUS_TURNS:]


def _dialogue_turn_mapping(
    unit: DialogueReviewUnit,
    span: QuoteSpan,
    *,
    speaker: str,
    text: str,
    turn_index: int,
    certainty: str,
) -> dict[str, Any]:
    return {
        "turn_index": turn_index,
        "speaker_id": speaker,
        "speaker_label": _speaker_label(speaker),
        "text": text,
        "source_line": int(unit.source["line"]),
        "paragraph_index": int(unit.source["paragraph_index"]),
        "source_char_start": span.start,
        "source_char_end": span.end,
        "span_id": span.span_id,
        "certainty": certainty,
    }


def _render_dialogue_content(
    *,
    header: str,
    stimulus: Sequence[Mapping[str, Any]],
    target_turn: Mapping[str, Any],
) -> str:
    target_section = (
        "【目标角色回答】\n"
        f"{target_turn['speaker_label']}：{target_turn['text']}"
    )
    mandatory = f"{header}\n{target_section}"
    if len(mandatory) > MAX_RECORD_CONTENT_CHARS:
        raise ValueError(
            f"目标角色台词超过记录长度上限：{target_turn['span_id']}"
        )
    selected = list(stimulus)
    while selected:
        context_lines = "\n".join(
            f"{turn['speaker_label']}：{turn['text']}" for turn in selected
        )
        content = f"{header}\n【对话上下文】\n{context_lines}\n{target_section}"
        if len(content) <= MAX_RECORD_CONTENT_CHARS:
            return content
        selected.pop(0)
    return mandatory


def _sanitize_nested_quotes(
    unit: DialogueReviewUnit,
    outer: QuoteSpan,
    reviewed_spans: Mapping[str, ReviewedSpan],
) -> str:
    text = outer.text
    # 只替换直接子引语。若把所有后代都收进来，先替换孙引语后再替换其父引语会让
    # 相对偏移失效；替换直接子引语已经会一并遮住它包含的更深层内容。
    children = [
        candidate
        for candidate in unit.spans
        if candidate.parent_span_id == outer.span_id
    ]
    for child in sorted(children, key=lambda item: item.start, reverse=True):
        reviewed = reviewed_spans.get(child.span_id)
        if reviewed is None:
            continue
        annotation = reviewed.annotation
        if (
            annotation.function == "speech"
            and (
                annotation.scope != "current_scene"
                or annotation.word_owner not in {"same", reviewed_spans[outer.span_id].annotation.speaker}
            )
        ):
            relative_start = child.start - outer.start
            relative_end = child.end - outer.start
            text = text[:relative_start] + "『引用内容略』" + text[relative_end:]
    return text


def _speaker_label(speaker: str) -> str:
    speaker = _canonical_speaker(speaker)
    if speaker in CHARACTER_DISPLAY_NAMES:
        return CHARACTER_DISPLAY_NAMES[speaker]
    if ":" in speaker:
        return speaker.split(":", 1)[1]
    return "未确认说话人" if speaker == "unknown" else speaker


def _canonical_speaker(speaker: str) -> str:
    if speaker.startswith("npc:"):
        candidate = speaker.split(":", 1)[1]
        if candidate in TARGET_SPEAKER_IDS:
            return candidate
    return speaker


def _allowed_persona_modes(
    unit: DialogueReviewUnit,
    character_id: str,
) -> tuple[str, ...] | None:
    if unit.source["book_id"] != "v04-disappearance" or character_id == "kyon":
        return None
    if unit.source["section_title"] in {"第一章", "第二章", "第三章"}:
        return (f"disappearance_{character_id}",)
    return _POST_DISAPPEARANCE_PERSONA_MODES[character_id]


def _review_stats(
    *,
    units: Sequence[DialogueReviewUnit],
    luna: DialogueReviewIndex,
    adjudication: DialogueReviewIndex | None,
    final_spans: Mapping[str, ReviewedSpan],
    dialogue_records: Sequence[CorpusRecord],
) -> dict[str, Any]:
    by_character = Counter(record.character_id for record in dialogue_records)
    by_certainty = Counter(
        str(record.metadata.get("review_certainty")) for record in dialogue_records
    )
    by_method = Counter(
        str(record.metadata.get("review_method")) for record in dialogue_records
    )
    exact_agreement = 0
    adjudicated_count = 0
    if adjudication is not None:
        for span_id, adjudicated in adjudication.spans.items():
            first = luna.spans[span_id].annotation
            second = adjudicated.annotation
            adjudicated_count += 1
            exact_agreement += (
                first.function,
                first.scope,
                first.speaker,
                first.word_owner,
            ) == (
                second.function,
                second.scope,
                second.speaker,
                second.word_owner,
            )
    return {
        "schema_version": "dialogue-review-overlay.v1",
        "candidate_units": len(units),
        "candidate_spans": luna.expected_span_count,
        "luna_coverage": luna.stats["coverage"],
        "adjudicated_spans": adjudicated_count,
        "luna_sol_exact_agreement": (
            round(exact_agreement / adjudicated_count, 6)
            if adjudicated_count
            else None
        ),
        "final_reviewed_spans": len(final_spans),
        "target_dialogue_records": len(dialogue_records),
        "target_dialogue_by_character": dict(sorted(by_character.items())),
        "target_dialogue_by_certainty": dict(sorted(by_certainty.items())),
        "target_dialogue_by_method": dict(sorted(by_method.items())),
        "parse_anomaly_units": sum(bool(unit.parse_warnings) for unit in units),
    }
