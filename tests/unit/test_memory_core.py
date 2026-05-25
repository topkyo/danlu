from __future__ import annotations

from aiwiki import app_memory
from aiwiki.memory.core import (
    machine_memory_digest,
    machine_memory_snapshot_is_reusable,
    reuse_machine_memory_core,
)


def _memory() -> dict:
    return {
        "version": 1,
        "compiled_at": "old",
        "source_nodes": [{"id": "source-a"}],
        "concept_nodes": [{"slug": "alpha"}],
        "judgment_nodes": [{"page_id": "judgment-a"}],
        "edges": {"source_to_concept": []},
        "citation_map": [],
        "term_index": {},
        "drift": {},
        "ignored": "not-digested",
    }


def test_app_memory_core_facades_match_owner():
    memory = _memory()

    assert app_memory.machine_memory_snapshot_is_reusable(memory) == machine_memory_snapshot_is_reusable(memory)
    assert app_memory.reuse_machine_memory_core(memory, "new") == reuse_machine_memory_core(memory, "new")
    assert app_memory.machine_memory_digest(memory) == machine_memory_digest(memory)


def test_machine_memory_core_reuse_contract_and_digest_fields():
    memory = _memory()

    reused = reuse_machine_memory_core(memory, "new")
    assert reused["compiled_at"] == "new"
    assert "judgment_nodes" not in reused
    assert machine_memory_snapshot_is_reusable(reused)

    changed = {**memory, "judgment_nodes": [{"page_id": "judgment-b"}]}
    ignored_changed = {**memory, "ignored": "changed"}
    assert machine_memory_digest(changed) != machine_memory_digest(memory)
    assert machine_memory_digest(ignored_changed) == machine_memory_digest(memory)
