"""Query/report/slides/memo rendering helpers extracted from app_compile.

OWNER STATUS: legacy owner. New large logic blocks should be extracted to a
dedicated subpackage (e.g. `aiwiki.queries.*` or `aiwiki.render.*`) rather
than added here. See AGENTS.md migration policy.
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

from .app_content import (
    _validate_rewrite_candidate_markdown,
    action_needs_review,
    action_supports_low_risk_apply,
    active_manual_source_concept_links,
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
    curated_asset_section_snapshot,
    curated_page_template,
    curated_page_transition_profile,
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
    review_history_entries,
    review_packs_dir,
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
from .app_memory_query import (
    build_machine_memory_query_routes,
    ranked_machine_memory_anchor_nodes,
    shortest_machine_memory_path,
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
from .app_render import protocol_output_pack_rows
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
from .config import LLMConfig

AUTO_ASK_PATH_MARKER = "本次投喂材料路径："
AUTO_ASK_QUESTION_MARKER = "用户问题："
AUTO_ASK_INLINE_PATH_MARKER = "材料路径供系统路由使用："
AUTO_ASK_INLINE_HINT_PREFIX = "请优先使用本次投喂材料回答"


def human_query_title(question: str) -> str:
    """Return the user-facing title for an ask artifact.

    Product Shell auto-ask prompts include repo paths as routing hints.  Those
    hints are useful to the runtime but should not leak into report headings,
    Obsidian titles, or output filenames.
    """

    text = str(question or "").strip()
    if not text:
        return "未命名问题"
    marker_index = text.rfind(AUTO_ASK_QUESTION_MARKER)
    if marker_index >= 0:
        candidate = text[marker_index + len(AUTO_ASK_QUESTION_MARKER) :].strip()
        if candidate:
            text = candidate
    visible_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if AUTO_ASK_INLINE_PATH_MARKER in stripped:
            before_marker = stripped.split(AUTO_ASK_INLINE_PATH_MARKER, 1)[0].strip()
            before_marker = before_marker.removesuffix("；").removesuffix(";").strip()
            if before_marker and before_marker != AUTO_ASK_INLINE_HINT_PREFIX:
                visible_lines.append(before_marker)
            continue
        if stripped == AUTO_ASK_INLINE_HINT_PREFIX or stripped.startswith(f"{AUTO_ASK_INLINE_HINT_PREFIX}；"):
            continue
        visible_lines.append(line)
    text = "\n".join(visible_lines).strip()
    text = re.sub(r"(?m)^\s*-\s*(?:raw|wiki|output|\.aiwiki)/\S+\s*$", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text or "未命名问题"


def _ranking_helpers() -> tuple[Any, Any, Any]:
    from . import app_compile as compile_facade

    return (
        compile_facade.build_ranking_source_record,
        compile_facade.ranking_source_record_is_reusable,
        compile_facade.ranking_source_summary_or_preview,
    )


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
    build_ranking_source_record, ranking_source_record_is_reusable, ranking_source_summary_or_preview = (
        _ranking_helpers()
    )
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


def compact_output_guidance_lines(
    output_guidance: list[str],
    default_line: str,
    *,
    limit: int = 3,
) -> list[str]:
    guidance = [str(line).strip() for line in output_guidance if str(line).strip()]
    return guidance[:limit] if guidance else [default_line]


def compact_machine_memory_focus_lines(machine_query: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    matched_terms = [str(term).strip() for term in machine_query.get("matched_terms", []) if str(term).strip()]
    if matched_terms:
        lines.append(f"- 命中词：`{', '.join(matched_terms[:5])}`")
    strategy = str(machine_query.get("selected_strategy") or "").strip()
    reason = str(machine_query.get("selection_reason") or "").strip()
    if strategy:
        suffix = f" / `{reason}`" if reason else ""
        lines.append(f"- 查询入口：`{strategy}`{suffix}")
    bridge_concepts = [
        str(slug).strip() for slug in machine_query.get("bridge_concept_slugs", []) if str(slug).strip()
    ]
    if bridge_concepts:
        lines.append(f"- 桥接概念：`{', '.join(bridge_concepts[:4])}`")
    archive_hints = machine_query.get("archive_recall_hints", []) or []
    if archive_hints:
        hint_labels = []
        for hint in archive_hints[:2]:
            title = str(hint.get("title") or hint.get("entry_id") or "").strip()
            temperature = str(hint.get("temperature") or "").strip()
            archive_status = str(hint.get("archive_status") or "").strip()
            state_label = "/".join(part for part in (temperature, archive_status) if part) or "hint"
            if title:
                hint_labels.append(f"{title} [{state_label}]")
        if hint_labels:
            lines.append(f"- 归档召回提示：`{', '.join(hint_labels)}`")
    planner_next_action = machine_query.get("planner_next_action", {}) or {}
    if not bridge_concepts:
        planner_title = str(planner_next_action.get("title") or planner_next_action.get("action_id") or "").strip()
        if planner_title:
            lines.append(f"- 下一动作提示：`{planner_title}`")
    if not lines:
        return ["- 当前没有明显的机器记忆命中，先从优先来源开始。"]
    return lines[:4]


def compact_concept_link_lines(
    concepts: list[dict[str, Any]],
    *,
    limit: int = 5,
    empty_message: str = "- 还没有排好序的概念页。",
) -> list[str]:
    if not concepts:
        return [empty_message]
    return [f"- [{concept['title']}](../../{concept['path']})" for concept in concepts[:limit]]


def compact_source_link_lines(
    entries: list[dict[str, Any]],
    *,
    limit: int = 5,
    empty_message: str = "- 还没有排好序的来源。先在 ingest 后运行 `aiwiki compile`。",
) -> list[str]:
    if not entries:
        return [empty_message]
    return [f"- [{entry['title']}](../../wiki/sources/{entry['id']}.md)" for entry in entries[:limit]]


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
    title = human_query_title(question)
    output_guidance = protocol_output_guidance(root, active_protocol, "report")
    focus_lines = compact_machine_memory_focus_lines(machine_query)
    frontmatter = render_frontmatter(
        {
            "kind": "output",
            "format": "report",
            "protocol": active_protocol,
            "query": question,
            "created_at": created_at,
            "generated_by": "aiwiki-ask",
            "_id": artifact_id,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {title}",
        "",
        "## 结论",
        "_LLM: 请在此填入一句话直接回答问题（最多 3 行）。保持判断明确，不要避而不答。_",
        "",
        "## 关键证据",
        "_LLM: 请在此填入至少 3 条 bullet，每条带至少 1 个 `wiki/sources/*.md` 引用。_",
    ]
    if focus_lines and focus_lines != ["- 当前没有明显的机器记忆命中，先从优先来源开始。"]:
        lines.append("")
        lines.append("_机器记忆提示：_")
        lines.extend(focus_lines)
    lines.extend(
        [
            "",
            "## 反证与不确定性",
            "_LLM: 请在此填入至少 1 条反证、缺口或不确定性。若证据集合确实充分，显式写明（例：未发现明显反证；证据覆盖 N 份来源 …）。_",
            "",
            "## 行动建议",
            "_LLM: 请在此填入至少 1 条可执行的 next step。_",
            "",
            "## 下次观察信号",
            "_LLM: 请在此填入至少 1 条触发复审的条件（当 X 出现 / Y 指标变化时复审本结论）。_",
            "",
            "## 引用",
            "_LLM: 请在此列出本报告引用到的全部 `wiki/sources/*.md` 路径，去重，按出现顺序。_",
            "",
            "## 参考",
            f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
            "",
            "_协议输出偏置：_",
        ]
    )
    lines.extend(
        f"- {line}"
        for line in compact_output_guidance_lines(output_guidance, "当前协议没有额外的报告偏置。")
    )
    lines.extend(
        [
            "",
            "_优先来源：_",
        ]
    )
    lines.extend(compact_source_link_lines(entries))
    lines.extend(
        [
            "",
            "_优先概念：_",
        ]
    )
    lines.extend(compact_concept_link_lines(concepts))
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
    title = human_query_title(question)
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
        f"title: {render_scalar(title)}",
        f"description: {render_scalar(f'Generated at {created_at}')}",
        "---",
        "",
        f"# {title}",
        "",
        "## 本稿用途",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "- 把问题压成 5 到 7 页幻灯片，先结论，再证据，再风险。",
        "- 每页正文都保留引用。",
        "",
        "## 协议输出偏置",
    ]
    lines.extend(
        f"- {line}"
        for line in compact_output_guidance_lines(output_guidance, "当前协议没有额外的幻灯片偏置。")
    )
    lines.extend(
        [
            "",
            "## 优先来源",
        ]
    )
    lines.extend(compact_source_link_lines(entries, empty_message="- 暂无排好序的来源。"))
    lines.extend(
        [
            "",
            "## 优先概念",
        ]
    )
    lines.extend(compact_concept_link_lines(concepts, empty_message="- 暂无排好序的概念页。"))
    lines.extend(
        [
            "",
            "## 建议页结构",
            "1. 结论页：一句话结论 + 1 个核心证据。",
            "2. 证据页：2 到 3 条关键事实。",
            "3. 机制页：解释为什么成立。",
            "4. 风险页：反证、限制和失效条件。",
            "5. 下一步：需要补的实验或决策。",
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
    title = human_query_title(question)
    output_guidance = protocol_output_guidance(root, active_protocol, "figure")
    focus_lines = compact_machine_memory_focus_lines(machine_query)
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
        f"# 图表简报：{title}",
        "",
        "## 这张图先回答什么",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "- 先用一张图回答一个问题，不要把多个结论塞进同一张图。",
    ]
    lines.extend(focus_lines)
    lines.extend(
        [
        "",
        "## 协议输出偏置",
        ]
    )
    lines.extend(
        f"- {line}"
        for line in compact_output_guidance_lines(output_guidance, "当前协议没有额外的图表偏置。")
    )
    lines.extend(
        [
            "",
            "## 优先来源",
        ]
    )
    lines.extend(compact_source_link_lines(entries, empty_message="- 暂无排好序的来源。"))
    lines.extend(
        [
            "",
            "## 优先概念",
        ]
    )
    lines.extend(compact_concept_link_lines(concepts, empty_message="- 暂无排好序的概念页。"))
    lines.extend(
        [
            "",
            "## 制图要求",
            "- 写明图表类型和横纵轴。",
            "- 变量或对比维度只保留最关键的 2 到 4 个。",
            "- 在图注里包含 source-page 引用和结论边界。",
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
    title = human_query_title(question)
    output_guidance = protocol_output_guidance(root, active_protocol, "decision-memo")
    focus_lines = compact_machine_memory_focus_lines(machine_query)
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
        f"# Decision Memo Request · {title}",
        "",
        "## 任务",
        "- 把这次问题压成一页可执行的 decision memo。",
        "- 保留 `wiki/sources/*.md` 级别的引用，不要删掉反证、失效条件和下一次信号。",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "",
        "## 协议输出偏置",
    ]
    lines.extend(
        f"- {line}"
        for line in compact_output_guidance_lines(output_guidance, "当前协议没有额外的 decision memo 偏置。")
    )
    lines.extend(["", "## 当前线索", *focus_lines, "", "## 优先来源"])
    lines.extend(compact_source_link_lines(entries, empty_message="- 暂无排好序的来源。"))
    lines.extend(["", "## 优先概念"])
    lines.extend(compact_concept_link_lines(concepts, empty_message="- 暂无排好序的概念页。"))
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


def render_note_answer(
    root: Path,
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    protocol_state: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    """Lightweight ask output. Q+A 段落式答复，无 R97-98.3 decision-grade 骨架；
    保留 frontmatter + citation 底线以便 candidate/corpus/shell summary 正常工作。"""
    active_protocol = protocol_state["active_protocol"]
    focus_lines = compact_machine_memory_focus_lines(machine_query)
    frontmatter = render_frontmatter(
        {
            "id": artifact_id,
            "kind": "output",
            "format": "note",
            "query": question,
            "protocol": active_protocol,
            "generated_by": "aiwiki-ask",
            "created_at": created_at,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {human_query_title(question)}",
        "",
        "## 回答",
        "_LLM: 请用 2–5 段自然语言直接回答上面的问题，保持判断明确；不要求六段骨架，但每段涉及事实时附 `wiki/sources/*.md` 引用。_",
        "",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
    ]
    if focus_lines and focus_lines != ["- 当前没有明显的机器记忆命中，先从优先来源开始。"]:
        lines.extend(["", "_机器记忆提示：_"])
        lines.extend(focus_lines)
    lines.extend(["", "## 优先来源"])
    lines.extend(compact_source_link_lines(entries))
    lines.extend(["", "## 优先概念"])
    lines.extend(compact_concept_link_lines(concepts))
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
    title = human_query_title(question)
    output_guidance = protocol_output_guidance(root, active_protocol, "sop")
    focus_lines = compact_machine_memory_focus_lines(machine_query)
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
        f"# SOP Request · {title}",
        "",
        "## 任务",
        "- 把这次问题压成可执行的 SOP 草案。",
        "- 保留前置检查、步骤、风险控制、dry-run / rollback 约束。",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "",
        "## 协议输出偏置",
    ]
    lines.extend(
        f"- {line}"
        for line in compact_output_guidance_lines(output_guidance, "当前协议没有额外的 SOP 偏置。")
    )
    lines.extend(["", "## 当前线索", *focus_lines, "", "## 优先来源"])
    lines.extend(compact_source_link_lines(entries, empty_message="- 暂无排好序的来源。"))
    lines.extend(["", "## 优先概念"])
    lines.extend(compact_concept_link_lines(concepts, empty_message="- 暂无排好序的概念页。"))
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
