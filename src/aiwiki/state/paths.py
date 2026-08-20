"""Core state path helpers extracted from aiwiki.app_state_paths."""

from __future__ import annotations

from pathlib import Path


def manifest_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "manifest.json"


def machine_memory_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory.json"


def compile_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "compile-state.json"


def material_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "material-state.json"


def lint_reports_dir(root: Path) -> Path:
    return root / ".aiwiki" / "lint"


STAGING_PROPOSALS_DIR = ".aiwiki/staging/proposals"


def l3_proposal_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "l3-proposals.json"


def output_candidates_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "output-candidates.json"
