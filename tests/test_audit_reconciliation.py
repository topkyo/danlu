from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_execution import append_execution_receipt_history
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import nightly_health_state_path
from aiwiki.app_utils import atomic_append_jsonl, atomic_write_text, relative_path, runtime_write_lock, utc_now
from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH, append_universal_audit_record
from aiwiki.execution.audit_reconciliation import reconcile_execution_receipts
from aiwiki.render.paths import execution_receipt_path
from aiwiki.runner import workflows


class _DummyClient:
    def __init__(self) -> None:
        self.config = type("Config", (), {"model": "dummy-model", "backend": "codex-cli"})()

    def complete(self, system_prompt: str, user_prompt: str):  # noqa: ANN201
        del system_prompt
        del user_prompt
        raise AssertionError("complete should not be called")


def _receipt(root: Path, action_id: str, *, operation: str = "apply", receipt_path: str | None = None) -> dict[str, object]:
    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-test",
        "applied_at": utc_now(),
        "operation": operation,
        "action_id": action_id,
        "title": action_id,
        "status": "resolved",
        "protocol": "general",
        "subject_kind": "test-subject",
        "subject_id": f"subject-{action_id}",
        "receipt_path": receipt_path or relative_path(root, execution_receipt_path(root, action_id)),
    }


def _write_receipt(root: Path, receipt: dict[str, object]) -> Path:
    receipt_path = root / str(receipt["receipt_path"])
    with runtime_write_lock(root):
        atomic_write_text(receipt_path, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt_path


def _append_history(root: Path, receipt: dict[str, object]) -> None:
    append_execution_receipt_history(root, receipt)


def _append_execution_audit(root: Path, receipt: dict[str, object], *, line: int = 1) -> None:
    append_universal_audit_record(
        root,
        source_stream="execution_receipts",
        source_ref=f".aiwiki/state/execution-receipts.jsonl#L{line}",
        document=dict(receipt),
    )


def _audit_rows(root: Path) -> list[dict[str, object]]:
    path = root / AUDIT_STREAM_PATH
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class AuditReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_clean_state_no_findings(self) -> None:
        receipt = _receipt(self.root, "apply-clean")
        _write_receipt(self.root, receipt)
        _append_history(self.root, receipt)
        _append_execution_audit(self.root, receipt)

        result = reconcile_execution_receipts(self.root)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["findings_count"], 0)
        self.assertEqual(result["appended_count"], 0)

    def test_missing_audit_event_emits_marker(self) -> None:
        receipt = _receipt(self.root, "apply-missing-audit")
        _write_receipt(self.root, receipt)
        with runtime_write_lock(self.root):
            atomic_append_jsonl(self.root / ".aiwiki" / "state" / "execution-receipts.jsonl", receipt)

        result = reconcile_execution_receipts(self.root)

        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["findings"][0]["reason"], "audit_event_missing")
        self.assertEqual(result["appended_count"], 1)

    def test_missing_receipt_file_emits_marker(self) -> None:
        receipt = _receipt(self.root, "apply-missing")
        receipt_path = _write_receipt(self.root, receipt)
        _append_history(self.root, receipt)
        _append_execution_audit(self.root, receipt)
        receipt_path.unlink()

        result = reconcile_execution_receipts(self.root)

        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["appended_count"], 1)
        self.assertEqual(result["findings"][0]["reason"], "receipt_path_missing")
        marker = _audit_rows(self.root)[-1]
        self.assertEqual(marker["source_stream"], "audit_reconciliation")
        self.assertEqual(marker["event_type"], "receipt_false_success_detected")
        self.assertEqual(marker["target_action_id"], "apply-missing")
        self.assertEqual(marker["target_receipt_path"], receipt["receipt_path"])
        self.assertEqual(marker["target_operation"], "apply")
        self.assertEqual(marker["reason"], "receipt_path_missing")
        self.assertEqual(marker["subject"], {"kind": "test-subject", "id": "subject-apply-missing"})
        self.assertTrue(marker["detected_at"])

    def test_marker_idempotent_across_runs(self) -> None:
        receipt = _receipt(self.root, "apply-idempotent")
        receipt_path = _write_receipt(self.root, receipt)
        _append_history(self.root, receipt)
        _append_execution_audit(self.root, receipt)
        receipt_path.unlink()

        first = reconcile_execution_receipts(self.root)
        second = reconcile_execution_receipts(self.root)

        self.assertEqual(first["appended_count"], 1)
        self.assertEqual(second["findings_count"], 1)
        self.assertEqual(second["appended_count"], 0)
        self.assertGreaterEqual(second["skipped_duplicate_count"], 1)

    def test_revert_after_apply_is_not_false_success(self) -> None:
        apply_receipt = _receipt(self.root, "apply-then-revert")
        _write_receipt(self.root, apply_receipt)
        _append_history(self.root, apply_receipt)
        _append_execution_audit(self.root, apply_receipt, line=1)
        revert_receipt = _receipt(self.root, "revert-then-revert", operation="revert")
        _write_receipt(self.root, revert_receipt)
        _append_history(self.root, revert_receipt)
        _append_execution_audit(self.root, revert_receipt, line=2)

        result = reconcile_execution_receipts(self.root)

        self.assertEqual(result["findings_count"], 0)
        self.assertEqual(result["appended_count"], 0)

    def test_path_traversal_receipt_path_flagged(self) -> None:
        receipt = _receipt(self.root, "apply-traversal", receipt_path="../etc/passwd")
        with runtime_write_lock(self.root):
            atomic_append_jsonl(self.root / ".aiwiki" / "state" / "execution-receipts.jsonl", receipt)

        # Guard against any read outside the test root. Reconciliation must
        # reject the traversal path before reaching read_text on it.
        root_resolved = self.root.resolve()
        original_read_text = Path.read_text

        def guarded_read_text(self: Path, *args: object, **kwargs: object) -> str:
            try:
                self.resolve().relative_to(root_resolved)
            except ValueError as exc:
                raise AssertionError(f"unexpected read of {self}") from exc
            return original_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

        with patch.object(Path, "read_text", autospec=True, side_effect=guarded_read_text):
            result = reconcile_execution_receipts(self.root)

        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["findings"][0]["reason"], "path_traversal_suspicious")
        self.assertEqual(result["appended_count"], 1)

    def test_receipt_content_mismatch_flagged(self) -> None:
        receipt = _receipt(self.root, "apply-mismatch")
        receipt_path = _write_receipt(self.root, receipt)
        _append_history(self.root, receipt)
        _append_execution_audit(self.root, receipt)
        mismatched = dict(receipt)
        mismatched["action_id"] = "different-action"
        with runtime_write_lock(self.root):
            atomic_write_text(receipt_path, json.dumps(mismatched, indent=2, sort_keys=True) + "\n")

        result = reconcile_execution_receipts(self.root)

        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["findings"][0]["reason"], "receipt_content_mismatch")

    def test_reconciliation_failure_does_not_break_nightly(self) -> None:
        def boom(root: Path) -> dict[str, object]:
            del root
            raise RuntimeError("reconcile boom")

        with patch.dict(os.environ, {"AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS": "0"}):
            patcher = patch.object(workflows, "reconcile_execution_receipts", side_effect=boom)
            with patcher:
                result = workflows.run_nightly(self.root, client=_DummyClient(), compile_limit=0, semantic_lint=False)

        state = json.loads(nightly_health_state_path(self.root).read_text(encoding="utf-8"))
        self.assertEqual(result["agent_loop"]["status"], "ok")
        self.assertEqual(state["audit_reconciliation"], {"status": "failed", "error": "reconcile boom"})

    def test_revert_missing_receipt_is_scanned(self) -> None:
        receipt = _receipt(self.root, "revert-missing", operation="revert")
        with runtime_write_lock(self.root):
            atomic_append_jsonl(self.root / ".aiwiki" / "state" / "execution-receipts.jsonl", receipt)

        result = reconcile_execution_receipts(self.root)

        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["findings"][0]["reason"], "receipt_path_missing")
        self.assertEqual(result["appended_count"], 1)

    def test_orphan_receipt_file_emits_marker(self) -> None:
        receipt = _receipt(self.root, "orphan-file")
        _write_receipt(self.root, receipt)

        result = reconcile_execution_receipts(self.root)

        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["findings"][0]["reason"], "orphan_receipt_file")
        self.assertEqual(result["appended_count"], 1)

    def test_orphan_receipt_file_scan_includes_subdirectories(self) -> None:
        receipt = _receipt(
            self.root,
            "nested-orphan",
            operation="revert",
            receipt_path="output/control/execution-receipts/reverts/nested-orphan.json",
        )
        _write_receipt(self.root, receipt)

        result = reconcile_execution_receipts(self.root)

        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["findings"][0]["reason"], "orphan_receipt_file")
        self.assertEqual(result["findings"][0]["source_ref"], receipt["receipt_path"])

    def test_orphan_receipt_file_scan_does_not_read_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as outside_dir:
            outside = Path(outside_dir) / "outside.json"
            outside.write_text(json.dumps({"action_id": "outside"}), encoding="utf-8")
            link = self.root / "output" / "control" / "execution-receipts" / "outside.json"
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(outside)

            root_resolved = self.root.resolve()
            original_read_text = Path.read_text

            def guarded_read_text(self: Path, *args: object, **kwargs: object) -> str:
                try:
                    self.resolve().relative_to(root_resolved)
                except ValueError as exc:
                    raise AssertionError(f"unexpected read of {self}") from exc
                return original_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

            with patch.object(Path, "read_text", autospec=True, side_effect=guarded_read_text):
                result = reconcile_execution_receipts(self.root)

        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["findings"][0]["reason"], "path_traversal_suspicious")

    def test_orphan_audit_record_emits_marker(self) -> None:
        receipt = _receipt(self.root, "orphan-audit")
        _append_execution_audit(self.root, receipt, line=99)

        result = reconcile_execution_receipts(self.root)

        self.assertEqual(result["findings_count"], 1)
        self.assertEqual(result["findings"][0]["reason"], "orphan_audit_record")
        self.assertEqual(result["appended_count"], 1)

    def test_non_success_operation_history_is_not_reported_as_orphan(self) -> None:
        receipt = _receipt(self.root, "preview-clean", operation="preview")
        _write_receipt(self.root, receipt)
        _append_history(self.root, receipt)

        result = reconcile_execution_receipts(self.root)

        self.assertEqual(result["findings_count"], 0)
        self.assertEqual(result["appended_count"], 0)
