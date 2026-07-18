"""Cache status state helpers extracted from the legacy app_state hub."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..cache.paths import cache_db_path, cache_status_path
from ..utils.path import relative_path
from .io import load_json_document, save_json_document

logger = logging.getLogger(__name__)


def default_cache_status() -> dict[str, Any]:
    return {
        "version": 1,
        "enabled": False,
        "schema_version": 0,
        "updated_at": "",
        "db_path": "",
        "state_path": "",
        "row_counts": {},
        "stats": {
            "query_hits": 0,
            "query_misses": 0,
            "query_bypasses": 0,
            "compile_syncs": 0,
            "rebuilds": 0,
            "drops": 0,
        },
        "last_sync": {},
        "last_query": {},
        "last_drop": {},
        "last_rebuild": {},
    }


def load_cache_status(root: Path) -> dict[str, Any]:
    try:
        document = load_json_document(cache_status_path(root))
    except OSError as exc:
        logger.warning("cache status load failed: %s", exc)
        return default_cache_status()
    if not isinstance(document, dict):
        return default_cache_status()
    row_counts = document.get("row_counts")
    stats = document.get("stats")
    last_sync = document.get("last_sync")
    last_query = document.get("last_query")
    last_drop = document.get("last_drop")
    last_rebuild = document.get("last_rebuild", {})
    if not isinstance(row_counts, dict) or not isinstance(stats, dict):
        return default_cache_status()
    if (
        not isinstance(last_sync, dict)
        or not isinstance(last_query, dict)
        or not isinstance(last_drop, dict)
        or not isinstance(last_rebuild, dict)
    ):
        return default_cache_status()
    return {
        "version": int(document.get("version", 1) or 1),
        "enabled": bool(document.get("enabled", False)),
        "schema_version": int(document.get("schema_version", 0) or 0),
        "updated_at": str(document.get("updated_at") or ""),
        "db_path": str(document.get("db_path") or relative_path(root, cache_db_path(root))),
        "state_path": str(document.get("state_path") or relative_path(root, cache_status_path(root))),
        "row_counts": {str(key): int(value or 0) for key, value in row_counts.items()},
        "stats": {
            "query_hits": int(stats.get("query_hits", 0) or 0),
            "query_misses": int(stats.get("query_misses", 0) or 0),
            "query_bypasses": int(stats.get("query_bypasses", 0) or 0),
            "compile_syncs": int(stats.get("compile_syncs", 0) or 0),
            "rebuilds": int(stats.get("rebuilds", 0) or 0),
            "drops": int(stats.get("drops", 0) or 0),
        },
        "last_sync": dict(last_sync),
        "last_query": dict(last_query),
        "last_drop": dict(last_drop),
        "last_rebuild": dict(last_rebuild),
    }


def save_cache_status(root: Path, document: dict[str, Any]) -> None:
    try:
        save_json_document(cache_status_path(root), document)
    except OSError as exc:
        logger.warning("cache status save failed: %s", exc)
        return None
