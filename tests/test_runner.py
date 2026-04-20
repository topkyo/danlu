from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_compile import compile_wiki
from aiwiki.app_content import ingest_source, sync_manifest_with_raw
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_utils import relative_path
from aiwiki.config import LLMConfig
from aiwiki.drop import drop_note
from aiwiki.llm import CompletionResult, LLMError
from aiwiki.runner import (
    _append_log,
    _build_ask_prompt,
    _build_compile_prompt,
    _build_concept_compile_prompt,
    _build_lint_prompt,
    _client_model_name,
    _context_budget,
    _extract_related_concept_slugs,
    _fit_log_prompt_section,
    _fit_prompt_section,
    _load_prompt,
    _normalize_markdown,
    _pending_summary_count,
    _protocol_context,
    _read_context,
    _render_machine_query,
    _rewrite_candidate_record,
    _rewrite_candidate_slugs,
    _schema_context,
    _system_prompt,
    _validate_concept_page,
    _validate_output_markdown,
    _validate_source_page,
    _write_automation_state,
    create_client,
    llm_probe,
    llm_status,
    run_ask,
    run_compile,
    run_lint,
)


class _DummyClient:
    def __init__(self) -> None:
        self.config = type("Config", (), {"model": "dummy-model"})()

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt
        del user_prompt
        raise AssertionError("complete should not be called in this test")


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)
        for name in ("compile.md", "ask.md", "lint.md"):
            (self.root / "prompts" / name).write_text(f"{name} fixture\n", encoding="utf-8")
        for name in ("index.md", "citations.md", "conflicts.md", "writeback.md", "taxonomy.md"):
            (self.root / "schema" / name).write_text(f"# {name}\n\nschema fixture\n", encoding="utf-8")
        for name in ("index.md", "taxonomy.md", "query.md", "review.md", "nightly.md", "decision.md", "judgment.md"):
            path = self.root / "schema" / "protocols" / "general" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {name}\n\nprotocol fixture\n", encoding="utf-8")
        self.sample = self.root / "sample.md"
        self.sample.write_text(
            "# Transformer Scaling\n\nTransformers benefit from scale.\nInference costs also rise.\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_llm_status_and_create_client_delegate_to_backend_layers(self) -> None:
        fake_status = {"configured": True, "max_context_chars": 12345}
        fake_client = object()
        with patch("aiwiki.runner.LLMConfig.status_from_env", return_value=fake_status):
            self.assertEqual(llm_status(), fake_status)
        fake_config = LLMConfig(backend="codex-cli", timeout_seconds=120)
        with patch("aiwiki.runner.LLMConfig.from_env", return_value=fake_config):
            with patch("aiwiki.runner.create_backend_client", return_value=fake_client) as create_backend_client:
                self.assertIs(create_client(self.root), fake_client)
                self.assertIs(create_client(self.root, timeout_seconds=45), fake_client)
        calls = create_backend_client.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[0].timeout_seconds, 120)
        self.assertEqual(calls[1].args[0].timeout_seconds, 45)
        self.assertEqual(calls[0].args[1], self.root)
        self.assertEqual(calls[1].args[1], self.root)

    def test_run_ask_uses_lean_prompt_immediately_when_requested(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-lean.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-lean\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-lean.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        class _LeanClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "gpt-5.4", "timeout_seconds": 120})()
                self.prompts: list[str] = []

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                self.prompts.append(user_prompt)
                return CompletionResult(
                    text="---\nid: query-lean\nkind: report\n---\n\n# Answer\n\nLean first.\n",
                    response_id="resp_lean",
                    usage={},
                )

        client = _LeanClient()
        with patch("aiwiki.runner.ask_question", return_value=artifact):
            with patch("aiwiki.runner._build_ask_prompt", return_value="lean prompt") as build_prompt:
                result = run_ask(self.root, "测试", "report", client=client, lean=True)

        self.assertEqual(result["prompt_profile"], "lean")
        self.assertEqual(result["retry_prompt_profile"], "")
        self.assertEqual(client.prompts, ["lean prompt"])
        build_prompt.assert_called_once()
        self.assertEqual(build_prompt.call_args.kwargs["prompt_profile"], "lean")
        self.assertEqual(result["timeout_seconds"], 120)

    def test_run_ask_timeout_override_is_scoped_to_single_client_creation(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-timeout-override.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-timeout-override\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-timeout-override.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        class _TimeoutClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "gpt-5.4", "timeout_seconds": 33})()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                return CompletionResult(
                    text="---\nid: query-timeout-override\nkind: report\n---\n\n# Answer\n\nok\n",
                    response_id="resp",
                    usage={},
                )

        with patch("aiwiki.runner.ask_question", return_value=artifact):
            with patch("aiwiki.runner.create_client", return_value=_TimeoutClient()) as create_client_mock:
                result = run_ask(
                    self.root,
                    "测试",
                    "report",
                    timeout_seconds=33,
                )

        create_client_mock.assert_called_once_with(self.root, timeout_seconds=33)
        self.assertEqual(result["timeout_seconds"], 33)

    def test_llm_probe_returns_static_status_when_unconfigured(self) -> None:
        fake_status = {"configured": False, "message": "missing backend"}
        with patch("aiwiki.runner.LLMConfig.status_from_env", return_value=fake_status):
            result = llm_probe(self.root, probe_all=False, timeout_seconds=17)

        self.assertFalse(result["configured"])
        self.assertEqual(result["probe_timeout_seconds"], 17)
        self.assertIsNone(result["probe"])
        self.assertEqual(result["probes"], [])

    def test_llm_probe_delegates_to_single_or_all_backend_probes(self) -> None:
        fake_status = {"configured": True, "backend": "codex-cli"}
        fake_config = type("Config", (), {"backend": "codex-cli"})()
        with patch("aiwiki.runner.LLMConfig.status_from_env", return_value=fake_status):
            with patch("aiwiki.runner.LLMConfig.from_env", return_value=fake_config):
                with patch("aiwiki.runner.probe_backend", return_value={"backend": "codex-cli", "ok": True}) as probe_one:
                    single = llm_probe(self.root, probe_all=False, timeout_seconds=13)
                with patch(
                    "aiwiki.runner.probe_available_backends",
                    return_value=[{"backend": "codex-cli", "ok": True}, {"backend": "copilot-cli", "ok": False}],
                ) as probe_all:
                    all_backends = llm_probe(self.root, probe_all=True, timeout_seconds=19)

        probe_one.assert_called_once_with(fake_config, self.root, timeout_seconds=13)
        probe_all.assert_called_once_with(fake_config, self.root, timeout_seconds=19)
        self.assertEqual(single["probe"], {"backend": "codex-cli", "ok": True})
        self.assertEqual(single["probes"], [])
        self.assertEqual(all_backends["probe"], {"backend": "codex-cli", "ok": True})
        self.assertEqual(len(all_backends["probes"]), 2)

    def test_build_ask_prompt_trims_indexes_and_protocol_pages_for_report_profile(self) -> None:
        target = self.root / "output" / "reports" / "query-test.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\nid: query-test\nkind: report\n---\n\n# Query\n", encoding="utf-8")

        prompt = _build_ask_prompt(
            self.root,
            target,
            "测试",
            "report",
            target.read_text(encoding="utf-8"),
            source_pages=[],
            concept_pages=[],
            protocol_pages=[
                ("schema/protocols/general/index.md", "protocol index"),
                ("schema/protocols/general/query.md", "protocol query"),
                ("schema/protocols/general/review.md", "protocol review"),
            ],
            index_pages=[
                ("wiki/indexes/index.md", "index home"),
                ("wiki/indexes/sources.md", "sources index"),
                ("wiki/indexes/review-center.md", "review center should be omitted"),
                ("wiki/indexes/machine-memory.md", "machine memory"),
                ("wiki/indexes/log.md", "## old\n\nold log\n" * 100),
                ("schema/index.md", "schema index"),
            ],
            machine_memory_query={},
            prompt_profile="lean",
        )

        self.assertIn("### wiki/indexes/index.md", prompt)
        self.assertIn("### wiki/indexes/sources.md", prompt)
        self.assertIn("### wiki/indexes/machine-memory.md", prompt)
        self.assertIn("### schema/index.md", prompt)
        self.assertNotIn("review-center.md", prompt)
        self.assertIn("### schema/protocols/general/index.md", prompt)
        self.assertIn("### schema/protocols/general/query.md", prompt)
        self.assertNotIn("protocol review", prompt)
        self.assertLess(len(prompt), 30000)

    def test_run_ask_retries_with_lean_prompt_on_timeout(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-timeout.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-timeout\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-timeout.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        class _RetryClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "gpt-5.4"})()
                self.prompts: list[str] = []

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                self.prompts.append(user_prompt)
                if len(self.prompts) == 1:
                    raise LLMError("Codex CLI timed out after 120 seconds.")
                return CompletionResult(
                    text="---\nid: query-timeout\nkind: report\n---\n\n# Answer\n\nRecovered.\n",
                    response_id="resp_retry",
                    usage={},
                )

        client = _RetryClient()
        with patch("aiwiki.runner.ask_question", return_value=artifact):
            with patch("aiwiki.runner._build_ask_prompt", side_effect=["balanced prompt", "lean prompt"]):
                result = run_ask(self.root, "测试", "report", client=client)

        self.assertEqual(result["path"], "output/reports/query-timeout.md")
        self.assertEqual(result["prompt_profile"], "lean")
        self.assertEqual(result["retry_prompt_profile"], "lean")
        self.assertEqual(client.prompts, ["balanced prompt", "lean prompt"])
        self.assertIn("# Answer", artifact_path.read_text(encoding="utf-8"))

    def test_run_ask_retries_with_github_models_minimal_profile_on_size_limit(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-github-models.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-github-models\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-github-models.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        class _GitHubModelsRetryClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "openai/gpt-4.1", "backend": "github-models-api"})()
                self.prompts: list[str] = []

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                self.prompts.append(user_prompt)
                if len(self.prompts) == 1:
                    raise LLMError("HTTP 413 from GitHub Models endpoint: tokens_limit_reached")
                return CompletionResult(
                    text="---\nid: query-github-models\nkind: report\n---\n\n# Answer\n\nRecovered.\n",
                    response_id="resp_retry",
                    usage={},
                )

        client = _GitHubModelsRetryClient()
        with patch("aiwiki.runner.ask_question", return_value=artifact):
            with patch("aiwiki.runner._build_ask_prompt", side_effect=["github-models prompt", "github-models-minimal prompt"]):
                result = run_ask(self.root, "测试", "report", client=client)

        self.assertEqual(result["prompt_profile"], "github-models-minimal")
        self.assertEqual(result["retry_prompt_profile"], "github-models-minimal")
        self.assertEqual(client.prompts, ["github-models prompt", "github-models-minimal prompt"])

    def test_run_compile_limit_zero_reports_pending_source_and_concept_pages(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_page = self.root / "wiki" / "concepts" / "transformer-scaling.md"
        text = concept_page.read_text(encoding="utf-8")
        before, marker, after = text.partition("## Summary\n")
        _, related_marker, remainder = after.partition("\n## Related Sources\n")
        concept_page.write_text(
            before
            + marker
            + "- Existing synthesis for transformer-scaling appears\n"
            + "- Keep the current synthesis grounded in the linked sources.\n"
            + related_marker
            + remainder,
            encoding="utf-8",
        )
        compile_wiki(self.root)

        result = run_compile(self.root, client=_DummyClient(), limit=0)

        self.assertEqual(result["pending_pages"], 1)
        self.assertEqual(result["pending_concept_pages"], 0)
        self.assertGreaterEqual(result["pending_rewrite_concept_pages"], 1)
        self.assertEqual(result["updated_pages"], [])
        self.assertEqual(result["updated_concept_pages"], [])
        self.assertIn(entry["id"], result["compile"]["clean_source_ids"] + result["compile"]["dirty_source_ids"])

    def test_prompt_helpers_include_schema_protocol_and_quality_signals(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        concept_page = self.root / "wiki" / "concepts" / "transformer-scaling.md"
        prompt = _build_compile_prompt(self.root, entry, self.root / entry["stored_path"], source_page.read_text(encoding="utf-8"))

        self.assertIn("## Runtime Schema", prompt)
        self.assertIn("## Active Protocol", prompt)
        self.assertIn(entry["stored_path"], prompt)
        self.assertIn("Replace file:", prompt)

        concept_prompt = _build_concept_compile_prompt(
            self.root,
            concept_page,
            concept_page.read_text(encoding="utf-8"),
            [f"wiki/sources/{entry['id']}.md"],
            ["transformer-scaling"],
            quality_record={
                "priority": "high",
                "issues": ["conflict", "gap"],
                "rewrite_strategy": "Make evidence boundaries explicit.",
                "conflict_signals": [{"label": "source-tension", "source_pages": [f"wiki/sources/{entry['id']}.md"]}],
                "gap_signals": [{"kind": "coverage-gap", "path": str(concept_page), "markers": ["missing-benchmark"]}],
            },
        )

        self.assertIn("Rewrite priority: `high`", concept_prompt)
        self.assertIn("Conflict `source-tension`", concept_prompt)
        self.assertIn("Gap `coverage-gap`", concept_prompt)
        self.assertIn("Make evidence boundaries explicit.", concept_prompt)
        self.assertIn("hardness: soft|medium|hard", concept_prompt)

    def test_github_models_prompt_profiles_trim_compile_and_lint_inputs(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        concept_page = self.root / "wiki" / "concepts" / "transformer-scaling.md"
        giant = ("## Section\n\n" + ("signal " * 300) + "\n\n") * 10
        for relative in (
            "wiki/indexes/index.md",
            "wiki/indexes/sources.md",
            "wiki/indexes/concepts.md",
            "wiki/indexes/compile-status.md",
            "wiki/indexes/machine-memory.md",
            "wiki/indexes/machine-memory-topology.md",
            "wiki/indexes/machine-memory-actions.md",
            "wiki/indexes/graph-health.md",
            "wiki/indexes/drift-report.md",
            "wiki/indexes/log.md",
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(giant, encoding="utf-8")
        deterministic_report = self.root / "output" / "lint" / "deterministic.md"
        deterministic_report.parent.mkdir(parents=True, exist_ok=True)
        deterministic_report.write_text(giant, encoding="utf-8")

        compile_prompt = _build_compile_prompt(
            self.root,
            entry,
            self.root / entry["stored_path"],
            source_page.read_text(encoding="utf-8"),
            prompt_profile="github-models",
        )
        concept_prompt = _build_concept_compile_prompt(
            self.root,
            concept_page,
            concept_page.read_text(encoding="utf-8"),
            [f"wiki/sources/{entry['id']}.md", f"wiki/sources/{entry['id']}.md", f"wiki/sources/{entry['id']}.md"],
            ["transformer-scaling", "transformer-scaling", "transformer-scaling"],
            quality_record={
                "priority": "high",
                "issues": ["conflict", "gap"],
                "rewrite_strategy": "Keep it short.",
                "conflict_signals": [{"label": "source-tension", "source_pages": [f"wiki/sources/{entry['id']}.md"]}] * 4,
                "gap_signals": [{"kind": "coverage-gap", "path": str(concept_page), "markers": ["missing-benchmark"]}] * 4,
            },
            prompt_profile="github-models",
        )
        lint_prompt = _build_lint_prompt(
            self.root,
            relative_path(self.root, deterministic_report),
            prompt_profile="github-models",
        )

        self.assertLess(len(compile_prompt), 14000)
        self.assertLess(len(concept_prompt), 14000)
        self.assertLess(len(lint_prompt), 14000)
        self.assertIn("Omitted", concept_prompt)
        self.assertIn("Additional wiki files were omitted", lint_prompt)

    def test_load_prompt_falls_back_to_runtime_templates_when_vault_prompt_is_missing(self) -> None:
        (self.root / "prompts" / "ask.md").unlink()

        prompt = _load_prompt(self.root, "ask.md")

        self.assertIn("Return the full replacement artifact only", prompt)

    def test_compile_prompt_adds_note_kind_hints_for_transcripts(self) -> None:
        drop_note(
            self.root,
            text="# Standup\n\nAlice: review backlog.\nBob: ship runtime validation.\n",
            kind="transcript",
        )
        manifest = sync_manifest_with_raw(self.root)
        entry = manifest["entries"][0]
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"

        prompt = _build_compile_prompt(self.root, entry, self.root / entry["stored_path"], source_page.read_text(encoding="utf-8"))

        self.assertIn("Material kind: `transcript`", prompt)
        self.assertIn("Preserve chronology, speaker attributions", prompt)

    def test_run_compile_retries_with_github_models_minimal_profile_on_size_limit(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        updated_markdown = source_page.read_text(encoding="utf-8").replace(
            "- Pending LLM summary.",
            "- Grounded summary from GitHub Models.",
        )

        class _GitHubModelsCompileRetryClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "openai/gpt-4.1", "backend": "github-models-api"})()
                self.prompts: list[str] = []

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                self.prompts.append(user_prompt)
                if len(self.prompts) == 1:
                    raise LLMError("HTTP 413 from GitHub Models endpoint: tokens_limit_reached")
                return CompletionResult(text=updated_markdown, response_id="resp_compile_retry", usage={})

        client = _GitHubModelsCompileRetryClient()
        with patch("aiwiki.runner._build_compile_prompt", side_effect=["github-models prompt", "github-models-minimal prompt"]):
            result = run_compile(self.root, client=client, limit=1)

        self.assertEqual(result["prompt_profile"], "github-models-minimal")
        self.assertEqual(result["retry_prompt_profile"], "github-models-minimal")
        self.assertEqual(client.prompts, ["github-models prompt", "github-models-minimal prompt"])
        self.assertIn("Grounded summary from GitHub Models.", source_page.read_text(encoding="utf-8"))

    def test_run_lint_retries_with_github_models_minimal_profile_on_size_limit(self) -> None:
        deterministic_report = self.root / "output" / "lint" / "deterministic.md"
        deterministic_report.parent.mkdir(parents=True, exist_ok=True)
        deterministic_report.write_text("# Deterministic\n\n- issue\n", encoding="utf-8")

        class _GitHubModelsLintRetryClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "openai/gpt-4.1", "backend": "github-models-api"})()
                self.prompts: list[str] = []

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                self.prompts.append(user_prompt)
                if len(self.prompts) == 1:
                    raise LLMError("HTTP 413 from GitHub Models endpoint: tokens_limit_reached")
                return CompletionResult(text="# Semantic Lint\n\n- Recovered.\n", response_id="resp_lint_retry", usage={})

        client = _GitHubModelsLintRetryClient()
        with patch("aiwiki.runner.lint_wiki", return_value={"path": relative_path(self.root, deterministic_report)}):
            with patch("aiwiki.runner._build_lint_prompt", side_effect=["github-models lint", "github-models-minimal lint"]):
                result = run_lint(self.root, client=client)

        self.assertEqual(result["prompt_profile"], "github-models-minimal")
        self.assertEqual(result["retry_prompt_profile"], "github-models-minimal")
        self.assertEqual(client.prompts, ["github-models lint", "github-models-minimal lint"])
        semantic_report = self.root / result["semantic_report"]
        self.assertIn("# Semantic Lint", semantic_report.read_text(encoding="utf-8"))

    def test_rewrite_candidate_and_machine_query_helpers_render_expected_details(self) -> None:
        memory = {
            "health": {
                "concept_quality": {
                    "rewrite_candidates": [
                        {"slug": "agent", "priority": "high", "issues": ["gap"]},
                        {"slug": "protocol", "priority": "medium", "issues": []},
                    ],
                    "weak_concepts": [
                        {
                            "slug": "agent",
                            "conflict_signals": [{"label": "conflict", "source_pages": ["wiki/sources/a.md"]}],
                            "gap_signals": [{"kind": "gap", "path": "wiki/concepts/agent.md", "markers": ["missing"]}],
                        }
                    ],
                }
            }
        }
        self.assertEqual(_rewrite_candidate_slugs(memory, exclude={"protocol"}), ["agent"])
        record = _rewrite_candidate_record(memory, "agent")
        self.assertEqual(record["priority"], "high")
        self.assertEqual(record["conflict_signals"][0]["label"], "conflict")
        self.assertEqual(_rewrite_candidate_record(memory, "missing"), {})

        rendered = _render_machine_query(
            {
                "matched_terms": ["agent", "protocol"],
                "selected_strategy": "graph-walk",
                "selection_reason": "graph-markers",
                "matched_source_markers": ["source"],
                "matched_graph_markers": ["why"],
                "direct_source_ids": ["s1"],
                "direct_concept_slugs": ["agent"],
                "ranked_source_ids": ["s1", "s2"],
                "ranked_concept_slugs": ["agent", "protocol"],
                "bridge_concept_slugs": ["memory"],
                "touched_component_ids": ["component-1"],
                "supporting_edges": [{"type": "source_to_concept", "left": "s1", "right": "agent"}],
                "query_subgraph": {"sources": [{"id": "s1"}], "concepts": [{"slug": "agent"}], "edges": [1, 2]},
                "query_routes": [
                    {
                        "start": {"id": "s1", "title": "Source 1"},
                        "goal": {"id": "agent", "title": "Agent"},
                        "length": 2,
                        "strategy": "graph-walk",
                    }
                ],
                "planner_next_action": {"action_id": "repair-1", "title": "Repair concept", "priority_score": 42},
                "relevant_actions": [
                    {
                        "priority": "high",
                        "title": "Repair concept",
                        "status": "open",
                        "execution_policy": "safe-apply",
                        "primary_path": "wiki/concepts/agent.md",
                        "secondary_path": "wiki/indexes/concept-quality.md",
                        "next_step": "review",
                        "proposal_kind": "rewrite",
                        "proposal_targets": ["wiki/concepts/agent.md"],
                        "proposal_summary": "Tighten synthesis",
                    }
                ],
            }
        )

        self.assertIn("Matched terms", rendered)
        self.assertIn("Route summaries", rendered)
        self.assertIn("Repair action summaries", rendered)
        self.assertIn("Planner next action", rendered)

    def test_text_helpers_validation_and_state_writers_cover_edge_cases(self) -> None:
        self.assertIn("local-first research wiki", _system_prompt("compile"))
        self.assertIn("Return only the full replacement artifact", _system_prompt("ask"))
        self.assertIn("semantic issues", _system_prompt("lint"))

        self.assertEqual(_normalize_markdown("```md\n# Title\n```\n"), "# Title\n")
        self.assertTrue(_fit_prompt_section("abcdef", 3).endswith("...[truncated]"))
        self.assertTrue(_fit_prompt_section("abcdef", 3, tail=True).startswith("...[truncated earlier content]"))
        log_text = "## A\none\n## B\ntwo\n## C\nthree\n## D\nfour\n"
        self.assertIn("truncated earlier log entries", _fit_log_prompt_section(log_text, 12))
        self.assertEqual(_extract_related_concept_slugs("[A](./agent.md)\n[B](./agent.md)\n[C](./protocol.md)"), ["agent", "protocol"])

        long_text = "x" * 40
        long_path = self.root / "long.md"
        long_path.write_text(long_text, encoding="utf-8")
        self.assertTrue(_read_context(long_path, 10).endswith("...[truncated]"))

        binary_path = self.root / "tiny.bin"
        binary_path.write_bytes(b"binary-content")
        with patch("aiwiki.runner.read_text_preview", return_value="preview"):
            self.assertEqual(_read_context(binary_path, 20), "preview")

        self.assertIn("schema/index.md", _schema_context(self.root, ("index.md", "missing.md")))
        self.assertIn("Active protocol: `general`", _protocol_context(self.root, ("index.md", "missing.md")))

        source_markdown = "\n".join(
            [
                "---",
                'id: "source-1"',
                'kind: "source"',
                'source_files: ["raw/inbox/source.md"]',
                'source_sha256: "sha-1"',
                "---",
                "",
                "# Title",
                "",
                "## Summary",
                "- Grounded summary.",
                "",
            ]
        )
        _validate_source_page(source_markdown, "source-1", "raw/inbox/source.md", "sha-1")
        with self.assertRaises(RuntimeError):
            _validate_source_page("# missing frontmatter\n", "source-1", "raw/inbox/source.md", "sha-1")
        with self.assertRaises(RuntimeError):
            _validate_source_page(source_markdown.replace('id: "source-1"', 'id: "source-2"'), "source-1", "raw/inbox/source.md", "sha-1")
        with self.assertRaises(RuntimeError):
            _validate_source_page(source_markdown.replace("- Grounded summary.", "- Pending LLM summary."), "source-1", "raw/inbox/source.md", "sha-1")

        concept_markdown = "\n".join(
            [
                "---",
                'id: "concept-agent"',
                'kind: "concept"',
                'source_signature: "sig-1"',
                'source_pages: ["wiki/sources/source-1.md"]',
                'hardness: "medium"',
                "---",
                "",
                "# Agent",
                "",
                "## Summary",
                "- Grounded synthesis.",
                "",
            ]
        )
        _validate_concept_page(concept_markdown, "agent", "sig-1", ["wiki/sources/source-1.md"])
        with self.assertRaises(RuntimeError):
            _validate_concept_page("# missing frontmatter\n", "agent", "sig-1", ["wiki/sources/source-1.md"])
        with self.assertRaises(RuntimeError):
            _validate_concept_page(concept_markdown.replace('id: "concept-agent"', 'id: "concept-other"'), "agent", "sig-1", ["wiki/sources/source-1.md"])
        with self.assertRaises(RuntimeError):
            _validate_concept_page(
                concept_markdown.replace("- Grounded synthesis.", "- This concept currently appears in `1` source page(s)."),
                "agent",
                "sig-1",
                ["wiki/sources/source-1.md"],
            )
        with self.assertRaises(RuntimeError):
            _validate_concept_page(
                concept_markdown.replace('hardness: "medium"', 'hardness: "unknown"'),
                "agent",
                "sig-1",
                ["wiki/sources/source-1.md"],
            )

        _validate_output_markdown("---\nformat: report\n---\n\nSee wiki/sources/source-1.md\n", "report", ["source-1"])
        with self.assertRaises(RuntimeError):
            _validate_output_markdown("# no frontmatter\n", "report", ["source-1"])
        with self.assertRaises(RuntimeError):
            _validate_output_markdown("---\nformat: report\n---\n\nNo citations here.\n", "report", ["source-1"])

        _append_log(self.root, {"event": "runner-test"})
        log_path = self.root / ".aiwiki" / "logs" / "runs.jsonl"
        self.assertTrue(log_path.exists())
        _write_automation_state(self.root, {"status": "ok"})
        state_path = self.root / ".aiwiki" / "state" / "automation.json"
        self.assertEqual(json.loads(state_path.read_text(encoding="utf-8"))["status"], "ok")
        self.assertEqual(_client_model_name(_DummyClient()), "dummy-model")

    def test_pending_summary_count_tracks_placeholder_sources(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        self.assertEqual(_pending_summary_count(self.root), 1)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace("- Pending LLM summary.", "- Grounded summary."),
            encoding="utf-8",
        )
        self.assertEqual(_pending_summary_count(self.root), 0)
        with patch("aiwiki.runner.LLMConfig.status_from_env", return_value={"max_context_chars": 1234}):
            self.assertEqual(_context_budget(), 1234)
