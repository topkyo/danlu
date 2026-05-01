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


class StubClient:
    def __init__(self, responses: list[str], *, backend: str = "", backend_requested: str = "") -> None:
        self.responses = list(responses)
        self.config = type(
            "Config",
            (),
            {
                "model": "stub-model",
                "backend": backend,
                "backend_requested": backend_requested or backend,
            },
        )()

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt
        del user_prompt
        if not self.responses:
            raise AssertionError("No stubbed LLM response left.")
        return CompletionResult(text=self.responses.pop(0), response_id="stub-response", usage={})


class StubVisionClient:
    def __init__(self, response: str, backend: str = "codex-cli") -> None:
        self.response = response
        self.config = type("Config", (), {"backend": backend, "model": "stub-vision-model"})()

    def analyze_image(self, system_prompt: str, user_prompt: str, image_path: Path) -> CompletionResult:
        del system_prompt
        del user_prompt
        del image_path
        return CompletionResult(text=self.response, response_id="stub-vision", usage={})


class CapturingClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt = ""
        self.config = type("Config", (), {"model": "capture-model"})()

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt
        self.prompt = user_prompt
        return CompletionResult(text=self.response, response_id="capture-response", usage={})


class FailingVisionClient:
    def __init__(self, backend: str = "codex-cli") -> None:
        self.config = type("Config", (), {"backend": backend, "model": "stub-vision-model"})()

    def analyze_image(self, system_prompt: str, user_prompt: str, image_path: Path) -> CompletionResult:
        del system_prompt
        del user_prompt
        del image_path
        raise RuntimeError("vision backend failed")


class AiwikiFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)
        (self.root / "prompts" / "compile.md").write_text("Compile prompt fixture.\n", encoding="utf-8")
        (self.root / "prompts" / "ask.md").write_text("Ask prompt fixture.\n", encoding="utf-8")
        (self.root / "prompts" / "lint.md").write_text("Lint prompt fixture.\n", encoding="utf-8")
        self.sample = self.root / "sample.md"
        self.sample.write_text(
            "# Transformer Scaling\n\nTransformers benefit from scale.\nInference costs also rise.\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _seed_machine_memory_actions(self) -> None:
        for index in range(4):
            source = self.root / f"action-{index}.md"
            source.write_text(f"# Latency Node {index}\n\nLatency throughput node {index}.\n", encoding="utf-8")
            ingest_source(self.root, str(source), title=f"Latency Node {index}")

    def _rewrite_concept_summary(self, concept_page: Path, summary_lines: list[str]) -> None:
        text = concept_page.read_text(encoding="utf-8")
        before, marker, after = text.partition("## Summary\n")
        self.assertTrue(marker)
        _, related_marker, remainder = after.partition("\n## Related Sources\n")
        self.assertTrue(related_marker)
        concept_page.write_text(
            before + marker + "\n".join(summary_lines) + "\n" + related_marker + remainder,
            encoding="utf-8",
        )

    def _seed_existing_concept_summaries(self) -> None:
        for concept_page in sorted((self.root / "wiki" / "concepts").glob("*.md")):
            self._rewrite_concept_summary(
                concept_page,
                [
                    f"- Existing synthesis for {concept_page.stem} appears",
                    "- Keep the current synthesis grounded in the linked sources.",
                ],
            )

    def _seed_legacy_placeholder_summary(self, concept_page: Path) -> None:
        self._rewrite_concept_summary(
            concept_page,
            [
                "- This concept currently appears in `1` source page(s).",
                "- Use the linked source pages below to deepen or revise this synthesis.",
            ],
        )

    def _prepare_ready_archive_candidate(self) -> dict[str, str]:
        archive_source = self.root / "archive-candidate.md"
        archive_source.write_text("# Obscure Legacy Note\n\nMisc.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(archive_source), title="Obscure Legacy Note")
        compile_wiki(self.root)
        manifest = load_manifest(self.root)
        for manifest_entry in manifest["entries"]:
            if manifest_entry["id"] == entry["id"]:
                manifest_entry["imported_at"] = "2025-01-01T00:00:00+00:00"
                manifest_entry["updated_at"] = "2025-01-01T00:00:00+00:00"
                break
        save_manifest(self.root, manifest)
        set_active_protocol(self.root, "investing")
        compile_wiki(self.root)
        compile_wiki(self.root)
        return entry

    def _prepare_citation_snapshot_refresh_action(self) -> tuple[dict[str, str], dict[str, Any], dict[str, Any]]:
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
        stored_source = self.root / entry["stored_path"]
        stored_source.write_text(
            "# Transformer Scaling\n\nTransformers still benefit from scale.\nNew serving optimizations changed inference cost assumptions.\n",
            encoding="utf-8",
        )
        compile_wiki(self.root)
        memory = load_machine_memory(self.root)
        action = next(
            (item for item in memory["health"]["actions"] if item.get("kind") == "refresh-citation-snapshots"),
            None,
        )
        if action is None:
            self.fail("Expected citation snapshot refresh action.")
        return entry, judgment, action

    def _seed_runtime_ranking_entries(self) -> list[dict[str, str]]:
        first = self.root / "alpha-cache.md"
        first.write_text("# Alpha Cache\n\nLatency cache tradeoff evidence.\n", encoding="utf-8")
        second = self.root / "zulu-cache.md"
        second.write_text("# Zulu Cache\n\nLatency cache tradeoff evidence.\n", encoding="utf-8")
        first_entry = ingest_source(self.root, str(first), title="Alpha Cache")
        second_entry = ingest_source(self.root, str(second), title="Zulu Cache")
        compile_wiki(self.root)
        manifest = load_manifest(self.root)
        return [entry for entry in manifest["entries"] if entry["id"] in {first_entry["id"], second_entry["id"]}]

    def _prepare_stale_protocol_material(self) -> dict[str, str]:
        sample = self.root / "earnings-thesis.md"
        sample.write_text(
            "# Earnings Thesis\n\nRevenue margin valuation EPS cashflow multiple underwrite risk.\n",
            encoding="utf-8",
        )
        entry = ingest_source(self.root, str(sample), title="Earnings Thesis")
        compile_wiki(self.root)
        manifest = load_manifest(self.root)
        manifest["entries"][0]["imported_at"] = "2025-01-01T00:00:00+00:00"
        manifest["entries"][0]["updated_at"] = "2025-01-01T00:00:00+00:00"
        save_manifest(self.root, manifest)
        compile_wiki(self.root)
        compile_wiki(self.root)
        return entry

    def _seed_lifecycle_governance_surface_state(self) -> tuple[str, str]:
        first = self.root / "first.md"
        first.write_text("# Latency Outlook\n\nLatency will increase with larger batches.\n", encoding="utf-8")
        second = self.root / "second.md"
        second.write_text("# Latency Outlook\n\nLatency may decrease after cache reuse.\n", encoding="utf-8")
        first_entry = ingest_source(self.root, str(first), title="Latency Outlook A")
        second_entry = ingest_source(self.root, str(second), title="Latency Outlook B")
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")

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
        retired_entry = next(
            entry
            for entry in lifecycle["entries"]
            if entry["kind"] == "concept" and entry["title"] != "Latency Outlook"
        )
        retire_concept(self.root, Path(retired_entry["path"]).stem, note="Retire concept for lifecycle governance summary.")
        compile_wiki(self.root)
        return "Latency Outlook", retired_entry["title"]

    def _seed_protocol_lifecycle_governance_surface_state(self, protocol: str = "research") -> tuple[str, str]:
        if protocol != "research":
            raise ValueError(f"Unsupported protocol fixture: {protocol}")

        first = self.root / "research-first.md"
        first.write_text(
            "# Latency Benchmark\n\nBenchmark regression shows latency bottleneck in the experiment repo.\n",
            encoding="utf-8",
        )
        second = self.root / "research-second.md"
        second.write_text(
            "# Latency Benchmark\n\nArchitecture change improves throughput but may hide another latency regression.\n",
            encoding="utf-8",
        )
        third = self.root / "research-third.md"
        third.write_text(
            "# Throughput Bottleneck\n\nRepo benchmark documents a persistent throughput bottleneck.\n",
            encoding="utf-8",
        )
        first_entry = ingest_source(self.root, str(first), title="Latency Benchmark A")
        second_entry = ingest_source(self.root, str(second), title="Latency Benchmark B")
        ingest_source(self.root, str(third), title="Throughput Bottleneck")
        set_active_protocol(self.root, protocol)

        compile_wiki(self.root)

        first_page = self.root / "wiki" / "sources" / f"{first_entry['id']}.md"
        second_page = self.root / "wiki" / "sources" / f"{second_entry['id']}.md"
        first_page.write_text(
            first_page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                "- Benchmark regression shows latency increasing while throughput collapses in the experiment repo.",
            ),
            encoding="utf-8",
        )
        second_page.write_text(
            second_page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                "- Benchmark rerun suggests architecture tuning restores throughput and reduces latency bottlenecks.",
            ),
            encoding="utf-8",
        )

        compile_wiki(self.root)

        lifecycle = load_knowledge_lifecycle_state(self.root)
        backlog_entry = next(
            entry
            for entry in lifecycle["entries"]
            if entry["kind"] == "concept" and entry["lifecycle_state"] in {"review", "revisit"}
        )
        retired_entry = next(
            entry
            for entry in lifecycle["entries"]
            if entry["kind"] == "concept" and entry["title"] != backlog_entry["title"]
        )
        retire_concept(
            self.root,
            Path(retired_entry["path"]).stem,
            note="Retire protocol-related concept for domain pilot lifecycle summary.",
        )
        compile_wiki(self.root)
        return backlog_entry["title"], retired_entry["title"]

    def _prepare_concept_rewrite_proposal(self, *, rewritten_phrase: str = "Rewritten synthesis") -> dict[str, object]:
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
        updated = concept_page.read_text(encoding="utf-8").replace("Existing synthesis", rewritten_phrase)
        compile_result = run_compile(self.root, client=StubClient([updated]), limit=1)
        proposal_path = self.root / compile_result["updated_rewrite_proposal_pages"][0]
        return {
            "entry": entry,
            "candidate": candidate,
            "concept_page": concept_page,
            "proposal_path": proposal_path,
            "slug": proposal_path.stem,
            "compile_result": compile_result,
        }

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

    def test_runtime_write_lock_is_reentrant_across_app_and_runner(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        current_report = (self.root / report["path"]).read_text(encoding="utf-8")

        with runtime_write_lock(self.root):
            rerun = run_ask(
                self.root,
                "Compare transformer scale and inference cost",
                "report",
                client=StubClient([current_report]),
            )
            filed = file_back(self.root, rerun["path"], title="Locked Decision", kind="decision")

        self.assertTrue((self.root / rerun["path"]).exists())
        self.assertTrue((self.root / filed["path"]).exists())
        self.assertTrue((self.root / ".aiwiki" / "state" / "runtime.lock").exists())

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

    def test_compile_creates_concepts_master_index_and_log(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compiled = compile_wiki(self.root)
        self.assertGreater(compiled["concepts"], 0)
        self.assertGreater(compiled["machine_memory_terms"], 0)

        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_frontmatter = parse_frontmatter(source_page.read_text(encoding="utf-8"))
        self.assertTrue(source_frontmatter["concepts"])
        self.assertTrue(list((self.root / "wiki" / "concepts").glob("*.md")))

        master_index = self.root / "wiki" / "indexes" / "index.md"
        log_page = self.root / "wiki" / "indexes" / "log.md"
        memory_page = self.root / "wiki" / "indexes" / "machine-memory.md"
        graph_health_page = self.root / "wiki" / "indexes" / "graph-health.md"
        decisions_index = self.root / "wiki" / "indexes" / "decisions.md"
        judgments_index = self.root / "wiki" / "indexes" / "judgments.md"
        agent_workbench = self.root / "wiki" / "indexes" / "agent-workbench.md"
        cognitive_history = self.root / "wiki" / "indexes" / "cognitive-history.md"
        output_packs = self.root / "wiki" / "indexes" / "output-packs.md"
        domain_pilots = self.root / "wiki" / "indexes" / "domain-pilots.md"
        review_queue = self.root / "wiki" / "indexes" / "review-queue.md"
        memory_state = self.root / ".aiwiki" / "state" / "machine-memory.json"
        memory_graph = self.root / ".aiwiki" / "cache" / "machine-memory-graph.json"
        drift_report = self.root / "wiki" / "indexes" / "drift-report.md"
        memory_history = self.root / ".aiwiki" / "state" / "machine-memory-history.jsonl"
        self.assertTrue(master_index.exists())
        self.assertTrue(log_page.exists())
        self.assertTrue(memory_page.exists())
        self.assertTrue(graph_health_page.exists())
        self.assertTrue(decisions_index.exists())
        self.assertTrue(judgments_index.exists())
        self.assertTrue(agent_workbench.exists())
        self.assertTrue(cognitive_history.exists())
        self.assertTrue(output_packs.exists())
        self.assertTrue(domain_pilots.exists())
        self.assertTrue(review_queue.exists())
        self.assertTrue(memory_state.exists())
        self.assertTrue(memory_graph.exists())
        self.assertTrue(drift_report.exists())
        self.assertTrue(memory_history.exists())
        self.assertIn("操作日志", master_index.read_text(encoding="utf-8"))
        self.assertIn("机器记忆", master_index.read_text(encoding="utf-8"))
        self.assertIn("决策索引", master_index.read_text(encoding="utf-8"))
        self.assertIn("判断索引", master_index.read_text(encoding="utf-8"))
        self.assertIn("审阅队列", master_index.read_text(encoding="utf-8"))
        self.assertIn("Agent Workbench", master_index.read_text(encoding="utf-8"))
        self.assertIn("认知历史", master_index.read_text(encoding="utf-8"))
        self.assertIn("输出 Pack 总览", master_index.read_text(encoding="utf-8"))
        self.assertIn("领域 Pilot 总览", master_index.read_text(encoding="utf-8"))
        self.assertIn("图谱健康", master_index.read_text(encoding="utf-8"))
        self.assertIn("漂移报告", master_index.read_text(encoding="utf-8"))
        self.assertIn("compile | wiki refresh", log_page.read_text(encoding="utf-8"))
        self.assertIn("运行时状态文件", memory_page.read_text(encoding="utf-8"))
        self.assertIn("连通分量", graph_health_page.read_text(encoding="utf-8"))
        memory = json.loads(memory_state.read_text(encoding="utf-8"))
        graph = json.loads(memory_graph.read_text(encoding="utf-8"))
        self.assertEqual(memory["source_nodes"][0]["id"], entry["id"])
        self.assertTrue(memory["term_index"])
        self.assertIn("health", memory)
        self.assertTrue(memory["digest"])
        self.assertTrue(memory["graph_digest"])
        self.assertTrue(graph["nodes"])
        self.assertTrue(graph["edges"])
        self.assertIn("没有可对比的上一版机器记忆快照", drift_report.read_text(encoding="utf-8"))

    def test_compile_writes_protocol_dashboard(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        protocol_page = self.root / "wiki" / "indexes" / "protocols.md"
        self.assertTrue(protocol_page.exists())
        payload = protocol_page.read_text(encoding="utf-8")
        self.assertIn("当前 active protocol", payload)
        self.assertIn("general", payload)
        self.assertIn("../../schema/protocols/general/index.md", payload)

    def test_compile_writes_material_state_baseline(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compiled = compile_wiki(self.root)

        material_state_path = self.root / ".aiwiki" / "state" / "material-state.json"
        active_corpora_path = self.root / ".aiwiki" / "state" / "active-corpora.json"
        material_routing_path = self.root / ".aiwiki" / "state" / "material-routing.json"
        archive_candidates_path = self.root / ".aiwiki" / "state" / "archive-candidates.json"
        knowledge_lifecycle_path = self.root / ".aiwiki" / "state" / "knowledge-lifecycle.json"
        knowledge_lifecycle_overrides_path = self.root / ".aiwiki" / "state" / "knowledge-lifecycle-overrides.json"
        self.assertEqual(compiled["material_state_path"], ".aiwiki/state/material-state.json")
        self.assertEqual(compiled["active_corpora_path"], ".aiwiki/state/active-corpora.json")
        self.assertEqual(compiled["material_routing_path"], ".aiwiki/state/material-routing.json")
        self.assertEqual(compiled["archive_candidates_path"], ".aiwiki/state/archive-candidates.json")
        self.assertEqual(compiled["knowledge_lifecycle_path"], ".aiwiki/state/knowledge-lifecycle.json")
        self.assertEqual(compiled["knowledge_lifecycle_overrides_path"], ".aiwiki/state/knowledge-lifecycle-overrides.json")
        self.assertTrue(material_state_path.exists())
        self.assertTrue(active_corpora_path.exists())
        self.assertTrue(material_routing_path.exists())
        self.assertTrue(archive_candidates_path.exists())
        self.assertTrue(knowledge_lifecycle_path.exists())
        self.assertTrue(knowledge_lifecycle_overrides_path.exists())

        material_state = json.loads(material_state_path.read_text(encoding="utf-8"))
        active_corpora = json.loads(active_corpora_path.read_text(encoding="utf-8"))
        material_routing = json.loads(material_routing_path.read_text(encoding="utf-8"))
        archive_candidates = json.loads(archive_candidates_path.read_text(encoding="utf-8"))
        knowledge_lifecycle = json.loads(knowledge_lifecycle_path.read_text(encoding="utf-8"))
        knowledge_lifecycle_overrides = json.loads(knowledge_lifecycle_overrides_path.read_text(encoding="utf-8"))
        self.assertEqual(material_state["version"], 1)
        self.assertEqual(len(material_state["entries"]), 1)
        self.assertEqual(active_corpora["version"], 1)
        self.assertEqual(active_corpora["corpora"], [])
        self.assertEqual(material_routing["version"], 1)
        self.assertEqual(material_routing["active_protocol"], "general")
        self.assertEqual(len(material_routing["entries"]), 1)
        self.assertEqual(archive_candidates["version"], 1)
        self.assertEqual(knowledge_lifecycle["version"], 1)
        self.assertEqual(knowledge_lifecycle_overrides["version"], 1)
        self.assertEqual(knowledge_lifecycle_overrides["entries"], [])
        self.assertGreater(knowledge_lifecycle["counts"]["total"], 0)
        self.assertGreater(knowledge_lifecycle["counts"]["by_kind"]["concept"]["total"], 0)
        self.assertTrue(any(item["kind"] == "concept" for item in knowledge_lifecycle["entries"]))

        record = material_state["entries"][0]
        routing_record = material_routing["entries"][0]
        self.assertEqual(record["entry_id"], entry["id"])
        self.assertEqual(record["path"], entry["stored_path"])
        self.assertEqual(record["active_corpus_ids"], [])
        self.assertIn(record["temperature"], {"hot", "warm", "cold"})
        self.assertTrue(record["protocol_hints"])
        self.assertTrue(record["last_touched_at"])
        self.assertEqual(routing_record["entry_id"], entry["id"])
        self.assertEqual(routing_record["protocol"], "general")
        self.assertIn("protocol_score", routing_record["scores"])
        self.assertIn("graph_score", routing_record["scores"])
        self.assertIn("judgment_score", routing_record["scores"])
        self.assertIn("recency_score", routing_record["scores"])
        self.assertIn("drift_score", routing_record["scores"])
        self.assertIn(routing_record["selected_as"], {"hot-evidence", "warm-evidence", "cold-evidence", "archive-candidate"})
        self.assertIsInstance(routing_record["is_bridge"], bool)
        self.assertIn("component_id", routing_record)
        self.assertIn("cross_protocol_bridge", routing_record)
        self.assertTrue(routing_record["protocol_snapshots"])
        self.assertTrue(routing_record["top_protocols"])
        self.assertLessEqual(len(routing_record["top_protocols"]), 3)
        self.assertTrue(
            {"general", "investing", "research", "product", "ops"}
            <= {item["protocol"] for item in routing_record["protocol_snapshots"]}
        )

    def test_compile_writes_phase_summary_and_compile_state(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")

        compiled = compile_wiki(self.root)

        compile_state_path = self.root / ".aiwiki" / "state" / "compile-state.json"
        concept_build_state_path = self.root / ".aiwiki" / "state" / "concept-build-state.json"
        machine_memory_build_state_path = self.root / ".aiwiki" / "state" / "machine-memory-build-state.json"
        ranking_build_state_path = self.root / ".aiwiki" / "state" / "ranking-build-state.json"
        output_pack_build_state_path = self.root / ".aiwiki" / "state" / "output-pack-build-state.json"
        domain_pilot_build_state_path = self.root / ".aiwiki" / "state" / "domain-pilot-build-state.json"
        cache_status_file_path = self.root / ".aiwiki" / "state" / "cache-status.json"
        compile_status_path = self.root / "wiki" / "indexes" / "compile-status.md"
        self.assertEqual(compiled["compile_state_path"], ".aiwiki/state/compile-state.json")
        self.assertEqual(compiled["cache_status_path"], ".aiwiki/state/cache-status.json")
        self.assertEqual(compiled["concept_build_state_path"], ".aiwiki/state/concept-build-state.json")
        self.assertEqual(
            compiled["machine_memory_build_state_path"],
            ".aiwiki/state/machine-memory-build-state.json",
        )
        self.assertEqual(compiled["ranking_build_state_path"], ".aiwiki/state/ranking-build-state.json")
        self.assertEqual(compiled["output_pack_build_state_path"], ".aiwiki/state/output-pack-build-state.json")
        self.assertEqual(compiled["domain_pilot_build_state_path"], ".aiwiki/state/domain-pilot-build-state.json")
        self.assertTrue(compile_state_path.exists())
        self.assertTrue(concept_build_state_path.exists())
        self.assertTrue(machine_memory_build_state_path.exists())
        self.assertTrue(ranking_build_state_path.exists())
        self.assertTrue(output_pack_build_state_path.exists())
        self.assertTrue(domain_pilot_build_state_path.exists())
        self.assertTrue(cache_status_file_path.exists())
        self.assertTrue(compile_status_path.exists())

        compile_state = json.loads(compile_state_path.read_text(encoding="utf-8"))
        concept_build_state = json.loads(concept_build_state_path.read_text(encoding="utf-8"))
        machine_memory_build_state = json.loads(machine_memory_build_state_path.read_text(encoding="utf-8"))
        ranking_build_state = json.loads(ranking_build_state_path.read_text(encoding="utf-8"))
        output_pack_build_state = json.loads(output_pack_build_state_path.read_text(encoding="utf-8"))
        domain_pilot_build_state = json.loads(domain_pilot_build_state_path.read_text(encoding="utf-8"))
        cache_status = json.loads(cache_status_file_path.read_text(encoding="utf-8"))
        self.assertEqual(compile_state["manifest_entry_count"], 1)
        self.assertEqual(compile_state["dirty_source_ids"], [entry["id"]])
        self.assertEqual(compile_state["clean_source_ids"], [])
        self.assertEqual(compile_state["dirty_concept_source_ids"], [entry["id"]])
        self.assertEqual(compile_state["clean_concept_source_ids"], [])
        self.assertTrue(compile_state["dirty_concept_slugs"])
        self.assertEqual(compile_state["clean_concept_slugs"], [])
        self.assertEqual(compile_state["dirty_machine_memory_source_ids"], [entry["id"]])
        self.assertEqual(compile_state["clean_machine_memory_source_ids"], [])
        self.assertTrue(compile_state["dirty_machine_memory_concept_slugs"])
        self.assertEqual(compile_state["clean_machine_memory_concept_slugs"], [])
        self.assertFalse(compile_state["machine_memory_core_reused"])
        self.assertEqual(compile_state["dirty_ranking_source_ids"], [entry["id"]])
        self.assertEqual(compile_state["clean_ranking_source_ids"], [])
        self.assertTrue(compile_state["dirty_ranking_concept_slugs"])
        self.assertEqual(compile_state["clean_ranking_concept_slugs"], [])
        self.assertTrue(compile_state["dirty_output_pack_groups"])
        self.assertEqual(compile_state["clean_output_pack_groups"], [])
        self.assertTrue(compile_state["dirty_domain_pilot_protocols"])
        self.assertEqual(compile_state["clean_domain_pilot_protocols"], [])
        self.assertTrue(compile_state["dirty_index_artifacts"])
        # Round 51 managed dashboard templates are refreshed on every compile.
        # Existing template pages can therefore be tracked as clean index artifacts
        # while dynamic owner pages are still dirty below.
        self.assertIn("wiki/indexes/graph-view.md", compile_state["clean_index_artifacts"])
        self.assertTrue(compile_state["dirty_maintenance_artifacts"])
        self.assertEqual(compile_state["clean_maintenance_artifacts"], [])
        self.assertIn(entry["id"], concept_build_state["entry_records"])
        self.assertTrue(concept_build_state["entry_records"][entry["id"]]["input_signature"])
        self.assertTrue(concept_build_state["entry_records"][entry["id"]]["terms"])
        self.assertIn(entry["id"], machine_memory_build_state["source_records"])
        self.assertTrue(machine_memory_build_state["source_records"][entry["id"]]["input_signature"])
        self.assertTrue(machine_memory_build_state["concept_records"])
        self.assertIn(entry["id"], ranking_build_state["source_records"])
        self.assertTrue(ranking_build_state["source_records"][entry["id"]]["input_signature"])
        self.assertTrue(ranking_build_state["source_records"][entry["id"]]["concept_terms"])
        self.assertTrue(ranking_build_state["source_records"][entry["id"]]["summary_or_preview"])
        self.assertTrue(ranking_build_state["concept_records"])
        self.assertIn("review_packs", output_pack_build_state["group_records"])
        self.assertTrue(output_pack_build_state["group_records"]["review_packs"]["input_signature"])
        self.assertIn("general", domain_pilot_build_state["protocol_records"])
        self.assertTrue(domain_pilot_build_state["protocol_records"]["general"]["input_signature"])
        self.assertTrue(cache_status["enabled"])
        self.assertEqual(cache_status["schema_version"], 1)
        self.assertIn("cache_nodes", cache_status["row_counts"])
        self.assertGreater(cache_status["row_counts"]["cache_nodes"], 0)
        phase_names = [phase["name"] for phase in compile_state["phase_summary"]]
        self.assertEqual(
            phase_names,
            [
                "metadata_refresh",
                "incremental_source_compile",
                "concept_refresh",
                "machine_memory_refresh",
                "ranking_refresh",
                "index_refresh",
                "cold_archive_maintenance",
                "output_pack_refresh",
                "domain_pilot_refresh",
            ],
        )
        source_phase = next(phase for phase in compile_state["phase_summary"] if phase["name"] == "incremental_source_compile")
        self.assertEqual(source_phase["mode"], "incremental")
        self.assertEqual(source_phase["details"]["dirty_sources"], 1)
        self.assertEqual(source_phase["details"]["clean_sources"], 0)
        concept_phase = next(phase for phase in compile_state["phase_summary"] if phase["name"] == "concept_refresh")
        self.assertEqual(concept_phase["mode"], "incremental")
        self.assertEqual(concept_phase["details"]["dirty_concept_sources"], 1)
        self.assertEqual(concept_phase["details"]["clean_concept_sources"], 0)
        self.assertEqual(concept_phase["details"]["dirty_concepts"], len(compile_state["dirty_concept_slugs"]))
        self.assertEqual(concept_phase["details"]["clean_concepts"], 0)
        machine_memory_phase = next(
            phase for phase in compile_state["phase_summary"] if phase["name"] == "machine_memory_refresh"
        )
        self.assertEqual(machine_memory_phase["mode"], "incremental")
        self.assertEqual(machine_memory_phase["details"]["dirty_machine_memory_sources"], 1)
        self.assertEqual(machine_memory_phase["details"]["clean_machine_memory_sources"], 0)
        self.assertEqual(
            machine_memory_phase["details"]["dirty_machine_memory_concepts"],
            len(compile_state["dirty_machine_memory_concept_slugs"]),
        )
        self.assertEqual(machine_memory_phase["details"]["clean_machine_memory_concepts"], 0)
        self.assertFalse(machine_memory_phase["details"]["reused_core"])
        self.assertTrue(machine_memory_phase["details"]["cache_enabled"])
        self.assertGreater(machine_memory_phase["details"]["cache_row_count"], 0)
        ranking_phase = next(phase for phase in compile_state["phase_summary"] if phase["name"] == "ranking_refresh")
        self.assertEqual(ranking_phase["mode"], "incremental")
        self.assertEqual(ranking_phase["details"]["dirty_ranking_sources"], 1)
        self.assertEqual(ranking_phase["details"]["clean_ranking_sources"], 0)
        self.assertEqual(
            ranking_phase["details"]["dirty_ranking_concepts"],
            len(compile_state["dirty_ranking_concept_slugs"]),
        )
        self.assertEqual(ranking_phase["details"]["clean_ranking_concepts"], 0)
        index_phase = next(phase for phase in compile_state["phase_summary"] if phase["name"] == "index_refresh")
        self.assertEqual(index_phase["mode"], "incremental")
        self.assertEqual(index_phase["details"]["dirty_artifacts"], len(compile_state["dirty_index_artifacts"]))
        self.assertEqual(index_phase["details"]["clean_artifacts"], len(compile_state["clean_index_artifacts"]))
        maintenance_phase = next(
            phase for phase in compile_state["phase_summary"] if phase["name"] == "cold_archive_maintenance"
        )
        self.assertEqual(maintenance_phase["mode"], "incremental")
        self.assertEqual(
            maintenance_phase["details"]["dirty_artifacts"],
            len(compile_state["dirty_maintenance_artifacts"]),
        )
        self.assertEqual(maintenance_phase["details"]["clean_artifacts"], 0)
        output_pack_phase = next(phase for phase in compile_state["phase_summary"] if phase["name"] == "output_pack_refresh")
        self.assertEqual(output_pack_phase["mode"], "incremental")
        self.assertEqual(output_pack_phase["details"]["dirty_pack_groups"], len(compile_state["dirty_output_pack_groups"]))
        self.assertEqual(output_pack_phase["details"]["clean_pack_groups"], 0)
        domain_pilot_phase = next(phase for phase in compile_state["phase_summary"] if phase["name"] == "domain_pilot_refresh")
        self.assertEqual(domain_pilot_phase["mode"], "incremental")
        self.assertEqual(
            domain_pilot_phase["details"]["dirty_protocols"],
            len(compile_state["dirty_domain_pilot_protocols"]),
        )
        self.assertEqual(domain_pilot_phase["details"]["clean_protocols"], 0)
        self.assertEqual(compiled["dirty_sources"], 1)
        self.assertEqual(compiled["clean_sources"], 0)
        self.assertEqual(compiled["dirty_source_ids"], [entry["id"]])
        self.assertEqual(compiled["clean_source_ids"], [])
        self.assertEqual(compiled["dirty_concept_sources"], 1)
        self.assertEqual(compiled["clean_concept_sources"], 0)
        self.assertEqual(compiled["dirty_concept_source_ids"], [entry["id"]])
        self.assertEqual(compiled["clean_concept_source_ids"], [])
        self.assertEqual(compiled["dirty_concepts"], len(compile_state["dirty_concept_slugs"]))
        self.assertEqual(compiled["clean_concepts"], 0)
        self.assertEqual(compiled["dirty_concept_slugs"], compile_state["dirty_concept_slugs"])
        self.assertEqual(compiled["clean_concept_slugs"], [])
        self.assertEqual(compiled["dirty_machine_memory_sources"], 1)
        self.assertEqual(compiled["clean_machine_memory_sources"], 0)
        self.assertEqual(compiled["dirty_machine_memory_source_ids"], [entry["id"]])
        self.assertEqual(compiled["clean_machine_memory_source_ids"], [])
        self.assertEqual(
            compiled["dirty_machine_memory_concept_slugs"],
            compile_state["dirty_machine_memory_concept_slugs"],
        )
        self.assertEqual(compiled["clean_machine_memory_concept_slugs"], [])
        self.assertFalse(compiled["machine_memory_core_reused"])
        self.assertEqual(compiled["dirty_ranking_sources"], 1)
        self.assertEqual(compiled["clean_ranking_sources"], 0)
        self.assertEqual(compiled["dirty_ranking_source_ids"], [entry["id"]])
        self.assertEqual(compiled["clean_ranking_source_ids"], [])
        self.assertEqual(
            compiled["dirty_ranking_concept_slugs"],
            compile_state["dirty_ranking_concept_slugs"],
        )
        self.assertEqual(compiled["clean_ranking_concept_slugs"], [])
        self.assertEqual(compiled["dirty_output_pack_groups"], compile_state["dirty_output_pack_groups"])
        self.assertEqual(compiled["clean_output_pack_groups"], [])
        self.assertEqual(compiled["dirty_domain_pilot_protocols"], compile_state["dirty_domain_pilot_protocols"])
        self.assertEqual(compiled["clean_domain_pilot_protocols"], [])
        self.assertEqual(compiled["index_changed_pages"], index_phase["details"]["updated_artifacts"])
        self.assertEqual(compiled["dirty_index_artifacts"], compile_state["dirty_index_artifacts"])
        self.assertEqual(compiled["clean_index_artifacts"], compile_state["clean_index_artifacts"])
        self.assertEqual(compiled["dirty_maintenance_artifacts"], compile_state["dirty_maintenance_artifacts"])
        self.assertEqual(compiled["clean_maintenance_artifacts"], [])

        compile_status = compile_status_path.read_text(encoding="utf-8")
        self.assertIn("## Compile Phases", compile_status)
        self.assertIn("incremental_source_compile", compile_status)
        self.assertIn("concept_refresh", compile_status)
        self.assertIn("dirty_concept_sources=1", compile_status)
        self.assertIn("## Dirty Concept Sources", compile_status)
        self.assertIn("machine_memory_refresh", compile_status)
        self.assertIn("dirty_machine_memory_sources=1", compile_status)
        self.assertIn("## Dirty Machine Memory Sources", compile_status)
        self.assertIn("## Dirty Machine Memory Concepts", compile_status)
        self.assertIn("ranking_refresh", compile_status)
        self.assertIn("dirty_ranking_sources=1", compile_status)
        self.assertIn("## Dirty Ranking Sources", compile_status)
        self.assertIn("## Dirty Ranking Concepts", compile_status)
        self.assertIn("output_pack_refresh", compile_status)
        self.assertIn("dirty_pack_groups=4", compile_status)
        self.assertIn("## Dirty Output Pack Groups", compile_status)
        self.assertIn("domain_pilot_refresh", compile_status)
        self.assertIn("## Dirty Domain Pilot Protocols", compile_status)
        self.assertIn("index_refresh", compile_status)
        self.assertIn("## Dirty Concepts", compile_status)
        self.assertIn("## Dirty Index Artifacts", compile_status)
        self.assertIn("## Dirty Maintenance Artifacts", compile_status)
        self.assertIn(".aiwiki/state/concept-build-state.json", compile_status)
        self.assertIn(".aiwiki/state/machine-memory-build-state.json", compile_status)
        self.assertIn(".aiwiki/state/ranking-build-state.json", compile_status)
        self.assertIn(".aiwiki/state/output-pack-build-state.json", compile_status)
        self.assertIn(".aiwiki/state/domain-pilot-build-state.json", compile_status)
        self.assertIn(".aiwiki/state/compile-state.json", compile_status)

    def test_compile_wiki_facade_reexports_compile_owner(self) -> None:
        self.assertIs(compile_wiki, compile_wiki_owner)

    def test_compile_skips_clean_source_pages_on_second_run(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")

        with patch("aiwiki.app_compile.utc_now", return_value="2026-04-10T10:00:00+00:00"):
            first = compile_wiki(self.root)

        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        first_frontmatter = parse_frontmatter(source_page.read_text(encoding="utf-8"))
        self.assertEqual(first_frontmatter["last_compiled_at"], first["compiled_at"])

        with patch("aiwiki.app_compile.utc_now", return_value="2026-04-10T10:05:00+00:00"):
            second = compile_wiki(self.root)

        second_frontmatter = parse_frontmatter(source_page.read_text(encoding="utf-8"))
        self.assertEqual(second["dirty_sources"], 0)
        self.assertEqual(second["clean_sources"], 1)
        self.assertEqual(second["dirty_source_ids"], [])
        self.assertEqual(second["clean_source_ids"], [entry["id"]])
        self.assertEqual(second_frontmatter["last_compiled_at"], first["compiled_at"])
        self.assertNotEqual(second["compiled_at"], first["compiled_at"])

        source_phase = next(phase for phase in second["phase_summary"] if phase["name"] == "incremental_source_compile")
        self.assertEqual(source_phase["details"]["updated_pages"], 0)
        self.assertEqual(source_phase["details"]["skipped_pages"], 1)

        compile_state = json.loads((self.root / ".aiwiki" / "state" / "compile-state.json").read_text(encoding="utf-8"))
        self.assertEqual(compile_state["dirty_source_ids"], [])
        self.assertEqual(compile_state["clean_source_ids"], [entry["id"]])

    def test_compile_skips_clean_concept_pages_on_second_run(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")

        with patch("aiwiki.app_compile.utc_now", return_value="2026-04-10T10:00:00+00:00"):
            first = compile_wiki(self.root)

        concept_page = sorted((self.root / "wiki" / "concepts").glob("*.md"))[0]
        concept_slugs = [path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md"))]
        first_frontmatter = parse_frontmatter(concept_page.read_text(encoding="utf-8"))
        self.assertEqual(first_frontmatter["last_compiled_at"], first["compiled_at"])

        with patch("aiwiki.app_compile.utc_now", return_value="2026-04-10T10:05:00+00:00"):
            second = compile_wiki(self.root)

        second_frontmatter = parse_frontmatter(concept_page.read_text(encoding="utf-8"))
        self.assertEqual(second["dirty_concepts"], 0)
        self.assertEqual(second["clean_concepts"], second["concepts"])
        self.assertEqual(second["dirty_concept_slugs"], [])
        self.assertEqual(set(second["clean_concept_slugs"]), set(concept_slugs))
        self.assertEqual(second_frontmatter["last_compiled_at"], first["compiled_at"])
        self.assertNotEqual(second["compiled_at"], first["compiled_at"])

        concept_phase = next(phase for phase in second["phase_summary"] if phase["name"] == "concept_refresh")
        self.assertEqual(concept_phase["mode"], "incremental")
        self.assertEqual(concept_phase["details"]["updated_pages"], 0)
        self.assertEqual(concept_phase["details"]["skipped_pages"], len(concept_slugs))

        compile_state = json.loads((self.root / ".aiwiki" / "state" / "compile-state.json").read_text(encoding="utf-8"))
        self.assertEqual(compile_state["dirty_concept_slugs"], [])
        self.assertEqual(set(compile_state["clean_concept_slugs"]), set(concept_slugs))

    def test_compile_reuses_clean_concept_source_terms_on_second_run(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        concept_build_state_path = self.root / ".aiwiki" / "state" / "concept-build-state.json"
        first_state = concept_build_state_path.read_text(encoding="utf-8")

        with patch(
            "aiwiki.app_content.entry_concept_terms",
            side_effect=AssertionError("should reuse clean concept source terms"),
        ), patch(
            "aiwiki.app_compile.entry_concept_terms",
            side_effect=AssertionError("should reuse clean concept source terms"),
        ):
            second = compile_wiki(self.root)

        self.assertEqual(second["dirty_concept_sources"], 0)
        self.assertEqual(second["clean_concept_sources"], 1)
        self.assertEqual(second["dirty_concept_source_ids"], [])
        self.assertEqual(second["clean_concept_source_ids"], [entry["id"]])
        self.assertEqual(first_state, concept_build_state_path.read_text(encoding="utf-8"))

        concept_phase = next(phase for phase in second["phase_summary"] if phase["name"] == "concept_refresh")
        self.assertEqual(concept_phase["details"]["dirty_concept_sources"], 0)
        self.assertEqual(concept_phase["details"]["clean_concept_sources"], 1)

    def test_compile_reuses_clean_machine_memory_core_on_second_run(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        machine_memory_build_state_path = self.root / ".aiwiki" / "state" / "machine-memory-build-state.json"
        first_state = machine_memory_build_state_path.read_text(encoding="utf-8")

        with patch(
            "aiwiki.app_compile.build_machine_memory",
            side_effect=AssertionError("should reuse clean machine memory core"),
        ):
            second = compile_wiki(self.root)

        self.assertEqual(second["dirty_machine_memory_sources"], 0)
        self.assertEqual(second["clean_machine_memory_sources"], 1)
        self.assertEqual(second["dirty_machine_memory_source_ids"], [])
        self.assertEqual(second["clean_machine_memory_source_ids"], [entry["id"]])
        self.assertEqual(second["dirty_machine_memory_concepts"], 0)
        self.assertEqual(
            len(second["clean_machine_memory_concept_slugs"]),
            second["clean_machine_memory_concepts"],
        )
        self.assertTrue(second["machine_memory_core_reused"])
        self.assertEqual(first_state, machine_memory_build_state_path.read_text(encoding="utf-8"))

        machine_memory_phase = next(
            phase for phase in second["phase_summary"] if phase["name"] == "machine_memory_refresh"
        )
        self.assertEqual(machine_memory_phase["details"]["dirty_machine_memory_sources"], 0)
        self.assertEqual(machine_memory_phase["details"]["clean_machine_memory_sources"], 1)
        self.assertEqual(machine_memory_phase["details"]["dirty_machine_memory_concepts"], 0)
        self.assertTrue(machine_memory_phase["details"]["reused_core"])

        compile_state = json.loads((self.root / ".aiwiki" / "state" / "compile-state.json").read_text(encoding="utf-8"))
        self.assertEqual(compile_state["dirty_machine_memory_source_ids"], [])
        self.assertEqual(compile_state["clean_machine_memory_source_ids"], [entry["id"]])
        self.assertEqual(compile_state["dirty_machine_memory_concept_slugs"], [])
        self.assertTrue(compile_state["machine_memory_core_reused"])

    def test_compile_reuses_clean_ranking_records_on_second_run(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        first = compile_wiki(self.root)

        ranking_build_state_path = self.root / ".aiwiki" / "state" / "ranking-build-state.json"
        first_state = ranking_build_state_path.read_text(encoding="utf-8")

        with patch(
            "aiwiki.app_compile.build_ranking_source_record",
            side_effect=AssertionError("should reuse clean source ranking records"),
        ), patch(
            "aiwiki.app_compile.build_ranking_concept_record",
            side_effect=AssertionError("should reuse clean concept ranking records"),
        ):
            second = compile_wiki(self.root)

        self.assertEqual(second["dirty_ranking_sources"], 0)
        self.assertEqual(second["clean_ranking_sources"], 1)
        self.assertEqual(second["dirty_ranking_source_ids"], [])
        self.assertEqual(second["clean_ranking_source_ids"], [entry["id"]])
        self.assertEqual(second["dirty_ranking_concepts"], 0)
        self.assertEqual(second["clean_ranking_concepts"], first["concepts"])
        self.assertEqual(second["dirty_ranking_concept_slugs"], [])
        self.assertEqual(first_state, ranking_build_state_path.read_text(encoding="utf-8"))

        ranking_phase = next(phase for phase in second["phase_summary"] if phase["name"] == "ranking_refresh")
        self.assertEqual(ranking_phase["details"]["dirty_ranking_sources"], 0)
        self.assertEqual(ranking_phase["details"]["clean_ranking_sources"], 1)
        self.assertEqual(ranking_phase["details"]["dirty_ranking_concepts"], 0)
        self.assertEqual(ranking_phase["details"]["clean_ranking_concepts"], second["clean_ranking_concepts"])

        compile_state = json.loads((self.root / ".aiwiki" / "state" / "compile-state.json").read_text(encoding="utf-8"))
        self.assertEqual(compile_state["dirty_ranking_source_ids"], [])
        self.assertEqual(compile_state["clean_ranking_source_ids"], [entry["id"]])
        self.assertEqual(compile_state["dirty_ranking_concept_slugs"], [])
        self.assertEqual(
            len(compile_state["clean_ranking_concept_slugs"]),
            second["clean_ranking_concepts"],
        )

    def test_compile_reuses_clean_output_pack_groups_on_second_run(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        output_pack_build_state_path = self.root / ".aiwiki" / "state" / "output-pack-build-state.json"
        first_state = output_pack_build_state_path.read_text(encoding="utf-8")

        with patch("aiwiki.app_content.build_output_pack_review_packs", side_effect=AssertionError("should reuse clean review packs")), patch(
            "aiwiki.app_content.build_output_pack_decision_memos",
            side_effect=AssertionError("should reuse clean decision memos"),
        ), patch("aiwiki.app_content.build_output_pack_sop_drafts", side_effect=AssertionError("should reuse clean sop drafts")):
            second = compile_wiki(self.root)

        self.assertEqual(second["dirty_output_pack_groups"], [])
        self.assertEqual(
            set(second["clean_output_pack_groups"]),
            {"lifecycle_summary", "review_packs", "decision_memos", "sop_drafts"},
        )
        self.assertEqual(first_state, output_pack_build_state_path.read_text(encoding="utf-8"))

        output_pack_phase = next(phase for phase in second["phase_summary"] if phase["name"] == "output_pack_refresh")
        self.assertEqual(output_pack_phase["details"]["dirty_pack_groups"], 0)
        self.assertEqual(output_pack_phase["details"]["clean_pack_groups"], 4)

        compile_state = json.loads((self.root / ".aiwiki" / "state" / "compile-state.json").read_text(encoding="utf-8"))
        self.assertEqual(compile_state["dirty_output_pack_groups"], [])
        self.assertEqual(
            set(compile_state["clean_output_pack_groups"]),
            {"lifecycle_summary", "review_packs", "decision_memos", "sop_drafts"},
        )

    def test_compile_reuses_clean_domain_pilot_scorecards_on_second_run(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        domain_pilot_build_state_path = self.root / ".aiwiki" / "state" / "domain-pilot-build-state.json"
        first_state = domain_pilot_build_state_path.read_text(encoding="utf-8")

        with patch(
            "aiwiki.app_content.build_domain_pilot_scorecard",
            side_effect=AssertionError("should reuse clean domain pilot scorecards"),
        ):
            second = compile_wiki(self.root)

        self.assertEqual(second["dirty_domain_pilot_protocols"], [])
        self.assertTrue(second["clean_domain_pilot_protocols"])
        self.assertEqual(first_state, domain_pilot_build_state_path.read_text(encoding="utf-8"))

        domain_pilot_phase = next(phase for phase in second["phase_summary"] if phase["name"] == "domain_pilot_refresh")
        self.assertEqual(domain_pilot_phase["details"]["dirty_protocols"], 0)
        self.assertEqual(
            domain_pilot_phase["details"]["clean_protocols"],
            len(second["clean_domain_pilot_protocols"]),
        )

        compile_state = json.loads((self.root / ".aiwiki" / "state" / "compile-state.json").read_text(encoding="utf-8"))
        self.assertEqual(compile_state["dirty_domain_pilot_protocols"], [])
        self.assertEqual(
            compile_state["clean_domain_pilot_protocols"],
            second["clean_domain_pilot_protocols"],
        )

    def test_compile_skips_clean_index_artifacts_on_second_run(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")

        with patch("aiwiki.app_compile.utc_now", return_value="2026-04-10T10:00:00+00:00"):
            compile_wiki(self.root)

        index_page = self.root / "wiki" / "indexes" / "index.md"
        first_index = index_page.read_text(encoding="utf-8")
        self.assertIn("- 最近编译时间：`2026-04-10T10:00:00+00:00`", first_index)

        with patch("aiwiki.app_compile.utc_now", return_value="2026-04-10T10:05:00+00:00"):
            second = compile_wiki(self.root)

        second_index = index_page.read_text(encoding="utf-8")
        self.assertEqual(first_index, second_index)
        self.assertIn("wiki/indexes/index.md", second["clean_index_artifacts"])
        self.assertNotIn("wiki/indexes/index.md", second["dirty_index_artifacts"])

        index_phase = next(phase for phase in second["phase_summary"] if phase["name"] == "index_refresh")
        self.assertEqual(index_phase["mode"], "incremental")
        self.assertGreater(index_phase["details"]["tracked_artifacts"], 0)
        self.assertGreater(index_phase["details"]["clean_artifacts"], 0)
        self.assertGreater(index_phase["details"]["skipped_artifacts"], 0)

        compile_state = json.loads((self.root / ".aiwiki" / "state" / "compile-state.json").read_text(encoding="utf-8"))
        self.assertIn("wiki/indexes/index.md", compile_state["clean_index_artifacts"])
        self.assertNotIn("wiki/indexes/index.md", compile_state["dirty_index_artifacts"])

    def test_compile_skips_clean_maintenance_artifacts_on_second_run(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")

        with patch("aiwiki.app_compile.utc_now", return_value="2026-04-10T10:00:00+00:00"):
            compile_wiki(self.root)

        material_state_path = self.root / ".aiwiki" / "state" / "material-state.json"
        knowledge_lifecycle_path = self.root / ".aiwiki" / "state" / "knowledge-lifecycle.json"
        first_material_state = material_state_path.read_text(encoding="utf-8")
        first_knowledge_lifecycle = knowledge_lifecycle_path.read_text(encoding="utf-8")

        with patch("aiwiki.app_compile.utc_now", return_value="2026-04-10T10:05:00+00:00"):
            second = compile_wiki(self.root)

        self.assertEqual(first_material_state, material_state_path.read_text(encoding="utf-8"))
        self.assertEqual(first_knowledge_lifecycle, knowledge_lifecycle_path.read_text(encoding="utf-8"))
        self.assertIn(".aiwiki/state/material-state.json", second["clean_maintenance_artifacts"])
        self.assertIn(".aiwiki/state/knowledge-lifecycle.json", second["clean_maintenance_artifacts"])
        self.assertNotIn(".aiwiki/state/material-state.json", second["dirty_maintenance_artifacts"])
        self.assertNotIn(".aiwiki/state/knowledge-lifecycle.json", second["dirty_maintenance_artifacts"])

        maintenance_phase = next(
            phase for phase in second["phase_summary"] if phase["name"] == "cold_archive_maintenance"
        )
        self.assertEqual(maintenance_phase["mode"], "incremental")
        self.assertGreater(maintenance_phase["details"]["tracked_artifacts"], 0)
        self.assertGreater(maintenance_phase["details"]["clean_artifacts"], 0)
        self.assertGreater(maintenance_phase["details"]["skipped_artifacts"], 0)

        compile_state = json.loads((self.root / ".aiwiki" / "state" / "compile-state.json").read_text(encoding="utf-8"))
        self.assertIn(".aiwiki/state/material-state.json", compile_state["clean_maintenance_artifacts"])
        self.assertNotIn(".aiwiki/state/material-state.json", compile_state["dirty_maintenance_artifacts"])

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

    def test_compile_clears_active_lifecycle_override_for_missing_concept_page(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        override_state = load_knowledge_lifecycle_override_state(self.root)
        entries = list(override_state.get("entries", []))
        entries.append(
            {
                "page_id": "concept-missing-noise",
                "slug": "missing-noise",
                "path": "wiki/concepts/missing-noise.md",
                "kind": "concept",
                "lifecycle_state": "deferred",
                "active": True,
                "operation": "review",
                "reason_codes": ["manual-review-ack"],
                "applied_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "note": "Ack for a concept that later disappeared.",
            }
        )
        save_knowledge_lifecycle_override_state(self.root, {"version": 1, "entries": entries})

        compile_wiki(self.root)

        updated_override_state = load_knowledge_lifecycle_override_state(self.root)
        stale_entry = next(entry for entry in updated_override_state["entries"] if entry["slug"] == "missing-noise")
        self.assertFalse(stale_entry["active"])
        self.assertEqual(stale_entry["cleared_reason_codes"], ["missing-target"])
        lint = lint_wiki(self.root)
        lint_report = (self.root / lint["path"]).read_text(encoding="utf-8")
        self.assertNotIn("Knowledge lifecycle override entry references missing page `wiki/concepts/missing-noise.md`.", lint_report)

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

    def test_compile_tracks_machine_memory_drift_between_snapshots(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        second = self.root / "sample-two.md"
        second.write_text("# Latency Notes\n\nThroughput and latency tradeoffs.\n", encoding="utf-8")
        ingest_source(self.root, str(second), title="Latency Notes")

        result = compile_wiki(self.root)

        drift_report = (self.root / "wiki" / "indexes" / "drift-report.md").read_text(encoding="utf-8")
        history_lines = (self.root / ".aiwiki" / "state" / "machine-memory-history.jsonl").read_text(
            encoding="utf-8"
        ).strip().splitlines()
        self.assertTrue(result["machine_memory_changed"])
        self.assertIn("新增来源节点：`1`", drift_report)
        self.assertGreaterEqual(len(history_lines), 2)
        latest = json.loads(history_lines[-1])
        self.assertEqual(len(latest["added_source_ids"]), 1)
        self.assertTrue(latest["added_source_ids"][0].endswith("-latency-notes"))

    def test_compile_preserves_existing_summary_on_recompile(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        current = source_page.read_text(encoding="utf-8")
        source_page.write_text(
            current.replace(
                "- Pending LLM summary.",
                "- Transformer scaling improves quality while increasing inference cost.",
            ),
            encoding="utf-8",
        )

        compile_wiki(self.root)
        refreshed = source_page.read_text(encoding="utf-8")
        self.assertIn("Transformer scaling improves quality while increasing inference cost.", refreshed)
        self.assertNotIn("Pending LLM summary.", refreshed)

    def test_compile_invalidates_summary_when_raw_source_changes(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                "- Old summary from llm that should be invalidated.",
            ),
            encoding="utf-8",
        )
        stored_source = self.root / entry["stored_path"]
        stored_source.write_text(
            "# Transformer Scaling\n\nLatency behavior changed after the source edit.\n",
            encoding="utf-8",
        )

        compile_wiki(self.root)

        refreshed = source_page.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(refreshed)
        self.assertIn("- Pending LLM summary.", refreshed)
        self.assertNotIn("Old summary from llm", refreshed)
        self.assertIn("Latency", refreshed)
        self.assertNotIn("summary", [item.lower() for item in frontmatter["concepts"]])
        self.assertTrue(frontmatter["source_sha256"])

    def test_compile_invalidates_concept_summary_when_backing_source_changes(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_page = self.root / "wiki" / "concepts" / "transformer-scaling.md"
        self._rewrite_concept_summary(concept_page, ["- OLD CONCEPT SUMMARY"])
        stored_source = self.root / entry["stored_path"]
        stored_source.write_text(
            "# Transformer Scaling\n\nLatency throughput cache locality.\n",
            encoding="utf-8",
        )

        compile_wiki(self.root)

        refreshed = concept_page.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(refreshed)
        self.assertNotIn("OLD CONCEPT SUMMARY", refreshed)
        self.assertIn("当前概念汇总了 `1` 个 source page", refreshed)
        self.assertTrue(frontmatter["source_signature"])
        self.assertTrue(frontmatter["render_signature"])

    def test_compile_rebuilds_dirty_concept_when_source_summary_changes(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")

        with patch("aiwiki.app_compile.utc_now", return_value="2026-04-10T10:00:00+00:00"):
            compile_wiki(self.root)

        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                "- Transformer scaling also rise.",
            ),
            encoding="utf-8",
        )
        compile_wiki(self.root)

        concept_page = self.root / "wiki" / "concepts" / "transformer-scaling.md"
        self._rewrite_concept_summary(
            concept_page,
            [
                "- Custom concept summary stays and currently appears",
                "- Keep the current synthesis grounded in the linked sources.",
            ],
        )
        before_frontmatter = parse_frontmatter(concept_page.read_text(encoding="utf-8"))
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace(
                "- Transformer scaling also rise.",
                "- TRANSFORMER scaling also rise!",
            ),
            encoding="utf-8",
        )

        with patch("aiwiki.app_compile.utc_now", return_value="2026-04-10T10:05:00+00:00"):
            second = compile_wiki(self.root)

        refreshed = concept_page.read_text(encoding="utf-8")
        after_frontmatter = parse_frontmatter(refreshed)
        self.assertIn("Custom concept summary stays", refreshed)
        self.assertEqual(before_frontmatter["source_signature"], after_frontmatter["source_signature"])
        self.assertNotEqual(before_frontmatter["render_signature"], after_frontmatter["render_signature"])
        self.assertEqual(after_frontmatter["last_compiled_at"], second["compiled_at"])
        self.assertIn("transformer-scaling", second["dirty_concept_slugs"])

    def test_compile_preserves_concept_render_signature_update_after_step_migration(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                "- Transformer scaling also rise.",
            ),
            encoding="utf-8",
        )
        compile_wiki(self.root)

        concept_page = self.root / "wiki" / "concepts" / "transformer-scaling.md"
        before_frontmatter = parse_frontmatter(concept_page.read_text(encoding="utf-8"))
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace(
                "- Transformer scaling also rise.",
                "- TRANSFORMER scaling also rise!",
            ),
            encoding="utf-8",
        )

        second = compile_wiki(self.root)
        after_frontmatter = parse_frontmatter(concept_page.read_text(encoding="utf-8"))

        self.assertTrue(before_frontmatter["render_signature"])
        self.assertTrue(after_frontmatter["render_signature"])
        self.assertNotEqual(before_frontmatter["render_signature"], after_frontmatter["render_signature"])
        self.assertIn("transformer-scaling", second["dirty_concept_slugs"])

    def test_compile_removes_stale_concept_pages_when_concepts_disappear(self) -> None:
        removable = self.root / "removable.md"
        removable.write_text("# Note\n\nAlpha beta gamma.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(removable), title="Note")
        compile_wiki(self.root)

        alpha_page = self.root / "wiki" / "concepts" / "alpha.md"
        self.assertTrue(alpha_page.exists())

        stored_source = self.root / entry["stored_path"]
        stored_source.write_text("# Note\n\nDelta epsilon zeta.\n", encoding="utf-8")

        compile_wiki(self.root)

        self.assertFalse(alpha_page.exists())
        self.assertTrue((self.root / "wiki" / "concepts" / "delta.md").exists())

    def test_compile_marks_related_index_artifact_dirty_when_concepts_change(self) -> None:
        removable = self.root / "removable.md"
        removable.write_text("# Note\n\nAlpha beta gamma.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(removable), title="Note")
        compile_wiki(self.root)

        concepts_index = self.root / "wiki" / "indexes" / "concepts.md"
        before = concepts_index.read_text(encoding="utf-8")
        self.assertIn("Alpha", before)

        stored_source = self.root / entry["stored_path"]
        stored_source.write_text("# Note\n\nDelta epsilon zeta.\n", encoding="utf-8")

        result = compile_wiki(self.root)

        after = concepts_index.read_text(encoding="utf-8")
        self.assertIn("wiki/indexes/concepts.md", result["dirty_index_artifacts"])
        self.assertNotIn("wiki/indexes/concepts.md", result["clean_index_artifacts"])
        self.assertNotEqual(before, after)
        self.assertIn("Delta", after)

    def test_compile_marks_related_maintenance_artifact_dirty_when_concepts_change(self) -> None:
        removable = self.root / "removable.md"
        removable.write_text("# Note\n\nAlpha beta gamma.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(removable), title="Note")
        compile_wiki(self.root)

        lifecycle_path = self.root / ".aiwiki" / "state" / "knowledge-lifecycle.json"
        before = lifecycle_path.read_text(encoding="utf-8")
        self.assertIn('"path": "wiki/concepts/alpha.md"', before)

        stored_source = self.root / entry["stored_path"]
        stored_source.write_text("# Note\n\nDelta epsilon zeta.\n", encoding="utf-8")

        result = compile_wiki(self.root)

        after = lifecycle_path.read_text(encoding="utf-8")
        self.assertIn(".aiwiki/state/knowledge-lifecycle.json", result["dirty_maintenance_artifacts"])
        self.assertNotIn(".aiwiki/state/knowledge-lifecycle.json", result["clean_maintenance_artifacts"])
        self.assertNotEqual(before, after)
        self.assertIn('"path": "wiki/concepts/delta.md"', after)

    def test_compile_marks_concept_source_dirty_when_source_summary_changes(self) -> None:
        removable = self.root / "removable.md"
        removable.write_text("# Note\n\nAlpha beta gamma.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(removable), title="Note")
        compile_wiki(self.root)

        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace("- Pending LLM summary.", "- Delta epsilon zeta."),
            encoding="utf-8",
        )

        with patch("aiwiki.app_content.entry_concept_terms", wraps=entry_concept_terms) as patched_content_terms, patch(
            "aiwiki.app_compile.entry_concept_terms",
            wraps=entry_concept_terms,
        ) as patched_compile_terms:
            result = compile_wiki(self.root)

        self.assertEqual(patched_content_terms.call_count, 1)
        self.assertEqual(patched_compile_terms.call_count, 1)
        self.assertEqual(result["dirty_concept_source_ids"], [entry["id"]])
        self.assertEqual(result["dirty_ranking_source_ids"], [entry["id"]])
        self.assertIn("delta", result["dirty_concept_slugs"])
        self.assertTrue((self.root / "wiki" / "concepts" / "delta.md").exists())

    def test_compile_marks_machine_memory_source_dirty_when_source_summary_changes(self) -> None:
        removable = self.root / "removable.md"
        removable.write_text("# Note\n\nAlpha beta gamma.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(removable), title="Note")
        compile_wiki(self.root)

        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace("- Pending LLM summary.", "- Delta epsilon zeta."),
            encoding="utf-8",
        )

        result = compile_wiki(self.root)

        self.assertEqual(result["dirty_machine_memory_source_ids"], [entry["id"]])
        self.assertIn("delta", result["dirty_machine_memory_concept_slugs"])
        self.assertFalse(result["machine_memory_core_reused"])
        compile_state = json.loads((self.root / ".aiwiki" / "state" / "compile-state.json").read_text(encoding="utf-8"))
        self.assertEqual(compile_state["dirty_machine_memory_source_ids"], [entry["id"]])
        self.assertIn("delta", compile_state["dirty_machine_memory_concept_slugs"])

    def test_compile_marks_concept_source_dirty_when_manual_link_changes(self) -> None:
        removable = self.root / "removable.md"
        removable.write_text("# Note\n\nAlpha beta gamma.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(removable), title="Note")
        compile_wiki(self.root)

        save_manual_link_state(
            self.root,
            {
                "version": 1,
                "source_to_concept": [
                    {
                        "source_id": entry["id"],
                        "concept_slug": "delta",
                        "active": True,
                    }
                ],
            },
        )

        with patch("aiwiki.app_content.entry_concept_terms", wraps=entry_concept_terms) as patched_content_terms, patch(
            "aiwiki.app_compile.entry_concept_terms",
            wraps=entry_concept_terms,
        ) as patched_compile_terms:
            result = compile_wiki(self.root)

        self.assertEqual(patched_content_terms.call_count, 1)
        self.assertEqual(patched_compile_terms.call_count, 1)
        self.assertEqual(result["dirty_concept_source_ids"], [entry["id"]])
        self.assertIn("delta", result["dirty_concept_slugs"])
        self.assertTrue((self.root / "wiki" / "concepts" / "delta.md").exists())

    def test_compile_marks_machine_memory_concept_dirty_when_manual_link_changes(self) -> None:
        removable = self.root / "removable.md"
        removable.write_text("# Note\n\nAlpha beta gamma.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(removable), title="Note")
        compile_wiki(self.root)

        save_manual_link_state(
            self.root,
            {
                "version": 1,
                "source_to_concept": [
                    {
                        "source_id": entry["id"],
                        "concept_slug": "delta",
                        "active": True,
                    }
                ],
            },
        )

        result = compile_wiki(self.root)

        self.assertEqual(result["dirty_machine_memory_source_ids"], [entry["id"]])
        self.assertIn("delta", result["dirty_machine_memory_concept_slugs"])
        self.assertFalse(result["machine_memory_core_reused"])
        compile_state = json.loads((self.root / ".aiwiki" / "state" / "compile-state.json").read_text(encoding="utf-8"))
        self.assertEqual(compile_state["dirty_machine_memory_source_ids"], [entry["id"]])
        self.assertIn("delta", compile_state["dirty_machine_memory_concept_slugs"])

    def test_compile_keeps_manual_link_when_auto_terms_already_fill_limit(self) -> None:
        removable = self.root / "removable.md"
        removable.write_text("# Note\n\nAlpha beta gamma delta epsilon zeta eta theta.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(removable), title="Note")
        compile_wiki(self.root)

        save_manual_link_state(
            self.root,
            {
                "version": 1,
                "source_to_concept": [
                    {
                        "source_id": entry["id"],
                        "concept_slug": "manual-bridge",
                        "active": True,
                    }
                ],
            },
        )

        compile_wiki(self.root)

        self.assertTrue((self.root / "wiki" / "concepts" / "manual-bridge.md").exists())
        concept_build_state = json.loads(
            (self.root / ".aiwiki" / "state" / "concept-build-state.json").read_text(encoding="utf-8")
        )
        self.assertIn("manual bridge", concept_build_state["entry_records"][entry["id"]]["terms"])

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
        self.assertIn("## 当前线索", report_text)
        self.assertIn("## 下一步", report_text)
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
        self.assertEqual(state["active_protocol"], "general")
        self.assertIn("investing", state["available_protocols"])
        self.assertIn("research", state["available_protocols"])
        self.assertIn("product", state["available_protocols"])
        self.assertIn("ops", state["available_protocols"])
        schema_index = (self.root / "schema" / "index.md").read_text(encoding="utf-8")
        self.assertIn("协议规则", schema_index)

    def test_ensure_layout_bootstraps_runtime_dashboard_files(self) -> None:
        for relative, marker in (
            ("wiki/indexes/furnace-center.md", "炉心面板"),
            ("wiki/indexes/execution-center.md", "执行中心"),
            ("wiki/indexes/execution-audit.md", "执行审计"),
            ("wiki/indexes/review-center.md", "审阅中心"),
            ("wiki/indexes/graph-view.md", "图谱视图"),
        ):
            path = self.root / relative
            self.assertTrue(path.exists(), relative)
            self.assertIn(marker, path.read_text(encoding="utf-8"))

    def test_compile_writes_furnace_center_markdown_and_html(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        ask_question(self.root, "Compare transformer scale and inference cost", "report")

        compile_wiki(self.root)

        dashboard = self.root / "wiki" / "indexes" / "furnace-center.md"
        dashboard_payload = dashboard.read_text(encoding="utf-8")
        html_path = self.root / "output" / "control" / "furnace-center.html"
        html_payload = html_path.read_text(encoding="utf-8")
        self.assertTrue(dashboard.exists())
        self.assertTrue(html_path.exists())
        self.assertIn("今天先做什么", dashboard_payload)
        self.assertIn("本地炉心面板", dashboard_payload)
        self.assertIn("`output/control/furnace-center.html`", dashboard_payload)
        self.assertNotIn("[本地炉心面板](", dashboard_payload)
        self.assertIn("Compare transformer scale and inference cost", dashboard_payload)
        self.assertIn("Furnace Center", html_payload)
        self.assertIn("../../wiki/indexes/furnace-center.md", html_payload)
        self.assertIn("Compare transformer scale and inference cost", html_payload)

    def test_compile_graph_view_note_explains_local_html_behavior(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        graph_view = (self.root / "wiki" / "indexes" / "graph-view.md").read_text(encoding="utf-8")

        self.assertIn("`output/graph/machine-memory.html`", graph_view)
        self.assertIn("默认工作流仍然是先看报告", graph_view)
        self.assertIn("材料提到概念", graph_view)
        self.assertIn("判断冲突", graph_view)
        self.assertIn("决策依据", graph_view)
        # The Mihomo/Clash troubleshooting hint must be present in chinese, but
        # we deliberately do not assert the english MIME literal `text/html` so
        # the user-facing surface stays chinese-first.
        self.assertIn("Mihomo/Clash", graph_view)
        self.assertIn("代理客户端", graph_view)

    def test_compile_refreshes_managed_dashboard_templates(self) -> None:
        graph_view = self.root / "wiki" / "indexes" / "graph-view.md"
        graph_view.write_text("# Stale User Copy\n\nold graph copy\n", encoding="utf-8")

        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        result = compile_wiki(self.root)

        payload = graph_view.read_text(encoding="utf-8")
        self.assertIn("# 图谱视图", payload)
        self.assertIn("默认工作流仍然是先看报告", payload)
        self.assertNotIn("Stale User Copy", payload)
        self.assertIn("wiki/indexes/graph-view.md", result["dirty_index_artifacts"])
        index_step = next(item for item in result["phase_summary"] if item["name"] == "index_refresh")
        self.assertGreaterEqual(index_step["details"]["updated_artifacts"], 1)

    def test_ensure_layout_does_not_overwrite_existing_dashboard_files(self) -> None:
        graph_view = self.root / "wiki" / "indexes" / "graph-view.md"
        graph_view.write_text("# User Owned Graph View\n\nkeep me until compile\n", encoding="utf-8")

        ensure_layout(self.root)

        self.assertIn("User Owned Graph View", graph_view.read_text(encoding="utf-8"))

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

    def test_compile_writes_machine_memory_graph_html(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        graph_html = self.root / "output" / "graph" / "machine-memory.html"
        payload = graph_html.read_text(encoding="utf-8")
        self.assertTrue(graph_html.exists())
        self.assertIn("炼丹炉关系图谱", payload)
        self.assertNotIn("Machine Memory Graph", payload)
        self.assertIn("<svg", payload)
        self.assertIn("Transformer Scaling", payload)
        self.assertIn("../../wiki/indexes/graph-view.md", payload)
        self.assertIn("关系图谱说明", payload)
        self.assertIn("材料提到概念", payload)
        self.assertIn("关系说明", payload)
        self.assertIn("data-relation-label", payload)
        self.assertNotIn("related edge", payload)

    def test_compile_writes_review_center_html(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        review_html = self.root / "output" / "review" / "review-center.html"
        payload = review_html.read_text(encoding="utf-8")
        self.assertTrue(review_html.exists())
        self.assertIn("Review Center", payload)
        self.assertIn("待审项目", payload)
        self.assertIn("../../wiki/indexes/review-center.md", payload)

    def test_review_center_html_surfaces_lifecycle_governance_summary(self) -> None:
        backlog_title, retired_title = self._seed_lifecycle_governance_surface_state()

        review_html = self.root / "output" / "review" / "review-center.html"
        payload = review_html.read_text(encoding="utf-8")

        self.assertIn("生命周期概念待审", payload)
        self.assertIn("已退役概念", payload)
        self.assertIn(backlog_title, payload)
        self.assertIn(retired_title, payload)

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

    def test_compile_writes_execution_center_markdown_and_html(self) -> None:
        self._seed_machine_memory_actions()
        compile_wiki(self.root)

        dashboard = self.root / "wiki" / "indexes" / "execution-center.md"
        html_path = self.root / "output" / "control" / "execution-center.html"
        dashboard_payload = dashboard.read_text(encoding="utf-8")
        html_payload = html_path.read_text(encoding="utf-8")
        self.assertTrue(dashboard.exists())
        self.assertTrue(html_path.exists())
        self.assertIn("Page-level patch steps", dashboard_payload)
        self.assertIn("Execution Center", html_payload)
        self.assertIn("../../wiki/indexes/execution-center.md", html_payload)

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

    def test_compile_writes_execution_audit_markdown_and_html(self) -> None:
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
        review_machine_memory_action(self.root, "manual-link-action", "accepted", note="Accepted for audit view.")
        dry_run = apply_machine_memory_action(self.root, "manual-link-action", dry_run=True)
        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        apply_machine_memory_action(
            self.root,
            "manual-link-action",
            note="Safe apply for audit page.",
            bundle_path=dry_run["bundle_path"],
        )
        revert_machine_memory_action(self.root, "manual-link-action", note="Rollback for audit page.")
        compile_wiki(self.root)

        dashboard = self.root / "wiki" / "indexes" / "execution-audit.md"
        html_path = self.root / "output" / "control" / "execution-audit.html"
        dashboard_payload = dashboard.read_text(encoding="utf-8")
        html_payload = html_path.read_text(encoding="utf-8")
        self.assertTrue(dashboard.exists())
        self.assertTrue(html_path.exists())
        self.assertIn("Policy Bands", dashboard_payload)
        self.assertIn("Recent Apply", dashboard_payload)
        self.assertIn("Recent Revert", dashboard_payload)
        self.assertIn("Execution Audit", html_payload)
        self.assertIn("../../wiki/indexes/execution-audit.md", html_payload)

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

    def test_compile_persists_planner_state_and_policy_history_for_citation_snapshot_repairs(self) -> None:
        _, _, action = self._prepare_citation_snapshot_refresh_action()

        review_machine_memory_action(self.root, action["id"], "accepted", note="Queue safe apply.")
        compile_wiki(self.root)

        planner = load_planner_state(self.root)
        self.assertEqual(planner["state_path"], ".aiwiki/state/planner-state.json")
        self.assertGreaterEqual(planner["counts"]["pending_proposals"], 1)
        self.assertEqual(planner["next_action"]["action_id"], action["id"])
        self.assertEqual(planner["priority_queue"][0]["action_id"], action["id"])
        self.assertGreater(planner["priority_queue"][0]["priority_score"], 0)
        proposal = next(item for item in planner["pending_proposals"] if item["action_id"] == action["id"])
        self.assertTrue(proposal["auto_bundle_candidate"])
        self.assertFalse(proposal["human_required"])

        decisions = load_execution_policy_decision_history(self.root, limit=16)
        record = next(
            item
            for item in decisions
            if item.get("action_id") == action["id"] and item.get("status") == "accepted"
        )
        self.assertEqual(record["policy_decision"], "allow")
        self.assertEqual(record["policy_rule_id"], "general:refresh-citation-snapshots")
        self.assertEqual(record["execution_band"], "bundle-safe-apply")

        audit_payload = (self.root / "wiki" / "indexes" / "execution-audit.md").read_text(encoding="utf-8")
        self.assertIn("Recent Policy Decisions", audit_payload)
        self.assertIn(action["title"], audit_payload)
        self.assertIn("decision `allow`", audit_payload)

    def test_nightly_health_persists_planner_execution_history_for_auto_bundle_candidates(self) -> None:
        _, _, action = self._prepare_citation_snapshot_refresh_action()
        review_machine_memory_action(self.root, action["id"], "accepted", note="Queue nightly auto bundle.")
        compile_wiki(self.root)

        result = nightly_health(self.root)
        planner = load_planner_state(self.root)
        executed = next(item for item in planner["executed_actions"] if item.get("action_id") == action["id"])
        nightly_state = json.loads((self.root / ".aiwiki" / "state" / "nightly-health.json").read_text(encoding="utf-8"))

        self.assertGreaterEqual(planner["counts"]["executed_actions"], 1)
        self.assertEqual(executed["source"], "nightly-auto-bundle")
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
        self.assertGreaterEqual(len(auto_applied), 1)
        resolved_ids = {a["id"] for a in auto_applied if a.get("status") == "resolved"}
        self.assertIn(bridge["id"], resolved_ids)

    def test_compile_writes_drift_warnings_for_concept_disappear_source_break_and_judgment_invalidation(self) -> None:
        _, _, _ = self._prepare_citation_snapshot_refresh_action()
        compile_state_path = self.root / ".aiwiki" / "state" / "compile-state.json"
        previous_compile_state = json.loads(compile_state_path.read_text(encoding="utf-8"))
        previous_compile_state["clean_concept_slugs"] = sorted(
            set(previous_compile_state.get("clean_concept_slugs", [])) | {"phantom-concept"}
        )
        compile_state_path.write_text(
            json.dumps(previous_compile_state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        result = compile_wiki(self.root)
        compile_state = json.loads(compile_state_path.read_text(encoding="utf-8"))
        warning_kinds = {item["kind"] for item in compile_state["drift_warnings"]}

        self.assertIn("concept-disappear", warning_kinds)
        self.assertIn("source-reference-break", warning_kinds)
        self.assertIn("judgment-invalidation", warning_kinds)
        self.assertEqual(result["drift_warnings"], compile_state["drift_warnings"])

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
        self.assertIn("## 当前线索", report_text)
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

    def test_compile_rebuilds_cache_on_schema_mismatch(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        cache_db = self.root / ".aiwiki" / "cache.db"
        with sqlite3.connect(cache_db) as connection:
            connection.execute(
                "UPDATE cache_meta SET value = ? WHERE key = ?",
                (str(CACHE_SCHEMA_VERSION - 1), "schema_version"),
            )
            connection.commit()

        compile_wiki(self.root)

        cache_status = load_cache_status(self.root)
        self.assertEqual(cache_status["schema_version"], CACHE_SCHEMA_VERSION)
        self.assertEqual(cache_status["last_sync"]["rebuild_reason"], "schema-mismatch")
        self.assertEqual(cache_status["last_rebuild"]["reason"], "schema-mismatch")
        self.assertGreaterEqual(cache_status["stats"]["rebuilds"], 1)

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

    def test_cli_cache_drop_removes_db(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        code = cli_main(["--root", str(self.root), "cache", "--drop"])

        self.assertEqual(code, 0)
        self.assertFalse((self.root / ".aiwiki" / "cache.db").exists())

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

    def test_compile_invalidates_accepted_rewrite_when_source_signature_changes(self) -> None:
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
        self.assertTrue(review["apply_ready"])

        stored_source = self.root / entry["stored_path"]
        stored_source.write_text(
            "# Transformer Scaling\n\nLatency throughput cache locality changed after review.\n",
            encoding="utf-8",
        )

        compile_wiki(self.root)

        state = json.loads((self.root / ".aiwiki" / "state" / "concept-rewrite-proposals.json").read_text(encoding="utf-8"))
        proposal = next(item for item in state["proposals"] if item["slug"] == slug)
        self.assertEqual(proposal["status"], "proposed")
        self.assertFalse(proposal["apply_ready"])
        self.assertEqual(proposal["candidate_markdown"], "")
        self.assertEqual(proposal["reviewed_at"], "")
        proposal_text = (self.root / proposal["proposal_path"]).read_text(encoding="utf-8")
        self.assertIn("当前还没有生成候选重写内容", proposal_text)

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
        restored = concept_page.read_text(encoding="utf-8")
        self.assertIn("Existing synthesis", restored)
        self.assertNotIn("Rewritten synthesis", restored)

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

        result = revert_machine_memory_action(self.root, "manual-link-action", note="Rollback this safe apply.")

        self.assertEqual(result["status"], "proposed")
        manual_link_state = json.loads((self.root / ".aiwiki" / "state" / "manual-links.json").read_text(encoding="utf-8"))
        self.assertFalse(manual_link_state["source_to_concept"][0]["active"])
        receipt = json.loads((self.root / result["receipt_path"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt["kind"], "execution-receipt")
        self.assertEqual(receipt["operation"], "revert")
        self.assertEqual(receipt["bundle"]["status"], "proposed")
        history_lines = (self.root / ".aiwiki" / "state" / "execution-receipts.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(history_lines), 2)
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

    def test_lint_warns_when_reviewed_decision_keeps_placeholder_asset_sections(self) -> None:
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
        self.assertIn("Decision page still has placeholder `Counter Evidence` content.", report_text)

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

        report_markdown = "\n".join(
            [
                "---",
                'id: "query-1"',
                'kind: "output"',
                'format: "report"',
                'query: "Compare transformer scale and inference cost"',
                'generated_by: "aiwiki-ask"',
                'created_at: "2026-04-05T00:00:00+00:00"',
                "---",
                "",
                "# Compare transformer scale and inference cost",
                "",
                "Transformer capability rises with scale, while inference cost also grows. See `wiki/sources/"
                f"{entry['id']}.md`.",
            ]
        )
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
        report_markdown = "\n".join(
            [
                "---",
                'id: "query-1"',
                'kind: "output"',
                'format: "report"',
                'query: "Compare transformer scale and inference cost"',
                'generated_by: "aiwiki-ask"',
                'created_at: "2026-04-05T00:00:00+00:00"',
                "---",
                "",
                "# Compare transformer scale and inference cost",
                "",
                f"See `wiki/sources/{entry['id']}.md`.",
            ]
        )
        client = CapturingClient(report_markdown)

        run_ask(
            self.root,
            "Compare transformer scale and inference cost",
            "report",
            client=client,
        )

        self.assertIn("LATE-MARKER", client.prompt)
        self.assertNotIn("EARLY-MARKER EARLY-MARKER EARLY-MARKER EARLY-MARKER EARLY-MARKER", client.prompt)

    def test_compile_generates_agent_workbench_and_role_packs(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        workbench = (self.root / "wiki" / "indexes" / "agent-workbench.md").read_text(encoding="utf-8")
        self.assertIn("Agent Workbench", workbench)
        self.assertIn("Ingest Agent", workbench)
        self.assertIn("../../output/agents/ingest-agent.md", workbench)

        for role in (
            "ingest-agent",
            "concept-agent",
            "judgment-agent",
            "review-agent",
            "repair-planner",
            "execution-agent",
            "nightly-agent",
        ):
            pack_path = self.root / "output" / "agents" / f"{role}.md"
            self.assertTrue(pack_path.exists(), role)
            pack_text = pack_path.read_text(encoding="utf-8")
            self.assertIn("## Mission", pack_text)
            self.assertIn("## Current Focus", pack_text)
            self.assertIn("## Suggested Actions", pack_text)
            self.assertIn("## Related Links", pack_text)

    def test_review_agent_pack_surfaces_lifecycle_governance_summary(self) -> None:
        backlog_title, retired_title = self._seed_lifecycle_governance_surface_state()

        review_pack = (self.root / "output" / "agents" / "review-agent.md").read_text(encoding="utf-8")

        self.assertIn("生命周期概念待审", review_pack)
        self.assertIn("已退役概念", review_pack)
        self.assertIn(backlog_title, review_pack)
        self.assertIn(retired_title, review_pack)

    def test_agent_workbench_surfaces_lifecycle_governance_summary(self) -> None:
        backlog_title, retired_title = self._seed_lifecycle_governance_surface_state()

        workbench = (self.root / "wiki" / "indexes" / "agent-workbench.md").read_text(encoding="utf-8")

        self.assertIn("## Lifecycle Governance Summary", workbench)
        self.assertIn("## Lifecycle Dispatch Hints", workbench)
        self.assertIn("## Lifecycle Concept Backlog", workbench)
        self.assertIn("## Retired Concepts", workbench)
        self.assertIn(backlog_title, workbench)
        self.assertIn(retired_title, workbench)

    def test_compile_generates_output_packs_for_review_memo_and_sop(self) -> None:
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
        judgment_path = self.root / judgment["path"]
        judgment_text = judgment_path.read_text(encoding="utf-8")
        judgment_frontmatter = parse_frontmatter(judgment_text)
        judgment_frontmatter["counter_evidence"] = ["Serving optimizations lowered inference cost."]
        judgment_frontmatter["invalidation_rule"] = "Invalidate if cost per token keeps falling after the next benchmark."
        judgment_frontmatter["next_signals"] = ["Watch the next latency benchmark refresh."]
        judgment_path.write_text(
            f"{render_frontmatter(judgment_frontmatter)}\n\n{strip_frontmatter(judgment_text).lstrip()}",
            encoding="utf-8",
        )
        self._seed_machine_memory_actions()
        compile_wiki(self.root)
        review_machine_memory_action(self.root, "overloaded-concept-latency", "accepted", note="Queue SOP draft.")

        packs_index = (self.root / "wiki" / "indexes" / "output-packs.md").read_text(encoding="utf-8")
        review_pack = next((self.root / "output" / "packs" / "review").glob("*.md"))
        decision_memo = next((self.root / "output" / "packs" / "decision-memos").glob("*.md"))
        sop_draft = next((self.root / "output" / "packs" / "sop-drafts").glob("*.md"))

        self.assertIn("Review Pack", packs_index)
        self.assertIn("Decision Memo", packs_index)
        self.assertIn("SOP Draft", packs_index)
        self.assertIn("Scaling Decision", review_pack.read_text(encoding="utf-8"))
        decision_memo_text = decision_memo.read_text(encoding="utf-8")
        self.assertIn("Scaling Judgment", decision_memo_text)
        self.assertIn("## Recommendation", decision_memo_text)
        self.assertIn("Serving optimizations lowered inference cost.", decision_memo_text)
        self.assertIn("Invalidate if cost per token keeps falling", decision_memo_text)
        self.assertIn("Watch the next latency benchmark refresh.", decision_memo_text)
        self.assertIn("## Version History", decision_memo_text)
        sop_text = sop_draft.read_text(encoding="utf-8")
        self.assertIn("## Step-by-Step", sop_text)
        self.assertIn("Action id:", sop_text)
        self.assertIn("apply-action", sop_text)
        self.assertIn("Pattern frequency", sop_text)
        self.assertIn("## Dry Run Preview", sop_text)
        self.assertIn("## Version History", sop_text)

    def test_output_packs_index_surfaces_lifecycle_governance_summary(self) -> None:
        backlog_title, retired_title = self._seed_lifecycle_governance_surface_state()

        packs_index = (self.root / "wiki" / "indexes" / "output-packs.md").read_text(encoding="utf-8")

        self.assertIn("Lifecycle Governance Summary", packs_index)
        self.assertIn("Lifecycle Concept Backlog", packs_index)
        self.assertIn("Retired Concepts", packs_index)
        self.assertIn(backlog_title, packs_index)
        self.assertIn(retired_title, packs_index)

    def test_compile_fallback_sop_without_bundle_stays_dry_run_only(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))
        actions = []
        for index in range(17):
            actions.append(
                {
                    "id": f"accepted-link-{index:02d}",
                    "kind": "add-source-concept-link",
                    "title": f"Accepted Link {index:02d}",
                    "reason": "Backfill stable source/concept link.",
                    "primary_path": f"wiki/sources/{entry['id']}.md",
                    "secondary_path": f"wiki/concepts/{concept_slug}.md",
                    "status": "accepted",
                    "priority": "low",
                    "active": True,
                    "source_ids": [entry["id"]],
                    "concept_slugs": [concept_slug],
                    "protocol": "investing",
                }
            )
        save_machine_memory_action_state(self.root, {"version": 1, "actions": actions})

        compile_wiki(self.root)

        sop_drafts = list((self.root / "output" / "packs" / "sop-drafts").glob("*.md"))
        self.assertGreaterEqual(len(sop_drafts), 17)
        fallback_texts = [
            path.read_text(encoding="utf-8")
            for path in sop_drafts
            if "Execution Bundle: none" in path.read_text(encoding="utf-8")
        ]
        self.assertTrue(fallback_texts)
        self.assertIn("先停在 dry-run", fallback_texts[0])
        self.assertNotIn("--bundle", fallback_texts[0])

    def test_compile_generates_domain_pilot_scorecards(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        ask_question(self.root, "Should we underwrite this thesis?", "report", protocol="investing")
        ask_question(self.root, "Latency benchmark regression after cache migration", "report", protocol="research")
        report = ask_question(self.root, "Is this launch ready for beta users?", "report", protocol="product")
        judgment = file_back(self.root, report["path"], title="Launch Readiness", kind="judgment")
        review_page(
            self.root,
            judgment["path"],
            "confirmed",
            note="Stable enough for pilot scorecard.",
            confidence="medium",
        )
        compile_wiki(self.root)

        pilots_index = (self.root / "wiki" / "indexes" / "domain-pilots.md").read_text(encoding="utf-8")
        investing_scorecard = (self.root / "output" / "pilots" / "investing.md").read_text(encoding="utf-8")
        product_scorecard = (self.root / "output" / "pilots" / "product.md").read_text(encoding="utf-8")

        self.assertIn("## 协议 Scorecards", pilots_index)
        self.assertIn("通用协议 Pilot Scorecard", pilots_index)
        self.assertIn("投资协议 Pilot Scorecard", pilots_index)
        self.assertIn("## Density Snapshot", investing_scorecard)
        self.assertIn("## Gaps", investing_scorecard)
        self.assertIn("## Next Moves", product_scorecard)
        self.assertIn("## Recent Outputs", product_scorecard)

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
        entry = ingest_source(self.root, str(sample), title="Throughput Notes")
        compile_wiki(self.root)
        set_active_protocol(self.root, "investing")
        report_markdown = "\n".join(
            [
                "---",
                'id: "query-1"',
                'kind: "output"',
                'format: "report"',
                'query: "Compare latency tail behavior"',
                'protocol: "investing"',
                'generated_by: "aiwiki-ask"',
                'created_at: "2026-04-07T00:00:00+00:00"',
                "---",
                "",
                "# Compare latency tail behavior",
                "",
                f"See `wiki/sources/{entry['id']}.md`.",
            ]
        )
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

    def test_report_includes_protocol_specific_output_guidance(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        report = ask_question(self.root, "Should we underwrite this thesis?", "report", protocol="investing")
        report_text = (self.root / report["path"]).read_text(encoding="utf-8")

        self.assertIn("## 协议输出偏置", report_text)
        self.assertIn("thesis / bull-bear evidence / catalysts / risks / invalidation", report_text)

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

    def test_compile_generates_cognitive_history_and_surfaces_citation_drift(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        review_page(
            self.root,
            decision["path"],
            "approved",
            note="Approved before the source changed.",
        )

        (self.root / entry["stored_path"]).write_text(
            "# Transformer Scaling\n\nTransformers benefit from scale.\nThe cached inference path changed the cost tradeoff.\n",
            encoding="utf-8",
        )
        compile_wiki(self.root)

        cognitive_history = (self.root / "wiki" / "indexes" / "cognitive-history.md").read_text(encoding="utf-8")
        decisions_index = (self.root / "wiki" / "indexes" / "decisions.md").read_text(encoding="utf-8")
        self.assertIn("Scaling Decision", cognitive_history)
        self.assertIn("证据漂移", cognitive_history)
        self.assertIn("Scaling Decision", decisions_index)
        self.assertIn("证据漂移", decisions_index)

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
        report = ask_question(self.root, "Compare transformer scaling tradeoffs", "report")

        result = shell_status(self.root)

        self.assertTrue(result["recent_outputs"])
        self.assertEqual(result["recent_outputs"][0]["path"], report["path"])
        self.assertTrue(result["recent_runs"])
        self.assertEqual(result["recent_runs"][0]["event_type"], "query")
        self.assertEqual(result["recent_runs"][0]["output_path"], report["path"])

    def test_shell_status_surfaces_latest_llm_run_and_llm_health(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        report_markdown = "\n".join(
            [
                "---",
                'id: "query-health"',
                'kind: "output"',
                'format: "report"',
                'query: "Check shell summary llm health"',
                'generated_by: "aiwiki-ask"',
                'created_at: "2026-04-05T00:00:00+00:00"',
                "---",
                "",
                "# Check shell summary llm health",
                "",
                f"Grounded in `wiki/sources/{entry['id']}.md`.",
            ]
        )

        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "codex-cli"}, clear=False):
            ask_result = run_ask(
                self.root,
                "Check shell summary llm health",
                "report",
                client=StubClient([report_markdown], backend="codex-cli", backend_requested="codex-cli"),
            )
            result = shell_status(self.root)

        self.assertEqual(result["latest_llm_run"]["event"], "run-ask")
        self.assertEqual(result["latest_llm_run"]["status"], "success")
        self.assertEqual(result["latest_llm_run"]["backend_requested"], "codex-cli")
        self.assertEqual(result["latest_llm_run"]["backend_effective"], "codex-cli")
        self.assertEqual(result["latest_llm_run"]["model_selected"], "stub-model")
        self.assertEqual(result["latest_llm_run"]["model_final"], "stub-model")
        self.assertTrue(result["latest_llm_run"]["contract_validated"])
        self.assertEqual(result["latest_llm_run"]["result_path"], ask_result["path"])
        self.assertEqual(result["latest_llm_run"]["receipt_path"], ".aiwiki/logs/llm-receipts.jsonl")
        self.assertEqual(result["latest_llm_run"]["log_path"], ".aiwiki/logs/runs.jsonl")
        self.assertIn("./scripts/aiwiki-launcher.sh run-ask", result["latest_llm_run"]["recovery_command"])

        self.assertEqual(result["llm_health"]["status"], "healthy")
        self.assertEqual(result["llm_health"]["backend_requested"], "codex-cli")
        self.assertEqual(result["llm_health"]["backend_effective"], "codex-cli")
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
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        report_markdown = "\n".join(
            [
                "---",
                'id: "query-drift"',
                'kind: "output"',
                'format: "report"',
                'query: "Check llm route drift"',
                'generated_by: "aiwiki-ask"',
                'created_at: "2026-04-05T00:00:00+00:00"',
                "---",
                "",
                "# Check llm route drift",
                "",
                f"Grounded in `wiki/sources/{entry['id']}.md`.",
            ]
        )

        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "codex-cli"}, clear=False):
            run_ask(
                self.root,
                "Check llm route drift",
                "report",
                client=StubClient([report_markdown], backend="codex-cli", backend_requested="codex-cli"),
            )

        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "copilot-cli"}, clear=False):
            with patch("aiwiki.config.shutil.which", side_effect=lambda name: "/usr/bin/copilot" if name == "copilot" else ""):
                result = shell_status(self.root)

        self.assertTrue(result["llm_health"]["route_drift"])
        self.assertEqual(result["llm_health"]["status"], "unknown")
        self.assertEqual(result["llm_health"]["backend"], "copilot-cli")
        self.assertEqual(result["llm_health"]["backend_effective"], "codex-cli")
        self.assertIn("Current route changed", result["llm_health"]["reason"])

    def test_shell_status_surfaces_runtime_owned_deterministic_ask_fallback_lineage(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "codex-cli"}, clear=False):
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
                        "backend_requested": "codex-cli",
                        "backend_effective": "codex-cli",
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
        self.assertIn("--fallback-to-ask", result["latest_llm_run"]["recovery_command"])

        self.assertEqual(result["llm_health"]["status"], "degraded")
        self.assertEqual(result["llm_health"]["fallback_command"], "ask")
        self.assertEqual(result["llm_health"]["result_path"], "output/reports/query-frontdoor.md")
        self.assertIn("fell back to deterministic ask", result["llm_health"]["reason"])

    def test_shell_status_marks_compile_summary_chain_fallback_as_degraded(self) -> None:
        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "codex-cli"}, clear=False):
            with patch(
                "aiwiki.app_shell.load_llm_receipt_history",
                return_value=[
                    {
                        "created_at": "2026-04-22T00:00:00+00:00",
                        "event": "run-compile-summary",
                        "status": "success",
                        "backend_requested": "codex-cli",
                        "backend_effective": "codex-cli",
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
        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "codex-cli"}, clear=False):
            with patch(
                "aiwiki.app_shell.load_llm_receipt_history",
                return_value=[
                    {
                        "created_at": "2026-04-22T00:00:00+00:00",
                        "event": "run-compile-summary",
                        "status": "success",
                        "backend_requested": "codex-cli",
                        "backend_effective": "codex-cli",
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
        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "codex-cli"}, clear=False):
            with patch(
                "aiwiki.app_shell.load_llm_receipt_history",
                return_value=[
                    {
                        "created_at": "2026-04-22T00:00:00+00:00",
                        "event": "run-lint",
                        "status": "success",
                        "backend_requested": "codex-cli",
                        "backend_effective": "codex-cli",
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
        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "codex-cli"}, clear=False):
            with patch(
                "aiwiki.app_shell.load_llm_receipt_history",
                return_value=[
                    {
                        "created_at": "2026-04-22T00:00:00+00:00",
                        "event": "run-compile",
                        "status": "success",
                        "backend_requested": "codex-cli",
                        "backend_effective": "codex-cli",
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

    def test_llm_status_requires_explicit_backend_selection(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("aiwiki.config.shutil.which") as which_mock:
                which_mock.side_effect = lambda name: "/usr/bin/codex" if name == "codex" else ""
                status = LLMConfig.status_from_env()
        self.assertFalse(status["configured"])
        self.assertEqual(status["backend"], "")
        self.assertEqual(status["available_backends"], [BACKEND_CODEX_CLI])
        self.assertIn("No LLM backend selected", str(status["message"]))

    def test_llm_config_uses_copilot_backend_when_explicitly_configured(self) -> None:
        env = {
            "AIWIKI_LLM_BACKEND": "copilot-cli",
            "AIWIKI_LLM_MODEL": "claude-haiku-4.5",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("aiwiki.config.shutil.which", side_effect=lambda name: "/usr/bin/copilot" if name == "copilot" else ""):
                config = LLMConfig.from_env()
        self.assertEqual(config.backend, BACKEND_COPILOT_CLI)
        self.assertEqual(config.model, "claude-haiku-4.5")

    def test_llm_status_marks_claude_image_analysis_as_unsupported(self) -> None:
        with patch.dict(os.environ, {"AIWIKI_LLM_BACKEND": "claude-cli"}, clear=True):
            with patch("aiwiki.config.shutil.which") as which_mock:
                which_mock.side_effect = lambda name: "/usr/bin/claude" if name == "claude" else ""
                status = LLMConfig.status_from_env()
        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], "claude-cli")
        self.assertFalse(status["image_analysis_supported"])

    def test_auto_once_processes_raw_inbox_without_manual_ingest(self) -> None:
        dropped = self.root / "raw" / "inbox" / "dropped.md"
        dropped.write_text("# Dropped\n\nA dropped source should be auto-compiled.\n", encoding="utf-8")
        result = auto_process_once(self.root, deterministic_only=True, semantic_lint=False)
        manifest = load_manifest(self.root)
        self.assertEqual(len(manifest["entries"]), 1)
        self.assertFalse(result["llm_used"])
        entry_id = manifest["entries"][0]["id"]
        self.assertTrue((self.root / "wiki" / "sources" / f"{entry_id}.md").exists())
        self.assertTrue((self.root / ".aiwiki" / "state" / "automation.json").exists())

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

    def test_run_watch_script_uses_root_relative_paths(self) -> None:
        script = Path("/home/tim/ai-wiki/scripts/run_watch.sh")
        content = script.read_text(encoding="utf-8")
        self.assertIn('PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"', content)
        self.assertIn('TARGET_ROOT="${AIWIKI_VAULT:-$PROJECT_ROOT}"', content)
        self.assertIn('export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"', content)
        self.assertIn('--root "$TARGET_ROOT"', content)
        self.assertIn('AIWIKI_WATCH_DETERMINISTIC_ONLY:-1', content)
        self.assertIn('exec python3 -m aiwiki.cli "${ARGS[@]}"', content)

    def test_run_nightly_script_uses_root_relative_paths(self) -> None:
        script = Path("/home/tim/ai-wiki/scripts/run_nightly.sh")
        content = script.read_text(encoding="utf-8")
        self.assertIn('PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"', content)
        self.assertIn('TARGET_ROOT="${AIWIKI_VAULT:-$PROJECT_ROOT}"', content)
        self.assertIn('export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"', content)
        self.assertIn('--root "$TARGET_ROOT"', content)
        self.assertIn('exec python3 -m aiwiki.cli "${ARGS[@]}"', content)
        self.assertIn("run-nightly", content)
        self.assertIn("nightly", content)
        self.assertIn("AIWIKI_NIGHTLY_FALLBACK_BACKEND:-nvidia-nim-api", content)
        self.assertIn("AIWIKI_NIGHTLY_FALLBACK_MODEL:-openai/gpt-oss-120b", content)
        self.assertIn("source \"$FALLBACK_ENV\"", content)
        self.assertIn("retrying nightly with fallback", content)

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

    def test_aiwiki_launcher_script_uses_env_vault_when_present(self) -> None:
        script = Path("/home/tim/ai-wiki/scripts/aiwiki-launcher.sh")
        content = script.read_text(encoding="utf-8")
        self.assertTrue(os.access(script, os.X_OK))
        self.assertIn('PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"', content)
        self.assertIn('TARGET_ROOT="${AIWIKI_VAULT:-$PROJECT_ROOT}"', content)
        self.assertIn('PLUGIN_DATA="$TARGET_ROOT/.obsidian/plugins/furnace-product-shell/data.json"', content)
        self.assertIn('export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"', content)
        self.assertIn('exec python3 -m aiwiki.cli --root "$TARGET_ROOT" "$@"', content)

    def test_install_user_service_defaults_watcher_to_deterministic_only(self) -> None:
        script = Path("/home/tim/ai-wiki/scripts/install_user_service.sh")
        content = script.read_text(encoding="utf-8")
        self.assertIn("AIWIKI_WATCH_DETERMINISTIC_ONLY=1", content)
        self.assertIn("AIWIKI_NIGHTLY_DETERMINISTIC_ONLY=0", content)
        self.assertIn("AIWIKI_NIGHTLY_FALLBACK_ENABLED=1", content)
        self.assertIn("AIWIKI_NIGHTLY_FALLBACK_BACKEND=nvidia-nim-api", content)
        self.assertIn("AIWIKI_NIGHTLY_FALLBACK_MODEL=openai/gpt-oss-120b", content)

    def test_product_shell_plugin_manifest_declares_desktop_only(self) -> None:
        manifest_path = Path("/home/tim/ai-wiki/.obsidian/plugins/furnace-product-shell/manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "furnace-product-shell")
        self.assertEqual(manifest["name"], "Furnace Product Shell")
        self.assertTrue(manifest["isDesktopOnly"])
        self.assertGreaterEqual(str(manifest["minAppVersion"]), "1.8.0")

    def test_product_shell_plugin_main_js_passes_node_syntax_check(self) -> None:
        plugin_path = Path("/home/tim/ai-wiki/.obsidian/plugins/furnace-product-shell/main.js")
        result = subprocess.run(
            ["node", "--check", str(plugin_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

    def test_product_shell_plugin_scaffold_declares_p0_views_and_commands(self) -> None:
        plugin_path = Path("/home/tim/ai-wiki/.obsidian/plugins/furnace-product-shell/main.js")
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
        self.assertIn('id: "run-compile"', content)
        self.assertIn('id: "run-ask"', content)
        self.assertIn('id: "search-workspace"', content)
        self.assertIn('id: "run-nightly"', content)
        self.assertIn('id: "set-protocol"', content)
        self.assertIn('id: "open-home-note"', content)
        self.assertIn('id: "file-back"', content)
        self.assertIn('id: "review-page"', content)
        self.assertIn('id: "review-next-page"', content)
        self.assertIn('id: "batch-review-pages"', content)
        self.assertIn('id: "review-rewrite"', content)
        self.assertIn('id: "apply-rewrite"', content)
        self.assertIn('id: "retire-concept"', content)
        self.assertIn('id: "reactivate-concept"', content)
        self.assertIn('id: "apply-archive"', content)
        self.assertIn('id: "revert-archive"', content)
        self.assertIn('id: "review-action"', content)
        self.assertIn('id: "apply-action"', content)
        self.assertIn('id: "revert-action"', content)
        self.assertIn('id: "apply-all-accepted-low-risk"', content)
        self.assertIn('id: "revert-last-action-batch"', content)
        self.assertIn('renderReviewCenter(this.contentEl);', content)
        self.assertIn('renderExecutionCenter(this.contentEl);', content)

    def test_product_shell_plugin_supports_external_runtime_launcher_mode(self) -> None:
        plugin_path = Path("/home/tim/ai-wiki/.obsidian/plugins/furnace-product-shell/main.js")
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
        self.assertIn("this.runPluginCommand(label, [command, ...args], { refreshAfter: true });", content)
        self.assertIn('const DEFAULT_LOCALE = "zh";', content)
        self.assertIn('locale: DEFAULT_LOCALE', content)
        self.assertIn('label: "Review Page"', content)
        self.assertIn('label: "Review Next"', content)
        self.assertIn('label: "Batch Review"', content)
        self.assertIn('label: "File Back"', content)
        self.assertIn('label: "Review Action"', content)
        self.assertIn('label: "Apply Archive"', content)
        self.assertIn('.t("Re-review")', content)
        self.assertIn('Manual review...', content)
        self.assertIn('.t("Review")', content)
        self.assertIn('.t("Review action")', content)
        self.assertIn('.t(archiveControl.can_revert ? "Revert archive" : "Apply archive")', content)
        self.assertIn('.t(actionControl.can_revert ? "Revert action" : "Apply action")', content)
        self.assertIn('.t(String(entry.lifecycle_state || "") === "retired" ? "Reactivate concept" : "Retire concept")', content)
        self.assertIn("Judgment Focus", content)
        self.assertIn("Judgment Assets", content)
        self.assertIn("Next Review", content)
        self.assertIn("Batch Suggestions", content)
        self.assertIn("Decision Objects", content)
        self.assertIn("Judgment Objects", content)
        self.assertIn("Rewrite Proposal Objects", content)
        self.assertIn("Action Control Objects", content)
        self.assertIn("runReviewPageBatchTransition(pagePaths, status, note = \"\", confidence = \"\")", content)
        self.assertIn('this.t("Pick Review Transition")', content)
        self.assertIn('this.t("Pick Batch Review")', content)
        self.assertIn('this.t("Pick Rewrite Transition")', content)
        self.assertIn('this.t("Pick Action Transition")', content)
        self.assertIn('emptyNotice: this.t("No visible review backlog item is available; fell back to the manual form.")', content)
        self.assertIn('emptyNotice: this.t("No visible machine-memory action context is available; fell back to the manual form.")', content)
        self.assertIn('output/control/shell-summary.json', content)
        self.assertIn('review_controls', content)
        self.assertIn('reviewControlList("decision_pages")', content)
        self.assertIn('reviewControlList("judgment_pages")', content)
        self.assertIn('["judgment_assets_markdown", "Judgment Assets"]', content)
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
        app_shim = Path("/home/tim/ai-wiki/src/aiwiki/app.py").read_text(encoding="utf-8")
        self.assertNotIn("_sync_facade_bindings", app_shim)
        self.assertIn("transition_profile = _app_content.transition_profile", app_shim)
        self.assertIn("curated_page_transition_profile = _app_content.curated_page_transition_profile", app_shim)
        self.assertIn("rewrite_transition_profile = _app_content.rewrite_transition_profile", app_shim)
        self.assertIn("action_transition_profile = _app_content.action_transition_profile", app_shim)
        self.assertIn("archive_transition_profile = _app_content.archive_transition_profile", app_shim)
        self.assertIn("shell_review_controls = _app_shell.shell_review_controls", app_shim)
        self.assertIn("shell_action_control_objects = _app_shell.shell_action_control_objects", app_shim)
        self.assertIn("shell_archive_control_objects = _app_shell.shell_archive_control_objects", app_shim)
        self.assertIn("shell_execution_controls = _app_shell.shell_execution_controls", app_shim)
    def test_cli_shell_status_command_outputs_summary_json(self) -> None:
        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(cli_main(["--root", str(self.root), "shell-status"]), 0)
            payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["contract_version"], 1)
        self.assertEqual(payload["summary_path"], "output/control/shell-summary.json")

    def test_user_service_install_script_mentions_nightly_timer(self) -> None:
        script = Path("/home/tim/ai-wiki/scripts/install_user_service.sh")
        content = script.read_text(encoding="utf-8")
        self.assertIn("aiwiki-nightly.service", content)
        self.assertIn("aiwiki-nightly.timer", content)
        self.assertIn("AIWIKI_NIGHTLY_COMPILE_LIMIT", content)
        self.assertIn("AIWIKI_LLM_MODEL=gpt-5.5", content)
        self.assertIn("AIWIKI_NIGHTLY_FALLBACK_ENV", content)
        self.assertIn("ensure_env_key", content)

    def test_nightly_systemd_templates_exist(self) -> None:
        service_template = Path("/home/tim/ai-wiki/systemd/aiwiki-nightly.service.template")
        timer_template = Path("/home/tim/ai-wiki/systemd/aiwiki-nightly.timer.template")
        self.assertTrue(service_template.exists())
        self.assertTrue(timer_template.exists())
        self.assertIn("ExecStart=__PROJECT_ROOT__/scripts/run_nightly.sh", service_template.read_text(encoding="utf-8"))
        self.assertIn("OnCalendar=__ON_CALENDAR__", timer_template.read_text(encoding="utf-8"))

    def test_compile_persists_component_health_metadata(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        second = self.root / "tail.md"
        second.write_text("# Tail Latency\n\nLatency throughput jitter tradeoffs.\n", encoding="utf-8")
        ingest_source(self.root, str(second), title="Tail Latency")

        compile_wiki(self.root)

        memory = json.loads((self.root / ".aiwiki" / "state" / "machine-memory.json").read_text(encoding="utf-8"))
        health = memory["health"]
        self.assertIn("components", health)
        self.assertTrue(health["components"])
        self.assertIn("source_component_ids", health)
        self.assertIn("concept_component_ids", health)
        self.assertIn("hub_concepts", health)
        self.assertIn("hub_sources", health)
        self.assertIn("link_suggestions", health)
        self.assertIn("actions", health)
        self.assertIn("action_counts", health)

    def test_compile_generates_machine_memory_topology_page(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        second = self.root / "tail.md"
        second.write_text("# Tail Latency\n\nLatency throughput jitter tradeoffs.\n", encoding="utf-8")
        ingest_source(self.root, str(second), title="Tail Latency")

        compile_wiki(self.root)

        topology_page = self.root / "wiki" / "indexes" / "machine-memory-topology.md"
        self.assertTrue(topology_page.exists())
        topology_text = topology_page.read_text(encoding="utf-8")
        self.assertIn("## Hub 概念", topology_text)
        self.assertIn("## Hub 来源", topology_text)
        self.assertIn("## Mermaid 拓扑切片", topology_text)
        self.assertIn("```mermaid", topology_text)

    def test_compile_generates_machine_memory_actions_page(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        second = self.root / "tail.md"
        second.write_text("# Tail Latency\n\nLatency throughput jitter tradeoffs.\n", encoding="utf-8")
        ingest_source(self.root, str(second), title="Tail Latency")

        compile_wiki(self.root)

        actions_page = self.root / "wiki" / "indexes" / "machine-memory-actions.md"
        self.assertTrue(actions_page.exists())
        actions_text = actions_page.read_text(encoding="utf-8")
        self.assertIn("## 优先队列", actions_text)
        self.assertIn("## 补链动作", actions_text)
        self.assertIn("## 相关链接", actions_text)

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

    def test_compile_generates_machine_memory_repair_plan_page(self) -> None:
        self._seed_machine_memory_actions()

        compile_wiki(self.root)

        repair_plan = self.root / "wiki" / "indexes" / "machine-memory-repair-plan.md"
        self.assertTrue(repair_plan.exists())
        repair_text = repair_plan.read_text(encoding="utf-8")
        self.assertIn("## Need Triage", repair_text)
        self.assertIn("## Execution Batches", repair_text)
        self.assertIn("## Execution Proposals", repair_text)
        self.assertIn("## Page-Level Patch Plans", repair_text)
        self.assertIn("review-action overloaded-concept-latency --status accepted", repair_text)

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

    def test_compile_writes_execution_bundle_json(self) -> None:
        self._seed_machine_memory_actions()

        compile_wiki(self.root)

        memory = load_machine_memory(self.root)
        proposal = memory["health"]["repair_plan"]["execution_proposals"][0]
        bundle_path = self.root / proposal["bundle_path"]
        self.assertTrue(bundle_path.exists())
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        self.assertEqual(bundle["kind"], "execution-bundle")
        self.assertEqual(bundle["action_id"], proposal["action_id"])
        self.assertEqual(bundle["bundle_path"], proposal["bundle_path"])
        self.assertTrue(bundle["page_patch_plan"])

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

    def test_compile_generates_concept_quality_page(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")

        compile_wiki(self.root)

        concept_quality = self.root / "wiki" / "indexes" / "concept-quality.md"
        self.assertTrue(concept_quality.exists())
        quality_text = concept_quality.read_text(encoding="utf-8")
        self.assertIn("## Rewrite Now", quality_text)
        self.assertIn("## Quality Distribution", quality_text)
        self.assertIn("## Rewrite Priority", quality_text)
        self.assertIn("## Conflict Signals", quality_text)
        self.assertIn("## Evidence Gaps", quality_text)
        self.assertIn("## Merge Candidates", quality_text)
        self.assertIn("平均质量分", quality_text)

    def test_compile_surfaces_concept_conflict_signals(self) -> None:
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

        memory = load_machine_memory(self.root)
        self.assertGreaterEqual(memory["health"]["concept_quality"]["counts"]["conflict_signals"], 1)
        quality_text = (self.root / "wiki" / "indexes" / "concept-quality.md").read_text(encoding="utf-8")
        self.assertIn("increase-vs-decrease", quality_text)

        concept_pages = list((self.root / "wiki" / "concepts").glob("*.md"))
        matching_pages = [page for page in concept_pages if "increase-vs-decrease" in page.read_text(encoding="utf-8")]
        self.assertTrue(matching_pages)
        concept_text = matching_pages[0].read_text(encoding="utf-8")
        self.assertIn("## Conflict Signals", concept_text)
        self.assertIn("## Evidence Gaps", concept_text)

    def test_compile_surfaces_concept_quality_metrics_and_scores(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        source_page = next((self.root / "wiki" / "sources").glob("*.md"))
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                "- Transformer scale improves capability and raises compute demand.",
            ),
            encoding="utf-8",
        )
        compile_wiki(self.root)

        memory = load_machine_memory(self.root)
        record = memory["health"]["concept_quality"]["all_concepts"][0]
        self.assertIn("quality_score", record)
        self.assertIn("quality_band", record)
        self.assertIn("quality_metrics", record)
        self.assertIn("source_coverage", record["quality_metrics"])
        self.assertIn("consistency", record["quality_metrics"])
        self.assertIn("evidence_depth", record["quality_metrics"])
        self.assertIn("recency", record["quality_metrics"])

    def test_compile_generates_judgment_assets_page(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")

        compile_wiki(self.root)

        judgment_assets = self.root / "wiki" / "indexes" / "judgment-assets.md"
        self.assertTrue(judgment_assets.exists())
        judgment_assets_text = judgment_assets.read_text(encoding="utf-8")
        self.assertIn("## 强判断资产", judgment_assets_text)
        self.assertIn("## 缺 Counter Evidence", judgment_assets_text)
        self.assertIn("Scaling Decision", judgment_assets_text)
        self.assertIn("Scaling Judgment", judgment_assets_text)

    def test_compile_persists_machine_memory_action_lifecycle_state(self) -> None:
        self._seed_machine_memory_actions()

        compile_wiki(self.root)
        state_path = self.root / ".aiwiki" / "state" / "machine-memory-actions.json"
        first_state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertTrue(first_state["actions"])
        overloaded = next(action for action in first_state["actions"] if action["id"] == "overloaded-concept-latency")
        self.assertEqual(overloaded["status"], "proposed")
        self.assertEqual(overloaded["occurrences"], 1)
        self.assertTrue(overloaded["active"])

        compile_wiki(self.root)
        second_state = json.loads(state_path.read_text(encoding="utf-8"))
        overloaded = next(action for action in second_state["actions"] if action["id"] == "overloaded-concept-latency")
        self.assertEqual(overloaded["occurrences"], 2)
        self.assertEqual(overloaded["pending_review"], "true")

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

    def test_compile_marks_disappeared_machine_memory_action_inactive(self) -> None:
        self._seed_machine_memory_actions()
        compile_wiki(self.root)

        manifest = load_manifest(self.root)
        target_entry = next(entry for entry in manifest["entries"] if entry["title"] == "Latency Node 3")
        source = self.root / target_entry["stored_path"]
        source.write_text(
            "---\n"
            'title: "Different Topic"\n'
            "---\n\n"
            "# Different Topic\n\n"
            "Completely unrelated material.\n",
            encoding="utf-8",
        )
        compile_wiki(self.root)

        state = json.loads((self.root / ".aiwiki" / "state" / "machine-memory-actions.json").read_text(encoding="utf-8"))
        action = next(action for action in state["actions"] if action["id"] == "overloaded-concept-latency")
        self.assertFalse(action["active"])
        self.assertTrue(action["inactive_since"])

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
                fetched = _fetch_url("https://example.com/post")
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
                fetched = _fetch_url("https://example.com/app")
        self.assertEqual(fetched["status"], "browser-rendered")
        self.assertEqual(fetched["content_type"], "text/html")
        self.assertIn("Rendered after client-side app boot.", fetched["text"])

    def test_drop_pdf_creates_asset_and_note(self) -> None:
        pdf_path = self.root / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%stub\n")
        with patch("aiwiki.drop._extract_pdf_text", return_value="Extracted PDF text"):
            result = drop_pdf(self.root, str(pdf_path), title="Paper")
        self.assertTrue((self.root / result["asset_path"]).exists())
        note_text = (self.root / result["note_path"]).read_text(encoding="utf-8")
        self.assertIn("Extracted PDF text", note_text)

    def test_drop_image_creates_asset_and_metadata_note(self) -> None:
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
        note_text = (self.root / result["note_path"]).read_text(encoding="utf-8")
        self.assertIn("Dimensions: `1x1`", note_text)
        self.assertIn("Visual Analysis", note_text)
        self.assertIn("A tiny single-pixel image.", note_text)
        self.assertTrue(result["visual_analysis_present"])
        self.assertEqual(result["vision_backend"], "codex-cli")
        self.assertEqual(result["vision_status"], "generated")

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
        note_text = (self.root / result["note_path"]).read_text(encoding="utf-8")
        self.assertFalse(result["visual_analysis_present"])
        self.assertEqual(result["vision_backend"], "codex-cli")
        self.assertEqual(result["vision_status"], "failed")
        self.assertIn("Vision status: `failed`", note_text)

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

    def test_compile_generates_interactive_machine_memory_graph_html(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        payload = (self.root / "output" / "graph" / "machine-memory.html").read_text(encoding="utf-8")
        self.assertIn("graph-search", payload)
        self.assertIn("graph-protocol", payload)
        self.assertIn("graph-node-browser", payload)
        self.assertIn("graphUiData", payload)
        self.assertIn("节点详情", payload)
        self.assertIn("关系组", payload)
        self.assertIn("核心概念", payload)
        self.assertIn("输入标题、关键词或来源编号", payload)
        self.assertIn('option value="judgment"', payload)
        self.assertIn('<option value="source">来源</option>', payload)
        self.assertIn("材料提到概念", payload)
        self.assertIn("材料支撑判断", payload)
        self.assertIn("概念相关", payload)
        self.assertIn("相关关系", payload)
        self.assertNotIn("输入标题、slug、来源 id", payload)
        self.assertNotIn("Hub 概念", payload)
        self.assertNotIn("Graph View Dashboard", payload)
        self.assertNotIn("related edge", payload)
        self.assertIn("graph-zoom-in", payload)
        self.assertIn("graph-focus-node", payload)
        self.assertIn("graph-reset-view", payload)
        self.assertIn("graph-viewport", payload)
        self.assertIn("setActiveNode", payload)
        self.assertIn("材料 A 支撑判断 J", payload)
        self.assertIn("relation-node-link", payload)
        self.assertIn("otherNodeId", payload)
        self.assertIn(".legend span { flex: 1 1 140px", payload)

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
                {"id": "concept:alpha", "kind": "concept", "title": "Alpha", "source_pages": []},
                {"id": "concept:beta", "kind": "concept", "title": "Beta", "source_pages": []},
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
            self.assertRegex(str(anchor), r"^(source|concept|judgment):")

        # Body section provides a chinese link back to the graph and lists each anchor.
        self.assertIn("## 关系图谱锚点", text)
        self.assertIn("output/graph/machine-memory.html", text)
        for anchor in anchors:
            self.assertIn(f"`{anchor}`", text)

    def test_compile_graph_html_lists_referencing_reports_for_anchored_nodes(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        result = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        # Re-run compile so the graph HTML picks up the anchor-bearing report.
        compile_wiki(self.root)

        payload = (self.root / "output" / "graph" / "machine-memory.html").read_text(encoding="utf-8")
        self.assertIn("引用此节点的报告", payload)
        self.assertIn("referenced_by", payload)
        # The report path should be embedded in the JSON payload that drives detail rendering.
        self.assertIn(result["path"], payload)

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
                {"id": "concept:alpha", "kind": "concept", "title": "Alpha", "source_pages": []},
                {"id": "concept:beta", "kind": "concept", "title": "Beta", "source_pages": []},
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
        # NOT pass merely because raw edge types leak through SVG
        # `data-relation-type` attributes. Extract the panel body and check both
        # raw edge types appear there as <code class="relation-machine-type">.
        marker = '<h2>关系说明</h2>'
        panel_start = payload.find(marker)
        self.assertGreater(panel_start, -1, "关系说明 panel missing")
        panel_end = payload.find('</section>', panel_start)
        panel_body = payload[panel_start:panel_end]
        self.assertIn(
            '<code class="relation-machine-type">JUDGMENT_NEW_FOO</code>',
            panel_body,
            "summary panel must key by edge_type, not chinese label",
        )
        self.assertIn(
            '<code class="relation-machine-type">JUDGMENT_NEW_BAR</code>',
            panel_body,
            "summary panel must key by edge_type, not chinese label",
        )
        # Both still render as 判断关系 in chinese, but via two list rows.
        self.assertGreaterEqual(panel_body.count("判断关系"), 2)
        # Each row counts a single edge, so the two unknown types must not be
        # silently merged into one row even though they share the chinese label.
        self.assertGreaterEqual(panel_body.count("1 条"), 2)

    def test_compile_attaches_judgment_assets_to_machine_memory_graph(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")

        review_page(
            self.root,
            judgment["path"],
            "confirmed",
            note="Judgment captured into the runtime graph.",
            confidence="high",
        )

        memory = load_machine_memory(self.root)
        judgment_node = next(node for node in memory["judgment_nodes"] if node["path"] == judgment["path"])
        judgment_frontmatter = parse_frontmatter((self.root / judgment["path"]).read_text(encoding="utf-8"))
        self.assertEqual(judgment_node["page_id"], judgment_frontmatter["id"])
        self.assertIn(entry["id"], judgment_node["source_ids"])
        self.assertTrue(
            any(
                edge["source_id"] == entry["id"] and edge["page_id"] == judgment_node["page_id"]
                for edge in memory["edges"]["source_to_judgment"]
            )
        )

        payload = (self.root / "output" / "graph" / "machine-memory.html").read_text(encoding="utf-8")
        self.assertIn("Scaling Judgment", payload)
        self.assertIn("判断 \u00b7 已确认", payload)
        self.assertIn("协议", payload)
        self.assertIn("材料支撑判断", payload)

    def test_compile_surfaces_judgment_relations_across_memory_and_history(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        primary_judgment = file_back(self.root, report["path"], title="Primary Judgment", kind="judgment")
        linked_judgment = file_back(self.root, report["path"], title="Linked Judgment", kind="judgment")
        decision = file_back(self.root, report["path"], title="Primary Decision", kind="decision")

        for page_path, updates in (
            (primary_judgment["path"], {"related_judgments": [linked_judgment["path"]]}),
            (linked_judgment["path"], {"contradicts": [primary_judgment["path"]]}),
            (decision["path"], {"supports": [primary_judgment["path"]]}),
        ):
            target = self.root / page_path
            content = target.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter(content)
            frontmatter.update(updates)
            target.write_text(
                f"{render_frontmatter(frontmatter)}\n\n{strip_frontmatter(content).lstrip()}",
                encoding="utf-8",
            )

        compile_wiki(self.root)

        memory = load_machine_memory(self.root)
        self.assertGreaterEqual(len(memory["edges"]["judgment_to_judgment"]), 2)
        self.assertGreaterEqual(len(memory["edges"]["judgment_to_decision"]), 1)
        self.assertTrue(any(edge["relation"] == "supports" for edge in memory["edges"]["judgment_to_decision"]))

        graph = json.loads((self.root / ".aiwiki" / "cache" / "machine-memory-graph.json").read_text(encoding="utf-8"))
        relation_edge_types = {
            edge["type"]
            for edge in graph["edges"]
            if edge["source"].startswith("judgment:") and edge["target"].startswith("judgment:")
        }
        self.assertTrue(any(edge_type.startswith("JUDGMENT_") for edge_type in relation_edge_types))
        self.assertTrue(any(edge_type.startswith("DECISION_") for edge_type in relation_edge_types))

        judgment_assets = (self.root / "wiki" / "indexes" / "judgment-assets.md").read_text(encoding="utf-8")
        topology = (self.root / "wiki" / "indexes" / "machine-memory-topology.md").read_text(encoding="utf-8")
        cognitive_history = (self.root / "wiki" / "indexes" / "cognitive-history.md").read_text(encoding="utf-8")
        self.assertIn("## Judgment 关联图谱", judgment_assets)
        self.assertIn("Primary Decision", judgment_assets)
        self.assertIn("supports ->", judgment_assets)
        graph_html = (self.root / "output" / "graph" / "machine-memory.html").read_text(encoding="utf-8")
        self.assertIn("判断冲突", graph_html)
        self.assertIn("决策依据", graph_html)
        self.assertIn("## Judgment Hub", topology)
        self.assertIn("## Judgment 关系事件", cognitive_history)
        self.assertIn("Primary Judgment", cognitive_history)

    def test_compile_generates_autogenerated_figures_and_slides(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        figures = sorted(path.name for path in (self.root / "output" / "figures").glob("*.md"))
        slides = sorted(path.name for path in (self.root / "output" / "slides").glob("*.md"))
        self.assertIn("judgment-relation-map.md", figures)
        self.assertIn("governance-health-dashboard.md", figures)
        self.assertIn("furnace-governance-status.md", slides)
        self.assertIn("furnace-output-density.md", slides)

        relation_figure = (self.root / "output" / "figures" / "judgment-relation-map.md").read_text(encoding="utf-8")
        status_slides = (self.root / "output" / "slides" / "furnace-governance-status.md").read_text(encoding="utf-8")
        self.assertIn("Judgment Relation Map", relation_figure)
        self.assertIn('format: "figure"', relation_figure)
        self.assertIn("marp: true", status_slides)
        self.assertIn("Furnace Governance Status", status_slides)

    def test_compile_escapes_script_sensitive_text_in_machine_memory_graph_html(self) -> None:
        scripted = self.root / "scripted.md"
        scripted.write_text("# Scripted Source\n\nGraph payload should stay safe.\n", encoding="utf-8")
        ingest_source(self.root, str(scripted), title="Bad </script> \u2028 title")

        compile_wiki(self.root)

        payload = (self.root / "output" / "graph" / "machine-memory.html").read_text(encoding="utf-8")
        self.assertIn("\\u003c/script\\u003e", payload)
        self.assertIn("\\u2028", payload)
        self.assertNotIn("Bad </script> \u2028 title", payload)

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

    def test_compile_detects_isolated_sources(self) -> None:
        """compile should detect sources not connected to any concept."""
        from aiwiki.app_memory import build_machine_memory_health

        # Ingest a single source with minimal content unlikely to produce concept terms
        isolated = self.root / "isolated_source.md"
        isolated.write_text("---\ntitle: xyz\n---\nxyz", encoding="utf-8")
        ingest_source(self.root, str(isolated), title="xyz")
        compile_wiki(self.root)

        memory = load_machine_memory(self.root)
        health = build_machine_memory_health(memory)
        # Health should have at least the isolated source detection fields
        self.assertIn("isolated_source_ids", health)
        self.assertIsInstance(health["isolated_source_ids"], list)

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


if __name__ == "__main__":
    unittest.main()
