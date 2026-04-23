"""Content/source/lifecycle logic extracted from aiwiki.app."""

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
    CAUSAL_RELATION_TYPES,
    CONCEPT_HARDNESS_LEVELS,
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
    RESOLVABLE_MONITOR_ACTION_KINDS,
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
    load_planner_state,
    load_runtime_history,
    manual_link_state_path,
    material_archive_action_id,
    material_archive_state_path,
    material_state_path,
    planner_state_path,
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
from .content.concepts import (  # noqa: F401
    _concept_summary_matches_legacy_placeholder,
    _normalize_summary_snippet,
    build_concept_quality,
    build_concept_records,
    concept_candidates,
    concept_hardness_rank,
    concept_label_to_slug,
    concept_label_to_title,
    concept_quality_band,
    concept_quality_metrics,
    concept_quality_tokens,
    concept_render_signature,
    concept_rewrite_priority,
    concept_rewrite_strategy,
    concept_source_freshness_score,
    concept_source_input_signature,
    concept_source_pages,
    concept_source_signature,
    detect_concept_conflict_signals,
    detect_concept_gap_signals,
    entry_concept_terms,
    normalize_concept_hardness,
    parse_causal_links,
    render_concept_causal_lines,
    render_concept_conflict_lines,
    render_concept_gap_lines,
    render_concept_page,
    render_concept_summary_fallback,
    render_concepts_index,
    render_sources_index,
)
from .content.io import (  # noqa: F401
    active_manual_source_concept_links,
    annotate_recurring_promotion,
    append_review_history_entry,
    collect_output_artifacts,
    collect_output_density_artifacts,
    collect_recent_output_artifacts,
    curated_asset_placeholder_lines,
    curated_asset_section_snapshot,
    entry_ids_from_paths,
    entry_lookup_maps,
    find_promoted_curated_page,
    ingest_source,
    load_source_page_context,
    manifest_change_summary,
    normalized_markdown_section_lines,
    preserved_section,
    recurring_promotion_needs_refresh,
    render_curated_asset_sections,
    render_review_history_section,
    render_source_page,
    render_source_page_with_state,
    review_history_entries,
    routing_snapshot_for_protocol,
    source_summary_or_preview,
    summarize_runtime_event_for_shell,
    sync_manifest_with_raw,
)
from .content.memory import (  # noqa: F401
    PATCH_ROLE_LABELS,
    action_priority_rank,
    action_status_rank,
    action_supports_low_risk_apply,
    append_execution_policy_decisions,
    build_machine_memory_repair_plan,
    build_page_patch_plan,
    collect_machine_memory_action_aging,
    collect_machine_memory_actions,
    describe_machine_memory_action,
    execution_band_label,
    execution_policy_decision_record,
    execution_policy_profile,
    load_execution_policy_decision_history,
    load_execution_receipt_history,
    machine_memory_concept_input_signature,
    machine_memory_source_input_signature,
    patch_mode_for_action,
    patch_role_for_path,
    patch_sections_for_action,
    patch_summary_for_action,
    remove_stale_generated_execution_bundle_files,
    remove_stale_generated_execution_proposal_pages,
    remove_stale_generated_markdown_files,
    safe_apply_preview,
)
from .content.outputs import (  # noqa: F401
    classify_recurring_output_kind,
    normalize_query_signature,
    promotion_page_title,
)


def _validate_rewrite_candidate_markdown(
    candidate_markdown: str,
    slug: str,
    source_signature: str,
    source_pages: list[str],
) -> None:
    frontmatter = parse_frontmatter(candidate_markdown)
    if str(frontmatter.get("id") or "") != f"concept-{slug}":
        raise RuntimeError("Rewrite candidate must preserve the concept id.")
    if str(frontmatter.get("kind") or "") != "concept":
        raise RuntimeError("Rewrite candidate must preserve `kind: concept`.")
    if str(frontmatter.get("source_signature") or "") != source_signature:
        raise RuntimeError("Rewrite candidate source_signature no longer matches the target concept.")
    candidate_source_pages = frontmatter.get("source_pages", [])
    if not isinstance(candidate_source_pages, list):
        raise RuntimeError("Rewrite candidate must preserve source_pages.")
    normalized_candidate_sources = [str(item) for item in candidate_source_pages if isinstance(item, str)]
    if normalized_candidate_sources != source_pages:
        raise RuntimeError("Rewrite candidate source_pages no longer match the target concept.")


def rewrite_proposal_candidate_is_current(root: Path, proposal: dict[str, Any]) -> bool:
    slug = str(proposal.get("slug") or "")
    candidate_markdown = str(proposal.get("candidate_markdown") or "")
    if not slug or not candidate_markdown:
        return False
    concept_path = root / str(proposal.get("target_path") or f"wiki/concepts/{slug}.md")
    if not concept_path.exists():
        return False
    current_frontmatter = parse_frontmatter(concept_path.read_text(encoding="utf-8", errors="replace"))
    current_source_signature = str(current_frontmatter.get("source_signature") or "")
    expected_source_signature = str(proposal.get("source_signature") or "")
    if expected_source_signature and current_source_signature != expected_source_signature:
        return False
    current_source_pages = current_frontmatter.get("source_pages", [])
    if not isinstance(current_source_pages, list):
        return False
    normalized_source_pages = [str(item) for item in current_source_pages if isinstance(item, str)]
    try:
        _validate_rewrite_candidate_markdown(
            candidate_markdown,
            slug,
            expected_source_signature,
            normalized_source_pages,
        )
    except RuntimeError:
        return False
    return True


def rewrite_proposal_is_apply_ready(root: Path, proposal: dict[str, Any]) -> bool:
    return str(proposal.get("status") or "") == "accepted" and rewrite_proposal_candidate_is_current(root, proposal)


def validate_low_risk_action_targets(root: Path, action: dict[str, Any]) -> tuple[str, str]:
    if not bool(action.get("active", True)):
        raise RuntimeError("Machine-memory action is no longer active.")
    source_ids = [str(item) for item in action.get("source_ids", []) if isinstance(item, str)]
    concept_slugs = [str(item) for item in action.get("concept_slugs", []) if isinstance(item, str)]
    if not source_ids or not concept_slugs:
        raise RuntimeError("Low-risk link action is missing source_ids or concept_slugs.")
    source_id = source_ids[0]
    concept_slug = concept_slugs[0]
    manifest = sync_manifest_with_raw(root)
    known_source_ids = {str(entry.get("id") or "") for entry in manifest.get("entries", []) if isinstance(entry, dict)}
    if source_id not in known_source_ids:
        raise RuntimeError("Low-risk link action references a source that is no longer in the manifest.")
    primary_path = root / str(action.get("primary_path") or "")
    secondary_path = root / str(action.get("secondary_path") or "")
    if not primary_path.is_file() or primary_path.stem != source_id:
        raise RuntimeError("Low-risk link action primary source page is missing or no longer matches the source id.")
    if not secondary_path.is_file() or secondary_path.stem != concept_slug:
        raise RuntimeError("Low-risk link action secondary concept page is missing or no longer matches the concept slug.")
    primary_frontmatter = parse_frontmatter(primary_path.read_text(encoding="utf-8", errors="replace"))
    secondary_frontmatter = parse_frontmatter(secondary_path.read_text(encoding="utf-8", errors="replace"))
    if str(primary_frontmatter.get("kind") or "") != "source":
        raise RuntimeError("Low-risk link action primary path is not a source page anymore.")
    if str(secondary_frontmatter.get("kind") or "") != "concept":
        raise RuntimeError("Low-risk link action secondary path is not a concept page anymore.")
    return source_id, concept_slug


def placeholder_concept_slugs(root: Path) -> list[str]:
    slugs: list[str] = []
    for page in sorted((root / "wiki" / "concepts").glob("*.md")):
        content = page.read_text(encoding="utf-8", errors="replace")
        if concept_summary_is_placeholder(content):
            slugs.append(page.stem)
    return slugs


def concept_summary_is_placeholder(markdown: str) -> bool:
    summary = preserved_section(markdown, "Summary", "")
    return _concept_summary_matches_legacy_placeholder(summary)



def proposal_rollback_summary(proposal: dict[str, Any]) -> str:
    preview = proposal.get("safe_apply_preview")
    if isinstance(preview, dict):
        apply_mode = str(preview.get("apply_mode") or "")
        if apply_mode == "manual-link-state":
            return "禁用对应的 manual-link state 条目并重跑 compile。"
        if apply_mode == "citation-snapshot-refresh":
            return "恢复之前的 citation_snapshots metadata 并重跑 compile。"
    return "回滚时需要人工恢复目标页，然后重跑 compile。"


def proposal_impact_score(action: dict[str, Any], proposal: dict[str, Any]) -> int:
    priority_base = {"high": 55, "medium": 35, "low": 20}.get(str(action.get("priority") or proposal.get("priority") or "medium"), 20)
    focus_bonus = min(24, int(action.get("focus_score", 0) or 0) * 3)
    occurrence_bonus = min(12, int(action.get("occurrences", 0) or 0) * 2)
    accepted_bonus = 10 if str(action.get("status") or proposal.get("status") or "") == "accepted" else 0
    escalation_bonus = 8 if str(action.get("escalation_candidate") or "") == "true" else 0
    overdue_bonus = 6 if str(action.get("overdue_review") or "") == "true" else 0
    policy_bonus = 6 if str(action.get("policy_decision") or proposal.get("policy_decision") or "") == "allow" else 0
    return min(100, priority_base + focus_bonus + occurrence_bonus + accepted_bonus + escalation_bonus + overdue_bonus + policy_bonus)


def proposal_dependency_weight(proposal: dict[str, Any]) -> tuple[int, int]:
    kind_rank = {
        "split-concept": 5,
        "expand-concept": 4,
        "connect-source": 3,
        "cross-link": 2,
        "refresh-snapshots": 1,
        "monitor-bridge": 1,
        "manual-repair": 0,
    }
    return (
        kind_rank.get(str(proposal.get("proposal_kind") or "manual-repair"), 0),
        int(proposal.get("impact_score", 0) or 0),
    )


def proposals_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_targets = {str(path) for path in left.get("target_paths", []) if isinstance(path, str) and path}
    right_targets = {str(path) for path in right.get("target_paths", []) if isinstance(path, str) and path}
    if left_targets and right_targets and left_targets.intersection(right_targets):
        return True
    left_sources = {str(item) for item in left.get("source_ids", []) if isinstance(item, str) and item}
    right_sources = {str(item) for item in right.get("source_ids", []) if isinstance(item, str) and item}
    left_concepts = {str(item) for item in left.get("concept_slugs", []) if isinstance(item, str) and item}
    right_concepts = {str(item) for item in right.get("concept_slugs", []) if isinstance(item, str) and item}
    if left_sources and right_sources and left_sources.intersection(right_sources):
        return True
    if left_concepts and right_concepts and left_concepts.intersection(right_concepts):
        return True
    component_id = str(left.get("component_id") or "")
    return bool(component_id) and component_id == str(right.get("component_id") or "")


def derive_proposal_dependencies(proposals: list[dict[str, Any]]) -> None:
    for proposal in proposals:
        current_weight = proposal_dependency_weight(proposal)
        depends_on: list[str] = []
        for candidate in proposals:
            if candidate is proposal:
                continue
            candidate_action_id = str(candidate.get("action_id") or "")
            if not candidate_action_id or not proposals_overlap(proposal, candidate):
                continue
            if proposal_dependency_weight(candidate) <= current_weight:
                continue
            if candidate_action_id not in depends_on:
                depends_on.append(candidate_action_id)
        proposal["depends_on"] = depends_on


def build_planner_state(
    root: Path,
    proposals: list[dict[str, Any]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    previous_state = load_planner_state(root)
    executed_actions = [dict(item) for item in previous_state.get("executed_actions", []) if isinstance(item, dict)]
    proposal_records: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for proposal in proposals:
        action_id = str(proposal.get("action_id") or "")
        depends_on = [str(item) for item in proposal.get("depends_on", []) if isinstance(item, str) and item]
        blocked = bool(depends_on)
        status = str(proposal.get("status") or "proposed")
        is_low_risk = str(proposal.get("risk") or "medium") == "low"
        auto_bundle_candidate = is_low_risk and status == "accepted" and not blocked
        human_required = bool(blocked or not auto_bundle_candidate)
        proposal_record = {
            **proposal,
            "status": status,
            "blocked": blocked,
            "auto_bundle_candidate": auto_bundle_candidate,
            "human_required": human_required,
        }
        proposal_records.append(proposal_record)
        queue_item = {
            "item_id": f"proposal:{action_id}",
            "item_kind": "execution-proposal",
            "action_id": action_id,
            "title": str(proposal.get("title") or action_id),
            "priority": str(proposal.get("priority") or "medium"),
            "status": status,
            "protocol": str(proposal.get("protocol") or active_protocol),
            "impact_score": int(proposal.get("impact_score", 0) or 0),
            "priority_score": int(proposal.get("priority_score", 0) or 0),
            "blocked": blocked,
            "depends_on": depends_on,
            "target_paths": list(proposal.get("target_paths", []) or []),
            "command_hint": str(proposal.get("command_hint") or ""),
            "next_step": str(proposal.get("next_step") or ""),
            "auto_bundle_candidate": auto_bundle_candidate,
            "human_required": human_required,
        }
        queue.append(queue_item)
        nodes.append(
            {
                "action_id": action_id,
                "title": queue_item["title"],
                "priority_score": queue_item["priority_score"],
                "impact_score": queue_item["impact_score"],
                "blocked": blocked,
            }
        )
        edges.extend({"from": action_id, "to": dependency} for dependency in depends_on)
    queue.sort(
        key=lambda item: (
            0 if not item.get("blocked") else 1,
            -int(item.get("priority_score", 0) or 0),
            action_priority_rank(str(item.get("priority") or "medium")),
            str(item.get("title") or "").lower(),
        )
    )
    next_action = queue[0] if queue else {}
    return {
        "version": 1,
        "generated_at": utc_now(),
        "state_path": relative_path(root, planner_state_path(root)),
        "active_protocol": active_protocol,
        "pending_proposals": proposal_records,
        "priority_queue": queue[:12],
        "dependency_graph": {
            "nodes": nodes[:16],
            "edges": edges[:24],
        },
        "next_action": next_action,
        "executed_actions": executed_actions[:16],
        "counts": {
            "pending_proposals": len(proposal_records),
            "blocked": sum(1 for item in queue if item.get("blocked")),
            "unblocked": sum(1 for item in queue if not item.get("blocked")),
            "executed_actions": len(executed_actions),
        },
    }


def repair_execution_proposals(
    root: Path,
    actions: list[dict[str, Any]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    strategy_map = {
        "add-source-concept-link": {
            "kind": "cross-link",
            "risk": "low",
            "summary": "补 source/concept 双向链接，并检查概念摘要是否需要吸收新证据。",
            "edits": [
                "在 source page 里补 concept 引用或相关链接。",
                "在 concept page 的 Related Sources 里加入该 source page。",
                "如果来源提供新证据，重写 concept 摘要并保持 provenance。",
            ],
        },
        "connect-isolated-source": {
            "kind": "connect-source",
            "risk": "medium",
            "summary": "把孤立来源接入至少一个稳定概念，并显式记录依据。",
            "edits": [
                "先从 source page 抽出候选概念。",
                "优先补到现有稳定概念；必要时再新建概念页。",
                "保持 source page 对 raw evidence 的回指。",
            ],
        },
        "expand-singleton-concept": {
            "kind": "expand-concept",
            "risk": "medium",
            "summary": "扩展单节点概念的来源覆盖或相关概念边界。",
            "edits": [
                "补更多来源或相关概念反链。",
                "重写摘要时强调当前证据仍然有限。",
                "如果概念过窄，考虑降级为 source-specific note。",
            ],
        },
        "split-overloaded-concept": {
            "kind": "split-concept",
            "risk": "high",
            "summary": "拆分过载概念，明确子概念边界和来源分流。",
            "edits": [
                "先定义更窄的子概念名称和边界。",
                "把 source pages 重新分流到更具体的概念页。",
                "在原概念页保留拆分说明和跳转链接。",
            ],
        },
        "monitor-bridge-concept": {
            "kind": "monitor-bridge",
            "risk": "low",
            "summary": "记录桥接概念仍然必要的原因，避免误删跨簇连接。",
            "edits": [
                "在 concept page 里补一段 bridge maintenance note。",
                "确认相关概念链接仍然成立。",
                "如果桥接已经失效，再把动作转成 merge 或 split。 ",
            ],
        },
        "refresh-citation-snapshots": {
            "kind": "refresh-snapshots",
            "risk": "low",
            "summary": "刷新 judgment citation snapshot metadata，让 drift / review surface 收敛。",
            "edits": [
                "重建 citation_snapshots metadata，不改正文结论。",
                "确认 provenance 仍指向现有 citation 列表。",
                "执行后重跑 compile，验证 judgment drift 与 review window 是否收敛。",
            ],
        },
    }
    protocol_hints = {
        "general": {
            "summary_suffix": "",
            "edits": [],
        },
        "investing": {
            "summary_suffix": " 同时检查 thesis、risk、catalyst 和 invalidation 是否需要同步更新。",
            "edits": [
                "如果涉及公司/赛道概念，明确 bull / bear evidence、catalyst、risk 和 invalidation。",
                "优先保持 company / thesis / valuation / risk factor 的边界清晰。",
            ],
        },
        "research": {
            "summary_suffix": " 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。",
            "edits": [
                "如果涉及研发概念，明确 benchmark、experiment、architecture tradeoff 和 regression risk。",
                "优先把 next experiment 或 validation path 写清楚。",
            ],
        },
        "product": {
            "summary_suffix": " 同时检查 user problem、metric、launch readiness 和 validation gap 是否需要同步更新。",
            "edits": [
                "如果涉及产品概念，明确 user problem、bet、metric impact 和 launch risk。",
                "优先把 next validation 或 rollout checkpoint 写清楚。",
            ],
        },
        "ops": {
            "summary_suffix": " 同时检查 incident timeline、blast radius、mitigation 和 follow-up 是否需要同步更新。",
            "edits": [
                "如果涉及运维概念，明确 incident 状态、根因判断、残余风险和 follow-up。",
                "优先把 owner、rollback path 或 next review window 写清楚。",
            ],
        },
    }
    proposals: list[dict[str, Any]] = []
    for action in actions:
        template = strategy_map.get(str(action.get("kind") or ""), {})
        action_id = str(action.get("id") or "")
        proposal_protocol = str(action.get("protocol") or active_protocol or DEFAULT_PROTOCOL)
        hint = protocol_hints.get(proposal_protocol, protocol_hints[DEFAULT_PROTOCOL])
        target_paths = [
            path
            for path in (
                str(action.get("primary_path") or ""),
                str(action.get("secondary_path") or ""),
            )
            if path
        ]
        proposal = {
            "id": f"proposal-{action_id}",
            "action_id": action_id,
            "title": str(action.get("title") or ""),
            "priority": str(action.get("priority") or "medium"),
            "status": str(action.get("status") or "proposed"),
            "execution_policy": str(action.get("execution_policy") or "triage"),
            "execution_band": str(action.get("execution_band") or "review-first"),
            "policy_decision": str(action.get("policy_decision") or ""),
            "policy_rule_id": str(action.get("policy_rule_id") or ""),
            "proposal_kind": str(template.get("kind") or "manual-repair"),
            "risk": str(template.get("risk") or "medium"),
            "summary": (
                str(template.get("summary") or action.get("reason") or "")
                + str(hint.get("summary_suffix") or "")
            ).strip(),
            "target_paths": target_paths,
            "suggested_edits": list(template.get("edits") or [str(action.get("reason") or "检查相关页面并补修复说明。")])
            + list(hint.get("edits") or []),
            "command_hint": str(action.get("command_hint") or ""),
            "next_step": str(action.get("next_step") or ""),
            "protocol": proposal_protocol,
            "focus_score": int(action.get("focus_score", 0)),
            "component_id": str(action.get("component_id") or ""),
            "source_ids": [str(item) for item in action.get("source_ids", []) if isinstance(item, str) and item],
            "concept_slugs": [str(item) for item in action.get("concept_slugs", []) if isinstance(item, str) and item],
            "apply_ready": str(action.get("apply_ready") or "false"),
        }
        proposal["page_patch_plan"] = build_page_patch_plan(root, action, active_protocol=proposal_protocol)
        proposal["proposal_path"] = relative_path(root, execution_proposal_path(root, action_id))
        proposal["bundle_path"] = relative_path(root, execution_bundle_path(root, action_id))
        proposal["safe_apply_preview"] = safe_apply_preview(root, action)
        proposal["rollback_summary"] = proposal_rollback_summary(proposal)
        proposal["impact_score"] = proposal_impact_score(action, proposal)
        proposal["priority_score"] = min(
            120,
            int(proposal["impact_score"])
            + {"accepted": 16, "proposed": 8, "deferred": 2}.get(proposal["status"], 0)
            + {"allow": 8, "review": 0, "history": -10}.get(proposal["policy_decision"], 0)
            + {"bundle-safe-apply": 6, "review-first": 0, "manual-repair": -4, "deferred": -8}.get(
                proposal["execution_band"],
                0,
            ),
        )
        proposals.append(proposal)
    derive_proposal_dependencies(proposals)
    for proposal in proposals:
        proposal["priority_score"] = max(
            0,
            int(proposal.get("priority_score", 0) or 0) - (4 * len(proposal.get("depends_on", []))),
        )
    proposals.sort(
        key=lambda item: (
            0 if not item.get("depends_on") else 1,
            action_status_rank(item["status"]),
            -int(item.get("priority_score", 0)),
            -int(item.get("impact_score", 0)),
            action_priority_rank(item["priority"]),
            item["proposal_kind"],
            item["title"].lower(),
        )
    )
    return proposals[:16]



from .app_lifecycle import (  # noqa: E402
    action_needs_review,
    action_transition_profile,
    apply_knowledge_lifecycle_override,
    archive_transition_profile,
    build_concept_lifecycle_entry,
    build_knowledge_lifecycle_document,
    build_knowledge_lifecycle_entry,
    collect_aging_signals,
    collect_curated_pages,
    concept_lifecycle_classification,
    concept_lifecycle_invalidation_signals,
    concept_lifecycle_matches_protocol,
    concept_lifecycle_review_signals,
    concept_protocol_ambiguity_state,
    concept_protocol_relevance,
    concept_protocol_relevance_for_source,
    curated_page_template,
    curated_page_transition_profile,
    default_curated_status,
    display_action_status,
    display_curated_status,
    display_judgment_lifecycle_state,
    display_knowledge_lifecycle_state,
    display_protocol_relevance_ambiguity,
    display_protocol_relevance_mode,
    display_rewrite_proposal_status,
    evaluate_page_aging,
    frontmatter_string_list,
    judgment_asset_frontmatter,
    judgment_lifecycle_profile,
    knowledge_lifecycle_active_corpus_ids,
    knowledge_lifecycle_classification,
    knowledge_lifecycle_counts,
    knowledge_lifecycle_governance_summary,
    knowledge_lifecycle_invalidation_signals,
    page_needs_review,
    protocol_related_concept_lifecycle_summary,
    refresh_knowledge_lifecycle_state,
    render_knowledge_lifecycle_entry_summary,
    review_queue,
    rewrite_proposal_needs_review,
    rewrite_proposal_status_rank,
    rewrite_transition_profile,
    select_knowledge_lifecycle_entries,
    sort_curated_pages,
    sort_knowledge_lifecycle_entries,
    transition_profile,
    valid_curated_statuses,
)
from .app_render import (  # noqa: E402
    append_wiki_log,
    build_domain_pilot_scorecard,
    build_domain_pilots,
    build_domain_pilots_incremental,
    build_output_pack_decision_memos,
    build_output_pack_review_packs,
    build_output_pack_sop_drafts,
    build_output_packs,
    build_output_packs_incremental,
    compact_section_lines,
    decision_memo_path,
    decision_memo_recommendation_lines,
    decision_memo_section_lines,
    decision_memos_dir,
    domain_pilot_protocol_input_signature,
    domain_pilot_protocol_inputs,
    domain_pilot_scorecard_is_reusable,
    domain_pilot_state_scorecard,
    domain_pilots_index_path,
    ensure_wiki_log,
    execution_bundle_path,
    execution_bundles_dir,
    execution_proposal_path,
    execution_proposals_dir,
    execution_receipt_path,
    execution_receipts_dir,
    extract_sop_pattern_frequencies,
    furnace_quick_commands,
    judgment_asset_attention_sort_key,
    judgment_asset_gap_codes,
    judgment_asset_shell_record,
    judgment_asset_summary,
    load_workspace_markdown,
    output_pack_decision_memo_group_input_signature,
    output_pack_group_is_reusable,
    output_pack_lifecycle_summary_input_signature,
    output_pack_repair_plan_candidates,
    output_pack_review_candidates,
    output_pack_review_group_input_signature,
    output_pack_reviewed_candidates,
    output_pack_sop_group_input_signature,
    output_pack_state_records,
    output_pack_version_history_lines,
    pack_stem,
    pack_workspace_link,
    pilot_scorecard_path,
    pilot_scorecards_dir,
    pilot_stage,
    protocol_execution_receipts,
    protocol_output_pack_rows,
    protocol_scorecard,
    remove_stale_generated_concept_pages,
    render_agent_pack,
    render_agent_workbench,
    render_aging_report,
    render_cognitive_history,
    render_compile_status,
    render_curated_index,
    render_curated_page_summary,
    render_domain_pilots_index,
    render_furnace_center,
    render_furnace_center_html,
    render_judgment_assets,
    render_master_index,
    render_output_packs_index,
    render_review_center_html,
    render_review_queue,
    review_pack_path,
    review_packs_dir,
    sop_draft_path,
    sop_drafts_dir,
    sop_pattern_key,
    workspace_file_signature,
    workspace_link,
)
