from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aiwiki.execution.receipts import ExecutionReceiptValidationError, write_execution_receipt
from aiwiki.runner.local_stats import (
    collect_markdown_counts,
    is_elixir_count_question,
    is_markdown_count_question,
)


class LocalStatsTests(unittest.TestCase):
    def test_elixir_count_intent(self) -> None:
        self.assertTrue(is_elixir_count_question("当前炼丹炉 vault 有几个金丹"))
        self.assertFalse(is_elixir_count_question("什么是金丹"))

    def test_markdown_count_intent(self) -> None:
        self.assertTrue(is_markdown_count_question("这个 vault 有多少 md 文件"))
        self.assertFalse(is_markdown_count_question("解释 markdown 语法"))

    def test_collect_markdown_counts_empty_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "wiki").mkdir()
            (root / "wiki" / "a.md").write_text("# a\n", encoding="utf-8")
            stats = collect_markdown_counts(root)
            self.assertEqual(stats["total"], 1)
            self.assertEqual(stats["by_top_level"]["wiki"], 1)


class ExecutionReceiptValidationTests(unittest.TestCase):
    def test_write_execution_receipt_requires_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ExecutionReceiptValidationError):
                write_execution_receipt(
                    root,
                    operation="",
                    generated_by="test",
                    subject_kind="test",
                    subject_id="t1",
                    target_file="output/reports/x.md",
                )

    def test_write_execution_receipt_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = write_execution_receipt(
                root,
                operation="run-ask",
                generated_by="test",
                subject_kind="output",
                subject_id="x",
                target_file="output/reports/x.md",
                status="success",
            )
            self.assertEqual(receipt["operation"], "run-ask")
            self.assertEqual(receipt["status"], "success")


class WorkflowsAskImportTests(unittest.TestCase):
    def test_workflows_reexports_ask_entrypoints(self) -> None:
        from aiwiki.runner import workflows, workflows_ask

        for name in ("run_ask", "run_ask_submit", "run_ask_resume"):
            self.assertIs(getattr(workflows, name), getattr(workflows_ask, name))


if __name__ == "__main__":
    unittest.main()
