"""Cache path helpers extracted from aiwiki.app_state_paths."""

from __future__ import annotations

from pathlib import Path


def cache_db_path(root: Path) -> Path:
    return root / ".aiwiki" / "cache.db"


def cache_status_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "cache-status.json"
