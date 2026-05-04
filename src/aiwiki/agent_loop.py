"""Nightly agent-loop orchestration.

This module makes the final-shape loop visible by default and can optionally
apply the already receipt-gated light lane. Semantic lanes (L1/L2/L3/Judgment)
auto-adoption is opt-in via env flags (``AIWIKI_NIGHTLY_AUTO_ADOPT_*``).
All auto-adopted items write receipts enabling revert.
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
    """Run the observe + dry-run agent loop after nightly state is written."""

    return run_nightly_agent_loop(root, scope=scope, lanes=lanes, apply_light=False, auto_adopt_l1=False, auto_adopt_l2=False, auto_adopt_judgments=False)


def run_nightly_agent_loop(
    root: Path,
    *,
    scope: str = "all",
    lanes: tuple[str, ...] = ("heavy", "light"),
    apply_light: bool = False,
    auto_adopt_l1: bool = False,
    auto_adopt_l2: bool = False,
    auto_adopt_l3: bool = False,
    auto_adopt_judgments: bool = False,
) -> dict[str, Any]:
    """Run nightly agent-loop preview, optionally applying the light lane.

    ``apply_light`` is intentionally narrow: only the light lane's existing
    deterministic auto primitives are executed, through the same alchemy
    receipt path used by the CLI.

    ``auto_adopt_l1`` / ``auto_adopt_l2`` / ``auto_adopt_l3`` enable silent
    auto-adoption of L1 semantic candidates, L2 machine-memory actions, and
    L3 prompt/policy/schema proposals. All write receipts enabling revert.

    ``auto_adopt_judgments`` enables LLM-powered counter-evidence review.
    """

    generated_at = utc_now()
    base: dict[str, Any] = {
        "status": "ok",
        "generated_at": generated_at,
        "mode": "observe_dry_run_and_light_apply" if apply_light else "observe_and_dry_run",
        "dry_run": not apply_light,
        "side_effects_allowed": bool(apply_light),
        "scope": scope,
    }
    try:
        signals_result = collect_signals(root)
        observe_result = write_planner_log(root, mode="observe_only")
        execute_result = write_planner_log(root, mode="execute")
        auto_preview = _build_auto_preview(root, scope=scope, lanes=lanes)
        auto_apply = _build_light_auto_apply(root, scope=scope) if apply_light else None
        l1_result = _build_auto_adopt_l1(root) if auto_adopt_l1 else None
        l2_result = _build_auto_adopt_l2(root) if auto_adopt_l2 else None
        l3_result = _build_auto_adopt_l3(root) if auto_adopt_l3 else None
        j_result = _build_auto_adopt_judgments(root) if auto_adopt_judgments else None
    except Exception as exc:  # noqa: BLE001 - preview failure must be surfaced in nightly state
        return {
            **base,
            "status": "failed",
            "error": str(exc),
            "error_type": type(exc).__name__,
        }

    auto_adopt_results = [item for item in (l1_result, l2_result, l3_result, j_result) if isinstance(item, dict)]
    if any(item.get("degraded") is True for item in auto_adopt_results):
        base["status"] = "degraded"

    return {
        **base,
        "signals": _signal_counts(signals_result),
        "planner": {
            "observe": _planner_counts(observe_result),
            "execute": _planner_counts(execute_result),
        },
        "auto_preview": auto_preview,
        **({"auto_apply": auto_apply} if auto_apply is not None else {}),
        **({"auto_adopt_l1": l1_result} if l1_result is not None else {}),
        **({"auto_adopt_l2": l2_result} if l2_result is not None else {}),
        **({"auto_adopt_l3": l3_result} if l3_result is not None else {}),
        **({"auto_adopt_judgments": j_result} if j_result is not None else {}),
    }


def attach_agent_loop_to_nightly_state(root: Path, state: dict[str, Any], agent_loop: dict[str, Any]) -> dict[str, Any]:
    """Persist ``agent_loop`` inside nightly-health and return the updated state."""

    path = nightly_health_state_path(root)
    latest_state = state
    if path.exists():
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(candidate, dict):
                latest_state = candidate
        except (TypeError, json.JSONDecodeError):
            latest_state = state
    if state.get("llm_used"):
        latest_state = {**latest_state, "llm_used": True}
    updated = {**latest_state, "agent_loop": agent_loop}
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


def _build_light_auto_apply(root: Path, *, scope: str) -> dict[str, Any]:
    from .runner.alchemy import run_alchemy_auto

    result = run_alchemy_auto(
        root,
        apply=True,
        lanes=["light"],
        scope=scope,
        note="nightly unattended light-lane maintenance",
        allow_current_writer_lock=True,
    )
    return _auto_apply_summary(result)


def _auto_apply_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(result.get("status") or ""),
        "mode": str(result.get("mode") or ""),
        "dry_run": bool(result.get("dry_run", False)),
        "side_effects_allowed": bool(result.get("side_effects_allowed", False)),
        "scope": str(result.get("scope") or ""),
        "decision_mode": str(result.get("decision_mode") or ""),
        "lanes": [str(item) for item in result.get("lanes", []) if isinstance(item, str)],
        "requested_primitives": [
            str(item) for item in result.get("requested_primitives", []) if isinstance(item, str)
        ],
        "applied_count": int(result.get("applied_count") or 0),
        "skipped_count": int(result.get("skipped_count") or 0),
        "lane_results": _auto_apply_lane_summaries(result.get("lane_results", [])),
    }


def _auto_apply_lane_summaries(lane_results: Any) -> list[dict[str, Any]]:
    if not isinstance(lane_results, list):
        return []
    summaries: list[dict[str, Any]] = []
    for item in lane_results:
        if not isinstance(item, dict):
            continue
        apply_result = item.get("apply_result") if isinstance(item.get("apply_result"), dict) else {}
        primitive_results = apply_result.get("primitive_results") if isinstance(apply_result, dict) else []
        summaries.append(
            {
                "lane": str(item.get("lane") or ""),
                "status": str(item.get("status") or ""),
                "reason": str(item.get("reason") or ""),
                "selected_primitives": [
                    str(primitive)
                    for primitive in item.get("selected_primitives", [])
                    if isinstance(primitive, str)
                ],
                "primitive_receipts": [
                    str(result.get("receipt_path") or "")
                    for result in primitive_results
                    if isinstance(result, dict) and result.get("receipt_path")
                ]
                if isinstance(primitive_results, list)
                else [],
            }
        )
    return summaries


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


__all__ = [
    "attach_agent_loop_to_nightly_state",
    "run_nightly_agent_loop",
    "run_nightly_agent_loop_preview",
]


def _build_auto_adopt_l1(root: Path) -> dict[str, Any]:
    from .runner.auto_adopt import auto_adopt_l1

    try:
        result = auto_adopt_l1(root)
        if result.get("degraded") is True or result.get("error"):
            result["degraded"] = True
        return result
    except Exception as exc:
        return {"level": "L1", "applied": False, "error": str(exc), "error_type": type(exc).__name__, "degraded": True}


def _build_auto_adopt_l2(root: Path) -> dict[str, Any]:
    from .runner.auto_adopt import auto_adopt_l2

    try:
        result = auto_adopt_l2(root)
        if result.get("degraded") is True or result.get("error"):
            result["degraded"] = True
        return result
    except Exception as exc:
        return {"level": "L2", "applied": False, "error": str(exc), "error_type": type(exc).__name__, "degraded": True}


def _build_auto_adopt_l3(root: Path) -> dict[str, Any]:
    from .runner.auto_adopt import auto_adopt_l3

    try:
        result = auto_adopt_l3(root)
        if result.get("degraded") is True or result.get("error"):
            result["degraded"] = True
        return result
    except Exception as exc:
        return {"level": "L3", "applied": False, "error": str(exc), "error_type": type(exc).__name__, "degraded": True}


def _build_auto_adopt_judgments(root: Path) -> dict[str, Any]:
    from .runner.auto_adopt import auto_adopt_judgments
    from .runner.clients import create_client

    try:
        client = create_client(root, timeout_seconds=180)
        result = auto_adopt_judgments(root, client, limit=5)
        if result.get("degraded") is True or result.get("error"):
            result["degraded"] = True
        return result
    except Exception as exc:
        return {"level": "Judgment", "applied": False, "error": str(exc), "error_type": type(exc).__name__, "degraded": True}
