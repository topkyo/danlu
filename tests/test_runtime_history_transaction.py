from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_state import append_runtime_history, runtime_history_path
from aiwiki.app_utils import AuditMirrorError, AuditMirrorRollbackError
from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH


class RuntimeHistoryTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        path = runtime_history_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.event = {
            "ts": "2026-05-04T00:00:00Z",
            "kind": "test",
            "detail": "rt-test",
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _runtime_lines(self) -> list[dict[str, object]]:
        path = runtime_history_path(self.root)
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _audit_lines(self) -> list[dict[str, object]]:
        path = self.root / AUDIT_STREAM_PATH
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_audit_failure_rolls_back_primary(self) -> None:
        path = runtime_history_path(self.root)
        append_runtime_history(self.root, self.event)
        size_before = path.stat().st_size

        with patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")):
            with self.assertRaises(AuditMirrorError) as ctx:
                append_runtime_history(self.root, {**self.event, "detail": "rt-2"})

        self.assertIn("OSError('audit fail')", str(ctx.exception))
        self.assertEqual(path.stat().st_size, size_before)
        self.assertNotIn("rt-2", path.read_text(encoding="utf-8"))

    def test_truncate_failure_raises_rollback_error(self) -> None:
        append_runtime_history(self.root, self.event)

        with (
            patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")),
            patch("aiwiki.app_utils._durable_truncate", side_effect=OSError("truncate fail")),
        ):
            with self.assertRaises(AuditMirrorRollbackError) as ctx:
                append_runtime_history(self.root, {**self.event, "detail": "rt-3"})

        message = str(ctx.exception)
        self.assertIn("OSError('audit fail')", message)
        self.assertIn("OSError('truncate fail')", message)

    def test_success_path_writes_primary_and_audit_with_line_number(self) -> None:
        append_runtime_history(self.root, self.event)
        append_runtime_history(self.root, {**self.event, "detail": "rt-2"})

        runtime_lines = self._runtime_lines()
        self.assertEqual([line["detail"] for line in runtime_lines], ["rt-test", "rt-2"])

        audit_lines = self._audit_lines()
        self.assertEqual(audit_lines[-1]["source_stream"], "runtime_history")
        self.assertEqual(audit_lines[-1]["source_ref"], ".aiwiki/state/runtime-history.jsonl#L2")
        self.assertEqual(audit_lines[-1]["subject"], {"kind": "test", "id": ""})

    def test_primary_not_exists_before_audit_failure_leaves_empty_primary(self) -> None:
        path = runtime_history_path(self.root)
        if path.exists():
            path.unlink()
        self.assertFalse(path.exists())

        with patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")):
            with self.assertRaises(AuditMirrorError):
                append_runtime_history(self.root, self.event)

        self.assertTrue(path.exists())
        self.assertEqual(path.stat().st_size, 0)

    def test_rollback_uses_durable_truncate_helper(self) -> None:
        """防退化：未来有人改回 bare os.truncate 会被这条测试拦截。"""
        path = runtime_history_path(self.root)
        append_runtime_history(self.root, self.event)
        size_before = path.stat().st_size

        def truncate_without_fsync(truncate_path: Path, size: int) -> None:
            with open(truncate_path, "r+b") as handle:
                handle.truncate(size)

        with patch("aiwiki.app_utils._durable_truncate", side_effect=truncate_without_fsync) as durable_truncate:
            with patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")):
                with self.assertRaises(AuditMirrorError):
                    append_runtime_history(self.root, {**self.event, "detail": "rt-fsync"})

        durable_truncate.assert_called_once_with(path, size_before)
        self.assertEqual(path.stat().st_size, size_before)
        self.assertNotIn("rt-fsync", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
