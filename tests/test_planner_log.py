from __future__ import annotations

import ast
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import aiwiki.planner.log_writer as log_writer
from aiwiki.cli import build_parser, main
from aiwiki.planner.log_writer import write_planner_log
from aiwiki.planner.rollback import preview_planner_log_rollback
from aiwiki.planner.schema import (
    DECISIONS,
    MODES,
    TOP_LEVEL_FIELD_ORDER,
    canonical_dumps_planner_log,
    compute_planner_log_dedupe_key,
    validate_planner_log_record,
)
from aiwiki.signals.schema import KINDS

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "planner_log"


def _fixed_now() -> datetime:
    return datetime(2026, 4, 24, 12, 0, 0)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _snapshot_files(root: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == ".aiwiki/state/runtime.lock":
            continue
        snapshot[rel] = path.read_bytes()
    return snapshot


class _FixtureCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.temp_root = Path(self._tmpdir.name).resolve()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _copy_case_root(self, case_name: str) -> Path:
        dst = self.temp_root / case_name
        shutil.copytree(FIXTURE_DIR / case_name / "root", dst)
        return dst


class TestSchemaValidation(unittest.TestCase):
    def _base_record(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "signal_id": "sig-20260424-schema01",
            "dedupe_key": "review_feedback:research:runtime_history:sha256-1234",
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "decision": "enqueue-light",
            "mode": "observe_only",
            "reason_codes": ["review_feedback_routine"],
            "budget_used": {},
            "locks_acquired": [],
            "primitive_refs": [],
            "side_effects_allowed": False,
            "decided_at": "2026-04-24T12:00:00Z",
        }

    def test_valid_record_passes(self) -> None:
        result = validate_planner_log_record(self._base_record())
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, ())

    def test_non_object_rejected(self) -> None:
        result = validate_planner_log_record("x")  # type: ignore[arg-type]
        self.assertFalse(result.ok)

    def test_schema_version_must_be_int_and_v1(self) -> None:
        record = self._base_record()
        record["schema_version"] = "1"
        self.assertFalse(validate_planner_log_record(record).ok)
        record["schema_version"] = 2
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_signal_id_regex(self) -> None:
        record = self._base_record()
        record["signal_id"] = "bad"
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_dedupe_key_non_empty_string(self) -> None:
        record = self._base_record()
        record["dedupe_key"] = ""
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_trace_id_regex(self) -> None:
        record = self._base_record()
        record["trace_id"] = "NOT-A-UUID"
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_decision_enum(self) -> None:
        record = self._base_record()
        record["decision"] = "run-now"
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_mode_enum(self) -> None:
        record = self._base_record()
        record["mode"] = "dry_run"
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_reason_codes_non_empty_list(self) -> None:
        record = self._base_record()
        record["reason_codes"] = []
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_reason_codes_pattern(self) -> None:
        record = self._base_record()
        record["reason_codes"] = ["Bad-Reason"]
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_reason_codes_must_be_unique_but_may_preserve_semantic_order(self) -> None:
        record = self._base_record()
        record["reason_codes"] = ["b", "a", "a"]
        errors = validate_planner_log_record(record).errors
        self.assertTrue(any("duplicate" in item for item in errors))

        record["reason_codes"] = ["b", "a"]
        self.assertTrue(validate_planner_log_record(record).ok)

    def test_budget_used_must_be_empty_dict(self) -> None:
        record = self._base_record()
        record["budget_used"] = {"max_pages": 1}
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_locks_acquired_must_be_empty_list(self) -> None:
        record = self._base_record()
        record["locks_acquired"] = ["runtime"]
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_primitive_refs_must_be_empty_list(self) -> None:
        record = self._base_record()
        record["primitive_refs"] = ["compile"]
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_side_effects_allowed_must_be_strict_bool_false(self) -> None:
        record = self._base_record()
        record["side_effects_allowed"] = 0
        self.assertFalse(validate_planner_log_record(record).ok)
        record["side_effects_allowed"] = True
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_decided_at_format(self) -> None:
        record = self._base_record()
        record["decided_at"] = "2026-04-24T12:00:00+00:00"
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_unknown_field_rejected(self) -> None:
        record = self._base_record()
        record["extra"] = "x"
        self.assertFalse(validate_planner_log_record(record).ok)

    def test_null_rejected(self) -> None:
        record = self._base_record()
        record["decision"] = None
        self.assertFalse(validate_planner_log_record(record).ok)


class TestDecisionDerivation(unittest.TestCase):
    def test_review_feedback_medium(self) -> None:
        decision, reason_codes = log_writer._derive_decision("review_feedback", "medium")
        self.assertEqual(decision, "enqueue-light")
        self.assertEqual(set(reason_codes), {"review_feedback_routine"})

    def test_review_feedback_high(self) -> None:
        decision, reason_codes = log_writer._derive_decision("review_feedback", "high")
        self.assertEqual(decision, "enqueue-heavy")
        self.assertEqual(set(reason_codes), {"review_feedback_high_severity"})

    def test_review_feedback_critical(self) -> None:
        decision, reason_codes = log_writer._derive_decision("review_feedback", "critical")
        self.assertEqual(decision, "enqueue-heavy")
        self.assertEqual(set(reason_codes), {"review_feedback_high_severity"})

    def test_schedule_tick_low(self) -> None:
        decision, reason_codes = log_writer._derive_decision("schedule_tick", "low")
        self.assertEqual(decision, "ignore")
        self.assertEqual(set(reason_codes), {"schedule_tick_routine"})

    def test_schedule_tick_medium(self) -> None:
        decision, reason_codes = log_writer._derive_decision("schedule_tick", "medium")
        self.assertEqual(decision, "enqueue-light")
        self.assertEqual(set(reason_codes), {"schedule_tick_escalated"})

    def test_schedule_tick_high(self) -> None:
        decision, reason_codes = log_writer._derive_decision("schedule_tick", "high")
        self.assertEqual(decision, "enqueue-light")
        self.assertEqual(set(reason_codes), {"schedule_tick_escalated"})

    def test_schedule_tick_critical(self) -> None:
        decision, reason_codes = log_writer._derive_decision("schedule_tick", "critical")
        self.assertEqual(decision, "enqueue-light")
        self.assertEqual(set(reason_codes), {"schedule_tick_escalated"})

    def test_runtime_failure_medium(self) -> None:
        decision, reason_codes = log_writer._derive_decision("runtime_failure", "medium")
        self.assertEqual(decision, "enqueue-light")
        self.assertEqual(set(reason_codes), {"runtime_failure_routine"})

    def test_runtime_failure_high(self) -> None:
        decision, reason_codes = log_writer._derive_decision("runtime_failure", "high")
        self.assertEqual(decision, "generate-proposal")
        self.assertEqual(set(reason_codes), {"runtime_failure_observed", "proposal_recommended"})

    def test_runtime_failure_critical(self) -> None:
        decision, reason_codes = log_writer._derive_decision("runtime_failure", "critical")
        self.assertEqual(decision, "escalate-human")
        self.assertEqual(set(reason_codes), {"runtime_failure_critical"})

    def test_raw_added_medium_maps_to_enqueue_light(self) -> None:
        decision, reason_codes = log_writer._derive_decision("raw_added", "medium")
        self.assertEqual(decision, "enqueue-light")
        self.assertEqual(set(reason_codes), {"raw_added_observed"})

    def test_raw_added_low_is_routine_ignore(self) -> None:
        decision, reason_codes = log_writer._derive_decision("raw_added", "low")
        self.assertEqual(decision, "ignore")
        self.assertEqual(set(reason_codes), {"raw_added_routine"})

    def test_unknown_kind_fallback(self) -> None:
        decision, reason_codes = log_writer._derive_decision("unknown_kind", "medium")
        self.assertEqual(decision, "ignore")
        self.assertEqual(set(reason_codes), {"unmapped_kind"})

    def test_all_v1_signal_kinds_have_explicit_routing(self) -> None:
        severities = ("low", "medium", "high", "critical")
        missing: list[str] = []
        for kind in sorted(KINDS):
            decisions = [log_writer._derive_decision(kind, severity) for severity in severities]
            if not any("unmapped_kind" not in reason_codes for _decision, reason_codes in decisions):
                missing.append(kind)
        self.assertEqual(missing, [])

    def test_review_feedback_low_is_unmapped(self) -> None:
        decision, reason_codes = log_writer._derive_decision("review_feedback", "low")
        self.assertEqual(decision, "ignore")
        self.assertEqual(set(reason_codes), {"unmapped_kind"})

    def test_schedule_tick_unknown_severity_is_unmapped(self) -> None:
        decision, reason_codes = log_writer._derive_decision("schedule_tick", "unknown")
        self.assertEqual(decision, "ignore")
        self.assertEqual(set(reason_codes), {"unmapped_kind"})

    def test_runtime_failure_low_is_unmapped(self) -> None:
        decision, reason_codes = log_writer._derive_decision("runtime_failure", "low")
        self.assertEqual(decision, "ignore")
        self.assertEqual(set(reason_codes), {"unmapped_kind"})

    def test_drift_low_maps_to_ignore(self) -> None:
        decision, reason_codes = log_writer._derive_decision("drift", "low")
        self.assertEqual(decision, "ignore")
        self.assertEqual(set(reason_codes), {"drift_routine"})

    def test_drift_medium_maps_to_enqueue_light(self) -> None:
        decision, reason_codes = log_writer._derive_decision("drift", "medium")
        self.assertEqual(decision, "enqueue-light")
        self.assertEqual(set(reason_codes), {"drift_routine"})

    def test_drift_high_maps_to_generate_proposal(self) -> None:
        decision, reason_codes = log_writer._derive_decision("drift", "high")
        self.assertEqual(decision, "generate-proposal")
        self.assertEqual(set(reason_codes), {"drift_observed", "proposal_recommended"})

    def test_drift_critical_maps_to_enqueue_heavy(self) -> None:
        decision, reason_codes = log_writer._derive_decision("drift", "critical")
        self.assertEqual(decision, "enqueue-heavy")
        self.assertEqual(set(reason_codes), {"drift_critical"})

    def test_planner_log_maps_elixir_dependency_break_to_generate_proposal(self) -> None:
        decision, reason_codes = log_writer._derive_decision("elixir_dependency_break", "high")
        self.assertEqual(decision, "generate-proposal")
        self.assertEqual(set(reason_codes), {"elixir_dependency_break_observed", "proposal_recommended"})

    def test_learning_threshold_medium_maps_to_generate_proposal(self) -> None:
        decision, reason_codes = log_writer._derive_decision("learning_threshold", "medium")
        self.assertEqual(decision, "generate-proposal")
        self.assertEqual(set(reason_codes), {"learning_threshold_observed", "proposal_recommended"})

    def test_learning_threshold_low_is_routine_ignore(self) -> None:
        decision, reason_codes = log_writer._derive_decision("learning_threshold", "low")
        self.assertEqual(decision, "ignore")
        self.assertEqual(set(reason_codes), {"learning_threshold_routine"})

    def test_learning_threshold_high_maps_to_heavy_lane(self) -> None:
        decision, reason_codes = log_writer._derive_decision("learning_threshold", "high")
        self.assertEqual(decision, "enqueue-heavy")
        self.assertEqual(reason_codes, ["learning_threshold_observed", "heavy_lane_recommended"])

    def test_learning_threshold_critical_maps_to_heavy_lane(self) -> None:
        decision, reason_codes = log_writer._derive_decision("learning_threshold", "critical")
        self.assertEqual(decision, "enqueue-heavy")
        self.assertEqual(reason_codes, ["learning_threshold_observed", "heavy_lane_recommended"])

    def test_counter_evidence_high_maps_to_generate_proposal(self) -> None:
        decision, reason_codes = log_writer._derive_decision("counter_evidence", "high")
        self.assertEqual(decision, "generate-proposal")
        self.assertEqual(set(reason_codes), {"counter_evidence_observed", "proposal_recommended"})

    def test_counter_evidence_critical_maps_to_heavy_lane(self) -> None:
        decision, reason_codes = log_writer._derive_decision("counter_evidence", "critical")
        self.assertEqual(decision, "enqueue-heavy")
        self.assertEqual(set(reason_codes), {"counter_evidence_observed", "heavy_lane_recommended"})

    def test_counter_evidence_medium_is_routine_ignore(self) -> None:
        decision, reason_codes = log_writer._derive_decision("counter_evidence", "medium")
        self.assertEqual(decision, "ignore")
        self.assertEqual(set(reason_codes), {"counter_evidence_routine"})


class TestGenerateProposalRouting(_FixtureCase):
    def test_derive_decision_runtime_failure_high_severity_emits_generate_proposal(self) -> None:
        decision, reason_codes = log_writer._derive_decision("runtime_failure", "high")
        self.assertEqual(decision, "generate-proposal")
        self.assertEqual(reason_codes, ["runtime_failure_observed", "proposal_recommended"])

    def test_derive_decision_runtime_failure_low_severity_not_upgraded(self) -> None:
        decision, reason_codes = log_writer._derive_decision("runtime_failure", "low")
        self.assertEqual(decision, "ignore")
        self.assertEqual(set(reason_codes), {"unmapped_kind"})
        self.assertNotEqual(decision, "generate-proposal")

    def test_derive_decision_drift_high_severity_emits_generate_proposal(self) -> None:
        decision, reason_codes = log_writer._derive_decision("drift", "high")
        self.assertEqual(decision, "generate-proposal")
        self.assertEqual(set(reason_codes), {"drift_observed", "proposal_recommended"})

    def test_derive_decision_drift_medium_severity_still_enqueue_light(self) -> None:
        decision, reason_codes = log_writer._derive_decision("drift", "medium")
        self.assertEqual(decision, "enqueue-light")
        self.assertEqual(set(reason_codes), {"drift_routine"})

    def test_derive_decision_elixir_dependency_break_emits_generate_proposal(self) -> None:
        decision, reason_codes = log_writer._derive_decision("elixir_dependency_break", "high")
        self.assertEqual(decision, "generate-proposal")
        self.assertEqual(set(reason_codes), {"elixir_dependency_break_observed", "proposal_recommended"})

    def test_derive_decision_review_feedback_unchanged(self) -> None:
        decision, reason_codes = log_writer._derive_decision("review_feedback", "medium")
        self.assertEqual(decision, "enqueue-light")
        self.assertEqual(set(reason_codes), {"review_feedback_routine"})

    def test_derive_decision_schedule_tick_unchanged(self) -> None:
        decision, reason_codes = log_writer._derive_decision("schedule_tick", "low")
        self.assertEqual(decision, "ignore")
        self.assertEqual(set(reason_codes), {"schedule_tick_routine"})

    def test_planner_log_record_mode_remains_observe_only_when_generate_proposal(self) -> None:
        root = self._copy_case_root("case_basic")
        write_planner_log(root, _now=_fixed_now)
        planner_records = _read_jsonl(root / ".aiwiki/state/planner-log.jsonl")
        target = next(item for item in planner_records if item["signal_id"] == "sig-20260424-pln000003")
        self.assertEqual(target["decision"], "generate-proposal")
        self.assertEqual(target["mode"], "observe_only")

    def test_planner_log_record_side_effects_allowed_false_when_generate_proposal(self) -> None:
        root = self._copy_case_root("case_basic")
        write_planner_log(root, _now=_fixed_now)
        planner_records = _read_jsonl(root / ".aiwiki/state/planner-log.jsonl")
        target = next(item for item in planner_records if item["signal_id"] == "sig-20260424-pln000003")
        self.assertEqual(target["decision"], "generate-proposal")
        self.assertIs(target["side_effects_allowed"], False)

    def test_planner_log_dedupe_key_unchanged_for_generate_proposal(self) -> None:
        root = self._copy_case_root("case_basic")
        write_planner_log(root, _now=_fixed_now)
        planner_records = _read_jsonl(root / ".aiwiki/state/planner-log.jsonl")
        target = next(item for item in planner_records if item["signal_id"] == "sig-20260424-pln000003")
        self.assertEqual(target["decision"], "generate-proposal")
        self.assertEqual(compute_planner_log_dedupe_key(target), "sig-20260424-pln000003:observe_only")

    def test_planner_log_replay_summary_emitted_by_decision_includes_generate_proposal(self) -> None:
        root = self._copy_case_root("case_basic")
        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["new_count"], 3)
        self.assertEqual(result["emitted_by_decision"]["generate-proposal"], 1)
        self.assertEqual(result["emitted_by_decision"]["enqueue-heavy"], 0)


class TestIdempotency(_FixtureCase):
    def test_case_basic_matches_expected_payload_and_summary(self) -> None:
        root = self._copy_case_root("case_basic")

        result = write_planner_log(root, _now=_fixed_now)

        expected_summary = json.loads((FIXTURE_DIR / "case_basic" / "expected" / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(result, expected_summary)

        planner_log_path = root / ".aiwiki/state/planner-log.jsonl"
        expected_log = (FIXTURE_DIR / "case_basic" / "expected" / "planner-log.jsonl").read_text(encoding="utf-8")
        self.assertEqual(planner_log_path.read_text(encoding="utf-8"), expected_log)

    def test_double_replay_is_idempotent(self) -> None:
        root = self._copy_case_root("case_basic")
        path = root / ".aiwiki/state/planner-log.jsonl"

        first = write_planner_log(root, _now=_fixed_now)
        before = path.read_bytes()
        second = write_planner_log(root, _now=_fixed_now)

        self.assertEqual(first["new_count"], 3)
        self.assertEqual(second["new_count"], 0)
        self.assertEqual(second["duplicate_count"], 3)
        self.assertEqual(path.read_bytes(), before)

    def test_fixture_idempotent_matches_summary_and_keeps_file(self) -> None:
        root = self._copy_case_root("case_idempotent")
        path = root / ".aiwiki/state/planner-log.jsonl"
        before = path.read_bytes()
        expected_summary = json.loads(
            (FIXTURE_DIR / "case_idempotent" / "expected" / "summary.json").read_text(encoding="utf-8")
        )

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result, expected_summary)
        self.assertEqual(path.read_bytes(), before)

    def test_append_new_signal_only_appends_one_line(self) -> None:
        root = self._copy_case_root("case_basic")
        path = root / ".aiwiki/state/planner-log.jsonl"
        signals_path = root / ".aiwiki/state/signals.jsonl"

        write_planner_log(root, _now=_fixed_now)
        before_count = len(_read_jsonl(path))

        with signals_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "schema_version": 1,
                        "signal_id": "sig-20260424-pln000004",
                        "dedupe_key": "runtime_failure:general:llm_receipt:sha256-new",
                        "kind": "runtime_failure",
                        "scope": {
                            "protocol": "general",
                            "source_ids": [],
                            "concept_slugs": [],
                            "elixir_refs": [],
                            "judgment_refs": [],
                        },
                        "severity": "critical",
                        "evidence_refs": ["output/reports/new.md"],
                        "emitted_at": "2026-04-24T00:00:04Z",
                        "emitted_by": "external",
                        "source_kind": "llm_receipt",
                        "source_event_ref": ".aiwiki/logs/llm-receipts.jsonl#L4",
                        "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                    },
                    separators=(",", ":"),
                    sort_keys=False,
                )
                + "\n"
            )

        result = write_planner_log(root, _now=_fixed_now)
        records = _read_jsonl(path)
        self.assertEqual(result["new_count"], 1)
        self.assertEqual(len(records), before_count + 1)
        self.assertEqual(records[-1]["decision"], "escalate-human")

    def test_write_planner_log_maps_elixir_dependency_break_end_to_end(self) -> None:
        root = self.temp_root / "elixir-break-mapping"
        signals_path = root / ".aiwiki/state/signals.jsonl"
        signals_path.parent.mkdir(parents=True, exist_ok=True)
        signals_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-20260424-elixir0001",
                    "dedupe_key": "elixir_dependency_break:research:execution_receipt:elixir-demote-a-1::elixir-b",
                    "kind": "elixir_dependency_break",
                    "scope": {
                        "protocol": "research",
                        "source_ids": [],
                        "concept_slugs": [],
                        "elixir_refs": ["wiki/elixirs/elixir-b.md"],
                        "judgment_refs": [],
                    },
                    "severity": "high",
                    "evidence_refs": ["elixir-demote-a-1"],
                    "emitted_at": "2026-04-24T11:30:00Z",
                    "emitted_by": "compile",
                    "source_kind": "execution_receipt",
                    "source_event_ref": ".aiwiki/state/execution-receipts.jsonl#L1",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                separators=(",", ":"),
                sort_keys=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)

        self.assertEqual(result["new_count"], 1)
        planner_records = _read_jsonl(root / ".aiwiki/state/planner-log.jsonl")
        self.assertEqual(len(planner_records), 1)
        record = planner_records[0]
        self.assertEqual(record["mode"], "observe_only")
        self.assertEqual(record["decision"], "generate-proposal")
        self.assertEqual(set(record["reason_codes"]), {"elixir_dependency_break_observed", "proposal_recommended"})
        self.assertNotEqual(record["decision"], "ignore")
        self.assertNotIn("unmapped_kind", record["reason_codes"])

    def test_write_planner_log_maps_learning_threshold_end_to_end(self) -> None:
        root = self.temp_root / "learning-threshold-mapping"
        signals_path = root / ".aiwiki/state/signals.jsonl"
        signals_path.parent.mkdir(parents=True, exist_ok=True)
        signals_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-20260424-learn0001",
                    "dedupe_key": "learning_threshold:general:runtime_history:learning-threshold::general::30::old-active",
                    "kind": "learning_threshold",
                    "scope": {
                        "protocol": "general",
                        "source_ids": ["old-active"],
                        "concept_slugs": [],
                        "elixir_refs": [],
                        "judgment_refs": [],
                    },
                    "severity": "medium",
                    "evidence_refs": [".aiwiki/state/protocol_learnings_age.json"],
                    "emitted_at": "2026-04-24T11:45:00Z",
                    "emitted_by": "user",
                    "source_kind": "runtime_history",
                    "source_event_ref": ".aiwiki/state/runtime-history.jsonl#L1",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                separators=(",", ":"),
                sort_keys=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)

        self.assertEqual(result["new_count"], 1)
        planner_records = _read_jsonl(root / ".aiwiki/state/planner-log.jsonl")
        self.assertEqual(len(planner_records), 1)
        record = planner_records[0]
        self.assertEqual(record["mode"], "observe_only")
        self.assertFalse(record["side_effects_allowed"])
        self.assertEqual(record["decision"], "generate-proposal")
        self.assertEqual(set(record["reason_codes"]), {"learning_threshold_observed", "proposal_recommended"})
        self.assertNotIn("unmapped_kind", record["reason_codes"])

    def test_write_planner_log_maps_counter_evidence_end_to_end(self) -> None:
        root = self.temp_root / "counter-evidence-mapping"
        signals_path = root / ".aiwiki/state/signals.jsonl"
        signals_path.parent.mkdir(parents=True, exist_ok=True)
        signals_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-20260424-counter001",
                    "dedupe_key": "counter_evidence:research:runtime_history:judgment-alpha:src-followup",
                    "kind": "counter_evidence",
                    "scope": {
                        "protocol": "research",
                        "source_ids": ["src-followup"],
                        "concept_slugs": [],
                        "elixir_refs": [],
                        "judgment_refs": ["wiki/judgments/judgment-alpha.md"],
                    },
                    "severity": "high",
                    "evidence_refs": ["wiki/judgments/judgment-alpha.md", "wiki/sources/src-followup.md"],
                    "emitted_at": "2026-04-24T11:46:00Z",
                    "emitted_by": "compile",
                    "source_kind": "runtime_history",
                    "source_event_ref": ".aiwiki/state/runtime-history.jsonl#L2",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                separators=(",", ":"),
                sort_keys=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)

        self.assertEqual(result["new_count"], 1)
        planner_records = _read_jsonl(root / ".aiwiki/state/planner-log.jsonl")
        record = planner_records[0]
        self.assertEqual(record["mode"], "observe_only")
        self.assertFalse(record["side_effects_allowed"])
        self.assertEqual(record["decision"], "generate-proposal")
        self.assertEqual(set(record["reason_codes"]), {"counter_evidence_observed", "proposal_recommended"})
        self.assertNotIn("unmapped_kind", record["reason_codes"])

    def test_write_planner_log_maps_raw_added_end_to_end(self) -> None:
        root = self.temp_root / "raw-added-mapping"
        signals_path = root / ".aiwiki/state/signals.jsonl"
        signals_path.parent.mkdir(parents=True, exist_ok=True)
        signals_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-20260424-rawadd001",
                    "dedupe_key": "raw_added:general:runtime_history:raw/inbox/src-note-1.md",
                    "kind": "raw_added",
                    "scope": {
                        "protocol": "general",
                        "source_ids": ["src-note-1"],
                        "concept_slugs": [],
                        "elixir_refs": [],
                        "judgment_refs": [],
                    },
                    "severity": "medium",
                    "evidence_refs": ["raw/inbox/src-note-1.md"],
                    "emitted_at": "2026-04-24T11:47:00Z",
                    "emitted_by": "user",
                    "source_kind": "runtime_history",
                    "source_event_ref": ".aiwiki/state/runtime-history.jsonl#L3",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                separators=(",", ":"),
                sort_keys=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)

        self.assertEqual(result["new_count"], 1)
        planner_records = _read_jsonl(root / ".aiwiki/state/planner-log.jsonl")
        record = planner_records[0]
        self.assertEqual(record["mode"], "observe_only")
        self.assertFalse(record["side_effects_allowed"])
        self.assertEqual(record["decision"], "enqueue-light")
        self.assertEqual(set(record["reason_codes"]), {"raw_added_observed"})
        self.assertNotIn("unmapped_kind", record["reason_codes"])

    def test_default_signals_path_missing_is_noop(self) -> None:
        root = self.temp_root / "empty-signals"
        root.mkdir(parents=True, exist_ok=True)

        result = write_planner_log(root, signals_path=None, _now=_fixed_now)
        self.assertEqual(result["scanned_count"], 0)
        self.assertEqual(result["new_count"], 0)
        self.assertFalse((root / ".aiwiki/state/planner-log.jsonl").exists())

    def test_explicit_signals_path_missing_raises(self) -> None:
        root = self.temp_root / "explicit-missing-signals"
        root.mkdir(parents=True, exist_ok=True)

        with self.assertRaisesRegex(FileNotFoundError, "signals path not found"):
            write_planner_log(root, signals_path=Path(".aiwiki/state/missing-signals.jsonl"), _now=_fixed_now)

    def test_relative_and_absolute_signals_path_supported(self) -> None:
        root = self._copy_case_root("case_basic")

        rel_result = write_planner_log(root, signals_path=Path(".aiwiki/state/signals.jsonl"), _now=_fixed_now)
        self.assertEqual(rel_result["new_count"], 3)

        abs_root = self.temp_root / "abs-signals"
        abs_root.mkdir(parents=True, exist_ok=True)
        abs_path = root / ".aiwiki/state/signals.jsonl"
        abs_result = write_planner_log(abs_root, signals_path=abs_path, _now=_fixed_now)
        self.assertEqual(abs_result["new_count"], 3)
        self.assertEqual(abs_result["signals_path"], str(abs_path))


class TestPlannerLogRollbackPreview(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _record(self, signal_id: str, trace_id: str, decision: str = "enqueue-heavy") -> dict[str, object]:
        return {
            "schema_version": 1,
            "signal_id": signal_id,
            "dedupe_key": f"review_feedback:research:runtime_history:{signal_id}",
            "trace_id": trace_id,
            "decision": decision,
            "mode": "observe_only",
            "reason_codes": ["review_feedback_observed", "heavy_lane_recommended"],
            "budget_used": {},
            "locks_acquired": [],
            "primitive_refs": [],
            "side_effects_allowed": False,
            "decided_at": "2026-04-24T12:00:00Z",
        }

    def _write_planner_log(self, records: list[dict[str, object]]) -> str:
        path = self.root / ".aiwiki/state/planner-log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(canonical_dumps_planner_log(record) + "\n" for record in records)
        path.write_text(content, encoding="utf-8")
        return content

    def test_preview_filters_and_does_not_mutate_planner_log(self) -> None:
        before = self._write_planner_log(
            [
                self._record("sig-20260424-rollback01", "550e8400-e29b-41d4-a716-446655440000"),
                self._record("sig-20260424-rollback02", "550e8400-e29b-41d4-a716-446655440001", "generate-proposal"),
            ]
        )

        result = preview_planner_log_rollback(
            self.root,
            trace_id="550e8400-e29b-41d4-a716-446655440001",
        )

        self.assertFalse(result["side_effects_allowed"])
        self.assertFalse(result["delete_supported"])
        self.assertEqual(result["rollback_strategy"], "append_marker")
        self.assertTrue(result["marker_planned"])
        self.assertEqual(result["scanned_count"], 2)
        self.assertEqual(result["matched_count"], 1)
        self.assertEqual(result["records"][0]["source_ref"], ".aiwiki/state/planner-log.jsonl#L2")
        self.assertEqual(result["records"][0]["decision"], "generate-proposal")
        self.assertFalse(result["records"][0]["delete_supported"])
        self.assertEqual((self.root / ".aiwiki/state/planner-log.jsonl").read_text(encoding="utf-8"), before)

    def test_preview_limit_caps_returned_records(self) -> None:
        self._write_planner_log(
            [
                self._record("sig-20260424-rollback01", "550e8400-e29b-41d4-a716-446655440000"),
                self._record("sig-20260424-rollback02", "550e8400-e29b-41d4-a716-446655440001"),
            ]
        )

        result = preview_planner_log_rollback(self.root, limit=1)

        self.assertEqual(result["matched_count"], 2)
        self.assertEqual(result["returned_count"], 1)

    def test_preview_rejects_non_positive_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit must be a positive integer"):
            preview_planner_log_rollback(self.root, limit=0)


class TestCorruptFailFast(_FixtureCase):
    def test_fixture_corrupt_hard_fail_and_file_unchanged(self) -> None:
        root = self._copy_case_root("case_corrupt")
        path = root / ".aiwiki/state/planner-log.jsonl"
        before = path.read_bytes()
        expected_fragment = (FIXTURE_DIR / "case_corrupt" / "expected" / "exception.txt").read_text(encoding="utf-8").strip()

        with self.assertRaisesRegex(RuntimeError, expected_fragment):
            write_planner_log(root, _now=_fixed_now)

        self.assertEqual(path.read_bytes(), before)

    def test_existing_planner_log_malformed_json_hard_fail(self) -> None:
        root = self.temp_root / "bad-existing-json"
        path = root / ".aiwiki/state/planner-log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{bad\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "invalid planner-log.jsonl JSON"):
            write_planner_log(root, _now=_fixed_now)

    def test_existing_planner_log_schema_invalid_hard_fail(self) -> None:
        root = self.temp_root / "bad-existing-schema"
        path = root / ".aiwiki/state/planner-log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema_version": 1}, separators=(",", ":")) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "invalid planner-log.jsonl record"):
            write_planner_log(root, _now=_fixed_now)

    def test_existing_planner_log_non_object_hard_fail(self) -> None:
        root = self.temp_root / "bad-existing-non-object"
        path = root / ".aiwiki/state/planner-log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "expected object"):
            write_planner_log(root, _now=_fixed_now)

    def test_existing_planner_log_blank_lines_are_ignored(self) -> None:
        root = self.temp_root / "existing-blank-lines"
        path = root / ".aiwiki/state/planner-log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "schema_version": 1,
            "signal_id": "sig-20260424-existing01",
            "dedupe_key": "review_feedback:research:runtime_history:sha256-existing",
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "decision": "enqueue-light",
            "mode": "observe_only",
            "reason_codes": ["review_feedback_routine"],
            "budget_used": {},
            "locks_acquired": [],
            "primitive_refs": [],
            "side_effects_allowed": False,
            "decided_at": "2026-04-24T12:00:00Z",
        }
        path.write_text("\n" + canonical_dumps_planner_log(record) + "\n", encoding="utf-8")

        result = write_planner_log(root, signals_path=None, _now=_fixed_now)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["scanned_count"], 0)


class TestBadSignalTolerance(_FixtureCase):
    def test_malformed_signal_lines_count_invalid(self) -> None:
        root = self.temp_root / "bad-signal"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{bad\n[]\n", encoding="utf-8")

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["scanned_count"], 2)
        self.assertEqual(result["invalid_count"], 2)
        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["skip_examples"][0]["reason"], "signal_malformed_json")
        self.assertEqual(result["skip_examples"][0]["source"], "signals")
        self.assertEqual(tuple(result["skip_examples"][0].keys()), ("reason", "source", "line"))
        self.assertEqual(result["skip_examples"][1]["reason"], "signal_non_object")
        self.assertEqual(result["skip_examples"][1]["source"], "signals")
        self.assertEqual(tuple(result["skip_examples"][1].keys()), ("reason", "source", "line"))

    def test_malformed_json_skip_example_source_is_signals(self) -> None:
        root = self.temp_root / "malformed-json-source"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{bad\n", encoding="utf-8")

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["skip_examples"][0]["reason"], "signal_malformed_json")
        self.assertEqual(result["skip_examples"][0]["source"], "signals")
        self.assertEqual(tuple(result["skip_examples"][0].keys()), ("reason", "source", "line"))

    def test_blank_signal_line_is_skipped_not_scanned(self) -> None:
        root = self.temp_root / "blank-signal-line"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n{bad\n", encoding="utf-8")

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["scanned_count"], 1)
        self.assertEqual(result["invalid_count"], 1)

    def test_signal_missing_kind_is_invalid_count(self) -> None:
        root = self.temp_root / "missing-kind"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-20260424-badsignal01",
                    "dedupe_key": "review_feedback:general:runtime_history:sha256-missing-kind",
                    "severity": "medium",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["skip_examples"][0]["reason"], "signal_missing_kind")
        self.assertEqual(result["skip_examples"][0]["source"], "signals")
        self.assertFalse((root / ".aiwiki/state/planner-log.jsonl").exists())

    def test_signal_invalid_severity_is_invalid_count(self) -> None:
        root = self.temp_root / "invalid-severity"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-20260424-badsignal02",
                    "dedupe_key": "review_feedback:general:runtime_history:sha256-invalid-severity",
                    "kind": "review_feedback",
                    "severity": "xxx",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["skip_examples"][0]["reason"], "signal_invalid_severity")

    def test_signal_missing_trace_id_is_invalid_count(self) -> None:
        root = self.temp_root / "missing-trace-id"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-20260424-badsignal03",
                    "dedupe_key": "review_feedback:general:runtime_history:sha256-missing-trace",
                    "kind": "review_feedback",
                    "severity": "medium",
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["skip_examples"][0]["reason"], "signal_missing_trace_id")

    def test_signal_invalid_signal_id_is_invalid_count(self) -> None:
        root = self.temp_root / "invalid-signal-id"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-bad",
                    "dedupe_key": "review_feedback:general:runtime_history:sha256-invalid-signal-id",
                    "kind": "review_feedback",
                    "severity": "medium",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["skip_examples"][0]["reason"], "signal_invalid_signal_id")

    def test_signal_missing_severity_is_invalid_count(self) -> None:
        root = self.temp_root / "missing-severity"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-20260424-badsignal04",
                    "dedupe_key": "review_feedback:general:runtime_history:sha256-missing-severity",
                    "kind": "review_feedback",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["skip_examples"][0]["reason"], "signal_missing_severity")

    def test_signal_missing_signal_id_is_invalid_count(self) -> None:
        root = self.temp_root / "missing-signal-id"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "dedupe_key": "review_feedback:general:runtime_history:sha256-missing-signal-id",
                    "kind": "review_feedback",
                    "severity": "medium",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["skip_examples"][0]["reason"], "signal_missing_signal_id")

    def test_signal_missing_dedupe_key_is_invalid_count(self) -> None:
        root = self.temp_root / "missing-dedupe-key"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-20260424-badsignal05",
                    "kind": "review_feedback",
                    "severity": "medium",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["skip_examples"][0]["reason"], "signal_missing_dedupe_key")

    def test_signal_invalid_trace_id_is_invalid_count(self) -> None:
        root = self.temp_root / "invalid-trace-id"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-20260424-badsignal06",
                    "dedupe_key": "review_feedback:general:runtime_history:sha256-invalid-trace-id",
                    "kind": "review_feedback",
                    "severity": "medium",
                    "trace_id": "not-a-uuid",
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["skip_examples"][0]["reason"], "signal_invalid_trace_id")

    def test_signal_missing_multiple_fields_reports_first_in_fixed_order(self) -> None:
        root = self.temp_root / "missing-multiple-fields-order"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "schema_version": 1,
                            "signal_id": "sig-20260424-multi0001",
                            "dedupe_key": "review_feedback:general:runtime_history:sha256-multi-01",
                            "severity": "medium",
                            # missing kind + trace_id => missing_kind first
                        },
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        {
                            "schema_version": 1,
                            "kind": "review_feedback",
                            "signal_id": "sig-20260424-multi0002",
                            # missing severity + dedupe_key => missing_severity first
                            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                        },
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        {
                            "schema_version": 1,
                            "kind": "review_feedback",
                            "severity": "medium",
                            # missing signal_id + dedupe_key + trace_id => missing_signal_id first
                        },
                        separators=(",", ":"),
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = write_planner_log(root, _now=_fixed_now)
        reasons = [item["reason"] for item in result["skip_examples"]]
        self.assertEqual(
            reasons,
            [
                "signal_missing_kind",
                "signal_missing_severity",
                "signal_missing_signal_id",
            ],
        )

    def test_planner_dedupe_key_build_failed_is_invalid_count(self) -> None:
        root = self.temp_root / "dedupe-build-failed"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-20260424-badsignal07",
                    "dedupe_key": "review_feedback:general:runtime_history:sha256-dedupe-fail",
                    "kind": "review_feedback",
                    "severity": "medium",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        with patch("aiwiki.planner.log_writer.compute_planner_log_dedupe_key", side_effect=RuntimeError("boom")):
            result = write_planner_log(root, _now=_fixed_now)

        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["skip_examples"][0]["reason"], "planner_dedupe_key_build_failed")
        self.assertEqual(result["skip_examples"][0]["source"], "signals")
        self.assertEqual(tuple(result["skip_examples"][0].keys()), ("reason", "source", "line"))

    def test_planner_record_validation_failed_is_invalid_count(self) -> None:
        root = self.temp_root / "planner-record-invalid"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "signal_id": "sig-20260424-badsignal08",
                    "dedupe_key": "review_feedback:general:runtime_history:sha256-validation-fail",
                    "kind": "review_feedback",
                    "severity": "medium",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        validation_result = type("ValidationResult", (), {"ok": False, "errors": ("invalid",)})()
        with patch("aiwiki.planner.log_writer.validate_planner_log_record", return_value=validation_result):
            result = write_planner_log(root, _now=_fixed_now)

        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["skip_examples"][0]["reason"], "planner_record_validation_failed")
        self.assertEqual(result["skip_examples"][0]["source"], "signals")
        self.assertEqual(tuple(result["skip_examples"][0].keys())[:3], ("reason", "source", "line"))

    def test_skip_examples_capped_at_five(self) -> None:
        root = self.temp_root / "skip-cap"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(["{bad"] * 7) + "\n", encoding="utf-8")

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["invalid_count"], 7)
        self.assertEqual(len(result["skip_examples"]), 5)

    def test_batch_duplicate_signal_identity_counts_duplicate(self) -> None:
        root = self.temp_root / "batch-dup"
        path = root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "schema_version": 1,
                "signal_id": "sig-20260424-pln000050",
                "dedupe_key": "review_feedback:research:runtime_history:sha256-dup",
                "kind": "review_feedback",
                "scope": {
                    "protocol": "research",
                    "source_ids": [],
                    "concept_slugs": [],
                    "elixir_refs": [],
                    "judgment_refs": [],
                },
                "severity": "medium",
                "evidence_refs": ["wiki/decisions/dup.md"],
                "emitted_at": "2026-04-24T00:05:00Z",
                "emitted_by": "user",
                "source_kind": "runtime_history",
                "source_event_ref": ".aiwiki/state/runtime-history.jsonl#L1",
                "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            },
            separators=(",", ":"),
        )
        path.write_text(line + "\n" + line + "\n", encoding="utf-8")

        result = write_planner_log(root, _now=_fixed_now)
        self.assertEqual(result["new_count"], 1)
        self.assertEqual(result["duplicate_count"], 1)


class TestObserveOnlyAST(unittest.TestCase):
    _ALLOWED_PREFIXES = {
        "aiwiki.planner",
        "aiwiki.signals",
        "aiwiki.app_utils",
    }

    def _collect_imports(self, module_path: Path, module_name: str) -> list[str]:
        return self._collect_imports_from_source(module_path.read_text(encoding="utf-8"), module_name)

    def _collect_imports_from_source(self, source: str, module_name: str) -> list[str]:
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
                continue
            if not isinstance(node, ast.ImportFrom):
                continue

            parts = module_name.split(".")
            prefix = parts[:-node.level] if node.level > 0 else []
            if node.module:
                base = ".".join([*prefix, node.module]) if prefix else node.module
            else:
                base = ".".join(prefix)

            for alias in node.names:
                if base == "aiwiki":
                    imports.append(f"aiwiki.{alias.name}")
                elif base:
                    imports.append(base)
                else:
                    imports.append(alias.name)
        return imports

    def _is_allowed(self, module: str) -> bool:
        if module in sys.stdlib_module_names or module.split(".")[0] in sys.stdlib_module_names:
            return True
        for prefix in self._ALLOWED_PREFIXES:
            if module == prefix or module.startswith(prefix + "."):
                return True
        return False

    def test_only_allowlisted_imports_in_planner_modules(self) -> None:
        src_root = Path(__file__).resolve().parent.parent / "src" / "aiwiki" / "planner"
        log_writer_imports = self._collect_imports(src_root / "log_writer.py", "aiwiki.planner.log_writer")
        schema_imports = self._collect_imports(src_root / "schema.py", "aiwiki.planner.schema")
        offending = sorted(name for name in (log_writer_imports + schema_imports) if not self._is_allowed(name))
        self.assertEqual(offending, [])

    def test_schema_does_not_import_aiwiki_signals(self) -> None:
        src_root = Path(__file__).resolve().parent.parent / "src" / "aiwiki" / "planner"
        schema_imports = self._collect_imports(src_root / "schema.py", "aiwiki.planner.schema")
        self.assertTrue(all(not name.startswith("aiwiki.signals") for name in schema_imports))

    def test_from_aiwiki_runner_is_rejected_by_allowlist(self) -> None:
        imports = self._collect_imports_from_source("from aiwiki import runner\n", "aiwiki.planner.log_writer")
        self.assertEqual(imports, ["aiwiki.runner"])
        self.assertFalse(self._is_allowed(imports[0]))

    def test_from_aiwiki_execution_review_is_rejected_by_allowlist(self) -> None:
        self.assertFalse(self._is_allowed("aiwiki.execution.review"))


class TestFileSystemDiff(_FixtureCase):
    def test_only_planner_log_changes_on_basic_replay(self) -> None:
        root = self._copy_case_root("case_basic")
        before = _snapshot_files(root)

        write_planner_log(root, _now=_fixed_now)

        after = _snapshot_files(root)
        changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
        self.assertEqual(changed, [".aiwiki/state/planner-log.jsonl"])

    def test_corrupt_replay_keeps_files_unchanged(self) -> None:
        root = self._copy_case_root("case_corrupt")
        before = _snapshot_files(root)

        with self.assertRaises(RuntimeError):
            write_planner_log(root, _now=_fixed_now)

        after = _snapshot_files(root)
        self.assertEqual(before, after)


class TestTraceIdPassthrough(_FixtureCase):
    def test_trace_id_passthrough_from_signal_to_planner_log(self) -> None:
        root = self._copy_case_root("case_basic")
        signals = _read_jsonl(root / ".aiwiki/state/signals.jsonl")

        write_planner_log(root, _now=_fixed_now)
        planner_records = _read_jsonl(root / ".aiwiki/state/planner-log.jsonl")

        signal_trace_by_id = {str(item["signal_id"]): str(item["trace_id"]) for item in signals}
        for record in planner_records:
            signal_id = str(record["signal_id"])
            self.assertEqual(str(record["trace_id"]), signal_trace_by_id[signal_id])

    def test_case_unmapped_kind_fixture_matches_expected(self) -> None:
        root = self._copy_case_root("case_unmapped_kind")
        result = write_planner_log(root, _now=_fixed_now)

        expected_summary = json.loads(
            (FIXTURE_DIR / "case_unmapped_kind" / "expected" / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(result, expected_summary)

        planner_log_path = root / ".aiwiki/state/planner-log.jsonl"
        expected_log = (FIXTURE_DIR / "case_unmapped_kind" / "expected" / "planner-log.jsonl").read_text(
            encoding="utf-8"
        )
        self.assertEqual(planner_log_path.read_text(encoding="utf-8"), expected_log)


class TestCLI(_FixtureCase):
    def _run_main(self, root: Path, argv: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            code = main(["--root", str(root), *argv])
        payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
        return code, payload, stderr.getvalue()

    def test_parser_registers_planner_log_replay_after_signals_replay(self) -> None:
        parser = build_parser()
        action = next(item for item in parser._actions if getattr(item, "dest", "") == "command")
        names = list(action.choices.keys())
        self.assertLess(names.index("signals-replay"), names.index("planner-log-replay"))
        self.assertLess(names.index("planner-log-replay"), names.index("llm-check"))

    def test_main_dispatches_planner_log_replay(self) -> None:
        with patch("aiwiki.cli.write_planner_log", return_value={"status": "ok"}) as mocked:
            code, payload, stderr = self._run_main(
                self.temp_root,
                ["planner-log-replay", "--signals-path", "custom/signals.jsonl"],
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        mocked.assert_called_once_with(self.temp_root, signals_path=Path("custom/signals.jsonl"))
        self.assertEqual(payload["status"], "ok")

    def test_parser_planner_log_replay_flags(self) -> None:
        parser = build_parser()
        action = next(item for item in parser._actions if getattr(item, "dest", "") == "command")
        replay_parser = action.choices["planner-log-replay"]
        signals_action = next(item for item in replay_parser._actions if item.dest == "signals_path")
        self.assertEqual(signals_action.option_strings, ["--signals-path"])

    def test_cli_end_to_end_summary_fixed_keys(self) -> None:
        root = self._copy_case_root("case_basic")
        code, payload, stderr = self._run_main(root, ["planner-log-replay"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            set(payload.keys()),
            {
                "status",
                "signals_path",
                "log_path",
                "scanned_count",
                "new_count",
                "duplicate_count",
                "invalid_count",
                "emitted_by_decision",
                "skip_examples",
            },
        )


class TestCanonicalDumps(unittest.TestCase):
    def test_canonical_dumps_order_and_idempotent(self) -> None:
        record = {
            "decided_at": "2026-04-24T12:00:00Z",
            "side_effects_allowed": False,
            "primitive_refs": [],
            "locks_acquired": [],
            "budget_used": {},
            "reason_codes": ["b", "a", "a"],
            "mode": "observe_only",
            "decision": "ignore",
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "dedupe_key": "k",
            "signal_id": "sig-20260424-canon01",
            "schema_version": 1,
        }
        dumped = canonical_dumps_planner_log(record)
        loaded = json.loads(dumped)
        self.assertEqual(tuple(loaded.keys()), TOP_LEVEL_FIELD_ORDER)
        self.assertEqual(loaded["reason_codes"], ["b", "a"])
        self.assertEqual(canonical_dumps_planner_log(loaded), dumped)

    def test_canonical_dumps_unknown_field_sorted_tail(self) -> None:
        record = {
            "schema_version": 1,
            "signal_id": "sig-20260424-canon02",
            "dedupe_key": "k",
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "decision": "ignore",
            "mode": "observe_only",
            "reason_codes": ["unmapped_kind"],
            "budget_used": {},
            "locks_acquired": [],
            "primitive_refs": [],
            "side_effects_allowed": False,
            "decided_at": "2026-04-24T12:00:00Z",
            "z_extra": 1,
            "a_extra": 2,
        }
        loaded = json.loads(canonical_dumps_planner_log(record))
        self.assertEqual(tuple(loaded.keys())[-2:], ("a_extra", "z_extra"))

    def test_compute_planner_log_dedupe_key(self) -> None:
        record = {"signal_id": "sig-20260424-canon03", "mode": "observe_only"}
        self.assertEqual(compute_planner_log_dedupe_key(record), "sig-20260424-canon03:observe_only")

    def test_canonical_dumps_reason_codes_passthrough_for_invalid_type(self) -> None:
        record = {
            "schema_version": 1,
            "signal_id": "sig-20260424-canon04",
            "dedupe_key": "k",
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "decision": "ignore",
            "mode": "observe_only",
            "reason_codes": "bad",
            "budget_used": {},
            "locks_acquired": [],
            "primitive_refs": [],
            "side_effects_allowed": False,
            "decided_at": "2026-04-24T12:00:00Z",
        }
        loaded = json.loads(canonical_dumps_planner_log(record))
        self.assertEqual(loaded["reason_codes"], "bad")

    def test_canonical_dumps_reason_codes_passthrough_for_mixed_list(self) -> None:
        record = {
            "schema_version": 1,
            "signal_id": "sig-20260424-canon05",
            "dedupe_key": "k",
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "decision": "ignore",
            "mode": "observe_only",
            "reason_codes": ["ok", 1],
            "budget_used": {},
            "locks_acquired": [],
            "primitive_refs": [],
            "side_effects_allowed": False,
            "decided_at": "2026-04-24T12:00:00Z",
        }
        loaded = json.loads(canonical_dumps_planner_log(record))
        self.assertEqual(len(loaded["reason_codes"]), 2)
        self.assertIn("ok", loaded["reason_codes"])
        self.assertIn(1, loaded["reason_codes"])

    def test_canonical_dumps_unknown_field_with_reason_codes_name_is_passthrough(self) -> None:
        record = {
            "schema_version": 1,
            "signal_id": "sig-20260424-canon06",
            "dedupe_key": "k",
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "decision": "ignore",
            "mode": "observe_only",
            "reason_codes": ["ok"],
            "budget_used": {},
            "locks_acquired": [],
            "primitive_refs": [],
            "side_effects_allowed": False,
            "decided_at": "2026-04-24T12:00:00Z",
            "a_extra": "x",
        }
        loaded = json.loads(canonical_dumps_planner_log(record))
        self.assertEqual(loaded["a_extra"], "x")


class TestPublicContracts(unittest.TestCase):
    def test_closed_sets_stable(self) -> None:
        self.assertEqual(MODES, frozenset({"observe_only"}))
        self.assertEqual(
            DECISIONS,
            frozenset(
                {
                    "ignore",
                    "enqueue-light",
                    "enqueue-heavy",
                    "generate-proposal",
                    "escalate-human",
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
