"""Alchemy lane and auto-scheduler orchestration."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from aiwiki import autonomy_policy
from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH
from aiwiki.execution.paths import execution_receipt_history_path
from aiwiki.render.paths import execution_receipt_path
from aiwiki.runner import alchemy_support as support
from aiwiki.utils.path import relative_path
from aiwiki.utils.time import utc_now

ApplyPrimitive = Callable[..., dict[str, Any]]
GlobalPrimitive = Callable[[Path], dict[str, Any]]


def run_lane_dry_run(
    root: Path,
    *,
    lane: str,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    allow_current_writer_lock: bool = False,
) -> dict[str, Any]:
    from aiwiki.planner import preview_alchemy_lane

    return preview_alchemy_lane(
        root,
        lane=lane,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        allow_current_writer_lock=allow_current_writer_lock,
    )


def run_lane_apply(
    root: Path,
    *,
    lane: str,
    scope: str,
    action_ids: list[str] | None = None,
    primitives: list[str] | None = None,
    note: str | None = None,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    allow_current_writer_lock: bool = False,
    deps: dict[str, Any],
) -> dict[str, Any]:
    from aiwiki.planner import preview_alchemy_lane

    reason = autonomy_policy.disabled_reason(root, "disable_lane_apply")
    if reason is not None:
        return {
            "status": "skipped",
            "flag": "disable_lane_apply",
            "reason": reason,
            "lane": lane,
            "scope": scope,
        }

    normalized_action_ids = [item.strip() for item in (action_ids or []) if item.strip()]
    normalized_primitives = support.normalize_lane_primitives(primitives or [])
    if not normalized_action_ids and not normalized_primitives:
        raise ValueError("alchemy lane --apply requires at least one --action-id or --primitive")

    plan = preview_alchemy_lane(
        root,
        lane=lane,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        allow_current_writer_lock=True,
    )
    plan = support.normalize_preview_lock_status(plan)
    status = str(plan.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy lane apply requires an ok dry-run plan (got {status})")
    if int(plan.get("selected_count") or 0) <= 0:
        raise RuntimeError("alchemy lane apply requires a non-empty dry-run plan")

    lane_name = str(plan.get("lane") or lane)
    plan_scope = str(plan.get("scope") or scope)
    append_lane_runtime_event(
        root,
        event_type="alchemy-lane-started",
        lane=lane_name,
        scope=plan_scope,
        action_ids=normalized_action_ids,
        primitives=normalized_primitives,
        plan=plan,
        status="started",
        deps=deps,
    )
    primitive_results = [
        run_receipted_lane_primitive(
            root,
            lane=lane_name,
            scope=plan_scope,
            primitive=primitive,
            plan=plan,
            note=note,
            planner_log_path=planner_log_path,
            signals_path=signals_path,
            decision_mode=decision_mode,
            max_signals=max_signals,
            max_pages=max_pages,
            max_tokens=max_tokens,
            deps=deps,
        )
        for primitive in normalized_primitives
    ]
    apply_result = None
    if normalized_action_ids:
        apply_result = deps["apply_machine_memory_actions_batch"](
            root,
            normalized_action_ids,
            note=note or f"alchemy {lane} apply for scope {scope}",
            dry_run=False,
        )
    append_lane_runtime_event(
        root,
        event_type="alchemy-lane-completed",
        lane=lane_name,
        scope=plan_scope,
        action_ids=normalized_action_ids,
        primitives=normalized_primitives,
        plan=plan,
        status="completed",
        primitive_results=primitive_results,
        apply_result=apply_result,
        deps=deps,
    )
    return {
        "status": "applied",
        "lane": lane_name,
        "scope": plan_scope,
        "action_ids": normalized_action_ids,
        "primitives": normalized_primitives,
        "plan": plan,
        "primitive_results": primitive_results,
        "apply_result": apply_result,
    }


def run_auto(
    root: Path,
    *,
    apply: bool = False,
    lanes: list[str] | None = None,
    scope: str = "all",
    primitives: list[str] | None = None,
    note: str | None = None,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    allow_current_writer_lock: bool = False,
    lane_dry_run_runner: Callable[..., dict[str, Any]],
    lane_apply_runner: Callable[..., dict[str, Any]],
    deps: dict[str, Any],
) -> dict[str, Any]:
    normalize_auto_lanes = deps.get("normalize_auto_lanes", support.normalize_auto_lanes)
    normalize_lane_primitives = deps.get("normalize_lane_primitives", support.normalize_lane_primitives)
    auto_primitives_for_lane = deps.get("auto_primitives_for_lane", support.auto_primitives_for_lane)
    auto_skip_reason = deps.get("auto_skip_reason", support.auto_skip_reason)
    normalized_lanes = normalize_auto_lanes(lanes or ["heavy", "light"])
    requested_primitives = normalize_lane_primitives(primitives or []) if primitives else []
    lane_results: list[dict[str, Any]] = []
    applied_results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for lane in normalized_lanes:
        plan = lane_dry_run_runner(
            root,
            lane=lane,
            scope=scope,
            planner_log_path=planner_log_path,
            signals_path=signals_path,
            decision_mode="execute",
            max_signals=max_signals,
            max_pages=max_pages,
            max_tokens=max_tokens,
            allow_current_writer_lock=True,
        )
        plan = support.normalize_preview_lock_status(plan)
        selected_primitives = auto_primitives_for_lane(lane, plan, requested_primitives=requested_primitives)
        lane_result: dict[str, Any] = {
            "lane": lane,
            "scope": scope,
            "plan": plan,
            "selected_primitives": selected_primitives,
        }
        skip_reason = auto_skip_reason(plan, selected_primitives)
        if skip_reason:
            lane_result["status"] = "skipped"
            lane_result["reason"] = skip_reason
            skipped.append({"lane": lane, "reason": skip_reason})
        elif apply:
            apply_result = lane_apply_runner(
                root,
                lane=lane,
                scope=scope,
                primitives=selected_primitives,
                note=note or "alchemy auto scheduler",
                planner_log_path=planner_log_path,
                signals_path=signals_path,
                decision_mode="execute",
                max_signals=max_signals,
                max_pages=max_pages,
                max_tokens=max_tokens,
                allow_current_writer_lock=allow_current_writer_lock,
            )
            lane_result["status"] = "applied"
            lane_result["apply_result"] = apply_result
            applied_results.append(apply_result)
        else:
            lane_result["status"] = "ready"
        lane_results.append(lane_result)

    if apply:
        append_auto_runtime_event(
            root,
            scope=scope,
            lanes=normalized_lanes,
            primitives=requested_primitives,
            lane_results=lane_results,
            applied_results=applied_results,
            skipped=skipped,
            deps=deps,
        )

    return {
        "status": "applied" if apply and applied_results else ("noop" if apply else "preview"),
        "mode": "apply" if apply else "dry_run",
        "dry_run": not apply,
        "side_effects_allowed": apply,
        "scope": scope,
        "decision_mode": "execute",
        "lanes": normalized_lanes,
        "requested_primitives": requested_primitives,
        "applied_count": len(applied_results),
        "skipped_count": len(skipped),
        "lane_results": lane_results,
    }


def append_auto_runtime_event(
    root: Path,
    *,
    scope: str,
    lanes: list[str],
    primitives: list[str],
    lane_results: list[dict[str, Any]],
    applied_results: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    deps: dict[str, Any],
) -> None:
    utc_now_func = deps.get("utc_now", utc_now)
    deps["append_runtime_history"](
        root,
        support.alchemy_auto_runtime_event_payload(
            scope=scope,
            lanes=lanes,
            primitives=primitives,
            lane_results=lane_results,
            applied_results=applied_results,
            skipped=skipped,
            recorded_at=utc_now_func(),
        ),
    )


def append_lane_runtime_event(
    root: Path,
    *,
    event_type: str,
    lane: str,
    scope: str,
    action_ids: list[str],
    primitives: list[str],
    plan: dict[str, Any],
    status: str,
    deps: dict[str, Any],
    primitive_results: list[dict[str, Any]] | None = None,
    apply_result: dict[str, Any] | None = None,
) -> None:
    utc_now_func = deps.get("utc_now", utc_now)
    event = support.alchemy_lane_runtime_event_payload(
        event_type=event_type,
        lane=lane,
        scope=scope,
        action_ids=action_ids,
        primitives=primitives,
        plan=plan,
        status=status,
        primitive_results=primitive_results,
        apply_result=apply_result,
        recorded_at=utc_now_func(),
    )
    try:
        deps["append_runtime_history"](root, event)
    except Exception as exc:
        logger = deps.get("logger")
        if not isinstance(logger, logging.Logger):
            logger = logging.getLogger(__name__)
        logger.warning("alchemy lane runtime-history append failed for %s:%s:%s: %s", lane, scope, event_type, exc)


def scoped_primitive_result(primitive: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "primitive": primitive,
        "trace_id": str(result.get("trace_id") or ""),
        "audit_path": str(result.get("audit_path") or ""),
        "receipt_path": str(result.get("receipt_path") or ""),
        "result": result,
    }


def run_receipted_lane_primitive(
    root: Path,
    *,
    lane: str,
    scope: str,
    primitive: str,
    plan: dict[str, Any],
    note: str | None,
    deps: dict[str, Any],
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    plan_step = support.lane_primitive_plan_step(plan, primitive)
    if plan_step is None:
        raise RuntimeError(f"primitive {primitive!r} is not present in the dry-run plan for lane {lane!r}")
    if plan_step.get("apply_supported") is not True:
        blocker = str(plan_step.get("apply_blocker") or "not_apply_supported")
        raise RuntimeError(
            f"primitive {primitive!r} is not apply-supported in the dry-run plan for lane {lane!r}: {blocker}"
        )

    scoped_apply = deps.get(f"{primitive}_apply")
    if primitive in {"review", "distill", "propose"} and callable(scoped_apply):
        return scoped_primitive_result(
            primitive,
            scoped_apply(
                root,
                scope=scope,
                planner_log_path=planner_log_path,
                signals_path=signals_path,
                decision_mode=decision_mode,
                max_signals=max_signals,
                max_pages=max_pages,
                max_tokens=max_tokens,
                note=note,
            ),
        )

    scope_plan = support.lane_primitive_scope(primitive=primitive, scope=scope)
    requested_scope = scope_plan["requested_scope"]
    effective_scope = scope_plan["effective_scope"]
    scope_downgraded_from = scope_plan["scope_downgraded_from"]
    if scope_downgraded_from:
        logger = deps.get("logger")
        if not isinstance(logger, logging.Logger):
            logger = logging.getLogger(__name__)
        logger.warning(
            "alchemy lane primitive %r runs globally; downgrading requested scope %r to 'all' "
            "(no per-scope filter implementation)",
            primitive,
            scope,
        )

    primitive_runner = deps.get(f"{primitive}_runner")
    if not callable(primitive_runner):  # pragma: no cover - guarded by normalize_lane_primitives
        raise ValueError(f"unsupported alchemy lane primitive: {primitive}")
    result = primitive_runner(root)

    utc_now_func = deps.get("utc_now", utc_now)
    applied_at = utc_now_func()
    action_id = support.unique_lane_primitive_action_id(root, lane=lane, primitive=primitive, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    history_path = execution_receipt_history_path(root)
    history_size_before = history_path.stat().st_size if history_path.exists() else 0
    audit_jsonl_path = root / AUDIT_STREAM_PATH
    audit_size_before = audit_jsonl_path.stat().st_size if audit_jsonl_path.exists() else 0
    receipt_rel = relative_path(root, receipt_path)
    receipt = support.lane_primitive_receipt_payload(
        lane=lane,
        primitive=primitive,
        plan=plan,
        result=result,
        action_id=action_id,
        applied_at=applied_at,
        receipt_path=receipt_rel,
        audit_path=audit_path,
        note=note or "",
        requested_scope=requested_scope,
        effective_scope=effective_scope,
        scope_downgraded_from=scope_downgraded_from,
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        deps["atomic_write_text"](
            receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        deps["append_execution_receipt_history"](root, receipt)
    except Exception as tx_exc:
        try:
            if history_path.exists():
                deps["durable_truncate"](history_path, history_size_before)
            if audit_jsonl_path.exists():
                deps["durable_truncate"](audit_jsonl_path, audit_size_before)
            receipt_path.unlink(missing_ok=True)
        except Exception as rollback_exc:
            raise deps["receipt_half_write_error_cls"](
                f"lane primitive receipt rollback failed for {lane}:{primitive}: tx_error={tx_exc}; "
                f"rollback_error={rollback_exc}"
            ) from rollback_exc
        raise deps["receipt_error_cls"](
            f"lane primitive receipt persistence failed for {lane}:{primitive}; mutation rolled back"
        ) from tx_exc
    return {
        "primitive": primitive,
        "trace_id": str(receipt.get("trace_id") or ""),
        "audit_path": audit_path,
        "receipt_path": receipt_rel,
        "result": result,
    }
