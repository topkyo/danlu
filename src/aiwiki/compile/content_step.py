"""Compile content step owner."""

from __future__ import annotations

from ..app_content import (
    build_concept_records,
    collect_curated_pages,
    concept_render_signature,
    ensure_wiki_log,
    remove_stale_generated_concept_pages,
    render_concept_page,
    render_concepts_index,
    render_curated_index,
    render_master_index,
    render_source_page_with_state,
    render_sources_index,
)
from ..app_queries import concept_page_requires_compile, source_page_requires_compile
from ..app_state import concept_build_state_path, default_concept_build_state, judgment_assets_path
from ..app_surfaces import render_judgment_assets
from ..app_utils import (
    read_text_preview,
    write_if_changed,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from .context import CompileContext


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
    write_json_document_if_changed_ignoring_generated_timestamps(concept_build_state_path(context.root), concept_build_state)

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

    context.removed_pages += remove_stale_generated_concept_pages(
        context.root,
        {record["slug"] for record in context.concepts},
    )


__all__ = ["compile_content_phase"]
