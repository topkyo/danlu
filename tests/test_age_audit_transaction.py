from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_utils import AuditMirrorError, AuditMirrorRollbackError
from aiwiki.execution.protocol_learnings import AUDIT_STATE_PATH, _write_age_audit


class AgeAuditTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.audit_path = self.root / AUDIT_STATE_PATH
        self.result_old = {
            "apply": True,
            "run_at": "2026-05-04T00:00:00Z",
            "threshold_days": 90,
            "aged": [],
            "aged_ids": [],
            "skipped": [],
            "errors": [],
        }
        self.result_new = {**self.result_old, "run_at": "2026-05-04T01:00:00Z"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_audit_failure_restores_existing_primary(self) -> None:
        _write_age_audit(self.root, self.result_old)
        old_bytes = self.audit_path.read_bytes()

        with patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")):
            with self.assertRaises(AuditMirrorError) as ctx:
                _write_age_audit(self.root, self.result_new)

        self.assertIn("OSError('audit fail')", str(ctx.exception))
        self.assertEqual(self.audit_path.read_bytes(), old_bytes)

    def test_audit_failure_removes_when_primary_did_not_exist(self) -> None:
        self.assertFalse(self.audit_path.exists())

        with patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")):
            with self.assertRaises(AuditMirrorError):
                _write_age_audit(self.root, self.result_new)

        self.assertFalse(self.audit_path.exists())

    def test_restore_failure_raises_rollback_error(self) -> None:
        _write_age_audit(self.root, self.result_old)

        with (
            patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")),
            patch("aiwiki.app_utils._durable_restore_or_remove", side_effect=OSError("restore fail")),
        ):
            with self.assertRaises(AuditMirrorRollbackError) as ctx:
                _write_age_audit(self.root, self.result_new)

        msg = str(ctx.exception)
        self.assertIn("OSError('audit fail')", msg)
        self.assertIn("OSError('restore fail')", msg)

    def test_success_path_writes_primary(self) -> None:
        _write_age_audit(self.root, self.result_new)
        self.assertTrue(self.audit_path.exists())
        loaded = json.loads(self.audit_path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["run_at"], self.result_new["run_at"])

    def test_rollback_uses_durable_restore_helper(self) -> None:
        """防退化：未来有人改回 bare write_bytes 会被这条测试拦截。"""
        _write_age_audit(self.root, self.result_old)

        def restore_without_fsync(path: Path, snapshot: bytes | None) -> None:
            if snapshot is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(snapshot)

        with patch("aiwiki.app_utils._durable_restore_or_remove", side_effect=restore_without_fsync) as restore_helper:
            with patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")):
                with self.assertRaises(AuditMirrorError):
                    _write_age_audit(self.root, self.result_new)

        restore_helper.assert_called_once()


if __name__ == "__main__":
    unittest.main()
