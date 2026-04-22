"""Compile pipeline persist/finalize step."""

from __future__ import annotations

from typing import Any

from ..app_cache import sync_query_cache
from ..app_content import append_wiki_log, manifest_change_summary
from ..app_state import (
    active_corpora_state_path,
    archive_candidates_state_path,
    cache_status_path,
    compile_state_path,
    concept_build_state_path,
    domain_pilot_build_state_path,
    knowledge_lifecycle_override_state_path,
    knowledge_lifecycle_state_path,
    machine_memory_build_state_path,
    material_routing_state_path,
    material_state_path,
    output_pack_build_state_path,
    ranking_build_state_path,
    save_compile_state,
)
from ..app_surfaces import render_compile_status
from ..app_utils import relative_path, write_if_changed
from .context import CompileContext


def _build_compile_phase_summary(context: CompileContext) -> list[dict[str, Any]]:
    metadata_details = manifest_change_summary(context.previous_manifest.get("entries", []), context.entries)
    cache_details = dict(context.cache_status or {})
    cache_stats = dict(cache_details.get("stats", {}) or {})
    return [
        {
            "name": "metadata_refresh",
            "label": "metadata refresh",
            "mode": "full",
            "status": "completed",
            "details": metadata_details,
        },
        {
            "name": "incremental_source_compile",
            "label": "incremental source compile",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "source_pages": len(context.entries),
                "dirty_sources": len(context.dirty_source_ids),
                "clean_sources": len(context.clean_source_ids),
                "updated_pages": context.source_changed_pages,
                "skipped_pages": len(context.clean_source_ids),
            },
        },
        {
            "name": "concept_refresh",
            "label": "concept refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "concept_sources": len(context.entries),
                "dirty_concept_sources": len(context.dirty_concept_source_ids),
                "clean_concept_sources": len(context.clean_concept_source_ids),
                "concept_pages": len(context.concepts),
                "dirty_concepts": len(context.dirty_concept_slugs),
                "clean_concepts": len(context.clean_concept_slugs),
                "updated_pages": context.concept_changed_pages,
                "skipped_pages": len(context.clean_concept_slugs),
            },
        },
        {
            "name": "machine_memory_refresh",
            "label": "machine memory refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "machine_memory_sources": len(context.entries),
                "dirty_machine_memory_sources": len(context.dirty_machine_memory_source_ids),
                "clean_machine_memory_sources": len(context.clean_machine_memory_source_ids),
                "machine_memory_concepts": len(context.concepts),
                "dirty_machine_memory_concepts": len(context.dirty_machine_memory_concept_slugs),
                "clean_machine_memory_concepts": len(context.clean_machine_memory_concept_slugs),
                "reused_core": context.machine_memory_core_reused,
                "cache_enabled": bool(cache_details.get("enabled", False)),
                "cache_schema_version": int(cache_details.get("schema_version", 0) or 0),
                "cache_row_count": int(sum(int(value or 0) for value in cache_details.get("row_counts", {}).values())),
                "cache_rebuilds": int(cache_stats.get("rebuilds", 0) or 0),
            },
        },
        {
            "name": "ranking_refresh",
            "label": "concept/global ranking refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "ranking_sources": len(context.entries),
                "dirty_ranking_sources": len(context.dirty_ranking_source_ids),
                "clean_ranking_sources": len(context.clean_ranking_source_ids),
                "ranking_concepts": len(context.concepts),
                "dirty_ranking_concepts": len(context.dirty_ranking_concept_slugs),
                "clean_ranking_concepts": len(context.clean_ranking_concept_slugs),
            },
        },
        {
            "name": "index_refresh",
            "label": "index refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "tracked_artifacts": len(context.dirty_index_artifacts) + len(context.clean_index_artifacts),
                "dirty_artifacts": len(context.dirty_index_artifacts),
                "clean_artifacts": len(context.clean_index_artifacts),
                "updated_artifacts": context.index_changed_pages,
                "skipped_artifacts": len(context.clean_index_artifacts),
            },
        },
        {
            "name": "cold_archive_maintenance",
            "label": "cold/archive maintenance",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "tracked_artifacts": len(context.dirty_maintenance_artifacts) + len(context.clean_maintenance_artifacts),
                "dirty_artifacts": len(context.dirty_maintenance_artifacts),
                "clean_artifacts": len(context.clean_maintenance_artifacts),
                "updated_artifacts": context.maintenance_changed_pages,
                "skipped_artifacts": len(context.clean_maintenance_artifacts),
                "removed_generated_pages": context.removed_pages,
                "material_state_entries": len(context.material_state["entries"]),
                "archive_candidates": len(context.archive_candidates.get("entries", [])),
                "active_corpora": len(context.active_corpora_state.get("corpora", [])),
                "knowledge_lifecycle_entries": len(context.knowledge_lifecycle.get("entries", [])),
            },
        },
        {
            "name": "output_pack_refresh",
            "label": "output pack refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "pack_groups": 4,
                "dirty_pack_groups": len(context.dirty_output_pack_groups),
                "clean_pack_groups": len(context.clean_output_pack_groups),
                "review_packs": int(context.output_packs.get("counts", {}).get("review_packs", 0) or 0),
                "decision_memos": int(context.output_packs.get("counts", {}).get("decision_memos", 0) or 0),
                "sop_drafts": int(context.output_packs.get("counts", {}).get("sop_drafts", 0) or 0),
                "updated_artifacts": context.output_pack_changed_pages,
                "skipped_artifacts": len(context.clean_output_pack_groups),
            },
        },
        {
            "name": "domain_pilot_refresh",
            "label": "domain pilot refresh",
            "mode": "incremental",
            "status": "completed",
            "details": {
                "pilot_protocols": len(context.domain_pilots.get("scorecards", [])),
                "dirty_protocols": len(context.dirty_domain_pilot_protocols),
                "clean_protocols": len(context.clean_domain_pilot_protocols),
                "updated_artifacts": context.domain_pilot_changed_pages,
                "skipped_artifacts": len(context.clean_domain_pilot_protocols),
            },
        },
    ]


def _build_compile_state_document(
    context: CompileContext,
    phase_summary: list[dict[str, Any]],
) -> dict[str, Any]:
    drift_warnings = _build_compile_drift_warnings(context)
    return {
        "version": 1,
        "compiled_at": context.compiled_at,
        "manifest_entry_count": len(context.entries),
        "dirty_source_ids": context.dirty_source_ids,
        "clean_source_ids": context.clean_source_ids,
        "dirty_concept_source_ids": context.dirty_concept_source_ids,
        "clean_concept_source_ids": context.clean_concept_source_ids,
        "dirty_concept_slugs": context.dirty_concept_slugs,
        "clean_concept_slugs": context.clean_concept_slugs,
        "dirty_machine_memory_source_ids": context.dirty_machine_memory_source_ids,
        "clean_machine_memory_source_ids": context.clean_machine_memory_source_ids,
        "dirty_machine_memory_concept_slugs": context.dirty_machine_memory_concept_slugs,
        "clean_machine_memory_concept_slugs": context.clean_machine_memory_concept_slugs,
        "machine_memory_core_reused": context.machine_memory_core_reused,
        "dirty_ranking_source_ids": context.dirty_ranking_source_ids,
        "clean_ranking_source_ids": context.clean_ranking_source_ids,
        "dirty_ranking_concept_slugs": context.dirty_ranking_concept_slugs,
        "clean_ranking_concept_slugs": context.clean_ranking_concept_slugs,
        "dirty_output_pack_groups": context.dirty_output_pack_groups,
        "clean_output_pack_groups": context.clean_output_pack_groups,
        "dirty_domain_pilot_protocols": context.dirty_domain_pilot_protocols,
        "clean_domain_pilot_protocols": context.clean_domain_pilot_protocols,
        "dirty_index_artifacts": context.dirty_index_artifacts,
        "clean_index_artifacts": context.clean_index_artifacts,
        "dirty_maintenance_artifacts": context.dirty_maintenance_artifacts,
        "clean_maintenance_artifacts": context.clean_maintenance_artifacts,
        "drift_warnings": drift_warnings,
        "phase_summary": phase_summary,
    }


def _compile_state_concept_slugs(document: dict[str, Any]) -> set[str]:
    concept_slugs: set[str] = set()
    for key in ("dirty_concept_slugs", "clean_concept_slugs"):
        items = document.get(key, [])
        if not isinstance(items, list):
            continue
        concept_slugs.update(str(slug) for slug in items if str(slug))
    return concept_slugs


def _build_compile_drift_warnings(context: CompileContext) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    previous_concept_slugs = _compile_state_concept_slugs(context.previous_compile_state)
    current_concept_slugs = {
        str(node.get("slug") or "")
        for node in context.memory.get("concept_nodes", [])
        if isinstance(node, dict) and str(node.get("slug") or "")
    }
    removed_concept_slugs = sorted(previous_concept_slugs - current_concept_slugs)
    if removed_concept_slugs:
        warnings.append(
            {
                "kind": "concept-disappear",
                "message": f"{len(removed_concept_slugs)} concept page(s) disappeared since the previous compile.",
                "concept_slugs": removed_concept_slugs[:8],
            }
        )

    drift = context.memory.get("drift", {})
    if isinstance(drift, dict):
        missing_reference_paths = [
            *[str(path) for path in drift.get("missing_raw_files", []) if str(path)],
            *[str(path) for path in drift.get("missing_source_pages", []) if str(path)],
        ]
        for path in missing_reference_paths[:4]:
            warnings.append(
                {
                    "kind": "source-reference-break",
                    "path": path,
                    "message": f"Missing source reference `{path}`.",
                }
            )

    invalidated_judgments: list[dict[str, Any]] = []
    for entry in context.knowledge_lifecycle.get("entries", []):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("kind") or "") != "judgment":
            continue
        invalidation_signals = entry.get("invalidation_signals", [])
        if not isinstance(invalidation_signals, list) or not invalidation_signals:
            continue
        invalidated_judgments.append(entry)
    citation_drift_judgments = [
        entry
        for entry in invalidated_judgments
        if "citation-drift" in entry.get("invalidation_signals", [])
        or bool(entry.get("citation_drift"))
    ]
    for entry in citation_drift_judgments[:4]:
        warnings.append(
            {
                "kind": "source-reference-break",
                "path": str(entry.get("path") or ""),
                "message": (
                    f"{str(entry.get('title') or entry.get('path') or 'judgment')} cites drifted source evidence."
                ),
            }
        )

    invalidated_judgments.sort(
        key=lambda item: (
            -len(item.get("invalidation_signals", []) if isinstance(item.get("invalidation_signals"), list) else []),
            str(item.get("path") or ""),
        )
    )
    for entry in invalidated_judgments[:4]:
        warnings.append(
            {
                "kind": "judgment-invalidation",
                "path": str(entry.get("path") or ""),
                "message": (
                    f"{str(entry.get('title') or entry.get('path') or 'judgment')} requires invalidation review."
                ),
                "invalidation_signals": [
                    str(signal)
                    for signal in entry.get("invalidation_signals", [])
                    if str(signal)
                ][:4],
            }
        )
    return warnings[:8]


def _compile_log_details(context: CompileContext) -> list[str]:
    return [
        f"compiled_at: `{context.compiled_at}`",
        f"compile_state: `{relative_path(context.root, compile_state_path(context.root))}`",
        f"compile_dirty_sources: `{len(context.dirty_source_ids)}`",
        f"compile_clean_sources: `{len(context.clean_source_ids)}`",
        f"compile_dirty_concept_sources: `{len(context.dirty_concept_source_ids)}`",
        f"compile_clean_concept_sources: `{len(context.clean_concept_source_ids)}`",
        f"compile_dirty_concepts: `{len(context.dirty_concept_slugs)}`",
        f"compile_clean_concepts: `{len(context.clean_concept_slugs)}`",
        f"compile_dirty_machine_memory_sources: `{len(context.dirty_machine_memory_source_ids)}`",
        f"compile_clean_machine_memory_sources: `{len(context.clean_machine_memory_source_ids)}`",
        f"compile_dirty_machine_memory_concepts: `{len(context.dirty_machine_memory_concept_slugs)}`",
        f"compile_clean_machine_memory_concepts: `{len(context.clean_machine_memory_concept_slugs)}`",
        f"machine_memory_core_reused: `{context.machine_memory_core_reused}`",
        f"compile_dirty_ranking_sources: `{len(context.dirty_ranking_source_ids)}`",
        f"compile_clean_ranking_sources: `{len(context.clean_ranking_source_ids)}`",
        f"compile_dirty_ranking_concepts: `{len(context.dirty_ranking_concept_slugs)}`",
        f"compile_clean_ranking_concepts: `{len(context.clean_ranking_concept_slugs)}`",
        f"compile_dirty_output_pack_groups: `{len(context.dirty_output_pack_groups)}`",
        f"compile_clean_output_pack_groups: `{len(context.clean_output_pack_groups)}`",
        f"compile_dirty_domain_pilot_protocols: `{len(context.dirty_domain_pilot_protocols)}`",
        f"compile_clean_domain_pilot_protocols: `{len(context.clean_domain_pilot_protocols)}`",
        f"compile_dirty_index_artifacts: `{len(context.dirty_index_artifacts)}`",
        f"compile_clean_index_artifacts: `{len(context.clean_index_artifacts)}`",
        f"compile_dirty_maintenance_artifacts: `{len(context.dirty_maintenance_artifacts)}`",
        f"compile_clean_maintenance_artifacts: `{len(context.clean_maintenance_artifacts)}`",
        f"compile_drift_warnings: `{len(_build_compile_drift_warnings(context))}`",
        f"source_pages_updated: `{context.source_changed_pages}`",
        f"source_pages: `{len(context.entries)}`",
        f"concept_pages: `{len(context.concepts)}`",
        f"active_protocol: `{context.protocol_state['active_protocol']}`",
        f"machine_memory_terms: `{len(context.memory['term_index'])}`",
        f"graph_components: `{context.memory['health']['component_count']}`",
        f"output_packs: `{context.output_packs['counts']['review_packs']}/{context.output_packs['counts']['decision_memos']}/{context.output_packs['counts']['sop_drafts']}`",
        f"domain_pilots: `{len(context.domain_pilots['scorecards'])}`",
        f"material_state_entries: `{len(context.material_state['entries'])}`",
        f"material_routing_entries: `{len(context.material_routing.get('entries', []))}`",
        f"archive_candidates: `{len(context.archive_candidates.get('entries', []))}`",
        f"active_corpora: `{len(context.active_corpora_state.get('corpora', []))}`",
        f"knowledge_lifecycle_entries: `{len(context.knowledge_lifecycle.get('entries', []))}`",
        f"machine_memory_changed: `{context.transition['changed']}`",
        f"changed_pages: `{context.changed_pages}`",
        f"removed_concept_pages: `{context.removed_pages}`",
    ]


def _build_compile_result_payload(
    context: CompileContext,
    phase_summary: list[dict[str, Any]],
) -> dict[str, Any]:
    drift_warnings = _build_compile_drift_warnings(context)
    concept_rewrite = context.memory.get("health", {}).get("concept_rewrite", {})
    concept_rewrite_proposals = [
        proposal
        for proposal in concept_rewrite.get("proposals", [])
        if isinstance(proposal, dict)
    ]
    return {
        "compiled_at": context.compiled_at,
        "sources": len(context.entries),
        "concepts": len(context.concepts),
        "machine_memory_terms": len(context.memory["term_index"]),
        "machine_memory_changed": context.transition["changed"],
        "changed_pages": context.changed_pages,
        "dirty_sources": len(context.dirty_source_ids),
        "clean_sources": len(context.clean_source_ids),
        "dirty_source_ids": list(context.dirty_source_ids),
        "clean_source_ids": list(context.clean_source_ids),
        "dirty_concept_sources": len(context.dirty_concept_source_ids),
        "clean_concept_sources": len(context.clean_concept_source_ids),
        "dirty_concept_source_ids": list(context.dirty_concept_source_ids),
        "clean_concept_source_ids": list(context.clean_concept_source_ids),
        "dirty_concepts": len(context.dirty_concept_slugs),
        "clean_concepts": len(context.clean_concept_slugs),
        "dirty_concept_slugs": list(context.dirty_concept_slugs),
        "clean_concept_slugs": list(context.clean_concept_slugs),
        "dirty_machine_memory_sources": len(context.dirty_machine_memory_source_ids),
        "clean_machine_memory_sources": len(context.clean_machine_memory_source_ids),
        "dirty_machine_memory_source_ids": list(context.dirty_machine_memory_source_ids),
        "clean_machine_memory_source_ids": list(context.clean_machine_memory_source_ids),
        "dirty_machine_memory_concepts": len(context.dirty_machine_memory_concept_slugs),
        "clean_machine_memory_concepts": len(context.clean_machine_memory_concept_slugs),
        "dirty_machine_memory_concept_slugs": list(context.dirty_machine_memory_concept_slugs),
        "clean_machine_memory_concept_slugs": list(context.clean_machine_memory_concept_slugs),
        "machine_memory_core_reused": context.machine_memory_core_reused,
        "dirty_ranking_sources": len(context.dirty_ranking_source_ids),
        "clean_ranking_sources": len(context.clean_ranking_source_ids),
        "dirty_ranking_source_ids": list(context.dirty_ranking_source_ids),
        "clean_ranking_source_ids": list(context.clean_ranking_source_ids),
        "dirty_ranking_concepts": len(context.dirty_ranking_concept_slugs),
        "clean_ranking_concepts": len(context.clean_ranking_concept_slugs),
        "dirty_ranking_concept_slugs": list(context.dirty_ranking_concept_slugs),
        "clean_ranking_concept_slugs": list(context.clean_ranking_concept_slugs),
        "dirty_output_pack_groups": list(context.dirty_output_pack_groups),
        "clean_output_pack_groups": list(context.clean_output_pack_groups),
        "dirty_domain_pilot_protocols": list(context.dirty_domain_pilot_protocols),
        "clean_domain_pilot_protocols": list(context.clean_domain_pilot_protocols),
        "dirty_index_artifacts": list(context.dirty_index_artifacts),
        "clean_index_artifacts": list(context.clean_index_artifacts),
        "dirty_maintenance_artifacts": list(context.dirty_maintenance_artifacts),
        "clean_maintenance_artifacts": list(context.clean_maintenance_artifacts),
        "drift_warnings": drift_warnings,
        "phase_summary": phase_summary,
        "output_packs": dict(context.output_packs["counts"]),
        "domain_pilots": len(context.domain_pilots["scorecards"]),
        "compile_state_path": relative_path(context.root, compile_state_path(context.root)),
        "cache_status_path": relative_path(context.root, cache_status_path(context.root)),
        "concept_build_state_path": relative_path(context.root, concept_build_state_path(context.root)),
        "machine_memory_build_state_path": relative_path(context.root, machine_memory_build_state_path(context.root)),
        "ranking_build_state_path": relative_path(context.root, ranking_build_state_path(context.root)),
        "output_pack_build_state_path": relative_path(context.root, output_pack_build_state_path(context.root)),
        "domain_pilot_build_state_path": relative_path(context.root, domain_pilot_build_state_path(context.root)),
        "material_state_path": relative_path(context.root, material_state_path(context.root)),
        "active_corpora_path": relative_path(context.root, active_corpora_state_path(context.root)),
        "material_routing_path": relative_path(context.root, material_routing_state_path(context.root)),
        "archive_candidates_path": relative_path(context.root, archive_candidates_state_path(context.root)),
        "knowledge_lifecycle_path": relative_path(context.root, knowledge_lifecycle_state_path(context.root)),
        "knowledge_lifecycle_overrides_path": relative_path(
            context.root,
            knowledge_lifecycle_override_state_path(context.root),
        ),
        "concept_rewrite": {
            "counts": dict(concept_rewrite.get("counts", {})) if isinstance(concept_rewrite.get("counts"), dict) else {},
            "state_path": str(concept_rewrite.get("state_path") or ""),
            "proposal_paths": [
                str(proposal.get("proposal_path") or "")
                for proposal in concept_rewrite_proposals
                if str(proposal.get("proposal_path") or "")
            ],
        },
    }


def finalize_compile_phase(context: CompileContext, *, force_cache_rebuild: bool = False) -> dict[str, Any]:
    context.cache_status = sync_query_cache(
        context.root,
        memory=context.memory,
        material_state=context.material_state,
        routing_state=context.material_routing,
        knowledge_lifecycle=context.knowledge_lifecycle,
        archive_candidates=context.archive_candidates,
        compiled_at=context.compiled_at,
        force_rebuild=force_cache_rebuild,
    )
    phase_summary = _build_compile_phase_summary(context)
    compile_state = _build_compile_state_document(context, phase_summary)
    save_compile_state(context.root, compile_state)
    compile_status_changed = int(
        write_if_changed(
            context.root / "wiki" / "indexes" / "compile-status.md",
            render_compile_status(
                context.entries,
                context.concepts,
                context.decision_pages,
                context.judgment_pages,
                context.protocol_state,
                context.compiled_at,
                compile_state=compile_state,
            ),
        )
    )
    context.changed_pages += compile_status_changed
    append_wiki_log(
        context.root,
        "compile",
        "wiki refresh",
        _compile_log_details(context),
    )
    return _build_compile_result_payload(context, phase_summary)


__all__ = ["finalize_compile_phase"]
