"""Memory hash computation and full cache synchronization."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..state.cache import load_cache_status
from ..utils.io import runtime_write_lock
from ..utils.time import utc_now
from .core import (
    CACHE_SCHEMA_VERSION,
    _cache_row_counts,
    _connect_cache,
    _delete_missing_rows,
    _drop_cache_tables,
    _initialize_schema,
    _json_dumps,
    _log_cache_fault,
    _payload_hash,
    _rebuild_reason,
    _upsert_json_rows,
    _write_meta,
)
from .status import _save_live_cache_status


def query_cache_memory_hash(memory: dict[str, Any]) -> str:
    edges = memory.get("edges", {})
    payload = {
        "compiled_at": str(memory.get("compiled_at") or ""),
        "source_nodes": memory.get("source_nodes", []),
        "concept_nodes": memory.get("concept_nodes", []),
        "judgment_nodes": memory.get("judgment_nodes", []),
        "elixir_nodes": memory.get("elixir_nodes", []),
        "edges": edges if isinstance(edges, dict) else {},
        "elixir_derived_from": (edges.get("elixir_derived_from", []) if isinstance(edges, dict) else []),
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
