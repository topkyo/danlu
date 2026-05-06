"""R94.5 — apply/revert L3 proposal critical pairs are transactional and atomic.

Pre-R94.5 `revert_l3_proposal` had no protection over `target write → revert
receipt write → state save`. A failed state save would leave target restored
to before_content but state still `accepted`, breaking the receipt→state
mapping and forcing human merge on retry.

These tests cover:
- revert state-save failure rolls back target file
- revert receipt-write failure rolls back target file
- revert phase 2 (page render / runtime history) failure does NOT roll back
- revert rollback-itself-fails preserves original exception + warns
- apply path uses atomic_write_text (regression guard for R94.5 switch)

R95.3 — apply phase 2 false-history rollback. Pre-R95.3 phase 2 order was
`append_execution_receipt_history → save_l3_proposal_state → page → runtime →
wiki_log`. Any post-history failure raised L3PostApplyAuditError after target
revert, but execution-receipts.jsonl + audit.jsonl retained a false "apply
success" line. R95.3 reorders to put history append after state+page, and
extends the rollback handler to truncate both jsonls back to size_before.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aiwiki import app_execution as app_execution_mod
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import execution_receipt_history_path
from aiwiki.execution import l3_proposals as l3_mod
from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH
from aiwiki.execution.l3_proposals import (
    L3PostApplyAuditError,
    L3RevertError,
    apply_l3_proposal,
    create_l3_proposal,
    revert_l3_proposal,
)


class _RevertFixture(unittest.TestCase):
    """Build a fully-applied L3 proposal so revert_l3_proposal can run."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        ensure_layout(self.root)
        self.target = self.root / "prompts" / "ask.md"
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.before_content = "Original ask prompt.\n"
        self.after_content = "Updated ask prompt.\n"
        self.target.write_text(self.before_content, encoding="utf-8")
        self.proposal_id = "prop-r945-tx"
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id=self.proposal_id,
            target_file="prompts/ask.md",
            content=self.after_content,
            evidence_refs=["e1", "e2", "e3", "e4", "e5"],
        )
        result = apply_l3_proposal(self.root, self.proposal_id)
        # Receipt id we'll feed to revert.
        self.receipt_path = self.root / result["receipt_path"]
        self.receipt_id = self.receipt_path.stem
        # Sanity: after apply, target == after_content.
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.after_content)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class RevertL3ProposalTransactionTests(_RevertFixture):
    def test_revert_state_save_failure_rolls_back_target_file(self) -> None:
        with patch.object(
            l3_mod,
            "save_l3_proposal_state",
            side_effect=OSError("simulated state save failure"),
        ):
            with self.assertRaises(OSError) as ctx:
                revert_l3_proposal(self.root, self.receipt_id, note="trigger")

        self.assertIn("simulated state save failure", str(ctx.exception))
        # Target must be rolled back to the applied (after) content.
        self.assertEqual(
            self.target.read_text(encoding="utf-8"),
            self.after_content,
        )

    def test_revert_receipt_write_failure_rolls_back_target_file(self) -> None:
        # Path-based discrimination (per R94.5 oracle NIT): make the receipt
        # write specifically fail rather than counting calls.
        original_atomic = l3_mod.atomic_write_text

        def flaky(path: Path, content: str, **kw: object) -> None:
            if "execution-receipts" in path.parts and path.suffix == ".json":
                raise OSError("simulated revert-receipt write failure")
            original_atomic(path, content, **kw)

        with patch.object(l3_mod, "atomic_write_text", side_effect=flaky):
            with self.assertRaises(OSError) as ctx:
                revert_l3_proposal(self.root, self.receipt_id, note="trigger")

        self.assertIn("simulated revert-receipt write failure", str(ctx.exception))
        self.assertEqual(
            self.target.read_text(encoding="utf-8"),
            self.after_content,
        )

    def test_revert_state_save_failure_removes_orphan_receipt(self) -> None:
        # R94.5 oracle BLOCK fix: if state save fails AFTER receipt was
        # written, the orphan receipt file must be unlinked — otherwise we
        # leave a false audit record claiming the revert happened.
        receipts_dir = self.root / "output" / "control" / "execution-receipts"
        before_revert = {p.name for p in receipts_dir.glob("*.json")}

        with patch.object(
            l3_mod,
            "save_l3_proposal_state",
            side_effect=OSError("simulated state save failure"),
        ):
            with self.assertRaises(OSError):
                revert_l3_proposal(self.root, self.receipt_id, note="trigger")

        after_revert = {p.name for p in receipts_dir.glob("*.json")}
        self.assertEqual(
            before_revert,
            after_revert,
            msg=f"orphan revert receipt left behind: {after_revert - before_revert}",
        )

    def test_revert_phase2_failure_is_swallowed_with_warning(self) -> None:
        # R94.5 oracle CONCERN fix: phase 2 (history/page/log) is now
        # best-effort. Failure must NOT raise — caller would retry and the
        # retry would see current_hash != after_hash, polluting a successful
        # revert with revert_conflict. Each failed step is logged.
        with (
            patch.object(
                l3_mod,
                "append_runtime_history",
                side_effect=OSError("phase 2 boom"),
            ),
            self.assertLogs(l3_mod.logger, level="WARNING") as log_ctx,
        ):
            result = revert_l3_proposal(self.root, self.receipt_id, note="trigger")

        self.assertEqual(result["state"], "reverted")
        self.assertEqual(
            self.target.read_text(encoding="utf-8"),
            self.before_content,
        )
        self.assertTrue(
            any("phase 2 step append_runtime_history failed" in msg for msg in log_ctx.output),
            msg=f"expected phase 2 warning, got: {log_ctx.output}",
        )

    def test_revert_rollback_failure_preserves_original_exception(self) -> None:
        # Forward write to target succeeds; rollback (atomic_write_bytes) fails;
        # state save fails — original state-save error must surface, rollback
        # warning must be logged.
        with (
            patch.object(
                l3_mod,
                "atomic_write_bytes",
                side_effect=OSError("rollback also failed"),
            ),
            patch.object(
                l3_mod,
                "save_l3_proposal_state",
                side_effect=OSError("simulated state corruption"),
            ),
            self.assertLogs(l3_mod.logger, level="WARNING") as log_ctx,
            self.assertRaises(OSError) as ctx,
        ):
            revert_l3_proposal(self.root, self.receipt_id, note="trigger")

        self.assertIn("simulated state corruption", str(ctx.exception))
        self.assertTrue(
            any("rollback failed" in msg for msg in log_ctx.output),
            msg=f"expected rollback warning, got: {log_ctx.output}",
        )


class ApplyL3ProposalAtomicTests(_RevertFixture):
    """Regression guard: apply path now routes through atomic_write_text /
    atomic_write_bytes (R94.5 switch from non-atomic Path.write_*)."""

    def test_apply_path_uses_atomic_write_text(self) -> None:
        # Re-create a fresh proposal in a sibling target (so applying it
        # exercises a forward write path) and verify atomic_write_text is
        # invoked at least twice (target + receipt).
        target2 = self.root / "prompts" / "answer.md"
        target2.parent.mkdir(parents=True, exist_ok=True)
        target2.write_text("Original answer.\n", encoding="utf-8")
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-atomic-check",
            target_file="prompts/answer.md",
            content="Updated answer.\n",
            evidence_refs=["e1", "e2", "e3", "e4", "e5"],
        )

        original_atomic = l3_mod.atomic_write_text
        calls: list[Path] = []

        def spy(path: Path, content: str, **kw: object) -> None:
            calls.append(path)
            original_atomic(path, content, **kw)

        with patch.object(l3_mod, "atomic_write_text", side_effect=spy):
            apply_l3_proposal(self.root, "prop-atomic-check")

        # At minimum: target file write + receipt write.
        target_writes = [p for p in calls if p == target2]
        self.assertGreaterEqual(
            len(target_writes), 1, msg=f"target not written via atomic_write_text; calls={calls}"
        )
        receipt_writes = [p for p in calls if "execution-receipts" in str(p)]
        self.assertGreaterEqual(
            len(receipt_writes), 1, msg=f"receipt not written via atomic_write_text; calls={calls}"
        )


class _ApplyFixture(unittest.TestCase):
    """Build a candidate L3 proposal so apply_l3_proposal can run fresh."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        ensure_layout(self.root)
        self.target = self.root / "prompts" / "ask.md"
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.before_content = "Original ask prompt.\n"
        self.after_content = "Updated ask prompt.\n"
        self.target.write_text(self.before_content, encoding="utf-8")
        self.proposal_id = "prop-r953-apply"
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id=self.proposal_id,
            target_file="prompts/ask.md",
            content=self.after_content,
            evidence_refs=["e1", "e2", "e3", "e4", "e5"],
        )
        self.history_path = execution_receipt_history_path(self.root)
        self.audit_path = self.root / AUDIT_STREAM_PATH

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _sizes(self) -> tuple[int, int]:
        h = self.history_path.stat().st_size if self.history_path.exists() else 0
        a = self.audit_path.stat().st_size if self.audit_path.exists() else 0
        return h, a


class ApplyL3ProposalFalseHistoryRollbackTests(_ApplyFixture):
    """R95.3 — phase 2 step failures must not leave false apply lines in
    execution-receipts.jsonl or universal audit.jsonl."""

    def test_apply_history_append_failure_rolls_back_target_and_state(self) -> None:
        # If history append itself fails, target must revert and state must
        # restore to candidate. (Reorder puts history append after state save
        # so state-restore is required.)
        h_before, a_before = self._sizes()
        with patch.object(
            l3_mod,
            "append_execution_receipt_history",
            side_effect=OSError("history append boom"),
        ):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, self.proposal_id)

        self.assertEqual(ctx.exception.failed_step, "append_execution_receipt_history")
        self.assertTrue(ctx.exception.target_reverted)
        # Target reverted.
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.before_content)
        # State restored to candidate.
        state = l3_mod.load_l3_proposal_state(self.root)
        proposals = state["proposals"]
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["state"], "candidate")
        # JSONL sizes preserved (truncate covers history append's own partial
        # writes).
        h_after, a_after = self._sizes()
        self.assertEqual(h_after, h_before)
        self.assertEqual(a_after, a_before)

    def test_apply_runtime_history_failure_truncates_execution_history_jsonl(self) -> None:
        h_before, a_before = self._sizes()
        with patch.object(
            l3_mod,
            "append_runtime_history",
            side_effect=OSError("runtime history boom"),
        ):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, self.proposal_id)

        self.assertEqual(ctx.exception.failed_step, "append_runtime_history")
        self.assertTrue(ctx.exception.target_reverted)
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.before_content)
        h_after, _ = self._sizes()
        self.assertEqual(
            h_after,
            h_before,
            msg="execution-receipts.jsonl retained false apply line after runtime_history failure",
        )

    def test_apply_wiki_log_failure_truncates_execution_history_jsonl(self) -> None:
        h_before, _ = self._sizes()
        with patch.object(
            l3_mod,
            "append_wiki_log",
            side_effect=OSError("wiki log boom"),
        ):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, self.proposal_id)

        self.assertEqual(ctx.exception.failed_step, "append_wiki_log")
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.before_content)
        h_after, _ = self._sizes()
        self.assertEqual(
            h_after,
            h_before,
            msg="execution-receipts.jsonl retained false apply line after wiki_log failure",
        )

    def test_apply_runtime_history_failure_truncates_universal_audit_jsonl(self) -> None:
        _, a_before = self._sizes()
        with patch.object(
            l3_mod,
            "append_runtime_history",
            side_effect=OSError("runtime history boom"),
        ):
            with self.assertRaises(L3PostApplyAuditError):
                apply_l3_proposal(self.root, self.proposal_id)

        _, a_after = self._sizes()
        self.assertEqual(
            a_after,
            a_before,
            msg="universal audit.jsonl retained false apply line after runtime_history failure",
        )

    def test_apply_receipt_history_rollback_error_outer_truncate_compensates(self) -> None:
        # R95.3 oracle NIT-3: defend the outer truncate covering
        # `append_execution_receipt_history` step. Simulate inner partial
        # write: primary line appended, universal audit append failed, inner
        # `_durable_truncate` (in app_execution) failed → ReceiptHistoryRollbackError
        # raised. Outer handler must still truncate primary jsonl.
        from aiwiki.app_execution import ReceiptHistoryRollbackError
        from aiwiki.execution import audit_preview as audit_mod

        h_before, a_before = self._sizes()

        # Make the *inner* truncate fail (the one in app_execution module
        # namespace). The outer truncate uses l3_mod._durable_truncate which
        # remains functional.
        def fail_audit(*args: object, **kw: object) -> None:
            raise OSError("audit append boom")

        def fail_inner_truncate(*args: object, **kw: object) -> None:
            raise OSError("inner truncate boom")

        with (
            patch.object(audit_mod, "append_universal_audit_record", side_effect=fail_audit),
            patch.object(app_execution_mod, "_durable_truncate", side_effect=fail_inner_truncate),
        ):
            # Outer wraps the ReceiptHistoryRollbackError from app_execution
            # into L3PostApplyAuditError; outer truncate succeeds, restoring
            # primary jsonl size.
            with self.assertRaises((L3PostApplyAuditError, ReceiptHistoryRollbackError)):
                apply_l3_proposal(self.root, self.proposal_id)

        # Even though inner failed to clean up, outer truncate compensated.
        h_after, a_after = self._sizes()
        self.assertEqual(
            h_after,
            h_before,
            msg="outer truncate did not compensate inner ReceiptHistoryRollbackError",
        )
        self.assertEqual(
            a_after,
            a_before,
            msg="universal audit retained false line after ReceiptHistoryRollbackError",
        )

    def test_apply_truncate_failure_raises_l3_revert_error(self) -> None:
        # If truncate itself fails during rollback, must surface as
        # L3RevertError (same severity as target-revert failure).
        with (
            patch.object(
                l3_mod,
                "append_runtime_history",
                side_effect=OSError("runtime history boom"),
            ),
            patch.object(
                l3_mod,
                "_durable_truncate",
                side_effect=OSError("truncate boom"),
            ),
        ):
            with self.assertRaises(L3RevertError) as ctx:
                apply_l3_proposal(self.root, self.proposal_id)

        self.assertIn("truncate boom", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
