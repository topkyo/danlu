"""Filesystem destinations for render / shell / execution artifacts.

Extracted from aiwiki.app_render (EP-017A). Pure path primitives
shared by dashboard renderers and execution owner modules.
"""

from __future__ import annotations

from pathlib import Path

from ..utils.markdown import parse_frontmatter
from ..utils.text import slugify
from ..utils.time import utc_now

# Kept bound for acceptance monkeypatch: `aiwiki.render.paths.utc_now`.
_ = utc_now


def remove_stale_generated_concept_pages_detailed(root: Path, active_slugs: set[str]) -> tuple[int, list[str]]:
    """Remove compile-generated concept pages whose slugs left the active set.

    Returns ``(removed_count, removed_slugs)`` for compile telemetry.
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


# --- Render output paths (extracted from aiwiki.app_state_paths) ---


def shell_summary_path(root: Path) -> Path:
    return root / "output" / "control" / "shell-summary.json"


def product_shell_html_path(root: Path) -> Path:
    return root / "output" / "control" / "product-shell.html"


def machine_memory_graph_path(root: Path) -> Path:
    return root / ".aiwiki" / "cache" / "machine-memory-graph.json"


def repair_backlog_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "repair-backlog.md"


def judgment_assets_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "judgment-assets.md"
