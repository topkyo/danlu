"""Read-only inspection helpers for signals and planner logs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .app_utils import parse_iso_datetime

_SIGNALS_PATH = Path(".aiwiki/state/signals.jsonl")
_PLANNER_LOG_PATH = Path(".aiwiki/state/planner-log.jsonl")


def read_signals(
    root: Path,
    *,
    kind: str | None = None,
    trace_id: str | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Read and filter signal records (recent first)."""

    since_dt = _parse_since(since)
    _validate_limit(limit)
    records = _read_jsonl_records(root / _SIGNALS_PATH)
    items: list[dict[str, Any]] = []
    for record in records:
        if kind is not None and str(record.get("kind") or "") != kind:
            continue
        if trace_id is not None and str(record.get("trace_id") or "") != trace_id:
            continue
        emitted_at = _parse_timestamp(record.get("emitted_at"))
        if since_dt is not None and (emitted_at is None or emitted_at < since_dt):
            continue
        items.append(record)
    items.sort(key=lambda record: _sort_key(record.get("emitted_at")), reverse=True)
    if limit is not None:
        items = items[:limit]
    return items


def read_planner_decisions(
    root: Path,
    *,
    decision: str | None = None,
    signal_id: str | None = None,
    trace_id: str | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Read and filter planner-log records (recent first)."""

    since_dt = _parse_since(since)
    _validate_limit(limit)
    records = _read_jsonl_records(root / _PLANNER_LOG_PATH)
    items: list[dict[str, Any]] = []
    for record in records:
        if decision is not None and str(record.get("decision") or "") != decision:
            continue
        if signal_id is not None and str(record.get("signal_id") or "") != signal_id:
            continue
        if trace_id is not None and str(record.get("trace_id") or "") != trace_id:
            continue
        decided_at = _parse_timestamp(record.get("decided_at"))
        if since_dt is not None and (decided_at is None or decided_at < since_dt):
            continue
        items.append(record)
    items.sort(key=lambda record: _sort_key(record.get("decided_at")), reverse=True)
    if limit is not None:
        items = items[:limit]
    return items


def find_signal_by_id(root: Path, signal_id: str) -> dict[str, Any] | None:
    """Find one signal by exact signal_id."""

    for record in _read_jsonl_records(root / _SIGNALS_PATH):
        if str(record.get("signal_id") or "") == signal_id:
            return record
    return None


def find_planner_decisions_for_signal(root: Path, signal_id: str) -> list[dict[str, Any]]:
    """Find planner decisions for one signal id (recent first)."""

    return read_planner_decisions(root, signal_id=signal_id)


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path} line {line_no}: {exc.msg}") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"Invalid JSONL at {path} line {line_no}: expected object record")
            records.append(parsed)
    return records


def _parse_since(since: str | None) -> datetime | None:
    if since is None:
        return None
    parsed = parse_iso_datetime(since)
    if parsed is None:
        raise ValueError("Invalid since datetime; expected ISO-8601 value.")
    return parsed


def _validate_limit(limit: int | None) -> None:
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than 0.")


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return parse_iso_datetime(value)


def _sort_key(value: Any) -> datetime:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return parsed
