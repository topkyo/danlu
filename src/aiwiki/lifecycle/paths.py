"""Lifecycle path helpers extracted from aiwiki.app_state_paths."""

from __future__ import annotations

from pathlib import Path


def knowledge_lifecycle_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "knowledge-lifecycle.json"


def knowledge_lifecycle_override_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "knowledge-lifecycle-overrides.json"


def nightly_health_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "nightly-health.json"
