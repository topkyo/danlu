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
    _validate_rewrite_candidate_markdown,
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
    preserved_section,
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
    rewrite_proposal_candidate_is_current,
    rewrite_proposal_is_apply_ready,
    rewrite_proposal_needs_review,
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
    concept_page_snapshot,
    concept_rewrite_proposal_digest,
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
    REWRITE_PROPOSAL_STATUSES,
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
    load_concept_rewrite_state,
    load_json_document,
    load_knowledge_lifecycle_state,
    load_machine_memory,
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
    rewrite_dry_run_path,
    save_compile_state,
    save_concept_rewrite_state,
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


@runtime_write_operation
def ask_question(
    root: Path,
    question: str,
    output_format: str,
    protocol: str | None = None,
    *,
    no_cache: bool = False,
) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    if wiki_requires_compile(root, entries):
        compile_wiki(root)
        manifest = load_manifest(root)
        entries = manifest["entries"]
    protocol_state = load_protocol_state(root)
    active_protocol = resolve_protocol(root, protocol)
    if active_protocol != protocol_state["active_protocol"]:
        protocol_state = {
            **protocol_state,
            "active_protocol": active_protocol,
        }
    blocked_source_ids = active_archived_material_ids(root)
    material_state = load_material_state(root)
    routing_state = load_material_routing_state(root)
    archive_candidates = load_archive_candidates_state(root)
    memory = load_machine_memory(root)
    machine_query = build_machine_memory_query(
        memory,
        question,
        root=root,
        protocol=active_protocol,
        material_state=material_state,
        routing_state=routing_state,
        archive_candidates=archive_candidates,
        no_cache=no_cache,
    )
    ranked_concepts = rank_concepts(
        root,
        question,
        boost_concept_slugs=set(machine_query["ranked_concept_slugs"]),
        protocol=active_protocol,
    )
    boosted_ids: set[str] = set(machine_query["ranked_source_ids"])
    for concept in ranked_concepts:
        for source_page in concept.get("source_pages", []):
            if isinstance(source_page, str) and source_page.startswith("wiki/sources/") and source_page.endswith(".md"):
                boosted_ids.add(Path(source_page).stem)
    ranked = rank_sources(root, entries, question, boost_source_ids=boosted_ids, protocol=active_protocol)
    created_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_seed = f"query-{stamp}-{slugify(question)[:48]}"

    if output_format == "report":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_report(root, question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    elif output_format == "decision-memo":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, f"{artifact_seed}-decision-memo")
        destination = directory / f"{artifact_id}.md"
        content = render_decision_memo_query(
            root,
            question,
            ranked,
            ranked_concepts,
            machine_query,
            protocol_state,
            created_at,
            artifact_id,
        )
    elif output_format == "sop":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, f"{artifact_seed}-sop")
        destination = directory / f"{artifact_id}.md"
        content = render_sop_query(
            root,
            question,
            ranked,
            ranked_concepts,
            machine_query,
            protocol_state,
            created_at,
            artifact_id,
        )
    elif output_format == "slides":
        directory = root / "output" / "slides"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_slides(root, question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    elif output_format == "figure":
        directory = root / "output" / "figures"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_figure_brief(root, question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    else:
        raise ValueError(f"Unsupported format: {output_format}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    artifact_ref = relative_path(root, destination)
    bridge_evidence_ids = active_corpus_bridge_evidence_ids(
        machine_query,
        [entry["id"] for entry in ranked],
        routing_state=routing_state,
        active_protocol=active_protocol,
        blocked_source_ids=blocked_source_ids,
    )
    active_corpus = upsert_active_corpus(
        root,
        protocol=active_protocol,
        question=question,
        source_ids=[entry["id"] for entry in ranked],
        concept_slugs=[concept["slug"] for concept in ranked_concepts],
        bridge_evidence_ids=bridge_evidence_ids,
        output_ref=artifact_ref,
        changed_at=created_at,
    )
    append_runtime_history(
        root,
        {
            "event_type": "query",
            "occurred_at": created_at,
            "protocol": active_protocol,
            "corpus_id": active_corpus["corpus_id"],
            "focus_kind": "question",
            "focus_ref": question,
            "question_hash": question_signature(question),
            "output_format": output_format,
            "output_ref": artifact_ref,
            "source_ids": [entry["id"] for entry in ranked],
            "concept_slugs": [concept["slug"] for concept in ranked_concepts],
            "bridge_evidence_ids": bridge_evidence_ids,
            "touched_component_ids": machine_query.get("touched_component_ids", []),
            "time_focus": str(machine_query.get("time_focus") or ""),
            "archive_recall_hint_ids": [
                str(item.get("entry_id") or "")
                for item in machine_query.get("archive_recall_hints", [])
                if isinstance(item, dict) and item.get("entry_id")
            ],
        },
    )
    route_telemetry = record_query_route_telemetry(
        root,
        question=question,
        machine_query=machine_query,
        protocol=active_protocol,
        occurred_at=created_at,
    )
    last_route_entry = route_telemetry.get("last_entry") if isinstance(route_telemetry, dict) else {}
    if isinstance(last_route_entry, dict):
        machine_query["route_telemetry"] = {
            key: value
            for key, value in last_route_entry.items()
            if key not in {"occurred_at", "question_preview"}
        }
    else:
        machine_query["route_telemetry"] = dict(machine_query.get("route_telemetry") or {})
    refresh_material_state(root, generated_at=created_at, active_protocol=active_protocol)
    refresh_knowledge_lifecycle_state(
        root,
        generated_at=created_at,
        entries=manifest["entries"],
        active_corpora_state=load_active_corpora_state(root),
        memory=memory,
    )
    write_shell_summary(root, build_shell_summary(root, generated_at=created_at))
    append_wiki_log(
        root,
        "query",
        question,
        [
            f"format: `{output_format}`",
            f"artifact: `{artifact_ref}`",
            f"ranked_sources: `{len(ranked)}`",
            f"ranked_concepts: `{len(ranked_concepts)}`",
            f"protocol: `{active_protocol}`",
            f"active_corpus: `{active_corpus['corpus_id']}`",
            f"machine_terms: `{len(machine_query['matched_terms'])}`",
            f"machine_hits: `{len(machine_query['ranked_source_ids'])}/{len(machine_query['ranked_concept_slugs'])}`",
            f"time_focus: `{str(machine_query.get('time_focus') or 'none')}`",
            f"protocol_shard_sources: `{len(machine_query.get('protocol_shard_source_ids', []))}`",
            f"time_shard_sources: `{len(machine_query.get('time_shard_source_ids', []))}`",
            f"archive_recall_hints: `{len(machine_query.get('archive_recall_hints', []))}`",
            f"bridge_concepts: `{len(machine_query['bridge_concept_slugs'])}`",
            f"query_routes: `{len(machine_query['query_routes'])}`",
            f"route_strategy: `{machine_query.get('selected_strategy', 'concept-first')}`",
        ],
    )
    return {
        "path": artifact_ref,
        "format": output_format,
        "protocol": active_protocol,
        "no_cache": no_cache,
        "active_corpus_id": active_corpus["corpus_id"],
        "ranked_sources": [entry["id"] for entry in ranked],
        "ranked_concepts": [concept["slug"] for concept in ranked_concepts],
        "machine_memory_query": machine_query,
        "index_pages": [
            "wiki/indexes/index.md",
            "wiki/indexes/sources.md",
            "wiki/indexes/concepts.md",
            "wiki/indexes/decisions.md",
            "wiki/indexes/judgments.md",
            "wiki/indexes/judgment-assets.md",
            "wiki/indexes/agent-workbench.md",
            "wiki/indexes/cognitive-history.md",
            "wiki/indexes/output-packs.md",
            "wiki/indexes/domain-pilots.md",
            "wiki/indexes/protocols.md",
            "wiki/indexes/review-queue.md",
            "wiki/indexes/review-center.md",
            "wiki/indexes/aging-report.md",
            "wiki/indexes/compile-status.md",
            "wiki/indexes/concept-quality.md",
            "wiki/indexes/machine-memory.md",
            "wiki/indexes/graph-view.md",
            "wiki/indexes/machine-memory-topology.md",
            "wiki/indexes/machine-memory-actions.md",
            "wiki/indexes/machine-memory-repair-plan.md",
            "wiki/indexes/graph-health.md",
            "wiki/indexes/drift-report.md",
            "wiki/indexes/repair-backlog.md",
            "wiki/indexes/log.md",
            "schema/index.md",
            "schema/protocols/index.md",
        ],
        "protocol_pages": protocol_paths(root, active_protocol),
    }


@runtime_write_operation
def file_back(
    root: Path,
    artifact: str,
    title: str | None = None,
    kind: str = "derived",
    protocol: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    candidate = Path(artifact)
    artifact_path = candidate if candidate.is_absolute() else (root / candidate)
    artifact_path = artifact_path.resolve()
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Artifact not found: {artifact}")
    if artifact_path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        raise ValueError("Only markdown or text artifacts can be filed back in the MVP.")
    if kind not in {"derived", "decision", "judgment"}:
        raise ValueError(f"Unsupported filed-back kind: {kind}")

    filed_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_ref = (
        relative_path(root, artifact_path) if artifact_path.is_relative_to(root) else str(artifact_path)
    )
    original = artifact_path.read_text(encoding="utf-8", errors="replace")
    original_frontmatter = parse_frontmatter(original)
    citations = extract_provenance_paths(root, original)
    citation_snapshots = build_citation_snapshots(root, citations)
    source_protocol = str(original_frontmatter.get("protocol") or "").strip()
    resolved_protocol = resolve_protocol(root, protocol or source_protocol or None)
    entry_seed = f"{kind}-{stamp}-{slugify(title or artifact_path.stem)[:48]}"
    directory = {
        "derived": root / "wiki" / "derived",
        "decision": root / "wiki" / "decisions",
        "judgment": root / "wiki" / "judgments",
    }[kind]
    entry_id = next_available_stem(directory, entry_seed)
    destination = directory / f"{entry_id}.md"
    revisit_after = ""
    escalate_after = ""
    if kind in {"decision", "judgment"}:
        revisit_after, escalate_after = schedule_review_windows(
            kind,
            default_curated_status(kind),
            filed_at,
            protocol=resolved_protocol,
            root=root,
        )
    frontmatter = render_frontmatter(
        {
            "id": entry_id,
            "kind": kind,
            "status": default_curated_status(kind),
            "title": title or artifact_path.stem,
            "protocol": resolved_protocol,
            "source_files": [artifact_ref],
            "citations": citations,
            "citation_snapshots": citation_snapshots,
            "generated_by": "aiwiki-file-back",
            "last_compiled_at": filed_at,
            "confidence": "medium",
            "counter_evidence": [],
            "invalidation_rule": "",
            "next_signals": [],
            "formed_at": filed_at,
            "last_reviewed": "",
            "reviewed_at": "",
            "revisit_after": revisit_after,
            "escalate_after": escalate_after,
        }
    )
    stripped = strip_frontmatter(original).strip()
    body_lines = curated_page_template(
        kind=kind,
        protocol=resolved_protocol,
        title=title or artifact_path.stem,
        artifact_ref=artifact_ref,
        filed_at=filed_at,
        revisit_after=revisit_after,
        escalate_after=escalate_after,
        supporting_body=stripped,
    )
    payload = "\n".join([frontmatter, "", *body_lines]).rstrip() + "\n"
    destination.write_text(payload, encoding="utf-8")
    append_wiki_log(
        root,
        "file-back",
        title or artifact_path.stem,
        [
            f"kind: `{kind}`",
            f"protocol: `{resolved_protocol}`",
            f"from: `{artifact_ref}`",
            f"destination: `{relative_path(root, destination)}`",
        ],
    )
    compile_wiki(root)
    return {"path": relative_path(root, destination), "protocol": resolved_protocol}


def _save_machine_memory_action_records(root: Path, actions: list[dict[str, Any]]) -> None:
    save_machine_memory_action_state(root, {"version": 1, "actions": actions})


def _load_concept_rewrite_proposals(root: Path) -> list[dict[str, Any]]:
    state = load_concept_rewrite_state(root)
    return [dict(proposal) for proposal in state.get("proposals", []) if isinstance(proposal, dict)]


def _find_concept_rewrite_proposal(proposals: list[dict[str, Any]], slug: str) -> dict[str, Any]:
    for proposal in proposals:
        if str(proposal.get("slug") or "") == slug:
            return proposal
    raise FileNotFoundError(f"Concept rewrite proposal not found: {slug}")


def _save_concept_rewrite_proposals(root: Path, proposals: list[dict[str, Any]]) -> None:
    save_concept_rewrite_state(root, {"version": 1, "proposals": proposals})


def _evaluate_concept_rewrite_verification(root: Path, proposal: dict[str, Any]) -> dict[str, Any]:
    slug = str(proposal.get("slug") or "")
    target_path = str(proposal.get("target_path") or f"wiki/concepts/{slug}.md")
    expected_source_signature = str(proposal.get("source_signature") or "")
    expected_source_pages = sorted(
        str(item)
        for item in proposal.get("source_pages", [])
        if isinstance(item, str) and item
    )
    candidate_summary = preserved_section(str(proposal.get("candidate_markdown") or ""), "Summary", "").strip()
    snapshot = concept_page_snapshot(root, slug)
    issues: list[str] = []
    if not snapshot.get("content"):
        issues.append("missing-concept-page")
    else:
        content = str(snapshot.get("content") or "")
        frontmatter = parse_frontmatter(content)
        if str(frontmatter.get("id") or "") != f"concept-{slug}":
            issues.append("concept-id-drift")
        if str(frontmatter.get("kind") or "") != "concept":
            issues.append("concept-kind-drift")
        if expected_source_signature and str(frontmatter.get("source_signature") or "") != expected_source_signature:
            issues.append("source-signature-drift")
        current_source_pages = sorted(
            str(item)
            for item in frontmatter.get("source_pages", [])
            if isinstance(item, str) and item
        )
        if current_source_pages != expected_source_pages:
            issues.append("source-pages-drift")
        current_summary = str(snapshot.get("summary") or "").strip()
        if candidate_summary and current_summary != candidate_summary:
            issues.append("summary-not-applied")

    memory = load_machine_memory(root)
    concept_node = next(
        (
            node
            for node in memory.get("concept_nodes", [])
            if isinstance(node, dict) and str(node.get("slug") or "") == slug
        ),
        None,
    )
    if concept_node is None:
        issues.append("missing-machine-memory-node")
    else:
        node_source_pages = sorted(
            str(item)
            for item in concept_node.get("source_pages", [])
            if isinstance(item, str) and item
        )
        if node_source_pages != expected_source_pages:
            issues.append("machine-memory-source-drift")
    quality_state = memory.get("health", {}).get("concept_quality", {})
    quality_record = next(
        (
            record
            for record in quality_state.get("all_concepts", [])
            if isinstance(record, dict) and str(record.get("slug") or "") == slug
        ),
        None,
    )
    if quality_record is None:
        issues.append("missing-quality-record")
    verification_status = "passed" if not issues else "failed"
    verification_summary = (
        "Concept page summary, source signature, machine memory node, and quality record all match the applied rewrite."
        if verification_status == "passed"
        else "Verification detected drift between the applied rewrite and current concept/runtime state."
    )
    return {
        "slug": slug,
        "target_path": target_path,
        "status": verification_status,
        "checked_at": utc_now(),
        "summary": verification_summary,
        "issues": issues,
        "quality_score": int(quality_record.get("quality_score", 0)) if isinstance(quality_record, dict) else 0,
        "quality_state": str(quality_record.get("quality_state") or "") if isinstance(quality_record, dict) else "",
    }


def _persist_concept_rewrite_verification(
    root: Path,
    slug: str,
    *,
    note: str | None = None,
    compile_after: bool,
) -> dict[str, Any]:
    ensure_layout(root)
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if str(target.get("status") or "") != "applied":
        raise RuntimeError("Concept rewrite proposal must be applied before verify.")
    verification = _evaluate_concept_rewrite_verification(root, target)
    target["verification_status"] = verification["status"]
    target["verification_checked_at"] = verification["checked_at"]
    target["verification_summary"] = verification["summary"]
    target["verification_issues"] = list(verification["issues"])
    _save_concept_rewrite_proposals(root, proposals)
    append_runtime_history(
        root,
        {
            "event_type": "rewrite-verify",
            "occurred_at": str(verification["checked_at"] or ""),
            "slug": slug,
            "target_path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            "status": str(verification["status"] or ""),
            "issues": list(verification["issues"]),
            "quality_score": int(verification.get("quality_score", 0) or 0),
            "quality_state": str(verification.get("quality_state") or ""),
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "rewrite-verify",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"target: `{target.get('target_path', '')}`",
            f"status: `{verification['status']}`",
            f"issues: `{', '.join(verification['issues']) or 'none'}`",
        ],
    )
    if compile_after:
        compile_wiki(root)
    return verification


@runtime_write_operation
def review_concept_rewrite(
    root: Path,
    slug: str,
    status: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    if status not in REWRITE_PROPOSAL_STATUSES:
        raise ValueError(f"Unsupported concept rewrite status: {status}")
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if status == "accepted" and not rewrite_proposal_candidate_is_current(root, target):
        raise RuntimeError("Concept rewrite proposal candidate is stale or invalid. Run run-compile again before accepting.")
    reviewed_at = utc_now()
    target["status"] = status
    target["reviewed_at"] = reviewed_at
    target["review_note"] = note or ""
    target["pending_review"] = "true" if rewrite_proposal_needs_review(status) else "false"
    target["apply_ready"] = rewrite_proposal_is_apply_ready(root, target)
    if status != "applied":
        target["applied_at"] = str(target.get("applied_at") or "")
    _save_concept_rewrite_proposals(root, proposals)
    append_runtime_history(
        root,
        {
            "event_type": "rewrite-review",
            "occurred_at": reviewed_at,
            "slug": slug,
            "target_path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            "status": status,
            "priority": str(target.get("priority") or ""),
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "rewrite-review",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"status: `{status}`",
            f"target: `{target.get('target_path', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "slug": slug,
        "status": status,
        "reviewed_at": reviewed_at,
        "apply_ready": bool(target.get("apply_ready", False)),
    }


@runtime_write_operation
def apply_concept_rewrite(
    root: Path,
    slug: str,
    *,
    note: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    ensure_layout(root)
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if str(target.get("status") or "") != "accepted":
        raise RuntimeError("Concept rewrite proposal must be accepted before apply.")
    candidate_markdown = str(target.get("candidate_markdown") or "")
    if not candidate_markdown:
        raise RuntimeError("Concept rewrite proposal has no candidate markdown to apply.")
    concept_path = root / str(target.get("target_path") or f"wiki/concepts/{slug}.md")
    if not concept_path.exists():
        raise FileNotFoundError(f"Concept page not found: {concept_path}")
    current_frontmatter = parse_frontmatter(concept_path.read_text(encoding="utf-8", errors="replace"))
    current_source_signature = str(current_frontmatter.get("source_signature") or "")
    expected_source_signature = str(target.get("source_signature") or "")
    if expected_source_signature and current_source_signature != expected_source_signature:
        raise RuntimeError("Concept page changed since this rewrite proposal was generated.")
    current_source_pages = current_frontmatter.get("source_pages", [])
    if not isinstance(current_source_pages, list):
        current_source_pages = []
    normalized_source_pages = [str(item) for item in current_source_pages if isinstance(item, str)]
    _validate_rewrite_candidate_markdown(
        candidate_markdown,
        slug,
        expected_source_signature,
        normalized_source_pages,
    )
    if dry_run:
        previewed_at = utc_now()
        current_markdown = concept_path.read_text(encoding="utf-8", errors="replace")
        dry_run_path = rewrite_dry_run_path(root, slug)
        payload = {
            "version": 1,
            "kind": "rewrite-dry-run",
            "generated_by": "aiwiki-apply-rewrite",
            "generated_at": previewed_at,
            "slug": slug,
            "title": str(target.get("title") or slug),
            "status": str(target.get("status") or "accepted"),
            "target_path": relative_path(root, concept_path),
            "proposal_path": str(target.get("proposal_path") or ""),
            "source_signature": expected_source_signature,
            "candidate_digest": concept_rewrite_proposal_digest(candidate_markdown),
            "current_digest": concept_rewrite_proposal_digest(current_markdown),
            "summary_before": preserved_section(current_markdown, "Summary", "").strip(),
            "summary_after": preserved_section(candidate_markdown, "Summary", "").strip(),
            "candidate_markdown": candidate_markdown,
        }
        write_execution_dry_run_document(dry_run_path, payload)
        append_runtime_history(
            root,
            {
                "event_type": "rewrite-dry-run",
                "occurred_at": previewed_at,
                "slug": slug,
                "target_path": relative_path(root, concept_path),
                "proposal_path": str(target.get("proposal_path") or ""),
                "status": "accepted",
                "note": note or "",
            },
        )
        append_wiki_log(
            root,
            "rewrite-dry-run",
            str(target.get("title") or slug),
            [
                f"slug: `{slug}`",
                f"target: `{relative_path(root, concept_path)}`",
                f"preview: `{relative_path(root, dry_run_path)}`",
            ],
        )
        return {
            "slug": slug,
            "status": str(target.get("status") or "accepted"),
            "dry_run": True,
            "dry_run_path": relative_path(root, dry_run_path),
            "path": relative_path(root, concept_path),
        }
    previous_snapshot = concept_page_snapshot(root, slug)
    concept_path.write_text(candidate_markdown.strip() + "\n", encoding="utf-8")
    applied_at = utc_now()
    target["status"] = "applied"
    target["applied_at"] = applied_at
    target["last_applied_at"] = applied_at
    target["reverted_at"] = ""
    target["revert_note"] = ""
    target["reviewed_at"] = applied_at
    target["review_note"] = note or "Applied accepted rewrite proposal."
    target["pending_review"] = "false"
    target["apply_ready"] = False
    target["previous_markdown"] = str(previous_snapshot.get("content") or "")
    target["previous_digest"] = concept_rewrite_proposal_digest(str(previous_snapshot.get("content") or ""))
    target["verification_status"] = "pending"
    target["verification_checked_at"] = ""
    target["verification_summary"] = ""
    target["verification_issues"] = []
    _save_concept_rewrite_proposals(root, proposals)
    append_wiki_log(
        root,
        "rewrite-apply",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"target: `{target.get('target_path', '')}`",
            f"proposal_path: `{target.get('proposal_path', '')}`",
        ],
    )
    compile_wiki(root)
    verification = _persist_concept_rewrite_verification(
        root,
        slug,
        note="Automatic verification after apply.",
        compile_after=False,
    )
    append_runtime_history(
        root,
        {
            "event_type": "rewrite-apply",
            "occurred_at": applied_at,
            "slug": slug,
            "target_path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            "proposal_path": str(target.get("proposal_path") or ""),
            "source_signature": expected_source_signature,
            "status": "applied",
            "verification_status": str(verification.get("status") or ""),
            "verification_issues": list(verification.get("issues", [])),
            "note": note or "",
        },
    )
    compile_wiki(root)
    return {
        "slug": slug,
        "status": "applied",
        "applied_at": applied_at,
        "path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
        "verification_status": str(verification.get("status") or ""),
    }


@runtime_write_operation
def verify_concept_rewrite(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    verification = _persist_concept_rewrite_verification(
        root,
        slug,
        note=note or "Manual verification requested.",
        compile_after=True,
    )
    return {
        "slug": slug,
        "status": str(verification.get("status") or ""),
        "checked_at": str(verification.get("checked_at") or ""),
        "issues": list(verification.get("issues", [])),
    }


@runtime_write_operation
def revert_concept_rewrite(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    proposals = _load_concept_rewrite_proposals(root)
    target = _find_concept_rewrite_proposal(proposals, slug)
    if str(target.get("status") or "") != "applied":
        raise RuntimeError("Concept rewrite proposal has not been applied.")
    previous_markdown = str(target.get("previous_markdown") or "")
    if not previous_markdown:
        raise RuntimeError("Concept rewrite proposal has no previous concept snapshot to restore.")
    candidate_summary = preserved_section(str(target.get("candidate_markdown") or ""), "Summary", "").strip()
    current_summary = concept_page_snapshot(root, slug).get("summary", "").strip()
    if candidate_summary and current_summary != candidate_summary:
        raise RuntimeError("Only the latest applied rewrite can be reverted.")
    concept_path = root / str(target.get("target_path") or f"wiki/concepts/{slug}.md")
    if not concept_path.exists():
        raise FileNotFoundError(f"Concept page not found: {concept_path}")
    concept_path.write_text(previous_markdown.strip() + "\n", encoding="utf-8")
    reverted_at = utc_now()
    target["status"] = "accepted"
    target["reviewed_at"] = reverted_at
    target["review_note"] = note or "Reverted applied rewrite proposal."
    target["pending_review"] = "true" if rewrite_proposal_needs_review("accepted") else "false"
    target["applied_at"] = ""
    target["reverted_at"] = reverted_at
    target["revert_note"] = note or "Reverted applied rewrite proposal."
    target["verification_status"] = ""
    target["verification_checked_at"] = ""
    target["verification_summary"] = ""
    target["verification_issues"] = []
    target["apply_ready"] = rewrite_proposal_is_apply_ready(root, target)
    _save_concept_rewrite_proposals(root, proposals)
    append_runtime_history(
        root,
        {
            "event_type": "rewrite-revert",
            "occurred_at": reverted_at,
            "slug": slug,
            "target_path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
            "status": "accepted",
            "last_applied_at": str(target.get("last_applied_at") or ""),
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "rewrite-revert",
        str(target.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"target: `{target.get('target_path', '')}`",
            "status: `accepted`",
        ],
    )
    compile_wiki(root)
    return {
        "slug": slug,
        "status": "accepted",
        "reverted_at": reverted_at,
        "path": str(target.get("target_path") or f"wiki/concepts/{slug}.md"),
    }


def refresh_knowledge_lifecycle_runtime(root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    manifest = sync_manifest_with_raw(root)
    return refresh_knowledge_lifecycle_state(
        root,
        generated_at=generated_at or utc_now(),
        entries=manifest["entries"],
        active_corpora_state=load_active_corpora_state(root),
        memory=load_machine_memory(root),
    )


@runtime_write_operation
def retire_concept(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    path = concept_page_path(root, slug)
    if not path.exists():
        raise FileNotFoundError(f"Concept page not found: {relative_path(root, path)}")
    lifecycle = refresh_knowledge_lifecycle_runtime(root)
    current_entry = concept_lifecycle_entry(lifecycle, slug)
    if not current_entry:
        raise RuntimeError(f"Concept lifecycle entry not found: {slug}")
    if current_entry.get("active_corpus_ids"):
        raise RuntimeError("Active-corpus concept cannot transition to retired.")
    if str(current_entry.get("lifecycle_state") or "") == "retired" and current_entry.get("override_active"):
        raise RuntimeError(f"Concept is already retired: {slug}")

    override_state = ensure_knowledge_lifecycle_override_state(root)
    override_entries = [dict(entry) for entry in override_state.get("entries", []) if isinstance(entry, dict)]
    retired_at = utc_now()
    path_ref = relative_path(root, path)
    page_id = str(current_entry.get("page_id") or f"concept-{slug}")
    for entry in override_entries:
        if (
            bool(entry.get("active"))
            and str(entry.get("kind") or "") == "concept"
            and str(entry.get("path") or "") == path_ref
        ):
            entry["active"] = False
            entry["cleared_at"] = retired_at
            entry["cleared_note"] = "Superseded by newer concept lifecycle override."
    override_entries.append(
        {
            "page_id": page_id,
            "slug": slug,
            "path": path_ref,
            "kind": "concept",
            "lifecycle_state": "retired",
            "active": True,
            "operation": "retire",
            "reason_codes": ["manual-retire"],
            "applied_at": retired_at,
            "updated_at": retired_at,
            "note": note or "Concept retired from the active knowledge plane.",
        }
    )
    save_knowledge_lifecycle_override_state(root, {"version": 1, "entries": override_entries})
    updated_lifecycle = refresh_knowledge_lifecycle_runtime(root, generated_at=retired_at)
    append_runtime_history(
        root,
        {
            "event_type": "knowledge-lifecycle-override",
            "occurred_at": retired_at,
            "operation": "retire",
            "kind": "concept",
            "page_id": page_id,
            "slug": slug,
            "path": path_ref,
            "lifecycle_state": "retired",
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "concept-retire",
        str(current_entry.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"path: `{path_ref}`",
            "lifecycle_state: `retired`",
            f"override_state: `{relative_path(root, knowledge_lifecycle_override_state_path(root))}`",
        ],
    )
    final_entry = concept_lifecycle_entry(updated_lifecycle, slug)
    return {
        "slug": slug,
        "path": path_ref,
        "status": str(final_entry.get("lifecycle_state") or "retired"),
        "override_path": relative_path(root, knowledge_lifecycle_override_state_path(root)),
        "knowledge_lifecycle_path": relative_path(root, knowledge_lifecycle_state_path(root)),
        "updated_at": retired_at,
    }


@runtime_write_operation
def reactivate_concept(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    path = concept_page_path(root, slug)
    if not path.exists():
        raise FileNotFoundError(f"Concept page not found: {relative_path(root, path)}")
    override_state = ensure_knowledge_lifecycle_override_state(root)
    override_entries = [dict(entry) for entry in override_state.get("entries", []) if isinstance(entry, dict)]
    path_ref = relative_path(root, path)
    target: dict[str, Any] | None = None
    for entry in override_entries:
        if (
            bool(entry.get("active"))
            and str(entry.get("kind") or "") == "concept"
            and str(entry.get("path") or "") == path_ref
            and str(entry.get("lifecycle_state") or "") == "retired"
        ):
            target = entry
            break
    if target is None:
        raise RuntimeError(f"No active retired concept override exists for slug: {slug}")
    reactivated_at = utc_now()
    target["active"] = False
    target["reactivated_at"] = reactivated_at
    target["reactivate_note"] = note or "Concept reactivated into heuristic lifecycle routing."
    target["updated_at"] = reactivated_at
    save_knowledge_lifecycle_override_state(root, {"version": 1, "entries": override_entries})
    updated_lifecycle = refresh_knowledge_lifecycle_runtime(root, generated_at=reactivated_at)
    final_entry = concept_lifecycle_entry(updated_lifecycle, slug)
    append_runtime_history(
        root,
        {
            "event_type": "knowledge-lifecycle-override",
            "occurred_at": reactivated_at,
            "operation": "reactivate",
            "kind": "concept",
            "page_id": str(target.get("page_id") or f"concept-{slug}"),
            "slug": slug,
            "path": path_ref,
            "lifecycle_state": str(final_entry.get("lifecycle_state") or ""),
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "concept-reactivate",
        str(final_entry.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"path: `{path_ref}`",
            f"lifecycle_state: `{str(final_entry.get('lifecycle_state') or 'unknown')}`",
            f"override_state: `{relative_path(root, knowledge_lifecycle_override_state_path(root))}`",
        ],
    )
    return {
        "slug": slug,
        "path": path_ref,
        "status": str(final_entry.get("lifecycle_state") or ""),
        "override_path": relative_path(root, knowledge_lifecycle_override_state_path(root)),
        "knowledge_lifecycle_path": relative_path(root, knowledge_lifecycle_state_path(root)),
        "updated_at": reactivated_at,
    }


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


@runtime_write_operation
def apply_material_archive(
    root: Path,
    entry_id: str,
    *,
    note: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    if (
        wiki_requires_compile(root, manifest["entries"])
        or not material_state_path(root).exists()
        or not archive_candidates_state_path(root).exists()
    ):
        compile_wiki(root)
        manifest = load_manifest(root)

    archive_candidates = load_archive_candidates_state(root)
    material_state = load_material_state(root)
    material_archive_state = load_material_archive_state(root)
    archived_entries = active_material_archive_entries(material_archive_state)
    if entry_id in archived_entries:
        raise RuntimeError(f"Material is already archived: {entry_id}")

    candidate = next(
        (
            item
            for item in archive_candidates.get("entries", [])
            if isinstance(item, dict) and str(item.get("entry_id") or "") == entry_id
        ),
        None,
    )
    if candidate is None:
        raise FileNotFoundError(f"Archive candidate not found: {entry_id}")
    if str(candidate.get("status") or "") != "ready":
        raise RuntimeError("Only ready archive candidates support apply.")
    if str(candidate.get("recommended_temperature") or "") != "archived":
        raise RuntimeError("Only archive candidates recommending `archived` support apply.")

    material_entry = next(
        (
            item
            for item in material_state.get("entries", [])
            if isinstance(item, dict) and str(item.get("entry_id") or "") == entry_id
        ),
        None,
    )
    if material_entry is None:
        raise FileNotFoundError(f"Material state entry not found: {entry_id}")
    if str(material_entry.get("temperature") or "") != "cold":
        raise RuntimeError("Only cold material can transition to archived.")
    if material_entry.get("active_corpus_ids"):
        raise RuntimeError("Active-corpus material cannot transition to archived.")

    manifest_entry = next(
        (
            item
            for item in manifest.get("entries", [])
            if isinstance(item, dict) and str(item.get("id") or "") == entry_id
        ),
        {},
    )
    title = str(manifest_entry.get("title") or entry_id)
    source_path = f"wiki/sources/{entry_id}.md"
    protocol = str(load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    applied_at = utc_now()
    bundle = build_material_archive_bundle(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=applied_at,
        operation="apply",
        current_temperature="cold",
        resulting_temperature="archived",
    )
    if dry_run:
        bundle_path = root / str(bundle.get("bundle_path") or relative_path(root, execution_bundle_path(root, material_archive_action_id(entry_id))))
        write_execution_bundle_document(bundle_path, bundle)
        dry_run_path = archive_dry_run_path(root, entry_id)
        dry_run_payload = {
            "version": 1,
            "kind": "archive-dry-run",
            "generated_by": "aiwiki-apply-archive",
            "generated_at": applied_at,
            "entry_id": entry_id,
            "title": title,
            "status": str(candidate.get("status") or ""),
            "protocol": protocol,
            "bundle_path": relative_path(root, bundle_path),
            "preview": bundle.get("safe_apply_preview"),
            "bundle": bundle,
        }
        write_execution_dry_run_document(dry_run_path, dry_run_payload)
        append_runtime_history(
            root,
            {
                "event_type": "archive-dry-run",
                "occurred_at": applied_at,
                "protocol": protocol,
                "source_ids": [entry_id],
                "bundle_path": relative_path(root, bundle_path),
                "preview_path": relative_path(root, dry_run_path),
                "note": note or "",
            },
        )
        append_wiki_log(
            root,
            "archive-dry-run",
            title,
            [
                f"entry_id: `{entry_id}`",
                f"source: `{source_path}`",
                f"bundle: `{relative_path(root, bundle_path)}`",
            ],
        )
        return {
            "id": entry_id,
            "status": str(candidate.get("status") or ""),
            "dry_run": True,
            "bundle_path": relative_path(root, bundle_path),
            "dry_run_path": relative_path(root, dry_run_path),
        }
    receipt = build_material_archive_receipt(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=applied_at,
        note=note,
        operation="apply",
        current_temperature="cold",
        resulting_temperature="archived",
    )
    receipt_path = execution_receipt_path(root, material_archive_action_id(entry_id))
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)

    archive_entries = [
        dict(item)
        for item in material_archive_state.get("entries", [])
        if isinstance(item, dict) and str(item.get("entry_id") or "") != entry_id
    ]
    archive_entries.append(
        {
            "entry_id": entry_id,
            "title": title,
            "source_path": source_path,
            "active": True,
            "archived_at": applied_at,
            "reverted_at": "",
            "previous_temperature": "cold",
            "note": note or "",
            "recommended_temperature": "archived",
            "last_receipt_path": relative_path(root, receipt_path),
        }
    )
    save_material_archive_state(root, {"version": 1, "entries": archive_entries})
    append_runtime_history(
        root,
        {
            "event_type": "archive-apply",
            "occurred_at": applied_at,
            "protocol": protocol,
            "source_ids": [entry_id],
            "receipt_path": relative_path(root, receipt_path),
        },
    )
    append_wiki_log(
        root,
        "archive-apply",
        title,
        [
            f"entry_id: `{entry_id}`",
            f"source: `{source_path}`",
            "temperature: `cold -> archived`",
            f"receipt: `{relative_path(root, receipt_path)}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": entry_id,
        "status": "archived",
        "applied_at": applied_at,
        "receipt_path": relative_path(root, receipt_path),
    }


@runtime_write_operation
def revert_material_archive(
    root: Path,
    entry_id: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    if wiki_requires_compile(root, manifest["entries"]) or not material_state_path(root).exists():
        compile_wiki(root)
        manifest = load_manifest(root)

    material_archive_state = load_material_archive_state(root)
    archive_entries = [dict(item) for item in material_archive_state.get("entries", []) if isinstance(item, dict)]
    target = next((item for item in archive_entries if str(item.get("entry_id") or "") == entry_id), None)
    if target is None or not bool(target.get("active", False)):
        raise RuntimeError(f"No active archived material exists for entry: {entry_id}")

    receipt_relative = str(target.get("last_receipt_path") or "")
    if not receipt_relative:
        raise RuntimeError("Archived material has no execution receipt to revert.")
    receipt_path = root / receipt_relative
    if not receipt_path.exists():
        raise FileNotFoundError(f"Execution receipt not found: {receipt_relative}")
    receipt = load_json_document(receipt_path)
    if not isinstance(receipt, dict) or str(receipt.get("kind") or "") != "execution-receipt":
        raise RuntimeError("Execution receipt is not valid.")
    if str(receipt.get("operation") or "") != "apply":
        raise RuntimeError("Only the latest apply archive receipt can be reverted.")
    if str(receipt.get("subject_id") or "") != entry_id:
        raise RuntimeError("Execution receipt subject_id does not match the requested entry.")

    manifest_entry = next(
        (
            item
            for item in manifest.get("entries", [])
            if isinstance(item, dict) and str(item.get("id") or "") == entry_id
        ),
        {},
    )
    title = str(manifest_entry.get("title") or target.get("title") or entry_id)
    source_path = str(target.get("source_path") or f"wiki/sources/{entry_id}.md")
    protocol = str(load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    reverted_at = utc_now()
    revert_receipt = build_material_archive_receipt(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=reverted_at,
        note=note,
        operation="revert",
        current_temperature="archived",
        resulting_temperature="cold",
    )
    receipt_path.write_text(json.dumps(revert_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, revert_receipt)

    target["active"] = False
    target["reverted_at"] = reverted_at
    target["revert_note"] = note or "Material archive reverted."
    target["last_receipt_path"] = relative_path(root, receipt_path)
    save_material_archive_state(root, {"version": 1, "entries": archive_entries})
    append_runtime_history(
        root,
        {
            "event_type": "archive-revert",
            "occurred_at": reverted_at,
            "protocol": protocol,
            "source_ids": [entry_id],
            "receipt_path": relative_path(root, receipt_path),
        },
    )
    append_wiki_log(
        root,
        "archive-revert",
        title,
        [
            f"entry_id: `{entry_id}`",
            f"source: `{source_path}`",
            "temperature: `archived -> cold`",
            f"receipt: `{relative_path(root, receipt_path)}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": entry_id,
        "status": "cold",
        "reverted_at": reverted_at,
        "receipt_path": relative_path(root, receipt_path),
    }


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


def nightly_health(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    compile_result = compile_wiki(root)
    promotion_result = promote_recurring_outputs(root)
    if promotion_result["count"]:
        compile_result = compile_wiki(root)
    lint_result = lint_wiki(root)

    # Auto-consume accepted low-risk actions (planner auto-consumption)
    auto_applied: list[dict[str, Any]] = []
    try:
        action_state = load_machine_memory_action_state(root)
        accepted_ids = [
            str(a.get("id") or "")
            for a in action_state.get("actions", [])
            if isinstance(a, dict)
            and str(a.get("status") or "") == "accepted"
            and bool(a.get("active", True))
            and (
                str(a.get("kind") or "") in LOW_RISK_APPLYABLE_ACTION_KINDS
                or str(a.get("kind") or "") in RESOLVABLE_MONITOR_ACTION_KINDS
            )
        ]
        for aid in accepted_ids:
            try:
                dry = apply_machine_memory_action(root, aid, note="nightly auto-consume", dry_run=True)
                result = apply_machine_memory_action(
                    root, aid, note="nightly auto-consume",
                    bundle_path=str(dry.get("bundle_path") or ""),
                )
                auto_applied.append(result)
            except Exception:
                pass  # skip individual failures; don't block nightly
        if auto_applied:
            compile_result = compile_wiki(root)
    except Exception:
        pass  # don't let auto-consumption errors block nightly

    state = write_nightly_health(
        root,
        compile_result,
        lint_result,
        promotion_result=promotion_result,
        semantic_report="",
        llm_used=False,
    )
    return {
        "compile": compile_result,
        "lint": lint_result,
        "promotions": promotion_result,
        "aging": state["aging"],
        "repair_backlog": state["repair_backlog"]["path"],
        "auto_applied": auto_applied,
        "state_path": relative_path(root, nightly_health_state_path(root)),
    }


@runtime_write_operation
def shell_status(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    summary = build_shell_summary(root)
    return write_shell_summary(root, summary)

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
