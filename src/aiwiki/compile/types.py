"""Compile domain TypedDict contracts."""

from __future__ import annotations

from typing import Any, TypedDict


class CompileState(TypedDict, total=False):
    version: int
    compiled_at: str
    manifest_entry_count: int
    dirty_source_ids: list[str]
    clean_source_ids: list[str]
    dirty_concept_source_ids: list[str]
    clean_concept_source_ids: list[str]
    dirty_concept_slugs: list[str]
    clean_concept_slugs: list[str]
    dirty_machine_memory_source_ids: list[str]
    clean_machine_memory_source_ids: list[str]
    dirty_machine_memory_concept_slugs: list[str]
    clean_machine_memory_concept_slugs: list[str]
    machine_memory_core_reused: bool
    dirty_ranking_source_ids: list[str]
    clean_ranking_source_ids: list[str]
    dirty_ranking_concept_slugs: list[str]
    clean_ranking_concept_slugs: list[str]
    dirty_output_pack_groups: list[str]
    clean_output_pack_groups: list[str]
    dirty_domain_pilot_protocols: list[str]
    clean_domain_pilot_protocols: list[str]
    dirty_index_artifacts: list[str]
    clean_index_artifacts: list[str]
    dirty_maintenance_artifacts: list[str]
    clean_maintenance_artifacts: list[str]
    drift_warnings: list[dict[str, Any]]
    phase_summary: list[dict[str, Any]]
