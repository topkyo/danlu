from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import l3_proposal_state_path
from aiwiki.execution.l3_proposals import (
    apply_l3_proposal,
    create_l3_proposal,
    list_l3_proposals,
    reject_l3_proposal,
    revert_l3_proposal,
)


class L3ProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        ensure_layout(self.root)
        (self.root / "prompts").mkdir(parents=True, exist_ok=True)
        (self.root / "prompts" / "ask.md").write_text("Original ask prompt.\n", encoding="utf-8")
        (self.root / "schema" / "policies").mkdir(parents=True, exist_ok=True)
        (self.root / "schema" / "policies" / "aging.json").write_text('{"days": 30}\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _state_proposal(self, proposal_id: str) -> dict[str, object]:
        state = json.loads(l3_proposal_state_path(self.root).read_text(encoding="utf-8"))
        return next(item for item in state["proposals"] if item["proposal_id"] == proposal_id)

    def test_create_manual_prompt_proposal_writes_independent_proposal_plane_and_state(self) -> None:
        result = create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-ask-tighten",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
            rationale="Tighten ask behavior.",
            evidence_refs=["output/receipts/receipt-123.md"],
            signal_ids=["sig-20260424-abc123"],
        )

        self.assertEqual(result["state"], "candidate")
        proposal_path = self.root / str(result["proposal_path"])
        self.assertTrue(proposal_path.exists())
        page_text = proposal_path.read_text(encoding="utf-8")
        self.assertIn("kind: \"prompt_proposal\"", page_text)
        self.assertIn("Updated ask prompt.", page_text)
        listed = list_l3_proposals(self.root)
        self.assertEqual([item["proposal_id"] for item in listed], ["prop-ask-tighten"])
        stored = self._state_proposal("prop-ask-tighten")
        self.assertEqual(stored["target_file"], "prompts/ask.md")
        self.assertEqual(stored["state"], "candidate")

    def test_policy_proposal_allows_schema_policies_only(self) -> None:
        result = create_l3_proposal(
            self.root,
            kind="policy_proposal",
            proposal_id="prop-aging",
            target_file="schema/policies/aging.json",
            content='{"days": 45}\n',
        )
        self.assertEqual(result["target_file"], "schema/policies/aging.json")

        (self.root / "schema" / "protocols" / "general").mkdir(parents=True, exist_ok=True)
        (self.root / "schema" / "protocols" / "general" / "index.md").write_text("# General\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "schema/policies"):
            create_l3_proposal(
                self.root,
                kind="policy_proposal",
                proposal_id="prop-core",
                target_file="schema/protocols/general/index.md",
                content="# Changed\n",
            )

    def test_apply_requires_matching_before_hash_and_marks_stale_without_half_write(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-stale",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
        )
        (self.root / "prompts" / "ask.md").write_text("Human edited prompt.\n", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "before_hash mismatch"):
            apply_l3_proposal(self.root, "prop-stale")

        self.assertEqual((self.root / "prompts" / "ask.md").read_text(encoding="utf-8"), "Human edited prompt.\n")
        stored = self._state_proposal("prop-stale")
        self.assertEqual(stored["state"], "stale")
        self.assertEqual(stored["stale_reason"], "before_hash_mismatch")

    def test_reject_candidate_marks_state_without_touching_target_or_receipt_history(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-reject",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
        )

        result = reject_l3_proposal(self.root, "prop-reject", note="not useful")

        self.assertEqual(result["state"], "rejected")
        self.assertEqual((self.root / "prompts" / "ask.md").read_text(encoding="utf-8"), "Original ask prompt.\n")
        self.assertFalse((self.root / ".aiwiki" / "state" / "execution-receipts.jsonl").exists())
        stored = self._state_proposal("prop-reject")
        self.assertEqual(stored["state"], "rejected")
        self.assertEqual(stored["reject_note"], "not useful")
        page_text = (self.root / str(stored["proposal_path"])).read_text(encoding="utf-8")
        self.assertIn("state: \"rejected\"", page_text)

    def test_reject_requires_candidate_state(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-no-reject",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
        )
        apply_l3_proposal(self.root, "prop-no-reject")

        with self.assertRaisesRegex(RuntimeError, "Only candidate"):
            reject_l3_proposal(self.root, "prop-no-reject")

    def test_apply_writes_target_and_receipt_then_clean_revert_restores_before_content(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-apply",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
        )

        applied = apply_l3_proposal(self.root, "prop-apply", note="accept")

        self.assertEqual((self.root / "prompts" / "ask.md").read_text(encoding="utf-8"), "Updated ask prompt.\n")
        receipt_path = self.root / str(applied["receipt_path"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["subject_kind"], "l3_proposal")
        self.assertEqual(receipt["operation"], "apply")
        self.assertTrue(receipt["revert_supported"])
        history = (self.root / ".aiwiki" / "state" / "execution-receipts.jsonl").read_text(encoding="utf-8")
        self.assertIn('"subject_kind": "l3_proposal"', history)

        reverted = revert_l3_proposal(self.root, str(applied["receipt_path"]), note="undo")

        self.assertEqual(reverted["state"], "reverted")
        self.assertEqual((self.root / "prompts" / "ask.md").read_text(encoding="utf-8"), "Original ask prompt.\n")
        stored = self._state_proposal("prop-apply")
        self.assertEqual(stored["state"], "reverted")
        self.assertTrue((self.root / str(reverted["receipt_path"])).exists())

    def test_revert_conflict_writes_human_merge_hint_without_overwriting_target(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-conflict",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
        )
        applied = apply_l3_proposal(self.root, "prop-conflict")
        (self.root / "prompts" / "ask.md").write_text("Human post-apply edit.\n", encoding="utf-8")

        result = revert_l3_proposal(self.root, str(applied["receipt_path"]))

        self.assertEqual(result["state"], "revert_conflict")
        self.assertEqual((self.root / "prompts" / "ask.md").read_text(encoding="utf-8"), "Human post-apply edit.\n")
        hint_path = self.root / str(result["hint_path"])
        self.assertTrue(hint_path.exists())
        self.assertIn("human_merge_required", hint_path.read_text(encoding="utf-8"))
        stored = self._state_proposal("prop-conflict")
        self.assertEqual(stored["state"], "revert_conflict")
