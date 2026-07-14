"""Agentic debt autopilot.

This module is the execution-owner surface for non-core debt detection and
safe debt digestion. Product Shell may render this data, but unattended apply
decisions must not depend on Product Shell controls.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .app_state import (
    l3_proposal_state_path,
    load_json_document,
    load_knowledge_lifecycle_state,
    load_machine_memory,
    load_machine_memory_action_state,
    load_manifest,
)
from .app_utils import runtime_write_operation
from .autonomy_domains import classify_l3_proposal, classify_machine_memory_action
from .autonomy_policy import load_policy
from .content.memory import action_supports_low_risk_apply
from .execution.machine_memory_actions import auto_resolve_machine_memory_actions

LLM_OWNED_NON_CORE = "llm_owned_non_core"
CORE_MANUAL_ONLY = "core_manual_only"
MAINTENANCE = "maintenance"
EXTERNAL_HUMAN_REQUIRED = "external_human_required"


def collect_auto_adopt_work(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return review/execution controls from owner state, not UI surfaces."""

    lifecycle = load_knowledge_lifecycle_state(root)
    entries = [entry for entry in lifecycle.get("entries", []) if isinstance(entry, dict)]
    concept_backlog = [
        {"slug": _entry_slug(entry), "path": str(entry.get("path") or "")}
        for entry in entries
        if str(entry.get("kind") or "") == "concept"
        and str(entry.get("lifecycle_state") or "") == "review"
        and _entry_slug(entry)
    ]
    revisit_concepts = [
        {"slug": _entry_slug(entry), "path": str(entry.get("path") or "")}
        for entry in entries
        if str(entry.get("kind") or "") == "concept"
        and str(entry.get("lifecycle_state") or "") == "revisit"
        and _entry_slug(entry)
    ]
    actions = [_action_control(root, action) for action in _active_actions(root)]
    return (
        {
            "source": "debt-autopilot-owner-state",
            "concept_backlog": concept_backlog,
            "revisit_concepts": revisit_concepts,
        },
        {
            "source": "debt-autopilot-owner-state",
            "actions": actions,
        },
    )


def collect_debt_inventory(root: Path, *, nightly: dict[str, Any] | None = None) -> dict[str, Any]:
    """Collect current non-core debt without mutating the vault."""

    memory = load_machine_memory(root)
    health = memory.get("health", {}) if isinstance(memory.get("health"), dict) else {}
    quality = health.get("concept_quality", {})
    if not isinstance(quality, dict):
        quality = {}
    applied_rewrite_slugs = _current_applied_rewrite_slugs(root)
    counter_evidence_scan = health.get("counter_evidence_scan", {})
    counter_evidence_pages = (
        counter_evidence_scan.get("pages", []) if isinstance(counter_evidence_scan, dict) else []
    )
    judgment_review_actions = health.get("judgment_review_actions", [])
    actions = _active_actions(root)
    l3_state = load_json_document(l3_proposal_state_path(root))
    l3_proposals = l3_state.get("proposals") if isinstance(l3_state.get("proposals"), list) else []

    categories: dict[str, dict[str, Any]] = {
        "pending_source_summaries": _category_from_values(
            _current_pending_source_summaries(root),
            apply_strategy="llm_run_compile",
        ),
        "weak_concepts": _category_from_values(
            _without_slugs(_slugs_from_records(quality.get("weak_concepts")), applied_rewrite_slugs),
            apply_strategy="llm_concept_rewrite",
        ),
        "rewrite_candidates": _category_from_values(
            _without_slugs(_slugs_from_records(quality.get("rewrite_candidates")), applied_rewrite_slugs),
            apply_strategy="llm_apply_rewrite",
        ),
        "judgment_review_actions": _category_from_values(
            [
                str(action.get("id") or "")
                for action in (judgment_review_actions if isinstance(judgment_review_actions, list) else [])
                if isinstance(action, dict)
            ],
            apply_strategy="llm_judgment_review",
        ),
        "counter_evidence_candidates": _category_from_values(
            [
                str(candidate.get("page_path") or "")
                for candidate in counter_evidence_pages
                if isinstance(candidate, dict)
            ],
            apply_strategy="llm_judgment_review",
        ),
        "machine_memory_actions": _category_from_values(
            _llm_owned_machine_memory_action_ids(root, actions),
            apply_strategy="llm_or_safe_action_apply",
        ),
        "l3_non_core_proposals": _category_from_values(
            _llm_owned_l3_proposal_ids(root, l3_proposals),
            apply_strategy="metadata_auto_apply",
        ),
    }
    for category in categories.values():
        category["autonomy_boundary"] = LLM_OWNED_NON_CORE
        category["domain"] = "non_core_semantic"

    items = _inventory_items(categories, limit=30)
    detected = sum(int(category["count"]) for category in categories.values())
    by_strategy = Counter(str(category.get("apply_strategy") or "") for category in categories.values() if int(category["count"]))
    return {
        "version": 1,
        "status": "clear" if detected == 0 else "active",
        "autonomy_boundary": LLM_OWNED_NON_CORE,
        "debt_detected_count": detected,
        "debt_remaining_count": detected,
        "llm_owned_non_core_pending_count": detected,
        "categories": categories,
        "apply_strategy_counts": dict(sorted(by_strategy.items())),
        "items": items,
    }


@runtime_write_operation
def run_debt_autopilot(
    root: Path,
    *,
    apply: bool = False,
    nightly: dict[str, Any] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Digest safe accepted non-core debt and report remaining LLM-owned debt."""

    before = collect_debt_inventory(root, nightly=nightly)
    content_result: dict[str, Any] = {
        "operation": "content-debt-digestion",
        "dry_run": not apply,
        "status": "skipped",
        "reason": "no_content_debt" if not _has_content_debt(before) else "apply_disabled",
        "counts": {
            "updated_source_pages": 0,
            "failed_source_pages": 0,
            "updated_concept_pages": 0,
            "generated_rewrite_proposals": 0,
            "applied_rewrite_proposals": 0,
            "skipped_rewrite_proposals": 0,
            "failed_rewrite_proposals": 0,
        },
        "items": [],
    }
    if apply and _has_content_debt(before):
        content_result = _digest_content_debt(root, limit=limit)
    auto_resolution = auto_resolve_machine_memory_actions(
        root,
        dry_run=not apply,
        limit=limit,
        include_proposed=False,
        escalate_unsupported=False,
        note="debt-autopilot: apply accepted low-risk non-core debt",
    )
    after = collect_debt_inventory(root, nightly=nightly) if apply else before
    counts = auto_resolution.get("counts") if isinstance(auto_resolution.get("counts"), dict) else {}
    content_counts = content_result.get("counts") if isinstance(content_result.get("counts"), dict) else {}
    auto_resolved = (
        int(counts.get("applied", 0) or 0)
        + int(counts.get("escalated", 0) or 0)
        + int(content_counts.get("updated_source_pages", 0) or 0)
        + int(content_counts.get("updated_concept_pages", 0) or 0)
        + int(content_counts.get("applied_rewrite_proposals", 0) or 0)
    )
    return {
        "operation": "debt-autopilot",
        "dry_run": not apply,
        "side_effects_allowed": bool(apply),
        "status": "applied" if apply and auto_resolved else "preview",
        "debt_detected_count": int(before.get("debt_detected_count") or 0),
        "debt_auto_resolved_count": auto_resolved,
        "debt_remaining_count": int(after.get("debt_remaining_count") or 0),
        "before": before,
        "after": after,
        "content_digestion": content_result,
        "auto_resolution": auto_resolution,
    }


def _active_actions(root: Path) -> list[dict[str, Any]]:
    state = load_machine_memory_action_state(root)
    return [
        dict(action)
        for action in state.get("actions", [])
        if isinstance(action, dict) and bool(action.get("active", True))
    ]


def _action_control(root: Path, action: dict[str, Any]) -> dict[str, Any]:
    status = _action_status(action)
    policy = load_policy(root)
    classification = classify_machine_memory_action(
        action,
        autonomy_profile=policy.autonomy_profile,
        revert_supported=action_supports_low_risk_apply(action),
        root=root,
    )
    return {
        "action_id": str(action.get("id") or ""),
        "kind": str(action.get("kind") or ""),
        "status": status,
        "title": str(action.get("title") or action.get("id") or ""),
        "can_review": status in {"proposed", "deferred"},
        "can_apply": status == "accepted" and action_supports_low_risk_apply(action),
        "autonomy_domain": classification.autonomy_domain,
        "autonomy_boundary": LLM_OWNED_NON_CORE
        if classification.autonomy_domain == "non_core_semantic"
        else classification.autonomy_domain,
        "execution_strategy": classification.execution_strategy,
    }


def _action_status(action: dict[str, Any]) -> str:
    return str(action.get("status") or "proposed")


def _action_is_already_human_required(action: dict[str, Any]) -> bool:
    return (
        _action_status(action) == "deferred"
        and str(action.get("human_required") or "").lower() == "true"
        and bool(str(action.get("human_required_reason") or "").strip())
    )


def _llm_owned_machine_memory_action_ids(root: Path, actions: list[dict[str, Any]]) -> list[str]:
    policy = load_policy(root)
    ids: list[str] = []
    for action in actions:
        status = _action_status(action)
        if status not in {"proposed", "accepted", "deferred"} or _action_is_already_human_required(action):
            continue
        classification = classify_machine_memory_action(
            action,
            autonomy_profile=policy.autonomy_profile,
            revert_supported=action_supports_low_risk_apply(action),
            root=root,
        )
        if classification.autonomy_domain == "non_core_semantic":
            action_id = str(action.get("id") or "")
            if action_id:
                ids.append(action_id)
    return ids


def _llm_owned_l3_proposal_ids(root: Path, proposals: object) -> list[str]:
    if not isinstance(proposals, list):
        return []
    policy = load_policy(root)
    ids: list[str] = []
    for proposal in proposals:
        if not isinstance(proposal, dict) or str(proposal.get("state") or "") not in {"candidate", "accepted"}:
            continue
        classification = classify_l3_proposal(
            proposal,
            autonomy_profile=policy.autonomy_profile,
            revert_supported=False,
            root=root,
        )
        if classification.autonomy_domain == "non_core_semantic":
            proposal_id = str(proposal.get("proposal_id") or "")
            if proposal_id:
                ids.append(proposal_id)
    return ids


def _entry_slug(entry: dict[str, Any]) -> str:
    slug = str(entry.get("slug") or "").strip()
    if slug:
        return slug
    path = str(entry.get("path") or "").strip()
    return Path(path).stem if path else ""


def _category_from_values(values: object, *, apply_strategy: str) -> dict[str, Any]:
    items = [str(item) for item in (values if isinstance(values, list) else []) if str(item).strip()]
    return {
        "count": len(items),
        "sample": items[:8],
        "apply_strategy": apply_strategy,
    }


def _slugs_from_records(records: object) -> list[str]:
    if not isinstance(records, list):
        return []
    return [
        str(item.get("slug") or Path(str(item.get("path") or "")).stem)
        for item in records
        if isinstance(item, dict) and (item.get("slug") or item.get("path"))
    ]


def _without_slugs(slugs: list[str], excluded: set[str]) -> list[str]:
    return [slug for slug in slugs if slug not in excluded]


def _current_applied_rewrite_slugs(root: Path) -> set[str]:
    from .app_state import load_concept_rewrite_state
    from .content.memory import rewrite_proposal_candidate_is_current

    state = load_concept_rewrite_state(root)
    slugs: set[str] = set()
    proposals = state.get("proposals") if isinstance(state.get("proposals"), list) else []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        slug = str(proposal.get("slug") or "").strip()
        if (
            slug
            and bool(proposal.get("active", True))
            and str(proposal.get("status") or "") == "applied"
            and str(proposal.get("verification_status") or "") == "passed"
            and rewrite_proposal_candidate_is_current(root, proposal)
        ):
            slugs.add(slug)
    return slugs


def _current_pending_source_summaries(root: Path) -> list[str]:
    from .app_linting.core import pending_source_summary_ids

    manifest = load_manifest(root)
    entries = [entry for entry in manifest.get("entries", []) if isinstance(entry, dict) and entry.get("id")]
    return pending_source_summary_ids(root, entries)


def _has_content_debt(inventory: dict[str, Any]) -> bool:
    categories = inventory.get("categories") if isinstance(inventory.get("categories"), dict) else {}
    return any(
        int((categories.get(name) if isinstance(categories.get(name), dict) else {}).get("count") or 0) > 0
        for name in ("pending_source_summaries", "weak_concepts", "rewrite_candidates")
    )


def _digest_content_debt(root: Path, *, limit: int | None) -> dict[str, Any]:
    from .runner.workflows import run_compile

    effective_limit = _effective_content_limit(limit)
    compile_runs: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    compile_counts = {
        "updated_source_pages": 0,
        "failed_source_pages": 0,
        "updated_concept_pages": 0,
        "generated_rewrite_proposals": 0,
    }
    for source_id in _current_pending_source_summaries(root)[:effective_limit]:
        item: dict[str, Any] = {"category": "pending_source_summaries", "ref": source_id}
        try:
            result = run_compile(root, limit=1, paths=[source_id])
        except Exception as exc:
            compile_counts["failed_source_pages"] += 1
            item["status"] = "failed"
            item["error"] = {"type": type(exc).__name__, "message": str(exc)}
            items.append(item)
            continue
        compile_runs.append(result)
        updated_pages = list(result.get("updated_pages", []) or [])
        updated_concept_pages = list(result.get("updated_concept_pages", []) or [])
        updated_rewrite_proposals = list(result.get("updated_rewrite_proposal_pages", []) or [])
        compile_counts["updated_source_pages"] += len(updated_pages)
        compile_counts["updated_concept_pages"] += len(updated_concept_pages)
        compile_counts["generated_rewrite_proposals"] += len(updated_rewrite_proposals)
        item["status"] = "applied" if updated_pages else "noop"
        item["updated_pages"] = updated_pages
        items.append(item)
    rewrite_generation_result = _generate_rewrite_candidates(root, limit=effective_limit)
    rewrite_generation_counts = (
        rewrite_generation_result.get("counts") if isinstance(rewrite_generation_result.get("counts"), dict) else {}
    )
    compile_counts["updated_concept_pages"] += int(rewrite_generation_counts.get("updated_concept_pages", 0) or 0)
    compile_counts["generated_rewrite_proposals"] += int(
        rewrite_generation_counts.get("generated_rewrite_proposals", 0) or 0
    )
    items.extend(rewrite_generation_result.get("items", []) if isinstance(rewrite_generation_result.get("items"), list) else [])
    rewrite_result = _auto_apply_concept_rewrite_proposals(root, limit=effective_limit)
    rewrite_counts = rewrite_result.get("counts") if isinstance(rewrite_result.get("counts"), dict) else {}
    changed_count = (
        int(compile_counts["updated_source_pages"] or 0)
        + int(compile_counts["updated_concept_pages"] or 0)
        + int(compile_counts["generated_rewrite_proposals"] or 0)
        + int(rewrite_counts.get("applied", 0) or 0)
    )
    return {
        "operation": "content-debt-digestion",
        "dry_run": False,
        "status": "applied" if changed_count > 0 else "noop",
        "limit": effective_limit,
        "counts": {
            **compile_counts,
            "applied_rewrite_proposals": int(rewrite_counts.get("applied", 0) or 0),
            "skipped_rewrite_proposals": int(rewrite_counts.get("skipped", 0) or 0),
            "failed_rewrite_proposals": int(rewrite_counts.get("failed", 0) or 0),
        },
        "items": items,
        "compile_runs": compile_runs,
        "rewrite_generation": rewrite_generation_result,
        "rewrite_apply": rewrite_result,
    }


def _effective_content_limit(limit: int | None) -> int:
    try:
        parsed = int(limit) if limit is not None else 5
    except (TypeError, ValueError):
        parsed = 5
    return max(0, parsed)


def _generate_rewrite_candidates(root: Path, *, limit: int) -> dict[str, Any]:
    from .runner.workflows import run_compile

    if limit <= 0:
        return {
            "operation": "generate-concept-rewrite-proposals",
            "status": "skipped",
            "reason": "limit_zero",
            "counts": {"updated_concept_pages": 0, "generated_rewrite_proposals": 0, "failed": 0},
            "items": [],
        }
    slugs = _current_rewrite_debt_slugs(root)
    if not slugs:
        return {
            "operation": "generate-concept-rewrite-proposals",
            "status": "skipped",
            "reason": "no_rewrite_debt",
            "counts": {"updated_concept_pages": 0, "generated_rewrite_proposals": 0, "failed": 0},
            "items": [],
        }
    selected_slugs = slugs[:limit]
    paths = [f"wiki/concepts/{slug}.md" for slug in selected_slugs]
    try:
        result = run_compile(root, limit=limit, paths=paths)
    except Exception as exc:
        return {
            "operation": "generate-concept-rewrite-proposals",
            "status": "failed",
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "counts": {"updated_concept_pages": 0, "generated_rewrite_proposals": 0, "failed": 1},
            "items": [{"category": "rewrite_candidates", "status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)}}],
        }
    updated_concepts = list(result.get("updated_concept_pages", []) or [])
    generated = list(result.get("updated_rewrite_proposal_pages", []) or [])
    return {
        "operation": "generate-concept-rewrite-proposals",
        "status": "applied" if updated_concepts or generated else "noop",
        "counts": {
            "updated_concept_pages": len(updated_concepts),
            "generated_rewrite_proposals": len(generated),
            "failed": 0,
        },
        "selected_slugs": selected_slugs,
        "items": [
            {
                "category": "rewrite_candidates",
                "status": "generated",
                "refs": selected_slugs,
                "updated_concept_pages": updated_concepts,
                "updated_rewrite_proposal_pages": generated,
            }
        ],
        "compile": result,
    }


def _current_rewrite_debt_slugs(root: Path) -> list[str]:
    memory = load_machine_memory(root)
    health = memory.get("health", {}) if isinstance(memory.get("health"), dict) else {}
    quality = health.get("concept_quality", {}) if isinstance(health.get("concept_quality"), dict) else {}
    applied_rewrite_slugs = _current_applied_rewrite_slugs(root)
    slugs: list[str] = []
    for key in ("rewrite_candidates", "weak_concepts"):
        records = quality.get(key) if isinstance(quality.get(key), list) else []
        for record in records:
            if not isinstance(record, dict):
                continue
            slug = str(record.get("slug") or "").strip()
            if slug and slug not in slugs and slug not in applied_rewrite_slugs:
                slugs.append(slug)
    return slugs


def _auto_apply_concept_rewrite_proposals(root: Path, *, limit: int) -> dict[str, Any]:
    from .app_state import load_concept_rewrite_state
    from .content.memory import rewrite_proposal_candidate_is_current
    from .execution.concept_rewrite import apply_concept_rewrite, review_concept_rewrite

    state = load_concept_rewrite_state(root)
    proposals = [dict(item) for item in state.get("proposals", []) if isinstance(item, dict)]
    candidates = [
        proposal
        for proposal in proposals
        if bool(proposal.get("active", True))
        and str(proposal.get("status") or "proposed") in {"proposed", "accepted"}
    ]
    current_candidates: list[dict[str, Any]] = []
    skipped_candidates: list[dict[str, Any]] = []
    for proposal in candidates:
        slug = str(proposal.get("slug") or "")
        if slug and rewrite_proposal_candidate_is_current(root, proposal):
            current_candidates.append(proposal)
        else:
            skipped_candidates.append(proposal)
    if current_candidates:
        candidates = current_candidates[:limit] if limit >= 0 else current_candidates
    else:
        candidates = skipped_candidates[:limit] if limit >= 0 else skipped_candidates
    items: list[dict[str, Any]] = []
    counts = {"evaluated": len(candidates), "applied": 0, "skipped": 0, "failed": 0}
    for proposal in candidates:
        slug = str(proposal.get("slug") or "")
        item: dict[str, Any] = {"slug": slug, "status_before": str(proposal.get("status") or "proposed")}
        if not slug:
            item["operation"] = "skip"
            item["reason_code"] = "missing_slug"
            counts["skipped"] += 1
            items.append(item)
            continue
        if proposal not in current_candidates and not rewrite_proposal_candidate_is_current(root, proposal):
            item["operation"] = "skip"
            item["reason_code"] = "stale_or_invalid_candidate"
            counts["skipped"] += 1
            items.append(item)
            continue
        try:
            if str(proposal.get("status") or "proposed") == "proposed":
                item["review"] = review_concept_rewrite(
                    root,
                    slug,
                    "accepted",
                    note="debt-autopilot: accept current non-core concept rewrite",
                )
            item["apply"] = apply_concept_rewrite(
                root,
                slug,
                note="debt-autopilot: apply current non-core concept rewrite",
            )
            verification_status = str(
                (item.get("apply") if isinstance(item.get("apply"), dict) else {}).get("verification_status") or ""
            )
            if verification_status and verification_status != "passed":
                item["operation"] = "failed"
                item["reason_code"] = "verification_failed"
                item["status_after"] = "applied"
                counts["failed"] += 1
                items.append(item)
                continue
            item["operation"] = "apply"
            item["status_after"] = "applied"
            counts["applied"] += 1
        except Exception as exc:
            item["operation"] = "failed"
            item["error"] = {"type": type(exc).__name__, "message": str(exc)}
            counts["failed"] += 1
            items.append(item)
            continue
        items.append(item)
    return {
        "operation": "auto-apply-concept-rewrite-proposals",
        "counts": counts,
        "items": items,
    }


def _inventory_items(categories: dict[str, dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for category_name, category in categories.items():
        for ref in category.get("sample", []):
            items.append(
                {
                    "category": category_name,
                    "ref": ref,
                    "autonomy_boundary": category["autonomy_boundary"],
                    "apply_strategy": category["apply_strategy"],
                }
            )
            if len(items) >= limit:
                return items
    return items


__all__ = [
    "CORE_MANUAL_ONLY",
    "EXTERNAL_HUMAN_REQUIRED",
    "LLM_OWNED_NON_CORE",
    "MAINTENANCE",
    "collect_auto_adopt_work",
    "collect_debt_inventory",
    "run_debt_autopilot",
]
