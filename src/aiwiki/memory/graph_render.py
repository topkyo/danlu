"""Machine-memory graph rendering primitives and HTML output.

EP-017B step 2: extracted from memory/graph.py. Holds the relation label /
style tables and the graph HTML renderer. Re-exported via the thin
``memory.graph`` facade for backward compatibility.
"""

from __future__ import annotations

import html
from typing import Any

from ..render.html_theme import html_meta_theme, html_theme_css
from ..state.constants import DEFAULT_PROTOCOL
from ..utils.json_utils import html_safe_json_literal

# Single source of truth for relationship graph language.
# Keep machine edge types in english (graph schema is unchanged); only the
# human-facing strings are translated. Naming patterns:
#   * cross-kind edges: "{源类型}{动词}{目标类型}" -> 材料提到概念 / 材料支撑判断
#   * same-kind edges: "{节点类型}{关系动词}" -> 概念相关 / 判断支持 / 决策依据 / 因果X
RELATION_LABELS: dict[str, str] = {
    "HAS_CONCEPT": "材料提到概念",
    "SUPPORTS_JUDGMENT": "材料支撑判断",
    "RELATED_CONCEPT": "概念相关",
    "JUDGMENT_SUPPORTS": "判断支持",
    "JUDGMENT_CONTRADICTS": "判断冲突",
    "JUDGMENT_RELATED": "判断相关",
    "DECISION_SUPPORTS": "决策依据",
    "DECISION_CONTRADICTS": "决策反证",
    "DECISION_RELATED": "决策相关",
    "DECISION_SUPERSEDES": "决策替代",
    "CAUSAL_CAUSES": "因果导致",
    "CAUSAL_ENABLES": "因果促成",
    "CAUSAL_CONSTRAINS": "因果约束",
    "CAUSAL_CONFLICTS_WITH": "因果冲突",
    "CAUSAL_BLOCKS": "因果阻塞",
    "ELIXIR_DERIVED_FROM": "金丹承接",
}

_RELATION_FAMILY_FALLBACK: tuple[tuple[str, str], ...] = (
    ("JUDGMENT_", "判断关系"),
    ("DECISION_", "决策关系"),
    ("CAUSAL_", "因果关系"),
)


def relation_label(edge_type: str) -> str:
    """Return the chinese label for a graph edge type.

    Unknown edge types fall back to a chinese family label (e.g. ``判断关系``)
    or ``其他关系`` so the human-facing surface never leaks english relation
    codes.
    """
    if not edge_type:
        return "其他关系"
    if edge_type in RELATION_LABELS:
        return RELATION_LABELS[edge_type]
    for prefix, family in _RELATION_FAMILY_FALLBACK:
        if edge_type.startswith(prefix):
            return family
    return "其他关系"


# Stroke colors and dash styles for SVG edges; keeps each relation visually
# distinguishable from the fallback so the legend stays readable.
_RELATION_STYLES: dict[str, tuple[str, str]] = {
    "HAS_CONCEPT": ("#0ea5e9", ""),  # sky-500, dedicated color (was fallback grey)
    "RELATED_CONCEPT": ("#f59e0b", ' stroke-dasharray="8 6"'),
    "SUPPORTS_JUDGMENT": ("#c2410c", ' stroke-dasharray="6 4"'),
    "ELIXIR_DERIVED_FROM": ("#facc15", ' stroke-dasharray="10 4"'),
}

_FAMILY_STYLES: tuple[tuple[str, tuple[str, str]], ...] = (
    ("JUDGMENT_CONTRADICTS", ("#dc2626", ' stroke-dasharray="4 4"')),
    ("JUDGMENT_SUPPORTS", ("#16a34a", ' stroke-dasharray="10 5"')),
    ("DECISION_SUPPORTS", ("#2563eb", "")),
)

_FAMILY_FALLBACK_STYLES: tuple[tuple[str, tuple[str, str]], ...] = (
    ("JUDGMENT_", ("#7c3aed", ' stroke-dasharray="3 6"')),
    ("DECISION_", ("#b91c1c", "")),
    ("CAUSAL_", ("#0891b2", ' stroke-dasharray="12 4"')),
)


def relation_style(edge_type: str) -> tuple[str, str]:
    """Return ``(stroke_color, dash_attr)`` for a graph edge type."""
    if edge_type in _RELATION_STYLES:
        return _RELATION_STYLES[edge_type]
    for key, style in _FAMILY_STYLES:
        if edge_type == key:
            return style
    for prefix, style in _FAMILY_FALLBACK_STYLES:
        if edge_type.startswith(prefix):
            return style
    return "#94a3b8", ""



def render_machine_memory_graph_html(
    memory: dict[str, Any],
    graph: dict[str, Any],
    *,
    report_anchors: dict[str, list[dict[str, str]]] | None = None,
) -> str:
    report_anchors = report_anchors or {}
    health = memory.get("health", {})
    source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    judgment_nodes = {node["page_id"]: node for node in memory.get("judgment_nodes", [])}
    components = health.get("components", [])
    judgment_edges = memory.get("edges", {}).get("source_to_judgment", [])
    judgment_by_source: dict[str, set[str]] = {}
    for edge in judgment_edges:
        source_id = str(edge.get("source_id") or "")
        page_id = str(edge.get("page_id") or "")
        if not source_id or not page_id:
            continue
        judgment_by_source.setdefault(source_id, set()).add(page_id)

    def resolve_protocol(protocols: set[str]) -> str:
        normalized = {protocol for protocol in protocols if protocol}
        if not normalized:
            return "unassigned"
        if len(normalized) == 1:
            return next(iter(normalized))
        return "mixed"

    def kind_label(kind: str) -> str:
        labels = {
            "source": "来源",
            "judgment": "判断",
            "concept": "概念",
            "elixir": "金丹",
            "decision": "决策",
            "derived": "派生",
        }
        return labels.get(kind, kind or "未知")

    def status_label(status: str) -> str:
        labels = {
            "accepted": "已采纳",
            "approved": "已批准",
            "confirmed": "已确认",
            "draft": "草稿",
            "needs-revisit": "需复核",
            "proposed": "待确认",
            "rejected": "已拒绝",
            "settled": "已沉淀",
            "superseded": "已替代",
            "tentative": "暂定",
            "tracking": "跟踪中",
            "unknown": "未知",
        }
        return labels.get(status, status or "未知")

    def protocol_label(protocol: str) -> str:
        labels = {
            "general": "通用",
            "mixed": "混合",
            "unassigned": "未分配",
        }
        return labels.get(protocol, protocol or "未分配")

    def component_display_label(component_id: str) -> str:
        if component_id == "elixir-settled":
            return "金丹关联"
        if component_id.startswith("component-"):
            suffix = component_id.removeprefix("component-")
            if suffix.isdigit():
                return f"关系组 {suffix}"
        return component_id or "未分组"

    edge_relation_label = relation_label
    edge_style = relation_style

    judgment_protocol_by_id = {
        page_id: str(node.get("protocol") or DEFAULT_PROTOCOL) for page_id, node in judgment_nodes.items()
    }
    source_protocol_by_id = {
        source_id: resolve_protocol(
            {judgment_protocol_by_id.get(page_id, "") for page_id in judgment_by_source.get(source_id, set())}
        )
        for source_id in source_nodes
    }
    concept_protocol_by_slug: dict[str, str] = {}
    for slug in concept_nodes:
        protocols = {
            source_protocol_by_id.get(source_id, "")
            for source_id, node in source_nodes.items()
            if slug in [str(item) for item in node.get("concept_slugs", []) if isinstance(item, str)]
        }
        concept_protocol_by_slug[slug] = resolve_protocol(protocols)

    def has_cjk(text: str) -> bool:
        return any("\u4e00" <= char <= "\u9fff" for char in text)

    def is_display_markdown_node(node: dict[str, Any]) -> bool:
        page_path = str(node.get("page_path") or node.get("source_page") or "").strip()
        if not page_path.endswith(".md"):
            return False
        if "chinese_related" in node:
            return bool(node.get("chinese_related"))
        return has_cjk(str(node.get("title") or ""))

    raw_graph_nodes = list(graph.get("nodes", []))

    def has_markdown_page(node: dict[str, Any]) -> bool:
        page_path = str(node.get("page_path") or node.get("source_page") or "").strip()
        return page_path.endswith(".md")

    graph_nodes = [node for node in raw_graph_nodes if is_display_markdown_node(node)]
    display_node_ids = {str(node.get("id") or "") for node in graph_nodes}
    neighbor_ids: set[str] = set()
    for edge in graph.get("edges", []):
        source_id = str(edge.get("source") or "")
        target_id = str(edge.get("target") or "")
        if source_id in display_node_ids:
            neighbor_ids.add(target_id)
        if target_id in display_node_ids:
            neighbor_ids.add(source_id)
    if neighbor_ids:
        expanded_ids = display_node_ids | neighbor_ids
        graph_nodes = [
            node for node in raw_graph_nodes if str(node.get("id") or "") in expanded_ids and has_markdown_page(node)
        ]
        display_node_ids = {str(node.get("id") or "") for node in graph_nodes}
    graph_edges = [
        edge
        for edge in graph.get("edges", [])
        if str(edge.get("source") or "") in display_node_ids and str(edge.get("target") or "") in display_node_ids
    ]
    elixir_nodes = [node for node in graph_nodes if str(node.get("kind") or "") == "elixir"]

    if not components and (source_nodes or concept_nodes or judgment_nodes):
        components = [
            {
                "id": "component-1",
                "source_ids": sorted(source_nodes),
                "concept_slugs": sorted(concept_nodes),
                "judgment_ids": sorted(judgment_nodes),
                "size": len(source_nodes) + len(concept_nodes) + len(judgment_nodes),
            }
        ]

    positions: dict[str, tuple[int, int]] = {}
    sections: list[dict[str, Any]] = []
    current_y = 36
    section_width = 980
    for component in components:
        source_ids = [
            source_id
            for source_id in component.get("source_ids", [])
            if source_id in source_nodes and f"source:{source_id}" in display_node_ids
        ]
        concept_slugs = [
            slug
            for slug in component.get("concept_slugs", [])
            if slug in concept_nodes and f"concept:{slug}" in display_node_ids
        ]
        judgment_ids = sorted(
            {
                page_id
                for source_id in source_ids
                for page_id in judgment_by_source.get(source_id, set())
                if page_id in judgment_nodes and f"judgment:{page_id}" in display_node_ids
            }
            | {
                page_id
                for page_id in component.get("judgment_ids", [])
                if isinstance(page_id, str) and page_id in judgment_nodes and f"judgment:{page_id}" in display_node_ids
            }
        )
        if not source_ids and not concept_slugs and not judgment_ids:
            continue
        row_count = max(len(source_ids), len(concept_slugs), len(judgment_ids), 1)
        row_gap = 68
        section_height = 96 + max(row_count - 1, 0) * row_gap
        row_top = current_y + 52
        for index, source_id in enumerate(source_ids):
            positions[f"source:{source_id}"] = (180, row_top + index * row_gap)
        for index, page_id in enumerate(judgment_ids):
            positions[f"judgment:{page_id}"] = (500, row_top + index * row_gap)
        for index, concept_slug in enumerate(concept_slugs):
            positions[f"concept:{concept_slug}"] = (820, row_top + index * row_gap)
        sections.append(
            {
                "id": component.get("id", "component"),
                "y": current_y,
                "height": section_height,
                "source_ids": source_ids,
                "judgment_ids": judgment_ids,
                "concept_slugs": concept_slugs,
            }
        )
        current_y += section_height + 28

    if elixir_nodes:
        row_gap = 72
        row_top = current_y + 52
        section_height = 96 + max(len(elixir_nodes) - 1, 0) * row_gap
        for index, node in enumerate(elixir_nodes):
            positions[str(node.get("id") or "")] = (500, row_top + index * row_gap)
        sections.append(
            {
                "id": "elixir-settled",
                "y": current_y,
                "height": section_height,
                "source_ids": [],
                "judgment_ids": [],
                "concept_slugs": [],
                "elixir_ids": [str(node.get("id") or "") for node in elixir_nodes],
            }
        )
        current_y += section_height + 28

    view_height = max(current_y + 24, 320)

    def truncate_label(text: str, limit: int = 30) -> str:
        return text if len(text) <= limit else f"{text[: limit - 3]}..."

    def edge_line_points(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int, int]:
        half_w = 120
        half_h = 22
        if x1 == x2:
            if y1 <= y2:
                return x1, y1 + half_h, x2, y2 - half_h
            return x1, y1 - half_h, x2, y2 + half_h
        if x1 < x2:
            return x1 + half_w, y1, x2 - half_w, y2
        return x1 - half_w, y1, x2 + half_w, y2

    edge_fragments: list[str] = []
    degree_map: dict[str, int] = {}
    edge_records: list[dict[str, str]] = []
    # Key by edge_type (machine-readable) so future types mapping to the same
    # chinese label do not silently merge counts. Render-time we resolve the
    # label per type when building the summary panel.
    relation_counts_by_type: dict[str, int] = {}
    for edge in graph_edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in positions or target not in positions:
            continue
        degree_map[source] = degree_map.get(source, 0) + 1
        degree_map[target] = degree_map.get(target, 0) + 1
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        lx1, ly1, lx2, ly2 = edge_line_points(x1, y1, x2, y2)
        edge_type = str(edge.get("type") or "")
        edge_label = edge_relation_label(edge_type)
        relation_counts_by_type[edge_type] = relation_counts_by_type.get(edge_type, 0) + 1
        stroke, dash = edge_style(edge_type)
        edge_fragments.append(
            f'<line class="graph-edge" data-source="{html.escape(source)}" data-target="{html.escape(target)}" '
            f'data-relation-type="{html.escape(edge_type)}" data-relation-label="{html.escape(edge_label)}" '
            f'x1="{lx1}" y1="{ly1}" x2="{lx2}" y2="{ly2}" stroke="{stroke}" stroke-width="2.5"{dash} opacity="0.88">'
            f"<title>{html.escape(edge_label)}</title></line>"
        )
        edge_records.append(
            {
                "source": source,
                "target": target,
                "type": edge_type,
                "label": edge_label,
            }
        )

    node_fragments: list[str] = []
    node_rows: list[str] = []
    node_records: list[dict[str, Any]] = []
    source_component_ids = health.get("source_component_ids", {})
    concept_component_ids = health.get("concept_component_ids", {})
    judgment_component_ids: dict[str, str] = {
        str(page_id): str(component_id)
        for page_id, component_id in health.get("judgment_component_ids", {}).items()
        if isinstance(page_id, str) and isinstance(component_id, str)
    }
    for edge in judgment_edges:
        source_id = str(edge.get("source_id") or "")
        page_id = str(edge.get("page_id") or "")
        component_id = str(source_component_ids.get(source_id, "") or "")
        if page_id and component_id and page_id not in judgment_component_ids:
            judgment_component_ids[page_id] = component_id
    component_label_by_id = {
        str(component.get("id") or ""): component_display_label(str(component.get("id") or ""))
        for component in components
    }
    protocol_colors = {
        "general": "#38bdf8",
        "mixed": "#94a3b8",
        "unassigned": "#64748b",
    }
    for node in graph_nodes:
        node_id = str(node.get("id") or "")
        position = positions.get(node_id)
        if not position:
            continue
        x, y = position
        kind = str(node.get("kind") or "concept")
        title = str(node.get("title") or node_id)
        if kind == "source":
            fill = "#0f766e"
            protocol = source_protocol_by_id.get(node_id.removeprefix("source:"), "unassigned")
            stroke = protocol_colors.get(protocol, protocol_colors["unassigned"])
            page_path = str(node.get("source_page") or "")
            href = f"../../{html.escape(page_path)}"
            subtitle = f"{kind_label(str(node.get('source_type') or 'source'))} · {protocol_label(protocol)}"
            component_id = str(source_component_ids.get(node_id.removeprefix("source:"), "") or "")
            secondary_metric = str(node.get("stored_path") or "")
            subtitle_fill = "#ccfbf1"
        elif kind == "judgment":
            fill = "#b45309"
            protocol = judgment_protocol_by_id.get(node_id.removeprefix("judgment:"), DEFAULT_PROTOCOL)
            stroke = protocol_colors.get(protocol, protocol_colors["unassigned"])
            page_path = str(node.get("page_path") or "")
            href = f"../../{html.escape(page_path)}"
            subtitle = (
                f"{kind_label(str(node.get('page_kind') or 'judgment'))} · "
                f"{status_label(str(node.get('status') or 'unknown'))} · {protocol_label(protocol)}"
            )
            component_id = str(judgment_component_ids.get(node_id.removeprefix("judgment:"), "") or "")
            secondary_metric = f"来源数 {len(node.get('source_ids', []))}"
            subtitle_fill = "#ffedd5"
        elif kind == "elixir":
            fill = "#a16207"
            protocol = str(node.get("protocol") or DEFAULT_PROTOCOL)
            stroke = protocol_colors.get(protocol, "#facc15")
            page_path = str(node.get("page_path") or "")
            href = f"../../{html.escape(page_path)}"
            subtitle = f"金丹 · {status_label(str(node.get('elixir_state') or 'settled'))} · {protocol_label(protocol)}"
            component_id = "elixir-settled"
            secondary_metric = f"承接 {len(node.get('derived_from', []))} 个文件"
            subtitle_fill = "#fef3c7"
        else:
            fill = "#1d4ed8"
            slug = node_id.removeprefix("concept:")
            protocol = concept_protocol_by_slug.get(slug, "unassigned")
            stroke = protocol_colors.get(protocol, protocol_colors["unassigned"])
            page_path = str(node.get("page_path") or f"wiki/concepts/{slug}.md")
            href = f"../../{html.escape(page_path)}"
            subtitle = f"概念 · {protocol_label(protocol)}"
            component_id = str(concept_component_ids.get(slug, "") or "")
            secondary_metric = f"来源页 {len(node.get('source_pages', []))}"
            subtitle_fill = "#dbeafe"
        safe_title = html.escape(title)
        label = html.escape(truncate_label(title))
        rx = x - 120
        ry = y - 22
        component_label = component_label_by_id.get(
            component_id, component_display_label(component_id) if component_id else "未分组"
        )
        node_fragments.append(
            "\n".join(
                [
                    f'<g class="graph-node" data-node-id="{html.escape(node_id)}" data-kind="{html.escape(kind)}" data-component="{html.escape(component_id)}" data-protocol="{html.escape(protocol)}" data-title="{safe_title.lower()}">',
                    f'  <a href="{href}">',
                    f"    <title>{safe_title}</title>",
                    f'    <rect x="{rx}" y="{ry}" width="240" height="44" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2" />',
                    f'    <text x="{x}" y="{y - 3}" text-anchor="middle" fill="#ffffff" font-size="14" font-weight="700">{label}</text>',
                    f'    <text x="{x}" y="{y + 14}" text-anchor="middle" fill="{subtitle_fill}" font-size="11">{html.escape(subtitle)}</text>',
                    "  </a>",
                    "</g>",
                ]
            )
        )
        node_rows.append(
            '<li class="node-row"'
            f' data-node-id="{html.escape(node_id)}"'
            f' data-kind="{html.escape(kind)}"'
            f' data-component="{html.escape(component_id)}"'
            f' data-protocol="{html.escape(protocol)}"'
            f' data-title="{safe_title.lower()}">'
            f'<button type="button" class="node-detail-button" data-node-id="{html.escape(node_id)}">详情</button> '
            f'<a href="{href}">{safe_title}</a>'
            f' <span class="node-meta">{html.escape(subtitle)} · {html.escape(component_label)} · 连接 {degree_map.get(node_id, 0)}</span>'
            "</li>"
        )
        referenced_by = list(report_anchors.get(node_id, [])) if report_anchors else []
        node_records.append(
            {
                "id": node_id,
                "kind": kind,
                "kind_label": kind_label(kind),
                "protocol": protocol,
                "protocol_label": protocol_label(protocol),
                "title": title,
                "subtitle": subtitle,
                "href": href,
                "page_path": page_path,
                "component_id": component_id,
                "component_label": component_label,
                "degree": degree_map.get(node_id, 0),
                "secondary_metric": secondary_metric,
                "x": x,
                "y": y,
                "referenced_by": referenced_by[:5],
            }
        )

    section_fragments: list[str] = []
    for section in sections:
        source_count = len(section.get("source_ids", []))
        concept_count = len(section.get("concept_slugs", []))
        judgment_count = len(section.get("judgment_ids", []))
        elixir_count = len(section.get("elixir_ids", []))
        if elixir_count:
            section_summary = f"金丹 {elixir_count}"
            section_detail = "金丹承接关系"
        else:
            section_summary = f"来源 {source_count} | 概念 {concept_count}"
            section_detail = f"判断 {judgment_count}"
        section_fragments.append(
            f'<rect x="20" y="{section["y"]}" width="{section_width}" height="{section["height"]}" rx="18" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5" />'
        )
        section_fragments.append(
            f'<text x="44" y="{section["y"] + 28}" fill="#0f172a" font-size="15" font-weight="700">{html.escape(component_display_label(str(section["id"] or "")))}</text>'
        )
        section_fragments.append(
            f'<text x="44" y="{section["y"] + 48}" fill="#475569" font-size="12">{html.escape(section_summary)}</text>'
        )
        section_fragments.append(
            f'<text x="300" y="{section["y"] + 48}" fill="#9a3412" font-size="12">{html.escape(section_detail)}</text>'
        )

    summary_items = [
        f"来源节点 {sum(1 for node in graph_nodes if str(node.get('kind') or '') == 'source')}",
        f"判断节点 {sum(1 for node in graph_nodes if str(node.get('kind') or '') == 'judgment')}",
        f"概念节点 {sum(1 for node in graph_nodes if str(node.get('kind') or '') == 'concept')}",
        f"金丹节点 {len(elixir_nodes)}",
        f"关系边 {len(edge_records)}",
    ]
    component_option_sections = sections
    component_options = "".join(
        f'<option value="{html.escape(str(component.get("id") or ""))}">{html.escape(component_display_label(str(component.get("id") or "")))} ({len(component.get("source_ids", [])) + len(component.get("concept_slugs", [])) + len(component.get("judgment_ids", [])) + len(component.get("elixir_ids", []))})</option>'
        for component in component_option_sections
        if component.get("id")
    )
    protocol_options = "".join(
        f'<option value="{html.escape(protocol)}">{html.escape(protocol_label(protocol))}</option>'
        for protocol in sorted(
            {str(record.get("protocol") or "") for record in node_records if str(record.get("protocol") or "")}
        )
    )
    node_rows_markup = "".join(node_rows) or "<li>当前没有可浏览的节点。</li>"
    default_node_id = ""
    for record in node_records:
        if record.get("kind") == "source" and int(record.get("degree") or 0) > 0:
            default_node_id = str(record.get("id") or "")
            break
    if not default_node_id and node_records:
        default_node_id = str(node_records[0].get("id") or "")
    node_payload = html_safe_json_literal(
        {
            "nodes": node_records,
            "edges": edge_records,
            "defaultNodeId": default_node_id,
            "viewBoxWidth": 1020,
            "viewBoxHeight": view_height,
        }
    )
    # Aggregate counts by chinese label for human readability, but only after
    # the per-edge_type counts have been collected, so multiple edge_types
    # mapping to the same family label (e.g. unknown JUDGMENT_*) are listed
    # transparently rather than collapsed at collection time.
    relation_summary_rows: list[tuple[str, str, int]] = []
    for edge_type, count in sorted(relation_counts_by_type.items()):
        relation_summary_rows.append((edge_type, edge_relation_label(edge_type), count))
    relation_summary_items = (
        "".join(
            f"<li><strong>{html.escape(label)}</strong>：{count} 条</li>"
            for edge_type, label, count in relation_summary_rows
        )
        or "<li>当前没有关系边。</li>"
    )

    report_index: dict[str, dict[str, Any]] = {}
    node_title_by_id = {
        str(record.get("id") or ""): str(record.get("title") or record.get("id") or "") for record in node_records
    }
    for node_id, reports in sorted(report_anchors.items()):
        for report in reports:
            path = str(report.get("path") or "").strip()
            if not path:
                continue
            record = report_index.setdefault(
                path,
                {"path": path, "title": str(report.get("title") or path), "anchors": [], "anchor_count": 0},
            )
            record["anchor_count"] = int(record.get("anchor_count") or 0) + 1
            if node_id in node_title_by_id:
                record["anchors"].append({"node_id": node_id, "title": node_title_by_id[node_id]})
    report_cards: list[str] = []
    for report in sorted(report_index.values(), key=lambda item: str(item.get("title") or item.get("path") or ""))[:12]:
        anchors = list(report.get("anchors") or [])[:8]
        anchor_buttons = (
            "".join(
                f'<button type="button" class="report-anchor-link" data-node-id="{html.escape(str(anchor.get("node_id") or ""))}">{html.escape(str(anchor.get("title") or anchor.get("node_id") or "证据锚点"))}</button>'
                for anchor in anchors
            )
            or '<span class="muted">暂无可点开的证据锚点。</span>'
        )
        report_cards.append(
            "".join(
                [
                    '<article class="report-card">',
                    f'<h3><a href="../../{html.escape(str(report.get("path") or ""))}">{html.escape(str(report.get("title") or report.get("path") or "未命名报告"))}</a></h3>',
                    f'<div class="node-meta">证据锚点 {int(report.get("anchor_count") or 0)} 个，可点开 {len(report.get("anchors") or [])} 个</div>',
                    f'<div class="report-anchors">{anchor_buttons}</div>',
                    "</article>",
                ]
            )
        )
    report_overview_markup = "".join(report_cards) or (
        '<div class="empty">当前还没有带证据锚点的报告。先生成报告；报告沉淀出 <code>graph_anchor_node_ids</code> 后，这里会优先显示报告到证据的追溯入口。</div>'
    )

    empty_state = ""
    if not graph_nodes:
        empty_state = '<div class="empty">当前没有可展示的中文相关 Markdown 图谱节点。请先沉淀中文内容的 source / concept / judgment / elixir 页面后重新编译；与已展示 source 直接相连的材料也会一并显示。</div>'

    svg_body = "\n".join(section_fragments + node_fragments + edge_fragments)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            html_meta_theme(),
            "  <title>炼丹炉报告证据图谱</title>",
            "  <style>",
            html_theme_css(),
            "    /* Graph-specific */ ",
            "    .canvas { overflow-x: auto; }",
            "    .graph-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }",
            "    .graph-toolbar button { border: 1px solid var(--line); background: var(--accent-bg); color: var(--accent); border-radius: 999px; padding: 6px 12px; cursor: pointer; font: inherit; }",
            "    .graph-toolbar button:hover { background: var(--accent); color: #fff; }",
            "    .graph-status { color: var(--muted); font-size: 12px; }",
            "    svg { width: 100%; min-width: 1020px; height: auto; display: block; }",
            "    .workbench { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(320px, 1fr); gap: 18px; align-items: start; }",
            "    .node-browser { max-height: 560px; overflow: auto; }",
            "    .node-browser ul { list-style: none; padding-left: 0; }",
            "    .node-row { padding: 10px 0; border-bottom: 1px solid var(--line); border-radius: 12px; }",
            "    .node-row:last-child { border-bottom: 0; }",
            "    .node-row.active { background: var(--accent-bg); padding-left: 10px; padding-right: 10px; }",
            "    .node-meta { color: var(--muted); font-size: 12px; }",
            "    .node-detail-button { margin-right: 8px; border: 1px solid var(--line); background: var(--accent-bg); color: var(--accent); border-radius: 999px; padding: 2px 10px; cursor: pointer; }",
            "    .node-detail-button:hover { background: var(--accent); color: #fff; }",
            "    .graph-node.hidden, .graph-edge.hidden, .node-row.hidden { display: none; }",
            "    .graph-edge { opacity: 0.88; }",
            "    .graph-node.active rect { stroke-width: 4; filter: drop-shadow(0 0 10px rgba(59,130,246,0.4)); }",
            "    .graph-edge.active { opacity: 1; stroke-width: 4; }",
            "    .details-grid { display: grid; gap: 10px; }",
            "    .details-grid code { background: var(--accent-bg); padding: 2px 6px; border-radius: 8px; }",
            "    .legend { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 12px; color: var(--muted); }",
            "    .legend span::before { content: ''; display: inline-block; width: 12px; height: 12px; border-radius: 999px; margin-right: 6px; vertical-align: -1px; }",
            "    .legend .source::before { background: #0f766e; } .legend .judgment::before { background: #b45309; }",
            "    .legend .concept::before { background: #3b82f6; } .legend .elixir::before { background: #a16207; } .legend .source-concept::before { background: #0ea5e9; }",
            "    .legend .source-judgment::before { background: #c2410c; } .legend .concept-related::before { background: #f59e0b; }",
            "    .legend .judgment-support::before { background: #16a34a; } .legend .judgment-conflict::before { background: #dc2626; }",
            "    .legend .decision-link::before { background: #3b82f6; } .legend .causal-link::before { background: #0891b2; } .legend .elixir-link::before { background: #facc15; }",
            "    .relation-machine-type { color: var(--muted); font-size: 11px; margin-left: 4px; }",
            "    .relation-node-link { border: 1px solid var(--line); background: var(--bg); color: var(--accent); border-radius: 999px; padding: 2px 8px; cursor: pointer; font: inherit; }",
            "    .relation-node-link:hover { background: var(--accent); color: #fff; }",
            "    .report-overview { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }",
            "    .report-card { border: 1px solid var(--line); border-radius: 16px; padding: 14px; background: var(--bg); }",
            "    .report-card h3 { margin-top: 0; font-size: 16px; }",
            "    .report-anchors { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }",
            "    .report-anchor-link { border: 1px solid var(--line); background: var(--accent-bg); color: var(--accent); border-radius: 999px; padding: 4px 10px; cursor: pointer; font: inherit; font-size: 12px; }",
            "    .report-anchor-link:hover { background: var(--accent); color: #fff; }",
            "    @media (max-width: 960px) { .workbench { grid-template-columns: 1fr; } .legend { gap: 8px; } .legend span { flex: 1 1 140px; font-size: 12px; } }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="panel">',
            "    <h1>报告证据图谱</h1>",
            f"    <p>编译时间：<code>{html.escape(str(memory.get('compiled_at', '')))}</code> | 图谱摘要：<code>{html.escape(str(graph.get('digest', '')))}</code></p>",
            "    <p>这是给读报告的人用的追溯入口：先看报告，再点证据锚点回到材料、判断和概念。内部 wiki 资产结构只作为解释层，默认不要求普通用户理解或浏览。</p>",
            '    <div class="meta">',
            *[
                f'      <div class="card"><div class="metric">{html.escape(item.split()[-1])}</div><div class="metric-label">{html.escape(" ".join(item.split()[:-1]) or item)}</div></div>'
                for item in summary_items
            ],
            "    </div>",
            '    <div class="legend">',
            '      <span class="source">来源</span>',
            '      <span class="judgment">判断</span>',
            '      <span class="concept">概念</span>',
            '      <span class="elixir">金丹</span>',
            '      <span class="source-concept">材料提到概念</span>',
            '      <span class="source-judgment">材料支撑判断</span>',
            '      <span class="concept-related">概念相关</span>',
            '      <span class="judgment-support">判断支持</span>',
            '      <span class="judgment-conflict">判断冲突</span>',
            '      <span class="decision-link">决策依据</span>',
            '      <span class="causal-link">因果关系</span>',
            '      <span class="elixir-link">金丹承接</span>',
            "    </div>",
            "  </section>",
            f"  {empty_state}",
            '  <section class="panel"><h2>报告证据入口</h2>',
            "    <p>优先从这里进入：选择一份报告，点它引用的证据锚点，右侧会显示直接关系、引用此节点的其他报告和原始页面。</p>",
            f'    <div class="report-overview">{report_overview_markup}</div>',
            "  </section>",
            '  <section class="panel">',
            '    <div class="controls">',
            '      <div><label for="graph-search">搜索节点</label><input id="graph-search" type="search" placeholder="输入标题、关键词或来源编号" /></div>',
            '      <div><label for="graph-kind">节点类型</label><select id="graph-kind"><option value="">全部</option><option value="source">来源</option><option value="judgment">判断</option><option value="concept">概念</option><option value="elixir">金丹</option></select></div>',
            f'      <div><label for="graph-protocol">协议</label><select id="graph-protocol"><option value="">全部协议</option>{protocol_options}</select></div>',
            f'      <div><label for="graph-component">关系组</label><select id="graph-component"><option value="">全部关系组</option>{component_options}</select></div>',
            "    </div>",
            '    <div class="workbench">',
            '      <div class="panel canvas">',
            '        <div class="graph-toolbar">',
            '          <button type="button" id="graph-zoom-out">缩小</button>',
            '          <button type="button" id="graph-zoom-in">放大</button>',
            '          <button type="button" id="graph-focus-node">聚焦当前节点</button>',
            '          <button type="button" id="graph-fit-view">适配全图</button>',
            '          <button type="button" id="graph-reset-view">重置视图</button>',
            '          <span id="graph-status" class="graph-status">100%</span>',
            "        </div>",
            f'        <svg id="graph-canvas" viewBox="0 0 1020 {view_height}" role="img" aria-label="炼丹炉报告证据图谱">',
            '          <g id="graph-viewport">',
            f"{svg_body}",
            "          </g>",
            "        </svg>",
            "      </div>",
            '      <div class="details-grid">',
            '        <div class="panel"><h2>证据详情</h2><div id="graph-node-details">选择报告证据锚点或节点详情按钮，查看关系组、连接数和详情页。</div></div>',
            '        <div class="panel node-browser"><h2>节点浏览器</h2><ul id="graph-node-browser">',
            f"{node_rows_markup}",
            "        </ul></div>",
            "      </div>",
            "    </div>",
            "  </section>",
            '  <section class="panel"><h2>关系说明</h2>',
            "    <p>图谱关系用中文表达：报告引用证据锚点；材料沉淀为来源节点，来源提到概念，来源支撑判断；判断之间可以互相支持、冲突或相关；决策依据来自判断；概念之间可形成相关或因果关系；金丹节点展示已沉淀的 <code>wiki/elixirs/*.md</code>。</p>",
            "    <p><strong>例子：</strong>材料 A 支撑判断 J，判断 J 成为决策 D 的依据；如果新判断 K 与 J 冲突，图谱会把它显示为“判断冲突”，帮助你从报告回到证据链。</p>",
            "    <ul>",
            f"{relation_summary_items}",
            "    </ul>",
            "  </section>",
            '  <section class="panel"><h2>相关入口</h2><ul>',
            '    <li><a href="../../wiki/indexes/furnace-center.md">回到炼丹炉</a></li>',
            '    <li><a href="../../wiki/indexes/graph-view.md">关系图谱说明</a></li>',
            '    <li><a href="../../wiki/indexes/graph-health.md">关系图谱健康</a></li>',
            "  </ul></section>",
            "  <script>",
            f"    const graphUiData = {node_payload};",
            "    const nodeMap = new Map((graphUiData.nodes || []).map((node) => [node.id, node]));",
            "    const searchInput = document.getElementById('graph-search');",
            "    const kindSelect = document.getElementById('graph-kind');",
            "    const protocolSelect = document.getElementById('graph-protocol');",
            "    const componentSelect = document.getElementById('graph-component');",
            "    const nodeDetails = document.getElementById('graph-node-details');",
            "    const graphViewport = document.getElementById('graph-viewport');",
            "    const graphStatus = document.getElementById('graph-status');",
            "    const zoomOutButton = document.getElementById('graph-zoom-out');",
            "    const zoomInButton = document.getElementById('graph-zoom-in');",
            "    const focusNodeButton = document.getElementById('graph-focus-node');",
            "    const fitViewButton = document.getElementById('graph-fit-view');",
            "    const resetViewButton = document.getElementById('graph-reset-view');",
            "    let activeNodeId = '';",
            "    let scale = 1;",
            "    let translateX = 0;",
            "    let translateY = 0;",
            "    function visibleGraphNodes() {",
            "      return Array.from(document.querySelectorAll('.graph-node')).filter((element) => !element.classList.contains('hidden'));",
            "    }",
            "    function fitGraphToView() {",
            "      const canvas = document.getElementById('graph-canvas');",
            "      const nodes = visibleGraphNodes();",
            "      if (!canvas || !nodes.length) return;",
            "      let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;",
            "      nodes.forEach((element) => {",
            "        const node = nodeMap.get(element.dataset.nodeId || '');",
            "        if (!node) return;",
            "        const x = Number(node.x || 0);",
            "        const y = Number(node.y || 0);",
            "        minX = Math.min(minX, x - 140);",
            "        maxX = Math.max(maxX, x + 140);",
            "        minY = Math.min(minY, y - 30);",
            "        maxY = Math.max(maxY, y + 30);",
            "      });",
            "      const bboxWidth = Math.max(maxX - minX, 120);",
            "      const bboxHeight = Math.max(maxY - minY, 80);",
            "      const viewBoxWidth = Number(graphUiData.viewBoxWidth || 1020);",
            "      const viewBoxHeight = Number(graphUiData.viewBoxHeight || 480);",
            "      const canvasWidth = Math.max(canvas.clientWidth || viewBoxWidth, 320);",
            "      const canvasHeight = Math.max(canvas.clientHeight || 480, 240);",
            "      const nextScale = Math.min(2.2, Math.max(0.35, Math.min((canvasWidth - 48) / bboxWidth, (canvasHeight - 48) / bboxHeight)));",
            "      scale = nextScale;",
            "      const centerX = (minX + maxX) / 2;",
            "      const centerY = (minY + maxY) / 2;",
            "      translateX = Math.round(viewBoxWidth / 2 - centerX * scale);",
            "      translateY = Math.round(viewBoxHeight / 2 - centerY * scale);",
            "      updateViewport();",
            "    }",
            "    function updateViewport() {",
            "      if (graphViewport) {",
            "        graphViewport.setAttribute('transform', `translate(${translateX} ${translateY}) scale(${scale})`);",
            "      }",
            "      if (graphStatus) {",
            "        graphStatus.textContent = `缩放 ${Math.round(scale * 100)}%`;",
            "      }",
            "    }",
            "    function setActiveNode(nodeId) {",
            "      activeNodeId = nodeId;",
            "      document.querySelectorAll('.graph-node').forEach((element) => {",
            "        const isActive = (element.dataset.nodeId || '') === nodeId && !element.classList.contains('hidden');",
            "        element.classList.toggle('active', isActive);",
            "      });",
            "      document.querySelectorAll('.node-row').forEach((element) => {",
            "        const isActive = (element.dataset.nodeId || '') === nodeId && !element.classList.contains('hidden');",
            "        element.classList.toggle('active', isActive);",
            "        if (isActive) element.scrollIntoView({ block: 'nearest' });",
            "      });",
            "      document.querySelectorAll('.graph-edge').forEach((element) => {",
            "        const source = element.dataset.source || '';",
            "        const target = element.dataset.target || '';",
            "        const isActive = Boolean(nodeId) && !element.classList.contains('hidden') && (source === nodeId || target === nodeId);",
            "        element.classList.toggle('active', isActive);",
            "      });",
            "    }",
            "    function focusNode(nodeId) {",
            "      const node = nodeMap.get(nodeId);",
            "      if (!node) return;",
            "      const viewBoxWidth = Number(graphUiData.viewBoxWidth || 1020);",
            "      const viewBoxHeight = Number(graphUiData.viewBoxHeight || 480);",
            "      translateX = Math.round(viewBoxWidth / 2 - Number(node.x || 0) * scale);",
            "      translateY = Math.round(viewBoxHeight / 2 - Number(node.y || 0) * scale);",
            "      updateViewport();",
            "    }",
            "    function renderDetails(nodeId) {",
            "      const node = nodeMap.get(nodeId);",
            "      if (!node) { nodeDetails.innerHTML = '当前没有可展示的节点详情。'; setActiveNode(''); return; }",
            "      const relationItems = (graphUiData.edges || [])",
            "        .filter((edge) => edge.source === nodeId || edge.target === nodeId)",
            "        .slice(0, 8)",
            "        .map((edge) => {",
            "          const otherNodeId = edge.source === nodeId ? edge.target : edge.source;",
            '          return `<li>${edge.label || \'关系\'}：<button type="button" class="relation-node-link" data-node-id="${otherNodeId}">${otherNodeId}</button></li>`;',
            "        })",
            "        .join('') || '<li>暂无直接关系。</li>';",
            "      const referencedReports = Array.isArray(node.referenced_by) ? node.referenced_by : [];",
            "      const referencedItems = referencedReports.length",
            "        ? referencedReports.slice(0, 5).map((report) => `<li><a href=\"../../${encodeURI(report.path || '')}\">${report.title || report.path || '未命名报告'}</a></li>`).join('')",
            "        : '<li>暂无引用此节点的报告。</li>';",
            "      nodeDetails.innerHTML = [",
            "        `<div><strong>${node.title}</strong></div>`,",
            "        `<div>类型：<code>${node.kind_label || node.kind}</code></div>`,",
            "        `<div>协议：<code>${node.protocol_label || node.protocol || '未分配'}</code></div>`,",
            "        `<div>关系组：<code>${node.component_label || '未分组'}</code></div>`,",
            "        `<div>连接数：<code>${node.degree}</code></div>`,",
            "        `<div>相关关系：<ul>${relationItems}</ul></div>`,",
            "        `<div>引用此节点的报告：<ul>${referencedItems}</ul></div>`,",
            "        `<div>详情页：<code>${node.page_path}</code></div>`,",
            "        `<div>${node.secondary_metric || ''}</div>`,",
            '        `<div><a href="${node.href}">打开页面</a></div>`',
            "      ].join('');",
            "      nodeDetails.querySelectorAll('.relation-node-link').forEach((button) => {",
            "        button.addEventListener('click', () => renderDetails(button.dataset.nodeId || ''));",
            "      });",
            "      setActiveNode(nodeId);",
            "    }",
            "    function applyFilters() {",
            "      const needle = (searchInput.value || '').trim().toLowerCase();",
            "      const kind = kindSelect.value || '';",
            "      const protocol = protocolSelect.value || '';",
            "      const component = componentSelect.value || '';",
            "      const visibleIds = new Set();",
            "      document.querySelectorAll('.graph-node').forEach((element) => {",
            "        const title = element.dataset.title || '';",
            "        const nodeKind = element.dataset.kind || '';",
            "        const nodeProtocol = element.dataset.protocol || '';",
            "        const nodeComponent = element.dataset.component || '';",
            "        const nodeId = element.dataset.nodeId || '';",
            "        const matches = (!needle || title.includes(needle) || nodeId.toLowerCase().includes(needle))",
            "          && (!kind || nodeKind === kind)",
            "          && (!protocol || nodeProtocol === protocol)"
            "          && (!component || nodeComponent === component);",
            "        element.classList.toggle('hidden', !matches);",
            "        if (matches) visibleIds.add(nodeId);",
            "      });",
            "      document.querySelectorAll('.graph-edge').forEach((element) => {",
            "        const visible = visibleIds.has(element.dataset.source || '') && visibleIds.has(element.dataset.target || '');",
            "        element.classList.toggle('hidden', !visible);",
            "      });",
            "      document.querySelectorAll('.node-row').forEach((element) => {",
            "        const title = element.dataset.title || '';",
            "        const nodeKind = element.dataset.kind || '';",
            "        const nodeProtocol = element.dataset.protocol || '';",
            "        const nodeComponent = element.dataset.component || '';",
            "        const nodeId = element.dataset.nodeId || '';",
            "        const matches = (!needle || title.includes(needle) || nodeId.toLowerCase().includes(needle))",
            "          && (!kind || nodeKind === kind)",
            "          && (!protocol || nodeProtocol === protocol)"
            "          && (!component || nodeComponent === component);",
            "        element.classList.toggle('hidden', !matches);",
            "      });",
            "      if (!visibleIds.size) {",
            "        nodeDetails.innerHTML = '当前筛选条件下没有节点。';",
            "        setActiveNode('');",
            "        return;",
            "      }",
            "      const preferredNodeId = activeNodeId && visibleIds.has(activeNodeId) ? activeNodeId : '';",
            "      if (preferredNodeId) {",
            "        renderDetails(preferredNodeId);",
            "        return;",
            "      }",
            "      const firstVisible = document.querySelector('.node-row:not(.hidden)');",
            "      if (firstVisible) renderDetails(firstVisible.dataset.nodeId || '');",
            "    }",
            "    document.querySelectorAll('.node-detail-button').forEach((button) => {",
            "      button.addEventListener('click', () => renderDetails(button.dataset.nodeId || ''));",
            "    });",
            "    document.querySelectorAll('.report-anchor-link').forEach((button) => {",
            "      button.addEventListener('click', () => { renderDetails(button.dataset.nodeId || ''); focusNode(button.dataset.nodeId || ''); });",
            "    });",
            "    if (zoomOutButton) zoomOutButton.addEventListener('click', () => { scale = Math.max(0.6, scale - 0.2); if (activeNodeId) { focusNode(activeNodeId); } else { updateViewport(); } });",
            "    if (zoomInButton) zoomInButton.addEventListener('click', () => { scale = Math.min(2.4, scale + 0.2); if (activeNodeId) { focusNode(activeNodeId); } else { updateViewport(); } });",
            "    if (focusNodeButton) focusNodeButton.addEventListener('click', () => focusNode(activeNodeId || graphUiData.defaultNodeId || ''));",
            "    if (fitViewButton) fitViewButton.addEventListener('click', () => fitGraphToView());",
            "    if (resetViewButton) resetViewButton.addEventListener('click', () => { scale = 1; translateX = 0; translateY = 0; updateViewport(); });",
            "    [searchInput, kindSelect, protocolSelect, componentSelect].forEach((element) => element.addEventListener('input', applyFilters));",
            "    [kindSelect, protocolSelect, componentSelect].forEach((element) => element.addEventListener('change', applyFilters));",
            "    fitGraphToView();",
            "    renderDetails(graphUiData.defaultNodeId || '');",
            "    applyFilters();",
            "    fitGraphToView();",
            "  </script>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )
