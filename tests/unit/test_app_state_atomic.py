from __future__ import annotations

import json

from aiwiki.app_state import (
    concept_rewrite_state_path,
    load_concept_rewrite_state,
    load_json_document,
    load_machine_memory_action_state,
    load_manual_link_state,
    machine_memory_action_state_path,
    manual_link_state_path,
    save_concept_rewrite_state,
    save_json_document,
    save_machine_memory_action_state,
    save_manual_link_state,
)


def _assert_no_tmp_residue(directory):
    assert list(directory.glob("*.tmp.*")) == []


def test_save_json_document_writes_atomically_and_loads_back(tmp_path):
    path = tmp_path / ".aiwiki" / "state" / "document.json"
    document = {"version": 1, "items": [{"id": "a"}]}

    save_json_document(path, document)

    assert path.read_text(encoding="utf-8") == '{\n  "items": [\n    {\n      "id": "a"\n    }\n  ],\n  "version": 1\n}\n'
    _assert_no_tmp_residue(path.parent)
    assert load_json_document(path) == document


def test_save_machine_memory_action_state_writes_atomically_and_loads_back(tmp_path):
    document = {"version": 1, "actions": [{"id": "act-1", "active": True}]}
    path = machine_memory_action_state_path(tmp_path)

    save_machine_memory_action_state(tmp_path, document)

    assert path.read_text(encoding="utf-8") == json.dumps(document, indent=2, sort_keys=True) + "\n"
    _assert_no_tmp_residue(path.parent)
    assert load_machine_memory_action_state(tmp_path) == document


def test_save_concept_rewrite_state_writes_atomically_and_loads_back(tmp_path):
    document = {"version": 1, "proposals": [{"id": "rewrite-1", "status": "pending"}]}
    path = concept_rewrite_state_path(tmp_path)

    save_concept_rewrite_state(tmp_path, document)

    assert path.read_text(encoding="utf-8") == json.dumps(document, indent=2, sort_keys=True) + "\n"
    _assert_no_tmp_residue(path.parent)
    assert load_concept_rewrite_state(tmp_path) == document


def test_save_manual_link_state_writes_atomically_and_loads_back(tmp_path):
    document = {"version": 1, "source_to_concept": [{"source": "wiki/sources/a.md", "concept": "alpha"}]}
    path = manual_link_state_path(tmp_path)

    save_manual_link_state(tmp_path, document)

    assert path.read_text(encoding="utf-8") == json.dumps(document, indent=2, sort_keys=True) + "\n"
    _assert_no_tmp_residue(path.parent)
    assert load_manual_link_state(tmp_path) == document


def test_save_json_document_fsync_failure_preserves_original(tmp_path, monkeypatch):
    """fsync OSError during saver must raise and leave on-disk state untouched + no tmp residue."""
    import os

    path = tmp_path / ".aiwiki" / "state" / "doc.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"version": 0, "items": []}\n', encoding="utf-8")

    def fail_fsync(_fd):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", fail_fsync)

    import pytest as _pytest

    with _pytest.raises(OSError, match="disk full"):
        save_json_document(path, {"version": 1, "items": [{"id": "new"}]})

    assert path.read_text(encoding="utf-8") == '{"version": 0, "items": []}\n'
    _assert_no_tmp_residue(path.parent)
