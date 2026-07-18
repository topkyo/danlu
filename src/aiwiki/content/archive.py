"""Material routing / archive-candidates / material-archive state helpers.

Extracted from the legacy app_state hub. Owned by the content layer (routing + archive
state lives here; the archive *execution* path remains in execution.archive).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_state_paths import (
    archive_candidates_state_path,
    material_archive_state_path,
    material_routing_state_path,
)
from ..state.collections import active_records_by_key, normalize_versioned_record_list_state
from ..state.constants import DEFAULT_PROTOCOL
from ..state.io import load_json_document, save_json_document


def default_material_routing_state() -> dict[str, Any]:
    return {"version": 1, "computed_at": "", "active_protocol": DEFAULT_PROTOCOL, "entries": []}


def load_material_routing_state(root: Path) -> dict[str, Any]:
    document = load_json_document(material_routing_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_material_routing_state,
        list_key="entries",
        string_fields={"computed_at": "", "active_protocol": DEFAULT_PROTOCOL},
    )


def save_material_routing_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(material_routing_state_path(root), document)


def default_archive_candidates_state() -> dict[str, Any]:
    return {"version": 1, "generated_at": "", "entries": []}


def load_archive_candidates_state(root: Path) -> dict[str, Any]:
    document = load_json_document(archive_candidates_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_archive_candidates_state,
        list_key="entries",
        string_fields={"generated_at": ""},
    )


def save_archive_candidates_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(archive_candidates_state_path(root), document)


def default_material_archive_state() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def load_material_archive_state(root: Path) -> dict[str, Any]:
    document = load_json_document(material_archive_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_material_archive_state,
        list_key="entries",
    )


def save_material_archive_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(material_archive_state_path(root), document)


def active_material_archive_entries(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return active_records_by_key(document, list_key="entries", key="entry_id")


def active_archived_material_ids(root: Path) -> set[str]:
    return set(active_material_archive_entries(load_material_archive_state(root)))
