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


class ReviewFlowTests(AppFlowTestBase):
    def test_review_updates_material_state_and_runtime_history(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")

        review_page(self.root, judgment["path"], status="tracking", note="keep watching", confidence="high")

        history_lines = (self.root / ".aiwiki" / "state" / "runtime-history.jsonl").read_text(encoding="utf-8").strip().splitlines()
        review_events = [json.loads(line) for line in history_lines if json.loads(line)["event_type"] == "review"]
        self.assertTrue(review_events)
        self.assertIn(entry["id"], review_events[-1]["source_ids"])

        material_state = json.loads((self.root / ".aiwiki" / "state" / "material-state.json").read_text(encoding="utf-8"))
        record = next(item for item in material_state["entries"] if item["entry_id"] == entry["id"])
        self.assertTrue(record["last_review_reference_at"])
        self.assertIn(Path(judgment["path"]).stem, record["supports_judgment_ids"])

    def test_reactivate_concept_clears_retired_override_and_restores_ranking(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        slug = Path(concept_entry["path"]).stem
        title = concept_entry["title"]
        retire_concept(self.root, slug, note="Retire before reactivation.")

        result = reactivate_concept(self.root, slug, note="Restore concept to heuristic routing.")

        self.assertIn(result["status"], {"active", "review", "deferred", "revisit"})
        updated_lifecycle = load_knowledge_lifecycle_state(self.root)
        reactivated_entry = next(entry for entry in updated_lifecycle["entries"] if entry["path"] == concept_entry["path"])
        self.assertNotEqual(reactivated_entry["lifecycle_state"], "retired")
        self.assertFalse(reactivated_entry["override_active"])
        self.assertEqual(reactivated_entry["override_state"], "")
        self.assertIn(slug, [item["slug"] for item in rank_concepts(self.root, title)])

        override_state = load_knowledge_lifecycle_override_state(self.root)
        self.assertFalse(any(entry["slug"] == slug and entry["active"] for entry in override_state["entries"]))

    def test_reactivate_concept_clears_review_ack_override(self) -> None:
        """Round 8: reactivate-concept 清除 review-ack 覆盖项 (P4-19b 反向操作)。"""
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        slug = Path(concept_entry["path"]).stem

        review_concept(self.root, slug, status="deferred", note="ack revisit")

        result = reactivate_concept(self.root, slug, note="rollback ack")

        self.assertEqual(result["cleared_lifecycle_state"], "deferred")
        self.assertNotEqual(result["status"], "deferred")
        updated = load_knowledge_lifecycle_state(self.root)
        updated_entry = next(entry for entry in updated["entries"] if entry["path"] == concept_entry["path"])
        self.assertFalse(updated_entry["override_active"])
        self.assertEqual(updated_entry["override_state"], "")
        override_state = load_knowledge_lifecycle_override_state(self.root)
        self.assertFalse(
            any(entry["slug"] == slug and entry["active"] for entry in override_state["entries"])
        )

    def test_reactivate_concept_clears_all_active_overrides_for_path(self) -> None:
        """Round 8: 同一 path 多个 active override (历史 bug / 手编) 必须一次全清。"""
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        slug = Path(concept_entry["path"]).stem
        path_ref = concept_entry["path"]

        # Hand-craft duplicate active overrides on the same path (simulates state corruption).
        from aiwiki.app_state import (
            ensure_knowledge_lifecycle_override_state,
            save_knowledge_lifecycle_override_state,
        )
        state = ensure_knowledge_lifecycle_override_state(self.root)
        entries = list(state.get("entries", []))
        for ls in ("review", "deferred"):
            entries.append(
                {
                    "page_id": f"concept-{slug}",
                    "slug": slug,
                    "path": path_ref,
                    "kind": "concept",
                    "lifecycle_state": ls,
                    "active": True,
                    "operation": "review",
                    "reason_codes": ["manual-review-ack"],
                    "applied_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                    "note": f"seeded {ls}",
                }
            )
        save_knowledge_lifecycle_override_state(self.root, {"version": 1, "entries": entries})

        result = reactivate_concept(self.root, slug, note="clear duplicates")

        # cleared_lifecycle_state reports the *last* match (deferred — what apply_override pinned).
        self.assertEqual(result["cleared_lifecycle_state"], "deferred")
        override_state = load_knowledge_lifecycle_override_state(self.root)
        active = [
            entry for entry in override_state["entries"]
            if entry["slug"] == slug and entry["active"]
        ]
        self.assertEqual(active, [])

    def test_reactivate_concept_errors_when_no_active_override(self) -> None:
        """Round 8: 没有任何 active concept override 时报清晰错误。"""
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        slug = Path(concept_entry["path"]).stem

        with self.assertRaises(RuntimeError) as cm:
            reactivate_concept(self.root, slug)
        self.assertIn("No active concept lifecycle override", str(cm.exception))
        """P4-19b: review_concept 写一条 active concept 覆盖项，把 revisit 概念路由到 deferred。"""
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        slug = Path(concept_entry["path"]).stem

        result = review_concept(self.root, slug, status="deferred", note="Acknowledge revisit signal.")

        self.assertEqual(result["slug"], slug)
        self.assertEqual(result["status"], "deferred")
        updated = load_knowledge_lifecycle_state(self.root)
        updated_entry = next(entry for entry in updated["entries"] if entry["path"] == concept_entry["path"])
        self.assertEqual(updated_entry["lifecycle_state"], "deferred")
        self.assertTrue(updated_entry["override_active"])
        self.assertEqual(updated_entry["override_state"], "deferred")

        override_state = load_knowledge_lifecycle_override_state(self.root)
        active = [
            entry for entry in override_state["entries"]
            if entry["slug"] == slug and entry["active"]
        ]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["lifecycle_state"], "deferred")
        self.assertEqual(active[0]["operation"], "review")
        self.assertIn("manual-review-ack", active[0]["reason_codes"])

    def test_review_concept_rejects_invalid_status(self) -> None:
        """retired 不能从 review-concept 进入 (走 retire-concept)；revisit 是启发式状态。"""
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        slug = Path(concept_entry["path"]).stem

        with self.assertRaises(ValueError):
            review_concept(self.root, slug, status="retired")
        with self.assertRaises(ValueError):
            review_concept(self.root, slug, status="revisit")

    def test_review_concept_rejects_already_retired(self) -> None:
        """已 retired 的概念必须先 reactivate 才能走 review。"""
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        slug = Path(concept_entry["path"]).stem
        retire_concept(self.root, slug, note="Retire before review.")

        with self.assertRaises(RuntimeError):
            review_concept(self.root, slug, status="deferred")

    def test_review_concept_supersedes_prior_active_concept_override(self) -> None:
        """新 review-ack 必须把同一 path 上之前的 active 覆盖项标 inactive。"""
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        slug = Path(concept_entry["path"]).stem

        review_concept(self.root, slug, status="deferred", note="first ack")
        review_concept(self.root, slug, status="review", note="second ack")

        override_state = load_knowledge_lifecycle_override_state(self.root)
        actives = [
            entry for entry in override_state["entries"]
            if str(entry.get("path") or "") == concept_entry["path"] and entry.get("active")
        ]
        self.assertEqual(len(actives), 1)
        self.assertEqual(actives[0]["lifecycle_state"], "review")

    def test_review_concepts_batch_fail_fast(self) -> None:
        """review_concepts_batch: 第一个失败立即停止，已成功条目不回滚。"""
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        good_slug = Path(concept_entry["path"]).stem

        with self.assertRaises(FileNotFoundError):
            review_concepts_batch(
                self.root,
                [good_slug, "does-not-exist", good_slug],
                status="deferred",
                note="batch ack",
            )

        # good_slug 第一个已写入；does-not-exist 抛错；第三个未被处理。
        override_state = load_knowledge_lifecycle_override_state(self.root)
        actives = [
            entry for entry in override_state["entries"]
            if str(entry.get("slug") or "") == good_slug and entry.get("active")
        ]
        self.assertEqual(len(actives), 1)

    def test_review_concepts_batch_dedupes_and_returns_count(self) -> None:
        """重复 slug 去重并保序；返回 receipts/count/status。"""
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        lifecycle = load_knowledge_lifecycle_state(self.root)
        concept_entry = next(entry for entry in lifecycle["entries"] if entry["kind"] == "concept")
        slug = Path(concept_entry["path"]).stem

        result = review_concepts_batch(
            self.root,
            [slug, slug, " "],
            status="deferred",
            note="dedupe",
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["slugs"], [slug])
        self.assertEqual(result["status"], "deferred")
        self.assertEqual(len(result["receipts"]), 1)

    def test_archive_candidates_progress_to_ready_and_reactivate(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        manifest = load_manifest(self.root)
        manifest["entries"][0]["imported_at"] = "2025-01-01T00:00:00+00:00"
        manifest["entries"][0]["updated_at"] = "2025-01-01T00:00:00+00:00"
        save_manifest(self.root, manifest)

        compile_wiki(self.root)
        archive_candidates = json.loads(
            (self.root / ".aiwiki" / "state" / "archive-candidates.json").read_text(encoding="utf-8")
        )
        candidate = next(item for item in archive_candidates["entries"] if item["entry_id"] == entry["id"])
        self.assertEqual(candidate["status"], "suggested")
        self.assertIn("no-active-corpus", candidate["reason_codes"])
        material_state = json.loads((self.root / ".aiwiki" / "state" / "material-state.json").read_text(encoding="utf-8"))
        self.assertTrue(next(item for item in material_state["entries"] if item["entry_id"] == entry["id"])["archive_candidate"])

        compile_wiki(self.root)
        archive_candidates = json.loads(
            (self.root / ".aiwiki" / "state" / "archive-candidates.json").read_text(encoding="utf-8")
        )
        candidate = next(item for item in archive_candidates["entries"] if item["entry_id"] == entry["id"])
        self.assertEqual(candidate["status"], "ready")

        ask_question(self.root, "Compare transformer scale and inference cost", "report")
        archive_candidates = json.loads(
            (self.root / ".aiwiki" / "state" / "archive-candidates.json").read_text(encoding="utf-8")
        )
        candidate = next(item for item in archive_candidates["entries"] if item["entry_id"] == entry["id"])
        self.assertEqual(candidate["status"], "reactivated")
        self.assertTrue(candidate["reactivation_signals"])
        self.assertIn("active-corpus", candidate["reactivation_signals"])
        material_state = json.loads((self.root / ".aiwiki" / "state" / "material-state.json").read_text(encoding="utf-8"))
        self.assertFalse(next(item for item in material_state["entries"] if item["entry_id"] == entry["id"])["archive_candidate"])

    def test_archive_candidate_skips_cross_protocol_bridge_sources(self) -> None:
        archive_candidates = build_archive_candidate_state(
            material_entries=[
                {
                    "entry_id": "src-cross",
                    "temperature": "cold",
                    "active_corpus_ids": [],
                    "supports_judgment_ids": [],
                    "last_query_hit_at": "",
                    "last_touched_at": "2025-01-01T00:00:00+00:00",
                }
            ],
            routing_entries=[
                {
                    "entry_id": "src-cross",
                    "selected_as": "archive-candidate",
                    "total_score": 1.6,
                    "is_bridge": False,
                    "cross_protocol_bridge": True,
                    "top_protocols": [
                        {"protocol": "research", "total_score": 2.6, "selected_as": "warm-evidence"},
                        {"protocol": "general", "total_score": 1.6, "selected_as": "archive-candidate"},
                    ],
                }
            ],
            active_judgment_ids=set(),
            generated_at="2026-04-09T00:00:00+00:00",
            previous_state={"entries": []},
            active_protocol="general",
        )

        self.assertEqual(archive_candidates["entries"], [])

    def test_archive_candidate_deferred_promotes_to_ready_after_judgment_unblocks(self) -> None:
        material_entries = [
            {
                "entry_id": "src-deferred",
                "temperature": "cold",
                "active_corpus_ids": [],
                "supports_judgment_ids": ["judgment-1"],
                "last_query_hit_at": "",
                "last_touched_at": "2025-01-01T00:00:00+00:00",
            }
        ]
        routing_entries = [
            {
                "entry_id": "src-deferred",
                "selected_as": "archive-candidate",
                "total_score": 1.0,
                "is_bridge": False,
                "cross_protocol_bridge": False,
                "top_protocols": [
                    {"protocol": "general", "total_score": 1.0, "selected_as": "archive-candidate"}
                ],
            }
        ]

        deferred_state = build_archive_candidate_state(
            material_entries=material_entries,
            routing_entries=routing_entries,
            active_judgment_ids={"judgment-1"},
            generated_at="2026-04-09T00:00:00+00:00",
            previous_state={"entries": []},
        )
        deferred_entry = deferred_state["entries"][0]
        self.assertEqual(deferred_entry["status"], "deferred")
        self.assertEqual(deferred_entry["blocked_by_judgment_ids"], ["judgment-1"])

        unblocked_state = build_archive_candidate_state(
            material_entries=material_entries,
            routing_entries=routing_entries,
            active_judgment_ids=set(),
            generated_at="2026-04-10T00:00:00+00:00",
            previous_state=deferred_state,
        )
        unblocked_entry = unblocked_state["entries"][0]
        self.assertEqual(unblocked_entry["status"], "ready")
        self.assertEqual(unblocked_entry["blocked_by_judgment_ids"], [])
        self.assertEqual(unblocked_entry["first_flagged_at"], "2026-04-09T00:00:00+00:00")

    def test_review_center_html_surfaces_lifecycle_governance_summary(self) -> None:
        backlog_title, retired_title = self._seed_lifecycle_governance_surface_state()

        review_html = self.root / "output" / "review" / "review-center.html"
        payload = review_html.read_text(encoding="utf-8")

        self.assertIn("生命周期概念待审", payload)
        self.assertIn("已退役概念", payload)
        self.assertIn(backlog_title, payload)
        self.assertIn(retired_title, payload)

    def test_review_and_apply_concept_rewrite_updates_concept_page(self) -> None:
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
        proposal_path = self.root / result["updated_rewrite_proposal_pages"][0]
        slug = proposal_path.stem

        review = review_concept_rewrite(self.root, slug, "accepted", note="Looks grounded.")
        applied = apply_concept_rewrite(self.root, slug, note="Apply accepted rewrite.")

        self.assertEqual(review["status"], "accepted")
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(applied["verification_status"], "passed")
        refreshed = concept_page.read_text(encoding="utf-8")
        self.assertIn("Rewritten synthesis", refreshed)
        proposal_text = proposal_path.read_text(encoding="utf-8")
        self.assertIn("已应用", proposal_text)
        self.assertIn("## Verification", proposal_text)
        self.assertIn("`passed`", proposal_text)

    def test_review_page_updates_status_and_refreshes_queue(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")
        compile_wiki(self.root)

        reviewed_decision = review_page(
            self.root,
            decision["path"],
            "approved",
            note="Approved after source review.",
        )
        reviewed_judgment = review_page(
            self.root,
            judgment["path"],
            "confirmed",
            note="Confirmed after follow-up checks.",
            confidence="high",
        )

        self.assertEqual(reviewed_decision["status"], "approved")
        self.assertEqual(reviewed_judgment["status"], "confirmed")
        decision_text = (self.root / decision["path"]).read_text(encoding="utf-8")
        judgment_text = (self.root / judgment["path"]).read_text(encoding="utf-8")
        self.assertIn("Approved after source review.", decision_text)
        self.assertIn("Confirmed after follow-up checks.", judgment_text)
        self.assertEqual(parse_frontmatter(decision_text)["status"], "approved")
        self.assertTrue(parse_frontmatter(decision_text)["reviewed_at"])
        self.assertEqual(parse_frontmatter(decision_text)["last_reviewed"], parse_frontmatter(decision_text)["reviewed_at"])
        self.assertEqual(parse_frontmatter(judgment_text)["status"], "confirmed")
        self.assertEqual(parse_frontmatter(judgment_text)["confidence"], "high")
        self.assertTrue(parse_frontmatter(judgment_text)["reviewed_at"])
        self.assertEqual(parse_frontmatter(judgment_text)["last_reviewed"], parse_frontmatter(judgment_text)["reviewed_at"])

        review_queue = (self.root / "wiki" / "indexes" / "review-queue.md").read_text(encoding="utf-8")
        self.assertIn("当前没有待审决策。", review_queue)
        self.assertIn("当前没有待审判断。", review_queue)
        self.assertIn("Scaling Decision", review_queue)
        self.assertIn("Scaling Judgment", review_queue)

    def test_review_page_records_judgment_lifecycle_event_in_cognitive_history(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")

        review_page(
            self.root,
            judgment["path"],
            "tracking",
            note="Keep the thesis under active review.",
            confidence="medium",
        )

        history_lines = (self.root / ".aiwiki" / "state" / "runtime-history.jsonl").read_text(encoding="utf-8").strip().splitlines()
        review_events = [
            json.loads(line)
            for line in history_lines
            if json.loads(line)["event_type"] == "review" and json.loads(line)["page_path"] == judgment["path"]
        ]
        self.assertTrue(review_events)
        self.assertEqual(review_events[-1]["judgment_lifecycle_state"], "under-review")
        self.assertIn("explicit-review-status", review_events[-1]["judgment_lifecycle_reason_codes"])

        cognitive_history = (self.root / "wiki" / "indexes" / "cognitive-history.md").read_text(encoding="utf-8")
        self.assertIn("Judgment 生命周期事件", cognitive_history)
        self.assertIn("Scaling Judgment", cognitive_history)
        self.assertIn("复审中", cognitive_history)

    def test_review_page_appends_review_history(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")

        review_page(
            self.root,
            decision["path"],
            "approved",
            note="Approved after source review.",
        )
        review_page(
            self.root,
            decision["path"],
            "needs-revisit",
            note="Need to revisit after fresh evidence.",
        )

        decision_text = (self.root / decision["path"]).read_text(encoding="utf-8")
        self.assertIn("## Review History", decision_text)
        self.assertIn("Approved after source review.", decision_text)
        self.assertIn("Need to revisit after fresh evidence.", decision_text)
        self.assertGreaterEqual(decision_text.count("| status `"), 2)

    def test_review_page_refreshes_citation_snapshots_after_source_change(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")

        decision_path = self.root / decision["path"]
        original_frontmatter = parse_frontmatter(decision_path.read_text(encoding="utf-8"))
        original_snapshots = list(original_frontmatter["citation_snapshots"])

        (self.root / entry["stored_path"]).write_text(
            "# Transformer Scaling\n\nTransformers still benefit from scale.\nInference cost curve shifted after cache updates.\n",
            encoding="utf-8",
        )
        compile_wiki(self.root)

        reviewed = review_page(
            self.root,
            decision["path"],
            "needs-revisit",
            note="Source changed after first judgment.",
        )

        refreshed_frontmatter = parse_frontmatter((self.root / reviewed["path"]).read_text(encoding="utf-8"))
        self.assertNotEqual(original_snapshots, refreshed_frontmatter["citation_snapshots"])
        self.assertTrue(refreshed_frontmatter["citation_snapshots"])
        self.assertIn("wiki/sources/", refreshed_frontmatter["citation_snapshots"][0])

    def test_review_page_clears_aging_windows_for_terminal_status(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")

        review_page(
            self.root,
            decision["path"],
            "approved",
            note="Approved after source review.",
        )

        decision_text = (self.root / decision["path"]).read_text(encoding="utf-8")
        decision_frontmatter = parse_frontmatter(decision_text)
        self.assertEqual(decision_frontmatter["revisit_after"], "")
        self.assertEqual(decision_frontmatter["escalate_after"], "")
        self.assertIn("- Revisit after: `none`", decision_text)
        self.assertIn("- Escalate after: `none`", decision_text)

    def test_review_page_uses_protocol_specific_revisit_windows(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Should we underwrite this thesis?", "report", protocol="investing")
        decision = file_back(self.root, report["path"], title="Investing Decision", kind="decision")

        review_page(
            self.root,
            decision["path"],
            "needs-revisit",
            note="Need to revisit after catalyst drift.",
        )

        decision_text = (self.root / decision["path"]).read_text(encoding="utf-8")
        decision_frontmatter = parse_frontmatter(decision_text)
        revisit_delta = datetime.fromisoformat(decision_frontmatter["revisit_after"]) - datetime.fromisoformat(
            decision_frontmatter["reviewed_at"]
        )
        escalate_delta = datetime.fromisoformat(decision_frontmatter["escalate_after"]) - datetime.fromisoformat(
            decision_frontmatter["reviewed_at"]
        )
        self.assertEqual(int(revisit_delta.total_seconds() // 86400), 2)
        self.assertEqual(int(escalate_delta.total_seconds() // 86400), 5)

    def test_review_agent_pack_surfaces_lifecycle_governance_summary(self) -> None:
        backlog_title, retired_title = self._seed_lifecycle_governance_surface_state()

        review_pack = (self.root / "output" / "agents" / "review-agent.md").read_text(encoding="utf-8")

        self.assertIn("生命周期概念待审", review_pack)
        self.assertIn("已退役概念", review_pack)
        self.assertIn(backlog_title, review_pack)
        self.assertIn(retired_title, review_pack)

    def test_review_machine_memory_action_updates_status_and_refreshes_page(self) -> None:
        self._seed_machine_memory_actions()
        compile_wiki(self.root)

        result = review_machine_memory_action(self.root, "overloaded-concept-latency", "accepted", note="Queue it.")

        self.assertEqual(result["status"], "accepted")
        state = json.loads((self.root / ".aiwiki" / "state" / "machine-memory-actions.json").read_text(encoding="utf-8"))
        action = next(action for action in state["actions"] if action["id"] == "overloaded-concept-latency")
        self.assertEqual(action["status"], "accepted")
        self.assertEqual(action["review_note"], "Queue it.")
        self.assertTrue(action["reviewed_at"])
        actions_page = (self.root / "wiki" / "indexes" / "machine-memory-actions.md").read_text(encoding="utf-8")
        repair_plan = (self.root / "wiki" / "indexes" / "machine-memory-repair-plan.md").read_text(encoding="utf-8")
        self.assertIn("已接受", actions_page)
        self.assertIn("## Ready Now", repair_plan)
        self.assertIn("review-action overloaded-concept-latency --status resolved", repair_plan)

    def test_review_machine_memory_actions_batch_updates_many_and_compiles_once(self) -> None:
        ensure_layout(self.root)
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "link-alpha",
                        "title": "Link Alpha",
                        "kind": "add-source-concept-link",
                        "active": True,
                        "status": "proposed",
                        "policy_decision": "review",
                        "execution_band": "review-first",
                        "protocol": "general",
                        "primary_path": "wiki/sources/a.md",
                        "secondary_path": "wiki/concepts/alpha.md",
                        "priority": "low",
                    },
                    {
                        "id": "link-beta",
                        "title": "Link Beta",
                        "kind": "add-source-concept-link",
                        "active": True,
                        "status": "proposed",
                        "policy_decision": "review",
                        "execution_band": "review-first",
                        "protocol": "general",
                        "primary_path": "wiki/sources/b.md",
                        "secondary_path": "wiki/concepts/beta.md",
                        "priority": "low",
                    },
                ],
            },
        )

        with patch("aiwiki.execution.machine_memory_actions.compile_wiki") as mocked_compile:
            result = review_machine_memory_actions_batch(
                self.root,
                ["link-alpha", "link-beta", "link-alpha"],
                "accepted",
                note="batch triage",
            )

        mocked_compile.assert_called_once_with(self.root)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["action_ids"], ["link-alpha", "link-beta"])
        state = load_machine_memory_action_state(self.root)
        actions = {action["id"]: action for action in state["actions"]}
        self.assertEqual(actions["link-alpha"]["status"], "accepted")
        self.assertEqual(actions["link-beta"]["status"], "accepted")
        self.assertEqual(actions["link-alpha"]["review_note"], "batch triage")
        self.assertEqual(actions["link-beta"]["pending_review"], "true")

    def test_review_machine_memory_action_rejects_ambiguous_title_fragment(self) -> None:
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "alpha-repair",
                        "kind": "add-source-concept-link",
                        "title": "Alpha repair",
                        "status": "proposed",
                        "active": True,
                    },
                    {
                        "id": "alpha-audit",
                        "kind": "add-source-concept-link",
                        "title": "Alpha audit",
                        "status": "proposed",
                        "active": True,
                    },
                ],
            },
        )

        with self.assertRaises(RuntimeError):
            review_machine_memory_action(self.root, "Alpha", "accepted", note="Should fail.")



def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(ReviewFlowTests))
    return suite


if __name__ == "__main__":
    unittest.main()
