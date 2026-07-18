"""Compile state helpers extracted from the legacy app_state hub."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_state_paths import compile_state_path
from ..state.io import load_json_document, save_json_document


def default_compile_state() -> dict[str, Any]:
    return {
        "version": 1,
        "compiled_at": "",
        "manifest_entry_count": 0,
        "dirty_source_ids": [],
        "clean_source_ids": [],
        "dirty_concept_source_ids": [],
        "clean_concept_source_ids": [],
        "dirty_concept_slugs": [],
        "clean_concept_slugs": [],
        "dirty_machine_memory_source_ids": [],
        "clean_machine_memory_source_ids": [],
        "dirty_machine_memory_concept_slugs": [],
        "clean_machine_memory_concept_slugs": [],
        "machine_memory_core_reused": False,
        "dirty_ranking_source_ids": [],
        "clean_ranking_source_ids": [],
        "dirty_ranking_concept_slugs": [],
        "clean_ranking_concept_slugs": [],
        "dirty_output_pack_groups": [],
        "clean_output_pack_groups": [],
        "dirty_domain_pilot_protocols": [],
        "clean_domain_pilot_protocols": [],
        "dirty_index_artifacts": [],
        "clean_index_artifacts": [],
        "dirty_maintenance_artifacts": [],
        "clean_maintenance_artifacts": [],
        "drift_warnings": [],
        "phase_summary": [],
    }


def load_compile_state(root: Path) -> dict[str, Any]:
    document = load_json_document(compile_state_path(root))
    if not isinstance(document, dict):
        return default_compile_state()
    dirty_source_ids = document.get("dirty_source_ids", [])
    clean_source_ids = document.get("clean_source_ids", [])
    dirty_concept_source_ids = document.get("dirty_concept_source_ids", [])
    clean_concept_source_ids = document.get("clean_concept_source_ids", [])
    dirty_concept_slugs = document.get("dirty_concept_slugs", [])
    clean_concept_slugs = document.get("clean_concept_slugs", [])
    dirty_machine_memory_source_ids = document.get("dirty_machine_memory_source_ids", [])
    clean_machine_memory_source_ids = document.get("clean_machine_memory_source_ids", [])
    dirty_machine_memory_concept_slugs = document.get("dirty_machine_memory_concept_slugs", [])
    clean_machine_memory_concept_slugs = document.get("clean_machine_memory_concept_slugs", [])
    dirty_ranking_source_ids = document.get("dirty_ranking_source_ids", [])
    clean_ranking_source_ids = document.get("clean_ranking_source_ids", [])
    dirty_ranking_concept_slugs = document.get("dirty_ranking_concept_slugs", [])
    clean_ranking_concept_slugs = document.get("clean_ranking_concept_slugs", [])
    dirty_output_pack_groups = document.get("dirty_output_pack_groups", [])
    clean_output_pack_groups = document.get("clean_output_pack_groups", [])
    dirty_domain_pilot_protocols = document.get("dirty_domain_pilot_protocols", [])
    clean_domain_pilot_protocols = document.get("clean_domain_pilot_protocols", [])
    dirty_index_artifacts = document.get("dirty_index_artifacts", [])
    clean_index_artifacts = document.get("clean_index_artifacts", [])
    dirty_maintenance_artifacts = document.get("dirty_maintenance_artifacts", [])
    clean_maintenance_artifacts = document.get("clean_maintenance_artifacts", [])
    drift_warnings = document.get("drift_warnings", [])
    phase_summary = document.get("phase_summary")
    if (
        not isinstance(dirty_source_ids, list)
        or not isinstance(clean_source_ids, list)
        or not isinstance(dirty_concept_source_ids, list)
        or not isinstance(clean_concept_source_ids, list)
        or not isinstance(dirty_concept_slugs, list)
        or not isinstance(clean_concept_slugs, list)
        or not isinstance(dirty_machine_memory_source_ids, list)
        or not isinstance(clean_machine_memory_source_ids, list)
        or not isinstance(dirty_machine_memory_concept_slugs, list)
        or not isinstance(clean_machine_memory_concept_slugs, list)
        or not isinstance(dirty_ranking_source_ids, list)
        or not isinstance(clean_ranking_source_ids, list)
        or not isinstance(dirty_ranking_concept_slugs, list)
        or not isinstance(clean_ranking_concept_slugs, list)
        or not isinstance(dirty_output_pack_groups, list)
        or not isinstance(clean_output_pack_groups, list)
        or not isinstance(dirty_domain_pilot_protocols, list)
        or not isinstance(clean_domain_pilot_protocols, list)
        or not isinstance(dirty_index_artifacts, list)
        or not isinstance(clean_index_artifacts, list)
        or not isinstance(dirty_maintenance_artifacts, list)
        or not isinstance(clean_maintenance_artifacts, list)
        or not isinstance(drift_warnings, list)
        or not isinstance(phase_summary, list)
    ):
        return default_compile_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "compiled_at": str(document.get("compiled_at") or ""),
        "manifest_entry_count": int(document.get("manifest_entry_count", 0) or 0),
        "dirty_source_ids": [str(entry_id) for entry_id in dirty_source_ids if str(entry_id)],
        "clean_source_ids": [str(entry_id) for entry_id in clean_source_ids if str(entry_id)],
        "dirty_concept_source_ids": [str(entry_id) for entry_id in dirty_concept_source_ids if str(entry_id)],
        "clean_concept_source_ids": [str(entry_id) for entry_id in clean_concept_source_ids if str(entry_id)],
        "dirty_concept_slugs": [str(slug) for slug in dirty_concept_slugs if str(slug)],
        "clean_concept_slugs": [str(slug) for slug in clean_concept_slugs if str(slug)],
        "dirty_machine_memory_source_ids": [
            str(entry_id) for entry_id in dirty_machine_memory_source_ids if str(entry_id)
        ],
        "clean_machine_memory_source_ids": [
            str(entry_id) for entry_id in clean_machine_memory_source_ids if str(entry_id)
        ],
        "dirty_machine_memory_concept_slugs": [str(slug) for slug in dirty_machine_memory_concept_slugs if str(slug)],
        "clean_machine_memory_concept_slugs": [str(slug) for slug in clean_machine_memory_concept_slugs if str(slug)],
        "machine_memory_core_reused": bool(document.get("machine_memory_core_reused", False)),
        "dirty_ranking_source_ids": [str(entry_id) for entry_id in dirty_ranking_source_ids if str(entry_id)],
        "clean_ranking_source_ids": [str(entry_id) for entry_id in clean_ranking_source_ids if str(entry_id)],
        "dirty_ranking_concept_slugs": [str(slug) for slug in dirty_ranking_concept_slugs if str(slug)],
        "clean_ranking_concept_slugs": [str(slug) for slug in clean_ranking_concept_slugs if str(slug)],
        "dirty_output_pack_groups": [str(group) for group in dirty_output_pack_groups if str(group)],
        "clean_output_pack_groups": [str(group) for group in clean_output_pack_groups if str(group)],
        "dirty_domain_pilot_protocols": [str(protocol) for protocol in dirty_domain_pilot_protocols if str(protocol)],
        "clean_domain_pilot_protocols": [str(protocol) for protocol in clean_domain_pilot_protocols if str(protocol)],
        "dirty_index_artifacts": [str(path) for path in dirty_index_artifacts if str(path)],
        "clean_index_artifacts": [str(path) for path in clean_index_artifacts if str(path)],
        "dirty_maintenance_artifacts": [str(path) for path in dirty_maintenance_artifacts if str(path)],
        "clean_maintenance_artifacts": [str(path) for path in clean_maintenance_artifacts if str(path)],
        "drift_warnings": [warning for warning in drift_warnings if isinstance(warning, dict)],
        "phase_summary": [phase for phase in phase_summary if isinstance(phase, dict)],
    }


def save_compile_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(compile_state_path(root), document)
