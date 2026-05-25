"""Machine-memory graph, query, transition, and history surfaces.

EP-017B step 1: extracted from app_memory_surfaces.py. Re-exported via the
facade at aiwiki.app_memory_surfaces for backward compatibility with existing
callers (app_queries, app_linting) and test patch seams.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from ..app_cache import (
    load_cached_query_result,
    load_query_cache_snapshot,
    query_cache_key,
    query_cache_memory_hash,
    record_query_cache_event,
    save_cached_query_result,
)
from ..app_memory import (
    machine_memory_source_runtime_record,
    question_signature,
)
from ..app_memory_query import (
    _machine_memory_query_payload_hash,
    build_machine_memory_adjacency,
    build_machine_memory_query_routes,  # noqa: F401  re-exported via facade; actual call uses lazy facade attr for patch seam
    select_machine_memory_query_strategy,
)
from ..app_protocol import PENDING_ACTION_STATUSES, action_focus_score
from ..app_state import DEFAULT_PROTOCOL, machine_memory_history_path
from ..app_utils import atomic_append_jsonl, html_safe_json_literal, tokenize
from ..content.memory import action_priority_rank, action_supports_low_risk_apply
from ..render.html_theme import html_meta_theme, html_theme_css
from .scoring import machine_memory_query_time_focus

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


# Round 49: report ↔ graph anchor reverse index. Compile-time helper that
# scans recent reports for ``graph_anchor_node_ids`` and produces a
# ``node_id -> [{"title", "path"}, ...]`` map for the graph HTML to render.
_REPORT_ANCHOR_DIRS: tuple[str, ...] = (
    "output/reports",
    "output/slides",
    "output/figures",
)


def collect_report_anchors(root: Path, *, limit: int = 50) -> dict[str, list[dict[str, str]]]:
    """Collect a node_id -> referencing reports map.

    Reads the most recent ``limit`` markdown files under ``output/reports``,
    ``output/slides`` and ``output/figures``; parses their frontmatter for
    ``graph_anchor_node_ids`` and ``title`` (falling back to ``id`` /
    file stem). Older files are skipped to keep the scan O(limit).

    The returned map is order-stable per node: most recent reports first.
    Empty / unreadable reports are skipped silently rather than raising,
    so a stray malformed artifact does not break compile.
    """
    from ..app_utils import parse_frontmatter, relative_path

    candidates: list[tuple[float, Path]] = []
    for relative in _REPORT_ANCHOR_DIRS:
        directory = root / relative
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.suffix != ".md" or not path.is_file():
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, path))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if limit > 0:
        candidates = candidates[:limit]

    index: dict[str, list[dict[str, str]]] = {}
    for _mtime, path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        frontmatter = parse_frontmatter(text)
        anchors = report_memory_anchor_ids(frontmatter)
        if not anchors:
            continue
        title = (
            str(frontmatter.get("title") or "").strip()
            or str(frontmatter.get("id") or "").strip()
            or path.stem
        )
        report_path = relative_path(root, path)
        record = {"title": title, "path": report_path}
        for anchor in anchors:
            bucket = index.setdefault(anchor, [])
            if record not in bucket:
                bucket.append(record)
    return index


def report_memory_anchor_ids(frontmatter: dict[str, Any]) -> list[str]:
    """Full machine-memory anchors for HTML/subgraph; prefers ``machine_memory_anchor_node_ids``."""
    for key in ("machine_memory_anchor_node_ids", "graph_anchor_node_ids"):
        raw = frontmatter.get(key)
        if isinstance(raw, list):
            anchors = [str(item).strip() for item in raw if str(item).strip()]
            if anchors:
                return anchors
    return []


class ReportSubgraphError(ValueError):
    """Raised when a per-report subgraph cannot be built (fail-loud)."""


def build_report_subgraph(root: Path, report_path: str) -> dict[str, Any]:
    """Build the 1-hop subgraph anchored at a single report.

    Reads ``report_path``'s frontmatter, takes ``graph_anchor_node_ids``, looks
    up the global machine-memory graph (via ``build_machine_memory_graph``),
    and returns the anchors + every 1-hop neighbor plus the connecting edges.

    Returns a dict with keys: ``report`` (relative path), ``anchor_node_ids``,
    ``nodes`` (anchors + neighbors, no duplicates, sorted by kind/id),
    ``edges`` (only edges touching an anchor), ``neighbors`` (anchors removed,
    sorted).

    Fails loud (``ReportSubgraphError``) on:
    - report file missing,
    - frontmatter lacks / has empty ``graph_anchor_node_ids``,
    - any anchor id does not resolve to a node in the current memory graph.

    Stdlib only; the caller wires this into the CLI / plugin.
    """
    from ..app_memory import build_machine_memory_graph
    from ..app_state import load_machine_memory
    from ..app_utils import parse_frontmatter

    report_rel = str(report_path or "").strip()
    if not report_rel:
        raise ReportSubgraphError("report path is empty")
    root_resolved = root.resolve()
    candidate = Path(report_rel)
    absolute = candidate.resolve() if candidate.is_absolute() else (root_resolved / candidate).resolve()
    try:
        absolute.relative_to(root_resolved)
    except ValueError as exc:
        raise ReportSubgraphError(
            f"report path is outside the vault root: {report_rel}"
        ) from exc
    if not absolute.is_file():
        raise ReportSubgraphError(f"report not found: {report_rel}")

    text = absolute.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(text)
    anchors = report_memory_anchor_ids(frontmatter)
    if not anchors:
        raise ReportSubgraphError(
            f"report {report_rel} has no machine-memory graph anchors in frontmatter"
        )

    memory = load_machine_memory(root)
    if not isinstance(memory, dict) or not memory.get("compiled_at"):
        raise ReportSubgraphError(
            "machine memory is not compiled; run `aiwiki advanced compile` first"
        )
    try:
        graph = build_machine_memory_graph(memory, root=root)
    except Exception as exc:  # corrupt/incomplete memory shape
        raise ReportSubgraphError(
            f"machine memory is corrupt or incomplete ({type(exc).__name__}: {exc}); "
            "rerun `aiwiki advanced compile`"
        ) from exc
    nodes_by_id: dict[str, dict[str, Any]] = {
        str(node.get("id") or ""): node for node in graph.get("nodes", [])
    }
    missing = [anchor for anchor in anchors if anchor not in nodes_by_id]
    if missing:
        raise ReportSubgraphError(
            f"report {report_rel} references unknown graph nodes: {', '.join(missing)}"
        )

    anchor_set = set(anchors)
    edges_in: list[dict[str, Any]] = []
    neighbor_ids: set[str] = set()
    for edge in graph.get("edges", []):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        touches_source = source in anchor_set
        touches_target = target in anchor_set
        if not (touches_source or touches_target):
            continue
        if source not in nodes_by_id or target not in nodes_by_id:
            continue
        edges_in.append(
            {
                "source": source,
                "target": target,
                "type": str(edge.get("type") or ""),
                "label": relation_label(str(edge.get("type") or "")),
            }
        )
        if not touches_source:
            neighbor_ids.add(source)
        if not touches_target:
            neighbor_ids.add(target)

    kept_ids = anchor_set | neighbor_ids
    nodes_out = [nodes_by_id[node_id] for node_id in sorted(kept_ids)]
    neighbors_out = sorted(neighbor_ids)
    return {
        "report": absolute.relative_to(root_resolved).as_posix(),
        "anchor_node_ids": list(anchors),
        "nodes": sorted(nodes_out, key=lambda item: (str(item.get("kind") or ""), str(item.get("id") or ""))),
        "edges": sorted(edges_in, key=lambda item: (item["type"], item["source"], item["target"])),
        "neighbors": neighbors_out,
    }


def render_report_subgraph_markdown(subgraph: dict[str, Any]) -> str:
    """Render a per-report subgraph dict to a deterministic markdown artifact.

    Output: frontmatter (kind/source_report/anchor_node_ids/generated_by) +
    `## 锚点` + `## 一跳邻居（按类型分组）` + `## 引用边`.
    No external deps; safe for `output/reports/<stem>.subgraph.md`.
    """
    report = str(subgraph.get("report") or "")
    anchors = [str(item) for item in subgraph.get("anchor_node_ids", [])]
    nodes = list(subgraph.get("nodes", []))
    edges = list(subgraph.get("edges", []))
    nodes_by_id = {str(node.get("id") or ""): node for node in nodes}

    def node_line(node_id: str) -> str:
        node = nodes_by_id.get(node_id, {})
        title = str(node.get("title") or node_id)
        kind = str(node.get("kind") or "")
        kind_zh = {"source": "来源", "concept": "概念", "judgment": "判断"}.get(kind, kind or "节点")
        return f"- `{node_id}` ({kind_zh}) — {title}"

    lines: list[str] = []
    lines.append("---")
    lines.append("kind: output/subgraph")
    lines.append(f"source_report: {report}")
    lines.append("graph_anchor_node_ids:")
    for anchor in anchors:
        lines.append(f"  - {anchor}")
    lines.append("generated_by: aiwiki report-subgraph")
    lines.append("---")
    lines.append("")
    lines.append(f"# 报告局部图谱：{report}")
    lines.append("")
    lines.append("## 锚点")
    lines.append("")
    if anchors:
        for anchor in anchors:
            lines.append(node_line(anchor))
    else:
        lines.append("- 暂无锚点。")
    lines.append("")

    lines.append("## 一跳邻居（按类型分组）")
    lines.append("")
    anchor_set = set(anchors)
    neighbors = [node for node in nodes if str(node.get("id") or "") not in anchor_set]
    if not neighbors:
        lines.append("- 当前锚点暂无一跳邻居。")
    else:
        by_kind: dict[str, list[dict[str, Any]]] = {}
        for node in neighbors:
            by_kind.setdefault(str(node.get("kind") or ""), []).append(node)
        kind_order = ("source", "judgment", "concept")
        seen_kinds: list[str] = []
        for kind in kind_order:
            if kind in by_kind:
                seen_kinds.append(kind)
        for kind in sorted(by_kind):
            if kind not in seen_kinds:
                seen_kinds.append(kind)
        for kind in seen_kinds:
            kind_zh = {"source": "来源", "concept": "概念", "judgment": "判断", "elixir": "金丹"}.get(kind, kind or "节点")
            lines.append(f"### {kind_zh}")
            lines.append("")
            for node in by_kind[kind]:
                lines.append(node_line(str(node.get("id") or "")))
            lines.append("")

    lines.append("## 引用边")
    lines.append("")
    if not edges:
        lines.append("- 当前锚点没有连接边。")
    else:
        for edge in edges:
            lines.append(
                f"- `{edge['source']}` —[{edge.get('label') or edge.get('type') or '关系'}]→ `{edge['target']}`"
            )
    lines.append("")
    return "\n".join(lines)


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
            "research": "研究",
            "investing": "投资",
            "product": "产品",
            "ops": "运营",
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
        page_id: str(node.get("protocol") or DEFAULT_PROTOCOL)
        for page_id, node in judgment_nodes.items()
    }
    source_protocol_by_id = {
        source_id: resolve_protocol(
            {
                judgment_protocol_by_id.get(page_id, "")
                for page_id in judgment_by_source.get(source_id, set())
            }
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
            node
            for node in raw_graph_nodes
            if str(node.get("id") or "") in expanded_ids and has_markdown_page(node)
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
        source_ids = [source_id for source_id in component.get("source_ids", []) if source_id in source_nodes and f"source:{source_id}" in display_node_ids]
        concept_slugs = [slug for slug in component.get("concept_slugs", []) if slug in concept_nodes and f"concept:{slug}" in display_node_ids]
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
        "research": "#a78bfa",
        "investing": "#f59e0b",
        "product": "#f472b6",
        "ops": "#34d399",
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
        component_label = component_label_by_id.get(component_id, component_display_label(component_id) if component_id else "未分组")
        node_fragments.append(
            "\n".join(
                [
                    f'<g class="graph-node" data-node-id="{html.escape(node_id)}" data-kind="{html.escape(kind)}" data-component="{html.escape(component_id)}" data-protocol="{html.escape(protocol)}" data-title="{safe_title.lower()}">',
                    f'  <a href="{href}">',
                    f'    <title>{safe_title}</title>',
                    f'    <rect x="{rx}" y="{ry}" width="240" height="44" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2" />',
                    f'    <text x="{x}" y="{y - 3}" text-anchor="middle" fill="#ffffff" font-size="14" font-weight="700">{label}</text>',
                    f'    <text x="{x}" y="{y + 14}" text-anchor="middle" fill="{subtitle_fill}" font-size="11">{html.escape(subtitle)}</text>',
                    "  </a>",
                    "</g>",
                ]
            )
        )
        node_rows.append(
            "<li class=\"node-row\""
            f" data-node-id=\"{html.escape(node_id)}\""
            f" data-kind=\"{html.escape(kind)}\""
            f" data-component=\"{html.escape(component_id)}\""
            f" data-protocol=\"{html.escape(protocol)}\""
            f" data-title=\"{safe_title.lower()}\">"
            f"<button type=\"button\" class=\"node-detail-button\" data-node-id=\"{html.escape(node_id)}\">详情</button> "
            f"<a href=\"{href}\">{safe_title}</a>"
            f" <span class=\"node-meta\">{html.escape(subtitle)} · {html.escape(component_label)} · 连接 {degree_map.get(node_id, 0)}</span>"
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
        for protocol in sorted({str(record.get("protocol") or "") for record in node_records if str(record.get("protocol") or "")})
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
    relation_summary_items = "".join(
        f"<li><strong>{html.escape(label)}</strong>：{count} 条</li>"
        for edge_type, label, count in relation_summary_rows
    ) or "<li>当前没有关系边。</li>"

    report_index: dict[str, dict[str, Any]] = {}
    node_title_by_id = {str(record.get("id") or ""): str(record.get("title") or record.get("id") or "") for record in node_records}
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
        anchor_buttons = "".join(
            f'<button type="button" class="report-anchor-link" data-node-id="{html.escape(str(anchor.get("node_id") or ""))}">{html.escape(str(anchor.get("title") or anchor.get("node_id") or "证据锚点"))}</button>'
            for anchor in anchors
        ) or '<span class="muted">暂无可点开的证据锚点。</span>'
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
            '  <title>炼丹炉报告证据图谱</title>',
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
            "  <section class=\"panel\">",
            "    <h1>报告证据图谱</h1>",
            f"    <p>编译时间：<code>{html.escape(str(memory.get('compiled_at', '')))}</code> | 图谱摘要：<code>{html.escape(str(graph.get('digest', '')))}</code></p>",
            "    <p>这是给读报告的人用的追溯入口：先看报告，再点证据锚点回到材料、判断和概念。内部 wiki 资产结构只作为解释层，默认不要求普通用户理解或浏览。</p>",
            "    <div class=\"meta\">",
            *[f'      <div class="card"><div class="metric">{html.escape(item.split()[-1])}</div><div class="metric-label">{html.escape(" ".join(item.split()[:-1]) or item)}</div></div>' for item in summary_items],
            "    </div>",
            "    <div class=\"legend\">",
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
            "          return `<li>${edge.label || '关系'}：<button type=\"button\" class=\"relation-node-link\" data-node-id=\"${otherNodeId}\">${otherNodeId}</button></li>`;",
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
            "        `<div><a href=\"${node.href}\">打开页面</a></div>`",
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


def _build_machine_memory_query_json(
    memory: dict[str, Any],
    question: str,
    *,
    root: Path | None = None,
    protocol: str = DEFAULT_PROTOCOL,
    material_state: dict[str, Any] | None = None,
    routing_state: dict[str, Any] | None = None,
    archive_candidates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    term_index = memory.get("term_index", {})
    edges = memory.get("edges", {})
    source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    question_tokens = tokenize(question)
    health = memory.get("health", {})
    adjacency = build_machine_memory_adjacency(memory)
    material_state = material_state or {"entries": []}
    routing_state = routing_state or {"entries": []}
    archive_candidates = archive_candidates or {"entries": []}
    material_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in material_state.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    routing_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in routing_state.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    archive_candidates_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in archive_candidates.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    time_focus_state = machine_memory_query_time_focus(question)
    time_focus = str(time_focus_state.get("focus") or "")

    direct_source_scores: dict[str, int] = {}
    direct_concept_scores: dict[str, int] = {}
    matched_terms: list[str] = []

    source_to_concepts: dict[str, set[str]] = {}
    concept_to_sources: dict[str, set[str]] = {}
    for edge in edges.get("source_to_concept", []):
        source_id = edge.get("source_id")
        concept_slug = edge.get("concept_slug")
        if not isinstance(source_id, str) or not isinstance(concept_slug, str):
            continue
        source_to_concepts.setdefault(source_id, set()).add(concept_slug)
        concept_to_sources.setdefault(concept_slug, set()).add(source_id)

    related_concepts: dict[str, set[str]] = {}
    for edge in edges.get("concept_to_concept", []):
        left = edge.get("from")
        right = edge.get("to")
        if not isinstance(left, str) or not isinstance(right, str):
            continue
        related_concepts.setdefault(left, set()).add(right)
        related_concepts.setdefault(right, set()).add(left)

    for token in question_tokens:
        payload = term_index.get(token)
        if not isinstance(payload, dict):
            continue
        matched_terms.append(token)
        for source_id in payload.get("source_ids", []):
            if source_id in source_nodes:
                direct_source_scores[source_id] = direct_source_scores.get(source_id, 0) + 3
        for concept_slug in payload.get("concept_slugs", []):
            if concept_slug in concept_nodes:
                direct_concept_scores[concept_slug] = direct_concept_scores.get(concept_slug, 0) + 4

    route_strategy = select_machine_memory_query_strategy(
        question,
        direct_source_scores=direct_source_scores,
        direct_concept_scores=direct_concept_scores,
        protocol=protocol,
        root=root,
    )
    selected_strategy = str(route_strategy.get("selected_strategy") or "concept-first")

    expanded_source_scores = dict(direct_source_scores)
    expanded_concept_scores = dict(direct_concept_scores)
    supporting_edges: set[tuple[str, str, str]] = set()

    for source_id in list(direct_source_scores):
        for concept_slug in sorted(source_to_concepts.get(source_id, set())):
            expanded_concept_scores[concept_slug] = expanded_concept_scores.get(concept_slug, 0) + 2
            supporting_edges.add(("HAS_CONCEPT", source_id, concept_slug))

    for concept_slug in list(direct_concept_scores):
        for source_id in sorted(concept_to_sources.get(concept_slug, set())):
            expanded_source_scores[source_id] = expanded_source_scores.get(source_id, 0) + 2
            supporting_edges.add(("HAS_CONCEPT", source_id, concept_slug))
        for related_slug in sorted(related_concepts.get(concept_slug, set())):
            expanded_concept_scores[related_slug] = expanded_concept_scores.get(related_slug, 0) + 1
            supporting_edges.add(("RELATED_CONCEPT", concept_slug, related_slug))
            for source_id in sorted(concept_to_sources.get(related_slug, set())):
                expanded_source_scores[source_id] = expanded_source_scores.get(source_id, 0) + 1
                supporting_edges.add(("HAS_CONCEPT", source_id, related_slug))

    # EP-017B step 1: call via facade attribute to preserve the
    # `patch("aiwiki.app_memory_surfaces.build_machine_memory_query_routes")`
    # seam (tests/test_app.py:3008). Direct binding from the module-level
    # import would bypass the facade monkeypatch.
    from .. import app_memory_surfaces as _facade

    query_routes = _facade.build_machine_memory_query_routes(
        memory,
        adjacency,
        direct_source_scores,
        direct_concept_scores,
        expanded_source_scores,
        expanded_concept_scores,
        strategy=selected_strategy,
    )
    for route in query_routes:
        for node in route["nodes"]:
            if node.get("kind") == "source":
                source_id = str(node.get("id") or "")
                if source_id:
                    expanded_source_scores[source_id] = expanded_source_scores.get(source_id, 0) + 2
                continue
            if node.get("kind") == "concept":
                concept_slug = str(node.get("slug") or "")
                if concept_slug:
                    expanded_concept_scores[concept_slug] = expanded_concept_scores.get(concept_slug, 0) + 2
        for edge in route["edges"]:
            if edge["type"] == "HAS_CONCEPT":
                supporting_edges.add(("HAS_CONCEPT", edge["left"], edge["right"]))
            elif edge["type"] == "RELATED_CONCEPT":
                supporting_edges.add(("RELATED_CONCEPT", edge["left"], edge["right"]))

    source_rank_records = [
        machine_memory_source_runtime_record(
            source_id,
            base_score=base_score,
            source_nodes=source_nodes,
            material_by_entry=material_by_entry,
            routing_by_entry=routing_by_entry,
            archive_candidates_by_entry=archive_candidates_by_entry,
            protocol=protocol,
            time_focus=time_focus,
        )
        for source_id, base_score in expanded_source_scores.items()
        if source_id in source_nodes
    ]
    source_rank_records.sort(
        key=lambda item: (
            -float(item.get("combined_score", 0.0) or 0.0),
            -float(item.get("base_score", 0.0) or 0.0),
            -float(item.get("protocol_bonus", 0.0) or 0.0),
            -float(item.get("time_bonus", 0.0) or 0.0),
            str(item.get("title") or item.get("entry_id") or "").lower(),
        )
    )
    ranked_source_ids = [
        str(item.get("entry_id") or "")
        for item in source_rank_records[:8]
        if item.get("entry_id")
    ]
    ranked_concept_slugs = [
        concept_slug
        for concept_slug, _score in sorted(
            expanded_concept_scores.items(),
            key=lambda item: (-item[1], concept_nodes.get(item[0], {}).get("title", item[0]).lower()),
        )[:8]
    ]
    bridge_concept_slugs = [
        slug for slug in ranked_concept_slugs if slug in set(health.get("bridge_concept_slugs", []))
    ]
    protocol_shard_source_ids = [
        str(item.get("entry_id") or "")
        for item in source_rank_records
        if bool(item.get("protocol_shard")) and item.get("entry_id")
    ][:5]
    time_shard_source_ids = [
        str(item.get("entry_id") or "")
        for item in source_rank_records
        if bool(item.get("time_shard")) and item.get("entry_id")
    ][:5]
    archive_recall_hints = [
        {
            "entry_id": str(item.get("entry_id") or ""),
            "title": str(item.get("title") or item.get("entry_id") or ""),
            "path": str(item.get("path") or ""),
            "temperature": str(item.get("temperature") or ""),
            "archive_status": str(item.get("archive_status") or ""),
            "recommended_temperature": str(item.get("recommended_temperature") or ""),
            "reason_codes": list(item.get("reason_codes", []) or []),
        }
        for item in sorted(
            source_rank_records,
            key=lambda record: (
                -float(record.get("archive_hint_score", 0.0) or 0.0),
                -float(record.get("combined_score", 0.0) or 0.0),
                str(record.get("title") or record.get("entry_id") or "").lower(),
            ),
        )
        if bool(item.get("archive_hint")) and item.get("entry_id")
    ][:3]
    query_subgraph_sources = [
        {
            "id": source_id,
            "title": source_nodes[source_id]["title"],
            "path": source_nodes[source_id]["source_page"],
        }
        for source_id in ranked_source_ids
        if source_id in source_nodes
    ]
    query_subgraph_concepts = [
        {
            "slug": concept_slug,
            "title": concept_nodes[concept_slug]["title"],
            "path": f"wiki/concepts/{concept_slug}.md",
        }
        for concept_slug in ranked_concept_slugs
        if concept_slug in concept_nodes
    ]
    query_subgraph_edges = [
        {"type": edge_type, "left": left, "right": right}
        for edge_type, left, right in sorted(supporting_edges)
        if (edge_type == "HAS_CONCEPT" and left in ranked_source_ids and right in ranked_concept_slugs)
        or (edge_type == "RELATED_CONCEPT" and left in ranked_concept_slugs and right in ranked_concept_slugs)
    ]
    touched_component_ids = sorted(
        {
            component_id
            for component_id in (
                [health.get("source_component_ids", {}).get(source_id) for source_id in ranked_source_ids]
                + [health.get("concept_component_ids", {}).get(slug) for slug in ranked_concept_slugs]
            )
            if component_id
        }
    )
    touched_components = [
        component
        for component in health.get("components", [])
        if component.get("id") in touched_component_ids
    ]
    proposal_by_action_id = {
        str(proposal.get("action_id") or ""): proposal
        for proposal in health.get("repair_plan", {}).get("execution_proposals", [])
        if proposal.get("action_id")
    }
    action_by_id = {
        str(action.get("id") or ""): action
        for action in health.get("actions", [])
        if isinstance(action, dict) and action.get("id")
    }
    relevant_actions: list[dict[str, Any]] = []
    ranked_source_set = set(ranked_source_ids) | set(direct_source_scores)
    ranked_concept_set = set(ranked_concept_slugs) | set(direct_concept_scores)

    def action_hits(action: dict[str, Any]) -> bool:
        source_hit = bool(ranked_source_set & {str(item) for item in action.get("source_ids", []) if isinstance(item, str)})
        concept_hit = bool(ranked_concept_set & {str(item) for item in action.get("concept_slugs", []) if isinstance(item, str)})
        component_hit = bool(action.get("component_id")) and action.get("component_id") in touched_component_ids
        return source_hit or concept_hit or component_hit

    for action in health.get("actions", []):
        if action.get("status") not in PENDING_ACTION_STATUSES:
            continue
        if not action_hits(action):
            continue
        proposal = proposal_by_action_id.get(str(action.get("id") or ""), {})
        relevant_actions.append(
            {
                "id": action["id"],
                "kind": action["kind"],
                "priority": action["priority"],
                "status": action.get("status", "proposed"),
                "title": action["title"],
                "primary_path": action["primary_path"],
                "secondary_path": action.get("secondary_path", ""),
                "reason": action.get("reason", ""),
                "execution_policy": action.get("execution_policy", "triage"),
                "next_step": action.get("next_step", ""),
                "command_hint": action.get("command_hint", ""),
                "apply_ready": action.get("apply_ready", "false"),
                "proposal_kind": proposal.get("proposal_kind", ""),
                "proposal_summary": proposal.get("summary", ""),
                "proposal_targets": proposal.get("target_paths", []),
                "focus_score": action_focus_score(protocol, action),
            }
        )
    relevant_actions.sort(
        key=lambda item: (
            0 if item.get("status") == "accepted" else 1,
            -int(item.get("focus_score", 0)),
            action_priority_rank(str(item.get("priority") or "")),
            str(item.get("title") or "").lower(),
        )
    )
    planner_state = dict(health.get("repair_plan", {}).get("planner_state") or {})
    planner_queue: list[dict[str, Any]] = []
    for item in planner_state.get("priority_queue", []):
        if not isinstance(item, dict):
            continue
        linked_action = action_by_id.get(str(item.get("action_id") or ""), {})
        if linked_action and not action_hits(linked_action) and planner_queue:
            continue
        planner_queue.append(
            {
                "action_id": str(item.get("action_id") or ""),
                "title": str(item.get("title") or item.get("action_id") or ""),
                "priority": str(item.get("priority") or "medium"),
                "status": str(item.get("status") or "proposed"),
                "priority_score": int(item.get("priority_score", 0) or 0),
                "impact_score": int(item.get("impact_score", 0) or 0),
                "blocked": bool(item.get("blocked", False)),
                "depends_on": [str(dep) for dep in item.get("depends_on", []) if isinstance(dep, str) and dep],
            }
        )
        if len(planner_queue) >= 4:
            break
    planner_next_action = (
        planner_queue[0]
        if planner_queue
        else dict(planner_state.get("next_action") or {})
        if isinstance(planner_state.get("next_action"), dict)
        else {}
    )
    route_telemetry = {
        "query_signature": question_signature(question),
        "protocol": protocol,
        "selected_strategy": selected_strategy,
        "selection_reason": str(route_strategy.get("selection_reason") or ""),
        "matched_source_markers": list(route_strategy.get("matched_source_markers", []) or []),
        "matched_graph_markers": list(route_strategy.get("matched_graph_markers", []) or []),
        "route_count": len(query_routes),
        "matched_terms": matched_terms[:8],
        "ranked_source_ids": ranked_source_ids[:5],
        "ranked_concept_slugs": ranked_concept_slugs[:5],
        "touched_component_ids": touched_component_ids[:5],
        "planner_next_action_id": str(planner_next_action.get("action_id") or ""),
    }

    return {
        "matched_terms": matched_terms,
        "direct_source_ids": sorted(direct_source_scores),
        "direct_concept_slugs": sorted(direct_concept_scores),
        "time_focus": time_focus,
        "time_focus_markers": list(time_focus_state.get("markers", []) or []),
        "route_config": dict(route_strategy.get("config") or {}),
        "selected_strategy": selected_strategy,
        "selection_reason": str(route_strategy.get("selection_reason") or ""),
        "matched_source_markers": list(route_strategy.get("matched_source_markers", []) or []),
        "matched_graph_markers": list(route_strategy.get("matched_graph_markers", []) or []),
        "ranked_source_ids": ranked_source_ids,
        "ranked_concept_slugs": ranked_concept_slugs,
        "protocol_shard_source_ids": protocol_shard_source_ids,
        "time_shard_source_ids": time_shard_source_ids,
        "archive_recall_hints": archive_recall_hints,
        "bridge_concept_slugs": bridge_concept_slugs,
        "supporting_edges": [
            {"type": edge_type, "left": left, "right": right}
            for edge_type, left, right in sorted(supporting_edges)
        ],
        "query_routes": query_routes,
        "touched_component_ids": touched_component_ids,
        "touched_components": touched_components,
        "relevant_actions": relevant_actions[:6],
        "planner_priority_queue": planner_queue,
        "planner_next_action": planner_next_action,
        "route_telemetry": route_telemetry,
        "query_subgraph": {
            "sources": query_subgraph_sources,
            "concepts": query_subgraph_concepts,
            "edges": query_subgraph_edges,
        },
    }


def build_machine_memory_query(
    memory: dict[str, Any],
    question: str,
    *,
    root: Path | None = None,
    protocol: str = DEFAULT_PROTOCOL,
    material_state: dict[str, Any] | None = None,
    routing_state: dict[str, Any] | None = None,
    archive_candidates: dict[str, Any] | None = None,
    no_cache: bool = False,
) -> dict[str, Any]:
    material_state = material_state or {"entries": []}
    routing_state = routing_state or {"entries": []}
    archive_candidates = archive_candidates or {"entries": []}
    payload_hash = _machine_memory_query_payload_hash(
        memory=memory,
        question=question,
        protocol=protocol,
        material_state=material_state,
        routing_state=routing_state,
        archive_candidates=archive_candidates,
    )
    query_key = query_cache_key(question=question, protocol=protocol)
    if root is not None and no_cache:
        record_query_cache_event(
            root,
            hit=False,
            bypass=True,
            query_key=query_key,
            payload_hash=payload_hash,
            reason="no-cache",
        )
    if root is not None and not no_cache:
        cached_result = load_cached_query_result(root, query_key, payload_hash)
        if cached_result is not None:
            record_query_cache_event(
                root,
                hit=True,
                query_key=query_key,
                payload_hash=payload_hash,
                reason="query-result",
            )
            return cached_result
        snapshot = load_query_cache_snapshot(root)
        if snapshot is not None:
            cached_memory = snapshot.get("memory")
            cached_memory_hash = str(snapshot.get("memory_hash") or "")
            if (
                isinstance(cached_memory, dict)
                and cached_memory_hash == query_cache_memory_hash(memory)
            ):
                result = _build_machine_memory_query_json(
                    cached_memory,
                    question,
                    root=root,
                    protocol=protocol,
                    material_state=material_state,
                    routing_state=routing_state,
                    archive_candidates=archive_candidates,
                )
                save_cached_query_result(root, query_key, payload_hash, result)
                record_query_cache_event(
                    root,
                    hit=False,
                    query_key=query_key,
                    payload_hash=payload_hash,
                    reason="snapshot-rebuild",
                )
                return result

    result = _build_machine_memory_query_json(
        memory,
        question,
        root=root,
        protocol=protocol,
        material_state=material_state,
        routing_state=routing_state,
        archive_candidates=archive_candidates,
    )
    if root is not None and not no_cache:
        save_cached_query_result(root, query_key, payload_hash, result)
        record_query_cache_event(
            root,
            hit=False,
            query_key=query_key,
            payload_hash=payload_hash,
            reason="json-fallback",
        )
    return result


def _judgment_relation_edge_signatures(memory: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    return {
        ("JUDGMENT_RELATION", str(edge.get("relation") or "related"), edge["from"], edge["to"])
        for edge in memory.get("edges", {}).get("judgment_to_judgment", [])
    } | {
        ("DECISION_RELATION", str(edge.get("relation") or "supports"), edge["from"], edge["to"])
        for edge in memory.get("edges", {}).get("judgment_to_decision", [])
    }


def summarize_machine_memory_transition(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_source_ids = {node["id"] for node in previous.get("source_nodes", [])}
    current_source_ids = {node["id"] for node in current.get("source_nodes", [])}
    previous_concept_slugs = {node["slug"] for node in previous.get("concept_nodes", [])}
    current_concept_slugs = {node["slug"] for node in current.get("concept_nodes", [])}
    previous_judgment_ids = {node["page_id"] for node in previous.get("judgment_nodes", [])}
    current_judgment_ids = {node["page_id"] for node in current.get("judgment_nodes", [])}
    previous_terms = set(previous.get("term_index", {}).keys())
    current_terms = set(current.get("term_index", {}).keys())
    previous_edges = {
        ("HAS_CONCEPT", edge["source_id"], edge["concept_slug"])
        for edge in previous.get("edges", {}).get("source_to_concept", [])
    } | {
        ("SUPPORTS_JUDGMENT", edge["source_id"], edge["page_id"])
        for edge in previous.get("edges", {}).get("source_to_judgment", [])
    } | {
        ("RELATED_CONCEPT", edge["from"], edge["to"])
        for edge in previous.get("edges", {}).get("concept_to_concept", [])
    } | _judgment_relation_edge_signatures(previous)
    current_edges = {
        ("HAS_CONCEPT", edge["source_id"], edge["concept_slug"])
        for edge in current.get("edges", {}).get("source_to_concept", [])
    } | {
        ("SUPPORTS_JUDGMENT", edge["source_id"], edge["page_id"])
        for edge in current.get("edges", {}).get("source_to_judgment", [])
    } | {
        ("RELATED_CONCEPT", edge["from"], edge["to"])
        for edge in current.get("edges", {}).get("concept_to_concept", [])
    } | _judgment_relation_edge_signatures(current)
    previous_digest = previous.get("digest", "")
    current_digest = current["digest"]
    return {
        "has_previous_snapshot": bool(previous_digest),
        "changed": previous_digest != current_digest,
        "previous_digest": previous_digest,
        "current_digest": current_digest,
        "added_source_ids": sorted(current_source_ids - previous_source_ids),
        "removed_source_ids": sorted(previous_source_ids - current_source_ids),
        "added_concept_slugs": sorted(current_concept_slugs - previous_concept_slugs),
        "removed_concept_slugs": sorted(previous_concept_slugs - current_concept_slugs),
        "added_judgment_ids": sorted(current_judgment_ids - previous_judgment_ids),
        "removed_judgment_ids": sorted(previous_judgment_ids - current_judgment_ids),
        "added_terms": sorted(current_terms - previous_terms)[:25],
        "removed_terms": sorted(previous_terms - current_terms)[:25],
        "added_edges": len(current_edges - previous_edges),
        "removed_edges": len(previous_edges - current_edges),
    }


def append_machine_memory_history(root: Path, memory: dict[str, Any], transition: dict[str, Any]) -> None:
    path = machine_memory_history_path(root)
    if transition["has_previous_snapshot"] and not transition["changed"]:
        return
    entry = {
        "compiled_at": memory["compiled_at"],
        "digest": memory["digest"],
        "sources": len(memory.get("source_nodes", [])),
        "concepts": len(memory.get("concept_nodes", [])),
        "judgments": len(memory.get("judgment_nodes", [])),
        "terms": len(memory.get("term_index", {})),
        "added_source_ids": transition["added_source_ids"],
        "removed_source_ids": transition["removed_source_ids"],
        "added_concept_slugs": transition["added_concept_slugs"],
        "removed_concept_slugs": transition["removed_concept_slugs"],
        "added_judgment_ids": transition["added_judgment_ids"],
        "removed_judgment_ids": transition["removed_judgment_ids"],
        "added_edges": transition["added_edges"],
        "removed_edges": transition["removed_edges"],
    }
    atomic_append_jsonl(path, entry)
