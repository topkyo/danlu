"""Shared vault state / proposal path helpers used by content and memory."""

from __future__ import annotations

from pathlib import Path


def manual_link_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "manual-links.json"


def concept_rewrite_proposal_page_path(root: Path, slug: str) -> Path:
    return root / "wiki" / "rewrite-proposals" / f"{slug}.md"


def concept_rewrite_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "concept-rewrite-proposals.json"
