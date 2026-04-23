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


def _save_machine_memory_action_records(root: Path, actions: list[dict[str, Any]]) -> None:
    save_machine_memory_action_state(root, {"version": 1, "actions": actions})


# EP-018B group 5 (B5): ``_load_concept_rewrite_proposals``,
# ``_find_concept_rewrite_proposal``, ``_save_concept_rewrite_proposals``,
# ``_evaluate_concept_rewrite_verification``,
# ``_persist_concept_rewrite_verification``, ``review_concept_rewrite``,
# ``apply_concept_rewrite``, ``verify_concept_rewrite``, and
# ``revert_concept_rewrite`` moved to ``aiwiki.execution.concept_rewrite``.
# Access the compat seam via ``aiwiki.app_compile.<name>`` — the
# ``_LAZY_OWNERS`` / ``__getattr__`` pair resolves them on first use.

# EP-018B group 3 (B3): ``refresh_knowledge_lifecycle_runtime``,
# ``retire_concept`` and ``reactivate_concept`` moved to
# ``aiwiki.execution.lifecycle``. The ``_LAZY_OWNERS`` table below
# still resolves ``aiwiki.app_compile.<name>`` lazily for backward
# compatibility (see EP-018A/B1/B2 for the mechanism).


def resolve_machine_memory_action_query(
    actions: list[dict[str, Any]],
    action_query: str,
) -> dict[str, Any]:
    normalized_query = action_query.strip()
    if not normalized_query:
        raise ValueError("Action id cannot be empty.")
    lowered_query = normalized_query.lower()

    def _match_stage(
        predicate: Any,
        *,
        skip_exact_id: bool = False,
        skip_exact_title: bool = False,
    ) -> dict[str, Any] | None:
        matches: list[dict[str, Any]] = []
        for action in actions:
            action_id = str(action.get("id") or "")
            action_title = str(action.get("title") or "").strip()
            lowered_id = action_id.lower()
            lowered_title = action_title.lower()
            if skip_exact_id and lowered_id == lowered_query:
                continue
            if skip_exact_title and lowered_title == lowered_query:
                continue
            if predicate(lowered_id, lowered_title):
                matches.append(action)
        if len(matches) == 1:
            return matches[0]
        if matches:
            candidates = ", ".join(
                f"{str(action.get('id') or '')} ({str(action.get('title') or '')})"
                for action in matches[:5]
            )
            raise RuntimeError(f"Machine-memory action is ambiguous: {action_query}. Candidates: {candidates}")
        return None

    exact_id_match = _match_stage(lambda lowered_id, lowered_title: lowered_id == lowered_query)
    if exact_id_match is not None:
        return exact_id_match
    exact_title_match = _match_stage(lambda lowered_id, lowered_title: lowered_title == lowered_query)
    if exact_title_match is not None:
        return exact_title_match
    prefix_match = _match_stage(
        lambda lowered_id, lowered_title: lowered_id.startswith(lowered_query) or lowered_title.startswith(lowered_query),
        skip_exact_title=True,
    )
    if prefix_match is not None:
        return prefix_match
    partial_match = _match_stage(
        lambda lowered_id, lowered_title: lowered_query in lowered_id or lowered_query in lowered_title,
        skip_exact_id=True,
        skip_exact_title=True,
    )
    if partial_match is not None:
        return partial_match
    raise FileNotFoundError(f"Machine-memory action not found: {action_query}")


@runtime_write_operation
def review_machine_memory_action(
    root: Path,
    action_id: str,
    status: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    if status not in ACTION_STATUSES:
        raise ValueError(f"Unsupported machine-memory action status: {status}")
    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    target = resolve_machine_memory_action_query(actions, action_id)
    resolved_action_id = str(target.get("id") or action_id.strip())
    reviewed_at = utc_now()
    target["status"] = status
    target["reviewed_at"] = reviewed_at
    target["status_updated_at"] = reviewed_at
    target["review_note"] = note or ""
    target["pending_review"] = "true" if action_needs_review(status) else "false"
    if status in PENDING_ACTION_STATUSES:
        revisit_after, escalate_after = schedule_review_windows(
            "action",
            status,
            reviewed_at,
            protocol=str(target.get("protocol") or DEFAULT_PROTOCOL),
            root=root,
        )
    else:
        revisit_after, escalate_after = "", ""
    target["revisit_after"] = revisit_after
    target["escalate_after"] = escalate_after
    target.update(evaluate_page_aging(target))
    save_machine_memory_action_state(root, {"version": 1, "actions": actions})
    append_wiki_log(
        root,
        "action-review",
        str(target.get("title") or resolved_action_id),
        [
            f"action_id: `{resolved_action_id}`",
            f"status: `{status}`",
            f"primary: `{target.get('primary_path', '')}`",
            f"priority: `{target.get('priority', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": resolved_action_id,
        "status": status,
        "reviewed_at": reviewed_at,
        "active": bool(target.get("active", True)),
    }


@runtime_write_operation
def apply_machine_memory_action(
    root: Path,
    action_id: str,
    *,
    note: str | None = None,
    dry_run: bool = False,
    bundle_path: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    target = resolve_machine_memory_action_query(actions, action_id)
    resolved_action_id = str(target.get("id") or action_id.strip())
    if str(target.get("status") or "") != "accepted":
        raise RuntimeError("Machine-memory action must be accepted before apply.")
    kind = str(target.get("kind") or "")
    protocol = str(target.get("protocol") or load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    preview_proposals = repair_execution_proposals(root, [target], active_protocol=protocol)
    proposal = preview_proposals[0] if preview_proposals else {
        "action_id": resolved_action_id,
        "title": str(target.get("title") or resolved_action_id),
        "proposal_kind": "manual-repair",
        "risk": "low",
        "priority": str(target.get("priority") or "medium"),
        "protocol": protocol,
        "summary": str(target.get("reason") or ""),
        "target_paths": [
            path
            for path in (str(target.get("primary_path") or ""), str(target.get("secondary_path") or ""))
            if path
        ],
        "page_patch_plan": build_page_patch_plan(root, target, active_protocol=protocol),
        "safe_apply_preview": safe_apply_preview(root, target),
        "command_hint": str(target.get("command_hint") or ""),
        "bundle_path": relative_path(root, execution_bundle_path(root, resolved_action_id)),
        "proposal_path": relative_path(root, execution_proposal_path(root, resolved_action_id)),
    }
    preview = proposal.get("safe_apply_preview")
    if not isinstance(preview, dict):
        raise RuntimeError("Only accepted actions with a safe apply preview support semi-auto apply.")
    preview_apply_mode = str(preview.get("apply_mode") or "")
    if not preview_apply_mode:
        raise RuntimeError("Safe apply preview is missing an apply mode.")
    previewed_at = utc_now()
    bundle = build_execution_bundle(root, proposal, compiled_at=previewed_at)
    if dry_run:
        selected_bundle_path = root / str(
            proposal.get("bundle_path") or relative_path(root, execution_bundle_path(root, resolved_action_id))
        )
        write_execution_bundle_document(selected_bundle_path, bundle)
        dry_run_path = execution_dry_run_path(root, resolved_action_id)
        dry_run_payload = {
            "version": 1,
            "kind": "execution-dry-run",
            "generated_by": "aiwiki-apply-action",
            "generated_at": previewed_at,
            "operation": "apply",
            "action_id": resolved_action_id,
            "title": str(target.get("title") or resolved_action_id),
            "status": str(target.get("status") or "accepted"),
            "apply_mode": preview_apply_mode,
            "proposal_path": str(proposal.get("proposal_path") or ""),
            "bundle_path": relative_path(root, selected_bundle_path),
            "preview": proposal.get("safe_apply_preview"),
            "bundle": bundle,
        }
        write_execution_dry_run_document(dry_run_path, dry_run_payload)
        append_runtime_history(
            root,
            {
                "event_type": "action-dry-run",
                "occurred_at": previewed_at,
                "action_id": resolved_action_id,
                "protocol": protocol,
                "bundle_path": relative_path(root, selected_bundle_path),
                "preview_path": relative_path(root, dry_run_path),
                "note": note or "",
            },
        )
        append_wiki_log(
            root,
            "action-dry-run",
            str(target.get("title") or resolved_action_id),
            [
                f"action_id: `{resolved_action_id}`",
                f"apply_mode: `{preview_apply_mode}`",
                f"bundle: `{relative_path(root, selected_bundle_path)}`",
            ],
        )
        return {
            "id": resolved_action_id,
            "dry_run": True,
            "apply_mode": preview_apply_mode,
            "status": str(target.get("status") or "accepted"),
            "bundle_path": relative_path(root, selected_bundle_path),
            "dry_run_path": relative_path(root, dry_run_path),
            "proposal_path": proposal.get("proposal_path", ""),
            "preview": proposal.get("safe_apply_preview"),
            "bundle": bundle,
        }

    selected_bundle_path = (
        root / bundle_path.strip()
        if bundle_path and bundle_path.strip()
        else root / str(proposal.get("bundle_path") or "")
    )
    if not selected_bundle_path.exists():
        raise FileNotFoundError(
            f"Execution bundle not found: {relative_path(root, selected_bundle_path)}. Run compile or apply-action --dry-run first."
        )
    stored_bundle = load_execution_bundle(selected_bundle_path)
    if str(stored_bundle.get("action_id") or "") != resolved_action_id:
        raise RuntimeError("Execution bundle action_id does not match the requested action.")
    if str(stored_bundle.get("digest") or "") != execution_bundle_digest(stored_bundle):
        raise RuntimeError("Execution bundle digest is invalid; regenerate the bundle before apply.")
    if str(stored_bundle.get("digest") or "") != str(bundle.get("digest") or ""):
        raise RuntimeError("Execution bundle is stale; re-run compile or apply-action --dry-run before apply.")

    applied_at = utc_now()
    stored_preview = stored_bundle.get("safe_apply_preview")
    if not isinstance(stored_preview, dict):
        raise RuntimeError("Execution bundle is missing the safe apply preview.")
    apply_mode = str(stored_preview.get("apply_mode") or "")
    if apply_mode == "manual-link-state":
        source_id, concept_slug = validate_low_risk_action_targets(root, target)
        manual_state = load_manual_link_state(root)
        manual_links = [dict(item) for item in manual_state.get("source_to_concept", []) if isinstance(item, dict)]
        existing = next(
            (
                item
                for item in manual_links
                if str(item.get("source_id") or "") == source_id
                and str(item.get("concept_slug") or "") == concept_slug
                and bool(item.get("active", True))
            ),
            None,
        )
        if existing is None:
            manual_links.append(
                {
                    "source_id": source_id,
                    "concept_slug": concept_slug,
                    "active": True,
                    "created_at": applied_at,
                    "applied_at": applied_at,
                    "origin_action_id": resolved_action_id,
                    "note": note or "Applied accepted low-risk repair action.",
                }
            )
        else:
            existing["active"] = True
            existing["applied_at"] = applied_at
            existing["origin_action_id"] = resolved_action_id
            existing["note"] = note or str(existing.get("note") or "")
        save_manual_link_state(root, {"version": 1, "source_to_concept": manual_links})
    elif apply_mode == "citation-snapshot-refresh":
        page_path = str(stored_preview.get("page_path") or target.get("primary_path") or "")
        if not page_path:
            raise RuntimeError("Safe apply preview is missing the judgment page path.")
        page = root / page_path
        if not page.exists():
            raise FileNotFoundError(f"Judgment page not found: {page_path}")
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        body = strip_frontmatter(content).strip()
        frontmatter["citation_snapshots"] = [
            str(item)
            for item in stored_preview.get("updated_citation_snapshots", [])
            if isinstance(item, str) and item.strip()
        ]
        page.write_text(f"{render_frontmatter(frontmatter)}\n\n{body}\n", encoding="utf-8")
    elif apply_mode == "resolve-monitor":
        pass  # no state mutation needed; receipt + status change is the outcome
    else:
        raise RuntimeError(f"Unsupported apply mode: {apply_mode}")

    receipt = build_execution_receipt(root, target, applied_at=applied_at, note=note, proposal=proposal)
    receipt_path = execution_receipt_path(root, resolved_action_id)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)

    target["status"] = "resolved"
    target["reviewed_at"] = applied_at
    target["status_updated_at"] = applied_at
    target["review_note"] = note or "Semi-auto apply completed."
    target["pending_review"] = "false"
    target["revisit_after"] = ""
    target["escalate_after"] = ""
    target["aging_state"] = ""
    target["overdue_review"] = "false"
    target["escalation_candidate"] = "false"
    target["last_receipt_path"] = relative_path(root, receipt_path)
    _save_machine_memory_action_records(root, actions)
    append_wiki_log(
        root,
        "action-apply",
        str(target.get("title") or resolved_action_id),
        [
            f"action_id: `{resolved_action_id}`",
            f"kind: `{kind}`",
            f"apply_mode: `{apply_mode}`",
            f"primary: `{target.get('primary_path', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": resolved_action_id,
        "status": "resolved",
        "applied_at": applied_at,
        "apply_mode": apply_mode,
        "receipt_path": relative_path(root, receipt_path),
    }


@runtime_write_operation
def revert_machine_memory_action(
    root: Path,
    action_id: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    target = resolve_machine_memory_action_query(actions, action_id)
    resolved_action_id = str(target.get("id") or action_id.strip())
    receipt_relative = str(target.get("last_receipt_path") or "")
    if not receipt_relative:
        raise RuntimeError("Machine-memory action has no execution receipt to revert.")
    receipt_path = root / receipt_relative
    if not receipt_path.exists():
        raise FileNotFoundError(f"Execution receipt not found: {receipt_relative}")
    receipt = load_json_document(receipt_path)
    if not isinstance(receipt, dict) or str(receipt.get("kind") or "") != "execution-receipt":
        raise RuntimeError("Execution receipt is not valid.")
    if str(receipt.get("operation") or "") != "apply":
        raise RuntimeError("Only the latest apply receipt can be reverted.")
    if str(receipt.get("action_id") or "") != resolved_action_id:
        raise RuntimeError("Execution receipt action_id does not match the requested action.")
    preview = receipt.get("safe_apply_preview")
    if not isinstance(preview, dict):
        raise RuntimeError("Execution receipt is missing the safe apply preview.")
    reverted_at = utc_now()
    apply_mode = str(preview.get("apply_mode") or "")
    if apply_mode == "manual-link-state":
        manual_state = load_manual_link_state(root)
        manual_links = [dict(item) for item in manual_state.get("source_to_concept", []) if isinstance(item, dict)]
        active_entry: dict[str, Any] | None = None
        for item in manual_links:
            if str(item.get("origin_action_id") or "") != resolved_action_id:
                continue
            if bool(item.get("active", True)):
                active_entry = item
                break
        if active_entry is None:
            raise RuntimeError("No active safe-apply state exists for this action.")
        active_entry["active"] = False
        active_entry["reverted_at"] = reverted_at
        active_entry["revert_note"] = note or "Safe apply reverted."
        save_manual_link_state(root, {"version": 1, "source_to_concept": manual_links})
    elif apply_mode == "citation-snapshot-refresh":
        page_path = str(preview.get("page_path") or target.get("primary_path") or "")
        if not page_path:
            raise RuntimeError("Execution receipt is missing the judgment page path.")
        page = root / page_path
        if not page.exists():
            raise FileNotFoundError(f"Judgment page not found: {page_path}")
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        body = strip_frontmatter(content).strip()
        frontmatter["citation_snapshots"] = [
            str(item)
            for item in preview.get("previous_citation_snapshots", [])
            if isinstance(item, str) and item.strip()
        ]
        page.write_text(f"{render_frontmatter(frontmatter)}\n\n{body}\n", encoding="utf-8")
    elif apply_mode == "resolve-monitor":
        pass  # no state to revert; status change below handles it
    else:
        raise RuntimeError(f"Unsupported revert apply mode: {apply_mode}")

    protocol = str(target.get("protocol") or load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    reverted_target = {
        **dict(target),
        "protocol": protocol,
        "status": "proposed",
        "execution_policy": "triage",
        "execution_band": "review-first",
        "reviewed_at": reverted_at,
        "status_updated_at": reverted_at,
        "review_note": note or "Safe apply reverted.",
        "pending_review": "true",
        "last_receipt_path": relative_path(root, receipt_path),
        "command_hint": f'PYTHONPATH=src python3 -m aiwiki.cli --root . review-action {resolved_action_id} --status accepted --note "Resume reverted repair."',
        "next_step": "回滚后重新 review，确认是否要再次 accepted 再执行。",
    }
    preview_proposals = repair_execution_proposals(root, [reverted_target], active_protocol=protocol)
    proposal = preview_proposals[0] if preview_proposals else {
        "action_id": resolved_action_id,
        "title": str(reverted_target.get("title") or resolved_action_id),
        "proposal_kind": "manual-repair",
        "risk": "low",
        "priority": str(reverted_target.get("priority") or "medium"),
        "protocol": protocol,
        "status": "proposed",
        "execution_policy": "triage",
        "summary": str(reverted_target.get("reason") or ""),
        "target_paths": [
            path
            for path in (str(reverted_target.get("primary_path") or ""), str(reverted_target.get("secondary_path") or ""))
            if path
        ],
        "page_patch_plan": build_page_patch_plan(root, reverted_target, active_protocol=protocol),
        "safe_apply_preview": safe_apply_preview(root, reverted_target),
        "command_hint": str(reverted_target.get("command_hint") or ""),
        "bundle_path": relative_path(root, execution_bundle_path(root, resolved_action_id)),
        "proposal_path": relative_path(root, execution_proposal_path(root, resolved_action_id)),
    }
    revert_receipt = build_execution_receipt(
        root,
        reverted_target,
        applied_at=reverted_at,
        note=note,
        proposal=proposal,
        operation="revert",
        resulting_status="proposed",
    )
    receipt_path.write_text(json.dumps(revert_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, revert_receipt)

    target["status"] = str(reverted_target["status"])
    target["reviewed_at"] = str(reverted_target["reviewed_at"])
    target["status_updated_at"] = str(reverted_target["status_updated_at"])
    target["review_note"] = str(reverted_target["review_note"])
    target["pending_review"] = str(reverted_target["pending_review"])
    target["last_receipt_path"] = str(reverted_target["last_receipt_path"])
    revisit_after, escalate_after = schedule_review_windows(
        "action",
        "proposed",
        reverted_at,
        protocol=str(target.get("protocol") or DEFAULT_PROTOCOL),
        root=root,
    )
    target["revisit_after"] = revisit_after
    target["escalate_after"] = escalate_after
    target.update(evaluate_page_aging(target))
    _save_machine_memory_action_records(root, actions)
    append_wiki_log(
        root,
        "action-revert",
        str(target.get("title") or resolved_action_id),
        [
            f"action_id: `{resolved_action_id}`",
            f"receipt: `{relative_path(root, receipt_path)}`",
            f"primary: `{target.get('primary_path', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": resolved_action_id,
        "status": "proposed",
        "reverted_at": reverted_at,
        "receipt_path": relative_path(root, receipt_path),
    }


# EP-018B group 4 (B4): apply_material_archive and
# revert_material_archive moved to aiwiki.execution.archive.
# The _LAZY_OWNERS table below still resolves
# aiwiki.app_compile.<name> lazily for backward compatibility.


@runtime_write_operation
def review_page(
    root: Path,
    page: str,
    status: str,
    *,
    note: str | None = None,
    confidence: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    candidate = Path(page)
    target = candidate if candidate.is_absolute() else (root / candidate)
    target = target.resolve()
    if not target.is_file():
        raise FileNotFoundError(f"Review target not found: {page}")
    content = target.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    kind = str(frontmatter.get("kind") or "")
    if kind not in {"decision", "judgment"}:
        raise ValueError("Only decision or judgment pages can enter the review workflow.")
    valid_statuses = valid_curated_statuses(kind)
    if status not in valid_statuses:
        raise ValueError(f"Unsupported review status for {kind}: {status}")
    reviewed_at = utc_now()
    frontmatter["status"] = status
    frontmatter["reviewed_at"] = reviewed_at
    frontmatter["formed_at"] = str(frontmatter.get("formed_at") or frontmatter.get("last_compiled_at") or reviewed_at)
    frontmatter["last_reviewed"] = reviewed_at
    frontmatter.setdefault("counter_evidence", [])
    frontmatter.setdefault("invalidation_rule", "")
    frontmatter.setdefault("next_signals", [])
    if kind == "judgment" and confidence:
        frontmatter["confidence"] = confidence
    revisit_after, escalate_after = schedule_review_windows(
        kind,
        status,
        reviewed_at,
        protocol=str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
        root=root,
    )
    frontmatter["revisit_after"] = revisit_after
    frontmatter["escalate_after"] = escalate_after
    body = strip_frontmatter(content).strip()
    review_status_lines = [
        f"- Current status: `{status}`",
        f"- Reviewed at: `{reviewed_at}`",
    ]
    if confidence and kind == "judgment":
        review_status_lines.append(f"- Confidence: `{confidence}`")
    review_notes_lines = [
        f"- Outcome: `{status}`",
        f"- Reviewed at: `{reviewed_at}`",
    ]
    if note:
        review_notes_lines.append(f"- Note: {note}")
    else:
        review_notes_lines.append("- No additional review note recorded.")
    updated_body = upsert_markdown_section(body, "Review Status", "\n".join(review_status_lines))
    updated_body = upsert_markdown_section(updated_body, "Review Notes", "\n".join(review_notes_lines))
    updated_body = upsert_markdown_section(
        updated_body,
        "Aging",
        "\n".join(
            [
                f"- Revisit after: `{revisit_after or 'none'}`",
                f"- Escalate after: `{escalate_after or 'none'}`",
            ]
        ),
    )
    updated_body = append_review_history_entry(
        updated_body,
        reviewed_at=reviewed_at,
        status=status,
        note=note,
        confidence=confidence if kind == "judgment" else None,
    )
    citations = extract_provenance_paths(root, updated_body)
    frontmatter["citations"] = citations
    frontmatter["citation_snapshots"] = build_citation_snapshots(root, citations)
    citation_snapshot_state = analyze_citation_snapshots(root, citations, frontmatter)
    judgment_lifecycle_state, judgment_lifecycle_reason_codes = judgment_lifecycle_profile(
        {
            "kind": kind,
            "status": status,
            "reviewed_at": reviewed_at,
            "last_reviewed": reviewed_at,
            "overdue_review": "false",
            "escalation_candidate": "false",
            "citation_drift": "true" if citation_snapshot_state["has_drift"] else "false",
            "citation_snapshot_gap_count": str(
                len(citation_snapshot_state["missing"]) + len(citation_snapshot_state["stale"])
            ),
            "review_history_entries": str(len(review_history_entries(updated_body))),
        }
    )
    target.write_text(f"{render_frontmatter(frontmatter)}\n\n{updated_body.strip()}\n", encoding="utf-8")
    _entry_by_id, path_to_entry_id = entry_lookup_maps(load_manifest(root).get("entries", []))
    source_ids = entry_ids_from_paths(path_to_entry_id, citations)
    append_runtime_history(
        root,
        {
            "event_type": "review",
            "occurred_at": reviewed_at,
            "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
            "page_id": str(frontmatter.get("id") or target.stem),
            "page_path": relative_path(root, target),
            "page_kind": kind,
            "status": status,
            "judgment_lifecycle_state": judgment_lifecycle_state,
            "judgment_lifecycle_reason_codes": judgment_lifecycle_reason_codes,
            "source_ids": source_ids,
        },
    )
    append_wiki_log(
        root,
        "review",
        str(frontmatter.get("title") or target.stem),
        [
            f"kind: `{kind}`",
            f"status: `{status}`",
            f"path: `{relative_path(root, target)}`",
            f"confidence: `{frontmatter.get('confidence', '') or 'n/a'}`",
        ],
    )
    compile_wiki(root)
    return {
        "path": relative_path(root, target),
        "kind": kind,
        "status": status,
        "reviewed_at": reviewed_at,
        "confidence": str(frontmatter.get("confidence") or ""),
    }


def _build_batch_id(prefix: str, subjects: list[str]) -> str:
    first_subject = next((subject for subject in subjects if subject), "item")
    return f"{prefix}-{utc_now()}-{slugify(first_subject)}"


def _load_latest_action_apply_batch_receipt(root: Path, batch_id: str | None) -> dict[str, Any]:
    if batch_id:
        receipt = load_json_document(execution_batch_receipt_path(root, batch_id))
        if not isinstance(receipt, dict) or not receipt:
            raise FileNotFoundError(f"Batch receipt not found: {batch_id}")
        return receipt
    history = [event for event in load_runtime_history(root) if isinstance(event, dict)]
    reverted_batch_ids = {
        str(event.get("reverted_batch_id") or "")
        for event in history
        if str(event.get("event_type") or "") == "action-revert-batch" and str(event.get("reverted_batch_id") or "")
    }
    for event in reversed(history):
        if str(event.get("event_type") or "") != "action-apply-batch":
            continue
        candidate_batch_id = str(event.get("batch_id") or "")
        if not candidate_batch_id or candidate_batch_id in reverted_batch_ids:
            continue
        receipt_path = root / str(event.get("receipt_path") or "")
        receipt = load_json_document(receipt_path)
        if isinstance(receipt, dict):
            return receipt
    raise RuntimeError("No unreverted action apply batch found.")


@runtime_write_operation
def review_pages_batch(
    root: Path,
    pages: list[str],
    status: str,
    *,
    note: str | None = None,
    confidence: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    ordered_pages: list[str] = []
    seen_pages: set[str] = set()
    for page in pages:
        normalized = page.strip()
        if not normalized or normalized in seen_pages:
            continue
        seen_pages.add(normalized)
        ordered_pages.append(normalized)
    if not ordered_pages:
        raise ValueError("Batch review requires at least one page.")
    items = [
        review_page(root, page, status, note=note, confidence=confidence)
        for page in ordered_pages
    ]
    generated_at = utc_now()
    batch_id = _build_batch_id("review-page-batch", ordered_pages)
    receipt = build_execution_batch_receipt(
        root,
        batch_id=batch_id,
        operation="review-page-batch",
        generated_at=generated_at,
        items=items,
        note=note,
        revert_supported=False,
    )
    receipt_path = execution_batch_receipt_path(root, batch_id)
    write_execution_batch_receipt_document(receipt_path, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "page-review-batch",
            "occurred_at": generated_at,
            "batch_id": batch_id,
            "receipt_path": relative_path(root, receipt_path),
            "page_paths": [str(item.get("path") or "") for item in items],
            "status": status,
            "count": len(items),
        },
    )
    append_wiki_log(
        root,
        "review-batch",
        f"{len(items)} pages",
        [
            f"status: `{status}`",
            f"receipt: `{relative_path(root, receipt_path)}`",
            f"pages: `{', '.join(str(item.get('path') or '') for item in items[:4])}`",
        ],
    )
    return {
        "batch_id": batch_id,
        "operation": "review-page-batch",
        "status": status,
        "count": len(items),
        "receipt_path": relative_path(root, receipt_path),
        "items": items,
    }


@runtime_write_operation
def apply_machine_memory_actions_batch(
    root: Path,
    action_ids: list[str],
    *,
    note: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    ensure_layout(root)
    ordered_ids: list[str] = []
    seen_ids: set[str] = set()
    for action_id in action_ids:
        normalized = action_id.strip()
        if not normalized or normalized in seen_ids:
            continue
        seen_ids.add(normalized)
        ordered_ids.append(normalized)
    if not ordered_ids:
        raise ValueError("Batch apply requires at least one action.")
    state = load_machine_memory_action_state(root)
    actions = {
        str(action.get("id") or ""): action
        for action in state.get("actions", [])
        if isinstance(action, dict) and str(action.get("id") or "")
    }
    missing = [action_id for action_id in ordered_ids if action_id not in actions]
    if missing:
        raise FileNotFoundError(f"Machine-memory action not found: {missing[0]}")
    unsupported = [action_id for action_id in ordered_ids if not action_supports_low_risk_apply(actions[action_id])]
    if unsupported:
        raise RuntimeError(f"Machine-memory action is not ready for low-risk batch apply: {unsupported[0]}")
    items: list[dict[str, Any]] = []
    operation = "action-dry-run-batch" if dry_run else "action-apply-batch"
    for action_id in ordered_ids:
        preview = apply_machine_memory_action(root, action_id, note=note, dry_run=True)
        if dry_run:
            items.append(preview)
            continue
        applied = apply_machine_memory_action(
            root,
            action_id,
            note=note,
            bundle_path=str(preview.get("bundle_path") or ""),
        )
        items.append(applied)
    generated_at = utc_now()
    batch_id = _build_batch_id(operation, ordered_ids)
    receipt = build_execution_batch_receipt(
        root,
        batch_id=batch_id,
        operation=operation,
        generated_at=generated_at,
        items=items,
        note=note,
        revert_supported=not dry_run,
    )
    receipt_path = execution_batch_receipt_path(root, batch_id)
    write_execution_batch_receipt_document(receipt_path, receipt)
    append_runtime_history(
        root,
        {
            "event_type": operation,
            "occurred_at": generated_at,
            "batch_id": batch_id,
            "receipt_path": relative_path(root, receipt_path),
            "action_ids": ordered_ids,
            "count": len(items),
            "dry_run": dry_run,
        },
    )
    append_wiki_log(
        root,
        "action-batch",
        f"{len(items)} actions",
        [
            f"operation: `{operation}`",
            f"receipt: `{relative_path(root, receipt_path)}`",
            f"actions: `{', '.join(ordered_ids[:5])}`",
        ],
    )
    return {
        "batch_id": batch_id,
        "operation": operation,
        "dry_run": dry_run,
        "count": len(items),
        "receipt_path": relative_path(root, receipt_path),
        "items": items,
    }


@runtime_write_operation
def revert_machine_memory_action_batch(
    root: Path,
    *,
    batch_id: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    target_receipt = _load_latest_action_apply_batch_receipt(root, batch_id)
    if str(target_receipt.get("kind") or "") != "execution-batch-receipt":
        raise RuntimeError("Batch receipt is not valid.")
    if str(target_receipt.get("operation") or "") != "action-apply-batch":
        raise RuntimeError("Only action apply batches can be reverted.")
    target_batch_id = str(target_receipt.get("batch_id") or batch_id or "")
    action_ids = [
        str(item.get("id") or item.get("action_id") or "")
        for item in target_receipt.get("items", [])
        if isinstance(item, dict) and (item.get("id") or item.get("action_id"))
    ]
    if not action_ids:
        raise RuntimeError("Action apply batch receipt is empty.")
    items = [revert_machine_memory_action(root, action_id, note=note) for action_id in reversed(action_ids)]
    generated_at = utc_now()
    revert_batch_id = _build_batch_id("action-revert-batch", action_ids)
    receipt = build_execution_batch_receipt(
        root,
        batch_id=revert_batch_id,
        operation="action-revert-batch",
        generated_at=generated_at,
        items=items,
        note=note,
        revert_supported=False,
        reverted_batch_id=target_batch_id,
    )
    receipt_path = execution_batch_receipt_path(root, revert_batch_id)
    write_execution_batch_receipt_document(receipt_path, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "action-revert-batch",
            "occurred_at": generated_at,
            "batch_id": revert_batch_id,
            "reverted_batch_id": target_batch_id,
            "receipt_path": relative_path(root, receipt_path),
            "action_ids": action_ids,
            "count": len(items),
        },
    )
    append_wiki_log(
        root,
        "action-batch-revert",
        f"{len(items)} actions",
        [
            f"reverted_batch: `{target_batch_id}`",
            f"receipt: `{relative_path(root, receipt_path)}`",
            f"actions: `{', '.join(action_ids[:5])}`",
        ],
    )
    return {
        "batch_id": revert_batch_id,
        "operation": "action-revert-batch",
        "reverted_batch_id": target_batch_id,
        "count": len(items),
        "receipt_path": relative_path(root, receipt_path),
        "items": items,
    }


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
    # Machine-memory action (EP-018B group 6)
    "resolve_machine_memory_action_query": "aiwiki.app_compile",
    "review_machine_memory_action": "aiwiki.app_compile",
    "apply_machine_memory_action": "aiwiki.app_compile",
    "revert_machine_memory_action": "aiwiki.app_compile",
    "_save_machine_memory_action_records": "aiwiki.app_compile",
    # Archive (EP-018B group 4)
    "apply_material_archive": "aiwiki.execution.archive",
    "revert_material_archive": "aiwiki.execution.archive",
    # Review page & batch (EP-018B group 7)
    "review_page": "aiwiki.app_compile",
    "review_pages_batch": "aiwiki.app_compile",
    "apply_machine_memory_actions_batch": "aiwiki.app_compile",
    "revert_machine_memory_action_batch": "aiwiki.app_compile",
    "_build_batch_id": "aiwiki.app_compile",
    "_load_latest_action_apply_batch_receipt": "aiwiki.app_compile",
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
