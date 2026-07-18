"""Compile content step owner."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..content.concepts import (
    build_concept_records,
    concept_render_signature,
    concept_source_pages,
    render_concept_page,
    render_concepts_index,
    render_sources_index,
)
from ..content.io import render_source_page_with_state
from ..lifecycle.status import collect_curated_pages
from ..render.judgment_assets import render_judgment_assets
from ..render.paths import (
    append_wiki_log,
    ensure_wiki_log,
    judgment_assets_path,
    remove_stale_generated_concept_pages_detailed,
)
from ..render.views import (
    render_curated_index,
    render_master_index,
)
from ..utils.hash import compiled_source_sha
from ..utils.io import write_if_changed, write_json_document_if_changed_ignoring_generated_timestamps
from ..utils.markdown import parse_frontmatter, read_text_preview
from .build import default_concept_build_state
from .context import CompileContext
from .paths import concept_build_state_path

logger = logging.getLogger(__name__)


def source_page_is_stale(root: Path, entry: dict[str, Any]) -> bool:
    page = root / "wiki" / "sources" / f"{entry['id']}.md"
    if not page.exists():
        return True
    return compiled_source_sha(page.read_text(encoding="utf-8", errors="replace")) != entry["sha256"]


def source_page_requires_compile(root: Path, entry: dict[str, Any], concepts: list[str]) -> bool:
    page = root / "wiki" / "sources" / f"{entry['id']}.md"
    if not page.exists():
        return True
    content = page.read_text(encoding="utf-8", errors="replace")
    if compiled_source_sha(content) != entry["sha256"]:
        return True
    frontmatter = parse_frontmatter(content)
    if str(frontmatter.get("source_updated_at") or "") != str(
        entry.get("updated_at") or entry.get("imported_at") or ""
    ):
        return True
    existing_concepts = frontmatter.get("concepts", [])
    if not isinstance(existing_concepts, list):
        existing_concepts = []
    normalized_existing = [str(label) for label in existing_concepts if str(label)]
    normalized_target = [str(label) for label in concepts if str(label)]
    return normalized_existing != normalized_target


def concept_page_requires_compile(root: Path, record: dict[str, Any]) -> bool:
    page = root / "wiki" / "concepts" / f"{record['slug']}.md"
    if not page.exists():
        return True
    content = page.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    existing_source_pages = frontmatter.get("source_pages", [])
    if not isinstance(existing_source_pages, list):
        existing_source_pages = []
    normalized_existing = [str(path) for path in existing_source_pages if str(path)]
    normalized_target = concept_source_pages(record)
    if normalized_existing != normalized_target:
        return True
    if str(frontmatter.get("source_signature") or "") != record["source_signature"]:
        return True
    render_signature = str(record.get("render_signature") or concept_render_signature(root, record))
    return str(frontmatter.get("render_signature") or "") != render_signature


def wiki_requires_compile(root: Path, entries: list[dict[str, Any]]) -> bool:
    if not entries:
        return False
    if not (root / "wiki" / "indexes" / "index.md").exists():
        return True
    if not (root / "wiki" / "indexes" / "review-queue.md").exists():
        return True
    if any(source_page_is_stale(root, entry) for entry in entries):
        return True
    concept_dir = root / "wiki" / "concepts"
    return not any(concept_dir.glob("*.md"))


def compile_content_phase(context: CompileContext) -> None:
    for entry in context.entries:
        source_file = context.root / entry["stored_path"]
        context.previews[entry["id"]] = read_text_preview(source_file)
    context.concepts, context.entry_terms, concept_build = build_concept_records(
        context.root,
        context.entries,
        context.previews,
        generated_at=context.compiled_at,
    )
    context.dirty_concept_source_ids = list(concept_build.get("dirty_concept_source_ids", []))
    context.clean_concept_source_ids = list(concept_build.get("clean_concept_source_ids", []))
    concept_build_state = concept_build.get("state_document", {})
    if not isinstance(concept_build_state, dict):
        concept_build_state = default_concept_build_state()
    try:
        write_json_document_if_changed_ignoring_generated_timestamps(
            concept_build_state_path(context.root),
            concept_build_state,
        )
    except OSError as exc:
        logger.warning("cache concept build-state save failed: %s", exc)

    dirty_source_id_set: set[str] = set()
    for entry in context.entries:
        entry_id = str(entry["id"])
        if source_page_requires_compile(context.root, entry, context.entry_terms.get(entry_id, [])):
            context.dirty_source_ids.append(entry_id)
            dirty_source_id_set.add(entry_id)
        else:
            context.clean_source_ids.append(entry_id)
    for entry in context.entries:
        if entry["id"] not in dirty_source_id_set:
            continue
        destination = context.root / "wiki" / "sources" / f"{entry['id']}.md"
        existing_page = destination.read_text(encoding="utf-8", errors="replace") if destination.exists() else ""
        content = render_source_page_with_state(
            entry,
            context.previews[entry["id"]],
            context.compiled_at,
            concepts=context.entry_terms.get(entry["id"], []),
            existing_page=existing_page,
        )
        wrote = int(write_if_changed(destination, content))
        context.source_changed_pages += wrote
        context.changed_pages += wrote

    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "sources.md",
        render_sources_index(context.entries, context.compiled_at),
    )
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "concepts.md",
        render_concepts_index(context.concepts, context.compiled_at),
    )
    context.decision_pages = collect_curated_pages(context.root, "decisions", "decision")
    context.judgment_pages = collect_curated_pages(context.root, "judgments", "judgment")
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "decisions.md",
        render_curated_index("决策索引", "决策列表", context.decision_pages, context.compiled_at),
    )
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "judgments.md",
        render_curated_index("判断索引", "判断列表", context.judgment_pages, context.compiled_at),
    )
    context.write_index_artifact(
        judgment_assets_path(context.root),
        render_judgment_assets(
            context.root,
            context.decision_pages,
            context.judgment_pages,
            context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
        ),
    )
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "index.md",
        render_master_index(
            context.entries,
            context.concepts,
            context.decision_pages,
            context.judgment_pages,
            context.protocol_state,
            context.compiled_at,
        ),
    )
    ensure_wiki_log(context.root)

    concept_lookup = {record["slug"]: record for record in context.concepts}
    dirty_concept_slug_set: set[str] = set()
    for record in context.concepts:
        record["record_lookup"] = concept_lookup
        record["root"] = context.root
        record["render_signature"] = concept_render_signature(context.root, record)
        if concept_page_requires_compile(context.root, record):
            slug = str(record["slug"])
            context.dirty_concept_slugs.append(slug)
            dirty_concept_slug_set.add(slug)
        else:
            context.clean_concept_slugs.append(str(record["slug"]))
    for record in context.concepts:
        if str(record["slug"]) not in dirty_concept_slug_set:
            continue
        destination = context.root / "wiki" / "concepts" / f"{record['slug']}.md"
        existing_page = destination.read_text(encoding="utf-8", errors="replace") if destination.exists() else ""
        wrote = int(write_if_changed(destination, render_concept_page(record, context.compiled_at, existing_page)))
        context.changed_pages += wrote
        context.concept_changed_pages += wrote

    removed_count, removed_slugs = remove_stale_generated_concept_pages_detailed(
        context.root,
        {record["slug"] for record in context.concepts},
    )
    context.removed_pages += removed_count
    if removed_slugs:
        # F-new-13 (Round 6): when noise-floor / extraction signature changes invalidate
        # previously generated concept pages, log them so the prune is auditable.
        append_wiki_log(
            context.root,
            "concept-noise-pruned",
            f"compile pruned {len(removed_slugs)} stale concept page(s)",
            [
                f"slugs: {', '.join(removed_slugs)}",
                "reason: extraction signature mismatch (noise floor or input change)",
            ],
        )


__all__ = ["compile_content_phase"]
