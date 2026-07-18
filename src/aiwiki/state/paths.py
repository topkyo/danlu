"""Core state path helpers extracted from aiwiki.app_state_paths."""

from __future__ import annotations

from pathlib import Path

from ..utils.text import slugify


def manifest_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "manifest.json"


def machine_memory_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory.json"


def compile_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "compile-state.json"


def material_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "material-state.json"


def today_snooze_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "today-snooze.json"


def lint_reports_dir(root: Path) -> Path:
    return root / ".aiwiki" / "lint"


def l3_proposal_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "l3-proposals.json"


def output_candidates_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "output-candidates.json"


def agent_pack_path(root: Path, role: str) -> Path:
    return root / ".aiwiki" / "derived" / "agents" / f"{slugify(role)}.md"
