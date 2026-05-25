"""Small machine-memory core helpers."""

from __future__ import annotations

import json
from typing import Any

from ..app_utils import sha256_bytes


def machine_memory_snapshot_is_reusable(memory: dict[str, Any]) -> bool:
    return (
        isinstance(memory.get("source_nodes"), list)
        and isinstance(memory.get("concept_nodes"), list)
        and isinstance(memory.get("edges"), dict)
        and isinstance(memory.get("citation_map"), list)
        and isinstance(memory.get("term_index"), dict)
        and isinstance(memory.get("drift"), dict)
    )


def reuse_machine_memory_core(previous: dict[str, Any], compiled_at: str) -> dict[str, Any]:
    return {
        "version": int(previous.get("version", 1) or 1),
        "compiled_at": compiled_at,
        "source_nodes": list(previous.get("source_nodes", [])),
        "concept_nodes": list(previous.get("concept_nodes", [])),
        "edges": dict(previous.get("edges", {})),
        "citation_map": list(previous.get("citation_map", [])),
        "term_index": dict(previous.get("term_index", {})),
        "drift": dict(previous.get("drift", {})),
    }


def machine_memory_digest(memory: dict[str, Any]) -> str:
    payload = {
        "source_nodes": memory.get("source_nodes", []),
        "concept_nodes": memory.get("concept_nodes", []),
        "judgment_nodes": memory.get("judgment_nodes", []),
        "edges": memory.get("edges", {}),
        "citation_map": memory.get("citation_map", []),
        "term_index": memory.get("term_index", {}),
        "drift": memory.get("drift", {}),
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))
