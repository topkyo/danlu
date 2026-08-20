"""Frontmatter / output formatting helpers for run-ask workflows."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aiwiki.runner.report_refs import OUTPUT_OBSIDIAN_CSSCLASS, OUTPUT_REPORT_LEAF_CSSCLASS
from aiwiki.utils.io import atomic_write_text
from aiwiki.utils.markdown import frontmatter_string_list, parse_frontmatter, render_frontmatter

_REPORT_SKELETON_REFERENCE_HEADINGS = {"## 参考"}
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")




def _runtime_provenance_field_lines(fields: dict[str, Any]) -> list[str]:
    if not fields:
        return []
    rendered = render_frontmatter(fields).splitlines()
    return rendered[1:-1]


def _drop_frontmatter_keys(header_lines: list[str], keys: set[str]) -> list[str]:
    filtered: list[str] = []
    skip_list_items = False
    for line in header_lines:
        if skip_list_items and line.startswith("  - "):
            continue
        skip_list_items = False
        if ":" not in line:
            filtered.append(line)
            continue
        key, _raw = line.split(":", 1)
        if key.strip() in keys:
            skip_list_items = True
            continue
        filtered.append(line)
    return filtered


def _ensure_output_cssclass(target: Path) -> None:
    """Ensure generated output hides Obsidian properties without dropping audit metadata."""

    if not target.exists():
        raise FileNotFoundError(f"output artifact not found: {target}")
    original = target.read_text(encoding="utf-8", errors="replace")
    lines = original.splitlines()
    has_frontmatter = bool(lines) and lines[0].strip() == "---"
    close_idx: int | None = None
    if has_frontmatter:
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                close_idx = idx
                break
    if not has_frontmatter or close_idx is None:
        updated = render_frontmatter({"cssclasses": [OUTPUT_OBSIDIAN_CSSCLASS]}).splitlines() + lines
        atomic_write_text(target, "\n".join(updated).rstrip() + "\n")
        return
    current = parse_frontmatter(original)
    raw_classes = current.get("cssclasses", [])
    classes = [str(item).strip() for item in raw_classes if str(item).strip()] if isinstance(raw_classes, list) else []
    if isinstance(raw_classes, str) and raw_classes.strip():
        classes = [raw_classes.strip()]
    if OUTPUT_OBSIDIAN_CSSCLASS in classes:
        needs_report_leaf = "output/reports/" in target.as_posix() and OUTPUT_REPORT_LEAF_CSSCLASS not in classes
        if not needs_report_leaf:
            return
    else:
        classes.append(OUTPUT_OBSIDIAN_CSSCLASS)
    if "output/reports/" in target.as_posix() and OUTPUT_REPORT_LEAF_CSSCLASS not in classes:
        classes.append(OUTPUT_REPORT_LEAF_CSSCLASS)
    header = _drop_frontmatter_keys(lines[1:close_idx], {"cssclasses"})
    css_lines = _runtime_provenance_field_lines({"cssclasses": classes})
    updated_lines = [lines[0], *header, *css_lines, lines[close_idx], *lines[close_idx + 1 :]]
    atomic_write_text(target, "\n".join(updated_lines).rstrip() + "\n")


def _restore_run_ask_provenance_frontmatter(
    target: Path,
    deterministic_artifact: str,
    *,
    material_refs: list[str] | None = None,
    used_context_refs: list[str] | None = None,
    used_refs: list[str] | None = None,
    web_search_used: bool | None = None,
    used_web_refs: list[str] | None = None,
) -> None:
    """Restore runtime-owned provenance fields after LLM overwrites an artifact.

    The LLM is allowed to rewrite the markdown body/frontmatter, but provenance used by
    audit gates is owned by the runtime. Restore these fields strictly from the
    deterministic artifact; LLM-provided provenance is dropped instead of trusted.
    """

    deterministic_frontmatter = parse_frontmatter(deterministic_artifact)
    current = target.read_text(encoding="utf-8", errors="replace")
    restored: dict[str, Any] = {}
    for key in ("derived_from", "source_files"):
        merged: list[str] = []
        for item in frontmatter_string_list(deterministic_frontmatter, key):
            if item not in merged:
                merged.append(item)
        if merged:
            restored[key] = merged
    for key, refs in (
        ("material_refs", material_refs or []),
        ("used_context_refs", used_context_refs or []),
        ("used_refs", used_refs or []),
        ("used_web_refs", used_web_refs if used_web_refs is not None else []),
    ):
        merged = []
        for item in refs:
            normalized = str(item or "").strip()
            if normalized and normalized not in merged:
                merged.append(normalized)
        if merged or (key == "used_web_refs" and used_web_refs is not None):
            restored[key] = merged
    if web_search_used is not None:
        restored["web_search_used"] = web_search_used

    lines = current.splitlines()
    has_frontmatter = bool(lines) and lines[0].strip() == "---"
    close_idx: int | None = None
    if has_frontmatter:
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                close_idx = idx
                break
    keys = {
        "derived_from",
        "source_files",
        "material_refs",
        "used_context_refs",
        "used_refs",
        "web_search_used",
        "used_web_refs",
    }
    restored_lines = _runtime_provenance_field_lines(restored)
    if not has_frontmatter or close_idx is None:
        if not restored_lines:
            return
        updated_lines = ["---", *restored_lines, "---", *lines]
    else:
        header = _drop_frontmatter_keys(lines[1:close_idx], keys)
        updated_lines = [lines[0], *header, *restored_lines, lines[close_idx], *lines[close_idx + 1 :]]
    atomic_write_text(target, "\n".join(updated_lines).rstrip() + "\n")


def _strip_report_skeleton_reference_hints(markdown: str) -> str:
    lines = str(markdown or "").splitlines()
    if not lines:
        return markdown
    h2_positions: list[tuple[int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## ") and not line.startswith("### "):
            h2_positions.append((index, line.strip()))
    if not any(title in _REPORT_SKELETON_REFERENCE_HEADINGS for _index, title in h2_positions):
        return markdown
    remove_ranges: list[tuple[int, int]] = []
    for position_index, (line_index, title) in enumerate(h2_positions):
        if title not in _REPORT_SKELETON_REFERENCE_HEADINGS:
            continue
        end = h2_positions[position_index + 1][0] if position_index + 1 < len(h2_positions) else len(lines)
        remove_ranges.append((line_index, end))
    kept: list[str] = []
    for index, line in enumerate(lines):
        if any(start <= index < end for start, end in remove_ranges):
            continue
        kept.append(line)
    return "\n".join(kept).rstrip() + "\n"


def _append_visible_quoted_report_refs(markdown: str, refs: list[str]) -> str:
    quoted_refs: list[str] = []
    for ref in refs:
        text = str(ref or "").strip()
        if not text.startswith("output/reports/") or not text.endswith(".md"):
            continue
        if text not in quoted_refs:
            quoted_refs.append(text)
    if not quoted_refs:
        return markdown

    lines = str(markdown or "").splitlines()
    h2_positions: list[tuple[int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## ") and not line.startswith("### "):
            h2_positions.append((index, line.strip()))

    remove_ranges: list[tuple[int, int]] = []
    for position_index, (line_index, title) in enumerate(h2_positions):
        if title != "## 引用报告":
            continue
        end = h2_positions[position_index + 1][0] if position_index + 1 < len(h2_positions) else len(lines)
        remove_ranges.append((line_index, end))

    kept = [line for index, line in enumerate(lines) if not any(start <= index < end for start, end in remove_ranges)]
    section = ["", "## 引用报告", *[f"- {ref}" for ref in quoted_refs]]
    return "\n".join(kept).rstrip() + "\n" + "\n".join(section).rstrip() + "\n"


def rewrite_report_relative_links(markdown: str, *, report_path: Path, root: Path) -> str:
    """Fix one-level-short relative links from ``output/reports/`` (``../schema`` → ``../../schema``)."""

    report_dir = report_path.parent
    root_resolved = root.resolve(strict=False)

    def _replace(match: re.Match[str]) -> str:
        label = match.group(1)
        href = str(match.group(2) or "").strip()
        if not href or href.startswith(("http://", "https://", "#", "mailto:")):
            return match.group(0)
        path_part, frag = (href.split("#", 1) + [""])[:2]
        if not path_part.startswith("."):
            return match.group(0)
        current = (report_dir / path_part).resolve(strict=False)
        try:
            current.relative_to(root_resolved)
            if current.exists():
                return match.group(0)
        except ValueError:
            pass
        extra = Path("..") / path_part
        candidate = (report_dir / extra).resolve(strict=False)
        try:
            candidate.relative_to(root_resolved)
        except ValueError:
            return match.group(0)
        if not candidate.exists():
            return match.group(0)
        new_href = extra.as_posix()
        if frag:
            new_href = f"{new_href}#{frag}"
        return f"[{label}]({new_href})"

    return _MD_LINK_RE.sub(_replace, markdown)
