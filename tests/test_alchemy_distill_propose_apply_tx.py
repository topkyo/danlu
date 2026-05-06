from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiwiki.runner.alchemy as runner_alchemy
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import execution_receipt_history_path
from aiwiki.app_utils import parse_frontmatter, render_frontmatter
from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH
from aiwiki.render.paths import execution_receipts_dir


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class AlchemyDistillProposeApplyTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _receipt_files(self) -> set[str]:
        receipts_dir = execution_receipts_dir(self.root)
        if not receipts_dir.exists():
            return set()
        return {p.name for p in receipts_dir.glob("*.json")}

    def _distill_candidate_path(self, elixir_id: str) -> Path:
        return self.root / "output" / "_candidates" / "elixirs" / f"{elixir_id}.md"

    def _write_candidate_elixir(self, elixir_id: str, *, iteration: int = 0) -> Path:
        path = self._distill_candidate_path(elixir_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        frontmatter = {
            "kind": "elixir",
            "elixir_id": elixir_id,
            "elixir_state": "draft",
            "iteration": iteration,
            "distill_history_json": "[]",
        }
        path.write_text(render_frontmatter(frontmatter) + f"\n\n# {elixir_id}\n\nBody.\n", encoding="utf-8")
        return path

    def _distill_preview(self, elixir_ids: list[str]) -> dict[str, object]:
        return {
            "status": "ok",
            "scope": "all",
            "selected_count": len(elixir_ids),
            "candidate_count": len(elixir_ids),
            "trace_ids": ["550e8400-e29b-41d4-a716-446655440000"],
            "scope_preview": {},
            "apply_contract": {"primitive": "distill"},
            "candidates": [
                {
                    "candidate_id": f"distill-{elixir_id}",
                    "kind": "elixir_candidate_refresh",
                    "apply_supported": True,
                    "target_ref": elixir_id,
                    "signal_ids": [f"sig-{idx}"],
                }
                for idx, elixir_id in enumerate(elixir_ids, start=1)
            ],
        }

    def _fake_distill(self, _root: Path, elixir_id: str, question: str) -> dict[str, object]:
        path = self._distill_candidate_path(elixir_id)
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
        history = json.loads(str(frontmatter.get("distill_history_json") or "[]"))
        history.append({"iteration": len(history) + 1, "question": question})
        frontmatter["distill_history_json"] = json.dumps(history)
        frontmatter["iteration"] = str(len(history))
        frontmatter["elixir_state"] = "distilling"
        path.write_text(render_frontmatter(frontmatter) + f"\n\n# {elixir_id}\n\nDistilled {len(history)}.\n", encoding="utf-8")
        return {
            "elixir_id": elixir_id,
            "path": path.relative_to(self.root).as_posix(),
            "iteration": len(history),
        }

    def _run_distill(self, elixir_ids: list[str]) -> dict[str, object]:
        with (
            patch.object(runner_alchemy, "run_alchemy_distill_preview", return_value=self._distill_preview(elixir_ids)),
            patch.object(runner_alchemy, "run_alchemy_distill", side_effect=self._fake_distill),
        ):
            return runner_alchemy.run_alchemy_distill_apply(self.root, scope="all", note="distill tx")

    def _write_propose_target(self) -> None:
        target = self.root / "prompts" / "ask.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Ask\n\nBaseline prompt.\n", encoding="utf-8")

    def _write_planner_log(self) -> None:
        path = self.root / ".aiwiki" / "state" / "planner-log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"signal_id": "sig-1"}) + "\n", encoding="utf-8")

    def _propose_preview(self, candidate_ids: list[str]) -> dict[str, object]:
        return {
            "status": "ok",
            "scope": "all",
            "selected_count": len(candidate_ids),
            "candidate_count": len(candidate_ids),
            "planner_log_path": ".aiwiki/state/planner-log.jsonl",
            "trace_ids": ["550e8400-e29b-41d4-a716-446655440000"],
            "scope_preview": {},
            "apply_contract": {"primitive": "propose"},
            "candidates": [
                {
                    "candidate_id": candidate_id,
                    "kind": "proposal_opportunity",
                    "apply_target_file": "prompts/ask.md",
                    "apply_proposal_kind": "prompt_proposal",
                    "target_ref": "prompts/ask.md",
                    "signal_ids": [f"sig-{idx}"],
                }
                for idx, candidate_id in enumerate(candidate_ids, start=1)
            ],
        }

    def _run_propose(self, candidate_ids: list[str]) -> dict[str, object]:
        self._write_planner_log()
        self._write_propose_target()
        with patch.object(runner_alchemy, "run_alchemy_propose_preview", return_value=self._propose_preview(candidate_ids)):
            return runner_alchemy.run_alchemy_propose_apply(self.root, scope="all", note="propose tx")

    def _proposal_page(self, candidate_id: str) -> Path:
        return self.root / "output" / "_proposals" / "prompt" / f"alchemy-{candidate_id}.md"

    def test_distill_happy_path_multi_candidate_writes_receipt_history_audit_runtime(self) -> None:
        for elixir_id in ("elixir-a", "elixir-b"):
            self._write_candidate_elixir(elixir_id)

        result = self._run_distill(["elixir-a", "elixir-b"])

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["refreshed_count"], 2)
        for elixir_id in ("elixir-a", "elixir-b"):
            frontmatter = parse_frontmatter(self._distill_candidate_path(elixir_id).read_text(encoding="utf-8"))
            self.assertEqual(frontmatter["elixir_state"], "distilling")
            self.assertEqual(len(json.loads(str(frontmatter["distill_history_json"]))), 1)
        receipt = json.loads((self.root / str(result["receipt_path"])).read_text(encoding="utf-8"))
        self.assertEqual(receipt["operation"], "alchemy-distill-refresh")
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root))[-1]["action_id"], receipt["action_id"])
        self.assertEqual(_read_jsonl(self.root / ".aiwiki/state/runtime-history.jsonl")[-1]["event_type"], "alchemy-distill-refreshed")
        self.assertIn("execution_receipts", {item["source_stream"] for item in _read_jsonl(self.root / AUDIT_STREAM_PATH)})
        self.assertIn("runtime_history", {item["source_stream"] for item in _read_jsonl(self.root / AUDIT_STREAM_PATH)})

    def test_distill_mid_loop_failure_restores_all_touched_files(self) -> None:
        path_a = self._write_candidate_elixir("elixir-a")
        path_b = self._write_candidate_elixir("elixir-b")
        before_a = path_a.read_bytes()
        before_b = path_b.read_bytes()
        calls = 0

        def flaky(root: Path, elixir_id: str, question: str) -> dict[str, object]:
            nonlocal calls
            calls += 1
            result = self._fake_distill(root, elixir_id, question)
            if calls == 2:
                raise OSError("second distill failed")
            return result

        with (
            patch.object(runner_alchemy, "run_alchemy_distill_preview", return_value=self._distill_preview(["elixir-a", "elixir-b"])),
            patch.object(runner_alchemy, "run_alchemy_distill", side_effect=flaky),
            self.assertRaises(runner_alchemy.AlchemyDistillApplyError) as ctx,
        ):
            runner_alchemy.run_alchemy_distill_apply(self.root, scope="all")

        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertEqual(path_a.read_bytes(), before_a)
        self.assertEqual(path_b.read_bytes(), before_b)
        self.assertEqual(self._receipt_files(), set())
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root)), [])
        self.assertEqual(_read_jsonl(self.root / AUDIT_STREAM_PATH), [])
        self.assertEqual(_read_jsonl(self.root / ".aiwiki/state/runtime-history.jsonl"), [])

    def test_distill_first_candidate_failure_unlinks_path_that_did_not_exist_before(self) -> None:
        path = self._distill_candidate_path("elixir-new")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("transient precheck stub\n", encoding="utf-8")

        def creates_then_fails(_root: Path, elixir_id: str, _question: str) -> dict[str, object]:
            path.write_text("partial\n", encoding="utf-8")
            raise OSError(f"created then failed {elixir_id}")

        with (
            patch.object(runner_alchemy, "run_alchemy_distill_preview", return_value=self._distill_preview(["elixir-new"])),
            patch.object(runner_alchemy, "run_alchemy_distill", side_effect=creates_then_fails),
            patch.object(runner_alchemy, "_snapshot_file_bytes", return_value=None),
            self.assertRaises(runner_alchemy.AlchemyDistillApplyError),
        ):
            runner_alchemy.run_alchemy_distill_apply(self.root, scope="all")

        self.assertFalse(path.exists())
        self.assertEqual(self._receipt_files(), set())

    def test_distill_receipt_write_failure_restores_loop_mutations(self) -> None:
        path_a = self._write_candidate_elixir("elixir-a")
        path_b = self._write_candidate_elixir("elixir-b")
        before_a = path_a.read_bytes()
        before_b = path_b.read_bytes()
        original_atomic = runner_alchemy.atomic_write_text

        def flaky(path: Path, content: str, original_atomic=original_atomic, **kwargs: object) -> None:
            if "execution-receipts" in path.parts and path.suffix == ".json":
                raise OSError("receipt write failed")
            original_atomic(path, content, **kwargs)

        with (
            patch.object(runner_alchemy, "run_alchemy_distill_preview", return_value=self._distill_preview(["elixir-a", "elixir-b"])),
            patch.object(runner_alchemy, "run_alchemy_distill", side_effect=self._fake_distill),
            patch.object(runner_alchemy, "atomic_write_text", side_effect=flaky),
            self.assertRaises(runner_alchemy.AlchemyDistillApplyError),
        ):
            runner_alchemy.run_alchemy_distill_apply(self.root, scope="all")

        self.assertEqual(path_a.read_bytes(), before_a)
        self.assertEqual(path_b.read_bytes(), before_b)
        self.assertEqual(self._receipt_files(), set())
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root)), [])
        self.assertEqual(_read_jsonl(self.root / AUDIT_STREAM_PATH), [])

    def test_distill_pre_seeded_jsonl_preserved_on_mid_loop_failure(self) -> None:
        path_a = self._write_candidate_elixir("elixir-a")
        path_b = self._write_candidate_elixir("elixir-b")
        before_a = path_a.read_bytes()
        before_b = path_b.read_bytes()
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

        def flaky(root: Path, elixir_id: str, question: str) -> dict[str, object]:
            result = self._fake_distill(root, elixir_id, question)
            if elixir_id == "elixir-b":
                raise OSError("mid loop failed")
            return result

        with (
            patch.object(runner_alchemy, "run_alchemy_distill_preview", return_value=self._distill_preview(["elixir-a", "elixir-b"])),
            patch.object(runner_alchemy, "run_alchemy_distill", side_effect=flaky),
            self.assertRaises(runner_alchemy.AlchemyDistillApplyError),
        ):
            runner_alchemy.run_alchemy_distill_apply(self.root, scope="all")

        self.assertEqual(path_a.read_bytes(), before_a)
        self.assertEqual(path_b.read_bytes(), before_b)
        self.assertEqual(history_path.stat().st_size, history_size_seeded)
        self.assertEqual(history_path.read_text(encoding="utf-8"), seeded_history)
        self.assertEqual(audit_path.stat().st_size, audit_size_seeded)
        self.assertEqual(audit_path.read_text(encoding="utf-8"), seeded_audit)

    def test_distill_rollback_failure_raises_half_write_loud(self) -> None:
        self._write_candidate_elixir("elixir-a")

        def fails_after_write(root: Path, elixir_id: str, question: str) -> dict[str, object]:
            self._fake_distill(root, elixir_id, question)
            raise OSError("distill failed")

        with (
            patch.object(runner_alchemy, "run_alchemy_distill_preview", return_value=self._distill_preview(["elixir-a"])),
            patch.object(runner_alchemy, "run_alchemy_distill", side_effect=fails_after_write),
            patch.object(runner_alchemy, "_restore_file_bytes", side_effect=OSError("restore failed")),
            self.assertRaises(runner_alchemy.AlchemyDistillApplyHalfWriteError) as ctx,
        ):
            runner_alchemy.run_alchemy_distill_apply(self.root, scope="all")

        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertIn("restore failed", str(ctx.exception.__cause__))
        self.assertIn("tx_error=distill failed", str(ctx.exception))
        self.assertIn("rollback_error=restore failed", str(ctx.exception))

    def test_propose_happy_path_multi_proposal_writes_receipt_history_audit_runtime(self) -> None:
        result = self._run_propose(["proposal-a", "proposal-b"])

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["generated_count"], 2)
        self.assertTrue(self._proposal_page("proposal-a").exists())
        self.assertTrue(self._proposal_page("proposal-b").exists())
        state = json.loads((self.root / ".aiwiki/state/l3-proposals.json").read_text(encoding="utf-8"))
        self.assertEqual({item["proposal_id"] for item in state["proposals"]}, {"alchemy-proposal-a", "alchemy-proposal-b"})
        receipt = json.loads((self.root / str(result["receipt_path"])).read_text(encoding="utf-8"))
        self.assertEqual(receipt["operation"], "alchemy-propose-generate")
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root))[-1]["action_id"], receipt["action_id"])
        self.assertEqual(_read_jsonl(self.root / ".aiwiki/state/runtime-history.jsonl")[-1]["event_type"], "alchemy-propose-generated")
        self.assertIn("execution_receipts", {item["source_stream"] for item in _read_jsonl(self.root / AUDIT_STREAM_PATH)})
        self.assertIn("runtime_history", {item["source_stream"] for item in _read_jsonl(self.root / AUDIT_STREAM_PATH)})

    def test_propose_receipt_write_failure_does_not_rollback_proposals(self) -> None:
        self._write_planner_log()
        self._write_propose_target()
        original_atomic = runner_alchemy.atomic_write_text

        def flaky(path: Path, content: str, original_atomic=original_atomic, **kwargs: object) -> None:
            if "execution-receipts" in path.parts and path.suffix == ".json":
                raise OSError("receipt write failed")
            original_atomic(path, content, **kwargs)

        with (
            patch.object(runner_alchemy, "run_alchemy_propose_preview", return_value=self._propose_preview(["proposal-a", "proposal-b"])),
            patch.object(runner_alchemy, "atomic_write_text", side_effect=flaky),
            self.assertRaises(runner_alchemy.AlchemyProposeApplyReceiptError),
        ):
            runner_alchemy.run_alchemy_propose_apply(self.root, scope="all")

        self.assertTrue(self._proposal_page("proposal-a").exists())
        self.assertTrue(self._proposal_page("proposal-b").exists())
        state = json.loads((self.root / ".aiwiki/state/l3-proposals.json").read_text(encoding="utf-8"))
        self.assertEqual(len(state["proposals"]), 2)
        runtime_events = [item["event_type"] for item in _read_jsonl(self.root / ".aiwiki/state/runtime-history.jsonl")]
        self.assertEqual(runtime_events, ["l3-proposal-create", "l3-proposal-create"])
        self.assertIn("l3-proposal-create", (self.root / "wiki" / "indexes" / "log.md").read_text(encoding="utf-8"))
        self.assertEqual(self._receipt_files(), set())
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root)), [])

    def test_propose_pre_seeded_jsonl_and_proposal_runtime_preserved_on_receipt_failure(self) -> None:
        self._write_planner_log()
        self._write_propose_target()
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
        original_atomic = runner_alchemy.atomic_write_text

        def flaky(path: Path, content: str, original_atomic=original_atomic, **kwargs: object) -> None:
            if "execution-receipts" in path.parts and path.suffix == ".json":
                raise OSError("receipt write failed")
            original_atomic(path, content, **kwargs)

        with (
            patch.object(runner_alchemy, "run_alchemy_propose_preview", return_value=self._propose_preview(["proposal-a"])),
            patch.object(runner_alchemy, "atomic_write_text", side_effect=flaky),
            self.assertRaises(runner_alchemy.AlchemyProposeApplyReceiptError),
        ):
            runner_alchemy.run_alchemy_propose_apply(self.root, scope="all")

        self.assertEqual(history_path.stat().st_size, history_size_seeded)
        self.assertEqual(history_path.read_text(encoding="utf-8"), seeded_history)
        self.assertGreater(audit_path.stat().st_size, audit_size_seeded)
        self.assertTrue(audit_path.read_text(encoding="utf-8").startswith(seeded_audit))
        self.assertIn("runtime_history", {item.get("source_stream") for item in _read_jsonl(audit_path)})
        self.assertEqual([item["event_type"] for item in _read_jsonl(self.root / ".aiwiki/state/runtime-history.jsonl")], ["l3-proposal-create"])
        self.assertTrue(self._proposal_page("proposal-a").exists())

    def test_propose_rollback_failure_raises_half_write_loud(self) -> None:
        self._write_planner_log()
        self._write_propose_target()
        history_path = execution_receipt_history_path(self.root)

        def partial_history(_root: Path, receipt: dict[str, object]) -> None:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            with history_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(receipt) + "\n")
            raise OSError("history failed")

        with (
            patch.object(runner_alchemy, "run_alchemy_propose_preview", return_value=self._propose_preview(["proposal-a"])),
            patch.object(runner_alchemy, "append_execution_receipt_history", side_effect=partial_history),
            patch.object(runner_alchemy, "_durable_truncate", side_effect=OSError("truncate failed")),
            self.assertRaises(runner_alchemy.AlchemyProposeApplyReceiptHalfWriteError) as ctx,
        ):
            runner_alchemy.run_alchemy_propose_apply(self.root, scope="all")

        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertIn("truncate failed", str(ctx.exception.__cause__))
        self.assertIn("tx_error=history failed", str(ctx.exception))
        self.assertIn("rollback_error=truncate failed", str(ctx.exception))
        self.assertTrue(self._proposal_page("proposal-a").exists())
