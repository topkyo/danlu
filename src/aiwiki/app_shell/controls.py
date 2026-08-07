from __future__ import annotations

from pathlib import Path
from typing import Any

from ..content.archive import (
    active_material_archive_entries,
    load_archive_candidates_state,
    load_material_archive_state,
)
from ..corpus.link_state import load_concept_rewrite_state
from ..lifecycle.status import (
    action_transition_profile,
    archive_transition_profile,
    curated_page_transition_profile,
    rewrite_proposal_status_rank,
    rewrite_transition_profile,
    transition_profile,
    valid_curated_statuses,
)
from ..memory.action_core import (
    action_priority_rank,
    action_status_rank,
    action_supports_low_risk_apply,
)
from ..protocol.runtime_config import ACTION_STATUSES, REWRITE_PROPOSAL_STATUSES
from ..render.judgment_assets import (
    judgment_asset_attention_sort_key,
    judgment_asset_shell_record,
)
from ..render.paths import (
    execution_bundle_path,
    execution_proposal_path,
)
from ..state.constants import DEFAULT_PROTOCOL
from ..state.manifest import load_manifest
from ..utils.path import relative_path


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
        control = rewrite_control_object(root, proposal)
        if control is not None:
            rewrite_controls.append(control)
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


def rewrite_control_object(root: Path, proposal: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(proposal, dict):
        return None
    slug = str(proposal.get("slug") or "").strip()
    status = str(proposal.get("status") or "proposed")
    can_revert = status == "applied" and bool(proposal.get("previous_markdown"))
    if not slug or (not bool(proposal.get("active", True)) and not can_revert):
        return None
    profile = rewrite_transition_profile(status)
    return {
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
        "has_candidate_markdown": bool(str(proposal.get("candidate_markdown") or "").strip()),
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
        "source_count": len(proposal.get("source_pages", [])) if isinstance(proposal.get("source_pages"), list) else 0,
        **profile,
    }


def rewrite_control_objects_for_paths(root: Path, proposal_paths: list[str]) -> list[dict[str, Any]]:
    normalized_paths = [str(path).strip() for path in proposal_paths if str(path).strip()]
    if not normalized_paths:
        return []
    controls_by_path: dict[str, dict[str, Any]] = {}
    for proposal in load_concept_rewrite_state(root).get("proposals", []):
        control = rewrite_control_object(root, proposal)
        if control is None:
            continue
        proposal_path = str(control.get("proposal_path") or "")
        if proposal_path:
            controls_by_path[proposal_path] = control
    controls: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for proposal_path in normalized_paths:
        control = controls_by_path.get(proposal_path)
        if control is None:
            continue
        slug = str(control.get("slug") or "")
        if slug and slug in seen_slugs:
            continue
        if slug:
            seen_slugs.add(slug)
        controls.append(control)
    return controls


def rewrite_followup_action(control: dict[str, Any]) -> dict[str, Any] | None:
    slug = str(control.get("slug") or "").strip()
    if not slug:
        return None
    title = str(control.get("title") or slug)
    status = str(control.get("current_status") or control.get("status") or "").strip()
    proposal_path = str(control.get("proposal_path") or "").strip()
    target_path = str(control.get("target_path") or "").strip()
    allowed_transitions = [
        str(item) for item in control.get("allowed_transitions", []) if isinstance(item, str) and item.strip()
    ]
    preferred_transitions = [
        str(item) for item in control.get("preferred_transitions", []) if isinstance(item, str) and item.strip()
    ]
    default_transition = str(
        control.get("default_transition") or (allowed_transitions[0] if allowed_transitions else "")
    ).strip()
    base = {
        "slug": slug,
        "status": status,
        "current_status": status,
        "proposal_path": proposal_path,
        "target_path": target_path,
        "allowed_transitions": allowed_transitions,
        "preferred_transitions": preferred_transitions,
        "default_transition": default_transition,
        "can_review": bool(control.get("can_review")),
        "can_apply": bool(control.get("can_apply")),
        "can_revert": bool(control.get("can_revert")),
    }
    if bool(control.get("can_apply")) or (
        bool(control.get("can_review")) and bool(control.get("has_candidate_markdown"))
    ):
        return {
            **base,
            "kind": "rewrite-proposal",
            "title": title,
            "command": "PYTHONPATH=src python3 -m aiwiki.cli --root . advanced review-queue --json",
            "path": proposal_path or target_path,
            "reason": "rewrite-apply-ready"
            if bool(control.get("can_apply"))
            else ("rewrite-review-needed" if bool(control.get("pending_review")) else f"rewrite-{status or 'review'}"),
            "transition": default_transition,
        }
    return None


def rewrite_followup_actions_for_controls(rewrite_controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen_commands: set[str] = set()
    for control in rewrite_controls:
        if not isinstance(control, dict):
            continue
        action = rewrite_followup_action(control)
        if action is None:
            continue
        command = str(action.get("command") or "").strip()
        if not command or command in seen_commands:
            continue
        seen_commands.add(command)
        actions.append(action)
    return actions


def rewrite_followup_payload_for_paths(root: Path, proposal_paths: list[str]) -> dict[str, Any]:
    rewrite_controls = rewrite_control_objects_for_paths(root, proposal_paths)
    return {
        "updated_rewrite_proposals": rewrite_controls,
        "rewrite_followup_actions": rewrite_followup_actions_for_controls(rewrite_controls),
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
