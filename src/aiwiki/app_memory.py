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
import re
import shutil
import threading
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .app_content import (
    action_needs_review,
    action_priority_rank,
    action_status_rank,
    action_supports_low_risk_apply,
    action_transition_profile,
    archive_transition_profile,
    collect_aging_signals,
    collect_curated_pages,
    collect_recent_output_artifacts,
    concept_label_to_slug,
    curated_page_transition_profile,
    describe_machine_memory_action,
    display_action_status,
    display_rewrite_proposal_status,
    entry_ids_from_paths,
    entry_lookup_maps,
    evaluate_page_aging,
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
    machine_memory_concept_input_signature,
    machine_memory_source_input_signature,
    normalize_concept_hardness,
    parse_causal_links,
    preserved_section,
    review_queue,
    rewrite_proposal_is_apply_ready,
    rewrite_proposal_needs_review,
    rewrite_proposal_status_rank,
    rewrite_transition_profile,
    routing_snapshot_for_protocol,
    safe_apply_preview,
    source_summary_or_preview,
    summarize_runtime_event_for_shell,
    transition_profile,
    valid_curated_statuses,
    validate_low_risk_action_targets,
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
    RESOLVABLE_MONITOR_ACTION_KINDS,
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
from .app_state import (
    DEFAULT_PROTOCOL,
    active_corpora_state_path,
    active_material_archive_entries,
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
    load_active_corpora_state,
    load_archive_candidates_state,
    load_concept_rewrite_state,
    load_json_document,
    load_knowledge_lifecycle_state,
    load_machine_memory,
    load_machine_memory_action_state_strict,
    load_machine_memory_build_state,
    load_manifest,
    load_manual_link_state,
    load_material_archive_state,
    load_query_route_telemetry,
    load_runtime_history,
    machine_memory_action_state_path,
    machine_memory_graph_html_path,
    machine_memory_history_path,
    nightly_health_state_path,
    output_packs_index_path,
    query_route_telemetry_path,
    review_center_html_path,
    save_active_corpora_state,
    save_archive_candidates_state,
    save_concept_rewrite_state,
    save_machine_memory_action_state,
    save_material_routing_state,
    save_material_state,
    save_query_route_telemetry,
    shell_summary_path,
)
from .app_utils import (
    analyze_citation_snapshots,
    extract_provenance_paths,
    html_safe_json_literal,
    parse_frontmatter,
    parse_iso_datetime,
    question_signature,
    read_text_preview,
    relative_path,
    render_frontmatter,
    sha256_bytes,
    slugify,
    tokenize,
    utc_now,
    write_if_changed,
)
from .config import LLMConfig


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


def timestamp_is_newer(candidate: str, current: str) -> bool:
    candidate_dt = parse_iso_datetime(candidate)
    current_dt = parse_iso_datetime(current)
    if candidate_dt is None:
        return False
    if current_dt is None:
        return True
    return candidate_dt > current_dt


def update_latest_timestamp(mapping: dict[str, str], key: str, timestamp: str) -> None:
    if not key or not timestamp:
        return
    if timestamp_is_newer(timestamp, mapping.get(key, "")):
        mapping[key] = timestamp


def protocol_hints_for_material(entry: dict[str, Any], preview: str) -> list[str]:
    text = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("source_type") or ""),
            preview,
        ]
    )
    scored: list[tuple[int, str]] = []
    for protocol in sorted(PROTOCOL_LIBRARY):
        if protocol == DEFAULT_PROTOCOL:
            continue
        score = protocol_focus_score(protocol, text)
        if score > 0:
            scored.append((score, protocol))
    scored.sort(key=lambda item: (-item[0], item[1]))
    hints = [protocol for _score, protocol in scored[:2]]
    return hints or [DEFAULT_PROTOCOL]


def recency_score_for_timestamp(timestamp: str) -> float:
    parsed = parse_iso_datetime(timestamp)
    if parsed is None:
        return 0.0
    now = datetime.now(timezone.utc)
    age = now - parsed
    if age <= timedelta(days=3):
        return 1.0
    if age <= timedelta(days=7):
        return 0.7
    if age <= timedelta(days=30):
        return 0.4
    return 0.1


QUERY_TIME_FOCUS_MARKERS: dict[str, tuple[str, ...]] = {
    "recent": ("latest", "recent", "current", "new", "newest", "updated", "today", "fresh"),
    "historical": ("history", "historical", "legacy", "old", "older", "previous", "prior", "archive", "archived"),
}


def machine_memory_query_time_focus(question: str) -> dict[str, Any]:
    normalized = " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", question.lower()))
    recent_hits = [marker for marker in QUERY_TIME_FOCUS_MARKERS["recent"] if marker in normalized]
    historical_hits = [marker for marker in QUERY_TIME_FOCUS_MARKERS["historical"] if marker in normalized]
    if historical_hits and len(historical_hits) >= len(recent_hits):
        return {"focus": "historical", "markers": historical_hits[:4]}
    if recent_hits:
        return {"focus": "recent", "markers": recent_hits[:4]}
    return {"focus": "", "markers": []}


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
    material_entry = material_by_entry.get(source_id, {})
    routing_entry = routing_by_entry.get(source_id, {})
    routing_snapshot = routing_snapshot_for_protocol(routing_entry, protocol)
    archive_candidate = archive_candidates_by_entry.get(source_id, {})
    temperature = str(material_entry.get("temperature") or "")

    protocol_bonus = 0.0
    top_protocols = [
        str(item.get("protocol") or "")
        for item in routing_entry.get("top_protocols", [])
        if isinstance(item, dict) and str(item.get("protocol") or "")
    ]
    protocol_is_top = top_protocols[:1] == [protocol]
    protocol_in_top2 = protocol in top_protocols[:2]
    selected_as = str(routing_snapshot.get("selected_as") or "")
    selected_bonus = 0.0
    if selected_as == "hot-evidence":
        selected_bonus = 0.9
    elif selected_as == "warm-evidence":
        selected_bonus = 0.6
    elif selected_as == "cold-evidence":
        selected_bonus = 0.3
    total_score = float(routing_snapshot.get("total_score", 0.0) or 0.0)
    if protocol_is_top:
        protocol_bonus += 2.5 + selected_bonus + min(1.0, total_score * 0.25)
    elif protocol_in_top2:
        protocol_bonus += 1.2 + min(0.25, selected_bonus * 0.4) + min(0.4, total_score * 0.1)

    activity_score = max(
        recency_score_for_timestamp(str(material_entry.get("last_touched_at") or "")),
        recency_score_for_timestamp(str(material_entry.get("last_query_hit_at") or "")),
        recency_score_for_timestamp(str(material_entry.get("last_review_reference_at") or "")),
    )
    time_bonus = 0.0
    if time_focus == "recent":
        time_bonus += activity_score * 4.0
        if temperature == "hot":
            time_bonus += 0.4
        elif temperature == "warm":
            time_bonus += 0.2
        elif temperature == "cold":
            time_bonus -= 0.35
        elif temperature == "archived":
            time_bonus -= 1.0
    elif time_focus == "historical":
        time_bonus += (1.0 - activity_score) * 4.0
        if temperature == "cold":
            time_bonus += 0.8
        elif temperature == "archived":
            time_bonus += 1.4
        elif temperature == "hot":
            time_bonus -= 0.25
        if archive_candidate:
            time_bonus += 0.6

    protocol_shard = protocol_is_top or (protocol_in_top2 and selected_as in {"hot-evidence", "warm-evidence"})
    time_shard = bool(time_focus) and time_bonus > 1.0
    archive_status = "archived" if temperature == "archived" else str(archive_candidate.get("status") or "")
    archive_hint = bool(
        temperature == "archived"
        or (time_focus == "historical" and (temperature == "cold" or bool(archive_candidate)))
        or (
            archive_candidate
            and str(archive_candidate.get("recommended_temperature") or "") == "archived"
        )
    )
    archive_hint_score = base_score + protocol_bonus + max(0.0, time_bonus)
    if temperature == "archived":
        archive_hint_score += 1.0
    elif archive_candidate:
        archive_hint_score += 0.6
    elif temperature == "cold":
        archive_hint_score += 0.3

    return {
        "entry_id": source_id,
        "title": str(source_nodes.get(source_id, {}).get("title") or source_id),
        "path": str(source_nodes.get(source_id, {}).get("source_page") or f"wiki/sources/{source_id}.md"),
        "base_score": float(base_score),
        "protocol_bonus": round(protocol_bonus, 3),
        "time_bonus": round(time_bonus, 3),
        "combined_score": round(float(base_score) + protocol_bonus + time_bonus, 3),
        "protocol_shard": protocol_shard,
        "time_shard": time_shard,
        "temperature": temperature,
        "archive_status": archive_status,
        "archive_hint": archive_hint,
        "archive_hint_score": round(archive_hint_score, 3),
        "recommended_temperature": str(archive_candidate.get("recommended_temperature") or ""),
        "reason_codes": [
            str(reason)
            for reason in archive_candidate.get("reason_codes", [])
            if isinstance(reason, str) and reason
        ],
    }


def build_machine_memory(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    previews: dict[str, str],
    entry_terms: dict[str, list[str]],
    compiled_at: str,
) -> dict[str, Any]:
    term_index: dict[str, dict[str, set[str]]] = {}
    source_nodes: list[dict[str, Any]] = []
    concept_nodes: list[dict[str, Any]] = []
    source_to_concept: list[dict[str, str]] = []
    concept_to_concept: list[dict[str, str]] = []
    concept_causal: list[dict[str, str]] = []
    citation_map: list[dict[str, Any]] = []

    def index_term(term: str, *, source_id: str | None = None, concept_slug: str | None = None) -> None:
        bucket = term_index.setdefault(term, {"source_ids": set(), "concept_slugs": set()})
        if source_id:
            bucket["source_ids"].add(source_id)
        if concept_slug:
            bucket["concept_slugs"].add(concept_slug)

    for entry in entries:
        concept_slugs = [concept_label_to_slug(label) for label in entry_terms.get(entry["id"], [])]
        source_page = f"wiki/sources/{entry['id']}.md"
        summary = source_summary_or_preview(root, entry, previews[entry["id"]])
        source_nodes.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "source_type": entry["source_type"],
                "kind": entry["kind"],
                "stored_path": entry["stored_path"],
                "original_path": entry["original_path"],
                "sha256": entry["sha256"],
                "source_page": source_page,
                "concept_slugs": concept_slugs,
            }
        )
        citation_map.append(
            {
                "source_page": source_page,
                "stored_path": entry["stored_path"],
                "original_path": entry["original_path"],
                "sha256": entry["sha256"],
            }
        )
        for slug in concept_slugs:
            source_to_concept.append({"source_id": entry["id"], "concept_slug": slug})
        for token in tokenize(f"{entry['title']}\n{summary}"):
            index_term(token, source_id=entry["id"])

    for record in concepts:
        page = root / "wiki" / "concepts" / f"{record['slug']}.md"
        frontmatter = parse_frontmatter(page.read_text(encoding="utf-8", errors="replace")) if page.exists() else {}
        causal_links = parse_causal_links(frontmatter)
        concept_nodes.append(
            {
                "slug": record["slug"],
                "title": record["title"],
                "path": f"wiki/concepts/{record['slug']}.md",
                "source_pages": [f"wiki/sources/{entry_id}.md" for entry_id in record["entry_ids"]],
                "related_slugs": record.get("related_slugs", []),
                "source_signature": record["source_signature"],
                "confidence": str(frontmatter.get("confidence") or ""),
                "hardness": normalize_concept_hardness(frontmatter.get("hardness"), default="soft"),
                "causal_links": causal_links,
            }
        )
        for related_slug in record.get("related_slugs", []):
            concept_to_concept.append({"from": record["slug"], "to": related_slug})
        for link in causal_links:
            concept_causal.append({
                "from": record["slug"],
                "to": link["target"],
                "relation": link["relation"],
                "evidence": link["evidence"],
            })
        for token in tokenize(record["title"]):
            index_term(token, concept_slug=record["slug"])

    drift = {
        "missing_raw_files": [
            entry["stored_path"] for entry in entries if not (root / entry["stored_path"]).exists()
        ],
        "missing_source_pages": [
            f"wiki/sources/{entry['id']}.md"
            for entry in entries
            if not (root / "wiki" / "sources" / f"{entry['id']}.md").exists()
        ],
        "missing_concept_pages": [
            f"wiki/concepts/{record['slug']}.md"
            for record in concepts
            if not (root / "wiki" / "concepts" / f"{record['slug']}.md").exists()
        ],
        "sources_without_concepts": [entry["id"] for entry in entries if not entry_terms.get(entry["id"])],
    }

    return {
        "version": 1,
        "compiled_at": compiled_at,
        "source_nodes": sorted(source_nodes, key=lambda item: item["id"]),
        "concept_nodes": sorted(concept_nodes, key=lambda item: item["slug"]),
        "edges": {
            "source_to_concept": sorted(source_to_concept, key=lambda item: (item["source_id"], item["concept_slug"])),
            "concept_to_concept": sorted(concept_to_concept, key=lambda item: (item["from"], item["to"])),
            "concept_causal": sorted(concept_causal, key=lambda item: (item["from"], item["to"], item["relation"])),
        },
        "citation_map": sorted(citation_map, key=lambda item: item["source_page"]),
        "term_index": {
            term: {
                "source_ids": sorted(payload["source_ids"]),
                "concept_slugs": sorted(payload["concept_slugs"]),
            }
            for term, payload in sorted(term_index.items())
        },
        "drift": drift,
    }


def _frontmatter_string_list(frontmatter: dict[str, Any], key: str) -> list[str]:
    value = frontmatter.get(key, [])
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]


def _resolve_curated_relation_id(
    reference: str,
    *,
    current_path: str,
    page_ids: set[str],
    path_to_page_id: dict[str, str],
) -> str:
    candidate = reference.strip()
    if not candidate:
        return ""
    if candidate in page_ids:
        return candidate
    if candidate in path_to_page_id:
        return path_to_page_id[candidate]
    if candidate.endswith(".md") and not candidate.startswith("wiki/"):
        relative_candidate = (Path(current_path).parent / candidate).as_posix()
        if relative_candidate in path_to_page_id:
            return path_to_page_id[relative_candidate]
    stem = Path(candidate).stem
    if stem in path_to_page_id:
        return path_to_page_id[stem]
    return ""


def attach_judgment_assets_to_machine_memory(
    root: Path,
    memory: dict[str, Any],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
) -> dict[str, Any]:
    manifest_entries = load_manifest(root).get("entries", [])
    path_to_entry_id: dict[str, str] = {}
    for entry in manifest_entries:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            continue
        path_to_entry_id[f"wiki/sources/{entry_id}.md"] = entry_id
        stored_path = str(entry.get("stored_path") or "")
        if stored_path:
            path_to_entry_id[stored_path] = entry_id
    page_records: list[dict[str, Any]] = []
    path_to_page_id: dict[str, str] = {}
    page_kind_by_id: dict[str, str] = {}
    for page in decisions + judgments:
        page_path = str(page.get("path") or "")
        if not page_path:
            continue
        target = root / page_path
        content = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        frontmatter = parse_frontmatter(content)
        citations = _frontmatter_string_list(frontmatter, "citations")
        citation_snapshot_state = analyze_citation_snapshots(root, citations, frontmatter)
        source_ids = sorted(
            {
                entry_id
                for entry_id in (path_to_entry_id.get(citation) for citation in citations)
                if isinstance(entry_id, str) and entry_id
            }
        )
        page_id = str(page.get("page_id") or frontmatter.get("id") or Path(page_path).stem)
        page_kind = str(page.get("kind") or frontmatter.get("kind") or "")
        record = {
            "page_id": page_id,
            "title": str(page.get("title") or frontmatter.get("title") or page_id),
            "path": page_path,
            "kind": page_kind,
            "status": str(page.get("status") or frontmatter.get("status") or ""),
            "protocol": str(page.get("protocol") or frontmatter.get("protocol") or DEFAULT_PROTOCOL),
            "confidence": str(page.get("confidence") or frontmatter.get("confidence") or ""),
            "citations": citations,
            "source_ids": source_ids,
            "counter_evidence": _frontmatter_string_list(frontmatter, "counter_evidence"),
            "invalidation_rule": str(frontmatter.get("invalidation_rule") or "").strip(),
            "next_signals": _frontmatter_string_list(frontmatter, "next_signals"),
            "reviewed_at": str(page.get("reviewed_at") or frontmatter.get("reviewed_at") or ""),
            "revisit_after": str(page.get("revisit_after") or frontmatter.get("revisit_after") or ""),
            "escalate_after": str(page.get("escalate_after") or frontmatter.get("escalate_after") or ""),
            "formed_at": str(page.get("formed_at") or frontmatter.get("formed_at") or frontmatter.get("last_compiled_at") or ""),
            "last_reviewed": str(page.get("last_reviewed") or frontmatter.get("last_reviewed") or frontmatter.get("reviewed_at") or ""),
            "asset_score": int(page.get("asset_score", "0") or 0),
            "citation_drift": "true" if citation_snapshot_state["has_drift"] else "false",
            "citation_drift_count": len(citation_snapshot_state["drifted"]),
            "citation_snapshot_gap_count": len(citation_snapshot_state["missing"])
            + len(citation_snapshot_state["stale"]),
            "related_judgments_raw": _frontmatter_string_list(frontmatter, "related_judgments"),
            "supports_raw": _frontmatter_string_list(frontmatter, "supports"),
            "contradicts_raw": _frontmatter_string_list(frontmatter, "contradicts"),
        }
        page_records.append(record)
        path_to_page_id[page_path] = page_id
        path_to_page_id[Path(page_path).name] = page_id
        path_to_page_id[Path(page_path).stem] = page_id
        page_kind_by_id[page_id] = page_kind
    judgment_nodes: list[dict[str, Any]] = []
    source_to_judgment: list[dict[str, str]] = []
    judgment_to_judgment: list[dict[str, str]] = []
    judgment_to_decision: list[dict[str, str]] = []
    page_ids = set(page_kind_by_id)
    seen_judgment_edges: set[tuple[str, str, str]] = set()
    seen_decision_edges: set[tuple[str, str, str]] = set()
    for record in page_records:
        page_id = str(record["page_id"])
        page_path = str(record["path"])
        related_judgments = [
            target_id
            for target_id in (
                _resolve_curated_relation_id(
                    reference,
                    current_path=page_path,
                    page_ids=page_ids,
                    path_to_page_id=path_to_page_id,
                )
                for reference in list(record.get("related_judgments_raw") or [])
            )
            if target_id and target_id != page_id
        ]
        supports = [
            target_id
            for target_id in (
                _resolve_curated_relation_id(
                    reference,
                    current_path=page_path,
                    page_ids=page_ids,
                    path_to_page_id=path_to_page_id,
                )
                for reference in list(record.get("supports_raw") or [])
            )
            if target_id and target_id != page_id
        ]
        contradicts = [
            target_id
            for target_id in (
                _resolve_curated_relation_id(
                    reference,
                    current_path=page_path,
                    page_ids=page_ids,
                    path_to_page_id=path_to_page_id,
                )
                for reference in list(record.get("contradicts_raw") or [])
            )
            if target_id and target_id != page_id
        ]
        judgment_nodes.append(
            {
                **record,
                "related_judgments": sorted(dict.fromkeys(related_judgments)),
                "supports": sorted(dict.fromkeys(supports)),
                "contradicts": sorted(dict.fromkeys(contradicts)),
            }
        )
        for source_id in list(record.get("source_ids") or []):
            source_to_judgment.append({"source_id": source_id, "page_id": page_id})
        relation_targets = (
            [("related", target_id) for target_id in related_judgments]
            + [("supports", target_id) for target_id in supports]
            + [("contradicts", target_id) for target_id in contradicts]
        )
        current_kind = str(record.get("kind") or "")
        for relation, target_id in relation_targets:
            target_kind = str(page_kind_by_id.get(target_id) or "")
            if "decision" in {current_kind, target_kind} and "judgment" in {current_kind, target_kind}:
                edge_key = (page_id, target_id, relation)
                if edge_key in seen_decision_edges:
                    continue
                seen_decision_edges.add(edge_key)
                judgment_to_decision.append(
                    {
                        "from": page_id,
                        "to": target_id,
                        "relation": relation,
                        "judgment_id": page_id if current_kind == "judgment" else target_id,
                        "decision_id": page_id if current_kind == "decision" else target_id,
                    }
                )
                continue
            edge_key = (page_id, target_id, relation)
            if edge_key in seen_judgment_edges:
                continue
            seen_judgment_edges.add(edge_key)
            judgment_to_judgment.append(
                {
                    "from": page_id,
                    "to": target_id,
                    "relation": relation,
                }
            )
    updated = dict(memory)
    updated["judgment_nodes"] = sorted(judgment_nodes, key=lambda item: (item["kind"], item["page_id"]))
    edges = dict(memory.get("edges", {}))
    edges["source_to_judgment"] = sorted(source_to_judgment, key=lambda item: (item["source_id"], item["page_id"]))
    edges["judgment_to_judgment"] = sorted(
        judgment_to_judgment,
        key=lambda item: (item["relation"], item["from"], item["to"]),
    )
    edges["judgment_to_decision"] = sorted(
        judgment_to_decision,
        key=lambda item: (item["relation"], item["from"], item["to"]),
    )
    updated["edges"] = edges
    return updated


def plan_machine_memory_build(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    previews: dict[str, str],
    entry_terms: dict[str, list[str]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    previous_state = load_machine_memory_build_state(root)
    previous_source_records = previous_state.get("source_records", {})
    previous_concept_records = previous_state.get("concept_records", {})
    if not isinstance(previous_source_records, dict):
        previous_source_records = {}
    if not isinstance(previous_concept_records, dict):
        previous_concept_records = {}

    source_records: dict[str, dict[str, str]] = {}
    dirty_source_ids: list[str] = []
    clean_source_ids: list[str] = []
    for entry in entries:
        entry_id = str(entry["id"])
        input_signature = machine_memory_source_input_signature(
            root,
            entry,
            previews.get(entry_id, ""),
            entry_terms.get(entry_id, []),
        )
        source_records[entry_id] = {"input_signature": input_signature}
        previous_record = previous_source_records.get(entry_id, {})
        if (
            isinstance(previous_record, dict)
            and str(previous_record.get("input_signature") or "") == input_signature
        ):
            clean_source_ids.append(entry_id)
        else:
            dirty_source_ids.append(entry_id)

    concept_records: dict[str, dict[str, str]] = {}
    dirty_concept_slugs: list[str] = []
    clean_concept_slugs: list[str] = []
    for record in concepts:
        slug = str(record["slug"])
        input_signature = machine_memory_concept_input_signature(root, record)
        concept_records[slug] = {"input_signature": input_signature}
        previous_record = previous_concept_records.get(slug, {})
        if (
            isinstance(previous_record, dict)
            and str(previous_record.get("input_signature") or "") == input_signature
        ):
            clean_concept_slugs.append(slug)
        else:
            dirty_concept_slugs.append(slug)

    removed_source_ids = sorted(set(previous_source_records) - set(source_records))
    removed_concept_slugs = sorted(set(previous_concept_records) - set(concept_records))
    return {
        "state_document": {
            "version": 1,
            "generated_at": generated_at,
            "source_records": source_records,
            "concept_records": concept_records,
        },
        "dirty_source_ids": dirty_source_ids,
        "clean_source_ids": clean_source_ids,
        "dirty_concept_slugs": dirty_concept_slugs,
        "clean_concept_slugs": clean_concept_slugs,
        "removed_source_ids": removed_source_ids,
        "removed_concept_slugs": removed_concept_slugs,
        "inputs_clean": not (
            dirty_source_ids
            or dirty_concept_slugs
            or removed_source_ids
            or removed_concept_slugs
        ),
    }


def machine_memory_snapshot_is_reusable(memory: dict[str, Any]) -> bool:
    return (
        isinstance(memory.get("source_nodes"), list)
        and isinstance(memory.get("concept_nodes"), list)
        and isinstance(memory.get("edges"), dict)
        and isinstance(memory.get("citation_map"), list)
        and isinstance(memory.get("term_index"), dict)
        and isinstance(memory.get("drift"), dict)
    )


def reuse_machine_memory_core(previous: dict[str, Any], compiled_at: str) -> dict[str, Any]:
    return {
        "version": int(previous.get("version", 1) or 1),
        "compiled_at": compiled_at,
        "source_nodes": list(previous.get("source_nodes", [])),
        "concept_nodes": list(previous.get("concept_nodes", [])),
        "edges": dict(previous.get("edges", {})),
        "citation_map": list(previous.get("citation_map", [])),
        "term_index": dict(previous.get("term_index", {})),
        "drift": dict(previous.get("drift", {})),
    }


def build_machine_memory_health(memory: dict[str, Any]) -> dict[str, Any]:
    # Local import breaks the historical app_memory <-> app_memory_surfaces cycle:
    # helpers live in app_memory_query now, but this function still belongs here.
    from . import app_memory_query as _memory_query

    source_nodes = memory.get("source_nodes", [])
    concept_nodes = memory.get("concept_nodes", [])
    edges = memory.get("edges", {})
    drift = memory.get("drift", {})

    source_to_concepts: dict[str, set[str]] = {}
    concept_to_sources: dict[str, set[str]] = {}
    concept_related: dict[str, set[str]] = {}
    source_node_by_id = {node["id"]: node for node in source_nodes}
    concept_node_by_slug = {node["slug"]: node for node in concept_nodes}

    for edge in edges.get("source_to_concept", []):
        source_id = edge.get("source_id")
        concept_slug = edge.get("concept_slug")
        if not isinstance(source_id, str) or not isinstance(concept_slug, str):
            continue
        source_to_concepts.setdefault(source_id, set()).add(concept_slug)
        concept_to_sources.setdefault(concept_slug, set()).add(source_id)

    for edge in edges.get("concept_to_concept", []):
        left = edge.get("from")
        right = edge.get("to")
        if not isinstance(left, str) or not isinstance(right, str):
            continue
        concept_related.setdefault(left, set()).add(right)
        concept_related.setdefault(right, set()).add(left)

    concept_causal_count = 0
    for edge in edges.get("concept_causal", []):
        left = edge.get("from")
        right = edge.get("to")
        if not isinstance(left, str) or not isinstance(right, str):
            continue
        concept_causal_count += 1
        concept_related.setdefault(left, set()).add(right)
        concept_related.setdefault(right, set()).add(left)

    isolated_source_ids = sorted(node["id"] for node in source_nodes if not source_to_concepts.get(node["id"]))
    singleton_concept_slugs = sorted(
        node["slug"]
        for node in concept_nodes
        if len(concept_to_sources.get(node["slug"], set())) <= 1 and not concept_related.get(node["slug"])
    )
    bridge_concept_slugs = [
        node["slug"]
        for node in sorted(
            concept_nodes,
            key=lambda item: (
                -len(concept_to_sources.get(item["slug"], set())),
                -len(concept_related.get(item["slug"], set())),
                item["title"].lower(),
            ),
        )
        if len(concept_to_sources.get(node["slug"], set())) >= 2 and concept_related.get(node["slug"])
    ]
    overloaded_concept_slugs = sorted(
        node["slug"] for node in concept_nodes if len(concept_to_sources.get(node["slug"], set())) >= 4
    )

    hub_concepts = [
        {
            "slug": node["slug"],
            "title": node["title"],
            "source_count": len(concept_to_sources.get(node["slug"], set())),
            "related_count": len(concept_related.get(node["slug"], set())),
            "component_id": "",
        }
        for node in concept_nodes
    ]
    hub_concepts.sort(
        key=lambda item: (-item["source_count"], -item["related_count"], item["title"].lower())
    )
    hub_sources = [
        {
            "id": node["id"],
            "title": node["title"],
            "concept_count": len(source_to_concepts.get(node["id"], set())),
            "source_page": node["source_page"],
            "component_id": "",
        }
        for node in source_nodes
    ]
    hub_sources.sort(key=lambda item: (-item["concept_count"], item["title"].lower()))

    adjacency = _memory_query.build_machine_memory_adjacency(memory)

    visited: set[str] = set()
    component_sizes: list[int] = []
    component_records: list[dict[str, Any]] = []
    for node_key in sorted(adjacency):
        if node_key in visited:
            continue
        stack = [node_key]
        members: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            members.add(current)
            stack.extend(sorted(set(adjacency.get(current, {})) - visited))
        component_sizes.append(len(members))
        source_ids = sorted(member.removeprefix("source:") for member in members if member.startswith("source:"))
        concept_slugs = sorted(member.removeprefix("concept:") for member in members if member.startswith("concept:"))
        judgment_ids = sorted(member.removeprefix("judgment:") for member in members if member.startswith("judgment:"))
        component_records.append(
            {
                "source_ids": source_ids,
                "concept_slugs": concept_slugs,
                "judgment_ids": judgment_ids,
                "size": len(members),
                "sort_key": (
                    -len(members),
                    source_ids[0] if source_ids else "~",
                    concept_slugs[0] if concept_slugs else "~",
                    judgment_ids[0] if judgment_ids else "~",
                ),
            }
        )
    component_sizes.sort(reverse=True)
    component_records.sort(key=lambda item: item["sort_key"])
    components: list[dict[str, Any]] = []
    source_component_ids: dict[str, str] = {}
    concept_component_ids: dict[str, str] = {}
    judgment_component_ids: dict[str, str] = {}
    for index, record in enumerate(component_records, start=1):
        component_id = f"component-{index}"
        components.append(
            {
                "id": component_id,
                "size": record["size"],
                "source_ids": record["source_ids"],
                "concept_slugs": record["concept_slugs"],
                "judgment_ids": record["judgment_ids"],
            }
        )
        for source_id in record["source_ids"]:
            source_component_ids[source_id] = component_id
        for concept_slug in record["concept_slugs"]:
            concept_component_ids[concept_slug] = component_id
        for judgment_id in record["judgment_ids"]:
            judgment_component_ids[judgment_id] = component_id

    for item in hub_concepts:
        item["component_id"] = concept_component_ids.get(item["slug"], "")
    for item in hub_sources:
        item["component_id"] = source_component_ids.get(item["id"], "")

    term_index = memory.get("term_index", {})
    suggestion_scores: dict[tuple[str, str], set[str]] = {}
    for term, payload in term_index.items():
        source_ids = payload.get("source_ids", [])
        concept_slugs = payload.get("concept_slugs", [])
        if not source_ids or not concept_slugs:
            continue
        for source_id in source_ids:
            if source_id not in drift.get("sources_without_concepts", []) and source_id not in isolated_source_ids:
                continue
            for concept_slug in concept_slugs:
                suggestion_scores.setdefault((source_id, concept_slug), set()).add(term)

    link_suggestions: list[dict[str, Any]] = []
    for (source_id, concept_slug), shared_terms in suggestion_scores.items():
        source_node = source_node_by_id.get(source_id)
        concept_node = concept_node_by_slug.get(concept_slug)
        if not source_node or not concept_node:
            continue
        link_suggestions.append(
            {
                "source_id": source_id,
                "source_title": source_node["title"],
                "source_page": source_node["source_page"],
                "concept_slug": concept_slug,
                "concept_title": concept_node["title"],
                "concept_page": f"wiki/concepts/{concept_slug}.md",
                "shared_terms": sorted(shared_terms),
                "score": len(shared_terms),
                "component_id": concept_component_ids.get(concept_slug, ""),
            }
        )
    link_suggestions.sort(
        key=lambda item: (-item["score"], item["source_title"].lower(), item["concept_title"].lower())
    )

    actions: list[dict[str, Any]] = []
    for suggestion in link_suggestions[:12]:
        shared_terms = suggestion.get("shared_terms", [])
        actions.append(
            {
                "id": f"link-{suggestion['source_id']}-{suggestion['concept_slug']}",
                "kind": "add-source-concept-link",
                "priority": "high" if suggestion["score"] >= 3 else "medium",
                "title": f"补连 {suggestion['source_title']} -> {suggestion['concept_title']}",
                "primary_path": suggestion["source_page"],
                "secondary_path": suggestion["concept_page"],
                "component_id": suggestion.get("component_id", ""),
                "reason": f"共享词：{', '.join(shared_terms[:6]) or 'none'}",
                "score": suggestion["score"],
                "source_ids": [suggestion["source_id"]],
                "concept_slugs": [suggestion["concept_slug"]],
            }
        )

    suggested_source_ids = {action["source_ids"][0] for action in actions if action.get("source_ids")}
    for source_id in isolated_source_ids:
        if source_id in suggested_source_ids:
            continue
        source_node = source_node_by_id.get(source_id)
        if not source_node:
            continue
        actions.append(
            {
                "id": f"isolated-source-{source_id}",
                "kind": "connect-isolated-source",
                "priority": "medium",
                "title": f"连接孤立来源 {source_node['title']}",
                "primary_path": source_node["source_page"],
                "secondary_path": "",
                "component_id": source_component_ids.get(source_id, ""),
                "reason": "来源节点当前没有接入任何概念。",
                "score": 1,
                "source_ids": [source_id],
                "concept_slugs": [],
            }
        )

    for concept_slug in singleton_concept_slugs[:8]:
        concept_node = concept_node_by_slug.get(concept_slug)
        if not concept_node:
            continue
        source_count = len(concept_to_sources.get(concept_slug, set()))
        actions.append(
            {
                "id": f"singleton-concept-{concept_slug}",
                "kind": "expand-singleton-concept",
                "priority": "medium",
                "title": f"扩展单节点概念 {concept_node['title']}",
                "primary_path": f"wiki/concepts/{concept_slug}.md",
                "secondary_path": "",
                "component_id": concept_component_ids.get(concept_slug, ""),
                "reason": f"当前只关联 `{source_count}` 个来源，且没有概念间连接。",
                "score": max(1, source_count),
                "source_ids": sorted(concept_to_sources.get(concept_slug, set())),
                "concept_slugs": [concept_slug],
            }
        )

    for concept_slug in overloaded_concept_slugs[:8]:
        concept_node = concept_node_by_slug.get(concept_slug)
        if not concept_node:
            continue
        source_count = len(concept_to_sources.get(concept_slug, set()))
        actions.append(
            {
                "id": f"overloaded-concept-{concept_slug}",
                "kind": "split-overloaded-concept",
                "priority": "high" if source_count >= 6 else "medium",
                "title": f"拆分过载概念 {concept_node['title']}",
                "primary_path": f"wiki/concepts/{concept_slug}.md",
                "secondary_path": "",
                "component_id": concept_component_ids.get(concept_slug, ""),
                "reason": f"当前挂接 `{source_count}` 个来源，可能过宽。",
                "score": source_count,
                "source_ids": sorted(concept_to_sources.get(concept_slug, set())),
                "concept_slugs": [concept_slug],
            }
        )

    for concept_slug in bridge_concept_slugs[:6]:
        concept_node = concept_node_by_slug.get(concept_slug)
        if not concept_node:
            continue
        related_count = len(concept_related.get(concept_slug, set()))
        actions.append(
            {
                "id": f"bridge-concept-{concept_slug}",
                "kind": "monitor-bridge-concept",
                "priority": "low",
                "title": f"观察桥接概念 {concept_node['title']}",
                "primary_path": f"wiki/concepts/{concept_slug}.md",
                "secondary_path": "",
                "component_id": concept_component_ids.get(concept_slug, ""),
                "reason": f"概念连接 `{related_count}` 个相关概念，属于图谱桥接点。",
                "score": related_count,
                "source_ids": sorted(concept_to_sources.get(concept_slug, set())),
                "concept_slugs": [concept_slug],
            }
        )

    for node in memory.get("judgment_nodes", []):
        if not isinstance(node, dict):
            continue
        page_id = str(node.get("page_id") or "").strip()
        page_path = str(node.get("path") or "").strip()
        if not page_id or not page_path:
            continue
        citation_drift_count = int(node.get("citation_drift_count", 0) or 0)
        citation_snapshot_gap_count = int(node.get("citation_snapshot_gap_count", 0) or 0)
        if citation_drift_count <= 0 and citation_snapshot_gap_count <= 0:
            continue
        source_ids = [str(item) for item in node.get("source_ids", []) if isinstance(item, str) and item]
        primary_source_id = source_ids[0] if source_ids else ""
        reason_parts: list[str] = []
        if citation_drift_count:
            reason_parts.append(f"citation drift `{citation_drift_count}`")
        if citation_snapshot_gap_count:
            reason_parts.append(f"snapshot gap `{citation_snapshot_gap_count}`")
        actions.append(
            {
                "id": f"refresh-citation-snapshots-{page_id}",
                "kind": "refresh-citation-snapshots",
                "priority": "high" if citation_drift_count else "medium",
                "title": f"刷新引用快照 {node.get('title') or page_id}",
                "primary_path": page_path,
                "secondary_path": "",
                "component_id": source_component_ids.get(primary_source_id, ""),
                "reason": " / ".join(reason_parts) or "Judgment page citation snapshot metadata has drift.",
                "score": citation_drift_count * 2 + citation_snapshot_gap_count,
                "source_ids": source_ids,
                "concept_slugs": [],
                "protocol": str(node.get("protocol") or DEFAULT_PROTOCOL),
            }
        )

    priority_order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(
        key=lambda item: (
            priority_order.get(str(item.get("priority")), 9),
            -int(item.get("score", 0)),
            str(item.get("title", "")).lower(),
            str(item.get("id", "")),
        )
    )
    action_counts = {
        "total": len(actions),
        "by_priority": {
            priority: sum(1 for action in actions if action.get("priority") == priority)
            for priority in ("high", "medium", "low")
        },
        "by_kind": {
            kind: sum(1 for action in actions if action.get("kind") == kind)
            for kind in (
                "add-source-concept-link",
                "connect-isolated-source",
                "expand-singleton-concept",
                "split-overloaded-concept",
                "monitor-bridge-concept",
                "refresh-citation-snapshots",
            )
        },
    }
    judgment_relation_counts = {
        "source_to_judgment": len(edges.get("source_to_judgment", [])),
        "judgment_to_judgment": len(edges.get("judgment_to_judgment", [])),
        "judgment_to_decision": len(edges.get("judgment_to_decision", [])),
    }

    return {
        "isolated_source_ids": isolated_source_ids,
        "singleton_concept_slugs": singleton_concept_slugs,
        "bridge_concept_slugs": bridge_concept_slugs[:10],
        "overloaded_concept_slugs": overloaded_concept_slugs,
        "hub_concepts": hub_concepts[:10],
        "hub_sources": hub_sources[:10],
        "link_suggestions": link_suggestions[:12],
        "actions": actions[:20],
        "action_counts": action_counts,
        "component_count": len(component_sizes),
        "component_sizes": component_sizes,
        "components": components,
        "source_component_ids": source_component_ids,
        "concept_component_ids": concept_component_ids,
        "judgment_component_ids": judgment_component_ids,
        "judgment_relation_counts": judgment_relation_counts,
        "concept_causal_count": concept_causal_count,
    }


def reconcile_machine_memory_actions(
    root: Path,
    health: dict[str, Any],
    *,
    compiled_at: str,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    previous_state = load_machine_memory_action_state_strict(root)
    previous_by_id = {
        str(action.get("id")): action for action in previous_state.get("actions", []) if action.get("id")
    }
    now = parse_iso_datetime(compiled_at) or datetime.now(timezone.utc)
    active_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for action in health.get("actions", []):
        action_id = str(action.get("id") or "").strip()
        if not action_id:
            continue
        previous = previous_by_id.get(action_id, {})
        previous_status = str(previous.get("status") or "proposed")
        protocol = str(previous.get("protocol") or action.get("protocol") or active_protocol or DEFAULT_PROTOCOL)
        status = previous_status if previous_status in ACTION_STATUSES else "proposed"
        reopened_count = int(previous.get("reopened_count") or 0)
        reopened_from = ""
        if previous and previous.get("active") is False and status in {"resolved", "rejected"}:
            reopened_from = status
            reopened_count += 1
            status = "proposed"
        first_seen_at = str(previous.get("first_seen_at") or compiled_at)
        occurrences = int(previous.get("occurrences") or 0)
        if occurrences <= 0:
            occurrences = 1
        else:
            occurrences += 1
        status_updated_at = str(previous.get("status_updated_at") or first_seen_at)
        if status != previous_status or not status_updated_at:
            status_updated_at = compiled_at
        reviewed_at = str(previous.get("reviewed_at") or "")
        review_note = str(previous.get("review_note") or "")
        last_receipt_path = str(previous.get("last_receipt_path") or "")
        auto_resolution = previous.get("auto_resolution") if isinstance(previous.get("auto_resolution"), dict) else None
        keep_auto_exception = (
            status == "deferred"
            and str(previous.get("human_required") or "").lower() == "true"
            and str(previous.get("human_required_reason") or "").strip()
        )
        human_required = str(previous.get("human_required") or "") if keep_auto_exception else ""
        human_required_reason = str(previous.get("human_required_reason") or "") if keep_auto_exception else ""
        revert_supported = str(previous.get("revert_supported") or "") if keep_auto_exception else ""
        revisit_after = str(previous.get("revisit_after") or "")
        escalate_after = str(previous.get("escalate_after") or "")
        if status in PENDING_ACTION_STATUSES:
            if not revisit_after and not escalate_after:
                base_timestamp = reviewed_at or status_updated_at or first_seen_at
                revisit_after, escalate_after = schedule_review_windows(
                    "action",
                    status,
                    base_timestamp,
                    protocol=protocol,
                    root=root,
                )
        else:
            revisit_after, escalate_after = "", ""
        record = {
            **action,
            "protocol": protocol,
            "status": status,
            "active": True,
            "first_seen_at": first_seen_at,
            "last_seen_at": compiled_at,
            "occurrences": occurrences,
            "status_updated_at": status_updated_at,
            "reviewed_at": reviewed_at,
            "review_note": review_note,
            "last_receipt_path": last_receipt_path,
            "revisit_after": revisit_after,
            "escalate_after": escalate_after,
            "reopened_count": reopened_count,
            "reopened_from": reopened_from,
            "inactive_since": "",
            "pending_review": "true" if action_needs_review(status) else "false",
        }
        if keep_auto_exception:
            record["human_required"] = human_required
            record["human_required_reason"] = human_required_reason
            record["revert_supported"] = revert_supported
        if keep_auto_exception and auto_resolution is not None:
            record["auto_resolution"] = dict(auto_resolution)
        record.update(evaluate_page_aging(record, now=now))
        active_records.append(record)
        seen_ids.add(action_id)

    inactive_records: list[dict[str, Any]] = []
    for action_id, previous in previous_by_id.items():
        if action_id in seen_ids:
            continue
        preserved_pending = (
            bool(previous.get("active", True))
            and str(previous.get("status") or "") in PENDING_ACTION_STATUSES
        )
        if preserved_pending:
            preview = safe_apply_preview(root, previous)
            kind = str(previous.get("kind") or "")
            if kind in LOW_RISK_APPLYABLE_ACTION_KINDS:
                try:
                    validate_low_risk_action_targets(root, previous)
                except RuntimeError:
                    preserved_pending = False
            elif kind in RESOLVABLE_MONITOR_ACTION_KINDS:
                # Monitor actions are signal-driven: if they disappear from the
                # current candidate set the underlying signal is gone.
                preserved_pending = False
            elif not isinstance(preview, dict):
                preserved_pending = False
        if preserved_pending:
            status = str(previous.get("status") or "proposed")
            reviewed_at = str(previous.get("reviewed_at") or "")
            first_seen_at = str(previous.get("first_seen_at") or compiled_at)
            status_updated_at = str(previous.get("status_updated_at") or first_seen_at)
            revisit_after = str(previous.get("revisit_after") or "")
            escalate_after = str(previous.get("escalate_after") or "")
            if not revisit_after and not escalate_after:
                base_timestamp = reviewed_at or status_updated_at or first_seen_at
                revisit_after, escalate_after = schedule_review_windows(
                    "action",
                    status,
                    base_timestamp,
                    protocol=str(previous.get("protocol") or active_protocol or DEFAULT_PROTOCOL),
                    root=root,
                )
            record = {
                **dict(previous),
                "protocol": str(previous.get("protocol") or active_protocol or DEFAULT_PROTOCOL),
                "status": status,
                "active": True,
                "last_seen_at": compiled_at,
                "inactive_since": "",
                "pending_review": "true" if action_needs_review(status) else "false",
                "revisit_after": revisit_after,
                "escalate_after": escalate_after,
            }
            record.update(evaluate_page_aging(record, now=now))
            active_records.append(record)
            seen_ids.add(action_id)
            continue
        record = dict(previous)
        record["protocol"] = str(previous.get("protocol") or active_protocol or DEFAULT_PROTOCOL)
        record["active"] = False
        record["inactive_since"] = str(previous.get("inactive_since") or compiled_at)
        record["pending_review"] = "false"
        record["aging_state"] = ""
        record["overdue_review"] = "false"
        record["escalation_candidate"] = "false"
        inactive_records.append(record)

    active_records.sort(
        key=lambda item: (
            action_status_rank(str(item.get("status"))),
            action_priority_rank(str(item.get("priority"))),
            -int(item.get("occurrences", 0)),
            -int(item.get("score", 0)),
            str(item.get("title", "")).lower(),
        )
    )
    inactive_records.sort(
        key=lambda item: (
            str(item.get("inactive_since") or item.get("last_seen_at") or ""),
            str(item.get("title", "")).lower(),
        ),
        reverse=True,
    )
    overdue_actions = [record for record in active_records if record.get("overdue_review") == "true"]
    escalated_actions = [record for record in active_records if record.get("escalation_candidate") == "true"]
    active_records = [{**record, **describe_machine_memory_action(record, root=root)} for record in active_records]
    inactive_records = [{**record, **describe_machine_memory_action(record, root=root)} for record in inactive_records]
    overdue_actions = [{**record, **describe_machine_memory_action(record, root=root)} for record in overdue_actions]
    escalated_actions = [{**record, **describe_machine_memory_action(record, root=root)} for record in escalated_actions]
    counts = {
        "total": len(active_records),
        "inactive": len(inactive_records),
        "overdue": len(overdue_actions),
        "escalated": len(escalated_actions),
        "by_priority": {
            priority: sum(1 for action in active_records if action.get("priority") == priority)
            for priority in ("high", "medium", "low")
        },
        "by_status": {
            status: sum(1 for action in active_records if action.get("status") == status)
            for status in ACTION_STATUSES
        },
        "by_kind": {
            kind: sum(1 for action in active_records if action.get("kind") == kind)
            for kind in (
                "add-source-concept-link",
                "connect-isolated-source",
                "expand-singleton-concept",
                "split-overloaded-concept",
                "monitor-bridge-concept",
            )
        },
    }
    state_document = {
        "version": 1,
        "compiled_at": compiled_at,
        "actions": active_records + inactive_records,
    }
    save_machine_memory_action_state(root, state_document)
    return {
        "actions": active_records[:20],
        "inactive_actions": inactive_records[:12],
        "overdue_actions": overdue_actions[:10],
        "escalated_actions": escalated_actions[:10],
        "action_counts": counts,
        "action_state_path": relative_path(root, machine_memory_action_state_path(root)),
    }


def machine_memory_digest(memory: dict[str, Any]) -> str:
    payload = {
        "source_nodes": memory.get("source_nodes", []),
        "concept_nodes": memory.get("concept_nodes", []),
        "judgment_nodes": memory.get("judgment_nodes", []),
        "edges": memory.get("edges", {}),
        "citation_map": memory.get("citation_map", []),
        "term_index": memory.get("term_index", {}),
        "drift": memory.get("drift", {}),
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def build_machine_memory_graph(memory: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for node in memory.get("source_nodes", []):
        nodes.append(
            {
                "id": f"source:{node['id']}",
                "kind": "source",
                "title": node["title"],
                "source_type": node["source_type"],
                "source_page": node["source_page"],
                "stored_path": node["stored_path"],
            }
        )
    for node in memory.get("concept_nodes", []):
        nodes.append(
            {
                "id": f"concept:{node['slug']}",
                "kind": "concept",
                "title": node["title"],
                "source_pages": node["source_pages"],
            }
        )
    for node in memory.get("judgment_nodes", []):
        nodes.append(
            {
                "id": f"judgment:{node['page_id']}",
                "kind": "judgment",
                "title": node["title"],
                "page_path": node["path"],
                "page_kind": node["kind"],
                "status": node["status"],
                "source_ids": node.get("source_ids", []),
            }
        )
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        edges.append(
            {
                "source": f"source:{edge['source_id']}",
                "target": f"concept:{edge['concept_slug']}",
                "type": "HAS_CONCEPT",
            }
        )
    for edge in memory.get("edges", {}).get("source_to_judgment", []):
        edges.append(
            {
                "source": f"source:{edge['source_id']}",
                "target": f"judgment:{edge['page_id']}",
                "type": "SUPPORTS_JUDGMENT",
            }
        )
    for edge in memory.get("edges", {}).get("judgment_to_judgment", []):
        relation = str(edge.get("relation") or "related").upper()
        edges.append(
            {
                "source": f"judgment:{edge['from']}",
                "target": f"judgment:{edge['to']}",
                "type": f"JUDGMENT_{relation}",
            }
        )
    for edge in memory.get("edges", {}).get("judgment_to_decision", []):
        relation = str(edge.get("relation") or "supports").upper()
        edges.append(
            {
                "source": f"judgment:{edge['from']}",
                "target": f"judgment:{edge['to']}",
                "type": f"DECISION_{relation}",
            }
        )
    for edge in memory.get("edges", {}).get("concept_to_concept", []):
        edges.append(
            {
                "source": f"concept:{edge['from']}",
                "target": f"concept:{edge['to']}",
                "type": "RELATED_CONCEPT",
            }
        )
    for edge in memory.get("edges", {}).get("concept_causal", []):
        relation = str(edge.get("relation") or "causes").upper()
        edges.append(
            {
                "source": f"concept:{edge['from']}",
                "target": f"concept:{edge['to']}",
                "type": f"CAUSAL_{relation}",
            }
        )
    graph = {
        "version": 1,
        "compiled_at": memory["compiled_at"],
        "nodes": sorted(nodes, key=lambda item: (item["kind"], item["id"])),
        "edges": sorted(edges, key=lambda item: (item["type"], item["source"], item["target"])),
    }
    graph["digest"] = sha256_bytes(json.dumps({"nodes": graph["nodes"], "edges": graph["edges"]}, sort_keys=True).encode("utf-8"))
    return graph


def store_concept_rewrite_candidate(
    root: Path,
    slug: str,
    *,
    quality_record: dict[str, Any],
    candidate_markdown: str,
    generated_at: str,
) -> dict[str, Any]:
    # Local import: concept_page_snapshot lives in app_memory_query;
    # concept_rewrite_proposal_digest / render_concept_rewrite_proposal_page live
    # in app_memory_surfaces. Local import avoids the module-level cycle.
    from . import app_memory_query as _memory_query
    from . import app_memory_surfaces as _memory_surfaces

    ensure_layout(root)
    snapshot = _memory_query.concept_page_snapshot(root, slug)
    state = load_concept_rewrite_state(root)
    proposals = [dict(proposal) for proposal in state.get("proposals", []) if isinstance(proposal, dict)]
    target: dict[str, Any] | None = None
    for proposal in proposals:
        if str(proposal.get("slug") or "") == slug:
            target = proposal
            break
    if target is None:
        target = {
            "slug": slug,
            "title": str(quality_record.get("title") or snapshot.get("title") or slug),
            "status": "proposed",
            "first_proposed_at": generated_at,
        }
        proposals.append(target)
    digest = _memory_surfaces.concept_rewrite_proposal_digest(candidate_markdown)
    previous_digest = str(target.get("candidate_digest") or "")
    previous_status = str(target.get("status") or "proposed")
    if previous_digest and previous_digest != digest and previous_status != "proposed":
        target["status"] = "proposed"
        target["reviewed_at"] = ""
        target["review_note"] = ""
        target["applied_at"] = ""
        target["last_applied_at"] = ""
        target["reverted_at"] = ""
        target["revert_note"] = ""
        target["previous_markdown"] = ""
        target["previous_digest"] = ""
        target["verification_status"] = ""
        target["verification_checked_at"] = ""
        target["verification_summary"] = ""
        target["verification_issues"] = []
    target.update(
        {
            "title": str(quality_record.get("title") or snapshot.get("title") or slug),
            "priority": str(quality_record.get("priority") or "medium"),
            "score": int(quality_record.get("score") or 0),
            "quality_score": int(quality_record.get("quality_score") or 0),
            "quality_band": str(quality_record.get("quality_band") or ""),
            "issues": list(quality_record.get("issues") or []),
            "rewrite_strategy": str(quality_record.get("rewrite_strategy") or ""),
            "target_path": str(quality_record.get("path") or snapshot.get("path") or f"wiki/concepts/{slug}.md"),
            "proposal_path": relative_path(root, concept_rewrite_proposal_page_path(root, slug)),
            "source_signature": str(quality_record.get("source_signature") or snapshot.get("source_signature") or ""),
            "source_pages": list(quality_record.get("source_pages") or snapshot.get("source_pages") or []),
            "active": True,
            "last_proposed_at": generated_at,
            "occurrences": int(target.get("occurrences") or 0) + 1,
            "candidate_markdown": candidate_markdown.strip() + "\n",
            "candidate_digest": digest,
            "current_summary": str(snapshot.get("summary") or ""),
        }
    )
    target["pending_review"] = "true" if rewrite_proposal_needs_review(str(target.get("status") or "proposed")) else "false"
    target["apply_ready"] = rewrite_proposal_is_apply_ready(root, target)
    save_concept_rewrite_state(root, {"version": 1, "proposals": proposals})
    write_if_changed(root / str(target["proposal_path"]), _memory_surfaces.render_concept_rewrite_proposal_page(target))
    return {
        "slug": slug,
        "proposal_path": str(target["proposal_path"]),
        "status": str(target.get("status") or "proposed"),
        "candidate_digest": digest,
    }


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
