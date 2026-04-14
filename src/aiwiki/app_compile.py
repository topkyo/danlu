"""Top-level orchestration extracted from aiwiki.app."""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import fcntl
import functools
import hashlib
import html
import json
import os
import re
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import LLMConfig

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
    execution_policy_log_path,
    execution_audit_html_path,
    execution_audit_path,
    execution_center_html_path,
    execution_center_path,
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
    shell_summary_path,
)

from .app_protocol import (
    ACTION_STATUSES,
    AGENT_PACK_LIBRARY,
    AUTO_PROMOTION_MIN_OCCURRENCES,
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

from .app_content import (
    _validate_rewrite_candidate_markdown,
    active_manual_source_concept_links,
    action_needs_review,
    action_supports_low_risk_apply,
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
    curated_page_transition_profile,
    curated_asset_section_snapshot,
    curated_page_template,
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
    review_packs_dir,
    review_history_entries,
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
    concept_page_snapshot,
    concept_rewrite_proposal_digest,
    concept_page_path,
    machine_memory_digest,
    machine_memory_snapshot_is_reusable,
    plan_machine_memory_build,
    question_signature,
    reconcile_active_corpora_state,
    reconcile_concept_rewrite_proposals,
    reconcile_machine_memory_actions,
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
    record_query_route_telemetry,
    render_machine_memory_topology,
    reuse_machine_memory_core,
    summarize_machine_memory_transition,
    upsert_active_corpus,
)

from .app_shell import build_shell_summary, write_shell_summary
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

@dataclass
class Finding:
    severity: str
    path: str
    message: str


@runtime_write_operation
def set_active_protocol(root: Path, protocol: str) -> dict[str, Any]:
    active = resolve_protocol(root, protocol)
    path = protocol_state_path(root)
    path.write_text(json.dumps({"version": 1, "active_protocol": active}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    state = load_protocol_state(root)
    write_if_changed(
        root / "wiki" / "indexes" / "protocols.md",
        render_protocols_dashboard(
            root,
            utc_now(),
            knowledge_lifecycle=load_knowledge_lifecycle_state(root),
        ),
    )
    append_wiki_log(
        root,
        "protocol",
        "switch active protocol",
        [
            f"active_protocol: `{active}`",
            f"state_path: `{state['state_path']}`",
        ],
    )
    return state


def render_protocols_dashboard(
    root: Path,
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    state = load_protocol_state(root)
    active = state["active_protocol"]
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle or load_knowledge_lifecycle_state(root),
        active_protocol=active,
    )
    lifecycle_counts = lifecycle_summary.get("counts", {})
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    lines = [
        "# 协议总览",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前 active protocol：`{active}` ({protocol_title(active)})",
        f"- 协议总数：`{len(state['available_protocols'])}`",
        f"- 状态文件：`{state['state_path']}`",
        f"- lifecycle concept backlog / retired：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}` / `{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        "- 切换命令：`PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-set <slug>`",
        "",
        "## 当前协议入口",
    ]
    for relative in protocol_paths(root, active):
        label = Path(relative).stem
        if label == "index":
            label = "overview"
        lines.append(f"- [{relative}](../../{relative})")
    lines.extend(["", "## 可用协议"])
    for descriptor in state["protocols"]:
        lines.append(
            f"- [{descriptor['title']}](../../{descriptor['paths']['index']})"
            f" | slug `{descriptor['slug']}` | {descriptor['summary']}"
        )
    lines.extend(
        [
            "",
            "## Lifecycle Governance Summary",
            "- 以下 lifecycle backlog 是全局 knowledge plane 工作面，按当前 active protocol 排序，不伪装成 protocol-specific 指标。",
            f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
            f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
            f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
            "",
            "## Lifecycle Concept Backlog",
        ]
    )
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
            "## 运行原则",
            "- 统一 runtime，不复制多个炉子。",
            "- 领域差异优先落在 `schema/protocols/`。",
            "- 查询、回流和审阅默认沿当前 active protocol 执行，但 page frontmatter 会保留显式 protocol 字段。",
            "",
            "## 当前协议语义",
            *protocol_runtime_summary(active),
        ]
    )
    return "\n".join(lines) + "\n"


@runtime_write_operation
def promote_recurring_outputs(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for artifact in collect_output_artifacts(root):
        groups.setdefault((artifact["protocol"], artifact["query_signature"]), []).append(artifact)

    generated_at = utc_now()
    created = 0
    updated = 0
    promotions: list[dict[str, str]] = []
    for (protocol, query_signature), artifacts in sorted(groups.items()):
        if len(artifacts) < AUTO_PROMOTION_MIN_OCCURRENCES:
            continue
        query = artifacts[0]["query"]
        kind = classify_recurring_output_kind(query, protocol)
        if kind not in {"decision", "judgment"}:
            continue
        existing = find_promoted_curated_page(root, kind, query_signature, protocol)
        if existing is None:
            result = file_back(
                root,
                artifacts[-1]["path"],
                title=f"{kind}-{query_signature}",
                kind=kind,
                protocol=protocol,
            )
            page_path = root / result["path"]
            action = "created"
            created += 1
        else:
            if not recurring_promotion_needs_refresh(existing, artifacts):
                continue
            page_path = existing
            action = "updated"
            updated += 1
        annotate_recurring_promotion(
            root,
            page_path,
            kind=kind,
            protocol=protocol,
            query=query,
            query_signature=query_signature,
            artifacts=artifacts,
            generated_at=generated_at,
        )
        promotions.append(
            {
                "kind": kind,
                "action": action,
                "path": relative_path(root, page_path),
                "protocol": protocol,
                "query": query,
                "query_signature": query_signature,
                "occurrences": str(len(artifacts)),
                "latest_artifact": artifacts[-1]["path"],
            }
        )
        append_wiki_log(
            root,
            "promote",
            query,
            [
                f"kind: `{kind}`",
                f"protocol: `{protocol}`",
                f"action: `{action}`",
                f"occurrences: `{len(artifacts)}`",
                f"page: `{relative_path(root, page_path)}`",
                f"latest_artifact: `{artifacts[-1]['path']}`",
            ],
        )

    return {
        "count": len(promotions),
        "created": created,
        "updated": updated,
        "pages": promotions,
    }


def build_agent_packs(
    root: Path,
    entries: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    active_protocol = protocol_state["active_protocol"]
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    health = memory.get("health", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    repair_plan = health.get("repair_plan", {})
    pending_sources = pending_source_summary_ids(root, entries)
    drifted_pages = [page for page in decisions + judgments if page.get("citation_drift") == "true"]
    snapshot_gap_pages = [
        page for page in decisions + judgments if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0
    ]
    missing_asset_pages = [
        page
        for page in decisions + judgments
        if page.get("has_counter_evidence") != "true"
        or page.get("has_invalidation") != "true"
        or page.get("has_next_signals") != "true"
    ]
    ready_actions = repair_plan.get("ready_actions", [])
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    all_actions = [*health.get("actions", []), *health.get("inactive_actions", [])]
    revert_ready_actions = [
        action for action in all_actions if str(action.get("status") or "") == "resolved" and action.get("last_receipt_path")
    ]
    execution_audit = build_execution_audit_snapshot(root, memory, active_protocol=active_protocol)
    packs: list[dict[str, str]] = []
    for spec in AGENT_PACK_LIBRARY:
        role = str(spec["role"])
        title = str(spec["title"])
        mission = str(spec["mission"])
        focus: list[str]
        actions: list[str]
        links: list[str]
        if role == "ingest-agent":
            focus = [
                f"待补来源摘要 `{len(pending_sources)}`",
                f"来源页 `{len(entries)}`",
                f"最近输出 `{len(recent_outputs)}`",
            ]
            actions = [f"补齐 `wiki/sources/{source_id}.md` 的来源摘要。" for source_id in pending_sources[:6]]
            if not actions:
                actions = ["继续观察新投料，并保持 source page 和 raw evidence 对齐。"]
            links = [
                "[来源索引](../../wiki/indexes/sources.md)",
                "[原料收件箱](../../wiki/indexes/Raw Inbox.md)",
                "[采集规则](../../schema/ingest.md)",
            ]
        elif role == "concept-agent":
            focus = [
                f"弱概念页 `{concept_quality.get('counts', {}).get('weak', 0)}`",
                f"冲突信号 `{concept_quality.get('counts', {}).get('conflict_signals', 0)}`",
                f"Rewrite 提案 `{rewrite_state.get('counts', {}).get('active', 0)}`",
            ]
            actions = [
                f"优先重写 `{candidate['path']}`，策略 `{candidate.get('rewrite_strategy', 'n/a')}`。"
                for candidate in concept_quality.get("rewrite_candidates", [])[:5]
            ]
            if not actions:
                actions = ["继续维护 concept 稳定性，确保冲突和证据缺口保持显式。"]
            links = [
                "[概念质量](../../wiki/indexes/concept-quality.md)",
                "[Rewrite 提案](../../wiki/indexes/rewrite-proposals.md)",
                "[概念索引](../../wiki/indexes/concepts.md)",
                "[机器记忆拓扑](../../wiki/indexes/machine-memory-topology.md)",
            ]
        elif role == "judgment-agent":
            focus = [
                f"最近输出 `{len(recent_outputs)}`",
                f"待补判断资产 `{len(missing_asset_pages)}`",
                f"证据漂移页面 `{len(drifted_pages)}`",
            ]
            actions = [
                f"补齐 `{page['path']}` 的反证 / 失效条件 / 下一信号。"
                for page in missing_asset_pages[:5]
            ]
            if recent_outputs:
                actions.append(f"检查最近输出 `{recent_outputs[0]['path']}` 是否值得晋升成 decision / judgment。")
            links = [
                "[判断资产](../../wiki/indexes/judgment-assets.md)",
                "[决策索引](../../wiki/indexes/decisions.md)",
                "[判断索引](../../wiki/indexes/judgments.md)",
                "[认知历史](../../wiki/indexes/cognitive-history.md)",
            ]
        elif role == "review-agent":
            focus = [
                f"待审项目 `{len(queue['pending_decisions']) + len(queue['pending_judgments'])}`",
                f"已到期 / 升级 `{len(aging.get('overdue', []))}` / `{len(aging.get('escalated', []))}`",
                f"证据漂移 / snapshot gap `{len(drifted_pages)}` / `{len(snapshot_gap_pages)}`",
                f"生命周期概念待审 `{len(concept_backlog)}`",
                f"已退役概念 `{len(retired_concepts)}`",
            ]
            actions = [
                f"推进 lifecycle concept `{entry.get('title') or entry.get('page_id') or 'unknown'}`，状态 `{display_knowledge_lifecycle_state(str(entry.get('lifecycle_state') or 'unknown'))}`。"
                for entry in concept_backlog[:3]
            ]
            actions.extend(
                f"复查 `{page['path']}`，因为它已被新证据挑战。"
                for page in drifted_pages[:3]
            )
            if retired_concepts:
                retired = retired_concepts[0]
                actions.append(
                    f"确认 retired concept `{retired.get('title') or retired.get('page_id') or 'unknown'}` 是否需要 re-activate。"
                )
            if not actions:
                actions = [
                    f"推进 `{page['path']}` 的 review 状态。"
                    for page in (queue.get("pending_decisions", []) + queue.get("pending_judgments", []))[:5]
                ]
            actions = actions[:6]
            links = [
                "[审阅队列](../../wiki/indexes/review-queue.md)",
                "[审阅中心](../../wiki/indexes/review-center.md)",
                "[Aging 报告](../../wiki/indexes/aging-report.md)",
                "[概念索引](../../wiki/indexes/concepts.md)",
                "[认知历史](../../wiki/indexes/cognitive-history.md)",
            ]
        elif role == "repair-planner":
            focus = [
                f"动作队列 `{len(health.get('actions', []))}`",
                f"Ready 动作 `{repair_plan.get('counts', {}).get('ready', 0)}`",
                f"执行提案 `{repair_plan.get('counts', {}).get('proposals', 0)}`",
            ]
            actions = [
                f"审阅 `{proposal.get('proposal_path', '')}`，确认 patch step `{len(proposal.get('page_patch_plan', []))}`。"
                for proposal in repair_plan.get("execution_proposals", [])[:5]
            ]
            if not actions:
                actions = ["当前没有新的 execution proposal，继续跟踪 machine-memory actions。"]
            links = [
                "[机器记忆动作队列](../../wiki/indexes/machine-memory-actions.md)",
                "[机器记忆修复计划](../../wiki/indexes/machine-memory-repair-plan.md)",
                "[修复待办](../../wiki/indexes/repair-backlog.md)",
                "[图谱健康](../../wiki/indexes/graph-health.md)",
            ]
        elif role == "execution-agent":
            focus = [
                f"可 apply 动作 `{len(apply_ready_actions)}`",
                f"可 revert 动作 `{len(revert_ready_actions)}`",
                f"执行 receipt `{execution_audit.get('counts', {}).get('receipts', 0)}`",
            ]
            actions = [
                f"对 `{action.get('id', '')}` 先做 `apply-action --dry-run`，再决定是否执行。"
                for action in apply_ready_actions[:5]
            ]
            if revert_ready_actions:
                actions.append(
                    f"必要时回滚 `{revert_ready_actions[0].get('id', '')}`，保持 low-risk execution 可逆。"
                )
            if not actions:
                actions = ["当前没有可执行动作，继续监控 execution audit 和 consistency signals。"]
            links = [
                "[执行中心](../../wiki/indexes/execution-center.md)",
                "[执行审计](../../wiki/indexes/execution-audit.md)",
                "[机器记忆修复计划](../../wiki/indexes/machine-memory-repair-plan.md)",
            ]
        else:
            focus = [
                f"待补来源摘要 `{len(pending_sources)}`",
                f"已到期页面 `{len(aging.get('overdue', []))}`",
                f"证据漂移页面 `{len(drifted_pages)}`",
            ]
            actions = [
                "夜间优先刷新 compile / lint / review queue / cognitive history。",
                "把 recurring outputs 继续晋升成 decision / judgment。",
                "追踪 drift、aging 和 repair backlog，避免知识层长期漂移。",
            ]
            links = [
                "[炉心面板](../../wiki/indexes/furnace-center.md)",
                "[修复待办](../../wiki/indexes/repair-backlog.md)",
                "[认知历史](../../wiki/indexes/cognitive-history.md)",
                "[编译状态](../../wiki/indexes/compile-status.md)",
            ]
        packs.append(
            {
                "role": role,
                "title": title,
                "mission": mission,
                "path": relative_path(root, agent_pack_path(root, role)),
                "content": render_agent_pack(
                    role,
                    title,
                    mission,
                    active_protocol,
                    compiled_at,
                    focus,
                    actions,
                    links,
                ),
            }
        )
    return packs


@runtime_write_operation
def compile_wiki(root: Path) -> dict[str, Any]:
    context = _start_compile_context(root)
    _compile_content_phase(context)
    _compile_runtime_phase(context)
    _compile_output_phase(context)
    return _finalize_compile_phase(context)


@dataclass
class _CompileContext:
    root: Path
    previous_manifest: dict[str, Any]
    manifest: dict[str, Any]
    entries: list[dict[str, Any]]
    compiled_at: str
    protocol_state: dict[str, Any]
    previous_memory: dict[str, Any]
    changed_pages: int = 0
    source_changed_pages: int = 0
    concept_changed_pages: int = 0
    index_changed_pages: int = 0
    maintenance_changed_pages: int = 0
    output_pack_changed_pages: int = 0
    domain_pilot_changed_pages: int = 0
    removed_pages: int = 0
    dirty_index_artifacts: list[str] = field(default_factory=list)
    clean_index_artifacts: list[str] = field(default_factory=list)
    dirty_maintenance_artifacts: list[str] = field(default_factory=list)
    clean_maintenance_artifacts: list[str] = field(default_factory=list)
    previews: dict[str, str] = field(default_factory=dict)
    concepts: list[dict[str, Any]] = field(default_factory=list)
    entry_terms: dict[str, list[str]] = field(default_factory=dict)
    decision_pages: list[dict[str, Any]] = field(default_factory=list)
    judgment_pages: list[dict[str, Any]] = field(default_factory=list)
    dirty_concept_source_ids: list[str] = field(default_factory=list)
    clean_concept_source_ids: list[str] = field(default_factory=list)
    dirty_source_ids: list[str] = field(default_factory=list)
    clean_source_ids: list[str] = field(default_factory=list)
    dirty_concept_slugs: list[str] = field(default_factory=list)
    clean_concept_slugs: list[str] = field(default_factory=list)
    dirty_machine_memory_source_ids: list[str] = field(default_factory=list)
    clean_machine_memory_source_ids: list[str] = field(default_factory=list)
    dirty_machine_memory_concept_slugs: list[str] = field(default_factory=list)
    clean_machine_memory_concept_slugs: list[str] = field(default_factory=list)
    machine_memory_core_reused: bool = False
    memory: dict[str, Any] = field(default_factory=dict)
    execution_audit: dict[str, Any] = field(default_factory=dict)
    transition: dict[str, Any] = field(default_factory=dict)
    dirty_ranking_source_ids: list[str] = field(default_factory=list)
    clean_ranking_source_ids: list[str] = field(default_factory=list)
    dirty_ranking_concept_slugs: list[str] = field(default_factory=list)
    clean_ranking_concept_slugs: list[str] = field(default_factory=list)
    all_outputs: list[dict[str, Any]] = field(default_factory=list)
    recent_outputs: list[dict[str, Any]] = field(default_factory=list)
    active_corpora_state: dict[str, Any] = field(default_factory=dict)
    material_state: dict[str, Any] = field(default_factory=dict)
    material_routing: dict[str, Any] = field(default_factory=dict)
    archive_candidates: dict[str, Any] = field(default_factory=dict)
    knowledge_lifecycle: dict[str, Any] = field(default_factory=dict)
    output_packs: dict[str, Any] = field(default_factory=dict)
    dirty_output_pack_groups: list[str] = field(default_factory=list)
    clean_output_pack_groups: list[str] = field(default_factory=list)
    domain_pilots: dict[str, Any] = field(default_factory=dict)
    dirty_domain_pilot_protocols: list[str] = field(default_factory=list)
    clean_domain_pilot_protocols: list[str] = field(default_factory=list)

    def write_index_artifact(self, destination: Path, content: str) -> int:
        wrote, dirty = write_if_changed_ignoring_timestamps(destination, content)
        relative = relative_path(self.root, destination)
        if dirty:
            self.dirty_index_artifacts.append(relative)
        else:
            self.clean_index_artifacts.append(relative)
        self.changed_pages += int(wrote)
        self.index_changed_pages += int(wrote)
        return int(wrote)

    def write_maintenance_artifact(self, destination: Path, document: dict[str, Any]) -> int:
        wrote, dirty = write_json_document_if_changed_ignoring_generated_timestamps(destination, document)
        relative = relative_path(self.root, destination)
        if dirty:
            self.dirty_maintenance_artifacts.append(relative)
        else:
            self.clean_maintenance_artifacts.append(relative)
        self.changed_pages += int(wrote)
        self.maintenance_changed_pages += int(wrote)
        return int(wrote)

    def write_output_pack_artifact(self, destination: Path, content: str) -> int:
        wrote, _dirty = write_if_changed_ignoring_timestamps(destination, content)
        self.changed_pages += int(wrote)
        self.output_pack_changed_pages += int(wrote)
        return int(wrote)

    def write_domain_pilot_artifact(self, destination: Path, content: str) -> int:
        wrote, _dirty = write_if_changed_ignoring_timestamps(destination, content)
        self.changed_pages += int(wrote)
        self.domain_pilot_changed_pages += int(wrote)
        return int(wrote)


def _start_compile_context(root: Path) -> _CompileContext:
    ensure_layout(root)
    previous_manifest = load_manifest(root)
    manifest = sync_manifest_with_raw(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    return _CompileContext(
        root=root,
        previous_manifest=previous_manifest,
        manifest=manifest,
        entries=entries,
        compiled_at=utc_now(),
        protocol_state=load_protocol_state(root),
        previous_memory=load_json_document(machine_memory_state_path(root)),
    )


def _compile_content_phase(context: _CompileContext) -> None:
    for entry in context.entries:
        source_file = context.root / entry["stored_path"]
        context.previews[entry["id"]] = read_text_preview(source_file)
    context.concepts, context.entry_terms, concept_build = build_concept_records(
        context.root,
        context.entries,
        context.previews,
        generated_at=context.compiled_at,
    )
    context.dirty_concept_source_ids = list(concept_build.get("dirty_concept_source_ids", []))
    context.clean_concept_source_ids = list(concept_build.get("clean_concept_source_ids", []))
    concept_build_state = concept_build.get("state_document", {})
    if not isinstance(concept_build_state, dict):
        concept_build_state = default_concept_build_state()
    write_json_document_if_changed_ignoring_generated_timestamps(concept_build_state_path(context.root), concept_build_state)
    dirty_source_id_set: set[str] = set()
    for entry in context.entries:
        entry_id = str(entry["id"])
        if source_page_requires_compile(context.root, entry, context.entry_terms.get(entry_id, [])):
            context.dirty_source_ids.append(entry_id)
            dirty_source_id_set.add(entry_id)
        else:
            context.clean_source_ids.append(entry_id)
    for entry in context.entries:
        if entry["id"] not in dirty_source_id_set:
            continue
        destination = context.root / "wiki" / "sources" / f"{entry['id']}.md"
        existing_page = destination.read_text(encoding="utf-8", errors="replace") if destination.exists() else ""
        content = render_source_page_with_state(
            entry,
            context.previews[entry["id"]],
            context.compiled_at,
            concepts=context.entry_terms.get(entry["id"], []),
            existing_page=existing_page,
        )
        wrote = int(write_if_changed(destination, content))
        context.source_changed_pages += wrote
        context.changed_pages += wrote

    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "sources.md",
        render_sources_index(context.entries, context.compiled_at),
    )
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "concepts.md",
        render_concepts_index(context.concepts, context.compiled_at),
    )
    context.decision_pages = collect_curated_pages(context.root, "decisions", "decision")
    context.judgment_pages = collect_curated_pages(context.root, "judgments", "judgment")
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "decisions.md",
        render_curated_index("决策索引", "决策列表", context.decision_pages, context.compiled_at),
    )
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "judgments.md",
        render_curated_index("判断索引", "判断列表", context.judgment_pages, context.compiled_at),
    )
    context.write_index_artifact(
        judgment_assets_path(context.root),
        render_judgment_assets(
            context.decision_pages,
            context.judgment_pages,
            context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
        ),
    )
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "index.md",
        render_master_index(
            context.entries,
            context.concepts,
            context.decision_pages,
            context.judgment_pages,
            context.protocol_state,
            context.compiled_at,
        ),
    )
    ensure_wiki_log(context.root)

    concept_lookup = {record["slug"]: record for record in context.concepts}
    dirty_concept_slug_set: set[str] = set()
    for record in context.concepts:
        record["record_lookup"] = concept_lookup
        record["root"] = context.root
        record["render_signature"] = concept_render_signature(context.root, record)
        slug = str(record["slug"])
        if concept_page_requires_compile(context.root, record):
            context.dirty_concept_slugs.append(slug)
            dirty_concept_slug_set.add(slug)
        else:
            context.clean_concept_slugs.append(slug)
    for record in context.concepts:
        if str(record["slug"]) not in dirty_concept_slug_set:
            continue
        destination = context.root / "wiki" / "concepts" / f"{record['slug']}.md"
        existing_page = destination.read_text(encoding="utf-8", errors="replace") if destination.exists() else ""
        wrote = int(write_if_changed(destination, render_concept_page(record, context.compiled_at, existing_page)))
        context.changed_pages += wrote
        context.concept_changed_pages += wrote

    context.removed_pages += remove_stale_generated_concept_pages(
        context.root,
        {record["slug"] for record in context.concepts},
    )


def _curated_page_scan_record(root: Path, page: dict[str, str]) -> dict[str, Any]:
    page_path = root / str(page.get("path") or "")
    content = page_path.read_text(encoding="utf-8", errors="replace") if page_path.exists() else ""
    frontmatter = parse_frontmatter(content)
    citations = [
        str(path)
        for path in frontmatter.get("citations", [])
        if isinstance(path, str) and path.strip()
    ]
    tokens = set(tokenize(f"{page.get('title', '')}\n{strip_frontmatter(content)}"))
    return {
        "citations": citations,
        "frontmatter": frontmatter,
        "tokens": tokens,
    }


def _counter_evidence_scan_phase(context: _CompileContext) -> dict[str, Any]:
    entry_by_id = {str(entry["id"]): entry for entry in context.entries}
    dirty_source_ids = [source_id for source_id in context.dirty_source_ids if source_id in entry_by_id]
    if not dirty_source_ids:
        return {"generated_at": context.compiled_at, "candidate_count": 0, "candidates": [], "pages": []}
    path_to_entry_id = entry_lookup_maps(context.manifest.get("entries", []))[1]
    candidates: list[dict[str, Any]] = []
    page_summaries: list[dict[str, Any]] = []
    for page in context.decision_pages + context.judgment_pages:
        scan_record = _curated_page_scan_record(context.root, page)
        cited_source_ids = set(entry_ids_from_paths(path_to_entry_id, scan_record["citations"]))
        page_candidates: list[dict[str, Any]] = []
        for source_id in dirty_source_ids:
            if source_id in cited_source_ids:
                continue
            source_entry = entry_by_id.get(source_id, {})
            source_terms = {
                token
                for label in context.entry_terms.get(source_id, [])
                for token in tokenize(label)
            }
            source_terms.update(tokenize(f"{source_entry.get('title', '')}\n{context.previews.get(source_id, '')}"))
            overlap = sorted(source_terms & scan_record["tokens"])
            if len(overlap) < 2:
                continue
            candidate = {
                "candidate_id": f"{page.get('page_id', '')}:{source_id}",
                "page_id": str(page.get("page_id") or ""),
                "page_path": str(page.get("path") or ""),
                "page_title": str(page.get("title") or ""),
                "page_kind": str(page.get("kind") or ""),
                "page_status": str(page.get("status") or ""),
                "protocol": str(page.get("protocol") or DEFAULT_PROTOCOL),
                "source_id": source_id,
                "source_title": str(source_entry.get("title") or source_id),
                "source_page": f"wiki/sources/{source_id}.md",
                "shared_terms": overlap[:8],
                "shared_term_count": len(overlap),
                "reason_code": "counter-evidence-candidate",
            }
            page_candidates.append(candidate)
            candidates.append(candidate)
        if page_candidates:
            page_summaries.append(
                {
                    "page_id": str(page.get("page_id") or ""),
                    "page_path": str(page.get("path") or ""),
                    "page_title": str(page.get("title") or ""),
                    "page_kind": str(page.get("kind") or ""),
                    "page_status": str(page.get("status") or ""),
                    "protocol": str(page.get("protocol") or DEFAULT_PROTOCOL),
                    "candidate_count": len(page_candidates),
                    "source_ids": [candidate["source_id"] for candidate in page_candidates],
                    "source_pages": [candidate["source_page"] for candidate in page_candidates],
                    "shared_terms": sorted(
                        {
                            term
                            for candidate in page_candidates
                            for term in candidate.get("shared_terms", [])
                        }
                    )[:10],
                }
            )
    candidates.sort(
        key=lambda item: (
            0 if item.get("page_kind") == "judgment" else 1,
            -int(item.get("shared_term_count", 0)),
            str(item.get("page_title") or "").lower(),
            str(item.get("source_title") or "").lower(),
        )
    )
    page_summaries.sort(
        key=lambda item: (
            0 if item.get("page_kind") == "judgment" else 1,
            -int(item.get("candidate_count", 0)),
            str(item.get("page_title") or "").lower(),
        )
    )
    return {
        "generated_at": context.compiled_at,
        "candidate_count": len(candidates),
        "candidates": candidates[:32],
        "pages": page_summaries[:16],
    }


def _build_judgment_review_actions(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    aging: dict[str, list[dict[str, str]]],
    counter_evidence_scan: dict[str, Any],
) -> list[dict[str, Any]]:
    page_by_path = {
        str(page.get("path") or ""): page
        for page in decisions + judgments
        if str(page.get("path") or "")
    }
    action_by_path: dict[str, dict[str, Any]] = {}
    priority_rank = {"high": 0, "medium": 1, "low": 2}

    def add_action(page: dict[str, str], reason_code: str, *, priority: str, candidate_count: int = 0) -> None:
        page_path = str(page.get("path") or "")
        if not page_path:
            return
        current = action_by_path.get(page_path)
        if current is None:
            profile = curated_page_transition_profile(
                str(page.get("kind") or ""),
                str(page.get("status") or ""),
            )
            default_transition = str(profile.get("default_transition") or page.get("status") or "")
            current = {
                "id": f"review-{slugify(str(page.get('page_id') or Path(page_path).stem))}",
                "title": f"Review {str(page.get('title') or Path(page_path).stem)}",
                "page_id": str(page.get("page_id") or Path(page_path).stem),
                "page_path": page_path,
                "page_kind": str(page.get("kind") or ""),
                "protocol": str(page.get("protocol") or DEFAULT_PROTOCOL),
                "status": "open",
                "priority": priority,
                "reason_codes": [],
                "candidate_count": 0,
                "review_command": (
                    f"PYTHONPATH=src python3 -m aiwiki.cli --root . review-page {page_path} --status {default_transition}"
                    if default_transition
                    else ""
                ),
            }
            action_by_path[page_path] = current
        if reason_code and reason_code not in current["reason_codes"]:
            current["reason_codes"].append(reason_code)
        current["candidate_count"] = max(int(current.get("candidate_count", 0)), candidate_count)
        if priority_rank.get(priority, 9) < priority_rank.get(str(current.get("priority") or "medium"), 9):
            current["priority"] = priority

    for page in aging.get("escalated", []):
        add_action(page, "escalation-candidate", priority="high")
    for page in aging.get("overdue", []):
        add_action(page, "overdue-review", priority="high" if page.get("kind") == "judgment" else "medium")
    for candidate in counter_evidence_scan.get("pages", []):
        if not isinstance(candidate, dict):
            continue
        page = page_by_path.get(str(candidate.get("page_path") or ""))
        if page is None:
            continue
        add_action(
            page,
            "counter-evidence-candidate",
            priority="high" if int(candidate.get("candidate_count", 0) or 0) > 1 else "medium",
            candidate_count=int(candidate.get("candidate_count", 0) or 0),
        )
    actions = list(action_by_path.values())
    actions.sort(
        key=lambda item: (
            priority_rank.get(str(item.get("priority") or "medium"), 9),
            0 if item.get("page_kind") == "judgment" else 1,
            -int(item.get("candidate_count", 0) or 0),
            str(item.get("title") or "").lower(),
        )
    )
    return actions


def _compile_runtime_phase(context: _CompileContext) -> None:
    machine_memory_build = plan_machine_memory_build(
        context.root,
        context.entries,
        context.concepts,
        context.previews,
        context.entry_terms,
        generated_at=context.compiled_at,
    )
    machine_memory_build_state = machine_memory_build.get("state_document", {})
    if not isinstance(machine_memory_build_state, dict):
        machine_memory_build_state = default_machine_memory_build_state()
    write_json_document_if_changed_ignoring_generated_timestamps(
        machine_memory_build_state_path(context.root),
        machine_memory_build_state,
    )
    context.dirty_machine_memory_source_ids = list(machine_memory_build.get("dirty_source_ids", []))
    context.clean_machine_memory_source_ids = list(machine_memory_build.get("clean_source_ids", []))
    context.dirty_machine_memory_concept_slugs = list(machine_memory_build.get("dirty_concept_slugs", []))
    context.clean_machine_memory_concept_slugs = list(machine_memory_build.get("clean_concept_slugs", []))
    context.machine_memory_core_reused = bool(
        machine_memory_build.get("inputs_clean")
        and machine_memory_snapshot_is_reusable(context.previous_memory)
    )
    if context.machine_memory_core_reused:
        context.memory = reuse_machine_memory_core(context.previous_memory, context.compiled_at)
    else:
        context.memory = build_machine_memory(
            context.root,
            context.entries,
            context.concepts,
            context.previews,
            context.entry_terms,
            context.compiled_at,
        )
    context.memory = attach_judgment_assets_to_machine_memory(
        context.root,
        context.memory,
        context.decision_pages,
        context.judgment_pages,
    )
    context.memory["health"] = build_machine_memory_health(context.memory)
    context.memory["health"].update(
        reconcile_machine_memory_actions(
            context.root,
            context.memory["health"],
            compiled_at=context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
        )
    )
    context.memory["health"]["repair_plan"] = build_machine_memory_repair_plan(
        context.root,
        context.memory["health"],
        active_protocol=context.protocol_state["active_protocol"],
    )
    planner_state = dict(context.memory["health"]["repair_plan"].get("planner_state") or {})
    planner_state["state_path"] = relative_path(context.root, planner_state_path(context.root))
    planner_state["generated_at"] = str(planner_state.get("generated_at") or context.compiled_at)
    context.memory["health"]["repair_plan"]["planner_state"] = planner_state
    context.write_maintenance_artifact(planner_state_path(context.root), planner_state)
    route_telemetry = load_json_document(query_route_telemetry_path(context.root))
    if not isinstance(route_telemetry, dict):
        route_telemetry = {}
    route_telemetry.setdefault("version", 1)
    route_telemetry.setdefault("entries", [])
    route_telemetry.setdefault("strategy_counts", {})
    route_telemetry.setdefault("protocol_counts", {})
    route_telemetry.setdefault("last_entry", {})
    route_telemetry["updated_at"] = str(route_telemetry.get("updated_at") or context.compiled_at)
    route_telemetry["state_path"] = relative_path(context.root, query_route_telemetry_path(context.root))
    context.write_maintenance_artifact(query_route_telemetry_path(context.root), route_telemetry)
    policy_decisions = [
        execution_policy_decision_record(
            action,
            occurred_at=context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
        )
        for action in [
            *context.memory["health"].get("actions", []),
            *context.memory["health"].get("inactive_actions", []),
        ]
        if isinstance(action, dict) and action.get("id")
    ]
    append_execution_policy_decisions(context.root, policy_decisions)
    context.memory["health"]["concept_quality"] = build_concept_quality(context.root, context.memory)
    context.memory["health"]["concept_rewrite"] = reconcile_concept_rewrite_proposals(
        context.root,
        context.memory["health"]["concept_quality"],
        compiled_at=context.compiled_at,
    )
    aging = collect_aging_signals(
        context.decision_pages,
        context.judgment_pages,
        active_protocol=context.protocol_state["active_protocol"],
    )
    context.memory["health"]["counter_evidence_scan"] = _counter_evidence_scan_phase(context)
    context.memory["health"]["judgment_review_actions"] = _build_judgment_review_actions(
        context.decision_pages,
        context.judgment_pages,
        aging=aging,
        counter_evidence_scan=context.memory["health"]["counter_evidence_scan"],
    )
    context.memory["digest"] = machine_memory_digest(context.memory)
    graph = build_machine_memory_graph(context.memory)
    context.memory["graph_digest"] = graph["digest"]
    context.memory["graph_path"] = relative_path(context.root, machine_memory_graph_path(context.root))
    context.memory["history_path"] = relative_path(context.root, machine_memory_history_path(context.root))
    context.transition = summarize_machine_memory_transition(context.previous_memory, context.memory)
    context.memory["transition"] = context.transition
    context.write_index_artifact(
        machine_memory_state_path(context.root),
        json.dumps(context.memory, indent=2, sort_keys=True) + "\n",
    )
    context.write_index_artifact(
        machine_memory_graph_path(context.root),
        json.dumps(graph, indent=2, sort_keys=True) + "\n",
    )
    context.write_index_artifact(
        machine_memory_graph_html_path(context.root),
        render_machine_memory_graph_html(context.memory, graph),
    )
    append_machine_memory_history(context.root, context.memory, context.transition)
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "machine-memory.md",
        render_machine_memory_index(context.memory),
    )
    context.write_index_artifact(machine_memory_topology_path(context.root), render_machine_memory_topology(context.memory))
    context.write_index_artifact(machine_memory_actions_path(context.root), render_machine_memory_actions(context.memory))
    context.write_index_artifact(
        machine_memory_repair_plan_path(context.root),
        render_machine_memory_repair_plan(context.memory),
    )
    context.write_index_artifact(
        execution_center_path(context.root),
        render_execution_center(
            context.memory,
            compiled_at=context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
        ),
    )
    context.execution_audit = build_execution_audit_snapshot(
        context.root,
        context.memory,
        active_protocol=context.protocol_state["active_protocol"],
    )
    context.write_index_artifact(
        execution_audit_path(context.root),
        render_execution_audit(context.execution_audit),
    )
    ranking_build = build_ranking_state(
        context.root,
        context.entries,
        context.concepts,
        generated_at=context.compiled_at,
    )
    ranking_build_state = ranking_build.get("state_document", {})
    if not isinstance(ranking_build_state, dict):
        ranking_build_state = default_ranking_build_state()
    write_json_document_if_changed_ignoring_generated_timestamps(
        ranking_build_state_path(context.root),
        ranking_build_state,
    )
    context.dirty_ranking_source_ids = list(ranking_build.get("dirty_source_ids", []))
    context.clean_ranking_source_ids = list(ranking_build.get("clean_source_ids", []))
    context.dirty_ranking_concept_slugs = list(ranking_build.get("dirty_concept_slugs", []))
    context.clean_ranking_concept_slugs = list(ranking_build.get("clean_concept_slugs", []))
    context.all_outputs = collect_output_density_artifacts(context.root)
    context.recent_outputs = collect_recent_output_artifacts(context.root)
    material_state_documents = build_material_state_documents(
        context.root,
        generated_at=context.compiled_at,
        entries=context.entries,
        active_protocol=context.protocol_state["active_protocol"],
    )
    context.active_corpora_state = material_state_documents["active_corpora_state"]
    context.material_state = material_state_documents["material_state"]
    context.material_routing = material_state_documents["material_routing"]
    context.archive_candidates = material_state_documents["archive_candidates"]
    context.knowledge_lifecycle = build_knowledge_lifecycle_document(
        context.root,
        generated_at=context.compiled_at,
        decisions=context.decision_pages,
        judgments=context.judgment_pages,
        entries=context.entries,
        active_corpora_state=context.active_corpora_state,
        memory=context.memory,
    )
    context.write_maintenance_artifact(material_state_path(context.root), context.material_state)
    context.write_maintenance_artifact(material_routing_state_path(context.root), context.material_routing)
    context.write_maintenance_artifact(archive_candidates_state_path(context.root), context.archive_candidates)
    context.write_maintenance_artifact(knowledge_lifecycle_state_path(context.root), context.knowledge_lifecycle)
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "protocols.md",
        render_protocols_dashboard(
            context.root,
            context.compiled_at,
            knowledge_lifecycle=context.knowledge_lifecycle,
        ),
    )


def _compile_output_phase(context: _CompileContext) -> None:
    output_pack_build = build_output_packs_incremental(
        context.root,
        context.decision_pages,
        context.judgment_pages,
        context.memory,
        context.protocol_state,
        context.recent_outputs,
        context.compiled_at,
        knowledge_lifecycle=context.knowledge_lifecycle,
    )
    output_pack_build_state = output_pack_build.get("state_document", {})
    if not isinstance(output_pack_build_state, dict):
        output_pack_build_state = default_output_pack_build_state()
    write_json_document_if_changed_ignoring_generated_timestamps(
        output_pack_build_state_path(context.root),
        output_pack_build_state,
    )
    context.output_packs = output_pack_build.get("output_packs", {})
    if not isinstance(context.output_packs, dict):
        context.output_packs = default_output_pack_build_state()
    context.dirty_output_pack_groups = list(output_pack_build.get("dirty_groups", []))
    context.clean_output_pack_groups = list(output_pack_build.get("clean_groups", []))
    dirty_output_pack_group_set = set(context.dirty_output_pack_groups)
    context.write_output_pack_artifact(
        output_packs_index_path(context.root),
        render_output_packs_index(context.output_packs, context.compiled_at, context.protocol_state["active_protocol"]),
    )
    if "review_packs" in dirty_output_pack_group_set:
        for pack in context.output_packs.get("review_packs", []):
            if isinstance(pack, dict) and "content" in pack:
                context.write_output_pack_artifact(context.root / str(pack["path"]), str(pack["content"]))
        context.removed_pages += remove_stale_generated_markdown_files(
            review_packs_dir(context.root),
            {
                Path(str(pack["path"])).stem
                for pack in context.output_packs.get("review_packs", [])
                if isinstance(pack, dict)
            },
        )
    if "decision_memos" in dirty_output_pack_group_set:
        for pack in context.output_packs.get("decision_memos", []):
            if isinstance(pack, dict) and "content" in pack:
                context.write_output_pack_artifact(context.root / str(pack["path"]), str(pack["content"]))
        context.removed_pages += remove_stale_generated_markdown_files(
            decision_memos_dir(context.root),
            {
                Path(str(pack["path"])).stem
                for pack in context.output_packs.get("decision_memos", [])
                if isinstance(pack, dict)
            },
        )
    if "sop_drafts" in dirty_output_pack_group_set:
        for pack in context.output_packs.get("sop_drafts", []):
            if isinstance(pack, dict) and "content" in pack:
                context.write_output_pack_artifact(context.root / str(pack["path"]), str(pack["content"]))
        context.removed_pages += remove_stale_generated_markdown_files(
            sop_drafts_dir(context.root),
            {
                Path(str(pack["path"])).stem
                for pack in context.output_packs.get("sop_drafts", [])
                if isinstance(pack, dict)
            },
        )
    domain_pilot_build = build_domain_pilots_incremental(
        context.root,
        context.decision_pages,
        context.judgment_pages,
        context.memory,
        context.protocol_state,
        context.recent_outputs,
        context.all_outputs,
        context.output_packs,
        context.execution_audit,
        context.compiled_at,
        knowledge_lifecycle=context.knowledge_lifecycle,
        material_routing=context.material_routing,
    )
    domain_pilot_build_state = domain_pilot_build.get("state_document", {})
    if not isinstance(domain_pilot_build_state, dict):
        domain_pilot_build_state = default_domain_pilot_build_state()
    write_json_document_if_changed_ignoring_generated_timestamps(
        domain_pilot_build_state_path(context.root),
        domain_pilot_build_state,
    )
    context.domain_pilots = domain_pilot_build.get("domain_pilots", {})
    if not isinstance(context.domain_pilots, dict):
        context.domain_pilots = {
            "compiled_at": context.compiled_at,
            "active_protocol": context.protocol_state["active_protocol"],
            "scorecards": [],
        }
    context.dirty_domain_pilot_protocols = list(domain_pilot_build.get("dirty_protocols", []))
    context.clean_domain_pilot_protocols = list(domain_pilot_build.get("clean_protocols", []))
    dirty_domain_pilot_protocol_set = set(context.dirty_domain_pilot_protocols)
    context.write_domain_pilot_artifact(
        domain_pilots_index_path(context.root),
        render_domain_pilots_index(context.domain_pilots, context.compiled_at, context.protocol_state["active_protocol"]),
    )
    for scorecard in context.domain_pilots.get("scorecards", []):
        if (
            isinstance(scorecard, dict)
            and str(scorecard.get("protocol") or "") in dirty_domain_pilot_protocol_set
            and "content" in scorecard
        ):
            context.write_domain_pilot_artifact(context.root / str(scorecard["path"]), str(scorecard["content"]))
    if context.dirty_domain_pilot_protocols or domain_pilot_build.get("removed_protocols"):
        context.removed_pages += remove_stale_generated_markdown_files(
            pilot_scorecards_dir(context.root),
            {
                Path(str(scorecard["path"])).stem
                for scorecard in context.domain_pilots.get("scorecards", [])
                if isinstance(scorecard, dict)
            },
        )
    agent_packs = build_agent_packs(
        context.root,
        context.entries,
        context.decision_pages,
        context.judgment_pages,
        context.memory,
        context.protocol_state,
        context.recent_outputs,
        context.compiled_at,
        knowledge_lifecycle=context.knowledge_lifecycle,
    )
    context.write_index_artifact(
        agent_workbench_path(context.root),
        render_agent_workbench(
            agent_packs,
            context.compiled_at,
            context.protocol_state["active_protocol"],
            knowledge_lifecycle=context.knowledge_lifecycle,
        ),
    )
    for pack in agent_packs:
        context.write_index_artifact(context.root / pack["path"], pack["content"])
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "furnace-center.md",
        render_furnace_center(
            context.decision_pages,
            context.judgment_pages,
            context.memory,
            context.compiled_at,
            context.protocol_state,
            context.recent_outputs,
            context.output_packs,
            context.domain_pilots,
            context.execution_audit,
            knowledge_lifecycle=context.knowledge_lifecycle,
        ),
    )
    context.write_index_artifact(
        review_center_html_path(context.root),
        render_review_center_html(
            context.decision_pages,
            context.judgment_pages,
            context.memory,
            context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
            knowledge_lifecycle=context.knowledge_lifecycle,
        ),
    )
    context.write_index_artifact(
        furnace_center_html_path(context.root),
        render_furnace_center_html(
            context.decision_pages,
            context.judgment_pages,
            context.memory,
            context.compiled_at,
            context.protocol_state,
            context.recent_outputs,
            context.output_packs,
            context.domain_pilots,
            context.execution_audit,
            knowledge_lifecycle=context.knowledge_lifecycle,
        ),
    )
    context.write_index_artifact(
        execution_center_html_path(context.root),
        render_execution_center_html(
            context.memory,
            compiled_at=context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
        ),
    )
    context.write_index_artifact(
        execution_audit_html_path(context.root),
        render_execution_audit_html(context.execution_audit),
    )
    context.write_index_artifact(concept_quality_path(context.root), render_concept_quality(context.memory))
    context.write_index_artifact(
        concept_rewrite_index_path(context.root),
        render_concept_rewrite_index(context.memory["health"]["concept_rewrite"], context.compiled_at),
    )
    for proposal in context.memory["health"]["concept_rewrite"].get("all_proposals", []):
        context.write_index_artifact(
            context.root / proposal["proposal_path"],
            render_concept_rewrite_proposal_page(proposal),
        )
    context.removed_pages += remove_stale_generated_execution_proposal_pages(
        context.root,
        {
            str(proposal.get("action_id") or "")
            for proposal in context.memory["health"]["repair_plan"].get("execution_proposals", [])
            if proposal.get("action_id")
        },
    )
    context.removed_pages += remove_stale_generated_execution_bundle_files(
        context.root,
        {
            str(proposal.get("action_id") or "")
            for proposal in context.memory["health"]["repair_plan"].get("execution_proposals", [])
            if proposal.get("action_id")
        },
    )
    for proposal in context.memory["health"]["repair_plan"].get("execution_proposals", []):
        context.write_index_artifact(
            context.root / str(proposal["proposal_path"]),
            render_execution_proposal_page(proposal, compiled_at=context.compiled_at),
        )
        context.write_index_artifact(
            context.root / str(proposal["bundle_path"]),
            json.dumps(
                build_execution_bundle(context.root, proposal, compiled_at=context.compiled_at),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    context.write_index_artifact(graph_health_report_path(context.root), render_graph_health(context.memory))
    context.write_index_artifact(
        machine_memory_drift_report_path(context.root),
        render_drift_report(context.memory, context.transition),
    )
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "review-queue.md",
        render_review_queue(
            context.decision_pages,
            context.judgment_pages,
            context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
            knowledge_lifecycle=context.knowledge_lifecycle,
            counter_evidence_scan=context.memory.get("health", {}).get("counter_evidence_scan", {}),
        ),
    )
    context.write_index_artifact(
        cognitive_history_path(context.root),
        render_cognitive_history(
            context.root,
            context.decision_pages,
            context.judgment_pages,
            context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
            knowledge_lifecycle=context.knowledge_lifecycle,
        ),
    )
    context.write_index_artifact(
        aging_report_path(context.root),
        render_aging_report(
            context.decision_pages,
            context.judgment_pages,
            context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
            knowledge_lifecycle=context.knowledge_lifecycle,
        ),
    )
    write_shell_summary(context.root, build_shell_summary(context.root, generated_at=context.compiled_at))

def _build_compile_phase_summary(context: _CompileContext) -> list[dict[str, Any]]:
    metadata_details = manifest_change_summary(context.previous_manifest.get("entries", []), context.entries)
    return [
        {
            "name": "metadata_refresh",
            "label": "metadata refresh",
            "mode": "full",
            "status": "completed",
            "details": metadata_details,
        },
        {
            "name": "incremental_source_compile",
            "label": "incremental source compile",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "source_pages": len(context.entries),
                "dirty_sources": len(context.dirty_source_ids),
                "clean_sources": len(context.clean_source_ids),
                "updated_pages": context.source_changed_pages,
                "skipped_pages": len(context.clean_source_ids),
            },
        },
        {
            "name": "concept_refresh",
            "label": "concept refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "concept_sources": len(context.entries),
                "dirty_concept_sources": len(context.dirty_concept_source_ids),
                "clean_concept_sources": len(context.clean_concept_source_ids),
                "concept_pages": len(context.concepts),
                "dirty_concepts": len(context.dirty_concept_slugs),
                "clean_concepts": len(context.clean_concept_slugs),
                "updated_pages": context.concept_changed_pages,
                "skipped_pages": len(context.clean_concept_slugs),
            },
        },
        {
            "name": "machine_memory_refresh",
            "label": "machine memory refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "machine_memory_sources": len(context.entries),
                "dirty_machine_memory_sources": len(context.dirty_machine_memory_source_ids),
                "clean_machine_memory_sources": len(context.clean_machine_memory_source_ids),
                "machine_memory_concepts": len(context.concepts),
                "dirty_machine_memory_concepts": len(context.dirty_machine_memory_concept_slugs),
                "clean_machine_memory_concepts": len(context.clean_machine_memory_concept_slugs),
                "reused_core": context.machine_memory_core_reused,
            },
        },
        {
            "name": "ranking_refresh",
            "label": "concept/global ranking refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "ranking_sources": len(context.entries),
                "dirty_ranking_sources": len(context.dirty_ranking_source_ids),
                "clean_ranking_sources": len(context.clean_ranking_source_ids),
                "ranking_concepts": len(context.concepts),
                "dirty_ranking_concepts": len(context.dirty_ranking_concept_slugs),
                "clean_ranking_concepts": len(context.clean_ranking_concept_slugs),
            },
        },
        {
            "name": "index_refresh",
            "label": "index refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "tracked_artifacts": len(context.dirty_index_artifacts) + len(context.clean_index_artifacts),
                "dirty_artifacts": len(context.dirty_index_artifacts),
                "clean_artifacts": len(context.clean_index_artifacts),
                "updated_artifacts": context.index_changed_pages,
                "skipped_artifacts": len(context.clean_index_artifacts),
            },
        },
        {
            "name": "cold_archive_maintenance",
            "label": "cold/archive maintenance",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "tracked_artifacts": len(context.dirty_maintenance_artifacts) + len(context.clean_maintenance_artifacts),
                "dirty_artifacts": len(context.dirty_maintenance_artifacts),
                "clean_artifacts": len(context.clean_maintenance_artifacts),
                "updated_artifacts": context.maintenance_changed_pages,
                "skipped_artifacts": len(context.clean_maintenance_artifacts),
                "removed_generated_pages": context.removed_pages,
                "material_state_entries": len(context.material_state["entries"]),
                "archive_candidates": len(context.archive_candidates.get("entries", [])),
                "active_corpora": len(context.active_corpora_state.get("corpora", [])),
                "knowledge_lifecycle_entries": len(context.knowledge_lifecycle.get("entries", [])),
            },
        },
        {
            "name": "output_pack_refresh",
            "label": "output pack refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "pack_groups": 4,
                "dirty_pack_groups": len(context.dirty_output_pack_groups),
                "clean_pack_groups": len(context.clean_output_pack_groups),
                "review_packs": int(context.output_packs.get("counts", {}).get("review_packs", 0) or 0),
                "decision_memos": int(context.output_packs.get("counts", {}).get("decision_memos", 0) or 0),
                "sop_drafts": int(context.output_packs.get("counts", {}).get("sop_drafts", 0) or 0),
                "updated_artifacts": context.output_pack_changed_pages,
                "skipped_artifacts": len(context.clean_output_pack_groups),
            },
        },
        {
            "name": "domain_pilot_refresh",
            "label": "domain pilot refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "pilot_protocols": len(context.domain_pilots.get("scorecards", [])),
                "dirty_protocols": len(context.dirty_domain_pilot_protocols),
                "clean_protocols": len(context.clean_domain_pilot_protocols),
                "updated_artifacts": context.domain_pilot_changed_pages,
                "skipped_artifacts": len(context.clean_domain_pilot_protocols),
            },
        },
    ]


def _build_compile_state_document(
    context: _CompileContext,
    phase_summary: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": 1,
        "compiled_at": context.compiled_at,
        "manifest_entry_count": len(context.entries),
        "dirty_source_ids": context.dirty_source_ids,
        "clean_source_ids": context.clean_source_ids,
        "dirty_concept_source_ids": context.dirty_concept_source_ids,
        "clean_concept_source_ids": context.clean_concept_source_ids,
        "dirty_concept_slugs": context.dirty_concept_slugs,
        "clean_concept_slugs": context.clean_concept_slugs,
        "dirty_machine_memory_source_ids": context.dirty_machine_memory_source_ids,
        "clean_machine_memory_source_ids": context.clean_machine_memory_source_ids,
        "dirty_machine_memory_concept_slugs": context.dirty_machine_memory_concept_slugs,
        "clean_machine_memory_concept_slugs": context.clean_machine_memory_concept_slugs,
        "machine_memory_core_reused": context.machine_memory_core_reused,
        "dirty_ranking_source_ids": context.dirty_ranking_source_ids,
        "clean_ranking_source_ids": context.clean_ranking_source_ids,
        "dirty_ranking_concept_slugs": context.dirty_ranking_concept_slugs,
        "clean_ranking_concept_slugs": context.clean_ranking_concept_slugs,
        "dirty_output_pack_groups": context.dirty_output_pack_groups,
        "clean_output_pack_groups": context.clean_output_pack_groups,
        "dirty_domain_pilot_protocols": context.dirty_domain_pilot_protocols,
        "clean_domain_pilot_protocols": context.clean_domain_pilot_protocols,
        "dirty_index_artifacts": context.dirty_index_artifacts,
        "clean_index_artifacts": context.clean_index_artifacts,
        "dirty_maintenance_artifacts": context.dirty_maintenance_artifacts,
        "clean_maintenance_artifacts": context.clean_maintenance_artifacts,
        "phase_summary": phase_summary,
    }


def _compile_log_details(context: _CompileContext) -> list[str]:
    return [
        f"compiled_at: `{context.compiled_at}`",
        f"compile_state: `{relative_path(context.root, compile_state_path(context.root))}`",
        f"compile_dirty_sources: `{len(context.dirty_source_ids)}`",
        f"compile_clean_sources: `{len(context.clean_source_ids)}`",
        f"compile_dirty_concept_sources: `{len(context.dirty_concept_source_ids)}`",
        f"compile_clean_concept_sources: `{len(context.clean_concept_source_ids)}`",
        f"compile_dirty_concepts: `{len(context.dirty_concept_slugs)}`",
        f"compile_clean_concepts: `{len(context.clean_concept_slugs)}`",
        f"compile_dirty_machine_memory_sources: `{len(context.dirty_machine_memory_source_ids)}`",
        f"compile_clean_machine_memory_sources: `{len(context.clean_machine_memory_source_ids)}`",
        f"compile_dirty_machine_memory_concepts: `{len(context.dirty_machine_memory_concept_slugs)}`",
        f"compile_clean_machine_memory_concepts: `{len(context.clean_machine_memory_concept_slugs)}`",
        f"machine_memory_core_reused: `{context.machine_memory_core_reused}`",
        f"compile_dirty_ranking_sources: `{len(context.dirty_ranking_source_ids)}`",
        f"compile_clean_ranking_sources: `{len(context.clean_ranking_source_ids)}`",
        f"compile_dirty_ranking_concepts: `{len(context.dirty_ranking_concept_slugs)}`",
        f"compile_clean_ranking_concepts: `{len(context.clean_ranking_concept_slugs)}`",
        f"compile_dirty_output_pack_groups: `{len(context.dirty_output_pack_groups)}`",
        f"compile_clean_output_pack_groups: `{len(context.clean_output_pack_groups)}`",
        f"compile_dirty_domain_pilot_protocols: `{len(context.dirty_domain_pilot_protocols)}`",
        f"compile_clean_domain_pilot_protocols: `{len(context.clean_domain_pilot_protocols)}`",
        f"compile_dirty_index_artifacts: `{len(context.dirty_index_artifacts)}`",
        f"compile_clean_index_artifacts: `{len(context.clean_index_artifacts)}`",
        f"compile_dirty_maintenance_artifacts: `{len(context.dirty_maintenance_artifacts)}`",
        f"compile_clean_maintenance_artifacts: `{len(context.clean_maintenance_artifacts)}`",
        f"source_pages_updated: `{context.source_changed_pages}`",
        f"source_pages: `{len(context.entries)}`",
        f"concept_pages: `{len(context.concepts)}`",
        f"active_protocol: `{context.protocol_state['active_protocol']}`",
        f"machine_memory_terms: `{len(context.memory['term_index'])}`",
        f"graph_components: `{context.memory['health']['component_count']}`",
        f"output_packs: `{context.output_packs['counts']['review_packs']}/{context.output_packs['counts']['decision_memos']}/{context.output_packs['counts']['sop_drafts']}`",
        f"domain_pilots: `{len(context.domain_pilots['scorecards'])}`",
        f"material_state_entries: `{len(context.material_state['entries'])}`",
        f"material_routing_entries: `{len(context.material_routing.get('entries', []))}`",
        f"archive_candidates: `{len(context.archive_candidates.get('entries', []))}`",
        f"active_corpora: `{len(context.active_corpora_state.get('corpora', []))}`",
        f"knowledge_lifecycle_entries: `{len(context.knowledge_lifecycle.get('entries', []))}`",
        f"machine_memory_changed: `{context.transition['changed']}`",
        f"changed_pages: `{context.changed_pages}`",
        f"removed_concept_pages: `{context.removed_pages}`",
    ]


def _build_compile_result_payload(
    context: _CompileContext,
    phase_summary: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "compiled_at": context.compiled_at,
        "sources": len(context.entries),
        "concepts": len(context.concepts),
        "machine_memory_terms": len(context.memory["term_index"]),
        "machine_memory_changed": context.transition["changed"],
        "changed_pages": context.changed_pages,
        "dirty_sources": len(context.dirty_source_ids),
        "clean_sources": len(context.clean_source_ids),
        "dirty_source_ids": list(context.dirty_source_ids),
        "clean_source_ids": list(context.clean_source_ids),
        "dirty_concept_sources": len(context.dirty_concept_source_ids),
        "clean_concept_sources": len(context.clean_concept_source_ids),
        "dirty_concept_source_ids": list(context.dirty_concept_source_ids),
        "clean_concept_source_ids": list(context.clean_concept_source_ids),
        "dirty_concepts": len(context.dirty_concept_slugs),
        "clean_concepts": len(context.clean_concept_slugs),
        "dirty_concept_slugs": list(context.dirty_concept_slugs),
        "clean_concept_slugs": list(context.clean_concept_slugs),
        "dirty_machine_memory_sources": len(context.dirty_machine_memory_source_ids),
        "clean_machine_memory_sources": len(context.clean_machine_memory_source_ids),
        "dirty_machine_memory_source_ids": list(context.dirty_machine_memory_source_ids),
        "clean_machine_memory_source_ids": list(context.clean_machine_memory_source_ids),
        "dirty_machine_memory_concepts": len(context.dirty_machine_memory_concept_slugs),
        "clean_machine_memory_concepts": len(context.clean_machine_memory_concept_slugs),
        "dirty_machine_memory_concept_slugs": list(context.dirty_machine_memory_concept_slugs),
        "clean_machine_memory_concept_slugs": list(context.clean_machine_memory_concept_slugs),
        "machine_memory_core_reused": context.machine_memory_core_reused,
        "dirty_ranking_sources": len(context.dirty_ranking_source_ids),
        "clean_ranking_sources": len(context.clean_ranking_source_ids),
        "dirty_ranking_source_ids": list(context.dirty_ranking_source_ids),
        "clean_ranking_source_ids": list(context.clean_ranking_source_ids),
        "dirty_ranking_concepts": len(context.dirty_ranking_concept_slugs),
        "clean_ranking_concepts": len(context.clean_ranking_concept_slugs),
        "dirty_ranking_concept_slugs": list(context.dirty_ranking_concept_slugs),
        "clean_ranking_concept_slugs": list(context.clean_ranking_concept_slugs),
        "dirty_output_pack_groups": list(context.dirty_output_pack_groups),
        "clean_output_pack_groups": list(context.clean_output_pack_groups),
        "dirty_domain_pilot_protocols": list(context.dirty_domain_pilot_protocols),
        "clean_domain_pilot_protocols": list(context.clean_domain_pilot_protocols),
        "dirty_index_artifacts": list(context.dirty_index_artifacts),
        "clean_index_artifacts": list(context.clean_index_artifacts),
        "dirty_maintenance_artifacts": list(context.dirty_maintenance_artifacts),
        "clean_maintenance_artifacts": list(context.clean_maintenance_artifacts),
        "phase_summary": phase_summary,
        "output_packs": dict(context.output_packs["counts"]),
        "domain_pilots": len(context.domain_pilots["scorecards"]),
        "compile_state_path": relative_path(context.root, compile_state_path(context.root)),
        "concept_build_state_path": relative_path(context.root, concept_build_state_path(context.root)),
        "machine_memory_build_state_path": relative_path(context.root, machine_memory_build_state_path(context.root)),
        "ranking_build_state_path": relative_path(context.root, ranking_build_state_path(context.root)),
        "output_pack_build_state_path": relative_path(context.root, output_pack_build_state_path(context.root)),
        "domain_pilot_build_state_path": relative_path(context.root, domain_pilot_build_state_path(context.root)),
        "material_state_path": relative_path(context.root, material_state_path(context.root)),
        "active_corpora_path": relative_path(context.root, active_corpora_state_path(context.root)),
        "material_routing_path": relative_path(context.root, material_routing_state_path(context.root)),
        "archive_candidates_path": relative_path(context.root, archive_candidates_state_path(context.root)),
        "knowledge_lifecycle_path": relative_path(context.root, knowledge_lifecycle_state_path(context.root)),
        "knowledge_lifecycle_overrides_path": relative_path(
            context.root,
            knowledge_lifecycle_override_state_path(context.root),
        ),
    }


def _finalize_compile_phase(context: _CompileContext) -> dict[str, Any]:
    phase_summary = _build_compile_phase_summary(context)
    compile_state = _build_compile_state_document(context, phase_summary)
    save_compile_state(context.root, compile_state)
    compile_status_changed = int(
        write_if_changed(
            context.root / "wiki" / "indexes" / "compile-status.md",
            render_compile_status(
                context.entries,
                context.concepts,
                context.decision_pages,
                context.judgment_pages,
                context.protocol_state,
                context.compiled_at,
                compile_state=compile_state,
            ),
        )
    )
    context.changed_pages += compile_status_changed
    append_wiki_log(
        context.root,
        "compile",
        "wiki refresh",
        _compile_log_details(context),
    )
    return _build_compile_result_payload(context, phase_summary)


def ranking_source_record_is_reusable(record: dict[str, Any]) -> bool:
    return (
        isinstance(record, dict)
        and isinstance(record.get("summary_or_preview"), str)
        and isinstance(record.get("concept_terms"), list)
    )


def ranking_concept_record_is_reusable(record: dict[str, Any]) -> bool:
    return (
        isinstance(record, dict)
        and isinstance(record.get("title"), str)
        and isinstance(record.get("path"), str)
        and isinstance(record.get("source_pages"), list)
        and isinstance(record.get("content"), str)
    )


def ranking_source_summary_or_preview(root: Path, entry: dict[str, Any]) -> str:
    source_file = root / str(entry.get("stored_path") or "")
    preview = read_text_preview(source_file, limit_lines=8) if source_file.exists() else ""
    return source_summary_or_preview(root, entry, preview)


def ranking_source_input_signature(
    entry: dict[str, Any],
    summary_or_preview: str,
    manual_slugs: list[str] | None = None,
) -> str:
    payload = {
        "entry_id": str(entry.get("id") or ""),
        "title": str(entry.get("title") or ""),
        "source_type": str(entry.get("source_type") or ""),
        "kind": str(entry.get("kind") or ""),
        "stored_path": str(entry.get("stored_path") or ""),
        "sha256": str(entry.get("sha256") or ""),
        "summary_or_preview": summary_or_preview,
        "manual_slugs": sorted(str(slug) for slug in (manual_slugs or []) if str(slug)),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def ranking_source_concept_terms(
    entry: dict[str, Any],
    summary_or_preview: str,
    *,
    manual_slugs: list[str] | None = None,
) -> list[str]:
    terms = entry_concept_terms(entry, summary_or_preview, max_terms=4)
    for manual_slug in sorted(str(slug) for slug in (manual_slugs or []) if str(slug)):
        manual_label = manual_slug.replace("-", " ")
        if manual_label not in terms:
            terms.append(manual_label)
    return terms


def build_ranking_source_record(
    entry: dict[str, Any],
    summary_or_preview: str,
    *,
    input_signature: str = "",
    manual_slugs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "input_signature": input_signature or ranking_source_input_signature(entry, summary_or_preview, manual_slugs),
        "summary_or_preview": summary_or_preview,
        "concept_terms": ranking_source_concept_terms(
            entry,
            summary_or_preview,
            manual_slugs=manual_slugs,
        ),
    }


def ranking_concept_input_signature(record: dict[str, Any]) -> str:
    payload = {
        "slug": str(record.get("slug") or ""),
        "title": str(record.get("title") or ""),
        "source_signature": str(record.get("source_signature") or ""),
        "render_signature": str(record.get("render_signature") or ""),
        "source_pages": concept_source_pages(record),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def build_ranking_concept_record(
    root: Path,
    path: Path,
    *,
    input_signature: str = "",
    fallback_title: str = "",
    fallback_source_pages: list[str] | None = None,
) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    source_pages = frontmatter.get("source_pages", fallback_source_pages or [])
    if not isinstance(source_pages, list):
        source_pages = fallback_source_pages or []
    return {
        "input_signature": input_signature,
        "title": str(frontmatter.get("title") or fallback_title or path.stem),
        "path": relative_path(root, path),
        "source_pages": [str(source_page) for source_page in source_pages if str(source_page)],
        "content": strip_frontmatter(content),
    }


def build_ranking_state(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    previous_state = load_ranking_build_state(root)
    previous_source_records = previous_state.get("source_records", {})
    previous_concept_records = previous_state.get("concept_records", {})
    if not isinstance(previous_source_records, dict):
        previous_source_records = {}
    if not isinstance(previous_concept_records, dict):
        previous_concept_records = {}

    source_records: dict[str, dict[str, Any]] = {}
    dirty_source_ids: list[str] = []
    clean_source_ids: list[str] = []
    manual_links = active_manual_source_concept_links(root)
    for entry in entries:
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            continue
        summary_or_preview = ranking_source_summary_or_preview(root, entry)
        manual_slugs = sorted(manual_links.get(entry_id, set()))
        input_signature = ranking_source_input_signature(entry, summary_or_preview, manual_slugs)
        previous_record = previous_source_records.get(entry_id, {})
        if (
            ranking_source_record_is_reusable(previous_record)
            and str(previous_record.get("input_signature") or "") == input_signature
        ):
            source_records[entry_id] = {
                "input_signature": input_signature,
                "summary_or_preview": str(previous_record.get("summary_or_preview") or ""),
                "concept_terms": [str(term) for term in previous_record.get("concept_terms", []) if str(term)],
            }
            clean_source_ids.append(entry_id)
        else:
            source_records[entry_id] = build_ranking_source_record(
                entry,
                summary_or_preview,
                input_signature=input_signature,
                manual_slugs=manual_slugs,
            )
            dirty_source_ids.append(entry_id)

    concept_records: dict[str, dict[str, Any]] = {}
    dirty_concept_slugs: list[str] = []
    clean_concept_slugs: list[str] = []
    for record in concepts:
        slug = str(record.get("slug") or "")
        if not slug:
            continue
        input_signature = ranking_concept_input_signature(record)
        previous_record = previous_concept_records.get(slug, {})
        if (
            ranking_concept_record_is_reusable(previous_record)
            and str(previous_record.get("input_signature") or "") == input_signature
        ):
            concept_records[slug] = {
                "input_signature": input_signature,
                "title": str(previous_record.get("title") or slug),
                "path": str(previous_record.get("path") or f"wiki/concepts/{slug}.md"),
                "source_pages": [str(path) for path in previous_record.get("source_pages", []) if str(path)],
                "content": str(previous_record.get("content") or ""),
            }
            clean_concept_slugs.append(slug)
        else:
            concept_records[slug] = build_ranking_concept_record(
                root,
                root / "wiki" / "concepts" / f"{slug}.md",
                input_signature=input_signature,
                fallback_title=str(record.get("title") or slug),
                fallback_source_pages=concept_source_pages(record),
            )
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


def rank_concepts(
    root: Path,
    question: str,
    boost_concept_slugs: set[str] | None = None,
    *,
    protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    boost_concept_slugs = boost_concept_slugs or set()
    ranked: list[tuple[int, dict[str, Any]]] = []
    ranking_state = load_ranking_build_state(root)
    concept_records = ranking_state.get("concept_records", {})
    if not isinstance(concept_records, dict):
        concept_records = {}
    lifecycle = load_knowledge_lifecycle_state(root)
    retired_paths = {
        str(entry.get("path") or "")
        for entry in lifecycle.get("entries", [])
        if isinstance(entry, dict)
        and str(entry.get("kind") or "") == "concept"
        and str(entry.get("lifecycle_state") or "") == "retired"
    }
    for path in sorted((root / "wiki" / "concepts").glob("*.md")):
        if relative_path(root, path) in retired_paths:
            continue
        record = concept_records.get(path.stem, {})
        if not ranking_concept_record_is_reusable(record):
            record = build_ranking_concept_record(root, path)
        title = str(record.get("title") or path.stem)
        content = str(record.get("content") or "")
        source_pages = record.get("source_pages", [])
        if not isinstance(source_pages, list):
            source_pages = []
        haystack = f"{title}\n{content}".lower()
        score = 0
        for token in question_tokens:
            score += haystack.count(token)
        score += concept_focus_score(protocol, title, content)
        if path.stem in boost_concept_slugs:
            score += 5
        if score:
            ranked.append(
                (
                    score,
                    {
                        "slug": path.stem,
                        "title": title,
                        "path": str(record.get("path") or relative_path(root, path)),
                        "source_pages": [str(source_page) for source_page in source_pages if str(source_page)],
                    },
                )
            )
    ranked.sort(key=lambda item: (-item[0], item[1]["title"].lower()))
    return [item for _score, item in ranked[:5]]


def source_page_is_stale(root: Path, entry: dict[str, Any]) -> bool:
    page = root / "wiki" / "sources" / f"{entry['id']}.md"
    if not page.exists():
        return True
    return compiled_source_sha(page.read_text(encoding="utf-8", errors="replace")) != entry["sha256"]


def source_page_requires_compile(root: Path, entry: dict[str, Any], concepts: list[str]) -> bool:
    page = root / "wiki" / "sources" / f"{entry['id']}.md"
    if not page.exists():
        return True
    content = page.read_text(encoding="utf-8", errors="replace")
    if compiled_source_sha(content) != entry["sha256"]:
        return True
    frontmatter = parse_frontmatter(content)
    existing_concepts = frontmatter.get("concepts", [])
    if not isinstance(existing_concepts, list):
        existing_concepts = []
    normalized_existing = [str(label) for label in existing_concepts if str(label)]
    normalized_target = [str(label) for label in concepts if str(label)]
    return normalized_existing != normalized_target


def concept_page_requires_compile(root: Path, record: dict[str, Any]) -> bool:
    page = root / "wiki" / "concepts" / f"{record['slug']}.md"
    if not page.exists():
        return True
    content = page.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    existing_source_pages = frontmatter.get("source_pages", [])
    if not isinstance(existing_source_pages, list):
        existing_source_pages = []
    normalized_existing = [str(path) for path in existing_source_pages if str(path)]
    normalized_target = concept_source_pages(record)
    if normalized_existing != normalized_target:
        return True
    if str(frontmatter.get("source_signature") or "") != record["source_signature"]:
        return True
    render_signature = str(record.get("render_signature") or concept_render_signature(root, record))
    return str(frontmatter.get("render_signature") or "") != render_signature


def wiki_requires_compile(root: Path, entries: list[dict[str, Any]]) -> bool:
    if not entries:
        return False
    if not (root / "wiki" / "indexes" / "index.md").exists():
        return True
    if not (root / "wiki" / "indexes" / "review-queue.md").exists():
        return True
    if any(source_page_is_stale(root, entry) for entry in entries):
        return True
    concept_dir = root / "wiki" / "concepts"
    return not any(concept_dir.glob("*.md"))


def rank_sources(
    root: Path,
    entries: list[dict[str, Any]],
    question: str,
    boost_source_ids: set[str] | None = None,
    *,
    protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    scored: list[tuple[float, int, float, dict[str, Any]]] = []
    boost_source_ids = boost_source_ids or set()
    ranking_state = load_ranking_build_state(root)
    source_records = ranking_state.get("source_records", {})
    if not isinstance(source_records, dict):
        source_records = {}
    material_state = load_material_state(root)
    material_by_id = {
        str(item.get("entry_id") or ""): item
        for item in material_state.get("entries", [])
        if isinstance(item, dict) and item.get("entry_id")
    }
    routing_state = load_material_routing_state(root)
    routing_by_id = {
        str(item.get("entry_id") or ""): item
        for item in routing_state.get("entries", [])
        if isinstance(item, dict) and item.get("entry_id")
    }
    archived_source_ids = active_archived_material_ids(root)
    manual_source_links = active_manual_source_concept_links(root)
    for entry in entries:
        entry_id = str(entry.get("id") or "")
        material_entry = material_by_id.get(entry_id, {})
        if entry_id in archived_source_ids or str(material_entry.get("temperature") or "") == "archived":
            continue
        ranking_record = source_records.get(entry_id, {})
        if ranking_source_record_is_reusable(ranking_record):
            summary_or_preview = str(ranking_record.get("summary_or_preview") or "")
            concept_terms = [str(term) for term in ranking_record.get("concept_terms", []) if str(term)]
        else:
            summary_or_preview = ranking_source_summary_or_preview(root, entry)
            ranking_record = build_ranking_source_record(
                entry,
                summary_or_preview,
                manual_slugs=sorted(manual_source_links.get(entry_id, set())),
            )
            concept_terms = [str(term) for term in ranking_record.get("concept_terms", []) if str(term)]
        haystack = " ".join([entry["title"], summary_or_preview]).lower()
        score = 0
        for token in question_tokens:
            score += haystack.count(token)
        for concept in concept_terms:
            for token in question_tokens:
                score += concept.lower().count(token)
        score += entry_focus_score(protocol, entry, summary_or_preview)
        if entry_id in boost_source_ids:
            score += 5
        if not score:
            continue

        routing_entry = routing_by_id.get(entry_id, {})
        routing_snapshot = routing_snapshot_for_protocol(routing_entry, protocol)
        runtime_score = 0.0
        if material_entry.get("active_corpus_ids"):
            runtime_score += 3.0
        temperature = str(material_entry.get("temperature") or "")
        if temperature == "hot":
            runtime_score += 2.0
        elif temperature == "warm":
            runtime_score += 1.0
        if material_entry.get("supports_judgment_ids"):
            runtime_score += 0.5

        selected_as = str(routing_snapshot.get("selected_as") or "")
        if selected_as == "hot-evidence":
            runtime_score += 2.5
        elif selected_as == "warm-evidence":
            runtime_score += 1.5
        elif selected_as == "cold-evidence":
            runtime_score += 0.5
        elif selected_as == "archive-candidate":
            runtime_score -= 0.5
        runtime_score += min(1.5, float(routing_snapshot.get("total_score", 0.0) or 0.0) * 0.35)

        top_protocols = [
            str(item.get("protocol") or "")
            for item in routing_entry.get("top_protocols", [])
            if isinstance(item, dict) and str(item.get("protocol") or "")
        ]
        if top_protocols[:1] == [protocol]:
            runtime_score += 1.0
        elif protocol in top_protocols[:2]:
            runtime_score += 0.5

        combined_score = float(score * 5) + runtime_score
        scored.append((combined_score, score, runtime_score, entry))
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]["title"].lower()))
    return [entry for _combined, _base, _runtime, entry in scored[:5]]


def machine_memory_query_plan_lines(machine_query: dict[str, Any]) -> list[str]:
    lines = [
        f"- 命中词：`{', '.join(machine_query.get('matched_terms', [])) or 'none'}`",
        f"- 路由策略：`{str(machine_query.get('selected_strategy') or 'concept-first')}`",
        f"- 路由原因：`{str(machine_query.get('selection_reason') or 'default-strategy')}`",
        f"- 来源意图词：`{', '.join(machine_query.get('matched_source_markers', [])) or 'none'}`",
        f"- 图谱意图词：`{', '.join(machine_query.get('matched_graph_markers', [])) or 'none'}`",
        f"- 提升权重的来源：`{', '.join(machine_query.get('ranked_source_ids', [])) or 'none'}`",
        f"- 提升权重的概念：`{', '.join(machine_query.get('ranked_concept_slugs', [])) or 'none'}`",
        f"- 协议 shard 来源：`{', '.join(machine_query.get('protocol_shard_source_ids', [])) or 'none'}`",
        f"- 时间偏置：`{str(machine_query.get('time_focus') or 'none')}`",
        f"- 时间意图词：`{', '.join(machine_query.get('time_focus_markers', [])) or 'none'}`",
        f"- 时间 shard 来源：`{', '.join(machine_query.get('time_shard_source_ids', [])) or 'none'}`",
        f"- 桥接概念：`{', '.join(machine_query.get('bridge_concept_slugs', [])) or 'none'}`",
        f"- 查询子图边数：`{len(machine_query.get('query_subgraph', {}).get('edges', []))}`",
        f"- 查询路径数：`{len(machine_query.get('query_routes', []))}`",
        f"- 触达分量：`{', '.join(machine_query.get('touched_component_ids', [])) or 'none'}`",
        f"- 命中的修复动作：`{len(machine_query.get('relevant_actions', []))}`",
    ]
    archive_hints = machine_query.get("archive_recall_hints", []) or []
    if archive_hints:
        hint_labels = []
        for hint in archive_hints[:3]:
            title = str(hint.get("title") or hint.get("entry_id") or "")
            temperature = str(hint.get("temperature") or "")
            archive_status = str(hint.get("archive_status") or "")
            state_label = "/".join(part for part in (temperature, archive_status) if part) or "hint"
            hint_labels.append(f"{title} [{state_label}]")
        lines.append(f"- 归档召回提示：`{', '.join(hint_labels)}`")
    else:
        lines.append("- 归档召回提示：`none`")
    planner_next_action = machine_query.get("planner_next_action", {}) or {}
    if planner_next_action:
        lines.append(
            f"- Planner next action：`{planner_next_action.get('action_id', '')}`"
            f" / `{planner_next_action.get('title', '')}`"
            f" / score `{planner_next_action.get('priority_score', 0)}`"
        )
    else:
        lines.append("- Planner next action：`none`")
    return lines


def render_report(
    root: Path,
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    protocol_state: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    output_guidance = protocol_output_guidance(root, active_protocol, "report")
    frontmatter = render_frontmatter(
        {
            "id": artifact_id,
            "kind": "output",
            "format": "report",
            "query": question,
            "protocol": active_protocol,
            "generated_by": "aiwiki-ask",
            "created_at": created_at,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {question}",
        "",
        "## 回答约束",
        "- 所有重要结论都要落回 `wiki/sources/*.md`。",
        "- 有不确定性就直接写出来，不要补洞。",
        "- 优先使用文件路径引用，而不是模糊转述。",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "",
        "## 协议输出偏置",
    ]
    if output_guidance:
        for line in output_guidance:
            lines.append(f"- {line}")
    else:
        lines.append("- 当前协议没有额外的报告偏置。")
    lines.extend(
        [
            "",
            "## 推荐索引页",
            "- [知识库总索引](../../wiki/indexes/index.md)",
            "- [来源索引](../../wiki/indexes/sources.md)",
            "- [概念索引](../../wiki/indexes/concepts.md)",
            "- [决策索引](../../wiki/indexes/decisions.md)",
            "- [判断索引](../../wiki/indexes/judgments.md)",
            "- [判断资产](../../wiki/indexes/judgment-assets.md)",
            "- [Agent Workbench](../../wiki/indexes/agent-workbench.md)",
            "- [认知历史](../../wiki/indexes/cognitive-history.md)",
            "- [输出 Pack 总览](../../wiki/indexes/output-packs.md)",
            "- [领域 Pilot 总览](../../wiki/indexes/domain-pilots.md)",
            "- [协议总览](../../wiki/indexes/protocols.md)",
            "- [审阅队列](../../wiki/indexes/review-queue.md)",
            "- [审阅中心](../../wiki/indexes/review-center.md)",
            "- [Aging 报告](../../wiki/indexes/aging-report.md)",
            "- [概念质量](../../wiki/indexes/concept-quality.md)",
            "- [机器记忆](../../wiki/indexes/machine-memory.md)",
            "- [图谱视图](../../wiki/indexes/graph-view.md)",
            "- [拓扑视图](../../wiki/indexes/machine-memory-topology.md)",
            "- [动作队列](../../wiki/indexes/machine-memory-actions.md)",
            "- [修复计划](../../wiki/indexes/machine-memory-repair-plan.md)",
            "- [图谱健康](../../wiki/indexes/graph-health.md)",
            "- [漂移报告](../../wiki/indexes/drift-report.md)",
            "- [修复待办](../../wiki/indexes/repair-backlog.md)",
            "- [运行时规则](../../schema/index.md)",
            f"- [当前协议规则](../../schema/protocols/{active_protocol}/index.md)",
            "",
            "## 机器记忆查询计划",
        ]
    )
    matched_terms = machine_query.get("matched_terms", [])
    if matched_terms:
        lines.append(f"- 命中词：`{', '.join(matched_terms)}`")
    else:
        lines.append("- 当前还没有直接命中的机器记忆词。")
    lines.extend(machine_memory_query_plan_lines(machine_query)[1:])
    lines.extend(
        [
            "",
        "## 推荐概念",
        ]
    )
    if not concepts:
        lines.append("- 还没有排好序的概念页。")
    else:
        for concept in concepts:
            lines.append(f"- [{concept['title']}](../../{concept['path']})")
    lines.extend(
        [
            "",
        "## 推荐来源",
        ]
    )
    if not entries:
        lines.append("- 还没有排好序的来源。先在 ingest 后运行 `aiwiki compile`。")
    else:
        for entry in entries:
            lines.append(f"- [{entry['title']}](../../wiki/sources/{entry['id']}.md)")
    lines.extend(
        [
            "",
        "## 草稿提纲",
        "1. 重新表述研究问题。",
        "2. 按当前协议优先组织最相关来源和概念。",
        "3. 写出分歧、证据缺口和下一步问题。",
        "",
        "## 引用要求",
        "- 在最终答案里加入 source-page 内联引用。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_slides(
    root: Path,
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    protocol_state: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    output_guidance = protocol_output_guidance(root, active_protocol, "slides")
    lines = [
        "---",
        "marp: true",
        'kind: "output"',
        'format: "slides"',
        f"query: {render_scalar(question)}",
        f'protocol: "{active_protocol}"',
        'generated_by: "aiwiki-ask"',
        f'created_at: "{created_at}"',
        f"title: {render_scalar(question)}",
        f"description: {render_scalar(f'Generated at {created_at}')}",
        "---",
        "",
        f"# {question}",
        "",
        "## 使用说明",
        "- 把排好序的来源页整理成 5 到 7 页幻灯片。",
        "- 每页正文都保留引用。",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "",
        "## 协议输出偏置",
    ]
    if output_guidance:
        for line in output_guidance:
            lines.append(f"- {line}")
    else:
        lines.append("- 当前协议没有额外的幻灯片偏置。")
    lines.extend(
        [
            "",
            "## 相关索引",
            "- `wiki/indexes/index.md`",
            "- `wiki/indexes/sources.md`",
            "- `wiki/indexes/concepts.md`",
            "- `wiki/indexes/decisions.md`",
            "- `wiki/indexes/judgments.md`",
            "- `wiki/indexes/judgment-assets.md`",
            "- `wiki/indexes/agent-workbench.md`",
            "- `wiki/indexes/cognitive-history.md`",
            "- `wiki/indexes/output-packs.md`",
            "- `wiki/indexes/domain-pilots.md`",
            "- `wiki/indexes/protocols.md`",
            "- `wiki/indexes/review-queue.md`",
            "- `wiki/indexes/review-center.md`",
            "- `wiki/indexes/aging-report.md`",
            "- `wiki/indexes/concept-quality.md`",
            "- `wiki/indexes/machine-memory.md`",
            "- `wiki/indexes/graph-view.md`",
            "- `wiki/indexes/machine-memory-topology.md`",
            "- `wiki/indexes/machine-memory-actions.md`",
            "- `wiki/indexes/machine-memory-repair-plan.md`",
            "- `wiki/indexes/graph-health.md`",
            "- `wiki/indexes/drift-report.md`",
            "- `wiki/indexes/repair-backlog.md`",
            "- `schema/index.md`",
            f"- `schema/protocols/{active_protocol}/index.md`",
            "",
            "## 机器记忆查询计划",
            "",
            "## 相关概念",
        ]
    )
    lines[-2:-2] = machine_memory_query_plan_lines(machine_query)
    if not concepts:
        lines.append("- 暂无排好序的概念页。")
    else:
        for concept in concepts:
            lines.append(f"- `{concept['path']}`")
    lines.extend(
        [
            "",
        "## 相关来源",
        ]
    )
    if not entries:
        lines.append("- 暂无排好序的来源。")
    else:
        for entry in entries:
            lines.append(f"- `wiki/sources/{entry['id']}.md`")
    lines.extend(
        [
            "",
            "---",
            "",
            f"<!-- artifact_id: {artifact_id} -->",
            "# 结论",
            "",
            "- 用有依据的内容替换这一页。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_figure_brief(
    root: Path,
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    protocol_state: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    output_guidance = protocol_output_guidance(root, active_protocol, "figure")
    frontmatter = render_frontmatter(
        {
            "id": artifact_id,
            "kind": "output",
            "format": "figure",
            "query": question,
            "protocol": active_protocol,
            "generated_by": "aiwiki-ask",
            "created_at": created_at,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# 图表简报：{question}",
        "",
        "## 目标",
        "- 描述这张图应该表达什么。",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "",
        "## 协议输出偏置",
    ]
    if output_guidance:
        for line in output_guidance:
            lines.append(f"- {line}")
    else:
        lines.append("- 当前协议没有额外的图表偏置。")
    lines.extend(
        [
            "",
            "## 推荐索引页",
            "- [知识库总索引](../../wiki/indexes/index.md)",
            "- [来源索引](../../wiki/indexes/sources.md)",
            "- [概念索引](../../wiki/indexes/concepts.md)",
            "- [决策索引](../../wiki/indexes/decisions.md)",
            "- [判断索引](../../wiki/indexes/judgments.md)",
            "- [判断资产](../../wiki/indexes/judgment-assets.md)",
            "- [Agent Workbench](../../wiki/indexes/agent-workbench.md)",
            "- [认知历史](../../wiki/indexes/cognitive-history.md)",
            "- [输出 Pack 总览](../../wiki/indexes/output-packs.md)",
            "- [领域 Pilot 总览](../../wiki/indexes/domain-pilots.md)",
            "- [协议总览](../../wiki/indexes/protocols.md)",
            "- [审阅队列](../../wiki/indexes/review-queue.md)",
            "- [审阅中心](../../wiki/indexes/review-center.md)",
            "- [Aging 报告](../../wiki/indexes/aging-report.md)",
            "- [概念质量](../../wiki/indexes/concept-quality.md)",
            "- [机器记忆](../../wiki/indexes/machine-memory.md)",
            "- [图谱视图](../../wiki/indexes/graph-view.md)",
            "- [拓扑视图](../../wiki/indexes/machine-memory-topology.md)",
            "- [动作队列](../../wiki/indexes/machine-memory-actions.md)",
            "- [修复计划](../../wiki/indexes/machine-memory-repair-plan.md)",
            "- [图谱健康](../../wiki/indexes/graph-health.md)",
            "- [漂移报告](../../wiki/indexes/drift-report.md)",
            "- [修复待办](../../wiki/indexes/repair-backlog.md)",
            "- [运行时规则](../../schema/index.md)",
            f"- [当前协议规则](../../schema/protocols/{active_protocol}/index.md)",
            "",
            "## 机器记忆查询计划",
            "",
            "## 推荐概念",
        ]
    )
    lines[-2:-2] = machine_memory_query_plan_lines(machine_query)
    if not concepts:
        lines.append("- 暂无排好序的概念页。")
    else:
        for concept in concepts:
            lines.append(f"- [{concept['title']}](../../{concept['path']})")
    lines.extend(
        [
            "",
            "## 推荐来源",
        ]
    )
    if not entries:
        lines.append("- 暂无排好序的来源。")
    else:
        for entry in entries:
            lines.append(f"- [{entry['title']}](../../wiki/sources/{entry['id']}.md)")
    lines.extend(
        [
            "",
            "## 制图要求",
            "- 写明图表类型。",
            "- 列出变量或对比维度。",
            "- 在图注里包含 source-page 引用。",
            "",
            f"<!-- artifact_id: {artifact_id} -->",
        ]
    )
    return "\n".join(lines) + "\n"


def _output_seed_terms(text: str) -> set[str]:
    return {term.lower() for term in tokenize(text) if len(term) >= 3}


def _output_seed_paths(frontmatter: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("source_files", "citations"):
        raw_value = frontmatter.get(key, [])
        if isinstance(raw_value, str):
            raw_items = [raw_value]
        elif isinstance(raw_value, list):
            raw_items = raw_value
        else:
            raw_items = []
        for item in raw_items:
            if isinstance(item, str) and item.strip():
                paths.append(item.strip())
    return paths


def _seed_pack_body(content: str) -> str:
    body = strip_frontmatter(content).strip()
    if not body.startswith("# "):
        return body
    lines = body.splitlines()
    drop_count = 1
    if len(lines) > 1 and not lines[1].strip():
        drop_count = 2
    return "\n".join(lines[drop_count:]).strip()


def _select_output_seed_pack(
    root: Path,
    *,
    output_format: str,
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    active_protocol: str,
) -> tuple[str, dict[str, Any], str]:
    directory = decision_memos_dir(root) if output_format == "decision-memo" else sop_drafts_dir(root)
    if not directory.exists():
        return "", {}, ""
    question_terms = _output_seed_terms(question)
    ranked_source_paths = {f"wiki/sources/{entry['id']}.md" for entry in entries}
    ranked_concept_slugs = {str(concept.get("slug") or "").strip() for concept in concepts if concept.get("slug")}
    best_score = -1
    best_ref = ""
    best_frontmatter: dict[str, Any] = {}
    best_content = ""
    for path in sorted(directory.glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        if frontmatter.get("kind") != "output-pack":
            continue
        body = _seed_pack_body(content)
        title = str(frontmatter.get("title") or path.stem)
        seed_terms = _output_seed_terms(f"{title}\n{body}")
        source_overlap = len(ranked_source_paths.intersection(_output_seed_paths(frontmatter)))
        concept_overlap = sum(
            1 for slug in ranked_concept_slugs if slug and (slug in body.lower() or slug in title.lower())
        )
        question_overlap = len(question_terms.intersection(seed_terms))
        protocol_bonus = 3 if str(frontmatter.get("protocol") or active_protocol) == active_protocol else 0
        score = source_overlap * 12 + concept_overlap * 4 + question_overlap * 2 + protocol_bonus
        if output_format == "decision-memo" and str(frontmatter.get("judgment_asset_path") or "").strip():
            score += 2
        relative = relative_path(root, path)
        if score > best_score or (score == best_score and relative < best_ref):
            best_score = score
            best_ref = relative
            best_frontmatter = frontmatter
            best_content = content
    return best_ref, best_frontmatter, best_content


def render_decision_memo_query(
    root: Path,
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    protocol_state: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    output_guidance = protocol_output_guidance(root, active_protocol, "decision-memo")
    seed_ref, seed_frontmatter, seed_content = _select_output_seed_pack(
        root,
        output_format="decision-memo",
        question=question,
        entries=entries,
        concepts=concepts,
        active_protocol=active_protocol,
    )
    source_files = list(dict.fromkeys(_output_seed_paths(seed_frontmatter) + ([seed_ref] if seed_ref else [])))
    frontmatter = render_frontmatter(
        {
            "id": artifact_id,
            "kind": "output",
            "format": "decision-memo",
            "query": question,
            "protocol": active_protocol,
            "generated_by": "aiwiki-ask",
            "created_at": created_at,
            "source_pack": seed_ref,
            "source_files": source_files,
            "judgment_asset_path": str(seed_frontmatter.get("judgment_asset_path") or ""),
        }
    )
    lines = [
        frontmatter,
        "",
        f"# Decision Memo Request · {question}",
        "",
        "## Usage",
        "- 把 seed memo 改写成这次问题要用的 decision memo。",
        "- 保留 `wiki/sources/*.md` 级别的引用，不要删掉反证、失效条件和下一次信号。",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "",
        "## 协议输出偏置",
    ]
    if output_guidance:
        lines.extend(f"- {line}" for line in output_guidance)
    else:
        lines.append("- 当前协议没有额外的 decision memo 偏置。")
    lines.extend(["", "## 机器记忆查询计划", *machine_memory_query_plan_lines(machine_query), "", "## 推荐概念"])
    if not concepts:
        lines.append("- 暂无排好序的概念页。")
    else:
        lines.extend(f"- [{concept['title']}](../../{concept['path']})" for concept in concepts[:8])
    lines.extend(["", "## 推荐来源"])
    if not entries:
        lines.append("- 暂无排好序的来源。")
    else:
        lines.extend(f"- [{entry['title']}](../../wiki/sources/{entry['id']}.md)" for entry in entries[:10])
    lines.extend(["", "## Seed Pack"])
    if not seed_ref:
        lines.append("- 当前没有可复用的 compiled decision memo；请基于推荐来源直接起草。")
    else:
        lines.append(f"- Source pack: `../../{seed_ref}`")
        if seed_frontmatter.get("judgment_asset_path"):
            lines.append(f"- Judgment asset: `../../{seed_frontmatter['judgment_asset_path']}`")
        if seed_frontmatter.get("target_path"):
            lines.append(f"- Target page: `../../{seed_frontmatter['target_path']}`")
    lines.extend(["", "## Seed Memo"])
    seed_body = _seed_pack_body(seed_content)
    if not seed_body:
        lines.extend(
            [
                "## Executive Summary",
                "- Pending synthesis.",
                "",
                "## Evidence",
                "- Cite the strongest supporting signals with `wiki/sources/*.md` links.",
                "",
                "## Counter Evidence",
                "- Record the strongest counter case explicitly.",
                "",
                "## Invalidation",
                "- State what would break the memo.",
                "",
                "## Next Signals",
                "- Note what should be checked next.",
            ]
        )
    else:
        lines.append(seed_body)
    return "\n".join(lines) + "\n"


def render_sop_query(
    root: Path,
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    protocol_state: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    output_guidance = protocol_output_guidance(root, active_protocol, "sop")
    seed_ref, seed_frontmatter, seed_content = _select_output_seed_pack(
        root,
        output_format="sop",
        question=question,
        entries=entries,
        concepts=concepts,
        active_protocol=active_protocol,
    )
    source_files = list(dict.fromkeys(_output_seed_paths(seed_frontmatter) + ([seed_ref] if seed_ref else [])))
    frontmatter = render_frontmatter(
        {
            "id": artifact_id,
            "kind": "output",
            "format": "sop",
            "query": question,
            "protocol": active_protocol,
            "generated_by": "aiwiki-ask",
            "created_at": created_at,
            "source_pack": seed_ref,
            "source_files": source_files,
            "action_id": str(seed_frontmatter.get("action_id") or ""),
        }
    )
    lines = [
        frontmatter,
        "",
        f"# SOP Request · {question}",
        "",
        "## Usage",
        "- 把 seed SOP 改写成这次问题要用的执行草案。",
        "- 保留前置检查、步骤、风险控制、dry-run / rollback 约束。",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "",
        "## 协议输出偏置",
    ]
    if output_guidance:
        lines.extend(f"- {line}" for line in output_guidance)
    else:
        lines.append("- 当前协议没有额外的 SOP 偏置。")
    lines.extend(["", "## 机器记忆查询计划", *machine_memory_query_plan_lines(machine_query), "", "## 推荐来源"])
    if not entries:
        lines.append("- 暂无排好序的来源。")
    else:
        lines.extend(f"- [{entry['title']}](../../wiki/sources/{entry['id']}.md)" for entry in entries[:10])
    lines.extend(["", "## 相关概念"])
    if not concepts:
        lines.append("- 暂无排好序的概念页。")
    else:
        lines.extend(f"- [{concept['title']}](../../{concept['path']})" for concept in concepts[:8])
    lines.extend(["", "## Seed Pack"])
    if not seed_ref:
        lines.append("- 当前没有可复用的 compiled SOP draft；请基于推荐来源直接起草。")
    else:
        lines.append(f"- Source pack: `../../{seed_ref}`")
        if seed_frontmatter.get("action_id"):
            lines.append(f"- Action id: `{seed_frontmatter['action_id']}`")
        if seed_frontmatter.get("pattern_key"):
            lines.append(f"- Pattern key: `{seed_frontmatter['pattern_key']}`")
        if seed_frontmatter.get("pattern_frequency"):
            lines.append(f"- Pattern frequency: `{seed_frontmatter['pattern_frequency']}`")
    lines.extend(["", "## Seed SOP"])
    seed_body = _seed_pack_body(seed_content)
    if not seed_body:
        lines.extend(
            [
                "## Preflight",
                "- Confirm inputs, guardrails, and dry-run mode.",
                "",
                "## Step-by-Step",
                "1. Capture the exact change scope.",
                "2. Run the dry-run path first.",
                "3. Record rollback and audit evidence.",
                "",
                "## Risk Controls",
                "- State the key stop conditions and rollback path.",
            ]
        )
    else:
        lines.append(seed_body)
    return "\n".join(lines) + "\n"


@runtime_write_operation
def ask_question(root: Path, question: str, output_format: str, protocol: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    if wiki_requires_compile(root, entries):
        compile_wiki(root)
        manifest = load_manifest(root)
        entries = manifest["entries"]
    protocol_state = load_protocol_state(root)
    active_protocol = resolve_protocol(root, protocol)
    if active_protocol != protocol_state["active_protocol"]:
        protocol_state = {
            **protocol_state,
            "active_protocol": active_protocol,
        }
    blocked_source_ids = active_archived_material_ids(root)
    material_state = load_material_state(root)
    routing_state = load_material_routing_state(root)
    archive_candidates = load_archive_candidates_state(root)
    memory = load_machine_memory(root)
    machine_query = build_machine_memory_query(
        memory,
        question,
        root=root,
        protocol=active_protocol,
        material_state=material_state,
        routing_state=routing_state,
        archive_candidates=archive_candidates,
    )
    ranked_concepts = rank_concepts(
        root,
        question,
        boost_concept_slugs=set(machine_query["ranked_concept_slugs"]),
        protocol=active_protocol,
    )
    boosted_ids: set[str] = set(machine_query["ranked_source_ids"])
    for concept in ranked_concepts:
        for source_page in concept.get("source_pages", []):
            if isinstance(source_page, str) and source_page.startswith("wiki/sources/") and source_page.endswith(".md"):
                boosted_ids.add(Path(source_page).stem)
    ranked = rank_sources(root, entries, question, boost_source_ids=boosted_ids, protocol=active_protocol)
    created_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_seed = f"query-{stamp}-{slugify(question)[:48]}"

    if output_format == "report":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_report(root, question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    elif output_format == "decision-memo":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, f"{artifact_seed}-decision-memo")
        destination = directory / f"{artifact_id}.md"
        content = render_decision_memo_query(
            root,
            question,
            ranked,
            ranked_concepts,
            machine_query,
            protocol_state,
            created_at,
            artifact_id,
        )
    elif output_format == "sop":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, f"{artifact_seed}-sop")
        destination = directory / f"{artifact_id}.md"
        content = render_sop_query(
            root,
            question,
            ranked,
            ranked_concepts,
            machine_query,
            protocol_state,
            created_at,
            artifact_id,
        )
    elif output_format == "slides":
        directory = root / "output" / "slides"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_slides(root, question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    elif output_format == "figure":
        directory = root / "output" / "figures"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_figure_brief(root, question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    else:
        raise ValueError(f"Unsupported format: {output_format}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    artifact_ref = relative_path(root, destination)
    bridge_evidence_ids = active_corpus_bridge_evidence_ids(
        machine_query,
        [entry["id"] for entry in ranked],
        routing_state=routing_state,
        active_protocol=active_protocol,
        blocked_source_ids=blocked_source_ids,
    )
    active_corpus = upsert_active_corpus(
        root,
        protocol=active_protocol,
        question=question,
        source_ids=[entry["id"] for entry in ranked],
        concept_slugs=[concept["slug"] for concept in ranked_concepts],
        bridge_evidence_ids=bridge_evidence_ids,
        output_ref=artifact_ref,
        changed_at=created_at,
    )
    append_runtime_history(
        root,
        {
            "event_type": "query",
            "occurred_at": created_at,
            "protocol": active_protocol,
            "corpus_id": active_corpus["corpus_id"],
            "focus_kind": "question",
            "focus_ref": question,
            "question_hash": question_signature(question),
            "output_format": output_format,
            "output_ref": artifact_ref,
            "source_ids": [entry["id"] for entry in ranked],
            "concept_slugs": [concept["slug"] for concept in ranked_concepts],
            "bridge_evidence_ids": bridge_evidence_ids,
            "touched_component_ids": machine_query.get("touched_component_ids", []),
            "time_focus": str(machine_query.get("time_focus") or ""),
            "archive_recall_hint_ids": [
                str(item.get("entry_id") or "")
                for item in machine_query.get("archive_recall_hints", [])
                if isinstance(item, dict) and item.get("entry_id")
            ],
        },
    )
    route_telemetry = record_query_route_telemetry(
        root,
        question=question,
        machine_query=machine_query,
        protocol=active_protocol,
        occurred_at=created_at,
    )
    machine_query["route_telemetry"] = dict(
        route_telemetry.get("last_entry") or machine_query.get("route_telemetry") or {}
    )
    refresh_material_state(root, generated_at=created_at, active_protocol=active_protocol)
    refresh_knowledge_lifecycle_state(
        root,
        generated_at=created_at,
        entries=manifest["entries"],
        active_corpora_state=load_active_corpora_state(root),
        memory=memory,
    )
    write_shell_summary(root, build_shell_summary(root, generated_at=created_at))
    append_wiki_log(
        root,
        "query",
        question,
        [
            f"format: `{output_format}`",
            f"artifact: `{artifact_ref}`",
            f"ranked_sources: `{len(ranked)}`",
            f"ranked_concepts: `{len(ranked_concepts)}`",
            f"protocol: `{active_protocol}`",
            f"active_corpus: `{active_corpus['corpus_id']}`",
            f"machine_terms: `{len(machine_query['matched_terms'])}`",
            f"machine_hits: `{len(machine_query['ranked_source_ids'])}/{len(machine_query['ranked_concept_slugs'])}`",
            f"time_focus: `{str(machine_query.get('time_focus') or 'none')}`",
            f"protocol_shard_sources: `{len(machine_query.get('protocol_shard_source_ids', []))}`",
            f"time_shard_sources: `{len(machine_query.get('time_shard_source_ids', []))}`",
            f"archive_recall_hints: `{len(machine_query.get('archive_recall_hints', []))}`",
            f"bridge_concepts: `{len(machine_query['bridge_concept_slugs'])}`",
            f"query_routes: `{len(machine_query['query_routes'])}`",
            f"route_strategy: `{machine_query.get('selected_strategy', 'concept-first')}`",
        ],
    )
    return {
        "path": artifact_ref,
        "format": output_format,
        "protocol": active_protocol,
        "active_corpus_id": active_corpus["corpus_id"],
        "ranked_sources": [entry["id"] for entry in ranked],
        "ranked_concepts": [concept["slug"] for concept in ranked_concepts],
        "machine_memory_query": machine_query,
        "index_pages": [
            "wiki/indexes/index.md",
            "wiki/indexes/sources.md",
            "wiki/indexes/concepts.md",
            "wiki/indexes/decisions.md",
            "wiki/indexes/judgments.md",
            "wiki/indexes/judgment-assets.md",
            "wiki/indexes/agent-workbench.md",
            "wiki/indexes/cognitive-history.md",
            "wiki/indexes/output-packs.md",
            "wiki/indexes/domain-pilots.md",
            "wiki/indexes/protocols.md",
            "wiki/indexes/review-queue.md",
            "wiki/indexes/review-center.md",
            "wiki/indexes/aging-report.md",
            "wiki/indexes/compile-status.md",
            "wiki/indexes/machine-memory.md",
            "wiki/indexes/graph-view.md",
            "wiki/indexes/machine-memory-topology.md",
            "wiki/indexes/machine-memory-actions.md",
            "wiki/indexes/machine-memory-repair-plan.md",
            "wiki/indexes/graph-health.md",
            "wiki/indexes/drift-report.md",
            "wiki/indexes/repair-backlog.md",
            "wiki/indexes/log.md",
            "schema/index.md",
            "schema/protocols/index.md",
        ],
        "protocol_pages": protocol_paths(root, active_protocol),
    }


@runtime_write_operation
def file_back(
    root: Path,
    artifact: str,
    title: str | None = None,
    kind: str = "derived",
    protocol: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    candidate = Path(artifact)
    artifact_path = candidate if candidate.is_absolute() else (root / candidate)
    artifact_path = artifact_path.resolve()
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Artifact not found: {artifact}")
    if artifact_path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        raise ValueError("Only markdown or text artifacts can be filed back in the MVP.")
    if kind not in {"derived", "decision", "judgment"}:
        raise ValueError(f"Unsupported filed-back kind: {kind}")

    filed_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_ref = (
        relative_path(root, artifact_path) if artifact_path.is_relative_to(root) else str(artifact_path)
    )
    original = artifact_path.read_text(encoding="utf-8", errors="replace")
    original_frontmatter = parse_frontmatter(original)
    citations = extract_provenance_paths(root, original)
    citation_snapshots = build_citation_snapshots(root, citations)
    source_protocol = str(original_frontmatter.get("protocol") or "").strip()
    resolved_protocol = resolve_protocol(root, protocol or source_protocol or None)
    entry_seed = f"{kind}-{stamp}-{slugify(title or artifact_path.stem)[:48]}"
    directory = {
        "derived": root / "wiki" / "derived",
        "decision": root / "wiki" / "decisions",
        "judgment": root / "wiki" / "judgments",
    }[kind]
    entry_id = next_available_stem(directory, entry_seed)
    destination = directory / f"{entry_id}.md"
    revisit_after = ""
    escalate_after = ""
    if kind in {"decision", "judgment"}:
        revisit_after, escalate_after = schedule_review_windows(
            kind,
            default_curated_status(kind),
            filed_at,
            protocol=resolved_protocol,
            root=root,
        )
    frontmatter = render_frontmatter(
        {
            "id": entry_id,
            "kind": kind,
            "status": default_curated_status(kind),
            "title": title or artifact_path.stem,
            "protocol": resolved_protocol,
            "source_files": [artifact_ref],
            "citations": citations,
            "citation_snapshots": citation_snapshots,
            "generated_by": "aiwiki-file-back",
            "last_compiled_at": filed_at,
            "confidence": "medium",
            "counter_evidence": [],
            "invalidation_rule": "",
            "next_signals": [],
            "formed_at": filed_at,
            "last_reviewed": "",
            "reviewed_at": "",
            "revisit_after": revisit_after,
            "escalate_after": escalate_after,
        }
    )
    stripped = strip_frontmatter(original).strip()
    body_lines = curated_page_template(
        kind=kind,
        protocol=resolved_protocol,
        title=title or artifact_path.stem,
        artifact_ref=artifact_ref,
        filed_at=filed_at,
        revisit_after=revisit_after,
        escalate_after=escalate_after,
        supporting_body=stripped,
    )
    payload = "\n".join([frontmatter, "", *body_lines]).rstrip() + "\n"
    destination.write_text(payload, encoding="utf-8")
    append_wiki_log(
        root,
        "file-back",
        title or artifact_path.stem,
        [
            f"kind: `{kind}`",
            f"protocol: `{resolved_protocol}`",
            f"from: `{artifact_ref}`",
            f"destination: `{relative_path(root, destination)}`",
        ],
    )
    compile_wiki(root)
    return {"path": relative_path(root, destination), "protocol": resolved_protocol}


def _save_machine_memory_action_records(root: Path, actions: list[dict[str, Any]]) -> None:
    save_machine_memory_action_state(root, {"version": 1, "actions": actions})


def _load_concept_rewrite_proposals(root: Path) -> list[dict[str, Any]]:
    state = load_concept_rewrite_state(root)
    return [dict(proposal) for proposal in state.get("proposals", []) if isinstance(proposal, dict)]


def _find_concept_rewrite_proposal(proposals: list[dict[str, Any]], slug: str) -> dict[str, Any]:
    for proposal in proposals:
        if str(proposal.get("slug") or "") == slug:
            return proposal
    raise FileNotFoundError(f"Concept rewrite proposal not found: {slug}")


def _save_concept_rewrite_proposals(root: Path, proposals: list[dict[str, Any]]) -> None:
    save_concept_rewrite_state(root, {"version": 1, "proposals": proposals})


def _evaluate_concept_rewrite_verification(root: Path, proposal: dict[str, Any]) -> dict[str, Any]:
    slug = str(proposal.get("slug") or "")
    target_path = str(proposal.get("target_path") or f"wiki/concepts/{slug}.md")
    expected_source_signature = str(proposal.get("source_signature") or "")
    expected_source_pages = sorted(
        str(item)
        for item in proposal.get("source_pages", [])
        if isinstance(item, str) and item
    )
    candidate_summary = preserved_section(str(proposal.get("candidate_markdown") or ""), "Summary", "").strip()
    snapshot = concept_page_snapshot(root, slug)
    issues: list[str] = []
    if not snapshot.get("content"):
        issues.append("missing-concept-page")
    else:
        content = str(snapshot.get("content") or "")
        frontmatter = parse_frontmatter(content)
        if str(frontmatter.get("id") or "") != f"concept-{slug}":
            issues.append("concept-id-drift")
        if str(frontmatter.get("kind") or "") != "concept":
            issues.append("concept-kind-drift")
        if expected_source_signature and str(frontmatter.get("source_signature") or "") != expected_source_signature:
            issues.append("source-signature-drift")
        current_source_pages = sorted(
            str(item)
            for item in frontmatter.get("source_pages", [])
            if isinstance(item, str) and item
        )
        if current_source_pages != expected_source_pages:
            issues.append("source-pages-drift")
        current_summary = str(snapshot.get("summary") or "").strip()
        if candidate_summary and current_summary != candidate_summary:
            issues.append("summary-not-applied")

    memory = load_machine_memory(root)
    concept_node = next(
        (
            node
            for node in memory.get("concept_nodes", [])
            if isinstance(node, dict) and str(node.get("slug") or "") == slug
        ),
        None,
    )
    if concept_node is None:
        issues.append("missing-machine-memory-node")
    else:
        node_source_pages = sorted(
            str(item)
            for item in concept_node.get("source_pages", [])
            if isinstance(item, str) and item
        )
        if node_source_pages != expected_source_pages:
            issues.append("machine-memory-source-drift")
    quality_state = memory.get("health", {}).get("concept_quality", {})
    quality_record = next(
        (
            record
            for record in quality_state.get("all_concepts", [])
            if isinstance(record, dict) and str(record.get("slug") or "") == slug
        ),
        None,
    )
    if quality_record is None:
        issues.append("missing-quality-record")
    verification_status = "passed" if not issues else "failed"
    verification_summary = (
        "Concept page summary, source signature, machine memory node, and quality record all match the applied rewrite."
        if verification_status == "passed"
        else "Verification detected drift between the applied rewrite and current concept/runtime state."
    )
    return {
        "slug": slug,
        "target_path": target_path,
        "status": verification_status,
        "checked_at": utc_now(),
        "summary": verification_summary,
        "issues": issues,
        "quality_score": int(quality_record.get("quality_score", 0)) if isinstance(quality_record, dict) else 0,
        "quality_state": str(quality_record.get("quality_state") or "") if isinstance(quality_record, dict) else "",
    }


def _persist_concept_rewrite_verification(
    root: Path,
    slug: str,
    *,
    note: str | None = None,
    compile_after: bool,
) -> dict[str, Any]:
    ensure_layout(root)
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if str(target.get("status") or "") != "applied":
        raise RuntimeError("Concept rewrite proposal must be applied before verify.")
    verification = _evaluate_concept_rewrite_verification(root, target)
    target["verification_status"] = verification["status"]
    target["verification_checked_at"] = verification["checked_at"]
    target["verification_summary"] = verification["summary"]
    target["verification_issues"] = list(verification["issues"])
    _save_concept_rewrite_proposals(root, proposals)
    append_runtime_history(
        root,
        {
            "event_type": "rewrite-verify",
            "occurred_at": str(verification["checked_at"] or ""),
            "slug": slug,
            "target_path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            "status": str(verification["status"] or ""),
            "issues": list(verification["issues"]),
            "quality_score": int(verification.get("quality_score", 0) or 0),
            "quality_state": str(verification.get("quality_state") or ""),
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "rewrite-verify",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"target: `{target.get('target_path', '')}`",
            f"status: `{verification['status']}`",
            f"issues: `{', '.join(verification['issues']) or 'none'}`",
        ],
    )
    if compile_after:
        compile_wiki(root)
    return verification


@runtime_write_operation
def review_concept_rewrite(
    root: Path,
    slug: str,
    status: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    if status not in REWRITE_PROPOSAL_STATUSES:
        raise ValueError(f"Unsupported concept rewrite status: {status}")
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if status == "accepted" and not rewrite_proposal_candidate_is_current(root, target):
        raise RuntimeError("Concept rewrite proposal candidate is stale or invalid. Run run-compile again before accepting.")
    reviewed_at = utc_now()
    target["status"] = status
    target["reviewed_at"] = reviewed_at
    target["review_note"] = note or ""
    target["pending_review"] = "true" if rewrite_proposal_needs_review(status) else "false"
    target["apply_ready"] = rewrite_proposal_is_apply_ready(root, target)
    if status != "applied":
        target["applied_at"] = str(target.get("applied_at") or "")
    _save_concept_rewrite_proposals(root, proposals)
    append_runtime_history(
        root,
        {
            "event_type": "rewrite-review",
            "occurred_at": reviewed_at,
            "slug": slug,
            "target_path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            "status": status,
            "priority": str(target.get("priority") or ""),
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "rewrite-review",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"status: `{status}`",
            f"target: `{target.get('target_path', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "slug": slug,
        "status": status,
        "reviewed_at": reviewed_at,
        "apply_ready": bool(target.get("apply_ready", False)),
    }


@runtime_write_operation
def apply_concept_rewrite(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if str(target.get("status") or "") != "accepted":
        raise RuntimeError("Concept rewrite proposal must be accepted before apply.")
    candidate_markdown = str(target.get("candidate_markdown") or "")
    if not candidate_markdown:
        raise RuntimeError("Concept rewrite proposal has no candidate markdown to apply.")
    concept_path = root / str(target.get("target_path") or f"wiki/concepts/{slug}.md")
    if not concept_path.exists():
        raise FileNotFoundError(f"Concept page not found: {concept_path}")
    current_frontmatter = parse_frontmatter(concept_path.read_text(encoding="utf-8", errors="replace"))
    current_source_signature = str(current_frontmatter.get("source_signature") or "")
    expected_source_signature = str(target.get("source_signature") or "")
    if expected_source_signature and current_source_signature != expected_source_signature:
        raise RuntimeError("Concept page changed since this rewrite proposal was generated.")
    current_source_pages = current_frontmatter.get("source_pages", [])
    if not isinstance(current_source_pages, list):
        current_source_pages = []
    normalized_source_pages = [str(item) for item in current_source_pages if isinstance(item, str)]
    _validate_rewrite_candidate_markdown(
        candidate_markdown,
        slug,
        expected_source_signature,
        normalized_source_pages,
    )
    previous_snapshot = concept_page_snapshot(root, slug)
    concept_path.write_text(candidate_markdown.strip() + "\n", encoding="utf-8")
    applied_at = utc_now()
    target["status"] = "applied"
    target["applied_at"] = applied_at
    target["last_applied_at"] = applied_at
    target["reverted_at"] = ""
    target["revert_note"] = ""
    target["reviewed_at"] = applied_at
    target["review_note"] = note or "Applied accepted rewrite proposal."
    target["pending_review"] = "false"
    target["apply_ready"] = False
    target["previous_markdown"] = str(previous_snapshot.get("content") or "")
    target["previous_digest"] = concept_rewrite_proposal_digest(str(previous_snapshot.get("content") or ""))
    target["verification_status"] = "pending"
    target["verification_checked_at"] = ""
    target["verification_summary"] = ""
    target["verification_issues"] = []
    _save_concept_rewrite_proposals(root, proposals)
    append_wiki_log(
        root,
        "rewrite-apply",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"target: `{target.get('target_path', '')}`",
            f"proposal_path: `{target.get('proposal_path', '')}`",
        ],
    )
    compile_wiki(root)
    verification = _persist_concept_rewrite_verification(
        root,
        slug,
        note="Automatic verification after apply.",
        compile_after=False,
    )
    append_runtime_history(
        root,
        {
            "event_type": "rewrite-apply",
            "occurred_at": applied_at,
            "slug": slug,
            "target_path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            "proposal_path": str(target.get("proposal_path") or ""),
            "source_signature": expected_source_signature,
            "status": "applied",
            "verification_status": str(verification.get("status") or ""),
            "verification_issues": list(verification.get("issues", [])),
            "note": note or "",
        },
    )
    compile_wiki(root)
    return {
        "slug": slug,
        "status": "applied",
        "applied_at": applied_at,
        "path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
        "verification_status": str(verification.get("status") or ""),
    }


@runtime_write_operation
def verify_concept_rewrite(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    verification = _persist_concept_rewrite_verification(
        root,
        slug,
        note=note or "Manual verification requested.",
        compile_after=True,
    )
    return {
        "slug": slug,
        "status": str(verification.get("status") or ""),
        "checked_at": str(verification.get("checked_at") or ""),
        "issues": list(verification.get("issues", [])),
    }


@runtime_write_operation
def revert_concept_rewrite(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if str(target.get("status") or "") != "applied":
        raise RuntimeError("Concept rewrite proposal has not been applied.")
    previous_markdown = str(target.get("previous_markdown") or "")
    if not previous_markdown:
        raise RuntimeError("Concept rewrite proposal has no previous concept snapshot to restore.")
    candidate_summary = preserved_section(str(target.get("candidate_markdown") or ""), "Summary", "").strip()
    current_summary = concept_page_snapshot(root, slug).get("summary", "").strip()
    if candidate_summary and current_summary != candidate_summary:
        raise RuntimeError("Only the latest applied rewrite can be reverted.")
    concept_path = root / str(target.get("target_path") or f"wiki/concepts/{slug}.md")
    if not concept_path.exists():
        raise FileNotFoundError(f"Concept page not found: {concept_path}")
    concept_path.write_text(previous_markdown.strip() + "\n", encoding="utf-8")
    reverted_at = utc_now()
    target["status"] = "accepted"
    target["reviewed_at"] = reverted_at
    target["review_note"] = note or "Reverted applied rewrite proposal."
    target["pending_review"] = "true" if rewrite_proposal_needs_review("accepted") else "false"
    target["applied_at"] = ""
    target["reverted_at"] = reverted_at
    target["revert_note"] = note or "Reverted applied rewrite proposal."
    target["verification_status"] = ""
    target["verification_checked_at"] = ""
    target["verification_summary"] = ""
    target["verification_issues"] = []
    target["apply_ready"] = rewrite_proposal_is_apply_ready(root, target)
    _save_concept_rewrite_proposals(root, proposals)
    append_runtime_history(
        root,
        {
            "event_type": "rewrite-revert",
            "occurred_at": reverted_at,
            "slug": slug,
            "target_path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            "status": "accepted",
            "last_applied_at": str(target.get("last_applied_at") or ""),
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "rewrite-revert",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"target: `{target.get('target_path', '')}`",
            "status: `accepted`",
        ],
    )
    compile_wiki(root)
    return {
        "slug": slug,
        "status": "accepted",
        "reverted_at": reverted_at,
        "path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
    }


def refresh_knowledge_lifecycle_runtime(root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    manifest = sync_manifest_with_raw(root)
    return refresh_knowledge_lifecycle_state(
        root,
        generated_at=generated_at or utc_now(),
        entries=manifest["entries"],
        active_corpora_state=load_active_corpora_state(root),
        memory=load_machine_memory(root),
    )


@runtime_write_operation
def retire_concept(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    path = concept_page_path(root, slug)
    if not path.exists():
        raise FileNotFoundError(f"Concept page not found: {relative_path(root, path)}")
    lifecycle = refresh_knowledge_lifecycle_runtime(root)
    current_entry = concept_lifecycle_entry(lifecycle, slug)
    if not current_entry:
        raise RuntimeError(f"Concept lifecycle entry not found: {slug}")
    if current_entry.get("active_corpus_ids"):
        raise RuntimeError("Active-corpus concept cannot transition to retired.")
    if str(current_entry.get("lifecycle_state") or "") == "retired" and current_entry.get("override_active"):
        raise RuntimeError(f"Concept is already retired: {slug}")

    override_state = ensure_knowledge_lifecycle_override_state(root)
    override_entries = [dict(entry) for entry in override_state.get("entries", []) if isinstance(entry, dict)]
    retired_at = utc_now()
    path_ref = relative_path(root, path)
    page_id = str(current_entry.get("page_id") or f"concept-{slug}")
    for entry in override_entries:
        if (
            bool(entry.get("active"))
            and str(entry.get("kind") or "") == "concept"
            and str(entry.get("path") or "") == path_ref
        ):
            entry["active"] = False
            entry["cleared_at"] = retired_at
            entry["cleared_note"] = "Superseded by newer concept lifecycle override."
    override_entries.append(
        {
            "page_id": page_id,
            "slug": slug,
            "path": path_ref,
            "kind": "concept",
            "lifecycle_state": "retired",
            "active": True,
            "operation": "retire",
            "reason_codes": ["manual-retire"],
            "applied_at": retired_at,
            "updated_at": retired_at,
            "note": note or "Concept retired from the active knowledge plane.",
        }
    )
    save_knowledge_lifecycle_override_state(root, {"version": 1, "entries": override_entries})
    updated_lifecycle = refresh_knowledge_lifecycle_runtime(root, generated_at=retired_at)
    append_runtime_history(
        root,
        {
            "event_type": "knowledge-lifecycle-override",
            "occurred_at": retired_at,
            "operation": "retire",
            "kind": "concept",
            "page_id": page_id,
            "slug": slug,
            "path": path_ref,
            "lifecycle_state": "retired",
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "concept-retire",
        str(current_entry.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"path: `{path_ref}`",
            "lifecycle_state: `retired`",
            f"override_state: `{relative_path(root, knowledge_lifecycle_override_state_path(root))}`",
        ],
    )
    final_entry = concept_lifecycle_entry(updated_lifecycle, slug)
    return {
        "slug": slug,
        "path": path_ref,
        "status": str(final_entry.get("lifecycle_state") or "retired"),
        "override_path": relative_path(root, knowledge_lifecycle_override_state_path(root)),
        "knowledge_lifecycle_path": relative_path(root, knowledge_lifecycle_state_path(root)),
        "updated_at": retired_at,
    }


@runtime_write_operation
def reactivate_concept(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    path = concept_page_path(root, slug)
    if not path.exists():
        raise FileNotFoundError(f"Concept page not found: {relative_path(root, path)}")
    override_state = ensure_knowledge_lifecycle_override_state(root)
    override_entries = [dict(entry) for entry in override_state.get("entries", []) if isinstance(entry, dict)]
    path_ref = relative_path(root, path)
    target: dict[str, Any] | None = None
    for entry in override_entries:
        if (
            bool(entry.get("active"))
            and str(entry.get("kind") or "") == "concept"
            and str(entry.get("path") or "") == path_ref
            and str(entry.get("lifecycle_state") or "") == "retired"
        ):
            target = entry
            break
    if target is None:
        raise RuntimeError(f"No active retired concept override exists for slug: {slug}")
    reactivated_at = utc_now()
    target["active"] = False
    target["reactivated_at"] = reactivated_at
    target["reactivate_note"] = note or "Concept reactivated into heuristic lifecycle routing."
    target["updated_at"] = reactivated_at
    save_knowledge_lifecycle_override_state(root, {"version": 1, "entries": override_entries})
    updated_lifecycle = refresh_knowledge_lifecycle_runtime(root, generated_at=reactivated_at)
    final_entry = concept_lifecycle_entry(updated_lifecycle, slug)
    append_runtime_history(
        root,
        {
            "event_type": "knowledge-lifecycle-override",
            "occurred_at": reactivated_at,
            "operation": "reactivate",
            "kind": "concept",
            "page_id": str(target.get("page_id") or f"concept-{slug}"),
            "slug": slug,
            "path": path_ref,
            "lifecycle_state": str(final_entry.get("lifecycle_state") or ""),
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "concept-reactivate",
        str(final_entry.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"path: `{path_ref}`",
            f"lifecycle_state: `{str(final_entry.get('lifecycle_state') or 'unknown')}`",
            f"override_state: `{relative_path(root, knowledge_lifecycle_override_state_path(root))}`",
        ],
    )
    return {
        "slug": slug,
        "path": path_ref,
        "status": str(final_entry.get("lifecycle_state") or ""),
        "override_path": relative_path(root, knowledge_lifecycle_override_state_path(root)),
        "knowledge_lifecycle_path": relative_path(root, knowledge_lifecycle_state_path(root)),
        "updated_at": reactivated_at,
    }


@runtime_write_operation
def review_machine_memory_action(
    root: Path,
    action_id: str,
    status: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    if status not in ACTION_STATUSES:
        raise ValueError(f"Unsupported machine-memory action status: {status}")
    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    target: dict[str, Any] | None = None
    for action in actions:
        if str(action.get("id") or "") == action_id:
            target = action
            break
    if target is None:
        raise FileNotFoundError(f"Machine-memory action not found: {action_id}")
    reviewed_at = utc_now()
    target["status"] = status
    target["reviewed_at"] = reviewed_at
    target["status_updated_at"] = reviewed_at
    target["review_note"] = note or ""
    target["pending_review"] = "true" if action_needs_review(status) else "false"
    if status in PENDING_ACTION_STATUSES:
        revisit_after, escalate_after = schedule_review_windows(
            "action",
            status,
            reviewed_at,
            protocol=str(target.get("protocol") or DEFAULT_PROTOCOL),
            root=root,
        )
    else:
        revisit_after, escalate_after = "", ""
    target["revisit_after"] = revisit_after
    target["escalate_after"] = escalate_after
    target.update(evaluate_page_aging(target))
    save_machine_memory_action_state(root, {"version": 1, "actions": actions})
    append_wiki_log(
        root,
        "action-review",
        str(target.get("title") or action_id),
        [
            f"action_id: `{action_id}`",
            f"status: `{status}`",
            f"primary: `{target.get('primary_path', '')}`",
            f"priority: `{target.get('priority', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": action_id,
        "status": status,
        "reviewed_at": reviewed_at,
        "active": bool(target.get("active", True)),
    }


@runtime_write_operation
def apply_machine_memory_action(
    root: Path,
    action_id: str,
    *,
    note: str | None = None,
    dry_run: bool = False,
    bundle_path: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    target: dict[str, Any] | None = None
    for action in actions:
        if str(action.get("id") or "") == action_id:
            target = action
            break
    if target is None:
        raise FileNotFoundError(f"Machine-memory action not found: {action_id}")
    if str(target.get("status") or "") != "accepted":
        raise RuntimeError("Machine-memory action must be accepted before apply.")
    kind = str(target.get("kind") or "")
    protocol = str(target.get("protocol") or load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    preview_proposals = repair_execution_proposals(root, [target], active_protocol=protocol)
    proposal = preview_proposals[0] if preview_proposals else {
        "action_id": action_id,
        "title": str(target.get("title") or action_id),
        "proposal_kind": "manual-repair",
        "risk": "low",
        "priority": str(target.get("priority") or "medium"),
        "protocol": protocol,
        "summary": str(target.get("reason") or ""),
        "target_paths": [
            path
            for path in (str(target.get("primary_path") or ""), str(target.get("secondary_path") or ""))
            if path
        ],
        "page_patch_plan": build_page_patch_plan(root, target, active_protocol=protocol),
        "safe_apply_preview": safe_apply_preview(root, target),
        "command_hint": str(target.get("command_hint") or ""),
        "bundle_path": relative_path(root, execution_bundle_path(root, action_id)),
        "proposal_path": relative_path(root, execution_proposal_path(root, action_id)),
    }
    preview = proposal.get("safe_apply_preview")
    if not isinstance(preview, dict):
        raise RuntimeError("Only accepted actions with a safe apply preview support semi-auto apply.")
    preview_apply_mode = str(preview.get("apply_mode") or "")
    if not preview_apply_mode:
        raise RuntimeError("Safe apply preview is missing an apply mode.")
    bundle = build_execution_bundle(root, proposal, compiled_at=utc_now())
    if dry_run:
        return {
            "id": action_id,
            "dry_run": True,
            "apply_mode": preview_apply_mode,
            "status": str(target.get("status") or "accepted"),
            "bundle_path": proposal.get("bundle_path", ""),
            "proposal_path": proposal.get("proposal_path", ""),
            "preview": proposal.get("safe_apply_preview"),
            "bundle": bundle,
        }

    selected_bundle_path = (
        root / bundle_path.strip()
        if bundle_path and bundle_path.strip()
        else root / str(proposal.get("bundle_path") or "")
    )
    if not selected_bundle_path.exists():
        raise FileNotFoundError(
            f"Execution bundle not found: {relative_path(root, selected_bundle_path)}. Run compile or apply-action --dry-run first."
        )
    stored_bundle = load_execution_bundle(selected_bundle_path)
    if str(stored_bundle.get("action_id") or "") != action_id:
        raise RuntimeError("Execution bundle action_id does not match the requested action.")
    if str(stored_bundle.get("digest") or "") != execution_bundle_digest(stored_bundle):
        raise RuntimeError("Execution bundle digest is invalid; regenerate the bundle before apply.")
    if str(stored_bundle.get("digest") or "") != str(bundle.get("digest") or ""):
        raise RuntimeError("Execution bundle is stale; re-run compile or apply-action --dry-run before apply.")

    applied_at = utc_now()
    stored_preview = stored_bundle.get("safe_apply_preview")
    if not isinstance(stored_preview, dict):
        raise RuntimeError("Execution bundle is missing the safe apply preview.")
    apply_mode = str(stored_preview.get("apply_mode") or "")
    if apply_mode == "manual-link-state":
        source_id, concept_slug = validate_low_risk_action_targets(root, target)
        manual_state = load_manual_link_state(root)
        manual_links = [dict(item) for item in manual_state.get("source_to_concept", []) if isinstance(item, dict)]
        existing = next(
            (
                item
                for item in manual_links
                if str(item.get("source_id") or "") == source_id
                and str(item.get("concept_slug") or "") == concept_slug
                and bool(item.get("active", True))
            ),
            None,
        )
        if existing is None:
            manual_links.append(
                {
                    "source_id": source_id,
                    "concept_slug": concept_slug,
                    "active": True,
                    "created_at": applied_at,
                    "applied_at": applied_at,
                    "origin_action_id": action_id,
                    "note": note or "Applied accepted low-risk repair action.",
                }
            )
        else:
            existing["active"] = True
            existing["applied_at"] = applied_at
            existing["origin_action_id"] = action_id
            existing["note"] = note or str(existing.get("note") or "")
        save_manual_link_state(root, {"version": 1, "source_to_concept": manual_links})
    elif apply_mode == "citation-snapshot-refresh":
        page_path = str(stored_preview.get("page_path") or target.get("primary_path") or "")
        if not page_path:
            raise RuntimeError("Safe apply preview is missing the judgment page path.")
        page = root / page_path
        if not page.exists():
            raise FileNotFoundError(f"Judgment page not found: {page_path}")
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        body = strip_frontmatter(content).strip()
        frontmatter["citation_snapshots"] = [
            str(item)
            for item in stored_preview.get("updated_citation_snapshots", [])
            if isinstance(item, str) and item.strip()
        ]
        page.write_text(f"{render_frontmatter(frontmatter)}\n\n{body}\n", encoding="utf-8")
    else:
        raise RuntimeError(f"Unsupported apply mode: {apply_mode}")

    receipt = build_execution_receipt(root, target, applied_at=applied_at, note=note, proposal=proposal)
    receipt_path = execution_receipt_path(root, action_id)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)

    target["status"] = "resolved"
    target["reviewed_at"] = applied_at
    target["status_updated_at"] = applied_at
    target["review_note"] = note or "Semi-auto apply completed."
    target["pending_review"] = "false"
    target["revisit_after"] = ""
    target["escalate_after"] = ""
    target["aging_state"] = ""
    target["overdue_review"] = "false"
    target["escalation_candidate"] = "false"
    target["last_receipt_path"] = relative_path(root, receipt_path)
    _save_machine_memory_action_records(root, actions)
    append_wiki_log(
        root,
        "action-apply",
        str(target.get("title") or action_id),
        [
            f"action_id: `{action_id}`",
            f"kind: `{kind}`",
            f"apply_mode: `{apply_mode}`",
            f"primary: `{target.get('primary_path', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": action_id,
        "status": "resolved",
        "applied_at": applied_at,
        "apply_mode": apply_mode,
        "receipt_path": relative_path(root, receipt_path),
    }


@runtime_write_operation
def revert_machine_memory_action(
    root: Path,
    action_id: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    target: dict[str, Any] | None = None
    for action in actions:
        if str(action.get("id") or "") == action_id:
            target = action
            break
    if target is None:
        raise FileNotFoundError(f"Machine-memory action not found: {action_id}")
    receipt_relative = str(target.get("last_receipt_path") or "")
    if not receipt_relative:
        raise RuntimeError("Machine-memory action has no execution receipt to revert.")
    receipt_path = root / receipt_relative
    if not receipt_path.exists():
        raise FileNotFoundError(f"Execution receipt not found: {receipt_relative}")
    receipt = load_json_document(receipt_path)
    if not isinstance(receipt, dict) or str(receipt.get("kind") or "") != "execution-receipt":
        raise RuntimeError("Execution receipt is not valid.")
    if str(receipt.get("operation") or "") != "apply":
        raise RuntimeError("Only the latest apply receipt can be reverted.")
    if str(receipt.get("action_id") or "") != action_id:
        raise RuntimeError("Execution receipt action_id does not match the requested action.")
    preview = receipt.get("safe_apply_preview")
    if not isinstance(preview, dict):
        raise RuntimeError("Execution receipt is missing the safe apply preview.")
    reverted_at = utc_now()
    apply_mode = str(preview.get("apply_mode") or "")
    if apply_mode == "manual-link-state":
        manual_state = load_manual_link_state(root)
        manual_links = [dict(item) for item in manual_state.get("source_to_concept", []) if isinstance(item, dict)]
        active_entry: dict[str, Any] | None = None
        for item in manual_links:
            if str(item.get("origin_action_id") or "") != action_id:
                continue
            if bool(item.get("active", True)):
                active_entry = item
                break
        if active_entry is None:
            raise RuntimeError("No active safe-apply state exists for this action.")
        active_entry["active"] = False
        active_entry["reverted_at"] = reverted_at
        active_entry["revert_note"] = note or "Safe apply reverted."
        save_manual_link_state(root, {"version": 1, "source_to_concept": manual_links})
    elif apply_mode == "citation-snapshot-refresh":
        page_path = str(preview.get("page_path") or target.get("primary_path") or "")
        if not page_path:
            raise RuntimeError("Execution receipt is missing the judgment page path.")
        page = root / page_path
        if not page.exists():
            raise FileNotFoundError(f"Judgment page not found: {page_path}")
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        body = strip_frontmatter(content).strip()
        frontmatter["citation_snapshots"] = [
            str(item)
            for item in preview.get("previous_citation_snapshots", [])
            if isinstance(item, str) and item.strip()
        ]
        page.write_text(f"{render_frontmatter(frontmatter)}\n\n{body}\n", encoding="utf-8")
    else:
        raise RuntimeError(f"Unsupported revert apply mode: {apply_mode}")

    protocol = str(target.get("protocol") or load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    reverted_target = {
        **dict(target),
        "protocol": protocol,
        "status": "proposed",
        "execution_policy": "triage",
        "execution_band": "review-first",
        "reviewed_at": reverted_at,
        "status_updated_at": reverted_at,
        "review_note": note or "Safe apply reverted.",
        "pending_review": "true",
        "last_receipt_path": relative_path(root, receipt_path),
        "command_hint": f'PYTHONPATH=src python3 -m aiwiki.cli --root . review-action {action_id} --status accepted --note "Resume reverted repair."',
        "next_step": "回滚后重新 review，确认是否要再次 accepted 再执行。",
    }
    preview_proposals = repair_execution_proposals(root, [reverted_target], active_protocol=protocol)
    proposal = preview_proposals[0] if preview_proposals else {
        "action_id": action_id,
        "title": str(reverted_target.get("title") or action_id),
        "proposal_kind": "manual-repair",
        "risk": "low",
        "priority": str(reverted_target.get("priority") or "medium"),
        "protocol": protocol,
        "status": "proposed",
        "execution_policy": "triage",
        "summary": str(reverted_target.get("reason") or ""),
        "target_paths": [
            path
            for path in (str(reverted_target.get("primary_path") or ""), str(reverted_target.get("secondary_path") or ""))
            if path
        ],
        "page_patch_plan": build_page_patch_plan(root, reverted_target, active_protocol=protocol),
        "safe_apply_preview": safe_apply_preview(root, reverted_target),
        "command_hint": str(reverted_target.get("command_hint") or ""),
        "bundle_path": relative_path(root, execution_bundle_path(root, action_id)),
        "proposal_path": relative_path(root, execution_proposal_path(root, action_id)),
    }
    revert_receipt = build_execution_receipt(
        root,
        reverted_target,
        applied_at=reverted_at,
        note=note,
        proposal=proposal,
        operation="revert",
        resulting_status="proposed",
    )
    receipt_path.write_text(json.dumps(revert_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, revert_receipt)

    target["status"] = str(reverted_target["status"])
    target["reviewed_at"] = str(reverted_target["reviewed_at"])
    target["status_updated_at"] = str(reverted_target["status_updated_at"])
    target["review_note"] = str(reverted_target["review_note"])
    target["pending_review"] = str(reverted_target["pending_review"])
    target["last_receipt_path"] = str(reverted_target["last_receipt_path"])
    revisit_after, escalate_after = schedule_review_windows(
        "action",
        "proposed",
        reverted_at,
        protocol=str(target.get("protocol") or DEFAULT_PROTOCOL),
        root=root,
    )
    target["revisit_after"] = revisit_after
    target["escalate_after"] = escalate_after
    target.update(evaluate_page_aging(target))
    _save_machine_memory_action_records(root, actions)
    append_wiki_log(
        root,
        "action-revert",
        str(target.get("title") or action_id),
        [
            f"action_id: `{action_id}`",
            f"receipt: `{relative_path(root, receipt_path)}`",
            f"primary: `{target.get('primary_path', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": action_id,
        "status": "proposed",
        "reverted_at": reverted_at,
        "receipt_path": relative_path(root, receipt_path),
    }


@runtime_write_operation
def apply_material_archive(
    root: Path,
    entry_id: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    if (
        wiki_requires_compile(root, manifest["entries"])
        or not material_state_path(root).exists()
        or not archive_candidates_state_path(root).exists()
    ):
        compile_wiki(root)
        manifest = load_manifest(root)

    archive_candidates = load_archive_candidates_state(root)
    material_state = load_material_state(root)
    material_archive_state = load_material_archive_state(root)
    archived_entries = active_material_archive_entries(material_archive_state)
    if entry_id in archived_entries:
        raise RuntimeError(f"Material is already archived: {entry_id}")

    candidate = next(
        (
            item
            for item in archive_candidates.get("entries", [])
            if isinstance(item, dict) and str(item.get("entry_id") or "") == entry_id
        ),
        None,
    )
    if candidate is None:
        raise FileNotFoundError(f"Archive candidate not found: {entry_id}")
    if str(candidate.get("status") or "") != "ready":
        raise RuntimeError("Only ready archive candidates support apply.")
    if str(candidate.get("recommended_temperature") or "") != "archived":
        raise RuntimeError("Only archive candidates recommending `archived` support apply.")

    material_entry = next(
        (
            item
            for item in material_state.get("entries", [])
            if isinstance(item, dict) and str(item.get("entry_id") or "") == entry_id
        ),
        None,
    )
    if material_entry is None:
        raise FileNotFoundError(f"Material state entry not found: {entry_id}")
    if str(material_entry.get("temperature") or "") != "cold":
        raise RuntimeError("Only cold material can transition to archived.")
    if material_entry.get("active_corpus_ids"):
        raise RuntimeError("Active-corpus material cannot transition to archived.")

    manifest_entry = next(
        (
            item
            for item in manifest.get("entries", [])
            if isinstance(item, dict) and str(item.get("id") or "") == entry_id
        ),
        {},
    )
    title = str(manifest_entry.get("title") or entry_id)
    source_path = f"wiki/sources/{entry_id}.md"
    protocol = str(load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    applied_at = utc_now()
    receipt = build_material_archive_receipt(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=applied_at,
        note=note,
        operation="apply",
        current_temperature="cold",
        resulting_temperature="archived",
    )
    receipt_path = execution_receipt_path(root, material_archive_action_id(entry_id))
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)

    archive_entries = [
        dict(item)
        for item in material_archive_state.get("entries", [])
        if isinstance(item, dict) and str(item.get("entry_id") or "") != entry_id
    ]
    archive_entries.append(
        {
            "entry_id": entry_id,
            "title": title,
            "source_path": source_path,
            "active": True,
            "archived_at": applied_at,
            "reverted_at": "",
            "previous_temperature": "cold",
            "note": note or "",
            "recommended_temperature": "archived",
            "last_receipt_path": relative_path(root, receipt_path),
        }
    )
    save_material_archive_state(root, {"version": 1, "entries": archive_entries})
    append_runtime_history(
        root,
        {
            "event_type": "archive-apply",
            "occurred_at": applied_at,
            "protocol": protocol,
            "source_ids": [entry_id],
            "receipt_path": relative_path(root, receipt_path),
        },
    )
    append_wiki_log(
        root,
        "archive-apply",
        title,
        [
            f"entry_id: `{entry_id}`",
            f"source: `{source_path}`",
            "temperature: `cold -> archived`",
            f"receipt: `{relative_path(root, receipt_path)}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": entry_id,
        "status": "archived",
        "applied_at": applied_at,
        "receipt_path": relative_path(root, receipt_path),
    }


@runtime_write_operation
def revert_material_archive(
    root: Path,
    entry_id: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    if wiki_requires_compile(root, manifest["entries"]) or not material_state_path(root).exists():
        compile_wiki(root)
        manifest = load_manifest(root)

    material_archive_state = load_material_archive_state(root)
    archive_entries = [dict(item) for item in material_archive_state.get("entries", []) if isinstance(item, dict)]
    target = next((item for item in archive_entries if str(item.get("entry_id") or "") == entry_id), None)
    if target is None or not bool(target.get("active", False)):
        raise RuntimeError(f"No active archived material exists for entry: {entry_id}")

    receipt_relative = str(target.get("last_receipt_path") or "")
    if not receipt_relative:
        raise RuntimeError("Archived material has no execution receipt to revert.")
    receipt_path = root / receipt_relative
    if not receipt_path.exists():
        raise FileNotFoundError(f"Execution receipt not found: {receipt_relative}")
    receipt = load_json_document(receipt_path)
    if not isinstance(receipt, dict) or str(receipt.get("kind") or "") != "execution-receipt":
        raise RuntimeError("Execution receipt is not valid.")
    if str(receipt.get("operation") or "") != "apply":
        raise RuntimeError("Only the latest apply archive receipt can be reverted.")
    if str(receipt.get("subject_id") or "") != entry_id:
        raise RuntimeError("Execution receipt subject_id does not match the requested entry.")

    manifest_entry = next(
        (
            item
            for item in manifest.get("entries", [])
            if isinstance(item, dict) and str(item.get("id") or "") == entry_id
        ),
        {},
    )
    title = str(manifest_entry.get("title") or target.get("title") or entry_id)
    source_path = str(target.get("source_path") or f"wiki/sources/{entry_id}.md")
    protocol = str(load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    reverted_at = utc_now()
    revert_receipt = build_material_archive_receipt(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=reverted_at,
        note=note,
        operation="revert",
        current_temperature="archived",
        resulting_temperature="cold",
    )
    receipt_path.write_text(json.dumps(revert_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, revert_receipt)

    target["active"] = False
    target["reverted_at"] = reverted_at
    target["revert_note"] = note or "Material archive reverted."
    target["last_receipt_path"] = relative_path(root, receipt_path)
    save_material_archive_state(root, {"version": 1, "entries": archive_entries})
    append_runtime_history(
        root,
        {
            "event_type": "archive-revert",
            "occurred_at": reverted_at,
            "protocol": protocol,
            "source_ids": [entry_id],
            "receipt_path": relative_path(root, receipt_path),
        },
    )
    append_wiki_log(
        root,
        "archive-revert",
        title,
        [
            f"entry_id: `{entry_id}`",
            f"source: `{source_path}`",
            "temperature: `archived -> cold`",
            f"receipt: `{relative_path(root, receipt_path)}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": entry_id,
        "status": "cold",
        "reverted_at": reverted_at,
        "receipt_path": relative_path(root, receipt_path),
    }


@runtime_write_operation
def review_page(
    root: Path,
    page: str,
    status: str,
    *,
    note: str | None = None,
    confidence: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    candidate = Path(page)
    target = candidate if candidate.is_absolute() else (root / candidate)
    target = target.resolve()
    if not target.is_file():
        raise FileNotFoundError(f"Review target not found: {page}")
    content = target.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    kind = str(frontmatter.get("kind") or "")
    if kind not in {"decision", "judgment"}:
        raise ValueError("Only decision or judgment pages can enter the review workflow.")
    valid_statuses = valid_curated_statuses(kind)
    if status not in valid_statuses:
        raise ValueError(f"Unsupported review status for {kind}: {status}")
    reviewed_at = utc_now()
    frontmatter["status"] = status
    frontmatter["reviewed_at"] = reviewed_at
    frontmatter["formed_at"] = str(frontmatter.get("formed_at") or frontmatter.get("last_compiled_at") or reviewed_at)
    frontmatter["last_reviewed"] = reviewed_at
    frontmatter.setdefault("counter_evidence", [])
    frontmatter.setdefault("invalidation_rule", "")
    frontmatter.setdefault("next_signals", [])
    if kind == "judgment" and confidence:
        frontmatter["confidence"] = confidence
    revisit_after, escalate_after = schedule_review_windows(
        kind,
        status,
        reviewed_at,
        protocol=str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
        root=root,
    )
    frontmatter["revisit_after"] = revisit_after
    frontmatter["escalate_after"] = escalate_after
    body = strip_frontmatter(content).strip()
    review_status_lines = [
        f"- Current status: `{status}`",
        f"- Reviewed at: `{reviewed_at}`",
    ]
    if confidence and kind == "judgment":
        review_status_lines.append(f"- Confidence: `{confidence}`")
    review_notes_lines = [
        f"- Outcome: `{status}`",
        f"- Reviewed at: `{reviewed_at}`",
    ]
    if note:
        review_notes_lines.append(f"- Note: {note}")
    else:
        review_notes_lines.append("- No additional review note recorded.")
    updated_body = upsert_markdown_section(body, "Review Status", "\n".join(review_status_lines))
    updated_body = upsert_markdown_section(updated_body, "Review Notes", "\n".join(review_notes_lines))
    updated_body = upsert_markdown_section(
        updated_body,
        "Aging",
        "\n".join(
            [
                f"- Revisit after: `{revisit_after or 'none'}`",
                f"- Escalate after: `{escalate_after or 'none'}`",
            ]
        ),
    )
    updated_body = append_review_history_entry(
        updated_body,
        reviewed_at=reviewed_at,
        status=status,
        note=note,
        confidence=confidence if kind == "judgment" else None,
    )
    citations = extract_provenance_paths(root, updated_body)
    frontmatter["citations"] = citations
    frontmatter["citation_snapshots"] = build_citation_snapshots(root, citations)
    citation_snapshot_state = analyze_citation_snapshots(root, citations, frontmatter)
    judgment_lifecycle_state, judgment_lifecycle_reason_codes = judgment_lifecycle_profile(
        {
            "kind": kind,
            "status": status,
            "reviewed_at": reviewed_at,
            "last_reviewed": reviewed_at,
            "overdue_review": "false",
            "escalation_candidate": "false",
            "citation_drift": "true" if citation_snapshot_state["has_drift"] else "false",
            "citation_snapshot_gap_count": str(
                len(citation_snapshot_state["missing"]) + len(citation_snapshot_state["stale"])
            ),
            "review_history_entries": str(len(review_history_entries(updated_body))),
        }
    )
    target.write_text(f"{render_frontmatter(frontmatter)}\n\n{updated_body.strip()}\n", encoding="utf-8")
    _entry_by_id, path_to_entry_id = entry_lookup_maps(load_manifest(root).get("entries", []))
    source_ids = entry_ids_from_paths(path_to_entry_id, citations)
    append_runtime_history(
        root,
        {
            "event_type": "review",
            "occurred_at": reviewed_at,
            "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
            "page_id": str(frontmatter.get("id") or target.stem),
            "page_path": relative_path(root, target),
            "page_kind": kind,
            "status": status,
            "judgment_lifecycle_state": judgment_lifecycle_state,
            "judgment_lifecycle_reason_codes": judgment_lifecycle_reason_codes,
            "source_ids": source_ids,
        },
    )
    append_wiki_log(
        root,
        "review",
        str(frontmatter.get("title") or target.stem),
        [
            f"kind: `{kind}`",
            f"status: `{status}`",
            f"path: `{relative_path(root, target)}`",
            f"confidence: `{frontmatter.get('confidence', '') or 'n/a'}`",
        ],
    )
    compile_wiki(root)
    return {
        "path": relative_path(root, target),
        "kind": kind,
        "status": status,
        "reviewed_at": reviewed_at,
        "confidence": str(frontmatter.get("confidence") or ""),
    }


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


def _write_lint_report(context: _LintContext) -> dict[str, Any]:
    generated_at = utc_now()
    report_name = f"lint-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
    report_path = context.root / "output" / "lint" / report_name
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
    append_runtime_history(
        root,
        {
            "event_type": "nightly",
            "occurred_at": generated_at,
            "protocol": protocol_state["active_protocol"],
            "cooled_corpus_ids": cooled_corpus_ids,
            "expired_corpus_ids": expired_corpus_ids,
            "active_corpus_ids": [
                str(corpus.get("corpus_id") or "")
                for corpus in active_corpora
                if str(corpus.get("status") or "") == "active"
            ],
        },
    )
    material_state = refresh_material_state(
        root,
        generated_at=generated_at,
        entries=manifest["entries"],
        active_protocol=protocol_state["active_protocol"],
    )
    material_routing = load_material_routing_state(root)
    archive_candidates = load_archive_candidates_state(root)
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


@runtime_write_operation
def nightly_health(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    compile_result = compile_wiki(root)
    promotion_result = promote_recurring_outputs(root)
    if promotion_result["count"]:
        compile_result = compile_wiki(root)
    lint_result = lint_wiki(root)
    state = write_nightly_health(
        root,
        compile_result,
        lint_result,
        promotion_result=promotion_result,
        semantic_report="",
        llm_used=False,
    )
    return {
        "compile": compile_result,
        "lint": lint_result,
        "promotions": promotion_result,
        "aging": state["aging"],
        "repair_backlog": state["repair_backlog"]["path"],
        "state_path": relative_path(root, nightly_health_state_path(root)),
    }


@runtime_write_operation
def shell_status(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    summary = build_shell_summary(root)
    return write_shell_summary(root, summary)
