from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.llm_telemetry import aggregate_llm_telemetry


class TestLlmTelemetry(unittest.TestCase):
    def test_aggregate_empty_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".aiwiki" / "logs").mkdir(parents=True)
            report = aggregate_llm_telemetry(root, limit=10)
            self.assertEqual(report["sample_size"], 0)
            self.assertIsNone(report["success_rate"])

    def test_aggregate_recent_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_dir = root / ".aiwiki" / "logs"
            log_dir.mkdir(parents=True)
            path = log_dir / "llm-receipts.jsonl"
            rows = [
                {"status": "success", "backend": "opencode-api", "model_final": "deepseek-v4-pro", "duration_ms": 100},
                {"status": "failed", "backend": "opencode-api", "error_class": "timeout", "duration_ms": 120000},
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            report = aggregate_llm_telemetry(root, limit=10)
            self.assertEqual(report["sample_size"], 2)
            self.assertEqual(report["success_count"], 1)
            self.assertEqual(report["failure_count"], 1)
            self.assertIn("opencode-api", report["backend_counts"])
