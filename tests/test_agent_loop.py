from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.agent_loop import (
    attach_agent_loop_to_nightly_state,
    run_nightly_agent_loop,
    run_nightly_agent_loop_preview,
)
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import append_runtime_history, nightly_health_state_path
from aiwiki.app_utils import runtime_write_lock
from aiwiki.planner import preview_alchemy_lane


class AgentLoopPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_preview_materializes_signals_planner_and_dry_run(self) -> None:
        append_runtime_history(
            self.root,
            {
                "event_type": "raw-added",
                "occurred_at": "2026-04-30T00:00:00+00:00",
                "protocol": "general",
                "stored_path": "raw/inbox/example.md",
                "original_path": "raw/inbox/example.md",
            },
        )

        result = run_nightly_agent_loop_preview(self.root)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["side_effects_allowed"])
        self.assertEqual(result["signals"]["new_count"], 1)
        self.assertEqual(result["planner"]["observe"]["new_count"], 1)
        self.assertEqual(result["planner"]["execute"]["new_count"], 1)
        self.assertEqual(result["auto_preview"]["mode"], "dry_run")
        self.assertFalse(result["auto_preview"]["side_effects_allowed"])
        light = next(item for item in result["auto_preview"]["lane_results"] if item["lane"] == "light")
        self.assertEqual(light["status"], "ready")
        self.assertEqual(light["selected_count"], 1)
        self.assertIn("compile", light["selected_primitives"])
        self.assertFalse((self.root / "output/control/execution-receipts").exists())

    def test_attach_agent_loop_updates_nightly_state_file(self) -> None:
        state = {"generated_at": "2026-04-30T00:00:00+00:00", "repair_backlog": {"path": "x"}}
        agent_loop = {"status": "ok", "dry_run": True, "side_effects_allowed": False}

        updated = attach_agent_loop_to_nightly_state(self.root, state, agent_loop)

        self.assertEqual(updated["agent_loop"], agent_loop)
        persisted = json.loads(nightly_health_state_path(self.root).read_text(encoding="utf-8"))
        self.assertEqual(persisted["agent_loop"], agent_loop)

    def test_lane_preview_can_opt_into_current_writer_lock(self) -> None:
        append_runtime_history(
            self.root,
            {
                "event_type": "raw-added",
                "occurred_at": "2026-04-30T00:00:00+00:00",
                "protocol": "general",
                "stored_path": "raw/inbox/example.md",
            },
        )
        run_nightly_agent_loop_preview(self.root)

        with runtime_write_lock(self.root):
            locked = preview_alchemy_lane(self.root, lane="light", scope="all", decision_mode="execute")
            allowed = preview_alchemy_lane(
                self.root,
                lane="light",
                scope="all",
                decision_mode="execute",
                allow_current_writer_lock=True,
            )

        self.assertEqual(locked["status"], "skipped")
        self.assertEqual(locked["reason"], "lock_conflict")
        self.assertEqual(allowed["status"], "ok")
        self.assertEqual(allowed["lock"]["status"], "held_by_current_process")

    def test_agent_loop_can_apply_light_lane_inside_current_writer_lock(self) -> None:
        append_runtime_history(
            self.root,
            {
                "event_type": "raw-added",
                "occurred_at": "2026-04-30T00:00:00+00:00",
                "protocol": "general",
                "stored_path": "raw/inbox/example.md",
            },
        )

        with runtime_write_lock(self.root):
            result = run_nightly_agent_loop(self.root, apply_light=True)

        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["dry_run"])
        self.assertTrue(result["side_effects_allowed"])
        self.assertEqual(result["auto_apply"]["status"], "applied")
        self.assertEqual(result["auto_apply"]["applied_count"], 1)
        light = result["auto_apply"]["lane_results"][0]
        self.assertEqual(light["lane"], "light")
        self.assertEqual(light["status"], "applied")
        self.assertEqual(light["selected_primitives"], ["compile", "lint", "nightly"])
        self.assertEqual(len(light["primitive_receipts"]), 3)
        for receipt in light["primitive_receipts"]:
            self.assertTrue((self.root / receipt).exists())


if __name__ == "__main__":
    unittest.main()
