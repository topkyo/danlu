from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_utils import AuditMirrorError, AuditMirrorRollbackError
from aiwiki.runner.receipts import _append_llm_receipt


class LlmReceiptTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log_path = self.root / ".aiwiki/logs/llm-receipts.jsonl"
        self.event = {
            "kind": "llm_attempt",
            "status": "success",
            "detail": "test-base",
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_audit_failure_rolls_back_primary(self) -> None:
        _append_llm_receipt(self.root, self.event)
        size_before = self.log_path.stat().st_size

        with patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")):
            with self.assertRaises(AuditMirrorError) as ctx:
                _append_llm_receipt(self.root, {**self.event, "detail": "rolled-back"})

        self.assertIn("OSError('audit fail')", str(ctx.exception))
        self.assertEqual(self.log_path.stat().st_size, size_before)
        self.assertNotIn("rolled-back", self.log_path.read_text(encoding="utf-8"))

    def test_truncate_failure_raises_rollback_error(self) -> None:
        _append_llm_receipt(self.root, self.event)

        with (
            patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")),
            patch("aiwiki.app_utils._durable_truncate", side_effect=OSError("truncate fail")),
        ):
            with self.assertRaises(AuditMirrorRollbackError) as ctx:
                _append_llm_receipt(self.root, {**self.event, "detail": "double-fail"})

        msg = str(ctx.exception)
        self.assertIn("OSError('audit fail')", msg)
        self.assertIn("OSError('truncate fail')", msg)

    def test_success_path_writes_primary(self) -> None:
        _append_llm_receipt(self.root, self.event)
        text = self.log_path.read_text(encoding="utf-8")
        self.assertIn("test-base", text)

    def test_primary_not_exists_before(self) -> None:
        self.assertFalse(self.log_path.exists())

        with patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")):
            with self.assertRaises(AuditMirrorError):
                _append_llm_receipt(self.root, self.event)

        if self.log_path.exists():
            self.assertEqual(self.log_path.stat().st_size, 0)

    def test_rollback_uses_durable_truncate_helper(self) -> None:
        """防退化：未来有人改回 bare os.truncate 会被这条测试拦截。"""
        _append_llm_receipt(self.root, self.event)

        def truncate_without_fsync(path: Path, size: int) -> None:
            with open(path, "r+b") as handle:
                handle.truncate(size)

        with patch("aiwiki.app_utils._durable_truncate", side_effect=truncate_without_fsync) as durable_truncate:
            with patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")):
                with self.assertRaises(AuditMirrorError):
                    _append_llm_receipt(self.root, {**self.event, "detail": "spy"})

        durable_truncate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
