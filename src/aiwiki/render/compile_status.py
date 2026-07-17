"""Compile status markdown rendering."""

from __future__ import annotations

from typing import Any

from ..app_lifecycle import collect_aging_signals, review_queue
from ..app_protocol import protocol_title
from ..app_state import default_compile_state

DETAIL_LABELS = {
    "manifest_entries": "entries",
    "changed_entries": "changed",
    "added_entries": "added",
    "updated_entries": "updated",
    "removed_entries": "removed",
    "source_pages": "sources",
    "dirty_sources": "dirty",
    "clean_sources": "clean",
    "updated_pages": "updated_pages",
    "skipped_pages": "skipped_pages",
    "concept_sources": "concept_sources",
    "dirty_concept_sources": "dirty_concept_sources",
    "clean_concept_sources": "clean_concept_sources",
    "concept_pages": "concepts",
    "dirty_concepts": "dirty_concepts",
    "clean_concepts": "clean_concepts",
    "machine_memory_sources": "machine_memory_sources",
    "dirty_machine_memory_sources": "dirty_machine_memory_sources",
    "clean_machine_memory_sources": "clean_machine_memory_sources",
    "machine_memory_concepts": "machine_memory_concepts",
    "dirty_machine_memory_concepts": "dirty_machine_memory_concepts",
    "clean_machine_memory_concepts": "clean_machine_memory_concepts",
    "reused_core": "reused_core",
    "ranking_sources": "ranking_sources",
    "dirty_ranking_sources": "dirty_ranking_sources",
    "clean_ranking_sources": "clean_ranking_sources",
    "ranking_concepts": "ranking_concepts",
    "dirty_ranking_concepts": "dirty_ranking_concepts",
    "clean_ranking_concepts": "clean_ranking_concepts",
    "pack_groups": "pack_groups",
    "dirty_pack_groups": "dirty_pack_groups",
    "clean_pack_groups": "clean_pack_groups",
    "review_packs": "review_packs",
    "decision_memos": "decision_memos",
    "sop_drafts": "sop_drafts",
    "pilot_protocols": "pilot_protocols",
    "dirty_protocols": "dirty_protocols",
    "clean_protocols": "clean_protocols",
    "tracked_artifacts": "tracked_artifacts",
    "dirty_artifacts": "dirty_artifacts",
    "clean_artifacts": "clean_artifacts",
    "updated_artifacts": "updated_artifacts",
    "skipped_artifacts": "skipped_artifacts",
    "removed_generated_pages": "removed_generated_pages",
    "material_state_entries": "material_state_entries",
    "archive_candidates": "archive_candidates",
    "active_corpora": "active_corpora",
    "knowledge_lifecycle_entries": "knowledge_lifecycle_entries",
}


def compile_state_string_list(compile_state: dict[str, Any], key: str) -> list[str]:
    return [str(item) for item in compile_state.get(key, []) if str(item)]


def compile_phase_lines(
    phase_summary: list[dict[str, Any]],
    detail_labels: dict[str, str] | None = None,
) -> list[str]:
    if not phase_summary:
        return ["- 当前还没有 compile phase summary。"]
    labels = detail_labels or DETAIL_LABELS
    lines: list[str] = []
    for phase in phase_summary:
        details = phase.get("details", {})
        detail_chunks = []
        if isinstance(details, dict):
            for key, value in details.items():
                if key in labels:
                    detail_chunks.append(f"{labels[key]}={value}")
        label = str(phase.get("label") or phase.get("name") or "")
        mode = str(phase.get("mode") or "full")
        status = str(phase.get("status") or "completed")
        detail_suffix = f" | {', '.join(detail_chunks)}" if detail_chunks else ""
        lines.append(f"- `{phase['name']}` `{label}` [{mode}/{status}]{detail_suffix}")
    return lines


def source_link_lines(
    source_ids: list[str],
    entry_by_id: dict[str, dict[str, Any]],
    *,
    empty_message: str,
    overflow_label: str,
) -> list[str]:
    if not source_ids:
        return [empty_message]
    lines = []
    for entry_id in source_ids[:8]:
        entry = entry_by_id.get(entry_id, {})
        title = str(entry.get("title") or entry_id)
        lines.append(f"- [{title}](../sources/{entry_id}.md)")
    if len(source_ids) > 8:
        lines.append(f"- 其余 {overflow_label}：`{len(source_ids) - 8}`")
    return lines


def concept_link_lines(
    concept_slugs: list[str],
    concept_by_slug: dict[str, dict[str, Any]],
    *,
    empty_message: str,
    overflow_label: str,
) -> list[str]:
    if not concept_slugs:
        return [empty_message]
    lines = []
    for slug in concept_slugs[:8]:
        record = concept_by_slug.get(slug, {})
        title = str(record.get("title") or slug)
        lines.append(f"- [{title}](../concepts/{slug}.md)")
    if len(concept_slugs) > 8:
        lines.append(f"- 其余 {overflow_label}：`{len(concept_slugs) - 8}`")
    return lines


def artifact_lines(values: list[str], *, empty_message: str, overflow_label: str, limit: int = 12) -> list[str]:
    if not values:
        return [empty_message]
    lines = [f"- `{relative}`" for relative in values[:limit]]
    if len(values) > limit:
        lines.append(f"- 其余 {overflow_label}：`{len(values) - limit}`")
    return lines


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
    active_protocol = protocol_state["active_protocol"]
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    compile_state = compile_state or default_compile_state()
    phase_summary = [
        phase
        for phase in compile_state.get("phase_summary", [])
        if isinstance(phase, dict) and str(phase.get("name") or "")
    ]
    lists = {
        key: compile_state_string_list(compile_state, key)
        for key in (
            "dirty_source_ids",
            "clean_source_ids",
            "dirty_concept_source_ids",
            "clean_concept_source_ids",
            "dirty_concept_slugs",
            "clean_concept_slugs",
            "dirty_machine_memory_source_ids",
            "clean_machine_memory_source_ids",
            "dirty_machine_memory_concept_slugs",
            "clean_machine_memory_concept_slugs",
            "dirty_ranking_source_ids",
            "clean_ranking_source_ids",
            "dirty_ranking_concept_slugs",
            "clean_ranking_concept_slugs",
            "dirty_output_pack_groups",
            "clean_output_pack_groups",
            "dirty_domain_pilot_protocols",
            "clean_domain_pilot_protocols",
            "dirty_index_artifacts",
            "clean_index_artifacts",
            "dirty_maintenance_artifacts",
            "clean_maintenance_artifacts",
        )
    }
    entry_by_id = {
        str(entry.get("id") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("id") or "")
    }
    concept_by_slug = {
        str(record.get("slug") or ""): record
        for record in concepts
        if isinstance(record, dict) and str(record.get("slug") or "")
    }
    lines = [
        "# 编译状态",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源页：`{len(entries)}`",
        f"- 概念页：`{len(concepts)}`",
        f"- 决策页：`{len(decisions)}`",
        f"- 判断页：`{len(judgments)}`",
        f"- 当前 active protocol：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 待审项目：`{len(queue['pending_decisions']) + len(queue['pending_judgments'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级：`{len(aging['escalated'])}`",
        f"- 证据漂移：`{sum(1 for page in decisions + judgments if page.get('citation_drift') == 'true')}`",
        "- Compile state：`.aiwiki/state/compile-state.json`",
        "- Concept build state：`.aiwiki/state/concept-build-state.json`",
        "- Machine memory build state：`.aiwiki/state/machine-memory-build-state.json`",
        "- Ranking build state：`.aiwiki/state/ranking-build-state.json`",
        "- Output pack build state：`.aiwiki/state/output-pack-build-state.json`",
        "- Domain pilot build state：`.aiwiki/state/domain-pilot-build-state.json`",
        f"- Dirty source：`{len(lists['dirty_source_ids'])}`",
        f"- Clean source：`{len(lists['clean_source_ids'])}`",
        f"- Dirty concept source：`{len(lists['dirty_concept_source_ids'])}`",
        f"- Clean concept source：`{len(lists['clean_concept_source_ids'])}`",
        f"- Dirty concept：`{len(lists['dirty_concept_slugs'])}`",
        f"- Clean concept：`{len(lists['clean_concept_slugs'])}`",
        f"- Dirty machine-memory source：`{len(lists['dirty_machine_memory_source_ids'])}`",
        f"- Clean machine-memory source：`{len(lists['clean_machine_memory_source_ids'])}`",
        f"- Dirty machine-memory concept：`{len(lists['dirty_machine_memory_concept_slugs'])}`",
        f"- Clean machine-memory concept：`{len(lists['clean_machine_memory_concept_slugs'])}`",
        f"- Machine-memory core reused：`{bool(compile_state.get('machine_memory_core_reused', False))}`",
        f"- Dirty ranking source：`{len(lists['dirty_ranking_source_ids'])}`",
        f"- Clean ranking source：`{len(lists['clean_ranking_source_ids'])}`",
        f"- Dirty ranking concept：`{len(lists['dirty_ranking_concept_slugs'])}`",
        f"- Clean ranking concept：`{len(lists['clean_ranking_concept_slugs'])}`",
        f"- Dirty output pack group：`{len(lists['dirty_output_pack_groups'])}`",
        f"- Clean output pack group：`{len(lists['clean_output_pack_groups'])}`",
        f"- Dirty domain pilot protocol：`{len(lists['dirty_domain_pilot_protocols'])}`",
        f"- Clean domain pilot protocol：`{len(lists['clean_domain_pilot_protocols'])}`",
        f"- Dirty index artifact：`{len(lists['dirty_index_artifacts'])}`",
        f"- Clean index artifact：`{len(lists['clean_index_artifacts'])}`",
        f"- Dirty maintenance artifact：`{len(lists['dirty_maintenance_artifacts'])}`",
        f"- Clean maintenance artifact：`{len(lists['clean_maintenance_artifacts'])}`",
        "- 总索引位于 `index.md`。",
        "- 运行时规则位于 `schema/`。",
        "- 协议规则位于 `schema/protocols/`。",
        "- 协议总览位于 `protocols.md`。",
        "- 炉心面板位于 `furnace-center.md`。",
        "- 执行中心位于 `execution-center.md`。",
        "- 输出 Pack 总览位于 `output-packs.md`。",
        "- 领域 Pilot 总览位于 `domain-pilots.md`。",
        "- 操作日志位于 `log.md`。",
        "- Agent Workbench 位于 `agent-workbench.md`。",
        "- 决策索引位于 `decisions.md`。",
        "- 判断索引位于 `judgments.md`。",
        "- 判断资产盘点位于 `judgment-assets.md`。",
        "- 认知历史位于 `cognitive-history.md`。",
        "- 审阅队列位于 `review-queue.md`。",
        "- 审阅中心位于 `review-center.md`。",
        "- aging 报告位于 `aging-report.md`。",
        "- 机器记忆摘要位于 `machine-memory.md`。",
        "- 图谱视图位于 `graph-view.md`。",
        "- 机器记忆拓扑位于 `machine-memory-topology.md`。",
        "- 机器记忆动作队列位于 `machine-memory-actions.md`。",
        "- 机器记忆修复计划位于 `machine-memory-repair-plan.md`。",
        "- Rewrite 提案队列位于 `rewrite-proposals.md`。",
        "- 图谱健康页位于 `graph-health.md`。",
        "- 漂移报告位于 `drift-report.md`。",
        "- 修复待办位于 `repair-backlog.md`。",
        "- derived、decision、judgment 页面通过 `aiwiki file-back` 显式回流。",
        "- lint 结果输出在 `.aiwiki/lint/`。",
        "",
        "## Compile Phases",
        *compile_phase_lines(phase_summary),
    ]
    linked_sections = [
        (
            "Dirty Sources",
            source_link_lines(
                lists["dirty_source_ids"],
                entry_by_id,
                empty_message="- 当前没有 dirty source page。",
                overflow_label="dirty source",
            ),
        ),
        (
            "Dirty Concept Sources",
            source_link_lines(
                lists["dirty_concept_source_ids"],
                entry_by_id,
                empty_message="- 当前没有 dirty concept source。",
                overflow_label="dirty concept source",
            ),
        ),
        (
            "Dirty Machine Memory Sources",
            source_link_lines(
                lists["dirty_machine_memory_source_ids"],
                entry_by_id,
                empty_message="- 当前没有 dirty machine-memory source input。",
                overflow_label="dirty machine-memory source",
            ),
        ),
        (
            "Dirty Concepts",
            concept_link_lines(
                lists["dirty_concept_slugs"],
                concept_by_slug,
                empty_message="- 当前没有 dirty concept page。",
                overflow_label="dirty concept",
            ),
        ),
        (
            "Dirty Machine Memory Concepts",
            concept_link_lines(
                lists["dirty_machine_memory_concept_slugs"],
                concept_by_slug,
                empty_message="- 当前没有 dirty machine-memory concept input。",
                overflow_label="dirty machine-memory concept",
            ),
        ),
        (
            "Dirty Ranking Sources",
            source_link_lines(
                lists["dirty_ranking_source_ids"],
                entry_by_id,
                empty_message="- 当前没有 dirty ranking source record。",
                overflow_label="dirty ranking source",
            ),
        ),
        (
            "Clean Ranking Sources",
            source_link_lines(
                lists["clean_ranking_source_ids"],
                entry_by_id,
                empty_message="- 当前没有 clean ranking source record。",
                overflow_label="clean ranking source",
            ),
        ),
        (
            "Dirty Ranking Concepts",
            concept_link_lines(
                lists["dirty_ranking_concept_slugs"],
                concept_by_slug,
                empty_message="- 当前没有 dirty ranking concept record。",
                overflow_label="dirty ranking concept",
            ),
        ),
        (
            "Clean Ranking Concepts",
            concept_link_lines(
                lists["clean_ranking_concept_slugs"],
                concept_by_slug,
                empty_message="- 当前没有 clean ranking concept record。",
                overflow_label="clean ranking concept",
            ),
        ),
        (
            "Dirty Output Pack Groups",
            artifact_lines(
                lists["dirty_output_pack_groups"],
                empty_message="- 当前没有 dirty output pack group。",
                overflow_label="dirty output pack group",
                limit=10**9,
            ),
        ),
        (
            "Clean Output Pack Groups",
            artifact_lines(
                lists["clean_output_pack_groups"],
                empty_message="- 当前没有 clean output pack group。",
                overflow_label="clean output pack group",
                limit=10**9,
            ),
        ),
        (
            "Dirty Domain Pilot Protocols",
            artifact_lines(
                lists["dirty_domain_pilot_protocols"],
                empty_message="- 当前没有 dirty domain pilot protocol。",
                overflow_label="dirty domain pilot protocol",
                limit=10**9,
            ),
        ),
        (
            "Clean Domain Pilot Protocols",
            artifact_lines(
                lists["clean_domain_pilot_protocols"],
                empty_message="- 当前没有 clean domain pilot protocol。",
                overflow_label="clean domain pilot protocol",
                limit=10**9,
            ),
        ),
        (
            "Dirty Index Artifacts",
            artifact_lines(
                lists["dirty_index_artifacts"],
                empty_message="- 当前没有 dirty index artifact。",
                overflow_label="dirty artifact",
            ),
        ),
        (
            "Dirty Maintenance Artifacts",
            artifact_lines(
                lists["dirty_maintenance_artifacts"],
                empty_message="- 当前没有 dirty maintenance artifact。",
                overflow_label="dirty artifact",
            ),
        ),
    ]
    for heading, section_lines in linked_sections:
        lines.extend(["", f"## {heading}", *section_lines])
    return "\n".join(lines) + "\n"
