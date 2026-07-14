from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.app_protocol import ensure_layout, save_manifest
from aiwiki.app_state import save_concept_rewrite_state
from scripts.dogfood_maturity_gate import (
    RUN_RECEIPT_KIND,
    _build_agentic_autonomy_report,
    _build_debt_autopilot_report,
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
            "elixir_quality_proof": {
                "kind": "elixir-quality-proof-report",
                "version": 1,
                "status": "pass",
                "verdict": "pass",
                "reason": "fixture elixir quality proof observed",
                "metrics": {
                    "settled_elixir_count": {"value": 1},
                    "elixir_output_reuse_count": {"value": 1},
                    "elixir_reuse_metric_count": {"value": 0},
                    "receipt_backed_actions": {"value": 1},
                    "failed_elixir_receipt_count": {"value": 0},
                    "elixir_revert_or_demotion_count": {"value": 0},
                },
                "compounding_sample": {
                    "artifact_path": "output/reports/r1.md",
                    "reused_ref": "wiki/elixirs/e1.md",
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
            "agentic_autonomy_report": {
                "version": 1,
                "status": "pass",
                "violations": [],
                "llm_governed_apply_count": 1,
                "non_core_human_required_count": 0,
                "core_proposal_count": 0,
                "core_auto_apply_count": 0,
                "degraded_agent_loop_count": 0,
                "degraded_signal_pipeline_count": 0,
                "auto_revert_count": 0,
            },
            "debt_autopilot_report": {
                "version": 1,
                "status": "digesting",
                "debt_detected_count": 3,
                "debt_auto_resolved_count": 1,
                "debt_remaining_count": 2,
                "llm_owned_non_core_pending_count": 2,
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

    def test_prepare_nightly_env_forces_agentic_non_core_flags(self) -> None:
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

        self.assertEqual(prepared["AIWIKI_AUTONOMY_PROFILE"], "agentic")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT"], "1")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_L1"], "1")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_L2"], "1")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_L3"], "1")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS"], "1")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_AUTO_APPLY_HEAVY_SEMANTIC"], "1")
        self.assertEqual(prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_CORE_L3"], "0")
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
        self.assertEqual(snapshot["elixir_quality_proof"]["status"], "not-yet")

    def test_agentic_autonomy_report_counts_judgment_human_required_from_nightly(self) -> None:
        report = _build_agentic_autonomy_report(
            self.root,
            {
                "agent_loop": {
                    "status": "ok",
                    "auto_adopt_judgments": {
                        "non_core_human_required_count": 1,
                        "items": [{"status": "human_required"}],
                    },
                }
            },
        )

        self.assertEqual(report["non_core_human_required_count"], 2)
        self.assertEqual(report["status"], "not-yet")
        self.assertIn("non_core_human_required", report["violations"])

    def test_debt_autopilot_report_collects_non_core_debt_and_last_run(self) -> None:
        save_manifest(self.root, {"version": 1, "entries": [{"id": "source-a", "title": "Source A"}]})
        (self.root / "wiki" / "sources" / "source-a.md").write_text(
            "# Source A\n\nPending LLM summary.\n",
            encoding="utf-8",
        )
        _write_json(
            self.root / ".aiwiki" / "state" / "machine-memory.json",
            {"health": {"concept_quality": {"weak_concepts": [{"slug": "agent"}]}}},
        )
        _write_json(
            self.root / ".aiwiki" / "state" / "nightly-health.json",
            {
                "agent_loop": {
                    "debt_autopilot": {
                        "debt_detected_count": 2,
                        "debt_auto_resolved_count": 1,
                        "debt_remaining_count": 1,
                    }
                },
            },
        )

        report = _build_debt_autopilot_report(self.root)

        self.assertEqual(report["status"], "digesting")
        self.assertEqual(report["debt_detected_count"], 2)
        self.assertEqual(report["debt_auto_resolved_count"], 1)
        self.assertEqual(report["debt_remaining_count"], 2)
        self.assertEqual(report["llm_owned_non_core_pending_count"], 2)
        self.assertEqual(report["autonomy_boundary"], "llm_owned_non_core")

    def test_debt_autopilot_report_uses_current_owner_state_over_stale_pipeline_inventory(self) -> None:
        save_manifest(self.root, {"version": 1, "entries": [{"id": "source-a", "title": "Source A"}]})
        (self.root / "wiki" / "sources" / "source-a.md").write_text(
            "# Source A\n\nPending LLM summary.\n",
            encoding="utf-8",
        )
        _write_json(
            self.root / ".aiwiki" / "state" / "nightly-health.json",
            {
                "repair_backlog": {
                    "pending_source_summaries": ["stale-source"],
                    "weak_concept_slugs": ["stale-concept"],
                },
                "agent_loop": {
                    "debt_autopilot": {
                        "debt_detected_count": 2,
                        "debt_auto_resolved_count": 1,
                        "debt_remaining_count": 2,
                    }
                },
                "signal_pipeline": {
                    "debt_inventory": {
                        "version": 1,
                        "debt_detected_count": 99,
                        "debt_remaining_count": 99,
                        "llm_owned_non_core_pending_count": 99,
                        "autonomy_boundary": "llm_owned_non_core",
                        "apply_strategy_counts": {},
                        "categories": {},
                    }
                },
            },
        )

        report = _build_debt_autopilot_report(self.root)

        self.assertEqual(report["status"], "digesting")
        self.assertEqual(report["debt_detected_count"], 1)
        self.assertEqual(report["debt_auto_resolved_count"], 1)
        self.assertEqual(report["debt_remaining_count"], 1)

    def test_debt_autopilot_report_fallback_ignores_stale_repair_backlog(self) -> None:
        _write_json(
            self.root / ".aiwiki" / "state" / "nightly-health.json",
            {
                "repair_backlog": {
                    "pending_source_summaries": ["stale-source"],
                    "weak_concept_slugs": ["stale-concept"],
                },
                "agent_loop": {"debt_autopilot": {"debt_auto_resolved_count": 0}},
            },
        )

        report = _build_debt_autopilot_report(self.root)

        self.assertEqual(report["status"], "clear")
        self.assertEqual(report["debt_detected_count"], 0)
        self.assertEqual(report["debt_remaining_count"], 0)

    def test_agentic_autonomy_report_requires_llm_governed_apply_evidence(self) -> None:
        report = _build_agentic_autonomy_report(
            self.root,
            {
                "agent_loop": {"status": "ok", "auto_adopt_judgments": {"items": []}},
                "signal_pipeline": {"status": "ok"},
            },
        )

        self.assertEqual(report["llm_governed_apply_count"], 0)
        self.assertEqual(report["status"], "not-yet")
        self.assertIn("missing_llm_governed_apply", report["violations"])

    def test_agentic_autonomy_report_counts_debt_autopilot_content_digestion(self) -> None:
        report = _build_agentic_autonomy_report(
            self.root,
            {
                "agent_loop": {
                    "status": "ok",
                    "auto_adopt_judgments": {"items": []},
                    "debt_autopilot": {
                        "content_digestion": {
                            "counts": {
                                "updated_source_pages": 2,
                                "updated_concept_pages": 0,
                                "applied_rewrite_proposals": 1,
                            }
                        }
                    },
                },
                "signal_pipeline": {"status": "ok"},
            },
        )

        self.assertEqual(report["llm_governed_apply_count"], 3)
        self.assertEqual(report["status"], "pass")
        self.assertNotIn("missing_llm_governed_apply", report["violations"])

    def test_agentic_autonomy_report_counts_verified_debt_autopilot_rewrite_state(self) -> None:
        save_concept_rewrite_state(
            self.root,
            {
                "version": 1,
                "proposals": [
                    {
                        "slug": "agent",
                        "status": "applied",
                        "verification_status": "passed",
                        "review_note": "debt-autopilot: apply current non-core concept rewrite",
                    },
                    {
                        "slug": "failed",
                        "status": "applied",
                        "verification_status": "failed",
                        "review_note": "debt-autopilot: apply current non-core concept rewrite",
                    },
                    {
                        "slug": "manual",
                        "status": "applied",
                        "verification_status": "passed",
                        "review_note": "manual apply",
                    },
                ],
            },
        )

        report = _build_agentic_autonomy_report(
            self.root,
            {
                "agent_loop": {"status": "ok", "auto_adopt_judgments": {"items": []}},
                "signal_pipeline": {"status": "ok"},
            },
        )

        self.assertEqual(report["llm_governed_apply_count"], 1)
        self.assertEqual(report["status"], "pass")
        self.assertNotIn("missing_llm_governed_apply", report["violations"])

    def test_agentic_autonomy_report_does_not_double_count_debt_autopilot_rewrite_evidence(self) -> None:
        save_concept_rewrite_state(
            self.root,
            {
                "version": 1,
                "proposals": [
                    {
                        "slug": "agent",
                        "status": "applied",
                        "verification_status": "passed",
                        "review_note": "debt-autopilot: apply current non-core concept rewrite",
                    }
                ],
            },
        )

        report = _build_agentic_autonomy_report(
            self.root,
            {
                "agent_loop": {
                    "status": "ok",
                    "auto_adopt_judgments": {"items": []},
                    "debt_autopilot": {
                        "content_digestion": {
                            "counts": {
                                "updated_source_pages": 0,
                                "updated_concept_pages": 0,
                                "applied_rewrite_proposals": 1,
                            }
                        }
                    },
                },
                "signal_pipeline": {"status": "ok"},
            },
        )

        self.assertEqual(report["llm_governed_apply_count"], 1)
        self.assertEqual(report["status"], "pass")

    def test_agentic_autonomy_report_falls_back_to_state_rewrite_count_when_nightly_has_only_source_updates(self) -> None:
        save_concept_rewrite_state(
            self.root,
            {
                "version": 1,
                "proposals": [
                    {
                        "slug": "agent",
                        "status": "applied",
                        "verification_status": "passed",
                        "review_note": "debt-autopilot: apply current non-core concept rewrite",
                    }
                ],
            },
        )

        report = _build_agentic_autonomy_report(
            self.root,
            {
                "agent_loop": {
                    "status": "ok",
                    "auto_adopt_judgments": {"items": []},
                    "debt_autopilot": {
                        "content_digestion": {
                            "counts": {
                                "updated_source_pages": 2,
                                "updated_concept_pages": 0,
                                "applied_rewrite_proposals": 0,
                            }
                        }
                    },
                },
                "signal_pipeline": {"status": "ok"},
            },
        )

        self.assertEqual(report["llm_governed_apply_count"], 3)
        self.assertEqual(report["status"], "pass")

    def test_agentic_autonomy_report_does_not_count_unbacked_judgment_review_as_llm_governed(self) -> None:
        _write_jsonl(
            self.root / ".aiwiki" / "state" / "execution-receipts.jsonl",
            [
                {
                    "kind": "execution-receipt",
                    "generated_by": "aiwiki-judgment-review",
                    "operation": "apply",
                    "subject_kind": "judgment_review",
                    "subject_id": "review-1",
                    "autonomy_domain": "non_core_semantic",
                    "validator_status": "passed",
                }
            ],
        )

        report = _build_agentic_autonomy_report(
            self.root,
            {
                "agent_loop": {"status": "ok", "auto_adopt_judgments": {"items": []}},
                "signal_pipeline": {"status": "ok"},
            },
        )

        self.assertEqual(report["llm_governed_apply_count"], 0)
        self.assertEqual(report["status"], "not-yet")
        self.assertIn("missing_llm_governed_apply", report["violations"])

    def test_agentic_autonomy_report_counts_judgment_review_with_matching_llm_receipt(self) -> None:
        _write_jsonl(
            self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl",
            [
                {
                    "event": "judgment-review-llm",
                    "review_id": "review-1",
                    "status": "success",
                    "delivery_mode": "llm-judgment-review",
                }
            ],
        )
        _write_jsonl(
            self.root / ".aiwiki" / "state" / "execution-receipts.jsonl",
            [
                {
                    "kind": "execution-receipt",
                    "generated_by": "aiwiki-judgment-review",
                    "operation": "apply",
                    "subject_kind": "judgment_review",
                    "subject_id": "review-1",
                    "autonomy_domain": "non_core_semantic",
                    "validator_status": "passed",
                    "judgment_llm_receipt_version": 1,
                    "llm_receipt_path": ".aiwiki/logs/llm-receipts.jsonl",
                }
            ],
        )

        report = _build_agentic_autonomy_report(
            self.root,
            {
                "agent_loop": {"status": "ok", "auto_adopt_judgments": {"items": []}},
                "signal_pipeline": {"status": "ok"},
            },
        )

        self.assertEqual(report["llm_governed_apply_count"], 1)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["violations"], [])

    def test_agentic_autonomy_report_respects_explicit_non_llm_governed_receipt(self) -> None:
        _write_jsonl(
            self.root / ".aiwiki" / "state" / "execution-receipts.jsonl",
            [
                {
                    "kind": "execution-receipt",
                    "generated_by": "aiwiki-judgment-review",
                    "operation": "apply",
                    "subject_kind": "judgment_review",
                    "subject_id": "review-1",
                    "autonomy_domain": "non_core_semantic",
                    "llm_governed": False,
                    "validator_status": "passed",
                }
            ],
        )

        report = _build_agentic_autonomy_report(
            self.root,
            {
                "agent_loop": {"status": "ok", "auto_adopt_judgments": {"items": []}},
                "signal_pipeline": {"status": "ok"},
            },
        )

        self.assertEqual(report["llm_governed_apply_count"], 0)
        self.assertEqual(report["status"], "not-yet")
        self.assertIn("missing_llm_governed_apply", report["violations"])

    def test_agentic_autonomy_report_counts_core_apply_without_human_accept_as_violation(self) -> None:
        _write_jsonl(
            self.root / ".aiwiki" / "state" / "execution-receipts.jsonl",
            [
                {
                    "kind": "execution-receipt",
                    "generated_by": "aiwiki-judgment-review",
                    "operation": "apply",
                    "subject_kind": "judgment_review",
                    "subject_id": "review-1",
                    "autonomy_domain": "non_core_semantic",
                    "llm_governed": True,
                    "validator_status": "passed",
                },
                {
                    "kind": "execution-receipt",
                    "generated_by": "aiwiki-l3-proposal",
                    "operation": "apply",
                    "subject_kind": "l3_proposal",
                    "subject_id": "core-1",
                    "autonomy_domain": "core",
                    "execution_strategy": "proposal_only",
                    "human_accept_required": False,
                    "validator_status": "passed",
                },
            ],
        )

        report = _build_agentic_autonomy_report(
            self.root,
            {
                "agent_loop": {"status": "ok", "auto_adopt_judgments": {"items": []}},
                "signal_pipeline": {"status": "ok"},
            },
        )

        self.assertEqual(report["llm_governed_apply_count"], 1)
        self.assertEqual(report["core_auto_apply_count"], 1)
        self.assertEqual(report["status"], "not-yet")
        self.assertIn("core_auto_apply", report["violations"])

    def test_agentic_autonomy_report_allows_human_accepted_core_apply(self) -> None:
        _write_jsonl(
            self.root / ".aiwiki" / "state" / "execution-receipts.jsonl",
            [
                {
                    "kind": "execution-receipt",
                    "generated_by": "aiwiki-judgment-review",
                    "operation": "apply",
                    "subject_kind": "judgment_review",
                    "subject_id": "review-1",
                    "autonomy_domain": "non_core_semantic",
                    "llm_governed": True,
                    "validator_status": "passed",
                },
                {
                    "kind": "execution-receipt",
                    "generated_by": "aiwiki-l3-proposal",
                    "operation": "apply",
                    "subject_kind": "l3_proposal",
                    "subject_id": "core-1",
                    "autonomy_domain": "core",
                    "execution_strategy": "proposal_only",
                    "human_accept_required": True,
                    "validator_status": "passed",
                },
            ],
        )

        report = _build_agentic_autonomy_report(
            self.root,
            {
                "agent_loop": {"status": "ok", "auto_adopt_judgments": {"items": []}},
                "signal_pipeline": {"status": "ok"},
            },
        )

        self.assertEqual(report["core_auto_apply_count"], 0)
        self.assertEqual(report["status"], "pass")

    def test_collect_metrics_explains_output_receipt_coverage_gaps_and_exemptions(self) -> None:
        runs_dir = self.root / "output" / "control" / "runs"
        for run_id in ("complete", "pending", "degraded"):
            run_notes = runs_dir / run_id / "thinking.md"
            run_notes.parent.mkdir(parents=True, exist_ok=True)
            run_notes.write_text("# Run Notes\n", encoding="utf-8")

        reports = self.root / "output" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "complete.md").write_text(
            "---\n"
            'kind: "output"\n'
            'generated_by: "aiwiki-run-ask-direct"\n'
            'created_at: "2026-05-18T00:00:00Z"\n'
            'delivery_mode: "llm-direct"\n'
            'run_notes_path: "output/control/runs/complete/thinking.md"\n'
            "---\n# Complete\n",
            encoding="utf-8",
        )
        (reports / "pending.md").write_text(
            "---\n"
            'kind: "output"\n'
            'generated_by: "aiwiki-ask"\n'
            'created_at: "2026-05-18T00:01:00Z"\n'
            'delivery_mode: "background-pending"\n'
            'background_status: "running"\n'
            'llm_status: "pending"\n'
            'run_notes_path: "output/control/runs/pending/thinking.md"\n'
            "---\n# Pending\n",
            encoding="utf-8",
        )
        (reports / "degraded.md").write_text(
            "---\n"
            'kind: "output"\n'
            'generated_by: "aiwiki-run-ask"\n'
            'created_at: "2026-05-18T00:02:00Z"\n'
            'delivery_mode: "llm-failed"\n'
            'llm_status: "timeout_or_unavailable"\n'
            'run_notes_path: "output/control/runs/degraded/thinking.md"\n'
            "---\n# Degraded\n",
            encoding="utf-8",
        )
        (reports / "missing.md").write_text(
            "---\n"
            'kind: "output"\n'
            'generated_by: "aiwiki-run-ask-direct"\n'
            'created_at: "2026-05-18T00:03:00Z"\n'
            'delivery_mode: "llm-direct"\n'
            "---\n# Missing\n",
            encoding="utf-8",
        )
        _write_jsonl(
            self.root / ".aiwiki" / "state" / "execution-receipts.jsonl",
            [
                {
                    "operation": "run-ask",
                    "status": "success",
                    "target_file": "output/reports/complete.md",
                    "receipt_path": "output/control/execution-receipts/complete.json",
                }
            ],
        )
        _write_jsonl(
            self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl",
            [
                {"event": "run-ask-direct", "status": "success", "target": "output/reports/complete.md"},
                {"event": "run-ask", "status": "failed", "target": "output/reports/degraded.md"},
            ],
        )

        coverage = collect_metrics(self.root, preview_limit=10)["receipt_coverage"]

        self.assertEqual(coverage["status"], "warn")
        self.assertEqual(coverage["outputs_checked"], 4)
        self.assertEqual(coverage["complete_count"], 3)
        self.assertEqual(coverage["missing_execution_receipt_count"], 1)
        self.assertEqual(coverage["missing_llm_receipt_count"], 1)
        self.assertEqual(coverage["missing_run_notes_count"], 1)
        self.assertGreaterEqual(coverage["exempt_count"], 2)
        samples_by_path = {sample["path"]: sample for sample in coverage["samples"]}
        self.assertIn("background_pending", samples_by_path["output/reports/pending.md"]["exemptions"])
        self.assertIn("failed_or_degraded_llm_artifact", samples_by_path["output/reports/degraded.md"]["exemptions"])
        self.assertEqual(
            samples_by_path["output/reports/missing.md"]["missing"],
            ["execution_receipt", "llm_receipt", "run_notes"],
        )
        small_preview = collect_metrics(self.root, preview_limit=1)["receipt_coverage"]
        self.assertNotEqual(small_preview["samples"][0]["path"], "output/reports/complete.md")

    def test_collect_metrics_does_not_treat_blank_output_metadata_as_deterministic_baseline(self) -> None:
        run_notes = self.root / "output" / "control" / "runs" / "blank" / "thinking.md"
        run_notes.parent.mkdir(parents=True, exist_ok=True)
        run_notes.write_text("# Run Notes\n", encoding="utf-8")
        report = self.root / "output" / "reports" / "blank.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "---\n"
            'kind: "output"\n'
            'created_at: "2026-05-18T00:00:00Z"\n'
            'run_notes_path: "output/control/runs/blank/thinking.md"\n'
            "---\n# Blank metadata output\n",
            encoding="utf-8",
        )

        coverage = collect_metrics(self.root, preview_limit=10)["receipt_coverage"]

        sample = coverage["samples"][0]
        self.assertEqual(sample["path"], "output/reports/blank.md")
        self.assertIn("execution_receipt", sample["missing"])
        self.assertIn("llm_receipt", sample["missing"])
        self.assertNotIn("deterministic_baseline_output", sample["exemptions"])

    def test_collect_metrics_does_not_exempt_llm_complete_artifact_with_aiwiki_ask_generator(self) -> None:
        run_notes = self.root / "output" / "control" / "runs" / "llm-complete" / "thinking.md"
        run_notes.parent.mkdir(parents=True, exist_ok=True)
        run_notes.write_text(
            "---\n"
            'kind: "run-progress-notes"\n'
            'status: "llm-complete"\n'
            "---\n# Run Notes\n",
            encoding="utf-8",
        )
        report = self.root / "output" / "reports" / "llm-complete-aiwiki-ask.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "---\n"
            'kind: "output"\n'
            'generated_by: "aiwiki-ask"\n'
            'created_at: "2026-05-18T00:00:00Z"\n'
            'run_notes_path: "output/control/runs/llm-complete/thinking.md"\n'
            "---\n# LLM-complete report\n",
            encoding="utf-8",
        )

        coverage = collect_metrics(self.root, preview_limit=10)["receipt_coverage"]

        sample = coverage["samples"][0]
        self.assertEqual(sample["path"], "output/reports/llm-complete-aiwiki-ask.md")
        self.assertIn("execution_receipt", sample["missing"])
        self.assertIn("llm_receipt", sample["missing"])
        self.assertNotIn("deterministic_baseline_output", sample["exemptions"])

    def test_collect_metrics_exempts_deterministic_ready_aiwiki_ask_output_from_llm_receipts(self) -> None:
        run_notes = self.root / "output" / "control" / "runs" / "deterministic-ready" / "thinking.md"
        run_notes.parent.mkdir(parents=True, exist_ok=True)
        run_notes.write_text(
            "---\n"
            'kind: "run-progress-notes"\n'
            'status: "deterministic-ready"\n'
            "---\n# Run Notes\n",
            encoding="utf-8",
        )
        report = self.root / "output" / "reports" / "deterministic-ready.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "---\n"
            'kind: "output"\n'
            'generated_by: "aiwiki-ask"\n'
            'created_at: "2026-05-18T00:00:00Z"\n'
            'run_notes_path: "output/control/runs/deterministic-ready/thinking.md"\n'
            "---\n# Deterministic report\n",
            encoding="utf-8",
        )

        coverage = collect_metrics(self.root, preview_limit=10)["receipt_coverage"]

        sample = coverage["samples"][0]
        self.assertEqual(sample["path"], "output/reports/deterministic-ready.md")
        self.assertEqual(sample["missing"], [])
        self.assertIn("deterministic_baseline_output", sample["exemptions"])

    def test_collect_metrics_exempts_legacy_direct_note_execution_receipts(self) -> None:
        run_notes = self.root / "output" / "control" / "runs" / "legacy-direct" / "thinking.md"
        run_notes.parent.mkdir(parents=True, exist_ok=True)
        run_notes.write_text(
            "---\n"
            'kind: "run-progress-notes"\n'
            'status: "llm-complete"\n'
            "---\n# Run Notes\n",
            encoding="utf-8",
        )
        report = self.root / "output" / "reports" / "legacy-direct.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "---\n"
            'kind: "output"\n'
            'generated_by: "aiwiki-run-ask-direct"\n'
            'created_at: "2026-05-21T00:00:00+00:00"\n'
            'delivery_mode: "llm-direct"\n'
            'run_notes_path: "output/control/runs/legacy-direct/thinking.md"\n'
            "---\n# Legacy direct note\n",
            encoding="utf-8",
        )
        _write_jsonl(
            self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl",
            [{"event": "run-ask-direct", "status": "success", "target": "output/reports/legacy-direct.md"}],
        )

        coverage = collect_metrics(self.root, preview_limit=10)["receipt_coverage"]

        self.assertEqual(coverage["status"], "pass")
        self.assertEqual(coverage["missing_execution_receipt_count"], 0)
        self.assertEqual(coverage["legacy_direct_note_exempt_count"], 1)
        sample = coverage["samples"][0]
        self.assertEqual(sample["path"], "output/reports/legacy-direct.md")
        self.assertEqual(sample["missing"], [])
        self.assertIn("legacy_direct_note_execution_receipt", sample["exemptions"])

    def test_collect_metrics_does_not_exempt_new_direct_note_missing_execution_receipt(self) -> None:
        run_notes = self.root / "output" / "control" / "runs" / "new-direct" / "thinking.md"
        run_notes.parent.mkdir(parents=True, exist_ok=True)
        run_notes.write_text("# Run Notes\n", encoding="utf-8")
        report = self.root / "output" / "reports" / "new-direct.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "---\n"
            'kind: "output"\n'
            'generated_by: "aiwiki-run-ask-direct"\n'
            'created_at: "2026-05-26T00:00:00+00:00"\n'
            'delivery_mode: "llm-direct"\n'
            'run_notes_path: "output/control/runs/new-direct/thinking.md"\n'
            "---\n# New direct note\n",
            encoding="utf-8",
        )
        _write_jsonl(
            self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl",
            [{"event": "run-ask-direct", "status": "success", "target": "output/reports/new-direct.md"}],
        )

        coverage = collect_metrics(self.root, preview_limit=10)["receipt_coverage"]

        self.assertEqual(coverage["status"], "warn")
        self.assertEqual(coverage["missing_execution_receipt_count"], 1)
        self.assertEqual(coverage["legacy_direct_note_exempt_count"], 0)
        sample = coverage["samples"][0]
        self.assertEqual(sample["path"], "output/reports/new-direct.md")
        self.assertEqual(sample["missing"], ["execution_receipt"])
        self.assertNotIn("legacy_direct_note_execution_receipt", sample["exemptions"])

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
        self.assertEqual(proof["elixir_compounding_proof"]["status"], "not-yet")
        self.assertEqual(snapshot["elixir_quality_proof"]["status"], "not-yet")
        self.assertIn(
            "trace_provenance_backed_elixir_compounding_sample",
            proof["elixir_compounding_proof"]["missing_evidence"],
        )
        self.assertEqual(proof["missing_evidence"], [])

    def test_collect_metrics_reports_elixir_specific_compounding_sample(self) -> None:
        ask_path = self.root / "prompts" / "ask.md"
        ask_path.parent.mkdir(parents=True, exist_ok=True)
        ask_path.write_text("# Ask\n", encoding="utf-8")
        _write_json(
            self.root / ".aiwiki" / "state" / "manifest.json",
            {"version": 1, "entries": [{"id": "src-1", "stored_path": "raw/src-1.md"}]},
        )
        (self.root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "sources" / "src-1.md").write_text("# Source\n", encoding="utf-8")
        (self.root / "wiki" / "elixirs").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "elixirs" / "e1.md").write_text(
            "---\nderived_from:\n  - wiki/judgments/j1.md\n---\n# Elixir\n",
            encoding="utf-8",
        )
        output_path = self.root / "output" / "reports" / "r1.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "---\nderived_from:\n  - wiki/elixirs/e1.md\ngenerated_at: 2026-05-18T00:00:00Z\n---\n# Report\n",
            encoding="utf-8",
        )
        _write_jsonl(
            self.root / ".aiwiki" / "state" / "execution-receipts.jsonl",
            [
                {
                    "subject_kind": "elixir_demotion",
                    "subject_id": "e-old",
                    "operation": "demote",
                    "target_file": "wiki/elixirs/e-old.md",
                    "applied_at": "2026-05-17T00:00:00Z",
                },
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

        snapshot = collect_metrics(self.root, preview_limit=5)
        proof = snapshot["knowledge_compounding_proof"]
        elixir_proof = proof["elixir_compounding_proof"]
        quality_proof = snapshot["elixir_quality_proof"]

        self.assertEqual(proof["status"], "pass")
        self.assertEqual(elixir_proof["status"], "pass")
        self.assertEqual(quality_proof["status"], "pass")
        self.assertEqual(elixir_proof["metrics"]["settled_elixir_count"]["value"], 1)
        self.assertEqual(elixir_proof["metrics"]["elixir_output_reuse_count"]["value"], 1)
        self.assertEqual(quality_proof["metrics"]["failed_elixir_receipt_count"]["value"], 0)
        self.assertEqual(quality_proof["metrics"]["elixir_revert_or_demotion_count"]["value"], 0)
        self.assertEqual(quality_proof["metrics"]["elixir_receipt_count"]["value"], 1)
        self.assertEqual(quality_proof["metrics"]["recent_elixir_receipt_count"]["value"], 0)
        self.assertEqual(elixir_proof["compounding_sample"]["artifact_path"], "output/reports/r1.md")
        self.assertEqual(elixir_proof["compounding_sample"]["reused_ref"], "wiki/elixirs/e1.md")
        self.assertEqual(quality_proof["compounding_sample"]["reused_ref"], "wiki/elixirs/e1.md")
        self.assertEqual(elixir_proof["missing_evidence"], [])
        self.assertEqual(quality_proof["missing_evidence"], [])

    def test_elixir_quality_rejects_settled_placeholder_body(self) -> None:
        ask_path = self.root / "prompts" / "ask.md"
        ask_path.parent.mkdir(parents=True, exist_ok=True)
        ask_path.write_text("# Ask\n", encoding="utf-8")
        _write_json(
            self.root / ".aiwiki" / "state" / "manifest.json",
            {"version": 1, "entries": [{"id": "src-1", "stored_path": "raw/src-1.md"}]},
        )
        (self.root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "sources" / "src-1.md").write_text("# Source\n", encoding="utf-8")
        (self.root / "wiki" / "elixirs").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "elixirs" / "e1.md").write_text(
            "---\nderived_from:\n  - wiki/judgments/j1.md\n---\n# Elixir\n\n## Thesis\n- pending refinement\n",
            encoding="utf-8",
        )
        output_path = self.root / "output" / "reports" / "r1.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "---\nderived_from:\n  - wiki/elixirs/e1.md\ngenerated_at: 2026-05-18T00:00:00Z\n---\n# Report\n",
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
        _write_json(self.root / "output" / "control" / "execution-receipts" / "report-r1.json", {"receipt_path": "output/control/execution-receipts/report-r1.json"})

        quality_proof = collect_metrics(self.root, preview_limit=5)["elixir_quality_proof"]

        self.assertEqual(quality_proof["status"], "not-yet")
        self.assertIn("settled_elixir_placeholder_body", quality_proof["missing_evidence"])
        self.assertEqual(quality_proof["metrics"]["settled_elixir_placeholder_count"]["value"], 1)

    def test_elixir_quality_flags_revert_after_compounding_sample(self) -> None:
        ask_path = self.root / "prompts" / "ask.md"
        ask_path.parent.mkdir(parents=True, exist_ok=True)
        ask_path.write_text("# Ask\n", encoding="utf-8")
        _write_json(
            self.root / ".aiwiki" / "state" / "manifest.json",
            {"version": 1, "entries": [{"id": "src-1", "stored_path": "raw/src-1.md"}]},
        )
        (self.root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "sources" / "src-1.md").write_text("# Source\n", encoding="utf-8")
        (self.root / "wiki" / "elixirs").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "elixirs" / "e1.md").write_text("# Elixir\n", encoding="utf-8")
        output_path = self.root / "output" / "reports" / "r1.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "---\nderived_from:\n  - wiki/elixirs/e1.md\ngenerated_at: 2026-05-18T00:00:00Z\n---\n# Report\n",
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
                },
                {
                    "subject_kind": "elixir_revert",
                    "subject_id": "e1",
                    "operation": "revert",
                    "target_file": "wiki/elixirs/e1.md",
                    "applied_at": "2026-05-18T00:00:02Z",
                },
            ],
        )

        quality_proof = collect_metrics(self.root, preview_limit=5)["elixir_quality_proof"]

        self.assertEqual(quality_proof["status"], "not-yet")
        self.assertIn("elixir_revert_or_demotion_receipts", quality_proof["missing_evidence"])

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

    def test_summary_passes_when_budget_is_clean_even_if_trend_summary_warns(self) -> None:
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

        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["trend_status"], "warn")
        self.assertEqual(summary["operational_maturity"]["status"], "pass")
        self.assertEqual(summary["operational_maturity"]["budget_violations"], [])
        self.assertTrue(summary["operational_maturity"]["receipt_integrity"]["consecutive_days"])

    def test_summary_does_not_pass_without_agentic_autonomy_proof(self) -> None:
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
            ),
        ]
        receipts[-1]["after"]["agentic_autonomy_report"] = {
            "version": 1,
            "status": "not-yet",
            "violations": ["missing_llm_governed_apply"],
            "llm_governed_apply_count": 0,
            "non_core_human_required_count": 0,
            "core_auto_apply_count": 0,
        }
        self._write_receipts(receipts)

        summary = summarize_recent_run_receipts(self.root, recent=3)

        self.assertEqual(summary["trend_status"], "pass")
        self.assertEqual(summary["agentic_autonomy_report"]["status"], "not-yet")
        self.assertEqual(summary["status"], "warn")

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
        self.assertEqual(summary["semantic_path_report"]["evidence"], "missing")

    def test_summarize_accepts_retained_semantic_path_without_new_review_delta(self) -> None:
        receipts = [
            _make_run_receipt(
                generated_at="2026-05-13T00:00:00Z",
                status="pass",
                before_backlog=10,
                after_backlog=9,
                before_candidate=3,
                after_candidate=2,
                before_judgment_receipts=2,
                after_judgment_receipts=2,
                already_exists_count=1,
            ),
            _make_run_receipt(
                generated_at="2026-05-14T00:00:00Z",
                status="pass",
                before_backlog=9,
                after_backlog=8,
                before_candidate=2,
                after_candidate=1,
                before_judgment_receipts=2,
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
                after_judgment_receipts=2,
                already_exists_count=1,
            ),
        ]
        for receipt in receipts:
            receipt["after"]["judgment_lane_report"]["exception_rate"] = 0.0
        self._write_receipts(receipts)

        summary = summarize_recent_run_receipts(self.root, recent=3)

        self.assertEqual(summary["status"], "pass")
        self.assertTrue(summary["semantic_path_observed"])
        self.assertEqual(summary["semantic_path_report"]["evidence"], "latest_state")
        self.assertEqual(summary["judgment_review_processed_delta"], 0)

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
        self.assertEqual(summary["elixir_quality_status"], "pass")
        self.assertEqual(summary["elixir_quality_missing_evidence"], [])

    def test_summarize_run_receipts_does_not_pass_without_elixir_quality_proof(self) -> None:
        receipt = _make_run_receipt(
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
        del receipt["after"]["elixir_quality_proof"]

        summary = summarize_run_receipts([receipt], recent=1)

        self.assertEqual(summary["status"], "warn")
        self.assertEqual(summary["elixir_quality_status"], "not-yet")
        self.assertIn("elixir_quality_proof", summary["elixir_quality_missing_evidence"])

    def test_summarize_strict_requires_current_day(self) -> None:
        receipt = _make_run_receipt(
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
        self._write_receipts([receipt])

        non_strict = summarize_recent_run_receipts(self.root, recent=1, expected_latest_day="2026-05-14")
        strict = summarize_recent_run_receipts(
            self.root,
            recent=1,
            require_current_day=True,
            expected_latest_day="2026-05-14",
        )

        self.assertEqual(non_strict["status"], "pass")
        self.assertEqual(strict["status"], "fail")
        self.assertEqual(strict["freshness_status"], "stale")
        self.assertEqual(strict["strict_failures"], ["latest_receipt_not_current_day"])

    def test_summarize_strict_fails_when_newer_snapshot_fails_budget(self) -> None:
        receipt = _make_run_receipt(
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
        self._write_receipts([receipt])
        snapshot = dict(receipt["after"])
        snapshot["judgment_lane_report"] = {
            "failure_rate": 0.0,
            "exception_rate": 0.0,
            "exception_queue": [],
        }
        snapshot["human_required_report"] = {
            "human_required_count": 0,
            "routine_primary_debt_count": 1,
            "exception_count": 0,
            "auto_resolved_count": 0,
        }
        _write_json(maturity_gate_dir(self.root) / "snapshot-20260513T000001Z.json", snapshot)

        summary = summarize_recent_run_receipts(
            self.root,
            recent=1,
            require_current_day=True,
            expected_latest_day="2026-05-13",
        )

        self.assertEqual(summary["status"], "fail")
        self.assertTrue(summary["snapshot_consistency"]["snapshot_newer_than_latest_run"])
        self.assertEqual(summary["snapshot_consistency"]["budget_violations"], ["routine_primary_debt"])
        self.assertEqual(summary["strict_failures"], ["latest_snapshot_newer_than_run_failed_budget"])

    def test_summarize_strict_allows_newer_snapshot_human_only_exceptions(self) -> None:
        receipt = _make_run_receipt(
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
        self._write_receipts([receipt])
        snapshot = dict(receipt["after"])
        snapshot["judgment_lane_report"] = {
            "failure_rate": 0.0,
            "exception_rate": 0.0,
            "exception_queue": [],
        }
        snapshot["human_required_report"] = {
            "human_required_count": 0,
            "routine_primary_debt_count": 0,
            "exception_count": 3,
            "auto_resolved_count": 0,
        }
        _write_json(maturity_gate_dir(self.root) / "snapshot-20260513T000001Z.json", snapshot)

        summary = summarize_recent_run_receipts(
            self.root,
            recent=1,
            require_current_day=True,
            expected_latest_day="2026-05-13",
        )

        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["snapshot_consistency"]["status"], "pass")
        self.assertEqual(summary["snapshot_consistency"]["budget_violations"], [])
        self.assertEqual(summary["strict_failures"], [])

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
