from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import aiwiki.app_state as state
import aiwiki.app_utils as utils
from aiwiki.app_protocol import ensure_layout


class AppStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def test_json_document_helpers_handle_missing_invalid_and_jsonl_noise(self) -> None:
        document_path = self.root / "tmp" / "doc.json"
        self.assertEqual(state.load_json_document(document_path), {})

        state.save_json_document(document_path, {"alpha": 1})
        self.assertEqual(state.load_json_document(document_path), {"alpha": 1})

        document_path.write_text("{bad json", encoding="utf-8")
        self.assertEqual(state.load_json_document(document_path), {})

        jsonl_path = self.root / "tmp" / "events.jsonl"
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl_path.write_text('{"a":1}\n\nnot-json\n["skip"]\n{"b":2}\n', encoding="utf-8")
        self.assertEqual(state.load_jsonl_documents(jsonl_path), [{"a": 1}, {"b": 2}])

    def test_strict_loaders_raise_corrupt_state_error(self) -> None:
        document_path = self.root / "tmp" / "doc.json"
        # Missing file is allowed (returns {}) — strict only rejects corrupt content.
        self.assertEqual(state.load_json_document_strict(document_path), {})

        document_path.parent.mkdir(parents=True, exist_ok=True)
        document_path.write_text('{"alpha": 1}', encoding="utf-8")
        self.assertEqual(state.load_json_document_strict(document_path), {"alpha": 1})

        document_path.write_text("{bad json", encoding="utf-8")
        with self.assertRaises(state.CorruptStateError) as ctx:
            state.load_json_document_strict(document_path)
        self.assertEqual(ctx.exception.path, document_path)
        self.assertIn("json decode failed", ctx.exception.reason)

        document_path.write_text('["not", "an", "object"]', encoding="utf-8")
        with self.assertRaises(state.CorruptStateError) as ctx:
            state.load_json_document_strict(document_path)
        self.assertIn("expected JSON object", ctx.exception.reason)

        jsonl_path = self.root / "tmp" / "events.jsonl"
        self.assertEqual(state.load_jsonl_documents_strict(jsonl_path), [])

        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl_path.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
        self.assertEqual(state.load_jsonl_documents_strict(jsonl_path), [{"a": 1}, {"b": 2}])

        jsonl_path.write_text('{"a":1}\nnot-json\n{"b":2}\n', encoding="utf-8")
        with self.assertRaises(state.CorruptStateError) as ctx:
            state.load_jsonl_documents_strict(jsonl_path)
        self.assertEqual(ctx.exception.line_number, 2)

        jsonl_path.write_text('{"a":1}\n["skip"]\n', encoding="utf-8")
        with self.assertRaises(state.CorruptStateError) as ctx:
            state.load_jsonl_documents_strict(jsonl_path)
        self.assertEqual(ctx.exception.line_number, 2)
        self.assertIn("expected JSON object", ctx.exception.reason)

    def test_best_effort_loaders_log_warning_on_corruption(self) -> None:
        document_path = self.root / "tmp" / "warn.json"
        document_path.parent.mkdir(parents=True, exist_ok=True)
        document_path.write_text("{bad json", encoding="utf-8")
        with self.assertLogs("aiwiki.app_state", level="WARNING") as cm:
            self.assertEqual(state.load_json_document(document_path), {})
        self.assertTrue(any("corrupt JSON state" in msg for msg in cm.output))

        jsonl_path = self.root / "tmp" / "warn.jsonl"
        jsonl_path.write_text('{"a":1}\nnot-json\n["skip"]\n{"b":2}\n', encoding="utf-8")
        with self.assertLogs("aiwiki.app_state", level="WARNING") as cm:
            result = state.load_jsonl_documents(jsonl_path)
        self.assertEqual(result, [{"a": 1}, {"b": 2}])
        joined = "\n".join(cm.output)
        self.assertIn("corrupt JSONL line", joined)
        self.assertIn("non-object JSONL record", joined)

    def test_load_json_document_returns_empty_when_top_level_not_object(self) -> None:
        document_path = self.root / "tmp" / "nonobject.json"
        document_path.parent.mkdir(parents=True, exist_ok=True)
        document_path.write_text('["a", "b"]', encoding="utf-8")
        with self.assertLogs("aiwiki.app_state", level="WARNING") as cm:
            self.assertEqual(state.load_json_document(document_path), {})
        self.assertTrue(any("non-object JSON top-level" in msg for msg in cm.output))

    def test_append_runtime_history_writes_universal_audit(self) -> None:
        event = {
            "event_type": "nightly",
            "recorded_at": "2026-04-26T10:02:00+00:00",
            "trace_id": "trace-runtime",
            "protocol": "research",
        }

        state.append_runtime_history(self.root, event)
        state.append_runtime_history(self.root, event)

        history_lines = (self.root / ".aiwiki/state/runtime-history.jsonl").read_text(encoding="utf-8").splitlines()
        audit_records = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        history_records = [json.loads(line) for line in history_lines if line.strip()]
        self.assertEqual(history_records, [event, event])
        self.assertEqual(len(audit_records), 2)
        self.assertEqual(audit_records[0]["source_stream"], "runtime_history")
        self.assertEqual(audit_records[0]["source_ref"], ".aiwiki/state/runtime-history.jsonl#L1")
        self.assertEqual(audit_records[0]["event_type"], "nightly")
        self.assertEqual(audit_records[0]["occurred_at"], "2026-04-26T10:02:00+00:00")
        self.assertEqual(audit_records[0]["trace_id"], "trace-runtime")
        self.assertEqual(audit_records[0]["subject"], {"kind": "nightly", "id": ""})
        self.assertFalse(audit_records[0]["revert_supported"])
        self.assertEqual(audit_records[1]["source_ref"], ".aiwiki/state/runtime-history.jsonl#L2")
        self.assertNotEqual(audit_records[0]["audit_event_id"], audit_records[1]["audit_event_id"])

    def test_build_state_loaders_normalize_and_fallback(self) -> None:
        self._write_json(
            state.compile_state_path(self.root),
            {
                "dirty_source_ids": "bad",
                "phase_summary": [],
            },
        )
        self.assertEqual(state.load_compile_state(self.root), state.default_compile_state())

        self._write_json(
            state.compile_state_path(self.root),
            {
                "version": 2,
                "compiled_at": "2025-01-01T00:00:00+00:00",
                "manifest_entry_count": 3,
                "dirty_source_ids": ["alpha", "", 3],
                "clean_source_ids": ["beta"],
                "dirty_concept_source_ids": ["alpha"],
                "clean_concept_source_ids": ["beta"],
                "dirty_concept_slugs": ["latency", ""],
                "clean_concept_slugs": ["cost"],
                "dirty_machine_memory_source_ids": ["alpha"],
                "clean_machine_memory_source_ids": ["beta"],
                "dirty_machine_memory_concept_slugs": ["latency"],
                "clean_machine_memory_concept_slugs": ["cost"],
                "machine_memory_core_reused": True,
                "dirty_ranking_source_ids": ["alpha"],
                "clean_ranking_source_ids": ["beta"],
                "dirty_ranking_concept_slugs": ["latency"],
                "clean_ranking_concept_slugs": ["cost"],
                "dirty_output_pack_groups": ["review_packs"],
                "clean_output_pack_groups": ["decision_memos"],
                "dirty_domain_pilot_protocols": ["research"],
                "clean_domain_pilot_protocols": ["ops"],
                "dirty_index_artifacts": ["wiki/indexes/index.md"],
                "clean_index_artifacts": ["wiki/indexes/sources.md"],
                "dirty_maintenance_artifacts": ["wiki/indexes/log.md"],
                "clean_maintenance_artifacts": ["wiki/indexes/aging-report.md"],
                "drift_warnings": [{"kind": "missing-source"}, "skip"],
                "phase_summary": [{"phase": "compile"}, "skip"],
            },
        )
        compile_state = state.load_compile_state(self.root)
        self.assertEqual(compile_state["manifest_entry_count"], 3)
        self.assertEqual(compile_state["dirty_source_ids"], ["alpha", "3"])
        self.assertTrue(compile_state["machine_memory_core_reused"])
        self.assertEqual(compile_state["drift_warnings"], [{"kind": "missing-source"}])
        self.assertEqual(compile_state["phase_summary"], [{"phase": "compile"}])

        self._write_json(state.concept_build_state_path(self.root), {"version": 1, "entry_records": {}})
        self.assertEqual(state.load_concept_build_state(self.root), state.default_concept_build_state())

        self._write_json(
            state.concept_build_state_path(self.root),
            {
                "version": 2,
                "generated_at": "2025-01-01T00:00:00+00:00",
                "entry_records": {
                    "entry-a": {"input_signature": "sig-a", "terms": ["Latency", ""]},
                    "entry-b": {"input_signature": "sig-b", "terms": "bad"},
                    "": {"input_signature": "skip", "terms": ["x"]},
                },
            },
        )
        concept_state = state.load_concept_build_state(self.root)
        self.assertEqual(concept_state["entry_records"], {"entry-a": {"input_signature": "sig-a", "terms": ["Latency"]}})

        self._write_json(state.machine_memory_build_state_path(self.root), {"source_records": []})
        self.assertEqual(state.load_machine_memory_build_state(self.root), state.default_machine_memory_build_state())

        self._write_json(
            state.machine_memory_build_state_path(self.root),
            {
                "version": 2,
                "generated_at": "2025-01-01T00:00:00+00:00",
                "source_records": {"entry-a": {"input_signature": "sig-a"}, "": {"input_signature": "skip"}},
                "concept_records": {"latency": {"input_signature": "sig-b"}, "": {"input_signature": "skip"}},
            },
        )
        memory_build = state.load_machine_memory_build_state(self.root)
        self.assertEqual(memory_build["source_records"], {"entry-a": {"input_signature": "sig-a"}})
        self.assertEqual(memory_build["concept_records"], {"latency": {"input_signature": "sig-b"}})

        self._write_json(state.ranking_build_state_path(self.root), {"source_records": []})
        self.assertEqual(state.load_ranking_build_state(self.root), state.default_ranking_build_state())

        self._write_json(
            state.ranking_build_state_path(self.root),
            {
                "version": 3,
                "generated_at": "2025-01-01T00:00:00+00:00",
                "source_records": {
                    "entry-a": {
                        "input_signature": "sig-a",
                        "summary_or_preview": "summary",
                        "concept_terms": ["Latency", ""],
                    },
                    "entry-b": {"input_signature": "sig-b", "summary_or_preview": "bad", "concept_terms": "nope"},
                },
                "concept_records": {
                    "latency": {
                        "input_signature": "sig-c",
                        "title": "Latency",
                        "path": "wiki/concepts/latency.md",
                        "source_pages": ["wiki/sources/entry-a.md", ""],
                        "content": "Concept body",
                    },
                    "cost": {"input_signature": "sig-d", "source_pages": "bad"},
                },
            },
        )
        ranking_state = state.load_ranking_build_state(self.root)
        self.assertEqual(list(ranking_state["source_records"]), ["entry-a"])
        self.assertEqual(ranking_state["concept_records"]["latency"]["source_pages"], ["wiki/sources/entry-a.md"])

    def test_output_material_archive_and_runtime_state_helpers(self) -> None:
        self._write_json(state.output_pack_build_state_path(self.root), {"group_records": []})
        self.assertEqual(state.load_output_pack_build_state(self.root), state.default_output_pack_build_state())

        self._write_json(
            state.output_pack_build_state_path(self.root),
            {
                "version": 2,
                "generated_at": "2025-01-01T00:00:00+00:00",
                "active_protocol": "research",
                "group_records": {"review_packs": {"input_signature": "sig"}},
                "lifecycle_summary": {"decision": 1},
                "review_packs": [{"path": "output/review.md"}, "skip"],
                "decision_memos": [{"path": "output/memo.md"}],
                "sop_drafts": [{"path": "output/sop.md"}],
                "counts": {
                    "review_packs": 1,
                    "decision_memos": 2,
                    "sop_drafts": 3,
                    "execution_proposal_sops": 4,
                },
            },
        )
        output_state = state.load_output_pack_build_state(self.root)
        self.assertEqual(output_state["active_protocol"], "research")
        self.assertEqual(output_state["review_packs"], [{"path": "output/review.md"}])
        self.assertEqual(output_state["counts"]["execution_proposal_sops"], 4)

        self._write_json(state.domain_pilot_build_state_path(self.root), {"protocol_records": []})
        self.assertEqual(state.load_domain_pilot_build_state(self.root), state.default_domain_pilot_build_state())

        self._write_json(
            state.domain_pilot_build_state_path(self.root),
            {
                "version": 2,
                "generated_at": "2025-01-01T00:00:00+00:00",
                "active_protocol": "ops",
                "protocol_records": {"ops": {"input_signature": "sig"}},
                "scorecards": [{"path": "output/agents/ops.md"}, "skip"],
            },
        )
        domain_state = state.load_domain_pilot_build_state(self.root)
        self.assertEqual(domain_state["protocol_records"], {"ops": {"input_signature": "sig"}})
        self.assertEqual(domain_state["scorecards"], [{"path": "output/agents/ops.md"}])

        self._write_json(state.material_state_path(self.root), {"entries": {}})
        self.assertEqual(state.load_material_state(self.root), state.default_material_state())
        self._write_json(state.material_state_path(self.root), {"version": 2, "entries": [{"entry_id": "a"}, "skip"]})
        self.assertEqual(state.load_material_state(self.root)["entries"], [{"entry_id": "a"}])

        self._write_json(state.active_corpora_state_path(self.root), {"corpora": {}})
        self.assertEqual(state.load_active_corpora_state(self.root), state.default_active_corpora_state())
        self._write_json(state.active_corpora_state_path(self.root), {"version": 2, "corpora": [{"corpus_id": "a"}, "skip"]})
        self.assertEqual(state.load_active_corpora_state(self.root)["corpora"], [{"corpus_id": "a"}])

        self._write_json(state.material_routing_state_path(self.root), {"entries": {}})
        self.assertEqual(state.load_material_routing_state(self.root), state.default_material_routing_state())
        self._write_json(
            state.material_routing_state_path(self.root),
            {"version": 2, "computed_at": "2025-01-01T00:00:00+00:00", "active_protocol": "ops", "entries": [{"entry_id": "a"}, "skip"]},
        )
        routing_state = state.load_material_routing_state(self.root)
        self.assertEqual(routing_state["active_protocol"], "ops")
        self.assertEqual(routing_state["entries"], [{"entry_id": "a"}])

        self._write_json(state.archive_candidates_state_path(self.root), {"entries": {}})
        self.assertEqual(state.load_archive_candidates_state(self.root), state.default_archive_candidates_state())
        self._write_json(state.archive_candidates_state_path(self.root), {"version": 2, "entries": [{"entry_id": "a"}, "skip"]})
        self.assertEqual(state.load_archive_candidates_state(self.root)["entries"], [{"entry_id": "a"}])

        state.save_material_archive_state(
            self.root,
            {
                "version": 1,
                "entries": [
                    {"entry_id": "a", "active": True},
                    {"entry_id": "b", "active": False},
                    "skip",
                ],
            },
        )
        archive_state = state.load_material_archive_state(self.root)
        self.assertEqual(len(archive_state["entries"]), 2)
        self.assertEqual(list(state.active_material_archive_entries(archive_state)), ["a"])
        self.assertEqual(state.active_archived_material_ids(self.root), {"a"})
        self.assertEqual(state.material_archive_action_id("entry-1"), "archive-entry-1")

    def test_lifecycle_and_runtime_action_states_normalize_and_persist(self) -> None:
        self._write_json(state.knowledge_lifecycle_state_path(self.root), {"entries": {}})
        self.assertEqual(state.load_knowledge_lifecycle_state(self.root), state.default_knowledge_lifecycle_state())

        self._write_json(
            state.knowledge_lifecycle_state_path(self.root),
            {
                "version": 2,
                "generated_at": "2025-01-01T00:00:00+00:00",
                "entries": [{"page_id": "a"}, "skip"],
                "counts": "bad",
            },
        )
        lifecycle_state = state.load_knowledge_lifecycle_state(self.root)
        self.assertEqual(lifecycle_state["entries"], [{"page_id": "a"}])
        self.assertEqual(lifecycle_state["counts"]["total"], 0)

        self._write_json(state.knowledge_lifecycle_override_state_path(self.root), {"entries": {}})
        self.assertEqual(
            state.load_knowledge_lifecycle_override_state(self.root),
            state.default_knowledge_lifecycle_override_state(),
        )
        override_state = state.ensure_knowledge_lifecycle_override_state(self.root)
        self.assertTrue(state.knowledge_lifecycle_override_state_path(self.root).exists())
        self.assertEqual(override_state, state.default_knowledge_lifecycle_override_state())

        active_overrides = state.active_knowledge_lifecycle_overrides(
            {
                "entries": [
                    {"path": "wiki/concepts/a.md", "active": True},
                    {"path": "wiki/concepts/b.md", "active": False},
                    {"active": True},
                ]
            }
        )
        self.assertEqual(list(active_overrides), ["wiki/concepts/a.md"])

        state.save_machine_memory_action_state(self.root, {"version": 1, "actions": [{"id": "a"}, "skip"]})
        self.assertEqual(state.load_machine_memory_action_state(self.root)["actions"], [{"id": "a"}])

        self._write_json(state.planner_state_path(self.root), {"pending_proposals": {}, "priority_queue": []})
        self.assertEqual(state.load_planner_state(self.root), state.default_planner_state())
        self._write_json(
            state.planner_state_path(self.root),
            {
                "version": 2,
                "generated_at": "2025-01-01T00:00:00+00:00",
                "active_protocol": "research",
                "pending_proposals": [{"id": "proposal-a"}, "skip"],
                "priority_queue": [{"action_id": "action-a"}, "skip"],
                "dependency_graph": {"nodes": [{"id": "action-a"}, "skip"], "edges": [{"from": "a", "to": "b"}, "skip"]},
                "next_action": ["bad"],
                "executed_actions": [{"action_id": "done"}, "skip"],
                "counts": {"pending_proposals": 1, "blocked": 2, "unblocked": 3, "executed_actions": 4},
            },
        )
        planner_state = state.load_planner_state(self.root)
        self.assertEqual(planner_state["state_path"], " .aiwiki/state/planner-state.json".strip())
        self.assertEqual(planner_state["next_action"], {})
        self.assertEqual(planner_state["executed_actions"], [{"action_id": "done"}])
        self.assertEqual(planner_state["counts"]["blocked"], 2)

        self._write_json(state.query_route_telemetry_path(self.root), {"entries": {}})
        self.assertEqual(state.load_query_route_telemetry(self.root), state.default_query_route_telemetry())
        self._write_json(
            state.query_route_telemetry_path(self.root),
            {
                "version": 2,
                "updated_at": "2025-01-01T00:00:00+00:00",
                "entries": [{"entry_id": "a"}, "skip"],
                "strategy_counts": {"source-first": "2"},
                "protocol_counts": {"research": "3"},
                "last_entry": ["bad"],
            },
        )
        telemetry_state = state.load_query_route_telemetry(self.root)
        self.assertEqual(telemetry_state["entries"], [{"entry_id": "a"}])
        self.assertEqual(telemetry_state["strategy_counts"], {"source-first": 2})
        self.assertEqual(telemetry_state["last_entry"], {})

        self.assertEqual(state.load_machine_memory(self.root), {})
        self._write_json(state.machine_memory_state_path(self.root), {"digest": "abc"})
        self.assertEqual(state.load_machine_memory(self.root), {"digest": "abc"})

        self._write_json(state.concept_rewrite_state_path(self.root), {"proposals": {}})
        self.assertEqual(state.load_concept_rewrite_state(self.root), state.default_concept_rewrite_state())
        state.save_concept_rewrite_state(self.root, {"version": 1, "proposals": [{"slug": "alpha"}, "skip"]})
        self.assertEqual(state.load_concept_rewrite_state(self.root)["proposals"], [{"slug": "alpha"}])

        self._write_json(state.manual_link_state_path(self.root), {"source_to_concept": {}})
        self.assertEqual(state.load_manual_link_state(self.root), state.default_manual_link_state())
        state.save_manual_link_state(self.root, {"version": 1, "source_to_concept": [{"source_id": "a"}, "skip"]})
        self.assertEqual(state.load_manual_link_state(self.root)["source_to_concept"], [{"source_id": "a"}])


class AppUtilsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_datetime_kind_preview_and_note_metadata_helpers(self) -> None:
        self.assertIsNone(utils.parse_iso_datetime(""))
        self.assertIsNone(utils.parse_iso_datetime("not-a-date"))
        self.assertEqual(utils.parse_iso_datetime("2025-01-01T00:00:00").tzinfo.utcoffset(None).total_seconds(), 0)
        self.assertEqual(utils.parse_iso_datetime("2025-01-01T08:00:00+08:00").hour, 0)

        self.assertEqual(utils.detect_kind(Path("note.md")), "markdown")
        self.assertEqual(utils.detect_kind(Path("note.txt")), "text")
        self.assertEqual(utils.detect_kind(Path("data.json")), "data")
        self.assertEqual(utils.detect_kind(Path("chart.png")), "image")
        self.assertEqual(utils.detect_kind(Path("paper.pdf")), "pdf")
        self.assertEqual(utils.detect_kind(Path("README")), "file")
        self.assertEqual(utils.detect_kind(Path("archive.bin")), "bin")

        self.assertEqual(utils.next_identifier({"entry", "entry-2"}, "entry"), "entry-3")
        inbox = self.root / "raw" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "note.md").write_text("x\n", encoding="utf-8")
        self.assertEqual(utils.next_available_stem(inbox, "note"), "note-2")

        image_path = self.root / "chart.png"
        image_path.write_bytes(b"\x89PNG\r\n")
        self.assertIn("Preview unavailable", utils.read_text_preview(image_path))

        empty_text = self.root / "empty.txt"
        empty_text.write_text("", encoding="utf-8")
        self.assertEqual(utils.read_text_preview(empty_text), "(empty text file)")

        long_text = self.root / "long.txt"
        long_text.write_text("a" * 2000, encoding="utf-8")
        self.assertTrue(utils.read_text_preview(long_text, limit_lines=1, limit_chars=10).endswith("..."))

        note = self.root / "raw" / "inbox" / "note.md"
        note.write_text(
            utils.render_frontmatter(
                {
                    "title": "Weekly Sync",
                    "source_type": "note-drop",
                    "original_path": "inline://note",
                    "note_kind": "transcript",
                }
            )
            + "\n\n# Weekly Sync\n",
            encoding="utf-8",
        )
        self.assertEqual(utils.raw_note_metadata(note)["note_kind"], "transcript")
        self.assertEqual(utils.raw_note_metadata(image_path), {})

    def test_parse_iso_datetime_accepts_z_suffix(self) -> None:
        parsed = utils.parse_iso_datetime("2025-01-01T00:00:00Z")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.tzinfo.utcoffset(None).total_seconds(), 0)
        self.assertEqual(parsed.isoformat(), "2025-01-01T00:00:00+00:00")

    def test_frontmatter_section_and_path_helpers(self) -> None:
        self.assertEqual(utils.parse_scalar('"hello"'), "hello")
        self.assertEqual(utils.parse_scalar('"broken'), '"broken')

        frontmatter = utils.parse_frontmatter(
            "---\n"
            'title: "Alpha"\n'
            "tags:\n"
            '  - "one"\n'
            "invalid line\n"
            "---\n"
            "# Alpha\n"
        )
        self.assertEqual(frontmatter, {"title": "Alpha", "tags": ["one"]})

        self.assertEqual(utils.strip_frontmatter("---\ntitle: x\n---\nbody\n"), "body")
        self.assertEqual(utils.strip_frontmatter("---\ntitle: x\nbody\n"), "---\ntitle: x\nbody\n")

        self.assertIn("## Notes", utils.upsert_markdown_section("Intro", "Notes", "Body"))
        self.assertIn("Updated", utils.upsert_markdown_section("## Notes\nOld\n", "Notes", "Updated"))
        self.assertEqual(utils.upsert_markdown_section("", "Notes", "Body"), "## Notes\nBody\n")

        self.assertEqual(utils.normalize_workspace_path("../raw/file.md;"), "raw/file.md")
        self.assertEqual(utils.normalize_workspace_path("./wiki/sources/a.md,"), "wiki/sources/a.md")

    def test_provenance_and_citation_helpers(self) -> None:
        raw_path = self.root / "raw" / "note.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text("raw evidence\n", encoding="utf-8")

        source_path = self.root / "wiki" / "sources" / "alpha.md"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(
            utils.render_frontmatter({"source_sha256": "sha-frontmatter"}) + "\n\n# Alpha\n\n- SHA256: `sha-inline`\n",
            encoding="utf-8",
        )

        markdown = (
            utils.render_frontmatter({"citations": ["wiki/sources/alpha.md", "raw/note.txt", "wiki/sources/missing.md"]})
            + "\n\nSee `wiki/sources/alpha.md` and `raw/note.txt`.\n"
        )
        paths = utils.extract_provenance_paths(self.root, markdown)
        self.assertEqual(paths, ["wiki/sources/alpha.md", "raw/note.txt"])

        self.assertEqual(utils.evidence_path_digest(self.root, "wiki/sources/alpha.md"), "sha-frontmatter")
        self.assertTrue(utils.evidence_path_digest(self.root, "raw/note.txt"))
        self.assertEqual(utils.evidence_path_digest(self.root, "raw/missing.txt"), "")

        snapshots = utils.build_citation_snapshots(
            self.root,
            ["wiki/sources/alpha.md", "wiki/sources/alpha.md", "raw/note.txt", "raw/missing.txt"],
        )
        self.assertEqual(len(snapshots), 2)

        parsed = utils.parse_citation_snapshots({"citation_snapshots": ["wiki/sources/alpha.md#old", "bad", 3]})
        self.assertEqual(parsed, {"wiki/sources/alpha.md": "old"})
        self.assertEqual(utils.parse_citation_snapshots({"citation_snapshots": "bad"}), {})

        analysis = utils.analyze_citation_snapshots(
            self.root,
            ["wiki/sources/alpha.md", "raw/note.txt"],
            {"citation_snapshots": ["wiki/sources/alpha.md#old", "raw/stale.txt#gone"]},
        )
        self.assertEqual(analysis["drifted"], ["wiki/sources/alpha.md"])
        self.assertEqual(analysis["missing"], ["raw/note.txt"])
        self.assertEqual(analysis["stale"], ["raw/stale.txt"])
        self.assertTrue(analysis["has_drift"])

    def test_heading_write_and_json_helpers(self) -> None:
        self.assertEqual(utils.replace_first_markdown_heading("# Old\n\nBody\n", "New"), "# New\n\nBody\n")
        self.assertEqual(utils.replace_first_markdown_heading("Body\n", "New"), "# New\n\nBody\n")
        self.assertEqual(utils.replace_first_markdown_heading("", "New"), "# New\n")
        self.assertEqual(utils.first_markdown_heading("---\ntitle: x\n---\n# Actual\n"), "Actual")

        path = self.root / "out" / "note.md"
        self.assertTrue(utils.write_if_changed(path, "hello\n"))
        self.assertFalse(utils.write_if_changed(path, "hello\n"))

        timestamp_path = self.root / "out" / "generated.md"
        timestamp_path.write_text("- Generated at `2025-01-01T00:00:00+00:00`\n", encoding="utf-8")
        self.assertEqual(
            utils.write_if_changed_ignoring_timestamps(
                timestamp_path,
                "- Generated at `2025-01-02T00:00:00+00:00`\n",
            ),
            (False, False),
        )
        self.assertEqual(utils.write_if_changed_ignoring_timestamps(timestamp_path, "changed\n"), (True, True))

        json_path = self.root / "out" / "state.json"
        json_path.write_text("{bad json", encoding="utf-8")
        self.assertEqual(
            utils.write_json_document_if_changed_ignoring_generated_timestamps(
                json_path,
                {"generated_at": "2025-01-01T00:00:00+00:00", "value": 1},
            ),
            (True, True),
        )
        self.assertEqual(
            utils.write_json_document_if_changed_ignoring_generated_timestamps(
                json_path,
                {"generated_at": "2025-01-02T00:00:00+00:00", "value": 1},
            ),
            (False, False),
        )

        self.assertEqual(
            utils.compiled_source_sha("---\nsource_sha256: \"abc\"\n---\n# Source\n"),
            "abc",
        )
        self.assertEqual(utils.compiled_source_sha("# Source\n\n- SHA256: `def`\n"), "def")
        self.assertEqual(utils.compiled_source_sha(""), "")

        safe_literal = utils.html_safe_json_literal({"text": "<tag>&\u2028"})
        self.assertIn("\\u003c", safe_literal)
        self.assertIn("\\u0026", safe_literal)
        self.assertIn("\\u2028", safe_literal)
        self.assertEqual(utils.tokenize("The fast latency and ops pipeline"), ["the", "latency", "and", "ops", "pipeline"])


if __name__ == "__main__":
    unittest.main()
