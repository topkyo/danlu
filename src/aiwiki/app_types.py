"""Stable runtime type declarations for cross-module contracts.

OWNER STATUS: stable utility owner. Small, broadly imported; treat as a
shared types module. Add new TypedDicts/protocols here only if they are
genuinely cross-module contracts. See AGENTS.md migration policy.
"""

from __future__ import annotations

from typing import Any, TypedDict


class ManifestEntry(TypedDict, total=False):
    id: str
    title: str
    source_type: str
    note_kind: str
    original_path: str
    stored_path: str
    kind: str
    sha256: str
    imported_at: str
    updated_at: str


class CompileState(TypedDict, total=False):
    version: int
    compiled_at: str
    manifest_entry_count: int
    dirty_source_ids: list[str]
    clean_source_ids: list[str]
    dirty_concept_source_ids: list[str]
    clean_concept_source_ids: list[str]
    dirty_concept_slugs: list[str]
    clean_concept_slugs: list[str]
    dirty_machine_memory_source_ids: list[str]
    clean_machine_memory_source_ids: list[str]
    dirty_machine_memory_concept_slugs: list[str]
    clean_machine_memory_concept_slugs: list[str]
    machine_memory_core_reused: bool
    dirty_ranking_source_ids: list[str]
    clean_ranking_source_ids: list[str]
    dirty_ranking_concept_slugs: list[str]
    clean_ranking_concept_slugs: list[str]
    dirty_output_pack_groups: list[str]
    clean_output_pack_groups: list[str]
    dirty_domain_pilot_protocols: list[str]
    clean_domain_pilot_protocols: list[str]
    dirty_index_artifacts: list[str]
    clean_index_artifacts: list[str]
    dirty_maintenance_artifacts: list[str]
    clean_maintenance_artifacts: list[str]
    drift_warnings: list[dict[str, Any]]
    phase_summary: list[dict[str, Any]]


class ProtocolDescriptorPaths(TypedDict, total=False):
    index: str
    taxonomy: str
    decision: str
    judgment: str
    review: str
    nightly: str
    query: str


class ProtocolDescriptor(TypedDict, total=False):
    slug: str
    title: str
    summary: str
    paths: ProtocolDescriptorPaths


class ProtocolState(TypedDict, total=False):
    version: int
    active_protocol: str
    available_protocols: list[str]
    protocols: list[ProtocolDescriptor]
    state_path: str


class ProtocolRuntimeRule(TypedDict, total=False):
    capabilities: list[str]
    decision: str
    execution_band: str
    execution_policy: str
    policy_summary: str


class ProtocolRuntimeExecutionPolicy(TypedDict, total=False):
    accepted_rules: dict[str, ProtocolRuntimeRule]


class ProtocolRuntimeQueryRoutes(TypedDict, total=False):
    default_strategy: str
    strategy_order: list[str]
    source_markers: list[str]
    graph_markers: list[str]


class ProtocolRuntimeSchema(TypedDict, total=False):
    version: int
    slug: str
    title: str
    summary: str
    review_windows: dict[str, list[int]]
    output_guidance: dict[str, list[str]]
    execution_policy: ProtocolRuntimeExecutionPolicy
    query_routes: ProtocolRuntimeQueryRoutes


class AgingSignal(TypedDict, total=False):
    page_id: str
    title: str
    path: str
    kind: str
    status: str
    protocol: str
    reviewed_at: str
    updated_at: str
    revisit_after: str
    escalate_after: str
    pending_review: str
    overdue_review: str
    escalation_candidate: str
    aging_state: str
    citation_drift: str
    citation_drift_count: str
    citation_snapshot_gap_count: str
    asset_score: str
    confidence: str


class JudgmentAsset(TypedDict, total=False):
    page_id: str
    title: str
    path: str
    kind: str
    status: str
    protocol: str
    citations: list[str]
    confidence: str
    counter_evidence: list[str]
    invalidation_rule: str
    next_signals: list[str]
    revisit_after: str
    escalate_after: str
    formed_at: str
    last_reviewed: str


class JudgmentReviewAction(TypedDict, total=False):
    id: str
    title: str
    page_id: str
    page_path: str
    page_kind: str
    protocol: str
    status: str
    priority: str
    reason_codes: list[str]
    candidate_count: int
    review_command: str


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


class MachineMemoryRecord(TypedDict, total=False):
    id: str
    kind: str
    title: str
    source_type: str
    source_page: str
    stored_path: str
    slug: str
    source_pages: list[str]
    source_ids: list[str]
    related_slugs: list[str]
    source_count: int
    related_count: int
    quality_state: str
    issues: list[str]
    rewrite_priority: str
    rewrite_strategy: str


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
    drift_warnings: list[dict[str, Any]]
    rewrite_recovery_actions: list[dict[str, Any]]
    recent_outputs: list[dict[str, Any]]
    recent_receipts: list[dict[str, Any]]
    recent_runs: list[dict[str, Any]]
    nightly: dict[str, Any]
    metrics: list[dict[str, Any]]
    links: dict[str, str]
    capabilities: dict[str, Any]
