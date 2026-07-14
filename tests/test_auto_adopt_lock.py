from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from aiwiki.app_utils import _RUNTIME_LOCKS
from aiwiki.runner.auto_adopt import auto_adopt_judgments, auto_adopt_l1, auto_adopt_l2, auto_adopt_l3


class AutoAdoptLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _assert_lock_held(self) -> None:
        state = _RUNTIME_LOCKS.get(str(self.root.resolve()))
        self.assertIsNotNone(state)
        self.assertGreaterEqual(int(state.get("depth", 0)), 1)

    def test_auto_adopt_l1_acquires_lock(self) -> None:
        with patch("aiwiki.runner.auto_adopt._build_controls", side_effect=lambda _root: self._assert_lock_held()):
            result = auto_adopt_l1(self.root)

        self.assertTrue(result.get("degraded"))
        self.assertIn("control surface unavailable", str(result.get("error", "")))

    def test_auto_adopt_l2_acquires_lock(self) -> None:
        with patch("aiwiki.runner.auto_adopt._build_controls", side_effect=lambda _root: self._assert_lock_held()):
            result = auto_adopt_l2(self.root)

        self.assertTrue(result.get("degraded"))
        self.assertIn("execution control unavailable", str(result.get("error", "")))

    def test_auto_adopt_l3_acquires_lock(self) -> None:
        with patch(
            "aiwiki.execution.l3_proposals.load_l3_proposal_state",
            side_effect=lambda _root: self._assert_lock_held(),
        ):
            result = auto_adopt_l3(self.root)

        self.assertTrue(result.get("degraded"))
        self.assertIn("L3 proposal state unavailable", str(result.get("error", "")))

    def test_auto_adopt_judgments_acquires_lock(self) -> None:
        def assert_then_fail(_root: Path) -> None:
            self._assert_lock_held()
            raise RuntimeError("test")

        with patch("aiwiki.app_state.load_machine_memory", side_effect=assert_then_fail):
            result = auto_adopt_judgments(self.root, MagicMock(), limit=1)

        self.assertIn("memory unavailable", str(result.get("error", "")))


if __name__ == "__main__":
    unittest.main()
