"""Execution domain TypedDict contracts."""

from __future__ import annotations

from typing import Any, TypedDict


class ExecutionBundle(TypedDict, total=False):
    version: int
    kind: str
    generated_by: str
    compiled_at: str
    action_id: str
    title: str
    status: str
    proposal_kind: str
    risk: str
    priority: str
    protocol: str
    policy_decision: str
    policy_rule_id: str
    execution_band: str
    impact_score: int
    priority_score: int
    summary: str
    target_paths: list[str]
    suggested_edits: list[str]
    proposal_path: str
    bundle_path: str
    page_patch_plan: list[dict[str, Any]]
    safe_apply_preview: dict[str, Any] | None
    depends_on: list[str]
    rollback_summary: str
    command_hint: str
    next_step: str
    dry_run_supported: bool
    digest: str


class ExecutionReceipt(TypedDict, total=False):
    version: int
    kind: str
    generated_by: str
    applied_at: str
    operation: str
    action_id: str
    title: str
    status: str
    protocol: str
    subject_kind: str
    subject_id: str
    apply_mode: str
    note: str
    primary_path: str
    secondary_path: str
    current_temperature: str
    resulting_temperature: str
    receipt_path: str
    bundle: ExecutionBundle
    safe_apply_preview: dict[str, Any] | None
