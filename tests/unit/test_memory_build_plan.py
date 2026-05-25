from __future__ import annotations

import json

from aiwiki import app_memory
from aiwiki.app_state import machine_memory_build_state_path
from aiwiki.memory.build_plan import plan_machine_memory_build


def test_app_memory_build_plan_facade_matches_owner_and_detects_changes(tmp_path):
    entries = [
        {
            "id": "source-a",
            "title": "Source A",
            "source_type": "note",
            "source_page": "wiki/sources/source-a.md",
            "stored_path": "raw/source-a.md",
            "tags": ["alpha"],
        },
        {
            "id": "source-b",
            "title": "Source B",
            "source_type": "note",
            "source_page": "wiki/sources/source-b.md",
            "stored_path": "raw/source-b.md",
            "tags": [],
        },
    ]
    concepts = [
        {
            "slug": "alpha",
            "title": "Alpha",
            "entry_ids": ["source-a"],
            "source_pages": ["wiki/sources/source-a.md"],
            "terms": ["alpha"],
            "causal_links": [],
        },
        {
            "slug": "beta",
            "title": "Beta",
            "entry_ids": ["source-b"],
            "source_pages": ["wiki/sources/source-b.md"],
            "terms": ["beta"],
            "causal_links": [],
        },
    ]
    previews = {"source-a": "preview a", "source-b": "preview b"}
    entry_terms = {"source-a": ["alpha"], "source-b": ["beta"]}
    baseline = plan_machine_memory_build(
        tmp_path,
        entries,
        concepts,
        previews,
        entry_terms,
        generated_at="2026-05-25T00:00:00+00:00",
    )

    state_path = machine_memory_build_state_path(tmp_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    stale_state = {
        "version": 1,
        "generated_at": "old",
        "source_records": {
            "source-a": baseline["state_document"]["source_records"]["source-a"],
            "removed-source": {"input_signature": "old-source"},
        },
        "concept_records": {
            "alpha": baseline["state_document"]["concept_records"]["alpha"],
            "removed-concept": {"input_signature": "old-concept"},
        },
    }
    state_path.write_text(json.dumps(stale_state), encoding="utf-8")

    owner = plan_machine_memory_build(
        tmp_path,
        entries,
        concepts,
        previews,
        entry_terms,
        generated_at="2026-05-25T01:00:00+00:00",
    )
    facade = app_memory.plan_machine_memory_build(
        tmp_path,
        entries,
        concepts,
        previews,
        entry_terms,
        generated_at="2026-05-25T01:00:00+00:00",
    )

    assert facade == owner
    assert facade["clean_source_ids"] == ["source-a"]
    assert facade["dirty_source_ids"] == ["source-b"]
    assert facade["removed_source_ids"] == ["removed-source"]
    assert facade["clean_concept_slugs"] == ["alpha"]
    assert facade["dirty_concept_slugs"] == ["beta"]
    assert facade["removed_concept_slugs"] == ["removed-concept"]
    assert facade["inputs_clean"] is False
