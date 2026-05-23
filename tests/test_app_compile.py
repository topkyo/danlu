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
    build_machine_memory_graph,
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


class CompileFlowTests(AppFlowTestBase):
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
        self.assertIn("latency-notes", latest["added_source_ids"][0])

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
        self.assertIn("# 报告证据图谱", graph_view)
        self.assertIn("报告证据 HTML", graph_view)
        self.assertIn("默认工作流仍然是先看报告", graph_view)
        self.assertIn("这份报告引用了哪些证据", graph_view)
        self.assertIn("普通读报告不需要看", graph_view)
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
        self.assertIn("# 报告证据图谱", payload)
        self.assertIn("默认工作流仍然是先看报告", payload)
        self.assertNotIn("Stale User Copy", payload)
        self.assertIn("wiki/indexes/graph-view.md", result["dirty_index_artifacts"])
        index_step = next(item for item in result["phase_summary"] if item["name"] == "index_refresh")
        self.assertGreaterEqual(index_step["details"]["updated_artifacts"], 1)

    def test_compile_writes_machine_memory_graph_html(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        graph_html = self.root / "output" / "graph" / "machine-memory.html"
        payload = graph_html.read_text(encoding="utf-8")
        self.assertTrue(graph_html.exists())
        self.assertIn("炼丹炉报告证据图谱", payload)
        self.assertIn("报告证据入口", payload)
        self.assertNotIn("Machine Memory Graph", payload)
        self.assertIn("<svg", payload)
        self.assertIn("Transformer Scaling", payload)
        self.assertNotIn("当前没有可展示的中文相关 Markdown 图谱节点", payload)
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

    def test_compile_generates_output_packs_for_review_memo_and_sop(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        file_back(self.root, report["path"], title="Scaling Decision", kind="decision")
        judgment = file_back(self.root, report["path"], title="缩放判断", kind="judgment")
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
        self.assertIn("缩放判断", decision_memo_text)
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
        self.assertIn("## Page-Level Patch Plans", repair_text)
        self.assertIn("review-action overloaded-concept-latency --status accepted", repair_text)

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

    def test_compile_generates_interactive_machine_memory_graph_html(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        payload = (self.root / "output" / "graph" / "machine-memory.html").read_text(encoding="utf-8")
        self.assertIn("graph-search", payload)
        self.assertIn("graph-protocol", payload)
        self.assertIn("graph-node-browser", payload)
        self.assertIn("graphUiData", payload)
        self.assertIn("证据详情", payload)
        self.assertIn("关系组", payload)
        self.assertNotIn("核心概念", payload)
        self.assertNotIn("核心来源", payload)
        self.assertNotIn("<h2>修复候选</h2>", payload)
        self.assertIn("输入标题、关键词或来源编号", payload)
        self.assertIn('option value="judgment"', payload)
        self.assertIn('<option value="source">来源</option>', payload)
        self.assertIn("材料提到概念", payload)
        self.assertIn("材料支撑判断", payload)
        self.assertIn("概念相关", payload)
        self.assertIn("相关关系", payload)
        self.assertIn("这是给读报告的人用的追溯入口", payload)
        self.assertIn("默认不要求普通用户理解或浏览", payload)
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

    def test_compile_graph_html_lists_referencing_reports_for_anchored_nodes(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        result = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        # Re-run compile so the graph HTML picks up the anchor-bearing report.
        compile_wiki(self.root)

        payload = (self.root / "output" / "graph" / "machine-memory.html").read_text(encoding="utf-8")
        self.assertIn("报告证据入口", payload)
        self.assertIn("引用此节点的报告", payload)
        self.assertIn("referenced_by", payload)
        # The report path should be embedded in the JSON payload that drives detail rendering.
        self.assertIn(result["path"], payload)

    def test_machine_memory_graph_keeps_only_existing_markdown_nodes_and_edges(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        memory = load_machine_memory(self.root)
        source_id = memory["source_nodes"][0]["id"]
        concept_slug = memory["concept_nodes"][0]["slug"]
        memory["source_nodes"].append(
            {
                "id": "missing-source",
                "title": "Missing Source",
                "source_type": "note",
                "source_page": "wiki/sources/missing-source.md",
                "stored_path": "raw/missing-source.md",
            }
        )
        memory["concept_nodes"].append(
            {
                "slug": "missing-concept",
                "title": "Missing Concept",
                "source_pages": [],
            }
        )
        memory["edges"]["source_to_concept"].extend(
            [
                {"source_id": source_id, "concept_slug": "missing-concept"},
                {"source_id": "missing-source", "concept_slug": concept_slug},
            ]
        )

        graph = build_machine_memory_graph(memory, root=self.root)
        node_ids = {node["id"] for node in graph["nodes"]}
        self.assertNotIn("source:missing-source", node_ids)
        self.assertNotIn("concept:missing-concept", node_ids)
        for node in graph["nodes"]:
            page_path = node.get("page_path") or node.get("source_page")
            self.assertTrue(str(page_path).endswith(".md"))
            self.assertTrue((self.root / str(page_path)).is_file(), page_path)
            self.assertIn("chinese_related", node)
        for edge in graph["edges"]:
            self.assertIn(edge["source"], node_ids)
            self.assertIn(edge["target"], node_ids)

    def test_machine_memory_graph_displays_english_title_markdown_with_chinese_content(self) -> None:
        source_page = self.root / "wiki" / "sources" / "english-title.md"
        concept_page = self.root / "wiki" / "concepts" / "english-slug.md"
        source_page.parent.mkdir(parents=True, exist_ok=True)
        concept_page.parent.mkdir(parents=True, exist_ok=True)
        source_page.write_text(
            '---\ntitle: "English Title"\n---\n\n# English Title\n\n这份材料正文是中文，所以应该进入默认图谱。\n',
            encoding="utf-8",
        )
        concept_page.write_text(
            '---\ntitle: "English Concept"\n---\n\n# English Concept\n\n概念说明是中文，所以也应该展示。\n',
            encoding="utf-8",
        )
        memory = {
            "compiled_at": "2026-05-20T00:00:00+00:00",
            "source_nodes": [
                {
                    "id": "src-1",
                    "title": "English Title",
                    "source_type": "note",
                    "source_page": "wiki/sources/english-title.md",
                    "stored_path": "raw/inbox/english-title.md",
                    "concept_slugs": ["english-slug"],
                }
            ],
            "concept_nodes": [
                {"slug": "english-slug", "title": "English Concept", "source_pages": ["wiki/sources/english-title.md"]}
            ],
            "judgment_nodes": [],
            "edges": {"source_to_concept": [{"source_id": "src-1", "concept_slug": "english-slug"}]},
            "health": {"components": [{"id": "component-1", "source_ids": ["src-1"], "concept_slugs": ["english-slug"], "judgment_ids": []}]},
        }

        graph = build_machine_memory_graph(memory, root=self.root)
        node_by_id = {node["id"]: node for node in graph["nodes"]}
        self.assertTrue(node_by_id["source:src-1"]["chinese_related"])
        self.assertTrue(node_by_id["concept:english-slug"]["chinese_related"])
        html = render_machine_memory_graph_html(memory, graph=graph)
        self.assertIn("English Title", html)
        self.assertIn("English Concept", html)
        self.assertIn('data-relation-label="材料提到概念"', html)

    def test_machine_memory_graph_keeps_one_hop_neighbors_for_displayed_sources(self) -> None:
        source_page = self.root / "wiki" / "sources" / "readme-source.md"
        concept_page = self.root / "wiki" / "concepts" / "readme.md"
        source_page.parent.mkdir(parents=True, exist_ok=True)
        concept_page.parent.mkdir(parents=True, exist_ok=True)
        source_page.write_text(
            '---\ntitle: "Readme Source"\n---\n\n# Readme Source\n\n这份 source 页面正文是中文。\n',
            encoding="utf-8",
        )
        concept_page.write_text(
            '---\ntitle: "Readme Concept"\n---\n\n# Readme Concept\n\n- 当前概念汇总了 related sources.\n',
            encoding="utf-8",
        )
        memory = {
            "compiled_at": "2026-05-21T00:00:00+00:00",
            "source_nodes": [
                {
                    "id": "readme-md",
                    "title": "Readme Source",
                    "source_type": "note",
                    "source_page": "wiki/sources/readme-source.md",
                    "stored_path": "raw/inbox/readme.md",
                    "concept_slugs": ["readme"],
                }
            ],
            "concept_nodes": [
                {"slug": "readme", "title": "Readme Concept", "source_pages": ["wiki/sources/readme-source.md"]}
            ],
            "judgment_nodes": [],
            "edges": {"source_to_concept": [{"source_id": "readme-md", "concept_slug": "readme"}]},
            "health": {
                "components": [
                    {
                        "id": "component-readme",
                        "source_ids": ["readme-md"],
                        "concept_slugs": ["readme"],
                        "judgment_ids": [],
                    }
                ]
            },
        }
        graph = build_machine_memory_graph(memory, root=self.root)
        node_ids = {node["id"] for node in graph["nodes"]}
        self.assertIn("source:readme-md", node_ids)
        self.assertIn("concept:readme", node_ids)
        html = render_machine_memory_graph_html(memory, graph=graph)
        self.assertIn('data-source="source:readme-md"', html)
        self.assertIn('data-target="concept:readme"', html)

    def test_machine_memory_graph_includes_settled_elixir_markdown_nodes(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        elixir_dir = self.root / "wiki" / "elixirs"
        elixir_dir.mkdir(parents=True, exist_ok=True)
        (elixir_dir / "elixir-a.md").write_text(
            '---\nid: "elixir-a"\nkind: "elixir"\nelixir_state: "settled"\ntopic: "第一颗中文金丹"\nprotocol: "research"\n---\n\n# Elixir\n',
            encoding="utf-8",
        )
        (elixir_dir / "elixir-b.md").write_text(
            '---\nid: "elixir-b"\nkind: "elixir"\nelixir_state: "settled"\ntopic: "第二颗中文金丹"\nderived_from:\n  - wiki/elixirs/elixir-a.md\n---\n\n# Elixir\n',
            encoding="utf-8",
        )

        memory = load_machine_memory(self.root)
        graph = build_machine_memory_graph(memory, root=self.root)
        node_by_id = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(node_by_id["elixir:elixir-a"]["title"], "金丹：第一颗中文金丹")
        self.assertEqual(node_by_id["elixir:elixir-b"]["page_path"], "wiki/elixirs/elixir-b.md")
        self.assertTrue(
            any(
                edge == {"source": "elixir:elixir-a", "target": "elixir:elixir-b", "type": "ELIXIR_DERIVED_FROM"}
                for edge in graph["edges"]
            )
        )

        html = render_machine_memory_graph_html(memory, graph=graph)
        self.assertIn("金丹：第一颗中文金丹", html)
        self.assertIn("金丹承接", html)
        self.assertIn("金丹关联", html)
        self.assertIn('option value="elixir"', html)
        self.assertNotIn("># Elixir<", html)

    def test_compile_attaches_judgment_assets_to_machine_memory_graph(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        judgment = file_back(self.root, report["path"], title="缩放判断", kind="judgment")

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
        self.assertIn("缩放判断", payload)
        self.assertIn("判断 \u00b7 已确认", payload)
        self.assertIn("协议", payload)
        self.assertIn("材料支撑判断", payload)

    def test_compile_surfaces_judgment_relations_across_memory_and_history(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Compare transformer scale and inference cost", "report")
        primary_judgment = file_back(self.root, report["path"], title="主要判断", kind="judgment")
        linked_judgment = file_back(self.root, report["path"], title="关联判断", kind="judgment")
        decision = file_back(self.root, report["path"], title="主要决策", kind="decision")

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
        self.assertIn("主要决策", judgment_assets)
        self.assertIn("supports ->", judgment_assets)
        graph_html = (self.root / "output" / "graph" / "machine-memory.html").read_text(encoding="utf-8")
        self.assertIn("判断冲突", graph_html)
        self.assertIn("决策依据", graph_html)
        self.assertIn("## Judgment Hub", topology)
        self.assertIn("## Judgment 关系事件", cognitive_history)
        self.assertIn("主要判断", cognitive_history)

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
        scripted.write_text("# 中文 Scripted Source\n\n这是一条中文图谱材料，Graph payload should stay safe.\n", encoding="utf-8")
        ingest_source(self.root, str(scripted), title="Bad </script> \u2028 title")

        compile_wiki(self.root)

        payload = (self.root / "output" / "graph" / "machine-memory.html").read_text(encoding="utf-8")
        self.assertIn("\\u003c/script\\u003e", payload)
        self.assertIn("\\u2028", payload)
        self.assertNotIn("Bad </script> \u2028 title", payload)

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



def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(CompileFlowTests))
    return suite


if __name__ == "__main__":
    unittest.main()
