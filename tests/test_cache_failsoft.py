from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from aiwiki.app_memory import build_machine_memory_query
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import (
    cache_db_path,
    load_archive_candidates_state,
    load_machine_memory,
    load_material_routing_state,
    load_material_state,
)
from aiwiki.compile import compile_wiki
from aiwiki.content.io import ingest_source


def _prepare_project(root: Path) -> str:
    ensure_layout(root)
    source = root / "sample.md"
    source.write_text(
        "# Transformer Scaling\n\nTransformers benefit from scale. Inference costs also rise.\n",
        encoding="utf-8",
    )
    entry = ingest_source(root, str(source), title="Transformer Scaling")
    compile_wiki(root)
    return str(entry["id"])


def _query(root: Path) -> dict:
    return build_machine_memory_query(
        load_machine_memory(root),
        "transformer scale",
        root=root,
        protocol="general",
        material_state=load_material_state(root),
        routing_state=load_material_routing_state(root),
        archive_candidates=load_archive_candidates_state(root),
    )


def _assert_valid_query_result(result: dict, entry_id: str) -> None:
    assert result["ranked_source_ids"]
    assert entry_id in result["ranked_source_ids"]


def _assert_primary_compile_outputs(root: Path, entry_id: str) -> None:
    assert (root / "wiki" / "sources" / f"{entry_id}.md").exists()
    assert (root / ".aiwiki" / "state" / "machine-memory.json").exists()
    assert (root / "wiki" / "indexes" / "machine-memory.md").exists()


def test_query_cache_corrupt_result_payload_falls_back(tmp_path, monkeypatch):
    del monkeypatch
    entry_id = _prepare_project(tmp_path)
    _assert_valid_query_result(_query(tmp_path), entry_id)
    with sqlite3.connect(cache_db_path(tmp_path)) as connection:
        connection.execute("UPDATE cache_query_results SET payload_json = ?", ("{bad",))
        connection.commit()

    _assert_valid_query_result(_query(tmp_path), entry_id)


def test_query_cache_corrupt_snapshot_payload_falls_back(tmp_path, monkeypatch):
    del monkeypatch
    entry_id = _prepare_project(tmp_path)
    with sqlite3.connect(cache_db_path(tmp_path)) as connection:
        connection.execute("UPDATE cache_nodes SET payload_json = ?", ("{bad",))
        connection.commit()

    _assert_valid_query_result(_query(tmp_path), entry_id)


def test_query_cache_corrupt_edges_payload_falls_back(tmp_path, monkeypatch):
    del monkeypatch
    entry_id = _prepare_project(tmp_path)
    with sqlite3.connect(cache_db_path(tmp_path)) as connection:
        connection.execute("UPDATE cache_edges SET payload_json = ?", ("{bad",))
        connection.commit()

    _assert_valid_query_result(_query(tmp_path), entry_id)


def test_query_cache_invalid_sqlite_db_is_miss(tmp_path, monkeypatch):
    del monkeypatch
    entry_id = _prepare_project(tmp_path)
    cache_db_path(tmp_path).write_bytes(b"not a sqlite db at all")

    _assert_valid_query_result(_query(tmp_path), entry_id)


def test_query_cache_write_failure_does_not_break_query(tmp_path, monkeypatch):
    del monkeypatch
    entry_id = _prepare_project(tmp_path)
    with patch("aiwiki.app_cache._connect_cache", side_effect=sqlite3.OperationalError("readonly database")):
        _assert_valid_query_result(_query(tmp_path), entry_id)


def test_cache_status_write_failure_does_not_break_query(tmp_path, monkeypatch):
    del monkeypatch
    entry_id = _prepare_project(tmp_path)
    with patch("aiwiki.app_state.save_json_document", side_effect=OSError("No space left on device")):
        _assert_valid_query_result(_query(tmp_path), entry_id)


def test_concept_build_state_write_failure_does_not_break_compile(tmp_path, monkeypatch):
    ensure_layout(tmp_path)
    source = tmp_path / "sample.md"
    source.write_text("# Transformer Scaling\n\nTransformers benefit from scale.\n", encoding="utf-8")
    entry = ingest_source(tmp_path, str(source), title="Transformer Scaling")
    monkeypatch.setattr(
        "aiwiki.compile.content_step.write_json_document_if_changed_ignoring_generated_timestamps",
        lambda _root, _document: (_ for _ in ()).throw(PermissionError("read-only")),
    )

    compile_wiki(tmp_path)

    _assert_primary_compile_outputs(tmp_path, str(entry["id"]))


def test_machine_memory_build_state_write_failure_does_not_break_compile(tmp_path, monkeypatch):
    ensure_layout(tmp_path)
    source = tmp_path / "sample.md"
    source.write_text("# Transformer Scaling\n\nTransformers benefit from scale.\n", encoding="utf-8")
    entry = ingest_source(tmp_path, str(source), title="Transformer Scaling")
    monkeypatch.setattr(
        "aiwiki.compile.runtime_step.write_json_document_if_changed_ignoring_generated_timestamps",
        lambda _root, _document: (_ for _ in ()).throw(PermissionError("read-only")),
    )

    compile_wiki(tmp_path)

    _assert_primary_compile_outputs(tmp_path, str(entry["id"]))


def test_ranking_build_state_write_failure_does_not_break_compile(tmp_path, monkeypatch):
    ensure_layout(tmp_path)
    source = tmp_path / "sample.md"
    source.write_text("# Transformer Scaling\n\nTransformers benefit from scale.\n", encoding="utf-8")
    entry = ingest_source(tmp_path, str(source), title="Transformer Scaling")
    monkeypatch.setattr(
        "aiwiki.compile.runtime_step.write_json_document_if_changed_ignoring_generated_timestamps",
        lambda _root, _document: (_ for _ in ()).throw(PermissionError("read-only")),
    )

    compile_wiki(tmp_path)

    _assert_primary_compile_outputs(tmp_path, str(entry["id"]))


def test_output_pack_build_state_write_failure_does_not_break_compile(tmp_path, monkeypatch):
    ensure_layout(tmp_path)
    source = tmp_path / "sample.md"
    source.write_text("# Transformer Scaling\n\nTransformers benefit from scale.\n", encoding="utf-8")
    entry = ingest_source(tmp_path, str(source), title="Transformer Scaling")
    monkeypatch.setattr(
        "aiwiki.compile.output_step.write_json_document_if_changed_ignoring_generated_timestamps",
        lambda _root, _document: (_ for _ in ()).throw(PermissionError("read-only")),
    )

    compile_wiki(tmp_path)

    _assert_primary_compile_outputs(tmp_path, str(entry["id"]))


def test_domain_pilot_build_state_write_failure_does_not_break_compile(tmp_path, monkeypatch):
    ensure_layout(tmp_path)
    source = tmp_path / "sample.md"
    source.write_text("# Transformer Scaling\n\nTransformers benefit from scale.\n", encoding="utf-8")
    entry = ingest_source(tmp_path, str(source), title="Transformer Scaling")
    monkeypatch.setattr(
        "aiwiki.compile.output_step.write_json_document_if_changed_ignoring_generated_timestamps",
        lambda _root, _document: (_ for _ in ()).throw(PermissionError("read-only")),
    )

    compile_wiki(tmp_path)

    _assert_primary_compile_outputs(tmp_path, str(entry["id"]))


def test_grep_guard_no_broad_except():
    repo = Path(__file__).resolve().parents[1]
    sources = [
        repo / "src" / "aiwiki" / "app_cache.py",
        repo / "src" / "aiwiki" / "compile" / "content_step.py",
        repo / "src" / "aiwiki" / "compile" / "runtime_step.py",
        repo / "src" / "aiwiki" / "compile" / "output_step.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)

    assert "except Exception" not in text
    assert "except BaseException" not in text


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    suite = unittest.TestSuite()
    tmp_path_monkeypatch_tests = [
        test_query_cache_corrupt_result_payload_falls_back,
        test_query_cache_corrupt_snapshot_payload_falls_back,
        test_query_cache_corrupt_edges_payload_falls_back,
        test_query_cache_invalid_sqlite_db_is_miss,
        test_query_cache_write_failure_does_not_break_query,
        test_cache_status_write_failure_does_not_break_query,
        test_concept_build_state_write_failure_does_not_break_compile,
        test_machine_memory_build_state_write_failure_does_not_break_compile,
        test_ranking_build_state_write_failure_does_not_break_compile,
        test_output_pack_build_state_write_failure_does_not_break_compile,
        test_domain_pilot_build_state_write_failure_does_not_break_compile,
    ]

    def make_case(fn):
        def run() -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                monkeypatch = pytest.MonkeyPatch()
                try:
                    fn(Path(tempdir), monkeypatch)
                finally:
                    monkeypatch.undo()

        run.__name__ = fn.__name__
        return unittest.FunctionTestCase(run)

    for test_fn in tmp_path_monkeypatch_tests:
        suite.addTest(make_case(test_fn))
    suite.addTest(unittest.FunctionTestCase(test_grep_guard_no_broad_except))
    return suite
