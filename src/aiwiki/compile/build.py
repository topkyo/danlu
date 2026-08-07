"""Build-state helpers (concept / machine-memory / ranking).

Extracted from the legacy app_state hub. Each builder owns its own persisted state file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..state.io import load_json_document, save_json_document
from .paths import (
    concept_build_state_path,
    machine_memory_build_state_path,
    ranking_build_state_path,
)


def default_concept_build_state() -> dict[str, Any]:
    return {"version": 2, "generated_at": "", "entry_records": {}}


def load_concept_build_state(root: Path) -> dict[str, Any]:
    document = load_json_document(concept_build_state_path(root))
    if not isinstance(document, dict):
        return default_concept_build_state()
    version = int(document.get("version", 1) or 1)
    if version < 2:
        return default_concept_build_state()
    entry_records = document.get("entry_records")
    if not isinstance(entry_records, dict):
        return default_concept_build_state()
    normalized_records: dict[str, dict[str, Any]] = {}
    for entry_id, record in entry_records.items():
        if not isinstance(entry_id, str) or not entry_id or not isinstance(record, dict):
            continue
        terms = record.get("terms", [])
        if not isinstance(terms, list):
            continue
        normalized_records[entry_id] = {
            "input_signature": str(record.get("input_signature") or ""),
            "terms": [str(label) for label in terms if str(label)],
        }
    return {
        "version": version,
        "generated_at": str(document.get("generated_at") or ""),
        "entry_records": normalized_records,
    }


def save_concept_build_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(concept_build_state_path(root), document)


def default_machine_memory_build_state() -> dict[str, Any]:
    return {"version": 1, "generated_at": "", "source_records": {}, "concept_records": {}}


def load_machine_memory_build_state(root: Path) -> dict[str, Any]:
    document = load_json_document(machine_memory_build_state_path(root))
    if not isinstance(document, dict):
        return default_machine_memory_build_state()
    source_records = document.get("source_records")
    concept_records = document.get("concept_records")
    if not isinstance(source_records, dict) or not isinstance(concept_records, dict):
        return default_machine_memory_build_state()

    normalized_source_records: dict[str, dict[str, str]] = {}
    for entry_id, record in source_records.items():
        if not isinstance(entry_id, str) or not entry_id or not isinstance(record, dict):
            continue
        normalized_source_records[entry_id] = {
            "input_signature": str(record.get("input_signature") or ""),
        }

    normalized_concept_records: dict[str, dict[str, str]] = {}
    for slug, record in concept_records.items():
        if not isinstance(slug, str) or not slug or not isinstance(record, dict):
            continue
        normalized_concept_records[slug] = {
            "input_signature": str(record.get("input_signature") or ""),
        }

    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "source_records": normalized_source_records,
        "concept_records": normalized_concept_records,
    }


def save_machine_memory_build_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(machine_memory_build_state_path(root), document)


def default_ranking_build_state() -> dict[str, Any]:
    return {"version": 1, "generated_at": "", "source_records": {}, "concept_records": {}}


def load_ranking_build_state(root: Path) -> dict[str, Any]:
    document = load_json_document(ranking_build_state_path(root))
    if not isinstance(document, dict):
        return default_ranking_build_state()
    source_records = document.get("source_records")
    concept_records = document.get("concept_records")
    if not isinstance(source_records, dict) or not isinstance(concept_records, dict):
        return default_ranking_build_state()

    normalized_source_records: dict[str, dict[str, Any]] = {}
    for entry_id, record in source_records.items():
        if not isinstance(entry_id, str) or not entry_id or not isinstance(record, dict):
            continue
        summary_or_preview = str(record.get("summary_or_preview") or "")
        concept_terms = record.get("concept_terms")
        if not isinstance(concept_terms, list):
            continue
        normalized_source_records[entry_id] = {
            "input_signature": str(record.get("input_signature") or ""),
            "summary_or_preview": summary_or_preview,
            "concept_terms": [str(term) for term in concept_terms if str(term)],
        }

    normalized_concept_records: dict[str, dict[str, Any]] = {}
    for slug, record in concept_records.items():
        if not isinstance(slug, str) or not slug or not isinstance(record, dict):
            continue
        source_pages = record.get("source_pages")
        if not isinstance(source_pages, list):
            continue
        normalized_concept_records[slug] = {
            "input_signature": str(record.get("input_signature") or ""),
            "title": str(record.get("title") or slug),
            "path": str(record.get("path") or f"wiki/concepts/{slug}.md"),
            "source_pages": [str(path) for path in source_pages if str(path)],
            "content": str(record.get("content") or ""),
        }

    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "source_records": normalized_source_records,
        "concept_records": normalized_concept_records,
    }


def save_ranking_build_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(ranking_build_state_path(root), document)
