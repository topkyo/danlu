"""Compile context and bootstrap helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..app_protocol import ensure_layout, load_protocol_state
from ..app_state import load_compile_state, load_json_document_strict, load_manifest, machine_memory_state_path
from ..app_utils import (
    relative_path,
    utc_now,
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from ..content.io import sync_manifest_with_raw


@dataclass
class CompileContext:
    root: Path
    previous_manifest: dict[str, Any]
    manifest: dict[str, Any]
    entries: list[dict[str, Any]]
    compiled_at: str
    protocol_state: dict[str, Any]
    previous_compile_state: dict[str, Any]
    previous_memory: dict[str, Any]
    changed_pages: int = 0
    source_changed_pages: int = 0
    concept_changed_pages: int = 0
    index_changed_pages: int = 0
    maintenance_changed_pages: int = 0
    output_pack_changed_pages: int = 0
    domain_pilot_changed_pages: int = 0
    removed_pages: int = 0
    dirty_index_artifacts: list[str] = field(default_factory=list)
    clean_index_artifacts: list[str] = field(default_factory=list)
    dirty_maintenance_artifacts: list[str] = field(default_factory=list)
    clean_maintenance_artifacts: list[str] = field(default_factory=list)
    previews: dict[str, str] = field(default_factory=dict)
    concepts: list[dict[str, Any]] = field(default_factory=list)
    entry_terms: dict[str, list[str]] = field(default_factory=dict)
    decision_pages: list[dict[str, Any]] = field(default_factory=list)
    judgment_pages: list[dict[str, Any]] = field(default_factory=list)
    dirty_concept_source_ids: list[str] = field(default_factory=list)
    clean_concept_source_ids: list[str] = field(default_factory=list)
    dirty_source_ids: list[str] = field(default_factory=list)
    clean_source_ids: list[str] = field(default_factory=list)
    dirty_concept_slugs: list[str] = field(default_factory=list)
    clean_concept_slugs: list[str] = field(default_factory=list)
    dirty_machine_memory_source_ids: list[str] = field(default_factory=list)
    clean_machine_memory_source_ids: list[str] = field(default_factory=list)
    dirty_machine_memory_concept_slugs: list[str] = field(default_factory=list)
    clean_machine_memory_concept_slugs: list[str] = field(default_factory=list)
    machine_memory_core_reused: bool = False
    memory: dict[str, Any] = field(default_factory=dict)
    execution_audit: dict[str, Any] = field(default_factory=dict)
    transition: dict[str, Any] = field(default_factory=dict)
    dirty_ranking_source_ids: list[str] = field(default_factory=list)
    clean_ranking_source_ids: list[str] = field(default_factory=list)
    dirty_ranking_concept_slugs: list[str] = field(default_factory=list)
    clean_ranking_concept_slugs: list[str] = field(default_factory=list)
    all_outputs: list[dict[str, Any]] = field(default_factory=list)
    recent_outputs: list[dict[str, Any]] = field(default_factory=list)
    active_corpora_state: dict[str, Any] = field(default_factory=dict)
    material_state: dict[str, Any] = field(default_factory=dict)
    material_routing: dict[str, Any] = field(default_factory=dict)
    archive_candidates: dict[str, Any] = field(default_factory=dict)
    knowledge_lifecycle: dict[str, Any] = field(default_factory=dict)
    output_packs: dict[str, Any] = field(default_factory=dict)
    dirty_output_pack_groups: list[str] = field(default_factory=list)
    clean_output_pack_groups: list[str] = field(default_factory=list)
    domain_pilots: dict[str, Any] = field(default_factory=dict)
    dirty_domain_pilot_protocols: list[str] = field(default_factory=list)
    clean_domain_pilot_protocols: list[str] = field(default_factory=list)
    cache_status: dict[str, Any] = field(default_factory=dict)

    def write_index_artifact(self, destination: Path, content: str) -> int:
        wrote, dirty = write_if_changed_ignoring_timestamps(destination, content)
        relative = relative_path(self.root, destination)
        if dirty:
            self.dirty_index_artifacts.append(relative)
        else:
            self.clean_index_artifacts.append(relative)
        self.changed_pages += int(wrote)
        self.index_changed_pages += int(wrote)
        return int(wrote)

    def write_maintenance_artifact(self, destination: Path, document: dict[str, Any]) -> int:
        wrote, dirty = write_json_document_if_changed_ignoring_generated_timestamps(destination, document)
        relative = relative_path(self.root, destination)
        if dirty:
            self.dirty_maintenance_artifacts.append(relative)
        else:
            self.clean_maintenance_artifacts.append(relative)
        self.changed_pages += int(wrote)
        self.maintenance_changed_pages += int(wrote)
        return int(wrote)

    def write_output_pack_artifact(self, destination: Path, content: str) -> int:
        wrote, _dirty = write_if_changed_ignoring_timestamps(destination, content)
        self.changed_pages += int(wrote)
        self.output_pack_changed_pages += int(wrote)
        return int(wrote)

    def write_domain_pilot_artifact(self, destination: Path, content: str) -> int:
        wrote, _dirty = write_if_changed_ignoring_timestamps(destination, content)
        self.changed_pages += int(wrote)
        self.domain_pilot_changed_pages += int(wrote)
        return int(wrote)


def start_compile_context(root: Path) -> CompileContext:
    ensure_layout(root)
    previous_manifest = load_manifest(root)
    manifest = sync_manifest_with_raw(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    # Preserve the long-lived test seam that patches `aiwiki.app_compile.utc_now`.
    from .. import app_compile as compile_facade

    return CompileContext(
        root=root,
        previous_manifest=previous_manifest,
        manifest=manifest,
        entries=entries,
        compiled_at=compile_facade.utc_now(),
        protocol_state=load_protocol_state(root),
        previous_compile_state=load_compile_state(root),
        previous_memory=load_json_document_strict(machine_memory_state_path(root)),
    )


__all__ = ["CompileContext", "start_compile_context"]
