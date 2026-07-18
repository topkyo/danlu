"""Material / active-corpora / manual-link state helpers.

Extracted from the legacy app_state hub. Owned by the content layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..app_state_paths import (
    active_corpora_state_path,
    manual_link_state_path,
    material_state_path,
)
from ..state.collections import normalize_versioned_record_list_state
from ..state.io import load_json_document, save_json_document
from ..utils.io import atomic_write_text, runtime_write_operation


def default_material_state() -> dict[str, Any]:
    return {"version": 1, "generated_at": "", "entries": []}


def load_material_state(root: Path) -> dict[str, Any]:
    document = load_json_document(material_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_material_state,
        list_key="entries",
        string_fields={"generated_at": ""},
    )


def save_material_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(material_state_path(root), document)


def default_active_corpora_state() -> dict[str, Any]:
    return {"version": 1, "corpora": []}


def load_active_corpora_state(root: Path) -> dict[str, Any]:
    document = load_json_document(active_corpora_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_active_corpora_state,
        list_key="corpora",
    )


def save_active_corpora_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(active_corpora_state_path(root), document)


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
