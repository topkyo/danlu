"""Product Shell contract helpers extracted from app_memory."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

from .app_content import (
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
from .app_protocol import (
    ACTION_STATUSES,
    PROTOCOL_LIBRARY,
    REWRITE_PROPOSAL_STATUSES,
    ensure_layout,
    load_protocol_state,
)
from .app_state import (
    DEFAULT_PROTOCOL,
    active_material_archive_entries,
    agent_workbench_path,
    domain_pilots_path,
    execution_audit_html_path,
    execution_audit_path,
    execution_center_html_path,
    execution_center_path,
    furnace_center_html_path,
    load_archive_candidates_state,
    load_compile_state,
    load_concept_rewrite_state,
    load_json_document,
    load_knowledge_lifecycle_state,
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
    shell_summary_path,
)
from .app_types import ProtocolState, ShellSummary
from .app_utils import (
    parse_frontmatter,
    relative_path,
    strip_frontmatter,
    tokenize,
    utc_now,
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from .config import LLMConfig


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


def shell_search_results(
    root: Path,
    query: str,
    *,
    limit: int = 12,
) -> dict[str, Any]:
    ensure_layout(root)
    normalized_query = query.strip()
    if not normalized_query:
        return {"query": "", "limit": limit, "result_count": 0, "results": []}
    terms = tokenize(normalized_query) or [normalized_query.lower()]
    directories = (
        ("source", root / "wiki" / "sources"),
        ("concept", root / "wiki" / "concepts"),
        ("judgment", root / "wiki" / "judgments"),
        ("decision", root / "wiki" / "decisions"),
        ("derived", root / "wiki" / "derived"),
    )
    results: list[dict[str, Any]] = []
    for kind, directory in directories:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(text)
            body = strip_frontmatter(text)
            title = str(frontmatter.get("title") or "")
            if not title:
                for line in body.splitlines():
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
            title = title or path.stem
            relative = relative_path(root, path)
            haystack = f"{title}\n{relative}\n{body}".lower()
            matched_terms = [term for term in terms if term in haystack]
            if not matched_terms and normalized_query.lower() not in haystack:
                continue
            title_lower = title.lower()
            relative_lower = relative.lower()
            score = 0
            for term in matched_terms or [normalized_query.lower()]:
                if term in title_lower:
                    score += 5
                if term in relative_lower:
                    score += 3
                score += haystack.count(term)
            preview = " ".join(line.strip() for line in body.splitlines() if line.strip())
            results.append(
                {
                    "kind": kind,
                    "title": title,
                    "path": relative,
                    "score": score,
                    "matched_terms": matched_terms,
                    "preview": preview[:220] + ("..." if len(preview) > 220 else ""),
                }
            )
    results.sort(key=lambda item: (-int(item.get("score", 0) or 0), str(item.get("path") or "")))
    return {
        "query": normalized_query,
        "limit": limit,
        "result_count": len(results),
        "results": results[:limit],
    }


def shell_drift_warnings(
    memory: dict[str, Any],
    *,
    judgment_assets: dict[str, Any],
    compile_state: dict[str, Any],
) -> list[dict[str, Any]]:
    stored_warnings = [
        dict(item)
        for item in compile_state.get("drift_warnings", [])
        if isinstance(item, dict)
    ]
    if stored_warnings:
        return stored_warnings[:8]
    warnings: list[dict[str, Any]] = []
    drift = memory.get("drift", {})
    if isinstance(drift, dict):
        for path in drift.get("missing_source_pages", [])[:4]:
            warnings.append(
                {
                    "kind": "source-reference-break",
                    "path": str(path),
                    "message": f"Missing source page `{path}`.",
                }
            )
        for path in drift.get("missing_concept_pages", [])[:4]:
            warnings.append(
                {
                    "kind": "concept-disappear",
                    "path": str(path),
                    "message": f"Missing concept page `{path}`.",
                }
            )
    attention_pages = judgment_assets.get("attention_pages", [])
    if isinstance(attention_pages, list):
        for page in attention_pages[:4]:
            if not isinstance(page, dict):
                continue
            invalidation_rule = str(page.get("invalidation_rule") or "")
            if not invalidation_rule:
                continue
            warnings.append(
                {
                    "kind": "judgment-invalidation",
                    "path": str(page.get("path") or ""),
                    "message": f"{str(page.get('title') or page.get('path') or 'judgment')} requires invalidation review.",
                }
            )
    return warnings[:8]


def shell_suggested_next_actions(
    *,
    planner_state: dict[str, Any],
    review_controls: dict[str, Any],
    execution_controls: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen_commands: set[str] = set()

    def add_action(kind: str, title: str, command: str, path: str, reason: str) -> None:
        normalized_command = command.strip()
        if not title or not normalized_command or normalized_command in seen_commands:
            return
        seen_commands.add(normalized_command)
        actions.append(
            {
                "kind": kind,
                "title": title,
                "command": normalized_command,
                "path": path,
                "reason": reason,
            }
        )

    next_action = planner_state.get("next_action", {}) if isinstance(planner_state, dict) else {}
    if isinstance(next_action, dict):
        action_id = str(next_action.get("action_id") or "")
        title = str(next_action.get("title") or action_id)
        if action_id and title:
            add_action(
                "planner",
                title,
                str(next_action.get("command_hint") or f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run"),
                str((next_action.get("target_paths") or [""])[0]),
                "planner-next-action",
            )

    for page in review_controls.get("pages", [])[:4]:
        if not isinstance(page, dict):
            continue
        path = str(page.get("path") or "")
        allowed = [str(item) for item in page.get("allowed_transitions", []) if isinstance(item, str) and item]
        status = str(page.get("default_transition") or (allowed[0] if allowed else ""))
        if not path or not status:
            continue
        add_action(
            "review",
            str(page.get("title") or path),
            f"PYTHONPATH=src python3 -m aiwiki.cli --root . review-page {path} --status {status}",
            path,
            ",".join(str(item) for item in page.get("reasons", [])[:2]) or "review-needed",
        )

    for action in execution_controls.get("actions", [])[:4]:
        if not isinstance(action, dict) or not action.get("can_apply"):
            continue
        action_id = str(action.get("action_id") or "")
        if not action_id:
            continue
        add_action(
            "apply-action",
            str(action.get("title") or action_id),
            str(
                action.get("command_hint")
                or f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run"
            ),
            str(action.get("primary_path") or ""),
            "safe-apply-ready",
        )

    for archive in execution_controls.get("archives", [])[:2]:
        if not isinstance(archive, dict) or not archive.get("can_apply"):
            continue
        entry_id = str(archive.get("entry_id") or "")
        if not entry_id:
            continue
        add_action(
            "archive",
            str(archive.get("title") or entry_id),
            f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-archive {entry_id} --dry-run",
            str(archive.get("source_path") or ""),
            "archive-ready",
        )

    return actions[:8]


def shell_dashboard(
    summary: ShellSummary,
    *,
    drift_warnings: list[dict[str, Any]],
    suggested_next_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    review_counts = summary.get("review_backlog_counts", {})
    planner = summary.get("planner", {})
    route_telemetry = summary.get("route_telemetry", {})
    recent_runs = summary.get("recent_runs", [])
    recent_receipts = summary.get("recent_receipts", [])
    return {
        "cards": [
            {"id": "pending-review", "label": "Pending review", "value": review_counts.get("pending_decisions", 0) + review_counts.get("pending_judgments", 0)},
            {"id": "ready-actions", "label": "Ready actions", "value": review_counts.get("ready_actions", 0)},
            {"id": "planner-blocked", "label": "Planner blocked", "value": planner.get("counts", {}).get("blocked", 0) if isinstance(planner, dict) else 0},
            {"id": "drift-warnings", "label": "Drift warnings", "value": len(drift_warnings)},
        ],
        "planner_next_action": dict(planner.get("next_action", {})) if isinstance(planner, dict) else {},
        "last_route": dict(route_telemetry.get("last_entry", {})) if isinstance(route_telemetry, dict) else {},
        "recent_runs": list(recent_runs[:4]),
        "recent_receipts": list(recent_receipts[:4]),
        "drift_warnings": list(drift_warnings[:4]),
        "suggested_next_actions": list(suggested_next_actions[:6]),
    }


def shell_review_controls(
    root: Path,
    *,
    queue: dict[str, list[dict[str, str]]],
    aging: dict[str, list[dict[str, str]]],
    active_protocol: str = DEFAULT_PROTOCOL,
    judgment_assets: dict[str, Any] | None = None,
    counter_evidence_scan: dict[str, Any] | None = None,
    review_actions: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    page_by_path: dict[str, dict[str, Any]] = {}
    judgment_assets = judgment_assets or {}
    counter_evidence_scan = counter_evidence_scan or {}
    review_actions = review_actions or []
    known_pages = {
        str(page.get("path") or ""): page
        for page in judgment_assets.get("lists", {}).get("pages", [])
        if isinstance(page, dict) and str(page.get("path") or "")
    }

    def add_page(page: dict[str, str], reason_code: str) -> None:
        page_path = str(page.get("path") or "")
        if not page_path:
            return
        current = page_by_path.get(page_path)
        if current is None:
            asset_record = judgment_asset_shell_record(page, active_protocol=active_protocol)
            current = {
                **asset_record,
                "can_review": False,
                "can_refresh_review": False,
                "reasons": [],
            }
            page_by_path[page_path] = current
        reasons = current.setdefault("reasons", [])
        if reason_code and reason_code not in reasons:
            reasons.append(reason_code)
        for gap_code in current.get("asset_gaps", []):
            if gap_code not in reasons:
                reasons.append(gap_code)
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
    asset_attention_pages = judgment_assets.get("lists", {}).get("attention_pages", [])
    if isinstance(asset_attention_pages, list):
        for page in asset_attention_pages:
            if not isinstance(page, dict):
                continue
            asset_record = judgment_asset_shell_record(page, active_protocol=active_protocol)
            for gap_code in asset_record.get("asset_gaps", []):
                add_page(page, gap_code)
    counter_evidence_pages = counter_evidence_scan.get("pages", [])
    if isinstance(counter_evidence_pages, list):
        for candidate in counter_evidence_pages:
            if not isinstance(candidate, dict):
                continue
            page_path = str(candidate.get("page_path") or "")
            if page_path:
                add_page(
                    known_pages.get(page_path)
                    or {
                        "path": page_path,
                        "page_id": str(candidate.get("page_id") or ""),
                        "title": str(candidate.get("page_title") or page_path),
                        "kind": str(candidate.get("page_kind") or "judgment"),
                        "status": str(candidate.get("page_status") or ""),
                        "protocol": str(candidate.get("protocol") or active_protocol),
                    },
                    "counter-evidence-candidate",
                )

    review_pages = sorted(page_by_path.values(), key=judgment_asset_attention_sort_key)

    rewrite_state = load_concept_rewrite_state(root)
    rewrite_controls: list[dict[str, Any]] = []
    for proposal in rewrite_state.get("proposals", []):
        if not isinstance(proposal, dict):
            continue
        slug = str(proposal.get("slug") or "").strip()
        can_revert = str(proposal.get("status") or "") == "applied" and bool(proposal.get("previous_markdown"))
        if not slug or (not bool(proposal.get("active", True)) and not can_revert):
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
                "quality_score": int(proposal.get("quality_score") or 0),
                "quality_band": str(proposal.get("quality_band") or ""),
                "proposal_path": str(proposal.get("proposal_path") or ""),
                "target_path": str(proposal.get("target_path") or f"wiki/concepts/{slug}.md"),
                "pending_review": str(proposal.get("pending_review") or "") == "true",
                "apply_ready": bool(proposal.get("apply_ready", False)),
                "can_review": bool(profile.get("allowed_transitions")),
                "can_refresh_review": status in REWRITE_PROPOSAL_STATUSES,
                "can_apply": bool(proposal.get("apply_ready", False)),
                "can_revert": can_revert,
                "first_proposed_at": str(proposal.get("first_proposed_at") or ""),
                "last_proposed_at": str(proposal.get("last_proposed_at") or ""),
                "reviewed_at": str(proposal.get("reviewed_at") or ""),
                "applied_at": str(proposal.get("applied_at") or ""),
                "reverted_at": str(proposal.get("reverted_at") or ""),
                "verification_status": str(proposal.get("verification_status") or ""),
                "verification_checked_at": str(proposal.get("verification_checked_at") or ""),
                "issue_count": len(proposal.get("issues", [])) if isinstance(proposal.get("issues"), list) else 0,
                "source_count": len(proposal.get("source_pages", []))
                if isinstance(proposal.get("source_pages"), list)
                else 0,
                **profile,
            }
        )
    rewrite_controls.sort(
        key=lambda item: (
            0 if item.get("can_review") else 1,
            0 if item.get("apply_ready") else 1,
            0 if item.get("can_revert") else 1,
            rewrite_proposal_status_rank(str(item.get("status") or "")),
            action_priority_rank(str(item.get("priority") or "")),
            int(item.get("quality_score", 0)),
            -int(item.get("score", 0)),
            str(item.get("title") or "").lower(),
        )
    )
    return {
        "pages": review_pages,
        "decision_pages": [page for page in review_pages if str(page.get("kind") or "") == "decision"],
        "judgment_pages": [page for page in review_pages if str(page.get("kind") or "") == "judgment"],
        "review_actions": [dict(action) for action in review_actions if isinstance(action, dict)],
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
                "recommended_temperature": str(
                    candidate.get("recommended_temperature") or archived.get("recommended_temperature") or ""
                ),
                "reason_codes": list(candidate.get("reason_codes", []))
                if isinstance(candidate.get("reason_codes"), list)
                else [],
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
    ready_actions = [action for action in repair_plan.get("ready_actions", []) if isinstance(action, dict)]
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
        if action.get("id") and action.get("last_receipt_path") and str(action.get("status") or "") == "resolved"
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
        "product_shell_html": relative_path(root, product_shell_html_path(root)),
        "furnace_center_markdown": "wiki/indexes/furnace-center.md",
        "review_center_markdown": "wiki/indexes/review-center.md",
        "judgment_assets_markdown": "wiki/indexes/judgment-assets.md",
        "cognitive_history_markdown": "wiki/indexes/cognitive-history.md",
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
                "dashboard",
                "search",
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
                "verify-rewrite",
                "revert-rewrite",
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
            "product_shell_html": product_shell_html_path(root).exists(),
        },
    }


def shell_protocol_state(root: Path) -> ProtocolState:
    state = load_protocol_state(root)
    available = sorted(PROTOCOL_LIBRARY)
    active = str(state.get("active_protocol") or DEFAULT_PROTOCOL)
    if active not in available:
        active = DEFAULT_PROTOCOL if DEFAULT_PROTOCOL in available else (available[0] if available else DEFAULT_PROTOCOL)
    return {
        "active_protocol": active,
        "available_protocols": available,
        "protocols": list(state.get("protocols", [])) if isinstance(state.get("protocols"), list) else [],
        "state_path": str(state.get("state_path") or ""),
    }


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
    execution_controls = shell_execution_controls(root, memory)
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
        "links": shell_links(root),
        "capabilities": shell_capabilities(root),
    }
    summary["dashboard"] = shell_dashboard(
        summary,
        drift_warnings=drift_warnings,
        suggested_next_actions=suggested_next_actions,
    )
    return summary


def render_product_shell_html(summary: ShellSummary) -> str:
    def shell_href(target: str) -> str:
        if not target:
            return ""
        return os.path.relpath(target, start="output/control").replace(os.sep, "/")
    locale_text = {
        "zh": {
            "Furnace Product Shell": "炼丹炉 Product Shell",
            "Protocol": "协议",
            "Generated": "生成于",
            "Quick Links": "快捷链接",
            "Planner": "规划器",
            "Query Routing": "查询路由",
            "Suggested Next Actions": "建议下一步动作",
            "Drift Warnings": "漂移告警",
            "Recent Runs": "最近运行",
            "Recent Receipts": "最近回执",
            "Furnace Center": "炉心面板",
            "Review Center": "审阅中心",
            "Execution Center": "执行中心",
            "Execution Audit": "执行审计",
            "Graph View": "图谱视图",
            "Shell Summary": "Shell 摘要",
            "LLM backend (effective)": "LLM 后端（生效）",
            "LLM backend (requested)": "LLM 后端（请求）",
            "LLM model (effective)": "LLM 模型（生效）",
            "LLM model (requested)": "LLM 模型（请求）",
            "Usage visibility": "Usage 可见性",
            "Usage accounting": "Usage 计费口径",
            "Auth mode": "认证方式",
            "Message": "提示",
            "action": "动作",
            "score": "分数",
            "reason": "原因",
            "query": "查询",
            "none": "无",
            "warning": "告警",
            "drift": "漂移",
            "runtime": "运行",
            "receipt": "回执",
            "review": "审阅",
            "Pending review": "待审阅",
            "Ready actions": "可执行动作",
            "Planner blocked": "规划阻塞",
            "Recent routes": "最近路由",
            "No planner action is queued yet.": "当前还没有排队中的规划动作。",
            "No query route telemetry has been recorded yet.": "当前还没有记录查询路由遥测。",
            "No runtime events yet.": "当前还没有运行事件。",
            "No execution receipts yet.": "当前还没有执行回执。",
            "No suggested actions yet.": "当前还没有建议动作。",
            "No drift warnings.": "当前没有漂移告警。",
            "general": "通用",
            "investing": "投资",
            "research": "研究",
            "product": "产品",
            "ops": "运维",
            "opaque-cli": "CLI 不透明",
            "response-usage": "返回 usage",
            "result-usage": "返回 usage",
            "codex-cli-session": "Codex CLI 会话",
            "nvidia-nim-api": "NVIDIA NIM API",
            "copilot-cli-session": "Copilot CLI 会话",
            "claude-cli-session": "Claude CLI 会话",
            "cli-session": "CLI 会话",
            "api-key": "API Key",
            "apply": "应用",
            "review-page": "审阅页面",
            "archive-apply": "归档应用",
            "archive-revert": "归档回滚",
            "knowledge-lifecycle-override": "生命周期覆盖",
            "nightly": "夜间巡检",
            "default": "默认",
            "success": "成功",
            "failed": "失败",
            "running": "运行中",
        }
    }

    def text(locale: str, key: str) -> str:
        base = str(key or "")
        if locale == "zh":
            return locale_text["zh"].get(base, base)
        return base

    def value_text(locale: str, value: Any, *, fallback: str = "none") -> str:
        raw = str(value or "").strip()
        token = raw or fallback
        return text(locale, token)

    def escape_value(locale: str, value: Any, *, fallback: str = "none") -> str:
        return html.escape(value_text(locale, value, fallback=fallback))

    links = summary.get("links", {})
    review_counts = summary.get("review_backlog_counts", {})
    dashboard = summary.get("dashboard", {})
    planner = summary.get("planner", {})
    planner_next_action = planner.get("next_action", {}) if isinstance(planner, dict) else {}
    route_telemetry = summary.get("route_telemetry", {})
    last_route = route_telemetry.get("last_entry", {}) if isinstance(route_telemetry, dict) else {}
    recent_runs = summary.get("recent_runs", [])
    recent_receipts = summary.get("recent_receipts", [])
    llm_status = summary.get("llm_status", {})
    dashboard_cards = dashboard.get("cards", []) if isinstance(dashboard, dict) else []
    summary_cards = [
        (
            str(card.get("label") or ""),
            card.get("value", 0),
        )
        for card in dashboard_cards
        if isinstance(card, dict)
    ] or [
        ("Pending review", review_counts.get("pending_decisions", 0) + review_counts.get("pending_judgments", 0)),
        ("Ready actions", review_counts.get("ready_actions", 0)),
        ("Planner blocked", planner.get("counts", {}).get("blocked", 0) if isinstance(planner, dict) else 0),
        ("Recent routes", len(route_telemetry.get("entries", [])) if isinstance(route_telemetry, dict) else 0),
    ]
    quick_links = [
        ("Furnace Center", str(links.get("furnace_center_html") or "")),
        ("Review Center", str(links.get("review_center_html") or "")),
        ("Execution Center", str(links.get("execution_center_html") or "")),
        ("Execution Audit", str(links.get("execution_audit_html") or "")),
        ("Graph View", str(links.get("graph_html") or "")),
        ("Shell Summary", str(links.get("summary_path") or "")),
    ]
    suggested_actions = summary.get("suggested_next_actions", [])
    drift_warnings = summary.get("drift_warnings", [])

    def render_cards(locale: str) -> str:
        return "".join(
            f"<article class='card'><h2>{html.escape(text(locale, title))}</h2><strong>{html.escape(str(value))}</strong></article>"
            for title, value in summary_cards
        )

    def render_links(locale: str) -> str:
        return "".join(
            f"<li><a href='{html.escape(shell_href(target))}'>{html.escape(text(locale, label))}</a></li>"
            for label, target in quick_links
            if target
        )

    def render_planner(locale: str) -> str:
        if planner_next_action:
            return (
                f"<p><strong>{html.escape(str(planner_next_action.get('title') or text(locale, 'none')))}</strong>"
                f" · {html.escape(text(locale, 'action'))} <code>{escape_value(locale, planner_next_action.get('action_id'))}</code>"
                f" · {html.escape(text(locale, 'score'))} <code>{html.escape(str(planner_next_action.get('priority_score', 0)))}</code></p>"
            )
        return f"<p>{html.escape(text(locale, 'No planner action is queued yet.'))}</p>"

    def render_route(locale: str) -> str:
        if last_route:
            return (
                f"<p><strong>{escape_value(locale, last_route.get('selected_strategy'))}</strong>"
                f" · {html.escape(text(locale, 'reason'))} <code>{escape_value(locale, last_route.get('selection_reason'))}</code>"
                f" · {html.escape(text(locale, 'query'))} <code>{escape_value(locale, last_route.get('query_signature'))}</code></p>"
            )
        return f"<p>{html.escape(text(locale, 'No query route telemetry has been recorded yet.'))}</p>"

    def render_runs(locale: str) -> str:
        return "".join(
            f"<li><code>{escape_value(locale, run.get('event_type'), fallback='runtime')}</code>"
            f" · {html.escape(str(run.get('occurred_at') or ''))}"
            f" · {html.escape(str(run.get('title') or run.get('summary') or ''))}</li>"
            for run in recent_runs[:6]
            if isinstance(run, dict)
        ) or f"<li>{html.escape(text(locale, 'No runtime events yet.'))}</li>"

    def render_receipts(locale: str) -> str:
        return "".join(
            f"<li><code>{escape_value(locale, receipt.get('operation'), fallback='apply')}</code>"
            f" · {html.escape(str(receipt.get('title') or receipt.get('action_id') or text(locale, 'receipt')))}"
            f" · {html.escape(str(receipt.get('applied_at') or ''))}</li>"
            for receipt in recent_receipts[:6]
            if isinstance(receipt, dict)
        ) or f"<li>{html.escape(text(locale, 'No execution receipts yet.'))}</li>"

    def render_suggested(locale: str) -> str:
        return "".join(
            f"<li><strong>{html.escape(str(action.get('title') or text(locale, 'action')))}</strong>"
            f" · <code>{html.escape(str(action.get('command') or ''))}</code></li>"
            for action in suggested_actions[:6]
            if isinstance(action, dict)
        ) or f"<li>{html.escape(text(locale, 'No suggested actions yet.'))}</li>"

    def render_drift(locale: str) -> str:
        return "".join(
            f"<li><code>{escape_value(locale, item.get('kind'), fallback='drift')}</code>"
            f" · {html.escape(str(item.get('message') or item.get('path') or text(locale, 'warning')))}</li>"
            for item in drift_warnings[:6]
            if isinstance(item, dict)
        ) or f"<li>{html.escape(text(locale, 'No drift warnings.'))}</li>"

    def render_llm(locale: str) -> str:
        rows = [
            ("LLM backend (effective)", llm_status.get("backend")),
            ("LLM backend (requested)", llm_status.get("backend_requested")),
            ("LLM model (effective)", llm_status.get("effective_model") or llm_status.get("model")),
            ("LLM model (requested)", llm_status.get("model_requested")),
            ("Usage visibility", llm_status.get("usage_visibility")),
            ("Usage accounting", llm_status.get("usage_accounting")),
            ("Auth mode", llm_status.get("auth_mode")),
        ]
        if llm_status.get("message"):
            rows.append(("Message", llm_status.get("message")))
        return "".join(
            f"<p><span class='meta-label'>{html.escape(text(locale, label))}</span> <code>{escape_value(locale, value)}</code></p>"
            for label, value in rows
        )

    def render_panel(locale: str) -> str:
        return "\n".join(
            [
                "      <div class='hero'>",
                "        <div>",
                f"          <h1>{html.escape(text(locale, 'Furnace Product Shell'))}</h1>",
                (
                    f"          <p>{html.escape(text(locale, 'Protocol'))} "
                    f"<code>{escape_value(locale, summary.get('active_protocol') or DEFAULT_PROTOCOL)}</code>"
                    f" · {html.escape(text(locale, 'Generated'))} "
                    f"<code>{html.escape(str(summary.get('generated_at') or ''))}</code></p>"
                ),
                "        </div>",
                "        <div class='llm-box'>",
                render_llm(locale),
                "        </div>",
                "      </div>",
                f"      <div class='cards'>{render_cards(locale)}</div>",
                "      <div class='grid'>",
                "        <section>",
                f"          <h2>{html.escape(text(locale, 'Quick Links'))}</h2>",
                f"          <ul>{render_links(locale)}</ul>",
                "        </section>",
                "        <section>",
                f"          <h2>{html.escape(text(locale, 'Planner'))}</h2>",
                f"          {render_planner(locale)}",
                "        </section>",
                "        <section>",
                f"          <h2>{html.escape(text(locale, 'Query Routing'))}</h2>",
                f"          {render_route(locale)}",
                "        </section>",
                "        <section>",
                f"          <h2>{html.escape(text(locale, 'Suggested Next Actions'))}</h2>",
                f"          <ul>{render_suggested(locale)}</ul>",
                "        </section>",
                "        <section>",
                f"          <h2>{html.escape(text(locale, 'Drift Warnings'))}</h2>",
                f"          <ul>{render_drift(locale)}</ul>",
                "        </section>",
                "        <section>",
                f"          <h2>{html.escape(text(locale, 'Recent Runs'))}</h2>",
                f"          <ul>{render_runs(locale)}</ul>",
                "        </section>",
                "        <section>",
                f"          <h2>{html.escape(text(locale, 'Recent Receipts'))}</h2>",
                f"          <ul>{render_receipts(locale)}</ul>",
                "        </section>",
                "      </div>",
            ]
        )

    return "\n".join(
        [
            "<!DOCTYPE html>",
            "<html lang='zh' data-default-locale='zh'>",
            "<head>",
            "  <meta charset='utf-8' />",
            "  <meta name='viewport' content='width=device-width, initial-scale=1' />",
            "  <title>炼丹炉 Product Shell</title>",
            "  <style>",
            "    body { font-family: Inter, system-ui, sans-serif; margin: 0; background: #0b1020; color: #e5eefc; }",
            "    main { max-width: 1100px; margin: 0 auto; padding: 24px 20px 48px; }",
            "    .toolbar { display: flex; justify-content: flex-end; margin-bottom: 12px; }",
            "    .locale-switch { display: inline-flex; gap: 8px; }",
            "    .locale-switch button { background: #111833; color: #e5eefc; border: 1px solid #243255; border-radius: 999px; padding: 6px 12px; cursor: pointer; }",
            "    .locale-switch button.active { background: #2f6feb; border-color: #2f6feb; }",
            "    .locale-panel { display: none; }",
            "    .locale-panel.active { display: block; }",
            "    .hero { display: flex; justify-content: space-between; gap: 24px; flex-wrap: wrap; margin-bottom: 24px; }",
            "    .llm-box { min-width: 280px; }",
            "    .meta-label { display: inline-block; min-width: 160px; color: #aebbd6; }",
            "    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0 28px; }",
            "    .card, section { background: #111833; border: 1px solid #243255; border-radius: 14px; padding: 16px; }",
            "    h1, h2 { margin: 0 0 12px; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    a { color: #8cc4ff; }",
            "    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }",
            "    code { color: #ffd580; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <div class='toolbar'>",
            "      <div class='locale-switch'>",
            "        <button type='button' data-locale-btn='zh' class='active'>中文</button>",
            "        <button type='button' data-locale-btn='en'>English</button>",
            "      </div>",
            "    </div>",
            "    <section class='locale-panel active' data-locale-panel='zh'>",
            render_panel("zh"),
            "    </section>",
            "    <section class='locale-panel' data-locale-panel='en'>",
            render_panel("en"),
            "    </section>",
            "  </main>",
            "  <script>",
            "    (() => {",
            "      const setLocale = (locale) => {",
            "        document.querySelectorAll('[data-locale-panel]').forEach((panel) => {",
            "          panel.classList.toggle('active', panel.getAttribute('data-locale-panel') === locale);",
            "        });",
            "        document.querySelectorAll('[data-locale-btn]').forEach((button) => {",
            "          button.classList.toggle('active', button.getAttribute('data-locale-btn') === locale);",
            "        });",
            "        document.documentElement.lang = locale === 'en' ? 'en' : 'zh';",
            "      };",
            "      document.querySelectorAll('[data-locale-btn]').forEach((button) => {",
            "        button.addEventListener('click', () => setLocale(button.getAttribute('data-locale-btn') || 'zh'));",
            "      });",
            "      setLocale(document.documentElement.getAttribute('data-default-locale') || 'zh');",
            "    })();",
            "  </script>",
            "</body>",
            "</html>",
            "",
        ]
    )


def shell_status_dashboard(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    summary = write_shell_summary(root, build_shell_summary(root))
    return {
        "generated_at": str(summary.get("generated_at") or ""),
        "active_protocol": str(summary.get("active_protocol") or DEFAULT_PROTOCOL),
        "dashboard": dict(summary.get("dashboard", {})) if isinstance(summary.get("dashboard"), dict) else {},
        "suggested_next_actions": list(summary.get("suggested_next_actions", [])),
        "drift_warnings": list(summary.get("drift_warnings", [])),
        "links": dict(summary.get("links", {})) if isinstance(summary.get("links"), dict) else {},
    }


def shell_search(root: Path, query: str, *, limit: int = 12) -> dict[str, Any]:
    ensure_layout(root)
    summary = build_shell_summary(root)
    summary["search_results"] = shell_search_results(root, query, limit=limit)
    write_shell_summary(root, summary)
    return dict(summary["search_results"])


def write_shell_summary(root: Path, summary: ShellSummary | None = None) -> ShellSummary:
    summary = summary or build_shell_summary(root)
    write_json_document_if_changed_ignoring_generated_timestamps(shell_summary_path(root), summary)
    write_if_changed_ignoring_timestamps(product_shell_html_path(root), render_product_shell_html(summary))
    return summary
