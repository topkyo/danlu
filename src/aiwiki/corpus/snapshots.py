"""Read-only wiki page snapshots shared by content and memory."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..utils.hash import compiled_source_sha
from ..utils.markdown import parse_frontmatter
from ..utils.path import relative_path
from .sections import preserved_section


def normalize_summary_snippet(text: Any, *, limit: int = 200) -> str:
    if not isinstance(text, str):
        return ""
    snippet = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    snippet = snippet.replace("\r", "\n")
    snippet = re.sub(r"^[#>\-\*\d\.\s]+", "", snippet, flags=re.MULTILINE)
    snippet = re.sub(r"[`*_]", "", snippet)
    snippet = re.sub(r"\s+", " ", snippet).strip()
    if len(snippet) <= limit:
        return snippet
    return snippet[: limit - 1].rstrip() + "…"


def concept_summary_matches_legacy_placeholder(summary: Any) -> bool:
    normalized = normalize_summary_snippet(summary).lower()
    if not normalized.startswith("this concept currently appears in"):
        return False
    return (
        "use the linked source pages below to deepen or revise this synthesis" in normalized
        or "source page" in normalized
        or "wiki/sources/" in normalized
    )


def source_summary_or_preview(root: Path, entry: dict[str, Any], preview: str) -> str:
    page = root / "wiki" / "sources" / f"{entry['id']}.md"
    if page.exists():
        content = page.read_text(encoding="utf-8", errors="replace")
        summary = preserved_section(content, "Summary", "")
        if compiled_source_sha(content) in ("", entry["sha256"]) and summary and "Pending LLM summary." not in summary:
            non_preview_lines = [
                line for line in summary.splitlines() if not line.strip().startswith("- Deterministic preview:")
            ]
            cleaned_summary = "\n".join(line for line in non_preview_lines if line.strip()).strip()
            return cleaned_summary or summary
    return preview


def concept_page_snapshot(root: Path, slug: str) -> dict[str, Any]:
    path = root / "wiki" / "concepts" / f"{slug}.md"
    if not path.exists():
        return {
            "path": relative_path(root, path),
            "title": slug,
            "source_signature": "",
            "source_pages": [],
            "summary": "",
            "content": "",
        }
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    source_pages = frontmatter.get("source_pages", [])
    if not isinstance(source_pages, list):
        source_pages = []
    return {
        "path": relative_path(root, path),
        "title": str(frontmatter.get("title") or path.stem),
        "source_signature": str(frontmatter.get("source_signature") or ""),
        "source_pages": [str(item) for item in source_pages if isinstance(item, str)],
        "summary": preserved_section(content, "Summary", ""),
        "content": content,
    }


def placeholder_concept_slugs(root: Path) -> list[str]:
    """Return concept slugs whose Summary matches the legacy placeholder marker."""
    slugs: list[str] = []
    for page in sorted((root / "wiki" / "concepts").glob("*.md")):
        content = page.read_text(encoding="utf-8", errors="replace")
        summary = preserved_section(content, "Summary", "")
        if concept_summary_matches_legacy_placeholder(summary):
            slugs.append(page.stem)
    return slugs
