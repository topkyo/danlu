from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

from ..app_content import (
    action_priority_rank,
    action_status_rank,
    action_supports_low_risk_apply,
    action_transition_profile,
    archive_transition_profile,
    collect_aging_signals,
    collect_curated_pages,
    collect_recent_output_artifacts,
    curated_page_transition_profile,
    execution_bundle_path,
    execution_proposal_path,
    judgment_asset_attention_sort_key,
    judgment_asset_shell_record,
    judgment_asset_summary,
    knowledge_lifecycle_governance_summary,
    load_execution_receipt_history,
    review_queue,
    rewrite_proposal_status_rank,
    rewrite_transition_profile,
    summarize_runtime_event_for_shell,
    transition_profile,
    valid_curated_statuses,
)
from ..app_protocol import (
    ACTION_STATUSES,
    PROTOCOL_LIBRARY,
    REWRITE_PROPOSAL_STATUSES,
    ensure_layout,
    load_protocol_state,
)
from ..app_state import (
    DEFAULT_PROTOCOL,
    active_material_archive_entries,
    agent_workbench_path,
    domain_pilots_path,
    execution_audit_html_path,
    execution_audit_path,
    execution_center_html_path,
    execution_center_path,
    furnace_center_html_path,
    llm_receipt_log_path,
    load_archive_candidates_state,
    load_compile_state,
    load_concept_rewrite_state,
    load_json_document,
    load_knowledge_lifecycle_state,
    load_llm_receipt_history,
    load_machine_memory,
    load_manifest,
    load_material_archive_state,
    load_planner_state,
    load_query_route_telemetry,
    load_runtime_history,
    load_today_snooze_state,
    machine_memory_graph_html_path,
    nightly_health_state_path,
    output_packs_index_path,
    product_shell_html_path,
    review_center_html_path,
    run_log_path,
    shell_summary_path,
)
from ..app_types import ProtocolState, ShellSummary
from ..app_utils import (
    parse_frontmatter,
    relative_path,
    strip_frontmatter,
    tokenize,
    utc_now,
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from ..config import LLMConfig
from ..execution.l3_proposals import list_l3_proposals
from ..input_router import is_obsidian_open_link
from ..llm import classify_backend_error
from .controls import (
    rewrite_recovery_actions_for_controls,
    shell_execution_controls,
    shell_review_controls,
)
from .helpers import _build_llm_recovery_command, _first_non_empty
from .meta import (
    shell_capabilities,
    shell_curated_page_roots,
    shell_links,
    shell_protocol_state,
)
from .surfaces import (
    shell_dashboard,
    shell_drift_warnings,
    shell_latest_llm_run,
    shell_latest_shell_sync_run,
    shell_llm_health,
    shell_recent_receipts,
    shell_recent_runs,
    shell_suggested_next_actions,
)


def _load_drift_aging_state(root: Path) -> dict[str, Any]:
    from ..drift_scan import DRIFT_AGING_REL_PATH

    path = root / DRIFT_AGING_REL_PATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _build_knowledge_stats(
    memory: dict,
    compile_state: dict,
    decisions: list,
    judgments: list,
) -> dict:
    """Build knowledge base statistics for the Product Shell dashboard."""
    edges = memory.get("edges", {})
    edge_total = sum(len(v) for v in edges.values() if isinstance(v, list))
    causal_count = len(edges.get("concept_causal", [])) if isinstance(edges.get("concept_causal"), list) else 0
    return {
        "source_nodes": len(memory.get("source_nodes", [])),
        "concept_nodes": len(memory.get("concept_nodes", [])),
        "judgment_nodes": len(memory.get("judgment_nodes", [])),
        "term_index": len(memory.get("term_index", [])),
        "edge_total": edge_total,
        "concept_causal_edges": causal_count,
        "decisions": len(decisions),
        "judgments": len(judgments),
        "compile_sources": len(compile_state.get("sources", {})),
        "compile_concepts": len(compile_state.get("concepts", {})),
    }


def _build_recent_raw_inputs(root: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    try:
        events = load_runtime_history(root)
        raw_inputs: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            if str(event.get("event_type") or "") != "raw-added":
                continue
            stored_path = str(event.get("stored_path") or "")
            material_path = Path(stored_path)
            material_parts = material_path.parts
            if (
                not stored_path
                or material_path.is_absolute()
                or ".." in material_parts
                or len(material_parts) < 3
                or material_parts[0] != "raw"
                or material_parts[1] not in {"inbox", "assets"}
                or not (root / material_path).is_file()
            ):
                continue
            raw_inputs.append(
                {
                    "stored_path": stored_path,
                    "original_path": str(event.get("original_path") or ""),
                    "source_type": str(event.get("source_type") or ""),
                    "title": str(event.get("title") or ""),
                    "occurred_at": str(event.get("occurred_at") or ""),
                    "protocol": str(event.get("protocol") or ""),
                }
            )
        return list(reversed(raw_inputs))[:limit]
    except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError):
        return []


def _build_watcher_summary(root: Path) -> dict[str, Any]:
    state_path = root / ".aiwiki" / "state" / "automation.json"
    state = load_json_document(state_path)
    has_deterministic_flag = isinstance(state, dict) and "deterministic_only" in state
    deterministic_only = bool(state.get("deterministic_only")) if has_deterministic_flag else None
    if deterministic_only is True:
        mode = "deterministic-only"
    elif deterministic_only is False:
        mode = "llm-enabled"
    else:
        mode = "unknown-legacy"
    return {
        "available": bool(state_path.exists()),
        "state_path": relative_path(root, state_path),
        "processed_at": str(state.get("processed_at") or "") if isinstance(state, dict) else "",
        "last_run_mode": mode,
        "deterministic_only": deterministic_only,
        "llm_used": bool(state.get("llm_used", False)) if isinstance(state, dict) else False,
        "llm_fallback": bool(state.get("llm_fallback", False)) if isinstance(state, dict) else False,
        "compile_limit": int(state.get("compile_limit", 0) or 0) if isinstance(state, dict) else 0,
        "semantic_lint": bool(state.get("semantic_lint", False)) if isinstance(state, dict) else False,
        "default_service_mode": "deterministic-only",
        "service_env": "AIWIKI_WATCH_DETERMINISTIC_ONLY=1",
        "recovery_command": "./scripts/aiwiki-launcher.sh auto-once --deterministic-only",
        "note": (
            "Default watcher service only performs deterministic inbox processing; "
            "LLM enrichment belongs to explicit run-* or nightly paths."
        ),
    }


def _latest_run_nightly_receipt(root: Path) -> dict[str, Any]:
    for item in reversed(load_llm_receipt_history(root)):
        if isinstance(item, dict) and str(item.get("event") or "") == "run-nightly":
            return dict(item)
    return {}


def _latest_run_nightly_execution_receipt(root: Path) -> dict[str, Any]:
    for receipt in reversed(load_execution_receipt_history(root)):
        if isinstance(receipt, dict) and str(receipt.get("operation") or "") == "run-nightly":
            return dict(receipt)
    return {}


def _receipt_time(record: dict[str, Any]) -> str:
    for key in ("applied_at", "created_at", "generated_at", "updated_at"):
        value = record.get(key)
        if value:
            return str(value)
    return ""


def _build_nightly_summary(root: Path, nightly_state: dict[str, Any]) -> dict[str, Any]:
    llm_receipt = _latest_run_nightly_receipt(root)
    execution_receipt = _latest_run_nightly_execution_receipt(root)
    llm_status = str(llm_receipt.get("status") or "")
    stale_reason = ""
    if execution_receipt and llm_status in {"failed", "error", "blocked"}:
        stale_reason = "latest run-nightly LLM receipt failed; prior success receipt is not current proof"
    elif execution_receipt and llm_status == "success":
        llm_checked_at = _receipt_time(llm_receipt)
        execution_applied_at = _receipt_time(execution_receipt)
        if llm_checked_at and (not execution_applied_at or execution_applied_at < llm_checked_at):
            stale_reason = "latest run-nightly LLM receipt has no matching execution receipt proof"
    execution_receipt_stale = bool(stale_reason)
    error_text = _first_non_empty(llm_receipt, ["error", "failure_reason", "primary_error", "fallback_reason"])
    error_class = str(llm_receipt.get("error_class") or "") or (classify_backend_error(error_text) if error_text else "")
    recovery_command = _build_llm_recovery_command(llm_receipt) if llm_receipt and llm_status != "success" else ""
    return {
        "available": nightly_health_state_path(root).exists(),
        "generated_at": str(nightly_state.get("generated_at") or ""),
        "state_path": relative_path(root, nightly_health_state_path(root)),
        "llm_used": bool(nightly_state.get("llm_used", False)),
        "lint_counts": dict(nightly_state.get("lint", {}).get("counts", {})),
        "agent_loop": dict(nightly_state.get("agent_loop") or {})
        if isinstance(nightly_state.get("agent_loop"), dict)
        else {},
        "llm_receipt": {
            "available": bool(llm_receipt),
            "status": llm_status,
            "checked_at": str(llm_receipt.get("created_at") or ""),
            "receipt_path": relative_path(root, llm_receipt_log_path(root)) if llm_receipt else "",
            "backend_effective": str(llm_receipt.get("backend_effective") or llm_receipt.get("backend") or ""),
            "model_final": str(llm_receipt.get("model_final") or llm_receipt.get("model") or ""),
            "delivery_mode": str(llm_receipt.get("delivery_mode") or ""),
            "error_class": error_class,
            "recovery_command": recovery_command,
        },
        "execution_receipt": {
            "available": bool(execution_receipt) and not execution_receipt_stale,
            "status": "stale-after-failed-run-nightly"
            if execution_receipt_stale and llm_status in {"failed", "error", "blocked"}
            else "stale-after-unmatched-run-nightly-proof"
            if execution_receipt_stale
            else str(execution_receipt.get("status") or ""),
            "receipt_path": "" if execution_receipt_stale else str(execution_receipt.get("receipt_path") or ""),
            "target_file": "" if execution_receipt_stale else str(execution_receipt.get("target_file") or ""),
            "stale": execution_receipt_stale,
            "stale_receipt_path": str(execution_receipt.get("receipt_path") or "")
            if execution_receipt_stale
            else "",
            "stale_reason": stale_reason,
        },
        "recovery_command": recovery_command,
        "retention": {
            "policy": "archive-first",
            "delete_receipts_by_default": False,
            "delete_logs_by_default": False,
            "archive_candidate_state_path": ".aiwiki/state/archive-candidates.json",
            "note": (
                "Retention moves cold material through explicit archive/revert flows; "
                "receipts and logs are not deleted by default."
            ),
        },
    }


def build_shell_summary(root: Path, *, generated_at: str | None = None) -> ShellSummary:
    ensure_layout(root)
    generated_at = generated_at or utc_now()
    protocol_state = shell_protocol_state(root)
    llm_status = LLMConfig.status_from_env()
    decisions = collect_curated_pages(root, "decisions", "decision")
    judgments = collect_curated_pages(root, "judgments", "judgment")
    queue = review_queue(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    aging = collect_aging_signals(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    judgment_assets = judgment_asset_summary(
        decisions,
        judgments,
        active_protocol=protocol_state["active_protocol"],
    )
    compile_state = load_compile_state(root)
    knowledge_lifecycle = load_knowledge_lifecycle_state(root)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=protocol_state["active_protocol"],
    )
    memory = load_machine_memory(root)
    planner_state = load_planner_state(root)
    route_telemetry = _filter_shell_route_telemetry(load_query_route_telemetry(root))
    counter_evidence_scan = memory.get("health", {}).get("counter_evidence_scan", {})
    judgment_review_actions = memory.get("health", {}).get("judgment_review_actions", [])
    nightly_state = load_json_document(nightly_health_state_path(root))
    review_backlog_counts = {
        "pending_decisions": len(queue["pending_decisions"]),
        "pending_judgments": len(queue["pending_judgments"]),
        "overdue_reviews": len(aging["overdue"]),
        "escalation_candidates": len(aging["escalated"]),
        "counter_evidence_candidates": len(counter_evidence_scan.get("pages", []))
        if isinstance(counter_evidence_scan, dict)
        else 0,
        "judgment_review_actions": len(judgment_review_actions) if isinstance(judgment_review_actions, list) else 0,
        "concept_backlog": lifecycle_summary.get("counts", {}).get("concept_backlog", 0),
        "review_concepts": lifecycle_summary.get("counts", {}).get("review_concepts", 0),
        "revisit_concepts": lifecycle_summary.get("counts", {}).get("revisit_concepts", 0),
        "retired_concepts": lifecycle_summary.get("counts", {}).get("retired_concepts", 0),
        "machine_memory_actions": memory.get("health", {}).get("action_counts", {}).get("total", 0),
        "ready_actions": memory.get("health", {}).get("repair_plan", {}).get("counts", {}).get("ready", 0),
        "overdue_actions": len(memory.get("health", {}).get("overdue_actions", [])),
        "escalated_actions": len(memory.get("health", {}).get("escalated_actions", [])),
    }
    review_controls = shell_review_controls(
        root,
        queue=queue,
        aging=aging,
        active_protocol=protocol_state["active_protocol"],
        judgment_assets=judgment_assets,
        counter_evidence_scan=counter_evidence_scan if isinstance(counter_evidence_scan, dict) else {},
        review_actions=judgment_review_actions if isinstance(judgment_review_actions, list) else [],
    )
    l3_review_controls = (
        list(review_controls.get("l3_proposals", []))
        if isinstance(review_controls.get("l3_proposals", []), list)
        else []
    )
    review_backlog_counts["l3_proposals"] = len(l3_review_controls)
    review_backlog_counts["l3_proposal_attention"] = sum(
        1 for proposal in l3_review_controls if isinstance(proposal, dict) and proposal.get("needs_attention")
    )
    execution_controls = shell_execution_controls(root, memory)
    review_backlog_counts.update(_action_review_backlog_counts(execution_controls))
    rewrite_recovery_actions = rewrite_recovery_actions_for_controls(
        list(review_controls.get("rewrite_proposals", []))
        if isinstance(review_controls.get("rewrite_proposals", []), list)
        else []
    )
    recent_outputs = collect_recent_output_artifacts(root, limit=8)
    recent_receipts = shell_recent_receipts(root, limit=8)
    recent_runs = shell_recent_runs(root, limit=8)
    recent_raw_inputs = _build_recent_raw_inputs(root, limit=8)
    drift_warnings = shell_drift_warnings(
        memory,
        judgment_assets=judgment_assets,
        compile_state=compile_state,
        aging_state=_load_drift_aging_state(root),
    )
    counter_evidence_pages = _counter_evidence_pages_from_memory(counter_evidence_scan)
    metrics_history_delta = _build_metrics_history_delta(root, generated_at)
    planner_log_preview = _build_planner_log_preview(root)
    suggested_next_actions = shell_suggested_next_actions(
        planner_state=planner_state,
        review_controls=review_controls,
        execution_controls=execution_controls,
    )
    latest_llm_run = shell_latest_llm_run(root)
    latest_shell_sync_run = shell_latest_shell_sync_run(root)
    curated_page_roots = shell_curated_page_roots(root)
    llm_health = shell_llm_health(root, llm_status, latest_llm_run=latest_llm_run)
    summary: ShellSummary = {
        "kind": "product-shell-summary",
        "contract_version": 1,
        "generated_at": generated_at,
        "generated_by": "aiwiki-shell-status",
        "summary_path": relative_path(root, shell_summary_path(root)),
        "active_protocol": protocol_state["active_protocol"],
        "available_protocols": list(protocol_state.get("available_protocols", [])),
        "llm_status": {
            "configured": bool(llm_status.get("configured")),
            "backend": str(llm_status.get("backend") or ""),
            "effective_backend": str(llm_status.get("backend") or ""),
            "backend_requested": str(llm_status.get("backend_requested") or ""),
            "model_requested": str(llm_status.get("model_requested") or ""),
            "model": str(llm_status.get("model") or ""),
            "effective_model": str(llm_status.get("effective_model") or ""),
            "codex_reasoning_effort": str(llm_status.get("codex_reasoning_effort") or ""),
            "available_backends": list(llm_status.get("available_backends", [])),
            "image_analysis_supported": bool(llm_status.get("image_analysis_supported")),
            "auth_mode": str(llm_status.get("auth_mode") or ""),
            "usage_visibility": str(llm_status.get("usage_visibility") or ""),
            "usage_accounting": str(llm_status.get("usage_accounting") or ""),
            "message": str(llm_status.get("message") or ""),
            "backend_fallbacks": list(llm_status.get("backend_fallbacks", [])),
        },
        "latest_llm_run": latest_llm_run,
        "latest_shell_sync_run": latest_shell_sync_run,
        "curated_page_roots": curated_page_roots,
        "llm_health": llm_health,
        "review_backlog_counts": review_backlog_counts,
        "aging_summary": {
            "overdue_count": len(aging["overdue"]),
            "escalated_count": len(aging["escalated"]),
            "scheduled_count": len(aging["scheduled"]),
            "overdue_pages": [page["path"] for page in aging["overdue"][:8]],
            "escalated_pages": [page["path"] for page in aging["escalated"][:8]],
            "scheduled_pages": [page["path"] for page in aging["scheduled"][:8]],
        },
        "judgment_assets": {
            "counts": dict(judgment_assets.get("counts", {})),
            "attention_pages": list(judgment_assets.get("attention_pages", []))[:8],
            "decision_focus": list(judgment_assets.get("decision_focus", []))[:8],
            "judgment_focus": list(judgment_assets.get("judgment_focus", []))[:8],
            "strong_assets": list(judgment_assets.get("strong_assets", []))[:8],
        },
        "review_controls": review_controls,
        "rewrite_recovery_actions": rewrite_recovery_actions,
        "execution_controls": execution_controls,
        "planner": planner_state,
        "route_telemetry": route_telemetry,
        "recent_outputs": recent_outputs,
        "recent_receipts": recent_receipts,
        "recent_runs": recent_runs,
        "recent_raw_inputs": recent_raw_inputs,
        "watcher": _build_watcher_summary(root),
        "search_results": {"query": "", "limit": 0, "result_count": 0, "results": []},
        "drift_warnings": drift_warnings,
        "counter_evidence_pages": counter_evidence_pages,
        "metrics_history_delta": metrics_history_delta,
        "planner_log_preview": planner_log_preview,
        "suggested_next_actions": suggested_next_actions,
        "today_snooze": load_today_snooze_state(root),
        "nightly": _build_nightly_summary(root, nightly_state),
        "knowledge_stats": _build_knowledge_stats(memory, compile_state, decisions, judgments),
        "metrics": _build_metrics_summary(root),
        "links": shell_links(root),
        "capabilities": shell_capabilities(root),
    }
    summary["dashboard"] = shell_dashboard(
        summary,
        drift_warnings=drift_warnings,
        suggested_next_actions=suggested_next_actions,
    )
    return summary


def _filter_shell_route_telemetry(route_telemetry: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(route_telemetry, dict):
        return {}
    filtered = dict(route_telemetry)
    entries = [
        entry
        for entry in route_telemetry.get("entries", [])
        if isinstance(entry, dict) and not is_obsidian_open_link(str(entry.get("question_preview") or ""))
    ]
    filtered["entries"] = entries
    last_entry = route_telemetry.get("last_entry")
    if isinstance(last_entry, dict) and not is_obsidian_open_link(str(last_entry.get("question_preview") or "")):
        filtered["last_entry"] = dict(last_entry)
    else:
        filtered["last_entry"] = dict(entries[0]) if entries else {}
    return filtered


def _action_review_backlog_counts(execution_controls: dict[str, Any]) -> dict[str, int]:
    actions = execution_controls.get("actions") if isinstance(execution_controls, dict) else []
    action_controls = [item for item in actions if isinstance(item, dict)] if isinstance(actions, list) else []
    machine_memory_actions = [item for item in action_controls if bool(item.get("can_apply")) or bool(item.get("can_review"))]
    ready_actions = [
        item
        for item in action_controls
        if str(item.get("current_status") or item.get("status") or "") == "accepted"
        and (bool(item.get("can_apply")) or bool(item.get("can_review")) or bool(item.get("can_revert")))
    ]
    return {"machine_memory_actions": len(machine_memory_actions), "ready_actions": len(ready_actions)}

def _counter_evidence_pages_from_memory(counter_evidence_scan: Any) -> list[dict[str, Any]]:
    """P0 — 把 memory.health.counter_evidence_scan.pages 抽成 today_feed 友好结构。

    每页只保留 today_feed 渲染必需字段；最多 8 条。

    Round 58 R3 fix: scan writer (`compile/runtime_step.py:152`) emits `page_path /
    page_title / page_kind / candidate_count / source_pages`, but this reader was
    expecting the `path / subject / summary` schema. Mismatch silently dropped
    every entry, so `today_feed._build_counter_evidence_entries` never surfaced
    a counter-evidence card even when scan candidates existed. Read both schemas
    so old/new memory caches both work.
    """
    if not isinstance(counter_evidence_scan, dict):
        return []
    pages = counter_evidence_scan.get("pages")
    if not isinstance(pages, list):
        return []
    out: list[dict[str, Any]] = []
    for item in pages[:8]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or item.get("page_path") or "").strip()
        if not path:
            continue
        candidate_count = item.get("candidate_count")
        if isinstance(candidate_count, int) and candidate_count > 0:
            default_summary = f"{candidate_count} 条新证据可能反驳此判断"
        else:
            default_summary = "judgment 被反驳"
        out.append(
            {
                "path": path,
                "subject": str(item.get("subject") or item.get("title") or item.get("page_title") or path),
                "summary": str(item.get("summary") or item.get("reason") or default_summary),
                "detected_at": str(
                    item.get("detected_at")
                    or item.get("updated_at")
                    or counter_evidence_scan.get("generated_at")
                    or ""
                ),
                "protocol": str(item.get("protocol") or ""),
            }
        )
    return out


def _build_metrics_history_delta(root: Path, generated_at: str) -> dict[str, Any]:
    """P0 — 比对 7d/30d baseline，找出关键 metric 的方向变化。

    best-effort：history 不可用 / baseline 缺失 → 返回 {available: False}。
    阈值：abs(diff) >= 0.05（即 5 个百分点 / 5 次）才算"值得提醒"。
    """
    try:
        from aiwiki.metrics import compute_metrics
        from aiwiki.metrics_history import find_baseline
        from aiwiki.metrics_io import build_metrics_snapshot

        snapshot = build_metrics_snapshot(root)
        metrics = compute_metrics(snapshot)
        current: dict[str, float] = {
            str(m.key): float(m.value)
            for m in metrics
            if isinstance(m.value, (int, float))
        }
        if not current:
            return {"available": False, "reason": "no current metrics"}

        # 优先 7d；若 7d 无 baseline，回退 30d
        baseline_7d = find_baseline(root, generated_at or snapshot.now_iso, 7)
        baseline = baseline_7d
        window = "7d"
        if baseline_7d is None:
            baseline_30d = find_baseline(root, generated_at or snapshot.now_iso, 30)
            if baseline_30d is None:
                return {"available": False, "reason": "no baseline within 30d"}
            baseline = baseline_30d
            window = "30d"

        baseline_ts, baseline_metrics = baseline
        alerts: list[dict[str, Any]] = []
        for key in sorted(current.keys()):
            now_value = current[key]
            prev_value = baseline_metrics.get(key)
            if not isinstance(prev_value, (int, float)):
                continue
            diff = now_value - prev_value
            if abs(diff) < 0.05:
                continue
            alerts.append(
                {
                    "metric_key": key,
                    "previous": float(prev_value),
                    "current": float(now_value),
                    "diff": float(diff),
                    "direction": "up" if diff > 0 else "down",
                }
            )
        return {
            "available": True,
            "window": window,
            "baseline_ts": baseline_ts,
            "alerts": alerts,
        }
    except Exception as exc:  # pragma: no cover - best-effort
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}


def _build_planner_log_preview(root: Path) -> list[dict[str, Any]]:
    """P0 — 浮出 planner-log 中等待人工决策的 generate-proposal 候选。

    best-effort：planner-log 不存在 → []. 仅返回 eligible+blockers 的 dedup 字段。
    """
    try:
        from aiwiki.execution.l3_proposals import preview_l3_proposal_generation

        result = preview_l3_proposal_generation(root, limit=5)
    except Exception:  # pragma: no cover - best-effort
        return []
    if not isinstance(result, dict):
        return []
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return []
    out: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "signal_id": str(item.get("signal_id") or ""),
                "proposal_id": str(item.get("proposal_id") or ""),
                "target_file": str(item.get("target_file") or ""),
                "decided_at": str(item.get("decided_at") or ""),
                "eligible": bool(item.get("eligible")),
                "blockers": [str(b) for b in (item.get("blockers") or []) if isinstance(b, str)],
            }
        )
    return out


def _build_metrics_summary(root: Path) -> list[dict[str, object]]:
    try:
        from aiwiki.metrics import compute_metrics
        from aiwiki.metrics_io import build_metrics_snapshot

        return [
            {
                "key": metric.key,
                "value": metric.value,
                "unit": metric.unit,
                "reason": metric.reason,
                "sample_size": metric.sample_size,
            }
            for metric in compute_metrics(build_metrics_snapshot(root))
        ]
    except Exception as exc:
        return [
            {
                "key": "_metrics_unavailable",
                "value": None,
                "unit": "",
                "reason": str(exc),
                "sample_size": 0,
                "error_type": type(exc).__name__,
            }
        ]
