"""Planner domain TypedDict contracts (not yet imported by callers; keep as schema)."""

from __future__ import annotations

from typing import Any, TypedDict


class PlannerQueueItem(TypedDict, total=False):
    item_id: str
    item_kind: str
    action_id: str
    title: str
    priority: str
    status: str
    protocol: str
    impact_score: int
    priority_score: int
    blocked: bool
    depends_on: list[str]
    target_paths: list[str]
    command_hint: str
    next_step: str


class PlannerState(TypedDict, total=False):
    version: int
    generated_at: str
    state_path: str
    active_protocol: str
    pending_proposals: list[dict[str, Any]]
    priority_queue: list[PlannerQueueItem]
    dependency_graph: dict[str, Any]
    next_action: dict[str, Any]
    executed_actions: list[dict[str, Any]]
    counts: dict[str, int]
