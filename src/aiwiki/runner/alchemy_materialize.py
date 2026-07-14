"""Filesystem materialization helpers for alchemy runner workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiwiki.app_utils import (
    parse_frontmatter,
    relative_path,
    render_frontmatter,
    sha256_bytes,
    slugify,
    strip_frontmatter,
)
from aiwiki.runner import alchemy_support as support

ALCHEMY_JUDGE_REFRESH_START = support.ALCHEMY_JUDGE_REFRESH_START
ALCHEMY_JUDGE_REFRESH_END = support.ALCHEMY_JUDGE_REFRESH_END

def materialize_alchemy_judge_refresh(
    root: Path,
    *,
    preview: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    target_ref = str(candidate.get("target_ref") or "")
    candidate_id = str(candidate.get("candidate_id") or "")
    target = (root / target_ref).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return {"status": "skipped", "candidate_id": candidate_id, "target_ref": target_ref, "reason": "target_outside_root"}
    if not target.exists():
        return {"status": "skipped", "candidate_id": candidate_id, "target_ref": target_ref, "reason": "target_missing"}
    original = target.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(original)
    kind = str(frontmatter.get("kind") or "")
    if kind not in {"decision", "judgment"}:
        return {"status": "skipped", "candidate_id": candidate_id, "target_ref": target_ref, "reason": "not_judgment_asset"}
    before_hash = sha256_bytes(original.encode("utf-8"))
    body = strip_frontmatter(original).strip()
    section = support.render_alchemy_judge_refresh_section(preview=preview, candidate=candidate)
    updated_body = support.replace_marker_section(
        body,
        section,
        start_marker=ALCHEMY_JUDGE_REFRESH_START,
        end_marker=ALCHEMY_JUDGE_REFRESH_END,
    )
    updated = f"{render_frontmatter(frontmatter)}\n\n{updated_body.strip()}\n"
    changed = updated != original
    if changed:
        target.write_text(updated, encoding="utf-8")
    after_hash = sha256_bytes(updated.encode("utf-8"))
    return {
        "status": "refreshed",
        "candidate_id": candidate_id,
        "target_ref": target_ref,
        "path": relative_path(root, target),
        "kind": kind,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "changed": changed,
    }


def materialize_alchemy_judge_proposal(
    root: Path,
    *,
    preview: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    target_ref = str(candidate.get("target_ref") or "")
    candidate_id = str(candidate.get("candidate_id") or "")
    proposal_id = slugify(f"alchemy-judge-proposal-{candidate_id or target_ref or 'candidate'}")
    proposal_path = root / "output" / "_proposals" / "judge" / f"{proposal_id}.md"
    target = (root / target_ref).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return {
            "status": "skipped",
            "candidate_id": candidate_id,
            "target_ref": target_ref,
            "proposal_id": proposal_id,
            "reason": "target_outside_root",
        }
    if not target.exists():
        return {
            "status": "skipped",
            "candidate_id": candidate_id,
            "target_ref": target_ref,
            "proposal_id": proposal_id,
            "reason": "target_missing",
        }
    original = target.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(original)
    kind = str(frontmatter.get("kind") or "")
    if kind not in {"decision", "judgment"}:
        return {
            "status": "skipped",
            "candidate_id": candidate_id,
            "target_ref": target_ref,
            "proposal_id": proposal_id,
            "reason": "not_judgment_asset",
        }
    before_hash = sha256_bytes(original.encode("utf-8"))
    if proposal_path.exists():
        return {
            "status": "skipped",
            "candidate_id": candidate_id,
            "target_ref": target_ref,
            "path": relative_path(root, proposal_path),
            "proposal_id": proposal_id,
            "before_hash": before_hash,
            "reason": "already_exists",
        }
    proposal = support.render_alchemy_judge_proposal_page(
        preview=preview,
        candidate=candidate,
        target_ref=target_ref,
        proposal_id=proposal_id,
        target_kind=kind,
        before_hash=before_hash,
    )
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_path.write_text(proposal, encoding="utf-8")
    return {
        "status": "generated",
        "candidate_id": candidate_id,
        "target_ref": target_ref,
        "path": relative_path(root, proposal_path),
        "proposal_id": proposal_id,
        "kind": kind,
        "before_hash": before_hash,
        "changed": True,
        "llm_invoked": False,
        "semantic_content_generated": False,
    }


def materialize_alchemy_review_queue(
    root: Path,
    *,
    preview: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    path = root / "wiki" / "indexes" / "review-queue.md"
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    before_hash = sha256_bytes(before.encode("utf-8")) if path.exists() else ""
    section = support.render_alchemy_review_queue_section(preview=preview, candidates=candidates)
    after = support.replace_review_queue_section(before, section)
    changed = after != before
    path.parent.mkdir(parents=True, exist_ok=True)
    if changed or not path.exists():
        path.write_text(after, encoding="utf-8")
    after_hash = sha256_bytes(after.encode("utf-8"))
    return {
        "path": relative_path(root, path),
        "before_hash": before_hash,
        "after_hash": after_hash,
        "changed": changed,
        "candidate_count": len(candidates),
    }


def resolve_alchemy_judge_proposal_path(root: Path, proposal: str | Path) -> Path:
    raw = str(proposal).strip().strip("'\"`")
    if not raw:
        raise ValueError("judge proposal path or id is required.")
    candidate = Path(raw)
    if not candidate.suffix and "/" not in raw and "\\" not in raw:
        candidate = Path("output") / "_proposals" / "judge" / f"{slugify(raw)}.md"
    resolved = candidate if candidate.is_absolute() else root / candidate
    resolved = resolved.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("judge proposal path must stay within the workspace.") from exc
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"judge proposal not found: {proposal}")
    return resolved

