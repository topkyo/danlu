"""Strict-load semantics for L3 proposal authoritative state.

SC-001: ``load_l3_proposal_state`` must raise ``CorruptStateError`` when the
state file exists but is malformed, so governance read-then-write paths cannot
silently overwrite a damaged registry.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import CorruptStateError, l3_proposal_state_path
from aiwiki.execution.l3_proposals import (
    apply_l3_proposal,
    create_l3_proposal,
    default_l3_proposal_state,
    list_l3_proposals,
    load_l3_proposal_state,
    reject_l3_proposal,
)


class L3ProposalStateStrictTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_state(self, contents: str) -> Path:
        path = l3_proposal_state_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        return path

    def test_missing_state_returns_default_empty(self) -> None:
        result = load_l3_proposal_state(self.root)
        self.assertEqual(result, default_l3_proposal_state())

    def test_unparseable_json_raises_corrupt_state_error(self) -> None:
        self._write_state("{not valid json")
        with self.assertRaises(CorruptStateError):
            load_l3_proposal_state(self.root)

    def test_non_object_top_level_raises_corrupt_state_error(self) -> None:
        self._write_state("[]")
        with self.assertRaises(CorruptStateError):
            load_l3_proposal_state(self.root)

    def test_non_list_proposals_field_raises_corrupt_state_error(self) -> None:
        self._write_state('{"version": 1, "proposals": {"bad": "shape"}}')
        with self.assertRaises(CorruptStateError):
            load_l3_proposal_state(self.root)

    def test_corrupt_state_blocks_governance_mutations(self) -> None:
        """Corrupt state must propagate through read-then-write entry points
        that consult the state registry directly (create / list / apply /
        reject). ``revert`` is parametrised by a receipt path rather than a
        proposal_id and consults state only after a valid receipt is loaded,
        so its strict propagation is covered indirectly via
        ``load_l3_proposal_state`` itself.
        """

        self._write_state("{not valid json")
        (self.root / "prompts").mkdir(parents=True, exist_ok=True)
        (self.root / "prompts" / "ask.md").write_text("ask\n", encoding="utf-8")

        with self.assertRaises(CorruptStateError):
            create_l3_proposal(
                self.root,
                kind="prompt_proposal",
                proposal_id="prop-corrupt",
                target_file="prompts/ask.md",
                content="updated\n",
                rationale="should not be silently overwritten",
                evidence_refs=["output/receipts/receipt-1.md"],
                signal_ids=["sig-corrupt"],
            )
        with self.assertRaises(CorruptStateError):
            list_l3_proposals(self.root)
        with self.assertRaises(CorruptStateError):
            apply_l3_proposal(self.root, "prop-corrupt")
        with self.assertRaises(CorruptStateError):
            reject_l3_proposal(self.root, "prop-corrupt", note="x")

    def test_corrupt_state_propagates_through_auto_adopt(self) -> None:
        """SC-001: ``auto_adopt_l3`` must not swallow ``CorruptStateError``.

        Earlier the runner caught a broad ``Exception`` and downgraded the
        result to ``{"error": ..., "degraded": True}``, which would silently
        skip a damaged registry. After the fix, ``CorruptStateError`` must
        propagate so nightly auto-adopt fails closed.
        """

        self._write_state("{not valid json")
        from aiwiki.runner.auto_adopt import auto_adopt_l3

        with self.assertRaises(CorruptStateError):
            auto_adopt_l3(self.root)


if __name__ == "__main__":
    unittest.main()
