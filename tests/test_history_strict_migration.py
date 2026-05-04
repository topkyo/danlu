from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.app_state import CorruptStateError, execution_policy_log_path, execution_receipt_history_path
from aiwiki.content.memory import (
    load_execution_policy_decision_history,
    load_execution_policy_decision_history_strict,
    load_execution_receipt_history,
    load_execution_receipt_history_strict,
)


class HistoryStrictMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_policy_strict_corrupt_raises(self) -> None:
        path = execution_policy_log_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"policy_decision":"allow"}\n{bad\n', encoding="utf-8")

        with self.assertRaises(CorruptStateError) as ctx:
            load_execution_policy_decision_history_strict(self.root)

        self.assertIn(str(path), str(ctx.exception))
        self.assertIn(":2", str(ctx.exception))
        self.assertEqual(load_execution_policy_decision_history(self.root), [{"policy_decision": "allow"}])

    def test_policy_strict_non_dict_raises(self) -> None:
        path = execution_policy_log_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('["array"]\n', encoding="utf-8")

        with self.assertRaisesRegex(CorruptStateError, "non-dict"):
            load_execution_policy_decision_history_strict(self.root)

    def test_policy_strict_missing_returns_empty(self) -> None:
        self.assertEqual(load_execution_policy_decision_history_strict(self.root), [])

    def test_policy_strict_limit_works(self) -> None:
        path = execution_policy_log_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps({"idx": idx}) for idx in range(3)) + "\n",
            encoding="utf-8",
        )

        self.assertEqual(load_execution_policy_decision_history_strict(self.root, limit=2), [{"idx": 2}, {"idx": 1}])

    def test_receipt_strict_corrupt_raises(self) -> None:
        path = execution_receipt_history_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"kind":"execution-receipt","action_id":"a1"}\n{bad\n', encoding="utf-8")

        with self.assertRaises(CorruptStateError) as ctx:
            load_execution_receipt_history_strict(self.root)

        self.assertIn(str(path), str(ctx.exception))
        self.assertIn(":2", str(ctx.exception))

    def test_receipt_strict_invalid_utf8_raises(self) -> None:
        path = execution_receipt_history_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xfe invalid utf8\n")

        with self.assertRaises(UnicodeDecodeError):
            load_execution_receipt_history_strict(self.root)
        self.assertEqual(load_execution_receipt_history(self.root), [])

    def test_receipt_strict_filters_kind(self) -> None:
        path = execution_receipt_history_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"kind": "other", "id": "skip"})
            + "\n"
            + json.dumps({"kind": "execution-receipt", "action_id": "keep"})
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(load_execution_receipt_history_strict(self.root), [{"kind": "execution-receipt", "action_id": "keep"}])

    def test_best_effort_corrupt_logs_warning(self) -> None:
        policy_path = execution_policy_log_path(self.root)
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text('{"policy_decision":"allow"}\n{bad\n', encoding="utf-8")
        receipt_path = execution_receipt_history_path(self.root)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text('{"kind":"execution-receipt","action_id":"a1"}\n{bad\n', encoding="utf-8")

        with self.assertLogs("aiwiki.content.memory", level="WARNING") as logs:
            self.assertEqual(load_execution_policy_decision_history(self.root), [{"policy_decision": "allow"}])
            self.assertEqual(load_execution_receipt_history(self.root), [{"kind": "execution-receipt", "action_id": "a1"}])

        text = "\n".join(logs.output)
        self.assertIn("path=", text)
        self.assertIn("line_no=2", text)
        self.assertIn("reason=JSONDecodeError", text)


if __name__ == "__main__":
    unittest.main()
