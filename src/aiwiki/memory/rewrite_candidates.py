"""Concept rewrite proposal candidate persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..content.concepts import concept_page_snapshot
from ..content.rewrite import load_concept_rewrite_state, save_concept_rewrite_state
from ..execution.repair_plan import rewrite_proposal_is_apply_ready
from ..lifecycle.status import rewrite_proposal_needs_review
from ..protocol.scaffold import ensure_layout
from ..utils.io import write_if_changed
from ..utils.path import relative_path
from .execution_surfaces import (
    concept_rewrite_proposal_digest,
    render_concept_rewrite_proposal_page,
)
from .paths import concept_rewrite_proposal_page_path


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
        target["last_applied_at"] = ""
        target["reverted_at"] = ""
        target["revert_note"] = ""
        target["previous_markdown"] = ""
        target["previous_digest"] = ""
        target["verification_status"] = ""
        target["verification_checked_at"] = ""
        target["verification_summary"] = ""
        target["verification_issues"] = []
    target.update(
        {
            "title": str(quality_record.get("title") or snapshot.get("title") or slug),
            "priority": str(quality_record.get("priority") or "medium"),
            "score": int(quality_record.get("score") or 0),
            "quality_score": int(quality_record.get("quality_score") or 0),
            "quality_band": str(quality_record.get("quality_band") or ""),
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
    target["pending_review"] = (
        "true" if rewrite_proposal_needs_review(str(target.get("status") or "proposed")) else "false"
    )
    target["apply_ready"] = rewrite_proposal_is_apply_ready(root, target)
    save_concept_rewrite_state(root, {"version": 1, "proposals": proposals})
    write_if_changed(root / str(target["proposal_path"]), render_concept_rewrite_proposal_page(target))
    return {
        "slug": slug,
        "proposal_path": str(target["proposal_path"]),
        "status": str(target.get("status") or "proposed"),
        "candidate_digest": digest,
    }
