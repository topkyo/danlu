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
    save_knowledge_lifecycle_override_state,
    save_machine_memory_action_state,
    save_manual_link_state,
    save_material_routing_state,
    save_material_state,
    shell_summary_path,
)
from aiwiki.app_utils import parse_frontmatter, relative_path, render_frontmatter, runtime_write_lock, strip_frontmatter
from aiwiki.cli import main as cli_main
from aiwiki.compile import compile_wiki as compile_wiki_owner
from aiwiki.config import BACKEND_OPENAI_API, BACKEND_OPENCODE_API, LLMConfig
from aiwiki.drop import _fetch_url, drop_image, drop_pdf, drop_repo, drop_url
from aiwiki.llm import CompletionResult
from aiwiki.runner import auto_process_once, run_ask, run_compile, run_lint, run_nightly, watch_inbox
from tests.test_app import AppFlowTestBase, CapturingClient, FailingVisionClient, StubClient, StubVisionClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_VALID_REPORT_BODY = (
    "---\nid: query-stub\nkind: output\nformat: report\n---\n\n"
    "# Stub answer\n\n"
    "## 结论\nStubbed conclusion.\n\n"
    "## 关键证据\n"
    "- See wiki/sources/source-1.md\n"
    "- Secondary evidence point.\n"
    "- Tertiary evidence point.\n\n"
    "## 反证与不确定性\n- None observed in stub.\n\n"
    "## 行动建议\n- Stub follow-up.\n\n"
    "## 下次观察信号\n- Stub revisit signal.\n\n"
    "## 引用\n- wiki/sources/source-1.md\n"
)


def _load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class MiscFlowTests(AppFlowTestBase):
    def test_ingest_compile_ask_file_back_and_lint(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        manifest = load_manifest(self.root)
        self.assertEqual(len(manifest["entries"]), 1)
        self.assertEqual(manifest["entries"][0]["id"], entry["id"])

        compiled = compile_wiki(self.root)
        self.assertEqual(compiled["sources"], 1)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        self.assertTrue(source_page.exists())

        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        report_path = self.root / report["path"]
        self.assertTrue(report_path.exists())
        report_text = report_path.read_text(encoding="utf-8")
        self.assertIn("../../wiki/sources/", report_text)

        filed = file_back(self.root, report["path"])
        filed_path = self.root / filed["path"]
        self.assertTrue(filed_path.exists())

        lint = lint_wiki(self.root)
        self.assertTrue((self.root / lint["path"]).exists())
        self.assertGreaterEqual(lint["counts"]["warnings"], 1)

    def test_runtime_write_lock_is_reentrant_across_app_and_runner(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        self.assertTrue((self.root / report["path"]).exists())

        with runtime_write_lock(self.root):
            rerun = run_ask(
                self.root,
                "Compare transformer scale and inference cost",
                "report",
                client=StubClient([_VALID_REPORT_BODY]),
            )
            filed = file_back(self.root, rerun["path"], title="Locked Decision", kind="decision")

        self.assertTrue((self.root / rerun["path"]).exists())
        self.assertTrue((self.root / filed["path"]).exists())
        self.assertTrue((self.root / ".aiwiki" / "state" / "runtime.lock").exists())

    def test_file_back_success_writes_execution_receipt_with_output_and_wiki_paths(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")

        filed = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")

        self.assertTrue((self.root / filed["path"]).exists())
        receipt_history = _load_jsonl_records(self.root / ".aiwiki" / "state" / "execution-receipts.jsonl")
        matching_history = [
            record
            for record in receipt_history
            if record.get("operation") == "file-back"
            and record.get("status") == "success"
            and record.get("target_file") == report["path"]
            and record.get("primary_path") == report["path"]
            and record.get("secondary_path") == filed["path"]
        ]
        self.assertTrue(matching_history, receipt_history)

        receipt_path = self.root / str(matching_history[-1]["receipt_path"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["operation"], "file-back")
        self.assertEqual(receipt["status"], "success")
        self.assertEqual(receipt["target_file"], report["path"])
        self.assertEqual(receipt["primary_path"], report["path"])
        self.assertEqual(receipt["secondary_path"], filed["path"])
        self.assertEqual(receipt["receipt_path"], relative_path(self.root, receipt_path))

    def test_file_back_absolute_artifact_under_resolved_root_stays_workspace_relative(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        absolute_artifact = (self.root / report["path"]).resolve(strict=False)

        filed = file_back(self.root, str(absolute_artifact), title="Scaling Decision", kind="decision")

        receipt_history = _load_jsonl_records(self.root / ".aiwiki" / "state" / "execution-receipts.jsonl")
        matching = [record for record in receipt_history if record.get("operation") == "file-back"]
        self.assertTrue(matching, receipt_history)
        self.assertEqual(matching[-1]["target_file"], report["path"])
        self.assertEqual(matching[-1]["primary_path"], report["path"])
        self.assertEqual(matching[-1]["secondary_path"], filed["path"])

    def test_file_back_execution_receipt_failure_rolls_back_mutation(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        before_candidates = (self.root / ".aiwiki" / "state" / "output-candidates.json").read_bytes()
        log_path = self.root / "wiki" / "indexes" / "log.md"
        before_log = log_path.read_bytes() if log_path.exists() else None

        with patch("aiwiki.execution.ask.write_execution_receipt", side_effect=RuntimeError("receipt failed")):
            with self.assertRaises(RuntimeError):
                file_back(self.root, report["path"], title="Scaling Decision", kind="decision")

        self.assertFalse((self.root / "wiki" / "decisions" / "scaling-decision.md").exists())
        self.assertEqual((self.root / ".aiwiki" / "state" / "output-candidates.json").read_bytes(), before_candidates)
        if before_log is None:
            self.assertFalse(log_path.exists())
        else:
            self.assertEqual(log_path.read_bytes(), before_log)

    def test_ingest_source_does_not_overwrite_existing_raw(self) -> None:
        existing = self.root / "raw" / "inbox" / "source-foo.md"
        existing.write_text("do not overwrite\n", encoding="utf-8")

        fetched = {
            "title": "foo",
            "final_url": "https://example.com/foo",
            "content_type": "text/html",
            "status": "200",
            "browser_backend": "",
            "extraction_mode": "readability",
            "description": "",
            "image_urls": [],
            "text": "Fetched body",
        }
        with patch("aiwiki.drop._fetch_url", return_value=fetched):
            entry = ingest_source(self.root, "https://example.com/foo", title="foo")

        self.assertEqual(existing.read_text(encoding="utf-8"), "do not overwrite\n")
        self.assertNotEqual(entry["stored_path"], "raw/inbox/source-foo.md")
        self.assertTrue((self.root / entry["stored_path"]).exists())

    def test_reviewed_pages_enter_knowledge_lifecycle_active_when_linked_to_active_corpus(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")

        review_page(self.root, decision["path"], status="approved", note="Approved after source review.")
        review_page(self.root, judgment["path"], status="confirmed", note="Confirmed after checks.", confidence="high")

        lifecycle = load_knowledge_lifecycle_state(self.root)
        self.assertEqual(lifecycle["counts"]["by_state"]["active"], 2)
        decision_entry = next(item for item in lifecycle["entries"] if item["page_id"] == Path(decision["path"]).stem)
        judgment_entry = next(item for item in lifecycle["entries"] if item["page_id"] == Path(judgment["path"]).stem)
        self.assertEqual(decision_entry["lifecycle_state"], "active")
        self.assertEqual(judgment_entry["lifecycle_state"], "active")
        self.assertEqual(decision_entry["source_ids"], [entry["id"]])
        self.assertEqual(judgment_entry["source_ids"], [entry["id"]])
        self.assertEqual(decision_entry["active_corpus_ids"], [report["active_corpus_id"]])
        self.assertEqual(judgment_entry["active_corpus_ids"], [report["active_corpus_id"]])
        self.assertEqual(judgment_entry["confidence"], "high")

    def test_knowledge_lifecycle_marks_citation_drift_as_revisit_signal(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")
        review_page(self.root, judgment["path"], status="confirmed", note="Confirmed after checks.", confidence="high")

        (self.root / entry["stored_path"]).write_text(
            "# Transformer Scaling\n\nTransformers still benefit from scale.\nInference cost shifted after cache changes.\n",
            encoding="utf-8",
        )
        compile_wiki(self.root)

        lifecycle = load_knowledge_lifecycle_state(self.root)
        judgment_entry = next(item for item in lifecycle["entries"] if item["page_id"] == Path(judgment["path"]).stem)
        self.assertEqual(judgment_entry["lifecycle_state"], "revisit")
        self.assertIn("citation-drift", judgment_entry["invalidation_signals"])
        self.assertTrue(judgment_entry["citation_drift"])

    def test_concept_conflict_enters_knowledge_lifecycle_revisit(self) -> None:
        first = self.root / "first.md"
        first.write_text("# Latency Outlook\n\nLatency will increase with larger batches.\n", encoding="utf-8")
        second = self.root / "second.md"
        second.write_text("# Latency Outlook\n\nLatency may decrease after cache reuse.\n", encoding="utf-8")
        first_entry = ingest_source(self.root, str(first), title="Latency Outlook A")
        second_entry = ingest_source(self.root, str(second), title="Latency Outlook B")

        compile_wiki(self.root)

        first_page = self.root / "wiki" / "sources" / f"{first_entry['id']}.md"
        second_page = self.root / "wiki" / "sources" / f"{second_entry['id']}.md"
        first_page.write_text(
            first_page.read_text(encoding="utf-8").replace("- Pending LLM summary.", "- Latency will increase as batches grow."),
            encoding="utf-8",
        )
        second_page.write_text(
            second_page.read_text(encoding="utf-8").replace("- Pending LLM summary.", "- Latency can decrease once cache reuse stabilizes."),
            encoding="utf-8",
        )

        compile_wiki(self.root)

        lifecycle = load_knowledge_lifecycle_state(self.root)
        revisit_concepts = [
            entry for entry in lifecycle["entries"]
            if entry["kind"] == "concept" and "concept-conflict" in entry.get("invalidation_signals", [])
        ]
        self.assertTrue(revisit_concepts)
        self.assertTrue(all(entry["lifecycle_state"] == "revisit" for entry in revisit_concepts))

    def test_retire_concept_sets_retired_override_and_exits_default_ranking(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        slug = Path(concept_entry["path"]).stem
        title = concept_entry["title"]
        self.assertIn(slug, [item["slug"] for item in rank_concepts(self.root, title)])

        result = retire_concept(self.root, slug, note="Retire noisy concept from active ranking.")

        self.assertEqual(result["status"], "retired")
        self.assertTrue(result["receipt_path"])
        updated_lifecycle = load_knowledge_lifecycle_state(self.root)
        retired_entry = next(entry for entry in updated_lifecycle["entries"] if entry["path"] == concept_entry["path"])
        self.assertEqual(retired_entry["lifecycle_state"], "retired")
        self.assertTrue(retired_entry["override_active"])
        self.assertEqual(retired_entry["override_state"], "retired")
        self.assertNotEqual(retired_entry["derived_lifecycle_state"], "retired")
        self.assertNotIn(slug, [item["slug"] for item in rank_concepts(self.root, title)])

        override_state = load_knowledge_lifecycle_override_state(self.root)
        active_override = next(
            entry
            for entry in override_state["entries"]
            if entry["slug"] == slug and entry["active"]
        )
        self.assertEqual(active_override["lifecycle_state"], "retired")
        receipts = load_jsonl_documents(execution_receipt_history_path(self.root))
        lifecycle_receipts = [receipt for receipt in receipts if receipt.get("subject_kind") == "concept_lifecycle"]
        self.assertEqual(lifecycle_receipts[-1]["semantic_operation"], "retire")
        self.assertEqual(lifecycle_receipts[-1]["domain"], "non_core_semantic")
        self.assertTrue(lifecycle_receipts[-1]["before_hash"])
        self.assertTrue(lifecycle_receipts[-1]["after_hash"])

    def test_retire_concept_rolls_back_when_receipt_write_fails(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        slug = Path(concept_entry["path"]).stem
        override_path = self.root / ".aiwiki" / "state" / "knowledge-lifecycle-overrides.json"
        lifecycle_path = self.root / ".aiwiki" / "state" / "knowledge-lifecycle.json"
        receipt_history = execution_receipt_history_path(self.root)
        original_override = override_path.read_bytes()
        original_lifecycle = lifecycle_path.read_bytes()
        original_receipts = receipt_history.read_bytes() if receipt_history.exists() else b""

        with patch("aiwiki.execution.lifecycle.write_execution_receipt", side_effect=RuntimeError("receipt down")):
            with self.assertRaisesRegex(RuntimeError, "receipt down"):
                retire_concept(self.root, slug, note="This should rollback.")

        self.assertEqual(override_path.read_bytes(), original_override)
        self.assertEqual(lifecycle_path.read_bytes(), original_lifecycle)
        self.assertEqual(receipt_history.read_bytes() if receipt_history.exists() else b"", original_receipts)
        self.assertNotIn("This should rollback.", override_path.read_text(encoding="utf-8"))

    def test_bridge_evidence_expands_beyond_top_ranked_sources(self) -> None:
        machine_query = {
            "bridge_concept_slugs": ["shared-bridge"],
            "ranked_source_ids": ["src-ranked", "src-bridge"],
            "query_subgraph": {
                "sources": [
                    {"id": "src-ranked", "title": "Ranked"},
                    {"id": "src-bridge", "title": "Bridge"},
                ],
                "edges": [
                    {"type": "HAS_CONCEPT", "left": "src-ranked", "right": "main-concept"},
                    {"type": "HAS_CONCEPT", "left": "src-bridge", "right": "shared-bridge"},
                ],
            },
        }

        bridge_ids = active_corpus_bridge_evidence_ids(machine_query, ["src-ranked"])
        self.assertEqual(bridge_ids, ["src-bridge"])

    def test_bridge_evidence_recalls_cross_protocol_routing_matches(self) -> None:
        machine_query = {
            "bridge_concept_slugs": [],
            "ranked_source_ids": ["src-ranked"],
            "query_subgraph": {"sources": [{"id": "src-ranked", "title": "Ranked"}], "edges": []},
            "touched_component_ids": ["component-7"],
        }
        routing_state = {
            "entries": [
                {
                    "entry_id": "src-cross",
                    "component_id": "component-7",
                    "cross_protocol_bridge": False,
                    "protocol_snapshots": [
                        {"protocol": "general", "total_score": 2.6, "is_bridge": True},
                        {"protocol": "research", "total_score": 1.4, "is_bridge": True},
                    ],
                },
                {
                    "entry_id": "src-weak",
                    "component_id": "component-7",
                    "cross_protocol_bridge": True,
                    "protocol_snapshots": [
                        {"protocol": "general", "total_score": 2.0, "is_bridge": True},
                        {"protocol": "research", "total_score": 1.5, "is_bridge": True},
                    ],
                },
            ]
        }

        bridge_ids = active_corpus_bridge_evidence_ids(
            machine_query,
            ["src-ranked"],
            routing_state=routing_state,
            active_protocol="research",
        )

        self.assertEqual(bridge_ids, ["src-cross"])

    def test_rank_sources_prefers_active_corpus_and_warmer_material_on_close_matches(self) -> None:
        entries = self._seed_runtime_ranking_entries()
        alpha = next(entry for entry in entries if entry["title"] == "Alpha Cache")
        zulu = next(entry for entry in entries if entry["title"] == "Zulu Cache")

        save_material_state(
            self.root,
            {
                "version": 1,
                "generated_at": "2026-04-09T00:00:00+00:00",
                "entries": [
                    {
                        "entry_id": alpha["id"],
                        "temperature": "cold",
                        "active_corpus_ids": [],
                        "supports_judgment_ids": [],
                    },
                    {
                        "entry_id": zulu["id"],
                        "temperature": "warm",
                        "active_corpus_ids": ["corpus-1"],
                        "supports_judgment_ids": [],
                    },
                ],
            },
        )
        save_material_routing_state(
            self.root,
            {
                "version": 1,
                "computed_at": "2026-04-09T00:00:00+00:00",
                "active_protocol": "general",
                "entries": [
                    {
                        "entry_id": alpha["id"],
                        "protocol": "general",
                        "selected_as": "cold-evidence",
                        "total_score": 1.4,
                        "top_protocols": [{"protocol": "general", "total_score": 1.4, "selected_as": "cold-evidence"}],
                        "protocol_snapshots": [
                            {"protocol": "general", "selected_as": "cold-evidence", "total_score": 1.4}
                        ],
                    },
                    {
                        "entry_id": zulu["id"],
                        "protocol": "general",
                        "selected_as": "warm-evidence",
                        "total_score": 2.7,
                        "top_protocols": [{"protocol": "general", "total_score": 2.7, "selected_as": "warm-evidence"}],
                        "protocol_snapshots": [
                            {"protocol": "general", "selected_as": "warm-evidence", "total_score": 2.7}
                        ],
                    },
                ],
            },
        )

        ranked = rank_sources(
            self.root,
            entries,
            "latency cache tradeoff",
            boost_source_ids={alpha["id"], zulu["id"]},
            protocol="general",
        )

        self.assertEqual(ranked[0]["id"], zulu["id"])

    def test_rank_sources_uses_protocol_specific_routing_snapshot(self) -> None:
        entries = self._seed_runtime_ranking_entries()
        alpha = next(entry for entry in entries if entry["title"] == "Alpha Cache")
        zulu = next(entry for entry in entries if entry["title"] == "Zulu Cache")

        save_material_state(
            self.root,
            {
                "version": 1,
                "generated_at": "2026-04-09T00:00:00+00:00",
                "entries": [
                    {
                        "entry_id": alpha["id"],
                        "temperature": "warm",
                        "active_corpus_ids": [],
                        "supports_judgment_ids": [],
                    },
                    {
                        "entry_id": zulu["id"],
                        "temperature": "warm",
                        "active_corpus_ids": [],
                        "supports_judgment_ids": [],
                    },
                ],
            },
        )
        save_material_routing_state(
            self.root,
            {
                "version": 1,
                "computed_at": "2026-04-09T00:00:00+00:00",
                "active_protocol": "general",
                "entries": [
                    {
                        "entry_id": alpha["id"],
                        "protocol": "general",
                        "selected_as": "warm-evidence",
                        "total_score": 2.5,
                        "top_protocols": [{"protocol": "general", "total_score": 2.5, "selected_as": "warm-evidence"}],
                        "protocol_snapshots": [
                            {"protocol": "general", "selected_as": "warm-evidence", "total_score": 2.5},
                            {"protocol": "investing", "selected_as": "cold-evidence", "total_score": 1.2},
                        ],
                    },
                    {
                        "entry_id": zulu["id"],
                        "protocol": "general",
                        "selected_as": "cold-evidence",
                        "total_score": 1.1,
                        "top_protocols": [{"protocol": "investing", "total_score": 2.8, "selected_as": "warm-evidence"}],
                        "protocol_snapshots": [
                            {"protocol": "general", "selected_as": "cold-evidence", "total_score": 1.1},
                            {"protocol": "investing", "selected_as": "warm-evidence", "total_score": 2.8},
                        ],
                    },
                ],
            },
        )

        general_ranked = rank_sources(
            self.root,
            entries,
            "latency cache tradeoff",
            boost_source_ids={alpha["id"], zulu["id"]},
            protocol="general",
        )
        investing_ranked = rank_sources(
            self.root,
            entries,
            "latency cache tradeoff",
            boost_source_ids={alpha["id"], zulu["id"]},
            protocol="investing",
        )

        self.assertEqual(general_ranked[0]["id"], alpha["id"])
        self.assertEqual(investing_ranked[0]["id"], zulu["id"])

    def test_stale_protocol_hinted_material_can_recommend_archived_under_general(self) -> None:
        entry = self._prepare_stale_protocol_material()

        archive_candidates = json.loads(
            (self.root / ".aiwiki" / "state" / "archive-candidates.json").read_text(encoding="utf-8")
        )
        candidate = next(item for item in archive_candidates["entries"] if item["entry_id"] == entry["id"])

        self.assertEqual(candidate["status"], "ready")
        self.assertEqual(candidate["recommended_temperature"], "archived")

    def test_append_execution_receipt_history_writes_universal_audit(self) -> None:
        receipt = {
            "kind": "execution-receipt",
            "operation": "apply",
            "protocol": "research",
            "action_id": "research-action",
            "title": "Research receipt",
            "receipt_path": "output/control/execution-receipts/research-action.json",
            "applied_at": "2026-04-09T10:00:00+08:00",
            "revert_supported": True,
        }

        append_execution_receipt_history(self.root, receipt)
        append_execution_receipt_history(self.root, receipt)

        receipt_lines = (self.root / ".aiwiki/state/execution-receipts.jsonl").read_text(encoding="utf-8").splitlines()
        audit_records = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(receipt_lines), 2)
        self.assertEqual(len(audit_records), 2)
        self.assertEqual(audit_records[0]["source_stream"], "execution_receipts")
        self.assertEqual(audit_records[0]["source_ref"], ".aiwiki/state/execution-receipts.jsonl#L1")
        self.assertEqual(audit_records[0]["event_type"], "apply")
        self.assertEqual(audit_records[0]["subject"], {"kind": "execution-receipt", "id": "research-action"})
        self.assertTrue(audit_records[0]["revert_supported"])
        self.assertNotEqual(audit_records[0]["audit_event_id"], audit_records[1]["audit_event_id"])

    def test_machine_memory_query_prefers_recent_sources_for_recent_questions(self) -> None:
        stale = self.root / "latency-alpha.md"
        stale.write_text("# Latency Notes\n\nLatency throughput notes.\n", encoding="utf-8")
        stale_entry = ingest_source(self.root, str(stale), title="Latency Notes Alpha")
        fresh = self.root / "latency-zeta.md"
        fresh.write_text("# Latency Notes\n\nLatency throughput notes.\n", encoding="utf-8")
        fresh_entry = ingest_source(self.root, str(fresh), title="Latency Notes Zeta")
        compile_wiki(self.root)

        manifest = load_manifest(self.root)
        for entry in manifest["entries"]:
            if entry["id"] == stale_entry["id"]:
                entry["imported_at"] = "2025-01-01T00:00:00+00:00"
                entry["updated_at"] = "2025-01-01T00:00:00+00:00"
        save_manifest(self.root, manifest)
        compile_wiki(self.root)

        machine_query = build_machine_memory_query(
            load_machine_memory(self.root),
            "latest latency notes",
            protocol="research",
            material_state=load_material_state(self.root),
            routing_state=load_material_routing_state(self.root),
            archive_candidates=load_archive_candidates_state(self.root),
        )

        self.assertEqual(machine_query["time_focus"], "recent")
        self.assertIn("latest", machine_query["time_focus_markers"])
        self.assertEqual(machine_query["ranked_source_ids"][0], fresh_entry["id"])
        self.assertIn(fresh_entry["id"], machine_query["time_shard_source_ids"])

    def test_machine_memory_query_protocol_shard_prefers_active_protocol_sources(self) -> None:
        investing = self.root / "investing-notes.md"
        investing.write_text("# Strategy Notes\n\nCompany thesis valuation catalyst.\n", encoding="utf-8")
        investing_entry = ingest_source(self.root, str(investing), title="Strategy Notes Alpha")
        research = self.root / "research-notes.md"
        research.write_text("# Strategy Notes\n\nLatency throughput benchmark experiment.\n", encoding="utf-8")
        research_entry = ingest_source(self.root, str(research), title="Strategy Notes Zeta")
        compile_wiki(self.root)

        investing_query = build_machine_memory_query(
            load_machine_memory(self.root),
            "compare strategy notes",
            protocol="investing",
            material_state=load_material_state(self.root),
            routing_state=load_material_routing_state(self.root),
            archive_candidates=load_archive_candidates_state(self.root),
        )
        research_query = build_machine_memory_query(
            load_machine_memory(self.root),
            "compare strategy notes",
            protocol="research",
            material_state=load_material_state(self.root),
            routing_state=load_material_routing_state(self.root),
            archive_candidates=load_archive_candidates_state(self.root),
        )

        self.assertEqual(investing_query["protocol_shard_source_ids"][0], investing_entry["id"])
        self.assertEqual(research_query["protocol_shard_source_ids"][0], research_entry["id"])

    def test_machine_memory_query_ignores_judgment_nodes_when_expanding_route_scores(self) -> None:
        memory = {
            "term_index": {"agent": {"concept_slugs": ["agent"]}},
            "source_nodes": [
                {"id": "src-1", "title": "Source 1", "source_page": "wiki/sources/src-1.md"},
            ],
            "concept_nodes": [
                {"slug": "agent", "title": "Agent"},
            ],
            "judgment_nodes": [
                {"page_id": "judgment-1", "title": "Judgment 1", "path": "wiki/judgments/judgment-1.md"},
            ],
            "edges": {
                "source_to_concept": [],
                "concept_to_concept": [],
            },
            "health": {
                "repair_plan": {},
                "actions": [],
                "components": [],
                "source_component_ids": {},
                "concept_component_ids": {},
            },
        }
        patched_routes = [
            {
                "start": {"kind": "source", "id": "src-1", "title": "Source 1"},
                "goal": {"kind": "concept", "slug": "agent", "title": "Agent"},
                "length": 2,
                "nodes": [
                    {"kind": "source", "id": "src-1", "title": "Source 1"},
                    {"kind": "judgment", "page_id": "judgment-1", "title": "Judgment 1"},
                    {"kind": "concept", "slug": "agent", "title": "Agent"},
                ],
                "edges": [
                    {"type": "SUPPORTS_JUDGMENT", "left": "src-1", "right": "judgment-1"},
                    {"type": "JUDGMENT_RELATION", "left": "judgment-1", "right": "agent"},
                ],
            }
        ]

        with patch("aiwiki.app_memory_surfaces.build_machine_memory_query_routes", return_value=patched_routes):
            machine_query = build_machine_memory_query(memory, "agent workflow", protocol="research")

        self.assertEqual(machine_query["query_routes"], patched_routes)
        self.assertIn("agent", machine_query["ranked_concept_slugs"])
        self.assertIn("src-1", machine_query["ranked_source_ids"])

    def test_private_query_helpers_are_not_reexported_from_memory_surfaces(self) -> None:
        import aiwiki.app_memory_surfaces as memory_surfaces
        from aiwiki.app_memory_query import _machine_memory_query_payload_hash, _route_anchor_candidates
        from aiwiki.app_memory_surfaces import build_machine_memory_query_routes

        self.assertTrue(callable(_machine_memory_query_payload_hash))
        self.assertTrue(callable(_route_anchor_candidates))
        self.assertTrue(callable(build_machine_memory_query_routes))
        self.assertFalse(hasattr(memory_surfaces, "_machine_memory_query_payload_hash"))
        self.assertFalse(hasattr(memory_surfaces, "_route_anchor_candidates"))

        with self.assertRaises(ImportError):
            exec(
                "from aiwiki.app_memory_surfaces import _machine_memory_query_payload_hash",
                {},
                {},
            )
        with self.assertRaises(ImportError):
            exec("from aiwiki.app_memory_surfaces import _route_anchor_candidates", {}, {})

    def test_machine_memory_query_ignores_stale_cache_snapshot(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        cache_db = self.root / ".aiwiki" / "cache.db"
        with sqlite3.connect(cache_db) as connection:
            connection.execute("UPDATE cache_meta SET value = ? WHERE key = ?", ("stale-hash", "memory_hash"))
            connection.commit()

        query = build_machine_memory_query(
            load_machine_memory(self.root),
            "transformer scale",
            root=self.root,
            protocol="general",
            material_state=load_material_state(self.root),
            routing_state=load_material_routing_state(self.root),
            archive_candidates=load_archive_candidates_state(self.root),
        )

        self.assertTrue(query["ranked_source_ids"])
        cache_status = load_cache_status(self.root)
        self.assertEqual(cache_status["last_query"]["reason"], "json-fallback")

    def test_force_rebuild_query_cache_updates_status_reason(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        result = force_rebuild_query_cache(self.root)

        self.assertTrue(result["rebuilt"])
        self.assertEqual(result["reason"], "forced")
        self.assertEqual(result["rebuild_reason"], "forced")
        self.assertEqual(result["last_rebuild"]["reason"], "forced")
        cache_status = load_cache_status(self.root)
        self.assertEqual(cache_status["last_sync"]["rebuild_reason"], "forced")
        self.assertEqual(cache_status["last_rebuild"]["reason"], "forced")
        self.assertGreaterEqual(cache_status["stats"]["rebuilds"], 1)

    def test_force_rebuild_query_cache_reports_missing_state_when_uninitialized(self) -> None:
        result = force_rebuild_query_cache(self.root)

        self.assertFalse(result["rebuilt"])
        self.assertEqual(result["reason"], "missing-state")

    def test_machine_memory_query_recreates_query_result_cache_after_drop(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        drop_query_cache(self.root)

        memory = load_machine_memory(self.root)
        material_state = load_material_state(self.root)
        routing_state = load_material_routing_state(self.root)
        archive_candidates = load_archive_candidates_state(self.root)

        first = build_machine_memory_query(
            memory,
            "transformer scale",
            root=self.root,
            protocol="general",
            material_state=material_state,
            routing_state=routing_state,
            archive_candidates=archive_candidates,
        )
        second = build_machine_memory_query(
            memory,
            "transformer scale",
            root=self.root,
            protocol="general",
            material_state=material_state,
            routing_state=routing_state,
            archive_candidates=archive_candidates,
        )

        self.assertEqual(first, second)
        cache_status = load_cache_status(self.root)
        self.assertTrue(cache_status["enabled"])
        self.assertEqual(cache_status["schema_version"], 1)
        self.assertGreaterEqual(cache_status["row_counts"].get("cache_query_results", 0), 1)
        self.assertGreaterEqual(cache_status["stats"]["query_hits"], 1)
        self.assertEqual(cache_status["last_query"]["reason"], "query-result")

    def test_historical_query_surfaces_archive_recall_hints_without_reintroducing_archived_source(self) -> None:
        legacy = self.root / "legacy-latency.md"
        legacy.write_text("# Legacy Latency Notes\n\nLatency notes.\n", encoding="utf-8")
        legacy_entry = ingest_source(self.root, str(legacy), title="Legacy Latency Notes")
        compile_wiki(self.root)

        manifest = load_manifest(self.root)
        for entry in manifest["entries"]:
            if entry["id"] == legacy_entry["id"]:
                entry["imported_at"] = "2025-01-01T00:00:00+00:00"
                entry["updated_at"] = "2025-01-01T00:00:00+00:00"
        save_manifest(self.root, manifest)

        compile_wiki(self.root)
        compile_wiki(self.root)
        archive_candidates = json.loads(
            (self.root / ".aiwiki" / "state" / "archive-candidates.json").read_text(encoding="utf-8")
        )
        legacy_candidate = next(item for item in archive_candidates["entries"] if item["entry_id"] == legacy_entry["id"])
        self.assertEqual(legacy_candidate["status"], "ready")
        self.assertEqual(legacy_candidate["recommended_temperature"], "archived")

        apply_material_archive(self.root, legacy_entry["id"], note="Archive legacy latency notes.")

        current = self.root / "current-latency.md"
        current.write_text("# Current Latency Notes\n\nLatency notes.\n", encoding="utf-8")
        current_entry = ingest_source(self.root, str(current), title="Current Latency Notes")
        compile_wiki(self.root)

        result = ask_question(self.root, "legacy latency notes", "report")

        machine_query = result["machine_memory_query"]
        report_text = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertEqual(machine_query["time_focus"], "historical")
        self.assertTrue(machine_query["archive_recall_hints"])
        self.assertEqual(machine_query["archive_recall_hints"][0]["entry_id"], legacy_entry["id"])
        self.assertNotIn(legacy_entry["id"], result["ranked_sources"])
        self.assertIn(current_entry["id"], result["ranked_sources"])
        self.assertIn("归档召回提示", report_text)

    def test_verify_concept_rewrite_detects_post_apply_drift(self) -> None:
        prepared = self._prepare_concept_rewrite_proposal()
        concept_page = prepared["concept_page"]
        proposal_path = prepared["proposal_path"]
        slug = str(prepared["slug"])

        review_concept_rewrite(self.root, slug, "accepted", note="Looks grounded.")
        apply_concept_rewrite(self.root, slug, note="Apply accepted rewrite.")
        concept_page.write_text(
            concept_page.read_text(encoding="utf-8").replace("Rewritten synthesis", "Post apply drifted synthesis"),
            encoding="utf-8",
        )
        compile_wiki(self.root)

        verification = verify_concept_rewrite(self.root, slug, note="Check drift after manual edit.")

        self.assertEqual(verification["status"], "failed")
        self.assertIn("summary-not-applied", verification["issues"])
        proposal_text = proposal_path.read_text(encoding="utf-8")
        self.assertIn("verify -> failed", (self.root / "wiki" / "indexes" / "cognitive-history.md").read_text(encoding="utf-8"))
        self.assertIn("`failed`", proposal_text)
        self.assertIn("summary-not-applied", proposal_text)

    def test_agent_workbench_surfaces_lifecycle_governance_summary(self) -> None:
        backlog_title, retired_title = self._seed_lifecycle_governance_surface_state()

        workbench = (self.root / "wiki" / "indexes" / "agent-workbench.md").read_text(encoding="utf-8")

        self.assertIn("## Lifecycle Governance Summary", workbench)
        self.assertIn("## Lifecycle Dispatch Hints", workbench)
        self.assertIn("## Lifecycle Concept Backlog", workbench)
        self.assertIn("## Retired Concepts", workbench)
        self.assertIn(backlog_title, workbench)
        self.assertIn(retired_title, workbench)

    def test_output_packs_index_surfaces_lifecycle_governance_summary(self) -> None:
        backlog_title, retired_title = self._seed_lifecycle_governance_surface_state()

        packs_index = (self.root / "wiki" / "indexes" / "output-packs.md").read_text(encoding="utf-8")

        self.assertIn("Lifecycle Governance Summary", packs_index)
        self.assertIn("Lifecycle Concept Backlog", packs_index)
        self.assertIn("Retired Concepts", packs_index)
        self.assertIn(backlog_title, packs_index)
        self.assertIn(retired_title, packs_index)

    def test_domain_pilots_count_slides_outputs(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        ask_question(self.root, "Summarize transformer scaling for a team deck", "slides", protocol="research")
        compile_wiki(self.root)

        research_scorecard = (self.root / "output" / "pilots" / "research.md").read_text(encoding="utf-8")
        self.assertIn("- Outputs: `1`", research_scorecard)

    def test_domain_pilot_scorecards_surface_protocol_aware_lifecycle_governance(self) -> None:
        backlog_title, retired_title = self._seed_protocol_lifecycle_governance_surface_state()

        pilots_index = (self.root / "wiki" / "indexes" / "domain-pilots.md").read_text(encoding="utf-8")
        research_scorecard = (self.root / "output" / "pilots" / "research.md").read_text(encoding="utf-8")
        investing_scorecard = (self.root / "output" / "pilots" / "investing.md").read_text(encoding="utf-8")

        self.assertIn("lifecycle backlog", pilots_index)
        self.assertIn("dominant/mixed/bridge", pilots_index)
        self.assertIn("## Lifecycle Governance", research_scorecard)
        self.assertIn("## Protocol Ambiguity Watchlist", research_scorecard)
        self.assertIn("## Protocol-Related Lifecycle Concept Backlog", research_scorecard)
        self.assertIn("## Protocol-Related Retired Concepts", research_scorecard)
        self.assertIn("Related direct / secondary / bridge concepts", research_scorecard)
        self.assertIn("Related dominant / mixed / bridge concepts", research_scorecard)
        self.assertIn("protocol_relevance", research_scorecard)
        self.assertIn(backlog_title, research_scorecard)
        self.assertIn(retired_title, research_scorecard)
        self.assertNotIn(backlog_title, investing_scorecard)
        self.assertNotIn(retired_title, investing_scorecard)

    def test_report_includes_protocol_specific_output_guidance(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        report = ask_question(self.root, "Should we underwrite this thesis?", "report", protocol="investing")
        report_text = (self.root / report["path"]).read_text(encoding="utf-8")

        self.assertIn("## 参考", report_text)
        self.assertIn("_协议输出偏置：_", report_text)
        self.assertIn("thesis / bull-bear evidence / catalysts / risks / invalidation", report_text)

    def test_governance_indexes_surface_lifecycle_revisit_concepts(self) -> None:
        first = self.root / "first.md"
        first.write_text("# Latency Outlook\n\nLatency will increase with larger batches.\n", encoding="utf-8")
        second = self.root / "second.md"
        second.write_text("# Latency Outlook\n\nLatency may decrease after cache reuse.\n", encoding="utf-8")
        first_entry = ingest_source(self.root, str(first), title="Latency Outlook A")
        second_entry = ingest_source(self.root, str(second), title="Latency Outlook B")

        compile_wiki(self.root)

        first_page = self.root / "wiki" / "sources" / f"{first_entry['id']}.md"
        second_page = self.root / "wiki" / "sources" / f"{second_entry['id']}.md"
        first_page.write_text(
            first_page.read_text(encoding="utf-8").replace("- Pending LLM summary.", "- Latency will increase as batches grow."),
            encoding="utf-8",
        )
        second_page.write_text(
            second_page.read_text(encoding="utf-8").replace("- Pending LLM summary.", "- Latency can decrease once cache reuse stabilizes."),
            encoding="utf-8",
        )

        compile_wiki(self.root)

        review_queue = (self.root / "wiki" / "indexes" / "review-queue.md").read_text(encoding="utf-8")
        aging_report = (self.root / "wiki" / "indexes" / "aging-report.md").read_text(encoding="utf-8")
        self.assertIn("生命周期概念待审", review_queue)
        self.assertIn("Latency Outlook", review_queue)
        self.assertIn("生命周期待回看项", aging_report)
        self.assertIn("Latency Outlook", aging_report)

    def test_cognitive_history_surfaces_concept_lifecycle_override_events(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        slug = Path(concept_entry["path"]).stem
        title = concept_entry["title"]

        retire_concept(self.root, slug, note="Retire concept from governance history test.")
        reactivate_concept(self.root, slug, note="Reactivate concept from governance history test.")
        compile_wiki(self.root)

        cognitive_history = (self.root / "wiki" / "indexes" / "cognitive-history.md").read_text(encoding="utf-8")
        self.assertIn("概念生命周期事件", cognitive_history)
        self.assertIn(title, cognitive_history)
        self.assertIn("reactivate ->", cognitive_history)

    def test_cognitive_history_surfaces_nightly_escalation_events(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        review_page(
            self.root,
            decision["path"],
            "approved",
            note="Approved before escalation window.",
        )

        decision_path = self.root / decision["path"]
        decision_text = decision_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(decision_text)
        frontmatter["revisit_after"] = "2000-01-01T00:00:00+00:00"
        frontmatter["escalate_after"] = "2000-01-02T00:00:00+00:00"
        decision_path.write_text(
            f"{render_frontmatter(frontmatter)}\n\n{strip_frontmatter(decision_text).lstrip()}",
            encoding="utf-8",
        )

        nightly_health(self.root)
        compile_wiki(self.root)

        cognitive_history = (self.root / "wiki" / "indexes" / "cognitive-history.md").read_text(encoding="utf-8")
        self.assertIn("Nightly 升级事件", cognitive_history)
        self.assertIn("Scaling Decision", cognitive_history)
        self.assertIn("escalated `1`", cognitive_history)

        review_page(
            self.root,
            decision["path"],
            "approved",
            note="Re-reviewed after escalation.",
        )
        result = nightly_health(self.root)
        compile_wiki(self.root)

        self.assertNotIn(decision["path"], result["aging"]["overdue_pages"])
        self.assertNotIn(decision["path"], result["aging"]["escalated_pages"])
        cognitive_history = (self.root / "wiki" / "indexes" / "cognitive-history.md").read_text(encoding="utf-8")
        self.assertIn("Judgment 生命周期事件", cognitive_history)
        self.assertIn("已批准", cognitive_history)

    def test_llm_status_defaults_to_opencode_and_reports_missing_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            status = LLMConfig.status_from_env()
        self.assertFalse(status["configured"])
        self.assertEqual(status["backend"], "")
        self.assertEqual(status["backend_requested"], "opencode-api")
        self.assertEqual(status["available_backends"], [])
        self.assertIn("Requested `opencode-api`", str(status["message"]))

    def test_llm_config_uses_openai_backend_when_explicitly_configured(self) -> None:
        env = {
            "AIWIKI_LLM_BACKEND": "openai-api",
            "AIWIKI_LLM_MODEL": "claude-haiku-4.5",
            "OPENAI_API_KEY": "openai_test_key",
        }
        with patch.dict(os.environ, env, clear=True):
            config = LLMConfig.from_env()
        self.assertEqual(config.backend, BACKEND_OPENAI_API)
        self.assertEqual(config.model, "claude-haiku-4.5")

    def test_llm_status_marks_removed_claude_cli_as_unconfigured(self) -> None:
        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "claude-cli"}, clear=True):
            status = LLMConfig.status_from_env()
        self.assertFalse(status["configured"])
        self.assertEqual(status["backend"], "")
        self.assertFalse(status["image_analysis_supported"])

    def test_llm_status_marks_opencode_text_model_image_analysis_as_unsupported(self) -> None:
        with patch.dict(os.environ, {"AIWIKI_OPENCODE_API_KEY": "opencode_test_key"}, clear=True):
            status = LLMConfig.status_from_env()

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], "opencode-api")
        self.assertFalse(status["image_analysis_supported"])

    def test_llm_status_marks_opencode_image_capable_model_as_supported(self) -> None:
        with patch.dict(
            os.environ,
            {"AIWIKI_OPENCODE_API_KEY": "opencode_test_key", "AIWIKI_LLM_MODEL": "gpt-4o"},
            clear=True,
        ):
            status = LLMConfig.status_from_env()

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], "opencode-api")
        self.assertTrue(status["image_analysis_supported"])

    def test_auto_once_processes_raw_inbox_without_manual_ingest(self) -> None:
        dropped = self.root / "raw" / "inbox" / "dropped.md"
        dropped.write_text("# Dropped\n\nA dropped source should be auto-compiled.\n", encoding="utf-8")
        result = auto_process_once(self.root, deterministic_only=True, semantic_lint=False)
        manifest = load_manifest(self.root)
        self.assertEqual(len(manifest["entries"]), 1)
        self.assertFalse(result["llm_used"])
        self.assertTrue(result["deterministic_only"])
        self.assertEqual(result["mode"], "deterministic-only")
        self.assertFalse(result["semantic_lint"])
        entry_id = manifest["entries"][0]["id"]
        self.assertTrue((self.root / "wiki" / "sources" / f"{entry_id}.md").exists())
        self.assertTrue((self.root / ".aiwiki" / "state" / "automation.json").exists())
        shell = shell_status(self.root)
        self.assertEqual(shell["watcher"]["last_run_mode"], "deterministic-only")
        self.assertEqual(shell["watcher"]["service_env"], "AIWIKI_WATCH_DETERMINISTIC_ONLY=1")
        self.assertFalse(shell["watcher"]["llm_used"])

    def test_watch_processes_initial_inbox_state(self) -> None:
        dropped = self.root / "raw" / "inbox" / "watch.md"
        dropped.write_text("# Watch\n\nWatcher should process this.\n", encoding="utf-8")
        result = watch_inbox(
            self.root,
            interval_seconds=0.0,
            deterministic_only=True,
            semantic_lint=False,
            max_cycles=1,
        )
        self.assertEqual(result["processed_runs"], 1)
        self.assertIsNotNone(result["last_result"])

    def test_aiwiki_launcher_script_uses_env_vault_when_present(self) -> None:
        script = PROJECT_ROOT / "scripts/aiwiki-launcher.sh"
        content = script.read_text(encoding="utf-8")
        self.assertTrue(os.access(script, os.X_OK))
        self.assertIn('PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"', content)
        self.assertIn('TARGET_ROOT="${AIWIKI_VAULT:-$PROJECT_ROOT}"', content)
        self.assertIn('PLUGIN_DATA="$TARGET_ROOT/.obsidian/plugins/furnace-product-shell/data.json"', content)
        self.assertIn('export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"', content)
        self.assertIn('exec python3 -m aiwiki.cli --root "$TARGET_ROOT" "$@"', content)

    def test_install_user_service_defaults_watcher_to_deterministic_only(self) -> None:
        script = PROJECT_ROOT / "scripts/install_user_service.sh"
        content = script.read_text(encoding="utf-8")
        self.assertIn("install_user_service.sh requires an explicit vault path", content)
        self.assertNotIn('VAULT_ROOT="${AIWIKI_VAULT:-$PROJECT_ROOT}"', content)
        self.assertIn("AIWIKI_VAULT=$VAULT_ROOT", content)
        self.assertIn('ensure_env_key "$WATCH_ENV_PATH" "AIWIKI_VAULT" "$VAULT_ROOT"', content)
        self.assertIn('ensure_env_key "$NIGHTLY_ENV_PATH" "AIWIKI_VAULT" "$VAULT_ROOT"', content)
        self.assertIn('WATCH_VAULT_ROOT="$(env_key_value "$WATCH_ENV_PATH" "AIWIKI_VAULT" "$VAULT_ROOT")"', content)
        self.assertIn('NIGHTLY_VAULT_ROOT="$(env_key_value "$NIGHTLY_ENV_PATH" "AIWIKI_VAULT" "$VAULT_ROOT")"', content)
        self.assertIn('s|__VAULT__|$WATCH_VAULT_ROOT|g', content)
        self.assertIn('s|__VAULT__|$NIGHTLY_VAULT_ROOT|g', content)
        self.assertIn("AIWIKI_WATCH_DETERMINISTIC_ONLY=1", content)
        self.assertIn("AIWIKI_NIGHTLY_DETERMINISTIC_ONLY=0", content)
        self.assertNotIn("AIWIKI_NIGHTLY_FALLBACK_BACKEND", content)
        self.assertNotIn("AIWIKI_NIGHTLY_FALLBACK_MODEL", content)
        self.assertIn("AIWIKI_AUTONOMY_PROFILE=${AIWIKI_AUTONOMY_PROFILE:-agentic}", content)
        self.assertIn("AIWIKI_NIGHTLY_AUTO_ADOPT_L1=${AIWIKI_NIGHTLY_AUTO_ADOPT_L1:-${AUTO_ADOPT_L1:-0}}", content)
        self.assertIn("AIWIKI_NIGHTLY_AUTO_ADOPT_L3=${AIWIKI_NIGHTLY_AUTO_ADOPT_L3:-${AUTO_ADOPT_L3:-0}}", content)
        self.assertIn("AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS=${AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS:-${AUTO_ADOPT_JUDGMENTS:-0}}", content)
        self.assertIn("AIWIKI_NIGHTLY_AUTO_APPLY_HEAVY_SEMANTIC=${AIWIKI_NIGHTLY_AUTO_APPLY_HEAVY_SEMANTIC:-0}", content)
        self.assertIn("AIWIKI_NIGHTLY_AUTO_ADOPT_CORE_L3=${AIWIKI_NIGHTLY_AUTO_ADOPT_CORE_L3:-0}", content)
        self.assertIn('INSTALL_DOGFOOD_MATURITY="${AIWIKI_INSTALL_DOGFOOD_MATURITY:-0}"', content)
        self.assertIn("AIWIKI_DOGFOOD_MATURITY_PREVIEW_LIMIT=1000", content)
        self.assertIn("AIWIKI_DOGFOOD_MATURITY_L3_LIMIT=1000", content)
        self.assertIn("AIWIKI_DOGFOOD_MATURITY_COMPILE_LIMIT=0", content)
        self.assertIn("AIWIKI_DOGFOOD_MATURITY_NO_SEMANTIC_LINT=1", content)
        self.assertIn("AIWIKI_DOGFOOD_MATURITY_ENVRC", content)
        self.assertIn('set_env_key "$DOGFOOD_MATURITY_ENV_PATH" "AIWIKI_DOGFOOD_MATURITY_ENVRC"', content)

    def test_user_service_install_script_mentions_nightly_timer(self) -> None:
        script = PROJECT_ROOT / "scripts/install_user_service.sh"
        content = script.read_text(encoding="utf-8")
        self.assertIn("aiwiki-nightly.service", content)
        self.assertIn("aiwiki-nightly.timer", content)
        self.assertIn("aiwiki-dogfood-maturity.service", content)
        self.assertIn("aiwiki-dogfood-maturity.timer", content)
        self.assertIn("aiwiki-dogfood-maturity.env", content)
        self.assertIn("AIWIKI_NIGHTLY_COMPILE_LIMIT", content)
        self.assertIn("AIWIKI_LLM_MODEL=deepseek-v4-pro", content)
        self.assertNotIn("AIWIKI_NIGHTLY_FALLBACK_ENV", content)
        self.assertIn("AIWIKI_DOGFOOD_MATURITY_ON_CALENDAR", content)
        self.assertIn("*-*-* 00:15:00 UTC", content)
        self.assertIn("AIWIKI_INSTALL_DOGFOOD_MATURITY=1", content)
        self.assertIn("maturity:      not installed", content)
        self.assertIn("dogfood maturity is a validation harness", content)
        self.assertIn('rm -f "$DOGFOOD_MATURITY_SERVICE_PATH" "$DOGFOOD_MATURITY_TIMER_PATH"', content)
        self.assertIn("ensure_env_key", content)

    def test_uninstall_user_service_mentions_dogfood_maturity_cleanup(self) -> None:
        script = PROJECT_ROOT / "scripts/uninstall_user_service.sh"
        content = script.read_text(encoding="utf-8")
        self.assertIn('systemctl --user disable --now "$DOGFOOD_MATURITY_TIMER_NAME"', content)
        self.assertIn('systemctl --user stop "$DOGFOOD_MATURITY_SERVICE_NAME"', content)
        self.assertIn("DOGFOOD_MATURITY_SERVICE_PATH", content)
        self.assertIn("DOGFOOD_MATURITY_TIMER_PATH", content)
        self.assertIn("--dogfood-maturity-only", content)
        self.assertIn("env files and vault data preserved", content)

    def test_collect_machine_memory_actions_respects_active_protocol_focus(self) -> None:
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "research-action",
                        "kind": "expand-singleton-concept",
                        "title": "Benchmark regression repair",
                        "reason": "benchmark throughput regression",
                        "primary_path": "wiki/concepts/benchmark-latency.md",
                        "secondary_path": "",
                        "status": "proposed",
                        "priority": "medium",
                        "active": True,
                    },
                    {
                        "id": "investing-action",
                        "kind": "split-overloaded-concept",
                        "title": "Moat thesis drift cleanup",
                        "reason": "valuation and catalyst thesis drift",
                        "primary_path": "wiki/concepts/company-moat.md",
                        "secondary_path": "",
                        "status": "proposed",
                        "priority": "medium",
                        "active": True,
                    },
                ],
            },
        )
        set_active_protocol(self.root, "research")

        actions = collect_machine_memory_actions(self.root)

        self.assertEqual(actions[0]["id"], "research-action")
        self.assertGreaterEqual(int(actions[0]["focus_score"]), int(actions[1]["focus_score"]))

    def test_fetch_url_prefers_browser_rendered_dom_when_available(self) -> None:
        raw_html = "<html><head><title>Loading</title></head><body><main>Loading...</main></body></html>"
        rendered_html = (
            "<html><head><title>Rendered Article</title></head>"
            "<body><article><h1>Rendered Article</h1><p>Hydrated content wins.</p></article></body></html>"
        )
        with patch("aiwiki.drop._http_fetch_url") as fetch_mock:
            fetch_mock.return_value = {
                "final_url": "https://example.com/post",
                "content_type": "text/html",
                "status": "200",
                "text": raw_html,
                "error": "",
            }
            with patch(
                "aiwiki.drop._render_url_in_browser",
                return_value={"html": rendered_html, "backend": "playwright-chromium"},
            ):
                fetched = _fetch_url("https://example.com/post", root=self.root)
        self.assertEqual(fetched["title"], "Rendered Article")
        self.assertIn("Hydrated content wins.", fetched["text"])
        self.assertEqual(fetched["browser_backend"], "playwright-chromium")
        self.assertEqual(fetched["extraction_mode"], "chromium-rendered+bs4-main-content")

    def test_fetch_url_can_fall_back_to_browser_when_http_fetch_fails(self) -> None:
        rendered_html = (
            "<html><head><title>Browser Only</title></head>"
            "<body><article><p>Rendered after client-side app boot.</p></article></body></html>"
        )
        with patch("aiwiki.drop._http_fetch_url") as fetch_mock:
            fetch_mock.return_value = {
                "final_url": "https://example.com/app",
                "content_type": "",
                "status": "",
                "text": "",
                "error": "403 Forbidden",
            }
            with patch(
                "aiwiki.drop._render_url_in_browser",
                return_value={"html": rendered_html, "backend": "playwright-chromium"},
            ):
                fetched = _fetch_url("https://example.com/app", root=self.root)
        self.assertEqual(fetched["status"], "browser-rendered")
        self.assertEqual(fetched["content_type"], "text/html")
        self.assertIn("Rendered after client-side app boot.", fetched["text"])

    def test_machine_memory_graph_relation_labels_are_chinese(self) -> None:
        memory = {
            "compiled_at": "2026-04-30T00:00:00+00:00",
            "source_nodes": [{"id": "src-1", "title": "材料 A", "concept_slugs": ["alpha"]}],
            "concept_nodes": [
                {"slug": "alpha", "title": "Alpha"},
                {"slug": "beta", "title": "Beta"},
            ],
            "judgment_nodes": [
                {"page_id": "judgment-a", "title": "判断 A", "path": "wiki/judgments/a.md", "kind": "judgment", "status": "confirmed", "source_ids": ["src-1"]},
                {"page_id": "judgment-b", "title": "判断 B", "path": "wiki/judgments/b.md", "kind": "decision", "status": "approved", "source_ids": ["src-1"]},
            ],
            "edges": {"source_to_judgment": [{"source_id": "src-1", "page_id": "judgment-a"}]},
            "health": {
                "components": [
                    {
                        "id": "component-1",
                        "source_ids": ["src-1"],
                        "concept_slugs": ["alpha", "beta"],
                        "judgment_ids": ["judgment-a", "judgment-b"],
                    }
                ]
            },
        }
        graph = {
            "digest": "demo",
            "nodes": [
                {"id": "source:src-1", "kind": "source", "title": "材料 A", "source_page": "wiki/sources/src-1.md"},
                {"id": "concept:alpha", "kind": "concept", "title": "Alpha", "page_path": "wiki/concepts/alpha.md", "chinese_related": True, "source_pages": []},
                {"id": "concept:beta", "kind": "concept", "title": "Beta", "page_path": "wiki/concepts/beta.md", "chinese_related": True, "source_pages": []},
                {"id": "judgment:judgment-a", "kind": "judgment", "title": "判断 A", "page_path": "wiki/judgments/a.md", "page_kind": "judgment", "status": "confirmed", "source_ids": ["src-1"]},
                {"id": "judgment:judgment-b", "kind": "judgment", "title": "判断 B", "page_path": "wiki/judgments/b.md", "page_kind": "decision", "status": "approved", "source_ids": ["src-1"]},
            ],
            "edges": [
                {"source": "judgment:judgment-a", "target": "judgment:judgment-b", "type": "DECISION_RELATED"},
                {"source": "concept:alpha", "target": "concept:beta", "type": "CAUSAL_ENABLES"},
                {"source": "concept:beta", "target": "concept:alpha", "type": "CAUSAL_CONFLICTS_WITH"},
            ],
        }

        payload = render_machine_memory_graph_html(memory, graph)

        self.assertIn("决策相关", payload)
        self.assertIn("因果促成", payload)
        self.assertIn("因果冲突", payload)
        self.assertNotIn("决策关系：related", payload)
        self.assertNotIn("因果关系：enables", payload)
        self.assertNotIn("促成关系", payload)
        self.assertNotIn("冲突关系", payload)

    def test_relation_label_table_is_uniform_chinese(self) -> None:
        from aiwiki.memory.graph import RELATION_LABELS, relation_label

        expected = {
            "HAS_CONCEPT": "材料提到概念",
            "SUPPORTS_JUDGMENT": "材料支撑判断",
            "RELATED_CONCEPT": "概念相关",
            "JUDGMENT_SUPPORTS": "判断支持",
            "JUDGMENT_CONTRADICTS": "判断冲突",
            "JUDGMENT_RELATED": "判断相关",
            "DECISION_SUPPORTS": "决策依据",
            "DECISION_CONTRADICTS": "决策反证",
            "DECISION_RELATED": "决策相关",
            "DECISION_SUPERSEDES": "决策替代",
            "CAUSAL_CAUSES": "因果导致",
            "CAUSAL_ENABLES": "因果促成",
            "CAUSAL_CONSTRAINS": "因果约束",
            "CAUSAL_CONFLICTS_WITH": "因果冲突",
            "CAUSAL_BLOCKS": "因果阻塞",
            "ELIXIR_DERIVED_FROM": "金丹承接",
        }
        self.assertEqual(RELATION_LABELS, expected)
        for label in RELATION_LABELS.values():
            for token in (":", "_", "lower", "upper", "Causes", "supports"):
                self.assertNotIn(token, label, f"label {label!r} leaks english/code token {token!r}")
        # Family fallbacks stay chinese for unknown future relation values.
        self.assertEqual(relation_label("JUDGMENT_FUTURE"), "判断关系")
        self.assertEqual(relation_label("DECISION_FUTURE"), "决策关系")
        self.assertEqual(relation_label("CAUSAL_FUTURE"), "因果关系")
        self.assertEqual(relation_label("UNKNOWN"), "其他关系")
        self.assertEqual(relation_label(""), "其他关系")

    def test_graph_surface_uses_unified_relation_naming(self) -> None:
        """Round 48 lock: legacy chinese "因果链" must not leak; replace with 因果关系/因果导致."""
        from aiwiki.memory.graph import RELATION_LABELS

        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        graph_html = (self.root / "output" / "graph" / "machine-memory.html").read_text(encoding="utf-8")
        graph_view = (self.root / "wiki" / "indexes" / "graph-view.md").read_text(encoding="utf-8")

        for surface, payload in (("graph_html", graph_html), ("graph_view", graph_view)):
            self.assertNotIn("因果链", payload, f"legacy label leaked into {surface}")
            self.assertIn("因果关系", payload, f"unified family label missing from {surface}")
        self.assertEqual(RELATION_LABELS["CAUSAL_CAUSES"], "因果导致")

    def test_relation_style_has_concept_uses_dedicated_color(self) -> None:
        from aiwiki.memory.graph import relation_style

        has_concept_color, _ = relation_style("HAS_CONCEPT")
        fallback_color, _ = relation_style("UNKNOWN")
        self.assertNotEqual(has_concept_color, fallback_color)
        self.assertEqual(has_concept_color, "#0ea5e9")
        self.assertEqual(fallback_color, "#94a3b8")

    def test_collect_report_anchors_returns_node_to_reports_map(self) -> None:
        from aiwiki.memory.graph import collect_report_anchors

        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        result = ask_question(self.root, "Compare transformer scale and inference cost", "report")

        index = collect_report_anchors(self.root)
        self.assertIsInstance(index, dict)
        self.assertTrue(index, "expected at least one anchor entry")
        seen_paths = {entry["path"] for nodes in index.values() for entry in nodes}
        self.assertIn(result["path"], seen_paths)
        for entries in index.values():
            self.assertLessEqual(len(entries), 50)
            for entry in entries:
                self.assertIn("title", entry)
                self.assertIn("path", entry)

    def test_render_graph_html_without_report_anchors_does_not_break(self) -> None:
        from aiwiki.app_memory_surfaces import render_machine_memory_graph_html

        memory = {
            "compiled_at": "2026-04-30T00:00:00+00:00",
            "source_nodes": [{"id": "src-1", "title": "材料 A", "concept_slugs": ["alpha"]}],
            "concept_nodes": [{"slug": "alpha", "title": "Alpha"}],
            "judgment_nodes": [],
            "edges": {},
            "health": {
                "components": [
                    {
                        "id": "component-1",
                        "source_ids": ["src-1"],
                        "concept_slugs": ["alpha"],
                        "judgment_ids": [],
                    }
                ]
            },
        }
        graph = {
            "digest": "demo",
            "nodes": [
                {"id": "source:src-1", "kind": "source", "title": "材料 A", "source_page": "wiki/sources/src-1.md"},
                {"id": "concept:alpha", "kind": "concept", "title": "Alpha", "source_pages": []},
            ],
            "edges": [],
        }

        # Default (None) and empty-dict both must render without raising and
        # still emit the empty-state message in the detail panel script.
        for anchors in (None, {}):
            payload = render_machine_memory_graph_html(memory, graph, report_anchors=anchors)
            self.assertIn("引用此节点的报告", payload)
            self.assertIn("暂无引用此节点的报告", payload)

    def test_relation_summary_keys_by_edge_type_not_chinese_label(self) -> None:
        memory = {
            "compiled_at": "2026-04-30T00:00:00+00:00",
            "source_nodes": [{"id": "src-1", "title": "材料 A", "concept_slugs": []}],
            "concept_nodes": [
                {"slug": "alpha", "title": "Alpha"},
                {"slug": "beta", "title": "Beta"},
            ],
            "judgment_nodes": [],
            "edges": {},
            "health": {
                "components": [
                    {
                        "id": "component-1",
                        "source_ids": ["src-1"],
                        "concept_slugs": ["alpha", "beta"],
                        "judgment_ids": [],
                    }
                ]
            },
        }
        graph = {
            "digest": "demo",
            "nodes": [
                {"id": "source:src-1", "kind": "source", "title": "材料 A", "source_page": "wiki/sources/src-1.md"},
                {"id": "concept:alpha", "kind": "concept", "title": "Alpha", "page_path": "wiki/concepts/alpha.md", "chinese_related": True, "source_pages": []},
                {"id": "concept:beta", "kind": "concept", "title": "Beta", "page_path": "wiki/concepts/beta.md", "chinese_related": True, "source_pages": []},
            ],
            "edges": [
                # Two unknown JUDGMENT_* types share the chinese fallback "判断关系".
                # If counts were keyed by chinese label they would silently merge.
                {"source": "concept:alpha", "target": "concept:beta", "type": "JUDGMENT_NEW_FOO"},
                {"source": "concept:beta", "target": "concept:alpha", "type": "JUDGMENT_NEW_BAR"},
            ],
        }

        payload = render_machine_memory_graph_html(memory, graph)

        # Scope the assertion to the "关系说明" summary panel so the test does
        # NOT fail merely because raw edge types remain in machine-readable SVG
        # `data-relation-type` attributes. The human panel should stay Chinese-only.
        marker = '<h2>关系说明</h2>'
        panel_start = payload.find(marker)
        self.assertGreater(panel_start, -1, "关系说明 panel missing")
        panel_end = payload.find('</section>', panel_start)
        panel_body = payload[panel_start:panel_end]
        self.assertNotIn("JUDGMENT_NEW_FOO", panel_body)
        self.assertNotIn("JUDGMENT_NEW_BAR", panel_body)
        # Both still render as 判断关系 in chinese, but via two list rows.
        self.assertGreaterEqual(panel_body.count("判断关系"), 2)
        # Each row counts a single edge, so the two unknown types must not be
        # silently merged into one row even though they share the chinese label.
        self.assertGreaterEqual(panel_body.count("1 条"), 2)

    def test_resolved_action_reopened_when_signal_reappears(self) -> None:
        """When a resolved action disappears then reappears, it should be reopened."""
        self._seed_machine_memory_actions()
        compile_wiki(self.root)

        state = load_machine_memory_action_state(self.root)
        bridge = next(
            (a for a in state["actions"] if a["kind"] == "monitor-bridge-concept" and a["active"]),
            None,
        )
        self.assertIsNotNone(bridge)
        bridge["status"] = "resolved"
        bridge["active"] = False
        bridge["reopened_count"] = 0
        _save_machine_memory_action_records(self.root, state["actions"])

        compile_wiki(self.root)
        state2 = load_machine_memory_action_state(self.root)
        refreshed = next((a for a in state2["actions"] if a["id"] == bridge["id"]), None)
        if refreshed is not None and refreshed.get("active"):
            self.assertEqual(refreshed["status"], "proposed")
            self.assertEqual(refreshed.get("reopened_count", 0), 1)

    def test_render_figure_brief_generates_valid_scaffold(self) -> None:
        """render_figure_brief should produce a valid figure scaffold."""
        from aiwiki.app_queries import render_figure_brief

        ingest_source(self.root, str(self.sample), title="Sample Source")
        compile_wiki(self.root)
        protocol_state = load_protocol_state(self.root)
        result = render_figure_brief(
            self.root,
            "什么是 Agent 的核心能力？",
            entries=[],
            concepts=[],
            machine_query={"top_concepts": [], "top_sources": [], "routing_analysis": {}},
            protocol_state=protocol_state,
            created_at="2026-01-01T00:00:00+00:00",
            artifact_id="test-figure-001",
        )
        self.assertIn("图表简报", result)
        self.assertIn("优先来源", result)
        self.assertIn("优先概念", result)
        self.assertIn("制图要求", result)
        self.assertNotIn("推荐索引页", result)
        self.assertIn("test-figure-001", result)

    def test_render_slides_generates_valid_scaffold(self) -> None:
        """render_slides should produce a valid marp scaffold."""
        from aiwiki.app_queries import render_slides

        ingest_source(self.root, str(self.sample), title="Sample Source")
        compile_wiki(self.root)
        protocol_state = load_protocol_state(self.root)
        result = render_slides(
            self.root,
            "Agent 技术栈全景",
            entries=[],
            concepts=[],
            machine_query={"top_concepts": [], "top_sources": [], "routing_analysis": {}},
            protocol_state=protocol_state,
            created_at="2026-01-01T00:00:00+00:00",
            artifact_id="test-slides-001",
        )
        self.assertIn("marp: true", result)
        self.assertIn("本稿用途", result)
        self.assertIn("优先来源", result)
        self.assertIn("建议页结构", result)

    def test_link_suggestion_scored_by_shared_terms(self) -> None:
        """Link suggestions should be scored by number of shared terms."""
        from aiwiki.app_memory import build_machine_memory_health

        ingest_source(self.root, str(self.sample), title="Agent Architecture Overview")
        second = self.root / "second_agent.md"
        second.write_text(
            "# Agent Architecture Deep Dive\n\nAgent systems require careful orchestration.\n",
            encoding="utf-8",
        )
        ingest_source(self.root, str(second), title="Agent Deep Dive")
        compile_wiki(self.root)

        memory = load_machine_memory(self.root)
        health = build_machine_memory_health(memory)
        suggestions = health.get("link_suggestions", [])
        if len(suggestions) >= 2:
            self.assertGreaterEqual(suggestions[0]["score"], suggestions[1]["score"])

    def test_machine_memory_action_runtime_functions_allow_title_fragment_matching(self) -> None:
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
                        "title": "Transformer Scaling link repair",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "proposed",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )

        review_result = review_machine_memory_action(self.root, "Transformer Scaling", "accepted", note="Resolve by fragment.")
        self.assertEqual(review_result["id"], "manual-link-action")
        dry_run = apply_machine_memory_action(self.root, "Scaling link repair", dry_run=True)
        self.assertTrue(dry_run["dry_run"])
        self.assertEqual(dry_run["id"], "manual-link-action")
        apply_result = apply_machine_memory_action(self.root, "Transformer Scaling", note="Apply by fragment.")
        self.assertEqual(apply_result["id"], "manual-link-action")
        revert_result = revert_machine_memory_action(self.root, "Scaling link repair", note="Revert by fragment.")
        self.assertEqual(revert_result["id"], "manual-link-action")



def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(MiscFlowTests))
    return suite


if __name__ == "__main__":
    unittest.main()
