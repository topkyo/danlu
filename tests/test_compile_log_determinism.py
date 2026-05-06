from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from aiwiki.app_compile import compile_wiki
from aiwiki.app_content import ingest_source
from aiwiki.app_protocol import ensure_layout
from aiwiki.compile.persist_step import finalize_compile_phase


class TestCompileLogDeterminism(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)
        self.source = self.root / "note.md"
        self.source.write_text("# Determinism Note\n\nInitial source material.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @property
    def log_path(self) -> Path:
        return self.root / "wiki" / "indexes" / "log.md"

    @property
    def compile_status_path(self) -> Path:
        return self.root / "wiki" / "indexes" / "compile-status.md"

    def _ingest_and_compile(self) -> dict[str, object]:
        ingest_source(self.root, str(self.source), title="Determinism Note")
        return compile_wiki(self.root)

    def _log_entry_count(self, content: str) -> int:
        return content.count("compile | wiki refresh")

    def _settle_compile(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for _ in range(6):
            result = compile_wiki(self.root)
            if result.get("changed_pages") == 0:
                return result
        return result

    def test_first_compile_appends_log(self) -> None:
        result = self._ingest_and_compile()

        self.assertIsInstance(result, dict)
        content = self.log_path.read_text(encoding="utf-8")
        self.assertIn("compile | wiki refresh", content)
        self.assertEqual(self._log_entry_count(content), 1)

    def test_clean_second_compile_skips_log(self) -> None:
        first = compile_wiki(self.root)
        compile_wiki(self.root)
        compile_wiki(self.root)
        compile_wiki(self.root)
        compile_wiki(self.root)
        snapshot1 = self.log_path.read_text(encoding="utf-8")

        with patch("aiwiki.compile.persist_step.append_wiki_log") as append_log:
            second = compile_wiki(self.root)

        self.assertIsInstance(first, dict)
        self.assertIsInstance(second, dict)
        self.assertEqual(snapshot1, self.log_path.read_text(encoding="utf-8"))
        append_log.assert_not_called()

    def test_clean_second_compile_skips_log_with_different_timestamps(self) -> None:
        context = SimpleNamespace(
            root=self.root,
            cache_status={},
            memory={"term_index": {}, "health": {"component_count": 0}},
            material_state={"entries": []},
            material_routing={"entries": []},
            knowledge_lifecycle={"entries": []},
            archive_candidates={"entries": []},
            previous_manifest={"entries": []},
            previous_compile_state={},
            entries=[],
            dirty_source_ids=[],
            clean_source_ids=[],
            dirty_concept_source_ids=[],
            clean_concept_source_ids=[],
            concepts=[],
            dirty_concept_slugs=[],
            clean_concept_slugs=[],
            dirty_machine_memory_source_ids=[],
            clean_machine_memory_source_ids=[],
            dirty_machine_memory_concept_slugs=[],
            clean_machine_memory_concept_slugs=[],
            machine_memory_core_reused=True,
            dirty_ranking_source_ids=[],
            clean_ranking_source_ids=[],
            dirty_ranking_concept_slugs=[],
            clean_ranking_concept_slugs=[],
            dirty_output_pack_groups=[],
            clean_output_pack_groups=[],
            dirty_domain_pilot_protocols=[],
            clean_domain_pilot_protocols=[],
            dirty_index_artifacts=[],
            clean_index_artifacts=[],
            dirty_maintenance_artifacts=[],
            clean_maintenance_artifacts=[],
            source_changed_pages=0,
            concept_changed_pages=0,
            index_changed_pages=0,
            maintenance_changed_pages=0,
            output_pack_changed_pages=0,
            domain_pilot_changed_pages=0,
            output_packs={"counts": {"review_packs": 0, "decision_memos": 0, "sop_drafts": 0}},
            domain_pilots={"scorecards": []},
            active_corpora_state={"corpora": []},
            transition={"changed": False},
            changed_pages=0,
            removed_pages=0,
            decision_pages=[],
            judgment_pages=[],
            protocol_state={"active_protocol": "general"},
            compiled_at="2025-01-01T00:00:00+00:00",
        )
        with patch("aiwiki.compile.persist_step.sync_query_cache", return_value={}), patch(
            "aiwiki.compile.persist_step.save_compile_state"
        ):
            finalize_compile_phase(context)  # type: ignore[arg-type]
        snapshot1 = self.compile_status_path.read_text(encoding="utf-8")

        context.compiled_at = "2025-01-02T00:00:00+00:00"
        context.changed_pages = 0
        with patch("aiwiki.compile.persist_step.sync_query_cache", return_value={}), patch(
            "aiwiki.compile.persist_step.save_compile_state"
        ), patch("aiwiki.compile.persist_step.append_wiki_log") as append_log:
            finalize_compile_phase(context)  # type: ignore[arg-type]
        snapshot2 = self.compile_status_path.read_text(encoding="utf-8")

        self.assertEqual(snapshot1, snapshot2)
        append_log.assert_not_called()

    def test_modified_source_compile_appends_log(self) -> None:
        self._ingest_and_compile()
        snapshot1 = self.log_path.read_text(encoding="utf-8")
        raw_note = self.root / "raw" / "inbox" / "determinism-note.md"
        raw_note.write_text("# Determinism Note\n\nModified source material.\n", encoding="utf-8")

        result = compile_wiki(self.root)
        snapshot2 = self.log_path.read_text(encoding="utf-8")

        self.assertIsInstance(result, dict)
        self.assertNotEqual(snapshot1, snapshot2)
        self.assertGreater(len(snapshot2), len(snapshot1))
        self.assertEqual(self._log_entry_count(snapshot2), self._log_entry_count(snapshot1) + 1)

    def test_removed_source_compile_appends_log(self) -> None:
        self._ingest_and_compile()
        snapshot1 = self.log_path.read_text(encoding="utf-8")
        raw_note = self.root / "raw" / "inbox" / "determinism-note.md"
        raw_note.unlink()

        result = compile_wiki(self.root)
        snapshot2 = self.log_path.read_text(encoding="utf-8")

        self.assertIsInstance(result, dict)
        self.assertNotEqual(snapshot1, snapshot2)
        self.assertGreater(len(snapshot2), len(snapshot1))
        self.assertEqual(self._log_entry_count(snapshot2), self._log_entry_count(snapshot1) + 1)

    def test_first_compile_writes_compile_status_md(self) -> None:
        result = self._ingest_and_compile()

        self.assertIsInstance(result, dict)
        self.assertTrue(self.compile_status_path.is_file())
        content = self.compile_status_path.read_text(encoding="utf-8")
        self.assertIn("# 编译状态", content)

    def test_clean_second_compile_compile_status_md_stable(self) -> None:
        self._ingest_and_compile()
        self._settle_compile()
        snapshot1 = self.compile_status_path.read_text(encoding="utf-8")

        result = compile_wiki(self.root)
        snapshot2 = self.compile_status_path.read_text(encoding="utf-8")

        self.assertIsInstance(result, dict)
        self.assertEqual(snapshot1, snapshot2)

    def test_finalize_clean_context_skips_compile_log_details(self) -> None:
        context = SimpleNamespace(
            root=self.root,
            cache_status={},
            memory={"term_index": {}, "health": {"component_count": 0}},
            material_state={"entries": []},
            material_routing={"entries": []},
            knowledge_lifecycle={"entries": []},
            archive_candidates={"entries": []},
            compiled_at="2026-04-10T10:00:00+00:00",
            previous_manifest={"entries": []},
            previous_compile_state={},
            entries=[],
            dirty_source_ids=[],
            clean_source_ids=[],
            dirty_concept_source_ids=[],
            clean_concept_source_ids=[],
            concepts=[],
            dirty_concept_slugs=[],
            clean_concept_slugs=[],
            dirty_machine_memory_source_ids=[],
            clean_machine_memory_source_ids=[],
            dirty_machine_memory_concept_slugs=[],
            clean_machine_memory_concept_slugs=[],
            machine_memory_core_reused=True,
            dirty_ranking_source_ids=[],
            clean_ranking_source_ids=[],
            dirty_ranking_concept_slugs=[],
            clean_ranking_concept_slugs=[],
            dirty_output_pack_groups=[],
            clean_output_pack_groups=[],
            dirty_domain_pilot_protocols=[],
            clean_domain_pilot_protocols=[],
            dirty_index_artifacts=[],
            clean_index_artifacts=[],
            dirty_maintenance_artifacts=[],
            clean_maintenance_artifacts=[],
            source_changed_pages=0,
            concept_changed_pages=0,
            index_changed_pages=0,
            maintenance_changed_pages=0,
            output_pack_changed_pages=0,
            domain_pilot_changed_pages=0,
            output_packs={"counts": {"review_packs": 0, "decision_memos": 0, "sop_drafts": 0}},
            domain_pilots={"scorecards": []},
            active_corpora_state={"corpora": []},
            transition={"changed": False},
            changed_pages=0,
            removed_pages=0,
            decision_pages=[],
            judgment_pages=[],
            protocol_state={"active_protocol": "general"},
        )

        log_details = MagicMock(return_value=[])
        with patch("aiwiki.compile.persist_step.sync_query_cache", return_value={}), patch(
            "aiwiki.compile.persist_step.save_compile_state"
        ), patch(
            "aiwiki.compile.persist_step.write_if_changed_ignoring_timestamps", return_value=(False, False)
        ), patch("aiwiki.compile.persist_step._compile_log_details", log_details):
            finalize_compile_phase(context)  # type: ignore[arg-type]

        log_details.assert_not_called()

    def test_transition_changed_appends_log(self) -> None:
        context = SimpleNamespace(
            root=self.root,
            cache_status={},
            memory={"term_index": {}, "health": {"component_count": 0}},
            material_state={"entries": []},
            material_routing={"entries": []},
            knowledge_lifecycle={"entries": []},
            archive_candidates={"entries": []},
            compiled_at="2026-04-10T10:00:00+00:00",
            previous_manifest={"entries": []},
            previous_compile_state={},
            entries=[],
            dirty_source_ids=[],
            clean_source_ids=[],
            dirty_concept_source_ids=[],
            clean_concept_source_ids=[],
            concepts=[],
            dirty_concept_slugs=[],
            clean_concept_slugs=[],
            dirty_machine_memory_source_ids=[],
            clean_machine_memory_source_ids=[],
            dirty_machine_memory_concept_slugs=[],
            clean_machine_memory_concept_slugs=[],
            machine_memory_core_reused=True,
            dirty_ranking_source_ids=[],
            clean_ranking_source_ids=[],
            dirty_ranking_concept_slugs=[],
            clean_ranking_concept_slugs=[],
            dirty_output_pack_groups=[],
            clean_output_pack_groups=[],
            dirty_domain_pilot_protocols=[],
            clean_domain_pilot_protocols=[],
            dirty_index_artifacts=[],
            clean_index_artifacts=[],
            dirty_maintenance_artifacts=[],
            clean_maintenance_artifacts=[],
            source_changed_pages=0,
            concept_changed_pages=0,
            index_changed_pages=0,
            maintenance_changed_pages=0,
            output_pack_changed_pages=0,
            domain_pilot_changed_pages=0,
            output_packs={"counts": {"review_packs": 0, "decision_memos": 0, "sop_drafts": 0}},
            domain_pilots={"scorecards": []},
            active_corpora_state={"corpora": []},
            transition={"changed": True},
            changed_pages=0,
            removed_pages=0,
            decision_pages=[],
            judgment_pages=[],
            protocol_state={"active_protocol": "general"},
        )

        with patch("aiwiki.compile.persist_step.sync_query_cache", return_value={}), patch(
            "aiwiki.compile.persist_step.save_compile_state"
        ), patch(
            "aiwiki.compile.persist_step.write_if_changed_ignoring_timestamps", return_value=(False, False)
        ), patch("aiwiki.compile.persist_step._compile_log_details", return_value=["transition changed"]), patch(
            "aiwiki.compile.persist_step.append_wiki_log"
        ) as append_log:
            finalize_compile_phase(context)  # type: ignore[arg-type]

        append_log.assert_called_once_with(self.root, "compile", "wiki refresh", ["transition changed"])


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestCompileLogDeterminism))
    return suite
