"""Nightly auto-adoption of L1 / L2 governance backlog.

Extends the nightly agent loop beyond deterministic light-primitive apply
(compile / lint / nightly) into *semantic-candidate adoption*. The original
boundary kept L1 candidate-only and L2 gate-only; this module changes the
design so that 炼丹炉 can silently auto-adopt safe-category items by default.

Opt-in per level via env vars:
- ``AIWIKI_NIGHTLY_AUTO_ADOPT_L1=1`` — auto-adopt L1 semantic candidates
- ``AIWIKI_NIGHTLY_AUTO_ADOPT_L2=1`` — auto-adopt L2 machine-memory actions

Policy (deliberately permissive, aligned with 炼丹炉 philosophy):
  L1 — concept backlog / revisit / source-concept links / counter-evidence
  L2 — concept splits (deterministic overloaded-concept proposals)

Explicitly EXCLUDED from auto-adopt:
  L3 proposals — remain gate-only (prompt / policy changes)
  judgment_review_actions that require reading evidence chains
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..app_shell.controls import shell_execution_controls, shell_review_controls
from ..app_state import load_machine_memory, load_planner_state
from ..execution.lifecycle import review_concepts_batch
from ..execution.machine_memory_actions import review_machine_memory_actions_batch
from ..execution.machine_memory_batch import (
    apply_machine_memory_actions_batch,
    review_pages_batch,
)


def _build_controls(root: Path):
    """Load the review and execution control surfaces."""
    from ..app_compile import collect_aging_signals, review_queue
    from ..app_state import (
        DEFAULT_PROTOCOL,
        load_compile_state,
    )

    compile_state = load_compile_state(root)
    memory = load_machine_memory(root)
    planner_state = load_planner_state(root)
    decisions = compile_state.get("decisions", [])
    judgments = compile_state.get("judgments", [])
    active_protocol = str(planner_state.get("active_protocol") or DEFAULT_PROTOCOL)
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    counter_evidence_scan = memory.get("health", {}).get("counter_evidence_scan", {})
    judgment_review_actions = memory.get("health", {}).get("judgment_review_actions", [])
    review_ctrl = shell_review_controls(
        root,
        queue=queue,
        aging=aging,
        active_protocol=active_protocol,
        counter_evidence_scan=counter_evidence_scan if isinstance(counter_evidence_scan, dict) else {},
        review_actions=judgment_review_actions if isinstance(judgment_review_actions, list) else [],
    )
    exec_ctrl = shell_execution_controls(root, memory)
    return review_ctrl, exec_ctrl

_logger = logging.getLogger(__name__)

_L1_CONCEPT_STATUS = "active"
_L1_REVISIT_STATUS = "deferred"
_L1_COUNTER_EVIDENCE_STATUS = "tracking"
_L1_ACTION_STATUS = "accepted"
_L2_CONCEPT_SPLIT_STATUS = "accepted"


def _env_flag(name: str) -> bool:
    import os

    value = os.environ.get(name, "0")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def auto_adopt_l1(root: Path) -> dict[str, Any]:
    """Auto-adopt L1 semantic candidates.

    Covers: concept backlog, revisit concepts, counter-evidence pages,
    source-concept link actions.
    """
    results: dict[str, Any] = {"level": "L1", "applied": False, "items": []}
    try:
        review_ctrl, exec_ctrl = _build_controls(root)
    except Exception as exc:
        results["error"] = f"control surface unavailable: {exc}"
        return results

    # --- L1a: concept backlog → active ---
    concept_backlog = [
        item.get("slug", "")
        for item in review_ctrl.get("concept_backlog", [])
        if isinstance(item, dict) and item.get("slug")
    ]
    results["concept_backlog_pending"] = len(concept_backlog)
    if concept_backlog:
        try:
            r = review_concepts_batch(root, concept_backlog, status=_L1_CONCEPT_STATUS, note="nightly L1 auto-adopt: concept backlog → active")
            results["items"].append({"kind": "concept_backlog", "count": r.get("count", 0), "status": _L1_CONCEPT_STATUS})
        except Exception as exc:
            results["items"].append({"kind": "concept_backlog", "error": str(exc)})

    # --- L1b: revisit concepts → deferred ---
    revisit = [
        item.get("slug", "")
        for item in review_ctrl.get("revisit_concepts", [])
        if isinstance(item, dict) and item.get("slug")
    ]
    results["revisit_concepts_pending"] = len(revisit)
    if revisit:
        try:
            r = review_concepts_batch(root, revisit, status=_L1_REVISIT_STATUS, note="nightly L1 auto-adopt: revisit → deferred")
            results["items"].append({"kind": "revisit_concepts", "count": r.get("count", 0), "status": _L1_REVISIT_STATUS})
        except Exception as exc:
            results["items"].append({"kind": "revisit_concepts", "error": str(exc)})

    # --- L1c: counter-evidence candidates → tracking ---
    ce_pages = [
        p.get("path", "")
        for p in review_ctrl.get("counter_evidence_candidates", [])
        if isinstance(p, dict) and p.get("path")
    ]
    results["counter_evidence_pending"] = len(ce_pages)
    if ce_pages:
        try:
            r = review_pages_batch(root, ce_pages, status=_L1_COUNTER_EVIDENCE_STATUS, note="nightly L1 auto-adopt: counter-evidence → tracking")
            results["items"].append({"kind": "counter_evidence", "count": r.get("count", 0), "status": _L1_COUNTER_EVIDENCE_STATUS})
        except Exception as exc:
            results["items"].append({"kind": "counter_evidence", "error": str(exc)})

    # --- L1d: source-concept link actions → accepted + apply ---
    link_actions = [
        a.get("action_id", "")
        for a in exec_ctrl.get("actions", [])
        if isinstance(a, dict)
        and a.get("kind") == "add-source-concept-link"
        and a.get("status") == "proposed"
        and str(a.get("can_review", "")).lower() in {"true", "1", "yes"}
    ]
    link_actions = [aid for aid in link_actions if aid]
    results["source_concept_links_pending"] = len(link_actions)
    if link_actions:
        try:
            r = review_machine_memory_actions_batch(root, link_actions, status=_L1_ACTION_STATUS, note="nightly L1 auto-adopt: source-concept link accepted")
            results["items"].append({"kind": "source_concept_links", "status": _L1_ACTION_STATUS, "count": r.get("count", 0)})
        except Exception as exc:
            results["items"].append({"kind": "source_concept_links", "error": str(exc)})

    # Apply all accepted low-risk actions (covers the links we just accepted)
    apply_ids = [
        a.get("action_id", "")
        for a in exec_ctrl.get("actions", [])
        if isinstance(a, dict) and str(a.get("can_apply", "")).lower() in {"true", "1", "yes"}
    ]
    apply_ids = [aid for aid in apply_ids if aid]
    if apply_ids:
        try:
            r = apply_machine_memory_actions_batch(root, apply_ids, note="nightly L1 auto-adopt: apply accepted low-risk", dry_run=False)
            results["items"].append({"kind": "apply_accepted", "count": r.get("applied_count", r.get("count", 0))})
        except Exception as exc:
            results["items"].append({"kind": "apply_accepted", "error": str(exc)})

    applied = any(item.get("count", 0) > 0 for item in results["items"] if "count" in item)
    results["applied"] = applied
    return results


def auto_adopt_l2(root: Path) -> dict[str, Any]:
    """Auto-adopt L2 machine-memory actions (concept splits only).

    Concept splits are deterministic proposals from the overloaded-concept
    detector. They are low-risk structural changes.
    """
    results: dict[str, Any] = {"level": "L2", "applied": False, "items": []}
    try:
        _review_ctrl, exec_ctrl = _build_controls(root)
    except Exception as exc:
        results["error"] = f"execution control unavailable: {exc}"
        return results

    split_actions = [
        a.get("action_id", "")
        for a in exec_ctrl.get("actions", [])
        if isinstance(a, dict)
        and a.get("kind") == "split-overloaded-concept"
        and a.get("status") == "proposed"
        and str(a.get("can_review", "")).lower() in {"true", "1", "yes"}
    ]
    results["concept_splits_pending"] = len(split_actions)
    if split_actions:
        try:
            r = review_machine_memory_actions_batch(root, split_actions, status=_L2_CONCEPT_SPLIT_STATUS, note="nightly L2 auto-adopt: concept split accepted")
            results["items"].append({"kind": "concept_splits_accepted", "count": r.get("count", 0)})
        except Exception as exc:
            results["items"].append({"kind": "concept_splits_accepted", "error": str(exc)})

    # Apply accepted splits
    apply_ids = [
        a.get("action_id", "")
        for a in exec_ctrl.get("actions", [])
        if isinstance(a, dict) and a.get("kind") == "split-overloaded-concept" and str(a.get("can_apply", "")).lower() in {"true", "1", "yes"}
    ]
    if apply_ids:
        try:
            r = apply_machine_memory_actions_batch(root, apply_ids, note="nightly L2 auto-adopt: apply concept splits", dry_run=False)
            results["items"].append({"kind": "concept_splits_applied", "count": r.get("applied_count", r.get("count", 0))})
        except Exception as exc:
            results["items"].append({"kind": "concept_splits_applied", "error": str(exc)})

    applied = any(item.get("count", 0) > 0 for item in results["items"] if "count" in item)
    results["applied"] = applied
    return results


__all__ = ["auto_adopt_l1", "auto_adopt_l2", "_env_flag"]
