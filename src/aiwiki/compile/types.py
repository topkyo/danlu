"""Compile domain TypedDict contracts."""

from __future__ import annotations

from typing import Any, TypedDict

# Single source of truth for CompileState persistence keys.
# ``compile.state`` (defaults + strict loader), ``compile.persist_step`` (state
# document) and ``render.compile_status`` derive from these registries; add a
# new dirty/clean pair here instead of editing N files.
COMPILE_STATE_SCALAR_DEFAULTS: dict[str, Any] = {
    "version": 1,
    "compiled_at": "",
    "manifest_entry_count": 0,
    "machine_memory_core_reused": False,
}

COMPILE_STATE_STR_LIST_KEYS: tuple[str, ...] = (
    "dirty_source_ids",
    "clean_source_ids",
    "dirty_concept_source_ids",
    "clean_concept_source_ids",
    "dirty_concept_slugs",
    "clean_concept_slugs",
    "dirty_machine_memory_source_ids",
    "clean_machine_memory_source_ids",
    "dirty_machine_memory_concept_slugs",
    "clean_machine_memory_concept_slugs",
    "dirty_ranking_source_ids",
    "clean_ranking_source_ids",
    "dirty_ranking_concept_slugs",
    "clean_ranking_concept_slugs",
    "dirty_index_artifacts",
    "clean_index_artifacts",
    "dirty_maintenance_artifacts",
    "clean_maintenance_artifacts",
)

COMPILE_STATE_DICT_LIST_KEYS: tuple[str, ...] = (
    "drift_warnings",
    "phase_summary",
)


class CompileState(TypedDict, total=False):
    # Field list mirrors the registries above (TypedDict cannot be table-driven);
    # keep them in sync when adding keys.
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
    dirty_index_artifacts: list[str]
    clean_index_artifacts: list[str]
    dirty_maintenance_artifacts: list[str]
    clean_maintenance_artifacts: list[str]
    drift_warnings: list[dict[str, Any]]
    phase_summary: list[dict[str, Any]]
