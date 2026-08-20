"""Ask report scaffold and compact machine-memory focus lines.

Extracted from render.views (hub single seam 2026-08-05).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..protocol.descriptors import protocol_title
from ..utils.markdown import render_frontmatter
from ..utils.text import human_query_title


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
    empty_message: str = "- 还没有排好序的来源。先在 ingest 后运行 `aiwiki advanced compile`。",
) -> list[str]:
    if not entries:
        return [empty_message]
    return [f"- [{entry['title']}](../../wiki/sources/{entry['id']}.md)" for entry in entries[:limit]]


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
            # Pending scaffold must not appear as a deliverable report while LLM runs.
            "llm_status": "pending",
            "delivery_mode": "llm-pending",
            "artifact_quality": "placeholder",
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {title}",
        "",
        "_LLM: awaiting synthesis.",
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
