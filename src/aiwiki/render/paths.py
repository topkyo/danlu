"""Filesystem destinations + wiki log helpers.

Extracted from aiwiki.app_render (EP-017A). Pure path/log primitives
shared by output-pack builders, pilot builders, dashboard renderers,
and execution owner modules under aiwiki.execution.

External callers should import from aiwiki.render.paths directly
to preserve B2/B5/B6/B7 true-origin convention; direct imports from
aiwiki.render.paths are also valid for new code.
"""

from __future__ import annotations

from pathlib import Path

from ..app_protocol import ensure_layout
from ..app_utils import parse_frontmatter, slugify, utc_now

# Kept bound for acceptance monkeypatch: `aiwiki.render.paths.utc_now`.
_ = utc_now


def ensure_wiki_log(root: Path) -> Path:
    """Return the legacy wiki log path without creating it.

    Obsidian-visible ``wiki/indexes/log.md`` is retired: unbounded append
    crashed Obsidian indexing. Canonical history lives in
    ``.aiwiki/state/runtime-history.jsonl`` (plus receipts / audit).
    Call sites may still call this for compatibility; it only ensures layout.
    """

    ensure_layout(root)
    return root / "wiki" / "indexes" / "log.md"


def append_wiki_log(root: Path, category: str, title: str, details: list[str]) -> None:
    """No-op: do not write Obsidian-visible ``wiki/indexes/log.md``.

    Operation history belongs in runtime-history.jsonl / receipts / audit.
    ``category``, ``title``, and ``details`` are retained for call-site
    compatibility and are intentionally unused.
    """

    _ = (root, category, title, details)
    return


def remove_stale_generated_concept_pages(root: Path, active_slugs: set[str]) -> int:
    removed_count, _ = remove_stale_generated_concept_pages_detailed(root, active_slugs)
    return removed_count


def remove_stale_generated_concept_pages_detailed(
    root: Path, active_slugs: set[str]
) -> tuple[int, list[str]]:
    """Same as `remove_stale_generated_concept_pages` but also returns the removed slugs.

    Used by the compile pipeline to emit a `concept-noise-pruned` wiki log entry when
    retroactive noise-floor changes invalidate previously generated concept pages
    (F-new-13, Round 6).
    """
    removed_slugs: list[str] = []
    for path in sorted((root / "wiki" / "concepts").glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if frontmatter.get("kind") != "concept":
            continue
        if frontmatter.get("generated_by") != "aiwiki-compile":
            continue
        concept_id = frontmatter.get("id", "")
        if not isinstance(concept_id, str) or not concept_id.startswith("concept-"):
            continue
        slug = concept_id[len("concept-") :]
        if slug in active_slugs:
            continue
        path.unlink()
        removed_slugs.append(slug)
    return len(removed_slugs), removed_slugs


def review_packs_dir(root: Path) -> Path:
    return root / ".aiwiki" / "derived" / "packs" / "review"


def decision_memos_dir(root: Path) -> Path:
    return root / ".aiwiki" / "derived" / "packs" / "decision-memos"


def sop_drafts_dir(root: Path) -> Path:
    return root / ".aiwiki" / "derived" / "packs" / "sop-drafts"


def pack_stem(seed: str) -> str:
    cleaned = seed.replace("/", "-").replace("\\", "-").replace(".md", "")
    return slugify(cleaned)[:96] or "pack"


def review_pack_path(root: Path, target_path: str) -> Path:
    return review_packs_dir(root) / f"{pack_stem(target_path)}.md"


def decision_memo_path(root: Path, target_path: str) -> Path:
    return decision_memos_dir(root) / f"{pack_stem(target_path)}.md"


def sop_draft_path(root: Path, action_id: str) -> Path:
    return sop_drafts_dir(root) / f"{pack_stem(action_id)}.md"


def execution_proposals_dir(root: Path) -> Path:
    return root / "wiki" / "execution-proposals"


def execution_proposal_path(root: Path, action_id: str) -> Path:
    return execution_proposals_dir(root) / f"{slugify(action_id)}.md"


def execution_bundles_dir(root: Path) -> Path:
    """Per-action execution bundle JSON directory (not Obsidian-visible).

    Legacy vault path ``output/control/execution-bundles/`` is retired.
    """

    return root / ".aiwiki" / "state" / "execution-bundles"


def execution_bundle_path(root: Path, action_id: str) -> Path:
    return execution_bundles_dir(root) / f"{slugify(action_id)}.json"


def execution_receipts_dir(root: Path) -> Path:
    """Per-action receipt JSON directory (not Obsidian-visible).

    History stream remains ``.aiwiki/state/execution-receipts.jsonl``.
    Legacy vault path ``output/control/execution-receipts/`` is retired.
    """

    return root / ".aiwiki" / "state" / "execution-receipts"


def execution_receipt_path(root: Path, action_id: str) -> Path:
    return execution_receipts_dir(root) / f"{slugify(action_id)}.json"


def legacy_execution_receipt_path(root: Path, action_id: str) -> Path:
    """Pre-2026-07 Obsidian-visible receipt path (read fallback only)."""

    return root / "output" / "control" / "execution-receipts" / f"{slugify(action_id)}.json"


def resolve_execution_receipt_path(root: Path, action_id: str) -> Path:
    """Prefer ``.aiwiki`` receipts; fall back to legacy vault copies for reads."""

    primary = execution_receipt_path(root, action_id)
    if primary.exists():
        return primary
    legacy = legacy_execution_receipt_path(root, action_id)
    if legacy.exists():
        return legacy
    return primary

