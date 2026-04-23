"""Top-level orchestration extracted from aiwiki.app."""

from __future__ import annotations

import fcntl
import functools
import hashlib
import html
import json
import os
import re
import shutil
import threading
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .app_content import (
    action_needs_review,
    action_supports_low_risk_apply,
    active_manual_source_concept_links,
    annotate_recurring_promotion,
    append_execution_policy_decisions,
    append_review_history_entry,
    append_wiki_log,
    build_concept_quality,
    build_concept_records,
    build_domain_pilots,
    build_domain_pilots_incremental,
    build_knowledge_lifecycle_document,
    build_machine_memory_repair_plan,
    build_output_packs,
    build_output_packs_incremental,
    build_page_patch_plan,
    classify_recurring_output_kind,
    collect_aging_signals,
    collect_curated_pages,
    collect_output_artifacts,
    collect_output_density_artifacts,
    collect_recent_output_artifacts,
    concept_render_signature,
    concept_source_pages,
    concept_summary_is_placeholder,
    curated_asset_section_snapshot,
    curated_page_template,
    curated_page_transition_profile,
    decision_memos_dir,
    default_curated_status,
    display_action_status,
    display_curated_status,
    display_knowledge_lifecycle_state,
    display_rewrite_proposal_status,
    domain_pilots_index_path,
    ensure_wiki_log,
    entry_concept_terms,
    entry_ids_from_paths,
    entry_lookup_maps,
    evaluate_page_aging,
    execution_bundle_path,
    execution_policy_decision_record,
    execution_proposal_path,
    execution_receipt_path,
    find_promoted_curated_page,
    frontmatter_string_list,
    judgment_lifecycle_profile,
    knowledge_lifecycle_governance_summary,
    load_execution_receipt_history,
    manifest_change_summary,
    pilot_scorecards_dir,
    placeholder_concept_slugs,
    recurring_promotion_needs_refresh,
    refresh_knowledge_lifecycle_state,
    remove_stale_generated_concept_pages,
    remove_stale_generated_execution_bundle_files,
    remove_stale_generated_execution_proposal_pages,
    remove_stale_generated_markdown_files,
    render_agent_pack,
    render_agent_workbench,
    render_aging_report,
    render_concept_page,
    render_concepts_index,
    render_curated_index,
    render_domain_pilots_index,
    render_knowledge_lifecycle_entry_summary,
    render_master_index,
    render_output_packs_index,
    render_review_queue,
    render_source_page_with_state,
    render_sources_index,
    repair_execution_proposals,
    review_history_entries,
    review_packs_dir,
    review_queue,
    routing_snapshot_for_protocol,
    safe_apply_preview,
    sop_drafts_dir,
    source_summary_or_preview,
    sync_manifest_with_raw,
    valid_curated_statuses,
    validate_low_risk_action_targets,
)
from .app_execution import (
    append_execution_receipt_history,
    build_execution_batch_receipt,
    build_execution_bundle,
    build_execution_receipt,
    build_material_archive_bundle,
    build_material_archive_receipt,
    execution_bundle_digest,
    load_execution_bundle,
    write_execution_batch_receipt_document,
    write_execution_bundle_document,
    write_execution_dry_run_document,
)
from .app_memory import (
    active_corpus_bridge_evidence_ids,
    append_machine_memory_history,
    attach_judgment_assets_to_machine_memory,
    build_execution_audit_snapshot,
    build_machine_memory,
    build_machine_memory_graph,
    build_machine_memory_health,
    build_machine_memory_query,
    build_material_state_documents,
    collect_execution_consistency_signals,
    concept_lifecycle_entry,
    concept_page_path,
    machine_memory_digest,
    machine_memory_snapshot_is_reusable,
    plan_machine_memory_build,
    question_signature,
    reconcile_active_corpora_state,
    reconcile_concept_rewrite_proposals,
    reconcile_machine_memory_actions,
    record_query_route_telemetry,
    refresh_material_state,
    render_concept_quality,
    render_concept_rewrite_index,
    render_concept_rewrite_proposal_page,
    render_drift_report,
    render_execution_proposal_page,
    render_graph_health,
    render_machine_memory_actions,
    render_machine_memory_index,
    render_machine_memory_repair_plan,
    render_machine_memory_topology,
    reuse_machine_memory_core,
    summarize_machine_memory_transition,
    upsert_active_corpus,
)
from .app_protocol import (
    ACTION_STATUSES,
    AGENT_PACK_LIBRARY,
    AUTO_PROMOTION_MIN_OCCURRENCES,
    CURATED_ASSET_SECTION_ORDER,
    DECISION_STATUSES,
    JUDGMENT_STATUSES,
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    PENDING_ACTION_STATUSES,
    PROTOCOL_LIBRARY,
    RESOLVABLE_MONITOR_ACTION_KINDS,
    concept_focus_score,
    ensure_layout,
    entry_focus_score,
    load_protocol_state,
    protocol_output_guidance,
    protocol_paths,
    protocol_runtime_schema_path,
    protocol_runtime_summary,
    protocol_state_path,
    protocol_title,
    resolve_protocol,
    schedule_review_windows,
)
from .app_shell import build_shell_summary, write_shell_summary
from .app_state import (
    DEFAULT_PROTOCOL,
    JUDGMENT_LIFECYCLE_STATES,
    KNOWLEDGE_LIFECYCLE_KINDS,
    KNOWLEDGE_LIFECYCLE_STATES,
    active_archived_material_ids,
    active_corpora_state_path,
    active_material_archive_entries,
    agent_pack_path,
    agent_workbench_path,
    aging_report_path,
    append_runtime_history,
    archive_candidates_state_path,
    archive_dry_run_path,
    cognitive_history_path,
    compile_state_path,
    concept_build_state_path,
    concept_quality_path,
    concept_rewrite_index_path,
    concept_rewrite_state_path,
    default_concept_build_state,
    default_domain_pilot_build_state,
    default_machine_memory_build_state,
    default_output_pack_build_state,
    default_ranking_build_state,
    domain_pilot_build_state_path,
    ensure_knowledge_lifecycle_override_state,
    execution_audit_html_path,
    execution_audit_path,
    execution_batch_receipt_path,
    execution_center_html_path,
    execution_center_path,
    execution_dry_run_path,
    execution_policy_log_path,
    furnace_center_html_path,
    graph_health_report_path,
    judgment_assets_path,
    knowledge_lifecycle_override_state_path,
    knowledge_lifecycle_state_path,
    load_active_corpora_state,
    load_archive_candidates_state,
    load_compile_state,
    load_json_document,
    load_knowledge_lifecycle_state,
    load_machine_memory_action_state,
    load_manifest,
    load_manual_link_state,
    load_material_archive_state,
    load_material_routing_state,
    load_material_state,
    load_ranking_build_state,
    load_runtime_history,
    machine_memory_action_state_path,
    machine_memory_actions_path,
    machine_memory_build_state_path,
    machine_memory_drift_report_path,
    machine_memory_graph_html_path,
    machine_memory_graph_path,
    machine_memory_history_path,
    machine_memory_repair_plan_path,
    machine_memory_state_path,
    machine_memory_topology_path,
    material_archive_action_id,
    material_routing_state_path,
    material_state_path,
    nightly_health_state_path,
    output_pack_build_state_path,
    output_packs_index_path,
    planner_state_path,
    product_shell_html_path,
    query_route_telemetry_path,
    ranking_build_state_path,
    repair_backlog_path,
    review_center_html_path,
    save_compile_state,
    save_knowledge_lifecycle_override_state,
    save_machine_memory_action_state,
    save_manual_link_state,
    save_material_archive_state,
    shell_summary_path,
)
from .app_surfaces import (
    render_cognitive_history,
    render_execution_audit,
    render_execution_audit_html,
    render_execution_center,
    render_execution_center_html,
    render_furnace_center,
    render_furnace_center_html,
    render_judgment_assets,
    render_machine_memory_graph_html,
    render_review_center_html,
)
from .app_utils import (
    analyze_citation_snapshots,
    build_citation_snapshots,
    compiled_source_sha,
    extract_provenance_paths,
    next_available_stem,
    parse_frontmatter,
    read_text_preview,
    relative_path,
    render_frontmatter,
    render_scalar,
    runtime_write_operation,
    sha256_bytes,
    slugify,
    strip_frontmatter,
    tokenize,
    upsert_markdown_section,
    utc_now,
    write_if_changed,
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from .compile import CompileContext, compile_wiki, start_compile_context
from .config import LLMConfig

_CompileContext = CompileContext
_start_compile_context = start_compile_context


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
        "inputs_clean": not (
            dirty_source_ids
            or dirty_concept_slugs
            or removed_source_ids
            or removed_concept_slugs
        ),
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


 # EP-018B group 2 (B2): ``ask_question`` and ``file_back`` moved to
 # ``aiwiki.execution.ask``. The compat seam at the bottom of this module
 # still resolves ``aiwiki.app_compile.ask_question`` / ``file_back`` lazily.


# EP-018B group 6 (B6): ``resolve_machine_memory_action_query``,
# ``review_machine_memory_action``, ``apply_machine_memory_action``,
# ``revert_machine_memory_action`` and ``_save_machine_memory_action_records``
# moved to ``aiwiki.execution.machine_memory_actions``. The ``_LAZY_OWNERS``
# table below still resolves ``aiwiki.app_compile.<name>`` lazily for
# backward compatibility.



# EP-018B group 4 (B4): apply_material_archive and
# revert_material_archive moved to aiwiki.execution.archive.
# The _LAZY_OWNERS table below still resolves
# aiwiki.app_compile.<name> lazily for backward compatibility.


# EP-018B group 7 (B7): ``review_page``, ``review_pages_batch``,
# ``apply_machine_memory_actions_batch``, ``revert_machine_memory_action_batch``,
# ``_build_batch_id``, and ``_load_latest_action_apply_batch_receipt`` moved
# to ``aiwiki.execution.review`` (``review_page`` only) and
# ``aiwiki.execution.machine_memory_batch`` (the other five). They remain
# importable from ``aiwiki.app_compile`` via the ``_LAZY_OWNERS`` / PEP 562
# compat seam below. With B7 landed, every execution entry point that used
# to live in ``app_compile`` has moved under ``aiwiki.execution.*``.




# EP-018B group 1 (B1): ``nightly_health`` and ``shell_status`` moved to
# ``aiwiki.execution.runtime_surfaces``. They remain importable from
# ``aiwiki.app_compile`` via the PEP 562 compat seam below.

from .app_compile_ops import (  # noqa: E402
    build_agent_packs,
    promote_recurring_outputs,
    render_protocols_dashboard,
    set_active_protocol,
)
from .app_linting import (  # noqa: E402
    Finding,
    lint_wiki,
    pending_source_summary_ids,
    render_repair_backlog,
    write_nightly_health,
)
from .app_queries import (  # noqa: E402
    concept_page_requires_compile,
    machine_memory_query_plan_lines,
    rank_sources,
    render_decision_memo_query,
    render_figure_brief,
    render_report,
    render_slides,
    render_sop_query,
    source_page_is_stale,
    source_page_requires_compile,
    wiki_requires_compile,
)

# ---------------------------------------------------------------------------
# EP-018A: execution owner lazy compat seam (PEP 562)
#
# Goal: expose a stable ``aiwiki.app_compile.<name>`` surface for all
# execution-layer helpers that EP-018B will migrate into the
# ``aiwiki.execution`` subpackage group-by-group. Today every execution name
# is still defined directly in this module, so each ``_LAZY_OWNERS`` entry
# self-references ``"aiwiki.app_compile"``. When EP-018B moves a function
# (e.g. ``ask_question``) to ``aiwiki.execution.ask``, the only code change
# required is to flip that one ``_LAZY_OWNERS`` entry — callers and tests
# keep importing from ``aiwiki.app_compile`` unchanged.
#
# Hot names that ``tests/test_app.py`` currently ``patch("aiwiki.app_compile.
# <name>")`` on (``utc_now``, ``entry_concept_terms``, ``build_machine_memory``,
# ``build_ranking_source_record``, ``build_ranking_concept_record``) are
# deliberately **not** listed here — they stay directly bound to this module's
# globals so ``unittest.mock.patch`` resolves them immediately, with no
# first-access / caching subtlety.
# ---------------------------------------------------------------------------

_LAZY_OWNERS: dict[str, str] = {
    # Ask / file-back (EP-018B group 2) — migrated to aiwiki.execution.ask
    "ask_question": "aiwiki.execution.ask",
    "file_back": "aiwiki.execution.ask",
    # Concept rewrite pipeline (EP-018B group 5) — migrated to aiwiki.execution.concept_rewrite
    "review_concept_rewrite": "aiwiki.execution.concept_rewrite",
    "apply_concept_rewrite": "aiwiki.execution.concept_rewrite",
    "verify_concept_rewrite": "aiwiki.execution.concept_rewrite",
    "revert_concept_rewrite": "aiwiki.execution.concept_rewrite",
    "_load_concept_rewrite_proposals": "aiwiki.execution.concept_rewrite",
    "_find_concept_rewrite_proposal": "aiwiki.execution.concept_rewrite",
    "_save_concept_rewrite_proposals": "aiwiki.execution.concept_rewrite",
    "_evaluate_concept_rewrite_verification": "aiwiki.execution.concept_rewrite",
    "_persist_concept_rewrite_verification": "aiwiki.execution.concept_rewrite",
    # Knowledge lifecycle (EP-018B group 3)
    "refresh_knowledge_lifecycle_runtime": "aiwiki.execution.lifecycle",
    "retire_concept": "aiwiki.execution.lifecycle",
    "reactivate_concept": "aiwiki.execution.lifecycle",
    # Machine-memory action (EP-018B group 6) — migrated to aiwiki.execution.machine_memory_actions
    "resolve_machine_memory_action_query": "aiwiki.execution.machine_memory_actions",
    "review_machine_memory_action": "aiwiki.execution.machine_memory_actions",
    "apply_machine_memory_action": "aiwiki.execution.machine_memory_actions",
    "revert_machine_memory_action": "aiwiki.execution.machine_memory_actions",
    "_save_machine_memory_action_records": "aiwiki.execution.machine_memory_actions",
    # Archive (EP-018B group 4)
    "apply_material_archive": "aiwiki.execution.archive",
    "revert_material_archive": "aiwiki.execution.archive",
    # Review page (EP-018B group 7) — migrated to aiwiki.execution.review
    "review_page": "aiwiki.execution.review",
    # Machine-memory batch (EP-018B group 7) — migrated to aiwiki.execution.machine_memory_batch
    "review_pages_batch": "aiwiki.execution.machine_memory_batch",
    "apply_machine_memory_actions_batch": "aiwiki.execution.machine_memory_batch",
    "revert_machine_memory_action_batch": "aiwiki.execution.machine_memory_batch",
    "_build_batch_id": "aiwiki.execution.machine_memory_batch",
    "_load_latest_action_apply_batch_receipt": "aiwiki.execution.machine_memory_batch",
    # Runtime surfaces (EP-018B group 1) — migrated to aiwiki.execution.runtime_surfaces
    "nightly_health": "aiwiki.execution.runtime_surfaces",
    "shell_status": "aiwiki.execution.runtime_surfaces",
}


# Note: intentionally no module-level ``__all__`` here. Defining one would
# replace the implicit ``*``-export surface (currently all public globals)
# and both drop existing public names (e.g. ``compile_wiki``, ``lint_wiki``)
# and expose private ``_LAZY_OWNERS`` helpers. EP-018A only needs attribute
# forwarding, not a star-import contract change.


def __getattr__(name: str) -> Any:
    owner_path = _LAZY_OWNERS.get(name)
    if owner_path is None:
        raise AttributeError(
            f"module 'aiwiki.app_compile' has no attribute {name!r}"
        )
    if owner_path == __name__:
        # Self-reference during EP-018A: the real definition lives in this
        # module. Python only calls __getattr__ when the name is NOT in
        # globals, so reaching this branch means the concrete binding is
        # missing — surface it rather than silently returning ``None``.
        if name not in globals():
            raise AttributeError(
                f"'aiwiki.app_compile.{name}' is registered in _LAZY_OWNERS "
                f"but has no concrete binding; owner migration may be incomplete"
            )
        return globals()[name]
    import importlib

    owner = importlib.import_module(owner_path)
    value = getattr(owner, name)
    globals()[name] = value  # cache for subsequent accesses
    return value
