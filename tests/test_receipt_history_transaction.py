from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_execution import (
    ReceiptHistoryAuditError,
    ReceiptHistoryRollbackError,
    append_execution_receipt_history,
)
from aiwiki.app_state import execution_receipt_history_path
from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH


class ReceiptHistoryTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt = {
            "version": 1,
            "kind": "execution-receipt",
            "generated_by": "test",
            "applied_at": "2026-05-04T00:00:00Z",
            "operation": "test",
            "action_id": "rcp-test",
            "revert_supported": True,
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _receipt_lines(self) -> list[dict[str, object]]:
        path = execution_receipt_history_path(self.root)
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _audit_lines(self) -> list[dict[str, object]]:
        path = self.root / AUDIT_STREAM_PATH
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_audit_failure_rolls_back_primary(self) -> None:
        path = execution_receipt_history_path(self.root)
        append_execution_receipt_history(self.root, self.receipt)
        size_before = path.stat().st_size

        with patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("disk full")):
            with self.assertRaises(ReceiptHistoryAuditError) as ctx:
                append_execution_receipt_history(self.root, {**self.receipt, "action_id": "rcp-2"})

        self.assertIn("OSError('disk full')", str(ctx.exception))
        self.assertEqual(path.stat().st_size, size_before)
        self.assertNotIn("rcp-2", path.read_text(encoding="utf-8"))

    def test_truncate_failure_raises_rollback_error(self) -> None:
        append_execution_receipt_history(self.root, self.receipt)

        with (
            patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")),
            patch("aiwiki.app_execution._durable_truncate", side_effect=OSError("truncate fail")),
        ):
            with self.assertRaises(ReceiptHistoryRollbackError) as ctx:
                append_execution_receipt_history(self.root, {**self.receipt, "action_id": "rcp-3"})

        message = str(ctx.exception)
        self.assertIn("OSError('audit fail')", message)
        self.assertIn("OSError('truncate fail')", message)

    def test_rollback_uses_durable_truncate_helper(self) -> None:
        path = execution_receipt_history_path(self.root)
        append_execution_receipt_history(self.root, self.receipt)
        size_before = path.stat().st_size

        def truncate_without_fsync(truncate_path: Path, size: int) -> None:
            with open(truncate_path, "r+b") as handle:
                handle.truncate(size)

        with (
            patch("aiwiki.app_execution._durable_truncate", side_effect=truncate_without_fsync) as durable_truncate,
            patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")),
        ):
            with self.assertRaises(ReceiptHistoryAuditError):
                append_execution_receipt_history(self.root, {**self.receipt, "action_id": "rcp-fsync"})

        durable_truncate.assert_called_once_with(path, size_before)
        self.assertEqual(path.stat().st_size, size_before)
        self.assertNotIn("rcp-fsync", path.read_text(encoding="utf-8"))

    def test_success_path_writes_primary_and_audit_with_line_number(self) -> None:
        append_execution_receipt_history(self.root, self.receipt)
        append_execution_receipt_history(self.root, {**self.receipt, "action_id": "rcp-2"})

        receipt_lines = self._receipt_lines()
        self.assertEqual([line["action_id"] for line in receipt_lines], ["rcp-test", "rcp-2"])

        audit_lines = self._audit_lines()
        self.assertEqual(audit_lines[-1]["source_stream"], "execution_receipts")
        self.assertEqual(audit_lines[-1]["source_ref"], ".aiwiki/state/execution-receipts.jsonl#L2")
        self.assertEqual(audit_lines[-1]["subject"], {"kind": "execution-receipt", "id": "rcp-2"})

    def test_primary_not_exists_before_audit_failure_leaves_empty_primary(self) -> None:
        path = execution_receipt_history_path(self.root)
        self.assertFalse(path.exists())

        with patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")):
            with self.assertRaises(ReceiptHistoryAuditError):
                append_execution_receipt_history(self.root, self.receipt)

        self.assertTrue(path.exists())
        self.assertEqual(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
