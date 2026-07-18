"""Machine-memory graph builder extracted from the legacy app_memory owner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..state.constants import DEFAULT_PROTOCOL
from ..utils.hash import sha256_bytes
from ..utils.markdown import parse_frontmatter, strip_frontmatter
from ..utils.path import relative_path


def _existing_markdown_graph_path(root: Path | None, path: str) -> str | None:
    normalized = path.strip()
    if not normalized or not normalized.endswith(".md"):
        return None
    if root is None:
        return normalized
    candidate = Path(normalized)
    absolute = candidate if candidate.is_absolute() else root / candidate
    try:
        root_resolved = root.resolve()
        resolved = absolute.resolve()
        relative = resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        return None
    if not resolved.is_file():
        return None
    return relative.as_posix()


def _markdown_graph_title(root: Path | None, page_path: str, fallback: str, *, prefix: str = "") -> str:
    fallback = str(fallback or "").strip() or Path(page_path).stem
    if root is None:
        title = fallback
    else:
        path = root / page_path
        title = ""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        frontmatter = parse_frontmatter(text) if text else {}
        for key in ("topic", "title", "id"):
            value = str(frontmatter.get(key) or "").strip()
            if value and value.lower() != "elixir":
                title = value
                break
        if not title and text:
            for line in strip_frontmatter(text).splitlines():
                heading = line.strip()
                if not heading.startswith("#"):
                    continue
                value = heading.lstrip("#").strip()
                if value and value.lower() != "elixir":
                    title = value
                    break
        title = title or fallback
    if prefix and not title.startswith(prefix):
        return f"{prefix}{title}"
    return title


def _has_cjk_text(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


_GRAPH_GENERATED_CONCEPT_PREFIXES = (
    "- 当前概念汇总了 ",
    "- 当前最直接的线索：",
    "- 当前 source page ",
    "- 目前还没有可引用的 source page ",
    "- 这还是单来源概念页；",
    "- 下一步优先收敛",
    "- 当前没有显式因果关系。",
    "- 当前没有显式冲突信号。",
    "- 当前没有显式证据缺口。",
)


def _markdown_graph_body_signal(markdown: str, *, kind: str = "") -> str:
    body_lines: list[str] = []
    for raw_line in strip_frontmatter(markdown).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if kind == "concept" and line.startswith(_GRAPH_GENERATED_CONCEPT_PREFIXES):
            continue
        body_lines.append(line)
    return "\n".join(body_lines)


def _markdown_graph_chinese_related(root: Path | None, page_path: str, title: str, *, kind: str = "") -> bool:
    signals = [title, page_path]
    if root is not None:
        try:
            text = (root / page_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if text:
            frontmatter = parse_frontmatter(text)
            for value in frontmatter.values():
                if isinstance(value, str):
                    signals.append(value)
                elif isinstance(value, list):
                    signals.extend(str(item) for item in value)
            signals.append(_markdown_graph_body_signal(text, kind=kind))
    return _has_cjk_text("\n".join(signals))


def build_machine_memory_graph(memory: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    elixir_path_to_node_id: dict[str, str] = {}
    for node in memory.get("source_nodes", []):
        source_page = _existing_markdown_graph_path(root, str(node.get("source_page") or ""))
        if source_page is None:
            continue
        title = _markdown_graph_title(root, source_page, str(node.get("title") or node["id"]))
        nodes.append(
            {
                "id": f"source:{node['id']}",
                "kind": "source",
                "title": title,
                "chinese_related": _markdown_graph_chinese_related(root, source_page, title, kind="source"),
                "source_type": node["source_type"],
                "source_page": source_page,
                "page_path": source_page,
                "stored_path": node["stored_path"],
            }
        )
    for node in memory.get("concept_nodes", []):
        slug = str(node.get("slug") or "")
        page_path = _existing_markdown_graph_path(root, f"wiki/concepts/{slug}.md")
        if page_path is None:
            continue
        title = _markdown_graph_title(root, page_path, str(node.get("title") or slug))
        nodes.append(
            {
                "id": f"concept:{slug}",
                "kind": "concept",
                "title": title,
                "chinese_related": _markdown_graph_chinese_related(root, page_path, title, kind="concept"),
                "page_path": page_path,
                "source_pages": node["source_pages"],
            }
        )
    for node in memory.get("judgment_nodes", []):
        page_path = _existing_markdown_graph_path(root, str(node.get("path") or ""))
        if page_path is None:
            continue
        title = _markdown_graph_title(root, page_path, str(node.get("title") or node["page_id"]))
        nodes.append(
            {
                "id": f"judgment:{node['page_id']}",
                "kind": "judgment",
                "title": title,
                "chinese_related": _markdown_graph_chinese_related(root, page_path, title, kind="judgment"),
                "page_path": page_path,
                "page_kind": node["kind"],
                "status": node["status"],
                "source_ids": node.get("source_ids", []),
            }
        )
    if root is not None:
        elixir_dir = root / "wiki" / "elixirs"
        for page in sorted(elixir_dir.glob("*.md")) if elixir_dir.exists() else []:
            page_path = _existing_markdown_graph_path(root, relative_path(root, page))
            if page_path is None:
                continue
            try:
                frontmatter = parse_frontmatter(page.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                frontmatter = {}
            state = str(frontmatter.get("elixir_state") or "settled").strip() or "settled"
            if state != "settled":
                continue
            elixir_id = str(frontmatter.get("id") or page.stem).strip() or page.stem
            node_id = f"elixir:{elixir_id}"
            elixir_path_to_node_id[page_path] = node_id
            derived_from = (
                [str(item).strip() for item in frontmatter.get("derived_from", []) if str(item).strip()]
                if isinstance(frontmatter.get("derived_from"), list)
                else []
            )
            title = _markdown_graph_title(root, page_path, elixir_id, prefix="金丹：")
            nodes.append(
                {
                    "id": node_id,
                    "kind": "elixir",
                    "title": title,
                    "chinese_related": _markdown_graph_chinese_related(root, page_path, title, kind="elixir"),
                    "page_path": page_path,
                    "elixir_state": state,
                    "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                    "derived_from": derived_from,
                }
            )
    retained_node_ids = {str(node.get("id") or "") for node in nodes}
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        edges.append(
            {
                "source": f"source:{edge['source_id']}",
                "target": f"concept:{edge['concept_slug']}",
                "type": "HAS_CONCEPT",
            }
        )
    for edge in memory.get("edges", {}).get("source_to_judgment", []):
        edges.append(
            {
                "source": f"source:{edge['source_id']}",
                "target": f"judgment:{edge['page_id']}",
                "type": "SUPPORTS_JUDGMENT",
            }
        )
    for edge in memory.get("edges", {}).get("judgment_to_judgment", []):
        relation = str(edge.get("relation") or "related").upper()
        edges.append(
            {
                "source": f"judgment:{edge['from']}",
                "target": f"judgment:{edge['to']}",
                "type": f"JUDGMENT_{relation}",
            }
        )
    for edge in memory.get("edges", {}).get("judgment_to_decision", []):
        relation = str(edge.get("relation") or "supports").upper()
        edges.append(
            {
                "source": f"judgment:{edge['from']}",
                "target": f"judgment:{edge['to']}",
                "type": f"DECISION_{relation}",
            }
        )
    for edge in memory.get("edges", {}).get("concept_to_concept", []):
        edges.append(
            {
                "source": f"concept:{edge['from']}",
                "target": f"concept:{edge['to']}",
                "type": "RELATED_CONCEPT",
            }
        )
    for edge in memory.get("edges", {}).get("concept_causal", []):
        relation = str(edge.get("relation") or "causes").upper()
        edges.append(
            {
                "source": f"concept:{edge['from']}",
                "target": f"concept:{edge['to']}",
                "type": f"CAUSAL_{relation}",
            }
        )
    for node in nodes:
        if node.get("kind") != "elixir":
            continue
        target = str(node.get("id") or "")
        for ref in node.get("derived_from", []):
            source = elixir_path_to_node_id.get(str(ref))
            if source:
                edges.append({"source": source, "target": target, "type": "ELIXIR_DERIVED_FROM"})
    edges = [
        edge
        for edge in edges
        if str(edge.get("source") or "") in retained_node_ids and str(edge.get("target") or "") in retained_node_ids
    ]
    graph = {
        "version": 1,
        "compiled_at": memory["compiled_at"],
        "nodes": sorted(nodes, key=lambda item: (item["kind"], item["id"])),
        "edges": sorted(edges, key=lambda item: (item["type"], item["source"], item["target"])),
    }
    graph["digest"] = sha256_bytes(
        json.dumps({"nodes": graph["nodes"], "edges": graph["edges"]}, sort_keys=True).encode("utf-8")
    )
    return graph
