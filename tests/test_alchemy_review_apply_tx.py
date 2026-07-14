from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiwiki.runner.alchemy as runner_alchemy
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import execution_receipt_history_path
from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH
from aiwiki.render.paths import execution_receipts_dir


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class AlchemyReviewApplyTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _preview(self) -> dict[str, object]:
        return {
            "status": "ok",
            "scope": "all",
            "selected_count": 1,
            "candidate_count": 1,
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "trace_ids": ["550e8400-e29b-41d4-a716-446655440000"],
            "scope_preview": {},
            "apply_contract": {"primitive": "review"},
            "candidates": [
                {
                    "candidate_id": "review-judgment-wiki-judgments-thesis-md",
                    "kind": "judgment_review_enqueue",
                    "protocol": "research",
                    "target_ref": "wiki/judgments/thesis.md",
                    "signal_ids": ["sig-1"],
                }
            ],
        }

    def _run_apply(self) -> dict[str, object]:
        with patch.object(runner_alchemy, "run_alchemy_review_preview", return_value=self._preview()):
            return runner_alchemy.run_alchemy_review_apply(self.root, scope="all", note="queue it")

    def _queue_path(self) -> Path:
        return self.root / "wiki" / "indexes" / "review-queue.md"

    def _receipt_files(self) -> set[str]:
        receipts_dir = execution_receipts_dir(self.root)
        if not receipts_dir.exists():
            return set()
        return {p.name for p in receipts_dir.glob("*.json")}

    def test_happy_path_writes_queue_receipt_history_audit_and_runtime(self) -> None:
        result = self._run_apply()

        self.assertEqual(result["status"], "applied")
        self.assertTrue(self._queue_path().exists())
        self.assertIn("review-judgment-wiki-judgments-thesis-md", self._queue_path().read_text(encoding="utf-8"))
        receipt_path = self.root / str(result["receipt_path"])
        self.assertTrue(receipt_path.exists())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["operation"], "alchemy-review-enqueue")
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root))[-1]["action_id"], receipt["action_id"])
        self.assertEqual(_read_jsonl(self.root / AUDIT_STREAM_PATH)[-1]["source_stream"], "runtime_history")
        self.assertIn("execution_receipts", {item["source_stream"] for item in _read_jsonl(self.root / AUDIT_STREAM_PATH)})
        runtime_path = self.root / ".aiwiki" / "state" / "runtime-history.jsonl"
        self.assertEqual(_read_jsonl(runtime_path)[-1]["event_type"], "alchemy-review-enqueued")

    def test_queue_write_failure_restores_absent_queue_and_no_receipt_history_audit(self) -> None:
        with (
            patch.object(runner_alchemy, "run_alchemy_review_preview", return_value=self._preview()),
            patch.object(runner_alchemy, "_materialize_alchemy_review_queue", side_effect=OSError("queue failed")),
            self.assertRaises(runner_alchemy.AlchemyReviewApplyError),
        ):
            runner_alchemy.run_alchemy_review_apply(self.root, scope="all")

        self.assertFalse(self._queue_path().exists())
        self.assertEqual(self._receipt_files(), set())
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root)), [])
        self.assertEqual(_read_jsonl(self.root / AUDIT_STREAM_PATH), [])

    def test_receipt_write_failure_restores_queue_and_no_history_audit_receipt(self) -> None:
        original_atomic = runner_alchemy.atomic_write_text

        def flaky(path: Path, content: str, **kwargs: object) -> None:
            if "execution-receipts" in path.parts and path.suffix == ".json":
                raise OSError("receipt write failed")
            original_atomic(path, content, **kwargs)

        with (
            patch.object(runner_alchemy, "run_alchemy_review_preview", return_value=self._preview()),
            patch.object(runner_alchemy, "atomic_write_text", side_effect=flaky),
            self.assertRaises(runner_alchemy.AlchemyReviewApplyError),
        ):
            runner_alchemy.run_alchemy_review_apply(self.root, scope="all")

        self.assertFalse(self._queue_path().exists())
        self.assertEqual(self._receipt_files(), set())
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root)), [])
        self.assertEqual(_read_jsonl(self.root / AUDIT_STREAM_PATH), [])

    def test_history_append_failure_truncates_post_receipt_and_audit_residue(self) -> None:
        history_path = execution_receipt_history_path(self.root)
        audit_path = self.root / AUDIT_STREAM_PATH

        def partial_history(_root: Path, receipt: dict[str, object]) -> None:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            with history_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(receipt) + "\n")
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"source_stream": "execution_receipts"}) + "\n")
            raise OSError("history append failed")

        with (
            patch.object(runner_alchemy, "run_alchemy_review_preview", return_value=self._preview()),
            patch.object(runner_alchemy, "append_execution_receipt_history", side_effect=partial_history),
            self.assertRaises(runner_alchemy.AlchemyReviewApplyError),
        ):
            runner_alchemy.run_alchemy_review_apply(self.root, scope="all")

        self.assertFalse(self._queue_path().exists())
        self.assertEqual(self._receipt_files(), set())
        self.assertEqual(_read_jsonl(history_path), [])
        self.assertEqual(_read_jsonl(audit_path), [])

    def test_pre_existing_jsonl_bytes_preserved_on_history_append_failure(self) -> None:
        history_path = execution_receipt_history_path(self.root)
        audit_path = self.root / AUDIT_STREAM_PATH
        history_path.parent.mkdir(parents=True, exist_ok=True)
        seeded_history = json.dumps({"action_id": "pre-existing-history"}) + "\n"
        history_path.write_text(seeded_history, encoding="utf-8")
        history_size_seeded = history_path.stat().st_size
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        seeded_audit = json.dumps({"audit_event_id": "pre-existing-audit"}) + "\n"
        audit_path.write_text(seeded_audit, encoding="utf-8")
        audit_size_seeded = audit_path.stat().st_size

        def partial_history(_root: Path, receipt: dict[str, object]) -> None:
            with history_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(receipt) + "\n")
            with audit_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"source_stream": "execution_receipts"}) + "\n")
            raise OSError("history append failed")

        with (
            patch.object(runner_alchemy, "run_alchemy_review_preview", return_value=self._preview()),
            patch.object(runner_alchemy, "append_execution_receipt_history", side_effect=partial_history),
            self.assertRaises(runner_alchemy.AlchemyReviewApplyError),
        ):
            runner_alchemy.run_alchemy_review_apply(self.root, scope="all")

        self.assertEqual(history_path.stat().st_size, history_size_seeded)
        self.assertEqual(history_path.read_text(encoding="utf-8"), seeded_history)
        self.assertEqual(audit_path.stat().st_size, audit_size_seeded)
        self.assertEqual(audit_path.read_text(encoding="utf-8"), seeded_audit)
        self.assertFalse(self._queue_path().exists())
        self.assertEqual(self._receipt_files(), set())

    def test_pre_existing_review_queue_bytes_preserved_on_failure(self) -> None:
        self._queue_path().parent.mkdir(parents=True, exist_ok=True)
        seeded_queue = b"# Review Queue\n\nPrior content.\n"
        self._queue_path().write_bytes(seeded_queue)

        with (
            patch.object(runner_alchemy, "run_alchemy_review_preview", return_value=self._preview()),
            patch.object(runner_alchemy, "append_execution_receipt_history", side_effect=OSError("history failed")),
            self.assertRaises(runner_alchemy.AlchemyReviewApplyError),
        ):
            runner_alchemy.run_alchemy_review_apply(self.root, scope="all")

        self.assertEqual(self._queue_path().read_bytes(), seeded_queue)
        self.assertEqual(self._receipt_files(), set())

    def test_runtime_history_failure_does_not_rollback_phase1(self) -> None:
        with (
            patch.object(runner_alchemy, "run_alchemy_review_preview", return_value=self._preview()),
            patch.object(runner_alchemy, "append_runtime_history", side_effect=OSError("runtime failed")),
            self.assertLogs(runner_alchemy.logger, level="WARNING") as log_ctx,
        ):
            result = runner_alchemy.run_alchemy_review_apply(self.root, scope="all")

        self.assertEqual(result["status"], "applied")
        self.assertTrue(self._queue_path().exists())
        self.assertTrue((self.root / str(result["receipt_path"])).exists())
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root))[-1]["action_id"], Path(str(result["receipt_path"])).stem)
        self.assertIn("execution_receipts", {item["source_stream"] for item in _read_jsonl(self.root / AUDIT_STREAM_PATH)})
        self.assertTrue(any("runtime-history append failed" in msg for msg in log_ctx.output))

    def test_rollback_failure_raises_half_write_loud(self) -> None:
        self._queue_path().parent.mkdir(parents=True, exist_ok=True)
        self._queue_path().write_text("# Review Queue\n\nPrior content.\n", encoding="utf-8")

        with (
            patch.object(runner_alchemy, "run_alchemy_review_preview", return_value=self._preview()),
            patch.object(runner_alchemy, "append_execution_receipt_history", side_effect=OSError("history failed")),
            patch.object(runner_alchemy, "_restore_file_bytes", side_effect=OSError("restore failed")),
            self.assertRaises(runner_alchemy.AlchemyReviewApplyHalfWriteError) as ctx,
        ):
            runner_alchemy.run_alchemy_review_apply(self.root, scope="all")

        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertIn("restore failed", str(ctx.exception.__cause__))
        self.assertIn("tx_error=history failed", str(ctx.exception))
        self.assertIn("rollback_error=restore failed", str(ctx.exception))
