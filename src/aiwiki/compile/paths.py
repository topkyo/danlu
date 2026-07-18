"""Compile build-state path helpers extracted from aiwiki.app_state_paths."""

from __future__ import annotations

from pathlib import Path


def concept_build_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "concept-build-state.json"


def machine_memory_build_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory-build-state.json"


def ranking_build_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "ranking-build-state.json"


def output_pack_build_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "output-pack-build-state.json"


def domain_pilot_build_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "domain-pilot-build-state.json"
