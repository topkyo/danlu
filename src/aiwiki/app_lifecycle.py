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
    save_knowledge_lifecycle_override_state,
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
from .content.concepts import build_concept_quality
from .content.io import (
    curated_asset_section_snapshot,
    entry_ids_from_paths,
    entry_lookup_maps,
    preserved_section,
    render_curated_asset_sections,
    render_review_history_section,
    review_history_entries,
    routing_snapshot_for_protocol,
    source_summary_or_preview,
)


def default_curated_status(kind: str) -> str:
    if kind == "decision":
        return "proposed"
    if kind == "judgment":
        return "tentative"
    return "filed"


def valid_curated_statuses(kind: str) -> tuple[str, ...]:
    if kind == "decision":
        return DECISION_STATUSES
    if kind == "judgment":
        return JUDGMENT_STATUSES
    return ()


def page_needs_review(kind: str, status: str) -> bool:
    if kind == "decision":
        return status in PENDING_DECISION_REVIEW_STATUSES
    if kind == "judgment":
        return status in PENDING_JUDGMENT_REVIEW_STATUSES
    return False


def evaluate_page_aging(page: dict[str, str], now: datetime | None = None) -> dict[str, str]:
    now = now or datetime.now(timezone.utc)
    revisit_after = parse_iso_datetime(page.get("revisit_after", ""))
    escalate_after = parse_iso_datetime(page.get("escalate_after", ""))
    overdue = bool(revisit_after and revisit_after <= now)
    escalated = bool(escalate_after and escalate_after <= now)
    aging_state = ""
    if escalated:
        aging_state = "escalated"
    elif overdue:
        aging_state = "overdue"
    elif revisit_after:
        aging_state = "scheduled"
    return {
        "revisit_after": revisit_after.replace(microsecond=0).isoformat() if revisit_after else "",
        "escalate_after": escalate_after.replace(microsecond=0).isoformat() if escalate_after else "",
        "aging_state": aging_state,
        "overdue_review": "true" if overdue else "false",
        "escalation_candidate": "true" if escalated else "false",
    }


def collect_aging_signals(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, list[dict[str, str]]]:
    pages = decisions + judgments
    overdue = sorted(
        [page for page in pages if page.get("overdue_review") == "true"],
        key=lambda page: (-page_focus_score(active_protocol, page), page.get("revisit_after", "") or "9999", page["title"].lower()),
    )
    escalated = sorted(
        [page for page in pages if page.get("escalation_candidate") == "true"],
        key=lambda page: (-page_focus_score(active_protocol, page), page.get("escalate_after", "") or "9999", page["title"].lower()),
    )
    scheduled = sorted(
        [page for page in pages if page.get("aging_state") == "scheduled"],
        key=lambda page: (-page_focus_score(active_protocol, page), page.get("revisit_after", "") or "9999", page["title"].lower()),
    )
    return {
        "overdue": overdue,
        "escalated": escalated,
        "scheduled": scheduled,
    }


def display_curated_status(status: str) -> str:
    mapping = {
        "filed": "已归档",
        "proposed": "待决策",
        "approved": "已批准",
        "needs-revisit": "待复审",
        "superseded": "已替代",
        "tentative": "暂定判断",
        "tracking": "持续观察",
        "confirmed": "已确认",
        "rejected": "已否决",
    }
    return mapping.get(status, status or "unknown")


def curated_page_template(
    *,
    kind: str,
    protocol: str,
    title: str,
    artifact_ref: str,
    filed_at: str,
    revisit_after: str,
    escalate_after: str,
    supporting_body: str,
) -> list[str]:
    origin_block = [
        "## Origin",
        f"- Filed from: `{artifact_ref}`",
        f"- Filed at: `{filed_at}`",
        f"- Protocol: `{protocol}`",
        "",
    ]
    if kind == "derived":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Filed Content",
            supporting_body,
        ]
    if kind == "decision":
        if protocol == "investing":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Position Decision",
                "- State the action: observe, build, add, trim, exit, or reject.",
                "",
                "## Scope And Sizing",
                "- Record the position scope, sizing guardrails, or watchlist boundary.",
                "",
                "## Thesis",
                "- Summarize the thesis and the supporting evidence.",
                "",
                "## Evidence",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "",
                "## Bear Case And Invalidation",
                "- Record the counter-thesis, invalidation triggers, and stop conditions.",
                "",
                "## Catalysts And Revisit",
                "- Record the next earnings/event/catalyst and what to monitor before revisiting.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when the action is approved, resized, exited, or invalidated.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        if protocol == "research":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Architecture Decision",
                "- State the action: adopt, reject, defer, migrate, or rollback.",
                "",
                "## Affected Surface",
                "- Record the systems, components, teams, or experiments affected.",
                "",
                "## Evidence",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "",
                "## Validation Plan",
                "- Define the benchmark, test, or rollout signal that would validate this decision.",
                "",
                "## Rollback And Risks",
                "- Record regression risks, rollback path, and explicit failure conditions.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when the rollout result, benchmark, or regression signal changes.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        if protocol == "product":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Product Decision",
                "- State the action: prioritize, launch, roll out, deprecate, or pause.",
                "",
                "## User Problem And Bet",
                "- Record the target user problem, the product bet, and the expected behavior change.",
                "",
                "## Metric And Validation",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "- Name the primary metric, rollout checkpoint, or validation signal.",
                "",
                "## Launch Risks And Rollback",
                "- Record launch blockers, segment risk, and rollback/containment conditions.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when launch readiness, metric movement, or the product bet changes.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        if protocol == "ops":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Incident Decision",
                "- State the action: mitigate, roll back, fail over, isolate, escalate, or follow up.",
                "",
                "## Incident Scope",
                "- Record the impacted service, blast radius, owner, and current operational state.",
                "",
                "## Mitigation Evidence",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "- Name the signal that shows mitigation is working.",
                "",
                "## Residual Risk And Follow-up",
                "- Record rollback/failover paths, residual risk, and follow-up owner.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when the incident state, blast radius, or owner changes.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Decision",
            "- State the concrete decision here.",
            "",
            "## Why",
            "- Summarize the rationale and tradeoffs.",
            "",
            "## Evidence",
            f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
            "",
            "## Risks And Revisit",
            "- Record what could invalidate this decision and when to revisit it.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `proposed`",
            "- Review this page when the decision is approved, superseded, or needs revisit.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "investing":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Investment Judgment",
            "- State the thesis or judgment call here.",
            "",
            "## Drivers And Catalysts",
            f"- Summarize the key drivers and catalysts from `{artifact_ref}` and supporting sources.",
            "",
            "## Risks And Invalidation",
            "- Record the main risks, disconfirming signals, and invalidation conditions.",
            "",
            "## Confidence And Watchlist",
            "- Keep confidence explicit and list the next datapoints to watch.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when the thesis strengthens, weakens, or is invalidated.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "research":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Research Judgment",
            "- State the hypothesis, expected gain, or architecture judgment here.",
            "",
            "## Supporting Evidence",
            f"- Summarize benchmark, experiment, or source evidence from `{artifact_ref}` and `wiki/sources/*.md`.",
            "",
            "## Counter Evidence",
            "- Record the regression risks, weak signals, or conflicting results.",
            "",
            "## Open Questions",
            "- List what remains uncertain and what experiment should resolve it.",
            "",
            "## Confidence And Next Experiment",
            "- Keep confidence explicit and name the next benchmark or follow-up check.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when new benchmark, regression, or experiment evidence arrives.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "product":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Product Judgment",
            "- State the insight, product bet, or launch-readiness judgment here.",
            "",
            "## User Signal And Evidence",
            f"- Summarize user signal, metric evidence, or rollout data from `{artifact_ref}` and supporting sources.",
            "",
            "## Counter Signals",
            "- Record what user, metric, or launch evidence could invalidate this judgment.",
            "",
            "## Confidence And Next Validation",
            "- Keep confidence explicit and name the next validation checkpoint, release, or metric review.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when the signal strengthens, weakens, or the launch plan changes.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "ops":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Ops Judgment",
            "- State the root-cause, blast-radius, or operational-risk judgment here.",
            "",
            "## Incident Evidence",
            f"- Summarize incident timeline, logs, or runbook evidence from `{artifact_ref}` and supporting sources.",
            "",
            "## Counter Evidence",
            "- Record what would falsify this root-cause or operational-risk judgment.",
            "",
            "## Confidence And Follow-up",
            "- Keep confidence explicit and name the next incident review, runbook update, or mitigation check.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when new incident evidence, residual risk, or follow-up status arrives.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    return [
        f"# {title}",
        "",
        *origin_block,
        "## Judgment",
        "- State the judgment call here.",
        "",
        "## Signals",
        f"- Summarize the signals from `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence.",
        "",
        "## Counterevidence",
        "- Record what could make this judgment wrong.",
        "",
        "## Confidence And Follow-up",
        "- Keep confidence explicit and list what to watch next.",
        f"- Default revisit window: `{revisit_after or 'none'}`",
        f"- Default escalation window: `{escalate_after or 'none'}`",
        *render_curated_asset_sections(
            revisit_after=revisit_after,
            escalate_after=escalate_after,
        ),
        "",
        "## Review Status",
        "- Current status: `tentative`",
        "- Review this page when the judgment is confirmed, rejected, or moved to active tracking.",
        "",
        "## Review Notes",
        "- No review has been recorded yet.",
        *render_review_history_section(),
        "",
        "## Supporting Artifact",
        supporting_body,
    ]


def action_needs_review(status: str) -> bool:
    return status in PENDING_ACTION_STATUSES


def display_action_status(status: str) -> str:
    mapping = {
        "proposed": "待处理",
        "accepted": "已接受",
        "deferred": "暂缓",
        "resolved": "已解决",
        "rejected": "已拒绝",
    }
    return mapping.get(status, status or "unknown")


def rewrite_proposal_needs_review(status: str) -> bool:
    return status in PENDING_REWRITE_PROPOSAL_STATUSES


def display_rewrite_proposal_status(status: str) -> str:
    mapping = {
        "proposed": "待审提案",
        "accepted": "已接受提案",
        "deferred": "暂缓提案",
        "applied": "已应用",
        "rejected": "已拒绝",
    }
    return mapping.get(status, status or "unknown")


def rewrite_proposal_status_rank(status: str) -> int:
    return {"proposed": 0, "accepted": 1, "deferred": 2, "applied": 3, "rejected": 4}.get(status, 9)


def transition_profile(
    allowed_transitions: list[str],
    *,
    preferred_transitions: list[str] | None = None,
    default_transition: str = "",
) -> dict[str, Any]:
    allowed = [str(item).strip() for item in allowed_transitions if str(item).strip()]
    preferred = [str(item).strip() for item in (preferred_transitions or []) if str(item).strip() in allowed]
    default_value = str(default_transition or "").strip()
    if default_value not in allowed:
        default_value = preferred[0] if preferred else (allowed[0] if allowed else "")
    return {
        "allowed_transitions": allowed,
        "preferred_transitions": preferred,
        "default_transition": default_value,
    }


def curated_page_transition_profile(kind: str, status: str) -> dict[str, Any]:
    if kind == "decision":
        if status == "proposed":
            return transition_profile(
                ["approved", "needs-revisit", "superseded"],
                preferred_transitions=["approved", "needs-revisit"],
                default_transition="approved",
            )
        if status == "approved":
            return transition_profile(
                ["needs-revisit", "superseded"],
                preferred_transitions=["needs-revisit"],
                default_transition="needs-revisit",
            )
        if status == "needs-revisit":
            return transition_profile(
                ["approved", "superseded"],
                preferred_transitions=["approved"],
                default_transition="approved",
            )
        return transition_profile([])
    if kind == "judgment":
        if status == "tentative":
            return transition_profile(
                ["tracking", "confirmed", "rejected"],
                preferred_transitions=["tracking", "confirmed"],
                default_transition="tracking",
            )
        if status == "tracking":
            return transition_profile(
                ["confirmed", "rejected"],
                preferred_transitions=["confirmed"],
                default_transition="confirmed",
            )
        if status == "confirmed":
            return transition_profile(
                ["tracking", "rejected"],
                preferred_transitions=["tracking"],
                default_transition="tracking",
            )
        return transition_profile([])
    return transition_profile([])


def rewrite_transition_profile(status: str) -> dict[str, Any]:
    if status == "proposed":
        return transition_profile(
            ["accepted", "deferred", "rejected"],
            preferred_transitions=["accepted", "deferred"],
            default_transition="accepted",
        )
    if status == "accepted":
        return transition_profile(
            ["deferred", "rejected"],
            preferred_transitions=["deferred"],
            default_transition="deferred",
        )
    if status == "deferred":
        return transition_profile(
            ["accepted", "rejected"],
            preferred_transitions=["accepted"],
            default_transition="accepted",
        )
    return transition_profile([])


def action_transition_profile(status: str) -> dict[str, Any]:
    if status == "proposed":
        return transition_profile(
            ["accepted", "deferred", "rejected"],
            preferred_transitions=["accepted", "deferred"],
            default_transition="accepted",
        )
    if status == "accepted":
        return transition_profile(
            ["resolved", "deferred", "rejected"],
            preferred_transitions=["resolved", "deferred"],
            default_transition="resolved",
        )
    if status == "deferred":
        return transition_profile(
            ["accepted", "resolved", "rejected"],
            preferred_transitions=["accepted", "resolved"],
            default_transition="accepted",
        )
    return transition_profile([])


def archive_transition_profile(*, can_apply: bool, can_revert: bool) -> dict[str, Any]:
    if can_apply:
        return transition_profile(["apply"], preferred_transitions=["apply"], default_transition="apply")
    if can_revert:
        return transition_profile(["revert"], preferred_transitions=["revert"], default_transition="revert")
    return transition_profile([])


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
        citations = [
            str(path)
            for path in frontmatter.get("citations", [])
            if isinstance(path, str) and path.strip()
        ]
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
                "has_structured_counter_evidence": "true"
                if asset_frontmatter.get("counter_evidence")
                else "false",
                "has_structured_invalidation_rule": "true"
                if str(asset_frontmatter.get("invalidation_rule") or "").strip()
                else "false",
                "has_structured_next_signals": "true"
                if asset_frontmatter.get("next_signals")
                else "false",
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
        page
        for page in decisions + judgments
        if page.get("reviewed_at") and page.get("pending_review") != "true"
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
    citations = [
        str(item)
        for item in frontmatter.get("citations", [])
        if isinstance(item, str) and item.strip()
    ]
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
    source_pages = [
        str(item)
        for item in frontmatter.get("source_pages", [])
        if isinstance(item, str) and item.strip()
    ]
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
        str(reason)
        for reason in override.get("reason_codes", [])
        if isinstance(reason, str) and reason.strip()
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
    current_concept_paths = {
        relative_path(root, path)
        for path in sorted((root / "wiki" / "concepts").glob("*.md"))
    }
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


def knowledge_lifecycle_counts(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_state = {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}
    by_kind = {kind: {"total": 0, "by_state": {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}} for kind in KNOWLEDGE_LIFECYCLE_KINDS}
    invalidated = 0
    active_corpus_linked = 0
    for entry in entries:
        lifecycle_state = str(entry.get("lifecycle_state") or "")
        kind = str(entry.get("kind") or "")
        if lifecycle_state in by_state:
            by_state[lifecycle_state] += 1
        if kind in by_kind:
            by_kind[kind]["total"] += 1
            if lifecycle_state in by_kind[kind]["by_state"]:
                by_kind[kind]["by_state"][lifecycle_state] += 1
        if entry.get("invalidation_signals"):
            invalidated += 1
        if entry.get("active_corpus_ids"):
            active_corpus_linked += 1
    return {
        "total": len(entries),
        "by_state": by_state,
        "by_kind": by_kind,
        "invalidated": invalidated,
        "active_corpus_linked": active_corpus_linked,
    }


def display_knowledge_lifecycle_state(state: str) -> str:
    mapping = {
        "active": "活跃",
        "review": "待审",
        "deferred": "暂挂",
        "retired": "已退役",
        "revisit": "待回看",
    }
    return mapping.get(state, state or "unknown")


def display_judgment_lifecycle_state(state: str) -> str:
    mapping = {
        "formed": "已形成",
        "active": "活跃",
        "under-review": "复审中",
        "revised": "已修订",
        "retired": "已退役",
    }
    return mapping.get(state, state or "unknown")


def display_protocol_relevance_mode(mode: str) -> str:
    mapping = {
        "source-top1": "top1",
        "strong-top2": "strong-top2",
        "cross-protocol-bridge": "bridge-top2",
    }
    return mapping.get(mode, mode or "unknown")


def display_protocol_relevance_ambiguity(state: str) -> str:
    mapping = {
        "dominant": "dominant",
        "mixed": "mixed",
        "bridge": "bridge",
    }
    return mapping.get(state, state or "unknown")


def select_knowledge_lifecycle_entries(
    knowledge_lifecycle: dict[str, Any],
    *,
    kinds: set[str] | None = None,
    states: set[str] | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for entry in knowledge_lifecycle.get("entries", []):
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "")
        lifecycle_state = str(entry.get("lifecycle_state") or "")
        if kinds is not None and kind not in kinds:
            continue
        if states is not None and lifecycle_state not in states:
            continue
        selected.append(dict(entry))
    return selected


def sort_knowledge_lifecycle_entries(
    entries: list[dict[str, Any]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    state_rank = {"revisit": 0, "review": 1, "active": 2, "deferred": 3, "retired": 4}
    return sorted(
        entries,
        key=lambda entry: (
            state_rank.get(str(entry.get("lifecycle_state") or ""), 9),
            0 if str(entry.get("protocol") or "") == active_protocol and active_protocol else 1,
            0 if bool(entry.get("override_active")) else 1,
            -len(entry.get("invalidation_signals", []) if isinstance(entry.get("invalidation_signals"), list) else []),
            -len(entry.get("active_corpus_ids", []) if isinstance(entry.get("active_corpus_ids"), list) else []),
            str(entry.get("title") or "").lower(),
        ),
    )


def render_knowledge_lifecycle_entry_summary(entry: dict[str, Any]) -> str:
    title = str(entry.get("title") or entry.get("page_id") or "unknown")
    path = str(entry.get("path") or "")
    kind = str(entry.get("kind") or "knowledge")
    lifecycle_state = str(entry.get("lifecycle_state") or "")
    parts = [
        f"kind `{kind}`",
        f"state `{display_knowledge_lifecycle_state(lifecycle_state)}`",
    ]
    judgment_lifecycle_state = str(entry.get("judgment_lifecycle_state") or "")
    if kind in {"decision", "judgment"} and judgment_lifecycle_state:
        parts.append(f"judgment_state `{display_judgment_lifecycle_state(judgment_lifecycle_state)}`")
    if bool(entry.get("override_active")):
        parts.append(f"override `{str(entry.get('override_state') or lifecycle_state or 'unknown')}`")
    invalidation_signals = entry.get("invalidation_signals", [])
    if isinstance(invalidation_signals, list) and invalidation_signals:
        parts.append(f"invalidation `{','.join(str(item) for item in invalidation_signals[:3])}`")
    active_corpus_ids = entry.get("active_corpus_ids", [])
    if isinstance(active_corpus_ids, list) and active_corpus_ids:
        parts.append(f"active_corpora `{len(active_corpus_ids)}`")
    review_signal_codes = entry.get("review_signal_codes", [])
    if isinstance(review_signal_codes, list) and review_signal_codes:
        parts.append(f"review_signals `{','.join(str(item) for item in review_signal_codes[:3])}`")
    reason_codes = entry.get("reason_codes", [])
    if isinstance(reason_codes, list) and reason_codes:
        parts.append(f"reasons `{','.join(str(item) for item in reason_codes[:3])}`")
    protocol_relevance_mode = str(entry.get("protocol_relevance_primary_mode") or "")
    if protocol_relevance_mode:
        parts.append(f"protocol_relevance `{display_protocol_relevance_mode(protocol_relevance_mode)}`")
    protocol_relevance_ambiguity = str(entry.get("protocol_relevance_ambiguity") or "")
    if protocol_relevance_ambiguity:
        parts.append(f"protocol_ambiguity `{display_protocol_relevance_ambiguity(protocol_relevance_ambiguity)}`")
    return f"- [{title}](../../{path}) | " + " | ".join(parts)


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
    concept_counts = (
        knowledge_lifecycle.get("counts", {})
        .get("by_kind", {})
        .get("concept", {})
        .get("by_state", {})
    )
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


def concept_protocol_relevance_for_source(
    source_id: str,
    *,
    protocol: str,
    routing_by_entry_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    routing_entry = routing_by_entry_id.get(source_id, {})
    if not isinstance(routing_entry, dict):
        return {}
    top_protocols = [
        str(item.get("protocol") or "")
        for item in routing_entry.get("top_protocols", [])
        if isinstance(item, dict) and str(item.get("protocol") or "")
    ]
    if protocol not in top_protocols[:2]:
        return {}
    routing_snapshot = routing_snapshot_for_protocol(routing_entry, protocol)
    if not routing_snapshot:
        return {}
    selected_as = str(routing_snapshot.get("selected_as") or "")
    if top_protocols[:1] == [protocol]:
        mode = "source-top1"
    elif bool(routing_entry.get("cross_protocol_bridge")) and selected_as in {"hot-evidence", "warm-evidence"}:
        mode = "cross-protocol-bridge"
    elif selected_as in {"hot-evidence", "warm-evidence"}:
        mode = "strong-top2"
    else:
        return {}
    return {
        "source_id": source_id,
        "mode": mode,
        "selected_as": selected_as,
        "total_score": float(routing_snapshot.get("total_score", 0.0) or 0.0),
    }


def concept_protocol_relevance(
    entry: dict[str, Any],
    *,
    protocol: str,
    routing_by_entry_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_ids = [str(item) for item in entry.get("source_ids", []) if isinstance(item, str) and item]
    if not source_ids:
        return {"related": False, "primary_mode": "", "modes": [], "source_ids": []}
    mode_rank = {"source-top1": 0, "cross-protocol-bridge": 1, "strong-top2": 2}
    matched_sources = [
        match
        for match in (
            concept_protocol_relevance_for_source(
                source_id,
                protocol=protocol,
                routing_by_entry_id=routing_by_entry_id,
            )
            for source_id in source_ids
        )
        if match
    ]
    if not matched_sources:
        return {"related": False, "primary_mode": "", "modes": [], "source_ids": []}
    matched_sources.sort(
        key=lambda item: (
            mode_rank.get(str(item.get("mode") or ""), 9),
            -float(item.get("total_score", 0.0) or 0.0),
            str(item.get("source_id") or ""),
        )
    )
    modes: list[str] = []
    matched_source_ids: list[str] = []
    for item in matched_sources:
        mode = str(item.get("mode") or "")
        source_id = str(item.get("source_id") or "")
        if mode and mode not in modes:
            modes.append(mode)
        if source_id and source_id not in matched_source_ids:
            matched_source_ids.append(source_id)
    return {
        "related": True,
        "primary_mode": modes[0] if modes else "",
        "modes": modes,
        "source_ids": matched_source_ids,
    }


def concept_protocol_ambiguity_state(modes: list[str]) -> str:
    normalized = [str(item) for item in modes if isinstance(item, str) and item]
    if "cross-protocol-bridge" in normalized:
        return "bridge"
    if normalized == ["source-top1"]:
        return "dominant"
    return "mixed"


def concept_lifecycle_matches_protocol(
    entry: dict[str, Any],
    *,
    protocol: str,
    routing_by_entry_id: dict[str, dict[str, Any]],
) -> bool:
    return bool(
        concept_protocol_relevance(
            entry,
            protocol=protocol,
            routing_by_entry_id=routing_by_entry_id,
        ).get("related")
    )


def protocol_related_concept_lifecycle_summary(
    knowledge_lifecycle: dict[str, Any] | None,
    material_routing: dict[str, Any] | None,
    *,
    protocol: str,
) -> dict[str, Any]:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    material_routing = material_routing or default_material_routing_state()
    routing_by_entry_id = {
        str(entry.get("entry_id") or ""): entry
        for entry in material_routing.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    mode_counts = {
        "source-top1": 0,
        "strong-top2": 0,
        "cross-protocol-bridge": 0,
    }
    ambiguity_counts = {
        "dominant": 0,
        "mixed": 0,
        "bridge": 0,
    }
    related_entries: list[dict[str, Any]] = []
    for entry in select_knowledge_lifecycle_entries(knowledge_lifecycle, kinds={"concept"}):
        relevance = concept_protocol_relevance(entry, protocol=protocol, routing_by_entry_id=routing_by_entry_id)
        if not relevance.get("related"):
            continue
        primary_mode = str(relevance.get("primary_mode") or "")
        ambiguity = concept_protocol_ambiguity_state(list(relevance.get("modes", [])))
        if primary_mode in mode_counts:
            mode_counts[primary_mode] += 1
        if ambiguity in ambiguity_counts:
            ambiguity_counts[ambiguity] += 1
        related_entries.append(
            {
                **entry,
                "protocol_relevance_primary_mode": primary_mode,
                "protocol_relevance_modes": list(relevance.get("modes", [])),
                "protocol_relevance_source_ids": list(relevance.get("source_ids", [])),
                "protocol_relevance_ambiguity": ambiguity,
            }
        )
    related_concepts = sort_knowledge_lifecycle_entries(related_entries, active_protocol=protocol)
    concept_backlog = [
        entry for entry in related_concepts if str(entry.get("lifecycle_state") or "") in {"review", "revisit"}
    ]
    review_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "review"]
    revisit_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "revisit"]
    retired_concepts = [
        entry for entry in related_concepts if str(entry.get("lifecycle_state") or "") == "retired"
    ]
    ambiguity_watchlist = [
        entry
        for entry in related_concepts
        if str(entry.get("protocol_relevance_ambiguity") or "") in {"mixed", "bridge"}
    ]
    mixed_concepts = [
        entry for entry in ambiguity_watchlist if str(entry.get("protocol_relevance_ambiguity") or "") == "mixed"
    ]
    bridge_concepts = [
        entry for entry in ambiguity_watchlist if str(entry.get("protocol_relevance_ambiguity") or "") == "bridge"
    ]
    return {
        "concept_backlog": concept_backlog,
        "review_concepts": review_concepts,
        "revisit_concepts": revisit_concepts,
        "retired_concepts": retired_concepts,
        "ambiguity_watchlist": ambiguity_watchlist,
        "mixed_concepts": mixed_concepts,
        "bridge_concepts": bridge_concepts,
        "counts": {
            "related_concepts": len(related_concepts),
            "concept_backlog": len(concept_backlog),
            "review_concepts": len(review_concepts),
            "revisit_concepts": len(revisit_concepts),
            "retired_concepts": len(retired_concepts),
            "active_concepts": sum(
                1 for entry in related_concepts if str(entry.get("lifecycle_state") or "") == "active"
            ),
            "direct_related_concepts": mode_counts["source-top1"],
            "secondary_related_concepts": mode_counts["strong-top2"],
            "bridge_related_concepts": mode_counts["cross-protocol-bridge"],
            "dominant_related_concepts": ambiguity_counts["dominant"],
            "mixed_related_concepts": ambiguity_counts["mixed"],
            "ambiguity_bridge_concepts": ambiguity_counts["bridge"],
        },
        "inference_mode": "source-top1-plus-strong-top2-plus-cross-protocol-bridge",
        "ambiguity_mode": "dominant-vs-mixed-vs-bridge",
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
    concept_quality = build_concept_quality(root, concept_memory) if concept_memory else {
        "weak_concepts": [],
        "stable_concepts": [],
    }
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
