"""Append-only metrics history + window baseline lookup (M7.3.1 Stage B).

Schema of each line in ``.aiwiki/state/metrics-history.jsonl``::

    {"ts": "2026-04-28T12:34:56Z", "metrics": {"provenance_completeness": 0.93, ...}}

Design notes:

- Append failures propagate so fsync / durability failures are visible to callers.
- Lookup is reverse-scan over the JSONL file (KISS; expected file size is
  small — one line per metrics command invocation).
- No third-party deps; stdlib datetime only.
- 7 metric key names are frozen by acceptance tests in
  `tests/test_acceptance_loop.py` (originally asserted in
  `tests/test_metrics.py`); this module never rewrites them.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .app_utils import atomic_append_jsonl, runtime_write_operation

HISTORY_RELATIVE = Path(".aiwiki") / "state" / "metrics-history.jsonl"


def history_path(root: Path) -> Path:
    return root / HISTORY_RELATIVE


@runtime_write_operation
def append_snapshot(root: Path, ts: str, metrics: dict[str, float | None]) -> None:
    """Append one snapshot line and propagate append durability failures."""

    path = history_path(root)
    record = {"ts": ts, "metrics": dict(metrics)}
    atomic_append_jsonl(path, record)


def _parse_iso(value: str) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        # Accept trailing Z; datetime.fromisoformat handles offsets in 3.11+,
        # but to stay 3.10-compatible we normalize Z → +00:00.
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _iter_history_lines_reverse(path: Path) -> Iterable[str]:
    if not path.exists():
        return ()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    return tuple(line for line in reversed(text.splitlines()) if line.strip())


def find_baseline(
    root: Path,
    now_iso: str,
    window_days: int,
) -> tuple[str, dict[str, float]] | None:
    """Return ``(baseline_ts, baseline_metrics)`` for the most recent snapshot
    older than or equal to ``now - window_days``. Return None if no such sample
    or the file/line is malformed.
    """

    now = _parse_iso(now_iso)
    if now is None:
        return None
    cutoff = now - timedelta(days=window_days)
    path = history_path(root)
    for line in _iter_history_lines_reverse(path):
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        ts_value = record.get("ts")
        ts = _parse_iso(ts_value) if isinstance(ts_value, str) else None
        if ts is None:
            continue
        if ts > cutoff:
            continue
        metrics = record.get("metrics")
        if not isinstance(metrics, dict):
            continue
        # Coerce values to float where possible; drop non-numeric.
        sanitized: dict[str, float] = {}
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                sanitized[str(key)] = float(value)
        return ts_value, sanitized
    return None


def format_delta_block(
    *,
    window_label: str,
    baseline: tuple[str, dict[str, float]] | None,
    current: dict[str, float],
) -> str:
    """Human-readable trailing block. KISS plain text."""

    if baseline is None:
        return f"# delta {window_label}: no baseline within window"
    baseline_ts, baseline_metrics = baseline
    lines = [f"# delta vs {baseline_ts} ({window_label} ago baseline)"]
    for key in sorted(current.keys()):
        now_value = current.get(key)
        if not isinstance(now_value, (int, float)):
            continue
        prev_value = baseline_metrics.get(key)
        if not isinstance(prev_value, (int, float)):
            lines.append(f"{key}: {now_value:.4g} (no baseline)")
            continue
        diff = now_value - prev_value
        sign = "+" if diff >= 0 else ""
        lines.append(f"{key}: {prev_value:.4g} → {now_value:.4g} ({sign}{diff:.4g})")
    return "\n".join(lines)
