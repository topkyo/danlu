from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.app_compile import apply_material_archive, compile_wiki
from aiwiki.app_content import ingest_source
from aiwiki.app_execution import load_execution_bundle
from aiwiki.app_protocol import ensure_layout, save_manifest
from aiwiki.app_state import (
    CorruptStateError,
    execution_batch_receipt_path,
    l3_proposal_state_path,
    load_manifest,
    load_runtime_history,
    load_runtime_history_strict,
    runtime_history_path,
    save_machine_memory_action_state,
)
from aiwiki.execution.archive import revert_material_archive
from aiwiki.execution.l3_proposals import apply_l3_proposal, create_l3_proposal, revert_l3_proposal
from aiwiki.execution.machine_memory_actions import revert_machine_memory_action
from aiwiki.execution.machine_memory_batch import _load_latest_action_apply_batch_receipt


class StrictReadMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        ensure_layout(self.root)
        (self.root / "prompts").mkdir(parents=True, exist_ok=True)
        (self.root / "prompts" / "ask.md").write_text("Original ask prompt.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _prepare_archive_candidate(self) -> dict[str, str]:
        archive_source = self.root / "archive-candidate.md"
        archive_source.write_text("# Obscure Legacy Note\n\nMisc.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(archive_source), title="Obscure Legacy Note")
        compile_wiki(self.root)
        manifest = load_manifest(self.root)
        for manifest_entry in manifest["entries"]:
            if manifest_entry["id"] == entry["id"]:
                manifest_entry["imported_at"] = "2025-01-01T00:00:00+00:00"
                manifest_entry["updated_at"] = "2025-01-01T00:00:00+00:00"
                break
        save_manifest(self.root, manifest)
        compile_wiki(self.root)
        compile_wiki(self.root)
        return entry

    def test_revert_machine_memory_corrupt_receipt_raises(self) -> None:
        receipt_path = self.root / "output/control/execution-receipts/mm.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text("{bad", encoding="utf-8")
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "mm-action",
                        "status": "resolved",
                        "active": True,
                        "last_receipt_path": "output/control/execution-receipts/mm.json",
                    }
                ],
            },
        )

        with self.assertRaises(CorruptStateError):
            revert_machine_memory_action(self.root, "mm-action")

    def test_l3_revert_corrupt_receipt_raises(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-corrupt",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
        )
        applied = apply_l3_proposal(self.root, "prop-corrupt")
        receipt_path = self.root / str(applied["receipt_path"])
        receipt_path.write_text("{bad", encoding="utf-8")

        with self.assertRaises(CorruptStateError):
            revert_l3_proposal(self.root, str(applied["receipt_path"]))

    def test_archive_revert_corrupt_receipt_raises(self) -> None:
        entry = self._prepare_archive_candidate()
        applied = apply_material_archive(self.root, entry["id"], note="Archive stale source.")
        receipt_path = self.root / str(applied["receipt_path"])
        receipt_path.write_text("{bad", encoding="utf-8")

        with self.assertRaises(CorruptStateError):
            revert_material_archive(self.root, entry["id"])

    def test_batch_select_corrupt_runtime_history_raises(self) -> None:
        path = runtime_history_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"event_type":"action-apply-batch"}\n{bad\n', encoding="utf-8")

        with self.assertRaises(CorruptStateError):
            _load_latest_action_apply_batch_receipt(self.root, None)

    def test_load_runtime_history_strict_vs_best_effort(self) -> None:
        path = runtime_history_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"event_type":"ok"}\n{bad\n', encoding="utf-8")

        self.assertEqual(load_runtime_history(self.root), [{"event_type": "ok"}])
        with self.assertRaises(CorruptStateError):
            load_runtime_history_strict(self.root)

    def test_execution_bundle_corrupt_raises(self) -> None:
        bundle_path = self.root / "output/control/execution-bundles/bad.json"
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text("{bad", encoding="utf-8")

        with self.assertRaises(CorruptStateError):
            load_execution_bundle(bundle_path)

    def test_batch_explicit_corrupt_receipt_raises(self) -> None:
        receipt_path = execution_batch_receipt_path(self.root, "batch-corrupt")
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text("{bad", encoding="utf-8")

        with self.assertRaises(CorruptStateError):
            _load_latest_action_apply_batch_receipt(self.root, "batch-corrupt")

    def test_batch_history_corrupt_receipt_raises(self) -> None:
        receipt_path = self.root / "output/control/execution-batches/batch-from-history.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text("{bad", encoding="utf-8")
        history_path = runtime_history_path(self.root)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(
            json.dumps(
                {
                    "event_type": "action-apply-batch",
                    "batch_id": "batch-from-history",
                    "receipt_path": "output/control/execution-batches/batch-from-history.json",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(CorruptStateError):
            _load_latest_action_apply_batch_receipt(self.root, None)


if __name__ == "__main__":
    unittest.main()
