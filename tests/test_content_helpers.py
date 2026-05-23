from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import aiwiki.app_compile as app_compile
import aiwiki.app_content as content
import aiwiki.app_queries as queries
import aiwiki.app_state as state
import aiwiki.app_utils as utils
from aiwiki.app_protocol import ensure_layout


class ContentHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_markdown(self, path: Path, frontmatter: dict[str, object], body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{utils.render_frontmatter(frontmatter)}\n\n{body.strip()}\n", encoding="utf-8")

    def test_wiki_log_cleanup_and_pack_path_helpers(self) -> None:
        log_path = content.ensure_wiki_log(self.root)
        self.assertTrue(log_path.exists())
        content.append_wiki_log(self.root, "compile", "Alpha", ["detail-a", "detail-b"])
        log_text = log_path.read_text(encoding="utf-8")
        self.assertIn("compile | Alpha", log_text)
        self.assertIn("- detail-a", log_text)

        concept_dir = self.root / "wiki" / "concepts"
        self._write_markdown(
            concept_dir / "keep.md",
            {"kind": "concept", "generated_by": "aiwiki-compile", "id": "concept-keep"},
            "# Keep\n\n## Summary\n- stable\n",
        )
        self._write_markdown(
            concept_dir / "stale.md",
            {"kind": "concept", "generated_by": "aiwiki-compile", "id": "concept-stale"},
            "# Stale\n\n## Summary\n- remove\n",
        )

        self._write_markdown(
            concept_dir / "manual.md",
            {"kind": "concept", "generated_by": "manual", "id": "concept-manual"},
            "# Manual\n",
        )
        self._write_markdown(
            concept_dir / "bad-id.md",
            {"kind": "concept", "generated_by": "aiwiki-compile", "id": "manual"},
            "# Bad\n",
        )

        removed = content.remove_stale_generated_concept_pages(self.root, {"keep"})
        self.assertEqual(removed, 1)
        self.assertFalse((concept_dir / "stale.md").exists())
        self.assertTrue((concept_dir / "keep.md").exists())
        self.assertTrue((concept_dir / "manual.md").exists())
        self.assertTrue((concept_dir / "bad-id.md").exists())

        # F-new-13 (Round 6): detailed variant returns the removed slugs for wiki-log.
        # Re-create a fresh stale page and verify the detailed return.
        self._write_markdown(
            concept_dir / "stale2.md",
            {"kind": "concept", "generated_by": "aiwiki-compile", "id": "concept-stale2"},
            "# Stale 2\n",
        )
        count, slugs = content.remove_stale_generated_concept_pages_detailed(self.root, {"keep"})
        self.assertEqual(count, 1)
        self.assertEqual(slugs, ["stale2"])
        self.assertFalse((concept_dir / "stale2.md").exists())

        self.assertEqual(content.review_packs_dir(self.root), self.root / "output" / "packs" / "review")
        self.assertEqual(content.decision_memos_dir(self.root), self.root / "output" / "packs" / "decision-memos")
        self.assertEqual(content.sop_drafts_dir(self.root), self.root / "output" / "packs" / "sop-drafts")
        self.assertEqual(content.pack_stem("wiki\\decisions/alpha.md"), "wiki-decisions-alpha")
        self.assertEqual(content.review_pack_path(self.root, "wiki/decisions/alpha.md").name, "wiki-decisions-alpha.md")
        self.assertEqual(content.decision_memo_path(self.root, "wiki/decisions/alpha.md").name, "wiki-decisions-alpha.md")
        self.assertEqual(content.sop_draft_path(self.root, "repair-action").name, "repair-action.md")
        self.assertEqual(content.execution_proposals_dir(self.root), self.root / "wiki" / "execution-proposals")
        self.assertEqual(content.execution_proposal_path(self.root, "repair-action").name, "repair-action.md")
        self.assertEqual(content.execution_bundles_dir(self.root), self.root / "output" / "control" / "execution-bundles")
        self.assertEqual(content.execution_bundle_path(self.root, "repair-action").name, "repair-action.json")
        self.assertEqual(content.execution_receipts_dir(self.root), self.root / "output" / "control" / "execution-receipts")
        self.assertEqual(content.execution_receipt_path(self.root, "repair-action").name, "repair-action.json")

    def test_render_source_page_keeps_llm_marker_and_adds_deterministic_preview(self) -> None:
        entry = {
            "id": "source-alpha",
            "title": "Alpha Source",
            "source_type": "note-drop",
            "original_path": "/tmp/alpha.md",
            "stored_path": "raw/inbox/alpha.md",
            "imported_at": "2026-01-01T00:00:00+00:00",
            "sha256": "sha-alpha",
        }
        preview = "\n".join(
            [
                "# Alpha Source",
                "",
                "## Capture Metadata",
                "- Captured at: `2026-01-01T00:00:00+00:00`",
                "",
                "## Captured Note",
                "# FAST-LIO2 Integration",
                "- Replace slam_toolbox with LiDAR-IMU odometry.",
            ]
        )

        rendered = content.render_source_page_with_state(
            entry,
            preview,
            "2026-01-01T00:01:00+00:00",
            concepts=[],
            existing_page="",
        )

        self.assertIn("- Pending LLM summary.", rendered)
        self.assertIn("- Deterministic preview: Alpha Source", rendered)
        self.assertIn("- Deterministic preview: FAST-LIO2 Integration", rendered)

    def test_ingest_source_writes_raw_added_runtime_history(self) -> None:
        sample = self.root / "sample.md"
        sample.write_text("# Runtime Source\n\nNew material.\n", encoding="utf-8")

        entry = content.ingest_source(self.root, str(sample), title="Runtime Source")

        history = state.load_runtime_history(self.root)
        self.assertEqual(history[-1]["event_type"], "raw-added")
        self.assertEqual(history[-1]["entry_id"], entry["id"])
        self.assertEqual(history[-1]["source_ids"], [entry["id"]])
        self.assertEqual(history[-1]["stored_path"], entry["stored_path"])

    def test_routing_lookup_and_rewrite_candidate_helpers(self) -> None:
        self.assertEqual(content.routing_snapshot_for_protocol({}, "ops"), {})
        direct = {"protocol": "ops", "title": "Ops"}
        self.assertEqual(content.routing_snapshot_for_protocol(direct, "ops"), direct)
        nested = {"protocol": "general", "protocol_snapshots": [{"protocol": "research", "title": "Research"}]}
        self.assertEqual(content.routing_snapshot_for_protocol(nested, "research"), {"protocol": "research", "title": "Research"})
        self.assertEqual(content.routing_snapshot_for_protocol(nested, "product"), {})

        entries = [
            {"id": "entry-a", "stored_path": "raw/inbox/a.md", "title": "A"},
            {"stored_path": "raw/inbox/missing-id.md"},
        ]
        by_id, by_path = content.entry_lookup_maps(entries)
        self.assertEqual(list(by_id), ["entry-a"])
        self.assertEqual(by_path["raw/inbox/a.md"], "entry-a")
        self.assertEqual(by_path["wiki/sources/entry-a.md"], "entry-a")
        self.assertEqual(
            content.entry_ids_from_paths(by_path, ["raw/inbox/a.md", "wiki/sources/entry-b.md", "raw/inbox/a.md"]),
            ["entry-a", "entry-b"],
        )

        candidate = (
            utils.render_frontmatter(
                {
                    "id": "concept-alpha",
                    "kind": "concept",
                    "source_signature": "sig-1",
                    "source_pages": ["wiki/sources/a.md"],
                }
            )
            + "\n\n# Alpha\n"
        )
        content._validate_rewrite_candidate_markdown(candidate, "alpha", "sig-1", ["wiki/sources/a.md"])

        with self.assertRaises(RuntimeError):
            content._validate_rewrite_candidate_markdown(candidate.replace("concept-alpha", "concept-beta"), "alpha", "sig-1", ["wiki/sources/a.md"])
        with self.assertRaises(RuntimeError):
            content._validate_rewrite_candidate_markdown(candidate.replace('"concept"', '"derived"'), "alpha", "sig-1", ["wiki/sources/a.md"])
        with self.assertRaises(RuntimeError):
            content._validate_rewrite_candidate_markdown(candidate, "alpha", "sig-2", ["wiki/sources/a.md"])
        with self.assertRaises(RuntimeError):
            content._validate_rewrite_candidate_markdown(
                utils.render_frontmatter({"id": "concept-alpha", "kind": "concept", "source_signature": "sig-1", "source_pages": "bad"})
                + "\n\n# Alpha\n",
                "alpha",
                "sig-1",
                ["wiki/sources/a.md"],
            )
        with self.assertRaises(RuntimeError):
            content._validate_rewrite_candidate_markdown(candidate, "alpha", "sig-1", ["wiki/sources/b.md"])

        concept_path = self.root / "wiki" / "concepts" / "alpha.md"
        self._write_markdown(
            concept_path,
            {
                "id": "concept-alpha",
                "kind": "concept",
                "source_signature": "sig-1",
                "source_pages": ["wiki/sources/a.md"],
            },
            "# Alpha\n\n## Summary\n- stable\n",
        )
        proposal = {"slug": "alpha", "candidate_markdown": candidate, "source_signature": "sig-1", "target_path": "wiki/concepts/alpha.md"}
        self.assertTrue(content.rewrite_proposal_candidate_is_current(self.root, proposal))

        self._write_markdown(
            concept_path,
            {
                "id": "concept-alpha",
                "kind": "concept",
                "source_signature": "sig-2",
                "source_pages": ["wiki/sources/a.md"],
            },
            "# Alpha\n\n## Summary\n- changed\n",
        )
        self.assertFalse(content.rewrite_proposal_candidate_is_current(self.root, proposal))
        self.assertFalse(content.rewrite_proposal_candidate_is_current(self.root, {"slug": "", "candidate_markdown": ""}))

    def test_concept_page_requires_compile_when_render_signature_changes(self) -> None:
        self._write_markdown(
            self.root / "wiki" / "sources" / "entry-a.md",
            {"id": "entry-a", "kind": "source", "title": "MCP Runtime", "status": "active"},
            "# MCP Runtime\n\n## Summary\n- MCP keeps tools and prompts structured across clients.\n",
        )
        record = {
            "slug": "mcp",
            "title": "MCP",
            "root": self.root,
            "entry_ids": ["entry-a"],
            "entries": [{"id": "entry-a", "title": "MCP Runtime"}],
            "source_signature": "source-sig",
            "record_lookup": {},
        }
        concept_path = self.root / "wiki" / "concepts" / "mcp.md"
        concept_path.parent.mkdir(parents=True, exist_ok=True)
        concept_path.write_text(
            utils.render_frontmatter(
                {
                    "id": "concept-mcp",
                    "kind": "concept",
                    "title": "MCP",
                    "source_pages": ["wiki/sources/entry-a.md"],
                    "source_signature": "source-sig",
                    "render_signature": "legacy-render-signature",
                    "generated_by": "aiwiki-compile",
                    "hardness": "hard",
                }
            )
            + "\n\n# MCP\n",
            encoding="utf-8",
        )

        self.assertTrue(queries.concept_page_requires_compile(self.root, record))

    def test_render_concept_page_replaces_placeholder_summary_and_restores_hardness(self) -> None:
        self._write_markdown(
            self.root / "wiki" / "sources" / "entry-a.md",
            {"id": "entry-a", "kind": "source", "title": "MCP Runtime", "status": "active"},
            "# MCP Runtime\n\n## Summary\n- MCP keeps tools, prompts, and context envelopes structured across clients.\n",
        )
        record = {
            "slug": "mcp",
            "title": "MCP",
            "root": self.root,
            "entry_ids": ["entry-a"],
            "entries": [{"id": "entry-a", "title": "MCP Runtime"}],
            "source_signature": "source-sig",
            "record_lookup": {},
            "related_slugs": [],
        }
        existing_page = (
            utils.render_frontmatter(
                {
                    "id": "concept-mcp",
                    "kind": "concept",
                    "title": "MCP",
                    "source_pages": ["wiki/sources/entry-a.md"],
                    "source_signature": "source-sig",
                    "render_signature": "legacy-render-signature",
                    "generated_by": "aiwiki-compile",
                }
            )
            + "\n\n"
            + "# MCP\n\n"
            + "## Summary\n"
            + "- This concept currently appears in `1` source page(s).\n"
            + "- Use the linked source pages below to deepen or revise this synthesis.\n"
        )

        rendered = content.render_concept_page(record, "2026-04-16T00:00:00+00:00", existing_page)
        frontmatter = content.parse_frontmatter(rendered)
        summary = content.preserved_section(rendered, "Summary", "").strip()

        self.assertEqual(frontmatter.get("hardness"), "soft")
        self.assertIn("wiki/sources/entry-a.md", summary)
        self.assertIn("MCP keeps tools, prompts, and context envelopes structured across clients.", summary)
        self.assertNotIn("This concept currently appears in", summary)

    def test_low_risk_target_and_quality_signal_helpers(self) -> None:
        sample = self.root / "sample.md"
        sample.write_text("# Transformer Scaling\n\nIncrease throughput.\n", encoding="utf-8")
        entry = content.ingest_source(self.root, str(sample), title="Transformer Scaling")
        app_compile.compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))
        valid_action = {
            "active": True,
            "source_ids": [entry["id"]],
            "concept_slugs": [concept_slug],
            "primary_path": f"wiki/sources/{entry['id']}.md",
            "secondary_path": f"wiki/concepts/{concept_slug}.md",
        }
        self.assertEqual(content.validate_low_risk_action_targets(self.root, valid_action), (entry["id"], concept_slug))

        with self.assertRaises(RuntimeError):
            content.validate_low_risk_action_targets(self.root, {**valid_action, "active": False})
        with self.assertRaises(RuntimeError):
            content.validate_low_risk_action_targets(self.root, {"active": True, "source_ids": [], "concept_slugs": []})
        with self.assertRaises(RuntimeError):
            content.validate_low_risk_action_targets(self.root, {**valid_action, "source_ids": ["missing-source"]})
        with self.assertRaises(RuntimeError):
            content.validate_low_risk_action_targets(self.root, {**valid_action, "primary_path": "wiki/sources/missing.md"})
        with self.assertRaises(RuntimeError):
            content.validate_low_risk_action_targets(self.root, {**valid_action, "secondary_path": "wiki/concepts/missing.md"})

        wrong_primary = self.root / "wiki" / "derived" / f"{entry['id']}.md"
        self._write_markdown(wrong_primary, {"kind": "derived"}, "# Wrong Primary\n")
        with self.assertRaises(RuntimeError):
            content.validate_low_risk_action_targets(self.root, {**valid_action, "primary_path": f"wiki/derived/{entry['id']}.md"})

        wrong_secondary = self.root / "wiki" / "decisions" / f"{concept_slug}.md"
        self._write_markdown(wrong_secondary, {"kind": "decision"}, "# Wrong Secondary\n")
        with self.assertRaises(RuntimeError):
            content.validate_low_risk_action_targets(self.root, {**valid_action, "secondary_path": f"wiki/decisions/{concept_slug}.md"})

        ready_source = self.root / "wiki" / "sources" / "ready.md"
        self._write_markdown(
            ready_source,
            {"kind": "source", "title": "Ready Source", "last_compiled_at": "2025-01-01T00:00:00+00:00"},
            "# Ready Source\n\n## Summary\n- Revenue increase but unknown durability.\n",
        )
        negative_source = self.root / "wiki" / "sources" / "negative.md"
        self._write_markdown(
            negative_source,
            {"kind": "source", "title": "Negative Source", "last_compiled_at": "2024-10-01T00:00:00+00:00"},
            "# Negative Source\n\n## Summary\n- Revenue decrease as costs rise.\n",
        )
        placeholder_source = self.root / "wiki" / "sources" / "placeholder.md"
        self._write_markdown(
            placeholder_source,
            {"kind": "source", "title": "Placeholder Source", "last_compiled_at": "2025-01-10T00:00:00+00:00"},
            "# Placeholder Source\n\n## Summary\n- Pending LLM summary.\n",
        )

        missing_context = content.load_source_page_context(self.root, "wiki/sources/missing.md")
        ready_context = content.load_source_page_context(self.root, "wiki/sources/ready.md")
        placeholder_context = content.load_source_page_context(self.root, "wiki/sources/placeholder.md")
        negative_context = content.load_source_page_context(self.root, "wiki/sources/negative.md")
        self.assertEqual(missing_context["status"], "missing")
        self.assertEqual(placeholder_context["status"], "placeholder")
        self.assertEqual(ready_context["status"], "ready")

        conflicts = content.detect_concept_conflict_signals([ready_context, negative_context])
        self.assertEqual(conflicts[0]["label"], "increase-vs-decrease")
        gaps = content.detect_concept_gap_signals([missing_context, placeholder_context, ready_context])
        self.assertEqual([gap["kind"] for gap in gaps], ["missing-source-page", "pending-source-summary", "evidence-gap"])

        self.assertEqual(content.concept_source_freshness_score([], compiled_at="bad"), 50)
        self.assertEqual(content.concept_source_freshness_score([{"last_compiled_at": ""}], compiled_at="2025-02-01T00:00:00+00:00"), 50)
        self.assertEqual(
            content.concept_source_freshness_score(
                [{"last_compiled_at": "2025-01-31T12:00:00+00:00"}],
                compiled_at="2025-02-01T00:00:00+00:00",
            ),
            100,
        )
        self.assertEqual(
            content.concept_source_freshness_score(
                [{"last_compiled_at": "2025-01-27T00:00:00+00:00"}],
                compiled_at="2025-02-01T00:00:00+00:00",
            ),
            85,
        )
        self.assertEqual(
            content.concept_source_freshness_score(
                [{"last_compiled_at": "2025-01-01T00:00:00+00:00"}],
                compiled_at="2025-02-01T00:00:00+00:00",
            ),
            55,
        )
        self.assertEqual(
            content.concept_source_freshness_score(
                [{"last_compiled_at": "2024-12-01T00:00:00+00:00"}],
                compiled_at="2025-02-01T00:00:00+00:00",
            ),
            55,
        )
        self.assertEqual(
            content.concept_source_freshness_score(
                [{"last_compiled_at": "2024-01-01T00:00:00+00:00"}],
                compiled_at="2025-02-01T00:00:00+00:00",
            ),
            35,
        )

        metrics = content.concept_quality_metrics(
            ["wiki/sources/ready.md", "wiki/sources/placeholder.md", "wiki/sources/missing.md"],
            [ready_context, placeholder_context, missing_context],
            conflicts,
            gaps,
            compiled_at="2025-02-01T00:00:00+00:00",
        )
        self.assertEqual(metrics["ready_sources"], 1)
        self.assertEqual(metrics["placeholder_sources"], 1)
        self.assertEqual(metrics["missing_sources"], 1)
        self.assertEqual(content.concept_quality_band(90), "strong")
        self.assertEqual(content.concept_quality_band(75), "stable")
        self.assertEqual(content.concept_quality_band(60), "watch")
        self.assertEqual(content.concept_quality_band(30), "fragile")
        self.assertEqual(content.normalize_concept_hardness("HARD"), "hard")
        self.assertEqual(content.normalize_concept_hardness("unknown"), "soft")
        self.assertEqual(content.concept_rewrite_priority(6, [], [], quality_score=80), "high")
        self.assertEqual(content.concept_rewrite_priority(3, [], [], quality_score=80), "medium")
        self.assertEqual(content.concept_rewrite_priority(1, [], [], quality_score=80), "low")
        self.assertEqual(content.concept_rewrite_priority(0, [], [], quality_score=90), "")
        strategy = content.concept_rewrite_strategy(
            {
                "issues": [
                    "placeholder-summary",
                    "conflicting-source-signals",
                    "evidence-gap",
                    "single-source",
                    "no-related-concepts",
                    "merge-boundary",
                ]
            }
        )
        self.assertIn("grounded synthesis", strategy)
        self.assertIn("冲突来源", strategy)
        self.assertIn("证据缺口", strategy)
        self.assertIn("manual-link state", content.proposal_rollback_summary({"safe_apply_preview": {"apply_mode": "manual-link-state"}}))
        self.assertIn("citation_snapshots", content.proposal_rollback_summary({"safe_apply_preview": {"apply_mode": "citation-snapshot-refresh"}}))
        self.assertIn("人工恢复", content.proposal_rollback_summary({}))

    def test_proposal_dependency_planner_and_concept_quality_helpers(self) -> None:
        self.assertEqual(
            content.proposal_impact_score(
                {
                    "priority": "high",
                    "focus_score": 3,
                    "occurrences": 2,
                    "status": "accepted",
                    "escalation_candidate": "true",
                    "overdue_review": "true",
                    "policy_decision": "allow",
                },
                {},
            ),
            98,
        )
        self.assertEqual(content.proposal_dependency_weight({"proposal_kind": "split-concept", "impact_score": 7}), (5, 7))
        self.assertTrue(content.proposals_overlap({"target_paths": ["a"]}, {"target_paths": ["a"]}))
        self.assertTrue(content.proposals_overlap({"source_ids": ["s1"]}, {"source_ids": ["s1"]}))
        self.assertTrue(content.proposals_overlap({"concept_slugs": ["c1"]}, {"concept_slugs": ["c1"]}))
        self.assertTrue(content.proposals_overlap({"component_id": "comp"}, {"component_id": "comp"}))
        self.assertFalse(content.proposals_overlap({"target_paths": ["a"]}, {"target_paths": ["b"]}))

        proposals = [
            {
                "action_id": "expand-alpha",
                "title": "Expand Alpha",
                "proposal_kind": "expand-concept",
                "impact_score": 10,
                "priority": "high",
                "priority_score": 12,
                "target_paths": ["wiki/concepts/alpha.md"],
                "status": "accepted",
                "risk": "low",
                "command_hint": "apply-action expand-alpha",
                "next_step": "Expand first",
            },
            {
                "action_id": "repair-alpha",
                "title": "Repair Alpha",
                "proposal_kind": "manual-repair",
                "impact_score": 3,
                "priority": "medium",
                "priority_score": 8,
                "target_paths": ["wiki/concepts/alpha.md"],
                "status": "proposed",
                "command_hint": "apply-action repair-alpha",
                "next_step": "Repair second",
            },
        ]
        content.derive_proposal_dependencies(proposals)
        self.assertEqual(proposals[0]["depends_on"], [])
        self.assertEqual(proposals[1]["depends_on"], ["expand-alpha"])

        state.save_planner_state(
            self.root,
            {
                "version": 1,
                "generated_at": "2025-01-01T00:00:00+00:00",
                "state_path": ".aiwiki/state/planner-state.json",
                "active_protocol": "general",
                "pending_proposals": [],
                "priority_queue": [],
                "dependency_graph": {"nodes": [], "edges": []},
                "next_action": {},
                "executed_actions": [{"action_id": "done-alpha", "title": "Done Alpha"}],
                "counts": {"pending_proposals": 0, "blocked": 0, "unblocked": 0, "executed_actions": 1},
            },
        )
        planner = content.build_planner_state(self.root, proposals, active_protocol="research")
        self.assertEqual(planner["next_action"]["action_id"], "expand-alpha")
        self.assertEqual(planner["counts"]["blocked"], 1)
        self.assertEqual(planner["counts"]["unblocked"], 1)
        self.assertEqual(planner["dependency_graph"]["edges"], [{"from": "repair-alpha", "to": "expand-alpha"}])
        self.assertEqual(planner["executed_actions"], [{"action_id": "done-alpha", "title": "Done Alpha"}])
        self.assertTrue(planner["pending_proposals"][0]["auto_bundle_candidate"])
        self.assertFalse(planner["pending_proposals"][0]["human_required"])
        self.assertTrue(planner["priority_queue"][0]["auto_bundle_candidate"])
        self.assertFalse(planner["priority_queue"][0]["human_required"])
        self.assertFalse(planner["pending_proposals"][1]["auto_bundle_candidate"])
        self.assertTrue(planner["pending_proposals"][1]["human_required"])

        alpha_concept = self.root / "wiki" / "concepts" / "alpha.md"
        beta_concept = self.root / "wiki" / "concepts" / "beta-latency.md"
        self._write_markdown(
            alpha_concept,
            {"kind": "concept", "generated_by": "aiwiki-compile", "id": "concept-alpha"},
            "# Alpha\n\n## Summary\n- This concept currently appears in `wiki/sources/a.md`.\n",
        )
        self._write_markdown(
            beta_concept,
            {"kind": "concept", "generated_by": "aiwiki-compile", "id": "concept-beta-latency"},
            "# Beta\n\n## Summary\n- Stable synthesis.\n",
        )
        self._write_markdown(
            self.root / "wiki" / "sources" / "a.md",
            {"kind": "source", "title": "Source A", "last_compiled_at": "2025-01-10T00:00:00+00:00"},
            "# Source A\n\n## Summary\n- Revenue increase but unknown durability.\n",
        )
        self._write_markdown(
            self.root / "wiki" / "sources" / "b.md",
            {"kind": "source", "title": "Source B", "last_compiled_at": "2024-11-01T00:00:00+00:00"},
            "# Source B\n\n## Summary\n- Revenue decrease as costs rise.\n",
        )
        quality = content.build_concept_quality(
            self.root,
            {
                "compiled_at": "2025-02-01T00:00:00+00:00",
                "health": {"singleton_concept_slugs": ["alpha"]},
                "concept_nodes": [
                    {
                        "slug": "alpha",
                        "title": "Alpha Latency",
                        "source_pages": ["wiki/sources/a.md"],
                        "related_slugs": [],
                        "source_signature": "sig-a",
                        "confidence": "medium",
                        "hardness": "soft",
                    },
                    {
                        "slug": "beta-latency",
                        "title": "Alpha Latency Beta",
                        "source_pages": ["wiki/sources/a.md", "wiki/sources/b.md"],
                        "related_slugs": ["alpha"],
                        "source_signature": "sig-b",
                        "confidence": "high",
                        "hardness": "hard",
                    },
                ],
            },
        )
        self.assertEqual(quality["counts"]["placeholders"], 1)
        self.assertEqual(quality["counts"]["merge_candidates"], 1)
        self.assertGreaterEqual(quality["counts"]["rewrite_candidates"], 1)
        self.assertEqual(quality["counts"]["soft_hardness"], 1)
        self.assertEqual(quality["counts"]["hard_hardness"], 1)
        self.assertEqual(quality["counts"]["medium_or_hard"], 1)
        self.assertEqual(quality["placeholder_slugs"], ["alpha"])
        self.assertTrue(any(record["slug"] == "alpha" for record in quality["weak_concepts"]))
        self.assertEqual(quality["hard_concepts"][0]["slug"], "beta-latency")
        self.assertTrue(any(candidate["slug"] == "alpha" for candidate in quality["rewrite_candidates"]))
        self.assertTrue(any(signal["label"] == "increase-vs-decrease" for signal in quality["conflict_signals"]))
        self.assertTrue(any(signal["kind"] == "evidence-gap" for signal in quality["gap_signals"]))


    # ------------------------------------------------------------------
    # Causal links
    # ------------------------------------------------------------------

    def test_parse_causal_links_valid(self) -> None:
        fm = {
            "causal_links": [
                "memory|enables|reason A",
                "protocol|constrains|reason B",
            ]
        }
        result = content.parse_causal_links(fm)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["target"], "memory")
        self.assertEqual(result[0]["relation"], "enables")
        self.assertEqual(result[1]["relation"], "constrains")

    def test_parse_causal_links_filters_invalid(self) -> None:
        fm = {
            "causal_links": [
                "memory|enables|ok",
                "memory|INVALID_RELATION|bad",
                "no-pipe-here",
                42,
            ]
        }
        result = content.parse_causal_links(fm)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["relation"], "enables")

    def test_parse_causal_links_empty(self) -> None:
        self.assertEqual(content.parse_causal_links({}), [])
        self.assertEqual(content.parse_causal_links({"causal_links": []}), [])

    def test_render_concept_causal_lines_empty(self) -> None:
        lines = content.render_concept_causal_lines([], {})
        self.assertEqual(len(lines), 1)
        self.assertIn("没有显式因果关系", lines[0])

    def test_render_concept_causal_lines_with_data(self) -> None:
        links = [
            {"target": "memory", "relation": "enables", "evidence": "reason"},
            {"target": "protocol", "relation": "constrains", "evidence": "reason2"},
        ]
        lookup = {
            "memory": {"slug": "memory", "title": "Memory"},
            "protocol": {"slug": "protocol", "title": "Protocol"},
        }
        lines = content.render_concept_causal_lines(links, lookup)
        joined = "\n".join(lines)
        self.assertIn("Memory", joined)
        self.assertIn("Protocol", joined)

    def test_machine_memory_concept_input_signature_includes_causal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            concept_dir = root / "wiki" / "concepts"
            concept_dir.mkdir(parents=True)
            # With causal links
            (concept_dir / "x.md").write_text(
                '---\nid: concept-x\ntitle: X\ncausal_links:\n'
                '  - "y|causes|evidence"\n---\nbody\n',
                encoding="utf-8",
            )
            sig_with = content.machine_memory_concept_input_signature(
                root, {"slug": "x", "title": "X", "source_signature": "s", "source_pages": [], "related_slugs": [], "entry_ids": []}
            )
            # Without causal links
            (concept_dir / "x.md").write_text(
                "---\nid: concept-x\ntitle: X\n---\nbody\n",
                encoding="utf-8",
            )
            sig_without = content.machine_memory_concept_input_signature(
                root, {"slug": "x", "title": "X", "source_signature": "s", "source_pages": [], "related_slugs": [], "entry_ids": []}
            )
            self.assertNotEqual(sig_with, sig_without)


if __name__ == "__main__":
    unittest.main()
