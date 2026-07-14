from __future__ import annotations

from aiwiki import app_memory
from aiwiki.memory.health import build_machine_memory_health


def test_app_memory_health_facade_matches_owner():
    memory = {
        "source_nodes": [
            {"id": "source-a", "title": "Source A", "source_page": "wiki/sources/source-a.md"},
            {"id": "source-b", "title": "Source B", "source_page": "wiki/sources/source-b.md"},
        ],
        "concept_nodes": [
            {"slug": "alpha", "title": "Alpha"},
            {"slug": "beta", "title": "Beta"},
        ],
        "edges": {
            "source_to_concept": [{"source_id": "source-a", "concept_slug": "alpha"}],
            "concept_to_concept": [{"from": "alpha", "to": "beta"}],
            "concept_causal": [],
            "source_to_judgment": [],
            "judgment_to_judgment": [],
            "judgment_to_decision": [],
        },
        "term_index": {"alpha": {"source_ids": ["source-b"], "concept_slugs": ["alpha"]}},
        "drift": {"sources_without_concepts": ["source-b"]},
    }

    owner = build_machine_memory_health(memory)
    facade = app_memory.build_machine_memory_health(memory)

    assert facade == owner
    assert facade["isolated_source_ids"] == ["source-b"]
    assert facade["link_suggestions"][0]["source_id"] == "source-b"
    assert "hub_concepts" in facade
    assert "action_counts" in facade
