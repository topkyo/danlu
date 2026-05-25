"""Small collection-state normalizers extracted from app_state."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def normalize_versioned_record_list_state(
    document: Any,
    *,
    default_state: Callable[[], dict[str, Any]],
    list_key: str,
    string_fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not isinstance(document, dict):
        return default_state()
    records = document.get(list_key)
    if not isinstance(records, list):
        return default_state()
    normalized = {
        "version": int(document.get("version", 1) or 1),
        list_key: [record for record in records if isinstance(record, dict)],
    }
    for field, fallback in (string_fields or {}).items():
        normalized[field] = str(document.get(field) or fallback)
    return normalized


def active_records_by_key(
    document: dict[str, Any],
    *,
    list_key: str,
    key: str,
    active_key: str = "active",
) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get(key) or ""): entry
        for entry in document.get(list_key, [])
        if isinstance(entry, dict) and entry.get(key) and bool(entry.get(active_key, False))
    }
