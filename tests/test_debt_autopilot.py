from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout, save_manifest
from aiwiki.app_state import (
    l3_proposal_state_path,
    load_machine_memory_action_state,
    machine_memory_action_state_path,
    machine_memory_state_path,
    save_concept_rewrite_state,
    save_json_document,
)
from aiwiki.debt_autopilot import (
    LLM_OWNED_NON_CORE,
    _auto_apply_concept_rewrite_proposals,
    _digest_content_debt,
    _generate_rewrite_candidates,
    collect_auto_adopt_work,
    collect_debt_inventory,
    run_debt_autopilot,
)
from aiwiki.memory.execution_surfaces import reconcile_concept_rewrite_proposals


class DebtAutopilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_collects_llm_owned_non_core_debt_from_owner_state(self) -> None:
        save_manifest(self.root, {"version": 1, "entries": [{"id": "source-a", "title": "Source A"}]})
        (self.root / "wiki" / "sources" / "source-a.md").write_text(
            "# Source A\n\nPending LLM summary.\n",
            encoding="utf-8",
        )
        save_json_document(
            machine_memory_state_path(self.root),
            {
                "health": {
                    "concept_quality": {
                        "weak_concepts": [{"slug": "agent"}],
                        "rewrite_candidates": [{"slug": "agent"}],
                    },
                    "judgment_review_actions": [{"id": "judgment-review-1"}],
                }
            },
        )
        save_json_document(
            machine_memory_action_state_path(self.root),
            {
                "version": 1,
                "actions": [
                    {
                        "id": "bridge-agent",
                        "kind": "monitor-bridge-concept",
                        "status": "proposed",
                        "active": True,
                    }
                ],
            },
        )
        save_json_document(
            l3_proposal_state_path(self.root),
            {
                "version": 1,
                "proposals": [
                    {
                        "proposal_id": "meta-1",
                        "state": "candidate",
                        "patch": {"kind": "metadata_only"},
                    }
                ],
            },
        )

        report = collect_debt_inventory(self.root)

        self.assertEqual(report["autonomy_boundary"], LLM_OWNED_NON_CORE)
        self.assertEqual(report["status"], "active")
        self.assertEqual(report["debt_detected_count"], 5)
        self.assertEqual(report["categories"]["pending_source_summaries"]["count"], 1)
        self.assertEqual(report["categories"]["machine_memory_actions"]["count"], 1)
        self.assertEqual(report["categories"]["l3_non_core_proposals"]["count"], 0)
        self.assertEqual(report["categories"]["machine_memory_actions"]["autonomy_boundary"], LLM_OWNED_NON_CORE)

    def test_collect_debt_inventory_excludes_governance_and_human_required_actions(self) -> None:
        save_json_document(
            machine_memory_action_state_path(self.root),
            {
                "version": 1,
                "actions": [
                    {
                        "id": "safe-link",
                        "kind": "add-source-concept-link",
                        "status": "proposed",
                        "active": True,
                    },
                    {
                        "id": "governance-refresh",
                        "kind": "refresh-citation-snapshots",
                        "status": "proposed",
                        "active": True,
                    },
                    {
                        "id": "already-human",
                        "kind": "split-overloaded-concept",
                        "status": "deferred",
                        "active": True,
                        "human_required": "true",
                        "human_required_reason": "operator_override",
                    },
                ],
            },
        )

        report = collect_debt_inventory(self.root)

        self.assertEqual(report["debt_detected_count"], 1)
        self.assertEqual(report["categories"]["machine_memory_actions"]["sample"], ["safe-link"])

    def test_collect_debt_inventory_excludes_governance_l3_metadata_proposals(self) -> None:
        save_json_document(
            l3_proposal_state_path(self.root),
            {
                "version": 1,
                "proposals": [
                    {
                        "proposal_id": "meta-1",
                        "state": "candidate",
                        "patch": {"kind": "metadata_only"},
                    },
                    {
                        "proposal_id": "full-1",
                        "state": "candidate",
                        "patch": {"kind": "full_replace"},
                    },
                ],
            },
        )

        report = collect_debt_inventory(self.root)

        self.assertEqual(report["debt_detected_count"], 0)
        self.assertEqual(report["categories"]["l3_non_core_proposals"]["count"], 0)

    def test_collect_debt_inventory_excludes_current_applied_rewrite(self) -> None:
        save_json_document(
            machine_memory_state_path(self.root),
            {
                "health": {
                    "concept_quality": {
                        "weak_concepts": [{"slug": "agent"}, {"slug": "repo"}],
                        "rewrite_candidates": [{"slug": "agent"}, {"slug": "repo"}],
                    }
                }
            },
        )
        save_concept_rewrite_state(
            self.root,
            {
                "version": 1,
                "proposals": [
                    {
                        "slug": "agent",
                        "status": "applied",
                        "active": True,
                        "verification_status": "passed",
                        "candidate_markdown": "# Agent\n",
                    }
                ],
            },
        )

        with patch("aiwiki.content.memory.rewrite_proposal_candidate_is_current", return_value=True):
            report = collect_debt_inventory(self.root)

        self.assertEqual(report["debt_detected_count"], 2)
        self.assertEqual(report["categories"]["weak_concepts"]["sample"], ["repo"])
        self.assertEqual(report["categories"]["rewrite_candidates"]["sample"], ["repo"])

    def test_collect_debt_inventory_keeps_failed_applied_rewrite_as_debt(self) -> None:
        save_json_document(
            machine_memory_state_path(self.root),
            {
                "health": {
                    "concept_quality": {
                        "weak_concepts": [{"slug": "agent"}],
                        "rewrite_candidates": [{"slug": "agent"}],
                    }
                }
            },
        )
        save_concept_rewrite_state(
            self.root,
            {
                "version": 1,
                "proposals": [
                    {
                        "slug": "agent",
                        "status": "applied",
                        "active": True,
                        "verification_status": "failed",
                        "candidate_markdown": "# Agent\n",
                    }
                ],
            },
        )

        with patch("aiwiki.content.memory.rewrite_proposal_candidate_is_current", return_value=True):
            report = collect_debt_inventory(self.root)

        self.assertEqual(report["debt_detected_count"], 2)
        self.assertEqual(report["categories"]["weak_concepts"]["sample"], ["agent"])
        self.assertEqual(report["categories"]["rewrite_candidates"]["sample"], ["agent"])

    def test_collect_debt_inventory_ignores_stale_nightly_repair_backlog(self) -> None:
        report = collect_debt_inventory(
            self.root,
            nightly={
                "repair_backlog": {
                    "pending_source_summaries": ["stale-source"],
                    "weak_concept_slugs": ["stale-concept"],
                    "judgment_review_actions": ["stale-review"],
                }
            },
        )

        self.assertEqual(report["status"], "clear")
        self.assertEqual(report["debt_detected_count"], 0)
        self.assertEqual(report["llm_owned_non_core_pending_count"], 0)

    def test_auto_adopt_work_uses_owner_state_not_product_shell_controls(self) -> None:
        save_json_document(
            self.root / ".aiwiki" / "state" / "knowledge-lifecycle.json",
            {
                "version": 1,
                "entries": [
                    {"kind": "concept", "slug": "agent", "path": "wiki/concepts/agent.md", "lifecycle_state": "review"},
                    {"kind": "concept", "slug": "repo", "path": "wiki/concepts/repo.md", "lifecycle_state": "revisit"},
                ],
            },
        )
        save_json_document(
            machine_memory_action_state_path(self.root),
            {
                "version": 1,
                "actions": [
                    {
                        "id": "split-agent",
                        "kind": "split-overloaded-concept",
                        "status": "proposed",
                        "active": True,
                    }
                ],
            },
        )

        with (
            patch("aiwiki.app_shell.controls.shell_review_controls", side_effect=AssertionError("shell review used")),
            patch("aiwiki.app_shell.controls.shell_execution_controls", side_effect=AssertionError("shell execution used")),
        ):
            review_ctrl, exec_ctrl = collect_auto_adopt_work(self.root)

        self.assertEqual(review_ctrl["concept_backlog"][0]["slug"], "agent")
        self.assertEqual(review_ctrl["revisit_concepts"][0]["slug"], "repo")
        self.assertEqual(exec_ctrl["actions"][0]["action_id"], "split-agent")
        self.assertTrue(exec_ctrl["actions"][0]["can_review"])

    def test_debt_autopilot_dry_run_does_not_escalate_proposed_debt(self) -> None:
        save_json_document(
            machine_memory_action_state_path(self.root),
            {
                "version": 1,
                "actions": [
                    {
                        "id": "bridge-agent",
                        "kind": "monitor-bridge-concept",
                        "status": "proposed",
                        "active": True,
                    }
                ],
            },
        )

        result = run_debt_autopilot(self.root, apply=False)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["debt_detected_count"], 1)
        self.assertEqual(result["debt_auto_resolved_count"], 0)
        state = load_machine_memory_action_state(self.root)
        self.assertEqual(state["actions"][0]["status"], "proposed")
        self.assertEqual(result["auto_resolution"]["counts"]["evaluated"], 0)

    def test_debt_autopilot_apply_skips_unsafe_accepted_debt_without_human_escalation(self) -> None:
        save_json_document(
            machine_memory_action_state_path(self.root),
            {
                "version": 1,
                "actions": [
                    {
                        "id": "bridge-agent",
                        "kind": "monitor-bridge-concept",
                        "status": "accepted",
                        "active": True,
                    }
                ],
            },
        )

        result = run_debt_autopilot(self.root, apply=True)

        self.assertFalse(result["dry_run"])
        self.assertEqual(result["debt_detected_count"], 1)
        self.assertEqual(result["debt_auto_resolved_count"], 0)
        self.assertEqual(result["auto_resolution"]["counts"]["skipped"], 1)
        self.assertEqual(result["auto_resolution"]["counts"]["escalated"], 0)
        item = result["auto_resolution"]["items"][0]
        self.assertEqual(item["operation"], "skip")
        self.assertEqual(item["skipped_operation"], "escalate")
        state = load_machine_memory_action_state(self.root)
        self.assertEqual(state["actions"][0]["status"], "accepted")
        self.assertNotIn("human_required", state["actions"][0])

    def test_debt_autopilot_apply_routes_content_debt_to_digestion(self) -> None:
        save_manifest(self.root, {"version": 1, "entries": [{"id": "source-a", "title": "Source A"}]})
        (self.root / "wiki" / "sources" / "source-a.md").write_text(
            "# Source A\n\nPending LLM summary.\n",
            encoding="utf-8",
        )

        with patch(
            "aiwiki.debt_autopilot._digest_content_debt",
            return_value={
                "operation": "content-debt-digestion",
                "dry_run": False,
                "status": "applied",
                "counts": {
                    "updated_source_pages": 1,
                    "updated_concept_pages": 0,
                    "generated_rewrite_proposals": 0,
                    "applied_rewrite_proposals": 0,
                    "skipped_rewrite_proposals": 0,
                    "failed_rewrite_proposals": 0,
                },
                "items": [],
            },
        ) as digest_mock:
            result = run_debt_autopilot(self.root, apply=True, limit=2)

        digest_mock.assert_called_once_with(self.root, limit=2)
        self.assertEqual(result["content_digestion"]["counts"]["updated_source_pages"], 1)
        self.assertEqual(result["debt_auto_resolved_count"], 1)

    def test_auto_apply_concept_rewrite_accepts_and_applies_current_non_core_proposal(self) -> None:
        save_concept_rewrite_state(
            self.root,
            {
                "version": 1,
                "proposals": [
                    {
                        "slug": "agent",
                        "status": "proposed",
                        "active": True,
                        "candidate_markdown": "# Agent\n",
                    }
                ],
            },
        )

        with (
            patch("aiwiki.content.memory.rewrite_proposal_candidate_is_current", return_value=True),
            patch(
                "aiwiki.execution.concept_rewrite.review_concept_rewrite",
                return_value={"slug": "agent", "status": "accepted"},
            ) as review_mock,
            patch(
                "aiwiki.execution.concept_rewrite.apply_concept_rewrite",
                return_value={"slug": "agent", "status": "applied"},
            ) as apply_mock,
        ):
            result = _auto_apply_concept_rewrite_proposals(self.root, limit=1)

        self.assertEqual(result["counts"]["evaluated"], 1)
        self.assertEqual(result["counts"]["applied"], 1)
        review_mock.assert_called_once()
        apply_mock.assert_called_once()
        self.assertEqual(result["items"][0]["operation"], "apply")

    def test_auto_apply_concept_rewrite_limit_does_not_starve_current_proposal(self) -> None:
        save_concept_rewrite_state(
            self.root,
            {
                "version": 1,
                "proposals": [
                    {
                        "slug": "stale",
                        "status": "proposed",
                        "active": True,
                    },
                    {
                        "slug": "agent",
                        "status": "proposed",
                        "active": True,
                        "candidate_markdown": "# Agent\n",
                    },
                ],
            },
        )

        def is_current(root: Path, proposal: dict) -> bool:
            return proposal.get("slug") == "agent"

        with (
            patch("aiwiki.content.memory.rewrite_proposal_candidate_is_current", side_effect=is_current),
            patch(
                "aiwiki.execution.concept_rewrite.review_concept_rewrite",
                return_value={"slug": "agent", "status": "accepted"},
            ) as review_mock,
            patch(
                "aiwiki.execution.concept_rewrite.apply_concept_rewrite",
                return_value={"slug": "agent", "status": "applied"},
            ) as apply_mock,
        ):
            result = _auto_apply_concept_rewrite_proposals(self.root, limit=1)

        self.assertEqual(result["counts"]["evaluated"], 1)
        self.assertEqual(result["counts"]["applied"], 1)
        self.assertEqual(result["counts"]["skipped"], 0)
        review_mock.assert_called_once_with(
            self.root,
            "agent",
            "accepted",
            note="debt-autopilot: accept current non-core concept rewrite",
        )
        apply_mock.assert_called_once()
        self.assertEqual(result["items"][0]["slug"], "agent")
        self.assertEqual(result["items"][0]["operation"], "apply")

    def test_auto_apply_concept_rewrite_does_not_count_failed_verification_as_applied(self) -> None:
        save_concept_rewrite_state(
            self.root,
            {
                "version": 1,
                "proposals": [
                    {
                        "slug": "agent",
                        "status": "proposed",
                        "active": True,
                        "candidate_markdown": "# Agent\n",
                    }
                ],
            },
        )

        with (
            patch("aiwiki.content.memory.rewrite_proposal_candidate_is_current", return_value=True),
            patch("aiwiki.execution.concept_rewrite.review_concept_rewrite", return_value={"status": "accepted"}),
            patch(
                "aiwiki.execution.concept_rewrite.apply_concept_rewrite",
                return_value={"slug": "agent", "status": "applied", "verification_status": "failed"},
            ),
        ):
            result = _auto_apply_concept_rewrite_proposals(self.root, limit=1)

        self.assertEqual(result["counts"]["applied"], 0)
        self.assertEqual(result["counts"]["failed"], 1)
        self.assertEqual(result["items"][0]["operation"], "failed")
        self.assertEqual(result["items"][0]["reason_code"], "verification_failed")

    def test_content_debt_digestion_continues_after_source_compile_failure(self) -> None:
        save_manifest(
            self.root,
            {
                "version": 1,
                "entries": [
                    {"id": "source-a", "title": "Source A"},
                    {"id": "source-b", "title": "Source B"},
                ],
            },
        )
        for source_id in ("source-a", "source-b"):
            (self.root / "wiki" / "sources" / f"{source_id}.md").write_text(
                f"# {source_id}\n\nPending LLM summary.\n",
                encoding="utf-8",
            )

        def fake_run_compile(root: Path, *, limit: int, paths: list[str]) -> dict:
            if paths == ["source-a"]:
                raise TimeoutError("source-a timed out")
            return {"updated_pages": [f"wiki/sources/{paths[0]}.md"], "updated_concept_pages": [], "updated_rewrite_proposal_pages": []}

        with (
            patch("aiwiki.runner.workflows.run_compile", side_effect=fake_run_compile),
            patch("aiwiki.debt_autopilot._auto_apply_concept_rewrite_proposals", return_value={"counts": {"applied": 0, "skipped": 0, "failed": 0}, "items": []}),
        ):
            result = _digest_content_debt(self.root, limit=2)

        self.assertEqual(result["counts"]["failed_source_pages"], 1)
        self.assertEqual(result["counts"]["updated_source_pages"], 1)
        self.assertEqual([item["status"] for item in result["items"]], ["failed", "applied"])

    def test_generates_rewrite_candidates_when_only_weak_concept_debt_exists(self) -> None:
        save_json_document(
            machine_memory_state_path(self.root),
            {"health": {"concept_quality": {"weak_concepts": [{"slug": "agent"}], "rewrite_candidates": []}}},
        )

        with patch(
            "aiwiki.runner.workflows.run_compile",
            return_value={
                "updated_pages": [],
                "updated_concept_pages": [],
                "updated_rewrite_proposal_pages": ["wiki/rewrite-proposals/agent.md"],
            },
        ) as compile_mock:
            result = _generate_rewrite_candidates(self.root, limit=1)

        compile_mock.assert_called_once_with(self.root, limit=1, paths=["wiki/concepts/agent.md"])
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["counts"]["generated_rewrite_proposals"], 1)

    def test_rewrite_generation_skips_current_applied_rewrites(self) -> None:
        save_json_document(
            machine_memory_state_path(self.root),
            {
                "health": {
                    "concept_quality": {
                        "rewrite_candidates": [{"slug": "agent"}, {"slug": "repo"}],
                    }
                }
            },
        )
        save_concept_rewrite_state(
            self.root,
            {
                "version": 1,
                "proposals": [
                    {
                        "slug": "agent",
                        "status": "applied",
                        "active": True,
                        "verification_status": "passed",
                        "candidate_markdown": "# Agent\n",
                    }
                ],
            },
        )

        with (
            patch("aiwiki.content.memory.rewrite_proposal_candidate_is_current", return_value=True),
            patch(
                "aiwiki.runner.workflows.run_compile",
                return_value={
                    "updated_pages": [],
                    "updated_concept_pages": [],
                    "updated_rewrite_proposal_pages": ["wiki/rewrite-proposals/repo.md"],
                },
            ) as compile_mock,
        ):
            result = _generate_rewrite_candidates(self.root, limit=1)

        compile_mock.assert_called_once_with(self.root, limit=1, paths=["wiki/concepts/repo.md"])
        self.assertEqual(result["selected_slugs"], ["repo"])

    def test_reconcile_keeps_weak_only_rewrite_proposal_active(self) -> None:
        concept_path = self.root / "wiki" / "concepts" / "weak-only.md"
        concept_path.write_text(
            "---\n"
            "id: concept-weak-only\n"
            "kind: concept\n"
            "source_signature: sig-1\n"
            "source_pages:\n"
            "- wiki/sources/source-a.md\n"
            "---\n\n"
            "# Weak Only\n\n"
            "## Summary\n\n"
            "Old summary.\n",
            encoding="utf-8",
        )
        save_concept_rewrite_state(
            self.root,
            {
                "version": 1,
                "proposals": [
                    {
                        "slug": "weak-only",
                        "title": "Weak Only",
                        "status": "proposed",
                        "active": True,
                        "candidate_markdown": "# Weak Only\n\n## Summary\n\nNew summary.\n",
                    }
                ],
            },
        )

        state = reconcile_concept_rewrite_proposals(
            self.root,
            {
                "rewrite_candidates": [],
                "weak_concepts": [
                    {
                        "slug": "weak-only",
                        "title": "Weak Only",
                        "path": "wiki/concepts/weak-only.md",
                        "source_signature": "sig-1",
                        "source_pages": ["wiki/sources/source-a.md"],
                    }
                ],
            },
            compiled_at="2026-06-01T00:00:00+00:00",
        )

        active = {proposal["slug"]: proposal for proposal in state["proposals"]}
        self.assertIn("weak-only", active)
        self.assertTrue(active["weak-only"]["active"])
        self.assertEqual(state["counts"]["inactive"], 0)

    def test_rewrite_generation_targets_concepts_without_reentering_source_queue(self) -> None:
        save_manifest(self.root, {"version": 1, "entries": [{"id": "source-a", "title": "Source A"}]})
        (self.root / "wiki" / "sources" / "source-a.md").write_text(
            "# Source A\n\nPending LLM summary.\n",
            encoding="utf-8",
        )
        save_json_document(
            machine_memory_state_path(self.root),
            {"health": {"concept_quality": {"rewrite_candidates": [{"slug": "agent"}]}}},
        )

        with patch(
            "aiwiki.runner.workflows.run_compile",
            return_value={
                "updated_pages": [],
                "updated_concept_pages": [],
                "updated_rewrite_proposal_pages": ["wiki/rewrite-proposals/agent.md"],
            },
        ) as compile_mock:
            result = _generate_rewrite_candidates(self.root, limit=1)

        compile_mock.assert_called_once_with(self.root, limit=1, paths=["wiki/concepts/agent.md"])
        self.assertEqual(result["counts"]["generated_rewrite_proposals"], 1)

    def test_auto_apply_concept_rewrite_continues_after_apply_failure(self) -> None:
        save_concept_rewrite_state(
            self.root,
            {
                "version": 1,
                "proposals": [
                    {"slug": "agent", "status": "proposed", "active": True, "candidate_markdown": "# Agent\n"},
                    {"slug": "repo", "status": "proposed", "active": True, "candidate_markdown": "# Repo\n"},
                ],
            },
        )

        def fake_apply(root: Path, slug: str, *, note: str | None = None, dry_run: bool = False) -> dict:
            if slug == "agent":
                raise RuntimeError("apply failed")
            return {"slug": slug, "status": "applied"}

        with (
            patch("aiwiki.content.memory.rewrite_proposal_candidate_is_current", return_value=True),
            patch("aiwiki.execution.concept_rewrite.review_concept_rewrite", return_value={"status": "accepted"}),
            patch("aiwiki.execution.concept_rewrite.apply_concept_rewrite", side_effect=fake_apply),
        ):
            result = _auto_apply_concept_rewrite_proposals(self.root, limit=2)

        self.assertEqual(result["counts"]["evaluated"], 2)
        self.assertEqual(result["counts"]["failed"], 1)
        self.assertEqual(result["counts"]["applied"], 1)
        self.assertEqual([item["operation"] for item in result["items"]], ["failed", "apply"])


if __name__ == "__main__":
    unittest.main()
