"""Query result I/O against the volatile SQLite cache."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..utils.hash import sha256_bytes
from ..utils.io import runtime_write_lock
from ..utils.time import utc_now
from .core import (
    CACHE_SCHEMA_VERSION,
    _connect_cache,
    _initialize_schema,
    _json_dumps,
    _log_cache_fault,
    _read_meta,
    _write_meta,
)
from .paths import cache_db_path
from .status import _save_live_cache_status


def _load_rows(connection: sqlite3.Connection, table: str, key_field: str) -> dict[str, Any]:
    rows = connection.execute(f"SELECT {key_field}, payload_json FROM {table}").fetchall()
    loaded: dict[str, Any] = {}
    try:
        for row in rows:
            key = str(row[key_field] or "")
            if not key:
                continue
            payload = json.loads(str(row["payload_json"] or "{}"))
            loaded[key] = payload
    except (json.JSONDecodeError, TypeError) as exc:
        _log_cache_fault(f"load {table}", exc)
        raise
    return loaded


def load_query_cache_snapshot(root: Path) -> dict[str, Any] | None:
    path = cache_db_path(root)
    if not path.exists():
        return None
    connection: sqlite3.Connection | None = None
    try:
        connection = _connect_cache(root)
        _initialize_schema(connection)
        if _read_meta(connection, "schema_version") != str(CACHE_SCHEMA_VERSION):
            return None

        nodes = _load_rows(connection, "cache_nodes", "node_key")
        edges_rows = connection.execute(
            "SELECT edge_key, edge_kind, payload_json FROM cache_edges ORDER BY edge_key"
        ).fetchall()
        edge_buckets: dict[str, list[dict[str, Any]]] = {
            "source_to_concept": [],
            "source_to_judgment": [],
            "concept_to_concept": [],
            "judgment_to_judgment": [],
            "judgment_to_decision": [],
            "concept_causal": [],
            "elixir_derived_from": [],
        }
        for row in edges_rows:
            edge_key = str(row["edge_key"] or "")
            bucket = edge_key.split(":", 1)[0]
            payload = json.loads(str(row["payload_json"] or "{}"))
            if bucket in edge_buckets and isinstance(payload, dict):
                edge_buckets[bucket].append(payload)

        term_index = {
            key: payload
            for key, payload in _load_rows(connection, "cache_term_index", "term").items()
            if isinstance(payload, dict)
        }
        material_entries = list(_load_rows(connection, "cache_material_state", "entry_id").values())
        routing_entries = list(_load_rows(connection, "cache_routing_snapshot", "entry_id").values())
        archive_entries = list(_load_rows(connection, "cache_archive_candidates", "entry_id").values())
        concept_lifecycle_entries = list(_load_rows(connection, "cache_concept_lifecycle", "slug").values())
        judgment_summary_entries = list(_load_rows(connection, "cache_judgment_summary", "page_id").values())
        health_map = _load_rows(connection, "cache_health", "key")
        health = {
            "components": health_map.get("components", []),
            "source_component_ids": health_map.get("source_component_ids", {}),
            "concept_component_ids": health_map.get("concept_component_ids", {}),
            "actions": health_map.get("actions", []),
            "bridge_concept_slugs": health_map.get("bridge_concept_slugs", []),
        }
        return {
            "compiled_at": _read_meta(connection, "compiled_at"),
            "memory_hash": _read_meta(connection, "memory_hash"),
            "memory": {
                "compiled_at": _read_meta(connection, "compiled_at"),
                "source_nodes": [payload for key, payload in nodes.items() if key.startswith("source:")],
                "concept_nodes": [payload for key, payload in nodes.items() if key.startswith("concept:")],
                "judgment_nodes": judgment_summary_entries
                or [payload for key, payload in nodes.items() if key.startswith("judgment:")],
                "elixir_nodes": [payload for key, payload in nodes.items() if key.startswith("elixir:")],
                "edges": edge_buckets,
                "term_index": term_index,
                "health": health,
            },
            "material_state": {"entries": material_entries},
            "routing_state": {"entries": routing_entries},
            "knowledge_lifecycle": {"entries": concept_lifecycle_entries},
            "archive_candidates": {"entries": archive_entries},
        }
    except (sqlite3.Error, OSError, json.JSONDecodeError, TypeError) as exc:
        _log_cache_fault("load snapshot", exc)
        return None
    finally:
        if connection is not None:
            connection.close()


def load_cached_query_result(root: Path, query_key: str, payload_hash: str) -> dict[str, Any] | None:
    path = cache_db_path(root)
    if not path.exists():
        return None
    connection: sqlite3.Connection | None = None
    try:
        connection = _connect_cache(root)
        _initialize_schema(connection)
        if _read_meta(connection, "schema_version") != str(CACHE_SCHEMA_VERSION):
            return None
        row = connection.execute(
            "SELECT payload_json FROM cache_query_results WHERE query_key = ? AND payload_hash = ?",
            (query_key, payload_hash),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(str(row["payload_json"] or "{}"))
        return payload if isinstance(payload, dict) else None
    except (sqlite3.Error, OSError, json.JSONDecodeError, TypeError) as exc:
        _log_cache_fault("load query result", exc)
        return None
    finally:
        if connection is not None:
            connection.close()


def save_cached_query_result(root: Path, query_key: str, payload_hash: str, payload: dict[str, Any]) -> None:
    with runtime_write_lock(root):
        connection: sqlite3.Connection | None = None
        try:
            connection = _connect_cache(root)
            _initialize_schema(connection)
            _write_meta(connection, "schema_version", str(CACHE_SCHEMA_VERSION))
            connection.execute(
                "INSERT INTO cache_query_results(query_key, payload_hash, payload_json, updated_at) VALUES(?, ?, ?, ?) "
                "ON CONFLICT(query_key) DO UPDATE SET payload_hash=excluded.payload_hash, payload_json=excluded.payload_json, updated_at=excluded.updated_at",
                (query_key, payload_hash, _json_dumps(payload), utc_now()),
            )
            connection.commit()
            _save_live_cache_status(root, connection, enabled=True)
        except (sqlite3.Error, OSError, json.JSONDecodeError, TypeError) as exc:
            _log_cache_fault("save query result", exc)
            return None
        finally:
            if connection is not None:
                connection.close()


def query_cache_key(*, question: str, protocol: str) -> str:
    normalized = f"{protocol}\n{' '.join(question.split())}"
    return f"sha256:{sha256_bytes(normalized.encode('utf-8'))}"
