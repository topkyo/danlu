"""Markdown link helpers and protocol output-pack row projection."""

from __future__ import annotations

from typing import Any

from ..state.constants import DEFAULT_PROTOCOL


def compact_section_lines(markdown: str, heading: str, *, fallback: str, limit: int = 5) -> list[str]:
    from ..content.io import preserved_section

    section = preserved_section(markdown, heading, "").strip()
    if not section:
        return [fallback]
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    if not lines:
        return [fallback]
    if len(lines) > limit:
        return [*lines[:limit], "- ..."]
    return lines


def workspace_link(path: str, label: str | None = None) -> str:
    target = path.strip()
    display = label or target
    return f"[{display}](../../{target})"


def pack_workspace_link(path: str, label: str | None = None) -> str:
    target = path.strip()
    display = label or target
    return f"[{display}](../../../{target})"


def protocol_output_pack_rows(output_packs: dict[str, Any], protocol: str, *, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for pack in output_packs.get("review_packs", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "Review Pack",
                "title": str(pack.get("title") or "Review Pack"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("reasons") or "manual review"),
            }
        )
    for pack in output_packs.get("decision_memos", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "Decision Memo",
                "title": str(pack.get("title") or "Decision Memo"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("reviewed_at") or "reviewed"),
            }
        )
    for pack in output_packs.get("sop_drafts", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "SOP Draft",
                "title": str(pack.get("title") or "SOP Draft"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("risk") or "medium"),
            }
        )
    rows.sort(key=lambda item: (item["kind"], item["title"].lower()))
    return rows[:limit]
