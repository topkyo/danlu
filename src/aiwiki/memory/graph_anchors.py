"""Report anchor / subgraph surfaces for the machine-memory graph.

EP-017B step 2: extracted from memory/graph.py. Holds the report-anchor
reverse index, the per-report 1-hop subgraph builder, and the markdown
renderer for subgraph artifacts. Re-exported via the thin ``memory.graph``
facade for backward compatibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .graph_render import relation_label

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
    from ..utils.markdown import parse_frontmatter
    from ..utils.path import relative_path

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
        title = str(frontmatter.get("title") or "").strip() or str(frontmatter.get("id") or "").strip() or path.stem
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
    from ..memory.graph_builder import build_machine_memory_graph
    from ..utils.markdown import parse_frontmatter
    from .state import load_machine_memory

    report_rel = str(report_path or "").strip()
    if not report_rel:
        raise ReportSubgraphError("report path is empty")
    root_resolved = root.resolve()
    candidate = Path(report_rel)
    absolute = candidate.resolve() if candidate.is_absolute() else (root_resolved / candidate).resolve()
    try:
        absolute.relative_to(root_resolved)
    except ValueError as exc:
        raise ReportSubgraphError(f"report path is outside the vault root: {report_rel}") from exc
    if not absolute.is_file():
        raise ReportSubgraphError(f"report not found: {report_rel}")

    text = absolute.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(text)
    anchors = report_memory_anchor_ids(frontmatter)
    if not anchors:
        raise ReportSubgraphError(f"report {report_rel} has no machine-memory graph anchors in frontmatter")

    memory = load_machine_memory(root)
    if not isinstance(memory, dict) or not memory.get("compiled_at"):
        raise ReportSubgraphError("machine memory is not compiled; run `aiwiki advanced compile` first")
    try:
        graph = build_machine_memory_graph(memory, root=root)
    except Exception as exc:  # corrupt/incomplete memory shape
        raise ReportSubgraphError(
            f"machine memory is corrupt or incomplete ({type(exc).__name__}: {exc}); rerun `aiwiki advanced compile`"
        ) from exc
    nodes_by_id: dict[str, dict[str, Any]] = {str(node.get("id") or ""): node for node in graph.get("nodes", [])}
    missing = [anchor for anchor in anchors if anchor not in nodes_by_id]
    if missing:
        raise ReportSubgraphError(f"report {report_rel} references unknown graph nodes: {', '.join(missing)}")

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
            kind_zh = {"source": "来源", "concept": "概念", "judgment": "判断", "elixir": "金丹"}.get(
                kind, kind or "节点"
            )
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
