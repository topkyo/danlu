from __future__ import annotations

import base64
import io
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from aiwiki.app_cache import CACHE_SCHEMA_VERSION, drop_query_cache, force_rebuild_query_cache
from aiwiki.app_compile import (
    _save_machine_memory_action_records,
    apply_concept_rewrite,
    apply_machine_memory_action,
    apply_material_archive,
    ask_question,
    compile_wiki,
    file_back,
    lint_wiki,
    nightly_health,
    rank_concepts,
    rank_sources,
    reactivate_concept,
    retire_concept,
    revert_concept_rewrite,
    revert_machine_memory_action,
    revert_material_archive,
    review_concept,
    review_concept_rewrite,
    review_concepts_batch,
    review_machine_memory_action,
    review_machine_memory_actions_batch,
    review_page,
    set_active_protocol,
    shell_status,
    verify_concept_rewrite,
)
from aiwiki.app_content import (
    collect_machine_memory_actions,
    entry_concept_terms,
    ingest_source,
    load_execution_policy_decision_history,
    placeholder_concept_slugs,
    protocol_related_concept_lifecycle_summary,
)
from aiwiki.app_execution import append_execution_receipt_history
from aiwiki.app_memory import (
    active_corpus_bridge_evidence_ids,
    build_archive_candidate_state,
    build_machine_memory_query,
)
from aiwiki.app_memory_surfaces import render_machine_memory_graph_html
from aiwiki.app_protocol import ensure_layout, load_protocol_state, save_manifest
from aiwiki.app_state import (
    concept_rewrite_state_path,
    execution_receipt_history_path,
    load_archive_candidates_state,
    load_cache_status,
    load_jsonl_documents,
    load_knowledge_lifecycle_override_state,
    load_knowledge_lifecycle_state,
    load_machine_memory,
    load_machine_memory_action_state,
    load_manifest,
    load_material_routing_state,
    load_material_state,
    load_output_candidates_state,
    load_planner_state,
    load_query_route_telemetry,
    runtime_history_path,
    save_knowledge_lifecycle_override_state,
    save_machine_memory_action_state,
    save_manual_link_state,
    save_material_routing_state,
    save_material_state,
    shell_summary_path,
)
from aiwiki.app_utils import parse_frontmatter, render_frontmatter, runtime_write_lock, strip_frontmatter
from aiwiki.cli import main as cli_main
from aiwiki.compile import compile_wiki as compile_wiki_owner
from aiwiki.config import BACKEND_CODEX_CLI, BACKEND_COPILOT_CLI, LLMConfig
from aiwiki.drop import _fetch_url, drop_image, drop_pdf, drop_repo, drop_url
from aiwiki.execution.machine_memory_actions import MachineMemoryActionReceiptError
from aiwiki.lifecycle.templates import repair_curated_page_body
from aiwiki.llm import CompletionResult
from aiwiki.runner import auto_process_once, run_ask, run_compile, run_lint, run_nightly, watch_inbox
from tests.test_app import AppFlowTestBase, CapturingClient, FailingVisionClient, StubClient, StubVisionClient


class LifecycleFlowTests(AppFlowTestBase):
    def test_apply_material_archive_persists_archived_temperature_across_compile(self) -> None:
        entry = self._prepare_ready_archive_candidate()

        result = apply_material_archive(self.root, entry["id"], note="Archive stale source.")

        self.assertEqual(result["status"], "archived")
        archive_state = json.loads((self.root / ".aiwiki" / "state" / "material-archives.json").read_text(encoding="utf-8"))
        archive_entry = next(item for item in archive_state["entries"] if item["entry_id"] == entry["id"])
        self.assertTrue(archive_entry["active"])
        self.assertEqual(archive_entry["previous_temperature"], "cold")
        material_state = json.loads((self.root / ".aiwiki" / "state" / "material-state.json").read_text(encoding="utf-8"))
        material_entry = next(item for item in material_state["entries"] if item["entry_id"] == entry["id"])
        self.assertEqual(material_entry["temperature"], "archived")
        self.assertTrue(material_entry["archive_override"])
        self.assertFalse(material_entry["archive_candidate"])
        receipt = json.loads((self.root / result["receipt_path"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt["kind"], "execution-receipt")
        self.assertEqual(receipt["subject_kind"], "material-archive")
        self.assertEqual(receipt["subject_id"], entry["id"])
        self.assertEqual(receipt["resulting_temperature"], "archived")

        compile_wiki(self.root)

        material_state = json.loads((self.root / ".aiwiki" / "state" / "material-state.json").read_text(encoding="utf-8"))
        material_entry = next(item for item in material_state["entries"] if item["entry_id"] == entry["id"])
        self.assertEqual(material_entry["temperature"], "archived")

    def test_revert_material_archive_restores_cold_and_query_visibility(self) -> None:
        entry = self._prepare_ready_archive_candidate()
        apply_material_archive(self.root, entry["id"], note="Archive stale source.")

        report = ask_question(self.root, "Obscure legacy note", "report")
        self.assertNotIn(entry["id"], report["ranked_sources"])

        result = revert_material_archive(self.root, entry["id"], note="Restore archived source.")

        self.assertEqual(result["status"], "cold")
        archive_state = json.loads((self.root / ".aiwiki" / "state" / "material-archives.json").read_text(encoding="utf-8"))
        archive_entry = next(item for item in archive_state["entries"] if item["entry_id"] == entry["id"])
        self.assertFalse(archive_entry["active"])
        receipt = json.loads((self.root / result["receipt_path"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt["operation"], "revert")
        self.assertEqual(receipt["resulting_temperature"], "cold")
        material_state = json.loads((self.root / ".aiwiki" / "state" / "material-state.json").read_text(encoding="utf-8"))
        material_entry = next(item for item in material_state["entries"] if item["entry_id"] == entry["id"])
        self.assertEqual(material_entry["temperature"], "cold")

        report = ask_question(self.root, "Obscure legacy note", "report")
        self.assertIn(entry["id"], report["ranked_sources"])

    def test_ensure_layout_bootstraps_runtime_schema_files(self) -> None:
        for relative in (
            "schema/index.md",
            "schema/policies",
            "schema/ingest.md",
            "schema/citations.md",
            "schema/conflicts.md",
            "schema/writeback.md",
            "schema/taxonomy.md",
        ):
            path = self.root / relative
            self.assertTrue(path.exists(), relative)
        schema_index = (self.root / "schema" / "index.md").read_text(encoding="utf-8")
        self.assertIn("运行时规则", schema_index)
        self.assertIn("产品运行时", schema_index)
        self.assertIn("schema/policies/", schema_index)

    def test_ensure_layout_bootstraps_protocol_library_and_state(self) -> None:
        for relative in (
            "schema/protocols/index.md",
            "schema/protocols/general/index.md",
            "schema/protocols/general/taxonomy.md",
            "schema/protocols/investing/index.md",
            "schema/protocols/research/index.md",
            "schema/protocols/product/index.md",
            "schema/protocols/ops/index.md",
        ):
            self.assertTrue((self.root / relative).exists(), relative)
        state = load_protocol_state(self.root)
        available_protocols = state.get("available_protocols") or []
        self.assertEqual(state.get("active_protocol"), "general")
        self.assertIn("investing", available_protocols)
        self.assertIn("research", available_protocols)
        self.assertIn("product", available_protocols)
        self.assertIn("ops", available_protocols)
        schema_index = (self.root / "schema" / "index.md").read_text(encoding="utf-8")
        self.assertIn("协议规则", schema_index)

    def test_ensure_layout_bootstraps_runtime_dashboard_files(self) -> None:
        for relative, marker in (
            ("wiki/indexes/furnace-center.md", "炉心面板"),
            ("wiki/indexes/execution-center.md", "执行中心"),
            ("wiki/indexes/execution-audit.md", "执行审计"),
            ("wiki/indexes/review-center.md", "审阅中心"),
            ("wiki/indexes/graph-view.md", "报告证据图谱"),
        ):
            path = self.root / relative
            self.assertTrue(path.exists(), relative)
            self.assertIn(marker, path.read_text(encoding="utf-8"))

    def test_ensure_layout_does_not_overwrite_existing_dashboard_files(self) -> None:
        graph_view = self.root / "wiki" / "indexes" / "graph-view.md"
        graph_view.write_text("# User Owned Graph View\n\nkeep me until compile\n", encoding="utf-8")

        ensure_layout(self.root)

        self.assertIn("User Owned Graph View", graph_view.read_text(encoding="utf-8"))

    def test_lint_reports_execution_consistency_issue_when_revert_receipt_keeps_manual_link_active(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))

        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-action",
                        "kind": "add-source-concept-link",
                        "title": "Manual safe apply link",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )
        dry_run = apply_machine_memory_action(self.root, "manual-link-action", dry_run=True)
        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        apply_machine_memory_action(
            self.root,
            "manual-link-action",
            note="Safe apply for consistency lint.",
            bundle_path=dry_run["bundle_path"],
        )
        revert_machine_memory_action(self.root, "manual-link-action", note="Rollback before lint.")
        manual_state_path = self.root / ".aiwiki" / "state" / "manual-links.json"
        manual_state = json.loads(manual_state_path.read_text(encoding="utf-8"))
        manual_state["source_to_concept"][0]["active"] = True
        manual_state_path.write_text(json.dumps(manual_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        lint = lint_wiki(self.root)
        report_text = (self.root / lint["path"]).read_text(encoding="utf-8")
        self.assertIn("Execution consistency issue for action `manual-link-action`", report_text)
        self.assertIn("最新 receipt 已是 revert，但 manual-link state 仍然 active", report_text)

    def test_revert_concept_rewrite_restores_previous_summary_and_shell_controls(self) -> None:
        prepared = self._prepare_concept_rewrite_proposal()
        concept_page = prepared["concept_page"]
        proposal_path = prepared["proposal_path"]
        slug = str(prepared["slug"])

        review_concept_rewrite(self.root, slug, "accepted", note="Looks grounded.")
        apply_concept_rewrite(self.root, slug, note="Apply accepted rewrite.")

        applied_shell = shell_status(self.root)
        rewrite_controls = {proposal["slug"]: proposal for proposal in applied_shell["review_controls"]["rewrite_proposals"]}
        self.assertTrue(rewrite_controls[slug]["can_revert"])
        self.assertFalse(rewrite_controls[slug]["can_apply"])

        reverted = revert_concept_rewrite(self.root, slug, note="Restore prior synthesis.")

        self.assertEqual(reverted["status"], "accepted")
        self.assertTrue(reverted["receipt_path"])
        restored = concept_page.read_text(encoding="utf-8")
        self.assertIn("Existing synthesis", restored)
        self.assertNotIn("Rewritten synthesis", restored)
        receipts = load_jsonl_documents(execution_receipt_history_path(self.root))
        rewrite_receipts = [receipt for receipt in receipts if receipt.get("subject_kind") == "concept_rewrite"]
        self.assertEqual([receipt["operation"] for receipt in rewrite_receipts[-2:]], ["apply", "revert"])
        self.assertEqual(rewrite_receipts[-1]["domain"], "non_core_semantic")
        self.assertTrue(rewrite_receipts[-1]["before_hash"])
        self.assertTrue(rewrite_receipts[-1]["after_hash"])
        self.assertEqual(rewrite_receipts[-1]["autonomy_decision"]["execution_strategy"], "semantic_revert")

        reverted_shell = shell_status(self.root)
        reverted_controls = {proposal["slug"]: proposal for proposal in reverted_shell["review_controls"]["rewrite_proposals"]}
        self.assertTrue(reverted_controls[slug]["can_apply"])
        self.assertFalse(reverted_controls[slug]["can_revert"])
        self.assertEqual(reverted_controls[slug]["current_status"], "accepted")

        proposal_text = proposal_path.read_text(encoding="utf-8")
        self.assertIn("Reverted at", proposal_text)
        cognitive_history = (self.root / "wiki" / "indexes" / "cognitive-history.md").read_text(encoding="utf-8")
        self.assertIn("Concept Rewrite 事件", cognitive_history)
        self.assertIn("revert -> accepted", cognitive_history)

    def test_apply_concept_rewrite_rolls_back_when_receipt_write_fails(self) -> None:
        prepared = self._prepare_concept_rewrite_proposal()
        concept_page = prepared["concept_page"]
        slug = str(prepared["slug"])

        review_concept_rewrite(self.root, slug, "accepted", note="Looks grounded.")
        original_page = concept_page.read_bytes()
        original_state = concept_rewrite_state_path(self.root).read_bytes()
        original_runtime = runtime_history_path(self.root).read_bytes()
        receipt_history = execution_receipt_history_path(self.root)
        original_receipts = receipt_history.read_bytes() if receipt_history.exists() else b""

        with patch("aiwiki.execution.concept_rewrite.write_execution_receipt", side_effect=RuntimeError("receipt down")):
            with self.assertRaisesRegex(RuntimeError, "receipt down"):
                apply_concept_rewrite(self.root, slug, note="Apply should rollback.")

        self.assertEqual(concept_page.read_bytes(), original_page)
        self.assertEqual(concept_rewrite_state_path(self.root).read_bytes(), original_state)
        self.assertEqual(runtime_history_path(self.root).read_bytes(), original_runtime)
        self.assertEqual(receipt_history.read_bytes() if receipt_history.exists() else b"", original_receipts)
        self.assertIn("Existing synthesis", concept_page.read_text(encoding="utf-8"))
        self.assertNotIn("Rewritten synthesis", concept_page.read_text(encoding="utf-8"))

    def test_apply_machine_memory_action_writes_manual_link_state(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))
        concept_path = self.root / "wiki" / "concepts" / f"{concept_slug}.md"
        before_signature = parse_frontmatter(concept_path.read_text(encoding="utf-8"))["source_signature"]

        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-action",
                        "kind": "add-source-concept-link",
                        "title": "Manual safe apply link",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )
        dry_run = apply_machine_memory_action(self.root, "manual-link-action", dry_run=True)
        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        result = apply_machine_memory_action(
            self.root,
            "manual-link-action",
            note="Safe apply for test.",
            bundle_path=dry_run["bundle_path"],
        )

        self.assertEqual(result["status"], "resolved")
        manual_link_state = json.loads(
            (self.root / ".aiwiki" / "state" / "manual-links.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manual_link_state["source_to_concept"][0]["source_id"], entry["id"])
        self.assertEqual(manual_link_state["source_to_concept"][0]["concept_slug"], concept_slug)
        self.assertIn("receipt_path", result)
        receipt = json.loads((self.root / result["receipt_path"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt["kind"], "execution-receipt")
        self.assertEqual(receipt["action_id"], "manual-link-action")
        after_signature = parse_frontmatter(concept_path.read_text(encoding="utf-8"))["source_signature"]
        self.assertNotEqual(before_signature, after_signature)

    def test_apply_machine_memory_action_dry_run_returns_bundle_without_mutation(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))

        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-action",
                        "kind": "add-source-concept-link",
                        "title": "Manual safe apply link",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )

        result = apply_machine_memory_action(self.root, "manual-link-action", dry_run=True)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["status"], "accepted")
        self.assertIn("bundle", result)
        self.assertEqual(result["bundle"]["kind"], "execution-bundle")
        self.assertEqual(result["bundle"]["action_id"], "manual-link-action")
        self.assertTrue(result["bundle"]["digest"])
        self.assertTrue(result["preview"])
        self.assertFalse((self.root / ".aiwiki" / "state" / "manual-links.json").exists())
        state = json.loads((self.root / ".aiwiki" / "state" / "machine-memory-actions.json").read_text(encoding="utf-8"))
        action = next(action for action in state["actions"] if action["id"] == "manual-link-action")
        self.assertEqual(action["status"], "accepted")

    def test_apply_machine_memory_action_rejects_inactive_action(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))

        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "inactive-link-action",
                        "kind": "add-source-concept-link",
                        "title": "Inactive safe apply link",
                        "reason": "Stale link action.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": False,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )

        with self.assertRaises(RuntimeError):
            apply_machine_memory_action(self.root, "inactive-link-action", note="Should fail.")

    def test_apply_machine_memory_action_requires_bundle_file(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))

        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-action",
                        "kind": "add-source-concept-link",
                        "title": "Manual safe apply link",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )

        with self.assertRaises(FileNotFoundError):
            apply_machine_memory_action(self.root, "manual-link-action", note="Should fail without bundle.")

    def test_apply_machine_memory_action_rejects_stale_bundle(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))

        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-action",
                        "kind": "add-source-concept-link",
                        "title": "Manual safe apply link",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )
        dry_run = apply_machine_memory_action(self.root, "manual-link-action", dry_run=True)
        state = load_machine_memory_action_state(self.root)
        state["actions"][0]["title"] = "Manual safe apply link after state changed"
        save_machine_memory_action_state(self.root, state)

        with self.assertRaises(RuntimeError) as ctx:
            apply_machine_memory_action(
                self.root,
                "manual-link-action",
                note="Should fail with stale bundle.",
                bundle_path=dry_run["bundle_path"],
            )
        message = str(ctx.exception)
        self.assertIn("Execution bundle is stale", message)
        self.assertIn("apply-action manual-link-action --dry-run", message)
        self.assertIn("apply-action manual-link-action", message)

    def test_lint_reports_missing_execution_receipt(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))

        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-action",
                        "kind": "add-source-concept-link",
                        "title": "Manual safe apply link",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )
        dry_run = apply_machine_memory_action(self.root, "manual-link-action", dry_run=True)
        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = apply_machine_memory_action(
            self.root,
            "manual-link-action",
            note="Safe apply for receipt test.",
            bundle_path=dry_run["bundle_path"],
        )
        (self.root / result["receipt_path"]).unlink()

        lint = lint_wiki(self.root)
        report_text = (self.root / lint["path"]).read_text(encoding="utf-8")
        self.assertIn("Referenced execution receipt does not exist for action `manual-link-action`.", report_text)

    def test_revert_machine_memory_action_deactivates_manual_link_and_writes_revert_receipt(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))

        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-action",
                        "kind": "add-source-concept-link",
                        "title": "Manual safe apply link",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )
        dry_run = apply_machine_memory_action(self.root, "manual-link-action", dry_run=True)
        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        apply_machine_memory_action(
            self.root,
            "manual-link-action",
            note="Apply before revert test.",
            bundle_path=dry_run["bundle_path"],
        )
        apply_receipt_path = self.root / "output/control/execution-receipts/manual-link-action.json"
        self.assertTrue(apply_receipt_path.exists())
        apply_receipt_before = json.loads(apply_receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(apply_receipt_before["operation"], "apply")

        result = revert_machine_memory_action(self.root, "manual-link-action", note="Rollback this safe apply.")

        self.assertEqual(result["status"], "proposed")
        self.assertTrue(apply_receipt_path.exists())
        self.assertEqual(json.loads(apply_receipt_path.read_text(encoding="utf-8"))["operation"], "apply")
        manual_link_state = json.loads((self.root / ".aiwiki" / "state" / "manual-links.json").read_text(encoding="utf-8"))
        self.assertFalse(manual_link_state["source_to_concept"][0]["active"])
        receipt = json.loads((self.root / result["receipt_path"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt["kind"], "execution-receipt")
        self.assertEqual(receipt["operation"], "revert")
        self.assertTrue(result["receipt_path"].endswith("reverts/manual-link-action.json"))
        self.assertEqual(receipt["receipt_path"], result["receipt_path"])
        self.assertEqual(receipt["bundle"]["status"], "proposed")
        history_lines = (self.root / ".aiwiki" / "state" / "execution-receipts.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(history_lines), 2)
        self.assertEqual([json.loads(line)["operation"] for line in history_lines], ["apply", "revert"])
        state = json.loads((self.root / ".aiwiki" / "state" / "machine-memory-actions.json").read_text(encoding="utf-8"))
        action = next(action for action in state["actions"] if action["id"] == "manual-link-action")
        self.assertEqual(action["status"], "proposed")
        self.assertEqual(action["last_receipt_path"], result["receipt_path"])

    def test_revert_machine_memory_action_rejects_non_apply_receipt(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))

        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-action",
                        "kind": "add-source-concept-link",
                        "title": "Manual safe apply link",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )
        dry_run = apply_machine_memory_action(self.root, "manual-link-action", dry_run=True)
        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        apply_machine_memory_action(
            self.root,
            "manual-link-action",
            note="Apply before double revert test.",
            bundle_path=dry_run["bundle_path"],
        )
        revert_machine_memory_action(self.root, "manual-link-action", note="First revert.")

        with self.assertRaises(RuntimeError):
            revert_machine_memory_action(self.root, "manual-link-action", note="Second revert should fail.")

    def test_lint_warns_when_curated_page_has_no_structured_citations(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        decision_path = self.root / decision["path"]
        decision_text = decision_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(decision_text)
        frontmatter["citations"] = []
        decision_path.write_text(
            f"{render_frontmatter(frontmatter)}\n\n{strip_frontmatter(decision_text).lstrip()}",
            encoding="utf-8",
        )

        lint = lint_wiki(self.root)

        report_text = (self.root / lint["path"]).read_text(encoding="utf-8")
        self.assertIn("Decision page is missing structured `citations` metadata.", report_text)

    def test_review_page_repairs_placeholder_asset_sections_before_lint(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        review_page(
            self.root,
            decision["path"],
            "approved",
            note="Approved after review.",
        )

        lint = lint_wiki(self.root)

        report_text = (self.root / lint["path"]).read_text(encoding="utf-8")
        decision_text = (self.root / decision["path"]).read_text(encoding="utf-8")
        self.assertNotIn("Pending counter evidence.", decision_text)
        self.assertNotIn("Decision page still has placeholder `Counter Evidence` content.", report_text)

    def test_repair_curated_page_body_replaces_generic_fallback_sections(self) -> None:
        body = """# AOS C2 Dogfood Live Proof Judgment

## Investment Judgment
- Filed from `output/reports/proof.md`; review the supporting artifact before confirmation.

## Drivers And Catalysts
- Evidence is preserved in the supporting artifact `output/reports/proof.md`.

## Risks And Invalidation
- No explicit counter evidence was found in the filed artifact.

## Confidence And Watchlist
- Revisit after `none` or when cited evidence changes.

## Supporting Artifact
# Proof Report

## 结论
真实判断：dogfood live proof 已形成可审计证据链。

## 关键证据
- 证据链贯通 raw 到 wiki 到 output。

## 反证与不确定性
- 仍需补充负面验证。

## 下次观察信号
- 后续 source checksum 变化时复审。
"""

        repaired = repair_curated_page_body(
            kind="judgment",
            protocol="investing",
            body=body,
            artifact_ref="output/reports/proof.md",
            revisit_after="",
            escalate_after="",
        )

        self.assertIn("- 真实判断：dogfood live proof 已形成可审计证据链。", repaired)
        self.assertIn("- 证据链贯通 raw 到 wiki 到 output。", repaired)
        self.assertIn("- 仍需补充负面验证。", repaired)
        self.assertIn("- 后续 source checksum 变化时复审。", repaired)
        self.assertNotIn("review the supporting artifact before confirmation", repaired)
        self.assertNotIn("Evidence is preserved in the supporting artifact", repaired)

    def test_repair_curated_page_body_replaces_default_next_signals_asset_section(self) -> None:
        body = """# AOS C2 Dogfood Live Proof Judgment

## Next Signals
- Pending next signals.
- Default revisit window: `none`
- Default escalation window: `none`

## Supporting Artifact
# Proof Report

## 下次观察信号
- Source checksum drift should trigger review.
"""

        repaired = repair_curated_page_body(
            kind="judgment",
            protocol="investing",
            body=body,
            artifact_ref="output/reports/proof.md",
            revisit_after="",
            escalate_after="",
        )

        self.assertIn("- Source checksum drift should trigger review.", repaired)
        self.assertNotIn("Pending next signals.", repaired)
        self.assertNotIn("Default revisit window:", repaired)
        self.assertNotIn("Default escalation window:", repaired)

    def test_repair_curated_page_body_preserves_manual_section_with_default_window_line(self) -> None:
        body = """# Manual Decision

## Catalysts And Revisit
- Manual reviewer checkpoint after partner launch.
- Revisit after `none` or when cited evidence changes.

## Supporting Artifact
# Proof Report

## 下次观察信号
- Source checksum drift should trigger review.
"""

        repaired = repair_curated_page_body(
            kind="decision",
            protocol="investing",
            body=body,
            artifact_ref="output/reports/proof.md",
            revisit_after="",
            escalate_after="",
        )

        self.assertIn("- Manual reviewer checkpoint after partner launch.", repaired)
        self.assertIn("- Revisit after `none` or when cited evidence changes.", repaired)
        self.assertNotIn("- Source checksum drift should trigger review.\n\n## Supporting Artifact", repaired)

    def test_review_page_refreshes_generated_hints_without_overwriting_manual_frontmatter(self) -> None:
        path = self.root / "wiki" / "judgments" / "manual-investing.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        frontmatter = {
            "kind": "judgment",
            "status": "proposed",
            "title": "Manual Investing Judgment",
            "protocol": "investing",
            "source_files": ["output/reports/manual.md"],
            "thesis": "Old supporting thesis.",
            "counter_evidence": ["Old supporting risk."],
            "invalidation_rule": "Manual frontmatter invalidation must stay.",
            "next_signals": ["Old supporting signal."],
        }
        body = """# Manual Investing Judgment

## Investment Judgment
- Manual body thesis.

## Drivers And Catalysts
- Manual body catalyst.

## Risks And Invalidation
- Manual body risk.

## Confidence And Watchlist
- Manual body signal.
- Revisit after `none` or when cited evidence changes.

## Supporting Artifact
# Old Report

## 结论
Old supporting thesis.

## 反证与不确定性
- Old supporting risk.

## 下次观察信号
- Old supporting signal.
"""
        path.write_text(f"{render_frontmatter(frontmatter)}\n\n{body}", encoding="utf-8")

        review_page(self.root, "wiki/judgments/manual-investing.md", "confirmed", confidence="high")

        updated = path.read_text(encoding="utf-8")
        updated_frontmatter = parse_frontmatter(updated)
        self.assertEqual(updated_frontmatter["thesis"], "Manual body thesis.")
        self.assertEqual(updated_frontmatter["counter_evidence"], ["Manual body risk."])
        self.assertEqual(updated_frontmatter["next_signals"], ["Manual body signal.", "Revisit after `none` or when cited evidence changes."])
        self.assertEqual(updated_frontmatter["invalidation_rule"], "Manual frontmatter invalidation must stay.")

    def test_lint_warns_when_elixir_has_placeholder_variant(self) -> None:
        elixir_dir = self.root / "wiki" / "elixirs"
        elixir_dir.mkdir(parents=True, exist_ok=True)
        (elixir_dir / "placeholder.md").write_text("# Elixir\n\n## Thesis\n- pending refinement\n", encoding="utf-8")

        lint = lint_wiki(self.root)

        report_text = (self.root / lint["path"]).read_text(encoding="utf-8")
        self.assertIn("Elixir page still has placeholder `Pending refinement` content.", report_text)

    def test_lint_warns_when_reviewed_judgment_has_citation_drift_and_snapshot_gap(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Will transformer inference cost keep rising?", "report")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")
        review_page(
            self.root,
            judgment["path"],
            "confirmed",
            note="Confirmed before evidence changed.",
            confidence="high",
        )

        (self.root / entry["stored_path"]).write_text(
            "# Transformer Scaling\n\nTransformers still benefit from scale.\nNew serving optimizations changed inference cost assumptions.\n",
            encoding="utf-8",
        )
        compile_wiki(self.root)

        judgment_path = self.root / judgment["path"]
        judgment_text = judgment_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(judgment_text)
        frontmatter["citation_snapshots"] = []
        judgment_path.write_text(
            f"{render_frontmatter(frontmatter)}\n\n{strip_frontmatter(judgment_text).lstrip()}",
            encoding="utf-8",
        )

        lint = lint_wiki(self.root)

        report_text = (self.root / lint["path"]).read_text(encoding="utf-8")
        self.assertIn("Judgment page is missing `citation_snapshots` metadata.", report_text)
        self.assertIn("Judgment page has citation snapshot gaps", report_text)
        self.assertIn("Reviewed judgment page has citation drift", report_text)

    def test_repair_plan_uses_protocol_specific_proposal_hints(self) -> None:
        self._seed_machine_memory_actions()
        set_active_protocol(self.root, "research")

        compile_wiki(self.root)

        memory = json.loads((self.root / ".aiwiki" / "state" / "machine-memory.json").read_text(encoding="utf-8"))
        proposals = memory["health"]["repair_plan"]["execution_proposals"]
        self.assertTrue(proposals)
        self.assertEqual(proposals[0]["protocol"], "research")
        self.assertIn("benchmark", proposals[0]["summary"].lower())

    def test_repair_plan_exposes_page_level_patch_steps(self) -> None:
        self._seed_machine_memory_actions()

        compile_wiki(self.root)

        memory = json.loads((self.root / ".aiwiki" / "state" / "machine-memory.json").read_text(encoding="utf-8"))
        proposals = memory["health"]["repair_plan"]["execution_proposals"]
        self.assertTrue(proposals)
        first = proposals[0]
        self.assertTrue(first["page_patch_plan"])
        self.assertIn("path", first["page_patch_plan"][0])
        self.assertIn("sections", first["page_patch_plan"][0])
        self.assertIn("proposal_path", first)
        repair_plan = (self.root / "wiki" / "indexes" / "machine-memory-repair-plan.md").read_text(encoding="utf-8")
        self.assertIn("mode `", repair_plan)
        proposal_page = self.root / first["proposal_path"]
        self.assertTrue(proposal_page.exists())
        self.assertIn("## Page-Level Patch Plan", proposal_page.read_text(encoding="utf-8"))

    def test_apply_and_revert_citation_snapshot_refresh_action_updates_judgment_frontmatter(self) -> None:
        _, judgment, action = self._prepare_citation_snapshot_refresh_action()

        review_machine_memory_action(self.root, action["id"], "accepted", note="Queue safe apply.")
        judgment_path = self.root / judgment["path"]
        before_frontmatter = parse_frontmatter(judgment_path.read_text(encoding="utf-8"))

        dry_run = apply_machine_memory_action(self.root, action["id"], dry_run=True)
        self.assertEqual(dry_run["apply_mode"], "citation-snapshot-refresh")
        self.assertEqual(dry_run["bundle"]["policy_decision"], "allow")
        self.assertEqual(dry_run["bundle"]["execution_band"], "bundle-safe-apply")
        self.assertTrue(dry_run["bundle"]["rollback_summary"])

        preview = dry_run["preview"]
        self.assertEqual(preview["previous_citation_snapshots"], before_frontmatter["citation_snapshots"])
        self.assertNotEqual(preview["updated_citation_snapshots"], before_frontmatter["citation_snapshots"])

        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        apply_result = apply_machine_memory_action(
            self.root,
            action["id"],
            note="Refresh citation snapshots.",
            bundle_path=dry_run["bundle_path"],
        )
        self.assertEqual(apply_result["apply_mode"], "citation-snapshot-refresh")

        applied_frontmatter = parse_frontmatter(judgment_path.read_text(encoding="utf-8"))
        self.assertEqual(applied_frontmatter["citation_snapshots"], preview["updated_citation_snapshots"])

        revert_machine_memory_action(self.root, action["id"], note="Rollback citation snapshot refresh.")
        reverted_frontmatter = parse_frontmatter(judgment_path.read_text(encoding="utf-8"))
        self.assertEqual(reverted_frontmatter["citation_snapshots"], preview["previous_citation_snapshots"])

        state = load_machine_memory_action_state(self.root)
        refreshed = next(item for item in state["actions"] if item["id"] == action["id"])
        self.assertEqual(refreshed["status"], "proposed")

    def test_apply_and_revert_monitor_bridge_concept_action(self) -> None:
        self._seed_machine_memory_actions()
        compile_wiki(self.root)

        state = load_machine_memory_action_state(self.root)
        bridge_action = next(
            (a for a in state["actions"] if a["kind"] == "monitor-bridge-concept" and a["active"]),
            None,
        )
        self.assertIsNotNone(bridge_action, "Expected at least one active bridge-concept action.")

        review_machine_memory_action(self.root, bridge_action["id"], "accepted", note="Accept bridge monitor.")

        dry_run = apply_machine_memory_action(self.root, bridge_action["id"], dry_run=True)
        self.assertEqual(dry_run["apply_mode"], "resolve-monitor")
        self.assertTrue(dry_run["dry_run"])

        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        apply_result = apply_machine_memory_action(
            self.root,
            bridge_action["id"],
            note="Resolve bridge concept monitor.",
            bundle_path=dry_run["bundle_path"],
        )
        self.assertEqual(apply_result["status"], "resolved")
        self.assertEqual(apply_result["apply_mode"], "resolve-monitor")
        self.assertTrue((self.root / apply_result["receipt_path"]).exists())

        revert_machine_memory_action(self.root, bridge_action["id"], note="Undo resolve.")
        state_after = load_machine_memory_action_state(self.root)
        reverted = next(a for a in state_after["actions"] if a["id"] == bridge_action["id"])
        self.assertEqual(reverted["status"], "proposed")

    def test_apply_split_overloaded_concept_action_auto_retires_concept(self) -> None:
        """P4-19a: split-overloaded-concept apply 完成后联动 retire concept，receipt 含 auto_retired_concept."""
        self._seed_machine_memory_actions()
        compile_wiki(self.root)

        state = load_machine_memory_action_state(self.root)
        overloaded_action = next(
            (a for a in state["actions"] if a["kind"] == "split-overloaded-concept" and a["active"]),
            None,
        )
        self.assertIsNotNone(overloaded_action, "Expected at least one active split-overloaded-concept action.")
        slug = (overloaded_action["concept_slugs"] or [None])[0]
        self.assertTrue(slug)

        review_machine_memory_action(self.root, overloaded_action["id"], "accepted", note="Accept overloaded action.")

        dry_run = apply_machine_memory_action(self.root, overloaded_action["id"], dry_run=True)
        self.assertEqual(dry_run["apply_mode"], "resolve-monitor")
        # auto_retired_concept 不应出现在 dry-run receipt
        self.assertNotIn("auto_retired_concept", dry_run)

        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        apply_result = apply_machine_memory_action(
            self.root,
            overloaded_action["id"],
            note="Resolve overloaded concept and auto-retire.",
            bundle_path=dry_run["bundle_path"],
        )
        self.assertEqual(apply_result["status"], "resolved")
        self.assertEqual(apply_result["apply_mode"], "resolve-monitor")
        # 关键：自动 retire 联动
        self.assertEqual(apply_result.get("auto_retired_concept"), slug)
        self.assertNotIn("auto_retire_error", apply_result)

        # 验证 lifecycle 状态确实已变 retired
        lifecycle = load_knowledge_lifecycle_state(self.root)
        retired_entry = next(
            (e for e in lifecycle["entries"] if Path(e["path"]).stem == slug and e["kind"] == "concept"),
            None,
        )
        self.assertIsNotNone(retired_entry)
        self.assertEqual(retired_entry["override_state"], "retired")
        self.assertTrue(retired_entry["override_active"])

    def test_apply_split_overloaded_concept_receipt_failure_rolls_back_auto_retire(self) -> None:
        self._seed_machine_memory_actions()
        compile_wiki(self.root)

        state = load_machine_memory_action_state(self.root)
        overloaded_action = next(
            (a for a in state["actions"] if a["kind"] == "split-overloaded-concept" and a["active"]),
            None,
        )
        self.assertIsNotNone(overloaded_action)
        assert overloaded_action is not None
        slug = (overloaded_action["concept_slugs"] or [None])[0]
        self.assertTrue(slug)

        review_machine_memory_action(self.root, overloaded_action["id"], "accepted", note="Accept overloaded action.")
        dry_run = apply_machine_memory_action(self.root, overloaded_action["id"], dry_run=True)
        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        override_before = json.dumps(load_knowledge_lifecycle_override_state(self.root), sort_keys=True)

        with (
            patch(
                "aiwiki.execution.machine_memory_actions.append_execution_receipt_history",
                side_effect=RuntimeError("history failed"),
            ),
            self.assertRaises(MachineMemoryActionReceiptError),
        ):
            apply_machine_memory_action(
                self.root,
                overloaded_action["id"],
                note="Resolve overloaded concept and auto-retire.",
                bundle_path=dry_run["bundle_path"],
            )

        self.assertEqual(json.dumps(load_knowledge_lifecycle_override_state(self.root), sort_keys=True), override_before)
        lifecycle = load_knowledge_lifecycle_state(self.root)
        entry = next((e for e in lifecycle["entries"] if Path(e["path"]).stem == slug and e["kind"] == "concept"), None)
        if entry is not None:
            self.assertNotEqual(entry.get("override_state"), "retired")
        refreshed_actions = load_machine_memory_action_state(self.root)["actions"]
        refreshed = next(action for action in refreshed_actions if action["id"] == overloaded_action["id"])
        self.assertEqual(refreshed["status"], "accepted")
        self.assertFalse((self.root / "output" / "control" / "execution-receipts" / f"{overloaded_action['id']}.json").exists())

    def test_apply_split_overloaded_concept_skips_active_corpus_softly(self) -> None:
        """F-new-13 (Round 6): active-corpus concept retire fails softly with auto_retire_skipped_active_corpus=True."""
        from unittest.mock import patch

        self._seed_machine_memory_actions()
        compile_wiki(self.root)

        state = load_machine_memory_action_state(self.root)
        overloaded_action = next(
            (a for a in state["actions"] if a["kind"] == "split-overloaded-concept" and a["active"]),
            None,
        )
        self.assertIsNotNone(overloaded_action)
        review_machine_memory_action(self.root, overloaded_action["id"], "accepted", note="Accept.")
        dry_run = apply_machine_memory_action(self.root, overloaded_action["id"], dry_run=True)
        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # Patch retire_concept to raise the active-corpus RuntimeError as if the concept
        # were still referenced by recent sources.
        with patch(
            "aiwiki.execution.lifecycle.retire_concept",
            side_effect=RuntimeError("Active-corpus concept cannot transition to retired."),
        ):
            apply_result = apply_machine_memory_action(
                self.root,
                overloaded_action["id"],
                note="Resolve and try auto-retire.",
                bundle_path=dry_run["bundle_path"],
            )

        self.assertEqual(apply_result["status"], "resolved")
        # 软失败：标记 skipped 而非 error，且不阻断 apply
        self.assertTrue(apply_result.get("auto_retire_skipped_active_corpus"))
        self.assertNotIn("auto_retired_concept", apply_result)
        self.assertNotIn("auto_retire_error", apply_result)

    def test_lint_reports_missing_indexes_and_broken_concept_source_refs(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        (self.root / "wiki" / "indexes" / "index.md").unlink()
        (self.root / "wiki" / "indexes" / "machine-memory.md").unlink()
        (self.root / "wiki" / "indexes" / "furnace-center.md").unlink()
        (self.root / "wiki" / "indexes" / "review-center.md").unlink()
        (self.root / "wiki" / "indexes" / "graph-view.md").unlink()
        (self.root / "wiki" / "indexes" / "execution-audit.md").unlink()
        (self.root / "wiki" / "indexes" / "machine-memory-topology.md").unlink()
        (self.root / "wiki" / "indexes" / "machine-memory-actions.md").unlink()
        (self.root / "wiki" / "indexes" / "machine-memory-repair-plan.md").unlink()
        (self.root / "wiki" / "indexes" / "execution-center.md").unlink()
        (self.root / "wiki" / "indexes" / "concept-quality.md").unlink()
        (self.root / "wiki" / "indexes" / "rewrite-proposals.md").unlink()
        (self.root / "wiki" / "indexes" / "graph-health.md").unlink()
        (self.root / "wiki" / "indexes" / "drift-report.md").unlink()
        (self.root / ".aiwiki" / "cache" / "machine-memory-graph.json").unlink()
        (self.root / "output" / "control" / "furnace-center.html").unlink()
        (self.root / "output" / "control" / "execution-center.html").unlink()
        (self.root / "output" / "control" / "execution-audit.html").unlink()
        (self.root / "output" / "graph" / "machine-memory.html").unlink()
        (self.root / "output" / "review" / "review-center.html").unlink()
        concept_page = next((self.root / "wiki" / "concepts").glob("*.md"))
        broken = concept_page.read_text(encoding="utf-8").replace("wiki/sources/", "wiki/sources/missing-", 1)
        concept_page.write_text(broken, encoding="utf-8")

        lint = lint_wiki(self.root)
        report_text = (self.root / lint["path"]).read_text(encoding="utf-8")
        self.assertGreaterEqual(lint["counts"]["errors"], 2)
        self.assertTrue((self.root / "wiki" / "indexes" / "furnace-center.md").exists())
        self.assertTrue((self.root / "wiki" / "indexes" / "execution-center.md").exists())
        self.assertTrue((self.root / "wiki" / "indexes" / "execution-audit.md").exists())
        self.assertTrue((self.root / "wiki" / "indexes" / "review-center.md").exists())
        self.assertTrue((self.root / "wiki" / "indexes" / "graph-view.md").exists())
        self.assertIn("Missing master wiki index page.", report_text)
        self.assertIn("Missing machine memory index page.", report_text)
        self.assertIn("Missing machine memory topology page.", report_text)
        self.assertIn("Missing machine memory actions page.", report_text)
        self.assertIn("Missing machine memory repair plan page.", report_text)
        self.assertIn("Missing concept quality page.", report_text)
        self.assertIn("Missing rewrite proposal index page.", report_text)
        self.assertIn("Missing machine memory graph health page.", report_text)
        self.assertIn("Missing machine memory drift report.", report_text)
        self.assertIn("Missing machine memory graph export.", report_text)
        self.assertIn("Missing furnace center HTML view.", report_text)
        self.assertIn("Missing execution center HTML view.", report_text)
        self.assertIn("Missing execution audit HTML view.", report_text)
        self.assertIn("Missing machine memory graph HTML view.", report_text)
        self.assertIn("Missing review center HTML view.", report_text)
        self.assertIn("Concept page references missing source page", report_text)

    def test_lint_reports_missing_execution_bundle(self) -> None:
        self._seed_machine_memory_actions()

        compile_wiki(self.root)

        memory = load_machine_memory(self.root)
        proposal = memory["health"]["repair_plan"]["execution_proposals"][0]
        bundle_path = self.root / proposal["bundle_path"]
        bundle_path.unlink()

        lint = lint_wiki(self.root)
        report_text = (self.root / lint["path"]).read_text(encoding="utf-8")
        self.assertIn(f"Missing execution bundle for action `{proposal['action_id']}`.", report_text)

    def test_lint_reports_missing_output_pack_candidates(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")
        review_page(
            self.root,
            judgment["path"],
            "confirmed",
            note="Confirmed for memo export.",
            confidence="high",
        )
        self._seed_machine_memory_actions()
        compile_wiki(self.root)
        review_machine_memory_action(self.root, "overloaded-concept-latency", "accepted", note="Queue SOP draft.")

        next((self.root / "output" / "packs" / "review").glob("*.md")).unlink()
        next((self.root / "output" / "packs" / "decision-memos").glob("*.md")).unlink()
        next((self.root / "output" / "packs" / "sop-drafts").glob("*.md")).unlink()

        lint = lint_wiki(self.root)
        report_text = (self.root / lint["path"]).read_text(encoding="utf-8")
        self.assertIn("Missing output pack", report_text)

    def test_lint_reports_missing_domain_pilot_scorecard(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        (self.root / "output" / "pilots" / "general.md").unlink()

        lint = lint_wiki(self.root)
        report_text = (self.root / lint["path"]).read_text(encoding="utf-8")
        self.assertIn("Missing domain pilot scorecard", report_text)



def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(LifecycleFlowTests))
    return suite


if __name__ == "__main__":
    unittest.main()
