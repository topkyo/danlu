"""Machine memory and execution snapshot logic extracted from aiwiki.app.

OWNER STATUS: legacy owner. New large logic blocks should be extracted to
`aiwiki.memory.*` rather than added here. See AGENTS.md migration policy.
"""

from __future__ import annotations

import fcntl
import functools
import hashlib
import html
import json
import os
import shutil
import threading
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .app_content import (
    action_supports_low_risk_apply,
    action_transition_profile,
    archive_transition_profile,
    collect_aging_signals,
    collect_curated_pages,
    collect_recent_output_artifacts,
    curated_page_transition_profile,
    display_action_status,
    entry_ids_from_paths,
    entry_lookup_maps,
    execution_band_label,
    execution_bundle_path,
    execution_policy_profile,
    execution_proposal_path,
    judgment_asset_attention_sort_key,
    judgment_asset_shell_record,
    judgment_asset_summary,
    knowledge_lifecycle_governance_summary,
    load_execution_policy_decision_history,
    load_execution_receipt_history,
    preserved_section,
    review_queue,
    rewrite_transition_profile,
    summarize_runtime_event_for_shell,
    transition_profile,
    valid_curated_statuses,
)
from .app_protocol import (
    ACTIVE_CORPUS_STATUSES,
    ACTIVE_CORPUS_TTL,
    ARCHIVE_CANDIDATE_STATUSES,
    ARCHIVE_QUERY_STALE_AFTER,
    action_focus_score,
    load_protocol_state,
    protocol_query_route_config,
    protocol_state_path,
    protocol_title,
)
from .app_state import (
    DEFAULT_PROTOCOL,
    active_corpora_state_path,
    active_material_archive_entries,
    agent_workbench_path,
    domain_pilots_path,
    execution_audit_html_path,
    execution_audit_path,
    execution_center_html_path,
    execution_center_path,
    execution_policy_log_path,
    execution_receipt_history_path,
    furnace_center_html_path,
    load_active_corpora_state,
    load_archive_candidates_state,
    load_json_document,
    load_knowledge_lifecycle_state,
    load_machine_memory,
    load_manual_link_state,
    load_material_archive_state,
    load_query_route_telemetry,
    load_runtime_history,
    machine_memory_graph_html_path,
    machine_memory_history_path,
    nightly_health_state_path,
    output_packs_index_path,
    query_route_telemetry_path,
    review_center_html_path,
    save_active_corpora_state,
    save_archive_candidates_state,
    save_material_routing_state,
    save_material_state,
    save_query_route_telemetry,
    shell_summary_path,
)
from .app_utils import (
    extract_provenance_paths,
    html_safe_json_literal,
    question_signature,
    read_text_preview,
    render_frontmatter,
    sha256_bytes,
    slugify,
    strip_frontmatter,
    utc_now,
)
from .config import LLMConfig
from .memory.actions import reconcile_machine_memory_actions as _reconcile_machine_memory_actions
from .memory.build_plan import plan_machine_memory_build as _plan_machine_memory_build
from .memory.builder import build_machine_memory as _build_machine_memory
from .memory.core import (
    machine_memory_digest as _machine_memory_digest,
)
from .memory.core import (
    machine_memory_snapshot_is_reusable as _machine_memory_snapshot_is_reusable,
)
from .memory.core import (
    reuse_machine_memory_core as _reuse_machine_memory_core,
)
from .memory.graph_builder import build_machine_memory_graph as _build_machine_memory_graph
from .memory.health import build_machine_memory_health as _build_machine_memory_health
from .memory.judgment_assets import (
    attach_judgment_assets_to_machine_memory as _attach_judgment_assets_to_machine_memory,
)
from .memory.rewrite_candidates import (
    store_concept_rewrite_candidate as _store_concept_rewrite_candidate,
)
from .memory.scoring import (
    machine_memory_query_time_focus,
    protocol_hints_for_material,
    recency_score_for_timestamp,
    timestamp_is_newer,
    update_latest_timestamp,
)
from .memory.source_records import (
    machine_memory_source_runtime_record as _machine_memory_source_runtime_record,
)


def concept_page_path(root: Path, slug: str) -> Path:
    return root / "wiki" / "concepts" / f"{slug}.md"


def concept_lifecycle_entry(lifecycle_state: dict[str, Any], slug: str) -> dict[str, Any]:
    target_path = f"wiki/concepts/{slug}.md"
    return next(
        (
            dict(entry)
            for entry in lifecycle_state.get("entries", [])
            if isinstance(entry, dict)
            and str(entry.get("kind") or "") == "concept"
            and str(entry.get("path") or "") == target_path
        ),
        {},
    )


def machine_memory_source_runtime_record(
    source_id: str,
    *,
    base_score: float,
    source_nodes: dict[str, dict[str, Any]],
    material_by_entry: dict[str, dict[str, Any]],
    routing_by_entry: dict[str, dict[str, Any]],
    archive_candidates_by_entry: dict[str, dict[str, Any]],
    protocol: str,
    time_focus: str,
) -> dict[str, Any]:
    return _machine_memory_source_runtime_record(
        source_id,
        base_score=base_score,
        source_nodes=source_nodes,
        material_by_entry=material_by_entry,
        routing_by_entry=routing_by_entry,
        archive_candidates_by_entry=archive_candidates_by_entry,
        protocol=protocol,
        time_focus=time_focus,
    )


def build_machine_memory(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    previews: dict[str, str],
    entry_terms: dict[str, list[str]],
    compiled_at: str,
) -> dict[str, Any]:
    return _build_machine_memory(root, entries, concepts, previews, entry_terms, compiled_at)


def attach_judgment_assets_to_machine_memory(
    root: Path,
    memory: dict[str, Any],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
) -> dict[str, Any]:
    return _attach_judgment_assets_to_machine_memory(root, memory, decisions, judgments)


def plan_machine_memory_build(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    previews: dict[str, str],
    entry_terms: dict[str, list[str]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    return _plan_machine_memory_build(
        root,
        entries,
        concepts,
        previews,
        entry_terms,
        generated_at=generated_at,
    )


def machine_memory_snapshot_is_reusable(memory: dict[str, Any]) -> bool:
    return _machine_memory_snapshot_is_reusable(memory)


def reuse_machine_memory_core(previous: dict[str, Any], compiled_at: str) -> dict[str, Any]:
    return _reuse_machine_memory_core(previous, compiled_at)


def build_machine_memory_health(memory: dict[str, Any]) -> dict[str, Any]:
    return _build_machine_memory_health(memory)


def reconcile_machine_memory_actions(
    root: Path,
    health: dict[str, Any],
    *,
    compiled_at: str,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    return _reconcile_machine_memory_actions(
        root,
        health,
        compiled_at=compiled_at,
        active_protocol=active_protocol,
    )


def machine_memory_digest(memory: dict[str, Any]) -> str:
    return _machine_memory_digest(memory)


def build_machine_memory_graph(memory: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    return _build_machine_memory_graph(memory, root=root)


def store_concept_rewrite_candidate(
    root: Path,
    slug: str,
    *,
    quality_record: dict[str, Any],
    candidate_markdown: str,
    generated_at: str,
) -> dict[str, Any]:
    return _store_concept_rewrite_candidate(
        root,
        slug,
        quality_record=quality_record,
        candidate_markdown=candidate_markdown,
        generated_at=generated_at,
    )


# ---------------------------------------------------------------------------
# Lazy compatibility re-exports (EP-011 round 3).
#
# Historical code (src/aiwiki/app.py, scripts/, tests/) accesses machine-memory
# surface/query/routing helpers via ``aiwiki.app_memory.<name>`` as if this
# module were a flat facade. The previous eager ``from .app_memory_surfaces
# import ...`` block here created a real import-time cycle — surfaces imports
# app_memory at its top, so cold ``import aiwiki.app_memory_surfaces`` raised
# ImportError for names not yet bound in the half-initialized module.
#
# PEP 562 ``__getattr__`` gives us the flat namespace without the cycle: names
# are resolved on first access, after both modules have finished loading.
# Owner modules remain the single source of truth; this facade only forwards.
# ---------------------------------------------------------------------------

_LAZY_OWNERS: dict[str, str] = {
    # Owned by app_memory_surfaces
    "append_machine_memory_history": "aiwiki.app_memory_surfaces",
    "build_execution_audit_snapshot": "aiwiki.app_memory_surfaces",
    "build_machine_memory_query": "aiwiki.app_memory_surfaces",
    "collect_execution_consistency_signals": "aiwiki.app_memory_surfaces",
    "concept_rewrite_proposal_digest": "aiwiki.app_memory_surfaces",
    "reconcile_concept_rewrite_proposals": "aiwiki.app_memory_surfaces",
    "render_concept_quality": "aiwiki.app_memory_surfaces",
    "render_concept_rewrite_index": "aiwiki.app_memory_surfaces",
    "render_concept_rewrite_proposal_page": "aiwiki.app_memory_surfaces",
    "render_drift_report": "aiwiki.app_memory_surfaces",
    "render_execution_audit": "aiwiki.app_memory_surfaces",
    "render_execution_audit_html": "aiwiki.app_memory_surfaces",
    "render_execution_center": "aiwiki.app_memory_surfaces",
    "render_execution_center_html": "aiwiki.app_memory_surfaces",
    "render_execution_proposal_page": "aiwiki.app_memory_surfaces",
    "render_graph_health": "aiwiki.app_memory_surfaces",
    "render_machine_memory_actions": "aiwiki.app_memory_surfaces",
    "render_machine_memory_graph_html": "aiwiki.app_memory_surfaces",
    "render_machine_memory_index": "aiwiki.app_memory_surfaces",
    "render_machine_memory_repair_plan": "aiwiki.app_memory_surfaces",
    "render_machine_memory_topology": "aiwiki.app_memory_surfaces",
    "summarize_machine_memory_transition": "aiwiki.app_memory_surfaces",
    # Owned by app_memory_query (EP-011 split)
    "_machine_memory_query_payload_hash": "aiwiki.app_memory_query",
    "_route_anchor_candidates": "aiwiki.app_memory_query",
    "build_machine_memory_adjacency": "aiwiki.app_memory_query",
    "build_machine_memory_query_routes": "aiwiki.app_memory_query",
    "concept_page_snapshot": "aiwiki.app_memory_query",
    "fallback_query_route_config": "aiwiki.app_memory_query",
    "machine_memory_node_metadata": "aiwiki.app_memory_query",
    "ranked_machine_memory_anchor_nodes": "aiwiki.app_memory_query",
    "recent_execution_dry_runs": "aiwiki.app_memory_query",
    "record_query_route_telemetry": "aiwiki.app_memory_query",
    "render_machine_memory_route": "aiwiki.app_memory_query",
    "select_machine_memory_query_strategy": "aiwiki.app_memory_query",
    "shortest_machine_memory_path": "aiwiki.app_memory_query",
    # Owned by app_routing
    "active_corpus_bridge_evidence_ids": "aiwiki.app_routing",
    "archive_candidate_reactivation_signals": "aiwiki.app_routing",
    "build_archive_candidate_state": "aiwiki.app_routing",
    "build_material_routing_entry": "aiwiki.app_routing",
    "build_material_routing_snapshot": "aiwiki.app_routing",
    "build_material_state_documents": "aiwiki.app_routing",
    "cross_protocol_bridge_entry": "aiwiki.app_routing",
    "material_graph_context": "aiwiki.app_routing",
    "material_protocol_score": "aiwiki.app_routing",
    "material_routing_selected_as": "aiwiki.app_routing",
    "material_top_protocols": "aiwiki.app_routing",
    "reconcile_active_corpora_state": "aiwiki.app_routing",
    "refresh_material_state": "aiwiki.app_routing",
    "routing_bridge_recall_ids": "aiwiki.app_routing",
    "scan_material_reference_state": "aiwiki.app_routing",
    "source_ids_for_citations": "aiwiki.app_routing",
    "temperature_from_routing": "aiwiki.app_routing",
    "upsert_active_corpus": "aiwiki.app_routing",
}


def __getattr__(name: str) -> Any:
    owner_path = _LAZY_OWNERS.get(name)
    if owner_path is None:
        raise AttributeError(f"module 'aiwiki.app_memory' has no attribute {name!r}")
    import importlib

    owner = importlib.import_module(owner_path)
    value = getattr(owner, name)
    globals()[name] = value  # cache for subsequent accesses
    return value
