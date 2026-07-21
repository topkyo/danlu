"""Obsidian native graph configuration and wikilink materialization."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .content.page_sections import CONCEPT_LINKS, upsert_page_section
from .utils.io import render_json_document, write_if_changed
from .utils.markdown import parse_frontmatter, upsert_markdown_section

OBSIDIAN_EVIDENCE_GRAPH_HUB = "wiki/evidence-graph.md"

# Evidence chain only: report → source → raw note (+ judgments / hub).
# Exclude concepts/derived/elixirs/indexes (furnace-internal) and raw/assets (binaries).
OBSIDIAN_NATIVE_GRAPH_SEARCH = (
    '(path:"output/reports" OR path:"wiki/sources" OR path:"wiki/judgments" '
    'OR path:"raw/inbox" OR path:"wiki/evidence-graph") '
    '-path:"wiki/concepts" -path:"wiki/derived" -path:"wiki/elixirs" '
    '-path:"wiki/indexes" -path:"raw/assets"'
)

_CONCEPT_WIKILINK_RE = re.compile(r"\[\[wiki/concepts/([^\]|]+)(?:\|([^\]]+))?\]\]")
_SOURCE_WIKILINK_RE = re.compile(r"\[\[wiki/sources/([^\]|]+)(?:\|([^\]]+))?\]\]")
_RELATIVE_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((\.\./[^)]+|\./[^)]+)\)")

DEFAULT_OBSIDIAN_GRAPH = {
    "collapse-filter": False,
    "search": OBSIDIAN_NATIVE_GRAPH_SEARCH,
    "showTags": False,
    "showAttachments": False,
    # Product policy: no dangling drop-body paths (.nvmrc / site.ts / …) and no isolates.
    "hideUnresolved": True,
    "showOrphans": False,
    "collapse-color-groups": False,
    "colorGroups": [
        {"query": 'path:"output/reports"', "color": {"a": 1, "rgb": 14701138}},
        {"query": 'path:"wiki/sources"', "color": {"a": 1, "rgb": 5025616}},
        {"query": 'path:"wiki/judgments"', "color": {"a": 1, "rgb": 12000251}},
        {"query": 'path:"raw/inbox"', "color": {"a": 1, "rgb": 7041664}},
        {"query": 'path:"wiki/evidence-graph"', "color": {"a": 1, "rgb": 10181046}},
    ],
    "collapse-display": True,
    "showArrow": False,
    "textFadeMultiplier": 0,
    "nodeSizeMultiplier": 1,
    "lineSizeMultiplier": 2,
    "collapse-forces": True,
    "centerStrength": 0.35,
    "repelStrength": 4,
    "linkStrength": 1.2,
    "linkDistance": 120,
    "scale": 1,
    "close": True,
}


def sync_obsidian_native_graph_config(root: Path) -> bool:
    """Refresh Obsidian core graph settings for the evidence subgraph.

    Evidence-path filter is authoritative: users open Graph and see report→source→raw
    only. Obsidian may persist an empty ``search`` when the panel is closed; compile,
    layout ensure, and ``sync-evidence-graph`` always restore the product default.
    """
    path = root / ".obsidian" / "graph.json"
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    payload = dict(DEFAULT_OBSIDIAN_GRAPH)
    payload["search"] = OBSIDIAN_NATIVE_GRAPH_SEARCH
    payload["colorGroups"] = list(DEFAULT_OBSIDIAN_GRAPH["colorGroups"])
    # Authoritative display policy (do not inherit looser vault-local toggles).
    payload["hideUnresolved"] = True
    payload["showOrphans"] = False
    payload["showAttachments"] = False
    payload["showTags"] = False
    for key in ("centerStrength", "repelStrength", "linkStrength", "linkDistance", "scale", "close"):
        if key in existing:
            payload[key] = existing[key]
    # Older vaults used repelStrength=10 + linkDistance=250, which spreads nodes so far
    # that edges look invisible in the global graph view.
    if float(payload.get("repelStrength", 0)) >= 8:
        payload["repelStrength"] = DEFAULT_OBSIDIAN_GRAPH["repelStrength"]
    if float(payload.get("linkDistance", 0)) > 180:
        payload["linkDistance"] = DEFAULT_OBSIDIAN_GRAPH["linkDistance"]
    payload["lineSizeMultiplier"] = max(
        float(DEFAULT_OBSIDIAN_GRAPH["lineSizeMultiplier"]),
        float(payload.get("lineSizeMultiplier", 1)),
    )
    return write_if_changed(path, render_json_document(payload))


def sync_evidence_graph_workspace(root: Path, memory: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply evidence-graph policy: Obsidian filter + wikilink materialization."""
    from .memory.state import load_machine_memory

    memory = memory if isinstance(memory, dict) else load_machine_memory(root)
    return {
        "graph_config_updated": sync_obsidian_native_graph_config(root),
        "materialize": materialize_obsidian_native_graph_links(root, memory),
    }


def _report_anchor_ids_from_body(report_text: str, memory: dict[str, Any]) -> list[str]:
    """Heuristic anchors when machine-memory term routing returns nothing."""
    body = report_text.lower()
    anchors: list[str] = []
    seen: set[str] = set()
    for node in memory.get("source_nodes", []):
        if not isinstance(node, dict):
            continue
        source_id = str(node.get("id") or "").strip()
        if not source_id:
            continue
        title = str(node.get("title") or "").strip()
        if len(title) < 4:
            continue
        if title.lower() in body:
            anchor = f"source:{source_id}"
            if anchor not in seen:
                seen.add(anchor)
                anchors.append(anchor)
        if len(anchors) >= 4:
            break
    return anchors


def native_graph_anchor_ids(anchors: list[str]) -> list[str]:
    """Native Obsidian graph only shows reports, sources, judgments, and raw — not concepts."""
    return [str(item).strip() for item in anchors if str(item).strip().startswith(("source:", "judgment:"))]


def expand_native_anchors_from_concepts(anchors: list[str], memory: dict[str, Any]) -> list[str]:
    """Map ``concept:*`` anchors to ``source:*`` via machine-memory edges."""
    concept_slugs = {str(item).split(":", 1)[1].strip() for item in anchors if str(item).strip().startswith("concept:")}
    if not concept_slugs:
        return []
    native: list[str] = []
    seen: set[str] = set()
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        if not isinstance(edge, dict):
            continue
        if str(edge.get("concept_slug") or "") not in concept_slugs:
            continue
        source_id = str(edge.get("source_id") or "").strip()
        if not source_id:
            continue
        anchor = f"source:{source_id}"
        if anchor in seen:
            continue
        seen.add(anchor)
        native.append(anchor)
        if len(native) >= 6:
            break
    return native


def resolve_report_native_anchors(
    *,
    raw_anchors: list[str],
    machine_anchors: list[str],
    frontmatter: dict[str, Any],
    report_text: str,
    memory: dict[str, Any],
    root: Path,
) -> list[str]:
    """Resolve Obsidian-native anchors for a report (sources/judgments, never concepts)."""
    from .execution.ask import _build_graph_anchor_node_ids
    from .memory.graph_query import build_machine_memory_query

    merged = list(raw_anchors) + [item for item in machine_anchors if item not in raw_anchors]
    native = native_graph_anchor_ids(merged)
    if not native:
        native = expand_native_anchors_from_concepts(merged, memory)
    if not native:
        query = str(frontmatter.get("query") or "").strip()
        if query:
            machine_query = build_machine_memory_query(memory, query, root=root)
            built = _build_graph_anchor_node_ids(machine_query, memory)
            native = native_graph_anchor_ids(built)
            if not native:
                native = expand_native_anchors_from_concepts(built, memory)
    if not native:
        native = _report_anchor_ids_from_body(report_text, memory)
    return native


def render_plain_concept_link_lines(concepts: list[str]) -> list[str]:
    """Plain-text concept index lines — no wikilinks (keeps Obsidian evidence graph clean)."""
    from .content.concepts import concept_label_to_slug, concept_label_to_title

    cleaned = [str(item).strip() for item in concepts if str(item).strip()]
    if not cleaned:
        return ["- 暂无概念索引。"]
    lines = [
        "以下为机器记忆主题索引（纯文本，不参与 Obsidian 证据关系图）：",
        "",
    ]
    for label in cleaned:
        slug = concept_label_to_slug(label)
        title = concept_label_to_title(label)
        lines.append(f"- `{title}`（`wiki/concepts/{slug}.md`）")
    return lines


def plainify_concept_page_links(text: str) -> str:
    """Remove graph-indexable links from concept pages (machine-memory index only)."""

    def _source_repl(match: re.Match[str]) -> str:
        source_id = match.group(1).strip()
        title = (match.group(2) or source_id).strip()
        return f"`{title}`（`wiki/sources/{source_id}.md`）"

    def _relative_repl(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        href = match.group(2).strip()
        if href.startswith("./"):
            path = f"wiki/concepts/{href[2:]}"
            if not path.endswith(".md"):
                path += ".md"
            return f"`{label}`（`{path}`）"
        return f"`{label}`（`{href}`）"

    text = strip_concept_wikilinks(text)
    text = _SOURCE_WIKILINK_RE.sub(_source_repl, text)
    return _RELATIVE_MD_LINK_RE.sub(_relative_repl, text)


def strip_concept_wikilinks(text: str) -> str:
    """Replace concept wikilinks with inline paths so Obsidian does not index graph edges."""

    def _repl(match: re.Match[str]) -> str:
        slug = match.group(1).strip()
        title = (match.group(2) or slug).strip()
        return f"`{title}`（`wiki/concepts/{slug}.md`）"

    return _CONCEPT_WIKILINK_RE.sub(_repl, text)


def apply_plain_concept_links_section(text: str) -> str:
    """Rewrite Concept Links without wikilinks; strip any remaining concept wikilinks in body."""
    frontmatter = parse_frontmatter(text)
    concepts_raw = frontmatter.get("concepts")
    concepts = (
        [str(item).strip() for item in concepts_raw if str(item).strip()] if isinstance(concepts_raw, list) else []
    )
    if concepts:
        section = "\n".join(render_plain_concept_link_lines(concepts) + [""])
    elif _CONCEPT_WIKILINK_RE.search(text):
        section = "\n".join(
            [
                "以下为机器记忆主题索引（纯文本，不参与 Obsidian 证据关系图）：",
                "",
                "- （已从 wikilink 转为纯文本索引）",
                "",
            ]
        )
    else:
        return strip_concept_wikilinks(text)
    updated = upsert_page_section(text, CONCEPT_LINKS, section)
    return strip_concept_wikilinks(updated)


def render_obsidian_evidence_graph_hub(root: Path, memory: dict[str, Any]) -> str:
    """Hub note linking reports, sources, and raw materials for Obsidian's native graph."""
    lines = [
        "---",
        "kind: index",
        "title: 证据关系总览",
        "generated_by: aiwiki-compile",
        "---",
        "",
        "# 证据关系总览",
        "",
        "这是 Obsidian 原生关系图谱的枢纽页：打开侧边栏 Graph 时，可看到报告、来源与原料之间的连接（不含概念页）。",
        "",
        "## 报告",
        "",
    ]
    reports_dir = root / "output" / "reports"
    if reports_dir.is_dir():
        for path in sorted(reports_dir.glob("*.md")):
            rel = path.relative_to(root).as_posix()
            stem = path.stem
            clean = rel[:-3] if rel.endswith(".md") else rel
            lines.append(f"- [[{clean}|{stem}]]")
    else:
        lines.append("- 暂无报告。")
    lines.extend(["", "## 来源", ""])
    for node in memory.get("source_nodes", []):
        if not isinstance(node, dict):
            continue
        source_id = str(node.get("id") or "").strip()
        if not source_id:
            continue
        title = str(node.get("title") or source_id)
        lines.append(f"- [[wiki/sources/{source_id}|{title}]]")
        stored = str(node.get("stored_path") or "").replace("\\", "/").strip()
        if stored.startswith("raw/"):
            clean = stored[:-3] if stored.endswith(".md") else stored
            lines.append(f"- [[{clean}|{title}]]")
    lines.append("")
    return "\n".join(lines)


def apply_native_graph_anchor_section(destination: Path, *, anchors: list[str], memory: dict[str, Any]) -> None:
    """Upsert native-graph anchors (sources/judgments only) into the report body."""
    from .execution.ask import _obsidian_wikilink, _resolve_anchor_md_link

    native = native_graph_anchor_ids(anchors)
    lines = ["相关来源（点击跳转）：", ""]
    if native:
        seen_links: set[str] = set()
        for anchor in native:
            link = _resolve_anchor_md_link(anchor, memory, destination.parent)
            if link and link not in seen_links:
                seen_links.add(link)
                lines.append(link)
            elif not link:
                lines.append(f"- `{anchor}`")
            if not anchor.startswith("source:"):
                continue
            source_id = anchor.split(":", 1)[1]
            for node in memory.get("source_nodes", []):
                if not isinstance(node, dict) or str(node.get("id") or "") != source_id:
                    continue
                stored = str(node.get("stored_path") or "").replace("\\", "/").strip()
                if not stored.startswith("raw/"):
                    break
                title = str(node.get("title") or source_id)
                raw_link = f"- {_obsidian_wikilink(stored, f'原料：{title}')}"
                if raw_link not in seen_links:
                    seen_links.add(raw_link)
                    lines.append(raw_link)
                break
    else:
        lines.append(f"- [[{OBSIDIAN_EVIDENCE_GRAPH_HUB[:-3]}|证据关系总览]]")
    body = destination.read_text(encoding="utf-8", errors="replace")
    body = upsert_markdown_section(body, "关系图谱锚点", "\n".join(lines + [""]))
    write_if_changed(destination, body.rstrip() + "\n")


def materialize_obsidian_native_graph_links(root: Path, memory: dict[str, Any] | None = None) -> dict[str, int]:
    """Write vault-relative wikilinks so Obsidian's native graph can render edges."""
    from .memory.state import load_machine_memory
    from .utils.markdown import parse_frontmatter, upsert_markdown_section

    memory = memory if isinstance(memory, dict) else load_machine_memory(root)
    counts = {
        "sources": 0,
        "sources_concepts": 0,
        "concepts": 0,
        "reports": 0,
        "reports_backfilled": 0,
        "hub": 0,
    }

    if memory.get("compiled_at"):
        hub_path = root / OBSIDIAN_EVIDENCE_GRAPH_HUB
        hub_path.parent.mkdir(parents=True, exist_ok=True)
        if write_if_changed(hub_path, render_obsidian_evidence_graph_hub(root, memory)):
            counts["hub"] = 1
        legacy_hub = root / "wiki" / "indexes" / "evidence-graph.md"
        if legacy_hub.is_file():
            legacy_hub.unlink()
            counts["hub"] += 1

    for path in sorted((root / "wiki" / "sources").glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(text)
        updated = text
        stored_candidates = frontmatter.get("source_files") or []
        stored_path = ""
        if isinstance(stored_candidates, list):
            for item in stored_candidates:
                candidate = str(item or "").replace("\\", "/").strip()
                if candidate.startswith("raw/"):
                    stored_path = candidate
                    break
        if not stored_path:
            match = re.search(r"^- Stored path: `([^`]+)`", text, flags=re.MULTILINE)
            stored_path = str(match.group(1) if match else "").strip()
        if stored_path.startswith("raw/"):
            title = str(frontmatter.get("title") or path.stem)
            clean = stored_path[:-3] if stored_path.endswith(".md") else stored_path
            section = "\n".join([f"- [[{clean}|{title}]]", ""])
            updated = upsert_markdown_section(updated, "原料文件", section)
        if "wiki/concepts" in updated or frontmatter.get("concepts"):
            plain = apply_plain_concept_links_section(updated)
            if plain != updated:
                counts["sources_concepts"] += 1
            updated = plain
        if write_if_changed(path, updated):
            counts["sources"] += 1

    concepts_dir = root / "wiki" / "concepts"
    if concepts_dir.is_dir():
        for path in sorted(concepts_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            plain = plainify_concept_page_links(text)
            if write_if_changed(path, plain):
                counts["concepts"] += 1

    reports_dir = root / "output" / "reports"
    if not reports_dir.is_dir() or not memory.get("compiled_at"):
        return counts

    for path in sorted(reports_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(text)
        anchors_raw = frontmatter.get("graph_anchor_node_ids")
        raw_anchors = (
            [str(item).strip() for item in anchors_raw if str(item).strip()] if isinstance(anchors_raw, list) else []
        )
        machine_raw = frontmatter.get("machine_memory_anchor_node_ids")
        machine_anchors = (
            [str(item).strip() for item in machine_raw if str(item).strip()] if isinstance(machine_raw, list) else []
        )
        backfilled = False
        native_anchors = resolve_report_native_anchors(
            raw_anchors=raw_anchors,
            machine_anchors=machine_anchors,
            frontmatter=frontmatter,
            report_text=text,
            memory=memory,
            root=root,
        )
        if native_anchors and not native_graph_anchor_ids(raw_anchors):
            backfilled = True
        has_concept_anchors = any(str(item).startswith("concept:") for item in raw_anchors)
        strip_concepts = "wiki/concepts" in text
        if not native_anchors and not strip_concepts and not has_concept_anchors and "## 关系图谱锚点" in text:
            continue
        from .execution.candidates import (
            write_graph_anchor_frontmatter,
            write_machine_memory_anchor_frontmatter,
        )

        before = path.read_text(encoding="utf-8", errors="replace")
        apply_native_graph_anchor_section(path, anchors=native_anchors, memory=memory)
        stripped = strip_concept_wikilinks(path.read_text(encoding="utf-8", errors="replace"))
        write_if_changed(path, stripped)
        full_anchors = machine_anchors or raw_anchors
        if full_anchors and any(str(item).startswith("concept:") for item in full_anchors):
            write_machine_memory_anchor_frontmatter(path, anchors=full_anchors)
        if raw_anchors and (
            native_anchors != raw_anchors or any(str(item).startswith("concept:") for item in raw_anchors)
        ):
            write_graph_anchor_frontmatter(path, anchors=native_anchors, force=True)
        after = path.read_text(encoding="utf-8", errors="replace")
        if after != before:
            counts["reports"] += 1
            if backfilled:
                counts["reports_backfilled"] += 1
    return counts


__all__ = [
    "DEFAULT_OBSIDIAN_GRAPH",
    "OBSIDIAN_EVIDENCE_GRAPH_HUB",
    "OBSIDIAN_NATIVE_GRAPH_SEARCH",
    "expand_native_anchors_from_concepts",
    "resolve_report_native_anchors",
    "apply_native_graph_anchor_section",
    "apply_plain_concept_links_section",
    "materialize_obsidian_native_graph_links",
    "native_graph_anchor_ids",
    "plainify_concept_page_links",
    "render_plain_concept_link_lines",
    "strip_concept_wikilinks",
    "sync_evidence_graph_workspace",
    "sync_obsidian_native_graph_config",
]
