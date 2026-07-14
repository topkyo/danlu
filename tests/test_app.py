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
from aiwiki.content.io import ingest_source
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
    def __init__(self, response: str, backend: str = "opencode-api") -> None:
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
    def __init__(self, backend: str = "opencode-api") -> None:
        self.config = type("Config", (), {"backend": backend, "model": "stub-vision-model"})()

    def analyze_image(self, system_prompt: str, user_prompt: str, image_path: Path) -> CompletionResult:
        del system_prompt
        del user_prompt
        del image_path
        raise RuntimeError("vision backend failed")



class AppFlowTestBase(unittest.TestCase):
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




class AiwikiFlowTests(AppFlowTestBase):
    pass


if __name__ == "__main__":
    unittest.main()
