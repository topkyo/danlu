"""Machine-memory query / traversal surfaces.

EP-017B step 2: extracted from memory/graph.py. Holds the query JSON builder
and its cache-aware public entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..cache.query import (
    load_cached_query_result,
    load_query_cache_snapshot,
    query_cache_key,
    save_cached_query_result,
)
from ..cache.status import record_query_cache_event
from ..cache.sync import query_cache_memory_hash
from ..memory.query_routes import (
    _machine_memory_query_payload_hash,
    build_machine_memory_adjacency,
    select_machine_memory_query_strategy,
)
from ..memory.source_records import machine_memory_source_runtime_record
from ..protocol.focus_scoring import action_focus_score
from ..protocol.runtime_config import PENDING_ACTION_STATUSES
from ..state.constants import DEFAULT_PROTOCOL
from ..utils.hash import question_signature
from ..utils.text import tokenize
from .action_core import action_priority_rank
from .scoring import machine_memory_query_time_focus


def _build_machine_memory_query_json(
    memory: dict[str, Any],
    question: str,
    *,
    root: Path | None = None,
    protocol: str = DEFAULT_PROTOCOL,
    material_state: dict[str, Any] | None = None,
    routing_state: dict[str, Any] | None = None,
    archive_candidates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    term_index = memory.get("term_index", {})
    edges = memory.get("edges", {})
    source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    question_tokens = tokenize(question)
    health = memory.get("health", {})
    adjacency = build_machine_memory_adjacency(memory)
    material_state = material_state or {"entries": []}
    routing_state = routing_state or {"entries": []}
    archive_candidates = archive_candidates or {"entries": []}
    material_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in material_state.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    routing_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in routing_state.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    archive_candidates_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in archive_candidates.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    time_focus_state = machine_memory_query_time_focus(question)
    time_focus = str(time_focus_state.get("focus") or "")

    direct_source_scores: dict[str, int] = {}
    direct_concept_scores: dict[str, int] = {}
    direct_judgment_scores: dict[str, int] = {}
    direct_elixir_scores: dict[str, int] = {}
    matched_terms: list[str] = []

    confirmed_judgment_nodes = {
        str(node.get("page_id") or ""): node
        for node in memory.get("judgment_nodes", [])
        if isinstance(node, dict)
        and str(node.get("kind") or "") == "judgment"
        and str(node.get("status") or "") == "confirmed"
        and node.get("page_id")
    }
    elixir_nodes = {
        str(node.get("elixir_id") or ""): node
        for node in memory.get("elixir_nodes", [])
        if isinstance(node, dict) and node.get("elixir_id")
    }

    source_to_concepts: dict[str, set[str]] = {}
    concept_to_sources: dict[str, set[str]] = {}
    for edge in edges.get("source_to_concept", []):
        source_id = edge.get("source_id")
        concept_slug = edge.get("concept_slug")
        if not isinstance(source_id, str) or not isinstance(concept_slug, str):
            continue
        source_to_concepts.setdefault(source_id, set()).add(concept_slug)
        concept_to_sources.setdefault(concept_slug, set()).add(source_id)

    related_concepts: dict[str, set[str]] = {}
    for edge in edges.get("concept_to_concept", []):
        left = edge.get("from")
        right = edge.get("to")
        if not isinstance(left, str) or not isinstance(right, str):
            continue
        related_concepts.setdefault(left, set()).add(right)
        related_concepts.setdefault(right, set()).add(left)

    for token in question_tokens:
        payload = term_index.get(token)
        if not isinstance(payload, dict):
            continue
        matched_terms.append(token)
        for source_id in payload.get("source_ids", []):
            if source_id in source_nodes:
                direct_source_scores[source_id] = direct_source_scores.get(source_id, 0) + 3
        for concept_slug in payload.get("concept_slugs", []):
            if concept_slug in concept_nodes:
                direct_concept_scores[concept_slug] = direct_concept_scores.get(concept_slug, 0) + 4
        for page_id in payload.get("judgment_page_ids", []):
            if page_id in confirmed_judgment_nodes:
                direct_judgment_scores[page_id] = direct_judgment_scores.get(page_id, 0) + 5
        for elixir_id in payload.get("elixir_ids", []):
            if elixir_id in elixir_nodes:
                direct_elixir_scores[elixir_id] = direct_elixir_scores.get(elixir_id, 0) + 6

    route_strategy = select_machine_memory_query_strategy(
        question,
        direct_source_scores=direct_source_scores,
        direct_concept_scores=direct_concept_scores,
        protocol=protocol,
        root=root,
    )
    selected_strategy = str(route_strategy.get("selected_strategy") or "concept-first")

    expanded_source_scores = dict(direct_source_scores)
    expanded_concept_scores = dict(direct_concept_scores)
    expanded_judgment_scores = dict(direct_judgment_scores)
    expanded_elixir_scores = dict(direct_elixir_scores)
    supporting_edges: set[tuple[str, str, str]] = set()

    for source_id in list(direct_source_scores):
        for concept_slug in sorted(source_to_concepts.get(source_id, set())):
            expanded_concept_scores[concept_slug] = expanded_concept_scores.get(concept_slug, 0) + 2
            supporting_edges.add(("HAS_CONCEPT", source_id, concept_slug))

    for concept_slug in list(direct_concept_scores):
        for source_id in sorted(concept_to_sources.get(concept_slug, set())):
            expanded_source_scores[source_id] = expanded_source_scores.get(source_id, 0) + 2
            supporting_edges.add(("HAS_CONCEPT", source_id, concept_slug))
        for related_slug in sorted(related_concepts.get(concept_slug, set())):
            expanded_concept_scores[related_slug] = expanded_concept_scores.get(related_slug, 0) + 1
            supporting_edges.add(("RELATED_CONCEPT", concept_slug, related_slug))
            for source_id in sorted(concept_to_sources.get(related_slug, set())):
                expanded_source_scores[source_id] = expanded_source_scores.get(source_id, 0) + 1
                supporting_edges.add(("HAS_CONCEPT", source_id, related_slug))

    from ..memory.query_routes import build_machine_memory_query_routes

    query_routes = build_machine_memory_query_routes(
        memory,
        adjacency,
        direct_source_scores,
        direct_concept_scores,
        expanded_source_scores,
        expanded_concept_scores,
        strategy=selected_strategy,
    )
    for route in query_routes:
        for node in route["nodes"]:
            if node.get("kind") == "source":
                source_id = str(node.get("id") or "")
                if source_id:
                    expanded_source_scores[source_id] = expanded_source_scores.get(source_id, 0) + 2
                continue
            if node.get("kind") == "concept":
                concept_slug = str(node.get("slug") or "")
                if concept_slug:
                    expanded_concept_scores[concept_slug] = expanded_concept_scores.get(concept_slug, 0) + 2
        for edge in route["edges"]:
            if edge["type"] == "HAS_CONCEPT":
                supporting_edges.add(("HAS_CONCEPT", edge["left"], edge["right"]))
            elif edge["type"] == "RELATED_CONCEPT":
                supporting_edges.add(("RELATED_CONCEPT", edge["left"], edge["right"]))

    for source_id in list(expanded_source_scores):
        for edge in edges.get("source_to_judgment", []):
            page_id = str(edge.get("page_id") or "")
            if str(edge.get("source_id") or "") != source_id or page_id not in confirmed_judgment_nodes:
                continue
            expanded_judgment_scores[page_id] = expanded_judgment_scores.get(page_id, 0) + 3
            supporting_edges.add(("SUPPORTS_JUDGMENT", source_id, page_id))

    for page_id in list(expanded_judgment_scores):
        for edge in edges.get("judgment_to_judgment", []):
            related_id = ""
            if str(edge.get("from") or "") == page_id:
                related_id = str(edge.get("to") or "")
            elif str(edge.get("to") or "") == page_id:
                related_id = str(edge.get("from") or "")
            if related_id and related_id in confirmed_judgment_nodes:
                expanded_judgment_scores[related_id] = expanded_judgment_scores.get(related_id, 0) + 1
                supporting_edges.add(("JUDGMENT_RELATED", page_id, related_id))

    for edge in edges.get("elixir_derived_from", []):
        elixir_id = str(edge.get("elixir_id") or "")
        from_kind = str(edge.get("from_kind") or "")
        from_id = str(edge.get("from_id") or "")
        if not elixir_id or elixir_id not in elixir_nodes:
            continue
        if from_kind == "source" and from_id not in expanded_source_scores:
            continue
        if from_kind == "judgment" and from_id not in expanded_judgment_scores:
            continue
        if from_kind == "elixir" and from_id not in expanded_elixir_scores:
            continue
        if from_kind not in {"source", "judgment", "elixir"}:
            continue
        expanded_elixir_scores[elixir_id] = expanded_elixir_scores.get(elixir_id, 0) + 3
        supporting_edges.add(("ELIXIR_DERIVED_FROM", from_id, elixir_id))

    source_rank_records = [
        machine_memory_source_runtime_record(
            source_id,
            base_score=base_score,
            source_nodes=source_nodes,
            material_by_entry=material_by_entry,
            routing_by_entry=routing_by_entry,
            archive_candidates_by_entry=archive_candidates_by_entry,
            protocol=protocol,
            time_focus=time_focus,
        )
        for source_id, base_score in expanded_source_scores.items()
        if source_id in source_nodes
    ]
    source_rank_records.sort(
        key=lambda item: (
            -float(item.get("combined_score", 0.0) or 0.0),
            -float(item.get("base_score", 0.0) or 0.0),
            -float(item.get("protocol_bonus", 0.0) or 0.0),
            -float(item.get("time_bonus", 0.0) or 0.0),
            str(item.get("title") or item.get("entry_id") or "").lower(),
        )
    )
    ranked_source_ids = [str(item.get("entry_id") or "") for item in source_rank_records[:8] if item.get("entry_id")]
    ranked_concept_slugs = [
        concept_slug
        for concept_slug, _score in sorted(
            expanded_concept_scores.items(),
            key=lambda item: (-item[1], concept_nodes.get(item[0], {}).get("title", item[0]).lower()),
        )[:8]
    ]
    ranked_judgment_ids = [
        page_id
        for page_id, _score in sorted(
            expanded_judgment_scores.items(),
            key=lambda item: (
                -item[1],
                -int(confirmed_judgment_nodes.get(item[0], {}).get("asset_score", 0) or 0),
                confirmed_judgment_nodes.get(item[0], {}).get("title", item[0]).lower(),
            ),
        )[:8]
        if page_id in confirmed_judgment_nodes
    ]
    ranked_elixir_ids = [
        elixir_id
        for elixir_id, _score in sorted(
            expanded_elixir_scores.items(),
            key=lambda item: (-item[1], elixir_nodes.get(item[0], {}).get("title", item[0]).lower()),
        )[:8]
        if elixir_id in elixir_nodes
    ]
    bridge_concept_slugs = [
        slug for slug in ranked_concept_slugs if slug in set(health.get("bridge_concept_slugs", []))
    ]
    protocol_shard_source_ids = [
        str(item.get("entry_id") or "")
        for item in source_rank_records
        if bool(item.get("protocol_shard")) and item.get("entry_id")
    ][:5]
    time_shard_source_ids = [
        str(item.get("entry_id") or "")
        for item in source_rank_records
        if bool(item.get("time_shard")) and item.get("entry_id")
    ][:5]
    archive_recall_hints = [
        {
            "entry_id": str(item.get("entry_id") or ""),
            "title": str(item.get("title") or item.get("entry_id") or ""),
            "path": str(item.get("path") or ""),
            "temperature": str(item.get("temperature") or ""),
            "archive_status": str(item.get("archive_status") or ""),
            "recommended_temperature": str(item.get("recommended_temperature") or ""),
            "reason_codes": list(item.get("reason_codes", []) or []),
        }
        for item in sorted(
            source_rank_records,
            key=lambda record: (
                -float(record.get("archive_hint_score", 0.0) or 0.0),
                -float(record.get("combined_score", 0.0) or 0.0),
                str(record.get("title") or record.get("entry_id") or "").lower(),
            ),
        )
        if bool(item.get("archive_hint")) and item.get("entry_id")
    ][:3]
    query_subgraph_sources = [
        {
            "id": source_id,
            "title": source_nodes[source_id]["title"],
            "path": source_nodes[source_id]["source_page"],
        }
        for source_id in ranked_source_ids
        if source_id in source_nodes
    ]
    query_subgraph_concepts = [
        {
            "slug": concept_slug,
            "title": concept_nodes[concept_slug]["title"],
            "path": f"wiki/concepts/{concept_slug}.md",
        }
        for concept_slug in ranked_concept_slugs
        if concept_slug in concept_nodes
    ]
    query_subgraph_judgments = [
        {
            "page_id": page_id,
            "title": confirmed_judgment_nodes[page_id]["title"],
            "path": confirmed_judgment_nodes[page_id]["path"],
        }
        for page_id in ranked_judgment_ids
        if page_id in confirmed_judgment_nodes
    ]
    query_subgraph_elixirs = [
        {
            "elixir_id": elixir_id,
            "title": elixir_nodes[elixir_id]["title"],
            "path": elixir_nodes[elixir_id]["path"],
        }
        for elixir_id in ranked_elixir_ids
        if elixir_id in elixir_nodes
    ]
    query_subgraph_edges = [
        {"type": edge_type, "left": left, "right": right}
        for edge_type, left, right in sorted(supporting_edges)
        if (edge_type == "HAS_CONCEPT" and left in ranked_source_ids and right in ranked_concept_slugs)
        or (edge_type == "RELATED_CONCEPT" and left in ranked_concept_slugs and right in ranked_concept_slugs)
    ]
    touched_component_ids = sorted(
        {
            component_id
            for component_id in (
                [health.get("source_component_ids", {}).get(source_id) for source_id in ranked_source_ids]
                + [health.get("concept_component_ids", {}).get(slug) for slug in ranked_concept_slugs]
            )
            if component_id
        }
    )
    touched_components = [
        component for component in health.get("components", []) if component.get("id") in touched_component_ids
    ]
    proposal_by_action_id = {
        str(proposal.get("action_id") or ""): proposal
        for proposal in health.get("repair_plan", {}).get("execution_proposals", [])
        if proposal.get("action_id")
    }
    action_by_id = {
        str(action.get("id") or ""): action
        for action in health.get("actions", [])
        if isinstance(action, dict) and action.get("id")
    }
    relevant_actions: list[dict[str, Any]] = []
    ranked_source_set = set(ranked_source_ids) | set(direct_source_scores)
    ranked_concept_set = set(ranked_concept_slugs) | set(direct_concept_scores)

    def action_hits(action: dict[str, Any]) -> bool:
        source_hit = bool(
            ranked_source_set & {str(item) for item in action.get("source_ids", []) if isinstance(item, str)}
        )
        concept_hit = bool(
            ranked_concept_set & {str(item) for item in action.get("concept_slugs", []) if isinstance(item, str)}
        )
        component_hit = bool(action.get("component_id")) and action.get("component_id") in touched_component_ids
        return source_hit or concept_hit or component_hit

    for action in health.get("actions", []):
        if action.get("status") not in PENDING_ACTION_STATUSES:
            continue
        if not action_hits(action):
            continue
        proposal = proposal_by_action_id.get(str(action.get("id") or ""), {})
        relevant_actions.append(
            {
                "id": action["id"],
                "kind": action["kind"],
                "priority": action["priority"],
                "status": action.get("status", "proposed"),
                "title": action["title"],
                "primary_path": action["primary_path"],
                "secondary_path": action.get("secondary_path", ""),
                "reason": action.get("reason", ""),
                "execution_policy": action.get("execution_policy", "triage"),
                "next_step": action.get("next_step", ""),
                "command_hint": action.get("command_hint", ""),
                "apply_ready": action.get("apply_ready", "false"),
                "proposal_kind": proposal.get("proposal_kind", ""),
                "proposal_summary": proposal.get("summary", ""),
                "proposal_targets": proposal.get("target_paths", []),
                "focus_score": action_focus_score(protocol, action),
            }
        )
    relevant_actions.sort(
        key=lambda item: (
            0 if item.get("status") == "accepted" else 1,
            -int(item.get("focus_score", 0)),
            action_priority_rank(str(item.get("priority") or "")),
            str(item.get("title") or "").lower(),
        )
    )
    planner_state = dict(health.get("repair_plan", {}).get("planner_state") or {})
    planner_queue: list[dict[str, Any]] = []
    for item in planner_state.get("priority_queue", []):
        if not isinstance(item, dict):
            continue
        linked_action = action_by_id.get(str(item.get("action_id") or ""), {})
        if linked_action and not action_hits(linked_action) and planner_queue:
            continue
        planner_queue.append(
            {
                "action_id": str(item.get("action_id") or ""),
                "title": str(item.get("title") or item.get("action_id") or ""),
                "priority": str(item.get("priority") or "medium"),
                "status": str(item.get("status") or "proposed"),
                "priority_score": int(item.get("priority_score", 0) or 0),
                "impact_score": int(item.get("impact_score", 0) or 0),
                "blocked": bool(item.get("blocked", False)),
                "depends_on": [str(dep) for dep in item.get("depends_on", []) if isinstance(dep, str) and dep],
            }
        )
        if len(planner_queue) >= 4:
            break
    planner_next_action = (
        planner_queue[0]
        if planner_queue
        else dict(planner_state.get("next_action") or {})
        if isinstance(planner_state.get("next_action"), dict)
        else {}
    )
    route_telemetry = {
        "query_signature": question_signature(question),
        "protocol": protocol,
        "selected_strategy": selected_strategy,
        "selection_reason": str(route_strategy.get("selection_reason") or ""),
        "matched_source_markers": list(route_strategy.get("matched_source_markers", []) or []),
        "matched_graph_markers": list(route_strategy.get("matched_graph_markers", []) or []),
        "route_count": len(query_routes),
        "matched_terms": matched_terms[:8],
        "ranked_source_ids": ranked_source_ids[:5],
        "ranked_concept_slugs": ranked_concept_slugs[:5],
        "ranked_judgment_ids": ranked_judgment_ids[:5],
        "ranked_elixir_ids": ranked_elixir_ids[:5],
        "touched_component_ids": touched_component_ids[:5],
        "planner_next_action_id": str(planner_next_action.get("action_id") or ""),
    }

    return {
        "matched_terms": matched_terms,
        "direct_source_ids": sorted(direct_source_scores),
        "direct_concept_slugs": sorted(direct_concept_scores),
        "direct_judgment_ids": sorted(direct_judgment_scores),
        "direct_elixir_ids": sorted(direct_elixir_scores),
        "time_focus": time_focus,
        "time_focus_markers": list(time_focus_state.get("markers", []) or []),
        "route_config": dict(route_strategy.get("config") or {}),
        "selected_strategy": selected_strategy,
        "selection_reason": str(route_strategy.get("selection_reason") or ""),
        "matched_source_markers": list(route_strategy.get("matched_source_markers", []) or []),
        "matched_graph_markers": list(route_strategy.get("matched_graph_markers", []) or []),
        "ranked_source_ids": ranked_source_ids,
        "ranked_concept_slugs": ranked_concept_slugs,
        "ranked_judgment_ids": ranked_judgment_ids,
        "ranked_elixir_ids": ranked_elixir_ids,
        "protocol_shard_source_ids": protocol_shard_source_ids,
        "time_shard_source_ids": time_shard_source_ids,
        "archive_recall_hints": archive_recall_hints,
        "bridge_concept_slugs": bridge_concept_slugs,
        "supporting_edges": [
            {"type": edge_type, "left": left, "right": right} for edge_type, left, right in sorted(supporting_edges)
        ],
        "query_routes": query_routes,
        "touched_component_ids": touched_component_ids,
        "touched_components": touched_components,
        "relevant_actions": relevant_actions[:6],
        "planner_priority_queue": planner_queue,
        "planner_next_action": planner_next_action,
        "route_telemetry": route_telemetry,
        "query_subgraph": {
            "sources": query_subgraph_sources,
            "concepts": query_subgraph_concepts,
            "judgments": query_subgraph_judgments,
            "elixirs": query_subgraph_elixirs,
            "edges": query_subgraph_edges,
        },
    }


def build_machine_memory_query(
    memory: dict[str, Any],
    question: str,
    *,
    root: Path | None = None,
    protocol: str = DEFAULT_PROTOCOL,
    material_state: dict[str, Any] | None = None,
    routing_state: dict[str, Any] | None = None,
    archive_candidates: dict[str, Any] | None = None,
    no_cache: bool = False,
) -> dict[str, Any]:
    material_state = material_state or {"entries": []}
    routing_state = routing_state or {"entries": []}
    archive_candidates = archive_candidates or {"entries": []}
    payload_hash = _machine_memory_query_payload_hash(
        memory=memory,
        question=question,
        protocol=protocol,
        material_state=material_state,
        routing_state=routing_state,
        archive_candidates=archive_candidates,
    )
    query_key = query_cache_key(question=question, protocol=protocol)
    if root is not None and no_cache:
        record_query_cache_event(
            root,
            hit=False,
            bypass=True,
            query_key=query_key,
            payload_hash=payload_hash,
            reason="no-cache",
        )
    if root is not None and not no_cache:
        cached_result = load_cached_query_result(root, query_key, payload_hash)
        if cached_result is not None:
            record_query_cache_event(
                root,
                hit=True,
                query_key=query_key,
                payload_hash=payload_hash,
                reason="query-result",
            )
            return cached_result
        snapshot = load_query_cache_snapshot(root)
        if snapshot is not None:
            cached_memory = snapshot.get("memory")
            cached_memory_hash = str(snapshot.get("memory_hash") or "")
            if isinstance(cached_memory, dict) and cached_memory_hash == query_cache_memory_hash(memory):
                result = _build_machine_memory_query_json(
                    cached_memory,
                    question,
                    root=root,
                    protocol=protocol,
                    material_state=material_state,
                    routing_state=routing_state,
                    archive_candidates=archive_candidates,
                )
                save_cached_query_result(root, query_key, payload_hash, result)
                record_query_cache_event(
                    root,
                    hit=False,
                    query_key=query_key,
                    payload_hash=payload_hash,
                    reason="snapshot-rebuild",
                )
                return result

    result = _build_machine_memory_query_json(
        memory,
        question,
        root=root,
        protocol=protocol,
        material_state=material_state,
        routing_state=routing_state,
        archive_candidates=archive_candidates,
    )
    if root is not None and not no_cache:
        save_cached_query_result(root, query_key, payload_hash, result)
        record_query_cache_event(
            root,
            hit=False,
            query_key=query_key,
            payload_hash=payload_hash,
            reason="json-fallback",
        )
    return result
