"""SQLite engine primitives for the volatile query cache."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from ..utils.hash import sha256_bytes
from .paths import cache_db_path

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
