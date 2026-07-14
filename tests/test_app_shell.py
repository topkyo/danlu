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
from aiwiki.app_compile import compile_wiki, lint_wiki, rank_concepts, rank_sources, set_active_protocol
from aiwiki.app_execution import append_execution_receipt_history
from aiwiki.app_lifecycle import protocol_related_concept_lifecycle_summary
from aiwiki.app_memory import (
    active_corpus_bridge_evidence_ids,
    build_archive_candidate_state,
    build_machine_memory_query,
)
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
from aiwiki.config import BACKEND_OPENAI_API, BACKEND_OPENCODE_API, LLMConfig
from aiwiki.content.concepts import entry_concept_terms
from aiwiki.content.io import (
    collect_recent_output_artifacts,
    ingest_source,
)
from aiwiki.content.memory import (
    collect_machine_memory_actions,
    load_execution_policy_decision_history,
    placeholder_concept_slugs,
)
from aiwiki.drop import _fetch_url, drop_image, drop_pdf, drop_repo, drop_url
from aiwiki.execution.archive import (
    apply_material_archive,
    revert_material_archive,
)
from aiwiki.execution.ask import (
    ask_question,
    file_back,
)
from aiwiki.execution.concept_rewrite import (
    apply_concept_rewrite,
    revert_concept_rewrite,
    review_concept_rewrite,
    verify_concept_rewrite,
)
from aiwiki.execution.lifecycle import (
    reactivate_concept,
    retire_concept,
    review_concept,
    review_concepts_batch,
)
from aiwiki.execution.machine_memory_actions import (
    _save_machine_memory_action_records,
    apply_machine_memory_action,
    revert_machine_memory_action,
    review_machine_memory_action,
    review_machine_memory_actions_batch,
)
from aiwiki.execution.review import review_page
from aiwiki.execution.runtime_surfaces import (
    nightly_health,
    shell_status,
)
from aiwiki.llm import CompletionResult
from aiwiki.memory.graph import render_machine_memory_graph_html
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


class ShellFlowTests(AppFlowTestBase):
    def test_furnace_center_surfaces_pilots_packs_receipts_and_commands(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        set_active_protocol(self.root, "research")
        report = ask_question(self.root, "Latency benchmark regression after cache migration", "report", protocol="research")
        file_back(self.root, report["path"], title="Latency Decision", kind="decision")
        judgment = file_back(self.root, report["path"], title="Latency Judgment", kind="judgment")
        review_page(
            self.root,
            judgment["path"],
            "confirmed",
            note="Stable enough for cockpit surfaces.",
            confidence="high",
        )
        self._seed_machine_memory_actions()
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))
        entry = load_manifest(self.root)["entries"][0]
        action_state = load_machine_memory_action_state(self.root)
        actions = [dict(item) for item in action_state.get("actions", []) if isinstance(item, dict)]
        actions.append(
            {
                "id": "manual-link-action",
                "kind": "add-source-concept-link",
                "title": "Manual safe apply link",
                "reason": "Backfill source/concept link for cockpit receipts.",
                "primary_path": f"wiki/sources/{entry['id']}.md",
                "secondary_path": f"wiki/concepts/{concept_slug}.md",
                "status": "accepted",
                "priority": "low",
                "active": True,
                "source_ids": [entry["id"]],
                "concept_slugs": [concept_slug],
                "protocol": "research",
            }
        )
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": actions,
            },
        )
        action_id = "manual-link-action"
        review_machine_memory_action(self.root, action_id, "accepted", note="Queue apply path.")
        review_machine_memory_action(self.root, "overloaded-concept-latency", "accepted", note="Queue SOP draft.")
        compile_wiki(self.root)
        dry_run = apply_machine_memory_action(self.root, action_id, dry_run=True)
        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        apply_machine_memory_action(
            self.root,
            action_id,
            bundle_path=dry_run["bundle_path"],
            note="Apply for cockpit receipt coverage.",
        )

        dashboard_payload = (self.root / "wiki" / "indexes" / "furnace-center.md").read_text(encoding="utf-8")
        html_payload = (self.root / "output" / "control" / "furnace-center.html").read_text(encoding="utf-8")

        self.assertIn("## 当前协议 Pilot", dashboard_payload)
        self.assertIn("研发协议 Pilot Scorecard", dashboard_payload)
        self.assertIn("## 最新输出 Packs", dashboard_payload)
        self.assertIn("Review Pack", dashboard_payload)
        self.assertIn("Decision Memo", dashboard_payload)
        self.assertIn("SOP Draft", dashboard_payload)
        self.assertIn("## 最近执行回执", dashboard_payload)
        self.assertIn("receipt", dashboard_payload)
        self.assertIn("## 快速命令", dashboard_payload)
        self.assertIn("protocol-status", dashboard_payload)
        self.assertIn("当前协议 Pilot", html_payload)
        self.assertIn("最新输出 Packs", html_payload)
        self.assertIn("最近执行回执", html_payload)
        self.assertIn("快速命令", html_payload)
        self.assertIn("研发协议 Pilot Scorecard", html_payload)

    def test_furnace_center_keeps_protocol_receipts_beyond_global_recent_cutoff(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        set_active_protocol(self.root, "research")
        append_execution_receipt_history(
            self.root,
            {
                "kind": "execution-receipt",
                "operation": "apply",
                "protocol": "research",
                "action_id": "research-action",
                "title": "Research receipt",
                "receipt_path": "output/control/execution-receipts/research-action.json",
                "applied_at": "2026-04-09T10:00:00+08:00",
            },
        )
        for index in range(9):
            append_execution_receipt_history(
                self.root,
                {
                    "kind": "execution-receipt",
                    "operation": "apply",
                    "protocol": "investing",
                    "action_id": f"investing-action-{index}",
                    "title": f"Investing receipt {index}",
                    "receipt_path": f"output/control/execution-receipts/investing-action-{index}.json",
                    "applied_at": f"2026-04-09T10:{index + 1:02d}:00+08:00",
                },
            )

        compile_wiki(self.root)

        dashboard_payload = (self.root / "wiki" / "indexes" / "furnace-center.md").read_text(encoding="utf-8")
        html_payload = (self.root / "output" / "control" / "furnace-center.html").read_text(encoding="utf-8")

        self.assertIn("Research receipt", dashboard_payload)
        self.assertIn("Research receipt", html_payload)

    def test_furnace_center_filters_actions_and_proposals_to_active_protocol(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        self._seed_machine_memory_actions()
        set_active_protocol(self.root, "research")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))
        entry = load_manifest(self.root)["entries"][0]
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "research-manual-link",
                        "kind": "add-source-concept-link",
                        "title": "Research safe apply link",
                        "reason": "Research cockpit action.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                        "protocol": "research",
                    },
                    {
                        "id": "investing-manual-link",
                        "kind": "add-source-concept-link",
                        "title": "Investing safe apply link",
                        "reason": "Investing cockpit action.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                        "protocol": "investing",
                    },
                ],
            },
        )

        compile_wiki(self.root)

        dashboard_payload = (self.root / "wiki" / "indexes" / "furnace-center.md").read_text(encoding="utf-8")
        html_payload = (self.root / "output" / "control" / "furnace-center.html").read_text(encoding="utf-8")

        self.assertIn("Research safe apply link", dashboard_payload)
        self.assertNotIn("Investing safe apply link", dashboard_payload)
        self.assertIn("Research safe apply link", html_payload)
        self.assertNotIn("Investing safe apply link", html_payload)

    def test_furnace_center_surfaces_lifecycle_governance_summary(self) -> None:
        backlog_title, retired_title = self._seed_lifecycle_governance_surface_state()

        dashboard_payload = (self.root / "wiki" / "indexes" / "furnace-center.md").read_text(encoding="utf-8")
        html_payload = (self.root / "output" / "control" / "furnace-center.html").read_text(encoding="utf-8")

        self.assertIn("## Lifecycle 治理摘要", dashboard_payload)
        self.assertIn("### Lifecycle Concept Backlog", dashboard_payload)
        self.assertIn("### Retired Concepts", dashboard_payload)
        self.assertIn(backlog_title, dashboard_payload)
        self.assertIn(retired_title, dashboard_payload)
        self.assertIn("生命周期治理", html_payload)
        self.assertIn("已退役概念", html_payload)
        self.assertIn(backlog_title, html_payload)
        self.assertIn(retired_title, html_payload)

    def test_shell_status_writes_summary_with_contract_version_and_capabilities(self) -> None:
        lifecycle_path = self.root / ".aiwiki" / "state" / "knowledge-lifecycle.json"
        history_path = self.root / ".aiwiki" / "state" / "runtime-history.jsonl"
        protocol_path = self.root / ".aiwiki" / "state" / "protocol.json"
        protocol_before = protocol_path.read_text(encoding="utf-8")
        self.assertFalse(lifecycle_path.exists())
        self.assertFalse(history_path.exists())

        result = shell_status(self.root)

        self.assertEqual(result["kind"], "product-shell-summary")
        self.assertEqual(result["contract_version"], 1)
        self.assertEqual(result["summary_path"], "output/control/shell-summary.json")
        self.assertIn("capabilities", result)
        self.assertIn("commands", result["capabilities"])
        self.assertIn("shell-status", result["capabilities"]["commands"]["p0"])
        self.assertFalse(result["capabilities"]["supports_hidden_state_read"])
        self.assertIn("llm_status", result)
        self.assertIn("model_requested", result["llm_status"])
        self.assertIn("effective_model", result["llm_status"])
        self.assertIn("codex_reasoning_effort", result["llm_status"])
        self.assertIn("usage_visibility", result["llm_status"])
        self.assertIn("usage_accounting", result["llm_status"])
        self.assertIn("judgment_assets", result)
        self.assertEqual(result["judgment_assets"]["counts"]["pages"], 0)
        self.assertEqual(result["links"]["judgment_assets_markdown"], "wiki/indexes/judgment-assets.md")
        self.assertEqual(result["links"]["cognitive_history_markdown"], "wiki/indexes/cognitive-history.md")
        self.assertEqual(result["recent_outputs"], [])
        self.assertEqual(result["recent_receipts"], [])
        self.assertEqual(result["recent_runs"], [])
        self.assertFalse(lifecycle_path.exists())
        self.assertFalse(history_path.exists())
        self.assertEqual(protocol_before, protocol_path.read_text(encoding="utf-8"))

        written = json.loads(shell_summary_path(self.root).read_text(encoding="utf-8"))
        self.assertEqual(written["contract_version"], 1)
        self.assertIn("capabilities", written)
        self.assertIn("judgment_assets", written)

    def test_shell_status_surfaces_metrics_unavailable_sentinel(self) -> None:
        with patch("aiwiki.metrics_io.build_metrics_snapshot", side_effect=RuntimeError("metrics boom")):
            result = shell_status(self.root)

        self.assertEqual(
            result["metrics"],
            [
                {
                    "key": "_metrics_unavailable",
                    "value": None,
                    "unit": "",
                    "reason": "metrics boom",
                    "sample_size": 0,
                    "error_type": "RuntimeError",
                }
            ],
        )

    def test_shell_status_surfaces_recent_outputs_and_query_runs(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = run_ask(self.root, "Compare transformer scaling tradeoffs", "report", client=StubClient([_VALID_REPORT_BODY]))

        result = shell_status(self.root)

        self.assertTrue(result["recent_outputs"])
        self.assertEqual(result["recent_outputs"][0]["path"], report["path"])
        self.assertEqual(result["recent_outputs"][0]["run_id"], report["run_id"])
        self.assertEqual(result["recent_outputs"][0]["run_notes_path"], report["run_notes_path"])
        self.assertTrue(result["recent_runs"])
        self.assertEqual(result["recent_runs"][0]["event_type"], "query")
        self.assertEqual(result["recent_runs"][0]["output_path"], report["path"])
        self.assertEqual(result["recent_runs"][0]["run_id"], report["run_id"])
        self.assertEqual(result["recent_runs"][0]["run_notes_path"], report["run_notes_path"])

    def test_collect_recent_output_artifacts_marks_degraded_outputs_for_downstream_filters(self) -> None:
        report_path = self.root / "output" / "reports" / "degraded-report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            "---\n"
            'id: "degraded-report"\n'
            'kind: "output"\n'
            'format: "report"\n'
            'protocol: "general"\n'
            'created_at: "2026-05-18T00:00:00Z"\n'
            'delivery_mode: "deterministic-fallback"\n'
            'llm_status: "timeout_or_unavailable"\n'
            'llm_backend: "opencode-api"\n'
            'llm_model: "deepseek-v4-pro"\n'
            'llm_failure_reason: "timeout"\n'
            "---\n\n"
            "# Degraded report\n",
            encoding="utf-8",
        )

        artifacts = collect_recent_output_artifacts(self.root, limit=8)

        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["path"], "output/reports/degraded-report.md")
        self.assertEqual(artifacts[0]["delivery_mode"], "deterministic-fallback")
        self.assertEqual(artifacts[0]["llm_status"], "timeout_or_unavailable")
        self.assertEqual(artifacts[0]["llm_backend"], "opencode-api")
        self.assertEqual(artifacts[0]["llm_model"], "deepseek-v4-pro")
        self.assertEqual(artifacts[0]["artifact_quality"], "degraded")
        self.assertEqual(artifacts[0]["contains_llm_placeholder"], "false")

    def test_collect_recent_output_artifacts_skips_background_pending_reports(self) -> None:
        report_path = self.root / "output" / "reports" / "pending-report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            "---\n"
            'id: "pending-report"\n'
            'kind: "output"\n'
            'format: "report"\n'
            'protocol: "general"\n'
            'created_at: "2026-05-18T00:00:00Z"\n'
            'run_id: "ask-pending"\n'
            'background_job_id: "ask-report-job"\n'
            'background_status: "running"\n'
            'delivery_mode: "background-pending"\n'
            'llm_status: "pending"\n'
            "---\n\n"
            "# Pending report\n",
            encoding="utf-8",
        )

        artifacts = collect_recent_output_artifacts(self.root, limit=8)

        self.assertEqual(artifacts, [])

    def test_collect_recent_output_artifacts_skips_unfilled_placeholder_reports(self) -> None:
        report_path = self.root / "output" / "reports" / "placeholder-report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            "---\n"
            'id: "placeholder-report"\n'
            'kind: "output"\n'
            'format: "report"\n'
            'protocol: "general"\n'
            'created_at: "2026-05-18T00:00:00Z"\n'
            'delivery_mode: "background-pending"\n'
            'llm_status: "pending"\n'
            "---\n\n"
            "# Placeholder report\n\n"
            "## 结论\n"
            "_LLM: 请在此填入结论。_\n",
            encoding="utf-8",
        )

        artifacts = collect_recent_output_artifacts(self.root, limit=8)

        self.assertEqual(artifacts, [])

    def test_ask_entrypoints_reject_obsidian_open_links(self) -> None:
        link = "obsidian://open?vault=%E7%82%BC%E4%B8%B9%E7%82%89&file=output%2Freports%2Fx.md"

        with self.assertRaisesRegex(ValueError, "navigation targets"):
            ask_question(self.root, link, "report")
        with self.assertRaisesRegex(ValueError, "navigation targets"):
            run_ask(self.root, link, "note")

    def test_shell_status_filters_legacy_obsidian_open_route_telemetry(self) -> None:
        from aiwiki.app_state import save_query_route_telemetry

        save_query_route_telemetry(
            self.root,
            {
                "version": 1,
                "updated_at": "2026-05-18T00:00:00Z",
                "state_path": ".aiwiki/state/query-route-telemetry.json",
                "entries": [
                    {
                        "question_preview": "obsidian://open?vault=v&file=output%2Freports%2Fx.md",
                        "selected_strategy": "concept-first",
                    },
                    {"question_preview": "real question", "selected_strategy": "source-first"},
                ],
                "strategy_counts": {"concept-first": 1, "source-first": 1},
                "protocol_counts": {"general": 2},
                "last_entry": {
                    "question_preview": "obsidian://open?vault=v&file=output%2Freports%2Fx.md",
                    "selected_strategy": "concept-first",
                },
            },
        )

        result = shell_status(self.root)

        self.assertEqual(len(result["route_telemetry"]["entries"]), 1)
        self.assertEqual(result["route_telemetry"]["last_entry"]["question_preview"], "real question")
        self.assertEqual(result["dashboard"]["last_route"]["question_preview"], "real question")

    def test_shell_status_surfaces_latest_llm_run_and_llm_health(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        report_markdown = _VALID_REPORT_BODY

        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "opencode-api", "AIWIKI_OPENCODE_API_KEY": "opencode_test_key"}, clear=False):
            ask_result = run_ask(
                self.root,
                "Check shell summary llm health",
                "report",
                client=StubClient([report_markdown], backend="opencode-api", backend_requested="opencode-api"),
            )
            result = shell_status(self.root)

        self.assertEqual(result["latest_llm_run"]["event"], "run-ask")
        self.assertEqual(result["latest_llm_run"]["status"], "success")
        self.assertEqual(result["latest_llm_run"]["backend_requested"], "opencode-api")
        self.assertEqual(result["latest_llm_run"]["backend_effective"], "opencode-api")
        self.assertEqual(result["latest_llm_run"]["model_selected"], "stub-model")
        self.assertEqual(result["latest_llm_run"]["model_final"], "stub-model")
        self.assertTrue(result["latest_llm_run"]["contract_validated"])
        self.assertEqual(result["latest_llm_run"]["result_path"], ask_result["path"])
        self.assertEqual(result["latest_llm_run"]["receipt_path"], ".aiwiki/logs/llm-receipts.jsonl")
        self.assertEqual(result["latest_llm_run"]["log_path"], ".aiwiki/logs/runs.jsonl")
        self.assertIn("./scripts/aiwiki-launcher.sh run-ask", result["latest_llm_run"]["recovery_command"])

        self.assertEqual(result["llm_health"]["status"], "healthy")
        self.assertEqual(result["llm_health"]["backend_requested"], "opencode-api")
        self.assertEqual(result["llm_health"]["backend_effective"], "opencode-api")
        self.assertEqual(result["llm_health"]["model_selected"], "stub-model")
        self.assertEqual(result["llm_health"]["model_final"], "stub-model")
        self.assertFalse(result["llm_health"]["route_drift"])
        self.assertEqual(result["llm_health"]["result_path"], ask_result["path"])
        self.assertEqual(result["llm_health"]["receipt_path"], ".aiwiki/logs/llm-receipts.jsonl")
        self.assertEqual(result["llm_health"]["log_path"], ".aiwiki/logs/runs.jsonl")

    def test_shell_status_surfaces_curated_page_roots(self) -> None:
        # EP-015: curated_page_roots is a single source of truth for which
        # repo-relative prefixes count as curated pages. The plugin uses
        # these prefixes (instead of hardcoded strings) to detect whether
        # the active file is a curated page.
        result = shell_status(self.root)
        roots = result["curated_page_roots"]
        self.assertIsInstance(roots, dict)
        self.assertEqual(roots.get("decisions"), "wiki/decisions/")
        self.assertEqual(roots.get("judgments"), "wiki/judgments/")
        # Prefixes must be repo-relative and directory-terminated so the
        # plugin can use startswith() without dealing with vault-absolute paths.
        for prefix in roots.values():
            self.assertIsInstance(prefix, str)
            self.assertTrue(prefix.endswith("/"))
            self.assertFalse(prefix.startswith("/"))

        # Indirect writers (compile_wiki) must also persist curated_page_roots
        # so the plugin sees it regardless of which entry point refreshed
        # shell-summary.json.
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        persisted = json.loads((self.root / "output" / "control" / "shell-summary.json").read_text(encoding="utf-8"))
        self.assertIn("curated_page_roots", persisted)
        self.assertEqual(persisted["curated_page_roots"].get("decisions"), "wiki/decisions/")
        self.assertEqual(persisted["curated_page_roots"].get("judgments"), "wiki/judgments/")

    def test_shell_status_surfaces_latest_shell_sync_run(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        # First shell_status call persists a summary; the returned
        # latest_shell_sync_run reflects whatever summary existed beforehand
        # (e.g. one written by compile_wiki).
        first = shell_status(self.root)

        # Second shell_status call: the previous summary on disk is the one
        # written by `first`. build_shell_summary must surface a snapshot of it.
        second = shell_status(self.root)
        snapshot = second["latest_shell_sync_run"]
        self.assertIsInstance(snapshot, dict)
        self.assertTrue(snapshot, "expected non-empty snapshot on second run")
        self.assertEqual(snapshot["generated_by"], "aiwiki-shell-status")
        self.assertEqual(snapshot["generated_at"], first["generated_at"])
        self.assertEqual(snapshot["summary_path"], first["summary_path"])
        self.assertEqual(snapshot["contract_version"], first["contract_version"])
        self.assertEqual(snapshot["active_protocol"], first["active_protocol"])
        self.assertIsInstance(snapshot["file_mtime_epoch"], float)
        self.assertGreater(snapshot["file_mtime_epoch"], 0.0)

        # Missing on-disk summary → empty snapshot (contract for fresh vaults).
        shell_summary_file = self.root / "output" / "control" / "shell-summary.json"
        shell_summary_file.unlink()
        third = shell_status(self.root)
        # `third` just wrote a new summary; but its own latest_shell_sync_run
        # was computed before write, when the file was absent → {}.
        self.assertEqual(third["latest_shell_sync_run"], {})

    def test_shell_status_marks_llm_route_drift_when_current_route_differs(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        report_markdown = _VALID_REPORT_BODY

        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "opencode-api", "AIWIKI_OPENCODE_API_KEY": "opencode_test_key"}, clear=False):
            run_ask(
                self.root,
                "Check llm route drift",
                "report",
                client=StubClient([report_markdown], backend="opencode-api", backend_requested="opencode-api"),
            )

        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "openai-api", "OPENAI_API_KEY": "openai_test_key"}, clear=False):
            result = shell_status(self.root)

        self.assertTrue(result["llm_health"]["route_drift"])
        self.assertEqual(result["llm_health"]["status"], "unknown")
        self.assertEqual(result["llm_health"]["backend"], "openai-api")
        self.assertEqual(result["llm_health"]["backend_effective"], "opencode-api")
        self.assertIn("Current route changed", result["llm_health"]["reason"])

    def test_shell_status_surfaces_historical_frontdoor_failure_lineage_without_recovery_fallback(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "opencode-api", "AIWIKI_OPENCODE_API_KEY": "opencode_test_key"}, clear=False):
            with patch(
                "aiwiki.app_shell.load_llm_receipt_history",
                return_value=[
                    {
                        "created_at": "2026-04-22T00:00:00+00:00",
                        "event": "run-ask-frontdoor",
                        "status": "success",
                        "question": "Check frontdoor fallback lineage",
                        "format": "report",
                        "protocol": "general",
                        "target": "output/reports/query-frontdoor.md",
                        "backend_requested": "opencode-api",
                        "backend_effective": "opencode-api",
                        "model_selected": "stub-model",
                        "model_final": "stub-model",
                        "fallback_stage": "",
                        "fallback_reason": "usage limit exceeded",
                        "contract_validated": False,
                        "delivery_mode": "deterministic-fallback",
                        "primary_attempt_status": "failed",
                        "primary_error": "usage limit exceeded",
                        "fallback_used": True,
                        "fallback_from": "run-ask",
                        "fallback_command": "ask",
                        "prompt_profile": "balanced",
                        "retry_prompt_profile": "",
                    }
                ],
            ):
                result = shell_status(self.root)

        self.assertEqual(result["latest_llm_run"]["event"], "run-ask-frontdoor")
        self.assertEqual(result["latest_llm_run"]["delivery_mode"], "deterministic-fallback")
        self.assertTrue(result["latest_llm_run"]["fallback_used"])
        self.assertEqual(result["latest_llm_run"]["fallback_from"], "run-ask")
        self.assertEqual(result["latest_llm_run"]["fallback_command"], "ask")
        self.assertEqual(result["latest_llm_run"]["result_path"], "output/reports/query-frontdoor.md")
        self.assertNotIn("--fallback-to-ask", result["latest_llm_run"]["recovery_command"])

        self.assertEqual(result["llm_health"]["status"], "degraded")
        self.assertEqual(result["llm_health"]["fallback_command"], "ask")
        self.assertEqual(result["llm_health"]["result_path"], "output/reports/query-frontdoor.md")
        self.assertIn("fell back to deterministic ask", result["llm_health"]["reason"])

    def test_shell_status_marks_compile_summary_chain_fallback_as_degraded(self) -> None:
        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "opencode-api", "AIWIKI_OPENCODE_API_KEY": "opencode_test_key"}, clear=False):
            with patch(
                "aiwiki.app_shell.load_llm_receipt_history",
                return_value=[
                    {
                        "created_at": "2026-04-22T00:00:00+00:00",
                        "event": "run-compile-summary",
                        "status": "success",
                        "backend_requested": "opencode-api",
                        "backend_effective": "opencode-api",
                        "model_selected": "stub-model",
                        "model_final": "stub-model",
                        "fallback_stage": "model-chain",
                        "fallback_reason": "model validation failed",
                        "contract_validated": True,
                        "delivery_mode": "llm-fallback-chain",
                        "fallback_used": True,
                        "fallback_from": "run-compile",
                        "fallback_command": "compile",
                        "primary_attempt_status": "failed",
                        "primary_error": "model validation failed",
                        "prompt_profile": "balanced",
                        "retry_prompt_profile": "",
                    }
                ],
            ):
                result = shell_status(self.root)

        self.assertEqual(result["llm_health"]["status"], "degraded")
        self.assertEqual(result["llm_health"]["reason"], "LLM completed via model-chain fallback.")

    def test_shell_status_marks_compile_summary_skip_as_healthy(self) -> None:
        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "opencode-api", "AIWIKI_OPENCODE_API_KEY": "opencode_test_key"}, clear=False):
            with patch(
                "aiwiki.app_shell.load_llm_receipt_history",
                return_value=[
                    {
                        "created_at": "2026-04-22T00:00:00+00:00",
                        "event": "run-compile-summary",
                        "status": "success",
                        "backend_requested": "opencode-api",
                        "backend_effective": "opencode-api",
                        "model_selected": "stub-model",
                        "model_final": "stub-model",
                        "delivery_mode": "skipped",
                        "fallback_used": False,
                    }
                ],
            ):
                result = shell_status(self.root)

        self.assertEqual(result["llm_health"]["status"], "healthy")
        self.assertEqual(result["llm_health"]["reason"], "Recent run-compile-summary skipped (no LLM invocation).")

    def test_shell_status_uses_prompt_profile_reason_for_fallback_chain(self) -> None:
        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "opencode-api", "AIWIKI_OPENCODE_API_KEY": "opencode_test_key"}, clear=False):
            with patch(
                "aiwiki.app_shell.load_llm_receipt_history",
                return_value=[
                    {
                        "created_at": "2026-04-22T00:00:00+00:00",
                        "event": "run-lint",
                        "status": "success",
                        "backend_requested": "opencode-api",
                        "backend_effective": "opencode-api",
                        "model_selected": "stub-model",
                        "model_final": "stub-model",
                        "fallback_stage": "prompt-profile",
                        "fallback_reason": "prompt validation failed",
                        "contract_validated": True,
                        "delivery_mode": "llm-fallback-chain",
                        "fallback_used": True,
                        "fallback_from": "run-lint",
                        "fallback_command": "lint",
                        "primary_attempt_status": "failed",
                        "primary_error": "prompt validation failed",
                        "prompt_profile": "balanced",
                        "retry_prompt_profile": "strict",
                    }
                ],
            ):
                result = shell_status(self.root)

        self.assertEqual(result["llm_health"]["status"], "degraded")
        self.assertEqual(result["llm_health"]["reason"], "LLM completed via prompt-profile retry.")

    def test_shell_status_uses_custom_fallback_stage_reason(self) -> None:
        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "opencode-api", "AIWIKI_OPENCODE_API_KEY": "opencode_test_key"}, clear=False):
            with patch(
                "aiwiki.app_shell.load_llm_receipt_history",
                return_value=[
                    {
                        "created_at": "2026-04-22T00:00:00+00:00",
                        "event": "run-compile",
                        "status": "success",
                        "backend_requested": "opencode-api",
                        "backend_effective": "opencode-api",
                        "model_selected": "stub-model",
                        "model_final": "stub-model",
                        "fallback_stage": "prompt-profile+model-chain",
                        "fallback_reason": "validation failed",
                        "contract_validated": True,
                        "delivery_mode": "llm-fallback-chain",
                        "fallback_used": True,
                        "fallback_from": "run-compile",
                        "fallback_command": "compile",
                        "primary_attempt_status": "failed",
                        "primary_error": "validation failed",
                        "prompt_profile": "balanced",
                        "retry_prompt_profile": "strict",
                    }
                ],
            ):
                result = shell_status(self.root)

        self.assertEqual(result["llm_health"]["reason"], "LLM completed via fallback (prompt-profile+model-chain).")

    def test_shell_status_surfaces_recent_receipts_and_nightly_snapshot(self) -> None:
        entry = self._prepare_ready_archive_candidate()
        archive_result = apply_material_archive(self.root, entry["id"], note="Archive for shell summary.")
        nightly_health(self.root)

        result = shell_status(self.root)

        self.assertTrue(result["nightly"]["available"])
        self.assertTrue(result["recent_receipts"])
        self.assertTrue(result["recent_receipts"][0]["action_id"])
        self.assertEqual(result["recent_receipts"][0]["receipt_path"], archive_result["receipt_path"])
        self.assertEqual(result["recent_receipts"][0]["operation"], "apply")
        self.assertEqual(result["nightly"]["retention"]["policy"], "archive-first")
        self.assertFalse(result["nightly"]["retention"]["delete_receipts_by_default"])

    def test_shell_status_exposes_failed_nightly_recovery_command(self) -> None:
        log_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            json.dumps(
                {
                    "event": "run-nightly",
                    "status": "failed",
                    "compile_limit": 2,
                    "semantic_lint": False,
                    "error_class": "timeout",
                    "error": "LLM endpoint timed out after 60 seconds.",
                    "backend_effective": "opencode-api",
                    "model_final": "deepseek-v4-pro",
                    "created_at": "2026-05-24T00:00:00+00:00",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = shell_status(self.root)

        self.assertEqual(result["nightly"]["llm_receipt"]["status"], "failed")
        self.assertEqual(result["nightly"]["llm_receipt"]["error_class"], "timeout")
        self.assertEqual(
            result["nightly"]["recovery_command"],
            "./scripts/aiwiki-launcher.sh run-nightly --compile-limit 2 --no-semantic-lint",
        )

    def test_failed_nightly_marks_previous_success_execution_receipt_stale(self) -> None:
        state_dir = self.root / ".aiwiki" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        old_receipt = {
            "kind": "execution-receipt",
            "operation": "run-nightly",
            "status": "success",
            "receipt_path": "output/control/execution-receipts/run-nightly-nightly-health.json",
            "target_file": ".aiwiki/state/nightly-health.json",
            "applied_at": "2026-05-23T00:00:00+00:00",
        }
        (state_dir / "execution-receipts.jsonl").write_text(json.dumps(old_receipt) + "\n", encoding="utf-8")
        log_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            json.dumps(
                {
                    "event": "run-nightly",
                    "status": "failed",
                    "compile_limit": 5,
                    "semantic_lint": True,
                    "error_class": "timeout",
                    "created_at": "2026-05-24T00:00:00+00:00",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = shell_status(self.root)

        execution_receipt = result["nightly"]["execution_receipt"]
        self.assertFalse(execution_receipt["available"])
        self.assertTrue(execution_receipt["stale"])
        self.assertEqual(execution_receipt["status"], "stale-after-failed-run-nightly")
        self.assertEqual(execution_receipt["receipt_path"], "")
        self.assertEqual(execution_receipt["stale_receipt_path"], old_receipt["receipt_path"])

    def test_latest_nightly_llm_success_requires_matching_execution_receipt(self) -> None:
        state_dir = self.root / ".aiwiki" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        old_receipt = {
            "kind": "execution-receipt",
            "operation": "run-nightly",
            "status": "success",
            "receipt_path": "output/control/execution-receipts/run-nightly-nightly-health.json",
            "target_file": ".aiwiki/state/nightly-health.json",
            "applied_at": "2026-05-23T00:00:00+00:00",
        }
        (state_dir / "execution-receipts.jsonl").write_text(json.dumps(old_receipt) + "\n", encoding="utf-8")
        log_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            json.dumps(
                {
                    "event": "run-nightly",
                    "status": "success",
                    "compile_limit": 5,
                    "semantic_lint": True,
                    "created_at": "2026-05-24T00:00:00+00:00",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = shell_status(self.root)

        execution_receipt = result["nightly"]["execution_receipt"]
        self.assertFalse(execution_receipt["available"])
        self.assertTrue(execution_receipt["stale"])
        self.assertEqual(execution_receipt["status"], "stale-after-unmatched-run-nightly-proof")
        self.assertEqual(execution_receipt["receipt_path"], "")
        self.assertEqual(execution_receipt["stale_receipt_path"], old_receipt["receipt_path"])

    def test_latest_nightly_llm_success_accepts_matching_execution_receipt(self) -> None:
        state_dir = self.root / ".aiwiki" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        receipt = {
            "kind": "execution-receipt",
            "operation": "run-nightly",
            "status": "success",
            "receipt_path": "output/control/execution-receipts/run-nightly-nightly-health.json",
            "target_file": ".aiwiki/state/nightly-health.json",
            "applied_at": "2026-05-24T00:00:01+00:00",
        }
        (state_dir / "execution-receipts.jsonl").write_text(json.dumps(receipt) + "\n", encoding="utf-8")
        log_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            json.dumps(
                {
                    "event": "run-nightly",
                    "status": "success",
                    "compile_limit": 5,
                    "semantic_lint": True,
                    "created_at": "2026-05-24T00:00:00+00:00",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = shell_status(self.root)

        execution_receipt = result["nightly"]["execution_receipt"]
        self.assertTrue(execution_receipt["available"])
        self.assertFalse(execution_receipt["stale"])
        self.assertEqual(execution_receipt["receipt_path"], receipt["receipt_path"])

    def test_shell_status_exposes_state_aware_execution_controls(self) -> None:
        archive_entry = self._prepare_ready_archive_candidate()
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
            note="Apply before shell control check.",
            bundle_path=dry_run["bundle_path"],
        )
        apply_material_archive(self.root, archive_entry["id"], note="Archive before shell control check.")

        result = shell_status(self.root)

        self.assertNotIn("manual-link-action", result["execution_controls"]["apply_ready_action_ids"])
        self.assertIn("manual-link-action", result["execution_controls"]["revert_ready_action_ids"])
        self.assertNotIn(archive_entry["id"], result["execution_controls"]["apply_ready_archive_entry_ids"])
        self.assertIn(archive_entry["id"], result["execution_controls"]["revert_ready_archive_entry_ids"])
        action_controls = {
            entry["action_id"]: entry
            for entry in result["execution_controls"]["actions"]
        }
        archive_controls = {
            entry["entry_id"]: entry
            for entry in result["execution_controls"]["archives"]
        }
        self.assertFalse(action_controls["manual-link-action"]["can_apply"])
        self.assertTrue(action_controls["manual-link-action"]["can_revert"])
        self.assertFalse(archive_controls[archive_entry["id"]]["can_apply"])
        self.assertTrue(archive_controls[archive_entry["id"]]["can_revert"])

        revert_machine_memory_action(self.root, "manual-link-action", note="Rollback after shell control check.")
        reverted = shell_status(self.root)

        self.assertNotIn("manual-link-action", reverted["execution_controls"]["apply_ready_action_ids"])
        self.assertNotIn("manual-link-action", reverted["execution_controls"]["revert_ready_action_ids"])

    def test_shell_status_exposes_identity_aware_review_and_execution_objects(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scaling tradeoffs", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")

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
        updated = concept_page.read_text(encoding="utf-8").replace("Existing synthesis", "Rewritten synthesis")
        compile_result = run_compile(self.root, client=StubClient([updated]), limit=1)
        rewrite_slug = Path(compile_result["updated_rewrite_proposal_pages"][0]).stem

        archive_entry = self._prepare_ready_archive_candidate()
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "identity-aware-action",
                        "kind": "add-source-concept-link",
                        "title": "Identity-aware manual link",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{rewrite_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [rewrite_slug],
                    }
                ],
            },
        )
        compile_wiki(self.root)

        result = shell_status(self.root)

        review_pages = {page["path"]: page for page in result["review_controls"]["pages"]}
        rewrite_controls = {proposal["slug"]: proposal for proposal in result["review_controls"]["rewrite_proposals"]}
        action_controls = {action["action_id"]: action for action in result["execution_controls"]["actions"]}
        archive_controls = {archive["entry_id"]: archive for archive in result["execution_controls"]["archives"]}

        self.assertIn(decision["path"], review_pages)
        self.assertTrue(review_pages[decision["path"]]["page_id"])
        self.assertEqual(review_pages[decision["path"]]["current_status"], "proposed")
        self.assertTrue(review_pages[decision["path"]]["can_refresh_review"])
        self.assertIn("pending-review", review_pages[decision["path"]]["reasons"])
        self.assertIn("approved", review_pages[decision["path"]]["allowed_transitions"])
        self.assertIn("needs-revisit", review_pages[decision["path"]]["preferred_transitions"])
        self.assertEqual(review_pages[decision["path"]]["default_transition"], "approved")
        self.assertIn(rewrite_slug, rewrite_controls)
        self.assertTrue(rewrite_controls[rewrite_slug]["can_review"])
        self.assertEqual(rewrite_controls[rewrite_slug]["current_status"], "proposed")
        self.assertTrue(rewrite_controls[rewrite_slug]["can_refresh_review"])
        self.assertEqual(rewrite_controls[rewrite_slug]["proposal_path"], f"wiki/rewrite-proposals/{rewrite_slug}.md")
        self.assertIn("accepted", rewrite_controls[rewrite_slug]["allowed_transitions"])
        self.assertEqual(rewrite_controls[rewrite_slug]["default_transition"], "accepted")
        self.assertIn("identity-aware-action", action_controls)
        self.assertTrue(action_controls["identity-aware-action"]["can_apply"])
        self.assertFalse(action_controls["identity-aware-action"]["can_revert"])
        self.assertEqual(action_controls["identity-aware-action"]["current_status"], "accepted")
        self.assertTrue(action_controls["identity-aware-action"]["can_refresh_review"])
        self.assertEqual(action_controls["identity-aware-action"]["primary_path"], f"wiki/sources/{entry['id']}.md")
        self.assertIn("resolved", action_controls["identity-aware-action"]["allowed_transitions"])
        self.assertEqual(action_controls["identity-aware-action"]["default_transition"], "resolved")
        self.assertIn(archive_entry["id"], archive_controls)
        self.assertTrue(archive_controls[archive_entry["id"]]["can_apply"])
        self.assertFalse(archive_controls[archive_entry["id"]]["can_revert"])
        self.assertEqual(archive_controls[archive_entry["id"]]["source_path"], f"wiki/sources/{archive_entry['id']}.md")
        self.assertEqual(archive_controls[archive_entry["id"]]["allowed_transitions"], ["apply"])
        self.assertEqual(archive_controls[archive_entry["id"]]["default_transition"], "apply")

    def test_shell_status_surfaces_runtime_owned_rewrite_next_action(self) -> None:
        prepared = self._prepare_concept_rewrite_proposal()
        slug = str(prepared["slug"])

        result = shell_status(self.root)

        rewrite_actions = [
            action
            for action in result["suggested_next_actions"]
            if action.get("kind") == "review-rewrite"
        ]
        self.assertTrue(rewrite_actions)
        rewrite_action = rewrite_actions[0]
        self.assertEqual(rewrite_action["slug"], slug)
        self.assertEqual(rewrite_action["transition"], "accepted")
        self.assertEqual(rewrite_action["path"], f"wiki/rewrite-proposals/{slug}.md")
        self.assertIn(f"review-rewrite {slug} --status accepted", rewrite_action["command"])
        self.assertTrue(result["rewrite_recovery_actions"])
        self.assertEqual(result["rewrite_recovery_actions"][0]["slug"], slug)

    def test_shell_status_surfaces_judgment_assets_and_split_review_objects(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")

        compile_wiki(self.root)

        result = shell_status(self.root)

        judgment_assets = result["judgment_assets"]
        self.assertEqual(judgment_assets["counts"]["decisions"], 1)
        self.assertEqual(judgment_assets["counts"]["judgments"], 1)
        self.assertGreaterEqual(judgment_assets["counts"]["attention_pages"], 2)
        decision_focus = {entry["path"]: entry for entry in judgment_assets["decision_focus"]}
        judgment_focus = {entry["path"]: entry for entry in judgment_assets["judgment_focus"]}
        self.assertIn(decision["path"], decision_focus)
        self.assertIn(judgment["path"], judgment_focus)
        self.assertIn("missing-counter-evidence", decision_focus[decision["path"]]["attention_reasons"])
        self.assertIn("missing-review-history", judgment_focus[judgment["path"]]["attention_reasons"])

        decision_controls = {page["path"]: page for page in result["review_controls"]["decision_pages"]}
        judgment_controls = {page["path"]: page for page in result["review_controls"]["judgment_pages"]}
        self.assertIn(decision["path"], decision_controls)
        self.assertIn(judgment["path"], judgment_controls)
        self.assertEqual(decision_controls[decision["path"]]["asset_score"], 0)
        self.assertFalse(decision_controls[decision["path"]]["has_counter_evidence"])
        self.assertIn("missing-counter-evidence", decision_controls[decision["path"]]["reasons"])
        self.assertIn("missing-review-history", judgment_controls[judgment["path"]]["reasons"])

    def test_shell_status_surfaces_counter_evidence_review_actions_for_judgments(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")
        review_page(
            self.root,
            judgment["path"],
            "confirmed",
            note="Confirmed before follow-up evidence arrived.",
            confidence="high",
        )

        conflicting = self.root / "conflicting.md"
        conflicting.write_text(
            "# Transformer Scaling Followup\n\nTransformers scale inference costs shifted after routing changes.\n",
            encoding="utf-8",
        )
        followup = ingest_source(self.root, str(conflicting), title="Transformer Scaling Followup")

        compile_wiki(self.root)
        result = shell_status(self.root)

        self.assertEqual(result["review_backlog_counts"]["counter_evidence_candidates"], 1)
        self.assertEqual(result["review_backlog_counts"]["judgment_review_actions"], 1)
        judgment_controls = {page["path"]: page for page in result["review_controls"]["judgment_pages"]}
        self.assertIn(judgment["path"], judgment_controls)
        self.assertIn("counter-evidence-candidate", judgment_controls[judgment["path"]]["reasons"])
        self.assertEqual(judgment_controls[judgment["path"]]["judgment_lifecycle_state"], "active")

        review_actions = result["review_controls"]["review_actions"]
        self.assertTrue(review_actions)
        self.assertEqual(review_actions[0]["page_path"], judgment["path"])
        self.assertIn("counter-evidence-candidate", review_actions[0]["reason_codes"])

        review_queue = (self.root / "wiki" / "indexes" / "review-queue.md").read_text(encoding="utf-8")
        self.assertIn("Counter-evidence Candidates", review_queue)
        self.assertIn("Scaling Judgment", review_queue)
        self.assertIn(followup["id"], review_queue)

    def test_reviewed_judgment_suppresses_existing_counter_evidence_candidates(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")

        conflicting = self.root / "conflicting.md"
        conflicting.write_text(
            "# Transformer Scaling Followup\n\nTransformers scale inference costs shifted after routing changes.\n",
            encoding="utf-8",
        )
        ingest_source(self.root, str(conflicting), title="Transformer Scaling Followup")

        compile_wiki(self.root)
        before_review = shell_status(self.root)
        self.assertEqual(before_review["review_backlog_counts"]["counter_evidence_candidates"], 1)
        self.assertEqual(before_review["review_backlog_counts"]["judgment_review_actions"], 1)

        with patch("aiwiki.app_utils.utc_now", return_value="2030-01-01T00:00:00+00:00"):
            review_page(
                self.root,
                judgment["path"],
                "confirmed",
                note="Reviewed the follow-up and confirmed the original judgment still holds.",
                confidence="high",
            )
        compile_wiki(self.root)
        after_review = shell_status(self.root)

        self.assertEqual(after_review["review_backlog_counts"]["counter_evidence_candidates"], 0)
        self.assertEqual(after_review["review_backlog_counts"]["judgment_review_actions"], 0)
        judgment_controls = {page["path"]: page for page in after_review["review_controls"]["judgment_pages"]}
        self.assertNotIn("counter-evidence-candidate", judgment_controls.get(judgment["path"], {}).get("reasons", []))

    def test_reviewed_judgment_keeps_same_timestamp_counter_evidence_candidates(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")

        conflicting = self.root / "same-timestamp-conflicting.md"
        conflicting.write_text(
            "# Transformer Scaling Followup\n\nTransformers scale inference costs shifted after routing changes.\n",
            encoding="utf-8",
        )
        followup = ingest_source(self.root, str(conflicting), title="Transformer Scaling Same Timestamp Followup")
        compile_wiki(self.root)
        before_review = shell_status(self.root)
        self.assertEqual(before_review["review_backlog_counts"]["counter_evidence_candidates"], 1)
        followup_entry = next(
            entry for entry in load_manifest(self.root)["entries"] if entry["id"] == followup["id"]
        )
        timestamp = followup_entry["updated_at"]
        with patch("aiwiki.app_utils.utc_now", return_value=timestamp):
            review_page(
                self.root,
                judgment["path"],
                "confirmed",
                note="Review timestamp matches the follow-up import timestamp.",
                confidence="high",
            )

        compile_wiki(self.root)
        result = shell_status(self.root)

        self.assertEqual(result["review_backlog_counts"]["counter_evidence_candidates"], 1)
        self.assertEqual(result["review_backlog_counts"]["judgment_review_actions"], 1)
        judgment_controls = {page["path"]: page for page in result["review_controls"]["judgment_pages"]}
        self.assertIn("counter-evidence-candidate", judgment_controls[judgment["path"]]["reasons"])

    def test_reviewed_decision_suppresses_existing_counter_evidence_candidates(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")

        conflicting = self.root / "decision-conflicting.md"
        conflicting.write_text(
            "# Transformer Scaling Followup\n\nTransformers scale inference costs shifted after routing changes.\n",
            encoding="utf-8",
        )
        ingest_source(self.root, str(conflicting), title="Transformer Scaling Followup")

        compile_wiki(self.root)
        before_review = shell_status(self.root)
        self.assertEqual(before_review["review_backlog_counts"]["counter_evidence_candidates"], 1)
        self.assertEqual(before_review["review_backlog_counts"]["judgment_review_actions"], 1)

        with patch("aiwiki.app_utils.utc_now", return_value="2030-01-01T00:00:00+00:00"):
            review_page(
                self.root,
                decision["path"],
                "approved",
                note="Reviewed the follow-up and approved the original decision.",
            )
        compile_wiki(self.root)
        after_review = shell_status(self.root)

        self.assertEqual(after_review["review_backlog_counts"]["counter_evidence_candidates"], 0)
        self.assertEqual(after_review["review_backlog_counts"]["judgment_review_actions"], 0)
        decision_controls = {page["path"]: page for page in after_review["review_controls"]["decision_pages"]}
        self.assertNotIn("counter-evidence-candidate", decision_controls.get(decision["path"], {}).get("reasons", []))

    def test_shell_status_control_objects_are_not_truncated(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scaling tradeoffs", "report")
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))

        for index in range(13):
            file_back(
                self.root,
                report["path"],
                title=f"Decision {index}",
                kind="decision",
            )

        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": f"bulk-action-{index}",
                        "kind": "add-source-concept-link",
                        "title": f"Bulk Action {index}",
                        "reason": "Bulk control-object fixture.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "proposed",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                    for index in range(17)
                ],
            },
        )
        compile_wiki(self.root)

        result = shell_status(self.root)

        self.assertGreaterEqual(len(result["review_controls"]["pages"]), 13)
        self.assertGreaterEqual(len(result["execution_controls"]["actions"]), 17)

    def test_product_shell_plugin_manifest_declares_desktop_only(self) -> None:
        manifest_path = PROJECT_ROOT / ".obsidian/plugins/furnace-product-shell/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "furnace-product-shell")
        self.assertEqual(manifest["name"], "Furnace Product Shell")
        self.assertTrue(manifest["isDesktopOnly"])
        self.assertGreaterEqual(str(manifest["minAppVersion"]), "1.8.0")

    def test_product_shell_plugin_main_js_passes_node_syntax_check(self) -> None:
        plugin_path = PROJECT_ROOT / ".obsidian/plugins/furnace-product-shell/main.js"
        result = subprocess.run(
            ["node", "--check", str(plugin_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

    def test_product_shell_plugin_scaffold_declares_p0_views_and_commands(self) -> None:
        plugin_path = PROJECT_ROOT / ".obsidian/plugins/furnace-product-shell/main.js"
        content = plugin_path.read_text(encoding="utf-8")
        self.assertIn('const VIEW_TYPE_FURNACE_CENTER = "furnace-product-shell-furnace-center";', content)
        self.assertIn('const VIEW_TYPE_RECENT_RUNS = "furnace-product-shell-recent-runs";', content)
        self.assertIn('const VIEW_TYPE_REVIEW_CENTER = "furnace-product-shell-review-center";', content)
        self.assertIn('const VIEW_TYPE_EXECUTION_CENTER = "furnace-product-shell-execution-center";', content)
        self.assertIn('id: "open-furnace-center"', content)
        self.assertIn('id: "open-recent-runs"', content)
        self.assertIn('id: "open-review-center"', content)
        self.assertIn('id: "open-execution-center"', content)
        self.assertIn('id: "refresh-furnace-shell"', content)
        for hidden_command in (
            'id: "run-compile"',
            'id: "run-ask"',
            'id: "capture-note"',
            'id: "drop-url"',
            'id: "drop-file"',
            'id: "open-evidence-graph"',
            'id: "search-workspace"',
            'id: "run-nightly"',
            'id: "set-protocol"',
            'id: "open-home-note"',
            'id: "file-back"',
            'id: "review-page"',
            'id: "review-next-page"',
            'id: "batch-review-pages"',
            'id: "review-rewrite"',
            'id: "apply-rewrite"',
            'id: "retire-concept"',
            'id: "reactivate-concept"',
            'id: "apply-archive"',
            'id: "revert-archive"',
            'id: "review-action"',
            'id: "apply-action"',
            'id: "revert-action"',
            'id: "apply-all-accepted-low-risk"',
            'id: "revert-last-action-batch"',
        ):
            self.assertNotIn(hidden_command, content)
        self.assertIn('renderReviewCenter(this.contentEl);', content)
        self.assertIn('renderExecutionCenter(this.contentEl);', content)

    def test_product_shell_plugin_supports_external_runtime_launcher_mode(self) -> None:
        plugin_path = PROJECT_ROOT / ".obsidian/plugins/furnace-product-shell/main.js"
        content = plugin_path.read_text(encoding="utf-8")
        self.assertNotIn('"src/aiwiki/cli.py"', content)
        self.assertIn("Vault-local or absolute launcher path.", content)
        self.assertIn("Missing scaffold or launcher", content)
        self.assertIn('Open Review Center', content)
        self.assertIn('Open Execution Center', content)
        self.assertIn("class StructuredCommandModal extends Modal", content)
        self.assertIn("class ContextPickerModal extends Modal", content)
        self.assertIn("openStructuredCommandModal(spec)", content)
        self.assertIn("openContextPicker(spec)", content)
        self.assertIn("controlIdSet(key)", content)
        self.assertIn("reviewControlList(key)", content)
        self.assertIn("executionControlList(key)", content)
        self.assertIn("transitionOptions(controlType, control)", content)
        self.assertIn("preferredTransitionOptions(controlType, control)", content)
        self.assertIn("manualReviewOption(controlType)", content)
        self.assertIn("openTransitionPicker({ title, description, controlType, control, onSubmit, onFallback, onManual, emptyNotice })", content)
        self.assertIn("runReviewPageTransition(pagePath, status)", content)
        self.assertIn("runReviewRewriteTransition(slug, status)", content)
        self.assertIn("runReviewActionTransition(actionId, status)", content)
        self.assertIn("openContextAwareAction(spec)", content)
        self.assertIn("visibleReviewPageCandidates()", content)
        self.assertIn("nextReviewCandidate()", content)
        self.assertIn("reviewBatchSuggestions()", content)
        self.assertIn("commonReviewTransitionOptions(pages)", content)
        self.assertIn("visibleRewriteCandidates()", content)
        self.assertIn('visibleActionCandidates(mode = "review")', content)
        self.assertIn('visibleArchiveCandidates(mode = "apply")', content)
        self.assertIn("reviewPageControlItems()", content)
        self.assertIn('rewriteControlItems(mode = "review")', content)
        self.assertIn('actionControlItems(mode = "review")', content)
        self.assertIn('archiveControlItems(mode = "apply")', content)
        self.assertIn("actionControlsById()", content)
        self.assertIn("archiveControlsById()", content)
        self.assertIn("openReviewPageContextPicker(options = this.visibleReviewPageCandidates())", content)
        self.assertIn("openReviewNextTransitionPicker()", content)
        self.assertIn("openReviewPageBatchModal(prefill = {})", content)
        self.assertIn("openReviewBatchSuggestionPicker()", content)
        self.assertIn("openReviewRewriteContextPicker(options = this.visibleRewriteCandidates())", content)
        self.assertIn('openReviewActionContextPicker(options = this.visibleActionCandidates("review"))', content)
        self.assertIn("openReviewPageTransitionPicker(control)", content)
        self.assertIn("openReviewRewriteTransitionPicker(control)", content)
        self.assertIn("openReviewActionTransitionPicker(control)", content)
        self.assertIn('openApplyArchiveContextPicker(options = this.visibleArchiveCandidates("apply"))', content)
        self.assertIn('openRevertArchiveContextPicker(options = this.visibleArchiveCandidates("revert"))', content)
        self.assertIn('openApplyActionContextPicker(options = this.visibleActionCandidates("apply"))', content)
        self.assertIn('openRevertActionContextPicker(options = this.visibleActionCandidates("revert"))', content)
        self.assertIn("runCliAction(label, command, args = [])", content)
        self.assertIn("getActiveOutputPath()", content)
        self.assertIn("getActiveCuratedPagePath()", content)
        self.assertIn("getActiveConceptSlug()", content)
        self.assertIn("runProductShellCliAction(this, label, command, args)", content)
        self.assertIn("plugin.runPluginCommand(label, [command, ...args], { refreshAfter: true });", content)
        self.assertIn('const DEFAULT_LOCALE = "zh";', content)
        self.assertIn('locale: DEFAULT_LOCALE', content)
        self.assertIn('.t("Review")', content)
        self.assertIn("Judgment Focus", content)
        self.assertIn("审阅概况", content)
        self.assertIn("查看完整审阅页", content)
        self.assertIn("执行概况", content)
        self.assertIn("待执行动作", content)
        self.assertIn("Judgment Assets", content)
        self.assertIn("Next Review", content)
        self.assertIn("Batch Suggestions", content)
        self.assertIn("Decision Objects", content)
        self.assertIn("Judgment Objects", content)
        self.assertIn("Rewrite Proposal Objects", content)
        self.assertIn("Action Control Objects", content)
        self.assertIn("async runReviewPageBatchTransition(pagePaths, status, note = \"\", confidence = \"\")", content)
        self.assertIn('this.t("Pick Review Transition")', content)
        self.assertIn('this.t("Pick Batch Review")', content)
        self.assertIn('this.t("Pick Rewrite Transition")', content)
        self.assertIn('this.t("Pick Action Transition")', content)
        self.assertIn('emptyNotice: this.t("No visible review backlog item is available; fell back to the manual form.")', content)
        self.assertIn('emptyNotice: this.t("No visible machine-memory action context is available; fell back to the manual form.")', content)
        self.assertIn('output/control/shell-summary.json', content)
        self.assertIn('review_controls', content)
        self.assertIn('reviewControlList(plugin, "rewrite_proposals")', content)
        self.assertIn("displayReviewReason(", content)
        self.assertIn("reviewObjectMetaText(", content)
        self.assertIn('execution_controls', content)
        self.assertIn('scripts/aiwiki-launcher.sh', content)
        self.assertIn("canRefreshReview", content)
        self.assertIn("currentStatus", content)
        self.assertIn("onManual: () => this.openReviewPageModal({ pagePath, status: currentStatus, confidence })", content)
        self.assertIn("onManual: () => this.openReviewRewriteModal({ slug, status: currentStatus })", content)
        self.assertIn("onManual: () => this.openReviewActionModal({ actionId, status: currentStatus })", content)
        self.assertNotIn(".aiwiki/state/", content)
        self.assertIn("launcherIsExecutable(launcherPath)", content)
        self.assertIn("fs.accessSync(launcherPath, fs.constants.X_OK)", content)
        self.assertIn("runUiAction(action, label = \"ui-action\")", content)
        self.assertIn("console.error(`[furnace-product-shell] ${label} failed`, error);", content)
        self.assertFalse((PROJECT_ROOT / "src/aiwiki/app.py").exists())
        self.assertFalse((PROJECT_ROOT / "src/aiwiki/app_content.py").exists())
        self.assertFalse((PROJECT_ROOT / "src/aiwiki/app_render.py").exists())
        self.assertFalse((PROJECT_ROOT / "src/aiwiki/app_surfaces.py").exists())
        self.assertFalse((PROJECT_ROOT / "src/aiwiki/app_memory_surfaces.py").exists())
        from aiwiki.app_lifecycle import (
            action_transition_profile,
            archive_transition_profile,
            curated_page_transition_profile,
            rewrite_transition_profile,
            transition_profile,
        )
        self.assertTrue(callable(transition_profile))
        self.assertTrue(callable(curated_page_transition_profile))
        self.assertTrue(callable(rewrite_transition_profile))
        self.assertTrue(callable(action_transition_profile))
        self.assertTrue(callable(archive_transition_profile))



def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(ShellFlowTests))
    return suite


if __name__ == "__main__":
    unittest.main()
