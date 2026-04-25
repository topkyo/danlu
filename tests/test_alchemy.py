from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_compile import ask_question
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_utils import parse_frontmatter
from aiwiki.execution.alchemy import (
    CANDIDATE_ELIXIR_DIR,
    ELIXIR_DIR,
    ELIXIR_STATE_VALUES,
    _detect_elixir_cycle,
    _parse_elixir_frontmatter,
    _read_elixir_anywhere,
    _validate_source_outputs,
    _validate_state_for_path,
    distill_elixir,
    finalize_elixir,
    list_promoted_outputs_for_corpus,
    seal_elixir,
    start_elixir,
)
from aiwiki.execution.candidates import promote_candidate
from aiwiki.execution.protocol_learnings import add_learning
from aiwiki.runner import run_alchemy_distill, run_alchemy_finalize, run_alchemy_seal, run_alchemy_start


def _settled_path(root: Path, elixir_id: str) -> Path:
    return root / ELIXIR_DIR / f"{elixir_id}.md"


def _candidate_path(root: Path, elixir_id: str) -> Path:
    return root / CANDIDATE_ELIXIR_DIR / f"{elixir_id}.md"


class AlchemyCandidatePlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)
        (self.root / "prompts" / "compile.md").write_text("Compile prompt fixture.\n", encoding="utf-8")
        (self.root / "prompts" / "ask.md").write_text("Ask prompt fixture.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _make_promoted_corpus(self) -> str:
        result = ask_question(self.root, "Should we increase transformer training spend?", "report")
        promote_candidate(self.root, result["path"])
        return str(result["active_corpus_id"])

    def _write_stub_elixir(self, path: Path, *, elixir_id: str, state: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "---",
                    'kind: "elixir"',
                    f'elixir_id: "{elixir_id}"',
                    f'elixir_state: "{state}"',
                    'protocol: "general"',
                    'iteration: "0"',
                    'provenance_corpus: "corp"',
                    "derived_from:",
                    '  - "wiki/derived/base.md"',
                    'topic: "topic"',
                    "counter_evidence:",
                    '  - "NONE_FOUND"',
                    'confidence_level: "low"',
                    'created_at: "2026-01-01T00:00:00+00:00"',
                    'updated_at: "2026-01-01T00:00:00+00:00"',
                    'distill_history_json: "[]"',
                    "---",
                    "# Elixir",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def test_start_writes_to_candidate_plane(self) -> None:
        corpus_id = self._make_promoted_corpus()

        result = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")

        self.assertTrue(result["path"].startswith(f"{CANDIDATE_ELIXIR_DIR}/"))
        self.assertTrue((self.root / result["path"]).exists())

    def test_start_frontmatter_contains_decision_b_defaults(self) -> None:
        corpus_id = self._make_promoted_corpus()

        result = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="research")

        frontmatter = parse_frontmatter((self.root / result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["counter_evidence"], ["NONE_FOUND"])
        self.assertEqual(frontmatter["confidence_level"], "low")
        self.assertEqual(frontmatter["kind"], "elixir")
        self.assertEqual(frontmatter["protocol"], "research")

    def test_start_rejects_existing_id_in_candidate_plane(self) -> None:
        corpus_id = self._make_promoted_corpus()
        from aiwiki.execution import alchemy as alchemy_module

        elixir_id = "elixir-existing-in-candidate"
        self._write_stub_elixir(_candidate_path(self.root, elixir_id), elixir_id=elixir_id, state="draft")
        with patch.object(alchemy_module, "next_available_stem", return_value=elixir_id):
            with self.assertRaises(FileExistsError):
                run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")

    def test_start_rejects_existing_id_in_wiki_plane(self) -> None:
        corpus_id = self._make_promoted_corpus()
        from aiwiki.execution import alchemy as alchemy_module

        elixir_id = "elixir-existing-in-wiki"
        self._write_stub_elixir(_settled_path(self.root, elixir_id), elixir_id=elixir_id, state="settled")
        with patch.object(alchemy_module, "next_available_stem", return_value=elixir_id):
            with self.assertRaises(FileExistsError):
                run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")

    def test_distill_writes_to_candidate_plane(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")

        result = run_alchemy_distill(self.root, started["elixir_id"], "What about latency?")

        self.assertTrue(result["path"].startswith(f"{CANDIDATE_ELIXIR_DIR}/"))
        frontmatter = parse_frontmatter((self.root / result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["elixir_state"], "distilling")

    def test_distill_rejects_source_in_wiki_plane(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        run_alchemy_seal(self.root, started["elixir_id"])

        with self.assertRaises(ValueError):
            run_alchemy_distill(self.root, started["elixir_id"], "What about latency?")

    def test_seal_reads_from_candidate_writes_to_wiki(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        run_alchemy_distill(self.root, started["elixir_id"], "What about latency?")

        result = run_alchemy_seal(self.root, started["elixir_id"])

        self.assertTrue(result["path"].startswith(f"{ELIXIR_DIR}/"))
        settled = _settled_path(self.root, started["elixir_id"])
        self.assertTrue(settled.exists())
        frontmatter = parse_frontmatter(settled.read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["elixir_state"], "settled")
        self.assertEqual(frontmatter["iteration"], "1")

    def test_seal_keeps_candidate_file_untouched(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        run_alchemy_distill(self.root, started["elixir_id"], "What about latency?")
        candidate = _candidate_path(self.root, started["elixir_id"])
        before = candidate.read_text(encoding="utf-8")

        run_alchemy_seal(self.root, started["elixir_id"])

        self.assertEqual(candidate.read_text(encoding="utf-8"), before)

    def test_read_elixir_anywhere_settled_priority_over_candidate(self) -> None:
        elixir_id = "elixir-priority"
        self._write_stub_elixir(_candidate_path(self.root, elixir_id), elixir_id=elixir_id, state="draft")
        self._write_stub_elixir(_settled_path(self.root, elixir_id), elixir_id=elixir_id, state="settled")

        path, frontmatter = _read_elixir_anywhere(self.root, elixir_id)

        self.assertEqual(path, _settled_path(self.root, elixir_id))
        self.assertEqual(frontmatter["elixir_state"], "settled")

    def test_read_elixir_anywhere_falls_back_to_candidate_when_no_settled(self) -> None:
        elixir_id = "elixir-candidate-only"
        self._write_stub_elixir(_candidate_path(self.root, elixir_id), elixir_id=elixir_id, state="draft")

        path, frontmatter = _read_elixir_anywhere(self.root, elixir_id)

        self.assertEqual(path, _candidate_path(self.root, elixir_id))
        self.assertEqual(frontmatter["elixir_state"], "draft")

    def test_read_elixir_anywhere_raises_when_neither_exists(self) -> None:
        with self.assertRaises(FileNotFoundError):
            _read_elixir_anywhere(self.root, "missing-elixir")

    def test_validate_state_for_path_rejects_settled_in_candidate_plane(self) -> None:
        with self.assertRaises(ValueError):
            _validate_state_for_path(self.root, "settled", _candidate_path(self.root, "x"))

    def test_validate_state_for_path_rejects_draft_in_wiki_plane(self) -> None:
        with self.assertRaises(ValueError):
            _validate_state_for_path(self.root, "draft", _settled_path(self.root, "x"))

    def test_state_enum_accepts_all_five_values(self) -> None:
        self.assertEqual(ELIXIR_STATE_VALUES, {"draft", "distilling", "candidate", "settled", "superseded"})
        _validate_state_for_path(self.root, "draft", _candidate_path(self.root, "a"))
        _validate_state_for_path(self.root, "distilling", _candidate_path(self.root, "b"))
        _validate_state_for_path(self.root, "candidate", _candidate_path(self.root, "c"))
        _validate_state_for_path(self.root, "superseded", _candidate_path(self.root, "d"))
        _validate_state_for_path(self.root, "settled", _settled_path(self.root, "e"))

    def test_protocol_learnings_can_still_reference_settled_elixir(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        run_alchemy_seal(self.root, started["elixir_id"])

        result = add_learning(
            self.root,
            "general",
            title="cites settled elixir",
            source_refs=[f"wiki/elixirs/{started['elixir_id']}.md"],
        )

        self.assertTrue((self.root / result["path"]).exists())

    def test_validate_source_outputs_rejects_non_string_ref(self) -> None:
        with self.assertRaises(ValueError):
            _validate_source_outputs(self.root, ["wiki/derived/base.md", ""], allowed={"wiki/derived/base.md"})

    def test_validate_source_outputs_rejects_missing_wiki_elixir_file(self) -> None:
        with self.assertRaises(ValueError):
            _validate_source_outputs(self.root, ["wiki/elixirs/missing.md"], allowed=set())

    def test_validate_state_for_path_rejects_invalid_state_value(self) -> None:
        with self.assertRaises(ValueError):
            _validate_state_for_path(self.root, "invalid", _candidate_path(self.root, "x"))

    def test_validate_state_for_path_rejects_path_outside_planes(self) -> None:
        with self.assertRaises(ValueError):
            _validate_state_for_path(self.root, "draft", self.root / "tmp" / "outside.md")

    def test_detect_cycle_handles_absolute_path_outside_root(self) -> None:
        cycle = _detect_elixir_cycle(self.root, Path("/tmp/outside-elixir.md"), [])
        self.assertIsNone(cycle)

    def test_detect_cycle_raises_when_existing_file_unparseable(self) -> None:
        bad = _settled_path(self.root, "bad")
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("---\nnot: valid\n---\n# bad\n", encoding="utf-8")
        with patch("aiwiki.execution.alchemy._parse_elixir_frontmatter", side_effect=ValueError("bad-fm")):
            with self.assertRaises(ValueError) as ctx:
                _detect_elixir_cycle(self.root, _settled_path(self.root, "new"), [])
        self.assertIn("金丹文件无法解析", str(ctx.exception))

    def test_detect_cycle_raises_when_dependency_parse_fails(self) -> None:
        seeded = _settled_path(self.root, "seeded")
        seeded.parent.mkdir(parents=True, exist_ok=True)
        seeded.write_text("---\n---\n# seeded\n", encoding="utf-8")
        with patch(
            "aiwiki.execution.alchemy._parse_elixir_frontmatter",
            side_effect=[{"elixir_state": "settled", "derived_from": []}, ValueError("bad-deps")],
        ):
            with self.assertRaises(ValueError) as ctx:
                _detect_elixir_cycle(self.root, _settled_path(self.root, "new"), [])
        self.assertIn("金丹文件无法解析", str(ctx.exception))

    def test_parse_frontmatter_handles_non_string_distill_history_json(self) -> None:
        path = _candidate_path(self.root, "history-list")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "---",
                    "distill_history_json:",
                    "  - bad-item",
                    "---",
                    "# Elixir",
                ]
            ),
            encoding="utf-8",
        )
        frontmatter = _parse_elixir_frontmatter(path)
        self.assertEqual(frontmatter.get("distill_history"), [])

    def test_start_rejects_missing_protocol_name(self) -> None:
        with patch("aiwiki.execution.alchemy._find_corpus", return_value={}):
            with self.assertRaises(ValueError):
                start_elixir(self.root, "corp", topic="VLA", protocol=None)

    def test_start_rejects_when_cycle_detector_reports_cycle(self) -> None:
        base = self.root / "wiki" / "derived" / "base.md"
        base.parent.mkdir(parents=True, exist_ok=True)
        base.write_text("base", encoding="utf-8")
        with patch("aiwiki.execution.alchemy._find_corpus", return_value={"protocol": "general"}):
            with patch(
                "aiwiki.execution.alchemy.list_promoted_outputs_for_corpus",
                return_value=[{"promoted_to": "wiki/derived/base.md"}],
            ):
                with patch("aiwiki.execution.alchemy._detect_elixir_cycle", return_value=["a", "a"]):
                    with self.assertRaises(ValueError) as ctx:
                        start_elixir(self.root, "corp", topic="VLA", protocol="general")
        self.assertIn("金丹引用形成环路", str(ctx.exception))

    def test_distill_rejects_candidate_file_marked_settled(self) -> None:
        elixir_id = "candidate-but-settled"
        self._write_stub_elixir(_candidate_path(self.root, elixir_id), elixir_id=elixir_id, state="settled")

        with self.assertRaises(ValueError):
            distill_elixir(self.root, elixir_id, question="q")

    def test_distill_include_rejects_candidate_reference(self) -> None:
        corpus_id = self._make_promoted_corpus()
        base = run_alchemy_start(self.root, corpus_id, "Base", protocol="general")
        include = run_alchemy_start(self.root, corpus_id, "Include", protocol="general")

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_distill(self.root, base["elixir_id"], "q", include_elixir_ids=[include["elixir_id"]])
        self.assertIn("只能引用 settled 金丹", str(ctx.exception))

    def test_seal_rejects_without_wiki_derived_anchor(self) -> None:
        ref_id = "ref-settled"
        self._write_stub_elixir(_settled_path(self.root, ref_id), elixir_id=ref_id, state="settled")
        target_id = "candidate-no-derived"
        self._write_stub_elixir(_candidate_path(self.root, target_id), elixir_id=target_id, state="distilling")
        target = _candidate_path(self.root, target_id)
        text = target.read_text(encoding="utf-8")
        text = text.replace('  - "wiki/derived/base.md"', f'  - "wiki/elixirs/{ref_id}.md"', 1)
        target.write_text(text, encoding="utf-8")

        with patch("aiwiki.execution.alchemy._find_corpus", return_value={"corpus_id": "corp"}):
            with patch("aiwiki.execution.alchemy.list_promoted_outputs_for_corpus", return_value=[]):
                with self.assertRaises(ValueError) as ctx:
                    seal_elixir(self.root, target_id)
        self.assertIn("必须至少包含一个 wiki/derived/", str(ctx.exception))

    def test_finalize_writes_candidate_state(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        before = parse_frontmatter((_candidate_path(self.root, started["elixir_id"])).read_text(encoding="utf-8"))

        result = finalize_elixir(self.root, elixir_id=started["elixir_id"])

        self.assertEqual(result["elixir_state"], "candidate")
        frontmatter = parse_frontmatter((_candidate_path(self.root, started["elixir_id"])).read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["elixir_state"], "candidate")
        self.assertEqual(frontmatter["iteration"], before["iteration"])
        self.assertEqual(frontmatter["confidence_level"], before["confidence_level"])

    def test_finalize_from_distilling_to_candidate(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        run_alchemy_distill(self.root, started["elixir_id"], "What about latency?")

        result = finalize_elixir(self.root, elixir_id=started["elixir_id"])

        self.assertEqual(result["elixir_state"], "candidate")
        frontmatter = parse_frontmatter((_candidate_path(self.root, started["elixir_id"])).read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["elixir_state"], "candidate")

    def test_finalize_rejects_already_candidate(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        finalize_elixir(self.root, elixir_id=started["elixir_id"])

        with self.assertRaises(ValueError) as ctx:
            finalize_elixir(self.root, elixir_id=started["elixir_id"])
        self.assertIn("already_candidate", str(ctx.exception))

    def test_finalize_rejects_settled(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        run_alchemy_seal(self.root, started["elixir_id"])

        with self.assertRaises(ValueError) as ctx:
            finalize_elixir(self.root, elixir_id=started["elixir_id"])
        self.assertIn("unsupported_source_state", str(ctx.exception))

    def test_finalize_rejects_superseded(self) -> None:
        elixir_id = "candidate-superseded"
        self._write_stub_elixir(_candidate_path(self.root, elixir_id), elixir_id=elixir_id, state="superseded")

        with self.assertRaises(ValueError) as ctx:
            finalize_elixir(self.root, elixir_id=elixir_id)
        self.assertIn("unsupported_source_state", str(ctx.exception))

    def test_finalize_runs_provenance_validation(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        candidate = _candidate_path(self.root, started["elixir_id"])
        fm = parse_frontmatter(candidate.read_text(encoding="utf-8"))
        current_ref = str(fm["derived_from"][0])
        updated = candidate.read_text(encoding="utf-8").replace(
            f'  - "{current_ref}"',
            '  - "wiki/derived/missing-finalize-anchor.md"',
            1,
        )
        candidate.write_text(updated, encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            finalize_elixir(self.root, elixir_id=started["elixir_id"])
        self.assertIn("source output missing", str(ctx.exception))

    def test_finalize_runs_dag_validation(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        target_ref = f"wiki/elixirs/{started['elixir_id']}.md"
        cycle_id = "cycle-parent"
        cycle_path = _settled_path(self.root, cycle_id)
        self._write_stub_elixir(cycle_path, elixir_id=cycle_id, state="settled")
        cycle_text = cycle_path.read_text(encoding="utf-8")
        cycle_path.write_text(cycle_text.replace('  - "wiki/derived/base.md"', f'  - "{target_ref}"', 1), encoding="utf-8")
        candidate = _candidate_path(self.root, started["elixir_id"])
        text = candidate.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)
        anchor_ref = str(frontmatter["derived_from"][0])
        text = text.replace(
            f'  - "{anchor_ref}"',
            f'  - "{anchor_ref}"\n  - "wiki/elixirs/{cycle_id}.md"',
            1,
        )
        candidate.write_text(text, encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            finalize_elixir(self.root, elixir_id=started["elixir_id"])
        self.assertIn("金丹引用形成环路", str(ctx.exception))

    def test_finalize_does_not_enforce_counter_evidence_nonempty(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        candidate = _candidate_path(self.root, started["elixir_id"])
        text = candidate.read_text(encoding="utf-8")
        text = text.replace('  - "NONE_FOUND"\n', "", 1)
        candidate.write_text(text, encoding="utf-8")

        result = finalize_elixir(self.root, elixir_id=started["elixir_id"])

        self.assertEqual(result["elixir_state"], "candidate")

    def test_distill_can_reopen_candidate(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        run_alchemy_finalize(self.root, elixir_id=started["elixir_id"])
        candidate_path = _candidate_path(self.root, started["elixir_id"])
        before = _parse_elixir_frontmatter(candidate_path)
        iteration_before = int(before.get("iteration", 0) or 0)
        history_before = before.get("distill_history") if isinstance(before.get("distill_history"), list) else []
        question = "What changed since finalize?"

        result = run_alchemy_distill(self.root, started["elixir_id"], question)

        self.assertEqual(result["elixir_state"], "distilling")
        frontmatter = _parse_elixir_frontmatter(candidate_path)
        self.assertEqual(frontmatter["elixir_state"], "distilling")
        iteration_after = int(frontmatter.get("iteration", 0) or 0)
        history_after = frontmatter.get("distill_history") if isinstance(frontmatter.get("distill_history"), list) else []
        self.assertEqual(iteration_after, iteration_before + 1)
        self.assertEqual(len(history_after), len(history_before) + 1)
        self.assertEqual(str(history_after[-1].get("question") or ""), question)

    def test_seal_accepts_candidate_source(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        run_alchemy_finalize(self.root, elixir_id=started["elixir_id"])

        result = run_alchemy_seal(self.root, started["elixir_id"])

        self.assertEqual(result["elixir_state"], "settled")
        settled = _settled_path(self.root, started["elixir_id"])
        self.assertTrue(settled.exists())

    def test_finalize_missing_candidate_file_raises_file_not_found(self) -> None:
        with self.assertRaises(FileNotFoundError):
            finalize_elixir(self.root, elixir_id="missing-candidate")

    def test_finalize_rejects_without_wiki_derived_anchor(self) -> None:
        ref_id = "ref-for-finalize"
        self._write_stub_elixir(_settled_path(self.root, ref_id), elixir_id=ref_id, state="settled")
        target_id = "candidate-no-derived-finalize"
        self._write_stub_elixir(_candidate_path(self.root, target_id), elixir_id=target_id, state="draft")
        target = _candidate_path(self.root, target_id)
        text = target.read_text(encoding="utf-8")
        text = text.replace('  - "wiki/derived/base.md"', f'  - "wiki/elixirs/{ref_id}.md"', 1)
        target.write_text(text, encoding="utf-8")

        with patch("aiwiki.execution.alchemy._find_corpus", return_value={"corpus_id": "corp"}):
            with patch("aiwiki.execution.alchemy.list_promoted_outputs_for_corpus", return_value=[]):
                with self.assertRaises(ValueError) as ctx:
                    finalize_elixir(self.root, elixir_id=target_id)
        self.assertIn("必须至少包含一个 wiki/derived/", str(ctx.exception))

    def test_distill_rejects_superseded_source_state(self) -> None:
        elixir_id = "candidate-superseded-distill"
        self._write_stub_elixir(_candidate_path(self.root, elixir_id), elixir_id=elixir_id, state="superseded")

        with self.assertRaises(ValueError) as ctx:
            distill_elixir(self.root, elixir_id, question="q")
        self.assertIn("unsupported_source_state", str(ctx.exception))

    def test_seal_rejects_superseded_source_state(self) -> None:
        elixir_id = "candidate-superseded-seal"
        self._write_stub_elixir(_candidate_path(self.root, elixir_id), elixir_id=elixir_id, state="superseded")

        with self.assertRaises(ValueError) as ctx:
            seal_elixir(self.root, elixir_id)
        self.assertIn("unsupported_source_state", str(ctx.exception))

    def test_distill_include_reports_missing_settled_reference(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")

        with self.assertRaises(FileNotFoundError):
            run_alchemy_distill(self.root, started["elixir_id"], "q", include_elixir_ids=["missing-settled-elixir"])

    def test_detect_cycle_skips_non_settled_entries_in_wiki_plane(self) -> None:
        self._write_stub_elixir(_settled_path(self.root, "draft-in-wiki"), elixir_id="draft-in-wiki", state="draft")
        cycle = _detect_elixir_cycle(self.root, _settled_path(self.root, "new"), [])
        self.assertIsNone(cycle)

    def test_list_promoted_outputs_ignores_empty_promoted_to(self) -> None:
        mocked_state = {
            "candidates": [
                {"corpus_id": "corp", "candidate_state": "promoted", "artifact_ref": "a", "promoted_to": "wiki/derived/a.md"},
                {"corpus_id": "corp", "candidate_state": "promoted", "artifact_ref": "b", "promoted_to": ""},
                {"corpus_id": "corp", "candidate_state": "pending", "artifact_ref": "c", "promoted_to": "wiki/derived/c.md"},
            ]
        }
        with patch("aiwiki.execution.alchemy.load_output_candidates_state", return_value=mocked_state):
            rows = list_promoted_outputs_for_corpus(self.root, "corp")
        self.assertEqual(rows, [{"artifact_ref": "a", "promoted_to": "wiki/derived/a.md", "question": ""}])

    def test_validate_source_outputs_rejects_blank_ref(self) -> None:
        with self.assertRaises(ValueError):
            _validate_source_outputs(self.root, [""], allowed=set())


if __name__ == "__main__":
    unittest.main()
