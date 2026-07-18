"""Volatile SQLite cache owner for machine-memory query acceleration.

OWNER STATUS: legacy owner. New large logic blocks should be extracted to a
dedicated subpackage (e.g. `aiwiki.cache.*`) rather than added here.
See AGENTS.md migration policy.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from .app_state import (
    cache_db_path,
    cache_status_path,
    load_archive_candidates_state,
    load_cache_status,
    load_compile_state,
    load_knowledge_lifecycle_state,
    load_machine_memory,
    load_material_routing_state,
    load_material_state,
    save_cache_status,
)
from .app_utils import relative_path, runtime_write_lock, sha256_bytes, utc_now

CACHE_SCHEMA_VERSION = 1

logger = logging.getLogger(__name__)


def _log_cache_fault(label: str, exc: BaseException) -> None:
    logger.warning("cache %s failed: %s", label, exc)


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload_hash(payload: Any) -> str:
    return f"sha256:{sha256_bytes(_json_dumps(payload).encode('utf-8'))}"


def _connect_cache(root: Path) -> sqlite3.Connection:
    path = cache_db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def _initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS cache_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cache_nodes (
            node_key TEXT PRIMARY KEY,
            node_kind TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cache_edges (
            edge_key TEXT PRIMARY KEY,
            edge_kind TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cache_term_index (
            term TEXT PRIMARY KEY,
            source_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cache_material_state (
            entry_id TEXT PRIMARY KEY,
            source_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cache_routing_snapshot (
            entry_id TEXT PRIMARY KEY,
            source_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cache_concept_lifecycle (
            slug TEXT PRIMARY KEY,
            source_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cache_judgment_summary (
            page_id TEXT PRIMARY KEY,
            source_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cache_archive_candidates (
            entry_id TEXT PRIMARY KEY,
            source_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cache_health (
            key TEXT PRIMARY KEY,
            source_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cache_query_results (
            query_key TEXT PRIMARY KEY,
            payload_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


def _cache_row_counts(connection: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in (
        "cache_nodes",
        "cache_edges",
        "cache_term_index",
        "cache_material_state",
        "cache_routing_snapshot",
        "cache_concept_lifecycle",
        "cache_judgment_summary",
        "cache_archive_candidates",
        "cache_health",
        "cache_query_results",
    ):
        counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return counts


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


def _write_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO cache_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def _read_meta(connection: sqlite3.Connection, key: str) -> str:
    row = connection.execute("SELECT value FROM cache_meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return ""
    return str(row[0] or "")


def _rebuild_required(connection: sqlite3.Connection, *, schema_version: int) -> bool:
    stored_version = _read_meta(connection, "schema_version")
    if stored_version != str(schema_version):
        return True
    return False


def _rebuild_reason(connection: sqlite3.Connection, *, schema_version: int, force_rebuild: bool) -> str:
    if force_rebuild:
        return "forced"
    stored_version = _read_meta(connection, "schema_version")
    if not stored_version:
        return "initial-sync"
    if stored_version != str(schema_version):
        return "schema-mismatch"
    return ""


def _drop_cache_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        DELETE FROM cache_nodes;
        DELETE FROM cache_edges;
        DELETE FROM cache_term_index;
        DELETE FROM cache_material_state;
        DELETE FROM cache_routing_snapshot;
        DELETE FROM cache_concept_lifecycle;
        DELETE FROM cache_judgment_summary;
        DELETE FROM cache_archive_candidates;
        DELETE FROM cache_health;
        DELETE FROM cache_query_results;
        DELETE FROM cache_meta;
        """
    )


def _upsert_json_rows(
    connection: sqlite3.Connection,
    table: str,
    *,
    key_column: str,
    kind_column: str | None,
    rows: list[tuple[str, str | None, str, str]],
) -> None:
    if not rows:
        return
    if kind_column is None:
        connection.executemany(
            f"INSERT INTO {table}({key_column}, source_hash, payload_json) VALUES(?, ?, ?) "
            f"ON CONFLICT({key_column}) DO UPDATE SET source_hash=excluded.source_hash, payload_json=excluded.payload_json",
            [(key, source_hash, payload_json) for key, _kind, source_hash, payload_json in rows],
        )
        return
    connection.executemany(
        f"INSERT INTO {table}({key_column}, {kind_column}, source_hash, payload_json) VALUES(?, ?, ?, ?) "
        f"ON CONFLICT({key_column}) DO UPDATE SET {kind_column}=excluded.{kind_column}, source_hash=excluded.source_hash, payload_json=excluded.payload_json",
        rows,
    )


def _delete_missing_rows(connection: sqlite3.Connection, table: str, key_column: str, live_keys: set[str]) -> None:
    rows = connection.execute(f"SELECT {key_column} FROM {table}").fetchall()
    stale_keys = [str(row[0] or "") for row in rows if str(row[0] or "") and str(row[0] or "") not in live_keys]
    if not stale_keys:
        return
    connection.executemany(f"DELETE FROM {table} WHERE {key_column} = ?", [(key,) for key in stale_keys])


def query_cache_memory_hash(memory: dict[str, Any]) -> str:
    edges = memory.get("edges", {})
    payload = {
        "compiled_at": str(memory.get("compiled_at") or ""),
        "source_nodes": memory.get("source_nodes", []),
        "concept_nodes": memory.get("concept_nodes", []),
        "judgment_nodes": memory.get("judgment_nodes", []),
        "elixir_nodes": memory.get("elixir_nodes", []),
        "edges": edges if isinstance(edges, dict) else {},
        "elixir_derived_from": (
            edges.get("elixir_derived_from", [])
            if isinstance(edges, dict)
            else []
        ),
        "term_index": memory.get("term_index", {}),
        "health": memory.get("health", {}),
    }
    return _payload_hash(payload)


def sync_query_cache(
    root: Path,
    *,
    memory: dict[str, Any],
    material_state: dict[str, Any],
    routing_state: dict[str, Any],
    knowledge_lifecycle: dict[str, Any],
    archive_candidates: dict[str, Any],
    compiled_at: str,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    with runtime_write_lock(root):
        connection: sqlite3.Connection | None = None
        try:
            connection = _connect_cache(root)
            _initialize_schema(connection)
            memory_hash = query_cache_memory_hash(memory)
            rebuild_reason = _rebuild_reason(
                connection,
                schema_version=CACHE_SCHEMA_VERSION,
                force_rebuild=force_rebuild,
            )
            rebuild_required = bool(rebuild_reason)
            if rebuild_required:
                _drop_cache_tables(connection)
                _initialize_schema(connection)

            node_rows: list[tuple[str, str | None, str, str]] = []
            for node in memory.get("source_nodes", []):
                if not isinstance(node, dict):
                    continue
                node_id = str(node.get("id") or "")
                if node_id:
                    payload_json = _json_dumps(node)
                    node_rows.append((f"source:{node_id}", "source", _payload_hash(node), payload_json))
            for node in memory.get("concept_nodes", []):
                if not isinstance(node, dict):
                    continue
                slug = str(node.get("slug") or "")
                if slug:
                    payload_json = _json_dumps(node)
                    node_rows.append((f"concept:{slug}", "concept", _payload_hash(node), payload_json))
            for node in memory.get("judgment_nodes", []):
                if not isinstance(node, dict):
                    continue
                page_id = str(node.get("page_id") or "")
                if page_id:
                    payload_json = _json_dumps(node)
                    node_rows.append((f"judgment:{page_id}", "judgment", _payload_hash(node), payload_json))
            for node in memory.get("elixir_nodes", []):
                if not isinstance(node, dict):
                    continue
                elixir_id = str(node.get("elixir_id") or "")
                if elixir_id:
                    payload_json = _json_dumps(node)
                    node_rows.append((f"elixir:{elixir_id}", "elixir", _payload_hash(node), payload_json))
            _upsert_json_rows(
                connection,
                "cache_nodes",
                key_column="node_key",
                kind_column="node_kind",
                rows=node_rows,
            )
            _delete_missing_rows(connection, "cache_nodes", "node_key", {row[0] for row in node_rows})

            edge_rows: list[tuple[str, str | None, str, str]] = []
            edges = memory.get("edges", {})
            edge_specs = (
                ("source_to_concept", "HAS_CONCEPT"),
                ("source_to_judgment", "SUPPORTS_JUDGMENT"),
                ("concept_to_concept", "RELATED_CONCEPT"),
                ("judgment_to_judgment", "JUDGMENT_RELATION"),
                ("judgment_to_decision", "DECISION_RELATION"),
                ("concept_causal", "CAUSAL_RELATION"),
                ("elixir_derived_from", "ELIXIR_DERIVED_FROM"),
            )
            for edge_bucket, edge_kind in edge_specs:
                for index, edge in enumerate(edges.get(edge_bucket, [])):
                    if not isinstance(edge, dict):
                        continue
                    payload_json = _json_dumps(edge)
                    edge_rows.append((f"{edge_bucket}:{index}", edge_kind, _payload_hash(edge), payload_json))
            _upsert_json_rows(
                connection,
                "cache_edges",
                key_column="edge_key",
                kind_column="edge_kind",
                rows=edge_rows,
            )
            _delete_missing_rows(connection, "cache_edges", "edge_key", {row[0] for row in edge_rows})

            term_rows = []
            for term, payload in sorted(memory.get("term_index", {}).items()):
                if not isinstance(term, str) or not term or not isinstance(payload, dict):
                    continue
                payload_json = _json_dumps(payload)
                term_rows.append((term, None, _payload_hash(payload), payload_json))
            _upsert_json_rows(
                connection,
                "cache_term_index",
                key_column="term",
                kind_column=None,
                rows=term_rows,
            )
            _delete_missing_rows(connection, "cache_term_index", "term", {row[0] for row in term_rows})

            material_rows = []
            for entry in material_state.get("entries", []):
                if not isinstance(entry, dict):
                    continue
                entry_id = str(entry.get("entry_id") or "")
                if not entry_id:
                    continue
                payload_json = _json_dumps(entry)
                material_rows.append((entry_id, None, _payload_hash(entry), payload_json))
            _upsert_json_rows(
                connection,
                "cache_material_state",
                key_column="entry_id",
                kind_column=None,
                rows=material_rows,
            )
            _delete_missing_rows(connection, "cache_material_state", "entry_id", {row[0] for row in material_rows})

            routing_rows = []
            for entry in routing_state.get("entries", []):
                if not isinstance(entry, dict):
                    continue
                entry_id = str(entry.get("entry_id") or "")
                if not entry_id:
                    continue
                payload_json = _json_dumps(entry)
                routing_rows.append((entry_id, None, _payload_hash(entry), payload_json))
            _upsert_json_rows(
                connection,
                "cache_routing_snapshot",
                key_column="entry_id",
                kind_column=None,
                rows=routing_rows,
            )
            _delete_missing_rows(connection, "cache_routing_snapshot", "entry_id", {row[0] for row in routing_rows})

            lifecycle_rows = []
            for entry in knowledge_lifecycle.get("entries", []):
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("kind") or "") != "concept":
                    continue
                slug = Path(str(entry.get("path") or "")).stem
                if not slug:
                    continue
                payload_json = _json_dumps(entry)
                lifecycle_rows.append((slug, None, _payload_hash(entry), payload_json))
            _upsert_json_rows(
                connection,
                "cache_concept_lifecycle",
                key_column="slug",
                kind_column=None,
                rows=lifecycle_rows,
            )
            _delete_missing_rows(connection, "cache_concept_lifecycle", "slug", {row[0] for row in lifecycle_rows})

            judgment_rows = []
            for entry in memory.get("judgment_nodes", []):
                if not isinstance(entry, dict):
                    continue
                page_id = str(entry.get("page_id") or "")
                if not page_id:
                    continue
                payload_json = _json_dumps(entry)
                judgment_rows.append((page_id, None, _payload_hash(entry), payload_json))
            _upsert_json_rows(
                connection,
                "cache_judgment_summary",
                key_column="page_id",
                kind_column=None,
                rows=judgment_rows,
            )
            _delete_missing_rows(connection, "cache_judgment_summary", "page_id", {row[0] for row in judgment_rows})

            archive_rows = []
            for entry in archive_candidates.get("entries", []):
                if not isinstance(entry, dict):
                    continue
                entry_id = str(entry.get("entry_id") or "")
                if not entry_id:
                    continue
                payload_json = _json_dumps(entry)
                archive_rows.append((entry_id, None, _payload_hash(entry), payload_json))
            _upsert_json_rows(
                connection,
                "cache_archive_candidates",
                key_column="entry_id",
                kind_column=None,
                rows=archive_rows,
            )
            _delete_missing_rows(connection, "cache_archive_candidates", "entry_id", {row[0] for row in archive_rows})

            health = memory.get("health", {})
            health_rows = []
            for key in (
                "components",
                "source_component_ids",
                "concept_component_ids",
                "repair_plan",
                "actions",
                "bridge_concept_slugs",
            ):
                payload = health.get(key)
                payload_json = _json_dumps(payload)
                health_rows.append((key, None, _payload_hash(payload), payload_json))
            _upsert_json_rows(
                connection,
                "cache_health",
                key_column="key",
                kind_column=None,
                rows=health_rows,
            )
            _delete_missing_rows(connection, "cache_health", "key", {row[0] for row in health_rows})

            _write_meta(connection, "schema_version", str(CACHE_SCHEMA_VERSION))
            _write_meta(connection, "memory_hash", memory_hash)
            _write_meta(connection, "compiled_at", compiled_at)
            connection.commit()

            row_counts = _cache_row_counts(connection)
            status = load_cache_status(root)
            stats = dict(status.get("stats", {}))
            stats["compile_syncs"] = int(stats.get("compile_syncs", 0) or 0) + 1
            if rebuild_reason and rebuild_reason != "initial-sync":
                stats["rebuilds"] = int(stats.get("rebuilds", 0) or 0) + 1
            updated_at = utc_now()
            last_rebuild = (
                {
                    "updated_at": updated_at,
                    "reason": rebuild_reason,
                    "schema_version": CACHE_SCHEMA_VERSION,
                }
                if rebuild_reason
                else dict(status.get("last_rebuild", {}))
            )
            document = _save_live_cache_status(
                root,
                connection,
                enabled=True,
                stats=stats,
                last_sync={
                    "compiled_at": compiled_at,
                    "updated_at": updated_at,
                    "memory_hash": memory_hash,
                    "rebuild": rebuild_required,
                    "rebuild_reason": rebuild_reason,
                },
                last_query=dict(status.get("last_query", {})),
                last_drop=dict(status.get("last_drop", {})),
                last_rebuild=last_rebuild,
            )
            document["row_counts"] = row_counts
            return document
        except (sqlite3.Error, OSError, json.JSONDecodeError, TypeError) as exc:
            _log_cache_fault("sync", exc)
            return load_cache_status(root)
        finally:
            if connection is not None:
                connection.close()


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
        edges_rows = connection.execute("SELECT edge_key, edge_kind, payload_json FROM cache_edges ORDER BY edge_key").fetchall()
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
            "repair_plan": health_map.get("repair_plan", {}),
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


def _merge_cache_status(root: Path, *, stats_delta: dict[str, int] | None = None, last_query: dict[str, Any] | None = None, last_drop: dict[str, Any] | None = None) -> dict[str, Any]:
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


def query_cache_key(*, question: str, protocol: str) -> str:
    normalized = f"{protocol}\n{' '.join(question.split())}"
    return f"sha256:{sha256_bytes(normalized.encode('utf-8'))}"


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


__all__ = [
    "CACHE_SCHEMA_VERSION",
    "cache_status_summary",
    "drop_query_cache",
    "force_rebuild_query_cache",
    "load_cached_query_result",
    "load_query_cache_snapshot",
    "query_cache_memory_hash",
    "query_cache_key",
    "record_query_cache_event",
    "save_cached_query_result",
    "sync_query_cache",
]
