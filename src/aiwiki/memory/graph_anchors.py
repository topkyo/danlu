"""Report anchor surfaces for the machine-memory graph.

Compile-time helper: scans recent reports for ``graph_anchor_node_ids`` and
builds a ``node_id -> [{"title", "path"}, ...]`` reverse index used by ask
and graph JSON export.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Round 49: report ↔ graph anchor reverse index. Compile-time helper that
# scans recent reports for ``graph_anchor_node_ids`` and produces a
# ``node_id -> [{"title", "path"}, ...]`` map for downstream graph surfaces.
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
    """Machine-memory anchors for ask/graph JSON; prefers ``machine_memory_anchor_node_ids``."""
    for key in ("machine_memory_anchor_node_ids", "graph_anchor_node_ids"):
        raw = frontmatter.get(key)
        if isinstance(raw, list):
            anchors = [str(item).strip() for item in raw if str(item).strip()]
            if anchors:
                return anchors
    return []
