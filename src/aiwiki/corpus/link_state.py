"""Manual-link JSON state loaders/savers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..state.io import load_json_document
from ..utils.io import atomic_write_text, runtime_write_operation
from .paths import manual_link_state_path


def default_manual_link_state() -> dict[str, Any]:
    return {"version": 1, "source_to_concept": []}


def load_manual_link_state(root: Path) -> dict[str, Any]:
    document = load_json_document(manual_link_state_path(root))
    if not isinstance(document, dict):
        return default_manual_link_state()
    source_to_concept = document.get("source_to_concept")
    if not isinstance(source_to_concept, list):
        return default_manual_link_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "source_to_concept": [item for item in source_to_concept if isinstance(item, dict)],
    }


@runtime_write_operation
def save_manual_link_state(root: Path, document: dict[str, Any]) -> None:
    atomic_write_text(manual_link_state_path(root), json.dumps(document, indent=2, sort_keys=True) + "\n")
