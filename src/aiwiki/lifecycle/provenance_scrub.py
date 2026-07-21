"""Report provenance scrub helpers (dead output/reports refs)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..utils.io import atomic_write_text
from ..utils.markdown import (
    frontmatter_string_list,
    parse_frontmatter,
    render_frontmatter,
    strip_frontmatter,
)
from ..utils.path import relative_path

REPORT_PREFIX = "output/reports/"
_CURATED_REL_DIRS = (
    "wiki/judgments",
    "wiki/derived",
    "wiki/elixirs",
)


def is_report_ref(value: str) -> bool:
    text = str(value or "").strip().replace("\\", "/")
    return text.startswith(REPORT_PREFIX)


def path_exists_in_root(root: Path, rel: str) -> bool:
    text = str(rel or "").strip().replace("\\", "/")
    if not text or text.startswith(("http://", "https://", "#")):
        return False
    candidate = (root / text).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return False
    return candidate.is_file()


def _filter_string_list(root: Path, values: list[str]) -> tuple[list[str], list[str]]:
    """Return (kept, stripped_dead_reports)."""
    kept: list[str] = []
    stripped: list[str] = []
    for raw in values:
        item = str(raw or "").strip()
        if not item:
            continue
        if is_report_ref(item) and not path_exists_in_root(root, item):
            stripped.append(item)
            continue
        kept.append(item)
    return kept, stripped


def _filter_citations(root: Path, values: list[Any]) -> tuple[list[Any], list[str]]:
    kept: list[Any] = []
    stripped: list[str] = []
    for raw in values:
        if isinstance(raw, str) and is_report_ref(raw) and not path_exists_in_root(root, raw):
            stripped.append(raw.strip())
            continue
        kept.append(raw)
    return kept, stripped


def classify_after_strip(root: Path, kept_paths: list[str], *, had_dead_reports: bool) -> str:
    if not had_dead_reports:
        return "ok"
    for path in kept_paths:
        if path_exists_in_root(root, path):
            return "degraded"
        # Non-path tokens (titles, ids) do not count as live anchors.
        if not ("/" in path or path.endswith(".md")):
            continue
    return "broken"


def scrub_page_text(root: Path, text: str) -> tuple[str, dict[str, Any]]:
    """Scrub one markdown page. Returns (new_text, meta)."""
    frontmatter = parse_frontmatter(text)
    if not frontmatter:
        return text, {"changed": False, "status": "ok", "stripped": []}

    stripped_all: list[str] = []
    source_files = frontmatter_string_list(frontmatter, "source_files")
    derived_from = frontmatter_string_list(frontmatter, "derived_from")
    citations = frontmatter.get("citations")
    citation_list = citations if isinstance(citations, list) else []

    new_source, stripped_sf = _filter_string_list(root, source_files)
    new_derived, stripped_df = _filter_string_list(root, derived_from)
    new_citations, stripped_cit = _filter_citations(root, citation_list)
    stripped_all.extend(stripped_sf)
    stripped_all.extend(stripped_df)
    stripped_all.extend(stripped_cit)

    had_dead = bool(stripped_all)
    previous_status = str(frontmatter.get("provenance_status") or "").strip()
    if had_dead:
        status = classify_after_strip(
            root,
            [*new_source, *new_derived, *[c for c in new_citations if isinstance(c, str)]],
            had_dead_reports=True,
        )
    elif previous_status in {"degraded", "broken"}:
        # Sticky until explicit GC: already-stripped pages must not flip back to ok.
        status = previous_status
    else:
        if (
            new_source == source_files
            and new_derived == derived_from
            and (not isinstance(citations, list) or new_citations == citation_list)
        ):
            return text, {"changed": False, "status": previous_status or "ok", "stripped": []}
        status = previous_status or "ok"

    changed = (
        new_source != source_files
        or new_derived != derived_from
        or (isinstance(citations, list) and new_citations != citation_list)
        or previous_status != status
        or had_dead
    )
    if not changed:
        return text, {"changed": False, "status": previous_status or status, "stripped": []}

    frontmatter["source_files"] = new_source
    if "derived_from" in frontmatter or new_derived:
        frontmatter["derived_from"] = new_derived
    if isinstance(citations, list) or stripped_cit:
        frontmatter["citations"] = new_citations
    if had_dead or previous_status in {"degraded", "broken"} or status in {"degraded", "broken"}:
        frontmatter["provenance_status"] = status
    elif previous_status:
        frontmatter["provenance_status"] = status

    body = strip_frontmatter(text)
    rendered = render_frontmatter(frontmatter) + ("\n\n" + body if body.strip() else "\n")
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered, {"changed": True, "status": status, "stripped": stripped_all}


def iter_curated_pages(root: Path) -> list[Path]:
    pages: list[Path] = []
    for rel in _CURATED_REL_DIRS:
        directory = root / rel
        if not directory.is_dir():
            continue
        pages.extend(sorted(path for path in directory.glob("*.md") if path.is_file()))
    return pages


def scrub_curated_pages(root: Path) -> dict[str, Any]:
    """Rewrite curated pages in place. Returns counts + changed paths."""
    degraded = 0
    broken = 0
    ok = 0
    changed_paths: list[str] = []
    stripped_total = 0
    for path in iter_curated_pages(root):
        original = path.read_text(encoding="utf-8")
        rewritten, meta = scrub_page_text(root, original)
        status = str(meta.get("status") or "ok")
        if status == "degraded":
            degraded += 1
        elif status == "broken":
            broken += 1
        else:
            ok += 1
        stripped_total += len(meta.get("stripped") or [])
        if meta.get("changed") and rewritten != original:
            atomic_write_text(path, rewritten)
            changed_paths.append(relative_path(root, path))
    return {
        "ok": ok,
        "degraded": degraded,
        "broken": broken,
        "changed_paths": changed_paths,
        "dead_report_refs_stripped": stripped_total,
    }


def count_provenance_statuses(root: Path) -> dict[str, int]:
    degraded = 0
    broken = 0
    for path in iter_curated_pages(root):
        status = str(parse_frontmatter(path.read_text(encoding="utf-8")).get("provenance_status") or "").strip()
        if status == "degraded":
            degraded += 1
        elif status == "broken":
            broken += 1
    return {"provenance_degraded": degraded, "provenance_broken": broken}


__all__ = [
    "REPORT_PREFIX",
    "classify_after_strip",
    "count_provenance_statuses",
    "is_report_ref",
    "iter_curated_pages",
    "path_exists_in_root",
    "scrub_curated_pages",
    "scrub_page_text",
]
