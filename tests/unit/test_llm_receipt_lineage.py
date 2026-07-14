from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.runner.receipts import _build_llm_audit, _llm_audit_from_result, _merge_llm_audits, record_llm_attempt


class LLMReceiptLineageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _read_last_jsonl(self, relative_path: str) -> dict[str, object]:
        path = self.root / relative_path
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return json.loads(lines[-1])

    def test_success_receipt_does_not_write_empty_historical_lineage(self) -> None:
        llm_audit = {
            "backend_requested": "opencode-api",
            "backend_effective": "opencode-api",
            "model_selected": "deepseek-v4-pro",
            "model_final": "deepseek-v4-pro",
            "fallback_stage": "",
            "fallback_reason": "",
            "contract_validated": True,
        }

        receipt = record_llm_attempt(
            self.root,
            {"event": "run-ask", "target": "output/reports/query.md"},
            llm_audit,
            status="success",
            response_id="resp-ok",
        )

        self.assertEqual(receipt["delivery_mode"], "llm-success")
        self.assertFalse(receipt["fallback_used"])
        self.assertNotIn("fallback_from", receipt)
        self.assertNotIn("fallback_command", receipt)
        self.assertNotIn("fallback_stage", receipt)
        self.assertNotIn("fallback_reason", receipt)
        self.assertNotIn("fallback_from", llm_audit)
        self.assertNotIn("fallback_command", llm_audit)
        self.assertNotIn("fallback_stage", llm_audit)
        self.assertNotIn("fallback_reason", llm_audit)

        llm_receipt = self._read_last_jsonl(".aiwiki/logs/llm-receipts.jsonl")
        run_log = self._read_last_jsonl(".aiwiki/logs/runs.jsonl")
        self.assertNotIn("fallback_from", llm_receipt)
        self.assertNotIn("fallback_command", llm_receipt)
        self.assertNotIn("fallback_stage", llm_receipt)
        self.assertNotIn("fallback_reason", llm_receipt)
        self.assertNotIn("fallback_from", run_log)
        self.assertNotIn("fallback_command", run_log)
        self.assertNotIn("fallback_stage", run_log)
        self.assertNotIn("fallback_reason", run_log)

    def test_explicit_historical_deterministic_lineage_is_preserved(self) -> None:
        llm_audit = {
            "backend_requested": "opencode-api",
            "backend_effective": "opencode-api",
            "model_selected": "deepseek-v4-pro",
            "model_final": "deepseek-v4-pro",
            "fallback_stage": "",
            "fallback_reason": "usage limit exceeded",
            "contract_validated": False,
        }

        receipt = record_llm_attempt(
            self.root,
            {
                "event": "run-ask-frontdoor",
                "delivery_mode": "deterministic-fallback",
                "fallback_from": "run-ask",
                "fallback_command": "ask",
                "target": "output/reports/query.md",
            },
            llm_audit,
            status="success",
            response_id="resp-historical-failure-notice",
        )

        self.assertEqual(receipt["delivery_mode"], "deterministic-fallback")
        self.assertTrue(receipt["fallback_used"])
        self.assertEqual(receipt["fallback_from"], "run-ask")
        self.assertEqual(receipt["fallback_command"], "ask")
        self.assertNotIn("fallback_stage", receipt)
        self.assertEqual(receipt["fallback_reason"], "usage limit exceeded")
        self.assertEqual(llm_audit["fallback_from"], "run-ask")
        self.assertEqual(llm_audit["fallback_command"], "ask")
        self.assertNotIn("fallback_stage", llm_audit)
        self.assertEqual(llm_audit["fallback_reason"], "usage limit exceeded")

        llm_receipt = self._read_last_jsonl(".aiwiki/logs/llm-receipts.jsonl")
        run_log = self._read_last_jsonl(".aiwiki/logs/runs.jsonl")
        self.assertEqual(llm_receipt["fallback_from"], "run-ask")
        self.assertEqual(llm_receipt["fallback_command"], "ask")
        self.assertNotIn("fallback_stage", llm_receipt)
        self.assertEqual(llm_receipt["fallback_reason"], "usage limit exceeded")
        self.assertEqual(run_log["fallback_from"], "run-ask")
        self.assertEqual(run_log["fallback_command"], "ask")
        self.assertNotIn("fallback_stage", run_log)
        self.assertEqual(run_log["fallback_reason"], "usage limit exceeded")

    def test_llm_audit_helpers_omit_empty_historical_lineage(self) -> None:
        built = _build_llm_audit(None, model_selected="stub", contract_validated=True)

        self.assertEqual(built["model_selected"], "stub")
        self.assertTrue(built["contract_validated"])
        self.assertNotIn("fallback_stage", built)
        self.assertNotIn("fallback_reason", built)

        merged = _merge_llm_audits(built, {"backend_effective": "opencode-api"})
        self.assertNotIn("fallback_stage", merged)
        self.assertNotIn("fallback_reason", merged)

        historical_current = _merge_llm_audits({"fallback_stage": "", "fallback_reason": ""}, {})
        self.assertNotIn("fallback_stage", historical_current)
        self.assertNotIn("fallback_reason", historical_current)

        from_result = _llm_audit_from_result(
            {
                "backend_requested": "opencode-api",
                "backend_effective": "opencode-api",
                "model_selected": "deepseek-v4-pro",
                "model_final": "deepseek-v4-pro",
                "fallback_stage": "",
                "fallback_reason": "",
                "contract_validated": True,
            }
        )
        self.assertNotIn("fallback_stage", from_result)
        self.assertNotIn("fallback_reason", from_result)

    def test_llm_audit_helpers_preserve_non_empty_historical_lineage(self) -> None:
        built = _build_llm_audit(
            None,
            model_selected="stub",
            fallback_stages=["prompt-profile", "model-chain"],
            fallback_reason="primary failed",
        )

        self.assertEqual(built["fallback_stage"], "prompt-profile+model-chain")
        self.assertEqual(built["fallback_reason"], "primary failed")

        merged = _merge_llm_audits(
            {"fallback_stage": "prompt-profile", "fallback_reason": "prompt failed"},
            {"fallback_stage": "model-chain", "fallback_reason": "model failed"},
        )
        self.assertEqual(merged["fallback_stage"], "prompt-profile+model-chain")
        self.assertEqual(merged["fallback_reason"], "model failed")

        from_result = _llm_audit_from_result(
            {
                "fallback_stage": "model-chain",
                "fallback_reason": "model failed",
            }
        )
        self.assertEqual(from_result["fallback_stage"], "model-chain")
        self.assertEqual(from_result["fallback_reason"], "model failed")


if __name__ == "__main__":
    unittest.main()
