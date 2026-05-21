from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.app_protocol import ensure_layout
from scripts.dogfood_maturity_gate import (
    RUN_RECEIPT_KIND,
    build_parser,
    collect_metrics,
    maturity_gate_dir,
    prepare_nightly_env,
    summarize_recent_run_receipts,
    summarize_run_receipts,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records) + "\n"
    path.write_text(text, encoding="utf-8")


def _make_run_receipt(
    *,
    generated_at: str,
    status: str,
    before_backlog: int,
    after_backlog: int,
    before_candidate: int,
    after_candidate: int,
    before_judgment_receipts: int,
    after_judgment_receipts: int,
    generated_count: int = 0,
    skipped_count: int = 0,
    already_exists_count: int = 0,
) -> dict:
    return {
        "kind": RUN_RECEIPT_KIND,
        "version": 1,
        "generated_at": generated_at,
        "status": status,
        "receipt_path": f"output/control/maturity-gate/run-{generated_at.replace(':', '').replace('-', '')}.json",
        "before": {
            "backlog_total": before_backlog,
            "l3_proposal_counts_by_state": {"candidate": before_candidate},
            "judgment_review_receipt_counts": {"total": before_judgment_receipts},
            "prompts_ask_sha256": "abc",
        },
        "after": {
            "backlog_total": after_backlog,
            "l3_proposal_counts_by_state": {"candidate": after_candidate},
            "judgment_review_receipt_counts": {"total": after_judgment_receipts},
            "prompts_ask_sha256": "abc",
            "knowledge_compounding_proof": {
                "kind": "knowledge-compounding-proof-report",
                "version": 1,
                "status": "pass",
                "verdict": "pass",
                "reason": "fixture compounding proof observed",
                "metrics": {
                    "raw_to_wiki_count": {"value": 1},
                    "judgment_or_elixir_reuse_count": {"value": 1},
                    "output_file_back_rate": {"value": 1.0},
                    "receipt_backed_actions": {"value": 1},
                    "human_required_exception_count": {"value": 0},
                },
                "compounding_sample": {
                    "artifact_path": "output/reports/r1.md",
                    "reused_ref": "wiki/judgments/j1.md",
                    "receipt_path": "output/control/execution-receipts/report-r1.json",
                },
                "missing_evidence": [],
            },
            "l3_debt_report": {
                "effective_preview_candidate_count": max(generated_count - already_exists_count, 0),
                "dedupe_or_noise_ratio": 0.5 if already_exists_count else 0.0,
            },
            "judgment_lane_report": {
                "failure_rate": 0.0,
                "exception_rate": 0.25,
                "exception_queue": [],
            },
            "human_required_report": {
                "human_required_count": 0,
                "routine_primary_debt_count": 0,
                "exception_count": 0,
                "auto_resolved_count": 0,
            },
        },
        "l3_generation": {
            "status": "ok",
            "generated_count": generated_count,
            "skipped_count": skipped_count,
            "already_exists_count": already_exists_count,
            "candidate_count": generated_count + skipped_count,
            "blocked_count": 0,
        },
        "nightly": {"status": status, "returncode": 0 if status == "pass" else 1},
        "prompt_hash_invariant": {"before": "abc", "after": "abc", "unchanged": True},
    }


class DogfoodMaturityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_receipts(self, receipts: list[dict]) -> None:
        gate_dir = maturity_gate_dir(self.root)
        gate_dir.mkdir(parents=True, exist_ok=True)
        for index, receipt in enumerate(receipts, start=1):
            path = gate_dir / f"run-20260513T00000{index}Z.json"
            _write_json(path, receipt)

    def test_parser_accepts_root_before_or_after_subcommand(self) -> None:
        parser = build_parser()

        before = parser.parse_args(["--root", str(self.root), "collect"])
        after = parser.parse_args(["collect", "--root", str(self.root)])
        days = parser.parse_args(["summarize", "--days", "3"])

        self.assertEqual(before.root, str(self.root))
        self.assertEqual(after.root, str(self.root))
        self.assertEqual(days.days, 3)

    def test_prepare_nightly_env_forces_all_auto_flags(self) -> None:
        prepared = prepare_nightly_env(
            self.root,
            compile_limit=0,
            env={
                "AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT": "0",
                "AIWIKI_NIGHTLY_AUTO_ADOPT_L1": "0",
                "AIWIKI_NIGHTLY_AUTO_ADOPT_L2": "0",
                "AIWIKI_NIGHTLY_AUTO_ADOPT_L3": "0",
                "AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS": "0",
            },
        )

        self.assertEqual(prepared["AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT"], "1")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_L1"], "1")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_L2"], "1")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_L3"], "1")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS"], "1")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_COMPILE_LIMIT"], "0")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_DETERMINISTIC_ONLY"], "0")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_REQUIRE_LLM"], "1")

    def test_prepare_nightly_env_allows_explicit_deterministic_debug_mode(self) -> None:
        prepared = prepare_nightly_env(self.root, deterministic_only=True)

        self.assertEqual(prepared["AIWIKI_NIGHTLY_DETERMINISTIC_ONLY"], "1")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_REQUIRE_LLM"], "0")

    def test_collect_metrics_reads_expected_indicators(self) -> None:
        ask_path = self.root / "prompts" / "ask.md"
        ask_path.parent.mkdir(parents=True, exist_ok=True)
        ask_path.write_text("# Ask\n", encoding="utf-8")
        _write_json(
            self.root / ".aiwiki" / "state" / "nightly-health.json",
            {
                "agent_loop": {
                    "status": "ok",
                    "dry_run": False,
                    "side_effects_allowed": True,
                }
            },
        )
        _write_json(
            self.root / ".aiwiki" / "state" / "l3-proposals.json",
            {
                "version": 1,
                "proposals": [
                    {"proposal_id": "p1", "state": "candidate", "created_at": "2026-05-13T00:00:00Z", "dedupe_key": "dup", "evidence_count": 1},
                    {"proposal_id": "p2", "state": "accepted", "created_at": "2026-05-13T00:00:01Z", "dedupe_key": "dup", "evidence_count": 5},
                    {"proposal_id": "p3", "state": "rejected", "created_at": "2026-05-13T00:00:02Z"},
                ],
            },
        )
        _write_jsonl(
            self.root / ".aiwiki" / "state" / "planner-log.jsonl",
            [
                {
                    "decision": "generate-proposal",
                    "mode": "execute",
                    "signal_id": "sig-1",
                    "trace_id": "trace-1",
                    "dedupe_key": "dedupe-1",
                    "decided_at": "2026-05-13T00:00:00Z",
                    "reason_codes": ["proposal_recommended"],
                },
                {
                    "decision": "generate-proposal",
                    "mode": "observe_only",
                    "signal_id": "sig-2",
                    "trace_id": "trace-2",
                    "dedupe_key": "dedupe-2",
                    "decided_at": "2026-05-13T00:01:00Z",
                    "reason_codes": ["proposal_recommended"],
                },
                {"decision": "noop", "mode": "observe_only"},
            ],
        )
        _write_jsonl(
            self.root / ".aiwiki" / "state" / "execution-receipts.jsonl",
            [
                {"subject_kind": "judgment_review", "subject_id": "jr-1", "operation": "apply", "target_file": "wiki/judgments/j1.md", "conclusion": "upheld", "confidence": "high"},
                {"subject_kind": "judgment_review", "subject_id": "jr-2", "operation": "apply", "target_file": "wiki/judgments/j2.md", "conclusion": "weakened", "confidence": "medium"},
                {"subject_kind": "l3_proposal", "subject_id": "other", "operation": "apply"},
                {"generated_by": "aiwiki-auto-resolve-actions", "action_id": "link-1", "operation": "apply", "note": "Auto-resolved accepted low-risk action via machine-memory:auto-resolution:v1."},
            ],
        )
        _write_json(
            self.root / ".aiwiki" / "state" / "machine-memory-actions.json",
            {
                "version": 1,
                "actions": [
                    {
                        "id": "bridge-1",
                        "kind": "monitor-bridge-concept",
                        "status": "deferred",
                        "active": True,
                        "human_required": "true",
                        "human_required_reason": "semantic_judgment_required",
                        "last_receipt_path": "output/control/execution-receipts/auto-resolution/bridge-1.json",
                    },
                    {"id": "link-1", "kind": "add-source-concept-link", "status": "resolved", "active": True},
                ],
            },
        )
        _write_json(
            self.root / "output" / "control" / "execution-receipts" / "auto-resolution" / "bridge-1.json",
            {
                "kind": "execution-receipt",
                "generated_by": "aiwiki-auto-resolve-actions",
                "operation": "escalate",
                "action_id": "bridge-1",
                "human_required": True,
                "human_required_reason": "semantic_judgment_required",
                "revert_supported": False,
            },
        )
        _write_json(
            self.root / ".aiwiki" / "state" / "nightly-health.json",
            {
                "agent_loop": {
                    "status": "ok",
                    "auto_adopt_judgments": {
                        "limit": 5,
                        "total_candidates": 4,
                        "reviewed": 2,
                        "failed": 1,
                        "exception_count": 2,
                        "exception_queue": [{"page": "wiki/judgments/j2.md", "reason": "weakened"}],
                        "items": [
                            {"review_id": "jr-1", "conclusion": "upheld", "confidence": "high"},
                            {"review_id": "jr-new", "conclusion": "refuted", "confidence": "low"},
                        ],
                    },
                }
            },
        )

        snapshot = collect_metrics(self.root, preview_limit=5)

        self.assertEqual(snapshot["nightly_agent_loop"]["status"], "ok")
        self.assertEqual(snapshot["l3_proposal_counts_by_state"]["candidate"], 1)
        self.assertEqual(snapshot["l3_proposal_counts_by_state"]["accepted"], 1)
        self.assertEqual(snapshot["l3_generation_preview_summary"]["candidate_count"], 2)
        self.assertEqual(snapshot["l3_generation_preview_summary"]["raw_candidate_count"], 2)
        self.assertEqual(snapshot["l3_generation_preview_summary"]["blocked_count"], 1)
        self.assertEqual(snapshot["l3_debt_report"]["preview_candidate_count"], 2)
        self.assertEqual(snapshot["l3_debt_report"]["preview_raw_candidate_count"], 2)
        self.assertEqual(snapshot["l3_debt_report"]["preview_eligible_count"], 1)
        self.assertEqual(snapshot["l3_debt_report"]["preview_not_eligible_count"], 1)
        self.assertEqual(snapshot["l3_debt_report"]["preview_blocker_counts"]["requires_execute_mode"], 1)
        self.assertEqual(snapshot["l3_debt_report"]["duplicate_existing_count"], 0)
        self.assertEqual(snapshot["l3_debt_report"]["low_evidence_candidate_count"], 1)
        self.assertEqual(snapshot["l3_debt_report"]["duplicate_state_count"], 1)
        self.assertEqual(snapshot["l3_debt_report"]["effective_attention_count"], 0)
        self.assertLessEqual(snapshot["l3_debt_report"]["dedupe_or_noise_ratio"], 1.0)
        self.assertEqual(snapshot["planner_log_counts"]["mode_counts"]["execute"], 1)
        self.assertEqual(snapshot["planner_log_counts"]["mode_counts"]["observe_only"], 2)
        self.assertEqual(snapshot["planner_log_counts"]["decision_counts"]["generate-proposal"], 2)
        self.assertEqual(snapshot["judgment_review_receipt_counts"]["total"], 2)
        self.assertEqual(snapshot["judgment_review_receipt_counts"]["unique_subject_ids"], 2)
        self.assertEqual(len(snapshot["judgment_review_receipt_counts"]["latest"]), 2)
        self.assertEqual(snapshot["judgment_lane_report"]["reviewed"], 2)
        self.assertEqual(snapshot["judgment_lane_report"]["failed"], 1)
        self.assertEqual(snapshot["judgment_lane_report"]["exception_count"], 2)
        self.assertEqual(snapshot["judgment_lane_report"]["failure_rate"], 0.25)
        self.assertEqual(snapshot["judgment_lane_report"]["exception_rate"], 0.5)
        self.assertEqual(snapshot["judgment_lane_report"]["confidence_counts"]["high"], 1)
        self.assertEqual(snapshot["judgment_lane_report"]["confidence_counts"]["low"], 1)
        self.assertEqual(snapshot["judgment_lane_report"]["conclusion_counts"]["upheld"], 1)
        self.assertEqual(snapshot["judgment_lane_report"]["conclusion_counts"]["weakened"], 1)
        self.assertEqual(snapshot["judgment_lane_report"]["conclusion_counts"]["refuted"], 1)
        self.assertEqual(snapshot["human_required_report"]["human_required_count"], 1)
        self.assertEqual(snapshot["human_required_report"]["routine_primary_debt_count"], 0)
        self.assertEqual(snapshot["human_required_report"]["primary_exception_counts"], {})
        self.assertEqual(snapshot["human_required_report"]["auto_resolved_count"], 1)
        self.assertEqual(snapshot["human_required_report"]["auto_resolution_report"]["auto_resolution_receipt_count"], 1)

    def test_collect_metrics_treats_existing_l3_issue_class_as_preview_noise(self) -> None:
        ask_path = self.root / "prompts" / "ask.md"
        ask_path.parent.mkdir(parents=True, exist_ok=True)
        ask_path.write_text("# Ask\n", encoding="utf-8")
        _write_json(
            self.root / ".aiwiki" / "state" / "l3-proposals.json",
            {
                "version": 1,
                "proposals": [
                    {
                        "proposal_id": "prop-covered-runtime-failure",
                        "kind": "prompt_proposal",
                        "target_file": "prompts/ask.md",
                        "state": "rejected",
                        "trigger": {"pattern": "contract_failure", "evidence_count": 3},
                    }
                ],
            },
        )
        _write_jsonl(
            self.root / ".aiwiki" / "state" / "planner-log.jsonl",
            [
                {
                    "decision": "generate-proposal",
                    "mode": "execute",
                    "signal_id": "sig-runtime-1",
                    "trace_id": "trace-a",
                    "dedupe_key": "runtime_failure:general:llm_receipt:a",
                    "decided_at": "2026-05-19T00:00:00Z",
                    "reason_codes": ["runtime_failure_observed", "proposal_recommended", "execute_mode_requested"],
                },
                {
                    "decision": "generate-proposal",
                    "mode": "execute",
                    "signal_id": "sig-runtime-2",
                    "trace_id": "trace-b",
                    "dedupe_key": "runtime_failure:general:llm_receipt:b",
                    "decided_at": "2026-05-19T00:01:00Z",
                    "reason_codes": ["runtime_failure_observed", "proposal_recommended", "execute_mode_requested"],
                },
            ],
        )

        snapshot = collect_metrics(self.root, preview_limit=1000)

        self.assertEqual(snapshot["l3_debt_report"]["preview_raw_candidate_count"], 2)
        self.assertEqual(snapshot["l3_debt_report"]["preview_candidate_count"], 1)
        self.assertEqual(snapshot["l3_debt_report"]["preview_eligible_count"], 1)
        self.assertEqual(snapshot["l3_debt_report"]["duplicate_existing_count"], 1)
        self.assertEqual(snapshot["l3_debt_report"]["effective_preview_candidate_count"], 0)
        self.assertEqual(
            snapshot["prompts_ask_sha256"],
            hashlib.sha256(ask_path.read_bytes()).hexdigest(),
        )
        self.assertIn("review_backlog_counts", snapshot)
        self.assertEqual(snapshot["knowledge_compounding_proof"]["status"], "not-yet")
        self.assertIn("trace_provenance_backed_compounding_sample", snapshot["knowledge_compounding_proof"]["missing_evidence"])

    def test_collect_metrics_reports_pass_for_receipt_backed_compounding_sample(self) -> None:
        ask_path = self.root / "prompts" / "ask.md"
        ask_path.parent.mkdir(parents=True, exist_ok=True)
        ask_path.write_text("# Ask\n", encoding="utf-8")
        _write_json(
            self.root / ".aiwiki" / "state" / "manifest.json",
            {"version": 1, "entries": [{"id": "src-1", "stored_path": "raw/src-1.md"}]},
        )
        (self.root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "sources" / "src-1.md").write_text(
            "---\nsource_url: file://raw/src-1.md\ncaptured_at: 2026-05-18T00:00:00Z\nderived_from:\n  - raw/src-1.md\n---\n# Source\n",
            encoding="utf-8",
        )
        output_path = self.root / "output" / "reports" / "r1.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "---\nderived_from:\n  - wiki/judgments/j1.md\ngenerated_at: 2026-05-18T00:00:00Z\n---\n# Report\n",
            encoding="utf-8",
        )
        _write_jsonl(
            self.root / ".aiwiki" / "state" / "execution-receipts.jsonl",
            [
                {
                    "subject_kind": "report",
                    "subject_id": "r1",
                    "operation": "file-back",
                    "target_file": "output/reports/r1.md",
                    "receipt_path": "output/control/execution-receipts/report-r1.json",
                    "applied_at": "2026-05-18T00:00:01Z",
                }
            ],
        )
        _write_json(
            self.root / "output" / "control" / "execution-receipts" / "report-r1.json",
            {
                "kind": "execution-receipt",
                "operation": "file-back",
                "subject_kind": "report",
                "target_file": "output/reports/r1.md",
                "receipt_path": "output/control/execution-receipts/report-r1.json",
            },
        )

        snapshot = collect_metrics(self.root, preview_limit=5)
        proof = snapshot["knowledge_compounding_proof"]

        self.assertEqual(proof["status"], "pass")
        self.assertEqual(proof["metrics"]["raw_to_wiki_count"]["value"], 1)
        self.assertEqual(proof["metrics"]["judgment_or_elixir_reuse_count"]["value"], 1)
        self.assertEqual(proof["metrics"]["output_file_back_rate"]["value"], 1.0)
        self.assertEqual(proof["metrics"]["receipt_backed_actions"]["value"], 1)
        self.assertEqual(proof["metrics"]["human_required_exception_count"]["value"], 0)
        self.assertEqual(proof["compounding_sample"]["artifact_path"], "output/reports/r1.md")
        self.assertEqual(proof["compounding_sample"]["reused_ref"], "wiki/judgments/j1.md")
        self.assertEqual(proof["compounding_sample"]["receipt_path"], "output/control/execution-receipts/report-r1.json")
        self.assertEqual(proof["missing_evidence"], [])

    def test_collect_metrics_reports_not_yet_without_traceable_compounding_sample(self) -> None:
        ask_path = self.root / "prompts" / "ask.md"
        ask_path.parent.mkdir(parents=True, exist_ok=True)
        ask_path.write_text("# Ask\n", encoding="utf-8")
        _write_json(
            self.root / ".aiwiki" / "state" / "manifest.json",
            {"version": 1, "entries": [{"id": "src-1", "stored_path": "raw/src-1.md"}]},
        )
        (self.root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "sources" / "src-1.md").write_text("# Source\n", encoding="utf-8")
        output_path = self.root / "output" / "reports" / "r1.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "---\nderived_from:\n  - wiki/judgments/j1.md\ngenerated_at: 2026-05-18T00:00:00Z\n---\n# Report\n",
            encoding="utf-8",
        )

        snapshot = collect_metrics(self.root, preview_limit=5)
        proof = snapshot["knowledge_compounding_proof"]

        self.assertEqual(proof["status"], "not-yet")
        self.assertIn("receipt_backed_actions", proof["missing_evidence"])
        self.assertIn("trace_provenance_backed_compounding_sample", proof["missing_evidence"])
        self.assertIsNone(proof["compounding_sample"])

    def test_collect_metrics_rejects_revert_receipt_as_compounding_sample(self) -> None:
        ask_path = self.root / "prompts" / "ask.md"
        ask_path.parent.mkdir(parents=True, exist_ok=True)
        ask_path.write_text("# Ask\n", encoding="utf-8")
        _write_json(
            self.root / ".aiwiki" / "state" / "manifest.json",
            {"version": 1, "entries": [{"id": "src-1", "stored_path": "raw/src-1.md"}]},
        )
        (self.root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "sources" / "src-1.md").write_text("# Source\n", encoding="utf-8")
        output_path = self.root / "output" / "reports" / "r1.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "---\nderived_from:\n  - wiki/judgments/j1.md\ngenerated_at: 2026-05-18T00:00:00Z\n---\n# Report\n",
            encoding="utf-8",
        )
        _write_jsonl(
            self.root / ".aiwiki" / "state" / "execution-receipts.jsonl",
            [
                {
                    "subject_kind": "report",
                    "subject_id": "r1",
                    "operation": "revert",
                    "target_file": "output/reports/r1.md",
                    "receipt_path": "output/control/execution-receipts/revert-r1.json",
                }
            ],
        )

        proof = collect_metrics(self.root, preview_limit=5)["knowledge_compounding_proof"]

        self.assertEqual(proof["status"], "not-yet")
        self.assertIn("trace_provenance_backed_compounding_sample", proof["missing_evidence"])
        self.assertIsNone(proof["compounding_sample"])

    def test_summarize_old_run_receipt_without_compounding_proof_reports_not_yet(self) -> None:
        receipt = _make_run_receipt(
            generated_at="2026-05-13T00:00:00Z",
            status="pass",
            before_backlog=10,
            after_backlog=9,
            before_candidate=3,
            after_candidate=2,
            before_judgment_receipts=0,
            after_judgment_receipts=1,
            already_exists_count=1,
        )
        del receipt["after"]["knowledge_compounding_proof"]

        summary = summarize_run_receipts([receipt], recent=1)

        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["missing_required_fields"], {})
        self.assertEqual(summary["knowledge_compounding_status"], "not-yet")
        self.assertEqual(summary["knowledge_compounding_missing_evidence"], ["knowledge_compounding_proof"])
        self.assertIsNone(summary["knowledge_compounding_sample"])

    def test_human_required_report_counts_primary_exceptions_without_routine_backlog(self) -> None:
        from scripts.dogfood_maturity_gate import _build_human_required_report

        report = _build_human_required_report(
            self.root,
            {
                "pending_judgments": 2,
                "escalated_actions": 1,
                "overdue_actions": 5,
                "ready_actions": 4,
                "overdue_reviews": 3,
            },
        )

        self.assertEqual(report["primary_exception_count"], 3)
        self.assertEqual(report["primary_exception_counts"], {"escalated_actions": 1, "pending_judgments": 2})
        self.assertEqual(report["routine_primary_debt_count"], 0)
        self.assertEqual(report["routine_primary_debt_counts"], {})

    def test_human_required_report_flags_routine_bucket_policy_drift(self) -> None:
        from aiwiki import today_feed
        from scripts.dogfood_maturity_gate import _build_human_required_report

        today_feed._PRIMARY_REVIEW_BUCKETS.add("overdue_actions")
        try:
            report = _build_human_required_report(
                self.root,
                {
                    "pending_judgments": 2,
                    "overdue_actions": 5,
                },
            )
        finally:
            today_feed._PRIMARY_REVIEW_BUCKETS.discard("overdue_actions")

        self.assertEqual(report["primary_exception_count"], 2)
        self.assertEqual(report["primary_exception_counts"], {"pending_judgments": 2})
        self.assertEqual(report["routine_primary_debt_count"], 5)
        self.assertEqual(report["routine_primary_debt_counts"], {"overdue_actions": 5})

    def test_summarize_warns_when_receipts_are_insufficient(self) -> None:
        self._write_receipts(
            [
                _make_run_receipt(
                    generated_at="2026-05-13T00:00:00Z",
                    status="pass",
                    before_backlog=10,
                    after_backlog=9,
                    before_candidate=3,
                    after_candidate=2,
                    before_judgment_receipts=0,
                    after_judgment_receipts=1,
                    skipped_count=1,
                    already_exists_count=1,
                ),
                _make_run_receipt(
                    generated_at="2026-05-14T00:00:00Z",
                    status="pass",
                    before_backlog=9,
                    after_backlog=8,
                    before_candidate=2,
                    after_candidate=1,
                    before_judgment_receipts=1,
                    after_judgment_receipts=2,
                    skipped_count=1,
                    already_exists_count=1,
                ),
            ]
        )

        summary = summarize_recent_run_receipts(self.root, recent=3)

        self.assertEqual(summary["status"], "warn")
        self.assertEqual(summary["receipt_count"], 2)

    def test_summarize_passes_on_three_receipts_with_stable_trend(self) -> None:
        self._write_receipts(
            [
                _make_run_receipt(
                    generated_at="2026-05-13T00:00:00Z",
                    status="pass",
                    before_backlog=10,
                    after_backlog=9,
                    before_candidate=3,
                    after_candidate=3,
                    before_judgment_receipts=0,
                    after_judgment_receipts=1,
                    generated_count=1,
                    skipped_count=1,
                    already_exists_count=0,
                ),
                _make_run_receipt(
                    generated_at="2026-05-14T00:00:00Z",
                    status="pass",
                    before_backlog=9,
                    after_backlog=8,
                    before_candidate=3,
                    after_candidate=2,
                    before_judgment_receipts=1,
                    after_judgment_receipts=2,
                    generated_count=0,
                    skipped_count=1,
                    already_exists_count=1,
                ),
                _make_run_receipt(
                    generated_at="2026-05-15T00:00:00Z",
                    status="pass",
                    before_backlog=8,
                    after_backlog=7,
                    before_candidate=2,
                    after_candidate=1,
                    before_judgment_receipts=2,
                    after_judgment_receipts=3,
                    generated_count=0,
                    skipped_count=2,
                    already_exists_count=2,
                ),
            ]
        )

        summary = summarize_recent_run_receipts(self.root, recent=3)

        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["backlog_total_delta"], -3)
        self.assertEqual(summary["l3_candidate_delta"], -2)
        self.assertEqual(summary["l3_generated_total"], 1)
        self.assertEqual(summary["l3_already_exists_total"], 3)
        self.assertEqual(summary["l3_effective_candidate_count"], 0)
        self.assertEqual(summary["l3_dedupe_or_noise_ratio"], 0.5)
        self.assertEqual(summary["judgment_review_failure_rate"], 0.0)
        self.assertEqual(summary["judgment_review_exception_rate"], 0.25)
        self.assertEqual(summary["judgment_review_processed_delta"], 3)
        self.assertTrue(summary["consecutive_days"])
        self.assertEqual(summary["operational_maturity"]["status"], "not-yet")
        self.assertFalse(summary["operational_maturity"]["human_only_exceptions"])
        self.assertIn("judgment_exception_rate", summary["operational_maturity"]["budget_violations"])
        self.assertEqual(summary["operational_maturity"]["trend_windows"]["3"]["receipt_count"], 3)

    def test_operational_maturity_passes_when_three_day_budget_is_met(self) -> None:
        receipts = [
            _make_run_receipt(
                generated_at="2026-05-13T00:00:00Z",
                status="pass",
                before_backlog=10,
                after_backlog=9,
                before_candidate=2,
                after_candidate=1,
                before_judgment_receipts=0,
                after_judgment_receipts=1,
                already_exists_count=1,
            ),
            _make_run_receipt(
                generated_at="2026-05-14T00:00:00Z",
                status="pass",
                before_backlog=9,
                after_backlog=8,
                before_candidate=1,
                after_candidate=1,
                before_judgment_receipts=1,
                after_judgment_receipts=2,
                already_exists_count=1,
            ),
            _make_run_receipt(
                generated_at="2026-05-15T00:00:00Z",
                status="pass",
                before_backlog=8,
                after_backlog=7,
                before_candidate=1,
                after_candidate=0,
                before_judgment_receipts=2,
                after_judgment_receipts=3,
                already_exists_count=1,
            ),
        ]
        for receipt in receipts:
            receipt["after"]["judgment_lane_report"]["exception_rate"] = 0.0
        self._write_receipts(receipts)

        summary = summarize_recent_run_receipts(self.root, recent=3)

        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["operational_maturity"]["status"], "pass")
        self.assertTrue(summary["operational_maturity"]["human_only_exceptions"])
        self.assertEqual(summary["operational_maturity"]["budget_violations"], [])

    def test_operational_maturity_passes_when_budget_is_clean_even_if_trend_summary_warns(self) -> None:
        receipts = [
            _make_run_receipt(
                generated_at="2026-05-13T00:00:00Z",
                status="pass",
                before_backlog=10,
                after_backlog=12,
                before_candidate=0,
                after_candidate=0,
                before_judgment_receipts=1,
                after_judgment_receipts=1,
                already_exists_count=1,
            ),
            _make_run_receipt(
                generated_at="2026-05-14T00:00:00Z",
                status="pass",
                before_backlog=12,
                after_backlog=14,
                before_candidate=0,
                after_candidate=0,
                before_judgment_receipts=1,
                after_judgment_receipts=1,
                already_exists_count=1,
            ),
            _make_run_receipt(
                generated_at="2026-05-15T00:00:00Z",
                status="pass",
                before_backlog=14,
                after_backlog=16,
                before_candidate=0,
                after_candidate=0,
                before_judgment_receipts=1,
                after_judgment_receipts=1,
                already_exists_count=1,
            ),
        ]
        for receipt in receipts:
            receipt["after"]["judgment_lane_report"]["exception_rate"] = 0.0
        self._write_receipts(receipts)

        summary = summarize_recent_run_receipts(self.root, recent=3)

        self.assertEqual(summary["status"], "warn")
        self.assertEqual(summary["operational_maturity"]["status"], "pass")
        self.assertEqual(summary["operational_maturity"]["budget_violations"], [])
        self.assertTrue(summary["operational_maturity"]["receipt_integrity"]["consecutive_days"])

    def test_operational_maturity_flags_routine_primary_debt(self) -> None:
        receipts = [
            _make_run_receipt(
                generated_at="2026-05-13T00:00:00Z",
                status="pass",
                before_backlog=10,
                after_backlog=9,
                before_candidate=1,
                after_candidate=0,
                before_judgment_receipts=0,
                after_judgment_receipts=1,
                already_exists_count=1,
            ),
            _make_run_receipt(
                generated_at="2026-05-14T00:00:00Z",
                status="pass",
                before_backlog=9,
                after_backlog=8,
                before_candidate=0,
                after_candidate=0,
                before_judgment_receipts=1,
                after_judgment_receipts=2,
                already_exists_count=1,
            ),
            _make_run_receipt(
                generated_at="2026-05-15T00:00:00Z",
                status="pass",
                before_backlog=8,
                after_backlog=7,
                before_candidate=0,
                after_candidate=0,
                before_judgment_receipts=2,
                after_judgment_receipts=3,
                already_exists_count=1,
            ),
        ]
        for receipt in receipts:
            receipt["after"]["judgment_lane_report"]["exception_rate"] = 0.0
        receipts[-1]["after"]["human_required_report"]["routine_primary_debt_count"] = 1
        self._write_receipts(receipts)

        summary = summarize_recent_run_receipts(self.root, recent=3)

        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["routine_primary_debt_count"], 1)
        self.assertEqual(summary["operational_maturity"]["status"], "not-yet")
        self.assertIn("routine_primary_debt", summary["operational_maturity"]["budget_violations"])

    def test_summarize_warns_when_three_receipts_are_same_day(self) -> None:
        self._write_receipts(
            [
                _make_run_receipt(
                    generated_at="2026-05-13T00:00:00Z",
                    status="pass",
                    before_backlog=10,
                    after_backlog=9,
                    before_candidate=3,
                    after_candidate=2,
                    before_judgment_receipts=0,
                    after_judgment_receipts=1,
                    already_exists_count=1,
                ),
                _make_run_receipt(
                    generated_at="2026-05-13T01:00:00Z",
                    status="pass",
                    before_backlog=9,
                    after_backlog=8,
                    before_candidate=2,
                    after_candidate=1,
                    before_judgment_receipts=1,
                    after_judgment_receipts=2,
                    already_exists_count=1,
                ),
                _make_run_receipt(
                    generated_at="2026-05-13T02:00:00Z",
                    status="pass",
                    before_backlog=8,
                    after_backlog=7,
                    before_candidate=1,
                    after_candidate=0,
                    before_judgment_receipts=2,
                    after_judgment_receipts=3,
                    already_exists_count=1,
                ),
            ]
        )

        summary = summarize_recent_run_receipts(self.root, recent=3)

        self.assertEqual(summary["status"], "warn")
        self.assertFalse(summary["consecutive_days"])
        self.assertEqual(summary["operational_maturity"]["status"], "not-yet")

    def test_summarize_warns_without_judgment_review_progress(self) -> None:
        self._write_receipts(
            [
                _make_run_receipt(
                    generated_at="2026-05-13T00:00:00Z",
                    status="pass",
                    before_backlog=10,
                    after_backlog=9,
                    before_candidate=3,
                    after_candidate=2,
                    before_judgment_receipts=0,
                    after_judgment_receipts=0,
                    already_exists_count=1,
                ),
                _make_run_receipt(
                    generated_at="2026-05-14T00:00:00Z",
                    status="pass",
                    before_backlog=9,
                    after_backlog=8,
                    before_candidate=2,
                    after_candidate=1,
                    before_judgment_receipts=0,
                    after_judgment_receipts=0,
                    already_exists_count=1,
                ),
                _make_run_receipt(
                    generated_at="2026-05-15T00:00:00Z",
                    status="pass",
                    before_backlog=8,
                    after_backlog=7,
                    before_candidate=1,
                    after_candidate=0,
                    before_judgment_receipts=0,
                    after_judgment_receipts=0,
                    already_exists_count=1,
                ),
            ]
        )

        summary = summarize_recent_run_receipts(self.root, recent=3)

        self.assertEqual(summary["status"], "warn")
        self.assertFalse(summary["semantic_path_observed"])

    def test_summarize_fails_when_required_fields_are_missing(self) -> None:
        receipt = _make_run_receipt(
            generated_at="2026-05-13T00:00:00Z",
            status="pass",
            before_backlog=10,
            after_backlog=9,
            before_candidate=3,
            after_candidate=2,
            before_judgment_receipts=0,
            after_judgment_receipts=1,
            already_exists_count=1,
        )
        del receipt["after"]["prompts_ask_sha256"]
        self._write_receipts([receipt])

        summary = summarize_recent_run_receipts(self.root, recent=1)

        self.assertEqual(summary["status"], "fail")
        self.assertTrue(summary["missing_required_fields"])

    def test_summarize_fails_when_prompt_hash_changes(self) -> None:
        receipt = _make_run_receipt(
            generated_at="2026-05-13T00:00:00Z",
            status="pass",
            before_backlog=10,
            after_backlog=9,
            before_candidate=3,
            after_candidate=2,
            before_judgment_receipts=0,
            after_judgment_receipts=1,
            already_exists_count=1,
        )
        receipt["after"]["prompts_ask_sha256"] = "changed"
        receipt["prompt_hash_invariant"] = {"before": "abc", "after": "changed", "unchanged": False}
        self._write_receipts([receipt])

        summary = summarize_recent_run_receipts(self.root, recent=1)

        self.assertEqual(summary["status"], "fail")
        self.assertEqual(summary["prompt_hash_changed_runs"], [receipt["receipt_path"]])

    def test_summarize_fails_when_receipt_is_deterministic_only(self) -> None:
        receipt = _make_run_receipt(
            generated_at="2026-05-13T00:00:00Z",
            status="pass",
            before_backlog=10,
            after_backlog=9,
            before_candidate=3,
            after_candidate=2,
            before_judgment_receipts=0,
            after_judgment_receipts=1,
            already_exists_count=1,
        )
        receipt["settings"] = {"deterministic_only": True}
        receipt["nightly"] = {"status": "pass", "returncode": 0, "deterministic_only": True}
        self._write_receipts([receipt])

        summary = summarize_recent_run_receipts(self.root, recent=1)

        self.assertEqual(summary["status"], "fail")
        self.assertEqual(summary["deterministic_only_runs"], [receipt["receipt_path"]])
        self.assertEqual(
            summary["operational_maturity"]["receipt_integrity"]["deterministic_only_runs"],
            [receipt["receipt_path"]],
        )

    def test_summarize_days_uses_latest_receipt_per_calendar_day(self) -> None:
        receipts = [
            _make_run_receipt(
                generated_at="2026-05-13T00:00:00Z",
                status="pass",
                before_backlog=10,
                after_backlog=9,
                before_candidate=3,
                after_candidate=2,
                before_judgment_receipts=0,
                after_judgment_receipts=1,
                already_exists_count=1,
            ),
            _make_run_receipt(
                generated_at="2026-05-14T00:00:00Z",
                status="pass",
                before_backlog=9,
                after_backlog=8,
                before_candidate=2,
                after_candidate=1,
                before_judgment_receipts=1,
                after_judgment_receipts=2,
                already_exists_count=1,
            ),
            _make_run_receipt(
                generated_at="2026-05-15T00:00:00Z",
                status="pass",
                before_backlog=8,
                after_backlog=7,
                before_candidate=1,
                after_candidate=1,
                before_judgment_receipts=2,
                after_judgment_receipts=2,
                already_exists_count=1,
            ),
            _make_run_receipt(
                generated_at="2026-05-15T01:00:00Z",
                status="pass",
                before_backlog=7,
                after_backlog=6,
                before_candidate=1,
                after_candidate=0,
                before_judgment_receipts=2,
                after_judgment_receipts=3,
                already_exists_count=1,
            ),
        ]
        self._write_receipts(receipts)

        by_recent = summarize_recent_run_receipts(self.root, recent=3)
        by_days = summarize_recent_run_receipts(self.root, recent=3, by_days=True)

        self.assertEqual(by_recent["status"], "warn")
        self.assertFalse(by_recent["consecutive_days"])
        self.assertEqual(by_days["status"], "pass")
        self.assertEqual(by_days["days"], ["2026-05-13", "2026-05-14", "2026-05-15"])
        self.assertEqual(by_days["judgment_review_processed_delta"], 3)
        self.assertEqual(by_days["backlog_total_delta"], -4)

    def test_summarize_days_uses_full_history_for_operational_trend_windows(self) -> None:
        receipts = []
        for day in range(8):
            receipts.append(
                _make_run_receipt(
                    generated_at=f"2026-05-{13 + day:02d}T00:00:00Z",
                    status="pass",
                    before_backlog=20 - day,
                    after_backlog=19 - day,
                    before_candidate=10 - day,
                    after_candidate=9 - day,
                    before_judgment_receipts=day,
                    after_judgment_receipts=day + 1,
                    already_exists_count=1,
                )
            )
        self._write_receipts(receipts)

        summary = summarize_recent_run_receipts(self.root, recent=3, by_days=True)

        self.assertEqual(summary["receipt_count"], 3)
        self.assertEqual(summary["days"], ["2026-05-18", "2026-05-19", "2026-05-20"])
        self.assertEqual(summary["operational_maturity"]["trend_windows"]["3"]["receipt_count"], 3)
        self.assertEqual(summary["operational_maturity"]["trend_windows"]["7"]["receipt_count"], 7)
        self.assertEqual(summary["operational_maturity"]["trend_windows"]["14"]["receipt_count"], 8)

    def test_summarize_run_receipts_direct_keeps_receipt_order_contract(self) -> None:
        receipts = [
            _make_run_receipt(
                generated_at="2026-05-13T00:00:00Z",
                status="pass",
                before_backlog=3,
                after_backlog=2,
                before_candidate=1,
                after_candidate=0,
                before_judgment_receipts=0,
                after_judgment_receipts=1,
                already_exists_count=1,
            )
        ]

        summary = summarize_run_receipts(receipts, recent=1)

        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["knowledge_compounding_status"], "pass")
        self.assertEqual(summary["knowledge_compounding_missing_evidence"], [])
        self.assertEqual(summary["knowledge_compounding_sample"]["artifact_path"], "output/reports/r1.md")

    def test_summarize_fails_when_any_receipt_failed(self) -> None:
        self._write_receipts(
            [
                _make_run_receipt(
                    generated_at="2026-05-13T00:00:00Z",
                    status="pass",
                    before_backlog=10,
                    after_backlog=9,
                    before_candidate=3,
                    after_candidate=2,
                    before_judgment_receipts=0,
                    after_judgment_receipts=1,
                    skipped_count=1,
                    already_exists_count=1,
                ),
                _make_run_receipt(
                    generated_at="2026-05-14T00:00:00Z",
                    status="failed",
                    before_backlog=9,
                    after_backlog=9,
                    before_candidate=2,
                    after_candidate=2,
                    before_judgment_receipts=1,
                    after_judgment_receipts=1,
                ),
                _make_run_receipt(
                    generated_at="2026-05-15T00:00:00Z",
                    status="pass",
                    before_backlog=9,
                    after_backlog=8,
                    before_candidate=2,
                    after_candidate=1,
                    before_judgment_receipts=1,
                    after_judgment_receipts=2,
                    skipped_count=1,
                    already_exists_count=1,
                ),
            ]
        )

        summary = summarize_recent_run_receipts(self.root, recent=3)

        self.assertEqual(summary["status"], "fail")
        self.assertEqual(summary["status_counts"]["failed"], 1)
        self.assertEqual(len(summary["failed_runs"]), 1)


if __name__ == "__main__":
    unittest.main()
