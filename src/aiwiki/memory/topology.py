"""Machine-memory topology slice renderer.

EP-017B step 2: extracted from app_memory_surfaces.py. Re-exported via the
facade at aiwiki.app_memory_surfaces for backward compatibility.
"""

from __future__ import annotations

from typing import Any

from ..app_utils import slugify


def render_machine_memory_topology(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    hub_concepts = health.get("hub_concepts", [])
    hub_sources = health.get("hub_sources", [])
    link_suggestions = health.get("link_suggestions", [])
    judgment_nodes = {node["page_id"]: node for node in memory.get("judgment_nodes", []) if isinstance(node, dict)}
    judgment_relation_counts: dict[str, int] = {}
    for edge in memory.get("edges", {}).get("source_to_judgment", []):
        page_id = str(edge.get("page_id") or "")
        if page_id:
            judgment_relation_counts[page_id] = judgment_relation_counts.get(page_id, 0) + 1
    for group in ("judgment_to_judgment", "judgment_to_decision"):
        for edge in memory.get("edges", {}).get(group, []):
            left = str(edge.get("from") or "")
            right = str(edge.get("to") or "")
            if left:
                judgment_relation_counts[left] = judgment_relation_counts.get(left, 0) + 1
            if right:
                judgment_relation_counts[right] = judgment_relation_counts.get(right, 0) + 1
    hub_judgments = sorted(
        [
            {
                "page_id": page_id,
                "title": str(node.get("title") or page_id),
                "path": str(node.get("path") or ""),
                "relation_count": judgment_relation_counts.get(page_id, 0),
                "source_count": len(node.get("source_ids", [])),
                "kind": str(node.get("kind") or "judgment"),
            }
            for page_id, node in judgment_nodes.items()
            if judgment_relation_counts.get(page_id, 0) > 0
        ],
        key=lambda item: (-item["relation_count"], -item["source_count"], item["title"].lower()),
    )
    lines = [
        "# 机器记忆拓扑",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        f"- 已索引分量：`{health.get('component_count', 0)}`",
        f"- Hub 概念：`{len(hub_concepts)}`",
        f"- Hub 来源：`{len(hub_sources)}`",
        f"- Judgment 关系 Hub：`{len(hub_judgments)}`",
        f"- 修复候选：`{len(link_suggestions)}`",
        "",
        "## Hub 概念",
    ]
    if not hub_concepts:
        lines.append("- 当前没有可展示的 hub 概念。")
    else:
        for item in hub_concepts[:10]:
            lines.append(
                f"- [{item['title']}](../concepts/{item['slug']}.md)"
                f" | sources `{item['source_count']}`"
                f" | related `{item['related_count']}`"
                f" | component `{item['component_id'] or 'none'}`"
            )
    lines.extend(["", "## Hub 来源"])
    if not hub_sources:
        lines.append("- 当前没有可展示的 hub 来源。")
    else:
        for item in hub_sources[:10]:
            lines.append(
                f"- [{item['title']}](../sources/{item['id']}.md)"
                f" | concepts `{item['concept_count']}`"
                f" | component `{item['component_id'] or 'none'}`"
            )
    lines.extend(["", "## 修复候选"])
    if not link_suggestions:
        lines.append("- 当前没有机器记忆修复候选。")
    else:
        for suggestion in link_suggestions[:10]:
            lines.append(
                f"- [{suggestion['source_title']}](../sources/{suggestion['source_id']}.md)"
                f" -> [{suggestion['concept_title']}](../concepts/{suggestion['concept_slug']}.md)"
                f" | shared `{', '.join(suggestion['shared_terms'][:6])}`"
                f" | score `{suggestion['score']}`"
            )
    lines.extend(["", "## Judgment Hub"])
    if not hub_judgments:
        lines.append("- 当前还没有显式 judgment relation hub。")
    else:
        for item in hub_judgments[:10]:
            lines.append(
                f"- [{item['title']}](../{item['path']})"
                f" | relations `{item['relation_count']}`"
                f" | sources `{item['source_count']}`"
                f" | kind `{item['kind']}`"
            )
    lines.extend(["", "## Mermaid 拓扑切片", "```mermaid", "graph LR"])
    node_lines: list[str] = []
    edge_lines: list[str] = []
    added_nodes: set[str] = set()
    hub_concept_slugs = {item["slug"] for item in hub_concepts[:5]}
    hub_source_ids = {item["id"] for item in hub_sources[:5]}
    hub_judgment_ids = {item["page_id"] for item in hub_judgments[:5]}
    concept_by_slug = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    source_by_id = {node["id"]: node for node in memory.get("source_nodes", [])}
    for source_id in sorted(hub_source_ids):
        node = source_by_id.get(source_id)
        if not node:
            continue
        node_key = f"src_{slugify(source_id).replace('-', '_')}"
        if node_key in added_nodes:
            continue
        added_nodes.add(node_key)
        label = str(node["title"]).replace('"', "'")
        node_lines.append(f'    {node_key}["S: {label}"]')
    for concept_slug in sorted(hub_concept_slugs):
        node = concept_by_slug.get(concept_slug)
        if not node:
            continue
        node_key = f"concept_{slugify(concept_slug).replace('-', '_')}"
        if node_key in added_nodes:
            continue
        added_nodes.add(node_key)
        label = str(node["title"]).replace('"', "'")
        node_lines.append(f'    {node_key}["C: {label}"]')
    for page_id in sorted(hub_judgment_ids):
        node = judgment_nodes.get(page_id)
        if not node:
            continue
        node_key = f"judgment_{slugify(page_id).replace('-', '_')}"
        if node_key in added_nodes:
            continue
        added_nodes.add(node_key)
        label = str(node.get("title") or page_id).replace('"', "'")
        node_lines.append(f'    {node_key}["J: {label}"]')
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        source_id = edge.get("source_id")
        concept_slug = edge.get("concept_slug")
        if source_id not in hub_source_ids or concept_slug not in hub_concept_slugs:
            continue
        left = f"src_{slugify(source_id).replace('-', '_')}"
        right = f"concept_{slugify(concept_slug).replace('-', '_')}"
        edge_lines.append(f"    {left} --> {right}")
    seen_related_pairs: set[tuple[str, str]] = set()
    for edge in memory.get("edges", {}).get("concept_to_concept", []):
        left_slug = edge.get("from")
        right_slug = edge.get("to")
        if left_slug not in hub_concept_slugs or right_slug not in hub_concept_slugs:
            continue
        pair = tuple(sorted((str(left_slug), str(right_slug))))
        if pair in seen_related_pairs:
            continue
        seen_related_pairs.add(pair)
        left = f"concept_{slugify(left_slug).replace('-', '_')}"
        right = f"concept_{slugify(right_slug).replace('-', '_')}"
        edge_lines.append(f"    {left} -.-> {right}")
    for edge in memory.get("edges", {}).get("source_to_judgment", []):
        source_id = str(edge.get("source_id") or "")
        page_id = str(edge.get("page_id") or "")
        if source_id not in hub_source_ids or page_id not in hub_judgment_ids:
            continue
        left = f"src_{slugify(source_id).replace('-', '_')}"
        right = f"judgment_{slugify(page_id).replace('-', '_')}"
        edge_lines.append(f"    {left} --> {right}")
    for edge in memory.get("edges", {}).get("judgment_to_judgment", []):
        left_id = str(edge.get("from") or "")
        right_id = str(edge.get("to") or "")
        if left_id not in hub_judgment_ids or right_id not in hub_judgment_ids:
            continue
        left = f"judgment_{slugify(left_id).replace('-', '_')}"
        right = f"judgment_{slugify(right_id).replace('-', '_')}"
        if str(edge.get("relation") or "") == "supports":
            edge_lines.append(f"    {left} --> {right}")
        elif str(edge.get("relation") or "") == "contradicts":
            edge_lines.append(f"    {left} -.-> {right}")
        else:
            edge_lines.append(f"    {left} --- {right}")
    for edge in memory.get("edges", {}).get("judgment_to_decision", []):
        left_id = str(edge.get("from") or "")
        right_id = str(edge.get("to") or "")
        if left_id not in hub_judgment_ids or right_id not in hub_judgment_ids:
            continue
        left = f"judgment_{slugify(left_id).replace('-', '_')}"
        right = f"judgment_{slugify(right_id).replace('-', '_')}"
        edge_lines.append(f"    {left} ==> {right}")
    if not node_lines:
        lines.append('    placeholder["Not enough machine-memory nodes yet"]')
    else:
        lines.extend(node_lines)
        lines.extend(edge_lines[:24])
    lines.extend(
        [
            "```",
            "",
            "## 相关链接",
            "- [机器记忆](./machine-memory.md)",
            "- [图谱健康](./graph-health.md)",
            "- [动作队列](./machine-memory-actions.md)",
            "- [修复计划](./machine-memory-repair-plan.md)",
            "- [修复待办](./repair-backlog.md)",
            "- [概念质量](./concept-quality.md)",
        ]
    )
    return "\n".join(lines) + "\n"


