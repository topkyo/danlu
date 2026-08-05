"""Compat re-export — prefer ``aiwiki.corpus.scoring``."""

from __future__ import annotations

from aiwiki.corpus.scoring import (  # noqa: F401
    QUERY_TIME_FOCUS_MARKERS,
    machine_memory_query_time_focus,
    protocol_hints_for_material,
    recency_score_for_timestamp,
    timestamp_is_newer,
    update_latest_timestamp,
)

__all__ = [
    "QUERY_TIME_FOCUS_MARKERS",
    "machine_memory_query_time_focus",
    "protocol_hints_for_material",
    "recency_score_for_timestamp",
    "timestamp_is_newer",
    "update_latest_timestamp",
]
