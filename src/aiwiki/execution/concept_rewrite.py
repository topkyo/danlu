"""EP-018B group 5 (B5): concept rewrite execution owner.

Migrated out of ``aiwiki.app_compile`` on 2026-04-23. Contains the full
concept-rewrite lifecycle: load/find/save proposal state (``_load_*`` /
``_find_*`` / ``_save_*``), verification evaluation and persistence
(``_evaluate_*`` / ``_persist_*``), and the four user-facing write
operations (``review_concept_rewrite`` / ``apply_concept_rewrite`` /
``verify_concept_rewrite`` / ``revert_concept_rewrite``).

Design notes:

- All imports go to the TRUE origin module, never through ``app_compile``
  re-exports (``compile_wiki`` uses ``..compile.pipeline`` and not
  ``..compile`` per B4 oracle review).
- The five hot-patch targets (``utc_now``, ``entry_concept_terms``,
  ``build_machine_memory``, ``build_ranking_source_record``,
  ``build_ranking_concept_record``) stay directly bound in
  ``aiwiki.app_compile``. For the one B5 actually calls (``utc_now``),
  we use function-body lazy lookup
  (``from .. import app_compile as _app_compile; _app_compile.utc_now()``)
  so that ``patch("aiwiki.app_compile.utc_now")`` in tests continues to
  take effect.
- ``append_wiki_log`` is duplicated in ``app_content.py`` and
  ``app_render.py``. ``app_content.py`` imports the ``app_render`` copy
  at module load and re-binds its own ``append_wiki_log`` to it, so
  the runtime-effective origin is ``app_render``. We import from
  ``app_render`` directly (same choice as B2) to keep the true-origin
  discipline. Converging the duplicate definitions in source is
  pre-existing tech debt and out of B5 scope; B3 / B4 still route
  through ``app_content`` and should be realigned in a follow-up.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_content import (
    _validate_rewrite_candidate_markdown,
    preserved_section,
    rewrite_proposal_candidate_is_current,
    rewrite_proposal_is_apply_ready,
)
from ..app_execution import write_execution_dry_run_document
from ..app_lifecycle import rewrite_proposal_needs_review
from ..app_memory_query import concept_page_snapshot
from ..app_memory_surfaces import concept_rewrite_proposal_digest
from ..app_protocol import REWRITE_PROPOSAL_STATUSES, ensure_layout
from ..app_render import append_wiki_log
from ..app_state import (
    append_runtime_history,
    load_concept_rewrite_state,
    load_machine_memory,
    rewrite_dry_run_path,
    save_concept_rewrite_state,
)
from ..app_utils import parse_frontmatter, relative_path, runtime_write_operation
from ..compile.pipeline import compile_wiki


def _load_concept_rewrite_proposals(root: Path) -> list[dict[str, Any]]:
    state = load_concept_rewrite_state(root)
    return [dict(proposal) for proposal in state.get("proposals", []) if isinstance(proposal, dict)]


def _find_concept_rewrite_proposal(proposals: list[dict[str, Any]], slug: str) -> dict[str, Any]:
    for proposal in proposals:
        if str(proposal.get("slug") or "") == slug:
            return proposal
    raise FileNotFoundError(f"Concept rewrite proposal not found: {slug}")


def _save_concept_rewrite_proposals(root: Path, proposals: list[dict[str, Any]]) -> None:
    save_concept_rewrite_state(root, {"version": 1, "proposals": proposals})


def _evaluate_concept_rewrite_verification(root: Path, proposal: dict[str, Any]) -> dict[str, Any]:
    # Lazy-resolve ``utc_now`` via ``app_compile`` so ``tests/test_app.py``'s
    # ``patch("aiwiki.app_compile.utc_now", ...)`` sites still take effect on
    # this migrated function. Module-level ``from ..app_utils import utc_now``
    # would bind the original callable at import time and bypass the patch.
    from .. import app_compile as _app_compile

    slug = str(proposal.get("slug") or "")
    target_path = str(proposal.get("target_path") or f"wiki/concepts/{slug}.md")
    expected_source_signature = str(proposal.get("source_signature") or "")
    expected_source_pages = sorted(
        str(item)
        for item in proposal.get("source_pages", [])
        if isinstance(item, str) and item
    )
    candidate_summary = preserved_section(str(proposal.get("candidate_markdown") or ""), "Summary", "").strip()
    snapshot = concept_page_snapshot(root, slug)
    issues: list[str] = []
    if not snapshot.get("content"):
        issues.append("missing-concept-page")
    else:
        content = str(snapshot.get("content") or "")
        frontmatter = parse_frontmatter(content)
        if str(frontmatter.get("id") or "") != f"concept-{slug}":
            issues.append("concept-id-drift")
        if str(frontmatter.get("kind") or "") != "concept":
            issues.append("concept-kind-drift")
        if expected_source_signature and str(frontmatter.get("source_signature") or "") != expected_source_signature:
            issues.append("source-signature-drift")
        current_source_pages = sorted(
            str(item)
            for item in frontmatter.get("source_pages", [])
            if isinstance(item, str) and item
        )
        if current_source_pages != expected_source_pages:
            issues.append("source-pages-drift")
        current_summary = str(snapshot.get("summary") or "").strip()
        if candidate_summary and current_summary != candidate_summary:
            issues.append("summary-not-applied")

    memory = load_machine_memory(root)
    concept_node = next(
        (
            node
            for node in memory.get("concept_nodes", [])
            if isinstance(node, dict) and str(node.get("slug") or "") == slug
        ),
        None,
    )
    if concept_node is None:
        issues.append("missing-machine-memory-node")
    else:
        node_source_pages = sorted(
            str(item)
            for item in concept_node.get("source_pages", [])
            if isinstance(item, str) and item
        )
        if node_source_pages != expected_source_pages:
            issues.append("machine-memory-source-drift")
    quality_state = memory.get("health", {}).get("concept_quality", {})
    quality_record = next(
        (
            record
            for record in quality_state.get("all_concepts", [])
            if isinstance(record, dict) and str(record.get("slug") or "") == slug
        ),
        None,
    )
    if quality_record is None:
        issues.append("missing-quality-record")
    verification_status = "passed" if not issues else "failed"
    verification_summary = (
        "Concept page summary, source signature, machine memory node, and quality record all match the applied rewrite."
        if verification_status == "passed"
        else "Verification detected drift between the applied rewrite and current concept/runtime state."
    )
    return {
        "slug": slug,
        "target_path": target_path,
        "status": verification_status,
        "checked_at": _app_compile.utc_now(),
        "summary": verification_summary,
        "issues": issues,
        "quality_score": int(quality_record.get("quality_score", 0)) if isinstance(quality_record, dict) else 0,
        "quality_state": str(quality_record.get("quality_state") or "") if isinstance(quality_record, dict) else "",
    }


def _persist_concept_rewrite_verification(
    root: Path,
    slug: str,
    *,
    note: str | None = None,
    compile_after: bool,
) -> dict[str, Any]:
    ensure_layout(root)
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if str(target.get("status") or "") != "applied":
        raise RuntimeError("Concept rewrite proposal must be applied before verify.")
    verification = _evaluate_concept_rewrite_verification(root, target)
    target["verification_status"] = verification["status"]
    target["verification_checked_at"] = verification["checked_at"]
    target["verification_summary"] = verification["summary"]
    target["verification_issues"] = list(verification["issues"])
    _save_concept_rewrite_proposals(root, proposals)
    append_runtime_history(
        root,
        {
            "event_type": "rewrite-verify",
            "occurred_at": str(verification["checked_at"] or ""),
            "slug": slug,
            "target_path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            "status": str(verification["status"] or ""),
            "issues": list(verification["issues"]),
            "quality_score": int(verification.get("quality_score", 0) or 0),
            "quality_state": str(verification.get("quality_state") or ""),
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "rewrite-verify",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"target: `{target.get('target_path', '')}`",
            f"status: `{verification['status']}`",
            f"issues: `{', '.join(verification['issues']) or 'none'}`",
        ],
    )
    if compile_after:
        compile_wiki(root)
    return verification


@runtime_write_operation
def review_concept_rewrite(
    root: Path,
    slug: str,
    status: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    from .. import app_compile as _app_compile

    ensure_layout(root)
    if status not in REWRITE_PROPOSAL_STATUSES:
        raise ValueError(f"Unsupported concept rewrite status: {status}")
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if status == "accepted" and not rewrite_proposal_candidate_is_current(root, target):
        raise RuntimeError("Concept rewrite proposal candidate is stale or invalid. Run run-compile again before accepting.")
    reviewed_at = _app_compile.utc_now()
    target["status"] = status
    target["reviewed_at"] = reviewed_at
    target["review_note"] = note or ""
    target["pending_review"] = "true" if rewrite_proposal_needs_review(status) else "false"
    target["apply_ready"] = rewrite_proposal_is_apply_ready(root, target)
    if status != "applied":
        target["applied_at"] = str(target.get("applied_at") or "")
    _save_concept_rewrite_proposals(root, proposals)
    append_runtime_history(
        root,
        {
            "event_type": "rewrite-review",
            "occurred_at": reviewed_at,
            "slug": slug,
            "target_path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            "status": status,
            "priority": str(target.get("priority") or ""),
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "rewrite-review",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"status: `{status}`",
            f"target: `{target.get('target_path', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "slug": slug,
        "status": status,
        "reviewed_at": reviewed_at,
        "apply_ready": bool(target.get("apply_ready", False)),
    }


@runtime_write_operation
def apply_concept_rewrite(
    root: Path,
    slug: str,
    *,
    note: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    from .. import app_compile as _app_compile

    ensure_layout(root)
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if str(target.get("status") or "") != "accepted":
        raise RuntimeError("Concept rewrite proposal must be accepted before apply.")
    candidate_markdown = str(target.get("candidate_markdown") or "")
    if not candidate_markdown:
        raise RuntimeError("Concept rewrite proposal has no candidate markdown to apply.")
    concept_path = root / str(target.get("target_path") or f"wiki/concepts/{slug}.md")
    if not concept_path.exists():
        raise FileNotFoundError(f"Concept page not found: {concept_path}")
    current_frontmatter = parse_frontmatter(concept_path.read_text(encoding="utf-8", errors="replace"))
    current_source_signature = str(current_frontmatter.get("source_signature") or "")
    expected_source_signature = str(target.get("source_signature") or "")
    if expected_source_signature and current_source_signature != expected_source_signature:
        raise RuntimeError("Concept page changed since this rewrite proposal was generated.")
    current_source_pages = current_frontmatter.get("source_pages", [])
    if not isinstance(current_source_pages, list):
        current_source_pages = []
    normalized_source_pages = [str(item) for item in current_source_pages if isinstance(item, str)]
    _validate_rewrite_candidate_markdown(
        candidate_markdown,
        slug,
        expected_source_signature,
        normalized_source_pages,
    )
    if dry_run:
        previewed_at = _app_compile.utc_now()
        current_markdown = concept_path.read_text(encoding="utf-8", errors="replace")
        dry_run_path = rewrite_dry_run_path(root, slug)
        payload = {
            "version": 1,
            "kind": "rewrite-dry-run",
            "generated_by": "aiwiki-apply-rewrite",
            "generated_at": previewed_at,
            "slug": slug,
            "title": str(target.get("title") or slug),
            "status": str(target.get("status") or "accepted"),
            "target_path": relative_path(root, concept_path),
            "proposal_path": str(target.get("proposal_path") or ""),
            "source_signature": expected_source_signature,
            "candidate_digest": concept_rewrite_proposal_digest(candidate_markdown),
            "current_digest": concept_rewrite_proposal_digest(current_markdown),
            "summary_before": preserved_section(current_markdown, "Summary", "").strip(),
            "summary_after": preserved_section(candidate_markdown, "Summary", "").strip(),
            "candidate_markdown": candidate_markdown,
        }
        write_execution_dry_run_document(dry_run_path, payload)
        append_runtime_history(
            root,
            {
                "event_type": "rewrite-dry-run",
                "occurred_at": previewed_at,
                "slug": slug,
                "target_path": relative_path(root, concept_path),
                "proposal_path": str(target.get("proposal_path") or ""),
                "status": "accepted",
                "note": note or "",
            },
        )
        append_wiki_log(
            root,
            "rewrite-dry-run",
            str(target.get("title") or slug),
            [
                f"slug: `{slug}`",
                f"target: `{relative_path(root, concept_path)}`",
                f"preview: `{relative_path(root, dry_run_path)}`",
            ],
        )
        return {
            "slug": slug,
            "status": str(target.get("status") or "accepted"),
            "dry_run": True,
            "dry_run_path": relative_path(root, dry_run_path),
            "path": relative_path(root, concept_path),
        }
    previous_snapshot = concept_page_snapshot(root, slug)
    concept_path.write_text(candidate_markdown.strip() + "\n", encoding="utf-8")
    applied_at = _app_compile.utc_now()
    target["status"] = "applied"
    target["applied_at"] = applied_at
    target["last_applied_at"] = applied_at
    target["reverted_at"] = ""
    target["revert_note"] = ""
    target["reviewed_at"] = applied_at
    target["review_note"] = note or "Applied accepted rewrite proposal."
    target["pending_review"] = "false"
    target["apply_ready"] = False
    target["previous_markdown"] = str(previous_snapshot.get("content") or "")
    target["previous_digest"] = concept_rewrite_proposal_digest(str(previous_snapshot.get("content") or ""))
    target["verification_status"] = "pending"
    target["verification_checked_at"] = ""
    target["verification_summary"] = ""
    target["verification_issues"] = []
    _save_concept_rewrite_proposals(root, proposals)
    append_wiki_log(
        root,
        "rewrite-apply",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"target: `{target.get('target_path', '')}`",
            f"proposal_path: `{target.get('proposal_path', '')}`",
        ],
    )
    compile_wiki(root)
    verification = _persist_concept_rewrite_verification(
        root,
        slug,
        note="Automatic verification after apply.",
        compile_after=False,
    )
    append_runtime_history(
        root,
        {
            "event_type": "rewrite-apply",
            "occurred_at": applied_at,
            "slug": slug,
            "target_path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            "proposal_path": str(target.get("proposal_path") or ""),
            "source_signature": expected_source_signature,
            "status": "applied",
            "verification_status": str(verification.get("status") or ""),
            "verification_issues": list(verification.get("issues", [])),
            "note": note or "",
        },
    )
    compile_wiki(root)
    return {
        "slug": slug,
        "status": "applied",
        "applied_at": applied_at,
        "path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
        "verification_status": str(verification.get("status") or ""),
    }


@runtime_write_operation
def verify_concept_rewrite(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    verification = _persist_concept_rewrite_verification(
        root,
        slug,
        note=note or "Manual verification requested.",
        compile_after=True,
    )
    return {
        "slug": slug,
        "status": str(verification.get("status") or ""),
        "checked_at": str(verification.get("checked_at") or ""),
        "issues": list(verification.get("issues", [])),
    }


@runtime_write_operation
def revert_concept_rewrite(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    from .. import app_compile as _app_compile

    ensure_layout(root)
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if str(target.get("status") or "") != "applied":
        raise RuntimeError("Concept rewrite proposal has not been applied.")
    previous_markdown = str(target.get("previous_markdown") or "")
    if not previous_markdown:
        raise RuntimeError("Concept rewrite proposal has no previous concept snapshot to restore.")
    candidate_summary = preserved_section(str(target.get("candidate_markdown") or ""), "Summary", "").strip()
    current_summary = concept_page_snapshot(root, slug).get("summary", "").strip()
    if candidate_summary and current_summary != candidate_summary:
        raise RuntimeError("Only the latest applied rewrite can be reverted.")
    concept_path = root / str(target.get("target_path") or f"wiki/concepts/{slug}.md")
    if not concept_path.exists():
        raise FileNotFoundError(f"Concept page not found: {concept_path}")
    concept_path.write_text(previous_markdown.strip() + "\n", encoding="utf-8")
    reverted_at = _app_compile.utc_now()
    target["status"] = "accepted"
    target["reviewed_at"] = reverted_at
    target["review_note"] = note or "Reverted applied rewrite proposal."
    target["pending_review"] = "true" if rewrite_proposal_needs_review("accepted") else "false"
    target["applied_at"] = ""
    target["reverted_at"] = reverted_at
    target["revert_note"] = note or "Reverted applied rewrite proposal."
    target["verification_status"] = ""
    target["verification_checked_at"] = ""
    target["verification_summary"] = ""
    target["verification_issues"] = []
    target["apply_ready"] = rewrite_proposal_is_apply_ready(root, target)
    _save_concept_rewrite_proposals(root, proposals)
    append_runtime_history(
        root,
        {
            "event_type": "rewrite-revert",
            "occurred_at": reverted_at,
            "slug": slug,
            "target_path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            "status": "accepted",
            "last_applied_at": str(target.get("last_applied_at") or ""),
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "rewrite-revert",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"target: `{target.get('target_path', '')}`",
            "status: `accepted`",
        ],
    )
    compile_wiki(root)
    return {
        "slug": slug,
        "status": "accepted",
        "reverted_at": reverted_at,
        "path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
    }
