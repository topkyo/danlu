"""Protocol relevance helpers for knowledge lifecycle entries."""

from __future__ import annotations

from typing import Any

from ..content.archive import default_material_routing_state
from ..content.io import routing_snapshot_for_protocol
from .knowledge import (
    default_knowledge_lifecycle_state,
    select_knowledge_lifecycle_entries,
    sort_knowledge_lifecycle_entries,
)


def concept_protocol_relevance_for_source(
    source_id: str,
    *,
    protocol: str,
    routing_by_entry_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    routing_entry = routing_by_entry_id.get(source_id, {})
    if not isinstance(routing_entry, dict):
        return {}
    top_protocols = [
        str(item.get("protocol") or "")
        for item in routing_entry.get("top_protocols", [])
        if isinstance(item, dict) and str(item.get("protocol") or "")
    ]
    if protocol not in top_protocols[:2]:
        return {}
    routing_snapshot = routing_snapshot_for_protocol(routing_entry, protocol)
    if not routing_snapshot:
        return {}
    selected_as = str(routing_snapshot.get("selected_as") or "")
    if top_protocols[:1] == [protocol]:
        mode = "source-top1"
    elif bool(routing_entry.get("cross_protocol_bridge")) and selected_as in {"hot-evidence", "warm-evidence"}:
        mode = "cross-protocol-bridge"
    elif selected_as in {"hot-evidence", "warm-evidence"}:
        mode = "strong-top2"
    else:
        return {}
    return {
        "source_id": source_id,
        "mode": mode,
        "selected_as": selected_as,
        "total_score": float(routing_snapshot.get("total_score", 0.0) or 0.0),
    }


def concept_protocol_relevance(
    entry: dict[str, Any],
    *,
    protocol: str,
    routing_by_entry_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_ids = [str(item) for item in entry.get("source_ids", []) if isinstance(item, str) and item]
    if not source_ids:
        return {"related": False, "primary_mode": "", "modes": [], "source_ids": []}
    mode_rank = {"source-top1": 0, "cross-protocol-bridge": 1, "strong-top2": 2}
    matched_sources = [
        match
        for match in (
            concept_protocol_relevance_for_source(
                source_id,
                protocol=protocol,
                routing_by_entry_id=routing_by_entry_id,
            )
            for source_id in source_ids
        )
        if match
    ]
    if not matched_sources:
        return {"related": False, "primary_mode": "", "modes": [], "source_ids": []}
    matched_sources.sort(
        key=lambda item: (
            mode_rank.get(str(item.get("mode") or ""), 9),
            -float(item.get("total_score", 0.0) or 0.0),
            str(item.get("source_id") or ""),
        )
    )
    modes: list[str] = []
    matched_source_ids: list[str] = []
    for item in matched_sources:
        mode = str(item.get("mode") or "")
        source_id = str(item.get("source_id") or "")
        if mode and mode not in modes:
            modes.append(mode)
        if source_id and source_id not in matched_source_ids:
            matched_source_ids.append(source_id)
    return {
        "related": True,
        "primary_mode": modes[0] if modes else "",
        "modes": modes,
        "source_ids": matched_source_ids,
    }


def concept_protocol_ambiguity_state(modes: list[str]) -> str:
    normalized = [str(item) for item in modes if isinstance(item, str) and item]
    if "cross-protocol-bridge" in normalized:
        return "bridge"
    if normalized == ["source-top1"]:
        return "dominant"
    return "mixed"


def concept_lifecycle_matches_protocol(
    entry: dict[str, Any],
    *,
    protocol: str,
    routing_by_entry_id: dict[str, dict[str, Any]],
) -> bool:
    return bool(
        concept_protocol_relevance(
            entry,
            protocol=protocol,
            routing_by_entry_id=routing_by_entry_id,
        ).get("related")
    )


def protocol_related_concept_lifecycle_summary(
    knowledge_lifecycle: dict[str, Any] | None,
    material_routing: dict[str, Any] | None,
    *,
    protocol: str,
) -> dict[str, Any]:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    material_routing = material_routing or default_material_routing_state()
    routing_by_entry_id = {
        str(entry.get("entry_id") or ""): entry
        for entry in material_routing.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    mode_counts = {
        "source-top1": 0,
        "strong-top2": 0,
        "cross-protocol-bridge": 0,
    }
    ambiguity_counts = {
        "dominant": 0,
        "mixed": 0,
        "bridge": 0,
    }
    related_entries: list[dict[str, Any]] = []
    for entry in select_knowledge_lifecycle_entries(knowledge_lifecycle, kinds={"concept"}):
        relevance = concept_protocol_relevance(entry, protocol=protocol, routing_by_entry_id=routing_by_entry_id)
        if not relevance.get("related"):
            continue
        primary_mode = str(relevance.get("primary_mode") or "")
        ambiguity = concept_protocol_ambiguity_state(list(relevance.get("modes", [])))
        if primary_mode in mode_counts:
            mode_counts[primary_mode] += 1
        if ambiguity in ambiguity_counts:
            ambiguity_counts[ambiguity] += 1
        related_entries.append(
            {
                **entry,
                "protocol_relevance_primary_mode": primary_mode,
                "protocol_relevance_modes": list(relevance.get("modes", [])),
                "protocol_relevance_source_ids": list(relevance.get("source_ids", [])),
                "protocol_relevance_ambiguity": ambiguity,
            }
        )
    related_concepts = sort_knowledge_lifecycle_entries(related_entries, active_protocol=protocol)
    concept_backlog = [
        entry for entry in related_concepts if str(entry.get("lifecycle_state") or "") in {"review", "revisit"}
    ]
    review_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "review"]
    revisit_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "revisit"]
    retired_concepts = [entry for entry in related_concepts if str(entry.get("lifecycle_state") or "") == "retired"]
    ambiguity_watchlist = [
        entry
        for entry in related_concepts
        if str(entry.get("protocol_relevance_ambiguity") or "") in {"mixed", "bridge"}
    ]
    mixed_concepts = [
        entry for entry in ambiguity_watchlist if str(entry.get("protocol_relevance_ambiguity") or "") == "mixed"
    ]
    bridge_concepts = [
        entry for entry in ambiguity_watchlist if str(entry.get("protocol_relevance_ambiguity") or "") == "bridge"
    ]
    return {
        "concept_backlog": concept_backlog,
        "review_concepts": review_concepts,
        "revisit_concepts": revisit_concepts,
        "retired_concepts": retired_concepts,
        "ambiguity_watchlist": ambiguity_watchlist,
        "mixed_concepts": mixed_concepts,
        "bridge_concepts": bridge_concepts,
        "counts": {
            "related_concepts": len(related_concepts),
            "concept_backlog": len(concept_backlog),
            "review_concepts": len(review_concepts),
            "revisit_concepts": len(revisit_concepts),
            "retired_concepts": len(retired_concepts),
            "active_concepts": sum(
                1 for entry in related_concepts if str(entry.get("lifecycle_state") or "") == "active"
            ),
            "direct_related_concepts": mode_counts["source-top1"],
            "secondary_related_concepts": mode_counts["strong-top2"],
            "bridge_related_concepts": mode_counts["cross-protocol-bridge"],
            "dominant_related_concepts": ambiguity_counts["dominant"],
            "mixed_related_concepts": ambiguity_counts["mixed"],
            "ambiguity_bridge_concepts": ambiguity_counts["bridge"],
        },
        "inference_mode": "source-top1-plus-strong-top2-plus-cross-protocol-bridge",
        "ambiguity_mode": "dominant-vs-mixed-vs-bridge",
    }
