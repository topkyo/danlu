"""App shell domain TypedDict contracts."""

from __future__ import annotations

from typing import Any, TypedDict


class ShellSummary(TypedDict, total=False):
    kind: str
    contract_version: int
    generated_at: str
    generated_by: str
    summary_path: str
    active_protocol: str
    available_protocols: list[str]
    llm_status: dict[str, Any]
    latest_llm_run: dict[str, Any]
    latest_shell_sync_run: dict[str, Any]
    curated_page_roots: dict[str, str]
    llm_health: dict[str, Any]
    review_backlog_counts: dict[str, Any]
    aging_summary: dict[str, Any]
    judgment_assets: dict[str, Any]
    review_controls: dict[str, Any]
    execution_controls: dict[str, Any]
    planner: dict[str, Any]
    route_telemetry: dict[str, Any]
    dashboard: dict[str, Any]
    search_results: dict[str, Any]
    suggested_next_actions: list[dict[str, Any]]
    compound_suggest: dict[str, Any]
    drift_warnings: list[dict[str, Any]]
    rewrite_followup_actions: list[dict[str, Any]]
    recent_outputs: list[dict[str, Any]]
    recent_receipts: list[dict[str, Any]]
    recent_runs: list[dict[str, Any]]
    nightly: dict[str, Any]
    metrics: list[dict[str, Any]]
    links: dict[str, str]
    capabilities: dict[str, Any]
