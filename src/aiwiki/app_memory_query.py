"""Machine-memory query and routing helpers split from surfaces.

OWNER STATUS: legacy owner. New large logic blocks should be extracted to
`aiwiki.memory.*` rather than added here. See AGENTS.md migration policy.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

from .app_protocol import protocol_query_route_config
from .app_state import (
    DEFAULT_PROTOCOL,
    load_json_document,
    load_query_route_telemetry,
    load_runtime_history,
    query_route_telemetry_path,
    relative_path,
    save_query_route_telemetry,
)
from .app_utils import parse_frontmatter, question_signature, sha256_bytes, tokenize, utc_now
from .content.io import preserved_section


def fallback_query_route_config() -> dict[str, Any]:
    return {
        "default_strategy": "concept-first",
        "strategy_order": ["concept-first", "graph-walk", "source-first"],
        "source_markers": [],
        "graph_markers": [],
    }


def select_machine_memory_query_strategy(
    question: str,
    *,
    direct_source_scores: dict[str, int],
    direct_concept_scores: dict[str, int],
    protocol: str = DEFAULT_PROTOCOL,
    root: Path | None = None,
) -> dict[str, Any]:
    config = protocol_query_route_config(root, protocol) if root is not None else fallback_query_route_config()
    default_strategy = str(config.get("default_strategy") or "concept-first")
    strategy_order = [str(item) for item in config.get("strategy_order", []) if isinstance(item, str) and item]
    question_text = question.lower()
    matched_source_markers = [
        marker
        for marker in config.get("source_markers", [])
        if isinstance(marker, str) and marker and marker.lower() in question_text
    ]
    matched_graph_markers = [
        marker
        for marker in config.get("graph_markers", [])
        if isinstance(marker, str) and marker and marker.lower() in question_text
    ]
    selected_strategy = default_strategy
    selection_reason = "default-strategy"
    if matched_source_markers and not matched_graph_markers:
        selected_strategy = "source-first"
        selection_reason = "source-markers"
    elif matched_graph_markers and not matched_source_markers:
        selected_strategy = "graph-walk"
        selection_reason = "graph-markers"
    elif direct_source_scores and not direct_concept_scores:
        selected_strategy = "source-first"
        selection_reason = "direct-source-hit"
    elif direct_concept_scores and not direct_source_scores:
        selected_strategy = "concept-first"
        selection_reason = "direct-concept-hit"
    elif matched_graph_markers:
        selected_strategy = "graph-walk"
        selection_reason = "graph-markers"
    elif matched_source_markers:
        selected_strategy = "source-first"
        selection_reason = "source-markers"
    ordered_strategies = [selected_strategy]
    for item in strategy_order or fallback_query_route_config()["strategy_order"]:
        if item not in ordered_strategies:
            ordered_strategies.append(item)
    return {
        "config": config,
        "selected_strategy": selected_strategy,
        "selection_reason": selection_reason,
        "matched_source_markers": matched_source_markers[:4],
        "matched_graph_markers": matched_graph_markers[:4],
        "strategy_order": ordered_strategies,
    }


def _route_anchor_candidates(scores: dict[str, int], prefix: str, limit: int) -> list[str]:
    return [f"{prefix}:{item_id}" for item_id, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def _machine_memory_query_payload_hash(
    *,
    memory: dict[str, Any],
    question: str,
    protocol: str,
    material_state: dict[str, Any],
    routing_state: dict[str, Any],
    archive_candidates: dict[str, Any],
) -> str:
    payload = {
        "compiled_at": str(memory.get("compiled_at") or ""),
        "question": question,
        "protocol": protocol,
        "memory_digest": str(memory.get("digest") or ""),
        "memory_graph_digest": str(memory.get("graph_digest") or ""),
        "memory_source_count": len(memory.get("source_nodes", [])),
        "memory_concept_count": len(memory.get("concept_nodes", [])),
        "memory_judgment_count": len(memory.get("judgment_nodes", [])),
        "memory_elixir_count": len(memory.get("elixir_nodes", [])),
        "material_generated_at": str(material_state.get("generated_at") or ""),
        "material_entries": material_state.get("entries", []),
        "routing_computed_at": str(routing_state.get("computed_at") or ""),
        "routing_entries": routing_state.get("entries", []),
        "archive_generated_at": str(archive_candidates.get("generated_at") or ""),
        "archive_entries": archive_candidates.get("entries", []),
    }
    return f"sha256:{sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))}"


def build_machine_memory_adjacency(memory: dict[str, Any]) -> dict[str, dict[str, str]]:
    adjacency: dict[str, dict[str, str]] = {}
    for node in memory.get("source_nodes", []):
        adjacency.setdefault(f"source:{node['id']}", {})
    for node in memory.get("concept_nodes", []):
        adjacency.setdefault(f"concept:{node['slug']}", {})
    for node in memory.get("judgment_nodes", []):
        adjacency.setdefault(f"judgment:{node['page_id']}", {})
    for node in memory.get("elixir_nodes", []):
        adjacency.setdefault(f"elixir:{node['elixir_id']}", {})
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        source_key = f"source:{edge['source_id']}"
        concept_key = f"concept:{edge['concept_slug']}"
        adjacency.setdefault(source_key, {})[concept_key] = "HAS_CONCEPT"
        adjacency.setdefault(concept_key, {})[source_key] = "HAS_CONCEPT"
    for edge in memory.get("edges", {}).get("source_to_judgment", []):
        source_key = f"source:{edge['source_id']}"
        judgment_key = f"judgment:{edge['page_id']}"
        adjacency.setdefault(source_key, {})[judgment_key] = "SUPPORTS_JUDGMENT"
        adjacency.setdefault(judgment_key, {})[source_key] = "SUPPORTS_JUDGMENT"
    for edge in memory.get("edges", {}).get("concept_to_concept", []):
        left_key = f"concept:{edge['from']}"
        right_key = f"concept:{edge['to']}"
        adjacency.setdefault(left_key, {})[right_key] = "RELATED_CONCEPT"
        adjacency.setdefault(right_key, {})[left_key] = "RELATED_CONCEPT"
    for edge in memory.get("edges", {}).get("judgment_to_judgment", []):
        edge_type = f"JUDGMENT_{str(edge.get('relation') or 'related').upper()}"
        left_key = f"judgment:{edge['from']}"
        right_key = f"judgment:{edge['to']}"
        adjacency.setdefault(left_key, {})[right_key] = edge_type
        adjacency.setdefault(right_key, {})[left_key] = edge_type
    for edge in memory.get("edges", {}).get("judgment_to_decision", []):
        edge_type = f"DECISION_{str(edge.get('relation') or 'supports').upper()}"
        left_key = f"judgment:{edge['from']}"
        right_key = f"judgment:{edge['to']}"
        adjacency.setdefault(left_key, {})[right_key] = edge_type
        adjacency.setdefault(right_key, {})[left_key] = edge_type
    for edge in memory.get("edges", {}).get("concept_causal", []):
        edge_type = f"CAUSAL_{str(edge.get('relation') or 'causes').upper()}"
        left_key = f"concept:{edge['from']}"
        right_key = f"concept:{edge['to']}"
        adjacency.setdefault(left_key, {})[right_key] = edge_type
        adjacency.setdefault(right_key, {})[left_key] = edge_type
    for edge in memory.get("edges", {}).get("elixir_derived_from", []):
        elixir_key = f"elixir:{edge['elixir_id']}"
        from_kind = str(edge.get("from_kind") or "")
        from_id = str(edge.get("from_id") or "")
        if from_kind not in {"source", "judgment", "elixir"} or not from_id:
            continue
        from_key = f"{from_kind}:{from_id}"
        adjacency.setdefault(elixir_key, {})[from_key] = "ELIXIR_DERIVED_FROM"
        adjacency.setdefault(from_key, {})[elixir_key] = "ELIXIR_DERIVED_FROM"
    return adjacency


def machine_memory_node_metadata(memory: dict[str, Any], node_key: str) -> dict[str, Any]:
    if node_key.startswith("source:"):
        source_id = node_key.removeprefix("source:")
        source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
        node = source_nodes.get(source_id, {})
        return {"kind": "source", "id": source_id, "title": node.get("title", source_id), "path": node.get("source_page", f"wiki/sources/{source_id}.md")}
    if node_key.startswith("judgment:"):
        page_id = node_key.removeprefix("judgment:")
        judgment_nodes = {node["page_id"]: node for node in memory.get("judgment_nodes", [])}
        node = judgment_nodes.get(page_id, {})
        return {"kind": "judgment", "page_id": page_id, "title": node.get("title", page_id), "path": node.get("path", f"wiki/judgments/{page_id}.md")}
    if node_key.startswith("elixir:"):
        elixir_id = node_key.removeprefix("elixir:")
        elixir_nodes = {node["elixir_id"]: node for node in memory.get("elixir_nodes", [])}
        node = elixir_nodes.get(elixir_id, {})
        return {
            "kind": "elixir",
            "elixir_id": elixir_id,
            "title": node.get("title", elixir_id),
            "path": node.get("path", f"wiki/elixirs/{elixir_id}.md"),
        }
    concept_slug = node_key.removeprefix("concept:")
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    node = concept_nodes.get(concept_slug, {})
    return {"kind": "concept", "slug": concept_slug, "title": node.get("title", concept_slug), "path": f"wiki/concepts/{concept_slug}.md"}


def ranked_machine_memory_anchor_nodes(
    direct_source_scores: dict[str, int], direct_concept_scores: dict[str, int], expanded_source_scores: dict[str, int], expanded_concept_scores: dict[str, int], *, strategy: str = "concept-first"
) -> list[str]:
    anchors: list[str] = []
    if strategy == "source-first":
        candidate_groups = (_route_anchor_candidates(direct_source_scores, "source", 4), _route_anchor_candidates(direct_concept_scores, "concept", 3), _route_anchor_candidates(expanded_source_scores, "source", 4), _route_anchor_candidates(expanded_concept_scores, "concept", 3))
    elif strategy == "graph-walk":
        candidate_groups = (_route_anchor_candidates(direct_concept_scores, "concept", 3), _route_anchor_candidates(direct_source_scores, "source", 3), _route_anchor_candidates(expanded_concept_scores, "concept", 4), _route_anchor_candidates(expanded_source_scores, "source", 4))
    else:
        candidate_groups = (_route_anchor_candidates(direct_concept_scores, "concept", 4), _route_anchor_candidates(direct_source_scores, "source", 3), _route_anchor_candidates(expanded_concept_scores, "concept", 4), _route_anchor_candidates(expanded_source_scores, "source", 3))
    for group in candidate_groups:
        for anchor in group:
            if anchor not in anchors:
                anchors.append(anchor)
    return anchors[:5]


def shortest_machine_memory_path(adjacency: dict[str, dict[str, str]], start: str, goal: str) -> list[str]:
    if start == goal:
        return [start]
    if start not in adjacency or goal not in adjacency:
        return []
    queue: deque[str] = deque([start])
    parents: dict[str, str | None] = {start: None}
    while queue:
        current = queue.popleft()
        for neighbor in sorted(adjacency.get(current, {})):
            if neighbor in parents:
                continue
            parents[neighbor] = current
            if neighbor == goal:
                queue.clear()
                break
            queue.append(neighbor)
    if goal not in parents:
        return []
    path: list[str] = []
    current: str | None = goal
    while current is not None:
        path.append(current)
        current = parents[current]
    return list(reversed(path))


def render_machine_memory_route(memory: dict[str, Any], adjacency: dict[str, dict[str, str]], path: list[str]) -> dict[str, Any]:
    nodes = [machine_memory_node_metadata(memory, node_key) for node_key in path]
    edges: list[dict[str, str]] = []
    for left, right in zip(path, path[1:], strict=False):
        edge_type = adjacency.get(left, {}).get(right, "")
        if edge_type == "HAS_CONCEPT":
            if left.startswith("source:"):
                edges.append({"type": edge_type, "left": left.removeprefix("source:"), "right": right.removeprefix("concept:")})
            else:
                edges.append({"type": edge_type, "left": right.removeprefix("source:"), "right": left.removeprefix("concept:")})
        elif edge_type == "SUPPORTS_JUDGMENT":
            if left.startswith("source:"):
                edges.append({"type": edge_type, "left": left.removeprefix("source:"), "right": right.removeprefix("judgment:")})
            else:
                edges.append({"type": edge_type, "left": right.removeprefix("source:"), "right": left.removeprefix("judgment:")})
        else:
            edges.append({"type": edge_type or "RELATED_CONCEPT", "left": left.split(":", 1)[-1], "right": right.split(":", 1)[-1]})
    return {"start": nodes[0], "goal": nodes[-1], "length": max(0, len(path) - 1), "nodes": nodes, "edges": edges}


def build_machine_memory_query_routes(memory: dict[str, Any], adjacency: dict[str, dict[str, str]], direct_source_scores: dict[str, int], direct_concept_scores: dict[str, int], expanded_source_scores: dict[str, int], expanded_concept_scores: dict[str, int], *, strategy: str = "concept-first") -> list[dict[str, Any]]:
    anchor_nodes = ranked_machine_memory_anchor_nodes(direct_source_scores, direct_concept_scores, expanded_source_scores, expanded_concept_scores, strategy=strategy)
    routes: list[dict[str, Any]] = []
    seen_routes: set[tuple[str, ...]] = set()
    max_routes = 6 if strategy == "graph-walk" else 4
    for index, start in enumerate(anchor_nodes):
        for goal in anchor_nodes[index + 1 :]:
            path = shortest_machine_memory_path(adjacency, start, goal)
            if len(path) < 2:
                continue
            route_key = tuple(path)
            if route_key in seen_routes:
                continue
            seen_routes.add(route_key)
            route = render_machine_memory_route(memory, adjacency, path)
            route["strategy"] = strategy
            routes.append(route)
            if len(routes) >= max_routes:
                return routes
    return routes


def record_query_route_telemetry(root: Path, *, question: str, machine_query: dict[str, Any], protocol: str = DEFAULT_PROTOCOL, occurred_at: str | None = None) -> dict[str, Any]:
    occurred_at = occurred_at or utc_now()
    telemetry_state = load_query_route_telemetry(root)
    entries = [dict(entry) for entry in telemetry_state.get("entries", []) if isinstance(entry, dict)]
    entry = {"query_signature": question_signature(question), "question_preview": question.strip()[:160], "occurred_at": occurred_at, "protocol": protocol, "selected_strategy": str(machine_query.get("selected_strategy") or ""), "selection_reason": str(machine_query.get("selection_reason") or ""), "matched_terms": list(machine_query.get("matched_terms", []) or [])[:8], "matched_source_markers": list(machine_query.get("matched_source_markers", []) or [])[:4], "matched_graph_markers": list(machine_query.get("matched_graph_markers", []) or [])[:4], "route_count": len(machine_query.get("query_routes", []) or []), "ranked_source_ids": list(machine_query.get("ranked_source_ids", []) or [])[:5], "ranked_concept_slugs": list(machine_query.get("ranked_concept_slugs", []) or [])[:5], "ranked_judgment_ids": list(machine_query.get("ranked_judgment_ids", []) or [])[:5], "ranked_elixir_ids": list(machine_query.get("ranked_elixir_ids", []) or [])[:5], "touched_component_ids": list(machine_query.get("touched_component_ids", []) or [])[:5], "planner_next_action_id": str((machine_query.get("planner_next_action") or {}).get("action_id") or "")}
    entries.insert(0, entry)
    strategy_counts: dict[str, int] = {}
    protocol_counts: dict[str, int] = {}
    for item in entries[:24]:
        strategy = str(item.get("selected_strategy") or "")
        scoped_protocol = str(item.get("protocol") or DEFAULT_PROTOCOL)
        if strategy:
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        if scoped_protocol:
            protocol_counts[scoped_protocol] = protocol_counts.get(scoped_protocol, 0) + 1
    document = {"version": 1, "updated_at": occurred_at, "state_path": relative_path(root, query_route_telemetry_path(root)), "entries": entries[:24], "strategy_counts": strategy_counts, "protocol_counts": protocol_counts, "last_entry": entry}
    save_query_route_telemetry(root, document)
    return document


def recent_execution_dry_runs(root: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for event in reversed(load_runtime_history(root)):
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("event_type") or "")
        if "dry-run" not in event_type:
            continue
        preview_path = str(event.get("preview_path") or "")
        payload = load_json_document(root / preview_path) if preview_path else {}
        if not isinstance(payload, dict):
            payload = {}
        preview = payload.get("preview") if isinstance(payload.get("preview"), dict) else {}
        bundle = payload.get("bundle") if isinstance(payload.get("bundle"), dict) else {}
        safe_preview = bundle.get("safe_apply_preview") if isinstance(bundle.get("safe_apply_preview"), dict) else {}
        affected_paths = preview.get("affected_paths") if isinstance(preview.get("affected_paths"), list) else []
        if not affected_paths and isinstance(safe_preview.get("affected_paths"), list):
            affected_paths = safe_preview.get("affected_paths")
        records.append({"event_type": event_type, "title": str(payload.get("title") or event.get("action_id") or event.get("entry_id") or event.get("slug") or event_type), "occurred_at": str(event.get("occurred_at") or payload.get("generated_at") or ""), "preview_path": preview_path, "bundle_path": str(event.get("bundle_path") or payload.get("bundle_path") or ""), "apply_mode": str(payload.get("apply_mode") or preview.get("apply_mode") or safe_preview.get("apply_mode") or event_type), "affected_paths": [str(path) for path in affected_paths if isinstance(path, str) and path]})
        if len(records) >= limit:
            break
    return records


def concept_page_snapshot(root: Path, slug: str) -> dict[str, Any]:
    path = root / "wiki" / "concepts" / f"{slug}.md"
    if not path.exists():
        return {"path": relative_path(root, path), "title": slug, "source_signature": "", "source_pages": [], "summary": "", "content": ""}
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    source_pages = frontmatter.get("source_pages", [])
    if not isinstance(source_pages, list):
        source_pages = []
    return {"path": relative_path(root, path), "title": str(frontmatter.get("title") or path.stem), "source_signature": str(frontmatter.get("source_signature") or ""), "source_pages": [str(item) for item in source_pages if isinstance(item, str)], "summary": preserved_section(content, "Summary", ""), "content": content}
