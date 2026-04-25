from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..app_utils import runtime_write_lock
from . import adapters
from .schema import PROTOCOLS, SCHEMA_VERSION, canonical_dumps, compute_dedupe_key, parse_trace_id, validate

SIGNALS_REL_PATH = ".aiwiki/state/signals.jsonl"
SKIP_EXAMPLES_LIMIT = 5
SUPPORTED_SOURCES: tuple[str, str, str] = adapters.SUPPORTED_SOURCES
MAPPED_KINDS: tuple[str, str, str, str, str, str] = (
    "raw_added",
    "review_feedback",
    "schedule_tick",
    "runtime_failure",
    "drift",
    "elixir_dependency_break",
)


def collect_signals(
    root: Path,
    *,
    sources: list[str] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Replay upstream logs into `.aiwiki/state/signals.jsonl`.

    M1.2 仅映射 runtime_history.review / runtime_history.nightly / llm_receipt(status=failed)。
    对 runtime_history.review/nightly，如果 upstream event 没有 protocol，按 invalid 跳过。

    语义约束：`dedupe_key` 代表内容身份；`trace_id` 仅代表本次 replay 批次标识。
    因此 replay 命中既存 dedupe_key 时，无条件按 duplicate 处理，不做跨批 trace 比较。
    """

    selected_sources = _normalize_sources(sources)

    with runtime_write_lock(root):
        resolved_trace_id = _resolve_trace_id(trace_id)
        signals_path = root / SIGNALS_REL_PATH
        existing_dedupe_to_trace = _load_existing_dedupe_map(signals_path)

        scanned_count = 0
        duplicate_count = 0
        unmapped_count = 0
        invalid_count = 0
        skip_examples: list[dict[str, Any]] = []
        emitted_by_kind: dict[str, int] = {kind: 0 for kind in MAPPED_KINDS}

        batch_records: list[dict[str, Any]] = []
        batch_dedupe_keys: set[str] = set()

        for source in selected_sources:
            for line_no, raw_line, rel_path in adapters.iter_source_lines(root, source):
                scanned_count += 1
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    invalid_count += 1
                    _append_skip_example(skip_examples, reason=f"{source}_malformed_json", source=source, line=line_no)
                    continue

                if not isinstance(event, dict):
                    invalid_count += 1
                    _append_skip_example(skip_examples, reason=f"{source}_non_object", source=source, line=line_no)
                    continue

                seeds = _to_signal_seeds(source, event, line_no=line_no, rel_path=rel_path)
                if not seeds:
                    reason = _mapped_invalid_reason(source, event)
                    if reason is not None:
                        invalid_count += 1
                        _append_skip_example(skip_examples, reason=reason, source=source, line=line_no)
                    else:
                        unmapped_count += 1
                    continue

                for seed in seeds:
                    try:
                        dedupe_key = compute_dedupe_key(seed.record_base, seed.source_identity)
                    except Exception:
                        invalid_count += 1
                        _append_skip_example(skip_examples, reason="dedupe_key_build_failed", source=source, line=line_no)
                        continue

                    existing_trace = existing_dedupe_to_trace.get(dedupe_key)
                    if existing_trace is not None:
                        duplicate_count += 1
                        continue

                    if dedupe_key in batch_dedupe_keys:
                        duplicate_count += 1
                        continue

                    full_record = {
                        **seed.record_base,
                        "schema_version": SCHEMA_VERSION,
                        "signal_id": _new_signal_id(),
                        "dedupe_key": dedupe_key,
                        "trace_id": _seed_trace_id_or_default(seed, resolved_trace_id),
                    }
                    validation = validate(full_record)
                    if not validation.ok:
                        invalid_count += 1
                        _append_skip_example(skip_examples, reason="signal_validation_failed", source=source, line=line_no)
                        continue

                    batch_records.append(full_record)
                    batch_dedupe_keys.add(dedupe_key)
                    kind = str(full_record.get("kind") or "")
                    if kind in emitted_by_kind:
                        emitted_by_kind[kind] += 1

        if batch_records:
            _append_records(signals_path, batch_records)

        return {
            "status": "ok",
            "trace_id": resolved_trace_id,
            "signals_path": SIGNALS_REL_PATH,
            "sources": list(selected_sources),
            "scanned_count": scanned_count,
            "new_count": len(batch_records),
            "duplicate_count": duplicate_count,
            "unmapped_count": unmapped_count,
            "invalid_count": invalid_count,
            "emitted_by_kind": emitted_by_kind,
            "skip_examples": skip_examples,
        }


def _normalize_sources(sources: list[str] | None) -> list[str]:
    if sources is None:
        return list(SUPPORTED_SOURCES)
    selected: list[str] = []
    for source in sources:
        if source not in SUPPORTED_SOURCES:
            raise ValueError(f"unsupported source: {source}")
        if source not in selected:
            selected.append(source)
    return selected


def _resolve_trace_id(trace_id: str | None) -> str:
    if trace_id is None:
        return str(uuid.uuid4())
    return parse_trace_id(trace_id)


def _load_existing_dedupe_map(signals_path: Path) -> dict[str, str]:
    if not signals_path.exists():
        return {}

    dedupe_to_trace: dict[str, str] = {}
    with signals_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                record = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid signals.jsonl JSON at line {line_no}: {exc.msg}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"invalid signals.jsonl record at line {line_no}: expected object")

            validation = validate(record)
            if not validation.ok:
                raise ValueError(
                    f"invalid signals.jsonl record at line {line_no}: {'; '.join(validation.errors)}"
                )

            dedupe_key = str(record.get("dedupe_key") or "")
            existing_trace_id = str(record.get("trace_id") or "")
            previous_trace_id = dedupe_to_trace.get(dedupe_key)
            if previous_trace_id is not None and previous_trace_id != existing_trace_id:
                raise RuntimeError(
                    "corrupt signals.jsonl: "
                    f"dedupe_key={dedupe_key} has conflicting trace_id values "
                    f"{previous_trace_id} vs {existing_trace_id}"
                )
            dedupe_to_trace[dedupe_key] = existing_trace_id
    return dedupe_to_trace


def _to_signal_seeds(source: str, event: dict[str, Any], *, line_no: int, rel_path: str) -> list[adapters.SignalSeed]:
    if source == "runtime_history":
        return adapters._runtime_history_to_signals(event, line_no=line_no, rel_path=rel_path)
    if source == "llm_receipt":
        return adapters._llm_receipt_to_signals(
            event,
            line_no=line_no,
            rel_path=rel_path,
            allowed_protocols=set(PROTOCOLS),
        )
    if source == "archive":
        return [
            *adapters._archive_receipt_to_signals(
                event,
                receipt_rel_path=rel_path,
                history_line_no=line_no,
            ),
            *adapters._elixir_dependency_break_to_signals(
                event,
                receipt_rel_path=rel_path,
                history_line_no=line_no,
            ),
        ]
    raise ValueError(f"unsupported source: {source}")


def _mapped_invalid_reason(source: str, event: dict[str, Any]) -> str | None:
    if source == "runtime_history":
        event_type = str(event.get("event_type") or "")
        if event_type == "raw-added":
            protocol = event.get("protocol")
            if not isinstance(protocol, str) or not protocol:
                return "runtime_history_raw_added_missing_protocol"
            stored_path = event.get("stored_path") or event.get("note_path") or event.get("raw_path")
            if not isinstance(stored_path, str) or not stored_path:
                return "runtime_history_raw_added_missing_stored_path"
            return "runtime_history_raw_added_invalid"
        if event_type in {"review", "nightly"}:
            protocol = event.get("protocol")
            if not isinstance(protocol, str) or not protocol:
                return "runtime_history_missing_protocol"
            return "runtime_history_mapped_event_invalid"
        return None

    if source == "llm_receipt":
        status = str(event.get("status") or "")
        if status == "failed":
            protocol = event.get("protocol")
            if not isinstance(protocol, str) or not protocol:
                return "llm_receipt_missing_protocol"
            if protocol not in PROTOCOLS:
                return "llm_receipt_invalid_protocol"
            return "llm_receipt_failed_event_invalid"
        return None

    if source == "archive":
        if event.get("kind") != "execution-receipt":
            return None

        subject_kind = str(event.get("subject_kind") or "")
        if subject_kind in {"elixir_revert", "elixir_demotion"}:
            protocol = event.get("protocol")
            if not isinstance(protocol, str) or not protocol:
                return "archive_missing_protocol"

            bundle = event.get("bundle")
            if not isinstance(bundle, dict):
                return None
            dependency_breaks = bundle.get("dependency_breaks")
            if dependency_breaks is None:
                return None
            if not isinstance(dependency_breaks, list):
                return "archive_elixir_breaks_invalid"

            for item in dependency_breaks:
                if not isinstance(item, dict):
                    return "archive_elixir_break_item_invalid"
                dependent_elixir_id = item.get("dependent_elixir_id")
                if not isinstance(dependent_elixir_id, str) or not dependent_elixir_id:
                    return "archive_elixir_break_item_invalid"
            return None

        if subject_kind != "material-archive":
            return None

        protocol = event.get("protocol")
        if not isinstance(protocol, str) or not protocol:
            return "archive_missing_protocol"

        subject_id = event.get("subject_id")
        if not isinstance(subject_id, str) or not subject_id:
            return "archive_missing_subject_id"

        current_temperature = str(event.get("current_temperature") or "")
        resulting_temperature = str(event.get("resulting_temperature") or "")
        if (current_temperature, resulting_temperature) not in {
            ("cold", "archived"),
            ("archived", "cold"),
        }:
            return "archive_unknown_transition"
        return None

    return None


def _append_skip_example(skip_examples: list[dict[str, Any]], *, reason: str, source: str, line: int) -> None:
    if len(skip_examples) >= SKIP_EXAMPLES_LIMIT:
        return
    skip_examples.append({"reason": reason, "source": source, "line": line})


def _append_records(signals_path: Path, records: list[dict[str, Any]]) -> None:
    signals_path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(canonical_dumps(record) for record in records) + "\n"
    with signals_path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _new_signal_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:12]
    return f"sig-{day}-{suffix}"


def _seed_trace_id_or_default(seed: adapters.SignalSeed, default_trace_id: str) -> str:
    seed_trace_id = seed.record_base.get("trace_id")
    if isinstance(seed_trace_id, str) and seed_trace_id:
        return seed_trace_id
    return default_trace_id
