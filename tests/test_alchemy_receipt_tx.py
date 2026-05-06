from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiwiki.runner.alchemy as runner_alchemy
from aiwiki.app_compile import ask_question
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import execution_receipt_history_path
from aiwiki.app_utils import parse_frontmatter, render_frontmatter, sha256_bytes
from aiwiki.execution import alchemy as alchemy_mod
from aiwiki.execution.alchemy import CANDIDATE_ELIXIR_DIR, ELIXIR_DIR, PromoteHalfWriteError, PromoteReceiptError
from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH
from aiwiki.execution.candidates import promote_candidate
from aiwiki.render.paths import execution_receipts_dir


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class AlchemyReceiptTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        ensure_layout(self.root)
        (self.root / "prompts" / "compile.md").write_text("Compile prompt fixture.\n", encoding="utf-8")
        (self.root / "prompts" / "ask.md").write_text("Ask prompt fixture.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _make_promoted_corpus(self) -> str:
        result = ask_question(self.root, "Should we increase transformer training spend?", "report")
        promote_candidate(self.root, result["path"])
        return str(result["active_corpus_id"])

    def _candidate_path(self, elixir_id: str) -> Path:
        return self.root / CANDIDATE_ELIXIR_DIR / f"{elixir_id}.md"

    def _settled_path(self, elixir_id: str) -> Path:
        return self.root / ELIXIR_DIR / f"{elixir_id}.md"

    def _start_candidate_elixir(self, topic: str = "receipt tx") -> str:
        started = alchemy_mod.start_elixir(self.root, self._make_promoted_corpus(), topic=topic, protocol="general")
        alchemy_mod.finalize_elixir(self.root, elixir_id=str(started["elixir_id"]))
        return str(started["elixir_id"])

    def _write_judgment_fixture(self) -> tuple[str, Path, str, str]:
        target_ref = "wiki/judgments/thesis.md"
        target = self.root / target_ref
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            render_frontmatter(
                {
                    "id": "thesis",
                    "kind": "judgment",
                    "status": "tentative",
                    "title": "Thesis",
                    "protocol": "research",
                    "confidence": "medium",
                }
            )
            + "\n\n# Thesis\n\n## Judgment\n- Existing conclusion.\n",
            encoding="utf-8",
        )
        original_target = target.read_text(encoding="utf-8")
        before_hash = sha256_bytes(original_target.encode("utf-8"))
        proposal_id = "alchemy-judge-proposal-r96"
        proposal_path = self.root / "output" / "_proposals" / "judge" / f"{proposal_id}.md"
        proposal_path.parent.mkdir(parents=True, exist_ok=True)
        proposal_path.write_text(
            render_frontmatter(
                {
                    "kind": "alchemy-judge-proposal",
                    "proposal_id": proposal_id,
                    "state": "accepted",
                    "target_file": target_ref,
                    "target_kind": "judgment",
                    "before_hash": before_hash,
                }
            )
            + "\n\n# Judge Proposal\n\n"
            + "<!-- aiwiki:accepted-judge-refresh:start -->\n"
            + "## Proposed Judgment Update\n- Accepted refresh.\n"
            + "<!-- aiwiki:accepted-judge-refresh:end -->\n",
            encoding="utf-8",
        )
        return target_ref, target, proposal_path.relative_to(self.root).as_posix(), original_target

    def _receipt_files(self) -> set[str]:
        receipts_dir = execution_receipts_dir(self.root)
        if not receipts_dir.exists():
            return set()
        return {p.name for p in receipts_dir.glob("*.json")}

    def test_persist_receipt_helper_uses_atomic_write(self) -> None:
        receipt_path = "output/control/execution-receipts/helper-atomic.json"
        receipt = {
            "kind": "execution-receipt",
            "operation": "helper-atomic",
            "action_id": "helper-atomic",
            "subject_kind": "test",
            "subject_id": "helper",
            "applied_at": "2026-01-01T00:00:00+00:00",
            "receipt_path": receipt_path,
            "revert_supported": False,
        }

        def fail_write_text(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("Path.write_text must not be used")

        with patch.object(Path, "write_text", autospec=True, side_effect=fail_write_text):
            result = alchemy_mod._persist_receipt_transactionally(
                self.root,
                receipt=receipt,
                elixir_id="helper",
                operation="helper-atomic",
                rollback_data=lambda: None,
                receipt_error_cls=PromoteReceiptError,
                half_write_error_factory=lambda phase: PromoteHalfWriteError(
                    settled_path=self.root / "settled.md", candidate_path=self.root / "candidate.md", phase=phase
                ),
            )

        self.assertEqual(result, self.root / receipt_path)
        self.assertEqual(json.loads(result.read_text(encoding="utf-8"))["action_id"], "helper-atomic")

    def test_promote_receipt_failure_restores_both_files(self) -> None:
        elixir_id = self._start_candidate_elixir()
        candidate_before = self._candidate_path(elixir_id).read_bytes()
        receipts_before = self._receipt_files()

        with patch.object(alchemy_mod, "append_execution_receipt_history", side_effect=OSError("history failed")):
            with self.assertRaises(PromoteReceiptError):
                alchemy_mod.promote_elixir(self.root, elixir_id=elixir_id)

        self.assertFalse(self._settled_path(elixir_id).exists())
        self.assertEqual(self._candidate_path(elixir_id).read_bytes(), candidate_before)
        self.assertEqual(self._receipt_files(), receipts_before)

    def test_promote_rollback_failure_raises_half_write(self) -> None:
        elixir_id = self._start_candidate_elixir()

        with (
            patch.object(alchemy_mod, "append_execution_receipt_history", side_effect=OSError("history failed")),
            patch.object(alchemy_mod, "_restore_file_bytes", side_effect=OSError("restore failed")),
            self.assertRaises(PromoteHalfWriteError),
        ):
            alchemy_mod.promote_elixir(self.root, elixir_id=elixir_id)

    def test_promote_success_path_unchanged(self) -> None:
        elixir_id = self._start_candidate_elixir()

        result = alchemy_mod.promote_elixir(self.root, elixir_id=elixir_id, note="ok")

        self.assertEqual(result["elixir_state"], "settled")
        self.assertTrue(self._settled_path(elixir_id).exists())
        self.assertEqual(parse_frontmatter(self._candidate_path(elixir_id).read_text(encoding="utf-8"))["elixir_state"], "superseded")
        receipt = json.loads((self.root / str(result["receipt_path"])).read_text(encoding="utf-8"))
        self.assertEqual(receipt["operation"], "promote")
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root))[-1]["action_id"], receipt["action_id"])

    def test_promote_hash_compute_failure_rolls_back(self) -> None:
        """R96.0 NIT-1: hash compute is inside protected region; failure must restore both files."""
        elixir_id = self._start_candidate_elixir()
        candidate_before = self._candidate_path(elixir_id).read_bytes()
        receipts_before = self._receipt_files()

        with patch.object(alchemy_mod, "compute_file_sha256", side_effect=OSError("hash compute failed")):
            with self.assertRaises(PromoteReceiptError):
                alchemy_mod.promote_elixir(self.root, elixir_id=elixir_id)

        self.assertFalse(self._settled_path(elixir_id).exists())
        self.assertEqual(self._candidate_path(elixir_id).read_bytes(), candidate_before)
        self.assertEqual(self._receipt_files(), receipts_before)

    def test_judge_proposal_apply_target_write_failure(self) -> None:
        _target_ref, target, proposal_rel, original_target = self._write_judgment_fixture()
        proposal_path = self.root / proposal_rel
        original_proposal = proposal_path.read_text(encoding="utf-8")

        def flaky(path: Path, content: str, **kwargs: object) -> None:
            if path == target:
                raise OSError("target write failed")
            runner_alchemy.atomic_write_text(path, content, **kwargs)

        with patch.object(runner_alchemy, "atomic_write_text", side_effect=flaky):
            with self.assertRaises(runner_alchemy.AlchemyJudgeProposalApplyError):
                runner_alchemy.run_alchemy_judge_proposal_apply(self.root, proposal_rel)

        self.assertEqual(target.read_text(encoding="utf-8"), original_target)
        self.assertEqual(proposal_path.read_text(encoding="utf-8"), original_proposal)
        self.assertEqual(self._receipt_files(), set())

    def test_judge_proposal_apply_proposal_write_failure(self) -> None:
        _target_ref, target, proposal_rel, original_target = self._write_judgment_fixture()
        proposal_path = self.root / proposal_rel
        original_proposal = proposal_path.read_text(encoding="utf-8")
        original_atomic = runner_alchemy.atomic_write_text

        def flaky(path: Path, content: str, **kwargs: object) -> None:
            if path == proposal_path:
                raise OSError("proposal write failed")
            original_atomic(path, content, **kwargs)

        with patch.object(runner_alchemy, "atomic_write_text", side_effect=flaky):
            with self.assertRaises(runner_alchemy.AlchemyJudgeProposalApplyError):
                runner_alchemy.run_alchemy_judge_proposal_apply(self.root, proposal_rel)

        self.assertEqual(target.read_text(encoding="utf-8"), original_target)
        self.assertEqual(proposal_path.read_text(encoding="utf-8"), original_proposal)
        self.assertEqual(self._receipt_files(), set())

    def test_judge_proposal_apply_receipt_write_failure(self) -> None:
        _target_ref, target, proposal_rel, original_target = self._write_judgment_fixture()
        proposal_path = self.root / proposal_rel
        original_proposal = proposal_path.read_text(encoding="utf-8")
        original_atomic = runner_alchemy.atomic_write_text

        def flaky(path: Path, content: str, **kwargs: object) -> None:
            if "execution-receipts" in path.parts and path.suffix == ".json":
                raise OSError("receipt write failed")
            original_atomic(path, content, **kwargs)

        with patch.object(runner_alchemy, "atomic_write_text", side_effect=flaky):
            with self.assertRaises(runner_alchemy.AlchemyJudgeProposalApplyError):
                runner_alchemy.run_alchemy_judge_proposal_apply(self.root, proposal_rel)

        self.assertEqual(target.read_text(encoding="utf-8"), original_target)
        self.assertEqual(proposal_path.read_text(encoding="utf-8"), original_proposal)
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root)), [])

    def test_judge_proposal_apply_history_append_failure_truncates_residue(self) -> None:
        _target_ref, target, proposal_rel, original_target = self._write_judgment_fixture()
        proposal_path = self.root / proposal_rel
        original_proposal = proposal_path.read_text(encoding="utf-8")
        history_path = execution_receipt_history_path(self.root)
        audit_path = self.root / AUDIT_STREAM_PATH

        # R96.0 NIT-2: seed pre-existing jsonl bytes so we verify exact restore
        # to pre-TX size (not just empty-after-rollback).
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

        with patch.object(runner_alchemy, "append_execution_receipt_history", side_effect=partial_history):
            with self.assertRaises(runner_alchemy.AlchemyJudgeProposalApplyError):
                runner_alchemy.run_alchemy_judge_proposal_apply(self.root, proposal_rel)

        self.assertEqual(target.read_text(encoding="utf-8"), original_target)
        self.assertEqual(proposal_path.read_text(encoding="utf-8"), original_proposal)
        # Pre-existing bytes preserved exactly; residue line truncated.
        self.assertEqual(history_path.stat().st_size, history_size_seeded)
        self.assertEqual(history_path.read_text(encoding="utf-8"), seeded_history)
        self.assertEqual(audit_path.stat().st_size, audit_size_seeded)
        self.assertEqual(audit_path.read_text(encoding="utf-8"), seeded_audit)
        self.assertEqual(self._receipt_files(), set())

    def test_judge_proposal_apply_phase2_failure_does_not_rollback(self) -> None:
        _target_ref, target, proposal_rel, original_target = self._write_judgment_fixture()
        proposal_path = self.root / proposal_rel

        with (
            patch.object(runner_alchemy, "append_runtime_history", side_effect=OSError("runtime failed")),
            self.assertLogs(runner_alchemy.logger, level="WARNING") as log_ctx,
        ):
            result = runner_alchemy.run_alchemy_judge_proposal_apply(self.root, proposal_rel)

        self.assertEqual(result["status"], "applied")
        self.assertNotEqual(target.read_text(encoding="utf-8"), original_target)
        self.assertEqual(parse_frontmatter(proposal_path.read_text(encoding="utf-8"))["state"], "applied")
        self.assertTrue((self.root / str(result["receipt_path"])).exists())
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root))[-1]["action_id"], Path(str(result["receipt_path"])).stem)
        self.assertTrue(any("runtime-history append failed" in msg for msg in log_ctx.output))

    def test_judge_proposal_apply_rollback_failure_loud(self) -> None:
        _target_ref, _target, proposal_rel, _original_target = self._write_judgment_fixture()

        with (
            patch.object(runner_alchemy, "append_execution_receipt_history", side_effect=OSError("history failed")),
            patch.object(runner_alchemy, "_restore_file_bytes", side_effect=OSError("restore failed")),
            self.assertRaises(runner_alchemy.AlchemyJudgeProposalApplyHalfWriteError),
        ):
            runner_alchemy.run_alchemy_judge_proposal_apply(self.root, proposal_rel)
