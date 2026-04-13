"""Machine memory and execution snapshot logic extracted from aiwiki.app."""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import fcntl
import functools
import hashlib
import html
import json
import os
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import LLMConfig

from .app_utils import (
    extract_provenance_paths,
    html_safe_json_literal,
    parse_frontmatter,
    parse_iso_datetime,
    read_text_preview,
    relative_path,
    render_frontmatter,
    sha256_bytes,
    slugify,
    tokenize,
    utc_now,
    write_if_changed,
)

from .app_state import (
    DEFAULT_PROTOCOL,
    active_corpora_state_path,
    active_material_archive_entries,
    agent_workbench_path,
    concept_rewrite_proposal_page_path,
    concept_rewrite_state_path,
    domain_pilots_path,
    execution_audit_html_path,
    execution_audit_path,
    execution_center_html_path,
    execution_center_path,
    execution_receipt_history_path,
    furnace_center_html_path,
    load_active_corpora_state,
    load_archive_candidates_state,
    load_concept_rewrite_state,
    load_json_document,
    load_knowledge_lifecycle_state,
    load_machine_memory,
    load_machine_memory_action_state,
    load_machine_memory_build_state,
    load_manifest,
    load_manual_link_state,
    load_material_archive_state,
    load_runtime_history,
    machine_memory_action_state_path,
    machine_memory_graph_html_path,
    machine_memory_history_path,
    nightly_health_state_path,
    output_packs_index_path,
    review_center_html_path,
    save_active_corpora_state,
    save_archive_candidates_state,
    save_concept_rewrite_state,
    save_machine_memory_action_state,
    save_material_routing_state,
    save_material_state,
    shell_summary_path,
)

from .app_protocol import (
    ACTION_STATUSES,
    ACTIVE_CORPUS_STATUSES,
    ACTIVE_CORPUS_TTL,
    ARCHIVE_CANDIDATE_STATUSES,
    ARCHIVE_QUERY_STALE_AFTER,
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    PENDING_ACTION_STATUSES,
    PROTOCOL_LIBRARY,
    REWRITE_PROPOSAL_STATUSES,
    action_focus_score,
    ensure_layout,
    load_protocol_state,
    protocol_focus_score,
    protocol_state_path,
    protocol_title,
    schedule_review_windows,
)

from .app_content import (
    action_needs_review,
    action_priority_rank,
    action_status_rank,
    action_supports_low_risk_apply,
    action_transition_profile,
    archive_transition_profile,
    collect_aging_signals,
    collect_curated_pages,
    collect_recent_output_artifacts,
    concept_label_to_slug,
    curated_page_transition_profile,
    describe_machine_memory_action,
    display_action_status,
    display_rewrite_proposal_status,
    entry_ids_from_paths,
    entry_lookup_maps,
    evaluate_page_aging,
    execution_band_label,
    execution_bundle_path,
    execution_policy_profile,
    execution_proposal_path,
    knowledge_lifecycle_governance_summary,
    load_execution_receipt_history,
    machine_memory_concept_input_signature,
    machine_memory_source_input_signature,
    preserved_section,
    review_queue,
    rewrite_proposal_is_apply_ready,
    rewrite_proposal_needs_review,
    rewrite_proposal_status_rank,
    rewrite_transition_profile,
    routing_snapshot_for_protocol,
    source_summary_or_preview,
    summarize_runtime_event_for_shell,
    transition_profile,
    valid_curated_statuses,
    validate_low_risk_action_targets,
)

def shell_recent_runs(root: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    history = load_runtime_history(root)
    return [summarize_runtime_event_for_shell(event) for event in list(reversed(history))[:limit]]


def shell_recent_receipts(root: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    receipts = load_execution_receipt_history(root)
    return [
        {
            "action_id": str(receipt.get("action_id") or ""),
            "applied_at": str(receipt.get("applied_at") or ""),
            "operation": str(receipt.get("operation") or ""),
            "protocol": str(receipt.get("protocol") or ""),
            "receipt_path": str(receipt.get("receipt_path") or ""),
            "status": str(receipt.get("status") or ""),
            "subject_id": str(receipt.get("subject_id") or ""),
            "subject_kind": str(receipt.get("subject_kind") or ""),
            "title": str(receipt.get("title") or ""),
        }
        for receipt in receipts[:limit]
    ]


def shell_review_controls(
    root: Path,
    *,
    queue: dict[str, list[dict[str, str]]],
    aging: dict[str, list[dict[str, str]]],
) -> dict[str, list[dict[str, Any]]]:
    page_by_path: dict[str, dict[str, Any]] = {}

    def add_page(page: dict[str, str], reason_code: str) -> None:
        page_path = str(page.get("path") or "")
        if not page_path:
            return
        current = page_by_path.get(page_path)
        if current is None:
            current = {
                "page_id": str(page.get("page_id") or Path(page_path).stem),
                "title": str(page.get("title") or page_path),
                "path": page_path,
                "kind": str(page.get("kind") or ""),
                "status": str(page.get("status") or ""),
                "current_status": str(page.get("status") or ""),
                "protocol": str(page.get("protocol") or ""),
                "confidence": str(page.get("confidence") or ""),
                "pending_review": str(page.get("pending_review") or "") == "true",
                "overdue_review": str(page.get("overdue_review") or "") == "true",
                "escalation_candidate": str(page.get("escalation_candidate") or "") == "true",
                "aging_state": str(page.get("aging_state") or ""),
                "revisit_after": str(page.get("revisit_after") or ""),
                "escalate_after": str(page.get("escalate_after") or ""),
                "reviewed_at": str(page.get("reviewed_at") or ""),
                "updated_at": str(page.get("updated_at") or ""),
                "can_review": False,
                "can_refresh_review": False,
                "reasons": [],
            }
            page_by_path[page_path] = current
        reasons = current.setdefault("reasons", [])
        if reason_code and reason_code not in reasons:
            reasons.append(reason_code)
        profile = curated_page_transition_profile(
            str(current.get("kind") or ""),
            str(current.get("status") or ""),
        )
        current.update(profile)
        current["can_review"] = bool(profile.get("allowed_transitions"))
        current["can_refresh_review"] = bool(valid_curated_statuses(str(current.get("kind") or "")))

    for page in queue.get("pending_decisions", []) + queue.get("pending_judgments", []):
        add_page(page, "pending-review")
    for page in aging.get("escalated", []):
        add_page(page, "escalation-candidate")
    for page in aging.get("overdue", []):
        add_page(page, "overdue-review")
    for page in aging.get("scheduled", []):
        add_page(page, "scheduled-review")

    review_pages = sorted(
        page_by_path.values(),
        key=lambda item: (
            0 if item.get("escalation_candidate") else 1,
            0 if item.get("overdue_review") else 1,
            0 if item.get("pending_review") else 1,
            str(item.get("revisit_after") or "9999"),
            str(item.get("title") or "").lower(),
        ),
    )

    rewrite_state = load_concept_rewrite_state(root)
    rewrite_controls: list[dict[str, Any]] = []
    for proposal in rewrite_state.get("proposals", []):
        if not isinstance(proposal, dict):
            continue
        slug = str(proposal.get("slug") or "").strip()
        if not slug or not bool(proposal.get("active", True)):
            continue
        status = str(proposal.get("status") or "proposed")
        profile = rewrite_transition_profile(status)
        rewrite_controls.append(
            {
                "slug": slug,
                "title": str(proposal.get("title") or slug),
                "status": status,
                "current_status": status,
                "priority": str(proposal.get("priority") or "medium"),
                "score": int(proposal.get("score") or 0),
                "proposal_path": str(proposal.get("proposal_path") or ""),
                "target_path": str(proposal.get("target_path") or f"wiki/concepts/{slug}.md"),
                "pending_review": str(proposal.get("pending_review") or "") == "true",
                "apply_ready": bool(proposal.get("apply_ready", False)),
                "can_review": bool(profile.get("allowed_transitions")),
                "can_refresh_review": status in REWRITE_PROPOSAL_STATUSES,
                "can_apply": bool(proposal.get("apply_ready", False)),
                "first_proposed_at": str(proposal.get("first_proposed_at") or ""),
                "last_proposed_at": str(proposal.get("last_proposed_at") or ""),
                "reviewed_at": str(proposal.get("reviewed_at") or ""),
                "issue_count": len(proposal.get("issues", [])) if isinstance(proposal.get("issues"), list) else 0,
                "source_count": len(proposal.get("source_pages", [])) if isinstance(proposal.get("source_pages"), list) else 0,
                **profile,
            }
        )
    rewrite_controls.sort(
        key=lambda item: (
            0 if item.get("can_review") else 1,
            0 if item.get("apply_ready") else 1,
            rewrite_proposal_status_rank(str(item.get("status") or "")),
            action_priority_rank(str(item.get("priority") or "")),
            -int(item.get("score", 0)),
            str(item.get("title") or "").lower(),
        )
    )
    return {
        "pages": review_pages,
        "rewrite_proposals": rewrite_controls,
    }


def shell_action_control_objects(
    root: Path,
    memory: dict[str, Any],
    *,
    apply_ready_action_ids: set[str],
    revert_ready_action_ids: set[str],
) -> list[dict[str, Any]]:
    health = memory.get("health", {})
    repair_plan = health.get("repair_plan", {})
    all_actions = [
        action
        for action in [
            *health.get("actions", []),
            *health.get("inactive_actions", []),
            *repair_plan.get("ready_actions", []),
            *repair_plan.get("triage_actions", []),
            *repair_plan.get("deferred_actions", []),
        ]
        if isinstance(action, dict)
    ]
    controls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for action in all_actions:
        action_id = str(action.get("id") or "").strip()
        if not action_id or action_id in seen_ids:
            continue
        seen_ids.add(action_id)
        status = str(action.get("status") or "proposed")
        profile = action_transition_profile(status) if bool(action.get("active", True)) else transition_profile([])
        can_review = bool(profile.get("allowed_transitions"))
        can_apply = action_id in apply_ready_action_ids
        can_revert = action_id in revert_ready_action_ids
        proposal_path = execution_proposal_path(root, action_id)
        bundle_path = execution_bundle_path(root, action_id)
        controls.append(
            {
                "action_id": action_id,
                "title": str(action.get("title") or action_id),
                "status": status,
                "current_status": status,
                "kind": str(action.get("kind") or ""),
                "priority": str(action.get("priority") or "medium"),
                "protocol": str(action.get("protocol") or DEFAULT_PROTOCOL),
                "primary_path": str(action.get("primary_path") or ""),
                "secondary_path": str(action.get("secondary_path") or ""),
                "component_id": str(action.get("component_id") or ""),
                "execution_policy": str(action.get("execution_policy") or ""),
                "execution_band": str(action.get("execution_band") or ""),
                "policy_summary": str(action.get("policy_summary") or ""),
                "pending_review": str(action.get("pending_review") or "") == "true",
                "overdue_review": str(action.get("overdue_review") or "") == "true",
                "escalation_candidate": str(action.get("escalation_candidate") or "") == "true",
                "last_receipt_path": str(action.get("last_receipt_path") or ""),
                "proposal_path": relative_path(root, proposal_path) if proposal_path.exists() else "",
                "bundle_path": relative_path(root, bundle_path) if bundle_path.exists() else "",
                "can_review": can_review,
                "can_refresh_review": bool(action.get("active", True)) and status in ACTION_STATUSES,
                "can_apply": can_apply,
                "can_revert": can_revert,
                **profile,
            }
        )
    controls.sort(
        key=lambda item: (
            0 if item.get("can_apply") else 1,
            0 if item.get("can_review") else 1,
            0 if item.get("can_revert") else 1,
            0 if item.get("escalation_candidate") else 1,
            0 if item.get("overdue_review") else 1,
            action_status_rank(str(item.get("status") or "")),
            action_priority_rank(str(item.get("priority") or "")),
            str(item.get("title") or "").lower(),
        )
    )
    return controls


def shell_archive_control_objects(
    root: Path,
    *,
    apply_ready_archive_entry_ids: set[str],
    revert_ready_archive_entry_ids: set[str],
) -> list[dict[str, Any]]:
    manifest = load_manifest(root)
    manifest_by_id = {
        str(entry.get("id") or ""): entry
        for entry in manifest.get("entries", [])
        if isinstance(entry, dict) and entry.get("id")
    }
    archive_candidates = load_archive_candidates_state(root)
    archive_candidate_by_id = {
        str(entry.get("entry_id") or ""): entry
        for entry in archive_candidates.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    active_archives = active_material_archive_entries(load_material_archive_state(root))
    entry_ids = sorted(
        {
            *archive_candidate_by_id.keys(),
            *active_archives.keys(),
            *apply_ready_archive_entry_ids,
            *revert_ready_archive_entry_ids,
        }
    )
    controls: list[dict[str, Any]] = []
    for entry_id in entry_ids:
        candidate = archive_candidate_by_id.get(entry_id, {})
        archived = active_archives.get(entry_id, {})
        manifest_entry = manifest_by_id.get(entry_id, {})
        title = str(manifest_entry.get("title") or archived.get("title") or entry_id)
        source_path = str(archived.get("source_path") or f"wiki/sources/{entry_id}.md")
        can_apply = entry_id in apply_ready_archive_entry_ids
        can_revert = entry_id in revert_ready_archive_entry_ids
        profile = archive_transition_profile(can_apply=can_apply, can_revert=can_revert)
        controls.append(
            {
                "entry_id": entry_id,
                "title": title,
                "source_path": source_path,
                "candidate_status": str(candidate.get("status") or ""),
                "current_temperature": str(candidate.get("current_temperature") or ("archived" if archived else "")),
                "recommended_temperature": str(candidate.get("recommended_temperature") or archived.get("recommended_temperature") or ""),
                "reason_codes": list(candidate.get("reason_codes", [])) if isinstance(candidate.get("reason_codes"), list) else [],
                "blocked_by_judgment_ids": list(candidate.get("blocked_by_judgment_ids", []))
                if isinstance(candidate.get("blocked_by_judgment_ids"), list)
                else [],
                "reactivation_signals": list(candidate.get("reactivation_signals", []))
                if isinstance(candidate.get("reactivation_signals"), list)
                else [],
                "archived": bool(archived.get("active", False)),
                "archived_at": str(archived.get("archived_at") or ""),
                "last_receipt_path": str(archived.get("last_receipt_path") or ""),
                "can_apply": can_apply,
                "can_revert": can_revert,
                **profile,
            }
        )
    controls.sort(
        key=lambda item: (
            0 if item.get("can_apply") else 1,
            0 if item.get("can_revert") else 1,
            0 if item.get("archived") else 1,
            str(item.get("title") or "").lower(),
        )
    )
    return controls


def shell_execution_controls(root: Path, memory: dict[str, Any]) -> dict[str, Any]:
    repair_plan = memory.get("health", {}).get("repair_plan", {})
    ready_actions = [
        action
        for action in repair_plan.get("ready_actions", [])
        if isinstance(action, dict)
    ]
    apply_ready_action_ids = [
        str(action.get("id") or "")
        for action in ready_actions
        if action_supports_low_risk_apply(action) and action.get("id")
    ]
    all_actions = [
        action
        for action in [
            *memory.get("health", {}).get("actions", []),
            *memory.get("health", {}).get("inactive_actions", []),
        ]
        if isinstance(action, dict)
    ]
    revert_ready_action_ids = [
        str(action.get("id") or "")
        for action in all_actions
        if action.get("id")
        and action.get("last_receipt_path")
        and str(action.get("status") or "") == "resolved"
    ]
    archive_candidates = load_archive_candidates_state(root)
    apply_ready_archive_entry_ids = [
        str(entry.get("entry_id") or "")
        for entry in archive_candidates.get("entries", [])
        if (
            isinstance(entry, dict)
            and entry.get("entry_id")
            and str(entry.get("status") or "") == "ready"
            and str(entry.get("recommended_temperature") or "") == "archived"
        )
    ]
    revert_ready_archive_entry_ids = sorted(active_material_archive_entries(load_material_archive_state(root)).keys())
    apply_ready_action_id_set = {item for item in apply_ready_action_ids if item}
    revert_ready_action_id_set = {item for item in revert_ready_action_ids if item}
    apply_ready_archive_entry_id_set = {item for item in apply_ready_archive_entry_ids if item}
    revert_ready_archive_entry_id_set = set(revert_ready_archive_entry_ids)
    return {
        "apply_ready_action_ids": sorted(apply_ready_action_id_set),
        "revert_ready_action_ids": sorted(revert_ready_action_id_set),
        "apply_ready_archive_entry_ids": sorted(apply_ready_archive_entry_id_set),
        "revert_ready_archive_entry_ids": revert_ready_archive_entry_ids,
        "actions": shell_action_control_objects(
            root,
            memory,
            apply_ready_action_ids=apply_ready_action_id_set,
            revert_ready_action_ids=revert_ready_action_id_set,
        ),
        "archives": shell_archive_control_objects(
            root,
            apply_ready_archive_entry_ids=apply_ready_archive_entry_id_set,
            revert_ready_archive_entry_ids=revert_ready_archive_entry_id_set,
        ),
    }


def shell_links(root: Path) -> dict[str, str]:
    return {
        "summary_path": relative_path(root, shell_summary_path(root)),
        "furnace_center_markdown": "wiki/indexes/furnace-center.md",
        "review_center_markdown": "wiki/indexes/review-center.md",
        "execution_center_markdown": "wiki/indexes/execution-center.md",
        "execution_audit_markdown": "wiki/indexes/execution-audit.md",
        "graph_view_markdown": "wiki/indexes/graph-view.md",
        "protocols_markdown": "wiki/indexes/protocols.md",
        "domain_pilots_markdown": "wiki/indexes/domain-pilots.md",
        "output_packs_markdown": "wiki/indexes/output-packs.md",
        "agent_workbench_markdown": "wiki/indexes/agent-workbench.md",
        "furnace_center_html": relative_path(root, furnace_center_html_path(root)),
        "review_center_html": relative_path(root, review_center_html_path(root)),
        "execution_center_html": relative_path(root, execution_center_html_path(root)),
        "execution_audit_html": relative_path(root, execution_audit_html_path(root)),
        "graph_html": relative_path(root, machine_memory_graph_html_path(root)),
        "product_shell_design": "wiki/indexes/Furnace Product Shell Plugin.md",
        "product_shell_runtime_plan": "wiki/indexes/Furnace Product Shell Runtime Plan.md",
    }


def shell_capabilities(root: Path) -> dict[str, Any]:
    return {
        "launcher_mode": "repo-local",
        "supports_hidden_state_read": False,
        "commands": {
            "p0": [
                "shell-status",
                "compile",
                "ask",
                "run-ask",
                "nightly",
                "protocol-status",
                "protocol-set",
                "llm-check",
            ],
            "p1": [
                "run-compile",
                "run-nightly",
                "file-back",
                "review-page",
                "review-rewrite",
                "apply-rewrite",
                "retire-concept",
                "reactivate-concept",
                "apply-archive",
                "revert-archive",
            ],
            "p2": ["review-action", "apply-action", "revert-action", "watch", "auto-once"],
        },
        "views": {
            "furnace_center_markdown": (root / "wiki" / "indexes" / "furnace-center.md").exists(),
            "review_center_markdown": (root / "wiki" / "indexes" / "review-center.md").exists(),
            "execution_center_markdown": execution_center_path(root).exists(),
            "execution_audit_markdown": execution_audit_path(root).exists(),
            "domain_pilots_markdown": domain_pilots_path(root).exists(),
            "output_packs_markdown": output_packs_index_path(root).exists(),
            "agent_workbench_markdown": agent_workbench_path(root).exists(),
            "furnace_center_html": furnace_center_html_path(root).exists(),
            "review_center_html": review_center_html_path(root).exists(),
            "execution_center_html": execution_center_html_path(root).exists(),
            "execution_audit_html": execution_audit_html_path(root).exists(),
            "graph_html": machine_memory_graph_html_path(root).exists(),
        },
    }


def shell_protocol_state(root: Path) -> dict[str, Any]:
    state = load_json_document(protocol_state_path(root))
    available = sorted(PROTOCOL_LIBRARY)
    active = str(state.get("active_protocol") or DEFAULT_PROTOCOL)
    if active not in available:
        active = DEFAULT_PROTOCOL if DEFAULT_PROTOCOL in available else (available[0] if available else DEFAULT_PROTOCOL)
    return {
        "active_protocol": active,
        "available_protocols": available,
        "state_path": relative_path(root, protocol_state_path(root)),
    }


def build_shell_summary(root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    generated_at = generated_at or utc_now()
    protocol_state = shell_protocol_state(root)
    llm_status = LLMConfig.status_from_env()
    decisions = collect_curated_pages(root, "decisions", "decision")
    judgments = collect_curated_pages(root, "judgments", "judgment")
    queue = review_queue(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    aging = collect_aging_signals(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    knowledge_lifecycle = load_knowledge_lifecycle_state(root)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=protocol_state["active_protocol"],
    )
    memory = load_machine_memory(root)
    nightly_state = load_json_document(nightly_health_state_path(root))
    review_backlog_counts = {
        "pending_decisions": len(queue["pending_decisions"]),
        "pending_judgments": len(queue["pending_judgments"]),
        "overdue_reviews": len(aging["overdue"]),
        "escalation_candidates": len(aging["escalated"]),
        "concept_backlog": lifecycle_summary.get("counts", {}).get("concept_backlog", 0),
        "review_concepts": lifecycle_summary.get("counts", {}).get("review_concepts", 0),
        "revisit_concepts": lifecycle_summary.get("counts", {}).get("revisit_concepts", 0),
        "retired_concepts": lifecycle_summary.get("counts", {}).get("retired_concepts", 0),
        "machine_memory_actions": memory.get("health", {}).get("action_counts", {}).get("total", 0),
        "ready_actions": memory.get("health", {}).get("repair_plan", {}).get("counts", {}).get("ready", 0),
        "overdue_actions": len(memory.get("health", {}).get("overdue_actions", [])),
        "escalated_actions": len(memory.get("health", {}).get("escalated_actions", [])),
    }
    review_controls = shell_review_controls(root, queue=queue, aging=aging)
    return {
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
            "backend_requested": str(llm_status.get("backend_requested") or ""),
            "model": str(llm_status.get("model") or ""),
            "available_backends": list(llm_status.get("available_backends", [])),
            "image_analysis_supported": bool(llm_status.get("image_analysis_supported")),
            "message": str(llm_status.get("message") or ""),
        },
        "review_backlog_counts": review_backlog_counts,
        "aging_summary": {
            "overdue_count": len(aging["overdue"]),
            "escalated_count": len(aging["escalated"]),
            "scheduled_count": len(aging["scheduled"]),
            "overdue_pages": [page["path"] for page in aging["overdue"][:8]],
            "escalated_pages": [page["path"] for page in aging["escalated"][:8]],
            "scheduled_pages": [page["path"] for page in aging["scheduled"][:8]],
        },
        "review_controls": review_controls,
        "execution_controls": shell_execution_controls(root, memory),
        "recent_outputs": collect_recent_output_artifacts(root, limit=8),
        "recent_receipts": shell_recent_receipts(root, limit=8),
        "recent_runs": shell_recent_runs(root, limit=8),
        "nightly": {
            "available": nightly_health_state_path(root).exists(),
            "generated_at": str(nightly_state.get("generated_at") or ""),
            "state_path": relative_path(root, nightly_health_state_path(root)),
            "llm_used": bool(nightly_state.get("llm_used", False)),
            "lint_counts": dict(nightly_state.get("lint", {}).get("counts", {})),
        },
        "links": shell_links(root),
        "capabilities": shell_capabilities(root),
    }


def write_shell_summary(root: Path, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = summary or build_shell_summary(root)
    write_if_changed(shell_summary_path(root), json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def concept_page_path(root: Path, slug: str) -> Path:
    return root / "wiki" / "concepts" / f"{slug}.md"


def concept_lifecycle_entry(lifecycle_state: dict[str, Any], slug: str) -> dict[str, Any]:
    target_path = f"wiki/concepts/{slug}.md"
    return next(
        (
            dict(entry)
            for entry in lifecycle_state.get("entries", [])
            if isinstance(entry, dict)
            and str(entry.get("kind") or "") == "concept"
            and str(entry.get("path") or "") == target_path
        ),
        {},
    )


def question_signature(question: str) -> str:
    normalized = " ".join(question.lower().split())
    return f"sha256:{sha256_bytes(normalized.encode('utf-8'))}"


def timestamp_is_newer(candidate: str, current: str) -> bool:
    candidate_dt = parse_iso_datetime(candidate)
    current_dt = parse_iso_datetime(current)
    if candidate_dt is None:
        return False
    if current_dt is None:
        return True
    return candidate_dt > current_dt


def update_latest_timestamp(mapping: dict[str, str], key: str, timestamp: str) -> None:
    if not key or not timestamp:
        return
    if timestamp_is_newer(timestamp, mapping.get(key, "")):
        mapping[key] = timestamp


def protocol_hints_for_material(entry: dict[str, Any], preview: str) -> list[str]:
    text = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("source_type") or ""),
            preview,
        ]
    )
    scored: list[tuple[int, str]] = []
    for protocol in sorted(PROTOCOL_LIBRARY):
        if protocol == DEFAULT_PROTOCOL:
            continue
        score = protocol_focus_score(protocol, text)
        if score > 0:
            scored.append((score, protocol))
    scored.sort(key=lambda item: (-item[0], item[1]))
    hints = [protocol for _score, protocol in scored[:2]]
    return hints or [DEFAULT_PROTOCOL]


def recency_score_for_timestamp(timestamp: str) -> float:
    parsed = parse_iso_datetime(timestamp)
    if parsed is None:
        return 0.0
    now = datetime.now(timezone.utc)
    age = now - parsed
    if age <= timedelta(days=3):
        return 1.0
    if age <= timedelta(days=7):
        return 0.7
    if age <= timedelta(days=30):
        return 0.4
    return 0.1


QUERY_TIME_FOCUS_MARKERS: dict[str, tuple[str, ...]] = {
    "recent": ("latest", "recent", "current", "new", "newest", "updated", "today", "fresh"),
    "historical": ("history", "historical", "legacy", "old", "older", "previous", "prior", "archive", "archived"),
}


def machine_memory_query_time_focus(question: str) -> dict[str, Any]:
    normalized = " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", question.lower()))
    recent_hits = [marker for marker in QUERY_TIME_FOCUS_MARKERS["recent"] if marker in normalized]
    historical_hits = [marker for marker in QUERY_TIME_FOCUS_MARKERS["historical"] if marker in normalized]
    if historical_hits and len(historical_hits) >= len(recent_hits):
        return {"focus": "historical", "markers": historical_hits[:4]}
    if recent_hits:
        return {"focus": "recent", "markers": recent_hits[:4]}
    return {"focus": "", "markers": []}


def machine_memory_source_runtime_record(
    source_id: str,
    *,
    base_score: float,
    source_nodes: dict[str, dict[str, Any]],
    material_by_entry: dict[str, dict[str, Any]],
    routing_by_entry: dict[str, dict[str, Any]],
    archive_candidates_by_entry: dict[str, dict[str, Any]],
    protocol: str,
    time_focus: str,
) -> dict[str, Any]:
    material_entry = material_by_entry.get(source_id, {})
    routing_entry = routing_by_entry.get(source_id, {})
    routing_snapshot = routing_snapshot_for_protocol(routing_entry, protocol)
    archive_candidate = archive_candidates_by_entry.get(source_id, {})
    temperature = str(material_entry.get("temperature") or "")

    protocol_bonus = 0.0
    top_protocols = [
        str(item.get("protocol") or "")
        for item in routing_entry.get("top_protocols", [])
        if isinstance(item, dict) and str(item.get("protocol") or "")
    ]
    protocol_is_top = top_protocols[:1] == [protocol]
    protocol_in_top2 = protocol in top_protocols[:2]
    selected_as = str(routing_snapshot.get("selected_as") or "")
    selected_bonus = 0.0
    if selected_as == "hot-evidence":
        selected_bonus = 0.9
    elif selected_as == "warm-evidence":
        selected_bonus = 0.6
    elif selected_as == "cold-evidence":
        selected_bonus = 0.3
    total_score = float(routing_snapshot.get("total_score", 0.0) or 0.0)
    if protocol_is_top:
        protocol_bonus += 2.5 + selected_bonus + min(1.0, total_score * 0.25)
    elif protocol_in_top2:
        protocol_bonus += 1.2 + min(0.25, selected_bonus * 0.4) + min(0.4, total_score * 0.1)

    activity_score = max(
        recency_score_for_timestamp(str(material_entry.get("last_touched_at") or "")),
        recency_score_for_timestamp(str(material_entry.get("last_query_hit_at") or "")),
        recency_score_for_timestamp(str(material_entry.get("last_review_reference_at") or "")),
    )
    time_bonus = 0.0
    if time_focus == "recent":
        time_bonus += activity_score * 4.0
        if temperature == "hot":
            time_bonus += 0.4
        elif temperature == "warm":
            time_bonus += 0.2
        elif temperature == "cold":
            time_bonus -= 0.35
        elif temperature == "archived":
            time_bonus -= 1.0
    elif time_focus == "historical":
        time_bonus += (1.0 - activity_score) * 4.0
        if temperature == "cold":
            time_bonus += 0.8
        elif temperature == "archived":
            time_bonus += 1.4
        elif temperature == "hot":
            time_bonus -= 0.25
        if archive_candidate:
            time_bonus += 0.6

    protocol_shard = protocol_is_top or (protocol_in_top2 and selected_as in {"hot-evidence", "warm-evidence"})
    time_shard = bool(time_focus) and time_bonus > 1.0
    archive_status = "archived" if temperature == "archived" else str(archive_candidate.get("status") or "")
    archive_hint = bool(
        temperature == "archived"
        or (time_focus == "historical" and (temperature == "cold" or bool(archive_candidate)))
        or (
            archive_candidate
            and str(archive_candidate.get("recommended_temperature") or "") == "archived"
        )
    )
    archive_hint_score = base_score + protocol_bonus + max(0.0, time_bonus)
    if temperature == "archived":
        archive_hint_score += 1.0
    elif archive_candidate:
        archive_hint_score += 0.6
    elif temperature == "cold":
        archive_hint_score += 0.3

    return {
        "entry_id": source_id,
        "title": str(source_nodes.get(source_id, {}).get("title") or source_id),
        "path": str(source_nodes.get(source_id, {}).get("source_page") or f"wiki/sources/{source_id}.md"),
        "base_score": float(base_score),
        "protocol_bonus": round(protocol_bonus, 3),
        "time_bonus": round(time_bonus, 3),
        "combined_score": round(float(base_score) + protocol_bonus + time_bonus, 3),
        "protocol_shard": protocol_shard,
        "time_shard": time_shard,
        "temperature": temperature,
        "archive_status": archive_status,
        "archive_hint": archive_hint,
        "archive_hint_score": round(archive_hint_score, 3),
        "recommended_temperature": str(archive_candidate.get("recommended_temperature") or ""),
        "reason_codes": [
            str(reason)
            for reason in archive_candidate.get("reason_codes", [])
            if isinstance(reason, str) and reason
        ],
    }


def material_protocol_score(
    active_protocol: str,
    *,
    protocol_hints: list[str],
    entry: dict[str, Any],
    preview: str,
) -> float:
    text = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("source_type") or ""),
            preview,
        ]
    )
    focus_score = protocol_focus_score(active_protocol, text)
    non_default_hints = [hint for hint in protocol_hints if hint and hint != DEFAULT_PROTOCOL]
    if active_protocol == DEFAULT_PROTOCOL:
        base = 0.4 if not non_default_hints else 0.25
    elif active_protocol in protocol_hints:
        base = 0.75
    else:
        base = 0.2
    return round(min(1.0, base + min(0.25, focus_score * 0.05)), 3)


def material_graph_context(memory: dict[str, Any]) -> dict[str, Any]:
    health = memory.get("health", {})
    bridge_concepts = set(health.get("bridge_concept_slugs", []))
    concept_count_by_entry: dict[str, int] = {}
    bridge_source_ids: set[str] = set()
    source_component_ids = {
        str(source_id): str(component_id)
        for source_id, component_id in health.get("source_component_ids", {}).items()
        if isinstance(source_id, str) and isinstance(component_id, str)
    }
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        source_id = str(edge.get("source_id") or "")
        concept_slug = str(edge.get("concept_slug") or "")
        if not source_id or not concept_slug:
            continue
        concept_count_by_entry[source_id] = concept_count_by_entry.get(source_id, 0) + 1
        if concept_slug in bridge_concepts:
            bridge_source_ids.add(source_id)
    action_pressure_by_entry: dict[str, float] = {}
    for action in health.get("actions", []):
        if not isinstance(action, dict):
            continue
        weight = 0.2
        if str(action.get("priority") or "") == "high":
            weight += 0.15
        if str(action.get("status") or "") in {"accepted", "proposed"}:
            weight += 0.1
        for source_id in action.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id:
                action_pressure_by_entry[source_id] = action_pressure_by_entry.get(source_id, 0.0) + weight
    for action in health.get("overdue_actions", []):
        if not isinstance(action, dict):
            continue
        for source_id in action.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id:
                action_pressure_by_entry[source_id] = action_pressure_by_entry.get(source_id, 0.0) + 0.2
    for action in health.get("escalated_actions", []):
        if not isinstance(action, dict):
            continue
        for source_id in action.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id:
                action_pressure_by_entry[source_id] = action_pressure_by_entry.get(source_id, 0.0) + 0.25
    return {
        "concept_count_by_entry": concept_count_by_entry,
        "bridge_source_ids": bridge_source_ids,
        "action_pressure_by_entry": action_pressure_by_entry,
        "sources_without_concepts": set(memory.get("drift", {}).get("sources_without_concepts", [])),
        "source_component_ids": source_component_ids,
    }


def material_routing_selected_as(total_score: float, *, active_corpus_ids: list[str]) -> str:
    if active_corpus_ids or total_score >= 3.2:
        return "hot-evidence"
    if total_score >= 2.2:
        return "warm-evidence"
    if total_score >= 1.2:
        return "cold-evidence"
    return "archive-candidate"


def temperature_from_routing(selected_as: str, *, supports_judgment_ids: list[str]) -> str:
    if selected_as == "hot-evidence":
        return "hot"
    if selected_as == "warm-evidence":
        return "warm"
    if supports_judgment_ids:
        return "warm"
    return "cold"


def source_ids_for_citations(root: Path, entries: list[dict[str, Any]], markdown: str) -> list[str]:
    _by_id, path_to_entry_id = entry_lookup_maps(entries)
    return entry_ids_from_paths(path_to_entry_id, extract_provenance_paths(root, markdown))


def scan_material_reference_state(
    root: Path,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    _by_id, path_to_entry_id = entry_lookup_maps(entries)
    citation_count_by_entry: dict[str, int] = {}
    supports_judgment_ids: dict[str, set[str]] = {}
    active_judgment_ids: set[str] = set()

    for relative in ("wiki/derived", "wiki/decisions", "wiki/judgments"):
        directory = root / relative
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            cited_entry_ids = entry_ids_from_paths(path_to_entry_id, extract_provenance_paths(root, content))
            for entry_id in cited_entry_ids:
                citation_count_by_entry[entry_id] = citation_count_by_entry.get(entry_id, 0) + 1
            if relative != "wiki/judgments":
                continue
            frontmatter = parse_frontmatter(content)
            judgment_id = str(frontmatter.get("id") or path.stem)
            if str(frontmatter.get("status") or "") != "rejected":
                active_judgment_ids.add(judgment_id)
            for entry_id in cited_entry_ids:
                supports_judgment_ids.setdefault(entry_id, set()).add(judgment_id)

    return {
        "citation_count_by_entry": citation_count_by_entry,
        "supports_judgment_ids": {entry_id: sorted(ids) for entry_id, ids in supports_judgment_ids.items()},
        "active_judgment_ids": sorted(active_judgment_ids),
    }


def build_material_routing_snapshot(
    *,
    active_protocol: str,
    entry: dict[str, Any],
    preview: str,
    protocol_hints: list[str],
    active_corpus_ids: list[str],
    supports_judgment_ids: list[str],
    last_query_hit_at: str,
    last_review_reference_at: str,
    graph_context: dict[str, Any],
    computed_at: str,
) -> dict[str, Any]:
    entry_id = str(entry.get("id") or "")
    concept_count = int(graph_context.get("concept_count_by_entry", {}).get(entry_id, 0))
    is_bridge = entry_id in graph_context.get("bridge_source_ids", set())
    graph_score = 0.0
    graph_score += min(0.55, concept_count * 0.18)
    if active_corpus_ids:
        graph_score += 0.25
    if is_bridge:
        graph_score += 0.2
    graph_score = round(min(1.0, graph_score), 3)

    judgment_score = round(min(1.0, len(supports_judgment_ids) * 0.35), 3)
    recency_score = round(
        min(
            1.0,
            max(
                recency_score_for_timestamp(str(entry.get("updated_at") or entry.get("imported_at") or "")),
                recency_score_for_timestamp(last_query_hit_at),
                recency_score_for_timestamp(last_review_reference_at),
            ),
        ),
        3,
    )

    drift_score = 0.0
    if entry_id in graph_context.get("sources_without_concepts", set()):
        drift_score += 0.4
    drift_score += float(graph_context.get("action_pressure_by_entry", {}).get(entry_id, 0.0))
    drift_score = round(min(1.0, drift_score), 3)

    protocol_score = material_protocol_score(
        active_protocol,
        protocol_hints=protocol_hints,
        entry=entry,
        preview=preview,
    )
    total_score = round(protocol_score + graph_score + judgment_score + recency_score + drift_score, 3)
    selected_as = material_routing_selected_as(total_score, active_corpus_ids=active_corpus_ids)
    return {
        "entry_id": entry_id,
        "protocol": active_protocol,
        "component_id": str(graph_context.get("source_component_ids", {}).get(entry_id, "") or ""),
        "scores": {
            "protocol_score": protocol_score,
            "graph_score": graph_score,
            "judgment_score": judgment_score,
            "recency_score": recency_score,
            "drift_score": drift_score,
        },
        "total_score": total_score,
        "selected_as": selected_as,
        "is_bridge": is_bridge,
        "computed_at": computed_at,
    }


def material_top_protocols(protocol_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        [snapshot for snapshot in protocol_snapshots if isinstance(snapshot, dict)],
        key=lambda item: (-float(item.get("total_score", 0.0) or 0.0), str(item.get("protocol") or "")),
    )
    return [
        {
            "protocol": str(snapshot.get("protocol") or ""),
            "total_score": float(snapshot.get("total_score", 0.0) or 0.0),
            "selected_as": str(snapshot.get("selected_as") or ""),
        }
        for snapshot in ranked[:3]
    ]


def cross_protocol_bridge_entry(protocol_snapshots: list[dict[str, Any]], active_protocol: str) -> bool:
    for snapshot in protocol_snapshots:
        if not isinstance(snapshot, dict):
            continue
        if str(snapshot.get("protocol") or "") == active_protocol:
            continue
        if bool(snapshot.get("is_bridge")) and float(snapshot.get("total_score", 0.0) or 0.0) >= 2.2:
            return True
    return False


def build_material_routing_entry(
    *,
    active_protocol: str,
    entry: dict[str, Any],
    preview: str,
    protocol_hints: list[str],
    active_corpus_ids: list[str],
    supports_judgment_ids: list[str],
    last_query_hit_at: str,
    last_review_reference_at: str,
    graph_context: dict[str, Any],
    computed_at: str,
) -> dict[str, Any]:
    protocol_snapshots = [
        build_material_routing_snapshot(
            active_protocol=protocol,
            entry=entry,
            preview=preview,
            protocol_hints=protocol_hints,
            active_corpus_ids=active_corpus_ids,
            supports_judgment_ids=supports_judgment_ids,
            last_query_hit_at=last_query_hit_at,
            last_review_reference_at=last_review_reference_at,
            graph_context=graph_context,
            computed_at=computed_at,
        )
        for protocol in sorted(PROTOCOL_LIBRARY)
    ]
    active_snapshot = next(
        (snapshot for snapshot in protocol_snapshots if str(snapshot.get("protocol") or "") == active_protocol),
        protocol_snapshots[0],
    )
    return {
        **active_snapshot,
        "protocol_snapshots": protocol_snapshots,
        "top_protocols": material_top_protocols(protocol_snapshots),
        "cross_protocol_bridge": cross_protocol_bridge_entry(protocol_snapshots, active_protocol),
    }


def archive_candidate_reactivation_signals(
    material_entry: dict[str, Any],
    routing_snapshot: dict[str, Any],
    previous_candidate: dict[str, Any],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[str]:
    signals: list[str] = []
    previous_flagged_at = str(previous_candidate.get("last_flagged_at") or "")
    if material_entry.get("active_corpus_ids"):
        signals.append("active-corpus")
    if str(material_entry.get("last_query_hit_at") or "") and timestamp_is_newer(
        str(material_entry.get("last_query_hit_at") or ""),
        previous_flagged_at,
    ):
        signals.append("query-hit")
    if str(material_entry.get("last_review_reference_at") or "") and timestamp_is_newer(
        str(material_entry.get("last_review_reference_at") or ""),
        previous_flagged_at,
    ):
        signals.append("review-reference")
    if bool(routing_snapshot.get("is_bridge")):
        signals.append("bridge-evidence")
    if float(routing_snapshot.get("total_score", 0.0) or 0.0) >= 2.2:
        signals.append("routing-score-recovered")
    if bool(routing_snapshot.get("cross_protocol_bridge")):
        signals.append("cross-protocol-bridge")
    top_protocols = [
        str(item.get("protocol") or "")
        for item in routing_snapshot.get("top_protocols", [])
        if isinstance(item, dict) and str(item.get("protocol") or "")
    ]
    if any(protocol != active_protocol for protocol in top_protocols[:2]):
        signals.append("cross-protocol-top-rank")
    return signals


def build_archive_candidate_state(
    *,
    material_entries: list[dict[str, Any]],
    routing_entries: list[dict[str, Any]],
    active_judgment_ids: set[str],
    generated_at: str,
    previous_state: dict[str, Any],
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    previous_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in previous_state.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    routing_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in routing_entries
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    entries: list[dict[str, Any]] = []
    for material_entry in material_entries:
        entry_id = str(material_entry.get("entry_id") or "")
        if not entry_id:
            continue
        routing_snapshot = routing_by_entry.get(entry_id, {})
        previous_candidate = previous_by_entry.get(entry_id, {})
        blocked_by_judgment_ids = sorted(set(material_entry.get("supports_judgment_ids", [])) & active_judgment_ids)
        last_query_hit_at = parse_iso_datetime(str(material_entry.get("last_query_hit_at") or ""))
        query_stale = last_query_hit_at is None or (datetime.now(timezone.utc) - last_query_hit_at) > ARCHIVE_QUERY_STALE_AFTER
        touch_stale = recency_score_for_timestamp(str(material_entry.get("last_touched_at") or "")) <= 0.4
        total_score = float(routing_snapshot.get("total_score", 0.0) or 0.0)
        is_bridge = bool(routing_snapshot.get("is_bridge"))
        cross_protocol_bridge = bool(routing_snapshot.get("cross_protocol_bridge"))
        no_active_corpus = not material_entry.get("active_corpus_ids")
        candidate = (
            no_active_corpus
            and query_stale
            and touch_stale
            and not is_bridge
            and not cross_protocol_bridge
            and str(material_entry.get("temperature") or "") in {"warm", "cold"}
            and str(routing_snapshot.get("selected_as") or "") in {"cold-evidence", "archive-candidate"}
        )
        if candidate:
            reason_codes: list[str] = []
            if no_active_corpus:
                reason_codes.append("no-active-corpus")
            if query_stale:
                reason_codes.append("stale-no-query-hit")
            if touch_stale:
                reason_codes.append("stale-no-touch")
            if total_score < 2.0:
                reason_codes.append("low-routing-score")
            if str(material_entry.get("temperature") or "") == "cold":
                reason_codes.append("already-cold")
            recommended_temperature = "archived" if str(material_entry.get("temperature") or "") == "cold" and total_score < 1.2 else "cold"
            status = "suggested"
            if blocked_by_judgment_ids:
                status = "deferred"
            # Deferred means the candidate already crossed the archive bar once.
            # When the blocking judgments clear, it should resume at ready.
            elif previous_candidate and str(previous_candidate.get("status") or "") in {"suggested", "ready", "deferred"}:
                status = "ready"
            entries.append(
                {
                    "entry_id": entry_id,
                    "current_temperature": str(material_entry.get("temperature") or ""),
                    "recommended_temperature": recommended_temperature,
                    "reason_codes": reason_codes,
                    "first_flagged_at": str(previous_candidate.get("first_flagged_at") or generated_at),
                    "last_flagged_at": generated_at,
                    "blocked_by_judgment_ids": blocked_by_judgment_ids,
                    "reactivation_signals": list(previous_candidate.get("reactivation_signals", []))
                    if isinstance(previous_candidate.get("reactivation_signals"), list)
                    else [],
                    "status": status if status in ARCHIVE_CANDIDATE_STATUSES else "suggested",
                }
            )
            continue
        if previous_candidate:
            reactivation_signals = archive_candidate_reactivation_signals(
                material_entry,
                routing_snapshot,
                previous_candidate,
                active_protocol=active_protocol,
            )
            if reactivation_signals:
                entries.append(
                    {
                        "entry_id": entry_id,
                        "current_temperature": str(material_entry.get("temperature") or ""),
                        "recommended_temperature": str(previous_candidate.get("recommended_temperature") or "cold"),
                        "reason_codes": [],
                        "first_flagged_at": str(previous_candidate.get("first_flagged_at") or generated_at),
                        "last_flagged_at": str(previous_candidate.get("last_flagged_at") or generated_at),
                        "blocked_by_judgment_ids": blocked_by_judgment_ids,
                        "reactivation_signals": reactivation_signals,
                        "status": "reactivated",
                    }
    )
    return {"version": 1, "generated_at": generated_at, "entries": entries}


def routing_bridge_recall_ids(
    machine_query: dict[str, Any],
    routing_state: dict[str, Any],
    *,
    active_protocol: str,
    excluded_source_ids: set[str],
) -> list[str]:
    touched_component_ids = {
        str(component_id)
        for component_id in machine_query.get("touched_component_ids", [])
        if isinstance(component_id, str) and component_id
    }
    candidates: list[tuple[float, str]] = []
    for entry in routing_state.get("entries", []):
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("entry_id") or "")
        component_id = str(entry.get("component_id") or "")
        if not entry_id or entry_id in excluded_source_ids:
            continue
        if not touched_component_ids or component_id not in touched_component_ids:
            continue
        protocol_snapshots = [
            snapshot for snapshot in entry.get("protocol_snapshots", []) if isinstance(snapshot, dict)
        ]
        if not cross_protocol_bridge_entry(protocol_snapshots, active_protocol):
            continue
        non_active_scores = [
            float(snapshot.get("total_score", 0.0) or 0.0)
            for snapshot in protocol_snapshots
            if str(snapshot.get("protocol") or "") != active_protocol
        ]
        if not non_active_scores:
            continue
        best_score = max(non_active_scores)
        if best_score < 2.2:
            continue
        candidates.append((best_score, entry_id))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [entry_id for _score, entry_id in candidates[:3]]


def active_corpus_bridge_evidence_ids(
    machine_query: dict[str, Any],
    source_ids: list[str],
    *,
    routing_state: dict[str, Any] | None = None,
    active_protocol: str = DEFAULT_PROTOCOL,
    blocked_source_ids: set[str] | None = None,
) -> list[str]:
    blocked_source_ids = blocked_source_ids or set()
    bridge_concepts = set(machine_query.get("bridge_concept_slugs", []))
    source_set = set(source_ids) | {
        str(source_id)
        for source_id in machine_query.get("ranked_source_ids", [])
        if isinstance(source_id, str) and source_id and source_id not in blocked_source_ids
    }
    for node in machine_query.get("query_subgraph", {}).get("sources", []):
        if isinstance(node, dict):
            node_id = str(node.get("id") or "")
            if node_id and node_id not in blocked_source_ids:
                source_set.add(node_id)
    bridge_ids: list[str] = []
    seen: set[str] = set()
    if bridge_concepts:
        for edge in machine_query.get("query_subgraph", {}).get("edges", []):
            if not isinstance(edge, dict):
                continue
            if edge.get("type") != "HAS_CONCEPT":
                continue
            left = str(edge.get("left") or "")
            right = str(edge.get("right") or "")
            if (
                left in source_set
                and left not in blocked_source_ids
                and right in bridge_concepts
                and left not in seen
            ):
                seen.add(left)
                bridge_ids.append(left)
    if routing_state:
        excluded = set(source_set) | set(bridge_ids) | set(blocked_source_ids)
        for entry_id in routing_bridge_recall_ids(
            machine_query,
            routing_state,
            active_protocol=active_protocol,
            excluded_source_ids=excluded,
        ):
            if entry_id not in seen and entry_id not in blocked_source_ids:
                seen.add(entry_id)
                bridge_ids.append(entry_id)
    return bridge_ids


def reconcile_active_corpora_state(
    root: Path,
    *,
    changed_at: str,
    nightly_cooldown: bool = False,
) -> dict[str, Any]:
    ensure_layout(root)
    state = load_active_corpora_state(root)
    changed = not active_corpora_state_path(root).exists()
    corpora: list[dict[str, Any]] = []
    for raw_corpus in state.get("corpora", []):
        corpus = dict(raw_corpus)
        status = str(corpus.get("status") or "active")
        if status not in ACTIVE_CORPUS_STATUSES:
            status = "active"
            changed = True
        expires_at = str(corpus.get("expires_at") or "")
        if expires_at and timestamp_is_newer(changed_at, expires_at):
            if status != "expired":
                status = "expired"
                changed = True
        elif nightly_cooldown and status == "active":
            status = "cooling"
            changed = True
        corpus["status"] = status
        corpora.append(corpus)
    if changed:
        save_active_corpora_state(root, {"version": 1, "corpora": corpora})
    return {"version": 1, "corpora": corpora, "changed": changed}


def refresh_material_state(
    root: Path,
    *,
    generated_at: str,
    entries: list[dict[str, Any]] | None = None,
    active_protocol: str | None = None,
) -> dict[str, Any]:
    documents = build_material_state_documents(
        root,
        generated_at=generated_at,
        entries=entries,
        active_protocol=active_protocol,
    )
    save_material_state(root, documents["material_state"])
    save_material_routing_state(root, documents["material_routing"])
    save_archive_candidates_state(root, documents["archive_candidates"])
    return documents["material_state"]


def build_material_state_documents(
    root: Path,
    *,
    generated_at: str,
    entries: list[dict[str, Any]] | None = None,
    active_protocol: str | None = None,
) -> dict[str, dict[str, Any]]:
    ensure_layout(root)
    manifest_entries = entries if entries is not None else load_manifest(root).get("entries", [])
    resolved_protocol = active_protocol or load_protocol_state(root)["active_protocol"]
    history = load_runtime_history(root)
    active_corpora = reconcile_active_corpora_state(root, changed_at=generated_at)["corpora"]
    reference_state = scan_material_reference_state(root, manifest_entries)
    machine_memory = load_machine_memory(root)
    graph_context = material_graph_context(machine_memory)
    previous_archive_candidates = load_archive_candidates_state(root)
    material_archive_state = load_material_archive_state(root)
    archived_entries = active_material_archive_entries(material_archive_state)
    last_query_hit_at: dict[str, str] = {}
    last_review_reference_at: dict[str, str] = {}

    for event in history:
        occurred_at = str(event.get("occurred_at") or "")
        event_type = str(event.get("event_type") or "")
        source_ids = [str(item) for item in event.get("source_ids", []) if isinstance(item, str)]
        if event_type == "query":
            for entry_id in source_ids:
                update_latest_timestamp(last_query_hit_at, entry_id, occurred_at)
        elif event_type == "review":
            for entry_id in source_ids:
                update_latest_timestamp(last_review_reference_at, entry_id, occurred_at)

    active_corpus_ids_by_entry: dict[str, list[str]] = {}
    for corpus in active_corpora:
        status = str(corpus.get("status") or "")
        if status not in {"active", "cooling"}:
            continue
        corpus_id = str(corpus.get("corpus_id") or "")
        if not corpus_id:
            continue
        source_ids = [
            str(item)
            for item in [*(corpus.get("source_ids", []) or []), *(corpus.get("bridge_evidence_ids", []) or [])]
            if isinstance(item, str)
        ]
        for entry_id in source_ids:
            active_corpus_ids_by_entry.setdefault(entry_id, [])
            if corpus_id not in active_corpus_ids_by_entry[entry_id]:
                active_corpus_ids_by_entry[entry_id].append(corpus_id)

    material_entries: list[dict[str, Any]] = []
    routing_entries: list[dict[str, Any]] = []
    for entry in manifest_entries:
        entry_id = str(entry.get("id") or "")
        stored_path = str(entry.get("stored_path") or "")
        preview = read_text_preview(root / stored_path) if stored_path and (root / stored_path).exists() else ""
        supports_judgment_ids = reference_state["supports_judgment_ids"].get(entry_id, [])
        citation_count = int(reference_state["citation_count_by_entry"].get(entry_id, 0))
        active_corpus_ids = sorted(active_corpus_ids_by_entry.get(entry_id, []))
        query_hit_at = last_query_hit_at.get(entry_id, "")
        review_hit_at = last_review_reference_at.get(entry_id, "")
        protocol_hints = protocol_hints_for_material(entry, preview)
        routing_entry = build_material_routing_entry(
            active_protocol=resolved_protocol,
            entry=entry,
            preview=preview,
            protocol_hints=protocol_hints,
            active_corpus_ids=active_corpus_ids,
            supports_judgment_ids=supports_judgment_ids,
            last_query_hit_at=query_hit_at,
            last_review_reference_at=review_hit_at,
            graph_context=graph_context,
            computed_at=generated_at,
        )
        routing_entries.append(routing_entry)
        archive_record = archived_entries.get(entry_id, {})
        temperature = temperature_from_routing(
            str(routing_entry.get("selected_as") or ""),
            supports_judgment_ids=supports_judgment_ids,
        )
        if archive_record:
            temperature = "archived"
        material_entries.append(
            {
                "entry_id": entry_id,
                "path": stored_path,
                "kind": str(entry.get("kind") or ""),
                "source_type": str(entry.get("source_type") or ""),
                "protocol_hints": protocol_hints,
                "temperature": temperature,
                "last_touched_at": str(entry.get("updated_at") or entry.get("imported_at") or ""),
                "last_query_hit_at": query_hit_at,
                "last_review_reference_at": review_hit_at,
                "citation_count": citation_count,
                "supports_judgment_ids": supports_judgment_ids,
                "active_corpus_ids": active_corpus_ids,
                "archive_override": bool(archive_record),
                "archived_at": str(archive_record.get("archived_at") or ""),
                "archive_receipt_path": str(archive_record.get("last_receipt_path") or ""),
                "archive_candidate": False,
            }
        )

    routing_document = {
        "version": 1,
        "computed_at": generated_at,
        "active_protocol": resolved_protocol,
        "entries": routing_entries,
    }
    archive_document = build_archive_candidate_state(
        material_entries=material_entries,
        routing_entries=routing_entries,
        active_judgment_ids=set(reference_state.get("active_judgment_ids", [])),
        generated_at=generated_at,
        previous_state=previous_archive_candidates,
        active_protocol=resolved_protocol,
    )
    active_archive_ids = {
        str(entry.get("entry_id") or "")
        for entry in archive_document.get("entries", [])
        if str(entry.get("status") or "") in {"suggested", "deferred", "ready"}
    }
    for material_entry in material_entries:
        material_entry["archive_candidate"] = material_entry.get("entry_id") in active_archive_ids
    material_document = {"version": 1, "generated_at": generated_at, "entries": material_entries}
    return {
        "material_state": material_document,
        "material_routing": routing_document,
        "archive_candidates": archive_document,
        "active_corpora_state": {"version": 1, "corpora": active_corpora},
    }


def upsert_active_corpus(
    root: Path,
    *,
    protocol: str,
    question: str,
    source_ids: list[str],
    concept_slugs: list[str],
    bridge_evidence_ids: list[str],
    output_ref: str,
    changed_at: str,
) -> dict[str, Any]:
    ensure_layout(root)
    state = reconcile_active_corpora_state(root, changed_at=changed_at)
    corpora = [dict(corpus) for corpus in state.get("corpora", [])]
    base_timestamp = parse_iso_datetime(changed_at) or datetime.now(timezone.utc)
    signature = question_signature(question)
    seed = slugify(question)[:40] or "question"
    corpus_id = f"{protocol}-{seed}-{signature.split(':', 1)[1][:8]}"
    target: dict[str, Any] | None = None
    for corpus in corpora:
        if str(corpus.get("corpus_id") or "") == corpus_id:
            target = corpus
            break
    if target is None:
        target = {"corpus_id": corpus_id, "created_at": changed_at}
        corpora.append(target)
    output_refs = [str(item) for item in target.get("output_refs", []) if isinstance(item, str)]
    if output_ref and output_ref not in output_refs:
        output_refs.append(output_ref)
    target.update(
        {
            "protocol": protocol,
            "focus_kind": "question",
            "focus_ref": question,
            "question_hash": signature,
            "source_ids": source_ids,
            "concept_slugs": concept_slugs,
            "bridge_evidence_ids": bridge_evidence_ids,
            "output_refs": output_refs[-8:],
            "status": "active",
            "last_used_at": changed_at,
            "expires_at": (base_timestamp + ACTIVE_CORPUS_TTL).replace(microsecond=0).isoformat(),
        }
    )
    save_active_corpora_state(root, {"version": 1, "corpora": corpora})
    return target


def build_machine_memory(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    previews: dict[str, str],
    entry_terms: dict[str, list[str]],
    compiled_at: str,
) -> dict[str, Any]:
    term_index: dict[str, dict[str, set[str]]] = {}
    source_nodes: list[dict[str, Any]] = []
    concept_nodes: list[dict[str, Any]] = []
    source_to_concept: list[dict[str, str]] = []
    concept_to_concept: list[dict[str, str]] = []
    citation_map: list[dict[str, Any]] = []

    def index_term(term: str, *, source_id: str | None = None, concept_slug: str | None = None) -> None:
        bucket = term_index.setdefault(term, {"source_ids": set(), "concept_slugs": set()})
        if source_id:
            bucket["source_ids"].add(source_id)
        if concept_slug:
            bucket["concept_slugs"].add(concept_slug)

    for entry in entries:
        concept_slugs = [concept_label_to_slug(label) for label in entry_terms.get(entry["id"], [])]
        source_page = f"wiki/sources/{entry['id']}.md"
        summary = source_summary_or_preview(root, entry, previews[entry["id"]])
        source_nodes.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "source_type": entry["source_type"],
                "kind": entry["kind"],
                "stored_path": entry["stored_path"],
                "original_path": entry["original_path"],
                "sha256": entry["sha256"],
                "source_page": source_page,
                "concept_slugs": concept_slugs,
            }
        )
        citation_map.append(
            {
                "source_page": source_page,
                "stored_path": entry["stored_path"],
                "original_path": entry["original_path"],
                "sha256": entry["sha256"],
            }
        )
        for slug in concept_slugs:
            source_to_concept.append({"source_id": entry["id"], "concept_slug": slug})
        for token in tokenize(f"{entry['title']}\n{summary}"):
            index_term(token, source_id=entry["id"])

    for record in concepts:
        concept_nodes.append(
            {
                "slug": record["slug"],
                "title": record["title"],
                "source_pages": [f"wiki/sources/{entry_id}.md" for entry_id in record["entry_ids"]],
                "related_slugs": record.get("related_slugs", []),
                "source_signature": record["source_signature"],
            }
        )
        for related_slug in record.get("related_slugs", []):
            concept_to_concept.append({"from": record["slug"], "to": related_slug})
        for token in tokenize(record["title"]):
            index_term(token, concept_slug=record["slug"])

    drift = {
        "missing_raw_files": [
            entry["stored_path"] for entry in entries if not (root / entry["stored_path"]).exists()
        ],
        "missing_source_pages": [
            f"wiki/sources/{entry['id']}.md"
            for entry in entries
            if not (root / "wiki" / "sources" / f"{entry['id']}.md").exists()
        ],
        "missing_concept_pages": [
            f"wiki/concepts/{record['slug']}.md"
            for record in concepts
            if not (root / "wiki" / "concepts" / f"{record['slug']}.md").exists()
        ],
        "sources_without_concepts": [entry["id"] for entry in entries if not entry_terms.get(entry["id"])],
    }

    return {
        "version": 1,
        "compiled_at": compiled_at,
        "source_nodes": sorted(source_nodes, key=lambda item: item["id"]),
        "concept_nodes": sorted(concept_nodes, key=lambda item: item["slug"]),
        "edges": {
            "source_to_concept": sorted(source_to_concept, key=lambda item: (item["source_id"], item["concept_slug"])),
            "concept_to_concept": sorted(concept_to_concept, key=lambda item: (item["from"], item["to"])),
        },
        "citation_map": sorted(citation_map, key=lambda item: item["source_page"]),
        "term_index": {
            term: {
                "source_ids": sorted(payload["source_ids"]),
                "concept_slugs": sorted(payload["concept_slugs"]),
            }
            for term, payload in sorted(term_index.items())
        },
        "drift": drift,
    }


def plan_machine_memory_build(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    previews: dict[str, str],
    entry_terms: dict[str, list[str]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    previous_state = load_machine_memory_build_state(root)
    previous_source_records = previous_state.get("source_records", {})
    previous_concept_records = previous_state.get("concept_records", {})
    if not isinstance(previous_source_records, dict):
        previous_source_records = {}
    if not isinstance(previous_concept_records, dict):
        previous_concept_records = {}

    source_records: dict[str, dict[str, str]] = {}
    dirty_source_ids: list[str] = []
    clean_source_ids: list[str] = []
    for entry in entries:
        entry_id = str(entry["id"])
        input_signature = machine_memory_source_input_signature(
            root,
            entry,
            previews.get(entry_id, ""),
            entry_terms.get(entry_id, []),
        )
        source_records[entry_id] = {"input_signature": input_signature}
        previous_record = previous_source_records.get(entry_id, {})
        if (
            isinstance(previous_record, dict)
            and str(previous_record.get("input_signature") or "") == input_signature
        ):
            clean_source_ids.append(entry_id)
        else:
            dirty_source_ids.append(entry_id)

    concept_records: dict[str, dict[str, str]] = {}
    dirty_concept_slugs: list[str] = []
    clean_concept_slugs: list[str] = []
    for record in concepts:
        slug = str(record["slug"])
        input_signature = machine_memory_concept_input_signature(record)
        concept_records[slug] = {"input_signature": input_signature}
        previous_record = previous_concept_records.get(slug, {})
        if (
            isinstance(previous_record, dict)
            and str(previous_record.get("input_signature") or "") == input_signature
        ):
            clean_concept_slugs.append(slug)
        else:
            dirty_concept_slugs.append(slug)

    removed_source_ids = sorted(set(previous_source_records) - set(source_records))
    removed_concept_slugs = sorted(set(previous_concept_records) - set(concept_records))
    return {
        "state_document": {
            "version": 1,
            "generated_at": generated_at,
            "source_records": source_records,
            "concept_records": concept_records,
        },
        "dirty_source_ids": dirty_source_ids,
        "clean_source_ids": clean_source_ids,
        "dirty_concept_slugs": dirty_concept_slugs,
        "clean_concept_slugs": clean_concept_slugs,
        "removed_source_ids": removed_source_ids,
        "removed_concept_slugs": removed_concept_slugs,
        "inputs_clean": not (
            dirty_source_ids
            or dirty_concept_slugs
            or removed_source_ids
            or removed_concept_slugs
        ),
    }


def machine_memory_snapshot_is_reusable(memory: dict[str, Any]) -> bool:
    return (
        isinstance(memory.get("source_nodes"), list)
        and isinstance(memory.get("concept_nodes"), list)
        and isinstance(memory.get("edges"), dict)
        and isinstance(memory.get("citation_map"), list)
        and isinstance(memory.get("term_index"), dict)
        and isinstance(memory.get("drift"), dict)
    )


def reuse_machine_memory_core(previous: dict[str, Any], compiled_at: str) -> dict[str, Any]:
    return {
        "version": int(previous.get("version", 1) or 1),
        "compiled_at": compiled_at,
        "source_nodes": list(previous.get("source_nodes", [])),
        "concept_nodes": list(previous.get("concept_nodes", [])),
        "edges": dict(previous.get("edges", {})),
        "citation_map": list(previous.get("citation_map", [])),
        "term_index": dict(previous.get("term_index", {})),
        "drift": dict(previous.get("drift", {})),
    }


def build_machine_memory_health(memory: dict[str, Any]) -> dict[str, Any]:
    source_nodes = memory.get("source_nodes", [])
    concept_nodes = memory.get("concept_nodes", [])
    edges = memory.get("edges", {})
    drift = memory.get("drift", {})

    source_to_concepts: dict[str, set[str]] = {}
    concept_to_sources: dict[str, set[str]] = {}
    concept_related: dict[str, set[str]] = {}
    source_node_by_id = {node["id"]: node for node in source_nodes}
    concept_node_by_slug = {node["slug"]: node for node in concept_nodes}

    for edge in edges.get("source_to_concept", []):
        source_id = edge.get("source_id")
        concept_slug = edge.get("concept_slug")
        if not isinstance(source_id, str) or not isinstance(concept_slug, str):
            continue
        source_to_concepts.setdefault(source_id, set()).add(concept_slug)
        concept_to_sources.setdefault(concept_slug, set()).add(source_id)

    for edge in edges.get("concept_to_concept", []):
        left = edge.get("from")
        right = edge.get("to")
        if not isinstance(left, str) or not isinstance(right, str):
            continue
        concept_related.setdefault(left, set()).add(right)
        concept_related.setdefault(right, set()).add(left)

    isolated_source_ids = sorted(node["id"] for node in source_nodes if not source_to_concepts.get(node["id"]))
    singleton_concept_slugs = sorted(
        node["slug"]
        for node in concept_nodes
        if len(concept_to_sources.get(node["slug"], set())) <= 1 and not concept_related.get(node["slug"])
    )
    bridge_concept_slugs = [
        node["slug"]
        for node in sorted(
            concept_nodes,
            key=lambda item: (
                -len(concept_to_sources.get(item["slug"], set())),
                -len(concept_related.get(item["slug"], set())),
                item["title"].lower(),
            ),
        )
        if len(concept_to_sources.get(node["slug"], set())) >= 2 and concept_related.get(node["slug"])
    ]
    overloaded_concept_slugs = sorted(
        node["slug"] for node in concept_nodes if len(concept_to_sources.get(node["slug"], set())) >= 4
    )

    hub_concepts = [
        {
            "slug": node["slug"],
            "title": node["title"],
            "source_count": len(concept_to_sources.get(node["slug"], set())),
            "related_count": len(concept_related.get(node["slug"], set())),
            "component_id": "",
        }
        for node in concept_nodes
    ]
    hub_concepts.sort(
        key=lambda item: (-item["source_count"], -item["related_count"], item["title"].lower())
    )
    hub_sources = [
        {
            "id": node["id"],
            "title": node["title"],
            "concept_count": len(source_to_concepts.get(node["id"], set())),
            "source_page": node["source_page"],
            "component_id": "",
        }
        for node in source_nodes
    ]
    hub_sources.sort(key=lambda item: (-item["concept_count"], item["title"].lower()))

    adjacency = build_machine_memory_adjacency(memory)

    visited: set[str] = set()
    component_sizes: list[int] = []
    component_records: list[dict[str, Any]] = []
    for node_key in sorted(adjacency):
        if node_key in visited:
            continue
        stack = [node_key]
        members: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            members.add(current)
            stack.extend(sorted(set(adjacency.get(current, {})) - visited))
        component_sizes.append(len(members))
        source_ids = sorted(member.removeprefix("source:") for member in members if member.startswith("source:"))
        concept_slugs = sorted(member.removeprefix("concept:") for member in members if member.startswith("concept:"))
        component_records.append(
            {
                "source_ids": source_ids,
                "concept_slugs": concept_slugs,
                "size": len(members),
                "sort_key": (
                    -len(members),
                    source_ids[0] if source_ids else "~",
                    concept_slugs[0] if concept_slugs else "~",
                ),
            }
        )
    component_sizes.sort(reverse=True)
    component_records.sort(key=lambda item: item["sort_key"])
    components: list[dict[str, Any]] = []
    source_component_ids: dict[str, str] = {}
    concept_component_ids: dict[str, str] = {}
    for index, record in enumerate(component_records, start=1):
        component_id = f"component-{index}"
        components.append(
            {
                "id": component_id,
                "size": record["size"],
                "source_ids": record["source_ids"],
                "concept_slugs": record["concept_slugs"],
            }
        )
        for source_id in record["source_ids"]:
            source_component_ids[source_id] = component_id
        for concept_slug in record["concept_slugs"]:
            concept_component_ids[concept_slug] = component_id

    for item in hub_concepts:
        item["component_id"] = concept_component_ids.get(item["slug"], "")
    for item in hub_sources:
        item["component_id"] = source_component_ids.get(item["id"], "")

    term_index = memory.get("term_index", {})
    suggestion_scores: dict[tuple[str, str], set[str]] = {}
    for term, payload in term_index.items():
        source_ids = payload.get("source_ids", [])
        concept_slugs = payload.get("concept_slugs", [])
        if not source_ids or not concept_slugs:
            continue
        for source_id in source_ids:
            if source_id not in drift.get("sources_without_concepts", []) and source_id not in isolated_source_ids:
                continue
            for concept_slug in concept_slugs:
                suggestion_scores.setdefault((source_id, concept_slug), set()).add(term)

    link_suggestions: list[dict[str, Any]] = []
    for (source_id, concept_slug), shared_terms in suggestion_scores.items():
        source_node = source_node_by_id.get(source_id)
        concept_node = concept_node_by_slug.get(concept_slug)
        if not source_node or not concept_node:
            continue
        link_suggestions.append(
            {
                "source_id": source_id,
                "source_title": source_node["title"],
                "source_page": source_node["source_page"],
                "concept_slug": concept_slug,
                "concept_title": concept_node["title"],
                "concept_page": f"wiki/concepts/{concept_slug}.md",
                "shared_terms": sorted(shared_terms),
                "score": len(shared_terms),
                "component_id": concept_component_ids.get(concept_slug, ""),
            }
        )
    link_suggestions.sort(
        key=lambda item: (-item["score"], item["source_title"].lower(), item["concept_title"].lower())
    )

    actions: list[dict[str, Any]] = []
    for suggestion in link_suggestions[:12]:
        shared_terms = suggestion.get("shared_terms", [])
        actions.append(
            {
                "id": f"link-{suggestion['source_id']}-{suggestion['concept_slug']}",
                "kind": "add-source-concept-link",
                "priority": "high" if suggestion["score"] >= 3 else "medium",
                "title": f"补连 {suggestion['source_title']} -> {suggestion['concept_title']}",
                "primary_path": suggestion["source_page"],
                "secondary_path": suggestion["concept_page"],
                "component_id": suggestion.get("component_id", ""),
                "reason": f"共享词：{', '.join(shared_terms[:6]) or 'none'}",
                "score": suggestion["score"],
                "source_ids": [suggestion["source_id"]],
                "concept_slugs": [suggestion["concept_slug"]],
            }
        )

    suggested_source_ids = {action["source_ids"][0] for action in actions if action.get("source_ids")}
    for source_id in isolated_source_ids:
        if source_id in suggested_source_ids:
            continue
        source_node = source_node_by_id.get(source_id)
        if not source_node:
            continue
        actions.append(
            {
                "id": f"isolated-source-{source_id}",
                "kind": "connect-isolated-source",
                "priority": "medium",
                "title": f"连接孤立来源 {source_node['title']}",
                "primary_path": source_node["source_page"],
                "secondary_path": "",
                "component_id": source_component_ids.get(source_id, ""),
                "reason": "来源节点当前没有接入任何概念。",
                "score": 1,
                "source_ids": [source_id],
                "concept_slugs": [],
            }
        )

    for concept_slug in singleton_concept_slugs[:8]:
        concept_node = concept_node_by_slug.get(concept_slug)
        if not concept_node:
            continue
        source_count = len(concept_to_sources.get(concept_slug, set()))
        actions.append(
            {
                "id": f"singleton-concept-{concept_slug}",
                "kind": "expand-singleton-concept",
                "priority": "medium",
                "title": f"扩展单节点概念 {concept_node['title']}",
                "primary_path": f"wiki/concepts/{concept_slug}.md",
                "secondary_path": "",
                "component_id": concept_component_ids.get(concept_slug, ""),
                "reason": f"当前只关联 `{source_count}` 个来源，且没有概念间连接。",
                "score": max(1, source_count),
                "source_ids": sorted(concept_to_sources.get(concept_slug, set())),
                "concept_slugs": [concept_slug],
            }
        )

    for concept_slug in overloaded_concept_slugs[:8]:
        concept_node = concept_node_by_slug.get(concept_slug)
        if not concept_node:
            continue
        source_count = len(concept_to_sources.get(concept_slug, set()))
        actions.append(
            {
                "id": f"overloaded-concept-{concept_slug}",
                "kind": "split-overloaded-concept",
                "priority": "high" if source_count >= 6 else "medium",
                "title": f"拆分过载概念 {concept_node['title']}",
                "primary_path": f"wiki/concepts/{concept_slug}.md",
                "secondary_path": "",
                "component_id": concept_component_ids.get(concept_slug, ""),
                "reason": f"当前挂接 `{source_count}` 个来源，可能过宽。",
                "score": source_count,
                "source_ids": sorted(concept_to_sources.get(concept_slug, set())),
                "concept_slugs": [concept_slug],
            }
        )

    for concept_slug in bridge_concept_slugs[:6]:
        concept_node = concept_node_by_slug.get(concept_slug)
        if not concept_node:
            continue
        related_count = len(concept_related.get(concept_slug, set()))
        actions.append(
            {
                "id": f"bridge-concept-{concept_slug}",
                "kind": "monitor-bridge-concept",
                "priority": "low",
                "title": f"观察桥接概念 {concept_node['title']}",
                "primary_path": f"wiki/concepts/{concept_slug}.md",
                "secondary_path": "",
                "component_id": concept_component_ids.get(concept_slug, ""),
                "reason": f"概念连接 `{related_count}` 个相关概念，属于图谱桥接点。",
                "score": related_count,
                "source_ids": sorted(concept_to_sources.get(concept_slug, set())),
                "concept_slugs": [concept_slug],
            }
        )

    priority_order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(
        key=lambda item: (
            priority_order.get(str(item.get("priority")), 9),
            -int(item.get("score", 0)),
            str(item.get("title", "")).lower(),
            str(item.get("id", "")),
        )
    )
    action_counts = {
        "total": len(actions),
        "by_priority": {
            priority: sum(1 for action in actions if action.get("priority") == priority)
            for priority in ("high", "medium", "low")
        },
        "by_kind": {
            kind: sum(1 for action in actions if action.get("kind") == kind)
            for kind in (
                "add-source-concept-link",
                "connect-isolated-source",
                "expand-singleton-concept",
                "split-overloaded-concept",
                "monitor-bridge-concept",
            )
        },
    }

    return {
        "isolated_source_ids": isolated_source_ids,
        "singleton_concept_slugs": singleton_concept_slugs,
        "bridge_concept_slugs": bridge_concept_slugs[:10],
        "overloaded_concept_slugs": overloaded_concept_slugs,
        "hub_concepts": hub_concepts[:10],
        "hub_sources": hub_sources[:10],
        "link_suggestions": link_suggestions[:12],
        "actions": actions[:20],
        "action_counts": action_counts,
        "component_count": len(component_sizes),
        "component_sizes": component_sizes,
        "components": components,
        "source_component_ids": source_component_ids,
        "concept_component_ids": concept_component_ids,
    }


def reconcile_machine_memory_actions(
    root: Path,
    health: dict[str, Any],
    *,
    compiled_at: str,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    previous_state = load_machine_memory_action_state(root)
    previous_by_id = {
        str(action.get("id")): action for action in previous_state.get("actions", []) if action.get("id")
    }
    now = parse_iso_datetime(compiled_at) or datetime.now(timezone.utc)
    active_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for action in health.get("actions", []):
        action_id = str(action.get("id") or "").strip()
        if not action_id:
            continue
        previous = previous_by_id.get(action_id, {})
        previous_status = str(previous.get("status") or "proposed")
        protocol = str(previous.get("protocol") or action.get("protocol") or active_protocol or DEFAULT_PROTOCOL)
        status = previous_status if previous_status in ACTION_STATUSES else "proposed"
        reopened_count = int(previous.get("reopened_count") or 0)
        reopened_from = ""
        if previous and previous.get("active") is False and status in {"resolved", "rejected"}:
            reopened_from = status
            reopened_count += 1
            status = "proposed"
        first_seen_at = str(previous.get("first_seen_at") or compiled_at)
        occurrences = int(previous.get("occurrences") or 0)
        if occurrences <= 0:
            occurrences = 1
        else:
            occurrences += 1
        status_updated_at = str(previous.get("status_updated_at") or first_seen_at)
        if status != previous_status or not status_updated_at:
            status_updated_at = compiled_at
        reviewed_at = str(previous.get("reviewed_at") or "")
        review_note = str(previous.get("review_note") or "")
        last_receipt_path = str(previous.get("last_receipt_path") or "")
        revisit_after = str(previous.get("revisit_after") or "")
        escalate_after = str(previous.get("escalate_after") or "")
        if status in PENDING_ACTION_STATUSES:
            if not revisit_after and not escalate_after:
                base_timestamp = reviewed_at or status_updated_at or first_seen_at
                revisit_after, escalate_after = schedule_review_windows("action", status, base_timestamp)
        else:
            revisit_after, escalate_after = "", ""
        record = {
            **action,
            "protocol": protocol,
            "status": status,
            "active": True,
            "first_seen_at": first_seen_at,
            "last_seen_at": compiled_at,
            "occurrences": occurrences,
            "status_updated_at": status_updated_at,
            "reviewed_at": reviewed_at,
            "review_note": review_note,
            "last_receipt_path": last_receipt_path,
            "revisit_after": revisit_after,
            "escalate_after": escalate_after,
            "reopened_count": reopened_count,
            "reopened_from": reopened_from,
            "inactive_since": "",
            "pending_review": "true" if action_needs_review(status) else "false",
        }
        record.update(evaluate_page_aging(record, now=now))
        active_records.append(record)
        seen_ids.add(action_id)

    inactive_records: list[dict[str, Any]] = []
    for action_id, previous in previous_by_id.items():
        if action_id in seen_ids:
            continue
        preserved_pending = (
            bool(previous.get("active", True))
            and str(previous.get("status") or "") in PENDING_ACTION_STATUSES
            and str(previous.get("kind") or "") in LOW_RISK_APPLYABLE_ACTION_KINDS
        )
        if preserved_pending:
            try:
                validate_low_risk_action_targets(root, previous)
            except RuntimeError:
                preserved_pending = False
        if preserved_pending:
            status = str(previous.get("status") or "proposed")
            reviewed_at = str(previous.get("reviewed_at") or "")
            first_seen_at = str(previous.get("first_seen_at") or compiled_at)
            status_updated_at = str(previous.get("status_updated_at") or first_seen_at)
            revisit_after = str(previous.get("revisit_after") or "")
            escalate_after = str(previous.get("escalate_after") or "")
            if not revisit_after and not escalate_after:
                base_timestamp = reviewed_at or status_updated_at or first_seen_at
                revisit_after, escalate_after = schedule_review_windows("action", status, base_timestamp)
            record = {
                **dict(previous),
                "protocol": str(previous.get("protocol") or active_protocol or DEFAULT_PROTOCOL),
                "status": status,
                "active": True,
                "last_seen_at": compiled_at,
                "inactive_since": "",
                "pending_review": "true" if action_needs_review(status) else "false",
                "revisit_after": revisit_after,
                "escalate_after": escalate_after,
            }
            record.update(evaluate_page_aging(record, now=now))
            active_records.append(record)
            seen_ids.add(action_id)
            continue
        record = dict(previous)
        record["protocol"] = str(previous.get("protocol") or active_protocol or DEFAULT_PROTOCOL)
        record["active"] = False
        record["inactive_since"] = str(previous.get("inactive_since") or compiled_at)
        record["pending_review"] = "false"
        record["aging_state"] = ""
        record["overdue_review"] = "false"
        record["escalation_candidate"] = "false"
        inactive_records.append(record)

    active_records.sort(
        key=lambda item: (
            action_status_rank(str(item.get("status"))),
            action_priority_rank(str(item.get("priority"))),
            -int(item.get("occurrences", 0)),
            -int(item.get("score", 0)),
            str(item.get("title", "")).lower(),
        )
    )
    inactive_records.sort(
        key=lambda item: (
            str(item.get("inactive_since") or item.get("last_seen_at") or ""),
            str(item.get("title", "")).lower(),
        ),
        reverse=True,
    )
    overdue_actions = [record for record in active_records if record.get("overdue_review") == "true"]
    escalated_actions = [record for record in active_records if record.get("escalation_candidate") == "true"]
    active_records = [{**record, **describe_machine_memory_action(record)} for record in active_records]
    inactive_records = [{**record, **describe_machine_memory_action(record)} for record in inactive_records]
    overdue_actions = [{**record, **describe_machine_memory_action(record)} for record in overdue_actions]
    escalated_actions = [{**record, **describe_machine_memory_action(record)} for record in escalated_actions]
    counts = {
        "total": len(active_records),
        "inactive": len(inactive_records),
        "overdue": len(overdue_actions),
        "escalated": len(escalated_actions),
        "by_priority": {
            priority: sum(1 for action in active_records if action.get("priority") == priority)
            for priority in ("high", "medium", "low")
        },
        "by_status": {
            status: sum(1 for action in active_records if action.get("status") == status)
            for status in ACTION_STATUSES
        },
        "by_kind": {
            kind: sum(1 for action in active_records if action.get("kind") == kind)
            for kind in (
                "add-source-concept-link",
                "connect-isolated-source",
                "expand-singleton-concept",
                "split-overloaded-concept",
                "monitor-bridge-concept",
            )
        },
    }
    state_document = {
        "version": 1,
        "compiled_at": compiled_at,
        "actions": active_records + inactive_records,
    }
    save_machine_memory_action_state(root, state_document)
    return {
        "actions": active_records[:20],
        "inactive_actions": inactive_records[:12],
        "overdue_actions": overdue_actions[:10],
        "escalated_actions": escalated_actions[:10],
        "action_counts": counts,
        "action_state_path": relative_path(root, machine_memory_action_state_path(root)),
    }


def machine_memory_digest(memory: dict[str, Any]) -> str:
    payload = {
        "source_nodes": memory.get("source_nodes", []),
        "concept_nodes": memory.get("concept_nodes", []),
        "edges": memory.get("edges", {}),
        "citation_map": memory.get("citation_map", []),
        "term_index": memory.get("term_index", {}),
        "drift": memory.get("drift", {}),
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def build_machine_memory_graph(memory: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for node in memory.get("source_nodes", []):
        nodes.append(
            {
                "id": f"source:{node['id']}",
                "kind": "source",
                "title": node["title"],
                "source_type": node["source_type"],
                "source_page": node["source_page"],
                "stored_path": node["stored_path"],
            }
        )
    for node in memory.get("concept_nodes", []):
        nodes.append(
            {
                "id": f"concept:{node['slug']}",
                "kind": "concept",
                "title": node["title"],
                "source_pages": node["source_pages"],
            }
        )
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        edges.append(
            {
                "source": f"source:{edge['source_id']}",
                "target": f"concept:{edge['concept_slug']}",
                "type": "HAS_CONCEPT",
            }
        )
    for edge in memory.get("edges", {}).get("concept_to_concept", []):
        edges.append(
            {
                "source": f"concept:{edge['from']}",
                "target": f"concept:{edge['to']}",
                "type": "RELATED_CONCEPT",
            }
        )
    graph = {
        "version": 1,
        "compiled_at": memory["compiled_at"],
        "nodes": sorted(nodes, key=lambda item: (item["kind"], item["id"])),
        "edges": sorted(edges, key=lambda item: (item["type"], item["source"], item["target"])),
    }
    graph["digest"] = sha256_bytes(json.dumps({"nodes": graph["nodes"], "edges": graph["edges"]}, sort_keys=True).encode("utf-8"))
    return graph


def render_machine_memory_graph_html(memory: dict[str, Any], graph: dict[str, Any]) -> str:
    health = memory.get("health", {})
    source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    components = health.get("components", [])
    if not components and (source_nodes or concept_nodes):
        components = [
            {
                "id": "component-1",
                "source_ids": sorted(source_nodes),
                "concept_slugs": sorted(concept_nodes),
                "size": len(source_nodes) + len(concept_nodes),
            }
        ]

    positions: dict[str, tuple[int, int]] = {}
    sections: list[dict[str, Any]] = []
    current_y = 36
    section_width = 980
    for component in components:
        source_ids = [source_id for source_id in component.get("source_ids", []) if source_id in source_nodes]
        concept_slugs = [slug for slug in component.get("concept_slugs", []) if slug in concept_nodes]
        if not source_ids and not concept_slugs:
            continue
        row_count = max(len(source_ids), len(concept_slugs), 1)
        row_gap = 68
        section_height = 96 + max(row_count - 1, 0) * row_gap
        row_top = current_y + 52
        for index, source_id in enumerate(source_ids):
            positions[f"source:{source_id}"] = (220, row_top + index * row_gap)
        for index, concept_slug in enumerate(concept_slugs):
            positions[f"concept:{concept_slug}"] = (820, row_top + index * row_gap)
        sections.append(
            {
                "id": component.get("id", "component"),
                "y": current_y,
                "height": section_height,
                "source_ids": source_ids,
                "concept_slugs": concept_slugs,
            }
        )
        current_y += section_height + 28

    view_height = max(current_y + 24, 320)

    def truncate_label(text: str, limit: int = 30) -> str:
        return text if len(text) <= limit else f"{text[: limit - 3]}..."

    edge_fragments: list[str] = []
    degree_map: dict[str, int] = {}
    for edge in graph.get("edges", []):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in positions or target not in positions:
            continue
        degree_map[source] = degree_map.get(source, 0) + 1
        degree_map[target] = degree_map.get(target, 0) + 1
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        if str(edge.get("type") or "") == "RELATED_CONCEPT":
            stroke = "#f59e0b"
            dash = ' stroke-dasharray="8 6"'
        else:
            stroke = "#94a3b8"
            dash = ""
        edge_fragments.append(
            f'<line class="graph-edge" data-source="{html.escape(source)}" data-target="{html.escape(target)}" '
            f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="2"{dash} opacity="0.72" />'
        )

    node_fragments: list[str] = []
    node_rows: list[str] = []
    node_records: list[dict[str, Any]] = []
    source_component_ids = health.get("source_component_ids", {})
    concept_component_ids = health.get("concept_component_ids", {})
    component_label_by_id = {str(component.get("id") or ""): str(component.get("id") or "") for component in components}
    for node in graph.get("nodes", []):
        node_id = str(node.get("id") or "")
        position = positions.get(node_id)
        if not position:
            continue
        x, y = position
        kind = str(node.get("kind") or "concept")
        title = str(node.get("title") or node_id)
        if kind == "source":
            fill = "#0f766e"
            stroke = "#115e59"
            page_path = str(node.get("source_page") or "")
            href = f"../../{html.escape(page_path)}"
            subtitle = str(node.get("source_type") or "source")
            component_id = str(source_component_ids.get(node_id.removeprefix("source:"), "") or "")
            secondary_metric = str(node.get("stored_path") or "")
        else:
            fill = "#1d4ed8"
            stroke = "#1e40af"
            slug = node_id.removeprefix("concept:")
            page_path = f"wiki/concepts/{slug}.md"
            href = f"../../wiki/concepts/{html.escape(slug)}.md"
            subtitle = "concept"
            component_id = str(concept_component_ids.get(slug, "") or "")
            secondary_metric = f"source_pages {len(node.get('source_pages', []))}"
        safe_title = html.escape(title)
        label = html.escape(truncate_label(title))
        rx = x - 120
        ry = y - 22
        component_label = component_label_by_id.get(component_id, component_id or "none")
        node_fragments.append(
            "\n".join(
                [
                    f'<g class="graph-node" data-node-id="{html.escape(node_id)}" data-kind="{html.escape(kind)}" data-component="{html.escape(component_id)}" data-title="{safe_title.lower()}">',
                    f'  <a href="{href}">',
                    f'    <title>{safe_title}</title>',
                    f'    <rect x="{rx}" y="{ry}" width="240" height="44" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2" />',
                    f'    <text x="{x}" y="{y - 3}" text-anchor="middle" fill="#ffffff" font-size="14" font-weight="700">{label}</text>',
                    f'    <text x="{x}" y="{y + 14}" text-anchor="middle" fill="#dbeafe" font-size="11">{html.escape(subtitle)}</text>',
                    "  </a>",
                    "</g>",
                ]
            )
        )
        node_rows.append(
            "<li class=\"node-row\""
            f" data-node-id=\"{html.escape(node_id)}\""
            f" data-kind=\"{html.escape(kind)}\""
            f" data-component=\"{html.escape(component_id)}\""
            f" data-title=\"{safe_title.lower()}\">"
            f"<button type=\"button\" class=\"node-detail-button\" data-node-id=\"{html.escape(node_id)}\">详情</button> "
            f"<a href=\"{href}\">{safe_title}</a>"
            f" <span class=\"node-meta\">{html.escape(subtitle)} · {html.escape(component_label)} · degree {degree_map.get(node_id, 0)}</span>"
            "</li>"
        )
        node_records.append(
            {
                "id": node_id,
                "kind": kind,
                "title": title,
                "subtitle": subtitle,
                "href": href,
                "page_path": page_path,
                "component_id": component_id,
                "component_label": component_label,
                "degree": degree_map.get(node_id, 0),
                "secondary_metric": secondary_metric,
            }
        )

    section_fragments: list[str] = []
    for section in sections:
        section_fragments.append(
            f'<rect x="20" y="{section["y"]}" width="{section_width}" height="{section["height"]}" rx="18" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5" />'
        )
        section_fragments.append(
            f'<text x="44" y="{section["y"] + 28}" fill="#0f172a" font-size="15" font-weight="700">{html.escape(section["id"])}</text>'
        )
        section_fragments.append(
            f'<text x="44" y="{section["y"] + 48}" fill="#475569" font-size="12">sources {len(section["source_ids"])} | concepts {len(section["concept_slugs"])}</text>'
        )

    hub_concepts = health.get("hub_concepts", [])
    hub_sources = health.get("hub_sources", [])
    actions = health.get("action_counts", {})
    repair_counts = health.get("repair_plan", {}).get("counts", {})
    rewrite_counts = health.get("concept_rewrite", {}).get("counts", {})
    safe_apply_actions = [
        action for action in health.get("repair_plan", {}).get("ready_actions", []) if action_supports_low_risk_apply(action)
    ]
    summary_items = [
        f"来源节点 {len(memory.get('source_nodes', []))}",
        f"概念节点 {len(memory.get('concept_nodes', []))}",
        f"分量 {health.get('component_count', 0)}",
        f"桥接概念 {len(health.get('bridge_concept_slugs', []))}",
        f"修复动作 {actions.get('total', 0)}",
        f"执行提案 {repair_counts.get('proposals', 0)}",
        f"rewrite 提案 {rewrite_counts.get('active', 0)}",
        f"safe apply {len(safe_apply_actions)}",
    ]

    hub_concept_items = "".join(
        f'<li><a href="../../wiki/concepts/{html.escape(item["slug"])}.md">{html.escape(item["title"])}</a> | sources {item.get("source_count", 0)} | related {item.get("related_count", 0)}</li>'
        for item in hub_concepts[:8]
    ) or "<li>当前没有 hub 概念。</li>"
    hub_source_items = "".join(
        f'<li><a href="../../wiki/sources/{html.escape(item["id"])}.md">{html.escape(item["title"])}</a> | concepts {item.get("concept_count", 0)}</li>'
        for item in hub_sources[:8]
    ) or "<li>当前没有 hub 来源。</li>"
    suggestion_items = "".join(
        f'<li><a href="../../wiki/sources/{html.escape(item["source_id"])}.md">{html.escape(item["source_title"])}</a> -> <a href="../../wiki/concepts/{html.escape(item["concept_slug"])}.md">{html.escape(item["concept_title"])}</a> | score {item.get("score", 0)} | shared {html.escape(", ".join(item.get("shared_terms", [])[:5]) or "none")}</li>'
        for item in health.get("link_suggestions", [])[:8]
    ) or "<li>当前没有修复候选。</li>"
    apply_ready_items = "".join(
        f'<li>{html.escape(str(action.get("title") or action.get("id") or "action"))} | command <code>{html.escape(str(action.get("command_hint") or ""))}</code></li>'
        for action in safe_apply_actions[:8]
        if action.get("command_hint")
    ) or "<li>当前没有可直接 semi-auto apply 的动作。</li>"
    component_options = "".join(
        f'<option value="{html.escape(str(component.get("id") or ""))}">{html.escape(str(component.get("id") or ""))} ({len(component.get("source_ids", [])) + len(component.get("concept_slugs", []))})</option>'
        for component in components
        if component.get("id")
    )
    node_rows_markup = "".join(node_rows) or "<li>当前没有可浏览的节点。</li>"
    node_payload = html_safe_json_literal(
        {
            "nodes": node_records,
            "defaultNodeId": node_records[0]["id"] if node_records else "",
        }
    )

    empty_state = ""
    if not graph.get("nodes"):
        empty_state = '<div class="empty">当前还没有 machine-memory 节点。先投料并运行 compile，再打开这个页面。</div>'

    svg_body = "\n".join(section_fragments + edge_fragments + node_fragments)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Machine Memory Graph</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f8fafc; --ink: #0f172a; --muted: #475569; --panel: #ffffff; --line: #cbd5e1; }",
            "    body { margin: 0; padding: 24px; background: linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1120px; margin: 0 auto; }",
            "    h1, h2 { margin: 0 0 12px; }",
            "    p { margin: 0 0 12px; color: var(--muted); }",
            "    .meta, .cards, .lists { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin: 18px 0 24px; }",
            "    .card, .panel { background: rgba(255,255,255,0.92); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #1d4ed8; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    .panel { padding: 18px; margin-bottom: 18px; }",
            "    .controls { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-bottom: 18px; }",
            "    label { display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }",
            "    input, select { width: 100%; padding: 10px 12px; border: 1px solid var(--line); border-radius: 12px; font: inherit; background: #fff; }",
            "    .canvas { overflow-x: auto; }",
            "    svg { width: 100%; min-width: 1020px; height: auto; display: block; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 4px 0; }",
            "    a { color: #1d4ed8; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    .lists { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }",
            "    .workbench { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(320px, 1fr); gap: 18px; align-items: start; }",
            "    .node-browser { max-height: 560px; overflow: auto; }",
            "    .node-browser ul { list-style: none; padding-left: 0; }",
            "    .node-row { padding: 10px 0; border-bottom: 1px solid #e2e8f0; }",
            "    .node-row:last-child { border-bottom: 0; }",
            "    .node-meta { color: var(--muted); font-size: 12px; }",
            "    .node-detail-button { margin-right: 8px; border: 1px solid var(--line); background: #eff6ff; color: #1d4ed8; border-radius: 999px; padding: 2px 10px; cursor: pointer; }",
            "    .graph-node.hidden, .graph-edge.hidden, .node-row.hidden { display: none; }",
            "    .details-grid { display: grid; gap: 10px; }",
            "    .details-grid code { background: #eff6ff; padding: 2px 6px; border-radius: 8px; }",
            "    .legend { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 12px; color: var(--muted); }",
            "    .legend span::before { content: ''; display: inline-block; width: 12px; height: 12px; border-radius: 999px; margin-right: 6px; vertical-align: -1px; }",
            "    .legend .source::before { background: #0f766e; }",
            "    .legend .concept::before { background: #1d4ed8; }",
            "    .legend .related::before { background: #f59e0b; }",
            "    .empty { padding: 16px; background: #fff7ed; border: 1px solid #fdba74; border-radius: 14px; color: #9a3412; }",
            "    @media (max-width: 960px) { .workbench { grid-template-columns: 1fr; } }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            "  <section class=\"panel\">",
            "    <h1>Machine Memory Graph</h1>",
            f"    <p>编译时间：<code>{html.escape(str(memory.get('compiled_at', '')))}</code> | 图谱摘要：<code>{html.escape(str(graph.get('digest', '')))}</code></p>",
            "    <p>这是炼丹炉 machine-memory 的本地图谱视图。来源节点与概念节点按连通分量分块展示，直接点击节点可跳回对应的 wiki 页面。</p>",
            "    <div class=\"meta\">",
            *[f'      <div class="card"><div class="metric">{html.escape(item.split()[-1])}</div><div class="metric-label">{html.escape(" ".join(item.split()[:-1]) or item)}</div></div>' for item in summary_items],
            "    </div>",
            "    <div class=\"legend\">",
            '      <span class="source">source</span>',
            '      <span class="concept">concept</span>',
            '      <span class="related">related edge</span>',
            "    </div>",
            "  </section>",
            f"  {empty_state}",
            '  <section class="panel">',
            '    <div class="controls">',
            '      <div><label for="graph-search">搜索节点</label><input id="graph-search" type="search" placeholder="输入标题、slug、source id" /></div>',
            '      <div><label for="graph-kind">节点类型</label><select id="graph-kind"><option value="">全部</option><option value="source">source</option><option value="concept">concept</option></select></div>',
            f'      <div><label for="graph-component">分量</label><select id="graph-component"><option value="">全部分量</option>{component_options}</select></div>',
            "    </div>",
            '    <div class="workbench">',
            '      <div class="panel canvas">',
            f'        <svg viewBox="0 0 1020 {view_height}" role="img" aria-label="machine memory graph">',
            f"{svg_body}",
            "        </svg>",
            "      </div>",
            '      <div class="details-grid">',
            '        <div class="panel"><h2>节点详情</h2><div id="graph-node-details">选择右侧节点详情按钮，查看 component、degree 和回链路径。</div></div>',
            '        <div class="panel node-browser"><h2>节点浏览器</h2><ul id="graph-node-browser">',
            f"{node_rows_markup}",
            "        </ul></div>",
            "      </div>",
            "    </div>",
            "  </section>",
            "  <section class=\"lists\">",
            '    <div class="panel"><h2>Hub 概念</h2><ul>',
            f"{hub_concept_items}",
            "    </ul></div>",
            '    <div class="panel"><h2>Hub 来源</h2><ul>',
            f"{hub_source_items}",
            "    </ul></div>",
            '    <div class="panel"><h2>修复候选</h2><ul>',
            f"{suggestion_items}",
            "    </ul></div>",
            '    <div class="panel"><h2>Safe Apply</h2><ul>',
            f"{apply_ready_items}",
            "    </ul></div>",
            "  </section>",
            '  <section class="panel"><h2>相关入口</h2><ul>',
            '    <li><a href="../../wiki/indexes/furnace-center.md">炉心面板</a></li>',
            '    <li><a href="../../wiki/indexes/graph-view.md">Graph View Dashboard</a></li>',
            '    <li><a href="../../wiki/indexes/machine-memory.md">机器记忆</a></li>',
            '    <li><a href="../../wiki/indexes/machine-memory-topology.md">机器记忆拓扑</a></li>',
            '    <li><a href="../../wiki/indexes/graph-health.md">图谱健康</a></li>',
            '    <li><a href="../../wiki/indexes/machine-memory-repair-plan.md">修复计划</a></li>',
            "  </ul></section>",
            "  <script>",
            f"    const graphUiData = {node_payload};",
            "    const nodeMap = new Map((graphUiData.nodes || []).map((node) => [node.id, node]));",
            "    const searchInput = document.getElementById('graph-search');",
            "    const kindSelect = document.getElementById('graph-kind');",
            "    const componentSelect = document.getElementById('graph-component');",
            "    const nodeDetails = document.getElementById('graph-node-details');",
            "    function renderDetails(nodeId) {",
            "      const node = nodeMap.get(nodeId);",
            "      if (!node) { nodeDetails.innerHTML = '当前没有可展示的节点详情。'; return; }",
            "      nodeDetails.innerHTML = [",
            "        `<div><strong>${node.title}</strong></div>`,",
            "        `<div>kind: <code>${node.kind}</code></div>`,",
            "        `<div>component: <code>${node.component_label || 'none'}</code></div>`,",
            "        `<div>degree: <code>${node.degree}</code></div>`,",
            "        `<div>path: <code>${node.page_path}</code></div>`,",
            "        `<div>${node.secondary_metric || ''}</div>`,",
            "        `<div><a href=\"${node.href}\">打开页面</a></div>`",
            "      ].join('');",
            "    }",
            "    function applyFilters() {",
            "      const needle = (searchInput.value || '').trim().toLowerCase();",
            "      const kind = kindSelect.value || '';",
            "      const component = componentSelect.value || '';",
            "      const visibleIds = new Set();",
            "      document.querySelectorAll('.graph-node').forEach((element) => {",
            "        const title = element.dataset.title || '';",
            "        const nodeKind = element.dataset.kind || '';",
            "        const nodeComponent = element.dataset.component || '';",
            "        const nodeId = element.dataset.nodeId || '';",
            "        const matches = (!needle || title.includes(needle) || nodeId.toLowerCase().includes(needle))",
            "          && (!kind || nodeKind === kind)",
            "          && (!component || nodeComponent === component);",
            "        element.classList.toggle('hidden', !matches);",
            "        if (matches) visibleIds.add(nodeId);",
            "      });",
            "      document.querySelectorAll('.graph-edge').forEach((element) => {",
            "        const visible = visibleIds.has(element.dataset.source || '') && visibleIds.has(element.dataset.target || '');",
            "        element.classList.toggle('hidden', !visible);",
            "      });",
            "      document.querySelectorAll('.node-row').forEach((element) => {",
            "        const title = element.dataset.title || '';",
            "        const nodeKind = element.dataset.kind || '';",
            "        const nodeComponent = element.dataset.component || '';",
            "        const nodeId = element.dataset.nodeId || '';",
            "        const matches = (!needle || title.includes(needle) || nodeId.toLowerCase().includes(needle))",
            "          && (!kind || nodeKind === kind)",
            "          && (!component || nodeComponent === component);",
            "        element.classList.toggle('hidden', !matches);",
            "      });",
            "      if (!visibleIds.size) {",
            "        nodeDetails.innerHTML = '当前筛选条件下没有节点。';",
            "        return;",
            "      }",
            "      const firstVisible = document.querySelector('.node-row:not(.hidden)');",
            "      if (firstVisible) renderDetails(firstVisible.dataset.nodeId || '');",
            "    }",
            "    document.querySelectorAll('.node-detail-button').forEach((button) => {",
            "      button.addEventListener('click', () => renderDetails(button.dataset.nodeId || ''));",
            "    });",
            "    [searchInput, kindSelect, componentSelect].forEach((element) => element.addEventListener('input', applyFilters));",
            "    [kindSelect, componentSelect].forEach((element) => element.addEventListener('change', applyFilters));",
            "    renderDetails(graphUiData.defaultNodeId || '');",
            "    applyFilters();",
            "  </script>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def build_machine_memory_adjacency(memory: dict[str, Any]) -> dict[str, dict[str, str]]:
    adjacency: dict[str, dict[str, str]] = {}
    for node in memory.get("source_nodes", []):
        adjacency.setdefault(f"source:{node['id']}", {})
    for node in memory.get("concept_nodes", []):
        adjacency.setdefault(f"concept:{node['slug']}", {})
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        source_key = f"source:{edge['source_id']}"
        concept_key = f"concept:{edge['concept_slug']}"
        adjacency.setdefault(source_key, {})[concept_key] = "HAS_CONCEPT"
        adjacency.setdefault(concept_key, {})[source_key] = "HAS_CONCEPT"
    for edge in memory.get("edges", {}).get("concept_to_concept", []):
        left_key = f"concept:{edge['from']}"
        right_key = f"concept:{edge['to']}"
        adjacency.setdefault(left_key, {})[right_key] = "RELATED_CONCEPT"
        adjacency.setdefault(right_key, {})[left_key] = "RELATED_CONCEPT"
    return adjacency


def build_machine_memory_query(
    memory: dict[str, Any],
    question: str,
    *,
    protocol: str = DEFAULT_PROTOCOL,
    material_state: dict[str, Any] | None = None,
    routing_state: dict[str, Any] | None = None,
    archive_candidates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    term_index = memory.get("term_index", {})
    edges = memory.get("edges", {})
    source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    question_tokens = tokenize(question)
    health = memory.get("health", {})
    adjacency = build_machine_memory_adjacency(memory)
    material_state = material_state or {"entries": []}
    routing_state = routing_state or {"entries": []}
    archive_candidates = archive_candidates or {"entries": []}
    material_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in material_state.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    routing_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in routing_state.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    archive_candidates_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in archive_candidates.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    time_focus_state = machine_memory_query_time_focus(question)
    time_focus = str(time_focus_state.get("focus") or "")

    direct_source_scores: dict[str, int] = {}
    direct_concept_scores: dict[str, int] = {}
    matched_terms: list[str] = []

    source_to_concepts: dict[str, set[str]] = {}
    concept_to_sources: dict[str, set[str]] = {}
    for edge in edges.get("source_to_concept", []):
        source_id = edge.get("source_id")
        concept_slug = edge.get("concept_slug")
        if not isinstance(source_id, str) or not isinstance(concept_slug, str):
            continue
        source_to_concepts.setdefault(source_id, set()).add(concept_slug)
        concept_to_sources.setdefault(concept_slug, set()).add(source_id)

    related_concepts: dict[str, set[str]] = {}
    for edge in edges.get("concept_to_concept", []):
        left = edge.get("from")
        right = edge.get("to")
        if not isinstance(left, str) or not isinstance(right, str):
            continue
        related_concepts.setdefault(left, set()).add(right)
        related_concepts.setdefault(right, set()).add(left)

    for token in question_tokens:
        payload = term_index.get(token)
        if not isinstance(payload, dict):
            continue
        matched_terms.append(token)
        for source_id in payload.get("source_ids", []):
            if source_id in source_nodes:
                direct_source_scores[source_id] = direct_source_scores.get(source_id, 0) + 3
        for concept_slug in payload.get("concept_slugs", []):
            if concept_slug in concept_nodes:
                direct_concept_scores[concept_slug] = direct_concept_scores.get(concept_slug, 0) + 4

    expanded_source_scores = dict(direct_source_scores)
    expanded_concept_scores = dict(direct_concept_scores)
    supporting_edges: set[tuple[str, str, str]] = set()

    for source_id in list(direct_source_scores):
        for concept_slug in sorted(source_to_concepts.get(source_id, set())):
            expanded_concept_scores[concept_slug] = expanded_concept_scores.get(concept_slug, 0) + 2
            supporting_edges.add(("HAS_CONCEPT", source_id, concept_slug))

    for concept_slug in list(direct_concept_scores):
        for source_id in sorted(concept_to_sources.get(concept_slug, set())):
            expanded_source_scores[source_id] = expanded_source_scores.get(source_id, 0) + 2
            supporting_edges.add(("HAS_CONCEPT", source_id, concept_slug))
        for related_slug in sorted(related_concepts.get(concept_slug, set())):
            expanded_concept_scores[related_slug] = expanded_concept_scores.get(related_slug, 0) + 1
            supporting_edges.add(("RELATED_CONCEPT", concept_slug, related_slug))
            for source_id in sorted(concept_to_sources.get(related_slug, set())):
                expanded_source_scores[source_id] = expanded_source_scores.get(source_id, 0) + 1
                supporting_edges.add(("HAS_CONCEPT", source_id, related_slug))

    query_routes = build_machine_memory_query_routes(
        memory,
        adjacency,
        direct_source_scores,
        direct_concept_scores,
        expanded_source_scores,
        expanded_concept_scores,
    )
    for route in query_routes:
        for node in route["nodes"]:
            if node["kind"] == "source":
                expanded_source_scores[node["id"]] = expanded_source_scores.get(node["id"], 0) + 2
            else:
                expanded_concept_scores[node["slug"]] = expanded_concept_scores.get(node["slug"], 0) + 2
        for edge in route["edges"]:
            if edge["type"] == "HAS_CONCEPT":
                supporting_edges.add(("HAS_CONCEPT", edge["left"], edge["right"]))
            elif edge["type"] == "RELATED_CONCEPT":
                supporting_edges.add(("RELATED_CONCEPT", edge["left"], edge["right"]))

    source_rank_records = [
        machine_memory_source_runtime_record(
            source_id,
            base_score=base_score,
            source_nodes=source_nodes,
            material_by_entry=material_by_entry,
            routing_by_entry=routing_by_entry,
            archive_candidates_by_entry=archive_candidates_by_entry,
            protocol=protocol,
            time_focus=time_focus,
        )
        for source_id, base_score in expanded_source_scores.items()
        if source_id in source_nodes
    ]
    source_rank_records.sort(
        key=lambda item: (
            -float(item.get("combined_score", 0.0) or 0.0),
            -float(item.get("base_score", 0.0) or 0.0),
            -float(item.get("protocol_bonus", 0.0) or 0.0),
            -float(item.get("time_bonus", 0.0) or 0.0),
            str(item.get("title") or item.get("entry_id") or "").lower(),
        )
    )
    ranked_source_ids = [
        str(item.get("entry_id") or "")
        for item in source_rank_records[:8]
        if item.get("entry_id")
    ]
    ranked_concept_slugs = [
        concept_slug
        for concept_slug, _score in sorted(
            expanded_concept_scores.items(),
            key=lambda item: (-item[1], concept_nodes.get(item[0], {}).get("title", item[0]).lower()),
        )[:8]
    ]
    bridge_concept_slugs = [
        slug for slug in ranked_concept_slugs if slug in set(health.get("bridge_concept_slugs", []))
    ]
    protocol_shard_source_ids = [
        str(item.get("entry_id") or "")
        for item in source_rank_records
        if bool(item.get("protocol_shard")) and item.get("entry_id")
    ][:5]
    time_shard_source_ids = [
        str(item.get("entry_id") or "")
        for item in source_rank_records
        if bool(item.get("time_shard")) and item.get("entry_id")
    ][:5]
    archive_recall_hints = [
        {
            "entry_id": str(item.get("entry_id") or ""),
            "title": str(item.get("title") or item.get("entry_id") or ""),
            "path": str(item.get("path") or ""),
            "temperature": str(item.get("temperature") or ""),
            "archive_status": str(item.get("archive_status") or ""),
            "recommended_temperature": str(item.get("recommended_temperature") or ""),
            "reason_codes": list(item.get("reason_codes", []) or []),
        }
        for item in sorted(
            source_rank_records,
            key=lambda record: (
                -float(record.get("archive_hint_score", 0.0) or 0.0),
                -float(record.get("combined_score", 0.0) or 0.0),
                str(record.get("title") or record.get("entry_id") or "").lower(),
            ),
        )
        if bool(item.get("archive_hint")) and item.get("entry_id")
    ][:3]
    query_subgraph_sources = [
        {
            "id": source_id,
            "title": source_nodes[source_id]["title"],
            "path": source_nodes[source_id]["source_page"],
        }
        for source_id in ranked_source_ids
        if source_id in source_nodes
    ]
    query_subgraph_concepts = [
        {
            "slug": concept_slug,
            "title": concept_nodes[concept_slug]["title"],
            "path": f"wiki/concepts/{concept_slug}.md",
        }
        for concept_slug in ranked_concept_slugs
        if concept_slug in concept_nodes
    ]
    query_subgraph_edges = [
        {"type": edge_type, "left": left, "right": right}
        for edge_type, left, right in sorted(supporting_edges)
        if (edge_type == "HAS_CONCEPT" and left in ranked_source_ids and right in ranked_concept_slugs)
        or (edge_type == "RELATED_CONCEPT" and left in ranked_concept_slugs and right in ranked_concept_slugs)
    ]
    touched_component_ids = sorted(
        {
            component_id
            for component_id in (
                [health.get("source_component_ids", {}).get(source_id) for source_id in ranked_source_ids]
                + [health.get("concept_component_ids", {}).get(slug) for slug in ranked_concept_slugs]
            )
            if component_id
        }
    )
    touched_components = [
        component
        for component in health.get("components", [])
        if component.get("id") in touched_component_ids
    ]
    proposal_by_action_id = {
        str(proposal.get("action_id") or ""): proposal
        for proposal in health.get("repair_plan", {}).get("execution_proposals", [])
        if proposal.get("action_id")
    }
    relevant_actions: list[dict[str, Any]] = []
    ranked_source_set = set(ranked_source_ids) | set(direct_source_scores)
    ranked_concept_set = set(ranked_concept_slugs) | set(direct_concept_scores)
    for action in health.get("actions", []):
        if action.get("status") not in PENDING_ACTION_STATUSES:
            continue
        source_hit = bool(ranked_source_set & set(action.get("source_ids", [])))
        concept_hit = bool(ranked_concept_set & set(action.get("concept_slugs", [])))
        component_hit = bool(action.get("component_id")) and action.get("component_id") in touched_component_ids
        if not (source_hit or concept_hit or component_hit):
            continue
        proposal = proposal_by_action_id.get(str(action.get("id") or ""), {})
        relevant_actions.append(
            {
                "id": action["id"],
                "kind": action["kind"],
                "priority": action["priority"],
                "status": action.get("status", "proposed"),
                "title": action["title"],
                "primary_path": action["primary_path"],
                "secondary_path": action.get("secondary_path", ""),
                "reason": action.get("reason", ""),
                "execution_policy": action.get("execution_policy", "triage"),
                "next_step": action.get("next_step", ""),
                "command_hint": action.get("command_hint", ""),
                "apply_ready": action.get("apply_ready", "false"),
                "proposal_kind": proposal.get("proposal_kind", ""),
                "proposal_summary": proposal.get("summary", ""),
                "proposal_targets": proposal.get("target_paths", []),
                "focus_score": action_focus_score(protocol, action),
            }
        )
    relevant_actions.sort(
        key=lambda item: (
            0 if item.get("status") == "accepted" else 1,
            -int(item.get("focus_score", 0)),
            action_priority_rank(str(item.get("priority") or "")),
            str(item.get("title") or "").lower(),
        )
    )

    return {
        "matched_terms": matched_terms,
        "direct_source_ids": sorted(direct_source_scores),
        "direct_concept_slugs": sorted(direct_concept_scores),
        "time_focus": time_focus,
        "time_focus_markers": list(time_focus_state.get("markers", []) or []),
        "ranked_source_ids": ranked_source_ids,
        "ranked_concept_slugs": ranked_concept_slugs,
        "protocol_shard_source_ids": protocol_shard_source_ids,
        "time_shard_source_ids": time_shard_source_ids,
        "archive_recall_hints": archive_recall_hints,
        "bridge_concept_slugs": bridge_concept_slugs,
        "supporting_edges": [
            {"type": edge_type, "left": left, "right": right}
            for edge_type, left, right in sorted(supporting_edges)
        ],
        "query_routes": query_routes,
        "touched_component_ids": touched_component_ids,
        "touched_components": touched_components,
        "relevant_actions": relevant_actions[:6],
        "query_subgraph": {
            "sources": query_subgraph_sources,
            "concepts": query_subgraph_concepts,
            "edges": query_subgraph_edges,
        },
    }


def build_machine_memory_query_routes(
    memory: dict[str, Any],
    adjacency: dict[str, dict[str, str]],
    direct_source_scores: dict[str, int],
    direct_concept_scores: dict[str, int],
    expanded_source_scores: dict[str, int],
    expanded_concept_scores: dict[str, int],
) -> list[dict[str, Any]]:
    anchor_nodes = ranked_machine_memory_anchor_nodes(
        direct_source_scores,
        direct_concept_scores,
        expanded_source_scores,
        expanded_concept_scores,
    )
    routes: list[dict[str, Any]] = []
    seen_routes: set[tuple[str, ...]] = set()
    for index, start in enumerate(anchor_nodes):
        for goal in anchor_nodes[index + 1 :]:
            path = shortest_machine_memory_path(adjacency, start, goal)
            if len(path) < 2:
                continue
            route_key = tuple(path)
            if route_key in seen_routes:
                continue
            seen_routes.add(route_key)
            routes.append(render_machine_memory_route(memory, adjacency, path))
            if len(routes) >= 4:
                return routes
    return routes


def ranked_machine_memory_anchor_nodes(
    direct_source_scores: dict[str, int],
    direct_concept_scores: dict[str, int],
    expanded_source_scores: dict[str, int],
    expanded_concept_scores: dict[str, int],
) -> list[str]:
    anchors: list[str] = []
    for concept_slug, _score in sorted(direct_concept_scores.items(), key=lambda item: (-item[1], item[0]))[:4]:
        anchors.append(f"concept:{concept_slug}")
    for source_id, _score in sorted(direct_source_scores.items(), key=lambda item: (-item[1], item[0]))[:3]:
        anchors.append(f"source:{source_id}")
    if len(anchors) < 2:
        for concept_slug, _score in sorted(expanded_concept_scores.items(), key=lambda item: (-item[1], item[0]))[:4]:
            key = f"concept:{concept_slug}"
            if key not in anchors:
                anchors.append(key)
        for source_id, _score in sorted(expanded_source_scores.items(), key=lambda item: (-item[1], item[0]))[:3]:
            key = f"source:{source_id}"
            if key not in anchors:
                anchors.append(key)
    return anchors[:4]


def shortest_machine_memory_path(adjacency: dict[str, dict[str, str]], start: str, goal: str) -> list[str]:
    if start == goal:
        return [start]
    if start not in adjacency or goal not in adjacency:
        return []
    queue: deque[str] = deque([start])
    parents: dict[str, str | None] = {start: None}
    while queue:
        current = queue.popleft()
        for neighbor in sorted(adjacency.get(current, {})):
            if neighbor in parents:
                continue
            parents[neighbor] = current
            if neighbor == goal:
                queue.clear()
                break
            queue.append(neighbor)
    if goal not in parents:
        return []
    path: list[str] = []
    current: str | None = goal
    while current is not None:
        path.append(current)
        current = parents[current]
    return list(reversed(path))


def render_machine_memory_route(
    memory: dict[str, Any],
    adjacency: dict[str, dict[str, str]],
    path: list[str],
) -> dict[str, Any]:
    nodes = [machine_memory_node_metadata(memory, node_key) for node_key in path]
    edges: list[dict[str, str]] = []
    for left, right in zip(path, path[1:]):
        edge_type = adjacency.get(left, {}).get(right, "")
        if edge_type == "HAS_CONCEPT":
            if left.startswith("source:"):
                edges.append(
                    {
                        "type": edge_type,
                        "left": left.removeprefix("source:"),
                        "right": right.removeprefix("concept:"),
                    }
                )
            else:
                edges.append(
                    {
                        "type": edge_type,
                        "left": right.removeprefix("source:"),
                        "right": left.removeprefix("concept:"),
                    }
                )
        else:
            edges.append(
                {
                    "type": "RELATED_CONCEPT",
                    "left": left.removeprefix("concept:"),
                    "right": right.removeprefix("concept:"),
                }
            )
    return {
        "start": nodes[0],
        "goal": nodes[-1],
        "length": max(0, len(path) - 1),
        "nodes": nodes,
        "edges": edges,
    }


def machine_memory_node_metadata(memory: dict[str, Any], node_key: str) -> dict[str, Any]:
    if node_key.startswith("source:"):
        source_id = node_key.removeprefix("source:")
        source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
        node = source_nodes.get(source_id, {})
        return {
            "kind": "source",
            "id": source_id,
            "title": node.get("title", source_id),
            "path": node.get("source_page", f"wiki/sources/{source_id}.md"),
        }
    concept_slug = node_key.removeprefix("concept:")
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    node = concept_nodes.get(concept_slug, {})
    return {
        "kind": "concept",
        "slug": concept_slug,
        "title": node.get("title", concept_slug),
        "path": f"wiki/concepts/{concept_slug}.md",
    }


def summarize_machine_memory_transition(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_source_ids = {node["id"] for node in previous.get("source_nodes", [])}
    current_source_ids = {node["id"] for node in current.get("source_nodes", [])}
    previous_concept_slugs = {node["slug"] for node in previous.get("concept_nodes", [])}
    current_concept_slugs = {node["slug"] for node in current.get("concept_nodes", [])}
    previous_terms = set(previous.get("term_index", {}).keys())
    current_terms = set(current.get("term_index", {}).keys())
    previous_edges = {
        ("HAS_CONCEPT", edge["source_id"], edge["concept_slug"])
        for edge in previous.get("edges", {}).get("source_to_concept", [])
    } | {
        ("RELATED_CONCEPT", edge["from"], edge["to"])
        for edge in previous.get("edges", {}).get("concept_to_concept", [])
    }
    current_edges = {
        ("HAS_CONCEPT", edge["source_id"], edge["concept_slug"])
        for edge in current.get("edges", {}).get("source_to_concept", [])
    } | {
        ("RELATED_CONCEPT", edge["from"], edge["to"])
        for edge in current.get("edges", {}).get("concept_to_concept", [])
    }
    previous_digest = previous.get("digest", "")
    current_digest = current["digest"]
    return {
        "has_previous_snapshot": bool(previous_digest),
        "changed": previous_digest != current_digest,
        "previous_digest": previous_digest,
        "current_digest": current_digest,
        "added_source_ids": sorted(current_source_ids - previous_source_ids),
        "removed_source_ids": sorted(previous_source_ids - current_source_ids),
        "added_concept_slugs": sorted(current_concept_slugs - previous_concept_slugs),
        "removed_concept_slugs": sorted(previous_concept_slugs - current_concept_slugs),
        "added_terms": sorted(current_terms - previous_terms)[:25],
        "removed_terms": sorted(previous_terms - current_terms)[:25],
        "added_edges": len(current_edges - previous_edges),
        "removed_edges": len(previous_edges - current_edges),
    }


def append_machine_memory_history(root: Path, memory: dict[str, Any], transition: dict[str, Any]) -> None:
    path = machine_memory_history_path(root)
    if transition["has_previous_snapshot"] and not transition["changed"]:
        return
    entry = {
        "compiled_at": memory["compiled_at"],
        "digest": memory["digest"],
        "sources": len(memory.get("source_nodes", [])),
        "concepts": len(memory.get("concept_nodes", [])),
        "terms": len(memory.get("term_index", {})),
        "added_source_ids": transition["added_source_ids"],
        "removed_source_ids": transition["removed_source_ids"],
        "added_concept_slugs": transition["added_concept_slugs"],
        "removed_concept_slugs": transition["removed_concept_slugs"],
        "added_edges": transition["added_edges"],
        "removed_edges": transition["removed_edges"],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def render_drift_report(memory: dict[str, Any], transition: dict[str, Any]) -> str:
    drift = memory["drift"]
    lines = [
        "# 漂移报告",
        "",
        f"- 编译时间：`{memory['compiled_at']}`",
        f"- 当前摘要：`{memory['digest']}`",
        f"- 图谱摘要：`{memory['graph_digest']}`",
        "",
        "## 变化摘要",
    ]
    if not transition["has_previous_snapshot"]:
        lines.append("- 目前没有可对比的上一版机器记忆快照。")
    elif not transition["changed"]:
        lines.append("- 相比上一版快照，没有检测到结构性漂移。")
    else:
        lines.extend(
            [
                f"- 上一版摘要：`{transition['previous_digest']}`",
                f"- 新增来源节点：`{len(transition['added_source_ids'])}`",
                f"- 移除来源节点：`{len(transition['removed_source_ids'])}`",
                f"- 新增概念节点：`{len(transition['added_concept_slugs'])}`",
                f"- 移除概念节点：`{len(transition['removed_concept_slugs'])}`",
                f"- 新增边：`{transition['added_edges']}`",
                f"- 移除边：`{transition['removed_edges']}`",
                f"- 新增索引词（样本）：`{', '.join(transition['added_terms']) or 'none'}`",
                f"- 移除索引词（样本）：`{', '.join(transition['removed_terms']) or 'none'}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 当前漂移检查",
            f"- 缺失 raw 文件：`{len(drift['missing_raw_files'])}`",
            f"- 缺失来源页：`{len(drift['missing_source_pages'])}`",
            f"- 缺失概念页：`{len(drift['missing_concept_pages'])}`",
            f"- 无概念覆盖的来源：`{len(drift['sources_without_concepts'])}`",
            "",
            "## 机器记忆产物",
            "- 状态文件：`.aiwiki/state/machine-memory.json`",
            "- 图谱导出：`.aiwiki/cache/machine-memory-graph.json`",
            "- 历史记录：`.aiwiki/state/machine-memory-history.jsonl`",
        ]
    )
    return "\n".join(lines) + "\n"


def render_graph_health(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    lines = [
        "# 图谱健康",
        "",
        f"- 编译时间：`{memory['compiled_at']}`",
        f"- 连通分量数：`{health.get('component_count', 0)}`",
        f"- 分量大小：`{', '.join(str(size) for size in health.get('component_sizes', [])) or 'none'}`",
        f"- 孤立来源：`{len(health.get('isolated_source_ids', []))}`",
        f"- 单节点概念：`{len(health.get('singleton_concept_slugs', []))}`",
        f"- 桥接概念：`{len(health.get('bridge_concept_slugs', []))}`",
        f"- 过载概念：`{len(health.get('overloaded_concept_slugs', []))}`",
        f"- 修复动作：`{health.get('action_counts', {}).get('total', 0)}`",
        f"- 动作已到期：`{health.get('action_counts', {}).get('overdue', 0)}`",
        f"- 动作需升级：`{health.get('action_counts', {}).get('escalated', 0)}`",
        f"- 执行批次：`{health.get('repair_plan', {}).get('counts', {}).get('batches', 0)}`",
        f"- 执行提案：`{health.get('repair_plan', {}).get('counts', {}).get('proposals', 0)}`",
        f"- 页级 patch step：`{health.get('repair_plan', {}).get('counts', {}).get('patch_steps', 0)}`",
        "",
        "## 修复信号",
        f"- 孤立来源：`{', '.join(health.get('isolated_source_ids', [])[:10]) or 'none'}`",
        f"- 单节点概念：`{', '.join(health.get('singleton_concept_slugs', [])[:10]) or 'none'}`",
        f"- 桥接概念：`{', '.join(health.get('bridge_concept_slugs', [])[:10]) or 'none'}`",
        f"- 过载概念：`{', '.join(health.get('overloaded_concept_slugs', [])[:10]) or 'none'}`",
        f"- 修复候选：`{len(health.get('link_suggestions', []))}`",
        "",
        "## 最大分量",
    ]
    components = health.get("components", [])
    if not components:
        lines.append("- 暂无分量数据。")
    else:
        for component in components[:5]:
            lines.append(
                f"- `{component['id']}` size `{component['size']}`"
                f" | sources `{', '.join(component.get('source_ids', [])[:4]) or 'none'}`"
                f" | concepts `{', '.join(component.get('concept_slugs', [])[:4]) or 'none'}`"
            )
    lines.extend(
        [
            "",
        "## 相关链接",
        "- [机器记忆](./machine-memory.md)",
        "- [拓扑视图](./machine-memory-topology.md)",
        "- [动作队列](./machine-memory-actions.md)",
        "- [修复计划](./machine-memory-repair-plan.md)",
        "- [漂移报告](./drift-report.md)",
        "- [修复待办](./repair-backlog.md)",
        "- [决策索引](./decisions.md)",
        "- [判断索引](./judgments.md)",
        "- [审阅队列](./review-queue.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_machine_memory_index(memory: dict[str, Any]) -> str:
    concept_nodes = memory["concept_nodes"]
    edges = memory["edges"]
    drift = memory["drift"]
    health = memory.get("health", {})
    lines = [
        "# 机器记忆",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        "- 运行时状态文件：`.aiwiki/state/machine-memory.json`",
        "- 图谱导出文件：`.aiwiki/cache/machine-memory-graph.json`",
        "- 漂移报告：`wiki/indexes/drift-report.md`",
        f"- 来源节点：`{len(memory['source_nodes'])}`",
        f"- 概念节点：`{len(concept_nodes)}`",
        f"- 来源到概念的边：`{len(edges['source_to_concept'])}`",
        f"- 概念到概念的边：`{len(edges['concept_to_concept'])}`",
        f"- 索引词数量：`{len(memory['term_index'])}`",
        f"- 机器摘要：`{memory['digest']}`",
        f"- 图谱摘要：`{memory['graph_digest']}`",
        "",
        "## 图谱健康",
        f"- 连通分量：`{health.get('component_count', 0)}`",
        f"- 孤立来源：`{len(health.get('isolated_source_ids', []))}`",
        f"- 单节点概念：`{len(health.get('singleton_concept_slugs', []))}`",
        f"- 桥接概念：`{len(health.get('bridge_concept_slugs', []))}`",
        f"- 过载概念：`{len(health.get('overloaded_concept_slugs', []))}`",
        f"- 已索引分量：`{len(health.get('components', []))}`",
        f"- Hub 概念：`{len(health.get('hub_concepts', []))}`",
        f"- Hub 来源：`{len(health.get('hub_sources', []))}`",
        f"- 修复候选：`{len(health.get('link_suggestions', []))}`",
        f"- 修复动作：`{health.get('action_counts', {}).get('total', 0)}`",
        f"- 动作已到期：`{health.get('action_counts', {}).get('overdue', 0)}`",
        f"- 动作需升级：`{health.get('action_counts', {}).get('escalated', 0)}`",
        f"- 执行批次：`{health.get('repair_plan', {}).get('counts', {}).get('batches', 0)}`",
        f"- 执行提案：`{health.get('repair_plan', {}).get('counts', {}).get('proposals', 0)}`",
        f"- 页级 patch step：`{health.get('repair_plan', {}).get('counts', {}).get('patch_steps', 0)}`",
        f"- 概念冲突信号：`{health.get('concept_quality', {}).get('counts', {}).get('conflict_signals', 0)}`",
        f"- 概念重写候选：`{health.get('concept_quality', {}).get('counts', {}).get('rewrite_candidates', 0)}`",
        f"- Rewrite 提案：`{health.get('concept_rewrite', {}).get('counts', {}).get('active', 0)}`",
        f"- 可应用 Rewrite：`{health.get('concept_rewrite', {}).get('counts', {}).get('apply_ready', 0)}`",
        "",
        "## 判断层",
        "- 决策索引：`wiki/indexes/decisions.md`",
        "- 判断索引：`wiki/indexes/judgments.md`",
        "- 审阅队列：`wiki/indexes/review-queue.md`",
        "",
        "## 漂移摘要",
        f"- 缺失 raw 文件：`{len(drift['missing_raw_files'])}`",
        f"- 缺失来源页：`{len(drift['missing_source_pages'])}`",
        f"- 缺失概念页：`{len(drift['missing_concept_pages'])}`",
        f"- 无概念覆盖来源：`{len(drift['sources_without_concepts'])}`",
        "",
        "## 相关链接",
        "- [图谱健康](./graph-health.md)",
        "- [拓扑视图](./machine-memory-topology.md)",
        "- [动作队列](./machine-memory-actions.md)",
        "- [修复计划](./machine-memory-repair-plan.md)",
        "- [漂移报告](./drift-report.md)",
        "- [修复待办](./repair-backlog.md)",
        "- [概念质量](./concept-quality.md)",
        "- [Rewrite Proposals](./rewrite-proposals.md)",
        "",
        "## Action Workflow",
        f"- 状态文件：`{health.get('action_state_path', '.aiwiki/state/machine-memory-actions.json')}`",
        "- 通过 `review-action` 推进 action status。",
        "- nightly 会继续追踪 action 的 occurrences、aging 和 escalation。",
        "- repair 计划页：`wiki/indexes/machine-memory-repair-plan.md`",
        "",
        "## 查询加速",
        "- `ask` 和 `run-ask` 先用机器记忆 term index 做第一轮查询规划。",
        "- source-to-concept 和 concept-to-concept 边会在组装 prompt 前扩展候选范围。",
        "- 查询规划还会提取最短图路径和触达分量，支持更深的检索。",
        "- 图谱导出主要给 agent / tooling 使用，不建议直接人工修改。",
        "",
        "## 重点概念",
    ]
    if not concept_nodes:
        lines.append("- 还没有编译出概念节点。")
    else:
        for node in sorted(
            concept_nodes,
            key=lambda item: (-len(item["source_pages"]), item["title"].lower()),
        )[:10]:
            lines.append(
                f"- [{node['title']}](../concepts/{node['slug']}.md) "
                f"({len(node['source_pages'])} source(s), {len(node['related_slugs'])} related concept(s))"
            )
    lines.extend(
        [
            "",
            "## 运行时规则",
            "- [规则索引](../../schema/index.md)",
            "- [引用规则](../../schema/citations.md)",
            "- [冲突规则](../../schema/conflicts.md)",
            "- [审阅规则](../../schema/review.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_machine_memory_topology(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    hub_concepts = health.get("hub_concepts", [])
    hub_sources = health.get("hub_sources", [])
    link_suggestions = health.get("link_suggestions", [])
    lines = [
        "# 机器记忆拓扑",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        f"- 已索引分量：`{health.get('component_count', 0)}`",
        f"- Hub 概念：`{len(hub_concepts)}`",
        f"- Hub 来源：`{len(hub_sources)}`",
        f"- 修复候选：`{len(link_suggestions)}`",
        "",
        "## Hub 概念",
    ]
    if not hub_concepts:
        lines.append("- 当前没有可展示的 hub 概念。")
    else:
        for item in hub_concepts[:10]:
            lines.append(
                f"- [{item['title']}](../concepts/{item['slug']}.md)"
                f" | sources `{item['source_count']}`"
                f" | related `{item['related_count']}`"
                f" | component `{item['component_id'] or 'none'}`"
            )
    lines.extend(["", "## Hub 来源"])
    if not hub_sources:
        lines.append("- 当前没有可展示的 hub 来源。")
    else:
        for item in hub_sources[:10]:
            lines.append(
                f"- [{item['title']}](../sources/{item['id']}.md)"
                f" | concepts `{item['concept_count']}`"
                f" | component `{item['component_id'] or 'none'}`"
            )
    lines.extend(["", "## 修复候选"])
    if not link_suggestions:
        lines.append("- 当前没有机器记忆修复候选。")
    else:
        for suggestion in link_suggestions[:10]:
            lines.append(
                f"- [{suggestion['source_title']}](../sources/{suggestion['source_id']}.md)"
                f" -> [{suggestion['concept_title']}](../concepts/{suggestion['concept_slug']}.md)"
                f" | shared `{', '.join(suggestion['shared_terms'][:6])}`"
                f" | score `{suggestion['score']}`"
            )
    lines.extend(["", "## Mermaid 拓扑切片", "```mermaid", "graph LR"])
    node_lines: list[str] = []
    edge_lines: list[str] = []
    added_nodes: set[str] = set()
    hub_concept_slugs = {item["slug"] for item in hub_concepts[:5]}
    hub_source_ids = {item["id"] for item in hub_sources[:5]}
    concept_by_slug = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    source_by_id = {node["id"]: node for node in memory.get("source_nodes", [])}
    for source_id in sorted(hub_source_ids):
        node = source_by_id.get(source_id)
        if not node:
            continue
        node_key = f"src_{slugify(source_id).replace('-', '_')}"
        if node_key in added_nodes:
            continue
        added_nodes.add(node_key)
        label = str(node["title"]).replace('"', "'")
        node_lines.append(f'    {node_key}["S: {label}"]')
    for concept_slug in sorted(hub_concept_slugs):
        node = concept_by_slug.get(concept_slug)
        if not node:
            continue
        node_key = f"concept_{slugify(concept_slug).replace('-', '_')}"
        if node_key in added_nodes:
            continue
        added_nodes.add(node_key)
        label = str(node["title"]).replace('"', "'")
        node_lines.append(f'    {node_key}["C: {label}"]')
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        source_id = edge.get("source_id")
        concept_slug = edge.get("concept_slug")
        if source_id not in hub_source_ids or concept_slug not in hub_concept_slugs:
            continue
        left = f"src_{slugify(source_id).replace('-', '_')}"
        right = f"concept_{slugify(concept_slug).replace('-', '_')}"
        edge_lines.append(f"    {left} --> {right}")
    seen_related_pairs: set[tuple[str, str]] = set()
    for edge in memory.get("edges", {}).get("concept_to_concept", []):
        left_slug = edge.get("from")
        right_slug = edge.get("to")
        if left_slug not in hub_concept_slugs or right_slug not in hub_concept_slugs:
            continue
        pair = tuple(sorted((str(left_slug), str(right_slug))))
        if pair in seen_related_pairs:
            continue
        seen_related_pairs.add(pair)
        left = f"concept_{slugify(left_slug).replace('-', '_')}"
        right = f"concept_{slugify(right_slug).replace('-', '_')}"
        edge_lines.append(f"    {left} -.-> {right}")
    if not node_lines:
        lines.append('    placeholder["Not enough machine-memory nodes yet"]')
    else:
        lines.extend(node_lines)
        lines.extend(edge_lines[:18])
    lines.extend(
        [
            "```",
            "",
            "## 相关链接",
            "- [机器记忆](./machine-memory.md)",
            "- [图谱健康](./graph-health.md)",
            "- [动作队列](./machine-memory-actions.md)",
            "- [修复计划](./machine-memory-repair-plan.md)",
            "- [修复待办](./repair-backlog.md)",
            "- [概念质量](./concept-quality.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_machine_memory_actions(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    actions = health.get("actions", [])
    inactive_actions = health.get("inactive_actions", [])
    overdue_actions = health.get("overdue_actions", [])
    escalated_actions = health.get("escalated_actions", [])
    recent_receipts = sorted(
        [
            action
            for action in [*actions, *inactive_actions]
            if action.get("last_receipt_path")
        ],
        key=lambda item: str(item.get("status_updated_at") or item.get("reviewed_at") or ""),
        reverse=True,
    )
    counts = health.get("action_counts", {})
    by_priority = counts.get("by_priority", {})
    by_status = counts.get("by_status", {})
    kind_labels = {
        "add-source-concept-link": "补链动作",
        "connect-isolated-source": "孤立来源动作",
        "expand-singleton-concept": "单节点概念动作",
        "split-overloaded-concept": "过载概念动作",
        "monitor-bridge-concept": "桥接概念观察",
    }
    lines = [
        "# 机器记忆动作队列",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        f"- 动作总数：`{counts.get('total', 0)}`",
        f"- 高优先级：`{by_priority.get('high', 0)}`",
        f"- 中优先级：`{by_priority.get('medium', 0)}`",
        f"- 低优先级：`{by_priority.get('low', 0)}`",
        f"- 已到期：`{counts.get('overdue', 0)}`",
        f"- 已升级：`{counts.get('escalated', 0)}`",
        f"- 已清除：`{counts.get('inactive', 0)}`",
        f"- 状态文件：`{health.get('action_state_path', '.aiwiki/state/machine-memory-actions.json')}`",
        "",
        "## 状态分布",
    ]
    for status in ACTION_STATUSES:
        lines.append(f"- `{display_action_status(status)}`：`{by_status.get(status, 0)}`")
    lines.extend(
        [
            "",
            "## 已升级动作",
        ]
    )
    if not escalated_actions:
        lines.append("- 当前没有需要升级处理的动作。")
    else:
        for action in escalated_actions[:8]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f"{detail}"
                f" | occurrences `{action.get('occurrences', 0)}`"
            )
    lines.extend(
        [
            "",
            "## 已到期动作",
        ]
    )
    if not overdue_actions:
        lines.append("- 当前没有已到期待处理的动作。")
    else:
        for action in overdue_actions[:8]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f"{detail}"
                f" | revisit `{action.get('revisit_after', '') or 'none'}`"
            )
    lines.extend(
        [
            "",
        "## 优先队列",
        ]
    )
    if not actions:
        lines.append("- 当前没有 machine-memory 动作。")
    else:
        for action in actions[:12]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            action_status = display_action_status(str(action.get("status")))
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | status `{action_status}`"
                f" | band `{action.get('execution_band', 'review-first')}`"
                f" | policy `{action.get('execution_policy', 'triage')}`"
                f" | primary `{action['primary_path']}`"
                f"{detail}"
                f" | occurrences `{action.get('occurrences', 0)}`"
                f" | component `{action.get('component_id') or 'none'}`"
            )
    for kind, label in kind_labels.items():
        lines.extend(["", f"## {label}"])
        kind_actions = [action for action in actions if action.get("kind") == kind]
        if not kind_actions:
            lines.append("- 当前没有此类动作。")
            continue
        for action in kind_actions[:8]:
            paths = [f"primary `{action['primary_path']}`"]
            if action.get("secondary_path"):
                paths.append(f"secondary `{action['secondary_path']}`")
            action_status = display_action_status(str(action.get("status")))
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | status `{action_status}`"
                f" | band `{action.get('execution_band', 'review-first')}`"
                f" | policy `{action.get('execution_policy', 'triage')}`"
                f" | {' | '.join(paths)}"
                f" | first `{action.get('first_seen_at', '') or 'none'}`"
                f" | seen `{action.get('occurrences', 0)}`"
                f" | {action.get('reason', '') or 'no reason'}"
            )
    lines.extend(["", "## 最近清除"])
    if not inactive_actions:
        lines.append("- 当前没有最近清除的动作。")
    else:
        for action in inactive_actions[:8]:
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | last_seen `{action.get('last_seen_at', '') or 'none'}`"
                f" | inactive_since `{action.get('inactive_since', '') or 'none'}`"
            )
    lines.extend(["", "## 最近执行回执"])
    if not recent_receipts:
        lines.append("- 当前还没有 safe execution receipt。")
    else:
        for action in recent_receipts[:8]:
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | receipt `{action.get('last_receipt_path', '')}`"
                f" | updated `{action.get('status_updated_at', '') or action.get('reviewed_at', '') or 'none'}`"
            )
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [机器记忆](./machine-memory.md)",
            "- [拓扑视图](./machine-memory-topology.md)",
            "- [修复计划](./machine-memory-repair-plan.md)",
            "- [图谱健康](./graph-health.md)",
            "- [修复待办](./repair-backlog.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_machine_memory_repair_plan(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    counts = plan.get("counts", {})
    ready_actions = plan.get("ready_actions", [])
    triage_actions = plan.get("triage_actions", [])
    deferred_actions = plan.get("deferred_actions", [])
    inactive_actions = plan.get("inactive_actions", [])
    execution_batches = plan.get("execution_batches", [])
    execution_proposals = plan.get("execution_proposals", [])
    lines = [
        "# 机器记忆修复计划",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        f"- Ready 动作：`{counts.get('ready', 0)}`",
        f"- 待分流动作：`{counts.get('triage', 0)}`",
        f"- 暂缓动作：`{counts.get('deferred', 0)}`",
        f"- 最近清除：`{counts.get('inactive', 0)}`",
        f"- 执行批次：`{counts.get('batches', 0)}`",
        f"- 执行提案：`{counts.get('proposals', 0)}`",
        f"- 页级 patch step：`{counts.get('patch_steps', 0)}`",
        f"- 状态文件：`{health.get('action_state_path', '.aiwiki/state/machine-memory-actions.json')}`",
        "",
        "## Ready Now",
    ]
    if not ready_actions:
        lines.append("- 当前没有 ready action。")
    else:
        for action in ready_actions[:10]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            command_hint = action.get("command_hint", "")
            command_part = f" | command `{command_hint}`" if command_hint else ""
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f"{detail}"
                f" | band `{action.get('execution_band', 'review-first')}`"
                f" | next {action.get('next_step', 'n/a')}"
                f"{command_part}"
            )
    lines.extend(["", "## Need Triage"])
    if not triage_actions:
        lines.append("- 当前没有待分流动作。")
    else:
        for action in triage_actions[:10]:
            command_hint = action.get("command_hint", "")
            command_part = f" | command `{command_hint}`" if command_hint else ""
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f" | band `{action.get('execution_band', 'review-first')}`"
                f" | next {action.get('next_step', 'n/a')}"
                f"{command_part}"
            )
    lines.extend(["", "## Deferred"])
    if not deferred_actions:
        lines.append("- 当前没有暂缓动作。")
    else:
        for action in deferred_actions[:10]:
            command_hint = action.get("command_hint", "")
            command_part = f" | command `{command_hint}`" if command_hint else ""
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f" | revisit `{action.get('revisit_after', '') or 'none'}`"
                f" | band `{action.get('execution_band', 'review-first')}`"
                f"{command_part}"
            )
    lines.extend(["", "## Execution Batches"])
    if not execution_batches:
        lines.append("- 当前没有可执行批次。")
    else:
        for batch in execution_batches[:8]:
            lines.append(
                f"- {batch['label']}"
                f" | actions `{len(batch.get('actions', []))}`"
                f" | escalated `{batch.get('escalated', False)}`"
                f" | overdue `{batch.get('overdue', False)}`"
                f" | primary `{', '.join(batch.get('primary_paths', [])) or 'none'}`"
            )
            for action in batch.get("actions", [])[:4]:
                command_hint = action.get("command_hint", "")
                command_part = f" | command `{command_hint}`" if command_hint else ""
                lines.append(
                    f"  action [{action['priority']}] {action['title']}"
                    f" | status `{display_action_status(str(action.get('status')))}`"
                    f" | next {action.get('next_step', 'n/a')}"
                    f"{command_part}"
                )
    lines.extend(["", "## Execution Proposals"])
    if not execution_proposals:
        lines.append("- 当前没有页级执行提案。")
    else:
        for proposal in execution_proposals[:10]:
            command_part = f" | command `{proposal['command_hint']}`" if proposal.get("command_hint") else ""
            lines.append(
                f"- [{proposal['priority']}] {proposal['title']}"
                f" | status `{display_action_status(str(proposal.get('status')))}`"
                f" | kind `{proposal.get('proposal_kind', 'manual-repair')}`"
                f" | risk `{proposal.get('risk', 'medium')}`"
                f" | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
                f"{command_part}"
            )
            lines.append(f"  - strategy: {proposal.get('summary', 'n/a')}")
            lines.append(f"  - bundle: `{proposal.get('bundle_path', '') or 'none'}`")
            for edit in proposal.get("suggested_edits", [])[:3]:
                lines.append(f"  - edit: {edit}")
            patch_plan = proposal.get("page_patch_plan", [])
            if patch_plan:
                for patch in patch_plan[:4]:
                    sections = ", ".join(patch.get("sections", [])) or "none"
                    lines.append(
                        f"  - patch `{patch.get('path', '')}`"
                        f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                        f" | mode `{patch.get('mode', 'update')}`"
                        f" | sections `{sections}`"
                    )
    lines.extend(["", "## Page-Level Patch Plans"])
    if not execution_proposals:
        lines.append("- 当前没有页级 patch plan。")
    else:
        for proposal in execution_proposals[:8]:
            patch_plan = proposal.get("page_patch_plan", [])
            if not patch_plan:
                continue
            lines.append(
                f"### `{proposal.get('action_id', 'proposal')}` · {proposal.get('title', 'unnamed proposal')}"
            )
            lines.append(f"- Summary: {proposal.get('summary', 'n/a')}")
            lines.append(f"- Risk: `{proposal.get('risk', 'medium')}` | Protocol: `{proposal.get('protocol', DEFAULT_PROTOCOL)}`")
            for patch in patch_plan:
                sections = ", ".join(patch.get("sections", [])) or "none"
                command_hint = str(patch.get("command_hint") or "")
                lines.append(
                    f"- `{patch.get('path', '')}`"
                    f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                    f" | mode `{patch.get('mode', 'update')}`"
                    f" | sections `{sections}`"
                    f" | exists `{patch.get('exists', False)}`"
                )
                lines.append(f"  - {patch.get('summary', '检查相关页面并补充修复说明。')}")
                if command_hint:
                    lines.append(f"  - command: `{command_hint}`")
    lines.extend(["", "## Recently Cleared"])
    if not inactive_actions:
        lines.append("- 当前没有最近清除动作。")
    else:
        for action in inactive_actions[:10]:
            command_hint = action.get("command_hint", "")
            command_part = f" | command `{command_hint}`" if command_hint else ""
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | inactive_since `{action.get('inactive_since', '') or 'none'}`"
                f" | next {action.get('next_step', 'n/a')}"
                f"{command_part}"
            )
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [动作队列](./machine-memory-actions.md)",
            "- [机器记忆](./machine-memory.md)",
            "- [图谱健康](./graph-health.md)",
            "- [修复待办](./repair-backlog.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_execution_proposal_page(proposal: dict[str, Any], *, compiled_at: str) -> str:
    frontmatter = render_frontmatter(
        {
            "title": str(proposal.get("title") or proposal.get("action_id") or "Execution Proposal"),
            "kind": "execution-proposal",
            "status": str(proposal.get("status") or "proposed"),
            "action_id": str(proposal.get("action_id") or ""),
            "proposal_kind": str(proposal.get("proposal_kind") or "manual-repair"),
            "risk": str(proposal.get("risk") or "medium"),
            "priority": str(proposal.get("priority") or "medium"),
            "protocol": str(proposal.get("protocol") or DEFAULT_PROTOCOL),
            "target_paths": list(proposal.get("target_paths", [])),
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
        }
    )
    lines = [
        f"# {proposal.get('title') or proposal.get('action_id')}",
        "",
        "## Overview",
        f"- Action id: `{proposal.get('action_id', '')}`",
        f"- Status: `{display_action_status(str(proposal.get('status') or 'proposed'))}`",
        f"- Kind: `{proposal.get('proposal_kind', 'manual-repair')}`",
        f"- Risk: `{proposal.get('risk', 'medium')}`",
        f"- Protocol: `{proposal.get('protocol', DEFAULT_PROTOCOL)}`",
        f"- Priority: `{proposal.get('priority', 'medium')}`",
        f"- Targets: `{', '.join(proposal.get('target_paths', [])) or 'none'}`",
        f"- Bundle: `{proposal.get('bundle_path', '') or 'none'}`",
        "",
        "## Strategy",
        f"- {proposal.get('summary', 'n/a')}",
        "",
        "## Suggested Edits",
    ]
    edits = proposal.get("suggested_edits", [])
    if not edits:
        lines.append("- 当前没有额外建议。")
    else:
        lines.extend(f"- {edit}" for edit in edits)
    lines.extend(["", "## Page-Level Patch Plan"])
    patch_plan = proposal.get("page_patch_plan", [])
    if not patch_plan:
        lines.append("- 当前没有页级 patch step。")
    else:
        for patch in patch_plan:
            sections = ", ".join(patch.get("sections", [])) or "none"
            lines.append(
                f"- `{patch.get('path', '')}`"
                f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                f" | mode `{patch.get('mode', 'update')}`"
                f" | exists `{patch.get('exists', False)}`"
                f" | sections `{sections}`"
            )
            lines.append(f"  - {patch.get('summary', '检查相关页面并补充修复说明。')}")
    lines.extend(["", "## Commands"])
    if proposal.get("bundle_path"):
        lines.append(
            f"- Suggested apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {proposal.get('action_id', '')} --bundle {proposal.get('bundle_path', '')}`"
        )
    if proposal.get("command_hint"):
        lines.append(f"- Suggested next step: `{proposal['command_hint']}`")
    else:
        lines.append("- 当前没有直接命令提示。")
    safe_preview = proposal.get("safe_apply_preview")
    lines.extend(["", "## Safe Apply Preview"])
    if not safe_preview:
        lines.append("- 当前 proposal 不支持低风险 safe apply。")
    else:
        entry = safe_preview.get("entry", {})
        lines.append(f"- Apply mode: `{safe_preview.get('apply_mode', 'manual')}`")
        lines.append(f"- State path: `{safe_preview.get('state_path', '')}`")
        lines.append(
            f"- Manual link entry: source `{entry.get('source_id', '')}` -> concept `{entry.get('concept_slug', '')}`"
        )
        lines.append(f"- Affected paths: `{', '.join(safe_preview.get('affected_paths', [])) or 'none'}`")
        lines.append(f"- Follow-up: {safe_preview.get('follow_up', 'n/a')}")
    lines.extend(
        [
            "",
            "## Related Links",
            "- [执行中心](../indexes/execution-center.md)",
            "- [机器记忆修复计划](../indexes/machine-memory-repair-plan.md)",
            "- [机器记忆动作队列](../indexes/machine-memory-actions.md)",
            "- [炉心面板](../indexes/furnace-center.md)",
            f"- [Execution Bundle](../../{proposal.get('bundle_path', '')})" if proposal.get("bundle_path") else "- Execution Bundle: none",
        ]
    )
    return f"{frontmatter}\n\n" + "\n".join(lines).strip() + "\n"


def render_execution_center(memory: dict[str, Any], *, compiled_at: str, active_protocol: str) -> str:
    plan = memory.get("health", {}).get("repair_plan", {})
    proposals = plan.get("execution_proposals", [])
    ready_actions = plan.get("ready_actions", [])
    all_actions = [*memory.get("health", {}).get("actions", []), *memory.get("health", {}).get("inactive_actions", [])]
    recent_receipts = sorted(
        [
            action
            for action in all_actions
            if action.get("last_receipt_path")
        ],
        key=lambda item: str(item.get("status_updated_at") or item.get("reviewed_at") or ""),
        reverse=True,
    )
    revert_ready_actions = [
        action for action in recent_receipts if str(action.get("status") or "") == "resolved"
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in proposals)
    lines = [
        "# 执行中心",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- Ready actions：`{plan.get('counts', {}).get('ready', 0)}`",
        f"- 可安全执行动作：`{len(apply_ready_actions)}`",
        f"- Execution proposals：`{plan.get('counts', {}).get('proposals', 0)}`",
        f"- Page-level patch steps：`{patch_steps}`",
        "- 本地执行面板：`output/control/execution-center.html`",
        "",
        "## Safe Apply Now",
    ]
    if not apply_ready_actions:
        lines.append("- 当前没有可直接 `apply-action` 的低风险动作。")
    else:
        for action in apply_ready_actions[:10]:
            lines.append(
                f"- `{action['title']}` | band `{action.get('execution_band', 'bundle-safe-apply')}` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action.get('id', '')} --bundle output/control/execution-bundles/{slugify(str(action.get('id') or ''))}.json` | primary `{action.get('primary_path', '')}`"
            )
    lines.extend(["", "## Revert Safe Apply"])
    if not revert_ready_actions:
        lines.append("- 当前没有可回滚的 safe apply。")
    else:
        for action in revert_ready_actions[:10]:
            lines.append(
                f"- `{action['title']}` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {action.get('id', '')}` | receipt `{action.get('last_receipt_path', '')}`"
            )
    lines.extend(["", "## Execution Proposals"])
    if not proposals:
        lines.append("- 当前没有 execution proposal。")
    else:
        for proposal in proposals[:12]:
            lines.append(
                f"- [{proposal['title']}](../execution-proposals/{slugify(str(proposal.get('action_id') or ''))}.md)"
                f" | risk `{proposal.get('risk', 'medium')}`"
                f" | patch `{len(proposal.get('page_patch_plan', []))}`"
                f" | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
                f" | bundle `{proposal.get('bundle_path', '') or 'none'}`"
            )
    lines.extend(["", "## Recent Receipts"])
    if not recent_receipts:
        lines.append("- 当前还没有 safe execution receipt。")
    else:
        for action in recent_receipts[:8]:
            lines.append(
                f"- `{action['title']}`"
                f" | receipt `{action.get('last_receipt_path', '')}`"
                f" | updated `{action.get('status_updated_at', '') or action.get('reviewed_at', '') or 'none'}`"
            )
    lines.extend(
        [
            "",
            "## Quick Links",
            "- [机器记忆修复计划](./machine-memory-repair-plan.md)",
            "- [机器记忆动作队列](./machine-memory-actions.md)",
            "- [执行审计](./execution-audit.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [审阅中心](./review-center.md)",
            "- [炉心面板](./furnace-center.md)",
            "- [本地执行面板](../../output/control/execution-center.html)",
            "- [本地执行审计面板](../../output/control/execution-audit.html)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_execution_center_html(memory: dict[str, Any], *, compiled_at: str, active_protocol: str) -> str:
    plan = memory.get("health", {}).get("repair_plan", {})
    proposals = plan.get("execution_proposals", [])
    ready_actions = plan.get("ready_actions", [])
    all_actions = [*memory.get("health", {}).get("actions", []), *memory.get("health", {}).get("inactive_actions", [])]
    recent_receipts = sorted(
        [
            action
            for action in all_actions
            if action.get("last_receipt_path")
        ],
        key=lambda item: str(item.get("status_updated_at") or item.get("reviewed_at") or ""),
        reverse=True,
    )
    revert_ready_actions = [
        action for action in recent_receipts if str(action.get("status") or "") == "resolved"
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in proposals)
    summary_cards = [
        ("Ready Actions", str(plan.get("counts", {}).get("ready", 0))),
        ("Safe Apply", str(len(apply_ready_actions))),
        ("Proposals", str(plan.get("counts", {}).get("proposals", 0))),
        ("Patch Steps", str(patch_steps)),
    ]
    safe_apply_markup = "".join(
        f"<li><strong>{html.escape(str(action.get('title') or 'unnamed action'))}</strong>"
        f"<div><code>{html.escape(str(action.get('command_hint') or ''))}</code></div>"
        f"<div class=\"item-meta\">{html.escape(str(action.get('primary_path') or ''))}</div></li>"
        for action in apply_ready_actions[:8]
    ) or "<li>当前没有可直接 safe apply 的动作。</li>"
    revert_markup = "".join(
        f"<li><strong>{html.escape(str(action.get('title') or 'unnamed action'))}</strong>"
        f"<div><code>PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {html.escape(str(action.get('id') or ''))}</code></div>"
        f"<div class=\"item-meta\">{html.escape(str(action.get('last_receipt_path') or ''))}</div></li>"
        for action in revert_ready_actions[:8]
    ) or "<li>当前没有可回滚的 safe apply。</li>"
    proposal_markup = "".join(
        f"<li><strong><a href=\"../../wiki/execution-proposals/{html.escape(slugify(str(proposal.get('action_id') or '')))}.md\">{html.escape(str(proposal.get('title') or 'proposal'))}</a></strong>"
        f" <span class=\"item-meta\">risk {html.escape(str(proposal.get('risk') or 'medium'))} / patch {len(proposal.get('page_patch_plan', []))}</span>"
        f"<div>{html.escape(str(proposal.get('summary') or ''))}</div>"
        f"<div class=\"item-meta\"><a href=\"../../{html.escape(str(proposal.get('bundle_path') or ''))}\">Execution Bundle</a></div></li>"
        for proposal in proposals[:10]
    ) or "<li>当前没有 execution proposal。</li>"
    receipt_markup = "".join(
        f"<li><strong>{html.escape(str(action.get('title') or 'unnamed action'))}</strong>"
        f"<div class=\"item-meta\"><a href=\"../../{html.escape(str(action.get('last_receipt_path') or ''))}\">Execution Receipt</a></div></li>"
        for action in recent_receipts[:8]
    ) or "<li>当前还没有 safe execution receipt。</li>"
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Execution Center</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f8fafc; --ink: #0f172a; --muted: #475569; --panel: rgba(255,255,255,0.94); --line: #cbd5e1; }",
            "    body { margin: 0; padding: 24px; background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1100px; margin: 0 auto; }",
            "    .panel, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .panel { padding: 18px; margin-bottom: 18px; }",
            "    .meta, .grid { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin-top: 18px; }",
            "    .grid { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #1d4ed8; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 6px 0; }",
            "    a { color: #1d4ed8; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    .item-meta { color: var(--muted); font-size: 12px; }",
            "    code { background: #eff6ff; padding: 1px 6px; border-radius: 6px; }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="panel">',
            "    <h1>Execution Center</h1>",
            f"    <p>编译时间：<code>{html.escape(compiled_at)}</code>。当前协议：<code>{html.escape(active_protocol)}</code>。这里把 safe apply、execution proposal 和 patch-step 执行工作区收敛到一个地方。</p>",
            '    <div class="meta">',
            *[
                f'      <div class="card"><div class="metric">{html.escape(value)}</div><div class="metric-label">{html.escape(label)}</div></div>'
                for label, value in summary_cards
            ],
            "    </div>",
            "  </section>",
            '  <section class="grid">',
            f'    <div class="panel"><h2>Safe Apply Actions</h2><ul>{safe_apply_markup}</ul></div>',
            f'    <div class="panel"><h2>Revert Safe Apply</h2><ul>{revert_markup}</ul></div>',
            f'    <div class="panel"><h2>Execution Proposals</h2><ul>{proposal_markup}</ul></div>',
            f'    <div class="panel"><h2>Recent Receipts</h2><ul>{receipt_markup}</ul></div>',
            '    <div class="panel"><h2>相关入口</h2><ul>'
            '      <li><a href="../../wiki/indexes/execution-center.md">Markdown 执行中心</a></li>'
            '      <li><a href="../../wiki/indexes/execution-audit.md">执行审计</a></li>'
            '      <li><a href="../../wiki/indexes/machine-memory-repair-plan.md">修复计划</a></li>'
            '      <li><a href="../../wiki/indexes/machine-memory-actions.md">动作队列</a></li>'
            '      <li><a href="../../wiki/indexes/review-center.md">审阅中心</a></li>'
            '      <li><a href="../../wiki/indexes/furnace-center.md">炉心面板</a></li>'
            '      <li><a href="../../output/control/execution-audit.html">审计 HTML</a></li>'
            "    </ul></div>",
            "  </section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def collect_execution_consistency_signals(
    root: Path,
    actions: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> list[dict[str, str]]:
    manual_state = load_manual_link_state(root)
    active_manual_links: dict[str, list[dict[str, Any]]] = {}
    for item in manual_state.get("source_to_concept", []):
        if not isinstance(item, dict) or not bool(item.get("active", True)):
            continue
        origin_action_id = str(item.get("origin_action_id") or "")
        if not origin_action_id:
            continue
        active_manual_links.setdefault(origin_action_id, []).append(item)
    latest_receipt_by_action: dict[str, dict[str, Any]] = {}
    for record in history:
        action_id = str(record.get("action_id") or "")
        if action_id and action_id not in latest_receipt_by_action:
            latest_receipt_by_action[action_id] = record

    signals: list[dict[str, str]] = []
    for action in actions:
        if str(action.get("kind") or "") not in LOW_RISK_APPLYABLE_ACTION_KINDS:
            continue
        action_id = str(action.get("id") or "")
        if not action_id:
            continue
        status = str(action.get("status") or "proposed")
        latest = latest_receipt_by_action.get(action_id)
        latest_operation = str(latest.get("operation") or "") if latest else ""
        has_active_manual_link = bool(active_manual_links.get(action_id))
        title = str(action.get("title") or action_id)
        primary_path = str(action.get("primary_path") or "")

        if status == "resolved" and latest_operation != "apply":
            signals.append(
                {
                    "severity": "error",
                    "action_id": action_id,
                    "title": title,
                    "path": primary_path,
                    "message": "动作标记为 resolved，但最新 execution receipt 不是 apply。",
                }
            )
        if status == "resolved" and not has_active_manual_link:
            signals.append(
                {
                    "severity": "error",
                    "action_id": action_id,
                    "title": title,
                    "path": primary_path,
                    "message": "动作标记为 resolved，但 active manual-link state 缺失。",
                }
            )
        if latest_operation == "revert" and has_active_manual_link:
            signals.append(
                {
                    "severity": "error",
                    "action_id": action_id,
                    "title": title,
                    "path": primary_path,
                    "message": "最新 receipt 已是 revert，但 manual-link state 仍然 active。",
                }
            )
        if status in PENDING_ACTION_STATUSES and has_active_manual_link:
            signals.append(
                {
                    "severity": "warn",
                    "action_id": action_id,
                    "title": title,
                    "path": primary_path,
                    "message": "动作仍在待处理状态，但 manual-link state 仍然 active；需要确认是否应先 revert 或直接 resolve。",
                }
            )
    signals.sort(
        key=lambda item: (
            0 if item.get("severity") == "error" else 1,
            str(item.get("title") or "").lower(),
            str(item.get("message") or ""),
        )
    )
    return signals


def build_execution_audit_snapshot(root: Path, memory: dict[str, Any], *, active_protocol: str) -> dict[str, Any]:
    health = memory.get("health", {})
    actions = [dict(action) for action in health.get("actions", []) if isinstance(action, dict)]
    inactive_actions = [dict(action) for action in health.get("inactive_actions", []) if isinstance(action, dict)]
    all_actions = actions + inactive_actions
    history = load_execution_receipt_history(root)
    recent_apply = [record for record in history if str(record.get("operation") or "") == "apply"][:8]
    recent_revert = [record for record in history if str(record.get("operation") or "") == "revert"][:8]
    recent_by_protocol: dict[str, dict[str, list[dict[str, Any]]]] = {
        "recent_apply": {},
        "recent_revert": {},
    }
    band_counts: dict[str, int] = {}
    protocol_counts: dict[str, int] = {}
    receipt_counts: dict[str, int] = {}
    for record in history:
        protocol = str(record.get("protocol") or DEFAULT_PROTOCOL)
        protocol_counts[protocol] = protocol_counts.get(protocol, 0) + 1
        action_id = str(record.get("action_id") or "")
        if action_id:
            receipt_counts[action_id] = receipt_counts.get(action_id, 0) + 1
        operation = str(record.get("operation") or "")
        if operation in {"apply", "revert"}:
            bucket_name = "recent_apply" if operation == "apply" else "recent_revert"
            scoped = recent_by_protocol[bucket_name].setdefault(protocol, [])
            if len(scoped) < 8:
                scoped.append(record)
    action_rows: list[dict[str, Any]] = []
    for action in all_actions:
        profile = execution_policy_profile(action)
        band = str(action.get("execution_band") or profile.get("execution_band") or "review-first")
        band_counts[band] = band_counts.get(band, 0) + 1
        action_id = str(action.get("id") or "")
        capabilities = action.get("execution_capability_list")
        if not isinstance(capabilities, list):
            capabilities = list(profile.get("capabilities") or [])
        action_rows.append(
            {
                "id": action_id,
                "title": str(action.get("title") or action_id),
                "status": display_action_status(str(action.get("status") or "proposed")),
                "execution_band": band,
                "execution_band_label": execution_band_label(band),
                "execution_policy": str(action.get("execution_policy") or profile.get("execution_policy") or "triage"),
                "execution_capabilities": [str(item) for item in capabilities if isinstance(item, str) and item],
                "policy_summary": str(action.get("policy_summary") or profile.get("policy_summary") or ""),
                "receipt_count": receipt_counts.get(action_id, 0),
                "last_receipt_path": str(action.get("last_receipt_path") or ""),
                "primary_path": str(action.get("primary_path") or ""),
            }
        )
    action_rows.sort(
        key=lambda item: (
            0 if item.get("execution_band") == "bundle-safe-apply" else 1,
            0 if item.get("status") == display_action_status("accepted") else 1,
            str(item.get("title") or "").lower(),
        )
    )
    band_rows = [
        {"band": band, "label": execution_band_label(band), "count": band_counts.get(band, 0)}
        for band in ("bundle-safe-apply", "review-first", "manual-repair", "deferred", "closed", "history-only")
        if band_counts.get(band, 0)
    ]
    protocol_rows = [
        {"protocol": protocol, "title": protocol_title(protocol), "count": count}
        for protocol, count in sorted(protocol_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    consistency_signals = collect_execution_consistency_signals(root, all_actions, history)
    return {
        "compiled_at": str(memory.get("compiled_at") or ""),
        "active_protocol": active_protocol,
        "receipt_history_path": relative_path(root, execution_receipt_history_path(root)),
        "counts": {
            "actions": len(all_actions),
            "receipts": len(history),
            "apply": len([record for record in history if str(record.get("operation") or "") == "apply"]),
            "revert": len([record for record in history if str(record.get("operation") or "") == "revert"]),
            "bundle_safe": band_counts.get("bundle-safe-apply", 0),
        },
        "policy_bands": band_rows,
        "protocols": protocol_rows,
        "recent_apply": recent_apply,
        "recent_revert": recent_revert,
        "recent_by_protocol": recent_by_protocol,
        "actions": action_rows[:16],
        "consistency_signals": consistency_signals[:16],
        "consistency_counts": {
            "errors": sum(1 for item in consistency_signals if item.get("severity") == "error"),
            "warns": sum(1 for item in consistency_signals if item.get("severity") == "warn"),
        },
    }


def render_execution_audit(audit: dict[str, Any]) -> str:
    lines = [
        "# 执行审计",
        "",
        f"- 最近编译时间：`{audit.get('compiled_at', '')}`",
        f"- 当前协议：`{audit.get('active_protocol', DEFAULT_PROTOCOL)}` ({protocol_title(str(audit.get('active_protocol') or DEFAULT_PROTOCOL))})",
        f"- 动作总数：`{audit.get('counts', {}).get('actions', 0)}`",
        f"- Receipt 总数：`{audit.get('counts', {}).get('receipts', 0)}`",
        f"- Apply / Revert：`{audit.get('counts', {}).get('apply', 0)}` / `{audit.get('counts', {}).get('revert', 0)}`",
        f"- Bundle-safe actions：`{audit.get('counts', {}).get('bundle_safe', 0)}`",
        f"- Receipt history：`{audit.get('receipt_history_path', '.aiwiki/state/execution-receipts.jsonl')}`",
        "",
        "## Policy Bands",
    ]
    band_rows = audit.get("policy_bands", [])
    if not band_rows:
        lines.append("- 当前还没有可审计的 execution policy band。")
    else:
        for row in band_rows:
            lines.append(f"- `{row['band']}` | {row['label']} | count `{row['count']}`")
    lines.extend(["", "## Recent Apply"])
    recent_apply = audit.get("recent_apply", [])
    if not recent_apply:
        lines.append("- 当前还没有 apply receipt。")
    else:
        for receipt in recent_apply:
            lines.append(
                f"- `{receipt.get('title', receipt.get('action_id', 'receipt'))}`"
                f" | action `{receipt.get('action_id', '')}`"
                f" | protocol `{receipt.get('protocol', DEFAULT_PROTOCOL)}`"
                f" | applied `{receipt.get('applied_at', '')}`"
            )
    lines.extend(["", "## Recent Revert"])
    recent_revert = audit.get("recent_revert", [])
    if not recent_revert:
        lines.append("- 当前还没有 revert receipt。")
    else:
        for receipt in recent_revert:
            lines.append(
                f"- `{receipt.get('title', receipt.get('action_id', 'receipt'))}`"
                f" | action `{receipt.get('action_id', '')}`"
                f" | protocol `{receipt.get('protocol', DEFAULT_PROTOCOL)}`"
                f" | reverted `{receipt.get('applied_at', '')}`"
            )
    lines.extend(["", "## Protocol Breakdown"])
    protocols = audit.get("protocols", [])
    if not protocols:
        lines.append("- 当前还没有 protocol 级 execution history。")
    else:
        for row in protocols:
            lines.append(f"- `{row['protocol']}` ({row['title']}) | receipts `{row['count']}`")
    lines.extend(["", "## Consistency Signals"])
    consistency_signals = audit.get("consistency_signals", [])
    if not consistency_signals:
        lines.append("- 当前没有 execution consistency signal。")
    else:
        for signal in consistency_signals:
            lines.append(
                f"- [{signal.get('severity', 'warn')}] `{signal.get('title', signal.get('action_id', 'signal'))}`"
                f" | action `{signal.get('action_id', '')}`"
                f" | {signal.get('message', '')}"
            )
    lines.extend(["", "## Action Audit"])
    actions = audit.get("actions", [])
    if not actions:
        lines.append("- 当前还没有 action audit rows。")
    else:
        for action in actions:
            capabilities = ", ".join(action.get("execution_capabilities", [])) or "none"
            lines.append(
                f"- `{action['title']}`"
                f" | status `{action['status']}`"
                f" | band `{action['execution_band']}`"
                f" | policy `{action['execution_policy']}`"
                f" | receipts `{action['receipt_count']}`"
            )
            lines.append(f"  - capabilities: {capabilities}")
            lines.append(f"  - summary: {action.get('policy_summary', 'n/a')}")
            if action.get("last_receipt_path"):
                lines.append(f"  - last receipt: `{action['last_receipt_path']}`")
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [执行中心](./execution-center.md)",
            "- [机器记忆修复计划](./machine-memory-repair-plan.md)",
            "- [机器记忆动作队列](./machine-memory-actions.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [炉心面板](./furnace-center.md)",
            "- [本地执行审计面板](../../output/control/execution-audit.html)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_execution_audit_html(audit: dict[str, Any]) -> str:
    summary_cards = [
        ("Receipts", str(audit.get("counts", {}).get("receipts", 0))),
        ("Apply", str(audit.get("counts", {}).get("apply", 0))),
        ("Revert", str(audit.get("counts", {}).get("revert", 0))),
        ("Bundle Safe", str(audit.get("counts", {}).get("bundle_safe", 0))),
    ]
    band_markup = "".join(
        f"<li><strong>{html.escape(str(row.get('label') or row.get('band') or 'band'))}</strong>"
        f" <span class=\"item-meta\">{html.escape(str(row.get('band') or ''))}</span>"
        f"<div class=\"metric-inline\">count {html.escape(str(row.get('count') or 0))}</div></li>"
        for row in audit.get("policy_bands", [])
    ) or "<li>当前还没有可审计的 execution policy band。</li>"
    apply_markup = "".join(
        f"<li><strong>{html.escape(str(item.get('title') or item.get('action_id') or 'receipt'))}</strong>"
        f"<div class=\"item-meta\">{html.escape(str(item.get('action_id') or ''))} / {html.escape(str(item.get('protocol') or DEFAULT_PROTOCOL))}</div>"
        f"<div>{html.escape(str(item.get('applied_at') or ''))}</div></li>"
        for item in audit.get("recent_apply", [])
    ) or "<li>当前还没有 apply receipt。</li>"
    revert_markup = "".join(
        f"<li><strong>{html.escape(str(item.get('title') or item.get('action_id') or 'receipt'))}</strong>"
        f"<div class=\"item-meta\">{html.escape(str(item.get('action_id') or ''))} / {html.escape(str(item.get('protocol') or DEFAULT_PROTOCOL))}</div>"
        f"<div>{html.escape(str(item.get('applied_at') or ''))}</div></li>"
        for item in audit.get("recent_revert", [])
    ) or "<li>当前还没有 revert receipt。</li>"
    protocol_markup = "".join(
        f"<li><strong>{html.escape(str(row.get('title') or row.get('protocol') or 'protocol'))}</strong>"
        f" <span class=\"item-meta\">{html.escape(str(row.get('protocol') or ''))}</span>"
        f"<div>receipts {html.escape(str(row.get('count') or 0))}</div></li>"
        for row in audit.get("protocols", [])
    ) or "<li>当前还没有 protocol 级 execution history。</li>"
    action_markup = "".join(
        f"<li><strong>{html.escape(str(action.get('title') or action.get('id') or 'action'))}</strong>"
        f"<div class=\"item-meta\">{html.escape(str(action.get('execution_band_label') or action.get('execution_band') or ''))}"
        f" / {html.escape(str(action.get('execution_policy') or 'triage'))}"
        f" / receipts {html.escape(str(action.get('receipt_count') or 0))}</div>"
        f"<div>{html.escape(str(action.get('policy_summary') or ''))}</div></li>"
        for action in audit.get("actions", [])
    ) or "<li>当前还没有 action audit rows。</li>"
    consistency_markup = "".join(
        f"<li><strong>{html.escape(str(signal.get('title') or signal.get('action_id') or 'signal'))}</strong>"
        f" <span class=\"item-meta\">{html.escape(str(signal.get('severity') or 'warn'))}</span>"
        f"<div>{html.escape(str(signal.get('message') or ''))}</div></li>"
        for signal in audit.get("consistency_signals", [])
    ) or "<li>当前没有 execution consistency signal。</li>"
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Execution Audit</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f8fafc; --ink: #0f172a; --muted: #475569; --panel: rgba(255,255,255,0.94); --line: #cbd5e1; }",
            "    body { margin: 0; padding: 24px; background: linear-gradient(180deg, #f8fafc 0%, #ecfeff 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1100px; margin: 0 auto; }",
            "    .panel, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .panel { padding: 18px; margin-bottom: 18px; }",
            "    .meta, .grid { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin-top: 18px; }",
            "    .grid { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #0f766e; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    .metric-inline { color: #0f766e; font-weight: 700; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 6px 0; }",
            "    a { color: #0f766e; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    .item-meta { color: var(--muted); font-size: 12px; }",
            "    code { background: #ecfeff; padding: 1px 6px; border-radius: 6px; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <section class=\"panel\">",
            "      <h1>Execution Audit</h1>",
            f"      <p>当前协议 <strong>{html.escape(str(audit.get('active_protocol') or DEFAULT_PROTOCOL))}</strong> · 最近编译 {html.escape(str(audit.get('compiled_at') or ''))}</p>",
            "      <p><a href=\"../../wiki/indexes/execution-audit.md\">Markdown 审计页</a> · <a href=\"../../wiki/indexes/execution-center.md\">执行中心</a> · <a href=\"../../wiki/indexes/furnace-center.md\">炉心面板</a></p>",
            "      <div class=\"meta\">",
            *[
                "\n".join(
                    [
                        '        <div class="card">',
                        f'          <div class="metric-label">{html.escape(label)}</div>',
                        f'          <div class="metric">{html.escape(value)}</div>',
                        "        </div>",
                    ]
                )
                for label, value in summary_cards
            ],
            "      </div>",
            "    </section>",
            "    <section class=\"grid\">",
            f'      <div class="card"><h2>Policy Bands</h2><ul>{band_markup}</ul></div>',
            f'      <div class="card"><h2>Protocol Breakdown</h2><ul>{protocol_markup}</ul></div>',
            f'      <div class="card"><h2>Recent Apply</h2><ul>{apply_markup}</ul></div>',
            f'      <div class="card"><h2>Recent Revert</h2><ul>{revert_markup}</ul></div>',
            f'      <div class="card"><h2>Consistency Signals</h2><ul>{consistency_markup}</ul></div>',
            f'      <div class="card"><h2>Action Audit</h2><ul>{action_markup}</ul></div>',
            "    </section>",
            "  </main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def render_concept_quality(memory: dict[str, Any]) -> str:
    quality = memory.get("health", {}).get("concept_quality", {})
    rewrite_state = memory.get("health", {}).get("concept_rewrite", {})
    counts = quality.get("counts", {})
    weak_concepts = quality.get("weak_concepts", [])
    stable_concepts = quality.get("stable_concepts", [])
    merge_candidates = quality.get("merge_candidates", [])
    rewrite_candidates = quality.get("rewrite_candidates", [])
    conflict_signals = quality.get("conflict_signals", [])
    gap_signals = quality.get("gap_signals", [])
    lines = [
        "# 概念质量",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        f"- 弱概念页：`{counts.get('weak', 0)}`",
        f"- 稳定概念页：`{counts.get('stable', 0)}`",
        f"- 占位概念页：`{counts.get('placeholders', 0)}`",
        f"- 合并候选：`{counts.get('merge_candidates', 0)}`",
        f"- 重写候选：`{counts.get('rewrite_candidates', 0)}`",
        f"- 冲突信号：`{counts.get('conflict_signals', 0)}`",
        f"- 证据缺口：`{counts.get('gap_signals', 0)}`",
        f"- Rewrite 提案：`{rewrite_state.get('counts', {}).get('active', 0)}`",
        f"- 待审提案：`{rewrite_state.get('counts', {}).get('pending_review', 0)}`",
        f"- 可应用提案：`{rewrite_state.get('counts', {}).get('apply_ready', 0)}`",
        "",
        "## Rewrite Now",
    ]
    if not weak_concepts:
        lines.append("- 当前没有需要立即重写的概念页。")
    else:
        for concept in weak_concepts[:12]:
            lines.append(
                f"- [{concept['title']}](../concepts/{concept['slug']}.md)"
                f" | issues `{', '.join(concept.get('issues', [])) or 'none'}`"
                f" | sources `{concept.get('source_count', 0)}`"
                f" | related `{concept.get('related_count', 0)}`"
            )
    lines.extend(["", "## Rewrite Priority"])
    if not rewrite_candidates:
        lines.append("- 当前没有新的重写候选。")
    else:
        for candidate in rewrite_candidates[:10]:
            lines.append(
                f"- [{candidate['title']}](../concepts/{candidate['slug']}.md)"
                f" | priority `{candidate.get('priority', 'n/a')}`"
                f" | score `{candidate.get('score', 0)}`"
                f" | issues `{', '.join(candidate.get('issues', [])) or 'none'}`"
            )
            lines.append(f"  - strategy: {candidate.get('rewrite_strategy', 'n/a')}")
    lines.extend(["", "## Rewrite Proposals"])
    if not rewrite_state.get("proposals"):
        lines.append("- 当前还没有 concept rewrite proposal。先运行 `run-compile` 或等待下一次 rewrite proposal 生成。")
    else:
        for proposal in rewrite_state.get("proposals", [])[:10]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | status `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`"
                f" | priority `{proposal.get('priority', 'n/a')}`"
                f" | apply_ready `{proposal.get('apply_ready', False)}`"
            )
            if proposal.get("rewrite_strategy"):
                lines.append(f"  - strategy: {proposal['rewrite_strategy']}")
    lines.extend(["", "## Conflict Signals"])
    if not conflict_signals:
        lines.append("- 当前没有显式概念冲突信号。")
    else:
        for signal in conflict_signals[:10]:
            lines.append(
                f"- [{signal['title']}](../concepts/{signal['slug']}.md)"
                f" | signal `{signal.get('label', 'n/a')}`"
                f" | sources `{', '.join(signal.get('source_pages', [])) or 'none'}`"
            )
    lines.extend(["", "## Evidence Gaps"])
    if not gap_signals:
        lines.append("- 当前没有显式证据缺口。")
    else:
        for gap in gap_signals[:10]:
            lines.append(
                f"- [{gap['title']}](../concepts/{gap['slug']}.md)"
                f" | kind `{gap.get('kind', 'n/a')}`"
                f" | source `{gap.get('path', 'n/a')}`"
                f" | markers `{', '.join(gap.get('markers', [])) or 'none'}`"
            )
    lines.extend(["", "## Merge Candidates"])
    if not merge_candidates:
        lines.append("- 当前没有明显的概念合并候选。")
    else:
        for candidate in merge_candidates[:10]:
            lines.append(
                f"- [{candidate['left_title']}](../concepts/{candidate['left_slug']}.md)"
                f" <-> [{candidate['right_title']}](../concepts/{candidate['right_slug']}.md)"
                f" | shared_sources `{len(candidate.get('shared_sources', []))}`"
                f" | shared_tokens `{', '.join(candidate.get('shared_tokens', [])) or 'none'}`"
            )
    lines.extend(["", "## Stable Concepts"])
    if not stable_concepts:
        lines.append("- 当前还没有稳定概念页。")
    else:
        for concept in stable_concepts[:10]:
            lines.append(
                f"- [{concept['title']}](../concepts/{concept['slug']}.md)"
                f" | sources `{concept.get('source_count', 0)}`"
                f" | related `{concept.get('related_count', 0)}`"
            )
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [概念索引](./concepts.md)",
            "- [机器记忆](./machine-memory.md)",
            "- [动作队列](./machine-memory-actions.md)",
            "- [修复计划](./machine-memory-repair-plan.md)",
            "- [Rewrite Proposals](./rewrite-proposals.md)",
            "- [修复待办](./repair-backlog.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def concept_page_snapshot(root: Path, slug: str) -> dict[str, Any]:
    path = root / "wiki" / "concepts" / f"{slug}.md"
    if not path.exists():
        return {
            "path": relative_path(root, path),
            "title": slug,
            "source_signature": "",
            "source_pages": [],
            "summary": "",
            "content": "",
        }
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    source_pages = frontmatter.get("source_pages", [])
    if not isinstance(source_pages, list):
        source_pages = []
    return {
        "path": relative_path(root, path),
        "title": str(frontmatter.get("title") or path.stem),
        "source_signature": str(frontmatter.get("source_signature") or ""),
        "source_pages": [str(item) for item in source_pages if isinstance(item, str)],
        "summary": preserved_section(content, "Summary", ""),
        "content": content,
    }


def concept_rewrite_proposal_digest(candidate_markdown: str) -> str:
    if not candidate_markdown:
        return ""
    return sha256_bytes(candidate_markdown.encode("utf-8"))


def reconcile_concept_rewrite_proposals(
    root: Path,
    quality: dict[str, Any],
    *,
    compiled_at: str,
) -> dict[str, Any]:
    previous_state = load_concept_rewrite_state(root)
    previous_by_slug = {
        str(proposal.get("slug") or ""): proposal
        for proposal in previous_state.get("proposals", [])
        if proposal.get("slug")
    }
    active_records: list[dict[str, Any]] = []
    inactive_records: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    for candidate in quality.get("rewrite_candidates", []):
        slug = str(candidate.get("slug") or "").strip()
        if not slug:
            continue
        snapshot = concept_page_snapshot(root, slug)
        previous = previous_by_slug.get(slug, {})
        source_signature = str(candidate.get("source_signature") or snapshot.get("source_signature") or "")
        status = str(previous.get("status") or "proposed")
        if status not in REWRITE_PROPOSAL_STATUSES:
            status = "proposed"
        previous_signature = str(previous.get("source_signature") or "")
        signature_changed = bool(previous_signature and previous_signature != source_signature)
        if signature_changed and status in {"applied", "rejected"}:
            status = "proposed"
        candidate_markdown = str(previous.get("candidate_markdown") or "")
        candidate_digest = str(previous.get("candidate_digest") or concept_rewrite_proposal_digest(candidate_markdown))
        first_proposed_at = str(previous.get("first_proposed_at") or compiled_at)
        occurrences = int(previous.get("occurrences") or 0) + 1
        reviewed_at = str(previous.get("reviewed_at") or "")
        review_note = str(previous.get("review_note") or "")
        applied_at = str(previous.get("applied_at") or "")
        if signature_changed:
            status = "proposed"
            candidate_markdown = ""
            candidate_digest = ""
            reviewed_at = ""
            review_note = ""
            applied_at = ""
        record = {
            "slug": slug,
            "title": str(candidate.get("title") or snapshot.get("title") or slug),
            "priority": str(candidate.get("priority") or "medium"),
            "score": int(candidate.get("score") or 0),
            "issues": list(candidate.get("issues") or []),
            "rewrite_strategy": str(candidate.get("rewrite_strategy") or ""),
            "target_path": str(candidate.get("path") or snapshot.get("path") or f"wiki/concepts/{slug}.md"),
            "proposal_path": relative_path(root, concept_rewrite_proposal_page_path(root, slug)),
            "source_signature": source_signature,
            "source_pages": list(candidate.get("source_pages") or snapshot.get("source_pages") or []),
            "status": status,
            "active": True,
            "first_proposed_at": first_proposed_at,
            "last_proposed_at": compiled_at,
            "occurrences": occurrences,
            "reviewed_at": reviewed_at,
            "review_note": review_note,
            "applied_at": applied_at,
            "pending_review": "true" if rewrite_proposal_needs_review(status) else "false",
            "candidate_markdown": candidate_markdown,
            "candidate_digest": candidate_digest,
            "apply_ready": False,
            "current_summary": str(snapshot.get("summary") or ""),
        }
        record["apply_ready"] = rewrite_proposal_is_apply_ready(root, record)
        active_records.append(record)
        seen_slugs.add(slug)

    for slug, previous in previous_by_slug.items():
        if slug in seen_slugs:
            continue
        record = dict(previous)
        record["active"] = False
        record["pending_review"] = "false"
        record["apply_ready"] = False
        inactive_records.append(record)

    active_records.sort(
        key=lambda item: (
            rewrite_proposal_status_rank(str(item.get("status") or "")),
            action_priority_rank(str(item.get("priority") or "")),
            -int(item.get("score", 0)),
            str(item.get("title", "")).lower(),
        )
    )
    inactive_records.sort(
        key=lambda item: (
            str(item.get("applied_at") or item.get("reviewed_at") or item.get("last_proposed_at") or ""),
            str(item.get("title", "")).lower(),
        ),
        reverse=True,
    )
    document = {
        "version": 1,
        "compiled_at": compiled_at,
        "proposals": active_records + inactive_records,
    }
    save_concept_rewrite_state(root, document)
    counts = {
        "active": len(active_records),
        "inactive": len(inactive_records),
        "pending_review": sum(1 for proposal in active_records if proposal.get("pending_review") == "true"),
        "apply_ready": sum(1 for proposal in active_records if proposal.get("apply_ready")),
        "by_status": {
            status: sum(1 for proposal in active_records if proposal.get("status") == status)
            for status in REWRITE_PROPOSAL_STATUSES
        },
    }
    return {
        "all_proposals": active_records + inactive_records,
        "proposals": active_records[:12],
        "inactive_proposals": inactive_records[:8],
        "counts": counts,
        "state_path": relative_path(root, concept_rewrite_state_path(root)),
    }


def render_concept_rewrite_proposal_page(proposal: dict[str, Any]) -> str:
    frontmatter = render_frontmatter(
        {
            "id": f"rewrite-proposal-{proposal['slug']}",
            "kind": "rewrite-proposal",
            "status": proposal.get("status", "proposed"),
            "title": proposal["title"],
            "target_path": proposal.get("target_path", ""),
            "source_signature": proposal.get("source_signature", ""),
            "generated_by": "aiwiki-run-compile",
            "last_compiled_at": proposal.get("last_proposed_at", ""),
        }
    )
    lines = [
        frontmatter,
        "",
        f"# Rewrite Proposal · {proposal['title']}",
        "",
        "## Proposal Status",
        f"- Status: `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`",
        f"- Priority: `{proposal.get('priority', 'n/a')}`",
        f"- Score: `{proposal.get('score', 0)}`",
        f"- Apply ready: `{proposal.get('apply_ready', False)}`",
        f"- First proposed: `{proposal.get('first_proposed_at', '') or 'none'}`",
        f"- Last proposed: `{proposal.get('last_proposed_at', '') or 'none'}`",
        f"- Reviewed at: `{proposal.get('reviewed_at', '') or 'none'}`",
        f"- Applied at: `{proposal.get('applied_at', '') or 'none'}`",
        "",
        "## Target",
        f"- Target page: `{proposal.get('target_path', '')}`",
        f"- Source signature: `{proposal.get('source_signature', '')}`",
        f"- Source pages: `{', '.join(proposal.get('source_pages', [])) or 'none'}`",
        "",
        "## Current Summary Snapshot",
        proposal.get("current_summary", "") or "- No summary snapshot captured.",
        "",
        "## Rewrite Strategy",
        f"- Issues: `{', '.join(proposal.get('issues', [])) or 'none'}`",
        f"- Strategy: {proposal.get('rewrite_strategy', 'n/a')}",
        "",
        "## Commands",
        f"- Review: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite {proposal['slug']} --status accepted`",
        f"- Apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {proposal['slug']}`",
        "",
        "## Proposed Markdown",
    ]
    if proposal.get("candidate_markdown"):
        lines.extend(
            [
                "```markdown",
                str(proposal["candidate_markdown"]).strip(),
                "```",
            ]
        )
    else:
        lines.append("- 当前还没有生成候选重写内容。先运行 `run-compile`。")
    return "\n".join(lines) + "\n"


def render_concept_rewrite_index(state: dict[str, Any], compiled_at: str) -> str:
    proposals = state.get("proposals", [])
    inactive = state.get("inactive_proposals", [])
    counts = state.get("counts", {})
    lines = [
        "# Rewrite Proposals",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- Active proposals：`{counts.get('active', 0)}`",
        f"- Pending review：`{counts.get('pending_review', 0)}`",
        f"- Apply ready：`{counts.get('apply_ready', 0)}`",
        f"- 状态文件：`{state.get('state_path', '.aiwiki/state/concept-rewrite-proposals.json')}`",
        "",
        "## Pending Review",
    ]
    pending = [proposal for proposal in proposals if proposal.get("pending_review") == "true"]
    if not pending:
        lines.append("- 当前没有待审的 rewrite proposal。")
    else:
        for proposal in pending[:12]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | status `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`"
                f" | priority `{proposal.get('priority', 'n/a')}`"
                f" | apply_ready `{proposal.get('apply_ready', False)}`"
            )
    lines.extend(["", "## Apply Ready"])
    apply_ready = [proposal for proposal in proposals if proposal.get("apply_ready")]
    if not apply_ready:
        lines.append("- 当前没有可直接应用的 rewrite proposal。")
    else:
        for proposal in apply_ready[:12]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | command `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {proposal['slug']}`"
            )
    lines.extend(["", "## Recently Closed"])
    if not inactive:
        lines.append("- 当前没有已关闭的 rewrite proposal。")
    else:
        for proposal in inactive[:8]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | status `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`"
                f" | applied `{proposal.get('applied_at', '') or 'none'}`"
            )
    return "\n".join(lines) + "\n"


def store_concept_rewrite_candidate(
    root: Path,
    slug: str,
    *,
    quality_record: dict[str, Any],
    candidate_markdown: str,
    generated_at: str,
) -> dict[str, Any]:
    ensure_layout(root)
    snapshot = concept_page_snapshot(root, slug)
    state = load_concept_rewrite_state(root)
    proposals = [dict(proposal) for proposal in state.get("proposals", []) if isinstance(proposal, dict)]
    target: dict[str, Any] | None = None
    for proposal in proposals:
        if str(proposal.get("slug") or "") == slug:
            target = proposal
            break
    if target is None:
        target = {
            "slug": slug,
            "title": str(quality_record.get("title") or snapshot.get("title") or slug),
            "status": "proposed",
            "first_proposed_at": generated_at,
        }
        proposals.append(target)
    digest = concept_rewrite_proposal_digest(candidate_markdown)
    previous_digest = str(target.get("candidate_digest") or "")
    previous_status = str(target.get("status") or "proposed")
    if previous_digest and previous_digest != digest and previous_status != "proposed":
        target["status"] = "proposed"
        target["reviewed_at"] = ""
        target["review_note"] = ""
        target["applied_at"] = ""
    target.update(
        {
            "title": str(quality_record.get("title") or snapshot.get("title") or slug),
            "priority": str(quality_record.get("priority") or "medium"),
            "score": int(quality_record.get("score") or 0),
            "issues": list(quality_record.get("issues") or []),
            "rewrite_strategy": str(quality_record.get("rewrite_strategy") or ""),
            "target_path": str(quality_record.get("path") or snapshot.get("path") or f"wiki/concepts/{slug}.md"),
            "proposal_path": relative_path(root, concept_rewrite_proposal_page_path(root, slug)),
            "source_signature": str(quality_record.get("source_signature") or snapshot.get("source_signature") or ""),
            "source_pages": list(quality_record.get("source_pages") or snapshot.get("source_pages") or []),
            "active": True,
            "last_proposed_at": generated_at,
            "occurrences": int(target.get("occurrences") or 0) + 1,
            "candidate_markdown": candidate_markdown.strip() + "\n",
            "candidate_digest": digest,
            "current_summary": str(snapshot.get("summary") or ""),
        }
    )
    target["pending_review"] = "true" if rewrite_proposal_needs_review(str(target.get("status") or "proposed")) else "false"
    target["apply_ready"] = rewrite_proposal_is_apply_ready(root, target)
    save_concept_rewrite_state(root, {"version": 1, "proposals": proposals})
    write_if_changed(root / str(target["proposal_path"]), render_concept_rewrite_proposal_page(target))
    return {
        "slug": slug,
        "proposal_path": str(target["proposal_path"]),
        "status": str(target.get("status") or "proposed"),
        "candidate_digest": digest,
    }
