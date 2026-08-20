"""Cache status tracking and management operations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..compile.state import load_compile_state
from ..content.archive import load_archive_candidates_state, load_material_routing_state
from ..content.material import load_material_state
from ..lifecycle.knowledge import load_knowledge_lifecycle_state
from ..memory.state import load_machine_memory
from ..state.cache import load_cache_status, save_cache_status
from ..utils.io import runtime_write_lock
from ..utils.path import relative_path
from ..utils.time import utc_now
from .core import CACHE_SCHEMA_VERSION, _cache_row_counts, _log_cache_fault
from .paths import cache_db_path, cache_status_path


def _save_live_cache_status(
    root: Path,
    connection: sqlite3.Connection,
    *,
    enabled: bool,
    stats: dict[str, Any] | None = None,
    last_sync: dict[str, Any] | None = None,
    last_query: dict[str, Any] | None = None,
    last_drop: dict[str, Any] | None = None,
    last_rebuild: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = load_cache_status(root)
    document = {
        "version": int(status.get("version", 1) or 1),
        "enabled": enabled,
        "schema_version": CACHE_SCHEMA_VERSION,
        "updated_at": utc_now(),
        "db_path": relative_path(root, cache_db_path(root)),
        "state_path": relative_path(root, cache_status_path(root)),
        "row_counts": _cache_row_counts(connection),
        "stats": dict(stats if stats is not None else status.get("stats", {})),
        "last_sync": dict(last_sync if last_sync is not None else status.get("last_sync", {})),
        "last_query": dict(last_query if last_query is not None else status.get("last_query", {})),
        "last_drop": dict(last_drop if last_drop is not None else status.get("last_drop", {})),
        "last_rebuild": dict(last_rebuild if last_rebuild is not None else status.get("last_rebuild", {})),
    }
    save_cache_status(root, document)
    return document


def _merge_cache_status(
    root: Path,
    *,
    stats_delta: dict[str, int] | None = None,
    last_query: dict[str, Any] | None = None,
    last_drop: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with runtime_write_lock(root):
        try:
            status = load_cache_status(root)
            stats = dict(status.get("stats", {}))
            for key, value in (stats_delta or {}).items():
                stats[key] = int(stats.get(key, 0) or 0) + int(value or 0)
            document = {
                "version": int(status.get("version", 1) or 1),
                "enabled": bool(status.get("enabled", False)),
                "schema_version": int(status.get("schema_version", CACHE_SCHEMA_VERSION) or CACHE_SCHEMA_VERSION),
                "updated_at": utc_now(),
                "db_path": str(status.get("db_path") or relative_path(root, cache_db_path(root))),
                "state_path": str(status.get("state_path") or relative_path(root, cache_status_path(root))),
                "row_counts": dict(status.get("row_counts", {})),
                "stats": stats,
                "last_sync": dict(status.get("last_sync", {})),
                "last_query": dict(last_query if last_query is not None else status.get("last_query", {})),
                "last_drop": dict(last_drop if last_drop is not None else status.get("last_drop", {})),
                "last_rebuild": dict(status.get("last_rebuild", {})),
            }
            save_cache_status(root, document)
            return document
        except (sqlite3.Error, OSError, json.JSONDecodeError, TypeError) as exc:
            _log_cache_fault("status merge", exc)
            return load_cache_status(root)


def record_query_cache_event(
    root: Path,
    *,
    hit: bool,
    bypass: bool = False,
    query_key: str,
    payload_hash: str,
    reason: str,
) -> dict[str, Any]:
    stats_delta: dict[str, int]
    if bypass:
        stats_delta = {"query_bypasses": 1}
    elif hit:
        stats_delta = {"query_hits": 1}
    else:
        stats_delta = {"query_misses": 1}
    try:
        return _merge_cache_status(
            root,
            stats_delta=stats_delta,
            last_query={
                "updated_at": utc_now(),
                "query_key": query_key,
                "payload_hash": payload_hash,
                "hit": hit,
                "bypass": bypass,
                "reason": reason,
            },
        )
    except (sqlite3.Error, OSError, json.JSONDecodeError, TypeError) as exc:
        _log_cache_fault("record event", exc)
        return load_cache_status(root)


def drop_query_cache(root: Path) -> dict[str, Any]:
    with runtime_write_lock(root):
        path = cache_db_path(root)
        existed = path.exists()
        if existed:
            path.unlink()
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{path}{suffix}")
            if sidecar.exists():
                sidecar.unlink()
        status = load_cache_status(root)
        stats = dict(status.get("stats", {}))
        stats["drops"] = int(stats.get("drops", 0) or 0) + 1
        updated_at = utc_now()
        document = {
            "version": 1,
            "enabled": False,
            "schema_version": CACHE_SCHEMA_VERSION,
            "updated_at": updated_at,
            "db_path": relative_path(root, path),
            "state_path": relative_path(root, cache_status_path(root)),
            "row_counts": {},
            "stats": stats,
            "last_sync": dict(status.get("last_sync", {})),
            "last_query": dict(status.get("last_query", {})),
            "last_drop": {
                "updated_at": updated_at,
                "db_path": relative_path(root, path),
                "dropped": existed,
            },
            "last_rebuild": dict(status.get("last_rebuild", {})),
        }
        save_cache_status(root, document)
        return {
            "dropped": existed,
            "db_path": relative_path(root, path),
            "state_path": relative_path(root, cache_status_path(root)),
        }


def cache_status_summary(root: Path) -> dict[str, Any]:
    status = load_cache_status(root)
    row_counts = dict(status.get("row_counts", {}))
    stats = dict(status.get("stats", {}))
    last_sync = dict(status.get("last_sync", {}))
    last_query = dict(status.get("last_query", {}))
    last_drop = dict(status.get("last_drop", {}))
    last_rebuild = dict(status.get("last_rebuild", {}))
    return {
        "enabled": bool(status.get("enabled", False)),
        "schema_version": int(status.get("schema_version", 0) or 0),
        "db_path": str(status.get("db_path") or relative_path(root, cache_db_path(root))),
        "state_path": str(status.get("state_path") or relative_path(root, cache_status_path(root))),
        "updated_at": str(status.get("updated_at") or ""),
        "row_counts": row_counts,
        "row_count_total": int(sum(int(value or 0) for value in row_counts.values())),
        "stats": stats,
        "last_sync": last_sync,
        "last_query": last_query,
        "last_drop": last_drop,
        "last_rebuild": last_rebuild,
        "rebuild_reason": str(last_sync.get("rebuild_reason") or last_rebuild.get("reason") or ""),
    }


def force_rebuild_query_cache(root: Path) -> dict[str, Any]:
    memory = load_machine_memory(root)
    material_state = load_material_state(root)
    routing_state = load_material_routing_state(root)
    knowledge_lifecycle = load_knowledge_lifecycle_state(root)
    archive_candidates = load_archive_candidates_state(root)
    compile_state = load_compile_state(root)
    compiled_at = str(compile_state.get("compiled_at") or memory.get("compiled_at") or "").strip()
    if not compiled_at or not isinstance(memory, dict) or not memory:
        status = load_cache_status(root)
        return {
            "rebuilt": False,
            "reason": "missing-state",
            **cache_status_summary(root),
            "last_rebuild": dict(status.get("last_rebuild", {})),
        }
    # Local import to avoid a circular import with cache.sync (which imports
    # _save_live_cache_status from this module at top level).
    from .sync import sync_query_cache

    status = sync_query_cache(
        root,
        memory=memory,
        material_state=material_state,
        routing_state=routing_state,
        knowledge_lifecycle=knowledge_lifecycle,
        archive_candidates=archive_candidates,
        compiled_at=compiled_at,
        force_rebuild=True,
    )
    return {
        "rebuilt": True,
        "reason": "forced",
        **cache_status_summary(root),
        "last_rebuild": dict(status.get("last_rebuild", {})),
    }
