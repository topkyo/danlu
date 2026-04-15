"""Output-pack, dashboard-index, and pack/path helpers extracted from app_content."""

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
    action_supports_low_risk_apply,
    curated_asset_section_snapshot,
    execution_band_label,
    preserved_section,
    review_history_entries,
)
from .app_lifecycle import (
    collect_aging_signals,
    display_action_status,
    display_curated_status,
    display_judgment_lifecycle_state,
    display_knowledge_lifecycle_state,
    frontmatter_string_list,
    judgment_lifecycle_profile,
    knowledge_lifecycle_governance_summary,
    protocol_related_concept_lifecycle_summary,
    render_knowledge_lifecycle_entry_summary,
    review_queue,
    select_knowledge_lifecycle_entries,
    sort_curated_pages,
    sort_knowledge_lifecycle_entries,
)
from .app_protocol import (
    AUTO_PROMOTION_FORMATS,
    CONFLICT_SIGNAL_PAIRS,
    CURATED_ASSET_SECTION_ORDER,
    DECISION_QUERY_MARKERS,
    DECISION_STATUSES,
    EVIDENCE_GAP_MARKERS,
    EXECUTION_BAND_LABELS,
    JUDGMENT_QUERY_MARKERS,
    JUDGMENT_STATUSES,
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    PENDING_ACTION_STATUSES,
    PENDING_DECISION_REVIEW_STATUSES,
    PENDING_JUDGMENT_REVIEW_STATUSES,
    PENDING_REWRITE_PROPOSAL_STATUSES,
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
from .app_state import (
    DEFAULT_PROTOCOL,
    JUDGMENT_LIFECYCLE_STATES,
    KNOWLEDGE_LIFECYCLE_KINDS,
    KNOWLEDGE_LIFECYCLE_STATES,
    active_knowledge_lifecycle_overrides,
    default_compile_state,
    default_knowledge_lifecycle_state,
    default_material_routing_state,
    ensure_knowledge_lifecycle_override_state,
    execution_policy_log_path,
    execution_receipt_history_path,
    load_active_corpora_state,
    load_concept_build_state,
    load_concept_rewrite_state,
    load_domain_pilot_build_state,
    load_json_document,
    load_knowledge_lifecycle_state,
    load_machine_memory,
    load_machine_memory_action_state,
    load_manifest,
    load_manual_link_state,
    load_material_routing_state,
    load_output_pack_build_state,
    load_runtime_history,
    manual_link_state_path,
    material_archive_action_id,
    material_archive_state_path,
    material_state_path,
    save_knowledge_lifecycle_state,
)
from .app_types import JudgmentAsset
from .app_utils import (
    STOP_WORDS,
    analyze_citation_snapshots,
    build_citation_snapshots,
    compiled_source_sha,
    detect_kind,
    extract_provenance_paths,
    first_markdown_heading,
    next_identifier,
    normalize_workspace_path,
    parse_frontmatter,
    parse_iso_datetime,
    raw_note_metadata,
    relative_path,
    render_frontmatter,
    replace_first_markdown_heading,
    runtime_write_operation,
    sha256_bytes,
    sha256_file,
    slugify,
    strip_frontmatter,
    tokenize,
    upsert_markdown_section,
    utc_now,
)
from .config import LLMConfig


def render_curated_page_summary(page: dict[str, str]) -> str:
    suffix_parts = [f"状态 `{display_curated_status(page.get('status', '') or 'unknown')}`"]
    protocol = page.get("protocol", "")
    if protocol:
        suffix_parts.append(f"协议 `{protocol}`")
    confidence = page.get("confidence", "")
    if confidence:
        suffix_parts.append(f"置信度 `{confidence}`")
    reviewed_at = page.get("reviewed_at", "")
    if reviewed_at:
        suffix_parts.append(f"审阅时间 `{reviewed_at}`")
    revisit_after = page.get("revisit_after", "")
    if revisit_after:
        suffix_parts.append(f"复审截止 `{revisit_after}`")
    if page.get("asset_score"):
        suffix_parts.append(f"资产 `{page.get('asset_score')}/4`")
    review_history_entries = int(page.get("review_history_entries", "0") or "0")
    if review_history_entries:
        suffix_parts.append(f"复审历史 `{review_history_entries}`")
    citation_drift_count = int(page.get("citation_drift_count", "0") or "0")
    citation_snapshot_gap_count = int(page.get("citation_snapshot_gap_count", "0") or "0")
    if page.get("citation_drift") == "true":
        suffix_parts.append(f"证据漂移 `{citation_drift_count or 1}`")
    if citation_snapshot_gap_count:
        suffix_parts.append(f"快照缺口 `{citation_snapshot_gap_count}`")
    if page.get("overdue_review") == "true":
        suffix_parts.append("已到期待复审")
    if page.get("escalation_candidate") == "true":
        suffix_parts.append("需要升级处理")
    return f"- [{page['title']}](../../{page['path']}) | " + " | ".join(suffix_parts)


def judgment_asset_gap_codes(page: dict[str, str]) -> list[str]:
    if str(page.get("kind") or "") not in {"decision", "judgment"}:
        return []
    reasons: list[str] = []
    if page.get("has_counter_evidence") != "true":
        reasons.append("missing-counter-evidence")
    if page.get("has_invalidation") != "true":
        reasons.append("missing-invalidation")
    if page.get("has_next_signals") != "true":
        reasons.append("missing-next-signals")
    if page.get("has_review_history") != "true":
        reasons.append("missing-review-history")
    if page.get("citation_drift") == "true":
        reasons.append("citation-drift")
    if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0:
        reasons.append("citation-snapshot-gap")
    if page.get("has_counter_evidence_metadata") != "true":
        reasons.append("missing-counter-evidence-metadata")
    if page.get("has_invalidation_rule_metadata") != "true":
        reasons.append("missing-invalidation-rule-metadata")
    if page.get("has_next_signals_metadata") != "true":
        reasons.append("missing-next-signals-metadata")
    if page.get("has_formed_at_metadata") != "true":
        reasons.append("missing-formed-at-metadata")
    if page.get("has_last_reviewed_metadata") != "true":
        reasons.append("missing-last-reviewed-metadata")
    return reasons


def judgment_asset_shell_record(
    page: dict[str, str],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    asset_gaps = judgment_asset_gap_codes(page)
    judgment_lifecycle_state, judgment_lifecycle_reason_codes = judgment_lifecycle_profile(page)
    attention_reasons: list[str] = []
    if page.get("escalation_candidate") == "true":
        attention_reasons.append("escalation-candidate")
    if page.get("overdue_review") == "true":
        attention_reasons.append("overdue-review")
    if page.get("pending_review") == "true":
        attention_reasons.append("pending-review")
    if page.get("aging_state") == "scheduled":
        attention_reasons.append("scheduled-review")
    for reason_code in asset_gaps:
        if reason_code not in attention_reasons:
            attention_reasons.append(reason_code)
    return {
        "page_id": str(page.get("page_id") or ""),
        "title": str(page.get("title") or page.get("path") or ""),
        "path": str(page.get("path") or ""),
        "kind": str(page.get("kind") or ""),
        "status": str(page.get("status") or ""),
        "current_status": str(page.get("status") or ""),
        "protocol": str(page.get("protocol") or ""),
        "confidence": str(page.get("confidence") or ""),
        "formed_at": str(page.get("formed_at") or ""),
        "last_reviewed": str(page.get("last_reviewed") or page.get("reviewed_at") or ""),
        "reviewed_at": str(page.get("reviewed_at") or ""),
        "updated_at": str(page.get("updated_at") or ""),
        "revisit_after": str(page.get("revisit_after") or ""),
        "escalate_after": str(page.get("escalate_after") or ""),
        "aging_state": str(page.get("aging_state") or ""),
        "pending_review": str(page.get("pending_review") or "") == "true",
        "overdue_review": str(page.get("overdue_review") or "") == "true",
        "escalation_candidate": str(page.get("escalation_candidate") or "") == "true",
        "focus_score": page_focus_score(active_protocol, page),
        "asset_score": int(page.get("asset_score", "0") or "0"),
        "has_counter_evidence": str(page.get("has_counter_evidence") or "") == "true",
        "has_invalidation": str(page.get("has_invalidation") or "") == "true",
        "has_next_signals": str(page.get("has_next_signals") or "") == "true",
        "has_review_history": str(page.get("has_review_history") or "") == "true",
        "has_counter_evidence_metadata": str(page.get("has_counter_evidence_metadata") or "") == "true",
        "has_invalidation_rule_metadata": str(page.get("has_invalidation_rule_metadata") or "") == "true",
        "has_next_signals_metadata": str(page.get("has_next_signals_metadata") or "") == "true",
        "has_formed_at_metadata": str(page.get("has_formed_at_metadata") or "") == "true",
        "has_last_reviewed_metadata": str(page.get("has_last_reviewed_metadata") or "") == "true",
        "has_structured_counter_evidence": str(page.get("has_structured_counter_evidence") or "") == "true",
        "has_structured_invalidation_rule": str(page.get("has_structured_invalidation_rule") or "") == "true",
        "has_structured_next_signals": str(page.get("has_structured_next_signals") or "") == "true",
        "counter_evidence_count": int(page.get("counter_evidence_count", "0") or "0"),
        "next_signal_count": int(page.get("next_signal_count", "0") or "0"),
        "invalidation_rule": str(page.get("invalidation_rule") or ""),
        "review_history_entries": int(page.get("review_history_entries", "0") or "0"),
        "latest_review_history_entry": str(page.get("latest_review_history_entry") or ""),
        "citation_drift": str(page.get("citation_drift") or "") == "true",
        "citation_drift_count": int(page.get("citation_drift_count", "0") or "0"),
        "citation_snapshot_gap_count": int(page.get("citation_snapshot_gap_count", "0") or "0"),
        "judgment_lifecycle_state": judgment_lifecycle_state,
        "judgment_lifecycle_reason_codes": judgment_lifecycle_reason_codes,
        "asset_gaps": asset_gaps,
        "attention_reasons": attention_reasons,
    }


def judgment_asset_attention_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        0 if record.get("escalation_candidate") else 1,
        0 if record.get("overdue_review") else 1,
        0 if record.get("pending_review") else 1,
        0 if record.get("citation_drift") else 1,
        0 if int(record.get("citation_snapshot_gap_count", 0) or 0) > 0 else 1,
        -len(record.get("asset_gaps", [])),
        int(record.get("asset_score", 0) or 0),
        -int(record.get("focus_score", 0) or 0),
        str(record.get("revisit_after") or record.get("escalate_after") or "9999"),
        str(record.get("title") or "").lower(),
    )


def judgment_asset_summary(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    pages = sorted(
        decisions + judgments,
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            -(int(page.get("asset_score", "0") or "0")),
            page.get("title", "").lower(),
        ),
    )
    strong_assets = [page for page in pages if int(page.get("asset_score", "0") or "0") >= 3]
    missing_counter = [page for page in pages if page.get("has_counter_evidence") != "true"]
    missing_invalidation = [page for page in pages if page.get("has_invalidation") != "true"]
    missing_next_signals = [page for page in pages if page.get("has_next_signals") != "true"]
    missing_history = [page for page in pages if page.get("has_review_history") != "true"]
    drifted = [page for page in pages if page.get("citation_drift") == "true"]
    snapshot_gaps = [page for page in pages if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0]
    missing_counter_metadata = [page for page in pages if page.get("has_counter_evidence_metadata") != "true"]
    missing_invalidation_metadata = [page for page in pages if page.get("has_invalidation_rule_metadata") != "true"]
    missing_next_signal_metadata = [page for page in pages if page.get("has_next_signals_metadata") != "true"]
    missing_formed_at_metadata = [page for page in pages if page.get("has_formed_at_metadata") != "true"]
    missing_last_reviewed_metadata = [page for page in pages if page.get("has_last_reviewed_metadata") != "true"]
    shell_records = {
        str(page.get("path") or ""): judgment_asset_shell_record(page, active_protocol=active_protocol)
        for page in pages
        if str(page.get("path") or "")
    }
    attention_pages = [
        page
        for page in pages
        if shell_records.get(str(page.get("path") or ""), {}).get("attention_reasons")
    ]
    attention_records = [
        shell_records[str(page.get("path") or "")]
        for page in attention_pages
        if str(page.get("path") or "") in shell_records
    ]
    attention_records.sort(key=judgment_asset_attention_sort_key)
    strong_records = [
        shell_records[str(page.get("path") or "")]
        for page in strong_assets
        if str(page.get("path") or "") in shell_records
    ]
    lifecycle_counts = {state: 0 for state in JUDGMENT_LIFECYCLE_STATES}
    for record in shell_records.values():
        lifecycle_state = str(record.get("judgment_lifecycle_state") or "")
        if lifecycle_state in lifecycle_counts:
            lifecycle_counts[lifecycle_state] += 1
    return {
        "counts": {
            "pages": len(pages),
            "decisions": len(decisions),
            "judgments": len(judgments),
            "strong_assets": len(strong_assets),
            "attention_pages": len(attention_pages),
            "missing_counter_evidence": len(missing_counter),
            "missing_invalidation": len(missing_invalidation),
            "missing_next_signals": len(missing_next_signals),
            "missing_review_history": len(missing_history),
            "missing_counter_evidence_metadata": len(missing_counter_metadata),
            "missing_invalidation_rule_metadata": len(missing_invalidation_metadata),
            "missing_next_signals_metadata": len(missing_next_signal_metadata),
            "missing_formed_at_metadata": len(missing_formed_at_metadata),
            "missing_last_reviewed_metadata": len(missing_last_reviewed_metadata),
            "citation_drift": len(drifted),
            "citation_snapshot_gaps": len(snapshot_gaps),
            "pending_review": sum(1 for page in pages if page.get("pending_review") == "true"),
            "overdue_review": sum(1 for page in pages if page.get("overdue_review") == "true"),
            "scheduled_review": sum(1 for page in pages if page.get("aging_state") == "scheduled"),
            "escalation_candidates": sum(1 for page in pages if page.get("escalation_candidate") == "true"),
            "formed_lifecycle": lifecycle_counts["formed"],
            "active_lifecycle": lifecycle_counts["active"],
            "under_review_lifecycle": lifecycle_counts["under-review"],
            "revised_lifecycle": lifecycle_counts["revised"],
            "retired_lifecycle": lifecycle_counts["retired"],
        },
        "lists": {
            "pages": pages,
            "attention_pages": attention_pages,
            "strong_assets": strong_assets,
            "missing_counter_evidence": missing_counter,
            "missing_invalidation": missing_invalidation,
            "missing_next_signals": missing_next_signals,
            "missing_review_history": missing_history,
            "missing_counter_evidence_metadata": missing_counter_metadata,
            "missing_invalidation_rule_metadata": missing_invalidation_metadata,
            "missing_next_signals_metadata": missing_next_signal_metadata,
            "missing_formed_at_metadata": missing_formed_at_metadata,
            "missing_last_reviewed_metadata": missing_last_reviewed_metadata,
            "citation_drift": drifted,
            "citation_snapshot_gaps": snapshot_gaps,
            "escalation_candidates": [page for page in pages if page.get("escalation_candidate") == "true"],
        },
        "attention_pages": attention_records,
        "decision_focus": [record for record in attention_records if record.get("kind") == "decision"],
        "judgment_focus": [record for record in attention_records if record.get("kind") == "judgment"],
        "strong_assets": strong_records,
    }


def render_curated_index(
    heading: str,
    section_name: str,
    pages: list[dict[str, str]],
    compiled_at: str,
) -> str:
    pending_review = sum(1 for page in pages if page.get("pending_review") == "true")
    overdue_review = sum(1 for page in pages if page.get("overdue_review") == "true")
    escalated = sum(1 for page in pages if page.get("escalation_candidate") == "true")
    drifted = [page for page in pages if page.get("citation_drift") == "true"]
    snapshot_gaps = [page for page in pages if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0]
    status_counts: dict[str, int] = {}
    for page in pages:
        status = page.get("status", "") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    lines = [
        f"# {heading}",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 页面总数：`{len(pages)}`",
        f"- 待审阅数量：`{pending_review}`",
        f"- 已到期数量：`{overdue_review}`",
        f"- 需要升级：`{escalated}`",
        f"- 证据漂移：`{len(drifted)}`",
        f"- 快照缺口：`{len(snapshot_gaps)}`",
        "",
        "## 状态统计",
    ]
    if not status_counts:
        lines.append("- 还没有相关页面。")
    else:
        for status, count in sorted(status_counts.items()):
            lines.append(f"- `{display_curated_status(status)}`：`{count}`")
    lines.extend(
        [
            "",
        f"## {section_name}",
        ]
    )
    if not pages:
        lines.append(f"- 还没有{section_name}。")
    else:
        for page in pages:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 证据漂移"])
    if not drifted:
        lines.append("- 当前没有检测到 citation drift。")
    else:
        for page in drifted[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## Snapshot 缺口"])
    if not snapshot_gaps:
        lines.append("- 当前没有 citation snapshot 缺口。")
    else:
        for page in snapshot_gaps[:12]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def render_judgment_assets(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> str:
    from .app_surfaces import render_judgment_assets as _render_judgment_assets

    return _render_judgment_assets(
        decisions,
        judgments,
        compiled_at,
        active_protocol=active_protocol,
    )


def render_cognitive_history(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    from .app_surfaces import render_cognitive_history as _render_cognitive_history

    return _render_cognitive_history(
        root,
        decisions,
        judgments,
        compiled_at,
        active_protocol=active_protocol,
        knowledge_lifecycle=knowledge_lifecycle,
    )


def compact_section_lines(markdown: str, heading: str, *, fallback: str, limit: int = 5) -> list[str]:
    section = preserved_section(markdown, heading, "").strip()
    if not section:
        return [fallback]
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    if not lines:
        return [fallback]
    if len(lines) > limit:
        return [*lines[:limit], "- ..."]
    return lines


def workspace_link(path: str, label: str | None = None) -> str:
    target = path.strip()
    display = label or target
    return f"[{display}](../../{target})"


def pack_workspace_link(path: str, label: str | None = None) -> str:
    target = path.strip()
    display = label or target
    return f"[{display}](../../../{target})"


def load_workspace_markdown(root: Path, relative: str) -> tuple[dict[str, Any], str]:
    path = root / relative
    content = path.read_text(encoding="utf-8", errors="replace")
    return parse_frontmatter(content), content


def workspace_file_signature(root: Path, relative: str) -> str:
    path = root / relative
    if not path.exists() or not path.is_file():
        return ""
    return sha256_file(path)


def output_pack_review_candidates(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str,
) -> list[dict[str, str]]:
    pages = decisions + judgments
    return sorted(
        [
            page
            for page in pages
            if page.get("pending_review") == "true"
            or page.get("citation_drift") == "true"
            or page.get("overdue_review") == "true"
            or page.get("escalation_candidate") == "true"
        ],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            0 if page.get("citation_drift") == "true" else 1,
            0 if page.get("pending_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            page.get("title", "").lower(),
        ),
    )


def output_pack_reviewed_candidates(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
) -> list[dict[str, str]]:
    return sort_curated_pages([page for page in decisions + judgments if page.get("reviewed_at") and page.get("pending_review") != "true"])


def output_pack_repair_plan_candidates(memory: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    repair_plan = memory.get("health", {}).get("repair_plan", {})
    ready_actions = [
        action for action in repair_plan.get("ready_actions", []) if isinstance(action, dict) and action.get("active")
    ]
    execution_proposals = [
        proposal for proposal in repair_plan.get("execution_proposals", []) if isinstance(proposal, dict)
    ]
    return ready_actions, execution_proposals


def output_pack_state_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in record.items() if key != "content"} for record in records if isinstance(record, dict)]


def output_pack_group_is_reusable(root: Path, records: list[dict[str, Any]]) -> bool:
    for record in records:
        path = str(record.get("path") or "")
        if not path:
            return False
        if not (root / path).exists():
            return False
    return True


def output_pack_lifecycle_summary_input_signature(lifecycle_summary: dict[str, Any], *, active_protocol: str) -> str:
    payload = {
        "active_protocol": active_protocol,
        "lifecycle_summary": lifecycle_summary,
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def output_pack_review_group_input_signature(
    root: Path,
    review_candidates: list[dict[str, str]],
    *,
    active_protocol: str,
) -> str:
    payload = {
        "active_protocol": active_protocol,
        "review_candidates": [
            {
                "path": str(page.get("path") or ""),
                "title": str(page.get("title") or ""),
                "status": str(page.get("status") or ""),
                "kind": str(page.get("kind") or ""),
                "protocol": str(page.get("protocol") or ""),
                "pending_review": str(page.get("pending_review") or ""),
                "overdue_review": str(page.get("overdue_review") or ""),
                "escalation_candidate": str(page.get("escalation_candidate") or ""),
                "citation_drift": str(page.get("citation_drift") or ""),
                "citation_snapshot_gap_count": str(page.get("citation_snapshot_gap_count", "") or ""),
                "revisit_after": str(page.get("revisit_after") or ""),
                "escalate_after": str(page.get("escalate_after") or ""),
                "page_signature": workspace_file_signature(root, str(page.get("path") or "")),
            }
            for page in review_candidates
        ],
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def output_pack_decision_memo_group_input_signature(
    root: Path,
    reviewed_candidates: list[dict[str, str]],
    recent_outputs: list[dict[str, str]],
    *,
    active_protocol: str,
) -> str:
    payload = {
        "active_protocol": active_protocol,
        "reviewed_candidates": [
            {
                "path": str(page.get("path") or ""),
                "title": str(page.get("title") or ""),
                "status": str(page.get("status") or ""),
                "kind": str(page.get("kind") or ""),
                "protocol": str(page.get("protocol") or ""),
                "reviewed_at": str(page.get("reviewed_at") or ""),
                "confidence": str(page.get("confidence") or ""),
                "page_signature": workspace_file_signature(root, str(page.get("path") or "")),
            }
            for page in reviewed_candidates
        ],
        "recent_outputs": [
            {
                "path": str(artifact.get("path") or ""),
                "title": str(artifact.get("title") or ""),
                "format": str(artifact.get("format") or ""),
                "protocol": str(artifact.get("protocol") or ""),
                "created_at": str(artifact.get("created_at") or ""),
            }
            for artifact in recent_outputs[:5]
            if isinstance(artifact, dict)
        ],
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def output_pack_sop_group_input_signature(
    root: Path,
    ready_actions: list[dict[str, Any]],
    execution_proposals: list[dict[str, Any]],
    *,
    active_protocol: str,
) -> str:
    payload = {
        "active_protocol": active_protocol,
        "execution_proposals": [
            {
                "action_id": str(proposal.get("action_id") or ""),
                "title": str(proposal.get("title") or ""),
                "risk": str(proposal.get("risk") or ""),
                "proposal_kind": str(proposal.get("proposal_kind") or ""),
                "protocol": str(proposal.get("protocol") or ""),
                "summary": str(proposal.get("summary") or ""),
                "proposal_path": str(proposal.get("proposal_path") or ""),
                "bundle_path": str(proposal.get("bundle_path") or ""),
                "target_paths": list(proposal.get("target_paths", []) or []),
                "page_patch_plan": list(proposal.get("page_patch_plan", []) or []),
                "suggested_edits": list(proposal.get("suggested_edits", []) or []),
            }
            for proposal in execution_proposals
        ],
        "ready_actions": [
            {
                "id": str(action.get("id") or ""),
                "title": str(action.get("title") or ""),
                "status": str(action.get("status") or ""),
                "priority": str(action.get("priority") or ""),
                "protocol": str(action.get("protocol") or ""),
                "execution_band": str(action.get("execution_band") or ""),
                "primary_path": str(action.get("primary_path") or ""),
                "secondary_path": str(action.get("secondary_path") or ""),
                "reason": str(action.get("reason") or ""),
                "next_step": str(action.get("next_step") or ""),
                "command_hint": str(action.get("command_hint") or ""),
                "active": bool(action.get("active")),
                "bundle_exists": execution_bundle_path(root, str(action.get("id") or "")).exists(),
                "low_risk_apply": action_supports_low_risk_apply(action),
            }
            for action in ready_actions
        ],
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def build_output_pack_review_packs(
    root: Path,
    review_candidates: list[dict[str, str]],
    *,
    active_protocol: str,
    compiled_at: str,
) -> list[dict[str, Any]]:
    review_packs: list[dict[str, Any]] = []
    for page in review_candidates:
        frontmatter, content = load_workspace_markdown(root, page["path"])
        reasons: list[str] = []
        if page.get("pending_review") == "true":
            reasons.append("pending review")
        if page.get("overdue_review") == "true":
            reasons.append("overdue review")
        if page.get("escalation_candidate") == "true":
            reasons.append("escalation candidate")
        if page.get("citation_drift") == "true":
            reasons.append("citation drift")
        if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0:
            reasons.append("citation snapshot gap")
        kind = str(frontmatter.get("kind") or page.get("kind") or "curated")
        section_name = "Decision" if kind == "decision" else "Judgment"
        evidence_section = "Evidence" if kind == "decision" else "Signals"
        citations = [str(item) for item in frontmatter.get("citations", []) if isinstance(item, str) and item.strip()]
        destination = review_pack_path(root, page["path"])
        protocol = str(frontmatter.get("protocol") or active_protocol)
        frontmatter_text = render_frontmatter(
            {
                "id": f"review-pack-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "review-pack",
                "title": f"Review Pack · {page['title']}",
                "protocol": protocol,
                "target_path": page["path"],
                "target_kind": kind,
                "source_files": [page["path"]],
                "citations": citations,
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# Review Pack · {page['title']}",
            "",
            "## Overview",
            f"- Target page: `{page['path']}`",
            f"- Kind: `{kind}`",
            f"- Status: `{display_curated_status(page.get('status', 'unknown'))}`",
            f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
            f"- Review reasons: `{', '.join(reasons) or 'manual review'}`",
            f"- Revisit / Escalate: `{page.get('revisit_after', '') or 'none'}` / `{page.get('escalate_after', '') or 'none'}`",
            "",
            f"## Current {section_name}",
            *compact_section_lines(content, section_name, fallback="- 当前还没有稳定结论。"),
            "",
            f"## {evidence_section} Snapshot",
            *compact_section_lines(content, evidence_section, fallback="- 当前还没有整理过证据快照。"),
            "",
            "## Counter Evidence",
            *compact_section_lines(content, "Counter Evidence", fallback="- Pending counter evidence."),
            "",
            "## Invalidation",
            *compact_section_lines(content, "Invalidation", fallback="- Pending invalidation conditions."),
            "",
            "## Review History",
            *compact_section_lines(content, "Review History", fallback="- No review history yet."),
            "",
            "## Review Checklist",
            *[f"- {line}" for line in PROTOCOL_LIBRARY.get(protocol, {}).get("review", [])],
            "",
            "## Commands",
            f"- `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page {page['path']} --status "
            f"{'approved' if kind == 'decision' else 'confirmed'} --note \"Review pack follow-up.\"`",
            "",
            "## Citations",
        ]
        if not citations:
            lines.append("- 当前没有结构化 citations。")
        else:
            lines.extend(f"- `{citation}`" for citation in citations)
        lines.extend(
            [
                "",
                "## Related Links",
                f"- {pack_workspace_link(page['path'], page['title'])}",
                "- [审阅队列](../../../wiki/indexes/review-queue.md)",
                "- [审阅中心](../../../wiki/indexes/review-center.md)",
                "- [认知历史](../../../wiki/indexes/cognitive-history.md)",
            ]
        )
        review_packs.append(
            {
                "title": f"Review Pack · {page['title']}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "target_path": page["path"],
                "protocol": protocol,
                "reasons": ", ".join(reasons) or "manual review",
            }
        )
    return review_packs


def output_pack_version_history_lines(
    root: Path,
    destination: Path,
    *,
    compiled_at: str,
    entry_summary: str,
    limit: int = 5,
) -> list[str]:
    history_lines = [f"- `{compiled_at}` | {entry_summary}"]
    relative = relative_path(root, destination)
    if destination.exists():
        _, existing_content = load_workspace_markdown(root, relative)
        for line in compact_section_lines(existing_content, "Version History", fallback="", limit=limit):
            normalized = str(line).strip()
            if not normalized or normalized == "- ...":
                continue
            if normalized not in history_lines:
                history_lines.append(normalized)
    return history_lines[:limit]


def decision_memo_section_lines(
    content: str,
    frontmatter: dict[str, Any],
    heading: str,
    *,
    structured_values: list[str] | None = None,
    structured_scalar: str = "",
    fallback: str,
    limit: int = 5,
) -> list[str]:
    section_lines = compact_section_lines(content, heading, fallback="", limit=limit)
    normalized = [line for line in section_lines if str(line).strip()]
    if normalized and normalized != [fallback]:
        return normalized
    if structured_values:
        return [f"- {value}" for value in structured_values[:limit]]
    if structured_scalar:
        return [f"- {structured_scalar}"]
    return [fallback]


def decision_memo_recommendation_lines(page: dict[str, str], frontmatter: dict[str, Any]) -> list[str]:
    status = str(page.get("status") or frontmatter.get("status") or "")
    confidence = str(frontmatter.get("confidence") or page.get("confidence") or "unknown")
    counter_evidence = frontmatter_string_list(frontmatter, "counter_evidence")
    next_signals = frontmatter_string_list(frontmatter, "next_signals")
    if status in {"approved", "confirmed"} and confidence == "high" and not counter_evidence:
        lines = ["- 当前可以把这份 memo 当作工作基线，进入执行或持续跟踪。"]
    elif counter_evidence or status in {"tracking", "needs-revisit"}:
        lines = ["- 当前应保持谨慎，把它视为待复核立场，而不是最终结论。"]
    else:
        lines = ["- 当前可以作为候选立场流转，但执行前还应补一次人工复核。"]
    if next_signals:
        lines.append(f"- 下一次优先验证：`{next_signals[0]}`。")
    return lines


def build_output_pack_decision_memos(
    root: Path,
    reviewed_candidates: list[dict[str, str]],
    recent_outputs: list[dict[str, str]],
    *,
    active_protocol: str,
    compiled_at: str,
) -> list[dict[str, Any]]:
    decision_memos: list[dict[str, Any]] = []
    for page in reviewed_candidates:
        frontmatter, content = load_workspace_markdown(root, page["path"])
        kind = str(frontmatter.get("kind") or page.get("kind") or "curated")
        memo_label = "Decision Memo" if kind == "decision" else "Judgment Memo"
        section_name = "Decision" if kind == "decision" else "Judgment"
        evidence_section = "Evidence" if kind == "decision" else "Signals"
        citations = [str(item) for item in frontmatter.get("citations", []) if isinstance(item, str) and item.strip()]
        destination = decision_memo_path(root, page["path"])
        protocol = str(frontmatter.get("protocol") or active_protocol)
        counter_evidence_lines = decision_memo_section_lines(
            content,
            frontmatter,
            "Counter Evidence",
            structured_values=frontmatter_string_list(frontmatter, "counter_evidence"),
            fallback="- Pending counter evidence.",
            limit=5,
        )
        invalidation_lines = decision_memo_section_lines(
            content,
            frontmatter,
            "Invalidation",
            structured_scalar=str(frontmatter.get("invalidation_rule") or "").strip(),
            fallback="- Pending invalidation conditions.",
            limit=5,
        )
        next_signal_lines = decision_memo_section_lines(
            content,
            frontmatter,
            "Next Signals",
            structured_values=frontmatter_string_list(frontmatter, "next_signals"),
            fallback="- Pending next signals.",
            limit=5,
        )
        recommendation_lines = decision_memo_recommendation_lines(page, frontmatter)
        frontmatter_text = render_frontmatter(
            {
                "id": f"decision-memo-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "decision-memo",
                "title": f"{memo_label} · {page['title']}",
                "protocol": protocol,
                "target_path": page["path"],
                "target_kind": kind,
                "source_files": [page["path"], *citations],
                "citations": citations,
                "judgment_asset_path": page["path"],
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# {memo_label} · {page['title']}",
            "",
            "## Overview",
            f"- Target page: `{page['path']}`",
            f"- Status: `{display_curated_status(page.get('status', 'unknown'))}`",
            f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
            f"- Reviewed at: `{page.get('reviewed_at', '') or 'unknown'}`",
            f"- Confidence: `{frontmatter.get('confidence') or page.get('confidence', '') or 'n/a'}`",
            "",
            "## Executive Summary",
            *compact_section_lines(content, section_name, fallback="- 当前还没有稳定结论。", limit=6),
            "",
            f"## {evidence_section}",
            *compact_section_lines(content, evidence_section, fallback="- 当前还没有整理过证据。", limit=6),
            "",
            "## Recommendation",
            *recommendation_lines,
            "",
            "## Counter Evidence",
            *counter_evidence_lines,
            "",
            "## Invalidation",
            *invalidation_lines,
            "",
            "## Next Signals",
            *next_signal_lines,
            "",
            "## Review History",
            *compact_section_lines(content, "Review History", fallback="- No review history yet.", limit=6),
            "",
            "## Version History",
            *output_pack_version_history_lines(
                root,
                destination,
                compiled_at=compiled_at,
                entry_summary=f"status `{page.get('status', 'unknown')}` | confidence `{frontmatter.get('confidence') or page.get('confidence', '') or 'n/a'}`",
            ),
            "",
            "## Citations",
        ]
        if not citations:
            lines.append("- 当前没有结构化 citations。")
        else:
            lines.extend(f"- `{citation}`" for citation in citations)
        if recent_outputs:
            lines.extend(["", "## Nearby Recent Outputs"])
            for artifact in recent_outputs[:5]:
                lines.append(
                    f"- {pack_workspace_link(artifact['path'], artifact['title'])}"
                    f" | format `{artifact['format'] or 'unknown'}`"
                    f" | protocol `{artifact['protocol'] or DEFAULT_PROTOCOL}`"
                )
        lines.extend(
            [
                "",
                "## Related Links",
                f"- {pack_workspace_link(page['path'], page['title'])}",
                "- [判断资产](../../../wiki/indexes/judgment-assets.md)",
                "- [认知历史](../../../wiki/indexes/cognitive-history.md)",
                "- [审阅中心](../../../wiki/indexes/review-center.md)",
            ]
        )
        decision_memos.append(
            {
                "title": f"{memo_label} · {page['title']}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "target_path": page["path"],
                "protocol": protocol,
                "reviewed_at": page.get("reviewed_at", "") or "",
            }
        )
    return decision_memos


def sop_pattern_key(record: dict[str, Any]) -> str:
    proposal_kind = str(record.get("proposal_kind") or record.get("kind") or "manual-repair")
    risk = str(record.get("risk") or "")
    protocol = str(record.get("protocol") or DEFAULT_PROTOCOL)
    return "|".join(part for part in (proposal_kind, risk, protocol) if part)


def extract_sop_pattern_frequencies(
    ready_actions: list[dict[str, Any]],
    execution_proposals: list[dict[str, Any]],
) -> dict[str, int]:
    pattern_counts: dict[str, int] = {}
    for proposal in execution_proposals:
        key = sop_pattern_key(proposal)
        if key:
            pattern_counts[key] = pattern_counts.get(key, 0) + 1
    for action in ready_actions:
        key = sop_pattern_key(action)
        if key:
            pattern_counts[key] = pattern_counts.get(key, 0) + 1
    return pattern_counts


def build_output_pack_sop_drafts(
    root: Path,
    ready_actions: list[dict[str, Any]],
    execution_proposals: list[dict[str, Any]],
    *,
    active_protocol: str,
    compiled_at: str,
) -> tuple[list[dict[str, Any]], int]:
    sop_drafts: list[dict[str, Any]] = []
    proposal_by_action = {
        str(proposal.get("action_id") or ""): proposal
        for proposal in execution_proposals
        if proposal.get("action_id")
    }
    pattern_frequencies = extract_sop_pattern_frequencies(ready_actions, execution_proposals)
    proposal_count = 0
    for proposal in execution_proposals:
        action_id = str(proposal.get("action_id") or "").strip()
        if not action_id:
            continue
        destination = sop_draft_path(root, action_id)
        protocol = str(proposal.get("protocol") or active_protocol)
        pattern_key = sop_pattern_key(proposal)
        pattern_frequency = int(pattern_frequencies.get(pattern_key, 0))
        frontmatter_text = render_frontmatter(
            {
                "id": f"sop-draft-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "sop-draft",
                "title": f"SOP Draft · {proposal.get('title') or action_id}",
                "protocol": protocol,
                "action_id": action_id,
                "source_files": [str(proposal.get("proposal_path") or "")],
                "pattern_key": pattern_key,
                "pattern_frequency": pattern_frequency,
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        patch_plan = proposal.get("page_patch_plan", [])
        bundle_path = str(proposal.get("bundle_path") or "")
        safe_preview = proposal.get("safe_apply_preview") if isinstance(proposal.get("safe_apply_preview"), dict) else {}
        lines = [
            frontmatter_text,
            "",
            f"# SOP Draft · {proposal.get('title') or action_id}",
            "",
            "## Overview",
            f"- Action id: `{action_id}`",
            f"- Risk: `{proposal.get('risk', 'medium')}`",
            f"- Proposal kind: `{proposal.get('proposal_kind', 'manual-repair')}`",
            f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
            f"- Targets: `{', '.join(proposal.get('target_paths', [])) or 'none'}`",
            f"- Bundle: `{bundle_path or 'none'}`",
            f"- Pattern frequency: `{pattern_frequency}`",
            "",
            "## Strategy",
            f"- {proposal.get('summary', '检查目标页面并确认是否执行。')}",
            "",
            "## Step-by-Step",
            f"1. 先跑 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run`。",
        ]
        if bundle_path:
            lines.append(
                f"2. 如果 dry-run 结果符合预期，再执行 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --bundle {bundle_path}`。"
            )
        else:
            lines.append("2. 当前没有 bundle，先回到 execution proposal 页面确认执行边界。")
        lines.append(
            f"3. 如需回滚，执行 `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {action_id}`。"
        )
        lines.extend(["", "## Page-Level Patch Plan"])
        if not patch_plan:
            lines.append("- 当前没有页级 patch step。")
        else:
            for patch in patch_plan:
                lines.append(
                    f"- `{patch.get('path', '')}`"
                    f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                    f" | mode `{patch.get('mode', 'update')}`"
                    f" | sections `{', '.join(patch.get('sections', [])) or 'none'}`"
                )
                lines.append(f"  - {patch.get('summary', '检查相关页面并补充修复说明。')}")
        lines.extend(["", "## Suggested Edits"])
        edits = proposal.get("suggested_edits", [])
        if not edits:
            lines.append("- 当前没有额外建议。")
        else:
            lines.extend(f"- {edit}" for edit in edits[:8])
        lines.extend(["", "## Dry Run Preview"])
        if not safe_preview:
            lines.append("- 当前没有额外 dry-run preview。")
        else:
            lines.append(f"- Apply mode: `{safe_preview.get('apply_mode', 'dry-run')}`")
            lines.append(f"- Bundle path: `{safe_preview.get('bundle_path', '') or 'none'}`")
            lines.extend(
                f"- {step}"
                for step in safe_preview.get("steps", [])[:6]
                if isinstance(step, str) and step.strip()
            )
        lines.extend(
            [
                "",
                "## Version History",
                *output_pack_version_history_lines(
                    root,
                    destination,
                    compiled_at=compiled_at,
                    entry_summary=f"pattern `{pattern_key or 'manual-repair'}` | frequency `{pattern_frequency}`",
                ),
                "",
                "## Related Links",
                f"- {pack_workspace_link(str(proposal.get('proposal_path') or ''), 'Execution Proposal')}" if proposal.get("proposal_path") else "- Execution Proposal: none",
                f"- {pack_workspace_link(bundle_path, 'Execution Bundle')}" if bundle_path else "- Execution Bundle: none",
                "- [执行中心](../../../wiki/indexes/execution-center.md)",
                "- [执行审计](../../../wiki/indexes/execution-audit.md)",
                "- [机器记忆修复计划](../../../wiki/indexes/machine-memory-repair-plan.md)",
            ]
        )
        sop_drafts.append(
            {
                "title": f"SOP Draft · {proposal.get('title') or action_id}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "action_id": action_id,
                "protocol": protocol,
                "risk": str(proposal.get("risk") or "medium"),
            }
        )
        proposal_count += 1

    for action in ready_actions:
        action_id = str(action.get("id") or "").strip()
        if not action_id or action_id in proposal_by_action:
            continue
        destination = sop_draft_path(root, action_id)
        band = str(action.get("execution_band") or "review-first")
        action_protocol = str(action.get("protocol") or active_protocol)
        pattern_key = sop_pattern_key(action)
        pattern_frequency = int(pattern_frequencies.get(pattern_key, 0))
        bundle_absolute = execution_bundle_path(root, action_id)
        bundle_relative = relative_path(root, bundle_absolute)
        bundle_path = bundle_relative if bundle_absolute.exists() else ""
        frontmatter_text = render_frontmatter(
            {
                "id": f"sop-draft-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "sop-draft",
                "title": f"SOP Draft · {action.get('title') or action_id}",
                "protocol": action_protocol,
                "action_id": action_id,
                "source_files": [str(action.get("primary_path") or "")],
                "pattern_key": pattern_key,
                "pattern_frequency": pattern_frequency,
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# SOP Draft · {action.get('title') or action_id}",
            "",
            "## Overview",
            f"- Action id: `{action_id}`",
            f"- Status: `{display_action_status(str(action.get('status') or 'proposed'))}`",
            f"- Priority: `{action.get('priority', 'medium')}`",
            f"- Protocol: `{action_protocol}` ({protocol_title(action_protocol)})",
            f"- Execution band: `{band}` ({execution_band_label(band)})",
            f"- Primary / Secondary: `{action.get('primary_path', '')}` / `{action.get('secondary_path', '') or 'none'}`",
            f"- Pattern frequency: `{pattern_frequency}`",
            "",
            "## Step-by-Step",
            f"1. 先跑 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run`。",
        ]
        if bundle_path:
            lines.extend(
                [
                    f"2. 如果执行 band 仍允许，再执行 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --bundle {bundle_path}`。",
                    f"3. 必要时用 `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {action_id}` 回滚。",
                ]
            )
            bundle_link = f"- [Execution Bundle](../../../{bundle_path})"
        else:
            lines.extend(
                [
                    "2. 当前还没有稳定 bundle；先停在 dry-run，或回到 execution proposal 层生成 bundle。",
                    "3. 生成 bundle 后再执行真实 apply。",
                ]
            )
            bundle_link = "- Execution Bundle: none"
        lines.extend(
            [
                "",
                "## Action Notes",
                f"- Reason: {action.get('reason', 'n/a')}",
                f"- Next step: {action.get('next_step', 'n/a')}",
                f"- Command hint: `{action.get('command_hint', '') or 'none'}`",
                "",
                "## Version History",
                *output_pack_version_history_lines(
                    root,
                    destination,
                    compiled_at=compiled_at,
                    entry_summary=f"pattern `{pattern_key or band}` | frequency `{pattern_frequency}`",
                ),
                "",
                "## Related Links",
                "- [执行中心](../../../wiki/indexes/execution-center.md)",
                "- [执行审计](../../../wiki/indexes/execution-audit.md)",
                "- [机器记忆动作队列](../../../wiki/indexes/machine-memory-actions.md)",
                bundle_link,
            ]
        )
        sop_drafts.append(
            {
                "title": f"SOP Draft · {action.get('title') or action_id}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "action_id": action_id,
                "protocol": action_protocol,
                "risk": "low" if action_supports_low_risk_apply(action) else "medium",
            }
        )
    return sop_drafts, proposal_count


def build_output_packs(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_protocol = protocol_state["active_protocol"]
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    review_candidates = output_pack_review_candidates(decisions, judgments, active_protocol=active_protocol)
    reviewed_candidates = output_pack_reviewed_candidates(decisions, judgments)
    ready_actions, execution_proposals = output_pack_repair_plan_candidates(memory)
    review_packs = build_output_pack_review_packs(
        root,
        review_candidates,
        active_protocol=active_protocol,
        compiled_at=compiled_at,
    )
    decision_memos = build_output_pack_decision_memos(
        root,
        reviewed_candidates,
        recent_outputs,
        active_protocol=active_protocol,
        compiled_at=compiled_at,
    )
    sop_drafts, proposal_count = build_output_pack_sop_drafts(
        root,
        ready_actions,
        execution_proposals,
        active_protocol=active_protocol,
        compiled_at=compiled_at,
    )
    counts = {
        "review_packs": len(review_packs),
        "decision_memos": len(decision_memos),
        "sop_drafts": len(sop_drafts),
        "execution_proposal_sops": proposal_count,
    }
    return {
        "compiled_at": compiled_at,
        "active_protocol": active_protocol,
        "review_packs": review_packs,
        "decision_memos": decision_memos,
        "sop_drafts": sop_drafts,
        "lifecycle_summary": lifecycle_summary,
        "counts": counts,
    }


def build_output_packs_incremental(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_protocol = protocol_state["active_protocol"]
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    review_candidates = output_pack_review_candidates(decisions, judgments, active_protocol=active_protocol)
    reviewed_candidates = output_pack_reviewed_candidates(decisions, judgments)
    ready_actions, execution_proposals = output_pack_repair_plan_candidates(memory)
    previous_state = load_output_pack_build_state(root)
    previous_group_records = previous_state.get("group_records", {})
    signatures = {
        "lifecycle_summary": output_pack_lifecycle_summary_input_signature(
            lifecycle_summary,
            active_protocol=active_protocol,
        ),
        "review_packs": output_pack_review_group_input_signature(
            root,
            review_candidates,
            active_protocol=active_protocol,
        ),
        "decision_memos": output_pack_decision_memo_group_input_signature(
            root,
            reviewed_candidates,
            recent_outputs,
            active_protocol=active_protocol,
        ),
        "sop_drafts": output_pack_sop_group_input_signature(
            root,
            ready_actions,
            execution_proposals,
            active_protocol=active_protocol,
        ),
    }
    dirty_groups: list[str] = []
    clean_groups: list[str] = []
    review_packs: list[dict[str, Any]]
    decision_memos: list[dict[str, Any]]
    sop_drafts: list[dict[str, Any]]

    lifecycle_reusable = (
        isinstance(previous_group_records.get("lifecycle_summary"), dict)
        and str(previous_group_records["lifecycle_summary"].get("input_signature") or "") == signatures["lifecycle_summary"]
    )
    if lifecycle_reusable:
        clean_groups.append("lifecycle_summary")
    else:
        dirty_groups.append("lifecycle_summary")

    previous_review_packs = previous_state.get("review_packs", [])
    review_reusable = (
        isinstance(previous_group_records.get("review_packs"), dict)
        and str(previous_group_records["review_packs"].get("input_signature") or "") == signatures["review_packs"]
        and output_pack_group_is_reusable(root, previous_review_packs)
    )
    if review_reusable:
        review_packs = [dict(record) for record in previous_review_packs]
        clean_groups.append("review_packs")
    else:
        review_packs = build_output_pack_review_packs(
            root,
            review_candidates,
            active_protocol=active_protocol,
            compiled_at=compiled_at,
        )
        dirty_groups.append("review_packs")

    previous_decision_memos = previous_state.get("decision_memos", [])
    memo_reusable = (
        isinstance(previous_group_records.get("decision_memos"), dict)
        and str(previous_group_records["decision_memos"].get("input_signature") or "") == signatures["decision_memos"]
        and output_pack_group_is_reusable(root, previous_decision_memos)
    )
    if memo_reusable:
        decision_memos = [dict(record) for record in previous_decision_memos]
        clean_groups.append("decision_memos")
    else:
        decision_memos = build_output_pack_decision_memos(
            root,
            reviewed_candidates,
            recent_outputs,
            active_protocol=active_protocol,
            compiled_at=compiled_at,
        )
        dirty_groups.append("decision_memos")

    previous_sop_drafts = previous_state.get("sop_drafts", [])
    sop_reusable = (
        isinstance(previous_group_records.get("sop_drafts"), dict)
        and str(previous_group_records["sop_drafts"].get("input_signature") or "") == signatures["sop_drafts"]
        and output_pack_group_is_reusable(root, previous_sop_drafts)
    )
    if sop_reusable:
        sop_drafts = [dict(record) for record in previous_sop_drafts]
        clean_groups.append("sop_drafts")
        proposal_count = int(previous_state.get("counts", {}).get("execution_proposal_sops", 0) or 0)
    else:
        sop_drafts, proposal_count = build_output_pack_sop_drafts(
            root,
            ready_actions,
            execution_proposals,
            active_protocol=active_protocol,
            compiled_at=compiled_at,
        )
        dirty_groups.append("sop_drafts")

    counts = {
        "review_packs": len(review_packs),
        "decision_memos": len(decision_memos),
        "sop_drafts": len(sop_drafts),
        "execution_proposal_sops": proposal_count,
    }
    output_packs = {
        "compiled_at": compiled_at,
        "active_protocol": active_protocol,
        "review_packs": review_packs,
        "decision_memos": decision_memos,
        "sop_drafts": sop_drafts,
        "lifecycle_summary": lifecycle_summary,
        "counts": counts,
    }
    state_document = {
        "version": 1,
        "generated_at": compiled_at,
        "active_protocol": active_protocol,
        "group_records": {
            group: {"input_signature": signature}
            for group, signature in signatures.items()
        },
        "lifecycle_summary": lifecycle_summary,
        "review_packs": output_pack_state_records(review_packs),
        "decision_memos": output_pack_state_records(decision_memos),
        "sop_drafts": output_pack_state_records(sop_drafts),
        "counts": counts,
    }
    return {
        "output_packs": output_packs,
        "state_document": state_document,
        "dirty_groups": dirty_groups,
        "clean_groups": clean_groups,
    }


def render_output_packs_index(output_packs: dict[str, Any], compiled_at: str, active_protocol: str) -> str:
    review_packs = output_packs.get("review_packs", [])
    decision_memos = output_packs.get("decision_memos", [])
    sop_drafts = output_packs.get("sop_drafts", [])
    lifecycle_summary = output_packs.get("lifecycle_summary", {})
    lifecycle_counts = lifecycle_summary.get("counts", {})
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    counts = output_packs.get("counts", {})
    lines = [
        "# 输出 Pack 总览",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- Review packs：`{counts.get('review_packs', len(review_packs))}`",
        f"- Decision memos：`{counts.get('decision_memos', len(decision_memos))}`",
        f"- SOP drafts：`{counts.get('sop_drafts', len(sop_drafts))}`",
        f"- lifecycle concept backlog：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}`",
        f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
        f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        "",
        "## Pack 目录",
        "- `output/packs/review/`：待审 / 漂移 / aging 页面",
        "- `output/packs/decision-memos/`：已审 decision / judgment",
        "- `output/packs/sop-drafts/`：ready action / execution proposal",
        "",
        "## Lifecycle Governance Summary",
        f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
        f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
        f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
        "",
        "## Lifecycle Concept Backlog",
    ]
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(
        [
            "",
        "## Review Packs",
        ]
    )
    if not review_packs:
        lines.append("- 当前没有 review packs。")
    else:
        for pack in review_packs[:16]:
            lines.append(
                f"- {workspace_link(pack['path'], pack['title'])}"
                f" | target `{pack.get('target_path', '')}`"
                f" | reasons `{pack.get('reasons', 'manual review')}`"
            )
    lines.extend(["", "## Decision Memos"])
    if not decision_memos:
        lines.append("- 当前没有 decision memos。")
    else:
        for pack in decision_memos[:16]:
            lines.append(
                f"- {workspace_link(pack['path'], pack['title'])}"
                f" | target `{pack.get('target_path', '')}`"
                f" | reviewed `{pack.get('reviewed_at', '') or 'unknown'}`"
            )
    lines.extend(["", "## SOP Drafts"])
    if not sop_drafts:
        lines.append("- 当前没有 SOP drafts。")
    else:
        for pack in sop_drafts[:16]:
            lines.append(
                f"- {workspace_link(pack['path'], pack['title'])}"
                f" | action `{pack.get('action_id', '')}`"
                f" | risk `{pack.get('risk', 'medium')}`"
            )
    lines.extend(
        [
            "",
            "## 相关入口",
            "- [炉心面板](./furnace-center.md)",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
            "- [执行审计](./execution-audit.md)",
            "- [判断资产](./judgment-assets.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def domain_pilots_index_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "domain-pilots.md"


def pilot_scorecards_dir(root: Path) -> Path:
    return root / "output" / "pilots"


def pilot_scorecard_path(root: Path, protocol: str) -> Path:
    return pilot_scorecards_dir(root) / f"{slugify(protocol)}.md"


def pilot_stage(metrics: dict[str, int]) -> tuple[str, str]:
    curated = metrics["decisions"] + metrics["judgments"]
    reviewed = metrics["reviewed"]
    outputs = metrics["outputs"]
    receipts = metrics["receipts"]
    packs = metrics["review_packs"] + metrics["decision_memos"] + metrics["sop_drafts"]
    if curated == 0 and outputs == 0:
        return ("seed", "尚未形成该协议的稳定判断资产。")
    if curated < 2 or reviewed == 0:
        return ("warming-up", "已经开始沉淀，但 reviewed judgment / decision 还偏少。")
    if reviewed < 3 or outputs < 3:
        return ("building", "协议已经起量，但还没进入明显复利。")
    if packs < 2 or receipts == 0:
        return ("active", "判断和 pack 已形成，但执行闭环还不够密。")
    return ("compounding", "已经出现判断、pack、执行和复审的复利迹象。")


def domain_pilot_state_scorecard(scorecard: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in scorecard.items() if key != "content"}


def domain_pilot_scorecard_is_reusable(root: Path, scorecard: dict[str, Any]) -> bool:
    path = str(scorecard.get("path") or "")
    return bool(path) and (root / path).exists()


def domain_pilot_protocol_inputs(
    protocol: str,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    recent_outputs: list[dict[str, str]],
    all_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    execution_audit: dict[str, Any],
    memory: dict[str, Any],
    *,
    knowledge_lifecycle: dict[str, Any],
    material_routing: dict[str, Any],
    active_protocol: str,
) -> dict[str, Any]:
    lifecycle_summary = protocol_related_concept_lifecycle_summary(
        knowledge_lifecycle,
        material_routing,
        protocol=protocol,
    )
    receipt_counts = {
        str(row.get("protocol") or DEFAULT_PROTOCOL): int(row.get("count") or 0)
        for row in execution_audit.get("protocols", [])
        if isinstance(row, dict)
    }
    repair_plan = memory.get("health", {}).get("repair_plan", {})
    execution_proposals = [
        {
            "action_id": str(proposal.get("action_id") or ""),
            "title": str(proposal.get("title") or ""),
            "protocol": str(proposal.get("protocol") or DEFAULT_PROTOCOL),
            "proposal_kind": str(proposal.get("proposal_kind") or ""),
            "summary": str(proposal.get("summary") or ""),
        }
        for proposal in repair_plan.get("execution_proposals", [])
        if isinstance(proposal, dict) and str(proposal.get("protocol") or DEFAULT_PROTOCOL) == protocol
    ]
    return {
        "protocol": protocol,
        "active_protocol": active_protocol,
        "decisions": [
            {
                "title": str(page.get("title") or ""),
                "path": str(page.get("path") or ""),
                "status": str(page.get("status") or ""),
                "pending_review": str(page.get("pending_review") or ""),
                "overdue_review": str(page.get("overdue_review") or ""),
                "escalation_candidate": str(page.get("escalation_candidate") or ""),
                "reviewed_at": str(page.get("reviewed_at") or ""),
            }
            for page in decisions
            if str(page.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "judgments": [
            {
                "title": str(page.get("title") or ""),
                "path": str(page.get("path") or ""),
                "status": str(page.get("status") or ""),
                "pending_review": str(page.get("pending_review") or ""),
                "overdue_review": str(page.get("overdue_review") or ""),
                "escalation_candidate": str(page.get("escalation_candidate") or ""),
                "reviewed_at": str(page.get("reviewed_at") or ""),
            }
            for page in judgments
            if str(page.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "all_outputs": [
            {
                "title": str(artifact.get("title") or ""),
                "path": str(artifact.get("path") or ""),
                "format": str(artifact.get("format") or ""),
                "protocol": str(artifact.get("protocol") or DEFAULT_PROTOCOL),
                "created_at": str(artifact.get("created_at") or ""),
            }
            for artifact in all_outputs
            if str(artifact.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "recent_outputs": [
            {
                "title": str(artifact.get("title") or ""),
                "path": str(artifact.get("path") or ""),
                "format": str(artifact.get("format") or ""),
                "protocol": str(artifact.get("protocol") or DEFAULT_PROTOCOL),
                "created_at": str(artifact.get("created_at") or ""),
            }
            for artifact in recent_outputs
            if str(artifact.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ][:5],
        "review_packs": [
            {
                "title": str(pack.get("title") or ""),
                "path": str(pack.get("path") or ""),
            }
            for pack in output_packs.get("review_packs", [])
            if str(pack.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "decision_memos": [
            {
                "title": str(pack.get("title") or ""),
                "path": str(pack.get("path") or ""),
            }
            for pack in output_packs.get("decision_memos", [])
            if str(pack.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "sop_drafts": [
            {
                "title": str(pack.get("title") or ""),
                "path": str(pack.get("path") or ""),
                "risk": str(pack.get("risk") or "medium"),
            }
            for pack in output_packs.get("sop_drafts", [])
            if str(pack.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "receipt_count": receipt_counts.get(protocol, 0),
        "execution_proposals": execution_proposals,
        "lifecycle_summary": lifecycle_summary,
    }


def domain_pilot_protocol_input_signature(protocol_inputs: dict[str, Any]) -> str:
    return sha256_bytes(json.dumps(protocol_inputs, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def build_domain_pilot_scorecard(
    root: Path,
    protocol_inputs: dict[str, Any],
    *,
    compiled_at: str,
) -> dict[str, Any]:
    protocol = str(protocol_inputs.get("protocol") or DEFAULT_PROTOCOL)
    active_protocol = str(protocol_inputs.get("active_protocol") or DEFAULT_PROTOCOL)
    protocol_decisions = list(protocol_inputs.get("decisions", []) or [])
    protocol_judgments = list(protocol_inputs.get("judgments", []) or [])
    protocol_outputs = list(protocol_inputs.get("all_outputs", []) or [])
    protocol_recent_outputs = list(protocol_inputs.get("recent_outputs", []) or [])
    lifecycle_summary = dict(protocol_inputs.get("lifecycle_summary", {}) or {})
    lifecycle_counts = lifecycle_summary.get("counts", {})
    metrics = {
        "decisions": len(protocol_decisions),
        "judgments": len(protocol_judgments),
        "reviewed": sum(
            1
            for page in [*protocol_decisions, *protocol_judgments]
            if str(page.get("reviewed_at") or "") and str(page.get("pending_review") or "") != "true"
        ),
        "pending": sum(1 for page in [*protocol_decisions, *protocol_judgments] if page.get("pending_review") == "true"),
        "overdue": sum(1 for page in [*protocol_decisions, *protocol_judgments] if page.get("overdue_review") == "true"),
        "escalation": sum(
            1 for page in [*protocol_decisions, *protocol_judgments] if page.get("escalation_candidate") == "true"
        ),
        "outputs": len(protocol_outputs),
        "review_packs": len(list(protocol_inputs.get("review_packs", []) or [])),
        "decision_memos": len(list(protocol_inputs.get("decision_memos", []) or [])),
        "sop_drafts": len(list(protocol_inputs.get("sop_drafts", []) or [])),
        "receipts": int(protocol_inputs.get("receipt_count", 0) or 0),
        "execution_proposals": len(list(protocol_inputs.get("execution_proposals", []) or [])),
        "lifecycle_concept_backlog": int(lifecycle_counts.get("concept_backlog", 0) or 0),
        "lifecycle_retired_concepts": int(lifecycle_counts.get("retired_concepts", 0) or 0),
        "lifecycle_dominant_concepts": int(lifecycle_counts.get("dominant_related_concepts", 0) or 0),
        "lifecycle_mixed_concepts": int(lifecycle_counts.get("mixed_related_concepts", 0) or 0),
        "lifecycle_bridge_concepts": int(lifecycle_counts.get("ambiguity_bridge_concepts", 0) or 0),
    }
    stage, stage_summary = pilot_stage(metrics)
    gaps: list[str] = []
    if lifecycle_counts.get("concept_backlog", 0):
        gaps.append(
            f"有 `{lifecycle_counts.get('concept_backlog', 0)}` 个 protocol-related lifecycle concept backlog 尚未收敛。"
        )
    ambiguity_count = int(lifecycle_counts.get("mixed_related_concepts", 0)) + int(
        lifecycle_counts.get("ambiguity_bridge_concepts", 0)
    )
    if ambiguity_count:
        gaps.append(f"有 `{ambiguity_count}` 个 protocol-related concept 仍处于 mixed / bridge ambiguity，需要人工校准归属。")
    if metrics["decisions"] + metrics["judgments"] == 0:
        gaps.append("还没有该协议的 `decision / judgment` 资产。")
    if metrics["reviewed"] == 0:
        gaps.append("还没有 reviewed judgment / decision。")
    if metrics["outputs"] < 2:
        gaps.append("可回流 outputs 还不够密。")
    if metrics["pending"] > metrics["reviewed"]:
        gaps.append("待审页面多于已审资产。")
    if metrics["review_packs"] == 0 and metrics["pending"] > 0:
        gaps.append("需要先把 pending review 炼成 review packs。")
    if metrics["decision_memos"] == 0 and metrics["reviewed"] > 0:
        gaps.append("已审判断还没有形成 decision memos。")
    if metrics["sop_drafts"] == 0 and metrics["execution_proposals"] > 0:
        gaps.append("执行提案还没有形成 SOP drafts。")
    if metrics["receipts"] == 0 and metrics["sop_drafts"] > 0:
        gaps.append("还没有 execution receipt，可先从 dry-run / low-risk apply 开始。")
    next_moves = [
        PROTOCOL_LIBRARY[protocol]["focus"][0],
        PROTOCOL_LIBRARY[protocol]["review"][0],
        PROTOCOL_LIBRARY[protocol]["nightly"][0],
    ]
    if gaps:
        next_moves.insert(0, gaps[0])
    destination = pilot_scorecard_path(root, protocol)
    frontmatter_text = render_frontmatter(
        {
            "id": f"pilot-scorecard-{slugify(protocol)}",
            "kind": "pilot-scorecard",
            "title": f"{protocol_title(protocol)} Pilot Scorecard",
            "protocol": protocol,
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
        }
    )
    lines = [
        frontmatter_text,
        "",
        f"# {protocol_title(protocol)} Pilot Scorecard",
        "",
        "## Overview",
        f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
        f"- Stage: `{stage}`",
        f"- Summary: {stage_summary}",
        f"- 当前协议是否 active：`{'yes' if protocol == active_protocol else 'no'}`",
        "",
        "## Density Snapshot",
        f"- Decisions / Judgments: `{metrics['decisions']}` / `{metrics['judgments']}`",
        f"- Reviewed / Pending: `{metrics['reviewed']}` / `{metrics['pending']}`",
        f"- Overdue / Escalation: `{metrics['overdue']}` / `{metrics['escalation']}`",
        f"- Outputs: `{metrics['outputs']}`",
        f"- Review packs / Decision memos / SOP drafts: `{metrics['review_packs']}` / `{metrics['decision_memos']}` / `{metrics['sop_drafts']}`",
        f"- Execution proposals / Receipts: `{metrics['execution_proposals']}` / `{metrics['receipts']}`",
        f"- Protocol-related lifecycle backlog / retired concepts: `{metrics['lifecycle_concept_backlog']}` / `{metrics['lifecycle_retired_concepts']}`",
        "",
        "## Protocol Focus",
        *[f"- {line}" for line in PROTOCOL_LIBRARY[protocol]["focus"]],
        "",
        "## Gaps",
    ]
    if not gaps:
        lines.append("- 当前没有明显结构性缺口。")
    else:
        lines.extend(f"- {gap}" for gap in gaps)
    lines.extend(
        [
            "",
            "## Lifecycle Governance",
            "- 以下 concept lifecycle 摘要优先统计 supporting sources 的 `material-routing top_protocols` 首位命中；若来源在当前协议仍是 `warm/hot evidence`，或属于 `cross_protocol_bridge` 且当前协议仍位于 top2，也会保守纳入。",
            f"- Inference mode: `{lifecycle_summary.get('inference_mode', 'unknown')}`",
            f"- Ambiguity mode: `{lifecycle_summary.get('ambiguity_mode', 'unknown')}`",
            f"- Related direct / secondary / bridge concepts: `{lifecycle_counts.get('direct_related_concepts', 0)}` / `{lifecycle_counts.get('secondary_related_concepts', 0)}` / `{lifecycle_counts.get('bridge_related_concepts', 0)}`",
            f"- Related dominant / mixed / bridge concepts: `{lifecycle_counts.get('dominant_related_concepts', 0)}` / `{lifecycle_counts.get('mixed_related_concepts', 0)}` / `{lifecycle_counts.get('ambiguity_bridge_concepts', 0)}`",
            f"- Related review concepts: `{lifecycle_counts.get('review_concepts', 0)}`",
            f"- Related revisit concepts: `{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- Related retired concepts: `{lifecycle_counts.get('retired_concepts', 0)}`",
            f"- Related active concepts: `{lifecycle_counts.get('active_concepts', 0)}`",
            "",
            "## Protocol Ambiguity Watchlist",
        ]
    )
    if not lifecycle_summary.get("ambiguity_watchlist"):
        lines.append("- 当前没有 mixed / bridge ambiguity concept。")
    else:
        lines.append("- 以下概念仍需要人工判断是当前协议主归属、混合归属，还是桥接归属。")
        for entry in lifecycle_summary.get("ambiguity_watchlist", [])[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Protocol-Related Lifecycle Concept Backlog"])
    if not lifecycle_summary.get("concept_backlog"):
        lines.append("- 当前没有 protocol-related lifecycle concept backlog。")
    else:
        for entry in lifecycle_summary.get("concept_backlog", [])[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Protocol-Related Retired Concepts"])
    if not lifecycle_summary.get("retired_concepts"):
        lines.append("- 当前没有 protocol-related retired concept。")
    else:
        for entry in lifecycle_summary.get("retired_concepts", [])[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Next Moves"])
    lines.extend(f"- {item}" for item in next_moves[:5])
    lines.extend(["", "## Recent Outputs"])
    if not protocol_recent_outputs:
        lines.append("- 当前没有最近 output。")
    else:
        for artifact in protocol_recent_outputs:
            lines.append(
                f"- {pack_workspace_link(artifact['path'], artifact['title'])}"
                f" | format `{artifact['format'] or 'unknown'}`"
                f" | created `{artifact['created_at'] or 'unknown'}`"
            )
    lines.extend(
        [
            "",
            "## Related Links",
            f"- {pack_workspace_link(f'schema/protocols/{protocol}/index.md', f'{protocol_title(protocol)} 协议规则')}",
            "- [协议总览](../../../wiki/indexes/protocols.md)",
            "- [输出 Pack 总览](../../../wiki/indexes/output-packs.md)",
            "- [审阅中心](../../../wiki/indexes/review-center.md)",
            "- [执行中心](../../../wiki/indexes/execution-center.md)",
        ]
    )
    return {
        "protocol": protocol,
        "title": f"{protocol_title(protocol)} Pilot Scorecard",
        "path": relative_path(root, destination),
        "content": "\n".join(lines) + "\n",
        "stage": stage,
        "summary": stage_summary,
        "metrics": metrics,
        "lifecycle_summary": lifecycle_summary,
    }


def build_domain_pilots(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    all_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    execution_audit: dict[str, Any],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
    material_routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_protocol = protocol_state["active_protocol"]
    knowledge_lifecycle = knowledge_lifecycle or load_knowledge_lifecycle_state(root)
    material_routing = material_routing or load_material_routing_state(root)
    scorecards = [
        build_domain_pilot_scorecard(
            root,
            domain_pilot_protocol_inputs(
                protocol,
                decisions,
                judgments,
                recent_outputs,
                all_outputs,
                output_packs,
                execution_audit,
                memory,
                knowledge_lifecycle=knowledge_lifecycle,
                material_routing=material_routing,
                active_protocol=active_protocol,
            ),
            compiled_at=compiled_at,
        )
        for protocol in sorted(PROTOCOL_LIBRARY)
    ]
    return {
        "compiled_at": compiled_at,
        "active_protocol": active_protocol,
        "scorecards": scorecards,
    }


def build_domain_pilots_incremental(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    all_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    execution_audit: dict[str, Any],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
    material_routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_protocol = protocol_state["active_protocol"]
    knowledge_lifecycle = knowledge_lifecycle or load_knowledge_lifecycle_state(root)
    material_routing = material_routing or load_material_routing_state(root)
    previous_state = load_domain_pilot_build_state(root)
    previous_protocol_records = previous_state.get("protocol_records", {})
    previous_scorecards_by_protocol = {
        str(scorecard.get("protocol") or ""): scorecard
        for scorecard in previous_state.get("scorecards", [])
        if isinstance(scorecard, dict) and str(scorecard.get("protocol") or "")
    }
    scorecards: list[dict[str, Any]] = []
    dirty_protocols: list[str] = []
    clean_protocols: list[str] = []
    protocol_records: dict[str, dict[str, str]] = {}
    for protocol in sorted(PROTOCOL_LIBRARY):
        protocol_inputs = domain_pilot_protocol_inputs(
            protocol,
            decisions,
            judgments,
            recent_outputs,
            all_outputs,
            output_packs,
            execution_audit,
            memory,
            knowledge_lifecycle=knowledge_lifecycle,
            material_routing=material_routing,
            active_protocol=active_protocol,
        )
        signature = domain_pilot_protocol_input_signature(protocol_inputs)
        protocol_records[protocol] = {"input_signature": signature}
        previous_record = previous_protocol_records.get(protocol, {})
        previous_scorecard = previous_scorecards_by_protocol.get(protocol, {})
        reusable = (
            isinstance(previous_record, dict)
            and str(previous_record.get("input_signature") or "") == signature
            and domain_pilot_scorecard_is_reusable(root, previous_scorecard)
        )
        if reusable:
            reused_scorecard = dict(previous_scorecard)
            scorecard_path = str(reused_scorecard.get("path") or "")
            if scorecard_path:
                reused_scorecard["content"] = (root / scorecard_path).read_text(encoding="utf-8", errors="replace")
            scorecards.append(reused_scorecard)
            clean_protocols.append(protocol)
        else:
            scorecards.append(
                build_domain_pilot_scorecard(
                    root,
                    protocol_inputs,
                    compiled_at=compiled_at,
                )
            )
            dirty_protocols.append(protocol)
    removed_protocols = sorted(set(previous_scorecards_by_protocol) - set(PROTOCOL_LIBRARY))
    return {
        "domain_pilots": {
            "compiled_at": compiled_at,
            "active_protocol": active_protocol,
            "scorecards": scorecards,
        },
        "state_document": {
            "version": 1,
            "generated_at": compiled_at,
            "active_protocol": active_protocol,
            "protocol_records": protocol_records,
            "scorecards": [domain_pilot_state_scorecard(scorecard) for scorecard in scorecards],
        },
        "dirty_protocols": dirty_protocols,
        "clean_protocols": clean_protocols,
        "removed_protocols": removed_protocols,
    }


def render_domain_pilots_index(domain_pilots: dict[str, Any], compiled_at: str, active_protocol: str) -> str:
    lines = [
        "# 领域 Pilot 总览",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 协议总数：`{len(domain_pilots.get('scorecards', []))}`",
        "",
        "## 协议 Scorecards",
    ]
    for scorecard in domain_pilots.get("scorecards", []):
        metrics = scorecard.get("metrics", {})
        lines.append(
            f"- {workspace_link(scorecard['path'], scorecard['title'])}"
            f" | stage `{scorecard.get('stage', 'seed')}`"
            f" | curated `{int(metrics.get('decisions', 0)) + int(metrics.get('judgments', 0))}`"
            f" | outputs `{metrics.get('outputs', 0)}`"
            f" | receipts `{metrics.get('receipts', 0)}`"
            f" | lifecycle backlog `{metrics.get('lifecycle_concept_backlog', 0)}`"
            f" | retired `{metrics.get('lifecycle_retired_concepts', 0)}`"
            f" | dominant/mixed/bridge `{metrics.get('lifecycle_dominant_concepts', 0)}/{metrics.get('lifecycle_mixed_concepts', 0)}/{metrics.get('lifecycle_bridge_concepts', 0)}`"
        )
        lines.append(f"  - {scorecard.get('summary', '')}")
    lines.extend(
        [
            "",
            "## 相关入口",
            "- [协议总览](./protocols.md)",
            "- [输出 Pack 总览](./output-packs.md)",
            "- [炉心面板](./furnace-center.md)",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_agent_pack(
    role: str,
    title: str,
    mission: str,
    protocol: str,
    compiled_at: str,
    focus: list[str],
    actions: list[str],
    links: list[str],
) -> str:
    frontmatter = render_frontmatter(
        {
            "id": slugify(role),
            "kind": "agent-pack",
            "agent_role": role,
            "title": title,
            "protocol": protocol,
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {title}",
        "",
        f"- Agent role: `{role}`",
        f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
        f"- Compiled at: `{compiled_at}`",
        "",
        "## Mission",
        f"- {mission}",
        "",
        "## Current Focus",
    ]
    if not focus:
        lines.append("- 当前没有额外焦点。")
    else:
        lines.extend(f"- {item}" for item in focus)
    lines.extend(["", "## Suggested Actions"])
    if not actions:
        lines.append("- 当前没有新的建议动作。")
    else:
        lines.extend(f"- {item}" for item in actions)
    lines.extend(["", "## Related Links"])
    if not links:
        lines.append("- 当前没有相关链接。")
    else:
        lines.extend(f"- {item}" for item in links)
    return "\n".join(lines) + "\n"


def render_agent_workbench(
    packs: list[dict[str, str]],
    compiled_at: str,
    active_protocol: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    lifecycle_counts = lifecycle_summary.get("counts", {})
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    dispatch_hints: list[str] = []
    if concept_backlog:
        dispatch_hints.append(
            f"先调 [Review Agent](../../output/agents/review-agent.md)，处理 `{len(concept_backlog)}` 个 lifecycle concept backlog。"
        )
    if lifecycle_counts.get("review_concepts", 0) or lifecycle_counts.get("revisit_concepts", 0):
        dispatch_hints.append(
            f"需要概念整理时，再调 [Concept Agent](../../output/agents/concept-agent.md)，消化 `{lifecycle_counts.get('review_concepts', 0) + lifecycle_counts.get('revisit_concepts', 0)}` 个 review / revisit concept。"
        )
    if retired_concepts:
        dispatch_hints.append(
            f"确认 `{min(len(retired_concepts), 3)}` 个 retired concept 是否要恢复进入工作面，优先走 [Review Agent](../../output/agents/review-agent.md)。"
        )
    if not dispatch_hints:
        dispatch_hints.append("当前 lifecycle governance 较干净，按输出、执行或 ingest 压力决定要调度哪个角色。")
    lines = [
        "# Agent Workbench",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- Agent packs：`{len(packs)}`",
        f"- lifecycle concept backlog / retired：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}` / `{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        "",
        "## 角色总览",
    ]
    if not packs:
        lines.append("- 当前还没有 agent packs。")
    else:
        for pack in packs:
            lines.append(
                f"- [{pack['title']}](../../{pack['path']})"
                f" | role `{pack['role']}`"
                f" | {pack['mission']}"
            )
    lines.extend(
        [
            "",
            "## Lifecycle Governance Summary",
            f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
            f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
            f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
            "",
            "## Lifecycle Dispatch Hints",
        ]
    )
    lines.extend(f"- {hint}" for hint in dispatch_hints)
    lines.extend(["", "## Lifecycle Concept Backlog"])
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(
        [
            "",
            "## 如何使用",
            "1. Human Owner 先在炉心面板里决定今天要调度哪个角色。",
            "2. 进入对应 agent pack，看当前焦点、建议动作和相关链接。",
            "3. 角色之间共享同一个 `raw / wiki / machine memory / decision / judgment`，不维护私有真相。",
            "",
            "## 相关入口",
            "- [炉心面板](./furnace-center.md)",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
            "- [执行审计](./execution-audit.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [图谱视图](./graph-view.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_review_queue(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
    counter_evidence_scan: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    counter_evidence_scan = counter_evidence_scan or {}
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    counter_evidence_pages = [
        dict(item)
        for item in counter_evidence_scan.get("pages", [])
        if isinstance(item, dict)
    ]
    concept_backlog = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"review", "revisit"},
        ),
        active_protocol=active_protocol,
    )
    retired_concepts = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"retired"},
        ),
        active_protocol=active_protocol,
    )
    lines = [
        "# 审阅队列",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 待审决策：`{len(queue['pending_decisions'])}`",
        f"- 待审判断：`{len(queue['pending_judgments'])}`",
        f"- 最近已审项目：`{len(queue['recently_reviewed'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- Counter-evidence candidates：`{len(counter_evidence_pages)}`",
        f"- lifecycle concept backlog：`{len(concept_backlog)}`",
        f"- retired concepts：`{len(retired_concepts)}`",
        "",
        "## 协议审阅焦点",
        *[f"- {line}" for line in PROTOCOL_LIBRARY.get(active_protocol, {}).get("review", [])],
        "",
        "## 待审决策",
    ]
    if not queue["pending_decisions"]:
        lines.append("- 当前没有待审决策。")
    else:
        for page in queue["pending_decisions"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 待审判断"])
    if not queue["pending_judgments"]:
        lines.append("- 当前没有待审判断。")
    else:
        for page in queue["pending_judgments"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 已到期待复审"])
    if not aging["overdue"]:
        lines.append("- 当前没有已到期的决策或判断页面。")
    else:
        for page in aging["overdue"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 需要升级处理"])
    if not aging["escalated"]:
        lines.append("- 当前没有需要升级处理的页面。")
    else:
        for page in aging["escalated"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## Counter-evidence Candidates"])
    if not counter_evidence_pages:
        lines.append("- 当前没有新的 counter-evidence candidate。")
    else:
        for candidate in counter_evidence_pages[:12]:
            lines.append(
                f"- [{candidate.get('page_title') or candidate.get('page_path') or 'unknown'}](../../{candidate.get('page_path', '')})"
                f" | kind `{candidate.get('page_kind', 'unknown')}`"
                f" | candidates `{candidate.get('candidate_count', 0)}`"
                f" | sources `{', '.join(candidate.get('source_ids', [])) or 'none'}`"
                f" | shared `{', '.join(candidate.get('shared_terms', [])) or 'none'}`"
                f" | reason `counter-evidence-candidate`"
            )
    lines.extend(["", "## 生命周期概念待审"])
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle state 标记为 `review` / `revisit` 的 concept。")
    else:
        for entry in concept_backlog[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 已退役概念"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 最近已审"])
    if not queue["recently_reviewed"]:
        lines.append("- 还没有已审阅的决策或判断页面。")
    else:
        for page in queue["recently_reviewed"][:12]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def render_aging_report(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    pages = decisions + judgments
    lifecycle_revisit_entries = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            states={"revisit"},
        ),
        active_protocol=active_protocol,
    )
    retired_concepts = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"retired"},
        ),
        active_protocol=active_protocol,
    )
    lines = [
        "# Aging 报告",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- 已排期复审：`{len(aging['scheduled'])}`",
        f"- 生命周期待回看项：`{len(lifecycle_revisit_entries)}`",
        f"- retired concepts：`{len(retired_concepts)}`",
        "",
        "## 需要升级处理",
    ]
    if not aging["escalated"]:
        lines.append("- 当前没有升级处理项。")
    else:
        for page in aging["escalated"][:20]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 已到期待复审"])
    if not aging["overdue"]:
        lines.append("- 当前没有已到期页面。")
    else:
        for page in aging["overdue"][:20]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 已排期复审"])
    if not aging["scheduled"]:
        lines.append("- 当前没有已排期的复审页面。")
    else:
        for page in aging["scheduled"][:20]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 生命周期待回看项"])
    if not lifecycle_revisit_entries:
        lines.append("- 当前没有 lifecycle state 标记为 `revisit` 的知识项。")
    else:
        for entry in lifecycle_revisit_entries[:20]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 已退役概念"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:20]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 建议动作"])
    if aging["escalated"]:
        lines.append("- 优先处理升级项，补证据、更新状态或明确下一次复审窗口。")
    if aging["overdue"] and not aging["escalated"]:
        lines.append("- 先清理已到期页面，避免 review queue 长期堆积。")
    if lifecycle_revisit_entries:
        lines.append("- 把 lifecycle `revisit` 项和时间窗口型 overdue 项一起看，避免只盯 review date 而忽略证据失效。")
    if not aging["overdue"] and not aging["escalated"]:
        lines.append("- 当前 aging 状态健康，继续通过 nightly 跟踪。")
    stale_reviewed = [
        page
        for page in pages
        if page.get("pending_review") != "true" and page.get("revisit_after")
    ]
    if stale_reviewed:
        lines.append("- 已审页面如仍保留复审窗口，必要时在下一次 review 中收紧或清空。")
    return "\n".join(lines) + "\n"


def render_review_center_html(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    from .app_surfaces import render_review_center_html as _render_review_center_html

    return _render_review_center_html(
        decisions,
        judgments,
        memory,
        compiled_at,
        active_protocol=active_protocol,
        knowledge_lifecycle=knowledge_lifecycle,
    )


def protocol_scorecard(domain_pilots: dict[str, Any], protocol: str) -> dict[str, Any]:
    for scorecard in domain_pilots.get("scorecards", []):
        if isinstance(scorecard, dict) and str(scorecard.get("protocol") or "") == protocol:
            return scorecard
    return {}


def protocol_output_pack_rows(output_packs: dict[str, Any], protocol: str, *, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for pack in output_packs.get("review_packs", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "Review Pack",
                "title": str(pack.get("title") or "Review Pack"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("reasons") or "manual review"),
            }
        )
    for pack in output_packs.get("decision_memos", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "Decision Memo",
                "title": str(pack.get("title") or "Decision Memo"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("reviewed_at") or "reviewed"),
            }
        )
    for pack in output_packs.get("sop_drafts", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "SOP Draft",
                "title": str(pack.get("title") or "SOP Draft"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("risk") or "medium"),
            }
        )
    rows.sort(key=lambda item: (item["kind"], item["title"].lower()))
    return rows[:limit]


def protocol_execution_receipts(execution_audit: dict[str, Any], protocol: str, *, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    protocol_buckets = execution_audit.get("recent_by_protocol", {})
    for bucket_name, label in (("recent_apply", "apply"), ("recent_revert", "revert")):
        bucket_rows = []
        if isinstance(protocol_buckets, dict):
            scoped = protocol_buckets.get(bucket_name, {})
            if isinstance(scoped, dict):
                protocol_rows = scoped.get(protocol, [])
                if isinstance(protocol_rows, list):
                    bucket_rows = protocol_rows
        if not bucket_rows:
            bucket_rows = execution_audit.get(bucket_name, [])
        for record in bucket_rows:
            if str(record.get("protocol") or DEFAULT_PROTOCOL) != protocol:
                continue
            rows.append(
                {
                    "kind": label,
                    "title": str(record.get("title") or record.get("action_id") or "receipt"),
                    "action_id": str(record.get("action_id") or ""),
                    "receipt_path": str(record.get("receipt_path") or ""),
                    "applied_at": str(record.get("applied_at") or ""),
                }
            )
    rows.sort(key=lambda item: (item["applied_at"], item["title"].lower()), reverse=True)
    return rows[:limit]


def furnace_quick_commands(
    active_protocol: str,
    apply_ready_actions: list[dict[str, Any]],
    apply_ready_rewrites: list[dict[str, Any]],
) -> list[str]:
    commands = [
        "PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-status",
        f"PYTHONPATH=src python3 -m aiwiki.cli --root . ask \"对当前主题做协议化总结\" --format report --protocol {active_protocol}",
        "PYTHONPATH=src python3 -m aiwiki.cli --root . nightly",
    ]
    if apply_ready_actions:
        first_action = apply_ready_actions[0]
        action_id = str(first_action.get("id") or "")
        bundle_hint = str(first_action.get("bundle_path") or "")
        if action_id:
            commands.append(
                f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run"
            )
            if bundle_hint:
                commands.append(
                    f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --bundle {bundle_hint}"
                )
    if apply_ready_rewrites:
        first_rewrite = apply_ready_rewrites[0]
        slug = str(first_rewrite.get("slug") or "")
        if slug:
            commands.append(
                f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {slug}"
            )
    return commands[:6]


def render_furnace_center(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    domain_pilots: dict[str, Any],
    execution_audit: dict[str, Any],
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    from .app_surfaces import render_furnace_center as _render_furnace_center

    return _render_furnace_center(
        decisions,
        judgments,
        memory,
        compiled_at,
        protocol_state,
        recent_outputs,
        output_packs,
        domain_pilots,
        execution_audit,
        knowledge_lifecycle=knowledge_lifecycle,
    )


def render_furnace_center_html(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    domain_pilots: dict[str, Any],
    execution_audit: dict[str, Any],
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    from .app_surfaces import render_furnace_center_html as _render_furnace_center_html

    return _render_furnace_center_html(
        decisions,
        judgments,
        memory,
        compiled_at,
        protocol_state,
        recent_outputs,
        output_packs,
        domain_pilots,
        execution_audit,
        knowledge_lifecycle=knowledge_lifecycle,
    )


def render_compile_status(
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    protocol_state: dict[str, Any],
    compiled_at: str,
    *,
    compile_state: dict[str, Any] | None = None,
) -> str:
    from .app_surfaces import render_compile_status as _render_compile_status

    return _render_compile_status(
        entries,
        concepts,
        decisions,
        judgments,
        protocol_state,
        compiled_at,
        compile_state=compile_state,
    )


def render_master_index(
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    protocol_state: dict[str, Any],
    compiled_at: str,
) -> str:
    queue = review_queue(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    aging = collect_aging_signals(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    lines = [
        "# 知识库总索引",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源页：`{len(entries)}`",
        f"- 概念页：`{len(concepts)}`",
        f"- 决策页：`{len(decisions)}`",
        f"- 判断页：`{len(judgments)}`",
        f"- 当前 active protocol：`{protocol_state['active_protocol']}` ({protocol_title(protocol_state['active_protocol'])})",
        f"- 待审项目：`{len(queue['pending_decisions']) + len(queue['pending_judgments'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- 证据漂移：`{sum(1 for page in decisions + judgments if page.get('citation_drift') == 'true')}`",
        "",
        "## 核心页面",
        "- [来源索引](./sources.md)",
        "- [概念索引](./concepts.md)",
        "- [概念质量](./concept-quality.md)",
        "- [决策索引](./decisions.md)",
        "- [判断索引](./judgments.md)",
        "- [判断资产](./judgment-assets.md)",
        "- [Agent Workbench](./agent-workbench.md)",
        "- [认知历史](./cognitive-history.md)",
        "- [协议总览](./protocols.md)",
        "- [炉心面板](./furnace-center.md)",
        "- [执行中心](./execution-center.md)",
        "- [输出 Pack 总览](./output-packs.md)",
        "- [领域 Pilot 总览](./domain-pilots.md)",
        "- [审阅队列](./review-queue.md)",
        "- [审阅中心](./review-center.md)",
        "- [Aging 报告](./aging-report.md)",
        "- [编译状态](./compile-status.md)",
        "- [机器记忆](./machine-memory.md)",
        "- [图谱视图](./graph-view.md)",
        "- [机器记忆拓扑](./machine-memory-topology.md)",
        "- [机器记忆动作队列](./machine-memory-actions.md)",
        "- [机器记忆修复计划](./machine-memory-repair-plan.md)",
        "- [Rewrite Proposals](./rewrite-proposals.md)",
        "- [图谱健康](./graph-health.md)",
        "- [漂移报告](./drift-report.md)",
        "- [修复待办](./repair-backlog.md)",
        "- [操作日志](./log.md)",
        "- [运行时规则](../../schema/index.md)",
        "- [协议规则](../../schema/protocols/index.md)",
        "",
        "## 最近来源",
    ]
    if not entries:
        lines.append("- 还没有登记任何来源。")
    else:
        for entry in sorted(entries, key=lambda item: item["imported_at"], reverse=True)[:8]:
            lines.append(f"- [{entry['title']}](../sources/{entry['id']}.md)")
    lines.extend(["", "## 重点概念"])
    if not concepts:
        lines.append("- 还没有编译出概念页。")
    else:
        for concept in concepts[:10]:
            lines.append(f"- [{concept['title']}](../concepts/{concept['slug']}.md)")
    lines.extend(["", "## 待审项目"])
    if not queue["pending_decisions"] and not queue["pending_judgments"]:
        lines.append("- 当前没有等待审阅的决策或判断页面。")
    else:
        for page in (queue["pending_decisions"] + queue["pending_judgments"])[:8]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 最近决策"])
    if not decisions:
        lines.append("- 还没有回流的决策页面。")
    else:
        for page in decisions[:8]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 最近判断"])
    if not judgments:
        lines.append("- 还没有回流的判断页面。")
    else:
        for page in judgments[:8]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def ensure_wiki_log(root: Path) -> Path:
    ensure_layout(root)
    path = root / "wiki" / "indexes" / "log.md"
    if not path.exists():
        path.write_text("# 知识库日志\n\n", encoding="utf-8")
    return path


def append_wiki_log(root: Path, category: str, title: str, details: list[str]) -> None:
    path = ensure_wiki_log(root)
    timestamp = utc_now()
    lines = [
        f"## [{timestamp}] {category} | {title}",
        "",
        *[f"- {detail}" for detail in details],
        "",
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def remove_stale_generated_concept_pages(root: Path, active_slugs: set[str]) -> int:
    removed = 0
    for path in sorted((root / "wiki" / "concepts").glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if frontmatter.get("kind") != "concept":
            continue
        if frontmatter.get("generated_by") != "aiwiki-compile":
            continue
        concept_id = frontmatter.get("id", "")
        if not isinstance(concept_id, str) or not concept_id.startswith("concept-"):
            continue
        slug = concept_id[len("concept-") :]
        if slug in active_slugs:
            continue
        path.unlink()
        removed += 1
    return removed


def review_packs_dir(root: Path) -> Path:
    return root / "output" / "packs" / "review"


def decision_memos_dir(root: Path) -> Path:
    return root / "output" / "packs" / "decision-memos"


def sop_drafts_dir(root: Path) -> Path:
    return root / "output" / "packs" / "sop-drafts"


def pack_stem(seed: str) -> str:
    cleaned = seed.replace("/", "-").replace("\\", "-").replace(".md", "")
    return slugify(cleaned)[:96] or "pack"


def review_pack_path(root: Path, target_path: str) -> Path:
    return review_packs_dir(root) / f"{pack_stem(target_path)}.md"


def decision_memo_path(root: Path, target_path: str) -> Path:
    return decision_memos_dir(root) / f"{pack_stem(target_path)}.md"


def sop_draft_path(root: Path, action_id: str) -> Path:
    return sop_drafts_dir(root) / f"{pack_stem(action_id)}.md"


def execution_proposals_dir(root: Path) -> Path:
    return root / "wiki" / "execution-proposals"


def execution_proposal_path(root: Path, action_id: str) -> Path:
    return execution_proposals_dir(root) / f"{slugify(action_id)}.md"


def execution_bundles_dir(root: Path) -> Path:
    return root / "output" / "control" / "execution-bundles"


def execution_bundle_path(root: Path, action_id: str) -> Path:
    return execution_bundles_dir(root) / f"{slugify(action_id)}.json"


def execution_receipts_dir(root: Path) -> Path:
    return root / "output" / "control" / "execution-receipts"


def execution_receipt_path(root: Path, action_id: str) -> Path:
    return execution_receipts_dir(root) / f"{slugify(action_id)}.json"
