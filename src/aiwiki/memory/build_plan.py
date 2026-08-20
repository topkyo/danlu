"""Machine-memory build planning helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..compile.build import load_machine_memory_build_state
from .action_core import (
    machine_memory_concept_input_signature,
    machine_memory_source_input_signature,
)


def plan_machine_memory_build(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    previews: dict[str, str],
    entry_terms: dict[str, list[str]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    previous_state = load_machine_memory_build_state(root)
    previous_source_records = previous_state.get("source_records", {})
    previous_concept_records = previous_state.get("concept_records", {})
    if not isinstance(previous_source_records, dict):
        previous_source_records = {}
    if not isinstance(previous_concept_records, dict):
        previous_concept_records = {}

    source_records: dict[str, dict[str, str]] = {}
    dirty_source_ids: list[str] = []
    clean_source_ids: list[str] = []
    for entry in entries:
        entry_id = str(entry["id"])
        input_signature = machine_memory_source_input_signature(
            root,
            entry,
            previews.get(entry_id, ""),
            entry_terms.get(entry_id, []),
        )
        source_records[entry_id] = {"input_signature": input_signature}
        previous_record = previous_source_records.get(entry_id, {})
        if isinstance(previous_record, dict) and str(previous_record.get("input_signature") or "") == input_signature:
            clean_source_ids.append(entry_id)
        else:
            dirty_source_ids.append(entry_id)

    concept_records: dict[str, dict[str, str]] = {}
    dirty_concept_slugs: list[str] = []
    clean_concept_slugs: list[str] = []
    for record in concepts:
        slug = str(record["slug"])
        input_signature = machine_memory_concept_input_signature(root, record)
        concept_records[slug] = {"input_signature": input_signature}
        previous_record = previous_concept_records.get(slug, {})
        if isinstance(previous_record, dict) and str(previous_record.get("input_signature") or "") == input_signature:
            clean_concept_slugs.append(slug)
        else:
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
        "inputs_clean": not (dirty_source_ids or dirty_concept_slugs or removed_source_ids or removed_concept_slugs),
    }
