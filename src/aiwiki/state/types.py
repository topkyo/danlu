"""State domain TypedDict contracts."""

from __future__ import annotations

from typing import TypedDict


class ManifestEntry(TypedDict, total=False):
    id: str
    title: str
    source_type: str
    note_kind: str
    original_path: str
    stored_path: str
    kind: str
    sha256: str
    imported_at: str
    updated_at: str
