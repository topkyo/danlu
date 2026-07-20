"""Lint and nightly health helpers extracted from app_compile."""

from __future__ import annotations

import fcntl
import functools
import hashlib
import html
import json
import os
import re
import shutil
import threading
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..app_shell.meta import write_shell_summary
from ..app_shell.summary import build_shell_summary
from ..compile.build import (
    default_concept_build_state,
    default_domain_pilot_build_state,
    default_machine_memory_build_state,
    default_output_pack_build_state,
    default_ranking_build_state,
    load_ranking_build_state,
)
from ..compile.paths import (
    concept_build_state_path,
    domain_pilot_build_state_path,
    machine_memory_build_state_path,
    output_pack_build_state_path,
    ranking_build_state_path,
)
from ..compile.state import save_compile_state
from ..config import LLMConfig
from ..content.archive import (
    active_archived_material_ids,
    active_material_archive_entries,
    load_archive_candidates_state,
    load_material_archive_state,
    load_material_routing_state,
    save_material_archive_state,
)
from ..content.concepts import (
    build_concept_quality,
    build_concept_records,
    concept_page_snapshot,
    concept_render_signature,
    concept_source_pages,
    entry_concept_terms,
    normalize_concept_hardness,
    render_concept_page,
    render_concepts_index,
    render_sources_index,
)
from ..content.io import (
    active_manual_source_concept_links,
    annotate_recurring_promotion,
    append_review_history_entry,
    collect_output_artifacts,
    collect_output_density_artifacts,
    collect_recent_output_artifacts,
    curated_asset_section_snapshot,
    entry_ids_from_paths,
    entry_lookup_maps,
    find_promoted_curated_page,
    manifest_change_summary,
    preserved_section,
    recurring_promotion_needs_refresh,
    render_source_page_with_state,
    review_history_entries,
    routing_snapshot_for_protocol,
    source_summary_or_preview,
    sync_manifest_with_raw,
)
from ..content.material import (
    active_corpus_bridge_evidence_ids,
    build_material_state_documents,
    load_active_corpora_state,
    load_manual_link_state,
    load_material_state,
    reconcile_active_corpora_state,
    refresh_material_state,
    save_manual_link_state,
    upsert_active_corpus,
)
from ..content.memory import (
    concept_summary_is_placeholder,
    remove_stale_generated_markdown_files,
)
from ..content.outputs import classify_recurring_output_kind
from ..content.paths import (
    active_corpora_state_path,
    archive_candidates_state_path,
    material_routing_state_path,
)
from ..content.rewrite import load_concept_rewrite_state, save_concept_rewrite_state
from ..execution.history import append_execution_receipt_history, append_runtime_history
from ..execution.lifecycle import concept_lifecycle_entry, concept_page_path
from ..execution.patch_plan import build_page_patch_plan
from ..execution.paths import (
    execution_policy_log_path,
    material_archive_action_id,
)
from ..execution.policy import (
    append_execution_policy_decisions,
    execution_policy_decision_record,
    load_execution_receipt_history,
)
from ..execution.receipts import (
    build_execution_bundle,
    build_execution_receipt,
    build_material_archive_receipt,
    execution_bundle_digest,
    load_execution_bundle,
    write_execution_bundle_document,
)
from ..execution.repair_plan import (
    _validate_rewrite_candidate_markdown,
    build_machine_memory_repair_plan,
    repair_execution_proposals,
    rewrite_proposal_candidate_is_current,
    rewrite_proposal_is_apply_ready,
)
from ..lifecycle.aging import collect_aging_signals, evaluate_page_aging
from ..lifecycle.knowledge import (
    build_knowledge_lifecycle_document,
    display_knowledge_lifecycle_state,
    ensure_knowledge_lifecycle_override_state,
    judgment_lifecycle_profile,
    knowledge_lifecycle_governance_summary,
    load_knowledge_lifecycle_state,
    refresh_knowledge_lifecycle_state,
    render_knowledge_lifecycle_entry_summary,
    save_knowledge_lifecycle_override_state,
)
from ..lifecycle.paths import (
    knowledge_lifecycle_override_state_path,
    knowledge_lifecycle_state_path,
    nightly_health_state_path,
)
from ..lifecycle.status import (
    action_needs_review,
    collect_curated_pages,
    curated_page_transition_profile,
    default_curated_status,
    display_action_status,
    display_curated_status,
    display_rewrite_proposal_status,
    review_queue,
    rewrite_proposal_needs_review,
    valid_curated_statuses,
)
from ..lifecycle.templates import curated_page_template
from ..memory.action_core import (
    action_supports_low_risk_apply,
    placeholder_concept_slugs,
    remove_stale_generated_execution_bundle_files,
    remove_stale_generated_execution_proposal_pages,
    safe_apply_preview,
    validate_low_risk_action_targets,
)
from ..memory.action_state import load_machine_memory_action_state, save_machine_memory_action_state
from ..memory.actions import reconcile_machine_memory_actions
from ..memory.build_plan import plan_machine_memory_build
from ..memory.builder import build_machine_memory
from ..memory.core import (
    machine_memory_digest,
    machine_memory_snapshot_is_reusable,
    reuse_machine_memory_core,
)
from ..memory.execution_surfaces import (
    build_execution_audit_snapshot,
    collect_execution_consistency_signals,
    concept_rewrite_proposal_digest,
    reconcile_concept_rewrite_proposals,
    render_concept_quality,
    render_concept_rewrite_index,
    render_concept_rewrite_proposal_page,
    render_execution_audit,
    render_execution_audit_html,
    render_execution_proposal_page,
)
from ..memory.graph_builder import build_machine_memory_graph
from ..memory.graph_query import build_machine_memory_query
from ..memory.graph_transition import (
    append_machine_memory_history,
    summarize_machine_memory_transition,
)
from ..memory.health import build_machine_memory_health
from ..memory.judgment_assets import attach_judgment_assets_to_machine_memory
from ..memory.paths import (
    concept_rewrite_state_path,
    machine_memory_action_state_path,
    machine_memory_history_path,
)
from ..memory.state import load_machine_memory
from ..memory.status import (
    render_drift_report,
    render_machine_memory_actions,
    render_machine_memory_index,
    render_machine_memory_repair_plan,
)
from ..memory.topology import render_machine_memory_topology
from ..planner.paths import planner_state_path, query_route_telemetry_path
from ..planner.state import load_planner_state, record_query_route_telemetry, save_planner_state
from ..protocol.descriptors import AGENT_PACK_LIBRARY, protocol_paths, protocol_title
from ..protocol.focus_scoring import concept_focus_score, entry_focus_score
from ..protocol.library import PROTOCOL_LIBRARY
from ..protocol.review_windows import schedule_review_windows
from ..protocol.runtime_config import (
    ACTION_STATUSES,
    AUTO_PROMOTION_MIN_OCCURRENCES,
    CONCEPT_HARDNESS_LEVELS,
    DECISION_STATUSES,
    JUDGMENT_STATUSES,
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    PENDING_ACTION_STATUSES,
    REWRITE_PROPOSAL_STATUSES,
    protocol_output_guidance,
)
from ..protocol.runtime_schema import protocol_runtime_schema_path, protocol_runtime_summary
from ..protocol.scaffold import ensure_layout
from ..protocol.state import load_protocol_state, protocol_state_path, resolve_protocol
from ..protocol.templates import CURATED_ASSET_SECTION_ORDER
from ..render.cognitive_history import render_cognitive_history
from ..render.compile_status import render_compile_status
from ..render.furnace_center import (
    render_furnace_center,
)
from ..render.judgment_assets import render_judgment_assets
from ..render.paths import (
    agent_workbench_path,
    aging_report_path,
    append_wiki_log,
    cognitive_history_path,
    concept_quality_path,
    concept_rewrite_index_path,
    decision_memos_dir,
    ensure_wiki_log,
    execution_audit_html_path,
    execution_audit_path,
    execution_bundle_path,
    execution_proposal_path,
    execution_receipt_path,
    furnace_center_html_path,
    graph_health_report_path,
    judgment_assets_path,
    machine_memory_actions_path,
    machine_memory_repair_plan_path,
    machine_memory_topology_path,
    output_packs_index_path,
    product_shell_html_path,
    remove_stale_generated_concept_pages,
    repair_backlog_path,
    review_center_html_path,
    review_packs_dir,
    shell_summary_path,
    sop_drafts_dir,
)
from ..render.pilots import (
    build_domain_pilots,
    build_domain_pilots_incremental,
    domain_pilots_index_path,
    pilot_scorecards_dir,
)
from ..render.review_center import render_review_center_html
from ..render.views import (
    render_agent_pack,
    render_agent_workbench,
    render_aging_report,
    render_curated_index,
    render_domain_pilots_index,
    render_master_index,
    render_review_queue,
)
from ..state.constants import (
    DEFAULT_PROTOCOL,
    JUDGMENT_LIFECYCLE_STATES,
    KNOWLEDGE_LIFECYCLE_KINDS,
    KNOWLEDGE_LIFECYCLE_STATES,
)
from ..state.io import load_json_document
from ..state.manifest import load_manifest
from ..state.paths import (
    agent_pack_path,
    compile_state_path,
    lint_reports_dir,
    machine_memory_state_path,
    material_state_path,
)
from ..utils.hash import compiled_source_sha, question_signature, sha256_bytes
from ..utils.io import (
    atomic_write_text,
    runtime_write_operation,
    write_if_changed,
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from ..utils.markdown import (
    analyze_citation_snapshots,
    build_citation_snapshots,
    extract_provenance_paths,
    frontmatter_string_list,
    parse_frontmatter,
    read_text_preview,
    render_frontmatter,
    render_scalar,
    strip_frontmatter,
    upsert_markdown_section,
)
from ..utils.path import next_available_stem, relative_path
from ..utils.text import slugify, tokenize
from ..utils.time import utc_now


@dataclass
class Finding:
    severity: str
    path: str
    message: str


def pending_source_summary_ids(root: Path, entries: list[dict[str, Any]]) -> list[str]:
    pending: list[str] = []
    for entry in entries:
        page = root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
            continue
        content = page.read_text(encoding="utf-8", errors="replace")
        if "Pending LLM summary." in content:
            pending.append(entry["id"])
    return pending


@runtime_write_operation
def lint_wiki(root: Path) -> dict[str, Any]:
    context = _start_lint_context(root)
    _lint_layout_phase(context)
    _lint_runtime_phase(context)
    _lint_governance_phase(context)
    _lint_curated_phase(context)
    return _write_lint_report(context)


@dataclass
class _LintContext:
    root: Path
    manifest: dict[str, Any]
    findings: list[Finding] = field(default_factory=list)
    protocol_state: dict[str, Any] = field(default_factory=dict)
    decision_pages: list[dict[str, Any]] = field(default_factory=list)
    judgment_pages: list[dict[str, Any]] = field(default_factory=list)
    pack_memory: dict[str, Any] = field(default_factory=dict)
    expected_output_packs: dict[str, Any] = field(default_factory=dict)
    expected_domain_pilots: dict[str, Any] = field(default_factory=dict)

    def add(self, severity: str, path: str | Path, message: str) -> None:
        finding_path = relative_path(self.root, path) if isinstance(path, Path) else str(path)
        self.findings.append(Finding(severity, finding_path, message))


def _start_lint_context(root: Path) -> _LintContext:
    ensure_layout(root)
    return _LintContext(root=root, manifest=sync_manifest_with_raw(root))


_LINT_REPORT_KEEP = 10


def _rotate_lint_reports(lint_dir: Path) -> None:
    """Keep only the most recent _LINT_REPORT_KEEP reports per lint family."""
    for pattern in ("lint-*.md", "semantic-lint-*.md"):
        reports = sorted(lint_dir.glob(pattern))
        if len(reports) <= _LINT_REPORT_KEEP:
            continue
        for old in reports[: len(reports) - _LINT_REPORT_KEEP]:
            old.unlink(missing_ok=True)


def _write_lint_report(context: _LintContext) -> dict[str, Any]:
    generated_at = utc_now()
    report_name = f"lint-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
    lint_dir = lint_reports_dir(context.root)
    lint_dir.mkdir(parents=True, exist_ok=True)
    report_path = lint_dir / report_name
    error_count = sum(1 for finding in context.findings if finding.severity == "error")
    warn_count = sum(1 for finding in context.findings if finding.severity == "warn")
    lines = [
        "# Lint 报告",
        "",
        f"- 生成时间：`{generated_at}`",
        f"- 错误数：`{error_count}`",
        f"- 警告数：`{warn_count}`",
        "",
        "## 发现",
    ]
    if not context.findings:
        lines.append("- 没有发现问题。")
    else:
        for finding in context.findings:
            lines.append(f"- `{finding.severity}` {finding.path}: {finding.message}")
    atomic_write_text(report_path, "\n".join(lines) + "\n")
    _rotate_lint_reports(lint_dir)
    append_wiki_log(
        context.root,
        "lint",
        "wiki health check",
        [
            f"errors: `{error_count}`",
            f"warnings: `{warn_count}`",
            f"report: `{relative_path(context.root, report_path)}`",
        ],
    )
    return {
        "path": relative_path(context.root, report_path),
        "counts": {"errors": error_count, "warnings": warn_count},
        "findings": [
            {"severity": finding.severity, "path": finding.path, "message": finding.message}
            for finding in context.findings
        ],
    }


from .phases import (  # noqa: E402
    _lint_curated_phase,
    _lint_governance_phase,
    _lint_layout_phase,
    _lint_runtime_phase,
)
