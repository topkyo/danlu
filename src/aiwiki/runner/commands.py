"""Thin command façades for audit, planner rollback, and signals."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def run_audit_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from aiwiki.execution.audit_preview import preview_universal_audit_stream

    return preview_universal_audit_stream(root, limit=limit)


def run_audit_backfill(root: Path, *, limit: int = 50, apply: bool = False) -> dict[str, Any]:
    from aiwiki.execution.audit_preview import backfill_universal_audit_stream

    return backfill_universal_audit_stream(root, limit=limit, apply=apply)


def run_planner_log_rollback_preview(
    root: Path,
    *,
    signal_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    from aiwiki.planner.rollback import preview_planner_log_rollback

    return preview_planner_log_rollback(root, signal_id=signal_id, trace_id=trace_id, limit=limit)


def run_planner_log_rollback(
    root: Path,
    *,
    signal_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 20,
    apply: bool = False,
) -> dict[str, Any]:
    from aiwiki.planner.rollback import apply_planner_log_rollback_marker

    return apply_planner_log_rollback_marker(root, signal_id=signal_id, trace_id=trace_id, limit=limit, apply=apply)


def run_signals_list(
    root: Path,
    *,
    kind: str | None = None,
    trace_id: str | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from aiwiki.inspection import read_signals

    return read_signals(
        root,
        kind=kind,
        trace_id=trace_id,
        since=since,
        limit=limit,
    )


def run_signals_show(root: Path, signal_id: str) -> dict[str, Any]:
    from aiwiki.inspection import find_planner_decisions_for_signal, find_signal_by_id

    signal = find_signal_by_id(root, signal_id)
    if signal is None:
        return {"status": "not_found", "signal_id": signal_id}
    decisions = find_planner_decisions_for_signal(root, signal_id)
    return {
        "status": "ok",
        "signal": signal,
        "planner_decisions": decisions,
    }


def run_planner_log_list(
    root: Path,
    *,
    decision: str | None = None,
    signal_id: str | None = None,
    trace_id: str | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from aiwiki.inspection import read_planner_decisions

    return read_planner_decisions(
        root,
        decision=decision,
        signal_id=signal_id,
        trace_id=trace_id,
        since=since,
        limit=limit,
    )
