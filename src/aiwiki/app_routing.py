"""Material routing and archive-candidate helpers extracted from app_memory.

OWNER STATUS: legacy owner. New large logic blocks should be extracted to a
dedicated subpackage (e.g. `aiwiki.routing.*`) rather than added here.
See AGENTS.md migration policy.
"""

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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .app_lifecycle import (
    action_needs_review,
    action_transition_profile,
    archive_transition_profile,
    collect_aging_signals,
    collect_curated_pages,
    curated_page_transition_profile,
    display_action_status,
    display_rewrite_proposal_status,
    evaluate_page_aging,
    knowledge_lifecycle_governance_summary,
    review_queue,
    rewrite_proposal_needs_review,
    rewrite_proposal_status_rank,
    rewrite_transition_profile,
    transition_profile,
    valid_curated_statuses,
)
from .app_protocol import (
    ACTION_STATUSES,
    ACTIVE_CORPUS_STATUSES,
    ACTIVE_CORPUS_TTL,
    ARCHIVE_CANDIDATE_STATUSES,
    ARCHIVE_QUERY_STALE_AFTER,
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    PENDING_ACTION_STATUSES,
    PROTOCOL_LIBRARY,
    REWRITE_PROPOSAL_STATUSES,
    action_focus_score,
    ensure_layout,
    load_protocol_state,
    protocol_focus_score,
    protocol_query_route_config,
    protocol_state_path,
    protocol_title,
    schedule_review_windows,
)
from .app_state_paths import (
    active_corpora_state_path,
    agent_workbench_path,
    concept_rewrite_proposal_page_path,
    concept_rewrite_state_path,
    domain_pilots_path,
    execution_audit_html_path,
    execution_audit_path,
    execution_center_html_path,
    execution_center_path,
    execution_policy_log_path,
    execution_receipt_history_path,
    furnace_center_html_path,
    machine_memory_action_state_path,
    machine_memory_graph_html_path,
    machine_memory_history_path,
    nightly_health_state_path,
    output_packs_index_path,
    query_route_telemetry_path,
    review_center_html_path,
    shell_summary_path,
)
from .compile.build import load_machine_memory_build_state
from .config import LLMConfig
from .content.archive import (
    active_material_archive_entries,
    load_archive_candidates_state,
    load_material_archive_state,
    save_archive_candidates_state,
    save_material_routing_state,
)
from .content.concepts import concept_label_to_slug
from .content.io import (
    collect_recent_output_artifacts,
    entry_ids_from_paths,
    entry_lookup_maps,
    preserved_section,
    routing_snapshot_for_protocol,
    source_summary_or_preview,
    summarize_runtime_event_for_shell,
)
from .content.material import (
    load_active_corpora_state,
    load_manual_link_state,
    save_active_corpora_state,
    save_material_state,
)
from .content.rewrite import load_concept_rewrite_state, save_concept_rewrite_state
from .execution.history import load_runtime_history
from .execution.policy import (
    execution_band_label,
    execution_policy_profile,
    load_execution_policy_decision_history,
    load_execution_receipt_history,
)
from .execution.repair_plan import rewrite_proposal_is_apply_ready
from .lifecycle.knowledge import load_knowledge_lifecycle_state
from .memory.action_core import (
    action_priority_rank,
    action_status_rank,
    action_supports_low_risk_apply,
    describe_machine_memory_action,
    machine_memory_concept_input_signature,
    machine_memory_source_input_signature,
    safe_apply_preview,
    validate_low_risk_action_targets,
)
from .memory.action_state import load_machine_memory_action_state, save_machine_memory_action_state
from .memory.scoring import (
    protocol_hints_for_material,
    recency_score_for_timestamp,
    timestamp_is_newer,
    update_latest_timestamp,
)
from .memory.state import load_machine_memory
from .planner.state import load_query_route_telemetry, save_query_route_telemetry
from .render.paths import (
    execution_bundle_path,
    execution_proposal_path,
)
from .render.views import (
    judgment_asset_attention_sort_key,
    judgment_asset_shell_record,
    judgment_asset_summary,
)
from .state.constants import DEFAULT_PROTOCOL
from .state.io import load_json_document
from .state.manifest import load_manifest
from .utils.hash import question_signature, sha256_bytes
from .utils.io import write_if_changed
from .utils.json_utils import html_safe_json_literal
from .utils.markdown import (
    analyze_citation_snapshots,
    extract_provenance_paths,
    parse_frontmatter,
    read_text_preview,
    render_frontmatter,
)
from .utils.path import relative_path
from .utils.text import slugify, tokenize
from .utils.time import parse_iso_datetime, utc_now


def material_protocol_score(
    active_protocol: str,
    *,
    protocol_hints: list[str],
    entry: dict[str, Any],
    preview: str,
) -> float:
    text = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("source_type") or ""),
            preview,
        ]
    )
    focus_score = protocol_focus_score(active_protocol, text)
    non_default_hints = [hint for hint in protocol_hints if hint and hint != DEFAULT_PROTOCOL]
    if active_protocol == DEFAULT_PROTOCOL:
        base = 0.4 if not non_default_hints else 0.25
    elif active_protocol in protocol_hints:
        base = 0.75
    else:
        base = 0.2
    return round(min(1.0, base + min(0.25, focus_score * 0.05)), 3)


def material_graph_context(memory: dict[str, Any]) -> dict[str, Any]:
    health = memory.get("health", {})
    bridge_concepts = set(health.get("bridge_concept_slugs", []))
    concept_count_by_entry: dict[str, int] = {}
    bridge_source_ids: set[str] = set()
    source_component_ids = {
        str(source_id): str(component_id)
        for source_id, component_id in health.get("source_component_ids", {}).items()
        if isinstance(source_id, str) and isinstance(component_id, str)
    }
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        source_id = str(edge.get("source_id") or "")
        concept_slug = str(edge.get("concept_slug") or "")
        if not source_id or not concept_slug:
            continue
        concept_count_by_entry[source_id] = concept_count_by_entry.get(source_id, 0) + 1
        if concept_slug in bridge_concepts:
            bridge_source_ids.add(source_id)
    action_pressure_by_entry: dict[str, float] = {}
    for action in health.get("actions", []):
        if not isinstance(action, dict):
            continue
        weight = 0.2
        if str(action.get("priority") or "") == "high":
            weight += 0.15
        if str(action.get("status") or "") in {"accepted", "proposed"}:
            weight += 0.1
        for source_id in action.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id:
                action_pressure_by_entry[source_id] = action_pressure_by_entry.get(source_id, 0.0) + weight
    for action in health.get("overdue_actions", []):
        if not isinstance(action, dict):
            continue
        for source_id in action.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id:
                action_pressure_by_entry[source_id] = action_pressure_by_entry.get(source_id, 0.0) + 0.2
    for action in health.get("escalated_actions", []):
        if not isinstance(action, dict):
            continue
        for source_id in action.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id:
                action_pressure_by_entry[source_id] = action_pressure_by_entry.get(source_id, 0.0) + 0.25
    return {
        "concept_count_by_entry": concept_count_by_entry,
        "bridge_source_ids": bridge_source_ids,
        "action_pressure_by_entry": action_pressure_by_entry,
        "sources_without_concepts": set(memory.get("drift", {}).get("sources_without_concepts", [])),
        "source_component_ids": source_component_ids,
    }


def material_routing_selected_as(total_score: float, *, active_corpus_ids: list[str]) -> str:
    if active_corpus_ids or total_score >= 3.2:
        return "hot-evidence"
    if total_score >= 2.2:
        return "warm-evidence"
    if total_score >= 1.2:
        return "cold-evidence"
    return "archive-candidate"


def temperature_from_routing(selected_as: str, *, supports_judgment_ids: list[str]) -> str:
    if selected_as == "hot-evidence":
        return "hot"
    if selected_as == "warm-evidence":
        return "warm"
    if supports_judgment_ids:
        return "warm"
    return "cold"


def source_ids_for_citations(root: Path, entries: list[dict[str, Any]], markdown: str) -> list[str]:
    _by_id, path_to_entry_id = entry_lookup_maps(entries)
    return entry_ids_from_paths(path_to_entry_id, extract_provenance_paths(root, markdown))


def scan_material_reference_state(
    root: Path,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    _by_id, path_to_entry_id = entry_lookup_maps(entries)
    citation_count_by_entry: dict[str, int] = {}
    supports_judgment_ids: dict[str, set[str]] = {}
    active_judgment_ids: set[str] = set()

    for relative in ("wiki/derived", "wiki/decisions", "wiki/judgments"):
        directory = root / relative
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            cited_entry_ids = entry_ids_from_paths(path_to_entry_id, extract_provenance_paths(root, content))
            for entry_id in cited_entry_ids:
                citation_count_by_entry[entry_id] = citation_count_by_entry.get(entry_id, 0) + 1
            if relative != "wiki/judgments":
                continue
            frontmatter = parse_frontmatter(content)
            judgment_id = str(frontmatter.get("id") or path.stem)
            if str(frontmatter.get("status") or "") != "rejected":
                active_judgment_ids.add(judgment_id)
            for entry_id in cited_entry_ids:
                supports_judgment_ids.setdefault(entry_id, set()).add(judgment_id)

    return {
        "citation_count_by_entry": citation_count_by_entry,
        "supports_judgment_ids": {entry_id: sorted(ids) for entry_id, ids in supports_judgment_ids.items()},
        "active_judgment_ids": sorted(active_judgment_ids),
    }


def build_material_routing_snapshot(
    *,
    active_protocol: str,
    entry: dict[str, Any],
    preview: str,
    protocol_hints: list[str],
    active_corpus_ids: list[str],
    supports_judgment_ids: list[str],
    last_query_hit_at: str,
    last_review_reference_at: str,
    graph_context: dict[str, Any],
    computed_at: str,
) -> dict[str, Any]:
    entry_id = str(entry.get("id") or "")
    concept_count = int(graph_context.get("concept_count_by_entry", {}).get(entry_id, 0))
    is_bridge = entry_id in graph_context.get("bridge_source_ids", set())
    graph_score = 0.0
    graph_score += min(0.55, concept_count * 0.18)
    if active_corpus_ids:
        graph_score += 0.25
    if is_bridge:
        graph_score += 0.2
    graph_score = round(min(1.0, graph_score), 3)

    judgment_score = round(min(1.0, len(supports_judgment_ids) * 0.35), 3)
    recency_score = round(
        min(
            1.0,
            max(
                recency_score_for_timestamp(str(entry.get("updated_at") or entry.get("imported_at") or "")),
                recency_score_for_timestamp(last_query_hit_at),
                recency_score_for_timestamp(last_review_reference_at),
            ),
        ),
        3,
    )

    drift_score = 0.0
    if entry_id in graph_context.get("sources_without_concepts", set()):
        drift_score += 0.4
    drift_score += float(graph_context.get("action_pressure_by_entry", {}).get(entry_id, 0.0))
    drift_score = round(min(1.0, drift_score), 3)

    protocol_score = material_protocol_score(
        active_protocol,
        protocol_hints=protocol_hints,
        entry=entry,
        preview=preview,
    )
    total_score = round(protocol_score + graph_score + judgment_score + recency_score + drift_score, 3)
    selected_as = material_routing_selected_as(total_score, active_corpus_ids=active_corpus_ids)
    return {
        "entry_id": entry_id,
        "protocol": active_protocol,
        "component_id": str(graph_context.get("source_component_ids", {}).get(entry_id, "") or ""),
        "scores": {
            "protocol_score": protocol_score,
            "graph_score": graph_score,
            "judgment_score": judgment_score,
            "recency_score": recency_score,
            "drift_score": drift_score,
        },
        "total_score": total_score,
        "selected_as": selected_as,
        "is_bridge": is_bridge,
        "computed_at": computed_at,
    }


def material_top_protocols(protocol_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        [snapshot for snapshot in protocol_snapshots if isinstance(snapshot, dict)],
        key=lambda item: (-float(item.get("total_score", 0.0) or 0.0), str(item.get("protocol") or "")),
    )
    return [
        {
            "protocol": str(snapshot.get("protocol") or ""),
            "total_score": float(snapshot.get("total_score", 0.0) or 0.0),
            "selected_as": str(snapshot.get("selected_as") or ""),
        }
        for snapshot in ranked[:3]
    ]


def cross_protocol_bridge_entry(protocol_snapshots: list[dict[str, Any]], active_protocol: str) -> bool:
    for snapshot in protocol_snapshots:
        if not isinstance(snapshot, dict):
            continue
        if str(snapshot.get("protocol") or "") == active_protocol:
            continue
        if bool(snapshot.get("is_bridge")) and float(snapshot.get("total_score", 0.0) or 0.0) >= 2.2:
            return True
    return False


def build_material_routing_entry(
    *,
    active_protocol: str,
    entry: dict[str, Any],
    preview: str,
    protocol_hints: list[str],
    active_corpus_ids: list[str],
    supports_judgment_ids: list[str],
    last_query_hit_at: str,
    last_review_reference_at: str,
    graph_context: dict[str, Any],
    computed_at: str,
) -> dict[str, Any]:
    protocol_snapshots = [
        build_material_routing_snapshot(
            active_protocol=protocol,
            entry=entry,
            preview=preview,
            protocol_hints=protocol_hints,
            active_corpus_ids=active_corpus_ids,
            supports_judgment_ids=supports_judgment_ids,
            last_query_hit_at=last_query_hit_at,
            last_review_reference_at=last_review_reference_at,
            graph_context=graph_context,
            computed_at=computed_at,
        )
        for protocol in sorted(PROTOCOL_LIBRARY)
    ]
    active_snapshot = next(
        (snapshot for snapshot in protocol_snapshots if str(snapshot.get("protocol") or "") == active_protocol),
        protocol_snapshots[0],
    )
    return {
        **active_snapshot,
        "protocol_snapshots": protocol_snapshots,
        "top_protocols": material_top_protocols(protocol_snapshots),
        "cross_protocol_bridge": cross_protocol_bridge_entry(protocol_snapshots, active_protocol),
    }


def archive_candidate_reactivation_signals(
    material_entry: dict[str, Any],
    routing_snapshot: dict[str, Any],
    previous_candidate: dict[str, Any],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[str]:
    signals: list[str] = []
    previous_flagged_at = str(previous_candidate.get("last_flagged_at") or "")
    if material_entry.get("active_corpus_ids"):
        signals.append("active-corpus")
    if str(material_entry.get("last_query_hit_at") or "") and timestamp_is_newer(
        str(material_entry.get("last_query_hit_at") or ""),
        previous_flagged_at,
    ):
        signals.append("query-hit")
    if str(material_entry.get("last_review_reference_at") or "") and timestamp_is_newer(
        str(material_entry.get("last_review_reference_at") or ""),
        previous_flagged_at,
    ):
        signals.append("review-reference")
    if bool(routing_snapshot.get("is_bridge")):
        signals.append("bridge-evidence")
    if float(routing_snapshot.get("total_score", 0.0) or 0.0) >= 2.2:
        signals.append("routing-score-recovered")
    if bool(routing_snapshot.get("cross_protocol_bridge")):
        signals.append("cross-protocol-bridge")
    top_protocols = [
        str(item.get("protocol") or "")
        for item in routing_snapshot.get("top_protocols", [])
        if isinstance(item, dict) and str(item.get("protocol") or "")
    ]
    if any(protocol != active_protocol for protocol in top_protocols[:2]):
        signals.append("cross-protocol-top-rank")
    return signals


def build_archive_candidate_state(
    *,
    material_entries: list[dict[str, Any]],
    routing_entries: list[dict[str, Any]],
    active_judgment_ids: set[str],
    generated_at: str,
    previous_state: dict[str, Any],
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    previous_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in previous_state.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    routing_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in routing_entries
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    entries: list[dict[str, Any]] = []
    for material_entry in material_entries:
        entry_id = str(material_entry.get("entry_id") or "")
        if not entry_id:
            continue
        routing_snapshot = routing_by_entry.get(entry_id, {})
        previous_candidate = previous_by_entry.get(entry_id, {})
        blocked_by_judgment_ids = sorted(set(material_entry.get("supports_judgment_ids", [])) & active_judgment_ids)
        last_query_hit_at = parse_iso_datetime(str(material_entry.get("last_query_hit_at") or ""))
        query_stale = (
            last_query_hit_at is None or (datetime.now(timezone.utc) - last_query_hit_at) > ARCHIVE_QUERY_STALE_AFTER
        )
        touch_stale = recency_score_for_timestamp(str(material_entry.get("last_touched_at") or "")) <= 0.4
        total_score = float(routing_snapshot.get("total_score", 0.0) or 0.0)
        is_bridge = bool(routing_snapshot.get("is_bridge"))
        cross_protocol_bridge = bool(routing_snapshot.get("cross_protocol_bridge"))
        no_active_corpus = not material_entry.get("active_corpus_ids")
        candidate = (
            no_active_corpus
            and query_stale
            and touch_stale
            and not is_bridge
            and not cross_protocol_bridge
            and str(material_entry.get("temperature") or "") in {"warm", "cold"}
            and str(routing_snapshot.get("selected_as") or "") in {"cold-evidence", "archive-candidate"}
        )
        if candidate:
            reason_codes: list[str] = []
            if no_active_corpus:
                reason_codes.append("no-active-corpus")
            if query_stale:
                reason_codes.append("stale-no-query-hit")
            if touch_stale:
                reason_codes.append("stale-no-touch")
            if total_score < 2.0:
                reason_codes.append("low-routing-score")
            if str(material_entry.get("temperature") or "") == "cold":
                reason_codes.append("already-cold")
            recommended_temperature = (
                "archived" if str(material_entry.get("temperature") or "") == "cold" and total_score < 1.2 else "cold"
            )
            status = "suggested"
            if blocked_by_judgment_ids:
                status = "deferred"
            # Deferred means the candidate already crossed the archive bar once.
            # When the blocking judgments clear, it should resume at ready.
            elif previous_candidate and str(previous_candidate.get("status") or "") in {
                "suggested",
                "ready",
                "deferred",
            }:
                status = "ready"
            entries.append(
                {
                    "entry_id": entry_id,
                    "current_temperature": str(material_entry.get("temperature") or ""),
                    "recommended_temperature": recommended_temperature,
                    "reason_codes": reason_codes,
                    "first_flagged_at": str(previous_candidate.get("first_flagged_at") or generated_at),
                    "last_flagged_at": generated_at,
                    "blocked_by_judgment_ids": blocked_by_judgment_ids,
                    "reactivation_signals": list(previous_candidate.get("reactivation_signals", []))
                    if isinstance(previous_candidate.get("reactivation_signals"), list)
                    else [],
                    "status": status if status in ARCHIVE_CANDIDATE_STATUSES else "suggested",
                }
            )
            continue
        if previous_candidate:
            reactivation_signals = archive_candidate_reactivation_signals(
                material_entry,
                routing_snapshot,
                previous_candidate,
                active_protocol=active_protocol,
            )
            if reactivation_signals:
                entries.append(
                    {
                        "entry_id": entry_id,
                        "current_temperature": str(material_entry.get("temperature") or ""),
                        "recommended_temperature": str(previous_candidate.get("recommended_temperature") or "cold"),
                        "reason_codes": [],
                        "first_flagged_at": str(previous_candidate.get("first_flagged_at") or generated_at),
                        "last_flagged_at": str(previous_candidate.get("last_flagged_at") or generated_at),
                        "blocked_by_judgment_ids": blocked_by_judgment_ids,
                        "reactivation_signals": reactivation_signals,
                        "status": "reactivated",
                    }
                )
    return {"version": 1, "generated_at": generated_at, "entries": entries}


def routing_bridge_recall_ids(
    machine_query: dict[str, Any],
    routing_state: dict[str, Any],
    *,
    active_protocol: str,
    excluded_source_ids: set[str],
) -> list[str]:
    touched_component_ids = {
        str(component_id)
        for component_id in machine_query.get("touched_component_ids", [])
        if isinstance(component_id, str) and component_id
    }
    candidates: list[tuple[float, str]] = []
    for entry in routing_state.get("entries", []):
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("entry_id") or "")
        component_id = str(entry.get("component_id") or "")
        if not entry_id or entry_id in excluded_source_ids:
            continue
        if not touched_component_ids or component_id not in touched_component_ids:
            continue
        protocol_snapshots = [
            snapshot for snapshot in entry.get("protocol_snapshots", []) if isinstance(snapshot, dict)
        ]
        if not cross_protocol_bridge_entry(protocol_snapshots, active_protocol):
            continue
        non_active_scores = [
            float(snapshot.get("total_score", 0.0) or 0.0)
            for snapshot in protocol_snapshots
            if str(snapshot.get("protocol") or "") != active_protocol
        ]
        if not non_active_scores:
            continue
        best_score = max(non_active_scores)
        if best_score < 2.2:
            continue
        candidates.append((best_score, entry_id))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [entry_id for _score, entry_id in candidates[:3]]


def active_corpus_bridge_evidence_ids(
    machine_query: dict[str, Any],
    source_ids: list[str],
    *,
    routing_state: dict[str, Any] | None = None,
    active_protocol: str = DEFAULT_PROTOCOL,
    blocked_source_ids: set[str] | None = None,
) -> list[str]:
    blocked_source_ids = blocked_source_ids or set()
    bridge_concepts = set(machine_query.get("bridge_concept_slugs", []))
    source_set = set(source_ids) | {
        str(source_id)
        for source_id in machine_query.get("ranked_source_ids", [])
        if isinstance(source_id, str) and source_id and source_id not in blocked_source_ids
    }
    for node in machine_query.get("query_subgraph", {}).get("sources", []):
        if isinstance(node, dict):
            node_id = str(node.get("id") or "")
            if node_id and node_id not in blocked_source_ids:
                source_set.add(node_id)
    bridge_ids: list[str] = []
    seen: set[str] = set()
    if bridge_concepts:
        for edge in machine_query.get("query_subgraph", {}).get("edges", []):
            if not isinstance(edge, dict):
                continue
            if edge.get("type") != "HAS_CONCEPT":
                continue
            left = str(edge.get("left") or "")
            right = str(edge.get("right") or "")
            if left in source_set and left not in blocked_source_ids and right in bridge_concepts and left not in seen:
                seen.add(left)
                bridge_ids.append(left)
    if routing_state:
        excluded = set(source_set) | set(bridge_ids) | set(blocked_source_ids)
        for entry_id in routing_bridge_recall_ids(
            machine_query,
            routing_state,
            active_protocol=active_protocol,
            excluded_source_ids=excluded,
        ):
            if entry_id not in seen and entry_id not in blocked_source_ids:
                seen.add(entry_id)
                bridge_ids.append(entry_id)
    return bridge_ids


def reconcile_active_corpora_state(
    root: Path,
    *,
    changed_at: str,
    nightly_cooldown: bool = False,
) -> dict[str, Any]:
    ensure_layout(root)
    state = load_active_corpora_state(root)
    changed = not active_corpora_state_path(root).exists()
    corpora: list[dict[str, Any]] = []
    for raw_corpus in state.get("corpora", []):
        corpus = dict(raw_corpus)
        status = str(corpus.get("status") or "active")
        if status not in ACTIVE_CORPUS_STATUSES:
            status = "active"
            changed = True
        expires_at = str(corpus.get("expires_at") or "")
        if expires_at and timestamp_is_newer(changed_at, expires_at):
            if status != "expired":
                status = "expired"
                changed = True
        elif nightly_cooldown and status == "active":
            status = "cooling"
            changed = True
        corpus["status"] = status
        corpora.append(corpus)
    if changed:
        save_active_corpora_state(root, {"version": 1, "corpora": corpora})
    return {"version": 1, "corpora": corpora, "changed": changed}


def refresh_material_state(
    root: Path,
    *,
    generated_at: str,
    entries: list[dict[str, Any]] | None = None,
    active_protocol: str | None = None,
) -> dict[str, Any]:
    documents = build_material_state_documents(
        root,
        generated_at=generated_at,
        entries=entries,
        active_protocol=active_protocol,
    )
    save_material_state(root, documents["material_state"])
    save_material_routing_state(root, documents["material_routing"])
    save_archive_candidates_state(root, documents["archive_candidates"])
    return documents["material_state"]


def build_material_state_documents(
    root: Path,
    *,
    generated_at: str,
    entries: list[dict[str, Any]] | None = None,
    active_protocol: str | None = None,
) -> dict[str, dict[str, Any]]:
    ensure_layout(root)
    manifest_entries = entries if entries is not None else load_manifest(root).get("entries", [])
    resolved_protocol = active_protocol or load_protocol_state(root)["active_protocol"]
    history = load_runtime_history(root)
    active_corpora = reconcile_active_corpora_state(root, changed_at=generated_at)["corpora"]
    reference_state = scan_material_reference_state(root, manifest_entries)
    machine_memory = load_machine_memory(root)
    graph_context = material_graph_context(machine_memory)
    previous_archive_candidates = load_archive_candidates_state(root)
    material_archive_state = load_material_archive_state(root)
    archived_entries = active_material_archive_entries(material_archive_state)
    last_query_hit_at: dict[str, str] = {}
    last_review_reference_at: dict[str, str] = {}

    for event in history:
        occurred_at = str(event.get("occurred_at") or "")
        event_type = str(event.get("event_type") or "")
        source_ids = [str(item) for item in event.get("source_ids", []) if isinstance(item, str)]
        if event_type == "query":
            for entry_id in source_ids:
                update_latest_timestamp(last_query_hit_at, entry_id, occurred_at)
        elif event_type == "review":
            for entry_id in source_ids:
                update_latest_timestamp(last_review_reference_at, entry_id, occurred_at)

    active_corpus_ids_by_entry: dict[str, list[str]] = {}
    for corpus in active_corpora:
        status = str(corpus.get("status") or "")
        if status not in {"active", "cooling"}:
            continue
        corpus_id = str(corpus.get("corpus_id") or "")
        if not corpus_id:
            continue
        source_ids = [
            str(item)
            for item in [*(corpus.get("source_ids", []) or []), *(corpus.get("bridge_evidence_ids", []) or [])]
            if isinstance(item, str)
        ]
        for entry_id in source_ids:
            active_corpus_ids_by_entry.setdefault(entry_id, [])
            if corpus_id not in active_corpus_ids_by_entry[entry_id]:
                active_corpus_ids_by_entry[entry_id].append(corpus_id)

    material_entries: list[dict[str, Any]] = []
    routing_entries: list[dict[str, Any]] = []
    for entry in manifest_entries:
        entry_id = str(entry.get("id") or "")
        stored_path = str(entry.get("stored_path") or "")
        preview = read_text_preview(root / stored_path) if stored_path and (root / stored_path).exists() else ""
        supports_judgment_ids = reference_state["supports_judgment_ids"].get(entry_id, [])
        citation_count = int(reference_state["citation_count_by_entry"].get(entry_id, 0))
        active_corpus_ids = sorted(active_corpus_ids_by_entry.get(entry_id, []))
        query_hit_at = last_query_hit_at.get(entry_id, "")
        review_hit_at = last_review_reference_at.get(entry_id, "")
        protocol_hints = protocol_hints_for_material(entry, preview)
        routing_entry = build_material_routing_entry(
            active_protocol=resolved_protocol,
            entry=entry,
            preview=preview,
            protocol_hints=protocol_hints,
            active_corpus_ids=active_corpus_ids,
            supports_judgment_ids=supports_judgment_ids,
            last_query_hit_at=query_hit_at,
            last_review_reference_at=review_hit_at,
            graph_context=graph_context,
            computed_at=generated_at,
        )
        routing_entries.append(routing_entry)
        archive_record = archived_entries.get(entry_id, {})
        temperature = temperature_from_routing(
            str(routing_entry.get("selected_as") or ""),
            supports_judgment_ids=supports_judgment_ids,
        )
        if archive_record:
            temperature = "archived"
        material_entries.append(
            {
                "entry_id": entry_id,
                "path": stored_path,
                "kind": str(entry.get("kind") or ""),
                "source_type": str(entry.get("source_type") or ""),
                "protocol_hints": protocol_hints,
                "temperature": temperature,
                "last_touched_at": str(entry.get("updated_at") or entry.get("imported_at") or ""),
                "last_query_hit_at": query_hit_at,
                "last_review_reference_at": review_hit_at,
                "citation_count": citation_count,
                "supports_judgment_ids": supports_judgment_ids,
                "active_corpus_ids": active_corpus_ids,
                "archive_override": bool(archive_record),
                "archived_at": str(archive_record.get("archived_at") or ""),
                "archive_receipt_path": str(archive_record.get("last_receipt_path") or ""),
                "archive_candidate": False,
            }
        )

    routing_document = {
        "version": 1,
        "computed_at": generated_at,
        "active_protocol": resolved_protocol,
        "entries": routing_entries,
    }
    archive_document = build_archive_candidate_state(
        material_entries=material_entries,
        routing_entries=routing_entries,
        active_judgment_ids=set(reference_state.get("active_judgment_ids", [])),
        generated_at=generated_at,
        previous_state=previous_archive_candidates,
        active_protocol=resolved_protocol,
    )
    active_archive_ids = {
        str(entry.get("entry_id") or "")
        for entry in archive_document.get("entries", [])
        if str(entry.get("status") or "") in {"suggested", "deferred", "ready"}
    }
    for material_entry in material_entries:
        material_entry["archive_candidate"] = material_entry.get("entry_id") in active_archive_ids
    material_document = {"version": 1, "generated_at": generated_at, "entries": material_entries}
    return {
        "material_state": material_document,
        "material_routing": routing_document,
        "archive_candidates": archive_document,
        "active_corpora_state": {"version": 1, "corpora": active_corpora},
    }


def upsert_active_corpus(
    root: Path,
    *,
    protocol: str,
    question: str,
    source_ids: list[str],
    concept_slugs: list[str],
    bridge_evidence_ids: list[str],
    output_ref: str,
    changed_at: str,
    corpus_id_override: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    state = reconcile_active_corpora_state(root, changed_at=changed_at)
    corpora = [dict(corpus) for corpus in state.get("corpora", [])]
    base_timestamp = parse_iso_datetime(changed_at) or datetime.now(timezone.utc)
    signature = question_signature(question)
    if corpus_id_override:
        corpus_id = corpus_id_override
    else:
        seed = slugify(question)[:40] or "question"
        corpus_id = f"{protocol}-{seed}-{signature.split(':', 1)[1][:8]}"
    target: dict[str, Any] | None = None
    for corpus in corpora:
        if str(corpus.get("corpus_id") or "") == corpus_id:
            target = corpus
            break
    if target is None:
        target = {"corpus_id": corpus_id, "created_at": changed_at}
        corpora.append(target)
    output_refs = [str(item) for item in target.get("output_refs", []) if isinstance(item, str)]
    if output_ref and output_ref not in output_refs:
        output_refs.append(output_ref)
    target.update(
        {
            "protocol": protocol,
            "focus_kind": "question",
            "focus_ref": question,
            "question_hash": signature,
            "source_ids": source_ids,
            "concept_slugs": concept_slugs,
            "bridge_evidence_ids": bridge_evidence_ids,
            "output_refs": output_refs[-8:],
            "status": "active",
            "last_used_at": changed_at,
            "expires_at": (base_timestamp + ACTIVE_CORPUS_TTL).replace(microsecond=0).isoformat(),
        }
    )
    save_active_corpora_state(root, {"version": 1, "corpora": corpora})
    return target
