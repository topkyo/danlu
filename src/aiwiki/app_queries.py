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
from .app_memory_query import (
    build_machine_memory_query_routes,
    concept_page_snapshot,
    ranked_machine_memory_anchor_nodes,
    record_query_route_telemetry,
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
    protocol_paths,
    protocol_runtime_schema_path,
    protocol_runtime_summary,
    protocol_state_path,
    protocol_title,
    resolve_protocol,
    schedule_review_windows,
)
from .app_routing import (
    active_corpus_bridge_evidence_ids,
    build_material_state_documents,
    reconcile_active_corpora_state,
    refresh_material_state,
    upsert_active_corpus,
)
from .app_shell import build_shell_summary, write_shell_summary
from .app_state_paths import (
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
from .compile.build import (
    default_concept_build_state,
    default_domain_pilot_build_state,
    default_machine_memory_build_state,
    default_output_pack_build_state,
    default_ranking_build_state,
    load_ranking_build_state,
)
from .compile.state import save_compile_state
from .config import LLMConfig
from .content.archive import (
    active_archived_material_ids,
    active_material_archive_entries,
    load_archive_candidates_state,
    load_material_archive_state,
    load_material_routing_state,
    save_material_archive_state,
)
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
from .content.material import (
    load_active_corpora_state,
    load_manual_link_state,
    load_material_state,
    save_manual_link_state,
)
from .content.memory import (
    concept_summary_is_placeholder,
    remove_stale_generated_markdown_files,
)
from .content.outputs import classify_recurring_output_kind
from .content.rewrite import load_concept_rewrite_state, save_concept_rewrite_state
from .execution.history import append_runtime_history
from .execution.lifecycle import concept_lifecycle_entry, concept_page_path
from .execution.patch_plan import build_page_patch_plan
from .execution.policy import (
    append_execution_policy_decisions,
    execution_policy_decision_record,
    load_execution_receipt_history,
)
from .execution.repair_plan import (
    _validate_rewrite_candidate_markdown,
    build_machine_memory_repair_plan,
    repair_execution_proposals,
    rewrite_proposal_candidate_is_current,
    rewrite_proposal_is_apply_ready,
)
from .lifecycle.knowledge import (
    ensure_knowledge_lifecycle_override_state,
    load_knowledge_lifecycle_state,
    save_knowledge_lifecycle_override_state,
)
from .memory.action_core import (
    action_supports_low_risk_apply,
    placeholder_concept_slugs,
    remove_stale_generated_execution_bundle_files,
    remove_stale_generated_execution_proposal_pages,
    safe_apply_preview,
    validate_low_risk_action_targets,
)
from .memory.action_state import load_machine_memory_action_state, save_machine_memory_action_state
from .memory.actions import reconcile_machine_memory_actions
from .memory.build_plan import plan_machine_memory_build
from .memory.builder import build_machine_memory
from .memory.core import (
    machine_memory_digest,
    machine_memory_snapshot_is_reusable,
    reuse_machine_memory_core,
)
from .memory.execution_surfaces import (
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
from .memory.graph import (
    append_machine_memory_history,
    build_machine_memory_query,
    render_machine_memory_graph_html,
    summarize_machine_memory_transition,
)
from .memory.graph_builder import build_machine_memory_graph
from .memory.health import build_machine_memory_health
from .memory.judgment_assets import attach_judgment_assets_to_machine_memory
from .memory.state import load_machine_memory
from .memory.status import (
    render_drift_report,
    render_graph_health,
    render_machine_memory_actions,
    render_machine_memory_index,
    render_machine_memory_repair_plan,
)
from .memory.topology import render_machine_memory_topology
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
    protocol_output_pack_rows,
    render_output_packs_index,
)
from .render.paths import (
    append_wiki_log,
    ensure_wiki_log,
    execution_bundle_path,
    execution_proposal_path,
    execution_receipt_path,
    remove_stale_generated_concept_pages,
    review_packs_dir,
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
from .state.constants import (
    DEFAULT_PROTOCOL,
    JUDGMENT_LIFECYCLE_STATES,
    KNOWLEDGE_LIFECYCLE_KINDS,
    KNOWLEDGE_LIFECYCLE_STATES,
)
from .state.io import load_json_document
from .state.manifest import load_manifest
from .utils.hash import compiled_source_sha, question_signature, sha256_bytes
from .utils.io import (
    runtime_write_operation,
    write_if_changed,
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from .utils.markdown import (
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
from .utils.path import next_available_stem, relative_path
from .utils.text import slugify, tokenize
from .utils.time import utc_now

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
    if str(frontmatter.get("source_updated_at") or "") != str(
        entry.get("updated_at") or entry.get("imported_at") or ""
    ):
        return True
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
    # Lazy import: ``aiwiki.compile.ranking`` triggers ``aiwiki.compile.__init__``
    # which imports ``compile.pipeline`` → ``compile.content_step`` → ``app_queries``,
    # forming a cycle when placed at module level.
    from .compile.ranking import (
        build_ranking_source_record,
        ranking_source_record_is_reusable,
        ranking_source_summary_or_preview,
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
        f"- 提升权重的判断：`{', '.join(machine_query.get('ranked_judgment_ids', [])) or 'none'}`",
        f"- 提升权重的金丹：`{', '.join(machine_query.get('ranked_elixir_ids', [])) or 'none'}`",
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
    bridge_concepts = [str(slug).strip() for slug in machine_query.get("bridge_concept_slugs", []) if str(slug).strip()]
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


def compound_rank_boosts(
    memory: dict[str, Any],
    machine_query: dict[str, Any],
) -> tuple[set[str], set[str]]:
    """Derive source/concept boost ids from ranked confirmed judgments and settled elixirs."""

    ranked_judgments = {
        str(page_id).strip() for page_id in machine_query.get("ranked_judgment_ids", []) or [] if str(page_id).strip()
    }
    ranked_elixirs = {
        str(elixir_id).strip()
        for elixir_id in machine_query.get("ranked_elixir_ids", []) or []
        if str(elixir_id).strip()
    }
    boost_sources: set[str] = set()
    edges = memory.get("edges", {})
    source_to_concepts: dict[str, set[str]] = {}
    for edge in edges.get("source_to_concept", []):
        if not isinstance(edge, dict):
            continue
        source_id = str(edge.get("source_id") or "").strip()
        concept_slug = str(edge.get("concept_slug") or "").strip()
        if source_id and concept_slug:
            source_to_concepts.setdefault(source_id, set()).add(concept_slug)

    for node in memory.get("judgment_nodes", []):
        if not isinstance(node, dict):
            continue
        page_id = str(node.get("page_id") or "").strip()
        if page_id not in ranked_judgments:
            continue
        for source_id in node.get("source_ids", []) or []:
            normalized = str(source_id or "").strip()
            if normalized:
                boost_sources.add(normalized)

    for edge in edges.get("source_to_judgment", []):
        if not isinstance(edge, dict):
            continue
        page_id = str(edge.get("page_id") or "").strip()
        source_id = str(edge.get("source_id") or "").strip()
        if page_id in ranked_judgments and source_id:
            boost_sources.add(source_id)

    for edge in edges.get("elixir_derived_from", []):
        if not isinstance(edge, dict):
            continue
        elixir_id = str(edge.get("elixir_id") or "").strip()
        if elixir_id not in ranked_elixirs:
            continue
        if str(edge.get("from_kind") or "").strip() == "source":
            from_id = str(edge.get("from_id") or "").strip()
            if from_id:
                boost_sources.add(from_id)

    boost_concepts: set[str] = set()
    for source_id in boost_sources:
        boost_concepts.update(source_to_concepts.get(source_id, set()))
    return boost_sources, boost_concepts


def ranked_compound_page_paths(
    machine_query: dict[str, Any],
    *,
    judgment_limit: int = 3,
    elixir_limit: int = 2,
) -> list[str]:
    subgraph = machine_query.get("query_subgraph", {}) or {}
    refs: list[str] = []
    for node in subgraph.get("judgments", []) or []:
        if not isinstance(node, dict):
            continue
        path = str(node.get("path") or "").strip()
        if path and path not in refs:
            refs.append(path)
        if len([item for item in refs if item.startswith("wiki/judgments/")]) >= judgment_limit:
            break
    for node in subgraph.get("elixirs", []) or []:
        if not isinstance(node, dict):
            continue
        path = str(node.get("path") or "").strip()
        if path and path not in refs:
            refs.append(path)
        if len([item for item in refs if item.startswith("wiki/elixirs/")]) >= elixir_limit:
            break
    return refs


def build_ask_used_refs(
    *,
    ranked_sources: list[dict[str, Any]] | None = None,
    ranked_concepts: list[dict[str, Any]] | None = None,
    compound_paths: list[str] | None = None,
    material_paths: list[str] | None = None,
) -> list[str]:
    refs: list[str] = []
    for entry in ranked_sources or []:
        if not isinstance(entry, dict):
            continue
        source_id = str(entry.get("id") or "").strip()
        if source_id:
            path = f"wiki/sources/{source_id}.md"
            if path not in refs:
                refs.append(path)
    for concept in ranked_concepts or []:
        if not isinstance(concept, dict):
            continue
        path = str(concept.get("path") or "").strip()
        if not path and concept.get("slug"):
            path = f"wiki/concepts/{concept['slug']}.md"
        if path and path not in refs:
            refs.append(path)
    for path in compound_paths or []:
        normalized = str(path or "").strip()
        if normalized and normalized not in refs:
            refs.append(normalized)
    for path in material_paths or []:
        normalized = str(path or "").strip()
        if normalized and normalized not in refs:
            refs.append(normalized)
    return refs


def compact_judgment_link_lines(
    machine_query: dict[str, Any],
    *,
    limit: int = 3,
    empty_message: str = "- 当前没有命中的已确认判断。",
) -> list[str]:
    nodes = (machine_query.get("query_subgraph", {}) or {}).get("judgments", []) or []
    if not nodes:
        return [empty_message]
    lines: list[str] = []
    for node in nodes[:limit]:
        if not isinstance(node, dict):
            continue
        title = str(node.get("title") or node.get("page_id") or "").strip()
        path = str(node.get("path") or "").strip()
        if title and path:
            lines.append(f"- [{title}](../../{path})")
    return lines or [empty_message]


def compact_elixir_link_lines(
    machine_query: dict[str, Any],
    *,
    limit: int = 2,
    empty_message: str = "- 当前没有命中的 settled 金丹。",
) -> list[str]:
    nodes = (machine_query.get("query_subgraph", {}) or {}).get("elixirs", []) or []
    if not nodes:
        return [empty_message]
    lines: list[str] = []
    for node in nodes[:limit]:
        if not isinstance(node, dict):
            continue
        title = str(node.get("title") or node.get("elixir_id") or "").strip()
        path = str(node.get("path") or "").strip()
        if title and path:
            lines.append(f"- [{title}](../../{path})")
    return lines or [empty_message]


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
    focus_lines = compact_machine_memory_focus_lines(machine_query)
    frontmatter = render_frontmatter(
        {
            "kind": "output",
            "format": "report",
            "cssclasses": ["aiwiki-output"],
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
        "## 参考",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "",
    ]
    if focus_lines and focus_lines != ["- 当前没有明显的机器记忆命中，先从优先来源开始。"]:
        lines.extend(["", "_机器记忆提示：_"])
        lines.extend(focus_lines)
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
    if machine_query.get("ranked_judgment_ids") or (machine_query.get("query_subgraph", {}) or {}).get("judgments"):
        lines.extend(
            [
                "",
                "_优先判断：_",
            ]
        )
        lines.extend(compact_judgment_link_lines(machine_query))
    if machine_query.get("ranked_elixir_ids") or (machine_query.get("query_subgraph", {}) or {}).get("elixirs"):
        lines.extend(
            [
                "",
                "_优先金丹：_",
            ]
        )
        lines.extend(compact_elixir_link_lines(machine_query))
    return "\n".join(lines) + "\n"
