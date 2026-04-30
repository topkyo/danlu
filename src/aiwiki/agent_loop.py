"""Nightly agent-loop preview orchestration.

This module makes the final-shape loop visible without executing lane apply:
signals are collected, planner decisions are replayed, and alchemy lanes are
previewed in dry-run mode only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .app_state import nightly_health_state_path
from .app_utils import utc_now
from .planner import preview_alchemy_lane, write_planner_log
from .signals import collect_signals

_AUTO_DEFAULT_PRIMITIVES = {
    "heavy": ("compile", "lint"),
    "light": ("compile", "lint", "nightly"),
}
_AUTO_SUPPORTED_PRIMITIVES = {"compile", "lint", "nightly"}


def run_nightly_agent_loop_preview(
    root: Path,
    *,
    scope: str = "all",
    lanes: tuple[str, ...] = ("heavy", "light"),
) -> dict[str, Any]:
    """Run the observe + dry-run agent loop after nightly state is written.

    Writes are limited to signal/planner-log materialization. Lane execution is
    never allowed here; the lane step is a read-only preview.
    """

    generated_at = utc_now()
    base: dict[str, Any] = {
        "status": "ok",
        "generated_at": generated_at,
        "mode": "observe_and_dry_run",
        "dry_run": True,
        "side_effects_allowed": False,
        "scope": scope,
    }
    try:
        signals_result = collect_signals(root)
        observe_result = write_planner_log(root, mode="observe_only")
        execute_result = write_planner_log(root, mode="execute")
        auto_preview = _build_auto_preview(root, scope=scope, lanes=lanes)
    except Exception as exc:  # noqa: BLE001 - preview failure must be surfaced in nightly state
        return {
            **base,
            "status": "failed",
            "error": str(exc),
            "error_type": type(exc).__name__,
        }

    return {
        **base,
        "signals": _signal_counts(signals_result),
        "planner": {
            "observe": _planner_counts(observe_result),
            "execute": _planner_counts(execute_result),
        },
        "auto_preview": auto_preview,
    }


def attach_agent_loop_to_nightly_state(root: Path, state: dict[str, Any], agent_loop: dict[str, Any]) -> dict[str, Any]:
    """Persist ``agent_loop`` inside nightly-health and return the updated state."""

    updated = {**state, "agent_loop": agent_loop}
    path = nightly_health_state_path(root)
    path.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return updated


def _build_auto_preview(root: Path, *, scope: str, lanes: tuple[str, ...]) -> dict[str, Any]:
    lane_results: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    ready_count = 0
    for lane in lanes:
        plan = preview_alchemy_lane(
            root,
            lane=lane,
            scope=scope,
            decision_mode="execute",
            allow_current_writer_lock=True,
        )
        selected_primitives = _selected_auto_primitives(lane, plan)
        reason = _auto_skip_reason(plan, selected_primitives)
        status = "skipped" if reason else "ready"
        if reason:
            skipped.append({"lane": lane, "reason": reason})
        else:
            ready_count += 1
        lane_results.append(
            {
                "lane": lane,
                "status": status,
                "reason": reason,
                "plan_status": str(plan.get("status") or ""),
                "selected_count": int(plan.get("selected_count") or 0),
                "selected_primitives": selected_primitives,
                "budget_exceeded": bool(plan.get("budget", {}).get("exceeded"))
                if isinstance(plan.get("budget"), dict)
                else False,
            }
        )
    return {
        "status": "preview",
        "mode": "dry_run",
        "dry_run": True,
        "side_effects_allowed": False,
        "scope": scope,
        "decision_mode": "execute",
        "lanes": list(lanes),
        "ready_count": ready_count,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "lane_results": lane_results,
    }


def _selected_auto_primitives(lane: str, plan: dict[str, Any]) -> list[str]:
    defaults = _AUTO_DEFAULT_PRIMITIVES.get(lane, ())
    supported = {
        str(item.get("primitive") or "")
        for item in plan.get("primitive_plan", [])
        if (
            isinstance(item, dict)
            and item.get("apply_supported") is True
            and str(item.get("primitive") or "") in _AUTO_SUPPORTED_PRIMITIVES
        )
    }
    return [primitive for primitive in defaults if primitive in supported]


def _auto_skip_reason(plan: dict[str, Any], selected_primitives: list[str]) -> str:
    status = str(plan.get("status") or "")
    if status != "ok":
        return f"plan_{status or 'unknown'}"
    if int(plan.get("selected_count") or 0) <= 0:
        return "empty_execute_plan"
    if not selected_primitives:
        return "no_apply_supported_primitives"
    return ""


def _signal_counts(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(result.get("status") or ""),
        "path": str(result.get("signals_path") or ".aiwiki/state/signals.jsonl"),
        "scanned_count": int(result.get("scanned_count") or 0),
        "new_count": int(result.get("new_count") or 0),
        "duplicate_count": int(result.get("duplicate_count") or 0),
        "unmapped_count": int(result.get("unmapped_count") or 0),
        "invalid_count": int(result.get("invalid_count") or 0),
        "emitted_by_kind": dict(result.get("emitted_by_kind") or {}),
    }


def _planner_counts(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(result.get("status") or ""),
        "path": str(result.get("log_path") or ".aiwiki/state/planner-log.jsonl"),
        "scanned_count": int(result.get("scanned_count") or 0),
        "new_count": int(result.get("new_count") or 0),
        "duplicate_count": int(result.get("duplicate_count") or 0),
        "invalid_count": int(result.get("invalid_count") or 0),
        "emitted_by_decision": dict(result.get("emitted_by_decision") or {}),
    }


__all__ = ["attach_agent_loop_to_nightly_state", "run_nightly_agent_loop_preview"]
