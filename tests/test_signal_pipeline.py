from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.runner.signal_pipeline import run_signal_pipeline


class SignalPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_heavy_semantic_phase_reports_explicit_contract_without_default_apply(self) -> None:
        light_result = {
            "status": "ready",
            "mode": "dry_run",
            "side_effects_allowed": False,
            "lane_results": [],
        }
        heavy_result = {
            "status": "ready",
            "mode": "dry_run",
            "side_effects_allowed": False,
            "lane_results": [
                {
                    "lane": "heavy",
                    "selected_primitives": ["review", "distill", "propose"],
                    "plan": {
                        "scope": "all",
                        "scope_preview": {
                            "signal_ids": ["sig-1"],
                            "trace_ids": ["trace-1"],
                            "source_ids": ["source-1"],
                            "elixir_refs": ["wiki/elixirs/e1.md"],
                            "judgment_refs": ["wiki/judgments/j1.md"],
                        },
                    },
                }
            ],
        }

        with (
            patch("aiwiki.signals.collector.collect_signals", return_value={"new_count": 1}),
            patch("aiwiki.runner.signal_pipeline.write_planner_log", return_value={"new_count": 1}),
            patch("aiwiki.runner.signal_pipeline.run_alchemy_auto", side_effect=[light_result, heavy_result]) as auto_mock,
        ):
            result = run_signal_pipeline(self.root, apply_light=False)

        self.assertEqual(result["status"], "preview")
        self.assertFalse(result["heavy_semantic_apply_enabled"])
        heavy_call = auto_mock.call_args_list[1]
        self.assertFalse(heavy_call.kwargs["apply"])
        self.assertEqual(heavy_call.kwargs["lanes"], ["heavy"])
        self.assertEqual(heavy_call.kwargs["primitives"], ["review", "distill", "propose"])
        summary = result["heavy_semantic"]
        self.assertFalse(summary["applied"])
        self.assertEqual(summary["selected_contract_count"], 3)
        contract = summary["semantic_contracts"][0]
        self.assertEqual(contract["phase"], "heavy")
        self.assertTrue(contract["human_required"])
        self.assertEqual(contract["model_contract"], "explicit_llm_or_human_contract_required_for_semantic_content")
        self.assertEqual(contract["input_refs"]["signal_ids"], ["sig-1"])


if __name__ == "__main__":
    unittest.main()
