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
    load_execution_receipt_history_strict,
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
    execution_audit_path,
    execution_bundle_path,
    execution_proposal_path,
    execution_receipt_path,
    graph_health_report_path,
    judgment_assets_path,
    machine_memory_actions_path,
    machine_memory_drift_report_path,
    machine_memory_graph_path,
    machine_memory_repair_plan_path,
    machine_memory_topology_path,
    output_packs_index_path,
    product_shell_html_path,
    remove_stale_generated_concept_pages,
    repair_backlog_path,
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
from ..render.views import (
    render_agent_pack,
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
from .core import pending_source_summary_ids
from .repair import render_repair_backlog


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
                if str(entry.get("kind") or "") == "concept" and entry.get("active_corpus_ids")
            ],
            "retired_concept_ids": [
                str(entry.get("page_id") or "")
                for entry in knowledge_lifecycle.get("entries", [])
                if str(entry.get("kind") or "") == "concept" and str(entry.get("lifecycle_state") or "") == "retired"
            ],
            "governance_summary": {
                "concept_backlog_count": lifecycle_summary.get("counts", {}).get("concept_backlog", 0),
                "review_concept_count": lifecycle_summary.get("counts", {}).get("review_concepts", 0),
                "revisit_concept_count": lifecycle_summary.get("counts", {}).get("revisit_concepts", 0),
                "retired_concept_count": lifecycle_summary.get("counts", {}).get("retired_concepts", 0),
                "concept_backlog_ids": [
                    str(entry.get("page_id") or "") for entry in lifecycle_summary.get("concept_backlog", [])
                ],
                "review_concept_ids": [
                    str(entry.get("page_id") or "") for entry in lifecycle_summary.get("review_concepts", [])
                ],
                "revisit_concept_ids": [
                    str(entry.get("page_id") or "") for entry in lifecycle_summary.get("revisit_concepts", [])
                ],
                "retired_concept_ids": [
                    str(entry.get("page_id") or "") for entry in lifecycle_summary.get("retired_concepts", [])
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
                concept["slug"]
                for concept in memory.get("health", {}).get("concept_quality", {}).get("weak_concepts", [])
            ],
            "rewrite_candidate_slugs": [
                concept["slug"]
                for concept in memory.get("health", {}).get("concept_quality", {}).get("rewrite_candidates", [])
            ],
            "merge_candidates": memory.get("health", {})
            .get("concept_quality", {})
            .get("counts", {})
            .get("merge_candidates", 0),
            "conflict_signals": memory.get("health", {})
            .get("concept_quality", {})
            .get("counts", {})
            .get("conflict_signals", 0),
            "gap_signals": memory.get("health", {}).get("concept_quality", {}).get("counts", {}).get("gap_signals", 0),
        },
        "concept_rewrite": {
            "path": relative_path(root, concept_rewrite_index_path(root)),
            "state_path": memory.get("health", {})
            .get("concept_rewrite", {})
            .get("state_path", ".aiwiki/state/concept-rewrite-proposals.json"),
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
                concept["slug"]
                for concept in memory.get("health", {}).get("concept_quality", {}).get("weak_concepts", [])
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
    atomic_write_text(repair_backlog_path(root), repair_backlog)
    atomic_write_text(
        nightly_health_state_path(root),
        json.dumps(state, indent=2, sort_keys=True) + "\n",
    )
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
    del root, generated_at, active_protocol
    return dict(planner_state)
