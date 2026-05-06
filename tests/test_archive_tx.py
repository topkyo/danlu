from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwiki.app_compile_ops import set_active_protocol
from aiwiki.app_content import ingest_source
from aiwiki.app_protocol import ensure_layout, save_manifest
from aiwiki.app_state import load_manifest, load_material_archive_state, material_archive_action_id
from aiwiki.compile.pipeline import compile_wiki
from aiwiki.execution.archive import apply_material_archive, revert_material_archive


def _prepare_ready_archive_candidate(root: Path) -> dict[str, str]:
    ensure_layout(root)
    source = root / "archive-candidate.md"
    source.write_text("# Obscure Legacy Note\n\nMisc.\n", encoding="utf-8")
    entry = ingest_source(root, str(source), title="Obscure Legacy Note")
    compile_wiki(root)
    manifest = load_manifest(root)
    for manifest_entry in manifest["entries"]:
        if manifest_entry["id"] == entry["id"]:
            manifest_entry["imported_at"] = "2025-01-01T00:00:00+00:00"
            manifest_entry["updated_at"] = "2025-01-01T00:00:00+00:00"
            break
    save_manifest(root, manifest)
    set_active_protocol(root, "investing")
    compile_wiki(root)
    compile_wiki(root)
    return entry


def _archive_entry(root: Path, entry_id: str) -> dict[str, object] | None:
    state = load_material_archive_state(root)
    return next((item for item in state["entries"] if item.get("entry_id") == entry_id), None)


def test_apply_writes_atomic_receipt_and_commits_state(tmp_path: Path) -> None:
    entry = _prepare_ready_archive_candidate(tmp_path)

    result = apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")

    receipt_path = tmp_path / str(result["receipt_path"])
    assert receipt_path.exists()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["operation"] == "apply"
    archive_entry = _archive_entry(tmp_path, entry["id"])
    assert archive_entry is not None
    assert archive_entry["active"] is True
    assert archive_entry["last_receipt_path"] == str(result["receipt_path"])


def test_revert_preserves_apply_receipt_at_original_path(tmp_path: Path) -> None:
    entry = _prepare_ready_archive_candidate(tmp_path)
    apply_result = apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")
    apply_receipt_path = tmp_path / str(apply_result["receipt_path"])
    apply_receipt_before = json.loads(apply_receipt_path.read_text(encoding="utf-8"))

    revert_result = revert_material_archive(tmp_path, entry["id"], note="Restore archived source.")

    assert apply_receipt_path.exists()
    assert json.loads(apply_receipt_path.read_text(encoding="utf-8")) == apply_receipt_before
    revert_receipt = json.loads((tmp_path / str(revert_result["receipt_path"])).read_text(encoding="utf-8"))
    assert revert_receipt["operation"] == "revert"
    archive_entry = _archive_entry(tmp_path, entry["id"])
    assert archive_entry is not None
    assert archive_entry["active"] is False
    assert archive_entry["last_receipt_path"] == str(revert_result["receipt_path"])


def test_revert_writes_to_reverts_subdir_with_same_filename(tmp_path: Path) -> None:
    entry = _prepare_ready_archive_candidate(tmp_path)
    apply_result = apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")
    apply_receipt_path = tmp_path / str(apply_result["receipt_path"])

    revert_result = revert_material_archive(tmp_path, entry["id"], note="Restore archived source.")

    revert_receipt_path = tmp_path / str(revert_result["receipt_path"])
    assert revert_receipt_path == apply_receipt_path.parent / "reverts" / apply_receipt_path.name
    assert revert_receipt_path.exists()


def test_revert_then_revert_again_fails_because_last_receipt_is_revert_op(tmp_path: Path) -> None:
    entry = _prepare_ready_archive_candidate(tmp_path)
    apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")
    revert_material_archive(tmp_path, entry["id"], note="Restore archived source.")
    archive_entry = _archive_entry(tmp_path, entry["id"])
    assert archive_entry is not None
    archive_entry["active"] = True
    state = load_material_archive_state(tmp_path)
    for index, item in enumerate(state["entries"]):
        if item.get("entry_id") == entry["id"]:
            state["entries"][index] = archive_entry
            break
    from aiwiki.app_state import save_material_archive_state

    save_material_archive_state(tmp_path, state)

    with pytest.raises(RuntimeError, match="Only the latest apply archive receipt can be reverted"):
        revert_material_archive(tmp_path, entry["id"], note="Restore again.")


def test_apply_failure_at_history_append_leaves_no_state_entry(tmp_path: Path) -> None:
    entry = _prepare_ready_archive_candidate(tmp_path)

    with patch(
        "aiwiki.execution.archive.append_execution_receipt_history",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")

    assert _archive_entry(tmp_path, entry["id"]) is None


def test_revert_failure_at_history_append_leaves_state_unchanged_and_apply_receipt_intact(tmp_path: Path) -> None:
    entry = _prepare_ready_archive_candidate(tmp_path)
    apply_result = apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")
    apply_receipt_path = tmp_path / str(apply_result["receipt_path"])
    apply_receipt_before = json.loads(apply_receipt_path.read_text(encoding="utf-8"))
    state_before = load_material_archive_state(tmp_path)

    with patch(
        "aiwiki.execution.archive.append_execution_receipt_history",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            revert_material_archive(tmp_path, entry["id"], note="Restore archived source.")

    assert load_material_archive_state(tmp_path) == state_before
    assert json.loads(apply_receipt_path.read_text(encoding="utf-8")) == apply_receipt_before


def test_revert_receipt_path_pattern_exact(tmp_path: Path) -> None:
    entry = _prepare_ready_archive_candidate(tmp_path)
    apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")

    result = revert_material_archive(tmp_path, entry["id"], note="Restore archived source.")

    expected = f"output/control/execution-receipts/reverts/{material_archive_action_id(entry['id'])}.json"
    assert result["receipt_path"] == expected


def test_apply_uses_atomic_write_text_for_receipt() -> None:
    source = (Path(__file__).resolve().parents[1] / "src/aiwiki/execution/archive.py").read_text(
        encoding="utf-8"
    )
    assert re.search(r"\breceipt_path\.write_text\(\s*json\.dumps\(", source) is None
    assert "atomic_write_text(receipt_path," in source


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    suite = unittest.TestSuite()
    tmp_path_tests = [
        test_apply_writes_atomic_receipt_and_commits_state,
        test_revert_preserves_apply_receipt_at_original_path,
        test_revert_writes_to_reverts_subdir_with_same_filename,
        test_revert_then_revert_again_fails_because_last_receipt_is_revert_op,
        test_apply_failure_at_history_append_leaves_no_state_entry,
        test_revert_failure_at_history_append_leaves_state_unchanged_and_apply_receipt_intact,
        test_revert_receipt_path_pattern_exact,
    ]

    def make_case(fn):
        def run() -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                fn(Path(tempdir))

        run.__name__ = fn.__name__
        return unittest.FunctionTestCase(run)

    for test_fn in tmp_path_tests:
        suite.addTest(make_case(test_fn))
    suite.addTest(unittest.FunctionTestCase(test_apply_uses_atomic_write_text_for_receipt))
    return suite
