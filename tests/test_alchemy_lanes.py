from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_utils import runtime_write_lock
from aiwiki.cli import build_parser, main
from aiwiki.planner.dry_run import (
    preview_alchemy_lane,
    preview_distill_primitive,
    preview_judge_primitive,
    preview_propose_primitive,
    preview_review_primitive,
)
from aiwiki.runner import run_alchemy_auto, run_alchemy_lane_apply


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
        judgment_refs: list[str] | None = None,
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
                "judgment_refs": judgment_refs or [],
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

    def _planner(self, signal_id: str, *, decision: str, mode: str = "observe_only") -> dict[str, object]:
        return {
            "schema_version": 1,
            "signal_id": signal_id,
            "dedupe_key": f"{signal_id}:{mode}",
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "decision": decision,
            "mode": mode,
            "reason_codes": ["runtime_failure_routine"] if mode == "observe_only" else ["runtime_failure_routine", "execute_mode_requested"],
            "budget_used": {},
            "locks_acquired": [],
            "primitive_refs": [],
            "side_effects_allowed": mode == "execute" and decision in {"enqueue-heavy", "enqueue-light"},
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
        apply_support = {step["primitive"]: step["apply_supported"] for step in result["primitive_plan"]}
        self.assertEqual(
            apply_support,
            {
                "route": False,
                "compile": True,
                "judge": False,
                "distill": False,
                "lint": True,
                "review": False,
            },
        )
        self.assertEqual(result["primitive_plan"][2]["apply_blocker"], "missing_receipted_scoped_contract")

    def test_heavy_lane_does_not_consume_generate_proposal_decisions(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal(
                    "sig-20260425-proposal01",
                    severity="high",
                    protocol="research",
                    source_ids=["src-proposal"],
                    concept_slugs=["proposal-scope"],
                )
            ],
        )
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [self._planner("sig-20260425-proposal01", decision="generate-proposal")],
        )

        result = preview_alchemy_lane(self.root, lane="heavy", scope="all")

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["side_effects_allowed"])
        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(result["scope_preview"]["signal_ids"], [])
        self.assertTrue(all(step["signal_ids"] == [] for step in result["primitive_plan"]))

    def test_light_lane_does_not_consume_heavy_or_generate_proposal(self) -> None:
        self._seed_lane_records()

        result = preview_alchemy_lane(self.root, lane="light", scope="all")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["scope_preview"]["protocols"], ["ops"])
        self.assertEqual([step["primitive"] for step in result["primitive_plan"]], ["route", "compile", "lint", "nightly"])
        self.assertEqual(result["scope_preview"]["signal_ids"], ["sig-20260425-light01"])
        apply_support = {step["primitive"]: step["apply_supported"] for step in result["primitive_plan"]}
        self.assertEqual(apply_support, {"route": False, "compile": True, "lint": True, "nightly": True})

    def test_lane_dry_run_can_filter_execute_mode_decisions(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal("sig-20260425-light01", severity="medium", protocol="ops"),
                self._signal("sig-20260425-light02", severity="medium", protocol="ops"),
            ],
        )
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [
                self._planner("sig-20260425-light01", decision="enqueue-light"),
                self._planner("sig-20260425-light02", decision="enqueue-light", mode="execute"),
            ],
        )

        result = preview_alchemy_lane(self.root, lane="light", scope="all", decision_mode="execute")

        self.assertEqual(result["decision_mode"], "execute")
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["scope_preview"]["signal_ids"], ["sig-20260425-light02"])

    def test_auto_scheduler_preview_consumes_only_execute_mode(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal("sig-20260425-heavy01", severity="high", protocol="research"),
                self._signal("sig-20260425-light01", severity="medium", protocol="ops"),
            ],
        )
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [
                self._planner("sig-20260425-heavy01", decision="enqueue-heavy"),
                self._planner("sig-20260425-light01", decision="enqueue-light", mode="execute"),
            ],
        )

        result = run_alchemy_auto(self.root, apply=False)

        self.assertEqual(result["status"], "preview")
        self.assertFalse(result["side_effects_allowed"])
        self.assertEqual(result["decision_mode"], "execute")
        lanes = {item["lane"]: item for item in result["lane_results"]}
        self.assertEqual(lanes["heavy"]["status"], "skipped")
        self.assertEqual(lanes["heavy"]["reason"], "empty_execute_plan")
        self.assertEqual(lanes["light"]["status"], "ready")
        self.assertEqual(lanes["light"]["selected_primitives"], ["compile", "lint", "nightly"])

    def test_auto_scheduler_apply_invokes_supported_primitives_and_writes_runtime_history(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [self._signal("sig-20260425-light01", severity="medium", protocol="ops")],
        )
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [self._planner("sig-20260425-light01", decision="enqueue-light", mode="execute")],
        )
        applied = {
            "status": "applied",
            "lane": "light",
            "scope": "all",
            "primitives": ["compile"],
            "plan": {"scope_preview": {"trace_ids": ["550e8400-e29b-41d4-a716-446655440000"]}},
        }

        with patch("aiwiki.runner.run_alchemy_lane_apply", return_value=applied) as mocked:
            result = run_alchemy_auto(self.root, apply=True, lanes=["light"], primitives=["compile"], note="auto")

        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs["decision_mode"], "execute")
        self.assertEqual(kwargs["primitives"], ["compile"])
        self.assertEqual(result["status"], "applied")
        history = [
            json.loads(line)
            for line in (self.root / ".aiwiki" / "state" / "runtime-history.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(history[-1]["event_type"], "alchemy-auto-scheduler")
        self.assertEqual(history[-1]["applied_count"], 1)

    def test_dry_run_reports_deferred_high_risk_primitives(self) -> None:
        self._seed_lane_records()

        heavy = preview_alchemy_lane(self.root, lane="heavy", scope="all")
        light = preview_alchemy_lane(self.root, lane="light", scope="all")

        self.assertEqual(
            [item["primitive"] for item in heavy["deferred_primitives"]],
            ["judge", "distill", "review", "propose"],
        )
        self.assertEqual({item["reason_code"] for item in heavy["deferred_primitives"]}, {"missing_receipted_scoped_contract"})
        for item in heavy["deferred_primitives"]:
            contract = item["apply_contract"]
            self.assertEqual(contract["status"], "deferred")
            self.assertEqual(contract["primitive"], item["primitive"])
            self.assertTrue(contract["write_surfaces"])
            self.assertIn("execution-receipt v1", contract["receipt_schema"])
            self.assertIn("execution_receipt_history_append", contract["audit_event_schema"])
            self.assertIn("required_before_apply", contract["revert_policy"])
            self.assertIn("trace_ids", contract["idempotency_key"])
            self.assertTrue(contract["backend_policy"])
        self.assertEqual(
            [item["primitive"] for item in light["deferred_primitives"]],
            ["judge", "distill", "review", "propose"],
        )
        self.assertEqual({item["reason_code"] for item in light["deferred_primitives"]}, {"not_allowed_for_light_lane"})
        self.assertEqual({item["apply_contract"]["status"] for item in light["deferred_primitives"]}, {"deferred"})

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

    def test_apply_aborts_non_ok_preview_before_any_write_surface(self) -> None:
        self._seed_lane_records()

        with (
            patch("aiwiki.app_compile.apply_machine_memory_actions_batch") as mocked_action_batch,
            patch("aiwiki.runner.compile_wiki") as mocked_compile,
        ):
            with self.assertRaisesRegex(RuntimeError, "requires an ok dry-run plan"):
                run_alchemy_lane_apply(
                    self.root,
                    lane="heavy",
                    scope="all",
                    action_ids=["act-1"],
                    primitives=["compile"],
                    max_pages=10,
                )

        mocked_action_batch.assert_not_called()
        mocked_compile.assert_not_called()

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

    def test_apply_writes_lane_runtime_history_audit_events(self) -> None:
        self._seed_lane_records()

        with patch("aiwiki.app_compile.apply_machine_memory_actions_batch", return_value={"receipt_path": "receipt.json"}):
            result = run_alchemy_lane_apply(
                self.root,
                lane="heavy",
                scope="all",
                action_ids=["act-1"],
                primitives=[],
                note="ship",
            )

        self.assertEqual(result["status"], "applied")
        history = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/runtime-history.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual([item["event_type"] for item in history], ["alchemy-lane-started", "alchemy-lane-completed"])
        self.assertEqual([item["status"] for item in history], ["started", "completed"])
        for event in history:
            self.assertEqual(event["lane"], "heavy")
            self.assertEqual(event["scope"], "all")
            self.assertEqual(event["action_ids"], ["act-1"])
            self.assertEqual(event["primitives"], [])
            self.assertEqual(event["selected_count"], 1)
            self.assertEqual(event["trace_id"], "550e8400-e29b-41d4-a716-446655440000")
            self.assertEqual(event["trace_ids"], ["550e8400-e29b-41d4-a716-446655440000"])
            self.assertEqual(event["subject_kind"], "alchemy_lane")
            self.assertEqual(event["subject_id"], "heavy:all")
        self.assertEqual(history[-1]["action_batch_receipt"], "receipt.json")
        audit_records = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        runtime_audit = [item for item in audit_records if item["source_stream"] == "runtime_history"]
        self.assertEqual([item["event_type"] for item in runtime_audit], ["alchemy-lane-started", "alchemy-lane-completed"])
        self.assertEqual([item["source_ref"] for item in runtime_audit], [
            ".aiwiki/state/runtime-history.jsonl#L1",
            ".aiwiki/state/runtime-history.jsonl#L2",
        ])
        self.assertEqual(runtime_audit[0]["subject"], {"kind": "alchemy_lane", "id": "heavy:all"})

    def test_apply_preflight_failures_do_not_write_lane_runtime_history(self) -> None:
        self._seed_lane_records()

        with self.assertRaisesRegex(ValueError, "requires at least one --action-id or --primitive"):
            run_alchemy_lane_apply(self.root, lane="heavy", scope="all", action_ids=[])
        with self.assertRaisesRegex(RuntimeError, "requires an ok dry-run plan"):
            run_alchemy_lane_apply(self.root, lane="heavy", scope="all", action_ids=["act-1"], max_pages=10)

        self.assertFalse((self.root / ".aiwiki/state/runtime-history.jsonl").exists())
        self.assertFalse((self.root / ".aiwiki/state/audit.jsonl").exists())

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
        self.assertEqual(primitive_result["trace_id"], "550e8400-e29b-41d4-a716-446655440000")
        self.assertEqual(primitive_result["audit_path"], ".aiwiki/state/execution-receipts.jsonl")
        receipt_path = self.root / primitive_result["receipt_path"]
        self.assertTrue(receipt_path.exists())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["kind"], "execution-receipt")
        self.assertEqual(receipt["generated_by"], "aiwiki-alchemy-lane")
        self.assertEqual(receipt["operation"], "alchemy-lane-primitive")
        self.assertEqual(receipt["trace_id"], "550e8400-e29b-41d4-a716-446655440000")
        self.assertEqual(receipt["trace_ids"], ["550e8400-e29b-41d4-a716-446655440000"])
        self.assertEqual(receipt["audit_stream"], "execution_receipts")
        self.assertEqual(receipt["audit_event"], "execution_receipt_history_append")
        self.assertEqual(receipt["audit_path"], ".aiwiki/state/execution-receipts.jsonl")
        self.assertEqual(receipt["primitive"], "compile")
        self.assertEqual(receipt["lane"], "heavy")
        self.assertFalse(receipt["revert_supported"])
        history = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/execution-receipts.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(history[-1]["action_id"], receipt["action_id"])
        self.assertEqual(history[-1]["trace_id"], receipt["trace_id"])

    def test_apply_rejects_primitive_absent_from_lane_plan(self) -> None:
        self._seed_lane_records()

        with self.assertRaisesRegex(RuntimeError, "not present in the dry-run plan"):
            run_alchemy_lane_apply(self.root, lane="heavy", scope="all", action_ids=[], primitives=["nightly"])

    def test_apply_rejects_primitive_when_plan_step_is_not_apply_supported(self) -> None:
        self._seed_lane_records()
        plan = preview_alchemy_lane(self.root, lane="heavy", scope="all")
        for step in plan["primitive_plan"]:
            if step["primitive"] == "compile":
                step["apply_supported"] = False
                step["apply_blocker"] = "blocked-by-test"

        with (
            patch("aiwiki.planner.preview_alchemy_lane", return_value=plan),
            patch("aiwiki.runner.compile_wiki") as mocked_compile,
        ):
            with self.assertRaisesRegex(RuntimeError, "not apply-supported.*blocked-by-test"):
                run_alchemy_lane_apply(self.root, lane="heavy", scope="all", action_ids=[], primitives=["compile"])

        mocked_compile.assert_not_called()

    def test_apply_rejects_deferred_primitives(self) -> None:
        self._seed_lane_records()

        with self.assertRaisesRegex(ValueError, "unsupported alchemy lane primitive"):
            run_alchemy_lane_apply(self.root, lane="heavy", scope="all", action_ids=[], primitives=["judge"])
        with self.assertRaisesRegex(ValueError, "unsupported alchemy lane primitive"):
            run_alchemy_lane_apply(self.root, lane="heavy", scope="all", action_ids=[], primitives=["distill"])
        with self.assertRaisesRegex(ValueError, "unsupported alchemy lane primitive"):
            run_alchemy_lane_apply(self.root, lane="heavy", scope="all", action_ids=[], primitives=["review"])
        with self.assertRaisesRegex(ValueError, "unsupported alchemy lane primitive"):
            run_alchemy_lane_apply(self.root, lane="heavy", scope="all", action_ids=[], primitives=["propose"])

    def test_judge_preview_reports_scoped_candidates_without_writes(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal(
                    "sig-20260425-heavy01",
                    severity="high",
                    protocol="research",
                    source_ids=["src-b", "src-a"],
                    concept_slugs=["zeta", "alpha"],
                    judgment_refs=["wiki/judgments/thesis.md"],
                    max_pages=12,
                    max_tokens=3000,
                )
            ],
        )
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [self._planner("sig-20260425-heavy01", decision="enqueue-heavy")],
        )
        before = _snapshot_files(self.root)

        result = preview_judge_primitive(self.root, scope="all")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["primitive"], "judge")
        self.assertEqual(result["lane"], "heavy")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["side_effects_allowed"])
        self.assertFalse(result["apply_supported"])
        self.assertEqual(result["apply_blocker"], "missing_receipted_scoped_contract")
        self.assertTrue(result["llm_required_for_apply"])
        self.assertTrue(result["receipt_required_for_apply"])
        self.assertTrue(result["audit_required_for_apply"])
        self.assertEqual(result["apply_contract"]["primitive"], "judge")
        self.assertIn("wiki/judgments/", result["apply_contract"]["write_surfaces"])
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["candidate_count"], 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["candidate_id"], "judge-refresh-wiki-judgments-thesis-md")
        self.assertEqual(candidate["kind"], "judgment_refresh")
        self.assertEqual(candidate["target_ref"], "wiki/judgments/thesis.md")
        self.assertEqual(candidate["signal_ids"], ["sig-20260425-heavy01"])
        self.assertEqual(candidate["source_ids"], ["src-a", "src-b"])
        self.assertEqual(candidate["concept_slugs"], ["alpha", "zeta"])
        self.assertFalse(candidate["apply_supported"])
        self.assertEqual(candidate["apply_contract"]["status"], "deferred")
        self.assertEqual(_snapshot_files(self.root), before)

    def test_judge_preview_uses_scope_candidates_when_no_judgment_ref_exists(self) -> None:
        self._seed_lane_records()

        result = preview_judge_primitive(self.root, scope="all", limit=1)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["returned_count"], 1)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["candidates"][0]["kind"], "judgment_scope_refresh")
        self.assertEqual(result["candidates"][0]["protocol"], "research")

    def test_distill_preview_reports_scoped_candidates_without_writes(self) -> None:
        self._seed_lane_records()
        before = _snapshot_files(self.root)

        result = preview_distill_primitive(self.root, scope="all")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["primitive"], "distill")
        self.assertEqual(result["lane"], "heavy")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["side_effects_allowed"])
        self.assertFalse(result["apply_supported"])
        self.assertEqual(result["apply_blocker"], "missing_receipted_scoped_contract")
        self.assertTrue(result["llm_required_for_apply"])
        self.assertTrue(result["receipt_required_for_apply"])
        self.assertTrue(result["audit_required_for_apply"])
        self.assertTrue(result["candidate_plane_required_for_apply"])
        self.assertEqual(result["apply_contract"]["primitive"], "distill")
        self.assertIn("output/_candidates/elixirs/", result["apply_contract"]["write_surfaces"])
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["candidate_count"], 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["candidate_id"], "distill-refresh-elixir-z")
        self.assertEqual(candidate["kind"], "elixir_candidate_refresh")
        self.assertEqual(candidate["target_ref"], "elixir-z")
        self.assertEqual(candidate["signal_ids"], ["sig-20260425-heavy01"])
        self.assertEqual(candidate["source_ids"], ["src-a", "src-b"])
        self.assertEqual(candidate["concept_slugs"], ["alpha", "zeta"])
        self.assertEqual(candidate["elixir_refs"], ["elixir-z"])
        self.assertFalse(candidate["apply_supported"])
        self.assertEqual(candidate["apply_contract"]["status"], "deferred")
        self.assertEqual(_snapshot_files(self.root), before)

    def test_distill_preview_uses_scope_candidates_when_no_elixir_ref_exists(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal(
                    "sig-20260425-heavy01",
                    severity="high",
                    protocol="research",
                    source_ids=["src-a"],
                    concept_slugs=["alpha"],
                    elixir_refs=[],
                )
            ],
        )
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [self._planner("sig-20260425-heavy01", decision="enqueue-heavy")],
        )

        result = preview_distill_primitive(self.root, scope="all", limit=1)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["returned_count"], 1)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["candidates"][0]["kind"], "elixir_scope_refresh")
        self.assertEqual(result["candidates"][0]["protocol"], "research")

    def test_review_preview_reports_scoped_candidates_without_writes(self) -> None:
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
                    judgment_refs=["wiki/judgments/thesis.md"],
                    max_pages=12,
                    max_tokens=3000,
                )
            ],
        )
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [self._planner("sig-20260425-heavy01", decision="enqueue-heavy")],
        )
        before = _snapshot_files(self.root)

        result = preview_review_primitive(self.root, scope="all")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["primitive"], "review")
        self.assertEqual(result["lane"], "heavy")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["side_effects_allowed"])
        self.assertFalse(result["apply_supported"])
        self.assertEqual(result["apply_blocker"], "missing_receipted_scoped_contract")
        self.assertFalse(result["llm_required_for_apply"])
        self.assertTrue(result["receipt_required_for_apply"])
        self.assertTrue(result["audit_required_for_apply"])
        self.assertTrue(result["review_queue_write_required_for_apply"])
        self.assertEqual(result["apply_contract"]["primitive"], "review")
        self.assertIn("wiki/indexes/review-queue.md", result["apply_contract"]["write_surfaces"])
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["candidate_count"], 2)
        kinds = [candidate["kind"] for candidate in result["candidates"]]
        self.assertEqual(kinds, ["judgment_review_enqueue", "elixir_review_enqueue"])
        self.assertEqual(result["candidates"][0]["candidate_id"], "review-judgment-wiki-judgments-thesis-md")
        self.assertEqual(result["candidates"][0]["target_ref"], "wiki/judgments/thesis.md")
        self.assertEqual(result["candidates"][1]["candidate_id"], "review-elixir-elixir-z")
        self.assertEqual(result["candidates"][1]["target_ref"], "elixir-z")
        self.assertEqual(result["candidates"][0]["apply_contract"]["status"], "deferred")
        self.assertEqual(_snapshot_files(self.root), before)

    def test_review_preview_uses_scope_candidates_when_no_target_refs_exist(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal(
                    "sig-20260425-heavy01",
                    severity="high",
                    protocol="research",
                    source_ids=["src-a"],
                    concept_slugs=["alpha"],
                    elixir_refs=[],
                )
            ],
        )
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [self._planner("sig-20260425-heavy01", decision="enqueue-heavy")],
        )

        result = preview_review_primitive(self.root, scope="all", limit=1)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["returned_count"], 1)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["candidates"][0]["kind"], "scope_review_enqueue")
        self.assertEqual(result["candidates"][0]["protocol"], "research")

    def test_propose_preview_reports_scoped_candidates_without_writes(self) -> None:
        self._seed_lane_records()
        before = _snapshot_files(self.root)

        result = preview_propose_primitive(self.root, scope="all")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["primitive"], "propose")
        self.assertEqual(result["lane"], "heavy")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["side_effects_allowed"])
        self.assertFalse(result["apply_supported"])
        self.assertEqual(result["apply_blocker"], "missing_receipted_scoped_contract")
        self.assertTrue(result["llm_required_for_apply"])
        self.assertTrue(result["receipt_required_for_apply"])
        self.assertTrue(result["audit_required_for_apply"])
        self.assertTrue(result["proposal_plane_write_required_for_apply"])
        self.assertTrue(result["human_accept_required_after_apply"])
        self.assertEqual(result["apply_contract"]["primitive"], "propose")
        self.assertIn("output/_proposals/prompt/", result["apply_contract"]["write_surfaces"])
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["candidate_count"], 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["candidate_id"], "propose-scope-research-1")
        self.assertEqual(candidate["kind"], "proposal_opportunity")
        self.assertEqual(candidate["proposal_kinds"], ["prompt_proposal", "policy_proposal"])
        self.assertEqual(candidate["source_decision"], "enqueue-heavy")
        self.assertFalse(candidate["consumes_generate_proposal_decisions"])
        self.assertEqual(candidate["signal_ids"], ["sig-20260425-heavy01"])
        self.assertEqual(candidate["apply_contract"]["status"], "deferred")
        self.assertEqual(_snapshot_files(self.root), before)


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

    def test_parser_registers_nested_alchemy_commands(self) -> None:
        parser = build_parser()
        action = next(item for item in parser._actions if getattr(item, "dest", "") == "command")
        alchemy_parser = action.choices["alchemy"]
        lane_action = next(item for item in alchemy_parser._actions if getattr(item, "dest", "") == "alchemy_lane")
        self.assertEqual(set(lane_action.choices), {"heavy", "light", "judge", "distill", "review", "propose", "legacy-migration", "auto", "superseded-cleanup"})

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

    def test_main_dispatches_alchemy_judge_preview(self) -> None:
        with patch("aiwiki.cli.run_alchemy_judge_preview", return_value={"status": "ok", "primitive": "judge"}) as mocked:
            code, payload, stderr = self._run_main(
                [
                    "alchemy",
                    "judge",
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
                    "--limit",
                    "11",
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["primitive"], "judge")
        mocked.assert_called_once_with(
            self.root,
            scope="all",
            planner_log_path=Path("custom/planner-log.jsonl"),
            signals_path=Path("custom/signals.jsonl"),
            max_signals=3,
            max_pages=5,
            max_tokens=7,
            limit=11,
        )

    def test_main_dispatches_alchemy_distill_preview(self) -> None:
        with patch("aiwiki.cli.run_alchemy_distill_preview", return_value={"status": "ok", "primitive": "distill"}) as mocked:
            code, payload, stderr = self._run_main(
                [
                    "alchemy",
                    "distill",
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
                    "--limit",
                    "11",
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["primitive"], "distill")
        mocked.assert_called_once_with(
            self.root,
            scope="all",
            planner_log_path=Path("custom/planner-log.jsonl"),
            signals_path=Path("custom/signals.jsonl"),
            max_signals=3,
            max_pages=5,
            max_tokens=7,
            limit=11,
        )

    def test_main_dispatches_alchemy_review_preview(self) -> None:
        with patch("aiwiki.cli.run_alchemy_review_preview", return_value={"status": "ok", "primitive": "review"}) as mocked:
            code, payload, stderr = self._run_main(
                [
                    "alchemy",
                    "review",
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
                    "--limit",
                    "11",
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["primitive"], "review")
        mocked.assert_called_once_with(
            self.root,
            scope="all",
            planner_log_path=Path("custom/planner-log.jsonl"),
            signals_path=Path("custom/signals.jsonl"),
            max_signals=3,
            max_pages=5,
            max_tokens=7,
            limit=11,
        )

    def test_main_dispatches_alchemy_propose_preview(self) -> None:
        with patch("aiwiki.cli.run_alchemy_propose_preview", return_value={"status": "ok", "primitive": "propose"}) as mocked:
            code, payload, stderr = self._run_main(
                [
                    "alchemy",
                    "propose",
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
                    "--limit",
                    "11",
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["primitive"], "propose")
        mocked.assert_called_once_with(
            self.root,
            scope="all",
            planner_log_path=Path("custom/planner-log.jsonl"),
            signals_path=Path("custom/signals.jsonl"),
            max_signals=3,
            max_pages=5,
            max_tokens=7,
            limit=11,
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

    def test_alchemy_lane_rejects_deferred_primitive_at_parser(self) -> None:
        code, payload, stderr = self._run_main(["alchemy", "heavy", "all", "--apply", "--primitive", "judge"])

        self.assertEqual(code, 2)
        self.assertEqual(payload, {})
        self.assertIn("invalid choice", stderr)
