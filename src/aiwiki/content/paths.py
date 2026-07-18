"""Content/material path helpers extracted from aiwiki.app_state_paths."""

from __future__ import annotations

from pathlib import Path


def material_routing_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "material-routing.json"


def archive_candidates_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "archive-candidates.json"


def active_corpora_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "active-corpora.json"


def material_archive_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "material-archives.json"
