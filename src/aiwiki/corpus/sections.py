"""Shared markdown section heading aliases and preserved-section reader."""

from __future__ import annotations

import re

# (canonical_zh, *legacy_en) — single source for content.page_sections + readers.
SECTION_GROUPS: tuple[tuple[str, ...], ...] = (
    ("摘要", "Summary"),
    ("来源记录", "Source Record"),
    ("概念链接", "Concept Links"),
    ("充实待办", "Enrichment TODO"),
    ("预览", "Preview"),
    ("引用锚点", "Citation Anchor"),
    ("相关来源", "Related Sources"),
    ("相关概念", "Related Concepts"),
    ("因果网络", "Causal Network"),
    ("冲突信号", "Conflict Signals"),
    ("证据缺口", "Evidence Gaps"),
    ("维护说明", "Maintenance Notes"),
)


def section_candidates(heading: str) -> tuple[str, ...]:
    text = str(heading or "").strip()
    if not text:
        return ()
    for group in SECTION_GROUPS:
        if text in group:
            return group
    return (text,)


def preserved_section(markdown: str, heading: str, fallback: str) -> str:
    if not markdown:
        return fallback
    for name in section_candidates(heading):
        match = re.search(rf"(?ms)^## {re.escape(name)}\n(.*?)(?=^## |\Z)", markdown)
        if not match:
            continue
        section = match.group(1).strip()
        return section or fallback
    return fallback
