from __future__ import annotations

import json
import logging
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


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


class _capture_archive_warnings:
    def __enter__(self) -> list[str]:
        self.handler = _ListHandler()
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger = logging.getLogger("aiwiki.execution.archive")
        self.prev_level = self.logger.level
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.WARNING)
        return self.handler.records

    def __exit__(self, *exc: object) -> None:
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self.prev_level)


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


def test_apply_phase2_history_failure_keeps_state_and_logs(tmp_path: Path) -> None:
    # R95.1: history append moved to phase 2 best-effort. Failure must NOT
    # raise — state is SOT and caller-retry would fail at active-archive
    # check. Per-step warning preserves observability.
    entry = _prepare_ready_archive_candidate(tmp_path)

    with patch(
        "aiwiki.execution.archive.append_execution_receipt_history",
        side_effect=RuntimeError("boom"),
    ), _capture_archive_warnings() as captured:
        result = apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")

    assert result["status"] == "archived"
    archive_entry = _archive_entry(tmp_path, entry["id"])
    assert archive_entry is not None
    assert archive_entry["active"] is True
    receipt_path = tmp_path / str(result["receipt_path"])
    assert receipt_path.exists()
    assert any(
        "phase 2 step append_execution_receipt_history failed" in msg for msg in captured
    ), captured


def test_apply_state_save_failure_unlinks_orphan_receipt(tmp_path: Path) -> None:
    # R95.1 BLOCK fix: phase 1 is receipt write -> state save. State save
    # failure must unlink the orphan receipt so we don't leave a false
    # apply audit claiming success when state never committed.
    entry = _prepare_ready_archive_candidate(tmp_path)
    receipts_dir = tmp_path / "output" / "control" / "execution-receipts"
    before = {p.name for p in receipts_dir.glob("*.json")} if receipts_dir.exists() else set()
    history_path = tmp_path / "output" / "control" / "execution-receipts.jsonl"
    history_before = history_path.read_text(encoding="utf-8") if history_path.exists() else ""

    with patch(
        "aiwiki.execution.archive.save_material_archive_state",
        side_effect=OSError("simulated state save failure"),
    ), patch(
        "aiwiki.execution.archive.append_execution_receipt_history",
    ) as history_spy:
        with pytest.raises(OSError, match="simulated state save failure"):
            apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")

    after = {p.name for p in receipts_dir.glob("*.json")} if receipts_dir.exists() else set()
    assert after == before, f"orphan apply receipt left behind: {after - before}"
    assert _archive_entry(tmp_path, entry["id"]) is None
    # NIT-1: false-audit guard — history must NOT have been appended when
    # state never committed.
    history_spy.assert_not_called()
    history_after = history_path.read_text(encoding="utf-8") if history_path.exists() else ""
    assert history_after == history_before, "false history record left behind"


def test_revert_phase2_history_failure_keeps_state_and_logs(tmp_path: Path) -> None:
    # R95.1: history append moved to phase 2 best-effort.
    entry = _prepare_ready_archive_candidate(tmp_path)
    apply_result = apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")
    apply_receipt_path = tmp_path / str(apply_result["receipt_path"])
    apply_receipt_before = json.loads(apply_receipt_path.read_text(encoding="utf-8"))

    with patch(
        "aiwiki.execution.archive.append_execution_receipt_history",
        side_effect=RuntimeError("boom"),
    ), _capture_archive_warnings() as captured:
        revert_result = revert_material_archive(tmp_path, entry["id"], note="Restore archived source.")

    assert revert_result["status"] == "cold"
    archive_entry = _archive_entry(tmp_path, entry["id"])
    assert archive_entry is not None
    assert archive_entry["active"] is False
    # apply receipt unchanged
    assert json.loads(apply_receipt_path.read_text(encoding="utf-8")) == apply_receipt_before
    assert any(
        "phase 2 step append_execution_receipt_history failed" in msg for msg in captured
    ), captured


def test_revert_state_save_failure_unlinks_orphan_revert_receipt(tmp_path: Path) -> None:
    # R95.1 BLOCK fix: revert phase 1 is revert-receipt write -> state save.
    # State save failure must unlink the orphan revert receipt.
    entry = _prepare_ready_archive_candidate(tmp_path)
    apply_result = apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")
    apply_receipt_path = tmp_path / str(apply_result["receipt_path"])
    apply_receipt_before = json.loads(apply_receipt_path.read_text(encoding="utf-8"))
    state_before = load_material_archive_state(tmp_path)
    expected_revert_path = apply_receipt_path.parent / "reverts" / apply_receipt_path.name
    history_path = tmp_path / "output" / "control" / "execution-receipts.jsonl"
    history_before = history_path.read_text(encoding="utf-8") if history_path.exists() else ""

    with patch(
        "aiwiki.execution.archive.save_material_archive_state",
        side_effect=OSError("simulated state save failure"),
    ), patch(
        "aiwiki.execution.archive.append_execution_receipt_history",
    ) as history_spy:
        with pytest.raises(OSError, match="simulated state save failure"):
            revert_material_archive(tmp_path, entry["id"], note="Restore archived source.")

    assert not expected_revert_path.exists(), "orphan revert receipt left behind"
    assert load_material_archive_state(tmp_path) == state_before
    assert json.loads(apply_receipt_path.read_text(encoding="utf-8")) == apply_receipt_before
    # NIT-1: false-audit guard — revert history must NOT be appended when
    # state never committed.
    history_spy.assert_not_called()
    history_after = history_path.read_text(encoding="utf-8") if history_path.exists() else ""
    assert history_after == history_before, "false revert history record left behind"


def test_revert_rollback_failure_preserves_original_exception(tmp_path: Path) -> None:
    # NIT-2: symmetric coverage of test_apply_rollback_failure_preserves_original_exception.
    # Revert path: state save fails AND revert-receipt unlink also fails.
    # Original state-save exception must propagate; rollback failure logged.
    entry = _prepare_ready_archive_candidate(tmp_path)
    apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")
    real_unlink = Path.unlink

    def flaky_unlink(self: Path, missing_ok: bool = False) -> None:
        if "reverts" in self.parts and self.suffix == ".json":
            raise OSError("simulated revert unlink failure")
        real_unlink(self, missing_ok=missing_ok)

    with patch(
        "aiwiki.execution.archive.save_material_archive_state",
        side_effect=OSError("simulated state save failure"),
    ), patch.object(Path, "unlink", flaky_unlink), _capture_archive_warnings() as captured:
        with pytest.raises(OSError, match="simulated state save failure"):
            revert_material_archive(tmp_path, entry["id"], note="Restore archived source.")

    assert any("revert receipt unlink failed" in msg for msg in captured), captured


def test_apply_rollback_failure_preserves_original_exception(tmp_path: Path) -> None:
    # R95.1: when state save fails AND receipt unlink also fails, the
    # original state-save exception must propagate; rollback failure is
    # logged but not re-raised.
    entry = _prepare_ready_archive_candidate(tmp_path)
    real_unlink = Path.unlink

    def flaky_unlink(self: Path, missing_ok: bool = False) -> None:
        if "execution-receipts" in self.parts and self.suffix == ".json":
            raise OSError("simulated unlink failure")
        real_unlink(self, missing_ok=missing_ok)

    with patch(
        "aiwiki.execution.archive.save_material_archive_state",
        side_effect=OSError("simulated state save failure"),
    ), patch.object(Path, "unlink", flaky_unlink), _capture_archive_warnings() as captured:
        with pytest.raises(OSError, match="simulated state save failure"):
            apply_material_archive(tmp_path, entry["id"], note="Archive stale source.")

    assert any("receipt unlink failed" in msg for msg in captured), captured


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
        test_apply_phase2_history_failure_keeps_state_and_logs,
        test_apply_state_save_failure_unlinks_orphan_receipt,
        test_revert_phase2_history_failure_keeps_state_and_logs,
        test_revert_state_save_failure_unlinks_orphan_revert_receipt,
        test_apply_rollback_failure_preserves_original_exception,
        test_revert_rollback_failure_preserves_original_exception,
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
