"""Canonical Chinese page section headings with English read aliases.

Compile writes Chinese ``##`` headings for source/concept pages. Readers still
accept legacy English headings so existing vaults/fixtures keep working until
recompile upgrades them.

Heading groups live in ``aiwiki.corpus.sections`` (single source with
``preserved_section``).
"""

from __future__ import annotations

import re

from ..corpus.sections import SECTION_GROUPS, section_candidates

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

# Keep local name for any in-module references; groups owned by corpus.
_SECTION_GROUPS = SECTION_GROUPS


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


__all__ = [
    "SUMMARY",
    "SOURCE_RECORD",
    "CONCEPT_LINKS",
    "ENRICHMENT_TODO",
    "PREVIEW",
    "CITATION_ANCHOR",
    "RELATED_SOURCES",
    "RELATED_CONCEPTS",
    "CAUSAL_NETWORK",
    "CONFLICT_SIGNALS",
    "EVIDENCE_GAPS",
    "MAINTENANCE_NOTES",
    "section_candidates",
    "canonical_section",
    "page_has_section",
    "upsert_page_section",
]
