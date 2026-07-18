"""Lifecycle, governance, and curated-page helpers extracted from app_content.

OWNER STATUS: legacy owner. New large logic blocks should be extracted to a
dedicated subpackage (e.g. `aiwiki.lifecycle.*`) rather than added here.
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

from .app_protocol import (
    AUTO_PROMOTION_FORMATS,
    CONFLICT_SIGNAL_PAIRS,
    CURATED_ASSET_SECTION_ORDER,
    DECISION_QUERY_MARKERS,
    EVIDENCE_GAP_MARKERS,
    EXECUTION_BAND_LABELS,
    JUDGMENT_QUERY_MARKERS,
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    PROTOCOL_CLASSIFICATION_MARKERS,
    PROTOCOL_LIBRARY,
    PROTOCOL_PROMOTION_PREFIXES,
    action_focus_score,
    ensure_layout,
    load_protocol_state,
    page_focus_score,
    protocol_execution_policy_rule,
    protocol_title,
    save_manifest,
    schedule_review_windows,
)
from .app_state_paths import (
    execution_policy_log_path,
    execution_receipt_history_path,
    manual_link_state_path,
    material_archive_action_id,
    material_archive_state_path,
    material_state_path,
)
from .app_types import JudgmentAsset
from .compile.build import load_concept_build_state, load_domain_pilot_build_state, load_output_pack_build_state
from .compile.state import default_compile_state
from .config import LLMConfig
from .content.archive import load_material_routing_state
from .content.concepts import build_concept_quality
from .content.io import (
    curated_asset_section_snapshot,
    entry_ids_from_paths,
    entry_lookup_maps,
    preserved_section,
    review_history_entries,
    source_summary_or_preview,
)
from .content.material import load_active_corpora_state, load_manual_link_state
from .content.rewrite import load_concept_rewrite_state
from .execution.history import load_runtime_history
from .lifecycle.aging import collect_aging_signals, evaluate_page_aging
from .lifecycle.knowledge import (
    active_knowledge_lifecycle_overrides,
    default_knowledge_lifecycle_state,
    display_judgment_lifecycle_state,
    display_knowledge_lifecycle_state,
    display_protocol_relevance_ambiguity,
    display_protocol_relevance_mode,
    ensure_knowledge_lifecycle_override_state,
    knowledge_lifecycle_counts,
    load_knowledge_lifecycle_state,
    render_knowledge_lifecycle_entry_summary,
    save_knowledge_lifecycle_override_state,
    save_knowledge_lifecycle_state,
    select_knowledge_lifecycle_entries,
    sort_knowledge_lifecycle_entries,
)
from .lifecycle.protocol import (
    concept_lifecycle_matches_protocol,
    concept_protocol_ambiguity_state,
    concept_protocol_relevance,
    concept_protocol_relevance_for_source,
    protocol_related_concept_lifecycle_summary,
)
from .lifecycle.status import (
    action_needs_review,
    action_transition_profile,
    archive_transition_profile,
    curated_page_transition_profile,
    default_curated_status,
    display_action_status,
    display_curated_status,
    display_rewrite_proposal_status,
    page_needs_review,
    rewrite_proposal_needs_review,
    rewrite_proposal_status_rank,
    rewrite_transition_profile,
    transition_profile,
    valid_curated_statuses,
)
from .lifecycle.templates import curated_page_template
from .memory.action_state import load_machine_memory_action_state
from .memory.state import load_machine_memory
from .state.constants import DEFAULT_PROTOCOL, KNOWLEDGE_LIFECYCLE_STATES
from .state.io import load_json_document
from .state.manifest import load_manifest
from .utils.hash import compiled_source_sha, sha256_bytes, sha256_file
from .utils.io import runtime_write_operation
from .utils.markdown import (
    analyze_citation_snapshots,
    build_citation_snapshots,
    extract_provenance_paths,
    first_markdown_heading,
    parse_frontmatter,
    raw_note_metadata,
    render_frontmatter,
    replace_first_markdown_heading,
    strip_frontmatter,
    upsert_markdown_section,
)
from .utils.path import next_identifier, normalize_workspace_path, relative_path
from .utils.text import STOP_WORDS, detect_kind, slugify, tokenize
from .utils.time import utc_now


def sort_curated_pages(pages: list[dict[str, str]]) -> list[dict[str, str]]:
    def sort_key(page: dict[str, str]) -> tuple[str, str]:
        return (page.get("reviewed_at", "") or page.get("updated_at", ""), page["title"].lower())

    return sorted(pages, key=sort_key, reverse=True)


def frontmatter_string_list(frontmatter: dict[str, Any], key: str) -> list[str]:
    value = frontmatter.get(key, [])
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]


def judgment_asset_frontmatter(
    *,
    frontmatter: dict[str, Any],
    page_id: str,
    title: str,
    path: str,
    kind: str,
    status: str,
    protocol: str,
    citations: list[str],
    revisit_after: str,
    escalate_after: str,
) -> JudgmentAsset:
    return {
        "page_id": page_id,
        "title": title,
        "path": path,
        "kind": kind,
        "status": status,
        "protocol": protocol,
        "citations": citations,
        "confidence": str(frontmatter.get("confidence") or ""),
        "counter_evidence": frontmatter_string_list(frontmatter, "counter_evidence"),
        "invalidation_rule": str(frontmatter.get("invalidation_rule") or "").strip(),
        "next_signals": frontmatter_string_list(frontmatter, "next_signals"),
        "revisit_after": revisit_after,
        "escalate_after": escalate_after,
        "formed_at": str(frontmatter.get("formed_at") or frontmatter.get("last_compiled_at") or ""),
        "last_reviewed": str(frontmatter.get("last_reviewed") or frontmatter.get("reviewed_at") or ""),
    }


def collect_curated_pages(root: Path, folder: str, expected_kind: str) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    now = datetime.now(timezone.utc)
    for path in sorted((root / "wiki" / folder).glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        status = str(frontmatter.get("status") or default_curated_status(expected_kind))
        reviewed_at = str(frontmatter.get("reviewed_at") or "")
        updated_at = str(frontmatter.get("last_compiled_at") or "")
        protocol = str(frontmatter.get("protocol") or DEFAULT_PROTOCOL)
        revisit_after = str(frontmatter.get("revisit_after") or "")
        escalate_after = str(frontmatter.get("escalate_after") or "")
        if not revisit_after and not escalate_after:
            base_timestamp = reviewed_at or updated_at or utc_now()
            revisit_after, escalate_after = schedule_review_windows(
                expected_kind,
                status,
                base_timestamp,
                protocol=protocol,
                root=root,
            )
        asset_snapshots = {
            heading: curated_asset_section_snapshot(
                content,
                heading,
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            )
            for heading in CURATED_ASSET_SECTION_ORDER
        }
        citations = [str(path) for path in frontmatter.get("citations", []) if isinstance(path, str) and path.strip()]
        asset_frontmatter = judgment_asset_frontmatter(
            frontmatter=frontmatter,
            page_id=str(frontmatter.get("id") or path.stem),
            title=str(frontmatter.get("title") or path.stem),
            path=relative_path(root, path),
            kind=str(frontmatter.get("kind") or ""),
            status=status,
            protocol=protocol,
            citations=citations,
            revisit_after=revisit_after,
            escalate_after=escalate_after,
        )
        citation_snapshot_state = analyze_citation_snapshots(root, citations, frontmatter)
        review_entries = review_history_entries(content)
        asset_score = sum(1 for snapshot in asset_snapshots.values() if snapshot.get("meaningful"))
        pages.append(
            {
                "page_id": str(frontmatter.get("id") or path.stem),
                "title": str(frontmatter.get("title") or path.stem),
                "path": relative_path(root, path),
                "kind": str(frontmatter.get("kind") or ""),
                "status": status,
                "protocol": protocol,
                "confidence": str(frontmatter.get("confidence") or ""),
                "reviewed_at": reviewed_at,
                "updated_at": updated_at,
                "revisit_after": revisit_after,
                "escalate_after": escalate_after,
                "matches_expected_kind": str(frontmatter.get("kind") or "") == expected_kind,
                "pending_review": "true" if page_needs_review(expected_kind, status) else "false",
                "asset_score": str(asset_score),
                "has_counter_evidence": "true" if asset_snapshots["Counter Evidence"]["meaningful"] else "false",
                "has_invalidation": "true" if asset_snapshots["Invalidation"]["meaningful"] else "false",
                "has_next_signals": "true" if asset_snapshots["Next Signals"]["meaningful"] else "false",
                "has_review_history": "true" if asset_snapshots["Review History"]["meaningful"] else "false",
                "review_history_entries": str(asset_snapshots["Review History"]["review_history_entries"]),
                "latest_review_history_entry": review_entries[0] if review_entries else "",
                "citation_count": str(len(citations)),
                "citation_snapshot_count": str(len(citation_snapshot_state["recorded"])),
                "citation_drift": "true" if citation_snapshot_state["has_drift"] else "false",
                "citation_drift_count": str(len(citation_snapshot_state["drifted"])),
                "citation_snapshot_gap_count": str(
                    len(citation_snapshot_state["missing"]) + len(citation_snapshot_state["stale"])
                ),
                "formed_at": str(asset_frontmatter.get("formed_at") or ""),
                "last_reviewed": str(asset_frontmatter.get("last_reviewed") or ""),
                "counter_evidence_count": str(len(asset_frontmatter.get("counter_evidence", []))),
                "next_signal_count": str(len(asset_frontmatter.get("next_signals", []))),
                "invalidation_rule": str(asset_frontmatter.get("invalidation_rule") or ""),
                "has_counter_evidence_metadata": "true" if "counter_evidence" in frontmatter else "false",
                "has_invalidation_rule_metadata": "true" if "invalidation_rule" in frontmatter else "false",
                "has_next_signals_metadata": "true" if "next_signals" in frontmatter else "false",
                "has_formed_at_metadata": "true" if "formed_at" in frontmatter else "false",
                "has_last_reviewed_metadata": "true" if "last_reviewed" in frontmatter else "false",
                "has_structured_counter_evidence": "true" if asset_frontmatter.get("counter_evidence") else "false",
                "has_structured_invalidation_rule": "true"
                if str(asset_frontmatter.get("invalidation_rule") or "").strip()
                else "false",
                "has_structured_next_signals": "true" if asset_frontmatter.get("next_signals") else "false",
            }
        )
    enriched: list[dict[str, str]] = []
    for page in pages:
        enriched_page = dict(page)
        enriched_page.update(evaluate_page_aging(enriched_page, now=now))
        enriched.append(enriched_page)
    return sort_curated_pages(enriched)


def review_queue(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, list[dict[str, str]]]:
    pending_decisions = sorted(
        [page for page in decisions if page.get("pending_review") == "true"],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            page.get("revisit_after", "") or "9999",
            page["title"].lower(),
        ),
    )
    pending_judgments = sorted(
        [page for page in judgments if page.get("pending_review") == "true"],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            page.get("revisit_after", "") or "9999",
            page["title"].lower(),
        ),
    )
    reviewed = [
        page for page in decisions + judgments if page.get("reviewed_at") and page.get("pending_review") != "true"
    ]
    reviewed = sorted(reviewed, key=lambda page: (page.get("reviewed_at", ""), page["title"].lower()), reverse=True)
    return {
        "pending_decisions": pending_decisions,
        "pending_judgments": pending_judgments,
        "recently_reviewed": reviewed,
    }


def judgment_lifecycle_profile(page: dict[str, Any]) -> tuple[str, list[str]]:
    kind = str(page.get("kind") or "")
    status = str(page.get("status") or "")
    terminal_statuses = {"superseded"} if kind == "decision" else {"rejected"}
    if status in terminal_statuses:
        return "retired", ["terminal-status", status]
    reasons: list[str] = []
    if status in {"tracking", "needs-revisit"}:
        reasons.append("explicit-review-status")
    if str(page.get("overdue_review") or "").lower() == "true" or page.get("overdue_review") is True:
        reasons.append("overdue-review")
    if str(page.get("escalation_candidate") or "").lower() == "true" or page.get("escalation_candidate") is True:
        reasons.append("escalation-candidate")
    if str(page.get("citation_drift") or "").lower() == "true" or page.get("citation_drift") is True:
        reasons.append("citation-drift")
    if int(page.get("citation_snapshot_gap_count", "0") or 0) > 0:
        reasons.append("citation-snapshot-gap")
    if reasons:
        return "under-review", reasons
    if int(page.get("review_history_entries", "0") or 0) > 1:
        return "revised", ["reviewed-multiple-times"]
    if str(page.get("last_reviewed") or page.get("reviewed_at") or "") or status in {"approved", "confirmed"}:
        return "active", ["reviewed-active"]
    return "formed", ["filed-back"]


def knowledge_lifecycle_invalidation_signals(page: dict[str, str]) -> list[str]:
    signals: list[str] = []
    if str(page.get("status") or "") == "needs-revisit":
        signals.append("explicit-needs-revisit")
    if page.get("citation_drift") == "true":
        signals.append("citation-drift")
    if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0:
        signals.append("citation-snapshot-gap")
    if page.get("overdue_review") == "true":
        signals.append("overdue-review")
    if page.get("escalation_candidate") == "true":
        signals.append("escalation-candidate")
    return signals


def knowledge_lifecycle_active_corpus_ids(
    source_ids: list[str],
    active_corpora: list[dict[str, Any]],
    *,
    concept_slug: str = "",
) -> list[str]:
    source_id_set = {source_id for source_id in source_ids if source_id}
    active_ids: list[str] = []
    for corpus in active_corpora:
        if str(corpus.get("status") or "") not in {"active", "cooling"}:
            continue
        corpus_id = str(corpus.get("corpus_id") or "")
        if not corpus_id:
            continue
        if concept_slug:
            concept_slugs = {str(item) for item in corpus.get("concept_slugs", []) if isinstance(item, str)}
            if concept_slug in concept_slugs and corpus_id not in active_ids:
                active_ids.append(corpus_id)
                continue
        if not source_id_set:
            continue
        corpus_source_ids = {
            str(item)
            for item in [*(corpus.get("source_ids", []) or []), *(corpus.get("bridge_evidence_ids", []) or [])]
            if isinstance(item, str)
        }
        if source_id_set & corpus_source_ids:
            active_ids.append(corpus_id)
    return sorted(active_ids)


def knowledge_lifecycle_classification(
    *,
    status: str,
    pending_review: bool,
    invalidation_signals: list[str],
    active_corpus_ids: list[str],
) -> tuple[str, list[str]]:
    if status in {"superseded", "rejected"}:
        return "retired", ["terminal-status"]
    if invalidation_signals:
        return "revisit", ["invalidation-signal", *invalidation_signals]
    if pending_review:
        return "review", ["pending-review-status"]
    if active_corpus_ids and status in {"approved", "confirmed"}:
        return "active", ["active-corpus-linked"]
    return "deferred", ["reviewed-idle"]


def concept_lifecycle_invalidation_signals(quality_record: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    if quality_record.get("conflict_signals"):
        signals.append("concept-conflict")
    if quality_record.get("gap_signals"):
        signals.append("concept-evidence-gap")
    return signals


def concept_lifecycle_review_signals(
    quality_record: dict[str, Any],
    rewrite_proposal: dict[str, Any],
    *,
    active_corpus_ids: list[str],
) -> list[str]:
    signals: list[str] = []
    proposal_status = str(rewrite_proposal.get("status") or "")
    if rewrite_proposal.get("active") and rewrite_proposal.get("pending_review") == "true":
        if proposal_status == "accepted":
            signals.append("rewrite-proposal-accepted")
        elif proposal_status == "deferred":
            signals.append("rewrite-proposal-deferred")
        else:
            signals.append("rewrite-proposal-proposed")
    if rewrite_proposal.get("apply_ready"):
        signals.append("rewrite-apply-ready")
    if active_corpus_ids and str(quality_record.get("quality_state") or "") != "stable":
        signals.append("active-quality-pressure")
    return signals


def concept_lifecycle_classification(
    *,
    source_ids: list[str],
    active_corpus_ids: list[str],
    invalidation_signals: list[str],
    review_signals: list[str],
) -> tuple[str, list[str]]:
    if not source_ids:
        return "retired", ["no-source-pages"]
    if invalidation_signals:
        return "revisit", ["invalidation-signal", *invalidation_signals]
    if review_signals:
        return "review", ["quality-review", *review_signals]
    if active_corpus_ids:
        return "active", ["active-corpus-linked"]
    return "deferred", ["compiled-idle"]


def build_knowledge_lifecycle_entry(
    root: Path,
    page: dict[str, str],
    *,
    expected_kind: str,
    path_to_entry_id: dict[str, str],
    active_corpora: list[dict[str, Any]],
) -> dict[str, Any]:
    page_path = root / str(page.get("path") or "")
    content = page_path.read_text(encoding="utf-8", errors="replace") if page_path.exists() else ""
    frontmatter = parse_frontmatter(content)
    citations = [str(item) for item in frontmatter.get("citations", []) if isinstance(item, str) and item.strip()]
    if not citations and content:
        citations = extract_provenance_paths(root, content)
    source_ids = entry_ids_from_paths(path_to_entry_id, citations)
    active_corpus_ids = knowledge_lifecycle_active_corpus_ids(source_ids, active_corpora)
    invalidation_signals = knowledge_lifecycle_invalidation_signals(page)
    lifecycle_state, reason_codes = knowledge_lifecycle_classification(
        status=str(page.get("status") or ""),
        pending_review=page.get("pending_review") == "true",
        invalidation_signals=invalidation_signals,
        active_corpus_ids=active_corpus_ids,
    )
    judgment_lifecycle_state, judgment_lifecycle_reason_codes = judgment_lifecycle_profile(page)
    return {
        "page_id": str(frontmatter.get("id") or Path(str(page.get("path") or "")).stem),
        "title": str(page.get("title") or frontmatter.get("title") or Path(str(page.get("path") or "")).stem),
        "path": str(page.get("path") or ""),
        "kind": expected_kind,
        "protocol": str(page.get("protocol") or frontmatter.get("protocol") or DEFAULT_PROTOCOL),
        "status": str(page.get("status") or ""),
        "lifecycle_state": lifecycle_state,
        "reason_codes": reason_codes,
        "reviewed_at": str(page.get("reviewed_at") or ""),
        "revisit_after": str(page.get("revisit_after") or ""),
        "escalate_after": str(page.get("escalate_after") or ""),
        "aging_state": str(page.get("aging_state") or ""),
        "pending_review": page.get("pending_review") == "true",
        "overdue_review": page.get("overdue_review") == "true",
        "escalation_candidate": page.get("escalation_candidate") == "true",
        "source_ids": source_ids,
        "active_corpus_ids": active_corpus_ids,
        "invalidation_signals": invalidation_signals,
        "citation_count": int(page.get("citation_count", "0") or "0"),
        "citation_drift": page.get("citation_drift") == "true",
        "citation_drift_count": int(page.get("citation_drift_count", "0") or "0"),
        "citation_snapshot_gap_count": int(page.get("citation_snapshot_gap_count", "0") or "0"),
        "review_history_entries": int(page.get("review_history_entries", "0") or "0"),
        "asset_score": int(page.get("asset_score", "0") or "0"),
        "confidence": str(page.get("confidence") or ""),
        "formed_at": str(page.get("formed_at") or ""),
        "last_reviewed": str(page.get("last_reviewed") or page.get("reviewed_at") or ""),
        "counter_evidence_count": int(page.get("counter_evidence_count", "0") or "0"),
        "next_signal_count": int(page.get("next_signal_count", "0") or "0"),
        "invalidation_rule": str(page.get("invalidation_rule") or ""),
        "judgment_lifecycle_state": judgment_lifecycle_state,
        "judgment_lifecycle_reason_codes": judgment_lifecycle_reason_codes,
    }


def build_concept_lifecycle_entry(
    root: Path,
    path: Path,
    *,
    path_to_entry_id: dict[str, str],
    active_corpora: list[dict[str, Any]],
    quality_record: dict[str, Any],
    rewrite_proposal: dict[str, Any],
) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    slug = path.stem
    source_pages = [str(item) for item in frontmatter.get("source_pages", []) if isinstance(item, str) and item.strip()]
    source_ids = entry_ids_from_paths(path_to_entry_id, source_pages)
    active_corpus_ids = knowledge_lifecycle_active_corpus_ids(
        source_ids,
        active_corpora,
        concept_slug=slug,
    )
    invalidation_signals = concept_lifecycle_invalidation_signals(quality_record)
    review_signals = concept_lifecycle_review_signals(
        quality_record,
        rewrite_proposal,
        active_corpus_ids=active_corpus_ids,
    )
    lifecycle_state, reason_codes = concept_lifecycle_classification(
        source_ids=source_ids,
        active_corpus_ids=active_corpus_ids,
        invalidation_signals=invalidation_signals,
        review_signals=review_signals,
    )
    return {
        "page_id": str(frontmatter.get("id") or f"concept-{slug}"),
        "title": str(frontmatter.get("title") or path.stem),
        "path": relative_path(root, path),
        "kind": "concept",
        "protocol": "",
        "status": str(frontmatter.get("status") or "compiled"),
        "lifecycle_state": lifecycle_state,
        "reason_codes": reason_codes,
        "reviewed_at": "",
        "revisit_after": "",
        "escalate_after": "",
        "aging_state": "",
        "pending_review": bool(review_signals),
        "overdue_review": False,
        "escalation_candidate": False,
        "source_ids": source_ids,
        "active_corpus_ids": active_corpus_ids,
        "invalidation_signals": invalidation_signals,
        "citation_count": 0,
        "citation_drift": False,
        "citation_drift_count": 0,
        "citation_snapshot_gap_count": 0,
        "review_history_entries": 0,
        "asset_score": 0,
        "confidence": str(frontmatter.get("confidence") or ""),
        "source_pages": source_pages,
        "source_signature": str(frontmatter.get("source_signature") or ""),
        "quality_state": str(quality_record.get("quality_state") or "stable"),
        "issues": list(quality_record.get("issues") or []),
        "rewrite_priority": str(quality_record.get("rewrite_priority") or "low"),
        "rewrite_strategy": str(quality_record.get("rewrite_strategy") or ""),
        "review_signal_codes": review_signals,
        "rewrite_proposal_status": str(rewrite_proposal.get("status") or ""),
        "rewrite_pending_review": rewrite_proposal.get("pending_review") == "true",
        "rewrite_apply_ready": bool(rewrite_proposal.get("apply_ready")),
        "source_count": int(quality_record.get("source_count") or len(source_pages)),
        "related_count": int(quality_record.get("related_count") or 0),
        "override_active": False,
        "override_state": "",
        "override_reason_codes": [],
        "override_note": "",
        "override_updated_at": "",
        "override_source": "",
    }


def apply_knowledge_lifecycle_override(
    entry: dict[str, Any],
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = dict(entry)
    if not override or not bool(override.get("active")):
        return normalized
    override_state = str(override.get("lifecycle_state") or "")
    if override_state not in KNOWLEDGE_LIFECYCLE_STATES:
        return normalized
    override_reason_codes = [
        str(reason) for reason in override.get("reason_codes", []) if isinstance(reason, str) and reason.strip()
    ]
    normalized["derived_lifecycle_state"] = str(entry.get("lifecycle_state") or "")
    normalized["derived_reason_codes"] = list(entry.get("reason_codes") or [])
    normalized["override_active"] = True
    normalized["override_state"] = override_state
    normalized["override_reason_codes"] = override_reason_codes
    normalized["override_note"] = str(override.get("note") or "")
    normalized["override_updated_at"] = str(override.get("updated_at") or override.get("applied_at") or "")
    normalized["override_source"] = str(override.get("operation") or "manual-runtime")
    normalized["lifecycle_state"] = override_state
    normalized["reason_codes"] = ["manual-override", *(override_reason_codes or [f"manual-{override_state}"])]
    if override_state == "retired":
        normalized["pending_review"] = False
        normalized["overdue_review"] = False
        normalized["escalation_candidate"] = False
    return normalized


def clear_stale_knowledge_lifecycle_overrides(
    root: Path,
    override_state: dict[str, Any],
    *,
    cleared_at: str,
) -> dict[str, Any]:
    current_concept_paths = {relative_path(root, path) for path in sorted((root / "wiki" / "concepts").glob("*.md"))}
    entries: list[dict[str, Any]] = []
    changed = False
    for raw_entry in override_state.get("entries", []):
        if not isinstance(raw_entry, dict):
            continue
        entry = dict(raw_entry)
        path = str(entry.get("path") or "")
        if (
            bool(entry.get("active"))
            and str(entry.get("kind") or "") == "concept"
            and path.startswith("wiki/concepts/")
            and path not in current_concept_paths
        ):
            entry["active"] = False
            entry["cleared_at"] = cleared_at
            entry["cleared_note"] = "Target concept page no longer exists; cleared by lifecycle refresh."
            entry["cleared_reason_codes"] = ["missing-target"]
            entry["updated_at"] = cleared_at
            changed = True
        entries.append(entry)
    if not changed:
        return override_state
    cleaned_state = {
        "version": int(override_state.get("version", 1) or 1),
        "entries": entries,
    }
    save_knowledge_lifecycle_override_state(root, cleaned_state)
    return cleaned_state


def knowledge_lifecycle_governance_summary(
    knowledge_lifecycle: dict[str, Any] | None,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    concept_backlog = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"review", "revisit"},
        ),
        active_protocol=active_protocol,
    )
    review_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "review"]
    revisit_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "revisit"]
    retired_concepts = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"retired"},
        ),
        active_protocol=active_protocol,
    )
    concept_counts = knowledge_lifecycle.get("counts", {}).get("by_kind", {}).get("concept", {}).get("by_state", {})
    curated_entries = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"decision", "judgment"},
        ),
        active_protocol=active_protocol,
    )
    formed_judgments = [
        entry for entry in curated_entries if str(entry.get("judgment_lifecycle_state") or "") == "formed"
    ]
    active_judgments = [
        entry for entry in curated_entries if str(entry.get("judgment_lifecycle_state") or "") == "active"
    ]
    under_review_judgments = [
        entry for entry in curated_entries if str(entry.get("judgment_lifecycle_state") or "") == "under-review"
    ]
    revised_judgments = [
        entry for entry in curated_entries if str(entry.get("judgment_lifecycle_state") or "") == "revised"
    ]
    retired_judgments = [
        entry for entry in curated_entries if str(entry.get("judgment_lifecycle_state") or "") == "retired"
    ]
    return {
        "concept_backlog": concept_backlog,
        "review_concepts": review_concepts,
        "revisit_concepts": revisit_concepts,
        "retired_concepts": retired_concepts,
        "formed_judgments": formed_judgments,
        "active_judgments": active_judgments,
        "under_review_judgments": under_review_judgments,
        "revised_judgments": revised_judgments,
        "retired_judgments": retired_judgments,
        "counts": {
            "concept_backlog": len(concept_backlog),
            "review_concepts": len(review_concepts),
            "revisit_concepts": len(revisit_concepts),
            "retired_concepts": len(retired_concepts),
            "active_concepts": int(concept_counts.get("active", 0) or 0),
            "deferred_concepts": int(concept_counts.get("deferred", 0) or 0),
            "formed_judgments": len(formed_judgments),
            "active_judgments": len(active_judgments),
            "under_review_judgments": len(under_review_judgments),
            "revised_judgments": len(revised_judgments),
            "retired_judgments": len(retired_judgments),
        },
    }


def refresh_knowledge_lifecycle_state(
    root: Path,
    *,
    generated_at: str,
    decisions: list[dict[str, str]] | None = None,
    judgments: list[dict[str, str]] | None = None,
    entries: list[dict[str, Any]] | None = None,
    active_corpora_state: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document = build_knowledge_lifecycle_document(
        root,
        generated_at=generated_at,
        decisions=decisions,
        judgments=judgments,
        entries=entries,
        active_corpora_state=active_corpora_state,
        memory=memory,
    )
    save_knowledge_lifecycle_state(root, document)
    return document


def build_knowledge_lifecycle_document(
    root: Path,
    *,
    generated_at: str,
    decisions: list[dict[str, str]] | None = None,
    judgments: list[dict[str, str]] | None = None,
    entries: list[dict[str, Any]] | None = None,
    active_corpora_state: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    override_state = ensure_knowledge_lifecycle_override_state(root)
    override_state = clear_stale_knowledge_lifecycle_overrides(
        root,
        override_state,
        cleared_at=generated_at,
    )
    active_overrides = active_knowledge_lifecycle_overrides(override_state)
    manifest_entries = entries if entries is not None else load_manifest(root).get("entries", [])
    _entry_by_id, path_to_entry_id = entry_lookup_maps(manifest_entries)
    decision_pages = decisions if decisions is not None else collect_curated_pages(root, "decisions", "decision")
    judgment_pages = judgments if judgments is not None else collect_curated_pages(root, "judgments", "judgment")
    concept_memory = memory if memory is not None else load_machine_memory(root)
    concept_quality = (
        build_concept_quality(root, concept_memory)
        if concept_memory
        else {
            "weak_concepts": [],
            "stable_concepts": [],
        }
    )
    concept_quality_by_slug = {
        str(record.get("slug") or ""): dict(record)
        for record in (concept_quality.get("all_concepts", []) or [])
        if isinstance(record, dict) and record.get("slug")
    }
    concept_rewrite_by_slug = {
        str(proposal.get("slug") or ""): dict(proposal)
        for proposal in load_concept_rewrite_state(root).get("proposals", [])
        if isinstance(proposal, dict) and proposal.get("slug")
    }
    active_corpora = [
        dict(corpus)
        for corpus in (active_corpora_state or load_active_corpora_state(root)).get("corpora", [])
        if isinstance(corpus, dict)
    ]
    lifecycle_entries = [
        *[
            build_knowledge_lifecycle_entry(
                root,
                page,
                expected_kind="decision",
                path_to_entry_id=path_to_entry_id,
                active_corpora=active_corpora,
            )
            for page in decision_pages
        ],
        *[
            build_knowledge_lifecycle_entry(
                root,
                page,
                expected_kind="judgment",
                path_to_entry_id=path_to_entry_id,
                active_corpora=active_corpora,
            )
            for page in judgment_pages
        ],
        *[
            build_concept_lifecycle_entry(
                root,
                path,
                path_to_entry_id=path_to_entry_id,
                active_corpora=active_corpora,
                quality_record=concept_quality_by_slug.get(
                    path.stem,
                    {
                        "slug": path.stem,
                        "quality_state": "stable",
                        "issues": [],
                        "rewrite_priority": "low",
                        "rewrite_strategy": "",
                        "source_count": 0,
                        "related_count": 0,
                    },
                ),
                rewrite_proposal=concept_rewrite_by_slug.get(path.stem, {}),
            )
            for path in sorted((root / "wiki" / "concepts").glob("*.md"))
        ],
    ]
    lifecycle_entries = [
        apply_knowledge_lifecycle_override(entry, active_overrides.get(str(entry.get("path") or "")))
        if str(entry.get("kind") or "") == "concept"
        else entry
        for entry in lifecycle_entries
    ]
    document = {
        "version": 1,
        "generated_at": generated_at,
        "entries": lifecycle_entries,
        "counts": knowledge_lifecycle_counts(lifecycle_entries),
    }
    return document
