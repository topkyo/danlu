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


class IoFlowTests(AppFlowTestBase):
    def test_file_back_refreshes_review_queue_without_manual_compile(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")

        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")

        review_queue = (self.root / "wiki" / "indexes" / "review-queue.md").read_text(encoding="utf-8")
        decisions_index = (self.root / "wiki" / "indexes" / "decisions.md").read_text(encoding="utf-8")
        self.assertTrue((self.root / decision["path"]).exists())
        self.assertIn("Scaling Decision", review_queue)
        self.assertIn("Scaling Decision", decisions_index)

    def test_url_ingest_creates_stub_source(self) -> None:
        entry = ingest_source(self.root, "https://example.com/karpathy-note", title="Karpathy note")
        source_path = self.root / entry["stored_path"]
        self.assertTrue(source_path.exists())
        self.assertIn("来源 URL", source_path.read_text(encoding="utf-8"))

    def test_slides_output_contains_marp_header(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        slides = ask_question(self.root, "Summarize transformer scaling", "slides")
        slide_text = (self.root / slides["path"]).read_text(encoding="utf-8")
        self.assertIn("marp: true", slide_text)

    def test_decision_memo_output_reuses_compiled_seed_pack(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")
        review_page(
            self.root,
            judgment["path"],
            "confirmed",
            note="Confirmed for direct memo ask.",
            confidence="high",
        )

        memo = ask_question(self.root, "Should we keep the scaling judgment?", "decision-memo")
        memo_text = (self.root / memo["path"]).read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(memo_text)

        self.assertEqual(frontmatter["format"], "decision-memo")
        self.assertIn("output/packs/decision-memos/", frontmatter["source_pack"])
        self.assertEqual(frontmatter["judgment_asset_path"], judgment["path"])
        self.assertIn("## Seed Memo", memo_text)
        self.assertIn("## Recommendation", memo_text)
        self.assertIn("wiki/sources/", memo_text)

    def test_sop_output_reuses_compiled_seed_pack(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        self._seed_machine_memory_actions()
        compile_wiki(self.root)
        review_machine_memory_action(self.root, "overloaded-concept-latency", "accepted", note="Queue SOP draft.")

        sop = ask_question(self.root, "How should we execute the latency repair?", "sop")
        sop_text = (self.root / sop["path"]).read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(sop_text)

        self.assertEqual(frontmatter["format"], "sop")
        self.assertIn("output/packs/sop-drafts/", frontmatter["source_pack"])
        self.assertIn("## Seed SOP", sop_text)
        self.assertIn("Pattern frequency", sop_text)
        self.assertIn("apply-action", sop_text)
        self.assertIn("wiki/sources/", sop_text)

    def test_cli_apply_archive_and_revert_commands(self) -> None:
        entry = self._prepare_ready_archive_candidate()

        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(
                cli_main(["--root", str(self.root), "apply-archive", entry["id"], "--note", "Archive via CLI."]),
                0,
            )
            payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "archived")

        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(
                cli_main(["--root", str(self.root), "revert-archive", entry["id"], "--note", "Restore via CLI."]),
                0,
            )
            payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "cold")

    def test_drop_query_cache_removes_db_and_marks_status_disabled(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        db_path = self.root / ".aiwiki" / "cache.db"
        self.assertTrue(db_path.exists())

        result = drop_query_cache(self.root)

        self.assertFalse(db_path.exists())
        self.assertTrue(result["dropped"])
        cache_status = load_cache_status(self.root)
        self.assertFalse(cache_status["enabled"])
        self.assertGreaterEqual(cache_status["stats"]["drops"], 1)

    def test_cli_cache_drop_removes_db(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        code = cli_main(["--root", str(self.root), "cache", "--drop"])

        self.assertEqual(code, 0)
        self.assertFalse((self.root / ".aiwiki" / "cache.db").exists())

    def test_cli_verify_and_revert_rewrite_commands(self) -> None:
        prepared = self._prepare_concept_rewrite_proposal()
        concept_page = prepared["concept_page"]
        slug = str(prepared["slug"])

        review_concept_rewrite(self.root, slug, "accepted", note="Looks grounded.")
        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(
                cli_main(["--root", str(self.root), "apply-rewrite", slug, "--note", "Apply via CLI."]),
                0,
            )
            apply_payload = json.loads(stdout.getvalue())
        self.assertEqual(apply_payload["status"], "applied")
        self.assertEqual(apply_payload["verification_status"], "passed")

        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(
                cli_main(["--root", str(self.root), "verify-rewrite", slug, "--note", "Verify via CLI."]),
                0,
            )
            verify_payload = json.loads(stdout.getvalue())
        self.assertEqual(verify_payload["status"], "passed")

        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(
                cli_main(["--root", str(self.root), "revert-rewrite", slug, "--note", "Revert via CLI."]),
                0,
            )
            revert_payload = json.loads(stdout.getvalue())
        self.assertEqual(revert_payload["status"], "accepted")
        self.assertIn("Existing synthesis", concept_page.read_text(encoding="utf-8"))

    def test_file_back_supports_decision_and_judgment_kinds(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")

        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")

        decision_path = self.root / decision["path"]
        judgment_path = self.root / judgment["path"]
        self.assertTrue(decision_path.exists())
        self.assertTrue(judgment_path.exists())
        self.assertIn("wiki/decisions/", decision["path"])
        self.assertIn("wiki/judgments/", judgment["path"])
        decision_frontmatter = parse_frontmatter(decision_path.read_text(encoding="utf-8"))
        judgment_frontmatter = parse_frontmatter(judgment_path.read_text(encoding="utf-8"))
        self.assertEqual(decision_frontmatter["kind"], "decision")
        self.assertEqual(judgment_frontmatter["kind"], "judgment")
        self.assertEqual(decision_frontmatter["status"], "proposed")
        self.assertEqual(judgment_frontmatter["status"], "tentative")
        self.assertIn(f"wiki/sources/{entry['id']}.md", decision_frontmatter["citations"])
        self.assertIn(f"wiki/sources/{entry['id']}.md", judgment_frontmatter["citations"])
        self.assertTrue(decision_frontmatter["citation_snapshots"])
        self.assertTrue(judgment_frontmatter["citation_snapshots"])
        self.assertIn("counter_evidence", decision_frontmatter)
        self.assertIn("counter_evidence", judgment_frontmatter)
        self.assertIn("invalidation_rule", decision_frontmatter)
        self.assertIn("invalidation_rule", judgment_frontmatter)
        self.assertIn("next_signals", decision_frontmatter)
        self.assertIn("next_signals", judgment_frontmatter)
        self.assertTrue(decision_frontmatter["formed_at"])
        self.assertTrue(judgment_frontmatter["formed_at"])
        self.assertIn("last_reviewed", decision_frontmatter)
        self.assertIn("last_reviewed", judgment_frontmatter)
        self.assertIn("## Decision", decision_path.read_text(encoding="utf-8"))
        self.assertIn("## Evidence", decision_path.read_text(encoding="utf-8"))
        self.assertIn("## Counter Evidence", decision_path.read_text(encoding="utf-8"))
        self.assertIn("## Invalidation", decision_path.read_text(encoding="utf-8"))
        self.assertIn("## Next Signals", decision_path.read_text(encoding="utf-8"))
        self.assertIn("## Review History", decision_path.read_text(encoding="utf-8"))
        self.assertIn("## Review Status", decision_path.read_text(encoding="utf-8"))
        self.assertIn("## Review Notes", decision_path.read_text(encoding="utf-8"))
        self.assertIn("## Judgment", judgment_path.read_text(encoding="utf-8"))
        self.assertIn("## Signals", judgment_path.read_text(encoding="utf-8"))
        self.assertIn("## Counter Evidence", judgment_path.read_text(encoding="utf-8"))
        self.assertIn("## Invalidation", judgment_path.read_text(encoding="utf-8"))
        self.assertIn("## Next Signals", judgment_path.read_text(encoding="utf-8"))
        self.assertIn("## Review History", judgment_path.read_text(encoding="utf-8"))
        self.assertIn("## Review Status", judgment_path.read_text(encoding="utf-8"))
        self.assertIn("## Review Notes", judgment_path.read_text(encoding="utf-8"))

        compile_wiki(self.root)
        decisions_index = (self.root / "wiki" / "indexes" / "decisions.md").read_text(encoding="utf-8")
        judgments_index = (self.root / "wiki" / "indexes" / "judgments.md").read_text(encoding="utf-8")
        review_queue = (self.root / "wiki" / "indexes" / "review-queue.md").read_text(encoding="utf-8")
        self.assertIn("Scaling Decision", decisions_index)
        self.assertIn("Scaling Judgment", judgments_index)
        self.assertIn("Scaling Decision", review_queue)
        self.assertIn("Scaling Judgment", review_queue)

    def test_file_back_propagates_protocol_metadata(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Should we underwrite this thesis?", "report", protocol="investing")

        decision = file_back(self.root, report["path"], title="Investing Decision", kind="decision")

        decision_frontmatter = parse_frontmatter((self.root / decision["path"]).read_text(encoding="utf-8"))
        self.assertEqual(decision["protocol"], "investing")
        self.assertEqual(decision_frontmatter["protocol"], "investing")

    def test_file_back_uses_protocol_specific_decision_templates_and_windows(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        general_report = ask_question(self.root, "Should we adopt transformer caching?", "report", protocol="general")
        investing_report = ask_question(self.root, "Should we underwrite this thesis?", "report", protocol="investing")
        research_report = ask_question(self.root, "Should we adopt this benchmark pipeline?", "report", protocol="research")
        product_report = ask_question(self.root, "Should we launch this onboarding bet?", "report", protocol="product")
        ops_report = ask_question(self.root, "Should we fail over this incident service?", "report", protocol="ops")

        general_decision = file_back(self.root, general_report["path"], title="General Decision", kind="decision")
        investing_decision = file_back(self.root, investing_report["path"], title="Investing Decision", kind="decision")
        research_decision = file_back(self.root, research_report["path"], title="Research Decision", kind="decision")
        product_decision = file_back(self.root, product_report["path"], title="Product Decision", kind="decision")
        ops_decision = file_back(self.root, ops_report["path"], title="Ops Decision", kind="decision")

        general_text = (self.root / general_decision["path"]).read_text(encoding="utf-8")
        investing_text = (self.root / investing_decision["path"]).read_text(encoding="utf-8")
        research_text = (self.root / research_decision["path"]).read_text(encoding="utf-8")
        product_text = (self.root / product_decision["path"]).read_text(encoding="utf-8")
        ops_text = (self.root / ops_decision["path"]).read_text(encoding="utf-8")
        general_frontmatter = parse_frontmatter(general_text)
        investing_frontmatter = parse_frontmatter(investing_text)
        research_frontmatter = parse_frontmatter(research_text)
        product_frontmatter = parse_frontmatter(product_text)
        ops_frontmatter = parse_frontmatter(ops_text)

        self.assertIn("## Decision", general_text)
        self.assertIn("## Position Decision", investing_text)
        self.assertIn("## Scope And Sizing", investing_text)
        self.assertIn("## Bear Case And Invalidation", investing_text)
        self.assertIn("## Architecture Decision", research_text)
        self.assertIn("## Validation Plan", research_text)
        self.assertIn("## Rollback And Risks", research_text)
        self.assertIn("## Product Decision", product_text)
        self.assertIn("## User Problem And Bet", product_text)
        self.assertIn("## Metric And Validation", product_text)
        self.assertIn("## Incident Decision", ops_text)
        self.assertIn("## Incident Scope", ops_text)
        self.assertIn("## Residual Risk And Follow-up", ops_text)

        general_delta = datetime.fromisoformat(general_frontmatter["revisit_after"]) - datetime.fromisoformat(
            general_frontmatter["last_compiled_at"]
        )
        investing_delta = datetime.fromisoformat(investing_frontmatter["revisit_after"]) - datetime.fromisoformat(
            investing_frontmatter["last_compiled_at"]
        )
        research_delta = datetime.fromisoformat(research_frontmatter["revisit_after"]) - datetime.fromisoformat(
            research_frontmatter["last_compiled_at"]
        )
        product_delta = datetime.fromisoformat(product_frontmatter["revisit_after"]) - datetime.fromisoformat(
            product_frontmatter["last_compiled_at"]
        )
        ops_delta = datetime.fromisoformat(ops_frontmatter["revisit_after"]) - datetime.fromisoformat(
            ops_frontmatter["last_compiled_at"]
        )
        self.assertEqual(int(general_delta.total_seconds() // 86400), 7)
        self.assertEqual(int(investing_delta.total_seconds() // 86400), 3)
        self.assertEqual(int(research_delta.total_seconds() // 86400), 5)
        self.assertEqual(int(product_delta.total_seconds() // 86400), 4)
        self.assertEqual(int(ops_delta.total_seconds() // 86400), 1)

    def test_file_back_uses_protocol_specific_judgment_templates(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        investing_report = ask_question(self.root, "Will this thesis hold after earnings?", "report", protocol="investing")
        research_report = ask_question(self.root, "Latency benchmark regression after cache migration", "report", protocol="research")
        product_report = ask_question(self.root, "Is this launch ready for beta users?", "report", protocol="product")
        ops_report = ask_question(self.root, "What is the likely root cause of this incident?", "report", protocol="ops")

        investing_judgment = file_back(self.root, investing_report["path"], title="Investing Judgment", kind="judgment")
        research_judgment = file_back(self.root, research_report["path"], title="Research Judgment", kind="judgment")
        product_judgment = file_back(self.root, product_report["path"], title="Product Judgment", kind="judgment")
        ops_judgment = file_back(self.root, ops_report["path"], title="Ops Judgment", kind="judgment")

        investing_text = (self.root / investing_judgment["path"]).read_text(encoding="utf-8")
        research_text = (self.root / research_judgment["path"]).read_text(encoding="utf-8")
        product_text = (self.root / product_judgment["path"]).read_text(encoding="utf-8")
        ops_text = (self.root / ops_judgment["path"]).read_text(encoding="utf-8")

        self.assertIn("## Investment Judgment", investing_text)
        self.assertIn("## Drivers And Catalysts", investing_text)
        self.assertIn("## Risks And Invalidation", investing_text)
        self.assertIn("## Research Judgment", research_text)
        self.assertIn("## Supporting Evidence", research_text)
        self.assertIn("## Open Questions", research_text)
        self.assertIn("## Product Judgment", product_text)
        self.assertIn("## User Signal And Evidence", product_text)
        self.assertIn("## Confidence And Next Validation", product_text)
        self.assertIn("## Ops Judgment", ops_text)
        self.assertIn("## Incident Evidence", ops_text)
        self.assertIn("## Confidence And Follow-up", ops_text)

    def test_file_back_injects_protocol_specific_judgment_frontmatter(self) -> None:
        """P4-INV-3 (Round 59): newly file-backed judgments must carry the
        protocol-specific frontmatter slots (investing → thesis / catalyst /
        risk / invalidation_threshold; research → hypothesis / falsification;
        product → user_value_claim; ops → runbook_ref). Empty values are
        intentional; lint must still pass on legacy pages.
        """
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        investing_report = ask_question(self.root, "Will the NVDA thesis hold next quarter?", "report", protocol="investing")
        research_report = ask_question(self.root, "Latency hypothesis after cache migration", "report", protocol="research")
        product_report = ask_question(self.root, "Is this launch ready for beta users?", "report", protocol="product")
        ops_report = ask_question(self.root, "Likely root cause of incident X", "report", protocol="ops")

        investing_judgment = file_back(self.root, investing_report["path"], title="Investing Judgment", kind="judgment")
        research_judgment = file_back(self.root, research_report["path"], title="Research Judgment", kind="judgment")
        product_judgment = file_back(self.root, product_report["path"], title="Product Judgment", kind="judgment")
        ops_judgment = file_back(self.root, ops_report["path"], title="Ops Judgment", kind="judgment")

        from aiwiki.app_utils import parse_frontmatter

        invest_fm = parse_frontmatter((self.root / investing_judgment["path"]).read_text(encoding="utf-8"))
        research_fm = parse_frontmatter((self.root / research_judgment["path"]).read_text(encoding="utf-8"))
        product_fm = parse_frontmatter((self.root / product_judgment["path"]).read_text(encoding="utf-8"))
        ops_fm = parse_frontmatter((self.root / ops_judgment["path"]).read_text(encoding="utf-8"))

        # investing: thesis / catalyst / risk / invalidation_threshold slots all present
        self.assertIn("thesis", invest_fm)
        self.assertIn("catalyst", invest_fm)
        self.assertIn("risk", invest_fm)
        self.assertIn("invalidation_threshold", invest_fm)
        self.assertEqual(invest_fm.get("catalyst"), [])
        self.assertEqual(invest_fm.get("risk"), [])
        # research: hypothesis / falsification / experiment_refs
        self.assertIn("hypothesis", research_fm)
        self.assertIn("falsification", research_fm)
        self.assertEqual(research_fm.get("experiment_refs"), [])
        # product: user_value_claim / kill_metric
        self.assertIn("user_value_claim", product_fm)
        self.assertIn("kill_metric", product_fm)
        # ops: runbook_ref / blast_radius
        self.assertIn("runbook_ref", ops_fm)
        self.assertIn("blast_radius", ops_fm)
        # Cross-protocol negative: investing slots must not bleed into research page.
        self.assertNotIn("thesis", research_fm)
        self.assertNotIn("hypothesis", invest_fm)

    def test_file_back_generates_unique_paths_for_same_title(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")

        first = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        second = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")

        self.assertNotEqual(first["path"], second["path"])
        self.assertTrue((self.root / first["path"]).exists())
        self.assertTrue((self.root / second["path"]).exists())

    def test_file_back_sets_default_aging_windows_for_curated_pages(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")

        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")

        decision_frontmatter = parse_frontmatter((self.root / decision["path"]).read_text(encoding="utf-8"))
        judgment_frontmatter = parse_frontmatter((self.root / judgment["path"]).read_text(encoding="utf-8"))
        self.assertTrue(decision_frontmatter["revisit_after"])
        self.assertTrue(decision_frontmatter["escalate_after"])
        self.assertTrue(judgment_frontmatter["revisit_after"])
        self.assertTrue(judgment_frontmatter["escalate_after"])

    def test_cli_shell_status_command_outputs_summary_json(self) -> None:
        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(cli_main(["--root", str(self.root), "shell-status"]), 0)
            payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["contract_version"], 1)
        self.assertEqual(payload["summary_path"], "output/control/shell-summary.json")

    def test_drop_url_creates_note_and_manifest_metadata(self) -> None:
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z3ioAAAAASUVORK5CYII="
        )
        image_path = self.root / "hero.png"
        image_path.write_bytes(image_bytes)
        html_path = self.root / "page.html"
        html_path.write_text(
            "<html><head><title>Karpathy Note</title><meta name='description' content='Test description'></head>"
            "<body><nav>Ignore navigation boilerplate.</nav>"
            "<article><h1>LLM Knowledge Bases</h1><p>Compiled wiki workflows are useful.</p>"
            "<img src='hero.png' alt='hero'></article></body></html>",
            encoding="utf-8",
        )
        result = drop_url(self.root, html_path.as_uri())
        note_path = self.root / result["note_path"]
        note_text = note_path.read_text(encoding="utf-8")
        self.assertTrue(note_path.exists())
        self.assertIn("LLM Knowledge Bases", note_text)
        self.assertIn("Compiled wiki workflows are useful.", note_text)
        self.assertNotIn("Ignore navigation boilerplate.", note_text)
        self.assertEqual(len(result["asset_paths"]), 1)
        self.assertTrue((self.root / result["asset_paths"][0]).exists())
        frontmatter = parse_frontmatter(note_text)
        self.assertEqual(frontmatter["asset_files"], result["asset_paths"])

        auto_process_once(self.root, deterministic_only=True, semantic_lint=False)
        manifest = load_manifest(self.root)
        self.assertEqual(manifest["entries"][0]["source_type"], "url-drop")

    def test_drop_pdf_preserves_raw_asset_and_manifest_metadata(self) -> None:
        pdf_path = self.root / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%stub\n")
        result = drop_pdf(self.root, str(pdf_path), title="Paper")
        self.assertTrue((self.root / result["asset_path"]).exists())
        self.assertNotIn("note_path", result)
        self.assertEqual((self.root / result["asset_path"]).read_bytes(), b"%PDF-1.4\n%stub\n")
        entry = load_manifest(self.root)["entries"][-1]
        self.assertEqual(entry["source_type"], "pdf-drop")
        self.assertEqual(entry["stored_path"], result["asset_path"])

    def test_drop_image_preserves_raw_asset_and_runtime_metadata(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z3ioAAAAASUVORK5CYII="
        )
        image_path = self.root / "image.png"
        image_path.write_bytes(png_bytes)
        result = drop_image(
            self.root,
            str(image_path),
            title="Chart",
            client=StubVisionClient("- A tiny single-pixel image.\n- Confidence: low"),
        )
        self.assertTrue((self.root / result["asset_path"]).exists())
        self.assertNotIn("note_path", result)
        self.assertEqual((self.root / result["asset_path"]).read_bytes(), png_bytes)
        self.assertTrue(result["visual_analysis_present"])
        self.assertEqual(result["vision_backend"], "codex-cli")
        self.assertEqual(result["vision_status"], "generated")
        entry = load_manifest(self.root)["entries"][-1]
        self.assertEqual(entry["source_type"], "image-drop")
        self.assertEqual(entry["stored_path"], result["asset_path"])

    def test_drop_image_marks_failed_vision_without_fake_success_metadata(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z3ioAAAAASUVORK5CYII="
        )
        image_path = self.root / "broken-image.png"
        image_path.write_bytes(png_bytes)
        result = drop_image(
            self.root,
            str(image_path),
            title="Broken Vision",
            client=FailingVisionClient(),
        )
        self.assertNotIn("note_path", result)
        self.assertFalse(result["visual_analysis_present"])
        self.assertEqual(result["vision_backend"], "codex-cli")
        self.assertEqual(result["vision_status"], "failed")

    def test_drop_repo_snapshots_local_repository(self) -> None:
        repo_root = self.root / "repo"
        (repo_root / "src").mkdir(parents=True)
        (repo_root / "README.md").write_text("# Demo Repo\n\nA repository snapshot.\n", encoding="utf-8")
        (repo_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
        (repo_root / "src" / "main.py").write_text("print('demo')\n", encoding="utf-8")
        result = drop_repo(self.root, str(repo_root), title="Demo Repo")
        note_text = (self.root / result["note_path"]).read_text(encoding="utf-8")
        self.assertIn("Repository Tree", note_text)
        self.assertIn("README", note_text)



def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(IoFlowTests))
    return suite


if __name__ == "__main__":
    unittest.main()
