"""Ask report artifact quality assessment (deliverable vs no-evidence)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aiwiki.utils.markdown import frontmatter_string_list, strip_frontmatter

_VAULT_EVIDENCE_PREFIXES = ("wiki/", "raw/", "schema/", "output/reports/")
_VAULT_CITE_RE = re.compile(
    r"(?:(?:\.\./)+)?"
    r"((?:wiki/(?:sources|judgments|elixirs|concepts)|raw|schema|output/reports)"
    r"/[^\s`\]\)\"'<>]+?\.md)"
)
_WIKILINK_CITE_RE = re.compile(r"\[\[((?:wiki|raw|schema|output)/[^\]|#]+)(?:\|[^\]]*)?\]\]")


def _wiki_vault_refs(frontmatter: dict[str, Any]) -> list[str]:
    refs = frontmatter_string_list(frontmatter, "used_refs")
    return [ref for ref in refs if ref.startswith(_VAULT_EVIDENCE_PREFIXES)]


def _web_refs(frontmatter: dict[str, Any]) -> list[str]:
    return [
        ref
        for ref in frontmatter_string_list(frontmatter, "used_web_refs")
        if ref.startswith(("https://", "http://"))
    ]


def extract_cited_vault_paths(markdown: str, *, root: Path | None = None) -> list[str]:
    """Return vault-relative cite paths that actually appear in the report body."""

    body = strip_frontmatter(markdown)
    refs: list[str] = []
    seen: set[str] = set()

    def _add(path: str) -> None:
        normalized = path.split("#", 1)[0].strip().strip("`")
        if not normalized.endswith(".md"):
            normalized = f"{normalized}.md"
        if not normalized or normalized in seen:
            return
        if root is not None and not (root / normalized).exists():
            return
        seen.add(normalized)
        refs.append(normalized)

    for match in _VAULT_CITE_RE.finditer(body):
        _add(match.group(1))
    for match in _WIKILINK_CITE_RE.finditer(body):
        _add(match.group(1))
    return refs


def filter_web_refs_in_body(markdown: str, web_refs: list[str]) -> list[str]:
    """Keep provider web_search URLs that the model actually wrote into the body."""

    body = strip_frontmatter(markdown)
    cited: list[str] = []
    seen: set[str] = set()
    for ref in web_refs:
        normalized = str(ref or "").strip()
        if not normalized or normalized in seen:
            continue
        if normalized in body or normalized.rstrip("/") in body:
            seen.add(normalized)
            cited.append(normalized)
    return cited


def assess_ask_artifact_quality(frontmatter: dict[str, Any], body: str) -> str:
    """Return ``deliverable`` when the report cites real evidence, else ``no-evidence``.

    ``used_refs`` / ``used_web_refs`` must already be the body-cited lists, not the
    recall/material candidate lists. Empty body is no-evidence even if refs exist.
    """

    if not strip_frontmatter(body).strip():
        return "no-evidence"
    has_evidence_refs = bool(_wiki_vault_refs(frontmatter) or _web_refs(frontmatter))
    if has_evidence_refs:
        return "deliverable"
    return "no-evidence"


__all__ = [
    "assess_ask_artifact_quality",
    "extract_cited_vault_paths",
    "filter_web_refs_in_body",
]
