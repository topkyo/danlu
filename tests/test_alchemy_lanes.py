from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_utils import runtime_write_lock
from aiwiki.cli import build_parser, main
from aiwiki.planner.dry_run import preview_alchemy_lane
from aiwiki.runner import run_alchemy_lane_apply


def _snapshot_files(root: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[path.relative_to(root).as_posix()] = path.read_bytes()
    return snapshot


class AlchemyLaneDryRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_jsonl(self, rel: str, records: list[dict[str, object]]) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records),
            encoding="utf-8",
        )

    def _signal(
        self,
        signal_id: str,
        *,
        severity: str,
        protocol: str = "research",
        source_ids: list[str] | None = None,
        concept_slugs: list[str] | None = None,
        elixir_refs: list[str] | None = None,
        max_pages: int | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, object]:
        budget_hint: dict[str, object] = {}
        if max_pages is not None:
            budget_hint["max_pages"] = max_pages
        if max_tokens is not None:
            budget_hint["max_tokens"] = max_tokens
        record: dict[str, object] = {
            "schema_version": 1,
            "signal_id": signal_id,
            "dedupe_key": f"runtime_failure:{protocol}:runtime_history:{signal_id}",
            "kind": "runtime_failure",
            "scope": {
                "protocol": protocol,
                "source_ids": source_ids or [],
                "concept_slugs": concept_slugs or [],
                "elixir_refs": elixir_refs or [],
                "judgment_refs": [],
            },
            "severity": severity,
            "evidence_refs": [],
            "emitted_at": "2026-04-25T00:00:00Z",
            "emitted_by": "nightly",
            "source_kind": "runtime_history",
            "source_event_ref": ".aiwiki/state/runtime-history.jsonl#L1",
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
        }
        if budget_hint:
            record["budget_hint"] = budget_hint
        return record

    def _planner(self, signal_id: str, *, decision: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "signal_id": signal_id,
            "dedupe_key": f"{signal_id}:observe_only",
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "decision": decision,
            "mode": "observe_only",
            "reason_codes": ["runtime_failure_routine"],
            "budget_used": {},
            "locks_acquired": [],
            "primitive_refs": [],
            "side_effects_allowed": False,
            "decided_at": "2026-04-25T00:01:00Z",
        }

    def _seed_lane_records(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal(
                    "sig-20260425-heavy01",
                    severity="high",
                    protocol="research",
                    source_ids=["src-b", "src-a"],
                    concept_slugs=["zeta", "alpha"],
                    elixir_refs=["elixir-z"],
                    max_pages=12,
                    max_tokens=3000,
                ),
                self._signal(
                    "sig-20260425-light01",
                    severity="medium",
                    protocol="ops",
                    source_ids=["src-light"],
                    concept_slugs=["maintenance"],
                    max_pages=3,
                    max_tokens=500,
                ),
            ],
        )
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [
                self._planner("sig-20260425-heavy01", decision="enqueue-heavy"),
                self._planner("sig-20260425-light01", decision="enqueue-light"),
                self._planner("sig-20260425-heavy01", decision="generate-proposal"),
            ],
        )

    def test_heavy_lane_dry_run_filters_enqueue_heavy_and_stabilizes_scope(self) -> None:
        self._seed_lane_records()

        result = preview_alchemy_lane(self.root, lane="heavy", scope="all")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["lane"], "heavy")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["side_effects_allowed"])
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["scope_preview"]["source_ids"], ["src-a", "src-b"])
        self.assertEqual(result["scope_preview"]["concept_slugs"], ["alpha", "zeta"])
        self.assertEqual(result["scope_preview"]["elixir_refs"], ["elixir-z"])
        self.assertEqual([step["primitive"] for step in result["primitive_plan"]], ["route", "compile", "judge", "distill", "lint", "review"])

    def test_light_lane_does_not_consume_heavy_or_generate_proposal(self) -> None:
        self._seed_lane_records()

        result = preview_alchemy_lane(self.root, lane="light", scope="all")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["scope_preview"]["protocols"], ["ops"])
        self.assertEqual([step["primitive"] for step in result["primitive_plan"]], ["route", "compile", "lint", "nightly"])
        self.assertEqual(result["scope_preview"]["signal_ids"], ["sig-20260425-light01"])

    def test_scope_selector_filters_by_protocol(self) -> None:
        self._seed_lane_records()

        result = preview_alchemy_lane(self.root, lane="heavy", scope="protocol:ops")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["primitive_plan"][0]["signal_ids"], [])

    def test_budget_exceeded_is_explainable(self) -> None:
        self._seed_lane_records()

        result = preview_alchemy_lane(self.root, lane="heavy", scope="all", max_pages=10, max_tokens=1000)

        self.assertEqual(result["status"], "budget_exceeded")
        self.assertEqual(result["budget"]["used"]["max_pages"], 12)
        self.assertEqual(result["budget"]["used"]["max_tokens"], 3000)
        self.assertEqual(result["budget"]["reason_codes"], ["max_pages_exceeded", "max_tokens_exceeded"])

    def test_lock_conflict_skips_without_waiting(self) -> None:
        self._seed_lane_records()

        with runtime_write_lock(self.root):
            result = preview_alchemy_lane(self.root, lane="heavy", scope="all")

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "lock_conflict")
        self.assertEqual(result["lock"]["status"], "conflict")
        self.assertEqual(result["primitive_plan"], [])

    def test_missing_files_return_empty_plan(self) -> None:
        result = preview_alchemy_lane(self.root, lane="light", scope="all")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["scope_preview"]["signal_ids"], [])
        self.assertEqual(result["skip_examples"], [])

    def test_dry_run_does_not_write_files(self) -> None:
        self._seed_lane_records()
        before = _snapshot_files(self.root)

        preview_alchemy_lane(self.root, lane="heavy", scope="all")

        after = _snapshot_files(self.root)
        self.assertEqual(after, before)

    def test_apply_rejects_missing_action_ids_and_primitives(self) -> None:
        self._seed_lane_records()

        with self.assertRaisesRegex(ValueError, "requires at least one --action-id or --primitive"):
            run_alchemy_lane_apply(self.root, lane="heavy", scope="all", action_ids=[])

    def test_apply_rejects_empty_dry_run_plan(self) -> None:
        self._seed_lane_records()

        with self.assertRaisesRegex(RuntimeError, "non-empty dry-run plan"):
            run_alchemy_lane_apply(self.root, lane="heavy", scope="protocol:ops", action_ids=["act-1"])

    def test_apply_dispatches_to_receipted_action_batch_after_preview(self) -> None:
        self._seed_lane_records()

        with patch("aiwiki.app_compile.apply_machine_memory_actions_batch", return_value={"receipt_path": "receipt.json"}) as mocked:
            result = run_alchemy_lane_apply(
                self.root,
                lane="heavy",
                scope="all",
                action_ids=[" act-1 ", "", "act-2"],
                note="ship",
            )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["action_ids"], ["act-1", "act-2"])
        self.assertEqual(result["plan"]["selected_count"], 1)
        self.assertEqual(result["apply_result"], {"receipt_path": "receipt.json"})
        self.assertEqual(result["primitive_results"], [])
        mocked.assert_called_once_with(self.root, ["act-1", "act-2"], note="ship", dry_run=False)

    def test_apply_writes_receipt_for_deterministic_primitive(self) -> None:
        self._seed_lane_records()

        with patch("aiwiki.runner.compile_wiki", return_value={"updated_source_pages": ["wiki/sources/a.md"]}) as mocked:
            result = run_alchemy_lane_apply(
                self.root,
                lane="heavy",
                scope="all",
                action_ids=[],
                primitives=["compile"],
                note="compile lane",
            )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["primitives"], ["compile"])
        self.assertIsNone(result["apply_result"])
        mocked.assert_called_once_with(self.root)
        primitive_result = result["primitive_results"][0]
        receipt_path = self.root / primitive_result["receipt_path"]
        self.assertTrue(receipt_path.exists())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["kind"], "execution-receipt")
        self.assertEqual(receipt["generated_by"], "aiwiki-alchemy-lane")
        self.assertEqual(receipt["operation"], "alchemy-lane-primitive")
        self.assertEqual(receipt["primitive"], "compile")
        self.assertEqual(receipt["lane"], "heavy")
        self.assertFalse(receipt["revert_supported"])
        history = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/execution-receipts.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(history[-1]["action_id"], receipt["action_id"])

    def test_apply_rejects_primitive_absent_from_lane_plan(self) -> None:
        self._seed_lane_records()

        with self.assertRaisesRegex(RuntimeError, "not present in the dry-run plan"):
            run_alchemy_lane_apply(self.root, lane="heavy", scope="all", action_ids=[], primitives=["nightly"])


class AlchemyLaneCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _run_main(self, argv: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            try:
                code = main(["--root", str(self.root), *argv])
            except SystemExit as exc:
                code = int(exc.code or 0)
        payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
        return code, payload, stderr.getvalue()

    def test_parser_registers_nested_alchemy_heavy_light(self) -> None:
        parser = build_parser()
        action = next(item for item in parser._actions if getattr(item, "dest", "") == "command")
        alchemy_parser = action.choices["alchemy"]
        lane_action = next(item for item in alchemy_parser._actions if getattr(item, "dest", "") == "alchemy_lane")
        self.assertEqual(set(lane_action.choices), {"heavy", "light"})

    def test_main_dispatches_alchemy_lane_dry_run(self) -> None:
        with patch("aiwiki.cli.run_alchemy_lane_dry_run", return_value={"status": "ok", "lane": "heavy"}) as mocked:
            code, payload, stderr = self._run_main(
                [
                    "alchemy",
                    "heavy",
                    "all",
                    "--dry-run",
                    "--planner-log-path",
                    "custom/planner-log.jsonl",
                    "--signals-path",
                    "custom/signals.jsonl",
                    "--max-signals",
                    "3",
                    "--max-pages",
                    "5",
                    "--max-tokens",
                    "7",
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["lane"], "heavy")
        mocked.assert_called_once_with(
            self.root,
            lane="heavy",
            scope="all",
            planner_log_path=Path("custom/planner-log.jsonl"),
            signals_path=Path("custom/signals.jsonl"),
            max_signals=3,
            max_pages=5,
            max_tokens=7,
        )

    def test_alchemy_lane_rejects_missing_mode(self) -> None:
        code, payload, stderr = self._run_main(["alchemy", "light", "all"])

        self.assertEqual(code, 1)
        self.assertEqual(payload, {})
        self.assertIn("requires exactly one of --dry-run or --apply", stderr)

    def test_alchemy_lane_rejects_dry_run_apply_conflict(self) -> None:
        code, payload, stderr = self._run_main(["alchemy", "light", "all", "--dry-run", "--apply", "--action-id", "act-1"])

        self.assertEqual(code, 1)
        self.assertEqual(payload, {})
        self.assertIn("requires exactly one of --dry-run or --apply", stderr)
