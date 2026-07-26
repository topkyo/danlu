"""Machine-memory transition / history surfaces.

EP-017B step 2: extracted from memory/graph.py. Holds the transition diff
summarizer and the history-append helper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..utils.io import atomic_append_jsonl
from .paths import machine_memory_history_path


def _judgment_relation_edge_signatures(memory: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    return {
        ("JUDGMENT_RELATION", str(edge.get("relation") or "related"), edge["from"], edge["to"])
        for edge in memory.get("edges", {}).get("judgment_to_judgment", [])
    } | {
        ("DECISION_RELATION", str(edge.get("relation") or "supports"), edge["from"], edge["to"])
        for edge in memory.get("edges", {}).get("judgment_to_decision", [])
    }


def summarize_machine_memory_transition(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_source_ids = {node["id"] for node in previous.get("source_nodes", [])}
    current_source_ids = {node["id"] for node in current.get("source_nodes", [])}
    previous_concept_slugs = {node["slug"] for node in previous.get("concept_nodes", [])}
    current_concept_slugs = {node["slug"] for node in current.get("concept_nodes", [])}
    previous_judgment_ids = {node["page_id"] for node in previous.get("judgment_nodes", [])}
    current_judgment_ids = {node["page_id"] for node in current.get("judgment_nodes", [])}
    previous_terms = set(previous.get("term_index", {}).keys())
    current_terms = set(current.get("term_index", {}).keys())
    previous_edges = (
        {
            ("HAS_CONCEPT", edge["source_id"], edge["concept_slug"])
            for edge in previous.get("edges", {}).get("source_to_concept", [])
        }
        | {
            ("SUPPORTS_JUDGMENT", edge["source_id"], edge["page_id"])
            for edge in previous.get("edges", {}).get("source_to_judgment", [])
        }
        | {
            ("RELATED_CONCEPT", edge["from"], edge["to"])
            for edge in previous.get("edges", {}).get("concept_to_concept", [])
        }
        | _judgment_relation_edge_signatures(previous)
    )
    current_edges = (
        {
            ("HAS_CONCEPT", edge["source_id"], edge["concept_slug"])
            for edge in current.get("edges", {}).get("source_to_concept", [])
        }
        | {
            ("SUPPORTS_JUDGMENT", edge["source_id"], edge["page_id"])
            for edge in current.get("edges", {}).get("source_to_judgment", [])
        }
        | {
            ("RELATED_CONCEPT", edge["from"], edge["to"])
            for edge in current.get("edges", {}).get("concept_to_concept", [])
        }
        | _judgment_relation_edge_signatures(current)
    )
    previous_digest = previous.get("digest", "")
    current_digest = current["digest"]
    return {
        "has_previous_snapshot": bool(previous_digest),
        "changed": previous_digest != current_digest,
        "previous_digest": previous_digest,
        "current_digest": current_digest,
        "added_source_ids": sorted(current_source_ids - previous_source_ids),
        "removed_source_ids": sorted(previous_source_ids - current_source_ids),
        "added_concept_slugs": sorted(current_concept_slugs - previous_concept_slugs),
        "removed_concept_slugs": sorted(previous_concept_slugs - current_concept_slugs),
        "added_judgment_ids": sorted(current_judgment_ids - previous_judgment_ids),
        "removed_judgment_ids": sorted(previous_judgment_ids - current_judgment_ids),
        "added_terms": sorted(current_terms - previous_terms)[:25],
        "removed_terms": sorted(previous_terms - current_terms)[:25],
        "added_edges": len(current_edges - previous_edges),
        "removed_edges": len(previous_edges - current_edges),
    }


def append_machine_memory_history(root: Path, memory: dict[str, Any], transition: dict[str, Any]) -> None:
    path = machine_memory_history_path(root)
    if transition["has_previous_snapshot"] and not transition["changed"]:
        return
    entry = {
        "compiled_at": memory["compiled_at"],
        "digest": memory["digest"],
        "sources": len(memory.get("source_nodes", [])),
        "concepts": len(memory.get("concept_nodes", [])),
        "judgments": len(memory.get("judgment_nodes", [])),
        "terms": len(memory.get("term_index", {})),
        "added_source_ids": transition["added_source_ids"],
        "removed_source_ids": transition["removed_source_ids"],
        "added_concept_slugs": transition["added_concept_slugs"],
        "removed_concept_slugs": transition["removed_concept_slugs"],
        "added_judgment_ids": transition["added_judgment_ids"],
        "removed_judgment_ids": transition["removed_judgment_ids"],
        "added_edges": transition["added_edges"],
        "removed_edges": transition["removed_edges"],
    }
    atomic_append_jsonl(path, entry)
