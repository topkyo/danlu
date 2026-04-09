from __future__ import annotations

import base64
from datetime import datetime
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app import (
    active_corpus_bridge_evidence_ids,
    append_execution_receipt_history,
    apply_concept_rewrite,
    apply_material_archive,
    apply_machine_memory_action,
    ask_question,
    build_archive_candidate_state,
    build_machine_memory_query,
    collect_machine_memory_actions,
    compile_wiki,
    ensure_layout,
    file_back,
    ingest_source,
    lint_wiki,
    load_archive_candidates_state,
    load_knowledge_lifecycle_state,
    load_knowledge_lifecycle_override_state,
    load_machine_memory,
    load_machine_memory_action_state,
    load_manifest,
    load_material_routing_state,
    load_material_state,
    load_protocol_state,
    nightly_health,
    parse_frontmatter,
    placeholder_concept_slugs,
    render_frontmatter,
    reactivate_concept,
    revert_material_archive,
    revert_machine_memory_action,
    review_concept_rewrite,
    review_machine_memory_action,
    review_page,
    runtime_write_lock,
    rank_concepts,
    rank_sources,
    retire_concept,
    save_manifest,
    save_material_routing_state,
    save_material_state,
    save_machine_memory_action_state,
    set_active_protocol,
    strip_frontmatter,
)
from aiwiki.config import BACKEND_CODEX_CLI, BACKEND_OPENAI_API, LLMConfig
from aiwiki.cli import main as cli_main
from aiwiki.drop import _fetch_url, drop_image, drop_pdf, drop_repo, drop_url
from aiwiki.llm import CompletionResult
from aiwiki.runner import auto_process_once, run_ask, run_compile, run_lint, run_nightly, watch_inbox


class StubClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.config = type("Config", (), {"model": "stub-model"})()

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

    def _prepare_ready_archive_candidate(self) -> dict[str, str]:
        archive_source = self.root / "archive-candidate.md"
        archive_source.write_text("# Obscure Legacy Note\n\nMisc.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(archive_source), title="Obscure Legacy Note")
        compile_wiki(self.root)
        manifest = load_manifest(self.root)
        manifest["entries"][0]["imported_at"] = "2025-01-01T00:00:00+00:00"
        manifest["entries"][0]["updated_at"] = "2025-01-01T00:00:00+00:00"
        save_manifest(self.root, manifest)
        set_active_protocol(self.root, "investing")
        compile_wiki(self.root)
        compile_wiki(self.root)
        return entry

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
        concept_page.write_text(
            concept_page.read_text(encoding="utf-8").replace(
                "- This concept currently appears in `1` source page(s).",
                "- OLD CONCEPT SUMMARY",
            ),
            encoding="utf-8",
        )
        stored_source = self.root / entry["stored_path"]
        stored_source.write_text(
            "# Transformer Scaling\n\nLatency throughput cache locality.\n",
            encoding="utf-8",
        )

        compile_wiki(self.root)

        refreshed = concept_page.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(refreshed)
        self.assertNotIn("OLD CONCEPT SUMMARY", refreshed)
        self.assertIn("This concept currently appears", refreshed)
        self.assertTrue(frontmatter["source_signature"])

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
        self.assertIn("推荐概念", report_text)
        self.assertIn("推荐索引页", report_text)
        self.assertIn("机器记忆", report_text)
        self.assertIn("漂移报告", report_text)
        self.assertIn("决策索引", report_text)
        self.assertIn("判断索引", report_text)
        self.assertIn("审阅中心", report_text)
        self.assertIn("图谱视图", report_text)
        self.assertIn("运行时规则", report_text)

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
        self.assertIn("Compare transformer scale and inference cost", dashboard_payload)
        self.assertIn("Furnace Center", html_payload)
        self.assertIn("../../wiki/indexes/furnace-center.md", html_payload)
        self.assertIn("Compare transformer scale and inference cost", html_payload)

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

    def test_compile_writes_machine_memory_graph_html(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        graph_html = self.root / "output" / "graph" / "machine-memory.html"
        payload = graph_html.read_text(encoding="utf-8")
        self.assertTrue(graph_html.exists())
        self.assertIn("Machine Memory Graph", payload)
        self.assertIn("<svg", payload)
        self.assertIn("Transformer Scaling", payload)
        self.assertIn("../../wiki/indexes/graph-view.md", payload)

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
        self.assertIn("机器记忆查询计划", report_text)
        self.assertIn("桥接概念", report_text)
        self.assertIn("查询路径数", report_text)
        self.assertIn("触达分量", report_text)
        self.assertIn("latency", report_text.lower())

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
        self.assertIn("Transformers benefit from scale", source_page.read_text(encoding="utf-8"))

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
        target_slug = placeholder_concept_slugs(self.root)[0]
        concept_page = self.root / "wiki" / "concepts" / f"{target_slug}.md"
        current = concept_page.read_text(encoding="utf-8")
        updated = current.replace("- This concept currently appears", "- Enriched concept synthesis appears")

        result = run_compile(self.root, client=StubClient([updated]), limit=1)

        self.assertEqual(result["pending_pages"], 0)
        self.assertEqual(result["pending_concept_pages"], 5)
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

        for concept_page in sorted((self.root / "wiki" / "concepts").glob("*.md")):
            concept_page.write_text(
                concept_page.read_text(encoding="utf-8").replace(
                    "- This concept currently appears",
                    f"- Existing synthesis for {concept_page.stem} appears",
                ),
                encoding="utf-8",
            )
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

        for concept_page in sorted((self.root / "wiki" / "concepts").glob("*.md")):
            concept_page.write_text(
                concept_page.read_text(encoding="utf-8").replace(
                    "- This concept currently appears",
                    f"- Existing synthesis for {concept_page.stem} appears",
                ),
                encoding="utf-8",
            )
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
        refreshed = concept_page.read_text(encoding="utf-8")
        self.assertIn("Rewritten synthesis", refreshed)
        proposal_text = proposal_path.read_text(encoding="utf-8")
        self.assertIn("已应用", proposal_text)

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

        for concept_page in sorted((self.root / "wiki" / "concepts").glob("*.md")):
            concept_page.write_text(
                concept_page.read_text(encoding="utf-8").replace(
                    "- This concept currently appears",
                    f"- Existing synthesis for {concept_page.stem} appears",
                ),
                encoding="utf-8",
            )
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

    def test_apply_machine_memory_action_writes_manual_link_state(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
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
        bundle_path = self.root / dry_run["bundle_path"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle = dry_run["bundle"]
        bundle["summary"] = "tampered stale bundle"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        with self.assertRaises(RuntimeError):
            apply_machine_memory_action(
                self.root,
                "manual-link-action",
                note="Should fail with stale bundle.",
                bundle_path=dry_run["bundle_path"],
            )

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
        self.assertEqual(parse_frontmatter(decision_path.read_text(encoding="utf-8"))["kind"], "decision")
        self.assertEqual(parse_frontmatter(judgment_path.read_text(encoding="utf-8"))["kind"], "judgment")
        self.assertEqual(parse_frontmatter(decision_path.read_text(encoding="utf-8"))["status"], "proposed")
        self.assertEqual(parse_frontmatter(judgment_path.read_text(encoding="utf-8"))["status"], "tentative")
        self.assertIn(f"wiki/sources/{entry['id']}.md", parse_frontmatter(decision_path.read_text(encoding="utf-8"))["citations"])
        self.assertIn(f"wiki/sources/{entry['id']}.md", parse_frontmatter(judgment_path.read_text(encoding="utf-8"))["citations"])
        self.assertTrue(parse_frontmatter(decision_path.read_text(encoding="utf-8"))["citation_snapshots"])
        self.assertTrue(parse_frontmatter(judgment_path.read_text(encoding="utf-8"))["citation_snapshots"])
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
        self.assertEqual(parse_frontmatter(judgment_text)["status"], "confirmed")
        self.assertEqual(parse_frontmatter(judgment_text)["confidence"], "high")
        self.assertTrue(parse_frontmatter(judgment_text)["reviewed_at"])

        review_queue = (self.root / "wiki" / "indexes" / "review-queue.md").read_text(encoding="utf-8")
        self.assertIn("当前没有待审决策。", review_queue)
        self.assertIn("当前没有待审判断。", review_queue)
        self.assertIn("Scaling Decision", review_queue)
        self.assertIn("Scaling Judgment", review_queue)

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

        lint_markdown = "# Semantic Lint Report\n\n- No semantic contradictions detected.\n"
        lint_result = run_lint(self.root, client=StubClient([lint_markdown]))
        semantic_path = self.root / lint_result["semantic_report"]
        self.assertTrue(semantic_path.exists())
        self.assertIn("Semantic Lint Report", semantic_path.read_text(encoding="utf-8"))

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
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
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

        packs_index = (self.root / "wiki" / "indexes" / "output-packs.md").read_text(encoding="utf-8")
        review_pack = next((self.root / "output" / "packs" / "review").glob("*.md"))
        decision_memo = next((self.root / "output" / "packs" / "decision-memos").glob("*.md"))
        sop_draft = next((self.root / "output" / "packs" / "sop-drafts").glob("*.md"))

        self.assertIn("Review Pack", packs_index)
        self.assertIn("Decision Memo", packs_index)
        self.assertIn("SOP Draft", packs_index)
        self.assertIn("Scaling Decision", review_pack.read_text(encoding="utf-8"))
        self.assertIn("Scaling Judgment", decision_memo.read_text(encoding="utf-8"))
        sop_text = sop_draft.read_text(encoding="utf-8")
        self.assertIn("## Step-by-Step", sop_text)
        self.assertIn("Action id:", sop_text)
        self.assertIn("apply-action", sop_text)

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
        self.assertIn("## Lifecycle Governance", research_scorecard)
        self.assertIn("## Protocol-Related Lifecycle Concept Backlog", research_scorecard)
        self.assertIn("## Protocol-Related Retired Concepts", research_scorecard)
        self.assertIn(backlog_title, research_scorecard)
        self.assertIn(retired_title, research_scorecard)
        self.assertNotIn(backlog_title, investing_scorecard)
        self.assertNotIn(retired_title, investing_scorecard)

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
        self.assertIn("wiki/indexes/agent-workbench.md", client.prompt)
        self.assertIn("wiki/indexes/cognitive-history.md", client.prompt)
        self.assertIn("wiki/indexes/output-packs.md", client.prompt)
        self.assertIn("wiki/indexes/domain-pilots.md", client.prompt)
        self.assertIn("wiki/indexes/machine-memory-topology.md", client.prompt)
        self.assertIn("wiki/indexes/machine-memory-actions.md", client.prompt)
        self.assertIn("wiki/indexes/machine-memory-repair-plan.md", client.prompt)
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
        self.assertEqual(len(decision_pages), 1)
        decision_text = decision_pages[0].read_text(encoding="utf-8")
        decision_frontmatter = parse_frontmatter(decision_text)
        self.assertEqual(decision_frontmatter["kind"], "decision")
        self.assertEqual(decision_frontmatter["promotion_origin"], "nightly-recurring-output")
        self.assertEqual(decision_frontmatter["promotion_count"], "2")
        self.assertTrue(decision_frontmatter["citations"])
        self.assertTrue(decision_frontmatter["citation_snapshots"])
        self.assertIn(question, decision_text)
        self.assertIn("## Auto Promotion", decision_text)
        self.assertEqual(result["promotions"]["count"], 1)
        self.assertEqual(result["promotions"]["created"], 1)
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
        self.assertEqual(len(judgment_pages), 1)
        judgment_text = judgment_pages[0].read_text(encoding="utf-8")
        judgment_frontmatter = parse_frontmatter(judgment_text)
        self.assertEqual(judgment_frontmatter["kind"], "judgment")
        self.assertEqual(judgment_frontmatter["promotion_origin"], "nightly-recurring-output")
        self.assertEqual(judgment_frontmatter["promotion_count"], "2")
        self.assertEqual(judgment_frontmatter["status"], "tentative")
        self.assertTrue(judgment_frontmatter["citations"])
        self.assertTrue(judgment_frontmatter["citation_snapshots"])
        self.assertIn(question, judgment_text)
        self.assertEqual(result["promotions"]["count"], 1)

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

    def test_nightly_updates_existing_auto_promoted_page_without_duplicates(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Should we adopt transformer caching for inference?"
        ask_question(self.root, question, "report")
        ask_question(self.root, question, "report")
        nightly_health(self.root)

        ask_question(self.root, question, "report")
        result = nightly_health(self.root)

        decision_pages = sorted((self.root / "wiki" / "decisions").glob("*.md"))
        self.assertEqual(len(decision_pages), 1)
        decision_frontmatter = parse_frontmatter(decision_pages[0].read_text(encoding="utf-8"))
        self.assertEqual(decision_frontmatter["promotion_count"], "3")
        self.assertEqual(result["promotions"]["count"], 1)
        self.assertEqual(result["promotions"]["created"], 0)
        self.assertEqual(result["promotions"]["updated"], 1)

    def test_nightly_partitions_auto_promotions_by_protocol(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Should we adopt transformer caching for inference?"
        ask_question(self.root, question, "report", protocol="general")
        ask_question(self.root, question, "report", protocol="general")
        ask_question(self.root, question, "report", protocol="investing")
        ask_question(self.root, question, "report", protocol="investing")

        nightly_health(self.root)

        decision_pages = sorted((self.root / "wiki" / "decisions").glob("*.md"))
        self.assertEqual(len(decision_pages), 2)
        protocols = sorted(parse_frontmatter(path.read_text(encoding="utf-8"))["protocol"] for path in decision_pages)
        self.assertEqual(protocols, ["general", "investing"])

    def test_nightly_auto_promotion_uses_protocol_specific_titles(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Should we underwrite this thesis?"
        ask_question(self.root, question, "report", protocol="investing")
        ask_question(self.root, question, "report", protocol="investing")

        nightly_health(self.root)

        decision_pages = sorted((self.root / "wiki" / "decisions").glob("*.md"))
        self.assertEqual(len(decision_pages), 1)
        decision_frontmatter = parse_frontmatter(decision_pages[0].read_text(encoding="utf-8"))
        self.assertEqual(decision_frontmatter["protocol"], "investing")
        self.assertTrue(str(decision_frontmatter["title"]).startswith("投资决策沉淀："))

    def test_nightly_protocol_specific_markers_can_promote_research_judgment(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Latency bottleneck tradeoff after cache rewrite"
        ask_question(self.root, question, "report", protocol="research")
        ask_question(self.root, question, "report", protocol="research")

        nightly_health(self.root)

        judgment_pages = sorted((self.root / "wiki" / "judgments").glob("*.md"))
        self.assertEqual(len(judgment_pages), 1)
        judgment_frontmatter = parse_frontmatter(judgment_pages[0].read_text(encoding="utf-8"))
        self.assertEqual(judgment_frontmatter["protocol"], "research")
        self.assertTrue(str(judgment_frontmatter["title"]).startswith("研发判断沉淀："))

    def test_nightly_skips_auto_promotion_when_recurring_outputs_have_not_changed(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Should we adopt transformer caching for inference?"
        ask_question(self.root, question, "report")
        ask_question(self.root, question, "report")
        nightly_health(self.root)

        result = nightly_health(self.root)

        self.assertEqual(result["promotions"]["count"], 0)
        decision_pages = sorted((self.root / "wiki" / "decisions").glob("*.md"))
        self.assertEqual(len(decision_pages), 1)

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

    def test_llm_status_auto_prefers_codex_cli_when_api_is_absent(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("aiwiki.config.shutil.which") as which_mock:
                which_mock.side_effect = lambda name: "/usr/bin/codex" if name == "codex" else ""
                status = LLMConfig.status_from_env()
        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], BACKEND_CODEX_CLI)
        self.assertEqual(status["auth_mode"], "cli-session")
        self.assertTrue(status["image_analysis_supported"])

    def test_llm_config_uses_openai_backend_when_explicitly_configured(self) -> None:
        env = {
            "AIWIKI_LLM_BACKEND": "openai-api",
            "AIWIKI_LLM_MODEL": "gpt-4.1-mini",
            "AIWIKI_LLM_API_KEY": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("aiwiki.config.shutil.which", return_value=""):
                config = LLMConfig.from_env()
        self.assertEqual(config.backend, BACKEND_OPENAI_API)
        self.assertEqual(config.model, "gpt-4.1-mini")

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
        self.assertIn('exec python3 -m aiwiki.cli "${ARGS[@]}"', content)

    def test_run_nightly_script_uses_root_relative_paths(self) -> None:
        script = Path("/home/tim/ai-wiki/scripts/run_nightly.sh")
        content = script.read_text(encoding="utf-8")
        self.assertIn('PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"', content)
        self.assertIn('exec python3 -m aiwiki.cli "${ARGS[@]}"', content)
        self.assertIn("run-nightly", content)
        self.assertIn("nightly", content)

    def test_user_service_install_script_mentions_nightly_timer(self) -> None:
        script = Path("/home/tim/ai-wiki/scripts/install_user_service.sh")
        content = script.read_text(encoding="utf-8")
        self.assertIn("aiwiki-nightly.service", content)
        self.assertIn("aiwiki-nightly.timer", content)
        self.assertIn("AIWIKI_NIGHTLY_COMPILE_LIMIT", content)

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

    def test_compile_generates_concept_quality_page(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")

        compile_wiki(self.root)

        concept_quality = self.root / "wiki" / "indexes" / "concept-quality.md"
        self.assertTrue(concept_quality.exists())
        quality_text = concept_quality.read_text(encoding="utf-8")
        self.assertIn("## Rewrite Now", quality_text)
        self.assertIn("## Rewrite Priority", quality_text)
        self.assertIn("## Conflict Signals", quality_text)
        self.assertIn("## Evidence Gaps", quality_text)
        self.assertIn("## Merge Candidates", quality_text)

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
        self.assertIn("graph-node-browser", payload)
        self.assertIn("graphUiData", payload)
        self.assertIn("节点详情", payload)

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
        decision = file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
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


if __name__ == "__main__":
    unittest.main()
