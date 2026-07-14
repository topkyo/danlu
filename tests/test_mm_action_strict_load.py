"""R94.3 — strict mm-action state loader fails closed on corrupt JSON.

Execution paths that read action state and write it back must not silently
recover from corrupt JSON, otherwise the corrupt file gets overwritten with
an empty `actions` list = silent data loss of review status / receipts.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aiwiki.app_memory import reconcile_machine_memory_actions
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import (
    CorruptStateError,
    default_machine_memory_action_state,
    load_machine_memory_action_state,
    load_machine_memory_action_state_strict,
    machine_memory_action_state_path,
    save_machine_memory_action_state,
)
from aiwiki.execution.machine_memory_actions import review_machine_memory_action


class StrictMmActionLoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        ensure_layout(self.root)
        self.path = machine_memory_action_state_path(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_strict_missing_file_returns_default(self) -> None:
        # Path may not exist yet; strict loader matches best-effort here.
        self.assertFalse(self.path.exists())
        self.assertEqual(
            load_machine_memory_action_state_strict(self.root),
            default_machine_memory_action_state(),
        )

    def test_strict_valid_file_matches_best_effort(self) -> None:
        document = {
            "version": 1,
            "actions": [{"id": "act-1", "status": "proposed"}],
        }
        save_machine_memory_action_state(self.root, document)
        self.assertEqual(
            load_machine_memory_action_state_strict(self.root),
            load_machine_memory_action_state(self.root),
        )

    def test_strict_corrupt_json_raises(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        original_bytes = b'{"version": 1, "actions": [ttruncated'
        self.path.write_bytes(original_bytes)
        with self.assertRaises(CorruptStateError):
            load_machine_memory_action_state_strict(self.root)
        # File untouched.
        self.assertEqual(self.path.read_bytes(), original_bytes)

    def test_strict_non_object_top_level_raises(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("[1, 2, 3]\n", encoding="utf-8")
        with self.assertRaises(CorruptStateError):
            load_machine_memory_action_state_strict(self.root)

    def test_strict_non_list_actions_raises(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text('{"version": 1, "actions": "oops"}\n', encoding="utf-8")
        with self.assertRaises(CorruptStateError):
            load_machine_memory_action_state_strict(self.root)

    def test_strict_existing_empty_object_raises(self) -> None:
        # Existing `{}` is structurally invalid (no `actions` key at all).
        # MUST NOT be conflated with missing-file → default.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{}\n", encoding="utf-8")
        with self.assertRaises(CorruptStateError):
            load_machine_memory_action_state_strict(self.root)

    def test_strict_non_dict_action_item_raises(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            '{"version": 1, "actions": [{"id": "ok"}, "stringy"]}\n',
            encoding="utf-8",
        )
        with self.assertRaises(CorruptStateError) as ctx:
            load_machine_memory_action_state_strict(self.root)
        self.assertIn("actions[1]", str(ctx.exception))

    def test_strict_string_version_raises(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            '{"version": "1", "actions": []}\n', encoding="utf-8"
        )
        with self.assertRaises(CorruptStateError) as ctx:
            load_machine_memory_action_state_strict(self.root)
        self.assertIn("version", str(ctx.exception))

    def test_strict_null_version_raises(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            '{"version": null, "actions": []}\n', encoding="utf-8"
        )
        with self.assertRaises(CorruptStateError):
            load_machine_memory_action_state_strict(self.root)

    def test_strict_missing_version_defaults_to_1(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text('{"actions": []}\n', encoding="utf-8")
        result = load_machine_memory_action_state_strict(self.root)
        self.assertEqual(result, {"version": 1, "actions": []})

    def test_strict_bool_version_raises(self) -> None:
        # bool is int subclass in Python; must still be rejected.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            '{"version": true, "actions": []}\n', encoding="utf-8"
        )
        with self.assertRaises(CorruptStateError):
            load_machine_memory_action_state_strict(self.root)

    def test_review_action_corrupt_state_does_not_overwrite(self) -> None:
        # The critical regression guard: previously a corrupt action state
        # file silently produced empty `actions = []` and the subsequent
        # save_machine_memory_action_state(...) overwrote the corrupt file
        # with `{"version": 1, "actions": []}`. With the strict loader the
        # execution path must raise and leave the corrupt file as-is for
        # operator inspection / repair.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        corrupt = b'{"version": 1, "actions": [{"id": "act-1"} BROKEN'
        self.path.write_bytes(corrupt)
        with self.assertRaises(CorruptStateError):
            review_machine_memory_action(self.root, "act-1", "accepted")
        # The corrupt file must NOT have been replaced with an empty state.
        self.assertEqual(self.path.read_bytes(), corrupt)

    def test_reconcile_corrupt_state_does_not_overwrite(self) -> None:
        # Compile-time write-back path must also fail-closed on corrupt state.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        corrupt = b'{"version": 1, "actions": [{ HALF'
        self.path.write_bytes(corrupt)
        with self.assertRaises(CorruptStateError):
            reconcile_machine_memory_actions(
                self.root,
                {"aging": {}, "repair_backlog": {}},
                compiled_at="2026-01-01T00:00:00+00:00",
            )
        self.assertEqual(self.path.read_bytes(), corrupt)


if __name__ == "__main__":
    unittest.main()
