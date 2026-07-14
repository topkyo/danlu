"""R94.0-AUTOMATION-STATE-ATOMIC-WRITE: torn-write safety on automation.json."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.runner.automation import _write_automation_state


class AutomationStateAtomicWriteTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        ensure_layout(self.root)
        self.path = self.root / ".aiwiki" / "state" / "automation.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_writes_via_os_replace(self) -> None:
        with patch("aiwiki.app_utils.os.replace", wraps=__import__("os").replace) as wrapped:
            _write_automation_state(self.root, {"status": "ok"})
        self.assertTrue(wrapped.called)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"status": "ok"})

    def test_no_partial_file_when_replace_fails(self) -> None:
        # Seed an existing good file.
        _write_automation_state(self.root, {"status": "ok-prior"})
        before = self.path.read_text(encoding="utf-8")

        with patch("aiwiki.app_utils.os.replace", side_effect=OSError("replace boom")):
            with self.assertRaises(OSError):
                _write_automation_state(self.root, {"status": "would-be-new"})

        # Original content untouched.
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)
        # No tmp file lingering.
        leftovers = list(self.path.parent.glob("automation.json.tmp.*"))
        self.assertEqual(leftovers, [])

    def test_skip_replace_unchanged_not_required(self) -> None:
        # Sanity: contract intentionally writes every time (no change-detection layer here).
        _write_automation_state(self.root, {"status": "ok", "n": 1})
        _write_automation_state(self.root, {"status": "ok", "n": 2})
        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8")),
            {"status": "ok", "n": 2},
        )


if __name__ == "__main__":
    unittest.main()
