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

from ..app_execution import (
    append_execution_receipt_history,
    build_execution_bundle,
    build_execution_receipt,
    build_material_archive_receipt,
    execution_bundle_digest,
    load_execution_bundle,
    write_execution_bundle_document,
)
from ..app_lifecycle import (
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
from ..app_memory_query import (
    concept_page_snapshot,
    record_query_route_telemetry,
)
from ..app_protocol import (
    ACTION_STATUSES,
    AGENT_PACK_LIBRARY,
    AUTO_PROMOTION_MIN_OCCURRENCES,
    CONCEPT_HARDNESS_LEVELS,
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
from ..app_routing import (
    active_corpus_bridge_evidence_ids,
    build_material_state_documents,
    reconcile_active_corpora_state,
    refresh_material_state,
    upsert_active_corpus,
)
from ..app_shell import build_shell_summary, write_shell_summary
from ..app_state_paths import (
    active_corpora_state_path,
    agent_pack_path,
    agent_workbench_path,
    aging_report_path,
    archive_candidates_state_path,
    cognitive_history_path,
    compile_state_path,
    concept_build_state_path,
    concept_quality_path,
    concept_rewrite_index_path,
    concept_rewrite_state_path,
    domain_pilot_build_state_path,
    execution_audit_html_path,
    execution_audit_path,
    execution_policy_log_path,
    furnace_center_html_path,
    graph_health_report_path,
    judgment_assets_path,
    knowledge_lifecycle_override_state_path,
    knowledge_lifecycle_state_path,
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
    shell_summary_path,
)
from ..compile.build import (
    default_concept_build_state,
    default_domain_pilot_build_state,
    default_machine_memory_build_state,
    default_output_pack_build_state,
    default_ranking_build_state,
    load_ranking_build_state,
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
    load_active_corpora_state,
    load_manual_link_state,
    load_material_state,
    save_manual_link_state,
)
from ..content.memory import (
    concept_summary_is_placeholder,
    remove_stale_generated_markdown_files,
)
from ..content.outputs import classify_recurring_output_kind
from ..content.rewrite import load_concept_rewrite_state, save_concept_rewrite_state
from ..execution.history import append_runtime_history
from ..execution.lifecycle import concept_lifecycle_entry, concept_page_path
from ..execution.patch_plan import build_page_patch_plan
from ..execution.policy import (
    append_execution_policy_decisions,
    execution_policy_decision_record,
    load_execution_receipt_history,
)
from ..execution.repair_plan import (
    _validate_rewrite_candidate_markdown,
    build_machine_memory_repair_plan,
    repair_execution_proposals,
    rewrite_proposal_candidate_is_current,
    rewrite_proposal_is_apply_ready,
)
from ..lifecycle.knowledge import (
    ensure_knowledge_lifecycle_override_state,
    load_knowledge_lifecycle_state,
    save_knowledge_lifecycle_override_state,
)
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
    render_execution_audit_html,
    render_execution_proposal_page,
)
from ..memory.graph import (
    append_machine_memory_history,
    build_machine_memory_query,
    render_machine_memory_graph_html,
    summarize_machine_memory_transition,
)
from ..memory.graph_builder import build_machine_memory_graph
from ..memory.health import build_machine_memory_health
from ..memory.judgment_assets import attach_judgment_assets_to_machine_memory
from ..memory.state import load_machine_memory
from ..memory.status import (
    render_drift_report,
    render_graph_health,
    render_machine_memory_actions,
    render_machine_memory_index,
    render_machine_memory_repair_plan,
)
from ..memory.topology import render_machine_memory_topology
from ..planner.state import load_planner_state, save_planner_state
from ..render.cognitive_history import render_cognitive_history
from ..render.compile_status import render_compile_status
from ..render.furnace_center import (
    render_furnace_center,
    render_furnace_center_html,
)
from ..render.judgment_assets import render_judgment_assets
from ..render.packs import (
    build_output_packs,
    build_output_packs_incremental,
    render_output_packs_index,
)
from ..render.paths import (
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
from ..render.pilots import (
    build_domain_pilots,
    build_domain_pilots_incremental,
    domain_pilots_index_path,
    pilot_scorecards_dir,
)
from ..render.review_center import render_review_center_html
from ..render.views import (
    render_agent_pack,
    render_agent_workbench,
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
from ..utils.hash import compiled_source_sha, question_signature, sha256_bytes
from ..utils.io import (
    runtime_write_operation,
    write_if_changed,
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from ..utils.markdown import (
    analyze_citation_snapshots,
    build_citation_snapshots,
    extract_provenance_paths,
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
        f"- Soft 概念页：`{concept_quality.get('counts', {}).get('soft_hardness', 0)}`",
        f"- Medium+/Hard 概念页：`{concept_quality.get('counts', {}).get('medium_or_hard', 0)}`",
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
    if concept_quality.get("counts", {}).get("soft_hardness", 0):
        lines.append(
            f"3d. 把 `{concept_quality.get('counts', {}).get('soft_hardness', 0)}` 个仍停留在 `hardness: soft` 的概念页提升到更可复用的结构层。"
        )
    if rewrite_state.get("counts", {}).get("pending_review", 0):
        lines.append(
            f"3b. 先审 `{rewrite_state.get('counts', {}).get('pending_review', 0)}` 个 concept rewrite proposal。"
        )
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
        lines.append(
            f"7b. 执行 `{len(judgment_review_actions)}` 个 judgment review action，把升级项推进进显式 review workflow。"
        )
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
        lines.append(f"9c. 其中 `{len(apply_ready_actions)}` 个低风险动作可在 review-queue 中查看。")
    if overdue_actions:
        lines.append(f"10. 优先清理 `{len(overdue_actions)}` 个已到期待处理的 machine-memory 动作。")
    if escalated_actions:
        lines.append(f"11. 先处理 `{len(escalated_actions)}` 个已升级的 machine-memory 动作。")
    if concept_quality.get("counts", {}).get("conflict_signals", 0):
        lines.append(
            f"11a. 先把 `{concept_quality.get('counts', {}).get('conflict_signals', 0)}` 个概念冲突信号显式写进相关概念页。"
        )
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
            lines.append(f"- 升级：`{action['id']}` | {action['title']} | status `{action_status}`")
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
            command = f"review-queue / rewrite-proposal `{proposal['slug']}`"
            if proposal.get("status") == "applied" and str(proposal.get("previous_markdown") or ""):
                command = f"rewrite-proposal `{proposal['slug']}` (revert via audit receipt)"
            elif proposal.get("apply_ready"):
                command = f"rewrite-proposal `{proposal['slug']}` (apply-ready)"
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
