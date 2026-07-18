"""Manifest state helpers extracted from the legacy app_state hub."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..protocol.scaffold import ensure_layout
from ..utils.io import atomic_write_text
from .io import load_json_document_strict
from .paths import manifest_path


def default_manifest() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def load_manifest(root: Path) -> dict[str, Any]:
    path = manifest_path(root)
    if not path.exists():
        return default_manifest()
    return load_json_document_strict(path)


def save_manifest(root: Path, manifest: dict[str, Any]) -> None:
    ensure_layout(root)
    path = manifest_path(root)
    atomic_write_text(path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
