"""Planner state and query-route telemetry I/O.

Extracted from the legacy app_state hub. Owned by the planner layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_state_paths import planner_state_path, query_route_telemetry_path
from ..state.constants import DEFAULT_PROTOCOL
from ..state.io import load_json_document, save_json_document
from ..utils.path import relative_path


def default_planner_state() -> dict[str, Any]:
    return {
        "version": 1,
        "generated_at": "",
        "state_path": "",
        "active_protocol": DEFAULT_PROTOCOL,
        "pending_proposals": [],
        "priority_queue": [],
        "dependency_graph": {"nodes": [], "edges": []},
        "next_action": {},
        "executed_actions": [],
        "counts": {"pending_proposals": 0, "blocked": 0, "unblocked": 0, "executed_actions": 0},
    }


def load_planner_state(root: Path) -> dict[str, Any]:
    document = load_json_document(planner_state_path(root))
    if not isinstance(document, dict):
        return default_planner_state()
    pending_proposals = document.get("pending_proposals")
    priority_queue = document.get("priority_queue")
    dependency_graph = document.get("dependency_graph")
    counts = document.get("counts")
    next_action = document.get("next_action")
    executed_actions = document.get("executed_actions")
    if not isinstance(pending_proposals, list) or not isinstance(priority_queue, list):
        return default_planner_state()
    if not isinstance(dependency_graph, dict) or not isinstance(counts, dict) or not isinstance(executed_actions, list):
        return default_planner_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "state_path": str(document.get("state_path") or relative_path(root, planner_state_path(root))),
        "active_protocol": str(document.get("active_protocol") or DEFAULT_PROTOCOL),
        "pending_proposals": [proposal for proposal in pending_proposals if isinstance(proposal, dict)],
        "priority_queue": [item for item in priority_queue if isinstance(item, dict)],
        "dependency_graph": {
            "nodes": [node for node in dependency_graph.get("nodes", []) if isinstance(node, dict)],
            "edges": [edge for edge in dependency_graph.get("edges", []) if isinstance(edge, dict)],
        },
        "next_action": dict(next_action) if isinstance(next_action, dict) else {},
        "executed_actions": [item for item in executed_actions if isinstance(item, dict)],
        "counts": {
            "pending_proposals": int(counts.get("pending_proposals", 0) or 0),
            "blocked": int(counts.get("blocked", 0) or 0),
            "unblocked": int(counts.get("unblocked", 0) or 0),
            "executed_actions": int(counts.get("executed_actions", 0) or 0),
        },
    }


def save_planner_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(planner_state_path(root), document)


def default_query_route_telemetry() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": "",
        "state_path": "",
        "entries": [],
        "strategy_counts": {},
        "protocol_counts": {},
        "last_entry": {},
    }


def load_query_route_telemetry(root: Path) -> dict[str, Any]:
    document = load_json_document(query_route_telemetry_path(root))
    if not isinstance(document, dict):
        return default_query_route_telemetry()
    entries = document.get("entries")
    strategy_counts = document.get("strategy_counts")
    protocol_counts = document.get("protocol_counts")
    last_entry = document.get("last_entry")
    if not isinstance(entries, list) or not isinstance(strategy_counts, dict) or not isinstance(protocol_counts, dict):
        return default_query_route_telemetry()
    return {
        "version": int(document.get("version", 1) or 1),
        "updated_at": str(document.get("updated_at") or ""),
        "state_path": str(document.get("state_path") or relative_path(root, query_route_telemetry_path(root))),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
        "strategy_counts": {str(key): int(value or 0) for key, value in strategy_counts.items()},
        "protocol_counts": {str(key): int(value or 0) for key, value in protocol_counts.items()},
        "last_entry": dict(last_entry) if isinstance(last_entry, dict) else {},
    }


def save_query_route_telemetry(root: Path, document: dict[str, Any]) -> None:
    save_json_document(query_route_telemetry_path(root), document)
