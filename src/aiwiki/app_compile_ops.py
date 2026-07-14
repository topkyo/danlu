"""Protocol, promotion, and agent-pack helpers extracted from app_compile.

OWNER STATUS: legacy owner. New large logic blocks should be extracted to
`aiwiki.compile.*` rather than added here. See AGENTS.md migration policy.
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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .app_execution import (
    append_execution_receipt_history,
    build_execution_bundle,
    build_execution_receipt,
    build_material_archive_receipt,
    execution_bundle_digest,
    load_execution_bundle,
)
from .app_lifecycle import (
    action_needs_review,
    build_knowledge_lifecycle_document,
    collect_aging_signals,
    collect_curated_pages,
    curated_page_template,
    curated_page_transition_profile,
    default_curated_status,
    display_action_status,
    display_curated_status,
    display_knowledge_lifecycle_state,
    display_rewrite_proposal_status,
    evaluate_page_aging,
    frontmatter_string_list,
    judgment_lifecycle_profile,
    knowledge_lifecycle_governance_summary,
    refresh_knowledge_lifecycle_state,
    render_knowledge_lifecycle_entry_summary,
    review_queue,
    rewrite_proposal_needs_review,
    valid_curated_statuses,
)
from .app_linting import pending_source_summary_ids
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
    load_output_candidates_state,
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
    save_output_candidates_state,
    shell_summary_path,
    upsert_output_candidate,
)
from .app_utils import (
    analyze_citation_snapshots,
    atomic_write_text,
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
from .content.concepts import (
    build_concept_quality,
    build_concept_records,
    concept_render_signature,
    concept_source_pages,
    entry_concept_terms,
    render_concept_page,
    render_concepts_index,
    render_sources_index,
)
from .content.io import (
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
from .content.memory import (
    _validate_rewrite_candidate_markdown,
    action_supports_low_risk_apply,
    append_execution_policy_decisions,
    build_machine_memory_repair_plan,
    build_page_patch_plan,
    concept_summary_is_placeholder,
    execution_policy_decision_record,
    load_execution_receipt_history,
    placeholder_concept_slugs,
    remove_stale_generated_execution_bundle_files,
    remove_stale_generated_execution_proposal_pages,
    remove_stale_generated_markdown_files,
    repair_execution_proposals,
    rewrite_proposal_candidate_is_current,
    rewrite_proposal_is_apply_ready,
    safe_apply_preview,
    validate_low_risk_action_targets,
)
from .content.outputs import classify_recurring_output_kind
from .memory.execution_surfaces import (
    render_execution_audit,
    render_execution_audit_html,
    render_execution_center,
    render_execution_center_html,
)
from .memory.graph import render_machine_memory_graph_html
from .render.cognitive_history import render_cognitive_history
from .render.compile_status import render_compile_status
from .render.furnace_center import (
    render_furnace_center,
    render_furnace_center_html,
)
from .render.judgment_assets import render_judgment_assets
from .render.packs import (
    build_output_packs,
    build_output_packs_incremental,
    render_output_packs_index,
)
from .render.paths import (
    append_wiki_log,
    decision_memos_dir,
    ensure_wiki_log,
    execution_bundle_path,
    execution_proposal_path,
    execution_receipt_path,
    remove_stale_generated_concept_pages,
    review_packs_dir,
    sop_drafts_dir,
)
from .render.pilots import (
    build_domain_pilots,
    build_domain_pilots_incremental,
    domain_pilots_index_path,
    pilot_scorecards_dir,
)
from .render.review_center import render_review_center_html
from .render.views import (
    render_agent_pack,
    render_agent_workbench,
    render_aging_report,
    render_curated_index,
    render_domain_pilots_index,
    render_master_index,
    render_review_queue,
)


@runtime_write_operation
def set_active_protocol(root: Path, protocol: str) -> dict[str, Any]:
    active = resolve_protocol(root, protocol)
    path = protocol_state_path(root)
    atomic_write_text(path, json.dumps({"version": 1, "active_protocol": active}, indent=2, sort_keys=True) + "\n")
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
    enqueued = 0
    promotions: list[dict[str, str]] = []
    for (protocol, query_signature), artifacts in sorted(groups.items()):
        if len(artifacts) < AUTO_PROMOTION_MIN_OCCURRENCES:
            continue
        query = artifacts[0]["query"]
        kind = classify_recurring_output_kind(query, protocol)
        if kind not in {"decision", "judgment"}:
            continue
        candidate = upsert_output_candidate(
            root,
            artifact_ref=artifacts[-1]["path"],
            candidate_state="pending",
            created_at=generated_at,
            updated_at=generated_at,
            format=artifacts[-1].get("format", ""),
            protocol=protocol,
            corpus_id=artifacts[-1].get("corpus_id", ""),
            question=query,
            promotion_origin="nightly-recurring",
        )
        candidate["recurring_kind"] = kind
        state = load_output_candidates_state(root)
        for item in state.get("candidates", []):
            if str(item.get("artifact_ref") or "") == artifacts[-1]["path"]:
                item["recurring_kind"] = kind
                break
        save_output_candidates_state(root, state)
        enqueued += 1
        promotions.append(
            {
                "kind": kind,
                "action": "enqueued",
                "path": candidate["artifact_ref"],
                "candidate_ref": candidate["artifact_ref"],
                "protocol": protocol,
                "query": query,
                "query_signature": query_signature,
                "occurrences": str(len(artifacts)),
                "latest_artifact": artifacts[-1]["path"],
            }
        )
        append_wiki_log(
            root,
            "enqueue",
            query,
            [
                f"kind: `{kind}`",
                f"protocol: `{protocol}`",
                "action: `enqueued`",
                f"occurrences: `{len(artifacts)}`",
                f"candidate_ref: `{candidate['artifact_ref']}`",
                f"latest_artifact: `{artifacts[-1]['path']}`",
            ],
        )

    return {
        "count": enqueued,
        "created": 0,
        "updated": 0,
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
