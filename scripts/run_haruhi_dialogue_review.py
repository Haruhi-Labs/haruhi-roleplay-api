#!/usr/bin/env python3
"""使用 Codex Luna 分批审阅凉宫小说引语，支持并发、校验和断点续跑。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from haruhi_roleplay_api.corpus.dialogue_review import (  # noqa: E402
    REVIEW_PROMPT_VERSION,
    DialogueReviewUnit,
    ReviewAnnotation,
    compact_review_units,
    load_dialogue_review_index,
    load_dialogue_review_units,
    normalize_review_output,
    parse_review_annotations,
)


DEFAULT_CANDIDATES = (
    ROOT / ".data" / "rag-corpus" / "haruhi-review" / "dialogue_candidates.jsonl"
)
DEFAULT_OUTPUT = ROOT / ".data" / "rag-corpus" / "haruhi-review" / "reviews" / "luna"
DEFAULT_PROMPT = ROOT / "prompts" / "corpus" / "dialogue-review-v1.md"
DEFAULT_SCHEMA = ROOT / "schemas" / "dialogue-review-batch-v1.schema.json"


@dataclass(frozen=True, kw_only=True)
class ReviewBatch:
    batch_id: str
    units: tuple[DialogueReviewUnit, ...]
    span_ids: tuple[str, ...]
    model_span_ids: tuple[str, ...]
    span_aliases: Mapping[str, str]
    unit_aliases: Mapping[str, str]
    prior_annotations: Mapping[str, ReviewAnnotation]
    input_sha256: str


@dataclass(frozen=True, kw_only=True)
class BatchRunResult:
    batch_id: str
    status: str
    span_count: int
    elapsed_seconds: float
    usage: Mapping[str, int]
    path: Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="用 gpt-5.6-luna 低推理逐条审阅小说引语。"
    )
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--effort", default="low")
    parser.add_argument("--batch-prefix", default="luna-v1")
    parser.add_argument("--prompt-version", default=REVIEW_PROMPT_VERSION)
    parser.add_argument(
        "--span-selection",
        type=Path,
        default=None,
        help="只处理文本文件中列出的 span；命中的整个审阅单元会一起复核",
    )
    parser.add_argument(
        "--prior-review",
        type=Path,
        default=None,
        help="把已有审阅结果作为复核参考传给模型",
    )
    parser.add_argument("--batch-spans", type=int, default=80)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit-units", type=int, default=None)
    parser.add_argument("--book-id", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--retry", type=int, default=1)
    parser.add_argument("--batch-start", type=int, default=1)
    parser.add_argument("--batch-end", type=int, default=None)
    args = parser.parse_args()

    if args.batch_spans < 1:
        parser.error("--batch-spans 必须大于 0")
    if args.workers < 1:
        parser.error("--workers 必须大于 0")
    all_units = list(load_dialogue_review_units(args.candidates))
    units = list(all_units)
    if args.book_id:
        selected_books = set(args.book_id)
        units = [unit for unit in units if unit.source["book_id"] in selected_books]
    if args.span_selection is not None:
        selected_spans = {
            line.strip()
            for line in args.span_selection.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        if not selected_spans:
            parser.error("--span-selection 文件没有 span_id")
        all_span_ids = {span.span_id for unit in all_units for span in unit.spans}
        unknown_spans = selected_spans - all_span_ids
        if unknown_spans:
            parser.error(f"--span-selection 包含未知 span：{sorted(unknown_spans)[:3]}")
        units = [
            unit
            for unit in units
            if any(span.span_id in selected_spans for span in unit.spans)
        ]
    if args.limit_units is not None:
        if args.limit_units < 1:
            parser.error("--limit-units 必须大于 0")
        units = units[: args.limit_units]
    units = [unit for unit in units if unit.spans]
    if not units:
        parser.error("筛选后没有可审阅的引语 span")

    prior_annotations: dict[str, ReviewAnnotation] = {}
    if args.prior_review is not None:
        prior_index = load_dialogue_review_index(
            args.prior_review,
            units=all_units,
            require_complete=False,
        )
        prior_annotations = {
            span_id: reviewed.annotation
            for span_id, reviewed in prior_index.spans.items()
        }
    prompt_text = args.prompt.read_text(encoding="utf-8")
    all_batches = _make_batches(
        units,
        max_spans=args.batch_spans,
        batch_prefix=args.batch_prefix,
        prior_annotations=prior_annotations,
    )
    if args.batch_start < 1:
        parser.error("--batch-start 必须大于 0")
    if args.batch_end is not None and args.batch_end < args.batch_start:
        parser.error("--batch-end 不能小于 --batch-start")
    batches = tuple(
        batch
        for index, batch in enumerate(all_batches, start=1)
        if index >= args.batch_start
        and (args.batch_end is None or index <= args.batch_end)
    )
    if not batches:
        parser.error("指定的批次范围为空")
    output_dir = args.output.expanduser().resolve()
    batch_dir = output_dir / "batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    print_lock = threading.Lock()

    def run(batch: ReviewBatch) -> BatchRunResult:
        return _run_batch(
            batch,
            output_dir=batch_dir,
            prompt_text=prompt_text,
            schema_path=args.schema.expanduser().resolve(),
            model=args.model,
            effort=args.effort,
            prompt_version=args.prompt_version,
            timeout_seconds=args.timeout_seconds,
            retries=args.retry,
        )

    results: list[BatchRunResult] = []
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - 需要保留其他批次并输出失败清单
                failures.append(f"{batch.batch_id}: {exc}")
                with print_lock:
                    print(
                        json.dumps(
                            {"批次": batch.batch_id, "状态": "失败", "错误": str(exc)},
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                continue
            results.append(result)
            with print_lock:
                print(
                    json.dumps(
                        {
                            "批次": result.batch_id,
                            "状态": result.status,
                            "span数": result.span_count,
                            "耗时秒": round(result.elapsed_seconds, 2),
                            "用量": dict(result.usage),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    results.sort(key=lambda item: item.batch_id)
    aggregate_usage: dict[str, int] = {}
    for result in results:
        for key, value in result.usage.items():
            aggregate_usage[key] = aggregate_usage.get(key, 0) + value
    summary = {
        "schema_version": "dialogue-review-run.v1",
        "prompt_version": args.prompt_version,
        "model": args.model,
        "model_reasoning_effort": args.effort,
        "candidate_file": str(args.candidates.expanduser().resolve()),
        "candidate_sha256": hashlib.sha256(args.candidates.read_bytes()).hexdigest(),
        "batch_count": len(batches),
        "all_batch_count": len(all_batches),
        "batch_start": args.batch_start,
        "batch_end": args.batch_end,
        "completed_batches": len(results),
        "failed_batches": len(failures),
        "reviewed_spans": sum(result.span_count for result in results),
        "usage": aggregate_usage,
        "failures": failures,
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"汇总": summary}, ensure_ascii=False, indent=2), flush=True)
    return 1 if failures else 0


def _make_batches(
    units: Sequence[DialogueReviewUnit],
    *,
    max_spans: int,
    batch_prefix: str = "luna-v1",
    prior_annotations: Mapping[str, ReviewAnnotation] | None = None,
) -> tuple[ReviewBatch, ...]:
    groups: list[list[DialogueReviewUnit]] = []
    current: list[DialogueReviewUnit] = []
    current_spans = 0
    for unit in units:
        unit_spans = len(unit.spans)
        if current and current_spans + unit_spans > max_spans:
            groups.append(current)
            current = []
            current_spans = 0
        current.append(unit)
        current_spans += unit_spans
    if current:
        groups.append(current)

    batches: list[ReviewBatch] = []
    for index, group in enumerate(groups, start=1):
        span_ids = tuple(span.span_id for unit in group for span in unit.spans)
        span_aliases = {
            span_id: f"s{span_index:03d}"
            for span_index, span_id in enumerate(span_ids, start=1)
        }
        unit_aliases = {
            unit.review_unit_id: f"u{unit_index:03d}"
            for unit_index, unit in enumerate(group, start=1)
        }
        compact_json = json.dumps(
            compact_review_units(
                group,
                span_aliases=span_aliases,
                unit_aliases=unit_aliases,
                prior_reviews=prior_annotations,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
        input_sha256 = hashlib.sha256(compact_json.encode("utf-8")).hexdigest()
        digest = hashlib.blake2b("\0".join(span_ids).encode("utf-8"), digest_size=6).hexdigest()
        batch_prior_annotations = {
            span_id: prior_annotations[span_id]
            for span_id in span_ids
            if prior_annotations is not None and span_id in prior_annotations
        }
        batches.append(
            ReviewBatch(
                batch_id=f"{batch_prefix}-{index:05d}-{digest}",
                units=tuple(group),
                span_ids=span_ids,
                model_span_ids=tuple(span_aliases[span_id] for span_id in span_ids),
                span_aliases=span_aliases,
                unit_aliases=unit_aliases,
                prior_annotations=batch_prior_annotations,
                input_sha256=input_sha256,
            )
        )
    return tuple(batches)


def _run_batch(
    batch: ReviewBatch,
    *,
    output_dir: Path,
    prompt_text: str,
    schema_path: Path,
    model: str,
    effort: str,
    prompt_version: str,
    timeout_seconds: int,
    retries: int,
) -> BatchRunResult:
    output_path = output_dir / f"{batch.batch_id}.json"
    if output_path.is_file():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(existing, Mapping):
            raise ValueError(f"已有批次文件不是对象：{output_path}")
        if existing.get("input_sha256") != batch.input_sha256:
            raise ValueError(f"已有批次输入指纹不匹配：{batch.batch_id}")
        parse_review_annotations(existing, expected_span_ids=batch.span_ids)
        usage = _integer_mapping(existing.get("usage", {}))
        return BatchRunResult(
            batch_id=batch.batch_id,
            status="已存在",
            span_count=len(batch.span_ids),
            elapsed_seconds=0.0,
            usage=usage,
            path=output_path,
        )

    payload = {
        "batch_id": batch.batch_id,
        "units": compact_review_units(
            batch.units,
            span_aliases=batch.span_aliases,
            unit_aliases=batch.unit_aliases,
            prior_reviews=batch.prior_annotations,
        ),
    }
    prompt = (
        prompt_text.rstrip()
        + "\n\n下面是本批次数据。输出中的 batch_id 必须原样复制。\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 2):
        started = time.monotonic()
        attempt_prompt = prompt
        if last_error is not None:
            attempt_prompt += (
                "\n上一次输出未通过本地语义校验，原因如下：\n"
                f"{last_error}\n"
                "请重新逐条检查并修正该问题；仍须覆盖本批全部 span。\n"
            )
        with tempfile.TemporaryDirectory(prefix="haruhi-luna-review-") as directory:
            last_message_path = Path(directory) / "last-message.json"
            command = [
                "codex",
                "exec",
                "--model",
                model,
                "-c",
                f'model_reasoning_effort="{effort}"',
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(last_message_path),
                "--json",
                "--color",
                "never",
                "-",
            ]
            try:
                process = subprocess.run(
                    command,
                    input=attempt_prompt,
                    text=True,
                    capture_output=True,
                    cwd=ROOT,
                    timeout=timeout_seconds,
                    check=False,
                )
                if process.returncode != 0:
                    error_text = (process.stderr or process.stdout)[-4000:]
                    raise RuntimeError(
                        f"Codex 审阅模型退出码 {process.returncode}：{error_text.strip()}"
                    )
                if not last_message_path.is_file():
                    raise RuntimeError("Codex 审阅模型未生成结构化结果文件")
                raw_result = json.loads(last_message_path.read_text(encoding="utf-8"))
                if not isinstance(raw_result, Mapping):
                    raise ValueError("Codex 审阅模型结果必须是对象")
                if raw_result.get("batch_id") != batch.batch_id:
                    raise ValueError("Codex 审阅模型返回了错误的 batch_id")
                raw_result, normalizations = normalize_review_output(raw_result)
                model_annotations = parse_review_annotations(
                    raw_result,
                    expected_span_ids=batch.model_span_ids,
                )
                alias_to_span_id = {
                    alias: span_id for span_id, alias in batch.span_aliases.items()
                }
                annotations = tuple(
                    type(annotation)(
                        span_id=alias_to_span_id[annotation.span_id],
                        function=annotation.function,
                        scope=annotation.scope,
                        speaker=annotation.speaker,
                        word_owner=annotation.word_owner,
                        certainty=annotation.certainty,
                        evidence=annotation.evidence,
                        rationale=annotation.rationale,
                    )
                    for annotation in model_annotations
                )
                usage = _extract_usage(process.stdout)
                elapsed = time.monotonic() - started
                envelope = {
                    "schema_version": "dialogue-review-batch.v1",
                    "prompt_version": prompt_version,
                    "batch_id": batch.batch_id,
                    "model": model,
                    "model_reasoning_effort": effort,
                    "input_sha256": batch.input_sha256,
                    "attempt": attempt,
                    "elapsed_seconds": round(elapsed, 3),
                    "usage": usage,
                    "normalizations": list(normalizations),
                    "annotations": [annotation.to_mapping() for annotation in annotations],
                }
                temporary_path = output_path.with_suffix(".json.tmp")
                temporary_path.write_text(
                    json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                temporary_path.replace(output_path)
                return BatchRunResult(
                    batch_id=batch.batch_id,
                    status="完成",
                    span_count=len(annotations),
                    elapsed_seconds=elapsed,
                    usage=usage,
                    path=output_path,
                )
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt > retries:
                    break
    assert last_error is not None
    raise RuntimeError(f"批次 {batch.batch_id} 重试后仍失败：{last_error}") from last_error


def _extract_usage(events_jsonl: str) -> dict[str, int]:
    """从 Codex JSON 事件中提取最后一份 token 用量。"""

    last_usage: dict[str, int] = {}
    for line in events_jsonl.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        for mapping in _walk_mappings(event):
            usage = mapping.get("usage")
            if isinstance(usage, Mapping):
                integers = _integer_mapping(usage)
                if integers:
                    last_usage = integers
    return last_usage


def _walk_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mappings(child)


def _integer_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): int(item)
        for key, item in value.items()
        if isinstance(item, int) and not isinstance(item, bool)
    }


if __name__ == "__main__":
    raise SystemExit(main())
