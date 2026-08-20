"""Pure concept / routing parse helpers shared by content and memory."""

from __future__ import annotations

from typing import Any

from ..protocol.runtime_config import CAUSAL_RELATION_TYPES, CONCEPT_HARDNESS_LEVELS
from ..utils.text import slugify


def concept_label_to_slug(label: str) -> str:
    return slugify(label)[:64]


def concept_source_pages(record: dict[str, Any]) -> list[str]:
    return [f"wiki/sources/{entry_id}.md" for entry_id in record["entry_ids"]]


def normalize_concept_hardness(value: Any, *, default: str = "soft") -> str:
    normalized_default = str(default).strip().lower()
    if normalized_default not in CONCEPT_HARDNESS_LEVELS:
        normalized_default = "soft"
    if not isinstance(value, str):
        return normalized_default
    normalized = value.strip().lower()
    if normalized in CONCEPT_HARDNESS_LEVELS:
        return normalized
    return normalized_default


def parse_causal_links(frontmatter: dict[str, Any]) -> list[dict[str, str]]:
    """Parse causal_links from concept frontmatter.

    Supports pipe-delimited flat format compatible with the line-based parser:
      causal_links:
        - "memory|enables|Agent relies on memory for cross-turn continuity"
    Returns validated list of {target, relation, evidence} dicts.
    """
    raw = frontmatter.get("causal_links", [])
    if not isinstance(raw, list):
        return []
    result: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            target = str(item.get("target") or "").strip()
            relation = str(item.get("relation") or "").strip().lower()
            evidence = str(item.get("evidence") or "").strip()
        elif isinstance(item, str) and "|" in item:
            parts = item.split("|", 2)
            target = parts[0].strip()
            relation = parts[1].strip().lower() if len(parts) > 1 else ""
            evidence = parts[2].strip() if len(parts) > 2 else ""
        else:
            continue
        if not target or relation not in CAUSAL_RELATION_TYPES:
            continue
        result.append({"target": target, "relation": relation, "evidence": evidence})
    return result


def routing_snapshot_for_protocol(routing_entry: dict[str, Any], protocol: str) -> dict[str, Any]:
    if not isinstance(routing_entry, dict):
        return {}
    if str(routing_entry.get("protocol") or "") == protocol:
        return routing_entry
    for snapshot in routing_entry.get("protocol_snapshots", []):
        if isinstance(snapshot, dict) and str(snapshot.get("protocol") or "") == protocol:
            return snapshot
    return {}
