from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.llm_telemetry import aggregate_backend_telemetry, aggregate_llm_telemetry


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

    def test_aggregate_backend_telemetry_classifies_llm_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt_dir = root / "output" / "control" / "execution-receipts"
            receipt_dir.mkdir(parents=True)
            receipt = {
                "kind": "execution-receipt",
                "operation": "run-nightly",
                "status": "success",
                "receipt_path": "output/control/execution-receipts/run-nightly-nightly-health.json",
                "target_file": ".aiwiki/state/nightly-health.json",
                "backend_effective": "opencode-api",
            }
            (receipt_dir / "run-nightly-nightly-health.json").write_text(json.dumps(receipt), encoding="utf-8")
            state_dir = root / ".aiwiki" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "execution-receipts.jsonl").write_text(json.dumps(receipt) + "\n", encoding="utf-8")
            log_dir = root / ".aiwiki" / "logs"
            log_dir.mkdir(parents=True)
            rows = [
                {"event": "run-nightly", "status": "success", "backend_effective": "opencode-api", "model_final": "ok"},
                {"event": "run-ask", "status": "failed", "backend_effective": "opencode-api", "error_class": "timeout"},
                {"event": "run-nightly", "status": "failed", "backend_effective": "opencode-api", "error": "quota exceeded"},
            ]
            (log_dir / "llm-receipts.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            report = aggregate_backend_telemetry(root, limit=10)

            self.assertEqual(report["sample_size"], 1)
            self.assertEqual(report["operation_counts"]["run-nightly"], 1)
            self.assertEqual(report["llm_sample_size"], 3)
            self.assertEqual(report["timeout_failure_count"], 1)
            self.assertEqual(report["quota_failure_count"], 1)
            self.assertEqual(report["llm_failure_category_counts"]["timeout"], 1)
            self.assertEqual(report["llm_failure_category_counts"]["quota"], 1)

    def test_backend_telemetry_uses_receipt_timestamps_for_recent_execution_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt_dir = root / "output" / "control" / "execution-receipts"
            receipt_dir.mkdir(parents=True)
            state_dir = root / ".aiwiki" / "state"
            state_dir.mkdir(parents=True)
            rows = [
                {
                    "operation": "z-old",
                    "status": "success",
                    "receipt_path": "output/control/execution-receipts/z-old.json",
                    "applied_at": "2026-05-21T00:00:00Z",
                },
                {
                    "operation": "a-new",
                    "status": "success",
                    "receipt_path": "output/control/execution-receipts/a-new.json",
                    "applied_at": "2026-05-23T00:00:00Z",
                },
            ]
            for row in rows:
                (receipt_dir / Path(row["receipt_path"]).name).write_text(json.dumps(row), encoding="utf-8")
            (state_dir / "execution-receipts.jsonl").write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            report = aggregate_backend_telemetry(root, limit=1)

            self.assertEqual(report["sample_size"], 1)
            self.assertEqual(report["operation_counts"], {"a-new": 1})

    def test_backend_telemetry_uses_llm_receipt_timestamps_for_recent_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_dir = root / ".aiwiki" / "logs"
            log_dir.mkdir(parents=True)
            rows = [
                {
                    "event": "run-nightly",
                    "status": "failed",
                    "backend_effective": "opencode-api",
                    "error": "quota exceeded",
                    "created_at": "2026-05-23T00:00:00Z",
                },
                {
                    "event": "run-ask",
                    "status": "failed",
                    "backend_effective": "opencode-api",
                    "error_class": "timeout",
                    "created_at": "2026-05-21T00:00:00Z",
                },
            ]
            (log_dir / "llm-receipts.jsonl").write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            report = aggregate_backend_telemetry(root, limit=1)

            self.assertEqual(report["llm_sample_size"], 1)
            self.assertEqual(report["quota_failure_count"], 1)
            self.assertEqual(report["timeout_failure_count"], 0)
            self.assertEqual(report["recent_failures"][0]["failure_category"], "quota")
