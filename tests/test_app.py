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
    load_manifest,
    parse_frontmatter,
)
from aiwiki.config import BACKEND_CODEX_CLI, BACKEND_OPENAI_API, LLMConfig
from aiwiki.drop import _fetch_url, drop_image, drop_pdf, drop_repo, drop_url
from aiwiki.llm import CompletionResult
from aiwiki.runner import auto_process_once, run_ask, run_compile, run_lint, watch_inbox


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
        self.assertIn("Source URL", source_path.read_text(encoding="utf-8"))

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
        memory_state = self.root / ".aiwiki" / "state" / "machine-memory.json"
        self.assertTrue(master_index.exists())
        self.assertTrue(log_page.exists())
        self.assertTrue(memory_page.exists())
        self.assertTrue(memory_state.exists())
        self.assertIn("Operation Log", master_index.read_text(encoding="utf-8"))
        self.assertIn("Machine Memory", master_index.read_text(encoding="utf-8"))
        self.assertIn("compile | wiki refresh", log_page.read_text(encoding="utf-8"))
        self.assertIn("Runtime state file", memory_page.read_text(encoding="utf-8"))
        memory = json.loads(memory_state.read_text(encoding="utf-8"))
        self.assertEqual(memory["source_nodes"][0]["id"], entry["id"])
        self.assertTrue(memory["term_index"])

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
        self.assertIn("schema/index.md", result["index_pages"])

        report_text = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertIn("Recommended Concepts", report_text)
        self.assertIn("Recommended Index Pages", report_text)
        self.assertIn("Machine Memory", report_text)
        self.assertIn("Runtime Schema", report_text)

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
        self.assertIn("Runtime Schema", schema_index)
        self.assertIn("product-facing policy", schema_index)

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

    def test_run_compile_replaces_placeholder_summary(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        current = source_page.read_text(encoding="utf-8")
        updated = current.replace("- Pending LLM summary.", "- Transformers benefit from scale, but cost rises with inference demand.")
        result = run_compile(self.root, client=StubClient([updated]), limit=1)
        self.assertEqual(result["pending_pages"], 1)
        self.assertIn("Transformers benefit from scale", source_page.read_text(encoding="utf-8"))

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
        concept_page = next((self.root / "wiki" / "concepts").glob("*.md"))
        broken = concept_page.read_text(encoding="utf-8").replace("wiki/sources/", "wiki/sources/missing-", 1)
        concept_page.write_text(broken, encoding="utf-8")

        lint = lint_wiki(self.root)
        report_text = (self.root / lint["path"]).read_text(encoding="utf-8")
        self.assertGreaterEqual(lint["counts"]["errors"], 2)
        self.assertIn("Missing master wiki index page.", report_text)
        self.assertIn("Missing machine memory index page.", report_text)
        self.assertIn("Concept page references missing source page", report_text)


if __name__ == "__main__":
    unittest.main()
