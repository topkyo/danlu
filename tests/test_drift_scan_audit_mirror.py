"""R94.1-DRIFT-SCAN-AUDIT-MIRROR: drift_scan events go through append_runtime_history."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import runtime_history_path
from aiwiki.app_utils import AuditMirrorError
from aiwiki.drift_scan import _append_drift_scan_event


class DriftScanAuditMirrorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        ensure_layout(self.root)
        self.history_path = runtime_history_path(self.root)
        self.audit_path = self.root / ".aiwiki" / "state" / "audit.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _read_jsonl(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
        return rows

    def test_appends_runtime_history_and_universal_audit(self) -> None:
        ref = _append_drift_scan_event(
            self.root,
            emitted_at="2025-01-01T00:00:00Z",
            stale_count=2,
            changed_count=1,
            breaks_count=0,
        )

        history = self._read_jsonl(self.history_path)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["event_type"], "drift-scan")
        self.assertEqual(history[0]["stale_count"], 2)

        # Audit mirror got a parallel record.
        audit = self._read_jsonl(self.audit_path)
        self.assertGreaterEqual(len(audit), 1)
        drift_audits = [r for r in audit if r.get("source_stream") == "runtime_history"]
        self.assertGreaterEqual(len(drift_audits), 1)
        self.assertTrue(drift_audits[-1]["source_ref"].endswith("#L1"))

        # Returned ref points to the actual non-blank line of the new row.
        self.assertEqual(ref.split("#L")[-1], "1")

    def test_audit_mirror_failure_rolls_back_runtime_history(self) -> None:
        # Seed one prior history row so we can detect rollback to original size.
        _append_drift_scan_event(
            self.root,
            emitted_at="2025-01-01T00:00:00Z",
            stale_count=0,
            changed_count=0,
            breaks_count=1,
        )
        size_before = self.history_path.stat().st_size
        history_before = self._read_jsonl(self.history_path)

        with patch(
            "aiwiki.execution.audit_preview.append_universal_audit_record",
            side_effect=RuntimeError("audit boom"),
        ):
            with self.assertRaises(AuditMirrorError):
                _append_drift_scan_event(
                    self.root,
                    emitted_at="2025-01-02T00:00:00Z",
                    stale_count=5,
                    changed_count=5,
                    breaks_count=5,
                )

        # Runtime history truncated back to pre-call size; no torn second row.
        self.assertEqual(self.history_path.stat().st_size, size_before)
        self.assertEqual(self._read_jsonl(self.history_path), history_before)

    def test_line_ref_uses_non_blank_line_semantics(self) -> None:
        # Manually write a history with blank lines between real rows.
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text(
            json.dumps({"event_type": "seed", "occurred_at": "2025-01-01T00:00:00Z"})
            + "\n\n\n",
            encoding="utf-8",
        )

        ref = _append_drift_scan_event(
            self.root,
            emitted_at="2025-01-02T00:00:00Z",
            stale_count=1,
            changed_count=0,
            breaks_count=0,
        )

        # Only 1 prior non-blank row, so the new row should be #L2.
        self.assertEqual(ref.split("#L")[-1], "2")


if __name__ == "__main__":
    unittest.main()
