from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import CorruptStateError, machine_memory_action_state_path
from aiwiki.cli.dispatch_helpers import _resolve_action_ids, _resolve_review_action_ids


class BulkActionCorruptStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        ensure_layout(self.root)
        path = machine_memory_action_state_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not-json", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_review_all_pending_raises_on_corrupt_state(self) -> None:
        with self.assertRaises(CorruptStateError):
            _resolve_review_action_ids(
                self.root,
                [],
                all_pending=True,
                kind="split-overloaded-concept",
                execution_band="review-first",
            )

    def test_apply_all_accepted_low_risk_raises_on_corrupt_state(self) -> None:
        with self.assertRaises(CorruptStateError):
            _resolve_action_ids(
                self.root,
                None,
                batch=None,
                all_accepted_low_risk=True,
            )


if __name__ == "__main__":
    unittest.main()
