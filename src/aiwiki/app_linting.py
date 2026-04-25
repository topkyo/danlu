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

from .app_content import (
    _validate_rewrite_candidate_markdown,
    action_needs_review,
    action_supports_low_risk_apply,
    active_manual_source_concept_links,
    annotate_recurring_promotion,
    append_execution_policy_decisions,
    append_review_history_entry,
    append_wiki_log,
    build_concept_quality,
    build_concept_records,
    build_domain_pilots,
    build_domain_pilots_incremental,
    build_knowledge_lifecycle_document,
    build_machine_memory_repair_plan,
    build_output_packs,
    build_output_packs_incremental,
    build_page_patch_plan,
    classify_recurring_output_kind,
    collect_aging_signals,
    collect_curated_pages,
    collect_output_artifacts,
    collect_output_density_artifacts,
    collect_recent_output_artifacts,
    concept_render_signature,
    concept_source_pages,
    concept_summary_is_placeholder,
    curated_asset_section_snapshot,
    curated_page_template,
    curated_page_transition_profile,
    decision_memos_dir,
    default_curated_status,
    display_action_status,
    display_curated_status,
    display_knowledge_lifecycle_state,
    display_rewrite_proposal_status,
    domain_pilots_index_path,
    ensure_wiki_log,
    entry_concept_terms,
    entry_ids_from_paths,
    entry_lookup_maps,
    evaluate_page_aging,
    execution_bundle_path,
    execution_policy_decision_record,
    execution_proposal_path,
    execution_receipt_path,
    find_promoted_curated_page,
    frontmatter_string_list,
    judgment_lifecycle_profile,
    knowledge_lifecycle_governance_summary,
    load_execution_receipt_history,
    manifest_change_summary,
    normalize_concept_hardness,
    pilot_scorecards_dir,
    placeholder_concept_slugs,
    preserved_section,
    recurring_promotion_needs_refresh,
    refresh_knowledge_lifecycle_state,
    remove_stale_generated_concept_pages,
    remove_stale_generated_execution_bundle_files,
    remove_stale_generated_execution_proposal_pages,
    remove_stale_generated_markdown_files,
    render_agent_pack,
    render_agent_workbench,
    render_aging_report,
    render_concept_page,
    render_concepts_index,
    render_curated_index,
    render_domain_pilots_index,
    render_knowledge_lifecycle_entry_summary,
    render_master_index,
    render_output_packs_index,
    render_review_queue,
    render_source_page_with_state,
    render_sources_index,
    repair_execution_proposals,
    review_history_entries,
    review_packs_dir,
    review_queue,
    rewrite_proposal_candidate_is_current,
    rewrite_proposal_is_apply_ready,
    rewrite_proposal_needs_review,
    routing_snapshot_for_protocol,
    safe_apply_preview,
    sop_drafts_dir,
    source_summary_or_preview,
    sync_manifest_with_raw,
    valid_curated_statuses,
    validate_low_risk_action_targets,
)
from .app_execution import (
    append_execution_receipt_history,
    build_execution_bundle,
    build_execution_receipt,
    build_material_archive_receipt,
    execution_bundle_digest,
    load_execution_bundle,
    write_execution_bundle_document,
)
from .app_memory import (
    active_corpus_bridge_evidence_ids,
    append_machine_memory_history,
    attach_judgment_assets_to_machine_memory,
    build_execution_audit_snapshot,
    build_machine_memory,
    build_machine_memory_graph,
    build_machine_memory_health,
    build_machine_memory_query,
    build_material_state_documents,
    collect_execution_consistency_signals,
    concept_lifecycle_entry,
    concept_page_path,
    concept_page_snapshot,
    concept_rewrite_proposal_digest,
    machine_memory_digest,
    machine_memory_snapshot_is_reusable,
    plan_machine_memory_build,
    question_signature,
    reconcile_active_corpora_state,
    reconcile_concept_rewrite_proposals,
    reconcile_machine_memory_actions,
    record_query_route_telemetry,
    refresh_material_state,
    render_concept_quality,
    render_concept_rewrite_index,
    render_concept_rewrite_proposal_page,
    render_drift_report,
    render_execution_proposal_page,
    render_graph_health,
    render_machine_memory_actions,
    render_machine_memory_index,
    render_machine_memory_repair_plan,
    render_machine_memory_topology,
    reuse_machine_memory_core,
    summarize_machine_memory_transition,
    upsert_active_corpus,
)
from .app_memory_surfaces import build_execution_audit_snapshot, collect_execution_consistency_signals
from .app_protocol import (
    ACTION_STATUSES,
    AGENT_PACK_LIBRARY,
    AUTO_PROMOTION_MIN_OCCURRENCES,
    CONCEPT_HARDNESS_LEVELS,
    CURATED_ASSET_SECTION_ORDER,
    DECISION_STATUSES,
    JUDGMENT_STATUSES,
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    PENDING_ACTION_STATUSES,
    PROTOCOL_LIBRARY,
    REWRITE_PROPOSAL_STATUSES,
    concept_focus_score,
    ensure_layout,
    entry_focus_score,
    load_protocol_state,
    protocol_output_guidance,
    protocol_paths,
    protocol_runtime_schema_path,
    protocol_runtime_summary,
    protocol_state_path,
    protocol_title,
    resolve_protocol,
    schedule_review_windows,
)
from .app_render import render_aging_report, render_review_queue
from .app_shell import build_shell_summary, write_shell_summary
from .app_state import (
    DEFAULT_PROTOCOL,
    JUDGMENT_LIFECYCLE_STATES,
    KNOWLEDGE_LIFECYCLE_KINDS,
    KNOWLEDGE_LIFECYCLE_STATES,
    active_archived_material_ids,
    active_corpora_state_path,
    active_material_archive_entries,
    agent_pack_path,
    agent_workbench_path,
    aging_report_path,
    append_runtime_history,
    archive_candidates_state_path,
    cognitive_history_path,
    compile_state_path,
    concept_build_state_path,
    concept_quality_path,
    concept_rewrite_index_path,
    concept_rewrite_state_path,
    default_concept_build_state,
    default_domain_pilot_build_state,
    default_machine_memory_build_state,
    default_output_pack_build_state,
    default_ranking_build_state,
    domain_pilot_build_state_path,
    ensure_knowledge_lifecycle_override_state,
    execution_audit_html_path,
    execution_audit_path,
    execution_center_html_path,
    execution_center_path,
    execution_policy_log_path,
    furnace_center_html_path,
    graph_health_report_path,
    judgment_assets_path,
    knowledge_lifecycle_override_state_path,
    knowledge_lifecycle_state_path,
    load_active_corpora_state,
    load_archive_candidates_state,
    load_concept_rewrite_state,
    load_json_document,
    load_knowledge_lifecycle_state,
    load_machine_memory,
    load_machine_memory_action_state,
    load_manifest,
    load_manual_link_state,
    load_material_archive_state,
    load_material_routing_state,
    load_material_state,
    load_planner_state,
    load_ranking_build_state,
    machine_memory_action_state_path,
    machine_memory_actions_path,
    machine_memory_build_state_path,
    machine_memory_drift_report_path,
    machine_memory_graph_html_path,
    machine_memory_graph_path,
    machine_memory_history_path,
    machine_memory_repair_plan_path,
    machine_memory_state_path,
    machine_memory_topology_path,
    material_archive_action_id,
    material_routing_state_path,
    material_state_path,
    nightly_health_state_path,
    output_pack_build_state_path,
    output_packs_index_path,
    planner_state_path,
    product_shell_html_path,
    query_route_telemetry_path,
    ranking_build_state_path,
    repair_backlog_path,
    review_center_html_path,
    save_compile_state,
    save_concept_rewrite_state,
    save_knowledge_lifecycle_override_state,
    save_machine_memory_action_state,
    save_manual_link_state,
    save_material_archive_state,
    save_planner_state,
    shell_summary_path,
)
from .app_surfaces import (
    render_cognitive_history,
    render_compile_status,
    render_execution_audit,
    render_execution_audit_html,
    render_execution_center,
    render_execution_center_html,
    render_furnace_center,
    render_furnace_center_html,
    render_judgment_assets,
    render_machine_memory_graph_html,
    render_review_center_html,
)
from .app_utils import (
    analyze_citation_snapshots,
    build_citation_snapshots,
    compiled_source_sha,
    extract_provenance_paths,
    next_available_stem,
    parse_frontmatter,
    read_text_preview,
    relative_path,
    render_frontmatter,
    render_scalar,
    runtime_write_operation,
    sha256_bytes,
    slugify,
    strip_frontmatter,
    tokenize,
    upsert_markdown_section,
    utc_now,
    write_if_changed,
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from .config import LLMConfig


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


def _lint_layout_phase(context: _LintContext) -> None:
    for entry in context.manifest["entries"]:
        page = context.root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
            context.add("error", page, f"Missing source page for manifest entry `{entry['id']}`.")
            continue
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        for key in ("id", "kind", "source_files", "generated_by"):
            if key not in frontmatter or frontmatter[key] in ("", []):
                context.add("error", page, f"Frontmatter is missing required key `{key}`.")
        for source_file in frontmatter.get("source_files", []):
            candidate = context.root / source_file
            if not candidate.exists():
                context.add("error", page, f"Referenced source file does not exist: `{source_file}`.")
        if "Pending LLM summary." in content:
            context.add("warn", page, "Source page still contains the placeholder summary.")
        if not frontmatter.get("concepts"):
            context.add("warn", page, "Source page has no compiled concept links.")

    required_indexes = {
        "wiki/indexes/index.md": "Missing master wiki index page.",
        "wiki/indexes/sources.md": "Missing sources index page.",
        "wiki/indexes/concepts.md": "Missing concepts index page.",
        "wiki/indexes/decisions.md": "Missing decisions index page.",
        "wiki/indexes/judgments.md": "Missing judgments index page.",
        "wiki/indexes/judgment-assets.md": "Missing judgment asset dashboard page.",
        "wiki/indexes/agent-workbench.md": "Missing agent workbench page.",
        "wiki/indexes/cognitive-history.md": "Missing cognitive history page.",
        "wiki/indexes/output-packs.md": "Missing output packs index page.",
        "wiki/indexes/domain-pilots.md": "Missing domain pilots index page.",
        "wiki/indexes/rewrite-proposals.md": "Missing rewrite proposal index page.",
        "wiki/indexes/protocols.md": "Missing protocol dashboard page.",
        "wiki/indexes/furnace-center.md": "Missing furnace center page.",
        "wiki/indexes/execution-center.md": "Missing execution center page.",
        "wiki/indexes/execution-audit.md": "Missing execution audit page.",
        "wiki/indexes/review-queue.md": "Missing review queue page.",
        "wiki/indexes/review-center.md": "Missing review center page.",
        "wiki/indexes/aging-report.md": "Missing aging report page.",
        "wiki/indexes/concept-quality.md": "Missing concept quality page.",
        "wiki/indexes/compile-status.md": "Missing compile status page.",
        "wiki/indexes/machine-memory.md": "Missing machine memory index page.",
        "wiki/indexes/graph-view.md": "Missing graph view page.",
        "wiki/indexes/machine-memory-topology.md": "Missing machine memory topology page.",
        "wiki/indexes/machine-memory-actions.md": "Missing machine memory actions page.",
        "wiki/indexes/machine-memory-repair-plan.md": "Missing machine memory repair plan page.",
        "wiki/indexes/graph-health.md": "Missing machine memory graph health page.",
        "wiki/indexes/drift-report.md": "Missing machine memory drift report.",
        "wiki/indexes/log.md": "Missing wiki operation log.",
    }
    for relative, message in required_indexes.items():
        page = context.root / relative
        if not page.exists():
            context.add("error", relative, message)

    required_schema = {
        "schema/index.md": "Missing runtime schema index.",
        "schema/ingest.md": "Missing runtime ingest rules.",
        "schema/citations.md": "Missing runtime citation rules.",
        "schema/conflicts.md": "Missing runtime conflict rules.",
        "schema/review.md": "Missing runtime review rules.",
        "schema/writeback.md": "Missing runtime writeback rules.",
        "schema/protocols/index.md": "Missing protocol schema index.",
    }
    for relative, message in required_schema.items():
        page = context.root / relative
        if not page.exists():
            context.add("error", relative, message)
    for slug in sorted(PROTOCOL_LIBRARY):
        runtime_schema = protocol_runtime_schema_path(context.root, slug)
        if not runtime_schema.exists():
            context.add("error", runtime_schema, f"Missing protocol runtime schema for `{slug}`.")
            continue
        try:
            runtime_document = json.loads(runtime_schema.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            context.add("error", runtime_schema, f"Protocol runtime schema for `{slug}` is not valid JSON-compatible YAML.")
            continue
        if not isinstance(runtime_document, dict):
            context.add("error", runtime_schema, f"Protocol runtime schema for `{slug}` must be a mapping object.")

    context.protocol_state = load_protocol_state(context.root)
    for relative in protocol_paths(context.root, context.protocol_state["active_protocol"]):
        page = context.root / relative
        if not page.exists():
            context.add("error", relative, f"Missing active protocol rule file: `{relative}`.")


def _lint_runtime_phase(context: _LintContext) -> None:
    context.decision_pages = collect_curated_pages(context.root, "decisions", "decision")
    context.judgment_pages = collect_curated_pages(context.root, "judgments", "judgment")
    if machine_memory_state_path(context.root).exists():
        context.pack_memory = load_machine_memory(context.root)
    context.expected_output_packs = build_output_packs(
        context.root,
        context.decision_pages,
        context.judgment_pages,
        context.pack_memory,
        context.protocol_state,
        collect_recent_output_artifacts(context.root),
        utc_now(),
    )
    execution_audit_snapshot = build_execution_audit_snapshot(
        context.root,
        context.pack_memory,
        active_protocol=context.protocol_state["active_protocol"],
    ) if context.pack_memory else {"protocols": [], "counts": {}, "recent_apply": [], "recent_revert": []}
    context.expected_domain_pilots = build_domain_pilots(
        context.root,
        context.decision_pages,
        context.judgment_pages,
        context.pack_memory,
        context.protocol_state,
        collect_recent_output_artifacts(context.root),
        collect_output_density_artifacts(context.root),
        context.expected_output_packs,
        execution_audit_snapshot,
        utc_now(),
    )

    memory_state = machine_memory_state_path(context.root)
    graph_html = machine_memory_graph_html_path(context.root)
    furnace_html = furnace_center_html_path(context.root)
    execution_html = execution_center_html_path(context.root)
    execution_audit_html = execution_audit_html_path(context.root)
    shell_summary = shell_summary_path(context.root)
    product_shell_html = product_shell_html_path(context.root)
    planner_state = planner_state_path(context.root)
    query_route_telemetry = query_route_telemetry_path(context.root)
    policy_history = execution_policy_log_path(context.root)
    review_html = review_center_html_path(context.root)
    if context.manifest["entries"] and not memory_state.exists():
        context.add("error", memory_state, "Missing machine memory state file.")
    if context.manifest["entries"] and not graph_html.exists():
        context.add("error", graph_html, "Missing machine memory graph HTML view.")
    if context.manifest["entries"] and not furnace_html.exists():
        context.add("error", furnace_html, "Missing furnace center HTML view.")
    if context.manifest["entries"] and not execution_html.exists():
        context.add("error", execution_html, "Missing execution center HTML view.")
    if context.manifest["entries"] and not execution_audit_html.exists():
        context.add("error", execution_audit_html, "Missing execution audit HTML view.")
    if context.manifest["entries"] and not shell_summary.exists():
        context.add("error", shell_summary, "Missing shell summary JSON.")
    if context.manifest["entries"] and not product_shell_html.exists():
        context.add("error", product_shell_html, "Missing product shell HTML view.")
    if context.manifest["entries"] and not planner_state.exists():
        context.add("error", planner_state, "Missing planner state file.")
    if context.manifest["entries"] and not query_route_telemetry.exists():
        context.add("error", query_route_telemetry, "Missing query route telemetry file.")
    if context.manifest["entries"] and not review_html.exists():
        context.add("error", review_html, "Missing review center HTML view.")
    for pack_group in ("review_packs", "decision_memos", "sop_drafts"):
        for pack in context.expected_output_packs.get(pack_group, []):
            pack_path = context.root / str(pack.get("path") or "")
            if not pack_path.exists():
                context.add("error", pack_path, f"Missing output pack `{pack_path.name}` for `{pack_group}`.")
    for scorecard in context.expected_domain_pilots.get("scorecards", []):
        scorecard_path = context.root / str(scorecard.get("path") or "")
        if not scorecard_path.exists():
            context.add("error", scorecard_path, f"Missing domain pilot scorecard `{scorecard_path.name}`.")
    if context.manifest["entries"]:
        for pack in AGENT_PACK_LIBRARY:
            pack_path = agent_pack_path(context.root, str(pack["role"]))
            if not pack_path.exists():
                context.add("error", pack_path, f"Missing agent pack for role `{pack['role']}`.")
    if memory_state.exists():
        try:
            memory = json.loads(memory_state.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            context.add("error", memory_state, "Machine memory state is not valid JSON.")
        else:
            if "source_nodes" not in memory or "concept_nodes" not in memory:
                context.add("error", memory_state, "Machine memory state is missing required indexes.")
            if "health" not in memory:
                context.add("warn", memory_state, "Machine memory state is missing graph health data.")
            if not memory.get("digest"):
                context.add("warn", memory_state, "Machine memory state is missing a stable digest.")
            repair_plan = memory.get("health", {}).get("repair_plan", {}) if isinstance(memory, dict) else {}
            execution_proposals = repair_plan.get("execution_proposals", []) if isinstance(repair_plan, dict) else []
            for proposal in execution_proposals:
                if not isinstance(proposal, dict):
                    continue
                action_id = str(proposal.get("action_id") or "")
                proposal_path = context.root / str(
                    proposal.get("proposal_path")
                    or relative_path(context.root, execution_proposal_path(context.root, action_id))
                )
                if action_id and not proposal_path.exists():
                    context.add("error", proposal_path, f"Missing execution proposal page for action `{action_id}`.")
                bundle_path = context.root / str(
                    proposal.get("bundle_path")
                    or relative_path(context.root, execution_bundle_path(context.root, action_id))
                )
                if action_id and not bundle_path.exists():
                    context.add("error", bundle_path, f"Missing execution bundle for action `{action_id}`.")
    if planner_state.exists():
        planner_document = load_json_document(planner_state)
        if not isinstance(planner_document, dict) or not isinstance(planner_document.get("priority_queue"), list):
            context.add("error", planner_state, "Planner state is not valid JSON.")
    if query_route_telemetry.exists():
        telemetry_document = load_json_document(query_route_telemetry)
        if not isinstance(telemetry_document, dict) or not isinstance(telemetry_document.get("entries"), list):
            context.add("error", query_route_telemetry, "Query route telemetry is not valid JSON.")
    if shell_summary.exists():
        shell_document = load_json_document(shell_summary)
        if not isinstance(shell_document, dict):
            context.add("error", shell_summary, "Shell summary is not valid JSON.")

    graph_export = machine_memory_graph_path(context.root)
    if context.manifest["entries"] and not graph_export.exists():
        context.add("error", graph_export, "Missing machine memory graph export.")
    elif graph_export.exists():
        try:
            graph = json.loads(graph_export.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            context.add("error", graph_export, "Machine memory graph export is not valid JSON.")
        else:
            if "nodes" not in graph or "edges" not in graph:
                context.add("error", graph_export, "Machine memory graph export is missing nodes or edges.")

    history_path = machine_memory_history_path(context.root)
    if context.manifest["entries"] and not history_path.exists():
        context.add("warn", history_path, "Machine memory history file has not been initialized.")

    action_state_path = machine_memory_action_state_path(context.root)
    if context.manifest["entries"] and not action_state_path.exists():
        context.add("warn", action_state_path, "Machine memory action state file has not been initialized.")
    elif action_state_path.exists():
        action_state = load_json_document(action_state_path)
        if not isinstance(action_state, dict) or not isinstance(action_state.get("actions"), list):
            context.add("error", action_state_path, "Machine memory action state is not valid JSON.")
        else:
            for action in action_state.get("actions", []):
                if not isinstance(action, dict):
                    continue
                receipt_path = str(action.get("last_receipt_path") or "")
                if receipt_path and not (context.root / receipt_path).exists():
                    context.add(
                        "error",
                        receipt_path,
                        f"Referenced execution receipt does not exist for action `{action.get('id', '')}`.",
                    )
            consistency_signals = collect_execution_consistency_signals(
                context.root,
                [dict(action) for action in action_state.get("actions", []) if isinstance(action, dict)],
                load_execution_receipt_history(context.root),
            )
            for signal in consistency_signals:
                context.add(
                    str(signal.get("severity") or "warn"),
                    str(signal.get("path") or relative_path(context.root, action_state_path)),
                    f"Execution consistency issue for action `{signal.get('action_id', '')}`: {signal.get('message', '')}",
                )
            if action_state.get("actions") and not policy_history.exists():
                context.add("warn", policy_history, "Execution policy decision log has not been initialized.")
    if policy_history.exists():
        with policy_history.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    context.add("error", policy_history, f"Execution policy log line `{line_number}` is not valid JSON.")
                    break
                if not isinstance(record, dict):
                    context.add("error", policy_history, f"Execution policy log line `{line_number}` is not a JSON object.")
                    break

    rewrite_state_path = concept_rewrite_state_path(context.root)
    if context.manifest["entries"] and not rewrite_state_path.exists():
        context.add("warn", rewrite_state_path, "Concept rewrite proposal state file has not been initialized.")
    elif rewrite_state_path.exists():
        rewrite_state = load_json_document(rewrite_state_path)
        proposals = rewrite_state.get("proposals") if isinstance(rewrite_state, dict) else None
        if not isinstance(proposals, list):
            context.add("error", rewrite_state_path, "Concept rewrite proposal state is not valid JSON.")
        else:
            for proposal in proposals:
                if not isinstance(proposal, dict):
                    continue
                slug = str(proposal.get("slug") or "")
                proposal_path = context.root / str(proposal.get("proposal_path") or f"wiki/rewrite-proposals/{slug}.md")
                if slug and not proposal_path.exists():
                    context.add("error", proposal_path, f"Missing rewrite proposal page for concept `{slug}`.")
                target_path = context.root / str(proposal.get("target_path") or f"wiki/concepts/{slug}.md")
                if slug and not target_path.exists():
                    context.add("error", target_path, f"Rewrite proposal target concept page is missing: `{slug}`.")
                if proposal.get("apply_ready") and not proposal.get("candidate_markdown"):
                    context.add("error", proposal_path, "Rewrite proposal is marked apply_ready but has no candidate markdown.")
                if proposal.get("apply_ready") and not rewrite_proposal_is_apply_ready(context.root, proposal):
                    context.add(
                        "error",
                        proposal_path,
                        "Rewrite proposal is marked apply_ready but no longer matches the current concept sources.",
                    )
                proposal_status = str(proposal.get("status") or "")
                if proposal_status == "applied" and not str(proposal.get("previous_markdown") or ""):
                    context.add("error", proposal_path, "Applied rewrite proposal has no rollback snapshot.")
                verification_status = str(proposal.get("verification_status") or "")
                if proposal_status == "applied" and not verification_status:
                    context.add("warn", proposal_path, "Applied rewrite proposal has not been verified yet.")
                if proposal_status == "applied" and verification_status == "failed":
                    context.add(
                        "warn",
                        proposal_path,
                        "Applied rewrite proposal failed verification and should be reverted or regenerated.",
                    )


def _lint_governance_phase(context: _LintContext) -> None:
    knowledge_state_path = knowledge_lifecycle_state_path(context.root)
    concept_pages = sorted((context.root / "wiki" / "concepts").glob("*.md"))
    expected_lifecycle_paths = {page["path"] for page in context.decision_pages + context.judgment_pages} | {
        relative_path(context.root, path) for path in concept_pages
    }
    if expected_lifecycle_paths and not knowledge_state_path.exists():
        context.add("error", knowledge_state_path, "Missing knowledge lifecycle state file.")
    elif knowledge_state_path.exists():
        knowledge_state = load_json_document(knowledge_state_path)
        lifecycle_entries = knowledge_state.get("entries") if isinstance(knowledge_state, dict) else None
        if not isinstance(lifecycle_entries, list):
            context.add("error", knowledge_state_path, "Knowledge lifecycle state is not valid JSON.")
        else:
            if expected_lifecycle_paths and len(lifecycle_entries) != len(expected_lifecycle_paths):
                context.add(
                    "warn",
                    knowledge_state_path,
                    f"Knowledge lifecycle state entry count `{len(lifecycle_entries)}` does not match curated page count `{len(expected_lifecycle_paths)}`.",
                )
            for entry in lifecycle_entries:
                if not isinstance(entry, dict):
                    continue
                page_id = str(entry.get("page_id") or "")
                path = str(entry.get("path") or "")
                kind = str(entry.get("kind") or "")
                lifecycle_state = str(entry.get("lifecycle_state") or "")
                source_ids = entry.get("source_ids")
                active_corpus_ids = entry.get("active_corpus_ids")
                invalidation_signals = entry.get("invalidation_signals")
                if not page_id:
                    context.add("error", knowledge_state_path, "Knowledge lifecycle entry is missing `page_id`.")
                if kind not in set(KNOWLEDGE_LIFECYCLE_KINDS):
                    context.add(
                        "error",
                        knowledge_state_path,
                        f"Knowledge lifecycle entry has unsupported kind `{kind or 'unknown'}`.",
                    )
                if lifecycle_state not in KNOWLEDGE_LIFECYCLE_STATES:
                    context.add(
                        "error",
                        knowledge_state_path,
                        f"Knowledge lifecycle entry has unsupported state `{lifecycle_state or 'unknown'}`.",
                    )
                if not path:
                    context.add("error", knowledge_state_path, "Knowledge lifecycle entry is missing `path`.")
                elif not (context.root / path).exists():
                    context.add("error", knowledge_state_path, f"Knowledge lifecycle entry references missing page `{path}`.")
                elif expected_lifecycle_paths and path not in expected_lifecycle_paths:
                    context.add(
                        "warn",
                        knowledge_state_path,
                        f"Knowledge lifecycle entry references unmanaged page `{path}`.",
                    )
                if not isinstance(source_ids, list):
                    context.add("error", knowledge_state_path, "Knowledge lifecycle entry `source_ids` is not a list.")
                if not isinstance(active_corpus_ids, list):
                    context.add(
                        "error",
                        knowledge_state_path,
                        "Knowledge lifecycle entry `active_corpus_ids` is not a list.",
                    )
                if not isinstance(invalidation_signals, list):
                    context.add(
                        "error",
                        knowledge_state_path,
                        "Knowledge lifecycle entry `invalidation_signals` is not a list.",
                    )
                if kind in {"decision", "judgment"}:
                    judgment_lifecycle_state = str(entry.get("judgment_lifecycle_state") or "")
                    if judgment_lifecycle_state and judgment_lifecycle_state not in JUDGMENT_LIFECYCLE_STATES:
                        context.add(
                            "error",
                            knowledge_state_path,
                            f"Knowledge lifecycle entry `{page_id}` has unsupported judgment lifecycle state `{judgment_lifecycle_state}`.",
                        )
                    if not isinstance(entry.get("judgment_lifecycle_reason_codes", []), list):
                        context.add(
                            "error",
                            knowledge_state_path,
                            "Curated lifecycle entry `judgment_lifecycle_reason_codes` is not a list.",
                        )
                if kind == "concept":
                    if not isinstance(entry.get("issues"), list):
                        context.add("error", knowledge_state_path, "Concept lifecycle entry `issues` is not a list.")
                    if not isinstance(entry.get("review_signal_codes"), list):
                        context.add(
                            "error",
                            knowledge_state_path,
                            "Concept lifecycle entry `review_signal_codes` is not a list.",
                        )
                    if not isinstance(entry.get("source_pages"), list):
                        context.add(
                            "error",
                            knowledge_state_path,
                            "Concept lifecycle entry `source_pages` is not a list.",
                        )
                    if not str(entry.get("quality_state") or ""):
                        context.add(
                            "warn",
                            knowledge_state_path,
                            f"Concept lifecycle entry `{page_id}` is missing `quality_state`.",
                        )
                    if not isinstance(entry.get("override_reason_codes", []), list):
                        context.add(
                            "error",
                            knowledge_state_path,
                            "Concept lifecycle entry `override_reason_codes` is not a list.",
                        )
                    override_state = str(entry.get("override_state") or "")
                    if override_state and override_state not in KNOWLEDGE_LIFECYCLE_STATES:
                        context.add(
                            "error",
                            knowledge_state_path,
                            f"Concept lifecycle entry `{page_id}` has unsupported override state `{override_state}`.",
                        )
                    if not isinstance(entry.get("override_active"), bool):
                        context.add(
                            "error",
                            knowledge_state_path,
                            "Concept lifecycle entry `override_active` is not a bool.",
                        )

    knowledge_override_path = knowledge_lifecycle_override_state_path(context.root)
    if concept_pages and not knowledge_override_path.exists():
        context.add("error", knowledge_override_path, "Missing knowledge lifecycle override state file.")
    elif knowledge_override_path.exists():
        override_state = load_json_document(knowledge_override_path)
        override_entries = override_state.get("entries") if isinstance(override_state, dict) else None
        if not isinstance(override_entries, list):
            context.add(
                "error",
                knowledge_override_path,
                "Knowledge lifecycle override state is not valid JSON.",
            )
        else:
            active_override_paths: dict[str, int] = {}
            for entry in override_entries:
                if not isinstance(entry, dict):
                    continue
                slug = str(entry.get("slug") or "")
                path = str(entry.get("path") or "")
                kind = str(entry.get("kind") or "")
                lifecycle_state = str(entry.get("lifecycle_state") or "")
                if not slug:
                    context.add(
                        "error",
                        knowledge_override_path,
                        "Knowledge lifecycle override entry is missing `slug`.",
                    )
                if kind and kind != "concept":
                    context.add(
                        "error",
                        knowledge_override_path,
                        f"Knowledge lifecycle override entry has unsupported kind `{kind}`.",
                    )
                if lifecycle_state and lifecycle_state not in KNOWLEDGE_LIFECYCLE_STATES:
                    context.add(
                        "error",
                        knowledge_override_path,
                        f"Knowledge lifecycle override entry has unsupported state `{lifecycle_state}`.",
                    )
                if not isinstance(entry.get("active"), bool):
                    context.add(
                        "error",
                        knowledge_override_path,
                        "Knowledge lifecycle override entry `active` is not a bool.",
                    )
                if not path:
                    context.add(
                        "error",
                        knowledge_override_path,
                        "Knowledge lifecycle override entry is missing `path`.",
                    )
                elif not (context.root / path).exists():
                    context.add(
                        "error",
                        knowledge_override_path,
                        f"Knowledge lifecycle override entry references missing page `{path}`.",
                    )
                if bool(entry.get("active")):
                    active_override_paths[path] = active_override_paths.get(path, 0) + 1
                    if lifecycle_state != "retired":
                        context.add(
                            "warn",
                            knowledge_override_path,
                            f"Active concept lifecycle override for `{slug or path}` is `{lifecycle_state or 'unknown'}`; current workflow expects `retired`.",
                        )
            for path, count in active_override_paths.items():
                if path and count > 1:
                    context.add(
                        "error",
                        knowledge_override_path,
                        f"Multiple active knowledge lifecycle overrides reference `{path}`.",
                    )

    if context.manifest["entries"] and not concept_pages:
        context.add("warn", "wiki/concepts", "No concept pages have been compiled yet.")

    for page in concept_pages:
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        if frontmatter.get("kind") != "concept":
            context.add("warn", page, "Concept page kind is missing or incorrect.")
        if concept_summary_is_placeholder(content):
            context.add("warn", page, "Concept page still contains the fallback summary.")
        for section in ("## Conflict Signals", "## Evidence Gaps"):
            if section not in content:
                context.add("warn", page, f"Concept page is missing section `{section}`.")
        source_pages = frontmatter.get("source_pages", [])
        if not source_pages:
            context.add("warn", page, "Concept page has no source-page references.")
        if "hardness" not in frontmatter:
            context.add("warn", page, "Concept page is missing explicit `hardness` metadata.")
        else:
            raw_hardness = str(frontmatter.get("hardness") or "").strip().lower()
            hardness = normalize_concept_hardness(frontmatter.get("hardness"), default="")
            if hardness != raw_hardness:
                context.add(
                    "warn",
                    page,
                    f"Concept page has unsupported `hardness` metadata `{frontmatter.get('hardness', '')}`; expected one of `{', '.join(CONCEPT_HARDNESS_LEVELS)}`.",
                )
            elif hardness == "soft":
                context.add(
                    "warn",
                    page,
                    "Concept page is still marked `hardness: soft`; keep it in the repair backlog until grounded across more evidence or explicitly scoped down.",
                )
            else:
                confidence = str(frontmatter.get("confidence") or "").strip().lower()
                if confidence not in {"medium", "high"}:
                    context.add(
                        "warn",
                        page,
                        "Concept page with `hardness >= medium` should keep `confidence` at least `medium`.",
                    )
                if isinstance(source_pages, list) and len(source_pages) < 3:
                    context.add(
                        "warn",
                        page,
                        "Concept page with `hardness >= medium` should be grounded by at least 3 source pages.",
                    )
                conflict_section = preserved_section(content, "Conflict Signals", "")
                if "当前没有显式冲突信号" in conflict_section:
                    context.add(
                        "warn",
                        page,
                        "Concept page with `hardness >= medium` should record at least one explicit conflict or boundary signal.",
                    )
        for source_page in source_pages:
            candidate = context.root / source_page
            if not candidate.exists():
                context.add("error", page, f"Concept page references missing source page: `{source_page}`.")


def _lint_curated_phase(context: _LintContext) -> None:
    for group, expected_kind in (
        ("wiki/derived", "derived"),
        ("wiki/decisions", "decision"),
        ("wiki/judgments", "judgment"),
    ):
        for page in sorted((context.root / group).glob("*.md")):
            content = page.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            citations = [
                str(path)
                for path in frontmatter.get("citations", [])
                if isinstance(path, str) and path.strip()
            ]
            citation_snapshot_state = analyze_citation_snapshots(context.root, citations, frontmatter)
            if frontmatter.get("kind") != expected_kind:
                context.add("warn", page, f"{expected_kind.capitalize()} page kind is missing or incorrect.")
            if "wiki/sources/" not in content and "raw/" not in content:
                context.add("warn", page, f"{expected_kind.capitalize()} page has no explicit source-page reference.")
            if expected_kind in {"derived", "decision", "judgment"} and not citations:
                context.add(
                    "warn",
                    page,
                    f"{expected_kind.capitalize()} page is missing structured `citations` metadata.",
                )
            if expected_kind in {"derived", "decision", "judgment"} and citations and not frontmatter.get("citation_snapshots"):
                context.add(
                    "warn",
                    page,
                    f"{expected_kind.capitalize()} page is missing `citation_snapshots` metadata.",
                )
            for citation in citations:
                candidate = context.root / citation
                if not candidate.exists():
                    context.add(
                        "error",
                        page,
                        f"{expected_kind.capitalize()} page references missing citation path: `{citation}`.",
                    )
            if expected_kind in {"decision", "judgment"} and (
                citation_snapshot_state["missing"] or citation_snapshot_state["stale"]
            ):
                context.add(
                    "warn",
                    page,
                    f"{expected_kind.capitalize()} page has citation snapshot gaps: missing `{len(citation_snapshot_state['missing'])}` stale `{len(citation_snapshot_state['stale'])}`.",
                )
            if expected_kind in {"decision", "judgment"} and not frontmatter.get("protocol"):
                context.add("warn", page, f"{expected_kind.capitalize()} page is missing explicit `protocol` metadata.")
            if expected_kind in {"decision", "judgment"}:
                if not str(frontmatter.get("confidence") or "").strip():
                    context.add("warn", page, f"{expected_kind.capitalize()} page is missing explicit confidence metadata.")
                structured_keys = {
                    "counter_evidence": "structured `counter_evidence` metadata",
                    "invalidation_rule": "structured `invalidation_rule` metadata",
                    "next_signals": "structured `next_signals` metadata",
                    "revisit_after": "`revisit_after` metadata",
                    "escalate_after": "`escalate_after` metadata",
                    "formed_at": "`formed_at` metadata",
                    "last_reviewed": "`last_reviewed` metadata",
                }
                for key, label in structured_keys.items():
                    if key not in frontmatter:
                        context.add("warn", page, f"{expected_kind.capitalize()} page is missing {label}.")
                for key in ("counter_evidence", "next_signals"):
                    if key in frontmatter and not isinstance(frontmatter.get(key), list):
                        context.add("warn", page, f"{expected_kind.capitalize()} page `{key}` metadata should be a list.")
                if "counter_evidence" in frontmatter and not frontmatter_string_list(frontmatter, "counter_evidence"):
                    context.add("warn", page, f"{expected_kind.capitalize()} page has empty structured `counter_evidence` metadata.")
                if "next_signals" in frontmatter and not frontmatter_string_list(frontmatter, "next_signals"):
                    context.add("warn", page, f"{expected_kind.capitalize()} page has empty structured `next_signals` metadata.")
                if "invalidation_rule" in frontmatter and not str(frontmatter.get("invalidation_rule") or "").strip():
                    context.add("warn", page, f"{expected_kind.capitalize()} page has empty structured `invalidation_rule` metadata.")
                if "formed_at" in frontmatter and not str(frontmatter.get("formed_at") or "").strip():
                    context.add("warn", page, f"{expected_kind.capitalize()} page has empty `formed_at` metadata.")
                if frontmatter.get("reviewed_at") and not str(frontmatter.get("last_reviewed") or "").strip():
                    context.add("warn", page, f"Reviewed {expected_kind} page is missing `last_reviewed` metadata.")
            if expected_kind == "decision":
                if frontmatter.get("status") not in DECISION_STATUSES:
                    context.add(
                        "warn",
                        page,
                        f"Decision page has unsupported status `{frontmatter.get('status', '')}`.",
                    )
                for section in ("## Decision", "## Evidence"):
                    if section not in content:
                        context.add("warn", page, f"Decision page is missing section `{section}`.")
                for section in ("## Review Status", "## Review Notes"):
                    if section not in content:
                        context.add("warn", page, f"Decision page is missing section `{section}`.")
                for heading in CURATED_ASSET_SECTION_ORDER:
                    snapshot = curated_asset_section_snapshot(
                        content,
                        heading,
                        revisit_after=str(frontmatter.get("revisit_after") or ""),
                        escalate_after=str(frontmatter.get("escalate_after") or ""),
                    )
                    if not snapshot["present"]:
                        context.add("warn", page, f"Decision page is missing section `## {heading}`.")
                    elif (
                        heading != "Review History"
                        and frontmatter.get("status") in {"approved", "needs-revisit", "superseded"}
                        and not snapshot["meaningful"]
                    ):
                        context.add("warn", page, f"Decision page still has placeholder `{heading}` content.")
                    elif heading == "Review History" and frontmatter.get("reviewed_at") and not snapshot["meaningful"]:
                        context.add("warn", page, "Decision page is reviewed but has no populated `Review History`.")
                if frontmatter.get("status") in {"approved", "needs-revisit", "superseded"} and not frontmatter.get(
                    "reviewed_at"
                ):
                    context.add("warn", page, "Reviewed decision page is missing `reviewed_at`.")
                if frontmatter.get("reviewed_at") and citation_snapshot_state["has_drift"]:
                    context.add(
                        "warn",
                        page,
                        f"Reviewed decision page has citation drift: drifted `{len(citation_snapshot_state['drifted'])}` missing `{len(citation_snapshot_state['missing'])}` stale `{len(citation_snapshot_state['stale'])}`.",
                    )
            if expected_kind == "judgment":
                if frontmatter.get("status") not in JUDGMENT_STATUSES:
                    context.add(
                        "warn",
                        page,
                        f"Judgment page has unsupported status `{frontmatter.get('status', '')}`.",
                    )
                for section in ("## Judgment", "## Signals"):
                    if section not in content:
                        context.add("warn", page, f"Judgment page is missing section `{section}`.")
                for section in ("## Review Status", "## Review Notes"):
                    if section not in content:
                        context.add("warn", page, f"Judgment page is missing section `{section}`.")
                for heading in CURATED_ASSET_SECTION_ORDER:
                    snapshot = curated_asset_section_snapshot(
                        content,
                        heading,
                        revisit_after=str(frontmatter.get("revisit_after") or ""),
                        escalate_after=str(frontmatter.get("escalate_after") or ""),
                    )
                    if not snapshot["present"]:
                        context.add("warn", page, f"Judgment page is missing section `## {heading}`.")
                    elif (
                        heading != "Review History"
                        and frontmatter.get("status") in {"tracking", "confirmed", "rejected"}
                        and not snapshot["meaningful"]
                    ):
                        context.add("warn", page, f"Judgment page still has placeholder `{heading}` content.")
                    elif heading == "Review History" and frontmatter.get("reviewed_at") and not snapshot["meaningful"]:
                        context.add("warn", page, "Judgment page is reviewed but has no populated `Review History`.")
                if frontmatter.get("status") in {"tracking", "confirmed", "rejected"} and not frontmatter.get(
                    "reviewed_at"
                ):
                    context.add("warn", page, "Reviewed judgment page is missing `reviewed_at`.")
                if frontmatter.get("reviewed_at") and citation_snapshot_state["has_drift"]:
                    context.add(
                        "warn",
                        page,
                        f"Reviewed judgment page has citation drift: drifted `{len(citation_snapshot_state['drifted'])}` missing `{len(citation_snapshot_state['missing'])}` stale `{len(citation_snapshot_state['stale'])}`.",
                    )


_LINT_REPORT_KEEP = 10


def _rotate_lint_reports(lint_dir: Path) -> None:
    """Keep only the most recent _LINT_REPORT_KEEP lint reports."""
    reports = sorted(lint_dir.glob("lint-*.md"))
    if len(reports) <= _LINT_REPORT_KEEP:
        return
    for old in reports[: len(reports) - _LINT_REPORT_KEEP]:
        old.unlink(missing_ok=True)


def _write_lint_report(context: _LintContext) -> dict[str, Any]:
    generated_at = utc_now()
    report_name = f"lint-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
    lint_dir = context.root / "output" / "lint"
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
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
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


def render_repair_backlog(
    compile_result: dict[str, Any],
    lint_result: dict[str, Any],
    memory: dict[str, Any],
    active_protocol: str,
    promotion_result: dict[str, Any],
    pending_sources: list[str],
    placeholder_concepts: list[str],
    pending_review_decisions: list[dict[str, str]],
    pending_review_judgments: list[dict[str, str]],
    overdue_pages: list[dict[str, str]],
    escalated_pages: list[dict[str, str]],
    semantic_report: str,
    generated_at: str,
) -> str:
    drift = memory.get("drift", {})
    health = memory.get("health", {})
    transition = memory.get("transition", {})
    findings = lint_result.get("findings", [])
    error_findings = [finding for finding in findings if finding["severity"] == "error"]
    warn_findings = [finding for finding in findings if finding["severity"] == "warn"]
    sources_without_concepts = drift.get("sources_without_concepts", [])
    isolated_sources = health.get("isolated_source_ids", [])
    singleton_concepts = health.get("singleton_concept_slugs", [])
    bridge_concepts = health.get("bridge_concept_slugs", [])
    overloaded_concepts = health.get("overloaded_concept_slugs", [])
    actions = health.get("actions", [])
    overdue_actions = health.get("overdue_actions", [])
    escalated_actions = health.get("escalated_actions", [])
    inactive_actions = health.get("inactive_actions", [])
    repair_plan = health.get("repair_plan", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]
    apply_ready_actions = [action for action in actions if action_supports_low_risk_apply(action)]
    execution_proposals = repair_plan.get("execution_proposals", [])
    counter_evidence_scan = health.get("counter_evidence_scan", {})
    counter_evidence_pages = counter_evidence_scan.get("pages", []) if isinstance(counter_evidence_scan, dict) else []
    judgment_review_actions = health.get("judgment_review_actions", [])
    promotions = promotion_result.get("pages", [])
    lines = [
        "# 修复待办",
        "",
        f"- 生成时间：`{generated_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 本轮编译改动页数：`{compile_result.get('changed_pages', 0)}`",
        f"- 机器记忆是否变化：`{compile_result.get('machine_memory_changed', False)}`",
        f"- Lint 错误：`{lint_result['counts']['errors']}`",
        f"- Lint 警告：`{lint_result['counts']['warnings']}`",
        f"- 待补来源摘要：`{len(pending_sources)}`",
        f"- 占位概念摘要：`{len(placeholder_concepts)}`",
        f"- 待审决策：`{len(pending_review_decisions)}`",
        f"- 待审判断：`{len(pending_review_judgments)}`",
        f"- 已到期复审：`{len(overdue_pages)}`",
        f"- 升级处理项：`{len(escalated_pages)}`",
        f"- 自动晋升页面：`{promotion_result.get('count', 0)}`",
        f"- 图谱修复动作：`{len(actions)}`",
        f"- 动作已到期：`{len(overdue_actions)}`",
        f"- 动作需升级：`{len(escalated_actions)}`",
        f"- 最近清除动作：`{len(inactive_actions)}`",
        f"- Ready 动作：`{repair_plan.get('counts', {}).get('ready', 0)}`",
        f"- 待分流动作：`{repair_plan.get('counts', {}).get('triage', 0)}`",
        f"- 执行批次：`{repair_plan.get('counts', {}).get('batches', 0)}`",
        f"- 执行提案：`{repair_plan.get('counts', {}).get('proposals', 0)}`",
        f"- 弱概念页：`{concept_quality.get('counts', {}).get('weak', 0)}`",
        f"- Soft 概念页：`{concept_quality.get('counts', {}).get('soft_hardness', 0)}`",
        f"- Medium+/Hard 概念页：`{concept_quality.get('counts', {}).get('medium_or_hard', 0)}`",
        f"- 概念合并候选：`{concept_quality.get('counts', {}).get('merge_candidates', 0)}`",
        f"- 概念冲突信号：`{concept_quality.get('counts', {}).get('conflict_signals', 0)}`",
        f"- 概念证据缺口：`{concept_quality.get('counts', {}).get('gap_signals', 0)}`",
        f"- Rewrite 提案：`{rewrite_state.get('counts', {}).get('active', 0)}`",
        f"- 待审 Rewrite：`{rewrite_state.get('counts', {}).get('pending_review', 0)}`",
        f"- 可应用 Rewrite：`{len(apply_ready_rewrites)}`",
        f"- 可安全执行动作：`{len(apply_ready_actions)}`",
        f"- Counter-evidence candidates：`{len(counter_evidence_pages)}`",
        f"- Judgment review actions：`{len(judgment_review_actions)}`",
        f"- 图谱修复候选：`{len(health.get('link_suggestions', []))}`",
        f"- 无概念覆盖来源：`{len(sources_without_concepts)}`",
        f"- 图谱分量数：`{health.get('component_count', 0)}`",
        f"- 孤立来源：`{len(isolated_sources)}`",
        f"- 单节点概念：`{len(singleton_concepts)}`",
        f"- 桥接概念：`{len(bridge_concepts)}`",
        f"- 过载概念：`{len(overloaded_concepts)}`",
        "",
        "## 优先队列",
    ]
    if PROTOCOL_LIBRARY.get(active_protocol, {}).get("nightly"):
        lines.extend(["### 协议 Nightly 焦点"])
        for focus in PROTOCOL_LIBRARY.get(active_protocol, {}).get("nightly", []):
            lines.append(f"- {focus}")
        lines.append("")
    if error_findings:
        lines.append(f"1. 先解决 `{len(error_findings)}` 个 lint 错误，再继续依赖下游输出。")
    if pending_sources:
        lines.append(f"2. 补齐 `{len(pending_sources)}` 个仍是占位摘要的来源页。")
    if placeholder_concepts:
        lines.append(f"3. 重写 `{len(placeholder_concepts)}` 个仍使用回退摘要的概念页。")
    if concept_quality.get("counts", {}).get("weak", 0):
        lines.append(f"3a. 按概念质量看板优先处理 `{concept_quality.get('counts', {}).get('weak', 0)}` 个弱概念页。")
    if concept_quality.get("counts", {}).get("soft_hardness", 0):
        lines.append(
            f"3d. 把 `{concept_quality.get('counts', {}).get('soft_hardness', 0)}` 个仍停留在 `hardness: soft` 的概念页提升到更可复用的结构层。"
        )
    if rewrite_state.get("counts", {}).get("pending_review", 0):
        lines.append(f"3b. 先审 `{rewrite_state.get('counts', {}).get('pending_review', 0)}` 个 concept rewrite proposal。")
    if apply_ready_rewrites:
        lines.append(f"3c. 应用 `{len(apply_ready_rewrites)}` 个已接受的 concept rewrite proposal，让概念页先收敛。")
    if pending_review_decisions:
        lines.append(f"4. 审阅 `{len(pending_review_decisions)}` 个等待批准或复审的决策页。")
    if pending_review_judgments:
        lines.append(f"5. 审阅 `{len(pending_review_judgments)}` 个仍处于暂定或跟踪状态的判断页。")
    if overdue_pages:
        lines.append(f"6. 先清理 `{len(overdue_pages)}` 个已到期但还没复审的页面。")
    if escalated_pages:
        lines.append(f"7. 提升 `{len(escalated_pages)}` 个已经超过升级阈值的页面优先级。")
    if counter_evidence_pages:
        lines.append(f"7a. 审阅 `{len(counter_evidence_pages)}` 个新 source 触发的 counter-evidence candidate。")
    if judgment_review_actions:
        lines.append(f"7b. 执行 `{len(judgment_review_actions)}` 个 judgment review action，把升级项推进进显式 review workflow。")
    if promotions:
        lines.append(f"8. 检查本轮自动晋升的 `{len(promotions)}` 个页面，确认是否需要补证据和审阅。")
    if actions:
        lines.append(f"9. 按动作队列处理 `{len(actions)}` 个 machine-memory 修复动作。")
    if repair_plan.get("counts", {}).get("ready", 0):
        lines.append(
            f"9a. 先执行 `{repair_plan.get('counts', {}).get('ready', 0)}` 个已接受动作和 `{repair_plan.get('counts', {}).get('batches', 0)}` 个批次。"
        )
    if repair_plan.get("counts", {}).get("proposals", 0):
        lines.append(f"9b. 参考 `{repair_plan.get('counts', {}).get('proposals', 0)}` 个页级执行提案决定下一批修复。")
    if apply_ready_actions:
        lines.append(f"9c. 其中 `{len(apply_ready_actions)}` 个低风险动作可直接走 `apply-action` 半自动执行。")
    if overdue_actions:
        lines.append(f"10. 优先清理 `{len(overdue_actions)}` 个已到期待处理的 machine-memory 动作。")
    if escalated_actions:
        lines.append(f"11. 先处理 `{len(escalated_actions)}` 个已升级的 machine-memory 动作。")
    if concept_quality.get("counts", {}).get("conflict_signals", 0):
        lines.append(f"11a. 先把 `{concept_quality.get('counts', {}).get('conflict_signals', 0)}` 个概念冲突信号显式写进相关概念页。")
    if health.get("link_suggestions", []):
        lines.append(f"12. 审阅 `{len(health.get('link_suggestions', []))}` 个机器记忆补链候选，决定是否补链接。")
    if sources_without_concepts:
        lines.append(f"13. 检查 `{len(sources_without_concepts)}` 个没有概念覆盖的来源。")
    if isolated_sources:
        lines.append(f"14. 把 `{len(isolated_sources)}` 个孤立来源节点接入概念图谱。")
    if singleton_concepts:
        lines.append(f"15. 复查 `{len(singleton_concepts)}` 个还没接入更大上下文的单节点概念。")
    if overloaded_concepts:
        lines.append(f"16. 考虑拆分 `{len(overloaded_concepts)}` 个过载概念。")
    if transition.get("changed"):
        lines.append("17. 在下一轮研究前先检查最新的机器记忆漂移。")
    if not any(
        (
            error_findings,
            pending_sources,
            placeholder_concepts,
            pending_review_decisions,
            pending_review_judgments,
            overdue_pages,
            escalated_pages,
            promotions,
            sources_without_concepts,
            isolated_sources,
            singleton_concepts,
            overloaded_concepts,
            transition.get("changed"),
        )
    ):
        lines.append("1. 当前没有紧急修复项，继续观察 nightly 漂移和 lint 输出。")
    lines.extend(
        [
            "",
            "## 可执行事项",
        ]
    )
    if error_findings:
        lines.append("### Lint 错误")
        for finding in error_findings[:10]:
            lines.append(f"- `{finding['path']}`: {finding['message']}")
    if warn_findings:
        lines.append("")
        lines.append("### Lint 警告")
        for finding in warn_findings[:10]:
            lines.append(f"- `{finding['path']}`: {finding['message']}")
    if pending_sources:
        lines.append("")
        lines.append("### 待补来源摘要")
        for source_id in pending_sources[:10]:
            lines.append(f"- `wiki/sources/{source_id}.md`")
    if placeholder_concepts:
        lines.append("")
        lines.append("### 占位概念摘要")
        for slug in placeholder_concepts[:10]:
            lines.append(f"- `wiki/concepts/{slug}.md`")
    if pending_review_decisions or pending_review_judgments:
        lines.append("")
        lines.append("### 审阅队列")
        for page in pending_review_decisions[:10]:
            lines.append(f"- 决策：`{page['path']}` 状态 `{display_curated_status(page['status'])}`")
        for page in pending_review_judgments[:10]:
            lines.append(f"- 判断：`{page['path']}` 状态 `{display_curated_status(page['status'])}`")
    if overdue_pages or escalated_pages:
        lines.append("")
        lines.append("### Aging 信号")
        for page in escalated_pages[:10]:
            lines.append(f"- 升级：`{page['path']}` | 状态 `{display_curated_status(page['status'])}`")
        for page in overdue_pages[:10]:
            if page in escalated_pages[:10]:
                continue
            lines.append(f"- 到期：`{page['path']}` | 状态 `{display_curated_status(page['status'])}`")
    if counter_evidence_pages:
        lines.append("")
        lines.append("### Counter-evidence Candidates")
        for candidate in counter_evidence_pages[:10]:
            if not isinstance(candidate, dict):
                continue
            lines.append(
                f"- `{candidate.get('page_path', '')}`"
                f" | candidates `{candidate.get('candidate_count', 0)}`"
                f" | sources `{', '.join(candidate.get('source_ids', [])) or 'none'}`"
                f" | shared `{', '.join(candidate.get('shared_terms', [])) or 'none'}`"
            )
    if judgment_review_actions:
        lines.append("")
        lines.append("### Judgment Review Actions")
        for action in judgment_review_actions[:10]:
            if not isinstance(action, dict):
                continue
            command = str(action.get("review_command") or "")
            command_suffix = f" | command `{command}`" if command else ""
            lines.append(
                f"- `{action.get('title', 'review action')}`"
                f" | priority `{action.get('priority', 'medium')}`"
                f" | reasons `{', '.join(action.get('reason_codes', [])) or 'none'}`"
                f"{command_suffix}"
            )
    if promotions:
        lines.append("")
        lines.append("### 本轮自动晋升")
        for promotion in promotions[:10]:
            label = "决策" if promotion["kind"] == "decision" else "判断"
            lines.append(
                f"- {label}：`{promotion['path']}` | 动作 `{promotion['action']}` | 重复次数 `{promotion['occurrences']}`"
            )
    lines.append("")
    lines.append("### Machine Memory 动作")
    if actions:
        for action in actions[:10]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            action_status = display_action_status(str(action.get("status")))
            lines.append(
                f"- [{action['priority']}] `{action['primary_path']}`"
                f"{detail}"
                f" | {action['title']}"
                f" | status `{action_status}`"
                f" | seen `{action.get('occurrences', 0)}`"
            )
    else:
        lines.append("- 当前没有 machine-memory 动作。")
    if escalated_actions or overdue_actions:
        lines.append("")
        lines.append("### Action Aging")
        for action in escalated_actions[:10]:
            action_status = display_action_status(str(action.get("status")))
            lines.append(
                f"- 升级：`{action['id']}` | {action['title']} | status `{action_status}`"
            )
        for action in overdue_actions[:10]:
            if any(action["id"] == escalated["id"] for escalated in escalated_actions[:10]):
                continue
            lines.append(
                f"- 到期：`{action['id']}` | {action['title']} | revisit `{action.get('revisit_after', '') or 'none'}`"
            )
    if inactive_actions:
        lines.append("")
        lines.append("### 最近清除动作")
        for action in inactive_actions[:10]:
            lines.append(
                f"- 清除：`{action['id']}` | {action['title']} | inactive_since `{action.get('inactive_since', '') or 'none'}`"
            )
    if concept_quality.get("weak_concepts"):
        lines.append("")
        lines.append("### 弱概念页")
        for concept in concept_quality.get("weak_concepts", [])[:10]:
            lines.append(
                f"- `{concept['path']}` | issues `{', '.join(concept.get('issues', [])) or 'none'}`"
                f" | sources `{concept.get('source_count', 0)}`"
            )
    if concept_quality.get("rewrite_candidates"):
        lines.append("")
        lines.append("### 概念重写优先级")
        for candidate in concept_quality.get("rewrite_candidates", [])[:8]:
            lines.append(
                f"- `{candidate['path']}` | priority `{candidate.get('priority', 'n/a')}`"
                f" | strategy `{candidate.get('rewrite_strategy', 'n/a')}`"
            )
    if rewrite_proposals:
        lines.append("")
        lines.append("### Rewrite Proposals")
        for proposal in rewrite_proposals[:8]:
            command = f"PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite {proposal['slug']} --status accepted"
            if proposal.get("status") == "applied" and str(proposal.get("previous_markdown") or ""):
                command = f"PYTHONPATH=src python3 -m aiwiki.cli --root . revert-rewrite {proposal['slug']}"
            elif proposal.get("apply_ready"):
                command = f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {proposal['slug']}"
            lines.append(
                f"- `{proposal['target_path']}` | status `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`"
                f" | quality `{proposal.get('quality_score', 0)}`"
                f" | verify `{proposal.get('verification_status', '') or 'pending'}`"
                f" | strategy `{proposal.get('rewrite_strategy', 'n/a')}` | command `{command}`"
            )
    if concept_quality.get("conflict_signals"):
        lines.append("")
        lines.append("### 概念冲突信号")
        for signal in concept_quality.get("conflict_signals", [])[:8]:
            lines.append(
                f"- `{signal['slug']}` | signal `{signal.get('label', 'n/a')}`"
                f" | sources `{', '.join(signal.get('source_pages', [])) or 'none'}`"
            )
    if concept_quality.get("merge_candidates"):
        lines.append("")
        lines.append("### 概念合并候选")
        for candidate in concept_quality.get("merge_candidates", [])[:8]:
            lines.append(
                f"- `{candidate['left_slug']}` <-> `{candidate['right_slug']}`"
                f" | shared_sources `{len(candidate.get('shared_sources', []))}`"
                f" | shared_tokens `{', '.join(candidate.get('shared_tokens', [])) or 'none'}`"
            )
    if repair_plan.get("execution_batches"):
        lines.append("")
        lines.append("### 执行批次")
        for batch in repair_plan.get("execution_batches", [])[:8]:
            lines.append(
                f"- {batch['label']} | actions `{len(batch.get('actions', []))}`"
                f" | escalated `{batch.get('escalated', False)}`"
                f" | overdue `{batch.get('overdue', False)}`"
                f" | primary `{', '.join(batch.get('primary_paths', [])) or 'none'}`"
            )
    if execution_proposals:
        lines.append("")
        lines.append("### Repair Execution Proposals")
        for proposal in execution_proposals[:8]:
            lines.append(
                f"- `{proposal['action_id']}` | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
                f" | risk `{proposal.get('risk', 'medium')}`"
                f" | strategy `{proposal.get('summary', 'n/a')}`"
            )
    if apply_ready_actions:
        lines.append("")
        lines.append("### Safe Apply Actions")
        for action in apply_ready_actions[:8]:
            lines.append(
                f"- `{action['id']}` | `{action['title']}`"
                f" | command `{action.get('command_hint', '')}`"
                f" | primary `{action.get('primary_path', '')}`"
            )
    if health.get("link_suggestions", []):
        lines.append("")
        lines.append("### 图谱修复候选")
        for suggestion in health.get("link_suggestions", [])[:10]:
            lines.append(
                f"- `{suggestion['source_page']}` -> `{suggestion['concept_page']}`"
                f" | shared `{', '.join(suggestion['shared_terms'][:6])}`"
                f" | score `{suggestion['score']}`"
            )
    if sources_without_concepts:
        lines.append("")
        lines.append("### 无概念覆盖来源")
        for source_id in sources_without_concepts[:10]:
            lines.append(f"- `wiki/sources/{source_id}.md`")
    lines.append("")
    lines.append("### 图谱修复建议")
    if isolated_sources:
        for source_id in isolated_sources[:10]:
            lines.append(f"- 将孤立来源 `wiki/sources/{source_id}.md` 至少连接到一个稳定概念。")
    if singleton_concepts:
        for slug in singleton_concepts[:10]:
            lines.append(f"- 检查单节点概念 `wiki/concepts/{slug}.md` 是否缺少相关概念或来源链接。")
    if overloaded_concepts:
        for slug in overloaded_concepts[:10]:
            lines.append(f"- 考虑把过宽的概念 `wiki/concepts/{slug}.md` 拆成更窄的页面。")
    if bridge_concepts:
        lines.append(f"- 保留桥接概念：`{', '.join(bridge_concepts[:10])}`，因为它们连接了多个簇。")
    if not any((isolated_sources, singleton_concepts, overloaded_concepts, bridge_concepts)):
        lines.append("- 当前没有图谱专项修复项。")
    if transition.get("changed"):
        lines.append("")
        lines.append("### 结构漂移")
        lines.append(f"- 上一版摘要：`{transition.get('previous_digest', '') or 'none'}`")
        lines.append(f"- 当前摘要：`{transition.get('current_digest', '') or 'none'}`")
        lines.append(f"- 新增来源节点：`{len(transition.get('added_source_ids', []))}`")
        lines.append(f"- 新增概念节点：`{len(transition.get('added_concept_slugs', []))}`")
        lines.append(f"- 新增边：`{transition.get('added_edges', 0)}`")
        lines.append(f"- 移除边：`{transition.get('removed_edges', 0)}`")
    lines.extend(
        [
            "",
            "## 相关产物",
            f"- Lint 报告：`{lint_result['path']}`",
            "- Aging 报告：`wiki/indexes/aging-report.md`",
            "- 认知历史：`wiki/indexes/cognitive-history.md`",
            "- 机器记忆：`wiki/indexes/machine-memory.md`",
            "- 拓扑视图：`wiki/indexes/machine-memory-topology.md`",
            "- 动作队列：`wiki/indexes/machine-memory-actions.md`",
            "- 修复计划：`wiki/indexes/machine-memory-repair-plan.md`",
            "- 图谱健康：`wiki/indexes/graph-health.md`",
            "- 漂移报告：`wiki/indexes/drift-report.md`",
            "- 审阅队列：`wiki/indexes/review-queue.md`",
            "- 规则索引：`schema/index.md`",
        ]
    )
    if semantic_report:
        lines.append(f"- 语义 lint：`{semantic_report}`")
    return "\n".join(lines) + "\n"


@runtime_write_operation
def write_nightly_health(
    root: Path,
    compile_result: dict[str, Any],
    lint_result: dict[str, Any],
    *,
    promotion_result: dict[str, Any] | None = None,
    semantic_report: str = "",
    llm_used: bool = False,
    runtime_history_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    promotion_result = promotion_result or {"count": 0, "created": 0, "updated": 0, "pages": []}
    manifest = load_manifest(root)
    memory = load_machine_memory(root)
    pending_sources = pending_source_summary_ids(root, manifest["entries"])
    placeholder_concepts = placeholder_concept_slugs(root)
    decisions = collect_curated_pages(root, "decisions", "decision")
    judgments = collect_curated_pages(root, "judgments", "judgment")
    protocol_state = load_protocol_state(root)
    queue = review_queue(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    aging = collect_aging_signals(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    generated_at = utc_now()
    active_corpora_before = load_active_corpora_state(root)
    previous_status_by_corpus = {
        str(corpus.get("corpus_id") or ""): str(corpus.get("status") or "")
        for corpus in active_corpora_before.get("corpora", [])
        if corpus.get("corpus_id")
    }
    active_corpora_state = reconcile_active_corpora_state(root, changed_at=generated_at, nightly_cooldown=True)
    active_corpora = active_corpora_state["corpora"]
    cooled_corpus_ids = [
        str(corpus.get("corpus_id") or "")
        for corpus in active_corpora
        if str(corpus.get("status") or "") == "cooling"
        and previous_status_by_corpus.get(str(corpus.get("corpus_id") or "")) == "active"
    ]
    expired_corpus_ids = [
        str(corpus.get("corpus_id") or "")
        for corpus in active_corpora
        if str(corpus.get("status") or "") == "expired"
        and previous_status_by_corpus.get(str(corpus.get("corpus_id") or "")) != "expired"
    ]
    runtime_history_event = {
        "event_type": "nightly",
        "occurred_at": generated_at,
        "protocol": protocol_state["active_protocol"],
        "cooled_corpus_ids": cooled_corpus_ids,
        "expired_corpus_ids": expired_corpus_ids,
        "overdue_pages": [page["path"] for page in aging["overdue"]],
        "escalated_pages": [page["path"] for page in aging["escalated"]],
        "state_path": relative_path(root, nightly_health_state_path(root)),
        "repair_backlog": relative_path(root, repair_backlog_path(root)),
        "active_corpus_ids": [
            str(corpus.get("corpus_id") or "")
            for corpus in active_corpora
            if str(corpus.get("status") or "") == "active"
        ],
    }
    if runtime_history_extra:
        for key, value in runtime_history_extra.items():
            if key not in {"event_type", "occurred_at", "protocol"}:
                runtime_history_event[str(key)] = value
    append_runtime_history(root, runtime_history_event)
    material_state = refresh_material_state(
        root,
        generated_at=generated_at,
        entries=manifest["entries"],
        active_protocol=protocol_state["active_protocol"],
    )
    material_routing = load_material_routing_state(root)
    archive_candidates = load_archive_candidates_state(root)
    planner_state = refresh_nightly_planner_execution_state(
        root,
        load_planner_state(root),
        generated_at=generated_at,
        active_protocol=protocol_state["active_protocol"],
    )
    knowledge_lifecycle = refresh_knowledge_lifecycle_state(
        root,
        generated_at=generated_at,
        decisions=decisions,
        judgments=judgments,
        entries=manifest["entries"],
        active_corpora_state=active_corpora_state,
        memory=memory,
    )
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=protocol_state["active_protocol"],
    )
    state = {
        "generated_at": generated_at,
        "llm_used": llm_used,
        "protocol": {
            "active_protocol": protocol_state["active_protocol"],
            "state_path": protocol_state["state_path"],
            "available_protocols": protocol_state["available_protocols"],
            "dashboard_path": "wiki/indexes/protocols.md",
            "review_focus": PROTOCOL_LIBRARY.get(protocol_state["active_protocol"], {}).get("review", []),
            "nightly_focus": PROTOCOL_LIBRARY.get(protocol_state["active_protocol"], {}).get("nightly", []),
        },
        "compile": compile_result,
        "lint": {
            "path": lint_result["path"],
            "counts": lint_result["counts"],
        },
        "semantic_report": semantic_report,
        "material_state": {
            "path": relative_path(root, material_state_path(root)),
            "entry_count": len(material_state["entries"]),
        },
        "material_routing": {
            "path": relative_path(root, material_routing_state_path(root)),
            "entry_count": len(material_routing.get("entries", [])),
            "active_protocol": material_routing.get("active_protocol", protocol_state["active_protocol"]),
        },
        "archive_candidates": {
            "path": relative_path(root, archive_candidates_state_path(root)),
            "entry_count": len(archive_candidates.get("entries", [])),
            "ready_ids": [
                str(entry.get("entry_id") or "")
                for entry in archive_candidates.get("entries", [])
                if str(entry.get("status") or "") == "ready"
            ],
            "deferred_ids": [
                str(entry.get("entry_id") or "")
                for entry in archive_candidates.get("entries", [])
                if str(entry.get("status") or "") == "deferred"
            ],
        },
        "planner": {
            "state_path": relative_path(root, planner_state_path(root)),
            "executed_actions": int(planner_state.get("counts", {}).get("executed_actions", 0) or 0),
            "pending_proposals": int(planner_state.get("counts", {}).get("pending_proposals", 0) or 0),
            "recent_executed_action_ids": [
                str(item.get("action_id") or "")
                for item in planner_state.get("executed_actions", [])[:6]
                if str(item.get("action_id") or "")
            ],
        },
        "active_corpora": {
            "path": relative_path(root, active_corpora_state_path(root)),
            "count": len(active_corpora),
            "active_ids": [
                str(corpus.get("corpus_id") or "")
                for corpus in active_corpora
                if str(corpus.get("status") or "") == "active"
            ],
            "cooling_ids": [
                str(corpus.get("corpus_id") or "")
                for corpus in active_corpora
                if str(corpus.get("status") or "") == "cooling"
            ],
            "expired_ids": [
                str(corpus.get("corpus_id") or "")
                for corpus in active_corpora
                if str(corpus.get("status") or "") == "expired"
            ],
        },
        "knowledge_lifecycle": {
            "path": relative_path(root, knowledge_lifecycle_state_path(root)),
            "overrides_path": relative_path(root, knowledge_lifecycle_override_state_path(root)),
            "entry_count": len(knowledge_lifecycle.get("entries", [])),
            "state_counts": dict(knowledge_lifecycle.get("counts", {}).get("by_state", {})),
            "kind_counts": dict(knowledge_lifecycle.get("counts", {}).get("by_kind", {})),
            "invalidated_page_ids": [
                str(entry.get("page_id") or "")
                for entry in knowledge_lifecycle.get("entries", [])
                if entry.get("invalidation_signals")
            ],
            "active_page_ids": [
                str(entry.get("page_id") or "")
                for entry in knowledge_lifecycle.get("entries", [])
                if str(entry.get("lifecycle_state") or "") == "active"
            ],
            "active_concept_ids": [
                str(entry.get("page_id") or "")
                for entry in knowledge_lifecycle.get("entries", [])
                if str(entry.get("kind") or "") == "concept"
                and entry.get("active_corpus_ids")
            ],
            "retired_concept_ids": [
                str(entry.get("page_id") or "")
                for entry in knowledge_lifecycle.get("entries", [])
                if str(entry.get("kind") or "") == "concept"
                and str(entry.get("lifecycle_state") or "") == "retired"
            ],
            "governance_summary": {
                "concept_backlog_count": lifecycle_summary.get("counts", {}).get("concept_backlog", 0),
                "review_concept_count": lifecycle_summary.get("counts", {}).get("review_concepts", 0),
                "revisit_concept_count": lifecycle_summary.get("counts", {}).get("revisit_concepts", 0),
                "retired_concept_count": lifecycle_summary.get("counts", {}).get("retired_concepts", 0),
                "concept_backlog_ids": [
                    str(entry.get("page_id") or "")
                    for entry in lifecycle_summary.get("concept_backlog", [])
                ],
                "review_concept_ids": [
                    str(entry.get("page_id") or "")
                    for entry in lifecycle_summary.get("review_concepts", [])
                ],
                "revisit_concept_ids": [
                    str(entry.get("page_id") or "")
                    for entry in lifecycle_summary.get("revisit_concepts", [])
                ],
                "retired_concept_ids": [
                    str(entry.get("page_id") or "")
                    for entry in lifecycle_summary.get("retired_concepts", [])
                ],
            },
        },
        "promotions": promotion_result,
        "aging": {
            "overdue_pages": [page["path"] for page in aging["overdue"]],
            "escalated_pages": [page["path"] for page in aging["escalated"]],
            "scheduled_pages": [page["path"] for page in aging["scheduled"]],
        },
        "concept_quality": {
            "path": relative_path(root, concept_quality_path(root)),
            "weak_concept_slugs": [
                concept["slug"] for concept in memory.get("health", {}).get("concept_quality", {}).get("weak_concepts", [])
            ],
            "rewrite_candidate_slugs": [
                concept["slug"]
                for concept in memory.get("health", {}).get("concept_quality", {}).get("rewrite_candidates", [])
            ],
            "merge_candidates": memory.get("health", {}).get("concept_quality", {}).get("counts", {}).get("merge_candidates", 0),
            "conflict_signals": memory.get("health", {}).get("concept_quality", {}).get("counts", {}).get("conflict_signals", 0),
            "gap_signals": memory.get("health", {}).get("concept_quality", {}).get("counts", {}).get("gap_signals", 0),
        },
        "concept_rewrite": {
            "path": relative_path(root, concept_rewrite_index_path(root)),
            "state_path": memory.get("health", {}).get("concept_rewrite", {}).get("state_path", ".aiwiki/state/concept-rewrite-proposals.json"),
            "pending_review_slugs": [
                proposal["slug"]
                for proposal in memory.get("health", {}).get("concept_rewrite", {}).get("proposals", [])
                if proposal.get("pending_review") == "true"
            ],
            "apply_ready_slugs": [
                proposal["slug"]
                for proposal in memory.get("health", {}).get("concept_rewrite", {}).get("proposals", [])
                if proposal.get("apply_ready")
            ],
            "active_count": memory.get("health", {}).get("concept_rewrite", {}).get("counts", {}).get("active", 0),
        },
        "machine_memory": {
            "digest": memory.get("digest", ""),
            "graph_digest": memory.get("graph_digest", ""),
            "transition": memory.get("transition", {}),
            "drift": memory.get("drift", {}),
            "health": memory.get("health", {}),
            "topology_path": relative_path(root, machine_memory_topology_path(root)),
            "actions_path": relative_path(root, machine_memory_actions_path(root)),
            "repair_plan_path": relative_path(root, machine_memory_repair_plan_path(root)),
            "action_counts": memory.get("health", {}).get("action_counts", {}),
            "repair_plan_counts": memory.get("health", {}).get("repair_plan", {}).get("counts", {}),
            "overdue_action_ids": [action["id"] for action in memory.get("health", {}).get("overdue_actions", [])],
            "escalated_action_ids": [action["id"] for action in memory.get("health", {}).get("escalated_actions", [])],
            "ready_action_ids": [
                action["id"] for action in memory.get("health", {}).get("repair_plan", {}).get("ready_actions", [])
            ],
            "proposal_action_ids": [
                proposal["action_id"]
                for proposal in memory.get("health", {}).get("repair_plan", {}).get("execution_proposals", [])
            ],
        },
        "repair_backlog": {
            "path": relative_path(root, repair_backlog_path(root)),
            "pending_source_summaries": pending_sources,
            "placeholder_concepts": placeholder_concepts,
            "pending_review_decisions": [page["path"] for page in queue["pending_decisions"]],
            "pending_review_judgments": [page["path"] for page in queue["pending_judgments"]],
            "overdue_pages": [page["path"] for page in aging["overdue"]],
            "escalated_pages": [page["path"] for page in aging["escalated"]],
            "counter_evidence_candidates": [
                candidate["page_path"]
                for candidate in memory.get("health", {}).get("counter_evidence_scan", {}).get("pages", [])
                if isinstance(candidate, dict) and candidate.get("page_path")
            ],
            "judgment_review_actions": [
                action["id"]
                for action in memory.get("health", {}).get("judgment_review_actions", [])
                if isinstance(action, dict) and action.get("id")
            ],
            "auto_promotions": [page["path"] for page in promotion_result.get("pages", [])],
            "weak_concept_slugs": [
                concept["slug"] for concept in memory.get("health", {}).get("concept_quality", {}).get("weak_concepts", [])
            ],
            "rewrite_candidate_slugs": [
                concept["slug"]
                for concept in memory.get("health", {}).get("concept_quality", {}).get("rewrite_candidates", [])
            ],
            "machine_memory_actions": [action["id"] for action in memory.get("health", {}).get("actions", [])],
            "overdue_action_ids": [action["id"] for action in memory.get("health", {}).get("overdue_actions", [])],
            "escalated_action_ids": [action["id"] for action in memory.get("health", {}).get("escalated_actions", [])],
            "repair_plan_path": relative_path(root, machine_memory_repair_plan_path(root)),
            "ready_action_ids": [
                action["id"] for action in memory.get("health", {}).get("repair_plan", {}).get("ready_actions", [])
            ],
            "proposal_action_ids": [
                proposal["action_id"]
                for proposal in memory.get("health", {}).get("repair_plan", {}).get("execution_proposals", [])
            ],
        },
    }
    repair_backlog = render_repair_backlog(
        compile_result,
        lint_result,
        memory,
        protocol_state["active_protocol"],
        promotion_result,
        pending_sources,
        placeholder_concepts,
        queue["pending_decisions"],
        queue["pending_judgments"],
        aging["overdue"],
        aging["escalated"],
        semantic_report,
        generated_at,
    )
    repair_backlog_path(root).write_text(repair_backlog, encoding="utf-8")
    nightly_health_state_path(root).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_wiki_log(
        root,
        "nightly",
        "health and repair pass",
        [
            f"llm_used: `{llm_used}`",
            f"lint_errors: `{lint_result['counts']['errors']}`",
            f"lint_warnings: `{lint_result['counts']['warnings']}`",
            f"pending_source_summaries: `{len(pending_sources)}`",
            f"placeholder_concepts: `{len(placeholder_concepts)}`",
            f"pending_decision_reviews: `{len(queue['pending_decisions'])}`",
            f"pending_judgment_reviews: `{len(queue['pending_judgments'])}`",
            f"overdue_reviews: `{len(aging['overdue'])}`",
            f"escalation_candidates: `{len(aging['escalated'])}`",
            f"counter_evidence_candidates: `{len(memory.get('health', {}).get('counter_evidence_scan', {}).get('pages', []))}`",
            f"judgment_review_actions: `{len(memory.get('health', {}).get('judgment_review_actions', []))}`",
            f"cooled_active_corpora: `{len(cooled_corpus_ids)}`",
            f"expired_active_corpora: `{len(expired_corpus_ids)}`",
            f"archive_candidates: `{len(archive_candidates.get('entries', []))}`",
            f"knowledge_lifecycle_entries: `{len(knowledge_lifecycle.get('entries', []))}`",
            f"auto_promotions: `{promotion_result.get('count', 0)}`",
            f"weak_concepts: `{memory.get('health', {}).get('concept_quality', {}).get('counts', {}).get('weak', 0)}`",
            f"machine_memory_actions: `{memory.get('health', {}).get('action_counts', {}).get('total', 0)}`",
            f"ready_machine_memory_actions: `{memory.get('health', {}).get('repair_plan', {}).get('counts', {}).get('ready', 0)}`",
            f"repair_backlog: `{relative_path(root, repair_backlog_path(root))}`",
        ],
    )
    return state


def refresh_nightly_planner_execution_state(
    root: Path,
    planner_state: dict[str, Any],
    *,
    generated_at: str,
    active_protocol: str,
) -> dict[str, Any]:
    queue_items = {
        str(item.get("action_id") or ""): item
        for item in planner_state.get("priority_queue", [])
        if isinstance(item, dict) and str(item.get("action_id") or "")
    }
    executed_by_action: dict[str, dict[str, Any]] = {}
    for item in planner_state.get("executed_actions", []):
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("action_id") or "")
        if action_id:
            executed_by_action[action_id] = dict(item)

    for proposal in planner_state.get("pending_proposals", []):
        if not isinstance(proposal, dict):
            continue
        action_id = str(proposal.get("action_id") or "")
        if not action_id or action_id in executed_by_action:
            continue
        queue_item = queue_items.get(action_id, {})
        blocked = bool(queue_item.get("blocked", proposal.get("blocked", False)))
        if blocked or str(proposal.get("status") or "") != "accepted" or str(proposal.get("risk") or "") != "low":
            continue
        bundle = build_execution_bundle(root, proposal, compiled_at=generated_at)
        bundle_path = root / str(proposal.get("bundle_path") or "")
        if not str(proposal.get("bundle_path") or ""):
            bundle_path = execution_bundle_path(root, action_id)
        write_execution_bundle_document(bundle_path, bundle)
        executed_by_action[action_id] = {
            "action_id": action_id,
            "title": str(proposal.get("title") or action_id),
            "bundle_path": relative_path(root, bundle_path),
            "proposal_path": str(proposal.get("proposal_path") or ""),
            "executed_at": generated_at,
            "execution_band": str(proposal.get("execution_band") or ""),
            "protocol": str(proposal.get("protocol") or active_protocol),
            "source": "nightly-auto-bundle",
            "status": str(proposal.get("status") or ""),
        }
        append_runtime_history(
            root,
            {
                "event_type": "nightly-auto-bundle",
                "occurred_at": generated_at,
                "action_id": action_id,
                "protocol": str(proposal.get("protocol") or active_protocol),
                "bundle_path": relative_path(root, bundle_path),
                "proposal_path": str(proposal.get("proposal_path") or ""),
            },
        )

    for receipt in load_execution_receipt_history(root):
        if not isinstance(receipt, dict) or str(receipt.get("operation") or "") != "apply":
            continue
        action_id = str(receipt.get("action_id") or "")
        if not action_id:
            continue
        bundle = receipt.get("bundle") if isinstance(receipt.get("bundle"), dict) else {}
        current = executed_by_action.get(action_id, {})
        current_timestamp = str(current.get("executed_at") or "")
        receipt_timestamp = str(receipt.get("applied_at") or "")
        if current and current_timestamp and receipt_timestamp and current_timestamp >= receipt_timestamp:
            continue
        executed_by_action[action_id] = {
            "action_id": action_id,
            "title": str(receipt.get("title") or action_id),
            "bundle_path": str(bundle.get("bundle_path") or ""),
            "proposal_path": str(bundle.get("proposal_path") or ""),
            "executed_at": receipt_timestamp,
            "execution_band": str(bundle.get("execution_band") or ""),
            "protocol": str(receipt.get("protocol") or active_protocol),
            "receipt_path": str(receipt.get("receipt_path") or ""),
            "source": "receipt-history",
            "status": str(receipt.get("status") or ""),
        }

    executed_actions = sorted(
        executed_by_action.values(),
        key=lambda item: (str(item.get("executed_at") or ""), str(item.get("action_id") or "")),
        reverse=True,
    )[:16]
    updated_state = {
        **planner_state,
        "state_path": relative_path(root, planner_state_path(root)),
        "executed_actions": executed_actions,
        "counts": {
            **dict(planner_state.get("counts", {})),
            "executed_actions": len(executed_actions),
        },
    }
    save_planner_state(root, updated_state)
    return updated_state
