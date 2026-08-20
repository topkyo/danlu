from __future__ import annotations

from pathlib import Path
from typing import Any

from ..content.archive import (
    active_material_archive_entries,
    load_archive_candidates_state,
    load_material_archive_state,
)
from ..lifecycle.status import (
    action_transition_profile,
    archive_transition_profile,
    curated_page_transition_profile,
    transition_profile,
    valid_curated_statuses,
)
from ..memory.action_core import (
    action_priority_rank,
    action_status_rank,
)
from ..protocol.runtime_config import ACTION_STATUSES
from ..render.judgment_assets import (
    judgment_asset_attention_sort_key,
    judgment_asset_shell_record,
)
from ..state.constants import DEFAULT_PROTOCOL
from ..state.manifest import load_manifest


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
    return {
        "pages": review_pages,
        "decision_pages": [page for page in review_pages if str(page.get("kind") or "") == "decision"],
        "judgment_pages": [page for page in review_pages if str(page.get("kind") or "") == "judgment"],
        "review_actions": [dict(action) for action in review_actions if isinstance(action, dict)],
    }


def shell_action_control_objects(
    root: Path,
    memory: dict[str, Any],
    *,
    revert_ready_action_ids: set[str],
) -> list[dict[str, Any]]:
    del root
    health = memory.get("health", {})
    all_actions = [
        action
        for action in [
            *health.get("actions", []),
            *health.get("inactive_actions", []),
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
        can_revert = action_id in revert_ready_action_ids
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
                "can_review": can_review,
                "can_refresh_review": bool(action.get("active", True)) and status in ACTION_STATUSES,
                "can_revert": can_revert,
                **profile,
            }
        )
    controls.sort(
        key=lambda item: (
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
    revert_ready_action_id_set = {item for item in revert_ready_action_ids if item}
    apply_ready_archive_entry_id_set = {item for item in apply_ready_archive_entry_ids if item}
    revert_ready_archive_entry_id_set = set(revert_ready_archive_entry_ids)
    return {
        "revert_ready_action_ids": sorted(revert_ready_action_id_set),
        "revert_ready_archive_entry_ids": revert_ready_archive_entry_ids,
        "actions": shell_action_control_objects(
            root,
            memory,
            revert_ready_action_ids=revert_ready_action_id_set,
        ),
        "archives": shell_archive_control_objects(
            root,
            apply_ready_archive_entry_ids=apply_ready_archive_entry_id_set,
            revert_ready_archive_entry_ids=revert_ready_archive_entry_id_set,
        ),
    }
