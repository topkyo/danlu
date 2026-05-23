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
    auto_resolve_machine_memory_actions,
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
    load_archive_candidates_state,
    load_cache_status,
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
from aiwiki.llm import CompletionResult
from aiwiki.runner import auto_process_once, run_ask, run_compile, run_lint, run_nightly, watch_inbox
from tests.test_app import AppFlowTestBase, CapturingClient, FailingVisionClient, StubClient, StubVisionClient

_VALID_REPORT_BODY = (
    "---\nid: query-stub\nkind: output\nformat: report\n---\n\n"
    "# Stub answer\n\n"
    "## 结论\nStubbed conclusion.\n\n"
    "## 关键证据\n"
    "- See wiki/sources/transformer-scaling.md\n"
    "- Secondary evidence point.\n"
    "- Tertiary evidence point.\n\n"
    "## 反证与不确定性\n- None observed in stub.\n\n"
    "## 行动建议\n- Stub follow-up.\n\n"
    "## 下次观察信号\n- Stub revisit signal.\n\n"
    "## 引用\n- wiki/sources/transformer-scaling.md\n"
)


class RuntimeFlowTests(AppFlowTestBase):
    def test_ask_creates_active_corpus_and_runtime_history(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")

        active_corpora = json.loads((self.root / ".aiwiki" / "state" / "active-corpora.json").read_text(encoding="utf-8"))
        self.assertEqual(len(active_corpora["corpora"]), 1)
        corpus = active_corpora["corpora"][0]
        self.assertEqual(corpus["corpus_id"], report["active_corpus_id"])
        self.assertEqual(corpus["status"], "active")
        self.assertEqual(corpus["focus_kind"], "question")
        self.assertIn(entry["id"], corpus["source_ids"])
        self.assertIn(report["path"], corpus["output_refs"])
        self.assertTrue(corpus["expires_at"])

        history_lines = (self.root / ".aiwiki" / "state" / "runtime-history.jsonl").read_text(encoding="utf-8").strip().splitlines()
        last_event = json.loads(history_lines[-1])
        self.assertEqual(last_event["event_type"], "query")
        self.assertEqual(last_event["corpus_id"], report["active_corpus_id"])
        self.assertIn(entry["id"], last_event["source_ids"])

        material_state = json.loads((self.root / ".aiwiki" / "state" / "material-state.json").read_text(encoding="utf-8"))
        record = next(item for item in material_state["entries"] if item["entry_id"] == entry["id"])
        self.assertTrue(record["last_query_hit_at"])
        self.assertIn(report["active_corpus_id"], record["active_corpus_ids"])

    def test_nightly_cools_active_corpora_and_records_runtime_event(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")

        nightly_health(self.root)

        active_corpora = json.loads((self.root / ".aiwiki" / "state" / "active-corpora.json").read_text(encoding="utf-8"))
        corpus = next(item for item in active_corpora["corpora"] if item["corpus_id"] == report["active_corpus_id"])
        self.assertEqual(corpus["status"], "cooling")

        history_lines = (self.root / ".aiwiki" / "state" / "runtime-history.jsonl").read_text(encoding="utf-8").strip().splitlines()
        nightly_events = [json.loads(line) for line in history_lines if json.loads(line)["event_type"] == "nightly"]
        self.assertTrue(nightly_events)
        self.assertIn(report["active_corpus_id"], nightly_events[-1]["cooled_corpus_ids"])

    def test_ask_refreshes_concept_lifecycle_active_corpus_linkage(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")

        lifecycle = load_knowledge_lifecycle_state(self.root)
        linked_concepts = [
            entry for entry in lifecycle["entries"]
            if entry["kind"] == "concept" and report["active_corpus_id"] in entry.get("active_corpus_ids", [])
        ]
        self.assertTrue(linked_concepts)
        self.assertTrue(all(entry["lifecycle_state"] in {"active", "review", "revisit"} for entry in linked_concepts))

    def test_protocol_hinted_material_has_clear_top_protocol_margin(self) -> None:
        self._prepare_stale_protocol_material()

        routing_state = json.loads((self.root / ".aiwiki" / "state" / "material-routing.json").read_text(encoding="utf-8"))
        routing_entry = routing_state["entries"][0]
        self.assertEqual(routing_entry["top_protocols"][0]["protocol"], "investing")
        margin = routing_entry["top_protocols"][0]["total_score"] - routing_entry["top_protocols"][1]["total_score"]
        self.assertGreaterEqual(margin, 0.5)

    def test_protocol_set_updates_dashboard_without_compile(self) -> None:
        set_active_protocol(self.root, "investing")
        payload = (self.root / "wiki" / "indexes" / "protocols.md").read_text(encoding="utf-8")
        self.assertIn("investing", payload)
        self.assertIn("../../schema/protocols/investing/index.md", payload)

    def test_protocol_dashboard_lists_product_and_ops_protocols(self) -> None:
        compile_wiki(self.root)

        payload = (self.root / "wiki" / "indexes" / "protocols.md").read_text(encoding="utf-8")

        self.assertIn("../../schema/protocols/product/index.md", payload)
        self.assertIn("../../schema/protocols/ops/index.md", payload)
        set_active_protocol(self.root, "ops")
        updated = (self.root / "wiki" / "indexes" / "protocols.md").read_text(encoding="utf-8")
        self.assertIn("ops", updated)
        self.assertIn("../../schema/protocols/ops/index.md", updated)

    def test_protocol_dashboard_surfaces_lifecycle_governance_summary(self) -> None:
        backlog_title, retired_title = self._seed_lifecycle_governance_surface_state()

        payload = (self.root / "wiki" / "indexes" / "protocols.md").read_text(encoding="utf-8")

        self.assertIn("## Lifecycle Governance Summary", payload)
        self.assertIn("## Lifecycle Concept Backlog", payload)
        self.assertIn("## Retired Concepts", payload)
        self.assertIn(backlog_title, payload)
        self.assertIn(retired_title, payload)

    def test_protocol_set_keeps_lifecycle_governance_summary_without_compile(self) -> None:
        backlog_title, retired_title = self._seed_lifecycle_governance_surface_state()

        set_active_protocol(self.root, "ops")

        payload = (self.root / "wiki" / "indexes" / "protocols.md").read_text(encoding="utf-8")
        self.assertIn("ops", payload)
        self.assertIn("## Lifecycle Governance Summary", payload)
        self.assertIn(backlog_title, payload)
        self.assertIn(retired_title, payload)

    def test_ask_auto_compiles_and_returns_ranked_concepts_and_indexes(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        result = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        self.assertTrue((self.root / "wiki" / "indexes" / "index.md").exists())
        self.assertTrue(list((self.root / "wiki" / "sources").glob("*.md")))
        self.assertTrue(result["ranked_concepts"])
        self.assertIn("wiki/indexes/log.md", result["index_pages"])
        self.assertIn("wiki/indexes/machine-memory.md", result["index_pages"])
        self.assertIn("wiki/indexes/drift-report.md", result["index_pages"])
        self.assertIn("wiki/indexes/decisions.md", result["index_pages"])
        self.assertIn("wiki/indexes/judgments.md", result["index_pages"])
        self.assertIn("wiki/indexes/review-center.md", result["index_pages"])
        self.assertIn("wiki/indexes/graph-view.md", result["index_pages"])
        self.assertIn("schema/index.md", result["index_pages"])

        report_text = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertIn("优先概念", report_text)
        self.assertIn("优先来源", report_text)
        self.assertIn("## 结论", report_text)
        self.assertIn("## 行动建议", report_text)
        self.assertNotIn("推荐索引页", report_text)
        self.assertNotIn("机器记忆查询计划", report_text)

    def test_ask_reuses_clean_ranking_build_state(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        with patch(
            "aiwiki.app_compile.build_ranking_source_record",
            side_effect=AssertionError("should reuse clean source ranking state"),
        ), patch(
            "aiwiki.app_compile.build_ranking_concept_record",
            side_effect=AssertionError("should reuse clean concept ranking state"),
        ):
            result = ask_question(self.root, "Compare transformer scale and inference cost", "report")

        self.assertTrue(result["ranked_sources"])
        self.assertTrue(result["ranked_concepts"])

    def test_ask_can_override_protocol_and_exposes_protocol_pages(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        set_active_protocol(self.root, "general")

        result = ask_question(self.root, "Compare transformer scale and inference cost", "report", protocol="investing")

        report_text = (self.root / result["path"]).read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(report_text)
        self.assertEqual(result["protocol"], "investing")
        self.assertEqual(frontmatter["protocol"], "investing")
        self.assertIn("wiki/indexes/protocols.md", result["index_pages"])
        self.assertIn("schema/protocols/index.md", result["index_pages"])
        self.assertIn("schema/protocols/investing/index.md", result["protocol_pages"])
        self.assertIn("当前协议：`investing`", report_text)

    def test_ask_uses_protocol_focus_for_source_ranking(self) -> None:
        investing = self.root / "investing.md"
        investing.write_text(
            "# Company Outlook\n\nOutlook thesis catalyst valuation risk invalidation.\n",
            encoding="utf-8",
        )
        generic = self.root / "generic.md"
        generic.write_text(
            "# Generic Outlook\n\nOutlook summary and generic note.\n",
            encoding="utf-8",
        )
        investing_entry = ingest_source(self.root, str(investing), title="Company Outlook")
        ingest_source(self.root, str(generic), title="Generic Outlook")
        compile_wiki(self.root)

        result = ask_question(self.root, "Outlook review", "report", protocol="investing")

        self.assertEqual(result["ranked_sources"][0], investing_entry["id"])

    def test_execution_center_surfaces_recent_dry_runs(self) -> None:
        _, _, action = self._prepare_citation_snapshot_refresh_action()
        review_machine_memory_action(self.root, action["id"], "accepted", note="Ready for dry run.")
        dry_run = apply_machine_memory_action(self.root, action["id"], dry_run=True)
        compile_wiki(self.root)

        dashboard_payload = (self.root / "wiki" / "indexes" / "execution-center.md").read_text(encoding="utf-8")
        html_payload = (self.root / "output" / "control" / "execution-center.html").read_text(encoding="utf-8")

        self.assertIn("## Recent Dry Runs", dashboard_payload)
        self.assertIn(dry_run["dry_run_path"], dashboard_payload)
        self.assertIn("Recent Dry Runs", html_payload)
        self.assertIn(dry_run["dry_run_path"], html_payload)

    def test_execution_audit_surfaces_policy_band_and_capabilities(self) -> None:
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

        compile_wiki(self.root)

        audit_payload = (self.root / "wiki" / "indexes" / "execution-audit.md").read_text(encoding="utf-8")
        actions_payload = (self.root / "wiki" / "indexes" / "machine-memory-actions.md").read_text(encoding="utf-8")
        self.assertIn("bundle-safe-apply", audit_payload)
        self.assertIn("dry-run, bundle-apply, revert-safe, history", audit_payload)
        self.assertIn("band `bundle-safe-apply`", actions_payload)

    def test_nightly_health_persists_planner_execution_history_for_auto_bundle_candidates(self) -> None:
        _, _, action = self._prepare_citation_snapshot_refresh_action()
        review_machine_memory_action(self.root, action["id"], "accepted", note="Queue nightly auto bundle.")
        compile_wiki(self.root)

        result = nightly_health(self.root)
        planner = load_planner_state(self.root)
        executed = next(item for item in planner["executed_actions"] if item.get("action_id") == action["id"])
        nightly_state = json.loads((self.root / ".aiwiki" / "state" / "nightly-health.json").read_text(encoding="utf-8"))

        self.assertGreaterEqual(planner["counts"]["executed_actions"], 1)
        self.assertEqual(executed["source"], "receipt-history")
        self.assertTrue((self.root / executed["bundle_path"]).exists())
        self.assertEqual(result["state_path"], ".aiwiki/state/nightly-health.json")
        self.assertEqual(nightly_state["planner"]["recent_executed_action_ids"][0], action["id"])
        self.assertEqual(result["agent_loop"]["status"], "ok")
        self.assertTrue(result["agent_loop"]["dry_run"])
        self.assertFalse(result["agent_loop"]["side_effects_allowed"])
        self.assertEqual(nightly_state["agent_loop"]["status"], "ok")
        self.assertTrue(nightly_state["agent_loop"]["dry_run"])
        self.assertFalse(nightly_state["agent_loop"]["side_effects_allowed"])

    def test_nightly_auto_consumes_accepted_monitor_actions(self) -> None:
        self._seed_machine_memory_actions()
        compile_wiki(self.root)

        state = load_machine_memory_action_state(self.root)
        bridge = next(a for a in state["actions"] if a["kind"] == "monitor-bridge-concept" and a["active"])
        review_machine_memory_action(self.root, bridge["id"], "accepted", note="Queue nightly auto.")
        compile_wiki(self.root)

        result = nightly_health(self.root)
        auto_applied = result.get("auto_applied", [])
        self.assertNotIn(bridge["id"], {a.get("id") for a in auto_applied})
        refreshed = load_machine_memory_action_state(self.root)
        updated = next(a for a in refreshed["actions"] if a["id"] == bridge["id"])
        self.assertEqual(updated["status"], "accepted")
        self.assertTrue(updated["active"])

    def test_auto_resolve_deferred_monitor_writes_receipt_history_and_audit(self) -> None:
        self._seed_machine_memory_actions()
        compile_wiki(self.root)

        state = load_machine_memory_action_state(self.root)
        bridge = next(a for a in state["actions"] if a["kind"] == "monitor-bridge-concept" and a["active"])

        dry_run = auto_resolve_machine_memory_actions(self.root, dry_run=True)
        dry_item = next(item for item in dry_run["items"] if item["action_id"] == bridge["id"])
        self.assertEqual(dry_item["operation"], "escalate")
        self.assertEqual(dry_item["human_required_reason"], "semantic_judgment_required")
        self.assertFalse((self.root / "output" / "control" / "execution-receipts" / "auto-resolution" / f"{bridge['id']}.json").exists())

        result = auto_resolve_machine_memory_actions(self.root, note="nightly debt triage")
        item = next(entry for entry in result["items"] if entry["action_id"] == bridge["id"])
        self.assertEqual(item["operation"], "escalate")
        receipt_rel = item["result"]["receipt_path"]
        receipt_path = self.root / receipt_rel
        self.assertTrue(receipt_path.exists())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["operation"], "escalate")
        self.assertEqual(receipt["status_after"], "deferred")
        self.assertEqual(receipt["human_required_reason"], "semantic_judgment_required")
        self.assertFalse(receipt["revert_supported"])

        refreshed = load_machine_memory_action_state(self.root)
        updated = next(a for a in refreshed["actions"] if a["id"] == bridge["id"])
        self.assertEqual(updated["status"], "deferred")
        self.assertEqual(updated["pending_review"], "true")
        self.assertEqual(updated["human_required_reason"], "semantic_judgment_required")
        self.assertEqual(updated["last_receipt_path"], receipt_rel)
        self.assertNotEqual(updated["status"], "resolved")

        history_lines = (self.root / ".aiwiki" / "state" / "execution-receipts.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertTrue(any(json.loads(line).get("action_id") == bridge["id"] and json.loads(line).get("operation") == "escalate" for line in history_lines if line.strip()))
        audit_lines = (self.root / ".aiwiki" / "state" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        audit_records = [json.loads(line) for line in audit_lines if line.strip()]
        self.assertTrue(any(record.get("event_type") == "escalate" and record.get("subject", {}).get("id") == bridge["id"] for record in audit_records))

    def test_auto_resolve_skips_already_deferred_human_required_exception(self) -> None:
        self._seed_machine_memory_actions()
        compile_wiki(self.root)

        state = load_machine_memory_action_state(self.root)
        bridge = next(a for a in state["actions"] if a["kind"] == "monitor-bridge-concept" and a["active"])

        first = auto_resolve_machine_memory_actions(self.root, note="initial exceptionization")
        first_item = next(entry for entry in first["items"] if entry["action_id"] == bridge["id"])
        receipt_rel = first_item["result"]["receipt_path"]
        history_path = self.root / ".aiwiki" / "state" / "execution-receipts.jsonl"
        history_before = history_path.read_text(encoding="utf-8")

        second = auto_resolve_machine_memory_actions(self.root, note="rerun should be idempotent")
        second_item = next(entry for entry in second["items"] if entry["action_id"] == bridge["id"])

        self.assertEqual(second_item["operation"], "skip")
        self.assertEqual(second_item["reason_code"], "already_human_required_exception")
        self.assertEqual(history_path.read_text(encoding="utf-8"), history_before)
        refreshed = load_machine_memory_action_state(self.root)
        updated = next(a for a in refreshed["actions"] if a["id"] == bridge["id"])
        self.assertEqual(updated["last_receipt_path"], receipt_rel)

    def test_auto_resolve_review_accept_clears_exception_metadata(self) -> None:
        self._seed_machine_memory_actions()
        compile_wiki(self.root)

        state = load_machine_memory_action_state(self.root)
        bridge = next(a for a in state["actions"] if a["kind"] == "monitor-bridge-concept" and a["active"])

        auto_resolve_machine_memory_actions(self.root, note="mark exception")
        review_machine_memory_action(self.root, bridge["id"], "accepted", note="human reviewed")

        refreshed = load_machine_memory_action_state(self.root)
        updated = next(a for a in refreshed["actions"] if a["id"] == bridge["id"])
        self.assertEqual(updated["status"], "accepted")
        self.assertNotIn("human_required", updated)
        self.assertNotIn("human_required_reason", updated)
        self.assertNotIn("auto_resolution", updated)
        self.assertNotIn("revert_supported", updated)

    def test_auto_resolve_applies_accepted_low_risk_link_action(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-auto",
                        "kind": "add-source-concept-link",
                        "title": "Auto low-risk link",
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

        dry_run = auto_resolve_machine_memory_actions(self.root, dry_run=True, include_proposed=False)
        self.assertEqual(dry_run["counts"]["would_apply"], 1)
        item = dry_run["items"][0]
        self.assertEqual(item["action_id"], "manual-link-auto")
        self.assertEqual(item["operation"], "apply")

        result = auto_resolve_machine_memory_actions(self.root, include_proposed=False, note="auto apply")
        applied = next(entry for entry in result["items"] if entry["action_id"] == "manual-link-auto")
        self.assertEqual(applied["result"]["status"], "resolved")

    def test_auto_resolve_applies_citation_snapshot_refresh_action(self) -> None:
        _, _, action = self._prepare_citation_snapshot_refresh_action()
        review_machine_memory_action(self.root, action["id"], "accepted", note="Ready for auto apply.")
        compile_wiki(self.root)

        dry_run = auto_resolve_machine_memory_actions(self.root, dry_run=True, include_proposed=False)
        self.assertEqual(dry_run["counts"]["would_apply"], 1)
        self.assertEqual(dry_run["items"][0]["action_id"], action["id"])

        result = auto_resolve_machine_memory_actions(self.root, include_proposed=False)
        applied = next(entry for entry in result["items"] if entry["action_id"] == action["id"])

        self.assertEqual(applied["operation"], "apply")
        self.assertEqual(applied["result"]["status"], "resolved")
        receipt = json.loads((self.root / applied["result"]["receipt_path"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt["operation"], "apply")
        self.assertIn("Auto-resolved accepted low-risk action", receipt["note"])
        self.assertEqual(receipt["safe_apply_preview"]["apply_mode"], "citation-snapshot-refresh")

    def test_auto_resolve_mixed_apply_and_escalate_keeps_applied_state(self) -> None:
        self._seed_machine_memory_actions()
        compile_wiki(self.root)
        state = load_machine_memory_action_state(self.root)
        monitor_seed = next(a for a in state["actions"] if a["kind"] == "monitor-bridge-concept" and a["active"])
        concept_slug = str((monitor_seed.get("concept_slugs") or [""])[0])
        source_id = str((monitor_seed.get("source_ids") or [""])[0])
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-auto",
                        "kind": "add-source-concept-link",
                        "title": "Auto low-risk link",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{source_id}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [source_id],
                        "concept_slugs": [concept_slug],
                    },
                    monitor_seed,
                ],
            },
        )

        result = auto_resolve_machine_memory_actions(self.root, note="mixed run")
        self.assertEqual(result["counts"]["applied"], 1)
        self.assertEqual(result["counts"]["escalated"], 1)
        self.assertEqual(result["counts"]["skipped"], 0)
        refreshed = load_machine_memory_action_state(self.root)
        link = next(a for a in refreshed["actions"] if a["id"] == "manual-link-auto")
        monitor = next(a for a in refreshed["actions"] if a["id"] == monitor_seed["id"])
        self.assertEqual(link["status"], "resolved")
        self.assertEqual(monitor["status"], "deferred")
        self.assertEqual(monitor["human_required_reason"], "semantic_judgment_required")

    def test_execution_audit_surfaces_consistency_signal_for_resolved_action_without_receipt(self) -> None:
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
                        "status": "resolved",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )

        compile_wiki(self.root)

        audit_payload = (self.root / "wiki" / "indexes" / "execution-audit.md").read_text(encoding="utf-8")
        self.assertIn("Consistency Signals", audit_payload)
        self.assertIn("resolved，但最新 execution receipt 不是 apply", audit_payload)

    def test_execution_audit_allows_history_only_resolved_monitor_action_without_receipt(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))

        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "monitor-action",
                        "kind": "split-overloaded-concept",
                        "title": "Monitor closed concept",
                        "reason": "Already reviewed as historical noise.",
                        "primary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "resolved",
                        "priority": "low",
                        "active": True,
                        "execution_policy": "closed",
                        "execution_band": "closed",
                        "execution_capabilities": "history",
                        "execution_capability_list": ["history"],
                        "policy_decision": "history",
                    }
                ],
            },
        )

        compile_wiki(self.root)

        audit_payload = (self.root / "wiki" / "indexes" / "execution-audit.md").read_text(encoding="utf-8")
        self.assertIn("Consistency Signals", audit_payload)
        self.assertNotIn("resolved，但最新 execution receipt 不是 apply", audit_payload)

    def test_ask_recompiles_when_raw_source_changes(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        stored_source = self.root / entry["stored_path"]
        stored_source.write_text(
            "# Transformer Scaling\n\nLatency throughput cache locality.\n",
            encoding="utf-8",
        )

        result = ask_question(self.root, "Compare latency and throughput", "report")

        self.assertIn("latency", result["ranked_concepts"])
        self.assertTrue((self.root / "wiki" / "concepts" / "latency.md").exists())
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        self.assertIn("- Pending LLM summary.", source_page.read_text(encoding="utf-8"))

    def test_ask_uses_machine_memory_for_query_planning(self) -> None:
        sample = self.root / "latency.md"
        sample.write_text("# Throughput Notes\n\nLatency throughput cache locality.\n", encoding="utf-8")
        ingest_source(self.root, str(sample), title="Throughput Notes")
        sample_two = self.root / "tail.md"
        sample_two.write_text("# Tail Latency\n\nLatency throughput jitter tradeoffs.\n", encoding="utf-8")
        ingest_source(self.root, str(sample_two), title="Tail Latency")
        compile_wiki(self.root)

        result = ask_question(self.root, "Compare latency tail behavior", "report")

        machine_query = result["machine_memory_query"]
        report_text = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertIn("latency", machine_query["matched_terms"])
        self.assertTrue(any("throughput" in slug for slug in machine_query["ranked_concept_slugs"]))
        self.assertTrue(machine_query["bridge_concept_slugs"])
        self.assertTrue(machine_query["supporting_edges"])
        self.assertTrue(machine_query["query_routes"])
        self.assertTrue(machine_query["touched_component_ids"])
        self.assertTrue(machine_query["touched_components"])
        self.assertTrue(machine_query["query_subgraph"]["edges"])
        self.assertIn("_机器记忆提示：_", report_text)
        self.assertIn("桥接概念", report_text)
        self.assertIn("查询入口", report_text)
        self.assertIn("latency", report_text.lower())

    def test_ask_uses_runtime_query_route_schema_and_updates_shell_summary(self) -> None:
        _, _, action = self._prepare_citation_snapshot_refresh_action()
        runtime_path = self.root / "schema" / "protocols" / "research" / "runtime.yaml"
        runtime_payload = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime_payload["query_routes"] = {
            "default_strategy": "graph-walk",
            "strategy_order": ["graph-walk", "source-first", "concept-first"],
            "source_markers": ["evidencepilot"],
            "graph_markers": ["rootcausepilot"],
        }
        runtime_path.write_text(
            json.dumps(runtime_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        result = ask_question(self.root, "evidencepilot latency benchmark followup", "report", protocol="research")

        machine_query = result["machine_memory_query"]
        self.assertEqual(machine_query["selected_strategy"], "source-first")
        self.assertEqual(machine_query["selection_reason"], "source-markers")
        self.assertIn("evidencepilot", machine_query["matched_source_markers"])

        telemetry = load_query_route_telemetry(self.root)
        self.assertEqual(telemetry["state_path"], ".aiwiki/state/query-route-telemetry.json")
        self.assertEqual(telemetry["last_entry"]["selected_strategy"], "source-first")
        self.assertEqual(telemetry["last_entry"]["planner_next_action_id"], action["id"])
        self.assertGreaterEqual(telemetry["strategy_counts"].get("source-first", 0), 1)
        self.assertGreaterEqual(telemetry["protocol_counts"].get("research", 0), 1)

        shell = shell_status(self.root)
        self.assertEqual(shell["planner"]["next_action"]["action_id"], action["id"])
        self.assertEqual(shell["route_telemetry"]["last_entry"]["selected_strategy"], "source-first")

        written = json.loads(shell_summary_path(self.root).read_text(encoding="utf-8"))
        self.assertEqual(written["planner"]["next_action"]["action_id"], action["id"])
        self.assertEqual(written["route_telemetry"]["last_entry"]["selected_strategy"], "source-first")

        product_shell = (self.root / "output" / "control" / "product-shell.html").read_text(encoding="utf-8")
        self.assertIn("Furnace Product Shell", product_shell)
        self.assertIn("data-default-locale='zh'", product_shell)
        self.assertIn("中文", product_shell)
        self.assertIn("English", product_shell)
        self.assertIn(action["title"], product_shell)
        self.assertIn("source-first", product_shell)
        self.assertIn("../review/review-center.html", product_shell)
        self.assertIn("shell-summary.json", product_shell)

    def test_ask_cache_and_no_cache_paths_match_for_machine_query(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        cached = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        bypassed = ask_question(self.root, "Compare transformer scale and inference cost", "report", no_cache=True)

        cached_query = cached["machine_memory_query"]
        bypassed_query = bypassed["machine_memory_query"]
        self.assertEqual(cached_query, bypassed_query)

        cache_status = load_cache_status(self.root)
        self.assertGreaterEqual(cache_status["stats"]["query_hits"] + cache_status["stats"]["query_misses"], 1)
        self.assertGreaterEqual(cache_status["stats"]["query_bypasses"], 1)
        self.assertEqual(cache_status["last_query"]["bypass"], True)
        self.assertEqual(cache_status["last_query"]["reason"], "no-cache")

    def test_run_compile_replaces_placeholder_summary(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        current = source_page.read_text(encoding="utf-8")
        updated = current.replace("- Pending LLM summary.", "- Transformers benefit from scale, but cost rises with inference demand.")
        result = run_compile(self.root, client=StubClient([updated]), limit=1)
        self.assertEqual(result["pending_pages"], 1)
        self.assertEqual(result["model_selected"], "stub-model")
        self.assertEqual(result["model_final"], "stub-model")
        self.assertTrue(result["contract_validated"])
        self.assertIn("Transformers benefit from scale", source_page.read_text(encoding="utf-8"))
        llm_receipts = [
            json.loads(line)
            for line in (self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(llm_receipts[-1]["event"], "run-compile-summary")
        self.assertEqual(llm_receipts[-1]["model_selected"], "stub-model")

    def test_run_compile_rejects_source_response_that_keeps_placeholder(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        current = source_page.read_text(encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "placeholder state"):
            run_compile(self.root, client=StubClient([current]), limit=1)

    def test_run_compile_enriches_placeholder_concept_summary(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                "- Transformer scale improves capability and raises compute demand.",
            ),
            encoding="utf-8",
        )
        compile_wiki(self.root)
        concept_page = sorted((self.root / "wiki" / "concepts").glob("*.md"))[0]
        self._seed_legacy_placeholder_summary(concept_page)
        target_slug = placeholder_concept_slugs(self.root)[0]
        concept_page = self.root / "wiki" / "concepts" / f"{target_slug}.md"
        current = concept_page.read_text(encoding="utf-8")
        updated = current.replace("- This concept currently appears", "- Enriched concept synthesis appears")

        result = run_compile(self.root, client=StubClient([updated]), limit=1)

        self.assertEqual(result["pending_pages"], 0)
        self.assertEqual(result["pending_concept_pages"], 1)
        self.assertEqual(len(result["updated_concept_pages"]), 1)
        refreshed = concept_page.read_text(encoding="utf-8")
        self.assertIn("Enriched concept synthesis appears", refreshed)

    def test_run_compile_rejects_concept_response_that_keeps_fallback(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                "- Transformer scale improves capability and raises compute demand.",
            ),
            encoding="utf-8",
        )
        compile_wiki(self.root)
        concept_page = sorted((self.root / "wiki" / "concepts").glob("*.md"))[0]
        self._seed_legacy_placeholder_summary(concept_page)
        target_slug = placeholder_concept_slugs(self.root)[0]
        concept_page = self.root / "wiki" / "concepts" / f"{target_slug}.md"
        current = concept_page.read_text(encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "fallback state"):
            run_compile(self.root, client=StubClient([current]), limit=1)

    def test_run_compile_rewrites_weak_non_placeholder_concept(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                "- Transformer scale improves capability and raises compute demand.",
            ),
            encoding="utf-8",
        )
        compile_wiki(self.root)

        self._seed_existing_concept_summaries()
        compile_wiki(self.root)

        memory = load_machine_memory(self.root)
        candidate = memory["health"]["concept_quality"]["rewrite_candidates"][0]
        concept_page = self.root / candidate["path"]
        current = concept_page.read_text(encoding="utf-8")
        updated = current.replace("Existing synthesis", "Rewritten synthesis")

        result = run_compile(self.root, client=StubClient([updated]), limit=1)

        self.assertEqual(result["pending_pages"], 0)
        self.assertEqual(result["pending_concept_pages"], 0)
        self.assertGreaterEqual(result["pending_rewrite_concept_pages"], 1)
        self.assertEqual(len(result["updated_rewrite_concept_pages"]), 0)
        self.assertEqual(len(result["updated_rewrite_proposal_pages"]), 1)
        self.assertIn("Existing synthesis", concept_page.read_text(encoding="utf-8"))
        proposal_page = self.root / result["updated_rewrite_proposal_pages"][0]
        self.assertTrue(proposal_page.exists())
        self.assertIn("Rewritten synthesis", proposal_page.read_text(encoding="utf-8"))

    def test_nightly_prioritizes_pending_reviews_for_active_protocol(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        general_report = ask_question(self.root, "Should we adopt transformer caching?", "report", protocol="general")
        investing_report = ask_question(self.root, "Should we underwrite this thesis?", "report", protocol="investing")
        general_decision = file_back(self.root, general_report["path"], title="General Decision", kind="decision")
        investing_decision = file_back(self.root, investing_report["path"], title="Investing Decision", kind="decision")
        set_active_protocol(self.root, "investing")

        result = nightly_health(self.root)

        state = json.loads((self.root / result["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["protocol"]["active_protocol"], "investing")
        self.assertEqual(state["repair_backlog"]["pending_review_decisions"][0], investing_decision["path"])
        self.assertIn(general_decision["path"], state["repair_backlog"]["pending_review_decisions"])

    def test_run_ask_and_run_lint_write_llm_outputs(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        current = source_page.read_text(encoding="utf-8")
        source_page.write_text(
            current.replace("- Pending LLM summary.", "- Transformer scale improves capability and raises compute demand."),
            encoding="utf-8",
        )

        report_markdown = _VALID_REPORT_BODY
        ask_result = run_ask(
            self.root,
            "Compare transformer scale and inference cost",
            "report",
            client=StubClient([report_markdown]),
        )
        report_path = self.root / ask_result["path"]
        self.assertIn(f"wiki/sources/{entry['id']}.md", report_path.read_text(encoding="utf-8"))
        self.assertEqual(ask_result["model_selected"], "stub-model")
        self.assertEqual(ask_result["model_final"], "stub-model")
        self.assertTrue(ask_result["contract_validated"])

        llm_receipts_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        self.assertTrue(llm_receipts_path.exists())
        llm_receipt = json.loads(llm_receipts_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(llm_receipt["event"], "run-ask")
        self.assertEqual(llm_receipt["model_selected"], "stub-model")
        self.assertEqual(llm_receipt["model_final"], "stub-model")
        self.assertTrue(llm_receipt["contract_validated"])

        runs_log_path = self.root / ".aiwiki" / "logs" / "runs.jsonl"
        self.assertTrue(runs_log_path.exists())
        run_log = json.loads(runs_log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(run_log["event"], "run-ask")
        self.assertEqual(run_log["model_selected"], "stub-model")
        self.assertEqual(run_log["model_final"], "stub-model")
        self.assertTrue(run_log["contract_validated"])

        lint_markdown = "# Semantic Lint Report\n\n- No semantic contradictions detected.\n"
        lint_result = run_lint(self.root, client=StubClient([lint_markdown]))
        semantic_path = self.root / lint_result["semantic_report"]
        self.assertTrue(semantic_path.exists())
        self.assertIn("Semantic Lint Report", semantic_path.read_text(encoding="utf-8"))
        self.assertEqual(lint_result["model_selected"], "stub-model")
        self.assertEqual(lint_result["model_final"], "stub-model")
        self.assertTrue(lint_result["contract_validated"])
        llm_receipt = json.loads(llm_receipts_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(llm_receipt["event"], "run-lint")
        self.assertEqual(llm_receipt["model_selected"], "stub-model")
        self.assertTrue(llm_receipt["contract_validated"])

    def test_run_ask_truncates_append_only_log_context(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                "- Transformer scale improves capability and raises compute demand.",
            ),
            encoding="utf-8",
        )
        compile_wiki(self.root)

        log_page = self.root / "wiki" / "indexes" / "log.md"
        log_page.write_text(
            "# Wiki Log\n\n"
            + "EARLY-MARKER " * 1200
            + "\n\n## recent\n\n"
            + "LATE-MARKER " * 40
            + "\n",
            encoding="utf-8",
        )
        report_markdown = _VALID_REPORT_BODY
        client = CapturingClient(report_markdown)

        run_ask(
            self.root,
            "Compare transformer scale and inference cost",
            "report",
            client=client,
        )

        self.assertIn("LATE-MARKER", client.prompt)
        self.assertNotIn("EARLY-MARKER EARLY-MARKER EARLY-MARKER EARLY-MARKER EARLY-MARKER", client.prompt)

    def test_protocol_related_concept_lifecycle_summary_supports_strong_top2_and_bridge(self) -> None:
        knowledge_lifecycle = {
            "entries": [
                {
                    "kind": "concept",
                    "title": "Direct Research Concept",
                    "path": "wiki/concepts/direct-research.md",
                    "lifecycle_state": "review",
                    "source_ids": ["source-direct"],
                },
                {
                    "kind": "concept",
                    "title": "Strong Secondary Concept",
                    "path": "wiki/concepts/strong-secondary.md",
                    "lifecycle_state": "revisit",
                    "source_ids": ["source-secondary"],
                },
                {
                    "kind": "concept",
                    "title": "Bridge Research Concept",
                    "path": "wiki/concepts/bridge-research.md",
                    "lifecycle_state": "retired",
                    "source_ids": ["source-bridge"],
                },
                {
                    "kind": "concept",
                    "title": "Cold Secondary Concept",
                    "path": "wiki/concepts/cold-secondary.md",
                    "lifecycle_state": "review",
                    "source_ids": ["source-cold-secondary"],
                },
            ]
        }
        material_routing = {
            "entries": [
                {
                    "entry_id": "source-direct",
                    "top_protocols": [
                        {"protocol": "research", "total_score": 3.3, "selected_as": "hot-evidence"},
                        {"protocol": "investing", "total_score": 1.6, "selected_as": "cold-evidence"},
                    ],
                    "protocol_snapshots": [
                        {"protocol": "research", "selected_as": "hot-evidence", "total_score": 3.3, "is_bridge": False}
                    ],
                    "cross_protocol_bridge": False,
                },
                {
                    "entry_id": "source-secondary",
                    "top_protocols": [
                        {"protocol": "investing", "total_score": 3.4, "selected_as": "hot-evidence"},
                        {"protocol": "research", "total_score": 2.6, "selected_as": "warm-evidence"},
                    ],
                    "protocol_snapshots": [
                        {"protocol": "research", "selected_as": "warm-evidence", "total_score": 2.6, "is_bridge": False}
                    ],
                    "cross_protocol_bridge": False,
                },
                {
                    "entry_id": "source-bridge",
                    "top_protocols": [
                        {"protocol": "investing", "total_score": 3.5, "selected_as": "hot-evidence"},
                        {"protocol": "research", "total_score": 2.5, "selected_as": "warm-evidence"},
                    ],
                    "protocol_snapshots": [
                        {"protocol": "research", "selected_as": "warm-evidence", "total_score": 2.5, "is_bridge": True}
                    ],
                    "cross_protocol_bridge": True,
                },
                {
                    "entry_id": "source-cold-secondary",
                    "top_protocols": [
                        {"protocol": "investing", "total_score": 2.7, "selected_as": "warm-evidence"},
                        {"protocol": "research", "total_score": 1.8, "selected_as": "cold-evidence"},
                    ],
                    "protocol_snapshots": [
                        {"protocol": "research", "selected_as": "cold-evidence", "total_score": 1.8, "is_bridge": False}
                    ],
                    "cross_protocol_bridge": False,
                },
            ]
        }

        summary = protocol_related_concept_lifecycle_summary(
            knowledge_lifecycle,
            material_routing,
            protocol="research",
        )

        backlog_titles = [entry["title"] for entry in summary["concept_backlog"]]
        retired_titles = [entry["title"] for entry in summary["retired_concepts"]]

        self.assertIn("Direct Research Concept", backlog_titles)
        self.assertIn("Strong Secondary Concept", backlog_titles)
        self.assertIn("Bridge Research Concept", retired_titles)
        self.assertNotIn("Cold Secondary Concept", backlog_titles)
        self.assertEqual(summary["counts"]["direct_related_concepts"], 1)
        self.assertEqual(summary["counts"]["secondary_related_concepts"], 1)
        self.assertEqual(summary["counts"]["bridge_related_concepts"], 1)
        self.assertEqual(summary["counts"]["dominant_related_concepts"], 1)
        self.assertEqual(summary["counts"]["mixed_related_concepts"], 1)
        self.assertEqual(summary["counts"]["ambiguity_bridge_concepts"], 1)
        self.assertEqual(
            summary["inference_mode"],
            "source-top1-plus-strong-top2-plus-cross-protocol-bridge",
        )
        self.assertEqual(summary["ambiguity_mode"], "dominant-vs-mixed-vs-bridge")
        bridge_entry = next(entry for entry in summary["retired_concepts"] if entry["title"] == "Bridge Research Concept")
        direct_entry = next(entry for entry in summary["concept_backlog"] if entry["title"] == "Direct Research Concept")
        secondary_entry = next(
            entry for entry in summary["concept_backlog"] if entry["title"] == "Strong Secondary Concept"
        )
        self.assertEqual(bridge_entry["protocol_relevance_primary_mode"], "cross-protocol-bridge")
        self.assertEqual(secondary_entry["protocol_relevance_primary_mode"], "strong-top2")
        self.assertEqual(direct_entry["protocol_relevance_ambiguity"], "dominant")
        self.assertEqual(secondary_entry["protocol_relevance_ambiguity"], "mixed")
        self.assertEqual(bridge_entry["protocol_relevance_ambiguity"], "bridge")
        watchlist_titles = [entry["title"] for entry in summary["ambiguity_watchlist"]]
        self.assertIn("Strong Secondary Concept", watchlist_titles)
        self.assertIn("Bridge Research Concept", watchlist_titles)
        self.assertNotIn("Direct Research Concept", watchlist_titles)

    def test_run_ask_includes_machine_memory_query_plan_in_prompt(self) -> None:
        sample = self.root / "latency.md"
        sample.write_text("# Throughput Notes\n\nLatency throughput cache locality.\n", encoding="utf-8")
        ingest_source(self.root, str(sample), title="Throughput Notes")
        compile_wiki(self.root)
        set_active_protocol(self.root, "investing")
        report_markdown = _VALID_REPORT_BODY
        client = CapturingClient(report_markdown)

        run_ask(
            self.root,
            "Compare latency tail behavior",
            "report",
            client=client,
        )

        self.assertIn("## Machine Memory Query Plan", client.prompt)
        self.assertIn("Matched terms", client.prompt)
        self.assertIn("Bridge concepts", client.prompt)
        self.assertIn("Query subgraph edge count", client.prompt)
        self.assertIn("Query routes", client.prompt)
        self.assertIn("Touched components", client.prompt)
        self.assertIn("wiki/indexes/concept-quality.md", client.prompt)
        self.assertIn("### wiki/indexes/machine-memory.md", client.prompt)
        self.assertIn("### wiki/indexes/log.md", client.prompt)
        self.assertNotIn("### wiki/indexes/agent-workbench.md", client.prompt)
        self.assertNotIn("### wiki/indexes/output-packs.md", client.prompt)
        self.assertNotIn("### wiki/indexes/domain-pilots.md", client.prompt)
        self.assertNotIn("### wiki/indexes/machine-memory-topology.md", client.prompt)
        self.assertNotIn("### wiki/indexes/machine-memory-actions.md", client.prompt)
        self.assertNotIn("### wiki/indexes/machine-memory-repair-plan.md", client.prompt)
        self.assertIn("schema/protocols/investing/index.md", client.prompt)
        self.assertIn("schema/protocols/investing/query.md", client.prompt)
        self.assertIn("Relevant repair actions", client.prompt)
        self.assertIn("latency", client.prompt.lower())

    def test_nightly_auto_promotes_recurring_decision_outputs(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Should we adopt transformer caching for inference?"
        ask_question(self.root, question, "report")
        ask_question(self.root, question, "report")

        result = nightly_health(self.root)

        decision_pages = sorted((self.root / "wiki" / "decisions").glob("*.md"))
        self.assertEqual(len(decision_pages), 0)
        candidate_state = load_output_candidates_state(self.root)
        self.assertEqual(result["promotions"]["count"], 1)
        self.assertEqual(result["promotions"]["pages"][0]["path"], result["promotions"]["pages"][0]["candidate_ref"])
        promoted_ref = result["promotions"]["pages"][0]["candidate_ref"]
        candidate = next(c for c in candidate_state["candidates"] if c["artifact_ref"] == promoted_ref)
        self.assertEqual(candidate["promotion_origin"], "nightly-recurring")
        self.assertEqual(candidate["candidate_state"], "pending")
        state = json.loads((self.root / result["state_path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["promotions"]["count"], 1)
        self.assertTrue(state["repair_backlog"]["auto_promotions"])

    def test_nightly_auto_promotes_recurring_judgment_outputs(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Will transformer inference cost keep rising?"
        ask_question(self.root, question, "report")
        ask_question(self.root, question, "report")

        result = nightly_health(self.root)

        judgment_pages = sorted((self.root / "wiki" / "judgments").glob("*.md"))
        self.assertEqual(len(judgment_pages), 0)
        candidate_state = load_output_candidates_state(self.root)
        self.assertEqual(result["promotions"]["count"], 1)
        promoted_ref = result["promotions"]["pages"][0]["candidate_ref"]
        candidate = next(c for c in candidate_state["candidates"] if c["artifact_ref"] == promoted_ref)
        self.assertEqual(candidate["promotion_origin"], "nightly-recurring")
        self.assertEqual(candidate["candidate_state"], "pending")

    def test_nightly_updates_existing_auto_promoted_page_without_duplicates(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Should we adopt transformer caching for inference?"
        ask_question(self.root, question, "report")
        ask_question(self.root, question, "report")
        nightly_health(self.root)

        ask_question(self.root, question, "report")
        result = nightly_health(self.root)

        self.assertFalse((self.root / "wiki" / "decisions").exists())
        candidate_state = load_output_candidates_state(self.root)
        self.assertGreaterEqual(len(candidate_state["candidates"]), 1)
        self.assertEqual(result["promotions"]["count"], 1)

    def test_nightly_partitions_auto_promotions_by_protocol(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Should we adopt transformer caching for inference?"
        ask_question(self.root, question, "report", protocol="general")
        ask_question(self.root, question, "report", protocol="general")
        ask_question(self.root, question, "report", protocol="investing")
        ask_question(self.root, question, "report", protocol="investing")

        nightly_health(self.root)

        self.assertFalse((self.root / "wiki" / "decisions").exists())
        candidate_state = load_output_candidates_state(self.root)
        protocols = sorted({item["protocol"] for item in candidate_state["candidates"]})
        self.assertEqual(protocols, ["general", "investing"])

    def test_nightly_auto_promotion_uses_protocol_specific_titles(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Should we underwrite this thesis?"
        ask_question(self.root, question, "report", protocol="investing")
        ask_question(self.root, question, "report", protocol="investing")

        nightly_health(self.root)

        candidate_state = load_output_candidates_state(self.root)
        self.assertEqual(candidate_state["candidates"][-1]["protocol"], "investing")
        self.assertEqual(candidate_state["candidates"][-1]["candidate_state"], "pending")

    def test_nightly_protocol_specific_markers_can_promote_research_judgment(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Latency bottleneck tradeoff after cache rewrite"
        ask_question(self.root, question, "report", protocol="research")
        ask_question(self.root, question, "report", protocol="research")

        nightly_health(self.root)

        candidate_state = load_output_candidates_state(self.root)
        self.assertEqual(candidate_state["candidates"][-1]["protocol"], "research")
        self.assertEqual(candidate_state["candidates"][-1]["candidate_state"], "pending")

    def test_nightly_skips_auto_promotion_when_recurring_outputs_have_not_changed(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Should we adopt transformer caching for inference?"
        ask_question(self.root, question, "report")
        ask_question(self.root, question, "report")
        nightly_health(self.root)

        result = nightly_health(self.root)

        self.assertEqual(result["promotions"]["count"], 1)
        self.assertFalse((self.root / "wiki" / "decisions").exists())

    def test_nightly_surfaces_aging_overdue_and_escalation_signals(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        decision_path = self.root / decision["path"]
        decision_text = decision_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(decision_text)
        frontmatter["revisit_after"] = "2000-01-01T00:00:00+00:00"
        frontmatter["escalate_after"] = "2000-01-02T00:00:00+00:00"
        decision_path.write_text(
            f"{render_frontmatter(frontmatter)}\n\n{decision_text.split('---', 2)[2].lstrip()}",
            encoding="utf-8",
        )

        result = nightly_health(self.root)

        self.assertIn(decision["path"], result["aging"]["overdue_pages"])
        self.assertIn(decision["path"], result["aging"]["escalated_pages"])
        state = json.loads((self.root / result["state_path"]).read_text(encoding="utf-8"))
        self.assertIn(decision["path"], state["repair_backlog"]["overdue_pages"])
        self.assertIn(decision["path"], state["repair_backlog"]["escalated_pages"])
        aging_report = (self.root / "wiki" / "indexes" / "aging-report.md").read_text(encoding="utf-8")
        review_queue = (self.root / "wiki" / "indexes" / "review-queue.md").read_text(encoding="utf-8")
        self.assertIn("Scaling Decision", aging_report)
        self.assertIn("需要升级处理", aging_report)
        self.assertIn("已到期待复审", review_queue)
        self.assertIn("需要升级处理", review_queue)

    def test_nightly_writes_repair_backlog_and_state(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")

        result = nightly_health(self.root)

        backlog_path = self.root / result["repair_backlog"]
        state_path = self.root / result["state_path"]
        self.assertTrue(backlog_path.exists())
        self.assertTrue(state_path.exists())
        backlog_text = backlog_path.read_text(encoding="utf-8")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertIn("修复待办", backlog_text)
        self.assertIn("图谱修复建议", backlog_text)
        self.assertIn("Machine Memory 动作", backlog_text)
        self.assertIn("待补来源摘要", backlog_text)
        self.assertIn("审阅队列", backlog_text)
        self.assertIn("待审决策", backlog_text)
        self.assertEqual(state["repair_backlog"]["path"], result["repair_backlog"])
        self.assertEqual(state["lint"]["counts"]["warnings"], result["lint"]["counts"]["warnings"])
        self.assertEqual(state["concept_quality"]["path"], "wiki/indexes/concept-quality.md")
        self.assertEqual(state["knowledge_lifecycle"]["path"], ".aiwiki/state/knowledge-lifecycle.json")
        self.assertGreaterEqual(state["knowledge_lifecycle"]["entry_count"], 2)
        self.assertIn("review", state["knowledge_lifecycle"]["state_counts"])
        self.assertGreater(state["knowledge_lifecycle"]["kind_counts"]["concept"]["total"], 0)
        self.assertIn("rewrite_candidate_slugs", state["concept_quality"])
        self.assertIn("health", state["machine_memory"])
        self.assertEqual(state["machine_memory"]["actions_path"], "wiki/indexes/machine-memory-actions.md")
        self.assertEqual(state["machine_memory"]["repair_plan_path"], "wiki/indexes/machine-memory-repair-plan.md")
        self.assertIn("proposal_action_ids", state["machine_memory"])
        self.assertIn("machine_memory_actions", state["repair_backlog"])
        self.assertEqual(state["repair_backlog"]["repair_plan_path"], "wiki/indexes/machine-memory-repair-plan.md")
        self.assertTrue(state["repair_backlog"]["weak_concept_slugs"])
        self.assertIn("proposal_action_ids", state["repair_backlog"])
        self.assertTrue(state["repair_backlog"]["pending_review_decisions"])
        self.assertTrue(state["repair_backlog"]["pending_review_judgments"])
        self.assertIn("review_focus", state["protocol"])
        self.assertIn("nightly_focus", state["protocol"])
        self.assertFalse(state["llm_used"])

    def test_nightly_surfaces_judgment_review_actions_from_counter_evidence(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")
        review_page(
            self.root,
            judgment["path"],
            "confirmed",
            note="Initial judgment baseline.",
            confidence="high",
        )

        conflicting = self.root / "conflicting.md"
        conflicting.write_text(
            "# Transformer Scaling Followup\n\nTransformers scale inference costs shifted after routing changes.\n",
            encoding="utf-8",
        )
        followup = ingest_source(self.root, str(conflicting), title="Transformer Scaling Followup")

        result = nightly_health(self.root)

        backlog_text = (self.root / result["repair_backlog"]).read_text(encoding="utf-8")
        state = json.loads((self.root / result["state_path"]).read_text(encoding="utf-8"))
        memory = load_machine_memory(self.root)
        counter_evidence_pages = memory["health"]["counter_evidence_scan"]["pages"]
        judgment_actions = memory["health"]["judgment_review_actions"]
        self.assertIn("Judgment Review Actions", backlog_text)
        self.assertIn("counter-evidence-candidate", backlog_text)
        self.assertIn("Scaling Judgment", backlog_text)
        self.assertIn(followup["id"], backlog_text)
        self.assertIn(judgment["path"], state["repair_backlog"]["counter_evidence_candidates"])
        self.assertTrue(state["repair_backlog"]["judgment_review_actions"])
        self.assertEqual(counter_evidence_pages[0]["page_path"], judgment["path"])
        self.assertNotIn(entry["id"], counter_evidence_pages[0]["source_ids"])
        self.assertIn(followup["id"], counter_evidence_pages[0]["source_ids"])
        self.assertEqual(judgment_actions[0]["page_path"], judgment["path"])
        self.assertIn("counter-evidence-candidate", judgment_actions[0]["reason_codes"])

    def test_nightly_state_surfaces_lifecycle_governance_summary(self) -> None:
        self._seed_lifecycle_governance_surface_state()

        result = nightly_health(self.root)

        state = json.loads((self.root / result["state_path"]).read_text(encoding="utf-8"))
        governance_summary = state["knowledge_lifecycle"]["governance_summary"]
        self.assertGreater(governance_summary["concept_backlog_count"], 0)
        self.assertGreater(governance_summary["retired_concept_count"], 0)
        self.assertTrue(governance_summary["concept_backlog_ids"])
        self.assertTrue(governance_summary["retired_concept_ids"])

    def test_run_nightly_writes_semantic_artifacts_and_state(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        updated_source = source_page.read_text(encoding="utf-8").replace(
            "- Pending LLM summary.",
            "- Transformer scale improves capability and raises compute demand.",
        )
        semantic_lint = "# Semantic Lint Report\n\n- Review placeholder concept summaries next.\n"

        result = run_nightly(self.root, client=StubClient([updated_source, semantic_lint]), compile_limit=1)

        backlog_path = self.root / result["repair_backlog"]
        state = json.loads((self.root / result["state_path"]).read_text(encoding="utf-8"))
        self.assertTrue(backlog_path.exists())
        self.assertTrue(result["lint"]["semantic_report"])
        self.assertTrue(state["llm_used"])
        self.assertEqual(state["semantic_report"], result["lint"]["semantic_report"])
        self.assertIn("语义 lint", backlog_path.read_text(encoding="utf-8"))
        self.assertEqual(result["model_selected"], "stub-model")
        self.assertEqual(result["model_final"], "stub-model")
        self.assertTrue(result["contract_validated"])
        llm_receipt = json.loads((self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(llm_receipt["event"], "run-nightly")
        self.assertTrue(llm_receipt["llm_used"])
        self.assertEqual(llm_receipt["model_selected"], "stub-model")

    def test_run_watch_script_uses_root_relative_paths(self) -> None:
        script = Path("/home/tim/ai-wiki/scripts/run_watch.sh")
        content = script.read_text(encoding="utf-8")
        self.assertIn('PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"', content)
        self.assertIn('if [ -z "${AIWIKI_VAULT:-}" ]; then', content)
        self.assertIn('TARGET_ROOT="$AIWIKI_VAULT"', content)
        self.assertIn('export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"', content)
        self.assertIn('--root "$TARGET_ROOT"', content)
        self.assertIn('AIWIKI_WATCH_DETERMINISTIC_ONLY:-1', content)
        self.assertIn('exec python3 -m aiwiki.cli "${ARGS[@]}"', content)

    def test_run_nightly_script_uses_root_relative_paths(self) -> None:
        script = Path("/home/tim/ai-wiki/scripts/run_nightly.sh")
        content = script.read_text(encoding="utf-8")
        self.assertIn('PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"', content)
        self.assertIn('if [ -z "${AIWIKI_VAULT:-}" ]; then', content)
        self.assertIn('TARGET_ROOT="$AIWIKI_VAULT"', content)
        self.assertIn('export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"', content)
        self.assertIn('--root "$TARGET_ROOT"', content)
        self.assertIn('exec python3 -m aiwiki.cli "${ARGS[@]}"', content)
        self.assertIn("run-nightly", content)
        self.assertIn("nightly", content)
        self.assertIn("AIWIKI_NIGHTLY_FALLBACK_BACKEND:-nvidia-nim-api", content)
        self.assertIn("AIWIKI_NIGHTLY_FALLBACK_MODEL:-openai/gpt-oss-120b", content)
        self.assertIn("source \"$FALLBACK_ENV\"", content)
        self.assertIn("retrying nightly with fallback", content)
        self.assertIn("deterministic nightly fallback suppressed after run-nightly failure", content)

    def test_run_nightly_script_retries_nim_fallback_before_deterministic(self) -> None:
        script = Path("/home/tim/ai-wiki/scripts/run_nightly.sh")
        with tempfile.TemporaryDirectory() as tempdir:
            temp_root = Path(tempdir)
            bin_dir = temp_root / "bin"
            bin_dir.mkdir()
            fake_python = bin_dir / "python3"
            log_path = temp_root / "python.log"
            fallback_env = temp_root / "nvidia.env"
            fallback_env.write_text('export AIWIKI_NVIDIA_NIM_API_KEY="nvapi_test"\n', encoding="utf-8")
            fake_python.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-" ]]; then
  if [[ "${AIWIKI_LLM_BACKEND:-}" == "codex-cli" ]]; then
    exit 0
  fi
  if [[ "${AIWIKI_LLM_BACKEND:-}" == "nvidia-nim-api" && -n "${AIWIKI_NVIDIA_NIM_API_KEY:-}" ]]; then
    exit 0
  fi
  exit 1
fi
printf '%s|%s|%s\\n' "${AIWIKI_LLM_BACKEND:-}" "${AIWIKI_LLM_MODEL:-}" "$*" >>"${FAKE_PYTHON_LOG}"
if [[ "$*" == *"run-nightly"* ]]; then
  if [[ "${AIWIKI_LLM_BACKEND:-}" == "nvidia-nim-api" ]]; then
    exit 0
  fi
  exit 42
fi
exit 0
""",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                    "FAKE_PYTHON_LOG": str(log_path),
                    "AIWIKI_VAULT": str(temp_root / "vault"),
                    "AIWIKI_LLM_BACKEND": "codex-cli",
                    "AIWIKI_LLM_MODEL": "gpt-5.5",
                    "AIWIKI_NIGHTLY_FALLBACK_ENV": str(fallback_env),
                    "AIWIKI_NIGHTLY_FALLBACK_ENABLED": "1",
                    "AIWIKI_NIGHTLY_NO_SEMANTIC_LINT": "1",
                }
            )
            completed = subprocess.run(
                ["bash", str(script)],
                cwd="/home/tim/ai-wiki",
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            lines = log_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(lines), 2)
        self.assertIn("codex-cli|gpt-5.5|", lines[0])
        self.assertIn("run-nightly", lines[0])
        self.assertIn("nvidia-nim-api|openai/gpt-oss-120b|", lines[1])
        self.assertIn("--no-semantic-lint", lines[1])
        self.assertIn("retrying nightly with fallback nvidia-nim-api/openai/gpt-oss-120b", completed.stderr)

    def test_run_nightly_script_does_not_deterministic_fallback_after_llm_failure(self) -> None:
        script = Path("/home/tim/ai-wiki/scripts/run_nightly.sh")
        with tempfile.TemporaryDirectory() as tempdir:
            temp_root = Path(tempdir)
            bin_dir = temp_root / "bin"
            bin_dir.mkdir()
            fake_python = bin_dir / "python3"
            log_path = temp_root / "python.log"
            fake_python.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-" ]]; then
  exit 0
fi
printf '%s\n' "$*" >>"${FAKE_PYTHON_LOG}"
if [[ "$*" == *"run-nightly"* ]]; then
  exit 42
fi
exit 0
""",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                    "FAKE_PYTHON_LOG": str(log_path),
                    "AIWIKI_VAULT": str(temp_root / "vault"),
                    "AIWIKI_LLM_BACKEND": "codex-cli",
                    "AIWIKI_LLM_MODEL": "gpt-5.5",
                }
            )
            completed = subprocess.run(
                ["bash", str(script)],
                cwd="/home/tim/ai-wiki",
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            lines = log_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(completed.returncode, 42, completed.stderr)
        self.assertEqual(len(lines), 1)
        self.assertIn("run-nightly", lines[0])
        self.assertNotIn(" nightly", lines[0])
        self.assertIn("deterministic nightly fallback suppressed after run-nightly failure", completed.stderr)

    def test_run_nightly_script_allows_deterministic_when_only_fallback_is_unconfigured(self) -> None:
        script = Path("/home/tim/ai-wiki/scripts/run_nightly.sh")
        with tempfile.TemporaryDirectory() as tempdir:
            temp_root = Path(tempdir)
            bin_dir = temp_root / "bin"
            bin_dir.mkdir()
            fake_python = bin_dir / "python3"
            log_path = temp_root / "python.log"
            fake_python.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-" ]]; then
  exit 1
fi
printf '%s\n' "$*" >>"${FAKE_PYTHON_LOG}"
exit 0
""",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                    "FAKE_PYTHON_LOG": str(log_path),
                    "AIWIKI_VAULT": str(temp_root / "vault"),
                    "AIWIKI_NIGHTLY_FALLBACK_ENABLED": "1",
                    "AIWIKI_NIGHTLY_FALLBACK_ENV": str(temp_root / "missing.env"),
                }
            )
            completed = subprocess.run(
                ["bash", str(script)],
                cwd="/home/tim/ai-wiki",
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            lines = log_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(lines), 1)
        self.assertIn(" nightly", lines[0])
        self.assertIn("falling back to deterministic nightly", completed.stderr)

    def test_nightly_systemd_templates_exist(self) -> None:
        service_template = Path("/home/tim/ai-wiki/systemd/aiwiki-nightly.service.template")
        timer_template = Path("/home/tim/ai-wiki/systemd/aiwiki-nightly.timer.template")
        dogfood_service_template = Path("/home/tim/ai-wiki/systemd/aiwiki-dogfood-maturity.service.template")
        dogfood_timer_template = Path("/home/tim/ai-wiki/systemd/aiwiki-dogfood-maturity.timer.template")
        self.assertTrue(service_template.exists())
        self.assertTrue(timer_template.exists())
        self.assertTrue(dogfood_service_template.exists())
        self.assertTrue(dogfood_timer_template.exists())
        self.assertIn("ExecStart=__PROJECT_ROOT__/scripts/run_nightly.sh", service_template.read_text(encoding="utf-8"))
        self.assertIn("OnCalendar=__ON_CALENDAR__", timer_template.read_text(encoding="utf-8"))
        self.assertIn(
            "ExecStart=__PROJECT_ROOT__/scripts/run_dogfood_maturity.sh",
            dogfood_service_template.read_text(encoding="utf-8"),
        )
        self.assertIn("EnvironmentFile=__ENV_FILE__", dogfood_service_template.read_text(encoding="utf-8"))
        self.assertIn("OnCalendar=__ON_CALENDAR__", dogfood_timer_template.read_text(encoding="utf-8"))

    def test_execution_protocol_stays_stable_across_active_protocol_switch(self) -> None:
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
                        "protocol": "investing",
                    }
                ],
            },
        )
        set_active_protocol(self.root, "research")

        compile_wiki(self.root)

        memory = load_machine_memory(self.root)
        proposal = next(
            proposal
            for proposal in memory["health"]["repair_plan"]["execution_proposals"]
            if proposal["action_id"] == "manual-link-action"
        )
        self.assertEqual(proposal["protocol"], "investing")
        investing_scorecard = (self.root / "output" / "pilots" / "investing.md").read_text(encoding="utf-8")
        self.assertIn("Execution proposals / Receipts: `1` / `0`", investing_scorecard)

        dry_run = apply_machine_memory_action(self.root, "manual-link-action", dry_run=True)
        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = apply_machine_memory_action(
            self.root,
            "manual-link-action",
            note="Protocol stability apply.",
            bundle_path=dry_run["bundle_path"],
        )
        receipt = json.loads((self.root / result["receipt_path"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt["protocol"], "investing")

        compile_wiki(self.root)
        investing_scorecard = (self.root / "output" / "pilots" / "investing.md").read_text(encoding="utf-8")
        research_scorecard = (self.root / "output" / "pilots" / "research.md").read_text(encoding="utf-8")
        self.assertIn("Execution proposals / Receipts: `0` / `1`", investing_scorecard)
        self.assertIn("Execution proposals / Receipts: `0` / `0`", research_scorecard)

    def test_ask_question_writes_graph_anchor_frontmatter_and_body(self) -> None:
        from aiwiki.app_utils import parse_frontmatter

        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        result = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        report_path = self.root / result["path"]
        text = report_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)

        anchors = frontmatter.get("graph_anchor_node_ids")
        self.assertIsInstance(anchors, list)
        self.assertTrue(anchors, "report should record at least one graph anchor")
        self.assertLessEqual(len(anchors), 8)
        for anchor in anchors:
            self.assertRegex(str(anchor), r"^(source|judgment):")
        machine_memory_anchors = frontmatter.get("machine_memory_anchor_node_ids")
        self.assertIsInstance(machine_memory_anchors, list)
        self.assertTrue(any(str(anchor).startswith("concept:") for anchor in machine_memory_anchors))

        # Body section provides a chinese anchor section with clickable .md links.
        self.assertIn("## 关系图谱锚点", text)
        self.assertIn("相关来源（点击跳转）", text)
        self.assertIn("[[wiki/", text)
        anchor_section = text.split("## 关系图谱锚点", 1)[1]
        self.assertNotIn("../../wiki/", anchor_section)



def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(RuntimeFlowTests))
    return suite


if __name__ == "__main__":
    unittest.main()
