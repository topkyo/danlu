from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import l3_proposal_state_path, runtime_history_path
from aiwiki.execution import l3_proposals as l3_mod
from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class L3ProposalCreateTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        ensure_layout(self.root)
        self.target = self.root / "prompts" / "ask.md"
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text("# Ask\n\nBaseline prompt.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _create(self, proposal_id: str = "prop-create-tx") -> dict[str, object]:
        return l3_mod.create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id=proposal_id,
            target_file="prompts/ask.md",
            content="Updated prompt.\n",
            rationale="tx test",
            evidence_refs=["e1"],
            signal_ids=["sig-1"],
        )

    def _state_path(self) -> Path:
        return l3_proposal_state_path(self.root)

    def _runtime_path(self) -> Path:
        return runtime_history_path(self.root)

    def _audit_path(self) -> Path:
        return self.root / AUDIT_STREAM_PATH

    def _wiki_log_path(self) -> Path:
        return self.root / "wiki" / "indexes" / "log.md"

    def _proposal_page(self, proposal_id: str = "prop-create-tx") -> Path:
        return self.root / "output" / "_proposals" / "prompt" / f"{proposal_id}.md"

    def _seed_state(self) -> bytes:
        self._state_path().parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            {
                "version": 1,
                "proposals": [
                    {
                        "kind": "prompt_proposal",
                        "proposal_id": "existing-proposal",
                        "target_file": "prompts/ask.md",
                        "state": "candidate",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        self._state_path().write_text(content, encoding="utf-8")
        return self._state_path().read_bytes()

    def test_happy_path_writes_state_page_runtime_audit_and_wiki_log(self) -> None:
        result = self._create()

        self.assertEqual(result["proposal_id"], "prop-create-tx")
        state = json.loads(self._state_path().read_text(encoding="utf-8"))
        self.assertEqual(state["proposals"][0]["proposal_id"], "prop-create-tx")
        self.assertTrue(self._proposal_page().exists())
        self.assertIn("# L3 Proposal: prop-create-tx", self._proposal_page().read_text(encoding="utf-8"))
        self.assertEqual(_read_jsonl(self._runtime_path())[-1]["event_type"], "l3-proposal-create")
        self.assertIn("runtime_history", {item.get("source_stream") for item in _read_jsonl(self._audit_path())})
        self.assertIn("l3-proposal-create", self._wiki_log_path().read_text(encoding="utf-8"))

    def test_state_write_failure_rolls_back_without_other_artifacts(self) -> None:
        state_before = self._seed_state()

        with (
            patch.object(l3_mod, "save_l3_proposal_state", side_effect=OSError("state failed")),
            self.assertRaises(l3_mod.L3ProposalCreateError) as ctx,
        ):
            self._create()

        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertEqual(self._state_path().read_bytes(), state_before)
        self.assertFalse(self._proposal_page().exists())
        self.assertFalse(self._runtime_path().exists())
        self.assertFalse(self._audit_path().exists())
        self.assertFalse(self._wiki_log_path().exists())

    def test_page_write_failure_restores_state_and_removes_page(self) -> None:
        state_before = self._seed_state()

        with (
            patch.object(l3_mod, "_persist_l3_proposal_page", side_effect=OSError("page failed")),
            self.assertRaises(l3_mod.L3ProposalCreateError),
        ):
            self._create()

        self.assertEqual(self._state_path().read_bytes(), state_before)
        self.assertFalse(self._proposal_page().exists())
        self.assertFalse(self._runtime_path().exists())
        self.assertFalse(self._audit_path().exists())
        self.assertFalse(self._wiki_log_path().exists())

    def test_runtime_history_failure_restores_state_page_runtime_audit_and_no_wiki(self) -> None:
        state_before = self._seed_state()
        self._runtime_path().parent.mkdir(parents=True, exist_ok=True)
        runtime_seed = json.dumps({"event_type": "pre-existing"}) + "\n"
        self._runtime_path().write_text(runtime_seed, encoding="utf-8")
        self._audit_path().parent.mkdir(parents=True, exist_ok=True)
        audit_seed = json.dumps({"audit_event_id": "pre-existing-audit"}) + "\n"
        self._audit_path().write_text(audit_seed, encoding="utf-8")

        with (
            patch.object(l3_mod, "append_runtime_history", side_effect=OSError("runtime failed")),
            self.assertRaises(l3_mod.L3ProposalCreateError),
        ):
            self._create()

        self.assertEqual(self._state_path().read_bytes(), state_before)
        self.assertFalse(self._proposal_page().exists())
        self.assertEqual(self._runtime_path().read_text(encoding="utf-8"), runtime_seed)
        self.assertEqual(self._audit_path().read_text(encoding="utf-8"), audit_seed)
        self.assertFalse(self._wiki_log_path().exists())

    def test_wiki_log_failure_rolls_back_all_prior_writes(self) -> None:
        state_before = self._seed_state()

        with (
            patch.object(l3_mod, "append_wiki_log", side_effect=OSError("wiki failed")),
            self.assertRaises(l3_mod.L3ProposalCreateError),
        ):
            self._create()

        self.assertEqual(self._state_path().read_bytes(), state_before)
        self.assertFalse(self._proposal_page().exists())
        self.assertFalse(self._runtime_path().exists())
        self.assertFalse(self._audit_path().exists())
        self.assertFalse(self._wiki_log_path().exists())

    def test_pre_seeded_preservation_restores_exact_bytes_on_mid_tx_failure(self) -> None:
        state_before = self._seed_state()
        self._runtime_path().parent.mkdir(parents=True, exist_ok=True)
        runtime_seed = json.dumps({"event_type": "pre-existing-runtime"}) + "\n"
        self._runtime_path().write_text(runtime_seed, encoding="utf-8")
        self._audit_path().parent.mkdir(parents=True, exist_ok=True)
        audit_seed = json.dumps({"audit_event_id": "pre-existing-audit"}) + "\n"
        self._audit_path().write_text(audit_seed, encoding="utf-8")
        wiki_seed = "# 知识库日志\n\nprior log\n"
        self._wiki_log_path().parent.mkdir(parents=True, exist_ok=True)
        self._wiki_log_path().write_text(wiki_seed, encoding="utf-8")

        with (
            patch.object(l3_mod, "append_wiki_log", side_effect=OSError("wiki failed")),
            self.assertRaises(l3_mod.L3ProposalCreateError),
        ):
            self._create()

        self.assertEqual(self._state_path().read_bytes(), state_before)
        self.assertEqual(json.loads(self._state_path().read_text(encoding="utf-8"))["proposals"][0]["proposal_id"], "existing-proposal")
        self.assertFalse(self._proposal_page().exists())
        self.assertEqual(self._runtime_path().read_text(encoding="utf-8"), runtime_seed)
        self.assertEqual(self._audit_path().read_text(encoding="utf-8"), audit_seed)
        self.assertEqual(self._wiki_log_path().read_text(encoding="utf-8"), wiki_seed)

    def test_rollback_failure_raises_half_write_loud(self) -> None:
        state_before = self._seed_state()

        with (
            patch.object(l3_mod, "append_wiki_log", side_effect=OSError("wiki failed")),
            patch.object(l3_mod, "_restore_file_bytes", side_effect=OSError("restore failed")),
            self.assertRaises(l3_mod.L3ProposalCreateHalfWriteError) as ctx,
        ):
            self._create()

        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertIn("restore failed", str(ctx.exception.__cause__))
        self.assertIn("tx_error=wiki failed", str(ctx.exception))
        self.assertIn("rollback_error=restore failed", str(ctx.exception))
        self.assertNotEqual(self._state_path().read_bytes(), state_before)

    def test_wiki_log_none_snapshot_unlinks_created_log_on_rollback(self) -> None:
        state_before = self._seed_state()
        self.assertFalse(self._wiki_log_path().exists())

        def append_then_fail(root: Path, category: str, title: str, details: list[str]) -> None:
            from aiwiki.render.paths import append_wiki_log

            append_wiki_log(root, category, title, details)
            raise OSError("wiki failed after write")

        with (
            patch.object(l3_mod, "append_wiki_log", side_effect=append_then_fail),
            self.assertRaises(l3_mod.L3ProposalCreateError),
        ):
            self._create()

        self.assertEqual(self._state_path().read_bytes(), state_before)
        self.assertFalse(self._proposal_page().exists())
        self.assertFalse(self._runtime_path().exists())
        self.assertFalse(self._audit_path().exists())
        self.assertFalse(self._wiki_log_path().exists())
