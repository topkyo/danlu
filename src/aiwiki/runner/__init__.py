"""LLM-backed execution helpers for compile, ask, and lint workflows."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiwiki.app_compile import (
    ask_question,
    compile_wiki,
    lint_wiki,
    nightly_health,
    promote_recurring_outputs,
    write_nightly_health,
)
from aiwiki.app_content import (
    concept_summary_is_placeholder,
    placeholder_concept_slugs,
)
from aiwiki.app_memory import store_concept_rewrite_candidate
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_shell import rewrite_recovery_payload_for_paths
from aiwiki.app_state import append_runtime_history, load_machine_memory, load_manifest
from aiwiki.app_utils import (
    parse_frontmatter,
    relative_path,
    render_frontmatter,
    runtime_write_operation,
    sha256_bytes,
    slugify,
    strip_frontmatter,
    utc_now,
)
from aiwiki.llm import (
    CompletionResult,
    LLMError,
    classify_backend_error,
)
from aiwiki.runner.alchemy import (  # noqa: F401
    run_alchemy_demote,
    run_alchemy_distill,
    run_alchemy_distill_apply,
    run_alchemy_distill_preview,
    run_alchemy_finalize,
    run_alchemy_judge_apply,
    run_alchemy_judge_preview,
    run_alchemy_judge_proposal_apply,
    run_alchemy_judge_propose,
    run_alchemy_legacy_migration_apply,
    run_alchemy_legacy_migration_preview,
    run_alchemy_promote,
    run_alchemy_propose_apply,
    run_alchemy_propose_preview,
    run_alchemy_revert,
    run_alchemy_review_apply,
    run_alchemy_review_preview,
    run_alchemy_start,
    run_alchemy_superseded_cleanup_apply,
    run_alchemy_superseded_cleanup_preview,
)
from aiwiki.runner.clients import (  # noqa: F401
    _append_fallback_stage,
    _client_backend_name,
    _client_backend_requested,
    _client_model_name,
    _client_selected_model_name,
    _fallback_stage_label,
    _fallback_to_next_model,
    create_client,
    llm_probe,
    llm_status,
)
from aiwiki.runner.commands import (  # noqa: F401
    run_audit_backfill,
    run_audit_preview,
    run_demote,
    run_l3_proposal_apply,
    run_l3_proposal_create,
    run_l3_proposal_generate,
    run_l3_proposal_generation_preview,
    run_l3_proposal_list,
    run_l3_proposal_reject,
    run_l3_proposal_revert,
    run_planner_log_list,
    run_planner_log_rollback,
    run_planner_log_rollback_preview,
    run_promote,
    run_protocol_learn_add,
    run_protocol_learn_age,
    run_protocol_learn_archive,
    run_protocol_learn_demote,
    run_protocol_learn_list,
    run_protocol_learn_revert_activate,
    run_protocol_learn_show,
    run_protocol_learn_supersede,
    run_protocol_learn_verify,
    run_signals_list,
    run_signals_show,
)
from aiwiki.runner.interfaces import SupportsComplete  # noqa: F401
from aiwiki.runner.prompts import (  # noqa: F401
    ASK_INDEX_PAGES_BASE,
    ASK_INDEX_PAGES_BY_FORMAT,
    ASK_PROMPT_PROFILES,
    ASK_PROTOCOL_PAGE_NAMES_BASE,
    ASK_PROTOCOL_PAGE_NAMES_BY_FORMAT,
    COMPILE_PROMPT_PROFILES,
    LINT_PROMPT_PROFILES,
    _ask_prompt_profile,
    _build_ask_prompt,
    _build_compile_prompt,
    _build_concept_compile_prompt,
    _build_lint_prompt,
    _compile_prompt_profile,
    _context_budget,
    _extract_related_concept_slugs,
    _fit_log_prompt_section,
    _fit_prompt_section,
    _initial_ask_prompt_profile,
    _initial_compile_prompt_profile,
    _initial_lint_prompt_profile,
    _lean_ask_prompt_profile,
    _lint_prompt_profile,
    _load_prompt,
    _normalize_markdown,
    _protocol_context,
    _read_context,
    _render_machine_query,
    _retry_ask_prompt_profile,
    _retry_compile_prompt_profile,
    _retry_lint_prompt_profile,
    _rewrite_candidate_record,
    _rewrite_candidate_slugs,
    _schema_context,
    _select_ask_index_pages,
    _select_ask_protocol_pages,
    _select_initial_ask_prompt_profile,
    _system_prompt,
    _validate_concept_page,
    _validate_output_markdown,
    _validate_source_page,
)
from aiwiki.runner.receipts import (  # noqa: F401
    _append_jsonl_log,
    _append_llm_receipt,
    _append_llm_receipt_and_log,
    _append_log,
    _build_llm_audit,
    _empty_llm_audit,
    _infer_delivery_mode,
    _llm_audit_from_result,
    _merge_llm_audits,
    _next_jsonl_line_number,
)
from aiwiki.runner.workflows import (  # noqa: F401
    RUN_ASK_FALLBACK_ERROR_KINDS,
    RUN_ASK_FRONTDOOR_EVENT,
    _reinject_candidate_frontmatter,
    run_ask,
    run_compile,
    run_lint,
    run_nightly,
)


@runtime_write_operation
def auto_process_once(
    root: Path,
    client: SupportsComplete | None = None,
    compile_limit: int = 5,
    deterministic_only: bool = False,
    semantic_lint: bool = True,
) -> dict[str, Any]:
    ensure_layout(root)
    llm_enabled = bool(client) or (not deterministic_only and llm_status()["configured"])
    llm_failed = False

    if llm_enabled and not deterministic_only:
        try:
            compile_result = run_compile(root, client=client, limit=compile_limit)
        except Exception as exc:
            logging.getLogger("aiwiki").warning("LLM compile failed, falling back to deterministic: %s", exc)
            llm_failed = True
            compile_result = {
                "compile": compile_wiki(root),
                "updated_pages": [],
                "pending_pages": _pending_summary_count(root),
                "skipped_pages": 0,
            }
    else:
        compile_result = {
            "compile": compile_wiki(root),
            "updated_pages": [],
            "pending_pages": _pending_summary_count(root),
            "skipped_pages": 0,
        }

    if semantic_lint and llm_enabled and not deterministic_only and not llm_failed:
        try:
            lint_result = run_lint(root, client=client)
        except Exception as exc:
            logging.getLogger("aiwiki").warning("LLM lint failed, falling back to deterministic: %s", exc)
            llm_failed = True
            lint_result = {
                "deterministic": lint_wiki(root),
                "semantic_report": "",
            }
    else:
        lint_result = {
            "deterministic": lint_wiki(root),
            "semantic_report": "",
        }

    snapshot = inbox_snapshot(root)
    actually_used_llm = bool(llm_enabled and not deterministic_only and not llm_failed)
    result = {
        "processed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "llm_used": actually_used_llm,
        "llm_fallback": llm_failed,
        "compile": compile_result,
        "lint": lint_result,
        "inbox_snapshot": snapshot,
    }
    _write_automation_state(root, result)
    _append_log(
        root,
        {
            "event": "auto-process",
            "llm_used": result["llm_used"],
            "llm_fallback": llm_failed,
            "compile_limit": compile_limit,
            "inbox_digest": snapshot["digest"],
        },
    )
    return result

def run_alchemy_lane_dry_run(
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
    )


def run_alchemy_lane_apply(
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
) -> dict[str, Any]:
    from aiwiki.app_compile import apply_machine_memory_actions_batch
    from aiwiki.planner import preview_alchemy_lane

    normalized_action_ids = [item.strip() for item in (action_ids or []) if item.strip()]
    normalized_primitives = _normalize_lane_primitives(primitives or [])
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
    )
    status = str(plan.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy lane apply requires an ok dry-run plan (got {status})")
    if int(plan.get("selected_count") or 0) <= 0:
        raise RuntimeError("alchemy lane apply requires a non-empty dry-run plan")

    _append_alchemy_lane_runtime_event(
        root,
        event_type="alchemy-lane-started",
        lane=str(plan.get("lane") or lane),
        scope=str(plan.get("scope") or scope),
        action_ids=normalized_action_ids,
        primitives=normalized_primitives,
        plan=plan,
        status="started",
    )
    primitive_results = [
        _run_receipted_lane_primitive(
            root,
            lane=str(plan.get("lane") or lane),
            scope=str(plan.get("scope") or scope),
            primitive=primitive,
            plan=plan,
            note=note,
            planner_log_path=planner_log_path,
            signals_path=signals_path,
            decision_mode=decision_mode,
            max_signals=max_signals,
            max_pages=max_pages,
            max_tokens=max_tokens,
        )
        for primitive in normalized_primitives
    ]
    apply_result = None
    if normalized_action_ids:
        apply_result = apply_machine_memory_actions_batch(
            root,
            normalized_action_ids,
            note=note or f"alchemy {lane} apply for scope {scope}",
            dry_run=False,
        )
    _append_alchemy_lane_runtime_event(
        root,
        event_type="alchemy-lane-completed",
        lane=str(plan.get("lane") or lane),
        scope=str(plan.get("scope") or scope),
        action_ids=normalized_action_ids,
        primitives=normalized_primitives,
        plan=plan,
        status="completed",
        primitive_results=primitive_results,
        apply_result=apply_result,
    )
    return {
        "status": "applied",
        "lane": str(plan.get("lane") or lane),
        "scope": str(plan.get("scope") or scope),
        "action_ids": normalized_action_ids,
        "primitives": normalized_primitives,
        "plan": plan,
        "primitive_results": primitive_results,
        "apply_result": apply_result,
    }


def run_alchemy_auto(
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
) -> dict[str, Any]:
    normalized_lanes = _normalize_auto_lanes(lanes or ["heavy", "light"])
    requested_primitives = _normalize_lane_primitives(primitives or []) if primitives else []
    lane_results: list[dict[str, Any]] = []
    applied_results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for lane in normalized_lanes:
        plan = run_alchemy_lane_dry_run(
            root,
            lane=lane,
            scope=scope,
            planner_log_path=planner_log_path,
            signals_path=signals_path,
            decision_mode="execute",
            max_signals=max_signals,
            max_pages=max_pages,
            max_tokens=max_tokens,
        )
        selected_primitives = _auto_primitives_for_lane(lane, plan, requested_primitives=requested_primitives)
        lane_result: dict[str, Any] = {
            "lane": lane,
            "scope": scope,
            "plan": plan,
            "selected_primitives": selected_primitives,
        }
        skip_reason = _auto_skip_reason(plan, selected_primitives)
        if skip_reason:
            lane_result["status"] = "skipped"
            lane_result["reason"] = skip_reason
            skipped.append({"lane": lane, "reason": skip_reason})
        elif apply:
            apply_result = run_alchemy_lane_apply(
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
            )
            lane_result["status"] = "applied"
            lane_result["apply_result"] = apply_result
            applied_results.append(apply_result)
        else:
            lane_result["status"] = "ready"
        lane_results.append(lane_result)

    if apply:
        _append_alchemy_auto_runtime_event(
            root,
            scope=scope,
            lanes=normalized_lanes,
            primitives=requested_primitives,
            lane_results=lane_results,
            applied_results=applied_results,
            skipped=skipped,
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


def _normalize_auto_lanes(lanes: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in lanes:
        lane = item.strip().lower()
        if lane not in {"heavy", "light"}:
            raise ValueError(f"unsupported alchemy auto lane: {item}")
        if lane in seen:
            continue
        seen.add(lane)
        normalized.append(lane)
    if not normalized:
        raise ValueError("alchemy auto requires at least one lane")
    return normalized


def _auto_primitives_for_lane(
    lane: str,
    plan: dict[str, Any],
    *,
    requested_primitives: list[str],
) -> list[str]:
    defaults = {"heavy": ["compile", "lint"], "light": ["compile", "lint", "nightly"]}[lane]
    wanted = requested_primitives or defaults
    auto_supported_primitives = {"compile", "lint", "nightly"}
    if requested_primitives and lane == "heavy":
        auto_supported_primitives.add("distill")
        auto_supported_primitives.add("review")
        auto_supported_primitives.add("propose")
    supported = {
        str(item.get("primitive") or "")
        for item in plan.get("primitive_plan", [])
        if (
            isinstance(item, dict)
            and item.get("apply_supported") is True
            and str(item.get("primitive") or "") in auto_supported_primitives
        )
    }
    return [primitive for primitive in wanted if primitive in supported]


def _auto_skip_reason(plan: dict[str, Any], selected_primitives: list[str]) -> str:
    status = str(plan.get("status") or "")
    if status != "ok":
        return f"plan_{status or 'unknown'}"
    if int(plan.get("selected_count") or 0) <= 0:
        return "empty_execute_plan"
    if not selected_primitives:
        return "no_apply_supported_primitives"
    return ""


def _append_alchemy_auto_runtime_event(
    root: Path,
    *,
    scope: str,
    lanes: list[str],
    primitives: list[str],
    lane_results: list[dict[str, Any]],
    applied_results: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> None:
    trace_ids: set[str] = set()
    for lane_result in lane_results:
        plan = lane_result.get("plan")
        if not isinstance(plan, dict):
            continue
        trace_ids.update(_lane_receipt_trace_ids(plan))
    sorted_trace_ids = sorted(trace_ids)
    append_runtime_history(
        root,
        {
            "event_type": "alchemy-auto-scheduler",
            "recorded_at": utc_now(),
            "status": "completed",
            "scope": scope,
            "lanes": lanes,
            "requested_primitives": primitives,
            "applied_count": len(applied_results),
            "skipped_count": len(skipped),
            "skipped": skipped,
            "trace_id": sorted_trace_ids[0] if sorted_trace_ids else "",
            "trace_ids": sorted_trace_ids,
            "subject_kind": "alchemy_auto_scheduler",
            "subject_id": scope,
        },
    )


def _append_alchemy_lane_runtime_event(
    root: Path,
    *,
    event_type: str,
    lane: str,
    scope: str,
    action_ids: list[str],
    primitives: list[str],
    plan: dict[str, Any],
    status: str,
    primitive_results: list[dict[str, Any]] | None = None,
    apply_result: dict[str, Any] | None = None,
) -> None:
    trace_ids = _lane_receipt_trace_ids(plan)
    event: dict[str, Any] = {
        "event_type": event_type,
        "recorded_at": utc_now(),
        "status": status,
        "lane": lane,
        "scope": scope,
        "action_ids": action_ids,
        "primitives": primitives,
        "selected_count": int(plan.get("selected_count") or 0),
        "trace_id": trace_ids[0] if trace_ids else "",
        "trace_ids": trace_ids,
        "subject_kind": "alchemy_lane",
        "subject_id": f"{lane}:{scope}",
    }
    if primitive_results is not None:
        event["primitive_count"] = len(primitive_results)
        event["primitive_receipts"] = [
            str(item.get("receipt_path") or "") for item in primitive_results if isinstance(item, dict) and item.get("receipt_path")
        ]
    if apply_result is not None:
        event["action_batch_receipt"] = str(apply_result.get("receipt_path") or apply_result.get("batch_receipt_path") or "")
    append_runtime_history(root, event)


def _string_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item.strip() for item in value if isinstance(item, str) and item.strip()})


def _markdown_cell(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|")


def _normalize_lane_primitives(primitives: list[str]) -> list[str]:
    allowed = {"compile", "distill", "lint", "nightly", "review", "propose"}
    normalized: list[str] = []
    seen: set[str] = set()
    for item in primitives:
        primitive = item.strip().lower()
        if not primitive:
            continue
        if primitive not in allowed:
            raise ValueError(f"unsupported alchemy lane primitive: {item}")
        if primitive in seen:
            continue
        seen.add(primitive)
        normalized.append(primitive)
    return normalized


def _run_receipted_lane_primitive(
    root: Path,
    *,
    lane: str,
    scope: str,
    primitive: str,
    plan: dict[str, Any],
    note: str | None,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    plan_step = _lane_primitive_plan_step(plan, primitive)
    if plan_step is None:
        raise RuntimeError(f"primitive {primitive!r} is not present in the dry-run plan for lane {lane!r}")
    if plan_step.get("apply_supported") is not True:
        blocker = str(plan_step.get("apply_blocker") or "not_apply_supported")
        raise RuntimeError(f"primitive {primitive!r} is not apply-supported in the dry-run plan for lane {lane!r}: {blocker}")

    if primitive == "review":
        result = run_alchemy_review_apply(
            root,
            scope=scope,
            planner_log_path=planner_log_path,
            signals_path=signals_path,
            decision_mode=decision_mode,
            max_signals=max_signals,
            max_pages=max_pages,
            max_tokens=max_tokens,
            note=note,
        )
        return {
            "primitive": primitive,
            "trace_id": str(result.get("trace_id") or ""),
            "audit_path": str(result.get("audit_path") or ""),
            "receipt_path": str(result.get("receipt_path") or ""),
            "result": result,
        }
    if primitive == "distill":
        result = run_alchemy_distill_apply(
            root,
            scope=scope,
            planner_log_path=planner_log_path,
            signals_path=signals_path,
            decision_mode=decision_mode,
            max_signals=max_signals,
            max_pages=max_pages,
            max_tokens=max_tokens,
            note=note,
        )
        return {
            "primitive": primitive,
            "trace_id": str(result.get("trace_id") or ""),
            "audit_path": str(result.get("audit_path") or ""),
            "receipt_path": str(result.get("receipt_path") or ""),
            "result": result,
        }
    if primitive == "propose":
        result = run_alchemy_propose_apply(
            root,
            scope=scope,
            planner_log_path=planner_log_path,
            signals_path=signals_path,
            decision_mode=decision_mode,
            max_signals=max_signals,
            max_pages=max_pages,
            max_tokens=max_tokens,
            note=note,
        )
        return {
            "primitive": primitive,
            "trace_id": str(result.get("trace_id") or ""),
            "audit_path": str(result.get("audit_path") or ""),
            "receipt_path": str(result.get("receipt_path") or ""),
            "result": result,
        }
    if primitive == "compile":
        result = compile_wiki(root)
    elif primitive == "lint":
        result = lint_wiki(root)
    elif primitive == "nightly":
        result = nightly_health(root)
    else:  # pragma: no cover - guarded by _normalize_lane_primitives
        raise ValueError(f"unsupported alchemy lane primitive: {primitive}")

    applied_at = utc_now()
    action_id = _unique_lane_primitive_action_id(root, lane=lane, primitive=primitive, applied_at=applied_at)
    from aiwiki.app_execution import append_execution_receipt_history
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.render.paths import execution_receipt_path

    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = _lane_receipt_trace_ids(plan)
    trace_id = trace_ids[0] if trace_ids else ""
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-lane",
        "applied_at": applied_at,
        "operation": "alchemy-lane-primitive",
        "action_id": action_id,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "title": f"Alchemy {lane} {primitive}",
        "status": "applied",
        "protocol": _first_plan_protocol(plan),
        "subject_kind": "alchemy_lane_primitive",
        "subject_id": f"{lane}:{scope}:{primitive}",
        "apply_mode": f"alchemy-{lane}-{primitive}",
        "note": note or "",
        "primary_path": _primary_result_path(result),
        "secondary_path": "",
        "receipt_path": relative_path(root, receipt_path),
        "lane": lane,
        "scope": scope,
        "primitive": primitive,
        "revert_supported": False,
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
        "source_plan": _lane_receipt_plan_summary(plan),
        "result_summary": _lane_receipt_result_summary(result),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    return {
        "primitive": primitive,
        "trace_id": trace_id,
        "audit_path": audit_path,
        "receipt_path": relative_path(root, receipt_path),
        "result": result,
    }


def _unique_lane_primitive_action_id(root: Path, *, lane: str, primitive: str, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-{lane}-{primitive}-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _lane_primitive_plan_step(plan: dict[str, Any], primitive: str) -> dict[str, Any] | None:
    for item in plan.get("primitive_plan", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("primitive") or "") == primitive:
            return item
    return None


def _first_plan_protocol(plan: dict[str, Any]) -> str:
    scope_preview = plan.get("scope_preview")
    if isinstance(scope_preview, dict):
        protocols = scope_preview.get("protocols")
        if isinstance(protocols, list) and protocols:
            return str(protocols[0])
    return ""


def _lane_receipt_trace_ids(plan: dict[str, Any]) -> list[str]:
    scope_preview = plan.get("scope_preview")
    if not isinstance(scope_preview, dict):
        return []
    trace_ids = scope_preview.get("trace_ids")
    if not isinstance(trace_ids, list):
        return []
    normalized = sorted({item.strip() for item in trace_ids if isinstance(item, str) and item.strip()})
    return normalized


def _primary_result_path(result: dict[str, Any]) -> str:
    for key in ("state_path", "path", "semantic_report"):
        value = result.get(key)
        if isinstance(value, str) and value:
            return value
    repair_backlog = result.get("repair_backlog")
    if isinstance(repair_backlog, str) and repair_backlog:
        return repair_backlog
    return ""


def _lane_receipt_plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane": str(plan.get("lane") or ""),
        "scope": str(plan.get("scope") or ""),
        "selected_count": int(plan.get("selected_count") or 0),
        "scope_preview": plan.get("scope_preview") if isinstance(plan.get("scope_preview"), dict) else {},
        "primitive_plan": list(plan.get("primitive_plan") or []),
    }


def _lane_receipt_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("state_path", "repair_backlog", "semantic_report", "llm_used"):
        if key in result:
            summary[key] = result[key]
    if "updated_source_pages" in result:
        summary["updated_source_pages_count"] = len(result.get("updated_source_pages") or [])
    if "updated_concept_pages" in result:
        summary["updated_concept_pages_count"] = len(result.get("updated_concept_pages") or [])
    if "counts" in result and isinstance(result.get("counts"), dict):
        summary["counts"] = result["counts"]
    return summary

def watch_inbox(
    root: Path,
    interval_seconds: float = 5.0,
    client: SupportsComplete | None = None,
    compile_limit: int = 5,
    deterministic_only: bool = False,
    semantic_lint: bool = True,
    process_initial: bool = True,
    max_cycles: int | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    processed_runs: list[dict[str, Any]] = []
    cycles = 0
    last_snapshot = inbox_snapshot(root)

    if process_initial:
        processed_runs.append(
            auto_process_once(
                root,
                client=client,
                compile_limit=compile_limit,
                deterministic_only=deterministic_only,
                semantic_lint=semantic_lint,
            )
        )
        last_snapshot = inbox_snapshot(root)

    while max_cycles is None or cycles < max_cycles:
        time.sleep(interval_seconds)
        cycles += 1
        current_snapshot = inbox_snapshot(root)
        if current_snapshot["digest"] == last_snapshot["digest"]:
            continue
        processed_runs.append(
            auto_process_once(
                root,
                client=client,
                compile_limit=compile_limit,
                deterministic_only=deterministic_only,
                semantic_lint=semantic_lint,
            )
        )
        last_snapshot = inbox_snapshot(root)

    return {
        "watch_cycles": cycles,
        "processed_runs": len(processed_runs),
        "last_result": processed_runs[-1] if processed_runs else None,
    }


def inbox_snapshot(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    files: list[dict[str, Any]] = []
    for path in sorted((root / "raw" / "inbox").glob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        files.append(
            {
                "path": relative_path(root, path),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    digest = sha256_bytes(json.dumps(files, sort_keys=True).encode("utf-8"))
    return {"digest": digest, "files": files}


def _pending_summary_count(root: Path) -> int:
    manifest = load_manifest(root)
    pending = 0
    for entry in manifest["entries"]:
        page = root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
            continue
        content = page.read_text(encoding="utf-8", errors="replace")
        if "Pending LLM summary." in content:
            pending += 1
    return pending


def _write_automation_state(root: Path, result: dict[str, Any]) -> None:
    ensure_layout(root)
    path = root / ".aiwiki" / "state" / "automation.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
