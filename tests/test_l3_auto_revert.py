from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import load_runtime_history
from aiwiki.execution.l3_proposals import (
    L3PostApplyAuditError,
    L3RevertError,
    apply_l3_proposal,
    create_l3_proposal,
)
from aiwiki.runner.auto_adopt import auto_adopt_l3


class L3AutoRevertTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)
        self.target = self.root / "prompts" / "ask.md"
        self.target.write_text("Original ask prompt.\n", encoding="utf-8")
        self.before_content = self.target.read_text(encoding="utf-8")
        self.proposal_id = "prop-auto-revert"
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id=self.proposal_id,
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
            evidence_refs=["e1", "e2", "e3", "e4", "e5"],
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _receipt_path_for(self, error: L3PostApplyAuditError) -> Path:
        return self.root / "output" / "control" / "execution-receipts" / f"{error.action_id}.json"

    def test_revert_on_receipt_history_failure(self) -> None:
        with patch("aiwiki.execution.l3_proposals.append_execution_receipt_history", side_effect=OSError("disk full")):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, self.proposal_id)

        self.assertEqual(self.target.read_text(encoding="utf-8"), self.before_content)
        self.assertFalse(self._receipt_path_for(ctx.exception).exists())

    def test_l3_apply_audit_error_when_universal_audit_fails(self) -> None:
        before_bytes = self.target.read_bytes()

        with patch("aiwiki.execution.audit_preview.append_universal_audit_record", side_effect=OSError("audit fail")):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, self.proposal_id)

        self.assertEqual(ctx.exception.failed_step, "append_execution_receipt_history")
        self.assertEqual(self.target.read_bytes(), before_bytes)
        self.assertFalse(self._receipt_path_for(ctx.exception).exists())

    def test_revert_on_state_save_failure(self) -> None:
        with patch("aiwiki.execution.l3_proposals.save_l3_proposal_state", side_effect=OSError("perm denied")):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, self.proposal_id)

        self.assertEqual(self.target.read_text(encoding="utf-8"), self.before_content)
        self.assertFalse(self._receipt_path_for(ctx.exception).exists())

    def test_revert_on_runtime_history_failure(self) -> None:
        with patch("aiwiki.execution.l3_proposals.append_runtime_history", side_effect=OSError("io")):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, self.proposal_id)

        self.assertEqual(self.target.read_text(encoding="utf-8"), self.before_content)
        self.assertFalse(self._receipt_path_for(ctx.exception).exists())

    def test_revert_on_persist_proposal_page_failure(self) -> None:
        from aiwiki.execution import l3_proposals

        original_persist = l3_proposals._persist_l3_proposal_page
        calls = 0

        def fail_once(root: Path, proposal: dict[str, object]) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("page io")
            original_persist(root, proposal)

        with patch("aiwiki.execution.l3_proposals._persist_l3_proposal_page", side_effect=fail_once):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, self.proposal_id)

        self.assertEqual(ctx.exception.failed_step, "_persist_l3_proposal_page")
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.before_content)
        self.assertFalse(self._receipt_path_for(ctx.exception).exists())

    def test_revert_on_wiki_log_failure(self) -> None:
        with patch("aiwiki.execution.l3_proposals.append_wiki_log", side_effect=OSError("wiki log io")):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, self.proposal_id)

        self.assertEqual(ctx.exception.failed_step, "append_wiki_log")
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.before_content)
        self.assertFalse(self._receipt_path_for(ctx.exception).exists())

    def test_audit_error_carries_failed_step_and_hashes(self) -> None:
        with patch("aiwiki.execution.l3_proposals.append_runtime_history", side_effect=OSError("io")):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, self.proposal_id)

        self.assertEqual(ctx.exception.failed_step, "append_runtime_history")
        self.assertRegex(ctx.exception.before_hash, r"^[0-9a-f]{64}$")
        self.assertRegex(ctx.exception.after_hash, r"^[0-9a-f]{64}$")
        self.assertEqual(ctx.exception.target_file, "prompts/ask.md")
        self.assertTrue(ctx.exception.target_reverted)
        self.assertTrue(ctx.exception.deleted_receipt_path.endswith(f"{ctx.exception.action_id}.json"))

    def test_revert_failure_raises_l3_revert_error(self) -> None:
        # R94.5: rollback now goes through atomic_write_bytes (not Path.write_bytes
        # directly). Patch the atomic helper to simulate rollback failure.
        from aiwiki.execution import l3_proposals as l3_mod

        original_atomic = l3_mod.atomic_write_bytes

        def guarded_atomic_write_bytes(path: Path, data: bytes, **kwargs: object) -> None:
            if path == self.target and data == self.before_content.encode("utf-8"):
                raise OSError("revert also fails")
            original_atomic(path, data, **kwargs)

        with (
            patch("aiwiki.execution.l3_proposals.append_runtime_history", side_effect=OSError("audit fail")),
            patch("aiwiki.execution.l3_proposals.atomic_write_bytes", side_effect=guarded_atomic_write_bytes),
        ):
            with self.assertRaises(L3RevertError):
                apply_l3_proposal(self.root, self.proposal_id)


class AutoAdoptL3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_auto_adopt_l3_marks_auto_reverted_on_audit_error(self) -> None:
        error = L3PostApplyAuditError(
            "l3-proposal-apply-p1",
            "append_runtime_history",
            target_file="prompts/ask.md",
            before_hash="sha256:before",
            after_hash="sha256:after",
            target_reverted=True,
        )
        with (
            patch("aiwiki.execution.l3_proposals.load_l3_proposal_state", return_value={"proposals": [{"proposal_id": "p1", "state": "candidate", "evidence_count": 5}]}),
            patch("aiwiki.execution.l3_proposals.apply_l3_proposal", side_effect=error),
        ):
            result = auto_adopt_l3(self.root)

        self.assertEqual(result["items"][0]["status"], "auto_reverted")
        self.assertEqual(result["items"][0]["revert_status"], "auto_reverted")

    def test_auto_adopt_runtime_history_includes_metadata(self) -> None:
        error = L3PostApplyAuditError(
            "l3-proposal-apply-p1",
            "append_runtime_history",
            target_file="prompts/ask.md",
            before_hash="0" * 64,
            after_hash="1" * 64,
            target_reverted=True,
            deleted_receipt_path="output/control/execution-receipts/l3-proposal-apply-p1.json",
        )
        with (
            patch("aiwiki.execution.l3_proposals.load_l3_proposal_state", return_value={"proposals": [{"proposal_id": "p1", "state": "candidate", "evidence_count": 5}]}),
            patch("aiwiki.execution.l3_proposals.apply_l3_proposal", side_effect=error),
        ):
            auto_adopt_l3(self.root)

        events = load_runtime_history(self.root)
        event = next(item for item in events if item.get("event_type") == "l3-proposal-auto-revert")
        self.assertEqual(event["failed_step"], "append_runtime_history")
        self.assertEqual(event["before_hash"], "0" * 64)
        self.assertEqual(event["after_hash"], "1" * 64)
        self.assertTrue(event["target_reverted"])
        self.assertEqual(event["target_file"], "prompts/ask.md")
        self.assertEqual(event["deleted_receipt_path"], "output/control/execution-receipts/l3-proposal-apply-p1.json")
