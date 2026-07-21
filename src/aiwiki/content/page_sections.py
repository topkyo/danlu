"""Canonical Chinese page section headings with English read aliases.

Compile writes Chinese ``##`` headings for source/concept pages. Readers still
accept legacy English headings so existing vaults/fixtures keep working until
recompile upgrades them.
"""

from __future__ import annotations

import re

# (canonical_zh, *legacy_en)
_SECTION_GROUPS: tuple[tuple[str, ...], ...] = (
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

SUMMARY = "摘要"
SOURCE_RECORD = "来源记录"
CONCEPT_LINKS = "概念链接"
ENRICHMENT_TODO = "充实待办"
PREVIEW = "预览"
CITATION_ANCHOR = "引用锚点"
RELATED_SOURCES = "相关来源"
RELATED_CONCEPTS = "相关概念"
CAUSAL_NETWORK = "因果网络"
CONFLICT_SIGNALS = "冲突信号"
EVIDENCE_GAPS = "证据缺口"
MAINTENANCE_NOTES = "维护说明"


def section_candidates(heading: str) -> tuple[str, ...]:
    text = str(heading or "").strip()
    if not text:
        return ()
    for group in _SECTION_GROUPS:
        if text in group:
            return group
    return (text,)


def canonical_section(heading: str) -> str:
    candidates = section_candidates(heading)
    return candidates[0] if candidates else str(heading or "").strip()


def page_has_section(markdown: str, heading: str) -> bool:
    text = str(markdown or "")
    for name in section_candidates(heading):
        if re.search(rf"(?m)^## {re.escape(name)}\s*$", text):
            return True
    return False


def upsert_page_section(markdown: str, heading: str, content: str) -> str:
    """Write ``heading`` as its Chinese canonical form; replace any EN/CN alias."""
    canonical = canonical_section(heading)
    section = str(content or "").strip()
    block = f"## {canonical}\n{section}\n"
    text = str(markdown or "")
    replaced = False
    for name in section_candidates(heading):
        pattern = rf"(?ms)^## {re.escape(name)}\n(.*?)(?=^## |\Z)"
        if not re.search(pattern, text):
            continue
        if not replaced:
            text = re.sub(pattern, block + "\n", text, count=1)
            replaced = True
        else:
            text = re.sub(pattern, "", text)
    if replaced:
        return text.strip() + "\n"
    base = text.rstrip()
    if base:
        return base + "\n\n" + block
    return block
