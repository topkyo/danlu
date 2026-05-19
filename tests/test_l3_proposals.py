from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_shell import build_shell_summary
from aiwiki.app_state import l3_proposal_state_path
from aiwiki.execution.l3_proposals import (
    _automatic_l3_prompt_content,
    apply_l3_proposal,
    create_l3_proposal,
    generate_l3_proposals_from_planner,
    list_l3_proposals,
    preview_l3_proposal_generation,
    reject_l3_proposal,
    revert_l3_proposal,
)


class L3ProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        ensure_layout(self.root)
        (self.root / "prompts").mkdir(parents=True, exist_ok=True)
        (self.root / "prompts" / "ask.md").write_text("Original ask prompt.\n", encoding="utf-8")
        (self.root / "schema" / "policies").mkdir(parents=True, exist_ok=True)
        (self.root / "schema" / "policies" / "aging.json").write_text('{"days": 30}\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _state_proposal(self, proposal_id: str) -> dict[str, object]:
        state = json.loads(l3_proposal_state_path(self.root).read_text(encoding="utf-8"))
        return next(item for item in state["proposals"] if item["proposal_id"] == proposal_id)

    def test_create_manual_prompt_proposal_writes_independent_proposal_plane_and_state(self) -> None:
        result = create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-ask-tighten",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
            rationale="Tighten ask behavior.",
            evidence_refs=["output/receipts/receipt-123.md"],
            signal_ids=["sig-20260424-abc123"],
        )

        self.assertEqual(result["state"], "candidate")
        proposal_path = self.root / str(result["proposal_path"])
        self.assertTrue(proposal_path.exists())
        page_text = proposal_path.read_text(encoding="utf-8")
        self.assertIn("kind: \"prompt_proposal\"", page_text)
        self.assertIn("Updated ask prompt.", page_text)
        listed = list_l3_proposals(self.root)
        self.assertEqual([item["proposal_id"] for item in listed], ["prop-ask-tighten"])
        stored = self._state_proposal("prop-ask-tighten")
        self.assertEqual(stored["target_file"], "prompts/ask.md")
        self.assertEqual(stored["state"], "candidate")

    def test_policy_proposal_allows_schema_policies_only(self) -> None:
        result = create_l3_proposal(
            self.root,
            kind="policy_proposal",
            proposal_id="prop-aging",
            target_file="schema/policies/aging.json",
            content='{"days": 45}\n',
        )
        self.assertEqual(result["target_file"], "schema/policies/aging.json")

        (self.root / "schema" / "protocols" / "general").mkdir(parents=True, exist_ok=True)
        (self.root / "schema" / "protocols" / "general" / "index.md").write_text("# General\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "schema/policies"):
            create_l3_proposal(
                self.root,
                kind="policy_proposal",
                proposal_id="prop-core",
                target_file="schema/protocols/general/index.md",
                content="# Changed\n",
            )

    def test_apply_requires_matching_before_hash_and_marks_stale_without_half_write(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-stale",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
        )
        (self.root / "prompts" / "ask.md").write_text("Human edited prompt.\n", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "before_hash mismatch"):
            apply_l3_proposal(self.root, "prop-stale")

        self.assertEqual((self.root / "prompts" / "ask.md").read_text(encoding="utf-8"), "Human edited prompt.\n")
        stored = self._state_proposal("prop-stale")
        self.assertEqual(stored["state"], "stale")
        self.assertEqual(stored["stale_reason"], "before_hash_mismatch")

    def test_reject_candidate_marks_state_without_touching_target_or_receipt_history(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-reject",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
        )

        result = reject_l3_proposal(self.root, "prop-reject", note="not useful")

        self.assertEqual(result["state"], "rejected")
        self.assertEqual((self.root / "prompts" / "ask.md").read_text(encoding="utf-8"), "Original ask prompt.\n")
        self.assertFalse((self.root / ".aiwiki" / "state" / "execution-receipts.jsonl").exists())
        stored = self._state_proposal("prop-reject")
        self.assertEqual(stored["state"], "rejected")
        self.assertEqual(stored["reject_note"], "not useful")
        page_text = (self.root / str(stored["proposal_path"])).read_text(encoding="utf-8")
        self.assertIn("state: \"rejected\"", page_text)

    def test_reject_requires_candidate_state(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-no-reject",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
        )
        apply_l3_proposal(self.root, "prop-no-reject")

        with self.assertRaisesRegex(RuntimeError, "Only candidate"):
            reject_l3_proposal(self.root, "prop-no-reject")

    def test_apply_and_clean_revert_write_receipts_and_audit_metadata(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-apply",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
        )

        applied = apply_l3_proposal(self.root, "prop-apply", note="accept")

        self.assertEqual((self.root / "prompts" / "ask.md").read_text(encoding="utf-8"), "Updated ask prompt.\n")
        receipt_path = self.root / str(applied["receipt_path"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["subject_kind"], "l3_proposal")
        self.assertEqual(receipt["operation"], "apply")
        self.assertTrue(receipt["revert_supported"])
        self.assertEqual(receipt["audit_stream"], "execution_receipts")
        self.assertEqual(receipt["audit_event"], "execution_receipt_history_append")
        self.assertEqual(receipt["audit_path"], ".aiwiki/state/execution-receipts.jsonl")
        self.assertEqual(applied["audit_path"], ".aiwiki/state/execution-receipts.jsonl")
        history = (self.root / ".aiwiki" / "state" / "execution-receipts.jsonl").read_text(encoding="utf-8")
        self.assertIn('"subject_kind": "l3_proposal"', history)

        reverted = revert_l3_proposal(self.root, str(applied["receipt_path"]), note="undo")

        self.assertEqual(reverted["state"], "reverted")
        self.assertEqual((self.root / "prompts" / "ask.md").read_text(encoding="utf-8"), "Original ask prompt.\n")
        stored = self._state_proposal("prop-apply")
        self.assertEqual(stored["state"], "reverted")
        revert_receipt = json.loads((self.root / str(reverted["receipt_path"])).read_text(encoding="utf-8"))
        self.assertEqual(revert_receipt["audit_stream"], "execution_receipts")
        self.assertEqual(revert_receipt["audit_event"], "execution_receipt_history_append")
        self.assertEqual(revert_receipt["audit_path"], ".aiwiki/state/execution-receipts.jsonl")
        self.assertEqual(reverted["audit_path"], ".aiwiki/state/execution-receipts.jsonl")
        runtime_history = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/runtime-history.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(
            [item["event_type"] for item in runtime_history],
            ["l3-proposal-create", "l3-proposal-apply", "l3-proposal-revert"],
        )
        self.assertEqual(runtime_history[-1]["proposal_id"], "prop-apply")
        self.assertEqual(runtime_history[-1]["receipt_path"], str(reverted["receipt_path"]))
        audit_records = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        execution_audit = [item for item in audit_records if item["source_stream"] == "execution_receipts"]
        runtime_audit = [item for item in audit_records if item["source_stream"] == "runtime_history"]
        self.assertEqual([item["event_type"] for item in execution_audit], ["apply", "revert"])
        self.assertEqual(
            [item["event_type"] for item in runtime_audit],
            ["l3-proposal-create", "l3-proposal-apply", "l3-proposal-revert"],
        )
        self.assertEqual(runtime_audit[-1]["subject"], {"kind": "l3-proposal-revert", "id": "prop-apply"})

    def test_revert_conflict_writes_human_merge_hint_without_overwriting_target(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-conflict",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
        )
        applied = apply_l3_proposal(self.root, "prop-conflict")
        (self.root / "prompts" / "ask.md").write_text("Human post-apply edit.\n", encoding="utf-8")

        result = revert_l3_proposal(self.root, str(applied["receipt_path"]))

        self.assertEqual(result["state"], "revert_conflict")
        self.assertEqual((self.root / "prompts" / "ask.md").read_text(encoding="utf-8"), "Human post-apply edit.\n")
        hint_path = self.root / str(result["hint_path"])
        self.assertTrue(hint_path.exists())
        self.assertIn("human_merge_required", hint_path.read_text(encoding="utf-8"))
        stored = self._state_proposal("prop-conflict")
        self.assertEqual(stored["state"], "revert_conflict")

    def test_shell_summary_surfaces_l3_proposal_review_controls(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-shell-candidate",
            target_file="prompts/ask.md",
            content="Candidate prompt.\n",
        )
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-shell-accepted",
            target_file="prompts/ask.md",
            content="Accepted prompt.\n",
        )
        accepted = apply_l3_proposal(self.root, "prop-shell-accepted")
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-shell-conflict",
            target_file="prompts/ask.md",
            content="Conflict prompt.\n",
        )
        conflict = apply_l3_proposal(self.root, "prop-shell-conflict")
        (self.root / "prompts" / "ask.md").write_text("Human edit after apply.\n", encoding="utf-8")
        revert_l3_proposal(self.root, str(conflict["receipt_path"]))

        summary = build_shell_summary(self.root)
        controls = {
            str(item.get("proposal_id") or ""): item
            for item in summary["review_controls"]["l3_proposals"]
        }

        candidate = controls["prop-shell-candidate"]
        self.assertTrue(candidate["can_apply"])
        self.assertTrue(candidate["can_reject"])
        self.assertFalse(candidate["can_revert"])
        self.assertIn("apply", candidate["command_hints"])
        accepted_control = controls["prop-shell-accepted"]
        self.assertFalse(accepted_control["can_apply"])
        self.assertTrue(accepted_control["can_revert"])
        self.assertEqual(accepted_control["last_receipt_path"], accepted["receipt_path"])
        conflict_control = controls["prop-shell-conflict"]
        self.assertEqual(conflict_control["state"], "revert_conflict")
        self.assertTrue(conflict_control["needs_attention"])
        self.assertIn("human_merge_required", (self.root / conflict_control["revert_hint_path"]).read_text(encoding="utf-8"))
        self.assertEqual(summary["review_backlog_counts"]["l3_proposals"], 3)
        self.assertEqual(summary["review_backlog_counts"]["l3_proposal_attention"], 2)

    def _write_l3_planner_log(self, *, mode: str = "observe_only", signal_id: str = "sig-20260424-l3prev01") -> None:
        planner_log = self.root / ".aiwiki" / "state" / "planner-log.jsonl"
        planner_log.parent.mkdir(parents=True, exist_ok=True)
        planner_log.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "schema_version": 1,
                            "signal_id": signal_id,
                            "dedupe_key": f"{signal_id}:{mode}",
                            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                            "decision": "generate-proposal",
                            "mode": mode,
                            "reason_codes": ["runtime_failure_observed", "proposal_recommended"] if mode == "observe_only" else ["runtime_failure_observed", "proposal_recommended", "execute_mode_requested"],
                            "budget_used": {},
                            "locks_acquired": [],
                            "primitive_refs": [],
                            "side_effects_allowed": mode == "execute",
                            "decided_at": "2026-04-24T12:00:00Z",
                        },
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        {
                            "schema_version": 1,
                            "signal_id": "sig-20260424-light01",
                            "dedupe_key": "sig-20260424-light01:observe_only",
                            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                            "decision": "enqueue-light",
                            "mode": "observe_only",
                            "reason_codes": ["raw_added_observed"],
                            "budget_used": {},
                            "locks_acquired": [],
                            "primitive_refs": [],
                            "side_effects_allowed": False,
                            "decided_at": "2026-04-24T12:00:01Z",
                        },
                        separators=(",", ":"),
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def test_generation_preview_lists_blocked_planner_candidates_without_writes(self) -> None:
        self._write_l3_planner_log(mode="observe_only")

        result = preview_l3_proposal_generation(self.root)

        self.assertTrue(result["automatic_generation_enabled"])
        self.assertFalse(result["side_effects_allowed"])
        self.assertEqual(result["planner_log_path"], ".aiwiki/state/planner-log.jsonl")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["blocked_count"], 1)
        self.assertEqual(result["returned_count"], 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["signal_id"], "sig-20260424-l3prev01")
        self.assertFalse(candidate["eligible"])
        self.assertIn("requires_execute_mode", candidate["blockers"])
        self.assertFalse(l3_proposal_state_path(self.root).exists())
        self.assertFalse((self.root / "output" / "_proposals").exists())

    def test_generation_preview_marks_execute_mode_candidate_eligible(self) -> None:
        self._write_l3_planner_log(mode="execute", signal_id="sig-20260424-l3exec01")

        result = preview_l3_proposal_generation(self.root)

        candidate = result["candidates"][0]
        self.assertTrue(candidate["eligible"])
        self.assertEqual(candidate["proposal_kind"], "prompt_proposal")
        self.assertEqual(candidate["proposal_id"], "auto-sig-20260424-l3exec01")
        self.assertEqual(candidate["target_file"], "prompts/ask.md")
        self.assertEqual(candidate["blockers"], [])

    def test_generation_preview_coalesces_repeated_concrete_issue_and_prefers_execute(self) -> None:
        planner_log = self.root / ".aiwiki" / "state" / "planner-log.jsonl"
        planner_log.parent.mkdir(parents=True, exist_ok=True)
        records = [
            {
                "schema_version": 1,
                "signal_id": "sig-runtime-1",
                "dedupe_key": "runtime_failure:general:llm_receipt:a",
                "trace_id": "trace-l3-noise",
                "decision": "generate-proposal",
                "mode": "observe_only",
                "reason_codes": ["runtime_failure_observed", "proposal_recommended"],
                "decided_at": "2026-05-19T12:00:00Z",
            },
            {
                "schema_version": 1,
                "signal_id": "sig-runtime-2",
                "dedupe_key": "runtime_failure:general:llm_receipt:b",
                "trace_id": "trace-l3-noise",
                "decision": "generate-proposal",
                "mode": "execute",
                "reason_codes": ["runtime_failure_observed", "proposal_recommended", "execute_mode_requested"],
                "decided_at": "2026-05-19T12:01:00Z",
            },
            {
                "schema_version": 1,
                "signal_id": "sig-runtime-3",
                "dedupe_key": "runtime_failure:general:llm_receipt:c",
                "trace_id": "trace-l3-noise",
                "decision": "generate-proposal",
                "mode": "execute",
                "reason_codes": ["runtime_failure_observed", "proposal_recommended", "execute_mode_requested"],
                "decided_at": "2026-05-19T12:02:00Z",
            },
        ]
        planner_log.write_text("\n".join(json.dumps(record, separators=(",", ":")) for record in records) + "\n", encoding="utf-8")

        result = preview_l3_proposal_generation(self.root, limit=20)

        self.assertEqual(result["raw_candidate_count"], 3)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["blocked_count"], 0)
        self.assertEqual(result["returned_count"], 1)
        candidate = result["candidates"][0]
        self.assertTrue(candidate["eligible"])
        self.assertEqual(candidate["mode"], "execute")
        self.assertEqual(candidate["signal_id"], "sig-runtime-3")
        self.assertEqual(candidate["issue_key"], "prompt_proposal:prompts/ask.md:contract_failure")

    def test_generate_l3_proposals_from_execute_mode_planner_is_idempotent_and_does_not_touch_target(self) -> None:
        self._write_l3_planner_log(mode="execute", signal_id="sig-20260424-l3exec02")
        before = (self.root / "prompts" / "ask.md").read_text(encoding="utf-8")

        result = generate_l3_proposals_from_planner(self.root)
        second = generate_l3_proposals_from_planner(self.root)

        self.assertEqual(result["generated_count"], 1)
        generated = result["generated"][0]
        self.assertEqual(generated["proposal_id"], "auto-sig-20260424-l3exec02")
        self.assertEqual((self.root / "prompts" / "ask.md").read_text(encoding="utf-8"), before)
        stored = self._state_proposal("auto-sig-20260424-l3exec02")
        self.assertEqual(stored["state"], "candidate")
        self.assertEqual(stored["target_file"], "prompts/ask.md")
        self.assertIn("aiwiki:auto-proposal:start", stored["patch"]["content"])
        self.assertEqual(second["generated_count"], 0)
        self.assertEqual(second["skipped"][0]["reason"], "already_exists")
        runtime_history = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/runtime-history.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(runtime_history[-1]["event_type"], "l3-proposal-create")

    def test_generate_l3_proposals_skips_issue_already_covered_by_existing_proposal(self) -> None:
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-covered-runtime-failure",
            target_file="prompts/ask.md",
            content="Review context only.\n",
            pattern="contract_failure",
            patch_kind="metadata_only",
        )
        reject_l3_proposal(self.root, "prop-covered-runtime-failure", note="Already reviewed as a prompt-level issue.")
        self._write_l3_planner_log(mode="execute", signal_id="sig-20260424-covered01")

        result = generate_l3_proposals_from_planner(self.root)

        self.assertEqual(result["generated_count"], 0)
        self.assertEqual(result["skipped"][0]["reason"], "already_covered")

    def test_automatic_l3_prompt_content_includes_record_fields(self) -> None:
        candidate = {
            "signal_id": "sig-abc",
            "trace_id": "trace-xyz",
            "dedupe_key": "dk-1",
            "mode": "execute",
            "decided_at": "2026-05-12T10:00:00Z",
            "reason_codes": ["proposal_recommended", "drift_observed"],
        }

        content = _automatic_l3_prompt_content(
            "# ask prompt\n",
            candidate=candidate,
            planner_log_path="output/runtime/planner-log.jsonl",
        )

        self.assertIn("<!-- aiwiki:auto-proposal:start -->", content)
        self.assertIn("<!-- aiwiki:auto-proposal:end -->", content)
        self.assertIn("Auto-generated L3 proposal review", content)
        # F-INV-22: assert all 5 planner-decision bullet lines verbatim
        self.assertIn("- `signal_id`: sig-abc", content)
        self.assertIn("- `trace_id`: trace-xyz", content)
        self.assertIn("- `decided_at`: 2026-05-12T10:00:00Z", content)
        self.assertIn("- `dedupe_key`: dk-1", content)
        self.assertIn("- `reason_codes`: proposal_recommended, drift_observed", content)
        # F-INV-22: assert evidence bullet line verbatim
        self.assertIn("### Evidence references", content)
        self.assertIn("- `output/runtime/planner-log.jsonl#sig-abc`", content)
        # F-INV-22: assert bullets are inside the auto-proposal block (not after end marker)
        start_idx = content.index("<!-- aiwiki:auto-proposal:start -->")
        end_idx = content.index("<!-- aiwiki:auto-proposal:end -->")
        block = content[start_idx:end_idx]
        for bullet in (
            "- `signal_id`: sig-abc",
            "- `trace_id`: trace-xyz",
            "- `decided_at`: 2026-05-12T10:00:00Z",
            "- `dedupe_key`: dk-1",
            "- `reason_codes`: proposal_recommended, drift_observed",
            "- `output/runtime/planner-log.jsonl#sig-abc`",
        ):
            self.assertIn(bullet, block)

    def test_automatic_l3_prompt_content_handles_missing_fields(self) -> None:
        candidate = {
            "signal_id": "",
            "trace_id": "",
            "dedupe_key": "",
            "mode": "",
            "decided_at": "",
            "reason_codes": [],
        }

        content = _automatic_l3_prompt_content(
            "# ask prompt\n",
            candidate=candidate,
            planner_log_path="",
        )

        self.assertIn("- `signal_id`: (unknown)", content)
        self.assertIn("- `trace_id`: (unknown)", content)
        self.assertIn("- `decided_at`: (unknown)", content)
        self.assertIn("- `dedupe_key`: (unknown)", content)
        self.assertIn("- `reason_codes`: (none)", content)
        # F-INV-22: evidence bullet falls back to (unknown)#(unknown) when both empty
        self.assertIn("### Evidence references", content)
        self.assertIn("- `(unknown)#(unknown)`", content)

    def test_generation_preview_missing_planner_log_is_read_only_empty(self) -> None:
        result = preview_l3_proposal_generation(self.root)

        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["returned_count"], 0)
        self.assertEqual(result["candidates"], [])
        self.assertFalse(l3_proposal_state_path(self.root).exists())

    def test_metadata_only_apply_does_not_modify_target_file(self) -> None:
        """F-INV-20: metadata_only patch_kind must not write to target file.

        Acknowledgement-style proposals carry trace metadata in patch.content
        as review context only; apply records a receipt but leaves the target
        file's sha256 unchanged.
        """
        import hashlib

        target = self.root / "prompts" / "ask.md"
        original_bytes = target.read_bytes()
        original_sha = hashlib.sha256(original_bytes).hexdigest()

        result = create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-meta-only",
            target_file="prompts/ask.md",
            content="## Auto-generated review context\n- signal_id: sig-1\n",
            rationale="metadata_only acknowledgement",
            patch_kind="metadata_only",
        )
        self.assertEqual(result["state"], "candidate")

        # patch.kind persisted as metadata_only in state
        state_entry = self._state_proposal("prop-meta-only")
        self.assertEqual(state_entry["patch"]["kind"], "metadata_only")

        # apply
        apply_result = apply_l3_proposal(self.root, "prop-meta-only")
        self.assertEqual(apply_result["state"], "accepted")

        # target file sha256 unchanged
        after_apply_sha = hashlib.sha256(target.read_bytes()).hexdigest()
        self.assertEqual(after_apply_sha, original_sha, "metadata_only apply must not touch target file")
        self.assertEqual(apply_result["before_hash"], apply_result["after_hash"])

        # apply receipt carries patch_kind=metadata_only
        receipt = json.loads((self.root / apply_result["receipt_path"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt["patch_kind"], "metadata_only")
        self.assertEqual(receipt["before_hash"], receipt["after_hash"])
        self.assertEqual(receipt["before_content"], receipt["after_content"])

    def test_metadata_only_revert_is_noop_but_writes_receipt(self) -> None:
        """F-INV-20: metadata_only revert leaves target untouched, writes revert receipt."""
        import hashlib

        target = self.root / "prompts" / "ask.md"
        original_sha = hashlib.sha256(target.read_bytes()).hexdigest()

        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-meta-revert",
            target_file="prompts/ask.md",
            content="## Review context\n",
            patch_kind="metadata_only",
        )
        apply_result = apply_l3_proposal(self.root, "prop-meta-revert")

        # revert by apply receipt
        revert_result = revert_l3_proposal(self.root, apply_result["receipt_path"])
        self.assertEqual(revert_result["proposal_id"], "prop-meta-revert")

        # target still untouched
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), original_sha)

        # state moved to reverted
        state_entry = self._state_proposal("prop-meta-revert")
        self.assertEqual(state_entry["state"], "reverted")

        # revert receipt carries patch_kind=metadata_only and restored_hash == after_hash
        revert_receipt_path = self.root / state_entry["last_revert_receipt_path"]
        revert_receipt = json.loads(revert_receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(revert_receipt["patch_kind"], "metadata_only")
        self.assertEqual(revert_receipt["restored_hash"], revert_receipt["after_hash"])

    def test_create_l3_proposal_rejects_unknown_patch_kind(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported L3 patch_kind"):
            create_l3_proposal(
                self.root,
                kind="prompt_proposal",
                proposal_id="prop-bad-kind",
                target_file="prompts/ask.md",
                content="x\n",
                patch_kind="llm_diff",
            )

    def test_apply_defaults_missing_patch_kind_to_full_replace(self) -> None:
        """F-INV-20 backward-compat: legacy proposals without patch.kind apply as full_replace."""
        result = create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-legacy",
            target_file="prompts/ask.md",
            content="Legacy proposal content.\n",
        )
        # Simulate legacy state where patch.kind is missing
        state_path = l3_proposal_state_path(self.root)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for prop in state["proposals"]:
            if prop["proposal_id"] == "prop-legacy":
                prop["patch"].pop("kind", None)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        # apply must succeed (default to full_replace), not raise
        apply_result = apply_l3_proposal(self.root, "prop-legacy")
        self.assertEqual(apply_result["state"], "accepted")
        self.assertEqual(
            (self.root / "prompts" / "ask.md").read_text(encoding="utf-8"),
            "Legacy proposal content.\n",
        )
        del result

    def test_metadata_only_apply_is_stale_when_target_drifted(self) -> None:
        """F-INV-20 N3: metadata_only apply still honors stale gate on before_hash.

        Even though metadata_only does not write to target, the proposal is
        anchored to a specific target snapshot via patch.before_hash; if the
        target drifted before apply, apply must mark the proposal stale.
        """
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-meta-stale",
            target_file="prompts/ask.md",
            content="## Review context\n",
            patch_kind="metadata_only",
        )
        # External edit to target after candidate created
        (self.root / "prompts" / "ask.md").write_text("Drifted before apply.\n", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "stale"):
            apply_l3_proposal(self.root, "prop-meta-stale")

        state_entry = self._state_proposal("prop-meta-stale")
        self.assertEqual(state_entry["state"], "stale")
        self.assertEqual(state_entry["stale_reason"], "before_hash_mismatch")

    def test_metadata_only_revert_after_target_drift_still_succeeds(self) -> None:
        """F-INV-20: metadata_only revert must not be blocked by target drift.

        Since metadata_only apply did not touch the target, a later external
        edit to the target is not a merge responsibility of this proposal.
        Revert proceeds as no-op file op + receipt write.
        """
        import hashlib

        target = self.root / "prompts" / "ask.md"

        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-meta-drift",
            target_file="prompts/ask.md",
            content="## Review context\n",
            patch_kind="metadata_only",
        )
        apply_result = apply_l3_proposal(self.root, "prop-meta-drift")

        # Simulate external edit to target after apply (drift)
        drifted_content = "Externally modified content.\n"
        target.write_text(drifted_content, encoding="utf-8")
        drifted_sha = hashlib.sha256(target.read_bytes()).hexdigest()

        # revert should succeed (not enter revert_conflict)
        revert_result = revert_l3_proposal(self.root, apply_result["receipt_path"])
        self.assertEqual(revert_result["proposal_id"], "prop-meta-drift")

        state_entry = self._state_proposal("prop-meta-drift")
        self.assertEqual(state_entry["state"], "reverted")

        # target left as-is (drift preserved; metadata_only revert is no-op)
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), drifted_sha)
        self.assertEqual(target.read_text(encoding="utf-8"), drifted_content)

    def test_full_replace_revert_receipt_hash_fields_are_semantically_independent(self) -> None:
        """F-INV-23: revert receipt's `after_hash` and `restored_hash` carry
        distinct meanings:
        - `after_hash` = expected pre-revert hash (carried over from apply
          receipt's post-apply hash; conflict-gate reference, NOT recomputed).
        - `restored_hash` = actual post-revert hash (computed from disk after
          atomic write-back of `before_content`).
        In a clean full_replace revert, restored_hash == before_hash, while
        after_hash reflects the (different) post-apply state. They MUST differ
        whenever the apply changed the target content.
        """
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            proposal_id="prop-hash-sem",
            target_file="prompts/ask.md",
            content="Updated ask prompt.\n",
        )
        applied = apply_l3_proposal(self.root, "prop-hash-sem")
        reverted = revert_l3_proposal(self.root, str(applied["receipt_path"]))

        self.assertEqual(reverted["state"], "reverted")
        revert_receipt = json.loads((self.root / str(reverted["receipt_path"])).read_text(encoding="utf-8"))

        # all three hash fields present
        self.assertIn("before_hash", revert_receipt)
        self.assertIn("after_hash", revert_receipt)
        self.assertIn("restored_hash", revert_receipt)

        before_hash = revert_receipt["before_hash"]
        after_hash = revert_receipt["after_hash"]
        restored_hash = revert_receipt["restored_hash"]

        # clean full_replace revert: restored matches pre-apply (before_hash)
        self.assertEqual(restored_hash, before_hash)
        # after_hash carries the post-apply state, which differs from pre-apply
        self.assertNotEqual(before_hash, after_hash)
        # therefore restored_hash and after_hash are semantically independent
        self.assertNotEqual(restored_hash, after_hash)
