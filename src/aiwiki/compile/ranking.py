"""Ranking state and concept ranking helpers.

Migrated out of ``aiwiki.app_compile`` to break the reverse dependency from
``aiwiki.compile.runtime_step`` and ``aiwiki.app_queries`` back to
``aiwiki.app_compile``. These functions own the ranking build-state lifecycle
(source/concept record reuse, input signatures) plus the concept ranking used
by the ask execution surface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..app_protocol import concept_focus_score
from ..content.concepts import concept_source_pages, entry_concept_terms
from ..content.io import active_manual_source_concept_links, source_summary_or_preview
from ..lifecycle.knowledge import load_knowledge_lifecycle_state
from ..state.constants import DEFAULT_PROTOCOL
from ..utils.hash import sha256_bytes
from ..utils.markdown import parse_frontmatter, read_text_preview, strip_frontmatter
from ..utils.path import relative_path
from ..utils.text import tokenize
from .build import load_ranking_build_state


def ranking_source_record_is_reusable(record: dict[str, Any]) -> bool:
    return (
        isinstance(record, dict)
        and isinstance(record.get("summary_or_preview"), str)
        and isinstance(record.get("concept_terms"), list)
    )


def ranking_concept_record_is_reusable(record: dict[str, Any]) -> bool:
    return (
        isinstance(record, dict)
        and isinstance(record.get("title"), str)
        and isinstance(record.get("path"), str)
        and isinstance(record.get("source_pages"), list)
        and isinstance(record.get("content"), str)
    )


def ranking_source_summary_or_preview(root: Path, entry: dict[str, Any]) -> str:
    source_file = root / str(entry.get("stored_path") or "")
    preview = read_text_preview(source_file, limit_lines=8) if source_file.exists() else ""
    return source_summary_or_preview(root, entry, preview)


def ranking_source_input_signature(
    entry: dict[str, Any],
    summary_or_preview: str,
    manual_slugs: list[str] | None = None,
) -> str:
    payload = {
        "entry_id": str(entry.get("id") or ""),
        "title": str(entry.get("title") or ""),
        "source_type": str(entry.get("source_type") or ""),
        "kind": str(entry.get("kind") or ""),
        "stored_path": str(entry.get("stored_path") or ""),
        "sha256": str(entry.get("sha256") or ""),
        "summary_or_preview": summary_or_preview,
        "manual_slugs": sorted(str(slug) for slug in (manual_slugs or []) if str(slug)),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def ranking_source_concept_terms(
    entry: dict[str, Any],
    summary_or_preview: str,
    *,
    manual_slugs: list[str] | None = None,
) -> list[str]:
    terms = entry_concept_terms(entry, summary_or_preview, max_terms=4)
    for manual_slug in sorted(str(slug) for slug in (manual_slugs or []) if str(slug)):
        manual_label = manual_slug.replace("-", " ")
        if manual_label not in terms:
            terms.append(manual_label)
    return terms


def build_ranking_source_record(
    entry: dict[str, Any],
    summary_or_preview: str,
    *,
    input_signature: str = "",
    manual_slugs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "input_signature": input_signature or ranking_source_input_signature(entry, summary_or_preview, manual_slugs),
        "summary_or_preview": summary_or_preview,
        "concept_terms": ranking_source_concept_terms(
            entry,
            summary_or_preview,
            manual_slugs=manual_slugs,
        ),
    }


def ranking_concept_input_signature(record: dict[str, Any]) -> str:
    payload = {
        "slug": str(record.get("slug") or ""),
        "title": str(record.get("title") or ""),
        "source_signature": str(record.get("source_signature") or ""),
        "render_signature": str(record.get("render_signature") or ""),
        "source_pages": concept_source_pages(record),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def build_ranking_concept_record(
    root: Path,
    path: Path,
    *,
    input_signature: str = "",
    fallback_title: str = "",
    fallback_source_pages: list[str] | None = None,
) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    source_pages = frontmatter.get("source_pages", fallback_source_pages or [])
    if not isinstance(source_pages, list):
        source_pages = fallback_source_pages or []
    return {
        "input_signature": input_signature,
        "title": str(frontmatter.get("title") or fallback_title or path.stem),
        "path": relative_path(root, path),
        "source_pages": [str(source_page) for source_page in source_pages if str(source_page)],
        "content": strip_frontmatter(content),
    }


def build_ranking_state(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    previous_state = load_ranking_build_state(root)
    previous_source_records = previous_state.get("source_records", {})
    previous_concept_records = previous_state.get("concept_records", {})
    if not isinstance(previous_source_records, dict):
        previous_source_records = {}
    if not isinstance(previous_concept_records, dict):
        previous_concept_records = {}

    source_records: dict[str, dict[str, Any]] = {}
    dirty_source_ids: list[str] = []
    clean_source_ids: list[str] = []
    manual_links = active_manual_source_concept_links(root)
    for entry in entries:
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            continue
        summary_or_preview = ranking_source_summary_or_preview(root, entry)
        manual_slugs = sorted(manual_links.get(entry_id, set()))
        input_signature = ranking_source_input_signature(entry, summary_or_preview, manual_slugs)
        previous_record = previous_source_records.get(entry_id, {})
        if (
            ranking_source_record_is_reusable(previous_record)
            and str(previous_record.get("input_signature") or "") == input_signature
        ):
            source_records[entry_id] = {
                "input_signature": input_signature,
                "summary_or_preview": str(previous_record.get("summary_or_preview") or ""),
                "concept_terms": [str(term) for term in previous_record.get("concept_terms", []) if str(term)],
            }
            clean_source_ids.append(entry_id)
        else:
            source_records[entry_id] = build_ranking_source_record(
                entry,
                summary_or_preview,
                input_signature=input_signature,
                manual_slugs=manual_slugs,
            )
            dirty_source_ids.append(entry_id)

    concept_records: dict[str, dict[str, Any]] = {}
    dirty_concept_slugs: list[str] = []
    clean_concept_slugs: list[str] = []
    for record in concepts:
        slug = str(record.get("slug") or "")
        if not slug:
            continue
        input_signature = ranking_concept_input_signature(record)
        previous_record = previous_concept_records.get(slug, {})
        if (
            ranking_concept_record_is_reusable(previous_record)
            and str(previous_record.get("input_signature") or "") == input_signature
        ):
            concept_records[slug] = {
                "input_signature": input_signature,
                "title": str(previous_record.get("title") or slug),
                "path": str(previous_record.get("path") or f"wiki/concepts/{slug}.md"),
                "source_pages": [str(path) for path in previous_record.get("source_pages", []) if str(path)],
                "content": str(previous_record.get("content") or ""),
            }
            clean_concept_slugs.append(slug)
        else:
            concept_records[slug] = build_ranking_concept_record(
                root,
                root / "wiki" / "concepts" / f"{slug}.md",
                input_signature=input_signature,
                fallback_title=str(record.get("title") or slug),
                fallback_source_pages=concept_source_pages(record),
            )
            dirty_concept_slugs.append(slug)

    removed_source_ids = sorted(set(previous_source_records) - set(source_records))
    removed_concept_slugs = sorted(set(previous_concept_records) - set(concept_records))
    return {
        "state_document": {
            "version": 1,
            "generated_at": generated_at,
            "source_records": source_records,
            "concept_records": concept_records,
        },
        "dirty_source_ids": dirty_source_ids,
        "clean_source_ids": clean_source_ids,
        "dirty_concept_slugs": dirty_concept_slugs,
        "clean_concept_slugs": clean_concept_slugs,
        "removed_source_ids": removed_source_ids,
        "removed_concept_slugs": removed_concept_slugs,
        "inputs_clean": not (dirty_source_ids or dirty_concept_slugs or removed_source_ids or removed_concept_slugs),
    }


def rank_concepts(
    root: Path,
    question: str,
    boost_concept_slugs: set[str] | None = None,
    *,
    protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    boost_concept_slugs = boost_concept_slugs or set()
    ranked: list[tuple[int, dict[str, Any]]] = []
    ranking_state = load_ranking_build_state(root)
    concept_records = ranking_state.get("concept_records", {})
    if not isinstance(concept_records, dict):
        concept_records = {}
    lifecycle = load_knowledge_lifecycle_state(root)
    retired_paths = {
        str(entry.get("path") or "")
        for entry in lifecycle.get("entries", [])
        if isinstance(entry, dict)
        and str(entry.get("kind") or "") == "concept"
        and str(entry.get("lifecycle_state") or "") == "retired"
    }
    for path in sorted((root / "wiki" / "concepts").glob("*.md")):
        if relative_path(root, path) in retired_paths:
            continue
        record = concept_records.get(path.stem, {})
        if not ranking_concept_record_is_reusable(record):
            record = build_ranking_concept_record(root, path)
        title = str(record.get("title") or path.stem)
        content = str(record.get("content") or "")
        source_pages = record.get("source_pages", [])
        if not isinstance(source_pages, list):
            source_pages = []
        haystack = f"{title}\n{content}".lower()
        score = 0
        for token in question_tokens:
            score += haystack.count(token)
        score += concept_focus_score(protocol, title, content)
        if path.stem in boost_concept_slugs:
            score += 5
        if score:
            ranked.append(
                (
                    score,
                    {
                        "slug": path.stem,
                        "title": title,
                        "path": str(record.get("path") or relative_path(root, path)),
                        "source_pages": [str(source_page) for source_page in source_pages if str(source_page)],
                    },
                )
            )
    ranked.sort(key=lambda item: (-item[0], item[1]["title"].lower()))
    return [item for _score, item in ranked[:5]]


__all__ = [
    "build_ranking_concept_record",
    "build_ranking_source_record",
    "build_ranking_state",
    "rank_concepts",
    "ranking_concept_input_signature",
    "ranking_concept_record_is_reusable",
    "ranking_source_concept_terms",
    "ranking_source_input_signature",
    "ranking_source_record_is_reusable",
    "ranking_source_summary_or_preview",
]
