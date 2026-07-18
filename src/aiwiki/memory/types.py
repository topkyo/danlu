"""Memory domain TypedDict contracts."""

from __future__ import annotations

from typing import TypedDict


class MachineMemoryRecord(TypedDict, total=False):
    id: str
    kind: str
    title: str
    source_type: str
    source_page: str
    stored_path: str
    slug: str
    source_pages: list[str]
    source_ids: list[str]
    related_slugs: list[str]
    source_count: int
    related_count: int
    quality_state: str
    issues: list[str]
    rewrite_priority: str
    rewrite_strategy: str
