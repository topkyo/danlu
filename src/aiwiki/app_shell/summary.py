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
from ..llm import classify_backend_error
from .controls import (
    rewrite_recovery_actions_for_controls,
    shell_execution_controls,
    shell_review_controls,
)
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
    route_telemetry = load_query_route_telemetry(root)
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
    rewrite_recovery_actions = rewrite_recovery_actions_for_controls(
        list(review_controls.get("rewrite_proposals", []))
        if isinstance(review_controls.get("rewrite_proposals", []), list)
        else []
    )
    recent_outputs = collect_recent_output_artifacts(root, limit=8)
    recent_receipts = shell_recent_receipts(root, limit=8)
    recent_runs = shell_recent_runs(root, limit=8)
    drift_warnings = shell_drift_warnings(
        memory,
        judgment_assets=judgment_assets,
        compile_state=compile_state,
    )
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
        "search_results": {"query": "", "limit": 0, "result_count": 0, "results": []},
        "drift_warnings": drift_warnings,
        "suggested_next_actions": suggested_next_actions,
        "nightly": {
            "available": nightly_health_state_path(root).exists(),
            "generated_at": str(nightly_state.get("generated_at") or ""),
            "state_path": relative_path(root, nightly_health_state_path(root)),
            "llm_used": bool(nightly_state.get("llm_used", False)),
            "lint_counts": dict(nightly_state.get("lint", {}).get("counts", {})),
        },
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
    except Exception:
        return []
