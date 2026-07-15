"""把小说原文转换为适合角色扮演检索的短场景语料。"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from haruhi_roleplay_api.corpus.haruhi import (
    CHARACTER_ALIASES,
    CHARACTER_DISPLAY_NAMES,
    HARUHI_BOOKS,
    BookSpec,
    SectionSpec,
)


PIPELINE_VERSION = "1.0"
CORPUS_RECORD_SCHEMA_VERSION = "haruhi-rag-record.v2"
TARGET_CHARACTERS = tuple(CHARACTER_DISPLAY_NAMES)
MIN_DIALOGUE_CONFIDENCE = 0.65
MAX_RECORD_CONTENT_CHARS = 760

_CONTROL_LINE_RE = re.compile(
    r"^(?:chapter|chp|pic|插圖\s*\d+|插图\s*\d+|[＊*]{1,3})$",
    re.IGNORECASE,
)
_CHAPTER_HEADING_RE = re.compile(
    r"^(?:第[一二三四五六七八九十百0-9０-９]+章|序章|序曲|尾聲|最終章)$"
)
_DIRECT_QUOTE_RE = re.compile(r"^[「『]")
_SPEECH_VERB_RE = re.compile(
    r"(?:(?<!話可)說(?!來|明|不定|服|過)(?:道)?|問(?!題)(?:道)?|答(?!案)(?:道)?|"
    r"回答|喊(?:道)?|叫道|表示|開口|"
    r"出聲|嘟囔|低語|宣告|吶喊|回應|反問|附和|接話|續道|丟出|發表|"
    r"告訴|要求|命令|抱怨|解釋|陳情|主張|嘀咕)"
)
_MENTAL_RE = re.compile(
    r"(?:我想|我覺得|我認為|我明白|我知道|我不禁|我的心|心想|腦中|內心|"
    r"感到|希望|擔心|後悔|困惑|決定|打算|暗自|自問|回想|坦白說|老實說|"
    r"不由得|意識到|察覺|納悶|懷疑)"
)
_BEHAVIOR_RE = re.compile(
    r"(?:看|望|笑|說|問|答|表情|聲音|眼神|動作|走|坐|站|拿|點頭|搖頭|"
    r"沉默|命令|高興|生氣|害怕|微笑|嘆|喊|叫|皺眉|轉身|伸手|盯|瞪|語氣)"
)
_PERSPECTIVE_SECRET_RE = re.compile(
    r"(?:外星人|未來人|超能力者|資訊統合|信息统合|時間旅行|時空|閉鎖空間|"
    r"神人|世界(?:被|已|會|将|將)?改變|改寫世界|三年前的七夕|现实改写|現實改寫)"
)
_BOILERPLATE_MARKERS = (
    "lightnovel.cn",
    "輕之國度錄入組",
    "轻之国度录入组",
    "僅供個人學習交流",
    "仅供个人学习交流",
    "下载后请在24小时内删除",
    "下載後請在24小時內刪除",
    "禁作商業用途",
    "请尊重翻译",
    "請尊重翻譯",
    "嚴禁轉載",
    "严禁转载",
)

_NON_TARGET_SPEAKER_ALIASES = (
    "鶴屋學姊",
    "鶴屋",
    "谷口",
    "國木田",
    "朝倉涼子",
    "朝倉",
    "佐佐木",
    "橘京子",
    "橘",
    "周防九曜",
    "周防",
    "藤原",
    "喜綠江美里",
    "喜綠",
    "新川",
    "森園生",
    "森小姐",
    "多丸圭一",
    "多丸裕",
    "電研社社長",
    "學生會長",
    "會長",
    "三味線",
)

_POST_DISAPPEARANCE_PERSONA_MODES: dict[str, tuple[str, ...]] = {
    "haruhi": ("mid_late_haruhi", "surprise_haruhi"),
    "mikuru": ("default_mikuru", "surprise_mikuru"),
    "yuki": ("default_yuki", "surprise_yuki"),
    "itsuki": ("default_itsuki", "surprise_itsuki"),
}


@dataclass(frozen=True, kw_only=True)
class Paragraph:
    text: str
    line_number: int


@dataclass(frozen=True, kw_only=True)
class SectionText:
    book: BookSpec
    spec: SectionSpec
    index: int
    paragraphs: tuple[Paragraph, ...]


@dataclass(frozen=True, kw_only=True)
class DialogueAttribution:
    paragraph_index: int
    speaker_id: str | None
    confidence: float
    reason: str


@dataclass(frozen=True, kw_only=True)
class CorpusRecord:
    document_id: str
    title: str
    character_id: str
    timeline: str
    spoiler_level: int
    language: str
    source_type: str
    trust_level: str
    content: str
    metadata: Mapping[str, Any]

    def to_mapping(self) -> dict[str, Any]:
        mapping = {
            "document_id": self.document_id,
            "title": self.title,
            "character_id": self.character_id,
            "timeline": self.timeline,
            "spoiler_level": self.spoiler_level,
            "language": self.language,
            "source_type": self.source_type,
            "trust_level": self.trust_level,
            "content": self.content,
            "metadata": dict(self.metadata),
        }
        schema_version = self.metadata.get("record_schema_version")
        if schema_version is not None:
            mapping["schema_version"] = schema_version
        for field in (
            "corpus_version",
            "record_kind",
            "perspective",
            "retrieval_channel",
            "knowledge_owner",
            "subject_character_id",
            "usage",
        ):
            value = self.metadata.get(field)
            if value is not None:
                mapping[field] = value
        return mapping

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CorpusRecord":
        metadata = data.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ValueError("语料记录的 metadata 必须是对象")
        normalized_metadata = dict(metadata)
        schema_version = data.get("schema_version")
        if schema_version is not None:
            if schema_version != CORPUS_RECORD_SCHEMA_VERSION:
                raise ValueError("语料记录 schema_version 不受支持")
            normalized_metadata["record_schema_version"] = schema_version
        for field in (
            "corpus_version",
            "record_kind",
            "perspective",
            "retrieval_channel",
            "knowledge_owner",
            "subject_character_id",
            "usage",
        ):
            value = data.get(field)
            existing = normalized_metadata.get(field)
            if value is not None and existing is not None and value != existing:
                raise ValueError(f"语料记录顶层 {field} 与 metadata 不一致")
            if value is not None:
                normalized_metadata[field] = value
        if schema_version is not None:
            for field in (
                "corpus_version",
                "record_kind",
                "perspective",
                "retrieval_channel",
                "knowledge_owner",
                "subject_character_id",
                "usage",
            ):
                if not normalized_metadata.get(field):
                    raise ValueError(f"语料记录缺少必填字段 {field}")
        return cls(
            document_id=str(data["document_id"]),
            title=str(data["title"]),
            character_id=str(data["character_id"]),
            timeline=str(data["timeline"]),
            spoiler_level=int(data["spoiler_level"]),
            language=str(data["language"]),
            source_type=str(data["source_type"]),
            trust_level=str(data["trust_level"]),
            content=str(data["content"]),
            metadata=normalized_metadata,
        )


@dataclass(frozen=True, kw_only=True)
class BuildResult:
    records_path: Path
    manifest_path: Path
    record_count: int
    stats: Mapping[str, Any]


class SimplifiedChineseConverter:
    def __init__(self) -> None:
        try:
            from opencc import OpenCC
        except ImportError as exc:
            raise RuntimeError(
                "构建简体中文语料需要 opencc-python-reimplemented；"
                "请使用 `uv run --with opencc-python-reimplemented ...` 运行。"
            ) from exc
        self._converter = OpenCC("t2s")

    def __call__(self, text: str) -> str:
        return self._converter.convert(text)


def build_haruhi_corpus(
    source_dir: Path,
    output_dir: Path,
    *,
    converter: Callable[[str], str] | None = None,
) -> BuildResult:
    converter = converter or SimplifiedChineseConverter()
    source_dir = source_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[CorpusRecord] = []
    source_entries: list[dict[str, Any]] = []
    build_stats: Counter[str] = Counter()
    attribution_stats: Counter[str] = Counter()

    for book in HARUHI_BOOKS:
        source_path = source_dir / book.filename
        if not source_path.is_file():
            raise FileNotFoundError(f"缺少小说源文件：{source_path}")
        raw_bytes = source_path.read_bytes()
        source_entry = {
            "book_id": book.book_id,
            "volume": book.volume,
            "filename": book.filename,
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "bytes": len(raw_bytes),
        }
        source_entries.append(source_entry)
        lines = _clean_source_lines(_decode_source(raw_bytes))
        sections = _split_sections(book, lines)
        if not sections:
            raise ValueError(f"未从 {book.filename} 识别出任何篇章")
        body_paragraphs = sum(len(section.paragraphs) for section in sections)
        body_characters = sum(
            len(paragraph.text)
            for section in sections
            for paragraph in section.paragraphs
        )
        source_entry["sections"] = len(sections)
        source_entry["body_paragraphs"] = body_paragraphs
        source_entry["body_characters"] = body_characters
        build_stats["books"] += 1
        build_stats["sections"] += len(sections)
        build_stats["source_body_paragraphs"] += body_paragraphs
        build_stats["source_body_characters"] += body_characters
        for section in sections:
            section_records, section_attribution = _records_for_section(
                section,
                converter=converter,
            )
            records.extend(section_records)
            attribution_stats.update(section_attribution)

    records = _deduplicate_records(records)
    records, corpus_version = finalize_corpus_records(
        records,
        pipeline_version=PIPELINE_VERSION,
    )
    quality = _quality_report(records, build_stats, attribution_stats)
    if quality["errors"]:
        joined = "；".join(str(item) for item in quality["errors"])
        raise ValueError(f"语料质量校验失败：{joined}")

    records_path = output_dir / "records.jsonl"
    with records_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record.to_mapping(), ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    manifest = {
        "schema_version": 2,
        "record_schema_version": CORPUS_RECORD_SCHEMA_VERSION,
        "corpus_version": corpus_version,
        "pipeline_version": PIPELINE_VERSION,
        "language": "zh-CN",
        "source_policy": {
            "raw_text_embedded_in_repository": False,
            "generated_output": (
                "内部项目可追踪的版本化发布产物；"
                "不包含原始小说或模型审阅中间文件"
            ),
            "distribution_scope": "internal_project",
        },
        "sources": source_entries,
        "stats": quality["stats"],
        "quality": {
            "errors": quality["errors"],
            "warnings": quality["warnings"],
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return BuildResult(
        records_path=records_path,
        manifest_path=manifest_path,
        record_count=len(records),
        stats=quality["stats"],
    )


def finalize_corpus_records(
    records: Iterable[CorpusRecord],
    *,
    pipeline_version: str,
) -> tuple[list[CorpusRecord], str]:
    enriched: list[CorpusRecord] = []
    for record in records:
        semantics = _record_semantics(record)
        enriched.append(
            replace(
                record,
                metadata={
                    **dict(record.metadata),
                    "record_schema_version": CORPUS_RECORD_SCHEMA_VERSION,
                    **semantics,
                },
            )
        )
    enriched = _deduplicate_exact_records(enriched)
    digest = hashlib.blake2b(digest_size=12)
    digest.update(pipeline_version.encode("utf-8"))
    for record in sorted(enriched, key=lambda item: item.document_id):
        metadata = {
            key: value
            for key, value in record.metadata.items()
            if key not in {"corpus_version", "dataset_version", "atomic_record"}
        }
        digest.update(
            json.dumps(
                {
                    "document_id": record.document_id,
                    "character_id": record.character_id,
                    "timeline": record.timeline,
                    "content": record.content,
                    "metadata": metadata,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    corpus_version = f"haruhi-rag-{digest.hexdigest()}"
    finalized = [
        replace(
            record,
            metadata={
                **dict(record.metadata),
                "corpus_version": corpus_version,
                "dataset_version": corpus_version,
            },
        )
        for record in enriched
    ]
    return finalized, corpus_version


def _deduplicate_exact_records(records: list[CorpusRecord]) -> list[CorpusRecord]:
    grouped: dict[tuple[str, str, str], list[CorpusRecord]] = defaultdict(list)
    for record in records:
        grouped[
            (
                record.character_id,
                str(record.metadata.get("record_kind", "")),
                record.content,
            )
        ].append(record)
    winners = {
        min(group, key=_duplicate_record_priority).document_id
        for group in grouped.values()
    }
    return [record for record in records if record.document_id in winners]


def _duplicate_record_priority(record: CorpusRecord) -> tuple[float, int, int, str]:
    confidence = record.metadata.get("confidence")
    numeric_confidence = (
        float(confidence)
        if isinstance(confidence, int | float) and not isinstance(confidence, bool)
        else 0.0
    )
    review_method = str(record.metadata.get("review_method", ""))
    review_certainty = str(record.metadata.get("review_certainty", ""))
    return (
        -numeric_confidence,
        0 if review_method == "sol_adjudication" else 1,
        0 if review_certainty == "certain" else 1,
        record.document_id,
    )


def _record_semantics(record: CorpusRecord) -> dict[str, str]:
    record_kind = str(record.metadata.get("record_kind", ""))
    profiles = {
        "scene_memory": {
            "retrieval_channel": "canonical_memory",
            "knowledge_owner": "kyon",
            "usage": "knowledge",
        },
        "inner_monologue": {
            "retrieval_channel": "internal_voice",
            "knowledge_owner": "kyon",
            "usage": "style_and_memory",
        },
        "dialogue_example": {
            "retrieval_channel": "dialogue_style",
            "knowledge_owner": record.character_id,
            "usage": "style_only",
        },
        "behavior_observation": {
            "retrieval_channel": "style_observation",
            "knowledge_owner": "kyon",
            "usage": "style_only",
        },
    }
    if record_kind not in profiles:
        raise ValueError(f"不支持的语料记录类型：{record_kind}")
    return {
        **profiles[record_kind],
        "subject_character_id": record.character_id,
    }


def load_corpus_records(path: Path) -> tuple[CorpusRecord, ...]:
    records: list[CorpusRecord] = []
    expanded_path = path.expanduser()
    if expanded_path.suffix.casefold() == ".gz":
        handle_context = gzip.open(expanded_path, mode="rt", encoding="utf-8")
    else:
        handle_context = expanded_path.open(encoding="utf-8")
    with handle_context as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"语料 JSONL 第 {line_number} 行无法解析") from exc
            if not isinstance(data, Mapping):
                raise ValueError(f"语料 JSONL 第 {line_number} 行必须是对象")
            records.append(CorpusRecord.from_mapping(data))
    if not records:
        raise ValueError(f"语料文件为空：{path}")
    return tuple(records)


def _decode_source(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def _clean_source_lines(text: str) -> tuple[tuple[int, str], ...]:
    cleaned: list[tuple[int, str]] = []
    for line_number, raw_line in enumerate(
        text.replace("\r\n", "\n").replace("\r", "\n").splitlines(),
        start=1,
    ):
        line = unicodedata.normalize("NFC", raw_line).strip().replace("\ufeff", "")
        if not line:
            continue
        if _CONTROL_LINE_RE.fullmatch(line):
            continue
        if any(marker.casefold() in line.casefold() for marker in _BOILERPLATE_MARKERS):
            continue
        if line.startswith(("作者：", "插圖：", "譯者：", "图源：", "圖源：", "錄入：")):
            continue
        if set(line) <= {"─", "—", "-", " "}:
            continue
        cleaned.append((line_number, line))
    return tuple(cleaned)


def _split_sections(
    book: BookSpec,
    lines: tuple[tuple[int, str], ...],
) -> tuple[SectionText, ...]:
    marker_to_spec = {section.marker: section for section in book.sections}
    sections: list[SectionText] = []
    current_spec: SectionSpec | None = None
    current_paragraphs: list[Paragraph] = []

    def flush() -> None:
        if current_spec is None or not current_paragraphs:
            return
        sections.append(
            SectionText(
                book=book,
                spec=current_spec,
                index=len(sections) + 1,
                paragraphs=tuple(current_paragraphs),
            )
        )

    for line_number, line in lines:
        if current_spec is not None and line in book.stop_markers:
            flush()
            current_spec = None
            current_paragraphs = []
            break
        # 所有版本的正文都在录入信息之后开始；避免把卷名与同名短篇误判成正文。
        new_spec = marker_to_spec.get(line) if line_number >= 18 else None
        if new_spec is not None:
            flush()
            current_spec = new_spec
            current_paragraphs = []
            continue
        if current_spec is None:
            continue
        if _CONTROL_LINE_RE.fullmatch(line):
            continue
        if _CHAPTER_HEADING_RE.fullmatch(line) and line not in marker_to_spec:
            continue
        current_paragraphs.append(Paragraph(text=line, line_number=line_number))
    else:
        flush()
    return tuple(section for section in sections if section.paragraphs)


def _records_for_section(
    section: SectionText,
    *,
    converter: Callable[[str], str],
) -> tuple[list[CorpusRecord], Counter[str]]:
    attributions = _attribute_dialogue(section.paragraphs)
    records: list[CorpusRecord] = []
    records.extend(_scene_records(section, converter=converter))
    records.extend(
        _dialogue_records(section, attributions, converter=converter)
    )
    records.extend(_inner_monologue_records(section, converter=converter))
    records.extend(_observation_records(section, converter=converter))
    stats: Counter[str] = Counter()
    stats["quotes_total"] = sum(
        1 for paragraph in section.paragraphs if _is_direct_quote(paragraph.text)
    )
    for attribution in attributions.values():
        if attribution.speaker_id is None:
            stats["quotes_unattributed"] += 1
        else:
            stats["quotes_attributed_target"] += 1
            if attribution.confidence >= 0.9:
                stats["quotes_high_confidence"] += 1
            elif attribution.confidence >= MIN_DIALOGUE_CONFIDENCE:
                stats["quotes_medium_confidence"] += 1
    return records, stats


def _scene_records(
    section: SectionText,
    *,
    converter: Callable[[str], str],
) -> list[CorpusRecord]:
    records: list[CorpusRecord] = []
    for chunk_index, paragraphs in enumerate(
        _paragraph_chunks(section.paragraphs, max_chars=380, overlap=1),
        start=1,
    ):
        body = "\n".join(paragraph.text for paragraph in paragraphs)
        if len(body) < 50:
            continue
        records.append(
            _record(
                section,
                character_id="kyon",
                record_kind="scene_memory",
                body=body,
                title_suffix=f"场景 {chunk_index}",
                trust_level="canonical",
                confidence=1.0,
                perspective="kyon_first_person",
                converter=converter,
                extra={
                    "source_line_start": paragraphs[0].line_number,
                    "source_line_end": paragraphs[-1].line_number,
                },
            )
        )
    return records


def _dialogue_records(
    section: SectionText,
    attributions: Mapping[int, DialogueAttribution],
    *,
    converter: Callable[[str], str],
) -> list[CorpusRecord]:
    quote_indexes = tuple(sorted(attributions))
    records: list[CorpusRecord] = []
    seen: set[tuple[str, str]] = set()
    for position, paragraph_index in enumerate(quote_indexes):
        attribution = attributions[paragraph_index]
        if (
            attribution.speaker_id is None
            or attribution.confidence < MIN_DIALOGUE_CONFIDENCE
        ):
            continue
        context_indexes = tuple(
            context_index
            for context_index in quote_indexes[max(0, position - 2) : position + 3]
            if abs(context_index - paragraph_index) <= 5
        )
        lines: list[str] = []
        context_speakers: list[str] = []
        for context_index in context_indexes:
            context_attribution = attributions[context_index]
            speaker = (
                context_attribution.speaker_id
                if (
                    context_index == paragraph_index
                    or context_attribution.confidence >= 0.9
                )
                else None
            )
            label = (
                CHARACTER_DISPLAY_NAMES[speaker]
                if speaker is not None
                else "未确认说话人"
            )
            quote = _trim_text(section.paragraphs[context_index].text, 170)
            lines.append(f"{label}：{quote}")
            if speaker is not None and speaker not in context_speakers:
                context_speakers.append(speaker)
        body = "\n".join(lines)
        dedupe_key = (attribution.speaker_id, body)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        records.append(
            _record(
                section,
                character_id=attribution.speaker_id,
                record_kind="dialogue_example",
                body=body,
                title_suffix=f"{CHARACTER_DISPLAY_NAMES[attribution.speaker_id]}台词",
                trust_level="canonical_attributed",
                confidence=attribution.confidence,
                perspective="spoken_by_character",
                converter=converter,
                extra={
                    "attribution_reason": attribution.reason,
                    "source_line": section.paragraphs[paragraph_index].line_number,
                    "context_speakers": context_speakers,
                },
            )
        )
    return records


def _inner_monologue_records(
    section: SectionText,
    *,
    converter: Callable[[str], str],
) -> list[CorpusRecord]:
    records: list[CorpusRecord] = []
    candidates = tuple(
        paragraph
        for paragraph in section.paragraphs
        if not _is_direct_quote(paragraph.text) and _MENTAL_RE.search(paragraph.text)
    )
    for index, paragraphs in enumerate(
        _contiguous_paragraph_chunks(candidates, max_chars=330),
        start=1,
    ):
        body = "\n".join(paragraph.text for paragraph in paragraphs)
        if len(body) < 35:
            continue
        records.append(
            _record(
                section,
                character_id="kyon",
                record_kind="inner_monologue",
                body=body,
                title_suffix=f"阿虚心理与旁白 {index}",
                trust_level="canonical_heuristic",
                confidence=0.82,
                perspective="kyon_inner_monologue",
                converter=converter,
                extra={
                    "source_line_start": paragraphs[0].line_number,
                    "source_line_end": paragraphs[-1].line_number,
                },
            )
        )
    return records


def _observation_records(
    section: SectionText,
    *,
    converter: Callable[[str], str],
) -> list[CorpusRecord]:
    records: list[CorpusRecord] = []
    seen: set[tuple[str, str]] = set()
    for paragraph in section.paragraphs:
        if (
            _is_direct_quote(paragraph.text)
            or len(paragraph.text) < 30
            or paragraph.text.endswith(("：", ":"))
            or not _BEHAVIOR_RE.search(paragraph.text)
            or "我" in paragraph.text
            or _PERSPECTIVE_SECRET_RE.search(paragraph.text)
        ):
            continue
        for character_id in ("haruhi", "mikuru", "yuki", "itsuki"):
            if not _character_is_behavior_subject(paragraph.text, character_id):
                continue
            body = _trim_text(paragraph.text, 390)
            key = (character_id, body)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                _record(
                    section,
                    character_id=character_id,
                    record_kind="behavior_observation",
                    body=body,
                    title_suffix=f"{CHARACTER_DISPLAY_NAMES[character_id]}行为观察",
                    trust_level="canonical_heuristic",
                    confidence=0.78,
                    perspective="kyon_observation_not_character_memory",
                    converter=converter,
                    extra={"source_line": paragraph.line_number},
                )
            )
    return records


def _attribute_dialogue(
    paragraphs: tuple[Paragraph, ...],
) -> dict[int, DialogueAttribution]:
    quote_indexes = [
        index for index, paragraph in enumerate(paragraphs) if _is_direct_quote(paragraph.text)
    ]
    attributions: dict[int, DialogueAttribution] = {}
    for index in quote_indexes:
        candidates: list[tuple[float, str, str]] = []
        current = paragraphs[index].text
        closing = max(current.rfind("」"), current.rfind("』"))
        if closing >= 0 and closing + 1 < len(current):
            candidates.extend(
                _speaker_candidates(
                    current[closing + 1 :],
                    base_score=0.99,
                    reason="same_paragraph",
                )
            )
        if (
            index > 0
            and not _is_direct_quote(paragraphs[index - 1].text)
            and paragraphs[index - 1].text.endswith(("：", ":"))
        ):
            previous = paragraphs[index - 1].text
            candidates.extend(
                _speaker_candidates(
                    previous,
                    base_score=0.98,
                    reason="previous_paragraph",
                )
            )
        if (
            index + 1 < len(paragraphs)
            and not _is_direct_quote(paragraphs[index + 1].text)
            and not paragraphs[index + 1].text.endswith(("：", ":"))
        ):
            candidates.extend(
                _speaker_candidates(
                    paragraphs[index + 1].text,
                    base_score=0.93,
                    reason="next_paragraph",
                )
            )
        if candidates:
            score, speaker_id, reason = max(candidates, key=lambda item: item[0])
            attributions[index] = DialogueAttribution(
                paragraph_index=index,
                speaker_id=speaker_id,
                confidence=score,
                reason=reason,
            )
        else:
            attributions[index] = DialogueAttribution(
                paragraph_index=index,
                speaker_id=None,
                confidence=0.0,
                reason="unknown",
            )

    return attributions


def _speaker_candidates(
    text: str,
    *,
    base_score: float,
    reason: str,
) -> list[tuple[float, str, str]]:
    candidates: list[tuple[float, str, str]] = []
    for verb_match in _SPEECH_VERB_RE.finditer(text):
        prefix = text[: verb_match.start()]
        clause_start = max(
            (prefix.rfind(mark) for mark in "，。！？；："),
            default=-1,
        )
        clause = prefix[clause_start + 1 :]
        subject_candidates: list[tuple[int, str]] = []
        for character_id, aliases in CHARACTER_ALIASES.items():
            for alias in aliases:
                alias_position = clause.rfind(alias)
                if alias_position < 0:
                    continue
                before_alias = clause[max(0, alias_position - 3) : alias_position]
                if before_alias.endswith(
                    ("對", "向", "朝", "把", "將", "對著", "看著", "望著")
                ):
                    continue
                subject_candidates.append((alias_position, character_id))
        for alias in _NON_TARGET_SPEAKER_ALIASES:
            alias_position = clause.rfind(alias)
            if alias_position >= 0:
                subject_candidates.append((alias_position, "__non_target__"))
        kyon_matches = tuple(re.finditer(r"(?:^|[^\w])我", clause))
        if kyon_matches:
            subject_candidates.append((kyon_matches[-1].start(), "kyon"))
        if subject_candidates:
            subject_position, character_id = max(subject_candidates)
            if character_id == "__non_target__":
                continue
            candidates.append(
                (
                    base_score - subject_position * 0.002,
                    character_id,
                    reason,
                )
            )
    return candidates


def _record(
    section: SectionText,
    *,
    character_id: str,
    record_kind: str,
    body: str,
    title_suffix: str,
    trust_level: str,
    confidence: float,
    perspective: str,
    converter: Callable[[str], str],
    extra: Mapping[str, Any],
) -> CorpusRecord:
    converted_body = converter(body)
    section_title = converter(section.spec.title)
    header = (
        f"作品：{section.book.title}；篇章：{section_title}；"
        f"资料类型：{_kind_label(record_kind)}；角色：{CHARACTER_DISPLAY_NAMES[character_id]}。"
    )
    content = f"{header}\n{converted_body}"[:MAX_RECORD_CONTENT_CHARS].strip()
    digest = hashlib.blake2b(
        (
            f"{section.book.book_id}\0{section.index}\0{record_kind}\0"
            f"{character_id}\0{content}"
        ).encode("utf-8"),
        digest_size=8,
    ).hexdigest()
    document_id = (
        f"haruhi-{section.book.book_id}-{section.index:02d}-"
        f"{record_kind}-{character_id}-{digest}"
    )
    metadata = {
        "corpus": "haruhi-novels",
        "pipeline_version": PIPELINE_VERSION,
        "record_kind": record_kind,
        "perspective": perspective,
        "confidence": round(confidence, 2),
        "book_id": section.book.book_id,
        "volume": section.book.volume,
        "book_title": section.book.title,
        "section_index": section.index,
        "section_title": section_title,
        "branch": section.spec.branch,
        "source_filename": section.book.filename,
        **dict(extra),
    }
    allowed_persona_modes = _allowed_persona_modes(section, character_id)
    if allowed_persona_modes is not None:
        metadata["allowed_persona_modes"] = list(allowed_persona_modes)
    return CorpusRecord(
        document_id=document_id,
        title=f"{section.book.title}·{section_title}·{title_suffix}",
        character_id=character_id,
        timeline=section.spec.timeline,
        spoiler_level=section.spec.spoiler_level,
        language="zh-CN",
        source_type="scene",
        trust_level=trust_level,
        content=content,
        metadata=metadata,
    )


def _allowed_persona_modes(
    section: SectionText,
    character_id: str,
) -> tuple[str, ...] | None:
    if section.book.book_id != "v04-disappearance" or character_id == "kyon":
        return None
    # 第一至第三章是被改写后的普通世界；其余段落包含改写前、时间修复或恢复后的角色。
    if section.spec.marker in {"第一章", "第二章", "第三章"}:
        return (f"disappearance_{character_id}",)
    return _POST_DISAPPEARANCE_PERSONA_MODES[character_id]


def _kind_label(record_kind: str) -> str:
    return {
        "scene_memory": "阿虚第一人称场景记忆",
        "dialogue_example": "角色台词示例",
        "inner_monologue": "阿虚心理与旁白",
        "behavior_observation": "角色行为观察",
    }[record_kind]


def _paragraph_chunks(
    paragraphs: tuple[Paragraph, ...],
    *,
    max_chars: int,
    overlap: int,
) -> tuple[tuple[Paragraph, ...], ...]:
    chunks: list[tuple[Paragraph, ...]] = []
    current: list[Paragraph] = []
    current_chars = 0
    for paragraph in paragraphs:
        paragraph_chars = len(paragraph.text) + (1 if current else 0)
        if current and current_chars + paragraph_chars > max_chars:
            chunks.append(tuple(current))
            current = current[-overlap:] if overlap else []
            current_chars = sum(len(item.text) + 1 for item in current)
        if len(paragraph.text) > max_chars:
            if current and (not chunks or chunks[-1] != tuple(current)):
                chunks.append(tuple(current))
                current = []
                current_chars = 0
            for start in range(0, len(paragraph.text), max_chars):
                part = Paragraph(
                    text=paragraph.text[start : start + max_chars],
                    line_number=paragraph.line_number,
                )
                chunks.append((part,))
            continue
        current.append(paragraph)
        current_chars += paragraph_chars
    if current:
        chunks.append(tuple(current))
    return tuple(chunks)


def _contiguous_paragraph_chunks(
    paragraphs: tuple[Paragraph, ...],
    *,
    max_chars: int,
) -> tuple[tuple[Paragraph, ...], ...]:
    groups: list[tuple[Paragraph, ...]] = []
    current: list[Paragraph] = []
    for paragraph in paragraphs:
        if current and paragraph.line_number - current[-1].line_number > 2:
            groups.extend(_paragraph_chunks(tuple(current), max_chars=max_chars, overlap=0))
            current = []
        current.append(paragraph)
    if current:
        groups.extend(_paragraph_chunks(tuple(current), max_chars=max_chars, overlap=0))
    return tuple(groups)


def _character_is_behavior_subject(text: str, character_id: str) -> bool:
    for alias in CHARACTER_ALIASES[character_id]:
        start = 0
        while True:
            alias_position = text.find(alias, start)
            if alias_position < 0:
                break
            before_alias = text[max(0, alias_position - 3) : alias_position]
            if not before_alias.endswith(
                ("對", "向", "朝", "把", "將", "对", "将", "對著", "看著", "望著")
            ):
                clause = text[alias_position + len(alias) : alias_position + len(alias) + 28]
                if _BEHAVIOR_RE.search(clause):
                    return True
            start = alias_position + len(alias)
    return False


def _is_direct_quote(text: str) -> bool:
    return bool(_DIRECT_QUOTE_RE.match(text))


def _trim_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _deduplicate_records(records: Iterable[CorpusRecord]) -> list[CorpusRecord]:
    unique: dict[tuple[str, str, str, str], CorpusRecord] = {}
    for record in records:
        kind = str(record.metadata.get("record_kind", ""))
        key = (record.character_id, record.timeline, kind, record.content)
        unique.setdefault(key, record)
    return sorted(
        unique.values(),
        key=lambda record: (
            int(record.metadata.get("volume", 0)),
            int(record.metadata.get("section_index", 0)),
            record.character_id,
            str(record.metadata.get("record_kind", "")),
            record.document_id,
        ),
    )


def _quality_report(
    records: list[CorpusRecord],
    build_stats: Counter[str],
    attribution_stats: Counter[str],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    by_character = Counter(record.character_id for record in records)
    by_kind = Counter(str(record.metadata.get("record_kind")) for record in records)
    by_timeline = Counter(record.timeline for record in records)
    ids = [record.document_id for record in records]
    if build_stats["books"] != len(HARUHI_BOOKS):
        errors.append("未覆盖全部卷册")
    if len(ids) != len(set(ids)):
        errors.append("document_id 不唯一")
    for character_id in TARGET_CHARACTERS:
        if by_character[character_id] < 50:
            errors.append(f"角色 {character_id} 的记录少于 50 条")
    for kind in (
        "scene_memory",
        "dialogue_example",
        "inner_monologue",
        "behavior_observation",
    ):
        if by_kind[kind] == 0:
            errors.append(f"缺少 {kind} 记录")
    too_long = [record.document_id for record in records if len(record.content) > MAX_RECORD_CONTENT_CHARS]
    if too_long:
        errors.append(f"存在 {len(too_long)} 条超长记录")
    contaminated = [
        record.document_id
        for record in records
        if any(marker.casefold() in record.content.casefold() for marker in _BOILERPLATE_MARKERS)
    ]
    if contaminated:
        errors.append(f"存在 {len(contaminated)} 条站点或录入组污染记录")
    unsafe_observations = [
        record.document_id
        for record in records
        if record.metadata.get("record_kind") == "behavior_observation"
        and ("我" in record.content.split("\n", 1)[-1] or _PERSPECTIVE_SECRET_RE.search(record.content))
    ]
    if unsafe_observations:
        errors.append(f"存在 {len(unsafe_observations)} 条可能越过角色视角的行为观察")
    unbounded_disappearance = [
        record.document_id
        for record in records
        if record.metadata.get("book_id") == "v04-disappearance"
        and record.character_id != "kyon"
        and not record.metadata.get("allowed_persona_modes")
    ]
    if unbounded_disappearance:
        errors.append(f"存在 {len(unbounded_disappearance)} 条未限定 persona 的《消失》记录")
    quote_total = attribution_stats["quotes_total"]
    attributed = attribution_stats["quotes_attributed_target"]
    attribution_rate = attributed / quote_total if quote_total else 0.0
    if attribution_rate < 0.25:
        warnings.append("目标角色台词归因率低于 25%，未确认台词已保守舍弃")
    stats = {
        "books": build_stats["books"],
        "sections": build_stats["sections"],
        "source_body_paragraphs": build_stats["source_body_paragraphs"],
        "source_body_characters": build_stats["source_body_characters"],
        "records": len(records),
        "records_by_character": dict(sorted(by_character.items())),
        "records_by_kind": dict(sorted(by_kind.items())),
        "records_by_timeline": dict(sorted(by_timeline.items())),
        "quotes_total": quote_total,
        "quotes_attributed_target": attributed,
        "quotes_unattributed_or_nontarget": attribution_stats["quotes_unattributed"],
        "quote_target_attribution_rate": round(attribution_rate, 4),
        "quotes_high_confidence": attribution_stats["quotes_high_confidence"],
        "quotes_medium_confidence": attribution_stats["quotes_medium_confidence"],
        "max_content_chars": max((len(record.content) for record in records), default=0),
    }
    return {"stats": stats, "errors": errors, "warnings": warnings}
