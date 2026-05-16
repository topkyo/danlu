from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import (
    execution_batch_receipt_path,
    load_machine_memory_action_state_strict,
    runtime_history_path,
    save_machine_memory_action_state,
)
from aiwiki.execution import machine_memory_batch as batch_mod
from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class MachineMemoryActionBatchReceiptTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        ensure_layout(self.root)
        self.action_ids = ["action-a", "action-b"]
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": action_id,
                        "kind": "add-source-concept-link",
                        "title": f"Action {action_id}",
                        "status": "accepted",
                        "active": True,
                        "primary_path": f"wiki/sources/{action_id}.md",
                        "secondary_path": f"wiki/concepts/{action_id}.md",
                        "source_ids": [action_id],
                        "concept_slugs": [action_id],
                    }
                    for action_id in self.action_ids
                ],
            },
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _runtime_path(self) -> Path:
        return runtime_history_path(self.root)

    def _wiki_log_path(self) -> Path:
        return self.root / "wiki" / "indexes" / "log.md"

    def _audit_path(self) -> Path:
        return self.root / AUDIT_STREAM_PATH

    def _batch_receipt(self, batch_id: str = "batch-tx") -> Path:
        return execution_batch_receipt_path(self.root, batch_id)

    def _batch_receipts(self) -> list[Path]:
        root = self.root / "output" / "control" / "execution-batches"
        if not root.exists():
            return []
        return sorted(root.glob("*.json"))

    def _applied_ids(self) -> set[str]:
        state = load_machine_memory_action_state_strict(self.root)
        return {str(action.get("id")) for action in state["actions"] if str(action.get("status") or "") == "resolved"}

    def _apply_one(self, root: Path, action_id: str, **kwargs: object) -> dict[str, object]:
        state = load_machine_memory_action_state_strict(root)
        for action in state["actions"]:
            if action.get("id") == action_id:
                if kwargs.get("dry_run"):
                    return {"id": action_id, "dry_run": True, "bundle_path": f"output/control/execution/{action_id}.json"}
                action["status"] = "resolved"
                action["last_receipt_path"] = f"output/control/execution/{action_id}.json"
                save_machine_memory_action_state(root, state)
                return {"id": action_id, "status": "resolved", "receipt_path": action["last_receipt_path"]}
        raise FileNotFoundError(action_id)

    def _run_batch(self, *, batch_id: str = "batch-tx") -> dict[str, object]:
        with (
            patch.object(batch_mod, "_build_batch_id", return_value=batch_id),
            patch("aiwiki.app_compile.apply_machine_memory_action", side_effect=self._apply_one),
        ):
            return batch_mod.apply_machine_memory_actions_batch(self.root, self.action_ids, note="batch tx")

    def test_happy_path_two_actions_writes_batch_receipt_runtime_and_wiki_log(self) -> None:
        result = self._run_batch()

        self.assertEqual(result["operation"], "action-apply-batch")
        self.assertEqual(result["count"], 2)
        self.assertEqual(self._applied_ids(), set(self.action_ids))
        receipt = json.loads(self._batch_receipt().read_text(encoding="utf-8"))
        self.assertEqual(receipt["operation"], "action-apply-batch")
        self.assertEqual(receipt["action_ids"], self.action_ids)
        self.assertEqual(_read_jsonl(self._runtime_path())[-1]["event_type"], "action-apply-batch")
        self.assertIn("action-batch", self._wiki_log_path().read_text(encoding="utf-8"))

    def test_per_action_failure_propagates_unwrapped_and_skips_batch_writes(self) -> None:
        calls = 0

        def fail_second(root: Path, action_id: str, **kwargs: object) -> dict[str, object]:
            nonlocal calls
            if kwargs.get("dry_run"):
                return self._apply_one(root, action_id, **kwargs)
            calls += 1
            if calls == 2:
                raise ValueError("second action failed")
            return self._apply_one(root, action_id, **kwargs)

        with (
            patch.object(batch_mod, "_build_batch_id", return_value="batch-tx"),
            patch("aiwiki.app_compile.apply_machine_memory_action", side_effect=fail_second),
            self.assertRaises(ValueError) as ctx,
        ):
            batch_mod.apply_machine_memory_actions_batch(self.root, self.action_ids)

        self.assertEqual(str(ctx.exception), "second action failed")
        self.assertEqual(self._applied_ids(), {"action-a"})
        self.assertEqual(self._batch_receipts(), [])
        self.assertFalse(self._runtime_path().exists())
        self.assertFalse(self._wiki_log_path().exists())

    def test_batch_receipt_write_fail_retains_actions_and_writes_no_batch_metadata(self) -> None:
        with (
            patch.object(batch_mod, "write_execution_batch_receipt_document", side_effect=OSError("receipt failed")),
            self.assertRaises(batch_mod.MachineMemoryActionApplyBatchReceiptError) as ctx,
        ):
            self._run_batch()

        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertIn("successful actions retained", str(ctx.exception))
        self.assertEqual(self._applied_ids(), set(self.action_ids))
        self.assertEqual(self._batch_receipts(), [])
        self.assertFalse(self._runtime_path().exists())
        self.assertFalse(self._wiki_log_path().exists())

    def test_runtime_history_write_fail_unlinks_receipt_and_writes_no_wiki_log(self) -> None:
        with (
            patch.object(batch_mod, "append_runtime_history", side_effect=OSError("runtime failed")),
            self.assertRaises(batch_mod.MachineMemoryActionApplyBatchReceiptError),
        ):
            self._run_batch()

        self.assertEqual(self._applied_ids(), set(self.action_ids))
        self.assertEqual(self._batch_receipts(), [])
        self.assertFalse(self._runtime_path().exists())
        self.assertFalse(self._wiki_log_path().exists())

    def test_wiki_log_write_fail_unlinks_receipt_and_restores_runtime(self) -> None:
        with (
            patch.object(batch_mod, "append_wiki_log", side_effect=OSError("wiki failed")),
            self.assertRaises(batch_mod.MachineMemoryActionApplyBatchReceiptError),
        ):
            self._run_batch()

        self.assertEqual(self._applied_ids(), set(self.action_ids))
        self.assertEqual(self._batch_receipts(), [])
        self.assertFalse(self._runtime_path().exists())
        self.assertFalse(self._wiki_log_path().exists())

    def test_pre_seeded_runtime_and_wiki_bytes_preserved_on_mid_tx_failure(self) -> None:
        runtime_seed = b'{"event_type":"pre-existing"}\n'
        wiki_seed = "# 知识库日志\n\nprior log\n".encode()
        self._runtime_path().parent.mkdir(parents=True, exist_ok=True)
        self._runtime_path().write_bytes(runtime_seed)
        self._wiki_log_path().parent.mkdir(parents=True, exist_ok=True)
        self._wiki_log_path().write_bytes(wiki_seed)

        with (
            patch.object(batch_mod, "append_wiki_log", side_effect=OSError("wiki failed")),
            self.assertRaises(batch_mod.MachineMemoryActionApplyBatchReceiptError),
        ):
            self._run_batch()

        self.assertEqual(self._applied_ids(), set(self.action_ids))
        self.assertEqual(self._batch_receipts(), [])
        self.assertEqual(self._runtime_path().read_bytes(), runtime_seed)
        self.assertEqual(self._wiki_log_path().read_bytes(), wiki_seed)

    def test_rollback_failure_raises_half_write_loud(self) -> None:
        self._runtime_path().parent.mkdir(parents=True, exist_ok=True)
        self._runtime_path().write_text('{"event_type":"pre-existing"}\n', encoding="utf-8")

        with (
            patch.object(batch_mod, "append_wiki_log", side_effect=OSError("wiki failed")),
            patch.object(batch_mod, "_restore_file_bytes", side_effect=OSError("restore failed")),
            self.assertRaises(batch_mod.MachineMemoryActionApplyBatchReceiptHalfWriteError) as ctx,
        ):
            self._run_batch()

        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertIn("restore failed", str(ctx.exception.__cause__))
        self.assertIn("tx_error=wiki failed", str(ctx.exception))
        self.assertIn("rollback_error=restore failed", str(ctx.exception))

    def test_wiki_log_write_fail_rolls_back_audit_mirror(self) -> None:
        audit_seed = b'{"event_id":"pre-existing-audit"}\n'
        self._audit_path().parent.mkdir(parents=True, exist_ok=True)
        self._audit_path().write_bytes(audit_seed)

        with (
            patch.object(batch_mod, "append_wiki_log", side_effect=OSError("wiki failed")),
            self.assertRaises(batch_mod.MachineMemoryActionApplyBatchReceiptError),
        ):
            self._run_batch()

        self.assertEqual(self._applied_ids(), set(self.action_ids))
        self.assertEqual(self._batch_receipts(), [])
        self.assertFalse(self._runtime_path().exists())
        self.assertFalse(self._wiki_log_path().exists())
        # audit jsonl restored to pre-TX bytes: dangling batch audit record must be gone
        self.assertEqual(self._audit_path().read_bytes(), audit_seed)

    def test_dry_run_wiki_log_fail_still_rolls_back_batch_metadata(self) -> None:
        with (
            patch.object(batch_mod, "_build_batch_id", return_value="batch-dry-tx"),
            patch("aiwiki.app_compile.apply_machine_memory_action", side_effect=self._apply_one),
            patch.object(batch_mod, "append_wiki_log", side_effect=OSError("wiki failed")),
            self.assertRaises(batch_mod.MachineMemoryActionApplyBatchReceiptError),
        ):
            batch_mod.apply_machine_memory_actions_batch(self.root, self.action_ids, dry_run=True)

        # stubbed dry-run has no per-action mutations
        self.assertEqual(self._applied_ids(), set())
        self.assertEqual(self._batch_receipts(), [])
        self.assertFalse(self._runtime_path().exists())
        self.assertFalse(self._wiki_log_path().exists())
        self.assertFalse(self._audit_path().exists())


if __name__ == "__main__":
    unittest.main()
