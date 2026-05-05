from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

import pytest

from aiwiki.app_compile_ops import set_active_protocol
from aiwiki.app_protocol import (
    ensure_layout,
    load_protocol_runtime_schema,
    load_protocol_state,
    protocol_runtime_schema_path,
    protocol_state_path,
    save_manifest,
)
from aiwiki.app_state import manifest_path


def _assert_no_tmp_or_partial_residue(directory):
    assert list(directory.glob("*.tmp.*")) == []
    assert list(directory.glob("*.partial*")) == []


def test_save_manifest_atomic_replace_failure_preserves_old(tmp_path, monkeypatch):
    root = tmp_path
    ensure_layout(root)
    save_manifest(root, {"old": True})
    path = manifest_path(root)
    old_bytes = path.read_bytes()

    def fail_replace(_src, _dst):
        raise OSError("simulated")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated"):
        save_manifest(root, {"new": True})

    assert path.read_bytes() == old_bytes
    _assert_no_tmp_or_partial_residue(path.parent)


def test_set_active_protocol_atomic_replace_failure_preserves_old(tmp_path, monkeypatch):
    root = tmp_path
    ensure_layout(root)
    path = protocol_state_path(root)
    old_bytes = path.read_bytes()

    def fail_replace(_src, _dst):
        raise OSError("simulated")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated"):
        set_active_protocol(root, "investing")

    assert path.read_bytes() == old_bytes
    _assert_no_tmp_or_partial_residue(path.parent)


def test_load_protocol_state_normalization_failure_preserves_existing(tmp_path, monkeypatch):
    root = tmp_path
    ensure_layout(root)
    path = protocol_state_path(root)
    path.write_text('{"active_protocol": "missing-protocol"}\n', encoding="utf-8")
    old_bytes = path.read_bytes()

    def fail_replace(_src, _dst):
        raise OSError("simulated")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated"):
        load_protocol_state(root)

    assert path.read_bytes() == old_bytes
    _assert_no_tmp_or_partial_residue(path.parent)


def test_load_protocol_runtime_schema_default_creation_atomic_failure(tmp_path, monkeypatch):
    root = tmp_path
    path = protocol_runtime_schema_path(root, "general")
    assert not path.exists()

    def fail_replace(_src, _dst):
        raise OSError("simulated")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated"):
        load_protocol_runtime_schema(root, "general")

    assert not path.exists()
    _assert_no_tmp_or_partial_residue(path.parent)


def test_protocol_manifest_grep_guard():
    repo = Path(__file__).resolve().parents[1]
    sources = [
        repo / "src" / "aiwiki" / "app_protocol.py",
        repo / "src" / "aiwiki" / "app_compile_ops.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)

    assert re.search(r"\.write_text\(json\.dumps\(", text) is None
    # These two target modules have no legitimate json.dump callers today; keep
    # the guard broad so protocol/manifest state writes cannot regress quietly.
    assert "json.dump(" not in text


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    # scripts/verify.sh uses unittest discover, which does not collect pytest-style
    # tmp_path/monkeypatch tests. Keep the public pytest surface while executing
    # the same cases under unittest coverage.
    del loader, tests, pattern
    suite = unittest.TestSuite()
    tmp_path_monkeypatch_tests = [
        test_save_manifest_atomic_replace_failure_preserves_old,
        test_set_active_protocol_atomic_replace_failure_preserves_old,
        test_load_protocol_state_normalization_failure_preserves_existing,
        test_load_protocol_runtime_schema_default_creation_atomic_failure,
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
    suite.addTest(unittest.FunctionTestCase(test_protocol_manifest_grep_guard))
    return suite
