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
- The hot-patch target ``utc_now`` is owned by ``aiwiki.utils.time``;
  we use function-body lazy lookup
  (``from ..utils.time import utc_now; utc_now()``)
  so that ``patch("aiwiki.utils.time.utc_now")`` in tests continues to
  take effect. The other ranking helpers (``build_ranking_source_record``,
  ``build_ranking_concept_record``) are now owned by
  ``aiwiki.compile.ranking``.
- ``append_wiki_log`` comes from ``render.paths``. Owner modules should
  use the direct origin.
"""

from __future__ import annotations

import contextlib
import logging
import re
from pathlib import Path
from typing import Any

from ..compile.pipeline import compile_wiki
from ..content.concepts import concept_page_snapshot
from ..content.io import preserved_section
from ..content.rewrite import load_concept_rewrite_state, save_concept_rewrite_state
from ..execution.receipts import write_execution_dry_run_document
from ..lifecycle.status import rewrite_proposal_needs_review
from ..memory.execution_surfaces import concept_rewrite_proposal_digest
from ..memory.paths import concept_rewrite_state_path
from ..memory.state import load_machine_memory
from ..protocol.runtime_config import REWRITE_PROPOSAL_STATUSES
from ..protocol.scaffold import ensure_layout
from ..render.paths import append_wiki_log
from ..utils.hash import sha256_bytes
from ..utils.io import _restore_snapshots, _snapshot_file_bytes, atomic_write_text, runtime_write_operation
from ..utils.markdown import parse_frontmatter
from ..utils.path import relative_path
from .audit_preview import AUDIT_STREAM_PATH
from .history import append_runtime_history
from .paths import (
    execution_receipt_history_path,
    rewrite_dry_run_path,
    runtime_history_path,
)
from .receipts import write_execution_receipt
from .repair_plan import (
    _validate_rewrite_candidate_markdown,
    rewrite_proposal_candidate_is_current,
    rewrite_proposal_is_apply_ready,
)

logger = logging.getLogger(__name__)

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_MARKDOWN_LOCAL_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_RENDERED_LOCAL_LINK_RE = re.compile(r"`([^`]+)`\s*[（(]\s*`([^`]+)`\s*[）)]")


def _load_concept_rewrite_proposals(root: Path) -> list[dict[str, Any]]:
    state = load_concept_rewrite_state(root)
    return [dict(proposal) for proposal in state.get("proposals", []) if isinstance(proposal, dict)]


def _find_concept_rewrite_proposal(proposals: list[dict[str, Any]], slug: str) -> dict[str, Any]:
    for proposal in proposals:
        if str(proposal.get("slug") or "") == slug:
            return proposal
    raise FileNotFoundError(f"Concept rewrite proposal not found: {slug}")


def _hash_bytes(content: bytes) -> str:
    return sha256_bytes(content)


def _rewrite_source_provenance(target: dict[str, Any], *, source_signature: str) -> dict[str, Any]:
    source_pages = target.get("source_pages")
    if not isinstance(source_pages, list):
        source_pages = []
    return {
        "proposal_path": str(target.get("proposal_path") or ""),
        "source_signature": source_signature,
        "source_pages": [str(item) for item in source_pages if str(item).strip()],
    }


def _concept_rewrite_transaction_snapshots(root: Path, concept_path: Path) -> dict[Path, bytes | None]:
    return {
        concept_path: _snapshot_file_bytes(concept_path),
        concept_rewrite_state_path(root): _snapshot_file_bytes(concept_rewrite_state_path(root)),
        runtime_history_path(root): _snapshot_file_bytes(runtime_history_path(root)),
        root / "wiki" / "indexes" / "log.md": _snapshot_file_bytes(root / "wiki" / "indexes" / "log.md"),
        execution_receipt_history_path(root): _snapshot_file_bytes(execution_receipt_history_path(root)),
        root / AUDIT_STREAM_PATH: _snapshot_file_bytes(root / AUDIT_STREAM_PATH),
    }


def _rollback_concept_rewrite_transaction(
    root: Path,
    snapshots: dict[Path, bytes | None],
    *,
    receipt: dict[str, Any] | None,
) -> None:
    if receipt:
        receipt_path = str(receipt.get("receipt_path") or "")
        if receipt_path:
            with contextlib.suppress(FileNotFoundError):
                (root / receipt_path).unlink()
    _restore_snapshots(snapshots)


def _write_concept_rewrite_apply_receipt(
    root: Path,
    *,
    slug: str,
    target: dict[str, Any],
    previous_content_bytes: bytes,
    new_content: str,
    expected_source_signature: str,
    verification_status: str,
    status: str = "success",
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extra = {
        "domain": "non_core_semantic",
        "target_paths": [
            str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            str(target.get("proposal_path") or ""),
        ],
        "before_hash": _hash_bytes(previous_content_bytes),
        "after_hash": _hash_bytes(new_content.encode("utf-8")),
        "source_provenance": _rewrite_source_provenance(
            target,
            source_signature=expected_source_signature,
        ),
        "llm_receipt_id": str(target.get("llm_receipt_id") or ""),
        "llm_receipt_ref": target.get("llm_receipt_ref") if isinstance(target.get("llm_receipt_ref"), dict) else {},
        "autonomy_decision": {
            "autonomy_domain": "non_core_semantic",
            "execution_strategy": "semantic_apply",
            "llm_governed": bool(target.get("llm_governed", False)),
        },
        "revert_ref": f"concept_rewrite:{slug}",
        "verification_status": verification_status,
    }
    if extra_fields:
        extra.update(extra_fields)
    return write_execution_receipt(
        root,
        operation="apply",
        generated_by="aiwiki-apply-rewrite",
        subject_kind="concept_rewrite",
        subject_id=slug,
        target_file=str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
        primary_path=str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
        status=status,
        revert_supported=True,
        extra=extra,
    )


def _canonical_markdown_path_for_summary(path: str) -> str:
    text = path.strip()
    while text.endswith(".md.md"):
        text = text[:-3]
    if text.startswith("wiki/") and not text.endswith(".md"):
        text = f"{text}.md"
    return text


def _is_local_markdown_ref(path: str) -> bool:
    text = path.strip()
    if not text or "://" in text or text.startswith(("mailto:", "#")):
        return False
    return (
        text.startswith(("wiki/", "raw/", "../", "./"))
        or text.endswith(".md")
        or text.endswith(".jpeg")
        or text.endswith(".jpg")
        or text.endswith(".png")
    )


def _normalize_rewrite_summary_for_verification(summary: str) -> str:
    def replace_wikilink(match: re.Match[str]) -> str:
        path = _canonical_markdown_path_for_summary(match.group(1))
        alias = str(match.group(2) or Path(path).name).strip()
        return f"{alias} <{path}>"

    def replace_markdown_link(match: re.Match[str]) -> str:
        path = _canonical_markdown_path_for_summary(match.group(2))
        if not _is_local_markdown_ref(path):
            return match.group(0)
        alias = match.group(1).strip()
        return f"{alias} <{path}>"

    def replace_rendered_link(match: re.Match[str]) -> str:
        alias = match.group(1).strip()
        path = _canonical_markdown_path_for_summary(match.group(2))
        if not _is_local_markdown_ref(path):
            return match.group(0)
        return f"{alias} <{path}>"

    normalized = _WIKILINK_RE.sub(replace_wikilink, summary.strip())
    normalized = _MARKDOWN_LOCAL_LINK_RE.sub(replace_markdown_link, normalized)
    normalized = _RENDERED_LOCAL_LINK_RE.sub(replace_rendered_link, normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = "\n".join(line.strip() for line in normalized.splitlines())
    return normalized.strip()


def _rewrite_summaries_match(candidate_summary: str, current_summary: str) -> bool:
    return _normalize_rewrite_summary_for_verification(
        candidate_summary
    ) == _normalize_rewrite_summary_for_verification(current_summary)


def _save_concept_rewrite_proposals(root: Path, proposals: list[dict[str, Any]]) -> None:
    save_concept_rewrite_state(root, {"version": 1, "proposals": proposals})


def _evaluate_concept_rewrite_verification(root: Path, proposal: dict[str, Any]) -> dict[str, Any]:
    # Lazy-resolve ``utc_now`` via ``app_compile`` so that any
    # ``patch("aiwiki.utils.time.utc_now", ...)`` monkeypatch sites
    # (acceptance tests including test_acceptance_loop's _copy_case_and_fix_clock_from
    # and downstream suites) still take effect on this migrated function.
    # Module-level ``from ..utils.time import utc_now`` would bind the
    # original callable at import time and bypass the patch.
    from ..utils.time import utc_now

    slug = str(proposal.get("slug") or "")
    target_path = str(proposal.get("target_path") or f"wiki/concepts/{slug}.md")
    expected_source_signature = str(proposal.get("source_signature") or "")
    expected_source_pages = sorted(
        str(item) for item in proposal.get("source_pages", []) if isinstance(item, str) and item
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
            str(item) for item in frontmatter.get("source_pages", []) if isinstance(item, str) and item
        )
        if current_source_pages != expected_source_pages:
            issues.append("source-pages-drift")
        current_summary = str(snapshot.get("summary") or "").strip()
        if candidate_summary and not _rewrite_summaries_match(candidate_summary, current_summary):
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
            str(item) for item in concept_node.get("source_pages", []) if isinstance(item, str) and item
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
        "checked_at": utc_now(),
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
    from ..utils.time import utc_now

    ensure_layout(root)
    if status not in REWRITE_PROPOSAL_STATUSES:
        raise ValueError(
            f"Unsupported concept rewrite status: {status!r}; expected one of: {REWRITE_PROPOSAL_STATUSES}"
        )
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if status == "accepted" and not rewrite_proposal_candidate_is_current(root, target):
        raise RuntimeError(
            "Concept rewrite proposal candidate is stale or invalid. Run run-compile again before accepting."
        )
    reviewed_at = utc_now()
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
    from ..utils.time import utc_now

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
        previewed_at = utc_now()
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
    # R94.4: capture current bytes BEFORE overwriting concept page so we can
    # roll back if anything in the critical section (forward write through
    # state save) fails. concept_path is guaranteed to exist (checked above).
    previous_content_bytes = concept_path.read_bytes()
    new_content = candidate_markdown.strip() + "\n"
    transaction_snapshots = _concept_rewrite_transaction_snapshots(root, concept_path)
    receipt: dict[str, Any] | None = None
    try:
        atomic_write_text(concept_path, new_content)
        applied_at = utc_now()
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
    except BaseException:
        # R94.4: critical-section failure after forward write — restore the
        # concept file via byte-level atomic write so non-UTF-8 bytes survive.
        # Inner except is BaseException so a rollback-time KeyboardInterrupt
        # does not mask the original error; rollback failure is logged but
        # never re-raised in lieu of the original.
        try:
            _rollback_concept_rewrite_transaction(root, transaction_snapshots, receipt=receipt)
        except BaseException as rollback_exc:
            logger.warning(
                "concept rewrite apply rollback failed for %s: %s (%s)",
                concept_path,
                rollback_exc,
                type(rollback_exc).__name__,
            )
        raise
    post_state_phase = "wiki_log"
    try:
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
        post_state_phase = "compile"
        compile_wiki(root)
    except Exception as post_state_error:
        verification_status = f"{post_state_phase}_failed"
        try:
            receipt = _write_concept_rewrite_apply_receipt(
                root,
                slug=slug,
                target=target,
                previous_content_bytes=previous_content_bytes,
                new_content=new_content,
                expected_source_signature=expected_source_signature,
                verification_status=verification_status,
                status="partial",
                extra_fields={
                    "failure_phase": post_state_phase,
                    "failure_error": str(post_state_error),
                },
            )
        except Exception:
            try:
                _rollback_concept_rewrite_transaction(root, transaction_snapshots, receipt=receipt)
            except Exception as rollback_error:
                raise RuntimeError(
                    f"concept rewrite apply rollback failed for {relative_path(root, concept_path)}: "
                    f"transaction_error={post_state_error!r}; rollback_error={rollback_error!r}"
                ) from rollback_error
        raise
    try:
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
        receipt = _write_concept_rewrite_apply_receipt(
            root,
            slug=slug,
            target=target,
            previous_content_bytes=previous_content_bytes,
            new_content=new_content,
            expected_source_signature=expected_source_signature,
            verification_status=str(verification.get("status") or ""),
        )
        compile_wiki(root)
    except Exception as transaction_error:
        try:
            _rollback_concept_rewrite_transaction(root, transaction_snapshots, receipt=receipt)
        except Exception as rollback_error:
            raise RuntimeError(
                f"concept rewrite apply rollback failed for {relative_path(root, concept_path)}: "
                f"transaction_error={transaction_error!r}; rollback_error={rollback_error!r}"
            ) from rollback_error
        raise
    return {
        "slug": slug,
        "status": "applied",
        "applied_at": applied_at,
        "path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
        "verification_status": str(verification.get("status") or ""),
        "receipt_path": str(receipt.get("receipt_path") or ""),
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
    from ..utils.time import utc_now

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
    if candidate_summary and not _rewrite_summaries_match(candidate_summary, current_summary):
        raise RuntimeError("Only the latest applied rewrite can be reverted.")
    concept_path = root / str(target.get("target_path") or f"wiki/concepts/{slug}.md")
    if not concept_path.exists():
        raise FileNotFoundError(f"Concept page not found: {concept_path}")
    # R94.4: snapshot current bytes (the candidate that was applied) so we can
    # roll back the file if anything in the critical section fails halfway.
    previous_content_bytes = concept_path.read_bytes()
    transaction_snapshots = _concept_rewrite_transaction_snapshots(root, concept_path)
    receipt: dict[str, Any] | None = None
    try:
        atomic_write_text(concept_path, previous_markdown.strip() + "\n")
        reverted_at = utc_now()
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
    except BaseException:
        # R94.4: critical-section failure after forward write — restore the
        # candidate bytes so the proposal still reflects an applied state and
        # can be retried. See apply path for rationale on rollback shape.
        try:
            _rollback_concept_rewrite_transaction(root, transaction_snapshots, receipt=receipt)
        except BaseException as rollback_exc:
            logger.warning(
                "concept rewrite revert rollback failed for %s: %s (%s)",
                concept_path,
                rollback_exc,
                type(rollback_exc).__name__,
            )
        raise
    try:
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
        receipt = write_execution_receipt(
            root,
            operation="revert",
            generated_by="aiwiki-revert-rewrite",
            subject_kind="concept_rewrite",
            subject_id=slug,
            target_file=str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            primary_path=str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            revert_supported=False,
            extra={
                "domain": "non_core_semantic",
                "target_paths": [
                    str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
                    str(target.get("proposal_path") or ""),
                ],
                "before_hash": _hash_bytes(previous_content_bytes),
                "after_hash": _hash_bytes(previous_markdown.strip().encode("utf-8") + b"\n"),
                "source_provenance": _rewrite_source_provenance(
                    target,
                    source_signature=str(target.get("source_signature") or ""),
                ),
                "llm_receipt_id": str(target.get("llm_receipt_id") or ""),
                "llm_receipt_ref": target.get("llm_receipt_ref")
                if isinstance(target.get("llm_receipt_ref"), dict)
                else {},
                "autonomy_decision": {
                    "autonomy_domain": "non_core_semantic",
                    "execution_strategy": "semantic_revert",
                    "llm_governed": bool(target.get("llm_governed", False)),
                },
                "revert_ref": f"concept_rewrite:{slug}:last_applied_at:{str(target.get('last_applied_at') or '')}",
            },
        )
        compile_wiki(root)
    except Exception as transaction_error:
        try:
            _rollback_concept_rewrite_transaction(root, transaction_snapshots, receipt=receipt)
        except Exception as rollback_error:
            raise RuntimeError(
                f"concept rewrite revert rollback failed for {relative_path(root, concept_path)}: "
                f"transaction_error={transaction_error!r}; rollback_error={rollback_error!r}"
            ) from rollback_error
        raise
    return {
        "slug": slug,
        "status": "accepted",
        "reverted_at": reverted_at,
        "path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
        "receipt_path": str(receipt.get("receipt_path") or ""),
    }
