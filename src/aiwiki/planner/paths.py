"""Planner path helpers extracted from aiwiki.app_state_paths."""

from __future__ import annotations

from pathlib import Path


def planner_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "planner-state.json"


def query_route_telemetry_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "query-route-telemetry.json"
