from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app import (
    ask_question,
    compile_wiki,
    ensure_layout,
    file_back,
    ingest_source,
    lint_wiki,
    load_machine_memory,
    load_manifest,
    nightly_health,
    parse_frontmatter,
    placeholder_concept_slugs,
    render_frontmatter,
    review_machine_memory_action,
    review_page,
)
from aiwiki.config import BACKEND_CODEX_CLI, BACKEND_OPENAI_API, LLMConfig
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
        self.assertIn("schema/index.md", result["index_pages"])

        report_text = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertIn("推荐概念", report_text)
        self.assertIn("推荐索引页", report_text)
        self.assertIn("机器记忆", report_text)
        self.assertIn("漂移报告", report_text)
        self.assertIn("决策索引", report_text)
        self.assertIn("判断索引", report_text)
        self.assertIn("运行时规则", report_text)

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
        self.assertEqual(len(result["updated_rewrite_concept_pages"]), 1)
        self.assertIn("Rewritten synthesis", concept_page.read_text(encoding="utf-8"))

    def test_file_back_supports_decision_and_judgment_kinds(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
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
        self.assertIn("## Decision", decision_path.read_text(encoding="utf-8"))
        self.assertIn("## Evidence", decision_path.read_text(encoding="utf-8"))
        self.assertIn("## Review Status", decision_path.read_text(encoding="utf-8"))
        self.assertIn("## Review Notes", decision_path.read_text(encoding="utf-8"))
        self.assertIn("## Judgment", judgment_path.read_text(encoding="utf-8"))
        self.assertIn("## Signals", judgment_path.read_text(encoding="utf-8"))
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

    def test_run_ask_includes_machine_memory_query_plan_in_prompt(self) -> None:
        sample = self.root / "latency.md"
        sample.write_text("# Throughput Notes\n\nLatency throughput cache locality.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(sample), title="Throughput Notes")
        compile_wiki(self.root)
        report_markdown = "\n".join(
            [
                "---",
                'id: "query-1"',
                'kind: "output"',
                'format: "report"',
                'query: "Compare latency tail behavior"',
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
        self.assertIn("wiki/indexes/machine-memory-topology.md", client.prompt)
        self.assertIn("wiki/indexes/machine-memory-actions.md", client.prompt)
        self.assertIn("wiki/indexes/machine-memory-repair-plan.md", client.prompt)
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
        self.assertEqual(len(decision_pages), 1)
        decision_text = decision_pages[0].read_text(encoding="utf-8")
        decision_frontmatter = parse_frontmatter(decision_text)
        self.assertEqual(decision_frontmatter["kind"], "decision")
        self.assertEqual(decision_frontmatter["promotion_origin"], "nightly-recurring-output")
        self.assertEqual(decision_frontmatter["promotion_count"], "2")
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
        self.assertIn(question, judgment_text)
        self.assertEqual(result["promotions"]["count"], 1)

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
        self.assertFalse(state["llm_used"])

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

    def test_compile_generates_machine_memory_repair_plan_page(self) -> None:
        self._seed_machine_memory_actions()

        compile_wiki(self.root)

        repair_plan = self.root / "wiki" / "indexes" / "machine-memory-repair-plan.md"
        self.assertTrue(repair_plan.exists())
        repair_text = repair_plan.read_text(encoding="utf-8")
        self.assertIn("## Need Triage", repair_text)
        self.assertIn("## Execution Batches", repair_text)
        self.assertIn("## Execution Proposals", repair_text)
        self.assertIn("review-action overloaded-concept-latency --status accepted", repair_text)

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

    def test_lint_reports_missing_indexes_and_broken_concept_source_refs(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        (self.root / "wiki" / "indexes" / "index.md").unlink()
        (self.root / "wiki" / "indexes" / "machine-memory.md").unlink()
        (self.root / "wiki" / "indexes" / "machine-memory-topology.md").unlink()
        (self.root / "wiki" / "indexes" / "machine-memory-actions.md").unlink()
        (self.root / "wiki" / "indexes" / "machine-memory-repair-plan.md").unlink()
        (self.root / "wiki" / "indexes" / "concept-quality.md").unlink()
        (self.root / "wiki" / "indexes" / "graph-health.md").unlink()
        (self.root / "wiki" / "indexes" / "drift-report.md").unlink()
        (self.root / ".aiwiki" / "cache" / "machine-memory-graph.json").unlink()
        concept_page = next((self.root / "wiki" / "concepts").glob("*.md"))
        broken = concept_page.read_text(encoding="utf-8").replace("wiki/sources/", "wiki/sources/missing-", 1)
        concept_page.write_text(broken, encoding="utf-8")

        lint = lint_wiki(self.root)
        report_text = (self.root / lint["path"]).read_text(encoding="utf-8")
        self.assertGreaterEqual(lint["counts"]["errors"], 2)
        self.assertIn("Missing master wiki index page.", report_text)
        self.assertIn("Missing machine memory index page.", report_text)
        self.assertIn("Missing machine memory topology page.", report_text)
        self.assertIn("Missing machine memory actions page.", report_text)
        self.assertIn("Missing machine memory repair plan page.", report_text)
        self.assertIn("Missing concept quality page.", report_text)
        self.assertIn("Missing machine memory graph health page.", report_text)
        self.assertIn("Missing machine memory drift report.", report_text)
        self.assertIn("Missing machine memory graph export.", report_text)
        self.assertIn("Concept page references missing source page", report_text)


if __name__ == "__main__":
    unittest.main()
