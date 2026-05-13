"""Focused tests for nightly auto-adopt (L1 / L2 governance backlog)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.agent_loop import run_nightly_agent_loop
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import (
    execution_receipt_history_path,
    load_jsonl_documents_strict,
    load_runtime_history,
    save_json_document,
)
from aiwiki.execution.l3_proposals import L3PostApplyAuditError
from aiwiki.llm import CompletionResult
from aiwiki.runner.auto_adopt import _env_flag, auto_adopt_judgments, auto_adopt_l1, auto_adopt_l2, auto_adopt_l3


class StubClient:
    def __init__(self, response: str | None = None, *, fail: bool = False) -> None:
        self.response = response
        self.fail = fail

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt
        del user_prompt
        if self.fail:
            raise RuntimeError("llm boom")
        return CompletionResult(text=str(self.response or ""), response_id="stub", usage={})


def _memory_with_judgment_page(root: Path, page: Path) -> None:
    save_json_document(
        root / ".aiwiki" / "state" / "machine-memory.json",
        {
            "health": {
                "counter_evidence_scan": {
                    "generated_at": "2026-01-01T00:00:00Z",
                    "pages": [{"page_path": str(page.relative_to(root)), "page_title": "Judgment", "source_ids": ["s1"]}],
                }
            }
        },
    )


class AutoAdoptCriticalFixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_l3_auto_adopt_skips_low_evidence(self) -> None:
        with (
            patch("aiwiki.execution.l3_proposals.load_l3_proposal_state", return_value={"proposals": [{"proposal_id": "p1", "state": "candidate", "evidence_count": 1}]}),
            patch("aiwiki.execution.l3_proposals.apply_l3_proposal") as apply_mock,
            patch.dict(os.environ, {}, clear=True),
        ):
            result = auto_adopt_l3(self.root)
        self.assertEqual(result["items"][0]["status"], "skipped_low_evidence")
        self.assertEqual(result["items"][0]["threshold"], 5)
        apply_mock.assert_not_called()

    def test_l3_auto_adopt_threshold_from_env(self) -> None:
        with (
            patch("aiwiki.execution.l3_proposals.load_l3_proposal_state", return_value={"proposals": [{"proposal_id": "p1", "state": "candidate", "evidence_count": 3}]}),
            patch("aiwiki.execution.l3_proposals.apply_l3_proposal", return_value={"state": "accepted", "receipt_path": "r", "target_file": "t"}) as apply_mock,
            patch.dict(os.environ, {"AIWIKI_L3_AUTO_ADOPT_MIN_EVIDENCE": "3"}),
        ):
            result = auto_adopt_l3(self.root)
        apply_mock.assert_called_once()
        self.assertTrue(result["applied"])

    def test_l3_auto_adopt_default_threshold_boundary_passes(self) -> None:
        with (
            patch("aiwiki.execution.l3_proposals.load_l3_proposal_state", return_value={"proposals": [{"proposal_id": "p1", "state": "candidate", "evidence_count": 5}]}),
            patch("aiwiki.execution.l3_proposals.apply_l3_proposal", return_value={"state": "accepted", "receipt_path": "r", "target_file": "t"}) as apply_mock,
            patch.dict(os.environ, {}, clear=True),
        ):
            result = auto_adopt_l3(self.root)
        apply_mock.assert_called_once()
        self.assertTrue(result["applied"])

    def test_l3_auto_adopt_bad_env_falls_back_to_default_threshold(self) -> None:
        with (
            patch("aiwiki.execution.l3_proposals.load_l3_proposal_state", return_value={"proposals": [{"proposal_id": "p1", "state": "candidate", "evidence_count": 4}]}),
            patch("aiwiki.execution.l3_proposals.apply_l3_proposal") as apply_mock,
            patch.dict(os.environ, {"AIWIKI_L3_AUTO_ADOPT_MIN_EVIDENCE": "bad"}),
        ):
            result = auto_adopt_l3(self.root)
        apply_mock.assert_not_called()
        self.assertEqual(result["items"][0]["status"], "skipped_low_evidence")
        self.assertEqual(result["items"][0]["threshold"], 5)

    def test_l3_auto_adopt_non_integer_evidence_degrades_without_apply(self) -> None:
        with (
            patch("aiwiki.execution.l3_proposals.load_l3_proposal_state", return_value={"proposals": [{"proposal_id": "p1", "state": "candidate", "evidence_count": "many"}]}),
            patch("aiwiki.execution.l3_proposals.apply_l3_proposal") as apply_mock,
        ):
            result = auto_adopt_l3(self.root)
        apply_mock.assert_not_called()
        self.assertTrue(result["degraded"])
        self.assertEqual(result["items"][0]["status"], "failed_invalid_evidence")

    def test_l3_low_evidence_skip_writes_audit(self) -> None:
        with (
            patch("aiwiki.execution.l3_proposals.load_l3_proposal_state", return_value={"proposals": [{"proposal_id": "p1", "state": "candidate", "evidence_count": 1}]}),
            patch("aiwiki.execution.l3_proposals.apply_l3_proposal"),
        ):
            auto_adopt_l3(self.root)
        events = load_runtime_history(self.root)
        self.assertTrue(any(item.get("event_type") == "l3-proposal-skipped-low-evidence" for item in events))

    def test_judgment_review_skips_page_write_on_llm_error(self) -> None:
        page = self.root / "wiki" / "judgments" / "j1.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# J1\n", encoding="utf-8")
        before = page.read_text(encoding="utf-8")
        _memory_with_judgment_page(self.root, page)

        result = auto_adopt_judgments(self.root, StubClient(fail=True))

        self.assertEqual(page.read_text(encoding="utf-8"), before)
        self.assertEqual(result["items"][0]["status"], "llm_failed")
        self.assertEqual(result["failed"], 1)
        self.assertTrue(result["degraded"])
        self.assertTrue(any(item.get("event_type") == "judgment-review-failed" and item.get("failure_reason") == "llm_failed" for item in load_runtime_history(self.root)))

    def test_judgment_review_skips_page_write_on_unparsed_response(self) -> None:
        page = self.root / "wiki" / "judgments" / "j1.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# J1\n", encoding="utf-8")
        before = page.read_text(encoding="utf-8")
        _memory_with_judgment_page(self.root, page)

        result = auto_adopt_judgments(self.root, StubClient("not-json"))

        self.assertEqual(page.read_text(encoding="utf-8"), before)
        self.assertEqual(result["items"][0]["status"], "llm_unparsed")
        self.assertTrue(any(item.get("event_type") == "judgment-review-failed" and item.get("failure_reason") == "llm_unparsed" for item in load_runtime_history(self.root)))

    def test_judgment_review_writes_idempotent_id(self) -> None:
        page = self.root / "wiki" / "judgments" / "j1.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# J1\n", encoding="utf-8")
        _memory_with_judgment_page(self.root, page)
        response = json.dumps({"conclusion": "upheld", "confidence": "high", "key_findings": ["ok"], "recommendation": "keep"})

        first = auto_adopt_judgments(self.root, StubClient(response))
        after_first = page.read_text(encoding="utf-8")
        second = auto_adopt_judgments(self.root, StubClient(response))

        self.assertEqual(first["items"][0]["status"], "applied")
        self.assertEqual(second["items"][0]["status"], "skipped_idempotent")
        self.assertEqual(page.read_text(encoding="utf-8"), after_first)
        self.assertEqual(after_first.count("review_id="), 1)

    def test_judgment_review_audit_failure_keeps_page_and_degrades(self) -> None:
        page = self.root / "wiki" / "judgments" / "j1.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# J1\n", encoding="utf-8")
        before = page.read_text(encoding="utf-8")
        _memory_with_judgment_page(self.root, page)
        response = json.dumps({"conclusion": "upheld", "confidence": "high"})
        with patch("aiwiki.runner.auto_adopt.append_runtime_history", side_effect=RuntimeError("audit failed")):
            result = auto_adopt_judgments(self.root, StubClient(response))
        self.assertNotEqual(page.read_text(encoding="utf-8"), before)
        self.assertEqual(result["failed"], 1)
        self.assertTrue(result["degraded"])
        self.assertIn("audit step", result["items"][0]["error"])

    def test_judgment_review_writes_audit_event_with_sha256(self) -> None:
        page = self.root / "wiki" / "judgments" / "j1.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# J1\n", encoding="utf-8")
        _memory_with_judgment_page(self.root, page)
        response = json.dumps({"conclusion": "upheld", "confidence": "high"})
        with patch("aiwiki.runner.auto_adopt.append_runtime_history") as audit_mock:
            result = auto_adopt_judgments(self.root, StubClient(response))
        self.assertEqual(result["items"][0]["status"], "applied")
        payload = audit_mock.call_args.args[1]
        self.assertEqual(payload["event_type"], "judgment-review")
        self.assertIn("sha256", payload)
        self.assertIn("review_id", payload)

    def test_judgment_receipt_marks_revert_unsupported(self) -> None:
        page = self.root / "wiki" / "judgments" / "j1.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# J1\n", encoding="utf-8")
        _memory_with_judgment_page(self.root, page)
        response = json.dumps({"conclusion": "upheld", "confidence": "high"})

        result = auto_adopt_judgments(self.root, StubClient(response))

        self.assertEqual(result["items"][0]["status"], "applied")
        entries = load_jsonl_documents_strict(execution_receipt_history_path(self.root))
        receipt = entries[-1]
        self.assertIs(receipt["revert_supported"], False)
        self.assertEqual(receipt["revert_policy"], "manual_only")
        self.assertTrue(receipt["revert_note"])
        self.assertEqual(receipt["conclusion"], "upheld")
        self.assertEqual(receipt["confidence"], "high")
        self.assertEqual(receipt["scan_generated_at"], "2026-01-01T00:00:00Z")

    def test_judgment_review_surfaces_weakened_exception(self) -> None:
        page = self.root / "wiki" / "judgments" / "j1.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# J1\n", encoding="utf-8")
        _memory_with_judgment_page(self.root, page)
        response = json.dumps({"conclusion": "weakened", "confidence": "medium", "key_findings": ["risk"], "recommendation": "review"})

        result = auto_adopt_judgments(self.root, StubClient(response), limit=1)

        self.assertEqual(result["reviewed"], 1)
        self.assertEqual(result["exception_count"], 1)
        self.assertEqual(result["exception_queue"][0]["reason"], "weakened")
        self.assertEqual(result["conclusion_counts"]["weakened"], 1)

    def test_judgment_review_surfaces_refuted_exception(self) -> None:
        page = self.root / "wiki" / "judgments" / "j1.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# J1\n", encoding="utf-8")
        _memory_with_judgment_page(self.root, page)
        response = json.dumps({"conclusion": "refuted", "confidence": "high"})

        result = auto_adopt_judgments(self.root, StubClient(response), limit=1)

        self.assertEqual(result["exception_queue"][0]["reason"], "refuted")

    def test_judgment_review_surfaces_low_confidence_exception(self) -> None:
        page = self.root / "wiki" / "judgments" / "j1.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# J1\n", encoding="utf-8")
        _memory_with_judgment_page(self.root, page)
        response = json.dumps({"conclusion": "upheld", "confidence": "low"})

        result = auto_adopt_judgments(self.root, StubClient(response), limit=1)

        self.assertEqual(result["exception_queue"][0]["reason"], "low-confidence")
        self.assertEqual(result["confidence_counts"]["low"], 1)

    def test_judgment_review_idempotency_uses_receipt_history_not_page_text(self) -> None:
        page = self.root / "wiki" / "judgments" / "j1.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# J1\n", encoding="utf-8")
        _memory_with_judgment_page(self.root, page)
        response = json.dumps({"conclusion": "upheld", "confidence": "high"})
        first = auto_adopt_judgments(self.root, StubClient(response))
        receipt_history = execution_receipt_history_path(self.root)
        self.assertTrue(receipt_history.exists())
        text_without_review_id = page.read_text(encoding="utf-8").replace("review_id=", "review-id-removed=")
        page.write_text(text_without_review_id, encoding="utf-8")

        second = auto_adopt_judgments(self.root, StubClient(response))

        self.assertEqual(first["items"][0]["status"], "applied")
        self.assertEqual(second["items"][0]["status"], "skipped_idempotent")

    def test_judgment_review_missing_scan_generated_at_degrades_without_write(self) -> None:
        page = self.root / "wiki" / "judgments" / "j1.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# J1\n", encoding="utf-8")
        before = page.read_text(encoding="utf-8")
        save_json_document(
            self.root / ".aiwiki" / "state" / "machine-memory.json",
            {"health": {"counter_evidence_scan": {"pages": [{"page_path": str(page.relative_to(self.root)), "source_ids": ["s1"]}]}}},
        )

        result = auto_adopt_judgments(self.root, StubClient(json.dumps({"conclusion": "upheld", "confidence": "high"})))

        self.assertEqual(page.read_text(encoding="utf-8"), before)
        self.assertTrue(result["degraded"])
        self.assertEqual(result["items"][0]["status"], "missing_scan_generated_at")

    def test_judgment_review_corrupt_receipt_history_fail_closed(self) -> None:
        page = self.root / "wiki" / "judgments" / "j1.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# J1\n", encoding="utf-8")
        before = page.read_text(encoding="utf-8")
        _memory_with_judgment_page(self.root, page)
        history_path = execution_receipt_history_path(self.root)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text('{"subject_kind":"judgment_review","subject_id":"other"}\nnot-json{\n', encoding="utf-8")

        result = auto_adopt_judgments(self.root, StubClient(json.dumps({"conclusion": "upheld", "confidence": "high"})))

        self.assertEqual(page.read_text(encoding="utf-8"), before)
        self.assertEqual(result["items"][0]["status"], "receipt_history_corrupt")
        self.assertTrue(result["degraded"])
        self.assertTrue(any(item.get("event_type") == "judgment-review-failed" and "corrupt" in str(item.get("failure_reason")) for item in load_runtime_history(self.root)))

    def test_l3_audit_failed_counts_as_auto_reverted(self) -> None:
        error = L3PostApplyAuditError(
            "l3-proposal-apply-p1",
            "append_runtime_history",
            target_file="prompts/compile.md",
            before_hash="sha256:before",
            after_hash="sha256:after",
        )
        with (
            patch("aiwiki.execution.l3_proposals.load_l3_proposal_state", return_value={"proposals": [{"proposal_id": "p1", "state": "candidate", "evidence_count": 5}]}),
            patch("aiwiki.execution.l3_proposals.apply_l3_proposal", side_effect=error),
        ):
            result = auto_adopt_l3(self.root)
        self.assertTrue(result["applied"])
        self.assertTrue(result["degraded"])
        self.assertEqual(result["items"][0]["status"], "auto_reverted")
        self.assertEqual(result["items"][0]["revert_status"], "auto_reverted")

    def test_l1_auto_adopt_fail_fast_on_concept_backlog_error(self) -> None:
        review_ctrl = {"concept_backlog": [{"slug": "alpha"}], "revisit_concepts": [{"slug": "beta"}]}
        exec_ctrl = {"actions": []}
        with (
            patch("aiwiki.runner.auto_adopt._build_controls", return_value=(review_ctrl, exec_ctrl)),
            patch("aiwiki.runner.auto_adopt.review_concepts_batch", side_effect=RuntimeError("boom")) as review_mock,
            patch("aiwiki.runner.auto_adopt.review_machine_memory_actions_batch") as link_mock,
        ):
            result = auto_adopt_l1(self.root)
        self.assertTrue(result["degraded"])
        self.assertEqual(review_mock.call_count, 1)
        link_mock.assert_not_called()

    def test_l2_auto_adopt_fail_fast_on_accept_error(self) -> None:
        exec_ctrl = {"actions": [{"action_id": "s1", "kind": "split-overloaded-concept", "status": "proposed", "can_review": True}]}
        with (
            patch("aiwiki.runner.auto_adopt._build_controls", return_value=({}, exec_ctrl)),
            patch("aiwiki.runner.auto_adopt.review_machine_memory_actions_batch", side_effect=RuntimeError("boom")),
            patch("aiwiki.runner.auto_adopt.apply_machine_memory_actions_batch") as apply_mock,
        ):
            result = auto_adopt_l2(self.root)
        self.assertTrue(result["degraded"])
        apply_mock.assert_not_called()

    def test_l1_auto_adopt_reloads_exec_ctrl_after_accept(self) -> None:
        first_exec = {"actions": [{"action_id": "a1", "kind": "add-source-concept-link", "status": "proposed", "can_review": True, "can_apply": False}]}
        second_exec = {"actions": [{"action_id": "a1", "kind": "add-source-concept-link", "status": "accepted", "can_apply": True}]}
        with (
            patch("aiwiki.runner.auto_adopt._build_controls", side_effect=[({"concept_backlog": [], "revisit_concepts": []}, first_exec), ({}, second_exec)]),
            patch("aiwiki.runner.auto_adopt.review_machine_memory_actions_batch", return_value={"count": 1}),
            patch("aiwiki.runner.auto_adopt.apply_machine_memory_actions_batch", return_value={"applied_count": 1}) as apply_mock,
        ):
            auto_adopt_l1(self.root)
        apply_mock.assert_called_once()
        self.assertEqual(apply_mock.call_args.args[1], ["a1"])

    def test_nightly_status_degraded_when_any_level_degraded(self) -> None:
        with (
            patch("aiwiki.agent_loop.collect_signals", return_value={"status": "ok"}),
            patch("aiwiki.agent_loop.write_planner_log", return_value={"status": "ok"}),
            patch("aiwiki.agent_loop._build_auto_preview", return_value={"status": "preview"}),
            patch("aiwiki.runner.auto_adopt.auto_adopt_l1", return_value={"level": "L1", "applied": False, "degraded": True}),
        ):
            result = run_nightly_agent_loop(self.root, auto_adopt_l1=True)
        self.assertEqual(result["status"], "degraded")

    def test_nightly_status_degraded_when_l3_apply_fails(self) -> None:
        with (
            patch("aiwiki.agent_loop.collect_signals", return_value={"status": "ok"}),
            patch("aiwiki.agent_loop.write_planner_log", return_value={"status": "ok"}),
            patch("aiwiki.agent_loop._build_auto_preview", return_value={"status": "preview"}),
            patch("aiwiki.execution.l3_proposals.load_l3_proposal_state", return_value={"proposals": [{"proposal_id": "p1", "state": "candidate", "evidence_count": 5}]}),
            patch("aiwiki.execution.l3_proposals.apply_l3_proposal", side_effect=RuntimeError("apply failed")),
        ):
            result = run_nightly_agent_loop(self.root, auto_adopt_l3=True)
        self.assertEqual(result["status"], "degraded")
        self.assertTrue(result["auto_adopt_l3"]["degraded"])


class AutoAdoptEnvFlagTests(unittest.TestCase):
    def test_env_flag_true_values(self) -> None:
        for value in ("1", "true", "yes", "on", "TRUE", "Yes"):
            with patch.dict(os.environ, {"AIWIKI_TEST_FLAG": value}):
                self.assertTrue(_env_flag("AIWIKI_TEST_FLAG"), f"env_flag returned False for {value!r}")

    def test_env_flag_false_values(self) -> None:
        for value in ("0", "false", "no", "", "off"):
            with patch.dict(os.environ, {"AIWIKI_TEST_FLAG": value}):
                self.assertFalse(_env_flag("AIWIKI_TEST_FLAG"), f"env_flag returned True for {value!r}")

    def test_env_flag_missing_defaults_to_false(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(_env_flag("AIWIKI_NONEXISTENT_KEY"))
