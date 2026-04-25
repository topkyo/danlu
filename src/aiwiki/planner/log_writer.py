from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..app_utils import runtime_write_lock
from .schema import (
    DECISIONS,
    PLANNER_LOG_SCHEMA_VERSION,
    canonical_dumps_planner_log,
    compute_planner_log_dedupe_key,
    validate_planner_log_record,
)

_SIGNALS_REL_PATH = ".aiwiki/state/signals.jsonl"
_PLANNER_LOG_REL_PATH = ".aiwiki/state/planner-log.jsonl"
_SKIP_EXAMPLES_LIMIT = 5
_VALID_SIGNAL_SEVERITIES = frozenset({"low", "medium", "high", "critical"})
_SIGNAL_ID_RE = re.compile(r"^sig-[0-9]{8}-[a-z0-9]{6,32}$")
_TRACE_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def write_planner_log(
    root: Path,
    *,
    signals_path: Path | None = None,
    _now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    with runtime_write_lock(root):
        explicit_signals_path = signals_path is not None
        resolved_signals_path = _resolve_signals_path(root, signals_path)
        log_path = root / _PLANNER_LOG_REL_PATH
        existing_dedupe = _load_existing_planner_log(log_path)
        signals_path_label = _SIGNALS_REL_PATH if signals_path is None else str(signals_path)

        if not resolved_signals_path.exists():
            if explicit_signals_path:
                raise FileNotFoundError(f"signals path not found: {resolved_signals_path}")
            return {
                "status": "ok",
                "signals_path": signals_path_label,
                "log_path": _PLANNER_LOG_REL_PATH,
                "scanned_count": 0,
                "new_count": 0,
                "duplicate_count": 0,
                "invalid_count": 0,
                "emitted_by_decision": {decision: 0 for decision in sorted(DECISIONS)},
                "skip_examples": [],
            }

        scanned_count = 0
        new_count = 0
        duplicate_count = 0
        invalid_count = 0
        emitted_by_decision = {decision: 0 for decision in sorted(DECISIONS)}
        skip_examples: list[dict[str, Any]] = []

        batch: list[dict[str, Any]] = []
        batch_dedupe: set[str] = set()
        now_provider = _now or datetime.utcnow

        with resolved_signals_path.open("r", encoding="utf-8") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                payload = raw_line.strip()
                if not payload:
                    continue
                scanned_count += 1
                try:
                    signal = json.loads(payload)
                except json.JSONDecodeError:
                    invalid_count += 1
                    _append_skip_example(
                        skip_examples,
                        {
                            "reason": "signal_malformed_json",
                            "source": "signals",
                            "line": line_no,
                        },
                    )
                    continue

                if not isinstance(signal, dict):
                    invalid_count += 1
                    _append_skip_example(
                        skip_examples,
                        {
                            "reason": "signal_non_object",
                            "source": "signals",
                            "line": line_no,
                        },
                    )
                    continue

                signal_problem = _validate_signal_min_shape(signal)
                if signal_problem is not None:
                    invalid_count += 1
                    _append_skip_example(
                        skip_examples,
                        {
                            "reason": signal_problem,
                            "source": "signals",
                            "line": line_no,
                        },
                    )
                    continue

                kind = str(signal["kind"])
                severity = str(signal["severity"])
                decision, reason_codes = _derive_decision(kind, severity)

                decided_at = now_provider().strftime("%Y-%m-%dT%H:%M:%SZ")
                record = {
                    "schema_version": PLANNER_LOG_SCHEMA_VERSION,
                    "signal_id": signal.get("signal_id"),
                    "dedupe_key": signal.get("dedupe_key"),
                    "trace_id": signal.get("trace_id"),
                    "decision": decision,
                    "mode": "observe_only",
                    "reason_codes": reason_codes,
                    "budget_used": {},
                    "locks_acquired": [],
                    "primitive_refs": [],
                    "side_effects_allowed": False,
                    "decided_at": decided_at,
                }

                try:
                    dedupe_key_pl = compute_planner_log_dedupe_key(record)
                except Exception:
                    invalid_count += 1
                    _append_skip_example(
                        skip_examples,
                        {
                            "reason": "planner_dedupe_key_build_failed",
                            "source": "signals",
                            "line": line_no,
                        },
                    )
                    continue

                if dedupe_key_pl in existing_dedupe:
                    duplicate_count += 1
                    continue

                if dedupe_key_pl in batch_dedupe:
                    duplicate_count += 1
                    continue

                validation = validate_planner_log_record(record)
                if not validation.ok:
                    invalid_count += 1
                    _append_skip_example(
                        skip_examples,
                        {
                            "reason": "planner_record_validation_failed",
                            "source": "signals",
                            "line": line_no,
                            "errors": list(validation.errors),
                        },
                    )
                    continue

                batch.append(record)
                batch_dedupe.add(dedupe_key_pl)
                new_count += 1
                emitted_by_decision[decision] += 1

        if batch:
            _append_records(log_path, batch)

        return {
            "status": "ok",
            "signals_path": signals_path_label,
            "log_path": _PLANNER_LOG_REL_PATH,
            "scanned_count": scanned_count,
            "new_count": new_count,
            "duplicate_count": duplicate_count,
            "invalid_count": invalid_count,
            "emitted_by_decision": emitted_by_decision,
            "skip_examples": skip_examples,
        }


def _resolve_signals_path(root: Path, signals_path: Path | None) -> Path:
    if signals_path is None:
        return root / _SIGNALS_REL_PATH
    if signals_path.is_absolute():
        return signals_path
    return root / signals_path


def _load_existing_planner_log(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    dedupe_fingerprint: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            payload = raw_line.strip()
            if not payload:
                continue
            try:
                record = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid planner-log.jsonl JSON at line {line_no}: {exc.msg}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"invalid planner-log.jsonl record at line {line_no}: expected object")

            validation = validate_planner_log_record(record)
            if not validation.ok:
                raise ValueError(
                    f"invalid planner-log.jsonl record at line {line_no}: {'; '.join(validation.errors)}"
                )

            dedupe_key = compute_planner_log_dedupe_key(record)
            fingerprint = _fingerprint_without_dedupe_identity(record)
            previous = dedupe_fingerprint.get(dedupe_key)
            if previous is not None and previous != fingerprint:
                signal_id = str(record.get("signal_id") or "")
                mode = str(record.get("mode") or "")
                raise RuntimeError(
                    "corrupt planner-log.jsonl: "
                    f"duplicate decision identity ({signal_id}, {mode}) has conflicting payload"
                )
            dedupe_fingerprint[dedupe_key] = fingerprint

    return dedupe_fingerprint


def _fingerprint_without_dedupe_identity(record: dict[str, Any]) -> str:
    trimmed = {
        key: value
        for key, value in record.items()
        if key not in {"signal_id", "mode"}
    }
    return canonical_dumps_planner_log(trimmed)


def _append_records(log_path: Path, records: list[dict[str, Any]]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(canonical_dumps_planner_log(record) for record in records) + "\n"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _append_skip_example(skip_examples: list[dict[str, Any]], item: dict[str, Any]) -> None:
    if len(skip_examples) >= _SKIP_EXAMPLES_LIMIT:
        return
    skip_examples.append(item)


def _validate_signal_min_shape(signal: dict[str, Any]) -> str | None:
    kind = signal.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        return "signal_missing_kind"

    severity = signal.get("severity")
    if not isinstance(severity, str) or not severity.strip():
        return "signal_missing_severity"
    if severity not in _VALID_SIGNAL_SEVERITIES:
        return "signal_invalid_severity"

    signal_id = signal.get("signal_id")
    if not isinstance(signal_id, str) or not signal_id.strip():
        return "signal_missing_signal_id"
    if _SIGNAL_ID_RE.fullmatch(signal_id) is None:
        return "signal_invalid_signal_id"

    dedupe_key = signal.get("dedupe_key")
    if not isinstance(dedupe_key, str) or not dedupe_key.strip():
        return "signal_missing_dedupe_key"

    trace_id = signal.get("trace_id")
    if not isinstance(trace_id, str) or not trace_id.strip():
        return "signal_missing_trace_id"
    if _TRACE_ID_RE.fullmatch(trace_id) is None:
        return "signal_invalid_trace_id"

    return None


def _derive_decision(kind: str, severity: str) -> tuple[str, list[str]]:
    if kind == "raw_added":
        if severity == "low":
            return "ignore", ["raw_added_routine"]
        if severity in {"medium", "high", "critical"}:
            return "enqueue-light", ["raw_added_observed"]
        return "ignore", ["unmapped_kind"]

    if kind == "review_feedback":
        if severity == "medium":
            return "enqueue-light", ["review_feedback_routine"]
        if severity in {"high", "critical"}:
            return "enqueue-heavy", ["review_feedback_high_severity"]
        return "ignore", ["unmapped_kind"]

    if kind == "schedule_tick":
        if severity == "low":
            return "ignore", ["schedule_tick_routine"]
        if severity in {"medium", "high", "critical"}:
            return "enqueue-light", ["schedule_tick_escalated"]
        return "ignore", ["unmapped_kind"]

    if kind == "runtime_failure":
        if severity == "medium":
            return "enqueue-light", ["runtime_failure_routine"]
        if severity == "high":
            return "generate-proposal", ["runtime_failure_observed", "proposal_recommended"]
        if severity == "critical":
            return "escalate-human", ["runtime_failure_critical"]
        return "ignore", ["unmapped_kind"]

    if kind == "drift":
        if severity == "low":
            return "ignore", ["drift_routine"]
        if severity == "medium":
            return "enqueue-light", ["drift_routine"]
        if severity == "high":
            return "generate-proposal", ["drift_observed", "proposal_recommended"]
        if severity == "critical":
            return "enqueue-heavy", ["drift_critical"]
        return "ignore", ["unmapped_kind"]

    if kind == "counter_evidence":
        if severity in {"low", "medium"}:
            return "ignore", ["counter_evidence_routine"]
        if severity == "high":
            return "generate-proposal", ["counter_evidence_observed", "proposal_recommended"]
        if severity == "critical":
            return "enqueue-heavy", ["counter_evidence_observed", "heavy_lane_recommended"]
        return "ignore", ["unmapped_kind"]

    if kind == "elixir_dependency_break":
        if severity == "high":
            return "generate-proposal", ["elixir_dependency_break_observed", "proposal_recommended"]
        return "enqueue-heavy", ["elixir_dependency_break_observed"]

    if kind == "learning_threshold":
        if severity == "low":
            return "ignore", ["learning_threshold_routine"]
        if severity == "medium":
            return "generate-proposal", ["learning_threshold_observed", "proposal_recommended"]
        if severity in {"high", "critical"}:
            return "enqueue-heavy", ["learning_threshold_observed", "heavy_lane_recommended"]
        return "ignore", ["unmapped_kind"]

    return "ignore", ["unmapped_kind"]


__all__ = ["write_planner_log"]
