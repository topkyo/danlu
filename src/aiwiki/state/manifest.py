"""Manifest state helpers extracted from the legacy app_state hub."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_state_paths import manifest_path
from .io import load_json_document_strict


def default_manifest() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def load_manifest(root: Path) -> dict[str, Any]:
    path = manifest_path(root)
    if not path.exists():
        return default_manifest()
    return load_json_document_strict(path)
