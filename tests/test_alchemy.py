from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_compile import ask_question
from aiwiki.app_execution import compute_file_sha256, find_latest_elixir_promotion_receipt
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_utils import parse_frontmatter, slugify
from aiwiki.execution.alchemy import (
    CANDIDATE_ELIXIR_DIR,
    ELIXIR_DIR,
    ELIXIR_STATE_VALUES,
    PromoteHalfWriteError,
    RevertHalfWriteError,
    _collect_dependent_elixir_ids,
    _detect_elixir_cycle,
    _parse_elixir_frontmatter,
    _read_elixir_anywhere,
    _validate_source_outputs,
    _validate_state_for_path,
    _write_elixir_markdown,
    demote_elixir,
    distill_elixir,
    finalize_elixir,
    list_promoted_outputs_for_corpus,
    promote_elixir,
    revert_elixir,
    start_elixir,
)
from aiwiki.execution.candidates import promote_candidate
from aiwiki.execution.protocol_learnings import add_learning
from aiwiki.render.paths import execution_receipt_path
from aiwiki.runner import (
    run_alchemy_demote,
    run_alchemy_distill,
    run_alchemy_finalize,
    run_alchemy_promote,
    run_alchemy_revert,
    run_alchemy_start,
)


def _settled_path(root: Path, elixir_id: str) -> Path:
    return root / ELIXIR_DIR / f"{elixir_id}.md"


def _candidate_path(root: Path, elixir_id: str) -> Path:
    return root / CANDIDATE_ELIXIR_DIR / f"{elixir_id}.md"


def _receipt_history_entries(root: Path) -> list[dict[str, object]]:
    path = root / ".aiwiki" / "state" / "execution-receipts.jsonl"
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    for row in path.read_text(encoding="utf-8").splitlines():
        row = row.strip()
        if not row:
            continue
        decoded = json.loads(row)
        if isinstance(decoded, dict):
            entries.append(decoded)
    return entries


def _write_receipt_history_entries(root: Path, entries: list[dict[str, object]]) -> None:
    path = root / ".aiwiki" / "state" / "execution-receipts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry, ensure_ascii=False, sort_keys=True) for entry in entries]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _latest_receipt_by_subject(root: Path, *, subject_kind: str, subject_id: str) -> dict[str, object] | None:
    for entry in reversed(_receipt_history_entries(root)):
        if entry.get("subject_kind") == subject_kind and entry.get("subject_id") == subject_id:
            return entry
    return None


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

    def _start_candidate_elixir(self, *, topic: str = "VLA robotics") -> str:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, topic, protocol="general")
        run_alchemy_finalize(self.root, elixir_id=started["elixir_id"])
        return str(started["elixir_id"])

    def _update_candidate_frontmatter(self, elixir_id: str, **updates: object) -> None:
        path = _candidate_path(self.root, elixir_id)
        original = path.read_text(encoding="utf-8")
        frontmatter = _parse_elixir_frontmatter(path)
        frontmatter.update(updates)
        _write_elixir_markdown(path, frontmatter=frontmatter, body=original.split("---", 2)[-1].lstrip("\n"))

    def _update_frontmatter(self, path: Path, **updates: object) -> None:
        original = path.read_text(encoding="utf-8")
        frontmatter = _parse_elixir_frontmatter(path)
        frontmatter.update(updates)
        _write_elixir_markdown(path, frontmatter=frontmatter, body=original.split("---", 2)[-1].lstrip("\n"))

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

    def test_distill_preserves_counter_evidence_defaults(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")

        result = run_alchemy_distill(self.root, started["elixir_id"], "What about latency?")

        frontmatter = parse_frontmatter((self.root / result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["counter_evidence"], ["NONE_FOUND"])
        self.assertEqual(frontmatter["confidence_level"], "low")

    def test_distill_rejects_source_in_wiki_plane(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "VLA robotics", protocol="general")
        run_alchemy_finalize(self.root, elixir_id=started["elixir_id"])
        run_alchemy_promote(self.root, elixir_id=started["elixir_id"])

        with self.assertRaises(ValueError):
            run_alchemy_distill(self.root, started["elixir_id"], "What about latency?")

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
        run_alchemy_finalize(self.root, elixir_id=started["elixir_id"])
        run_alchemy_promote(self.root, elixir_id=started["elixir_id"])

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

    def test_distill_explicitly_rejects_settled_with_specific_message(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="distill-settled-reject")
        run_alchemy_promote(self.root, elixir_id=elixir_id)

        with self.assertRaises(ValueError) as ctx:
            distill_elixir(self.root, elixir_id, question="q")

        self.assertIn("sealed elixir cannot be distilled", str(ctx.exception))

    def test_distill_include_rejects_candidate_reference(self) -> None:
        corpus_id = self._make_promoted_corpus()
        base = run_alchemy_start(self.root, corpus_id, "Base", protocol="general")
        include = run_alchemy_start(self.root, corpus_id, "Include", protocol="general")

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_distill(self.root, base["elixir_id"], "q", include_elixir_ids=[include["elixir_id"]])
        self.assertIn("只能引用 settled 金丹", str(ctx.exception))

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
        run_alchemy_finalize(self.root, elixir_id=started["elixir_id"])
        run_alchemy_promote(self.root, elixir_id=started["elixir_id"])

        with self.assertRaises(ValueError) as ctx:
            finalize_elixir(self.root, elixir_id=started["elixir_id"])
        self.assertIn("unsupported_source_state", str(ctx.exception))

    def test_finalize_rejects_self_reference(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "finalize self ref", protocol="general")
        candidate_path = _candidate_path(self.root, started["elixir_id"])
        text = candidate_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)
        anchor = str(frontmatter["derived_from"][0])
        frontmatter["derived_from"] = [anchor, f"wiki/elixirs/{started['elixir_id']}.md"]
        _write_elixir_markdown(candidate_path, frontmatter=frontmatter, body=text.split("---", 2)[-1].lstrip("\n"))

        with patch("aiwiki.execution.alchemy._validate_source_outputs", return_value=None):
            with self.assertRaises(ValueError) as ctx:
                finalize_elixir(self.root, elixir_id=started["elixir_id"])

        self.assertIn("cannot reference self", str(ctx.exception))

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
        before = candidate.read_text(encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            finalize_elixir(self.root, elixir_id=started["elixir_id"])
        self.assertIn("source output missing", str(ctx.exception))
        self.assertEqual(candidate.read_text(encoding="utf-8"), before)

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

    def test_promote_writes_settled_and_tombstone(self) -> None:
        elixir_id = self._start_candidate_elixir()

        result = run_alchemy_promote(self.root, elixir_id=elixir_id)

        self.assertEqual(result["elixir_state"], "settled")
        settled = _settled_path(self.root, elixir_id)
        candidate = _candidate_path(self.root, elixir_id)
        self.assertTrue(settled.exists())
        self.assertTrue(candidate.exists())
        settled_frontmatter = parse_frontmatter(settled.read_text(encoding="utf-8"))
        tombstone_frontmatter = parse_frontmatter(candidate.read_text(encoding="utf-8"))
        self.assertEqual(settled_frontmatter["elixir_state"], "settled")
        self.assertEqual(tombstone_frontmatter["elixir_state"], "superseded")
        self.assertEqual(tombstone_frontmatter["superseded_by"], f"wiki/elixirs/{elixir_id}.md")
        self.assertTrue(tombstone_frontmatter["promoted_at"])
        self.assertEqual(settled_frontmatter["promoted_at"], tombstone_frontmatter["promoted_at"])
        self.assertNotIn("sealed_at", settled_frontmatter)

    def test_promote_writes_receipt_and_history(self) -> None:
        elixir_id = self._start_candidate_elixir()

        result = run_alchemy_promote(self.root, elixir_id=elixir_id, note="promote now")

        receipt_path = self.root / result["receipt_path"]
        self.assertTrue(receipt_path.exists())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["subject_kind"], "elixir_promotion")
        self.assertEqual(receipt["subject_id"], elixir_id)
        self.assertEqual(receipt["apply_mode"], "elixir-promote")
        self.assertEqual(receipt["operation"], "promote")
        self.assertEqual(receipt["generated_by"], "aiwiki-elixir-promote")
        self.assertRegex(str(receipt["action_id"]), rf"^elixir-promote-{slugify(elixir_id)}-\d{{13}}(?:-\d+)?$")
        self.assertEqual(receipt["primary_path"], f"wiki/elixirs/{elixir_id}.md")
        self.assertEqual(receipt["secondary_path"], f"output/_candidates/elixirs/{elixir_id}.md")
        bundle = receipt.get("bundle") or {}
        self.assertEqual(bundle.get("primary_path_sha256"), compute_file_sha256(_settled_path(self.root, elixir_id)))
        self.assertEqual(bundle.get("secondary_path_sha256"), compute_file_sha256(_candidate_path(self.root, elixir_id)))
        self.assertIsNone(receipt["safe_apply_preview"])
        self.assertEqual(receipt["note"], "promote now")

        history_path = self.root / ".aiwiki" / "state" / "execution-receipts.jsonl"
        self.assertTrue(history_path.exists())
        last = json.loads(history_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(last["action_id"], receipt["action_id"])
        self.assertEqual(last["receipt_path"], receipt["receipt_path"])

    def test_promote_action_id_includes_epoch_ms_suffix(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="promote-action-id-ms")

        result = run_alchemy_promote(self.root, elixir_id=elixir_id)

        receipt = json.loads((self.root / str(result["receipt_path"])).read_text(encoding="utf-8"))
        self.assertRegex(str(receipt["action_id"]), rf"^elixir-promote-{slugify(elixir_id)}-\d{{13}}(?:-\d+)?$")

    def test_promote_creates_distinct_receipts_for_repeat_promote(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="repeat-promote")

        first = run_alchemy_promote(self.root, elixir_id=elixir_id)
        run_alchemy_revert(self.root, elixir_id=elixir_id)
        second = run_alchemy_promote(self.root, elixir_id=elixir_id)

        self.assertNotEqual(first["receipt_path"], second["receipt_path"])
        self.assertTrue((self.root / str(first["receipt_path"])).exists())
        self.assertTrue((self.root / str(second["receipt_path"])).exists())
        history_promotes = [
            entry
            for entry in _receipt_history_entries(self.root)
            if entry.get("subject_kind") == "elixir_promotion" and entry.get("subject_id") == elixir_id
        ]
        self.assertEqual(len(history_promotes), 2)

    def test_promote_action_id_collision_fallback(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="promote-collision")
        fixed_dt = datetime(2026, 1, 1, 0, 0, 0, 123000, tzinfo=timezone.utc)
        base = f"elixir-promote-{slugify(elixir_id)}"
        occupied_action_id = f"{base}-{int(fixed_dt.timestamp() * 1000)}"
        occupied_path = execution_receipt_path(self.root, occupied_action_id)
        occupied_path.parent.mkdir(parents=True, exist_ok=True)
        occupied_path.write_text("{}\n", encoding="utf-8")

        with patch("aiwiki.execution.alchemy.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = fixed_dt
            result = run_alchemy_promote(self.root, elixir_id=elixir_id)

        receipt = json.loads((self.root / str(result["receipt_path"])).read_text(encoding="utf-8"))
        self.assertEqual(receipt["action_id"], f"{occupied_action_id}-2")

    def test_promote_receipt_records_settled_and_tombstone_sha256(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="promote-hash-anchor")

        result = run_alchemy_promote(self.root, elixir_id=elixir_id)

        receipt = json.loads((self.root / str(result["receipt_path"])).read_text(encoding="utf-8"))
        bundle = receipt.get("bundle") or {}
        self.assertEqual(bundle.get("primary_path_sha256"), compute_file_sha256(_settled_path(self.root, elixir_id)))
        self.assertEqual(bundle.get("secondary_path_sha256"), compute_file_sha256(_candidate_path(self.root, elixir_id)))

    def test_promote_receipt_records_counter_evidence_gate_fields(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="promote-gate-receipt")
        self._update_candidate_frontmatter(
            elixir_id,
            counter_evidence=["wiki/derived/evidence-a.md", "wiki/derived/evidence-b.md"],
            confidence_level="medium",
        )

        result = run_alchemy_promote(self.root, elixir_id=elixir_id)

        receipt = json.loads((self.root / str(result["receipt_path"])).read_text(encoding="utf-8"))
        bundle = receipt.get("bundle") or {}
        self.assertEqual(bundle.get("counter_evidence"), ["wiki/derived/evidence-a.md", "wiki/derived/evidence-b.md"])
        self.assertEqual(bundle.get("confidence_level"), "medium")

    def test_promote_preserves_frontmatter_fields(self) -> None:
        elixir_id = self._start_candidate_elixir()
        self._update_candidate_frontmatter(
            elixir_id,
            counter_evidence=["wiki/derived/evidence-a.md", "wiki/derived/evidence-b.md"],
            confidence_level="medium",
            iteration="7",
            distill_history=[{"iteration": 1, "question": "q", "at": "2026-01-02T00:00:00+00:00"}],
            custom_tag="keep-me",
        )
        before = _parse_elixir_frontmatter(_candidate_path(self.root, elixir_id))

        run_alchemy_promote(self.root, elixir_id=elixir_id)

        settled = _parse_elixir_frontmatter(_settled_path(self.root, elixir_id))
        self.assertEqual(settled["provenance_corpus"], before["provenance_corpus"])
        self.assertEqual(settled["counter_evidence"], before["counter_evidence"])
        self.assertEqual(settled["confidence_level"], before["confidence_level"])
        self.assertEqual(settled["iteration"], before["iteration"])
        self.assertEqual(settled.get("distill_history"), before.get("distill_history"))
        self.assertEqual(settled["custom_tag"], "keep-me")

    def test_promote_rejects_empty_counter_evidence(self) -> None:
        elixir_id = self._start_candidate_elixir()
        self._update_candidate_frontmatter(elixir_id, counter_evidence=[])

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_promote(self.root, elixir_id=elixir_id)
        self.assertIn("counter_evidence_required", str(ctx.exception))

    def test_promote_rejects_counter_evidence_with_empty_string_item(self) -> None:
        elixir_id = self._start_candidate_elixir()
        self._update_candidate_frontmatter(elixir_id, counter_evidence=["wiki/derived/evidence.md", "   "])

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_promote(self.root, elixir_id=elixir_id)
        self.assertIn("counter_evidence_invalid_format", str(ctx.exception))

    def test_promote_rejects_missing_counter_evidence(self) -> None:
        elixir_id = self._start_candidate_elixir()
        candidate_path = _candidate_path(self.root, elixir_id)
        original = candidate_path.read_text(encoding="utf-8")
        frontmatter = _parse_elixir_frontmatter(candidate_path)
        frontmatter.pop("counter_evidence", None)
        _write_elixir_markdown(candidate_path, frontmatter=frontmatter, body=original.split("---", 2)[-1].lstrip("\n"))

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_promote(self.root, elixir_id=elixir_id)
        self.assertIn("counter_evidence_required", str(ctx.exception))

    def test_promote_rejects_non_list_counter_evidence(self) -> None:
        for invalid_value in ["string", {}]:
            with self.subTest(counter_evidence=type(invalid_value).__name__):
                elixir_id = self._start_candidate_elixir(topic=f"non-list-{type(invalid_value).__name__}")
                self._update_candidate_frontmatter(elixir_id, counter_evidence=invalid_value)

                with self.assertRaises(ValueError) as ctx:
                    run_alchemy_promote(self.root, elixir_id=elixir_id)
                self.assertIn("counter_evidence_invalid_format", str(ctx.exception))

    def test_promote_rejects_missing_confidence_level(self) -> None:
        elixir_id = self._start_candidate_elixir()
        candidate_path = _candidate_path(self.root, elixir_id)
        original = candidate_path.read_text(encoding="utf-8")
        frontmatter = _parse_elixir_frontmatter(candidate_path)
        frontmatter["counter_evidence"] = ["wiki/derived/some-evidence.md"]
        frontmatter.pop("confidence_level", None)
        _write_elixir_markdown(candidate_path, frontmatter=frontmatter, body=original.split("---", 2)[-1].lstrip("\n"))

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_promote(self.root, elixir_id=elixir_id)
        self.assertIn("confidence_level_required", str(ctx.exception))

    def test_promote_accepts_none_found_with_low_confidence(self) -> None:
        elixir_id = self._start_candidate_elixir()
        self._update_candidate_frontmatter(elixir_id, counter_evidence=["NONE_FOUND"], confidence_level="low")

        result = run_alchemy_promote(self.root, elixir_id=elixir_id)

        self.assertEqual(result["elixir_state"], "settled")

    def test_promote_rejects_none_found_with_medium_confidence(self) -> None:
        elixir_id = self._start_candidate_elixir()
        self._update_candidate_frontmatter(elixir_id, counter_evidence=["NONE_FOUND"], confidence_level="medium")

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_promote(self.root, elixir_id=elixir_id)
        self.assertIn("none_found_requires_low_confidence", str(ctx.exception))

    def test_promote_rejects_none_found_mixed_with_other_evidence(self) -> None:
        for level in ["low", "medium", "high"]:
            with self.subTest(confidence_level=level):
                elixir_id = self._start_candidate_elixir(topic=f"mixed-none-found-{level}")
                self._update_candidate_frontmatter(
                    elixir_id,
                    counter_evidence=["NONE_FOUND", "some real evidence"],
                    confidence_level=level,
                )

                with self.assertRaises(ValueError) as ctx:
                    run_alchemy_promote(self.root, elixir_id=elixir_id)
                self.assertIn("counter_evidence_invalid_format", str(ctx.exception))

    def test_promote_rejects_none_found_at_non_first_position(self) -> None:
        elixir_id = self._start_candidate_elixir()
        self._update_candidate_frontmatter(
            elixir_id,
            counter_evidence=["evidence", "NONE_FOUND"],
            confidence_level="low",
        )

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_promote(self.root, elixir_id=elixir_id)
        self.assertIn("counter_evidence_invalid_format", str(ctx.exception))

    def test_promote_rejects_invalid_confidence_level(self) -> None:
        elixir_id = self._start_candidate_elixir()
        self._update_candidate_frontmatter(elixir_id, counter_evidence=["wiki/derived/evidence.md"], confidence_level="invalid")

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_promote(self.root, elixir_id=elixir_id)
        self.assertIn("confidence_level_required", str(ctx.exception))

    def test_promote_rejects_already_promoted(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_promote(self.root, elixir_id=elixir_id)
        self.assertIn("already_promoted", str(ctx.exception))

    def test_promote_rejects_draft_source(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "draft source", protocol="general")

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_promote(self.root, elixir_id=started["elixir_id"])
        self.assertIn("unsupported_source_state", str(ctx.exception))

    def test_promote_rejects_distilling_source(self) -> None:
        corpus_id = self._make_promoted_corpus()
        started = run_alchemy_start(self.root, corpus_id, "distilling source", protocol="general")
        run_alchemy_distill(self.root, started["elixir_id"], "refine")

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_promote(self.root, elixir_id=started["elixir_id"])
        self.assertIn("unsupported_source_state", str(ctx.exception))

    def test_promote_rejects_self_reference(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="promote-self-ref")
        candidate_path = _candidate_path(self.root, elixir_id)
        text = candidate_path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)
        anchor = str(frontmatter["derived_from"][0])
        frontmatter["derived_from"] = [anchor, f"wiki/elixirs/{elixir_id}.md"]
        _write_elixir_markdown(candidate_path, frontmatter=frontmatter, body=text.split("---", 2)[-1].lstrip("\n"))

        with patch("aiwiki.execution.alchemy._validate_source_outputs", return_value=None):
            with self.assertRaises(ValueError) as ctx:
                promote_elixir(self.root, elixir_id=elixir_id)

        self.assertIn("cannot reference self", str(ctx.exception))

    def test_promote_rejects_superseded_source(self) -> None:
        elixir_id = "candidate-superseded-promote"
        self._write_stub_elixir(_candidate_path(self.root, elixir_id), elixir_id=elixir_id, state="superseded")

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_promote(self.root, elixir_id=elixir_id)
        self.assertIn("unsupported_source_state", str(ctx.exception))

    def test_promote_raises_filenotfound_when_candidate_missing(self) -> None:
        with self.assertRaises(FileNotFoundError):
            run_alchemy_promote(self.root, elixir_id="missing-candidate")

    def test_promote_failure_after_settled_write_rolls_back_settled(self) -> None:
        elixir_id = self._start_candidate_elixir()
        candidate_path = _candidate_path(self.root, elixir_id)
        before = candidate_path.read_text(encoding="utf-8")
        from aiwiki.execution import alchemy as alchemy_module

        original_write = alchemy_module._write_atomic_text
        calls = {"count": 0}

        def _flaky_write(path: Path, content: str) -> None:
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("tombstone write failed")
            original_write(path, content)

        with patch("aiwiki.execution.alchemy._write_atomic_text", side_effect=_flaky_write):
            with self.assertRaises(OSError):
                promote_elixir(self.root, elixir_id=elixir_id)

        self.assertFalse(_settled_path(self.root, elixir_id).exists())
        self.assertEqual(candidate_path.read_text(encoding="utf-8"), before)
        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_promotion", subject_id=elixir_id)
        self.assertIsNone(latest)

    def test_promote_raises_halfwriteerror_when_unlink_also_fails(self) -> None:
        elixir_id = self._start_candidate_elixir()
        settled_path = _settled_path(self.root, elixir_id)
        candidate_path = _candidate_path(self.root, elixir_id)
        from aiwiki.execution import alchemy as alchemy_module

        original_write = alchemy_module._write_atomic_text
        calls = {"count": 0}

        def _flaky_write(path: Path, content: str) -> None:
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("tombstone write failed")
            original_write(path, content)

        with patch("aiwiki.execution.alchemy._write_atomic_text", side_effect=_flaky_write):
            with patch.object(Path, "unlink", autospec=True, side_effect=OSError("rollback unlink failed")):
                with self.assertRaises(PromoteHalfWriteError) as ctx:
                    promote_elixir(self.root, elixir_id=elixir_id)

        self.assertIn(str(settled_path), str(ctx.exception))
        self.assertIn(str(candidate_path), str(ctx.exception))

    def test_promote_does_not_rollback_when_receipt_write_fails(self) -> None:
        elixir_id = self._start_candidate_elixir()

        with patch("aiwiki.execution.alchemy.append_execution_receipt_history", side_effect=RuntimeError("history write failed")):
            result = run_alchemy_promote(self.root, elixir_id=elixir_id)

        settled_path = _settled_path(self.root, elixir_id)
        candidate_path = _candidate_path(self.root, elixir_id)
        self.assertEqual(result["elixir_state"], "settled")
        self.assertTrue(settled_path.exists())
        self.assertTrue(candidate_path.exists())
        settled_frontmatter = parse_frontmatter(settled_path.read_text(encoding="utf-8"))
        tombstone_frontmatter = parse_frontmatter(candidate_path.read_text(encoding="utf-8"))
        self.assertEqual(settled_frontmatter["elixir_state"], "settled")
        self.assertEqual(tombstone_frontmatter["elixir_state"], "superseded")
        self.assertTrue(result["receipt_path"])
        self.assertTrue((self.root / result["receipt_path"]).exists())

    def test_promote_failure_before_any_write_keeps_candidate_intact(self) -> None:
        elixir_id = self._start_candidate_elixir()
        candidate_path = _candidate_path(self.root, elixir_id)
        self._update_candidate_frontmatter(elixir_id, counter_evidence=[])
        expected = candidate_path.read_text(encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_promote(self.root, elixir_id=elixir_id)

        self.assertIn("counter_evidence_required", str(ctx.exception))
        self.assertEqual(candidate_path.read_text(encoding="utf-8"), expected)
        self.assertFalse(_settled_path(self.root, elixir_id).exists())
        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_promotion", subject_id=elixir_id)
        self.assertIsNone(latest)

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

    def test_collect_dependent_elixir_ids_finds_settled_dependents(self) -> None:
        source_id = "source-elixir"
        self._write_stub_elixir(_settled_path(self.root, source_id), elixir_id=source_id, state="settled")
        self._write_stub_elixir(_settled_path(self.root, "dependent-b"), elixir_id="dependent-b", state="settled")
        self._write_stub_elixir(_settled_path(self.root, "dependent-c"), elixir_id="dependent-c", state="settled")
        self._update_frontmatter(
            _settled_path(self.root, "dependent-b"),
            derived_from=["wiki/derived/base.md", f"wiki/elixirs/{source_id}.md"],
        )
        self._update_frontmatter(
            _settled_path(self.root, "dependent-c"),
            derived_from=[f"wiki/elixirs/{source_id}.md", "wiki/derived/base.md"],
        )

        dependent_ids = _collect_dependent_elixir_ids(self.root, source_elixir_id=source_id)

        self.assertEqual(dependent_ids, ["dependent-b", "dependent-c"])

    def test_collect_dependent_elixir_ids_excludes_self(self) -> None:
        source_id = "self-elixir"
        self._write_stub_elixir(_settled_path(self.root, source_id), elixir_id=source_id, state="settled")
        self._update_frontmatter(
            _settled_path(self.root, source_id),
            derived_from=["wiki/derived/base.md", f"wiki/elixirs/{source_id}.md"],
        )

        dependent_ids = _collect_dependent_elixir_ids(self.root, source_elixir_id=source_id)

        self.assertEqual(dependent_ids, [])

    def test_collect_dependent_elixir_ids_ignores_candidate_plane(self) -> None:
        source_id = "source-for-candidate-ignore"
        self._write_stub_elixir(_settled_path(self.root, source_id), elixir_id=source_id, state="settled")
        candidate_like = self.root / "wiki" / "elixirs" / "candidates" / "dependent-candidate.md"
        candidate_like.parent.mkdir(parents=True, exist_ok=True)
        candidate_like.write_text(
            "\n".join(
                [
                    "---",
                    'kind: "elixir"',
                    'elixir_id: "dependent-candidate"',
                    'elixir_state: "settled"',
                    'protocol: "general"',
                    'iteration: "0"',
                    'provenance_corpus: "corp"',
                    "derived_from:",
                    f'  - "wiki/elixirs/{source_id}.md"',
                    'topic: "topic"',
                    "counter_evidence:",
                    '  - "NONE_FOUND"',
                    'confidence_level: "low"',
                    'created_at: "2026-01-01T00:00:00+00:00"',
                    'updated_at: "2026-01-01T00:00:00+00:00"',
                    'distill_history_json: "[]"',
                    "---",
                    "# Elixir",
                ]
            ),
            encoding="utf-8",
        )

        dependent_ids = _collect_dependent_elixir_ids(self.root, source_elixir_id=source_id)

        self.assertEqual(dependent_ids, [])

    def test_collect_dependent_elixir_ids_handles_missing_frontmatter(self) -> None:
        source_id = "source-missing-frontmatter"
        self._write_stub_elixir(_settled_path(self.root, source_id), elixir_id=source_id, state="settled")
        self._write_stub_elixir(_settled_path(self.root, "good-dependent"), elixir_id="good-dependent", state="settled")
        self._update_frontmatter(
            _settled_path(self.root, "good-dependent"),
            derived_from=[f"wiki/elixirs/{source_id}.md"],
        )
        (_settled_path(self.root, "broken-frontmatter")).write_text("# broken\n", encoding="utf-8")

        dependent_ids = _collect_dependent_elixir_ids(self.root, source_elixir_id=source_id)

        self.assertEqual(dependent_ids, ["good-dependent"])

    def test_collect_dependent_elixir_ids_returns_sorted(self) -> None:
        source_id = "source-sorted"
        self._write_stub_elixir(_settled_path(self.root, source_id), elixir_id=source_id, state="settled")
        for dependent_id in ["zeta-dependent", "alpha-dependent", "beta-dependent"]:
            self._write_stub_elixir(_settled_path(self.root, dependent_id), elixir_id=dependent_id, state="settled")
            self._update_frontmatter(
                _settled_path(self.root, dependent_id),
                derived_from=[f"wiki/elixirs/{source_id}.md"],
            )

        dependent_ids = _collect_dependent_elixir_ids(self.root, source_elixir_id=source_id)

        self.assertEqual(dependent_ids, ["alpha-dependent", "beta-dependent", "zeta-dependent"])

    def test_collect_dependent_elixir_ids_returns_empty_when_settled_dir_missing(self) -> None:
        dependent_ids = _collect_dependent_elixir_ids(self.root, source_elixir_id="missing-source")

        self.assertEqual(dependent_ids, [])

    def test_collect_dependent_elixir_ids_ignores_non_list_derived_from(self) -> None:
        source_id = "source-non-list-derived-from"
        self._write_stub_elixir(_settled_path(self.root, source_id), elixir_id=source_id, state="settled")
        dependent_id = "dependent-with-string-derived-from"
        self._write_stub_elixir(_settled_path(self.root, dependent_id), elixir_id=dependent_id, state="settled")
        self._update_frontmatter(
            _settled_path(self.root, dependent_id),
            derived_from=f"wiki/elixirs/{source_id}.md",
        )

        dependent_ids = _collect_dependent_elixir_ids(self.root, source_elixir_id=source_id)

        self.assertEqual(dependent_ids, [])

    def test_validate_source_outputs_rejects_blank_ref(self) -> None:
        with self.assertRaises(ValueError):
            _validate_source_outputs(self.root, [""], allowed=set())

    def test_revert_deletes_settled_and_restores_candidate(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)

        result_path = run_alchemy_revert(self.root, elixir_id=elixir_id)

        self.assertEqual(result_path, _candidate_path(self.root, elixir_id))
        self.assertFalse(_settled_path(self.root, elixir_id).exists())
        self.assertTrue(_candidate_path(self.root, elixir_id).exists())
        frontmatter = _parse_elixir_frontmatter(_candidate_path(self.root, elixir_id))
        self.assertEqual(frontmatter["elixir_state"], "candidate")

    def test_revert_clears_superseded_by_and_promoted_at(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)

        run_alchemy_revert(self.root, elixir_id=elixir_id)

        frontmatter = _parse_elixir_frontmatter(_candidate_path(self.root, elixir_id))
        self.assertNotIn("superseded_by", frontmatter)
        self.assertNotIn("promoted_at", frontmatter)
        self.assertEqual(frontmatter["elixir_state"], "candidate")

    def test_revert_writes_receipt_with_source_receipt_applied_at(self) -> None:
        elixir_id = self._start_candidate_elixir()
        promote_result = run_alchemy_promote(self.root, elixir_id=elixir_id)
        promote_receipt = json.loads((self.root / str(promote_result["receipt_path"])).read_text(encoding="utf-8"))

        run_alchemy_revert(self.root, elixir_id=elixir_id, note="undo")

        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_revert", subject_id=elixir_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        receipt_path = self.root / str(latest["receipt_path"])
        self.assertTrue(receipt_path.exists())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["subject_kind"], "elixir_revert")
        self.assertEqual(receipt["apply_mode"], "elixir-revert")
        self.assertEqual(receipt["operation"], "revert")
        self.assertEqual(receipt["generated_by"], "aiwiki-elixir-revert")
        self.assertRegex(str(receipt["action_id"]), rf"^elixir-revert-{slugify(elixir_id)}-\d{{13}}(?:-\d+)?$")
        self.assertEqual(receipt["bundle"].get("from_state"), "settled")
        self.assertEqual(receipt["bundle"].get("tombstone_from_state"), "superseded")
        self.assertEqual(receipt["bundle"].get("to_state"), "candidate")
        self.assertEqual(receipt["bundle"].get("candidate_path"), f"output/_candidates/elixirs/{elixir_id}.md")
        self.assertEqual(receipt["bundle"].get("wiki_path"), f"wiki/elixirs/{elixir_id}.md")
        self.assertEqual(receipt["bundle"].get("source_receipt_applied_at"), promote_receipt["applied_at"])
        self.assertEqual(receipt["bundle"].get("source_receipt_action_id"), promote_receipt["action_id"])
        self.assertEqual(receipt["note"], "undo")

    def test_revert_writes_dependency_breaks_in_bundle(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-break-source")
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        dependent_id = "dependent-for-revert"
        self._write_stub_elixir(_settled_path(self.root, dependent_id), elixir_id=dependent_id, state="settled")
        self._update_frontmatter(
            _settled_path(self.root, dependent_id),
            derived_from=["wiki/derived/base.md", f"wiki/elixirs/{elixir_id}.md"],
        )

        run_alchemy_revert(self.root, elixir_id=elixir_id)

        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_revert", subject_id=elixir_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        bundle = latest.get("bundle")
        self.assertIsInstance(bundle, dict)
        assert isinstance(bundle, dict)
        self.assertEqual(
            bundle.get("dependency_breaks"),
            [{"dependent_elixir_id": dependent_id, "break_reason": "source_reverted"}],
        )

    def test_revert_dependency_break_collection_failure_falls_back_to_empty_list(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-break-collector-failure")
        run_alchemy_promote(self.root, elixir_id=elixir_id)

        with patch("aiwiki.execution.alchemy._collect_dependent_elixir_ids", side_effect=RuntimeError("boom")):
            run_alchemy_revert(self.root, elixir_id=elixir_id)

        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_revert", subject_id=elixir_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        bundle = latest.get("bundle")
        self.assertIsInstance(bundle, dict)
        assert isinstance(bundle, dict)
        self.assertEqual(bundle.get("dependency_breaks"), [])

    def test_revert_rejects_missing_promotion_receipt(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        history_path = self.root / ".aiwiki" / "state" / "execution-receipts.jsonl"
        history_path.unlink(missing_ok=True)

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_revert(self.root, elixir_id=elixir_id)
        self.assertIn("promotion_receipt_missing:", str(ctx.exception))

    def test_revert_rejects_missing_tombstone(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        _candidate_path(self.root, elixir_id).unlink()

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_revert(self.root, elixir_id=elixir_id)
        self.assertIn("revert_tombstone_missing", str(ctx.exception))

    def test_revert_action_id_includes_epoch_ms_suffix(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-action-id-ms")
        run_alchemy_promote(self.root, elixir_id=elixir_id)

        run_alchemy_revert(self.root, elixir_id=elixir_id)

        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_revert", subject_id=elixir_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertRegex(str(latest.get("action_id") or ""), rf"^elixir-revert-{slugify(elixir_id)}-\d{{13}}(?:-\d+)?$")

    def test_revert_action_id_collision_fallback(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-collision")
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        fixed_dt = datetime(2026, 1, 1, 0, 0, 0, 456000, tzinfo=timezone.utc)
        base = f"elixir-revert-{slugify(elixir_id)}"
        occupied_action_id = f"{base}-{int(fixed_dt.timestamp() * 1000)}"
        occupied_path = execution_receipt_path(self.root, occupied_action_id)
        occupied_path.parent.mkdir(parents=True, exist_ok=True)
        occupied_path.write_text("{}\n", encoding="utf-8")

        with patch("aiwiki.execution.alchemy.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = fixed_dt
            run_alchemy_revert(self.root, elixir_id=elixir_id)

        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_revert", subject_id=elixir_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.get("action_id"), f"{occupied_action_id}-2")

    def test_demote_action_id_includes_epoch_ms_suffix(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="demote-action-id-ms")
        run_alchemy_promote(self.root, elixir_id=elixir_id)

        run_alchemy_demote(self.root, elixir_id=elixir_id)

        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_demotion", subject_id=elixir_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertRegex(str(latest.get("action_id") or ""), rf"^elixir-demote-{slugify(elixir_id)}-\d{{13}}(?:-\d+)?$")

    def test_demote_action_id_collision_fallback(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="demote-collision")
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        fixed_dt = datetime(2026, 1, 1, 0, 0, 0, 789000, tzinfo=timezone.utc)
        base = f"elixir-demote-{slugify(elixir_id)}"
        occupied_action_id = f"{base}-{int(fixed_dt.timestamp() * 1000)}"
        occupied_path = execution_receipt_path(self.root, occupied_action_id)
        occupied_path.parent.mkdir(parents=True, exist_ok=True)
        occupied_path.write_text("{}\n", encoding="utf-8")

        with patch("aiwiki.execution.alchemy.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = fixed_dt
            run_alchemy_demote(self.root, elixir_id=elixir_id)

        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_demotion", subject_id=elixir_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.get("action_id"), f"{occupied_action_id}-2")

    def test_revert_uses_hash_first_when_receipt_has_hashes(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-hash-first")
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        settled = _settled_path(self.root, elixir_id)
        original_bytes = settled.read_bytes()
        stat = settled.stat()
        mutated = (original_bytes + b"\n") if original_bytes else b"x"
        if mutated == original_bytes:
            mutated = original_bytes + b"x"
        settled.write_bytes(mutated)
        os.utime(settled, (stat.st_atime, stat.st_mtime))

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_revert(self.root, elixir_id=elixir_id)
        self.assertIn("revert_conflict_settled_modified", str(ctx.exception))

    def test_revert_uses_hash_for_tombstone_when_receipt_has_hashes(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-hash-tombstone")
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        candidate = _candidate_path(self.root, elixir_id)
        original_bytes = candidate.read_bytes()
        candidate.write_bytes(original_bytes + b"\n# changed")

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_revert(self.root, elixir_id=elixir_id)
        self.assertIn("revert_conflict_candidate_modified", str(ctx.exception))

    def test_revert_ignores_receipt_applied_at_when_hashes_match(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-hash-only")
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        entries = _receipt_history_entries(self.root)
        for index in range(len(entries) - 1, -1, -1):
            entry = entries[index]
            if entry.get("subject_kind") == "elixir_promotion" and entry.get("subject_id") == elixir_id:
                rewritten = dict(entry)
                rewritten["applied_at"] = "1999-01-01T00:00:00+00:00"
                entries[index] = rewritten
                break
        _write_receipt_history_entries(self.root, entries)

        result_path = run_alchemy_revert(self.root, elixir_id=elixir_id)

        self.assertEqual(result_path, _candidate_path(self.root, elixir_id))
        self.assertFalse(_settled_path(self.root, elixir_id).exists())

    def test_revert_elixir_missing_primary_hash_returns_promotion_receipt_missing_hash(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-missing-primary-hash")
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        entries = _receipt_history_entries(self.root)
        for index in range(len(entries) - 1, -1, -1):
            entry = entries[index]
            if entry.get("subject_kind") == "elixir_promotion" and entry.get("subject_id") == elixir_id:
                rewritten = dict(entry)
                bundle = rewritten.get("bundle")
                rewritten_bundle = dict(bundle) if isinstance(bundle, dict) else {}
                rewritten_bundle.pop("primary_path_sha256", None)
                rewritten["bundle"] = rewritten_bundle
                entries[index] = rewritten
                break
        _write_receipt_history_entries(self.root, entries)

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_revert(self.root, elixir_id=elixir_id)
        self.assertIn("promotion_receipt_missing_hash", str(ctx.exception))

    def test_revert_elixir_missing_secondary_hash_returns_promotion_receipt_missing_hash(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-missing-secondary-hash")
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        entries = _receipt_history_entries(self.root)
        for index in range(len(entries) - 1, -1, -1):
            entry = entries[index]
            if entry.get("subject_kind") == "elixir_promotion" and entry.get("subject_id") == elixir_id:
                rewritten = dict(entry)
                bundle = rewritten.get("bundle")
                rewritten_bundle = dict(bundle) if isinstance(bundle, dict) else {}
                rewritten_bundle.pop("secondary_path_sha256", None)
                rewritten["bundle"] = rewritten_bundle
                entries[index] = rewritten
                break
        _write_receipt_history_entries(self.root, entries)

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_revert(self.root, elixir_id=elixir_id)
        self.assertIn("promotion_receipt_missing_hash", str(ctx.exception))

    def test_revert_elixir_bundle_not_dict_returns_promotion_receipt_missing_hash(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-bundle-not-dict")
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        entries = _receipt_history_entries(self.root)
        for index in range(len(entries) - 1, -1, -1):
            entry = entries[index]
            if entry.get("subject_kind") == "elixir_promotion" and entry.get("subject_id") == elixir_id:
                rewritten = dict(entry)
                rewritten["bundle"] = []
                entries[index] = rewritten
                break
        _write_receipt_history_entries(self.root, entries)

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_revert(self.root, elixir_id=elixir_id)
        self.assertIn("promotion_receipt_missing_hash", str(ctx.exception))

    def test_revert_elixir_empty_string_hash_returns_promotion_receipt_missing_hash(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-empty-string-hash")
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        entries = _receipt_history_entries(self.root)
        for index in range(len(entries) - 1, -1, -1):
            entry = entries[index]
            if entry.get("subject_kind") == "elixir_promotion" and entry.get("subject_id") == elixir_id:
                rewritten = dict(entry)
                bundle = rewritten.get("bundle")
                rewritten_bundle = dict(bundle) if isinstance(bundle, dict) else {}
                rewritten_bundle["primary_path_sha256"] = ""
                rewritten["bundle"] = rewritten_bundle
                entries[index] = rewritten
                break
        _write_receipt_history_entries(self.root, entries)

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_revert(self.root, elixir_id=elixir_id)
        self.assertIn("promotion_receipt_missing_hash", str(ctx.exception))

    def test_revert_elixir_whitespace_only_hash_returns_promotion_receipt_missing_hash(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-whitespace-hash")
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        entries = _receipt_history_entries(self.root)
        for index in range(len(entries) - 1, -1, -1):
            entry = entries[index]
            if entry.get("subject_kind") == "elixir_promotion" and entry.get("subject_id") == elixir_id:
                rewritten = dict(entry)
                bundle = rewritten.get("bundle")
                rewritten_bundle = dict(bundle) if isinstance(bundle, dict) else {}
                rewritten_bundle["primary_path_sha256"] = "   "
                rewritten["bundle"] = rewritten_bundle
                entries[index] = rewritten
                break
        _write_receipt_history_entries(self.root, entries)

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_revert(self.root, elixir_id=elixir_id)
        self.assertIn("promotion_receipt_missing_hash", str(ctx.exception))

    def test_revert_missing_settled_raises_file_not_found(self) -> None:
        with self.assertRaises(FileNotFoundError):
            run_alchemy_revert(self.root, elixir_id="missing-revert-target")

    def test_revert_does_not_rollback_when_receipt_write_fails(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="revert-receipt-write-failure")
        run_alchemy_promote(self.root, elixir_id=elixir_id)

        with patch("aiwiki.execution.alchemy.append_execution_receipt_history", side_effect=RuntimeError("history write failed")):
            result_path = run_alchemy_revert(self.root, elixir_id=elixir_id)

        self.assertEqual(result_path, _candidate_path(self.root, elixir_id))
        self.assertFalse(_settled_path(self.root, elixir_id).exists())
        self.assertTrue(_candidate_path(self.root, elixir_id).exists())

    def test_compute_file_sha256_helper(self) -> None:
        target = self.root / "tmp-hash.txt"
        target.write_text("abc", encoding="utf-8")

        digest = compute_file_sha256(target)

        self.assertEqual(digest, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_promote_skips_receipt_when_hash_anchor_compute_missing_file(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="promote-hash-anchor-missing")

        with patch("aiwiki.execution.alchemy.compute_file_sha256", side_effect=FileNotFoundError("missing")):
            result = run_alchemy_promote(self.root, elixir_id=elixir_id)

        self.assertEqual(result["receipt_path"], "")
        self.assertTrue(_settled_path(self.root, elixir_id).exists())
        self.assertTrue(_candidate_path(self.root, elixir_id).exists())

    def test_revert_rejects_modified_tombstone(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        candidate = _candidate_path(self.root, elixir_id)
        original = candidate.read_text(encoding="utf-8")
        frontmatter = _parse_elixir_frontmatter(candidate)
        frontmatter["promoted_at"] = "2099-01-01T00:00:00+00:00"
        _write_elixir_markdown(candidate, frontmatter=frontmatter, body=original.split("---", 2)[-1].lstrip("\n"))

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_revert(self.root, elixir_id=elixir_id)
        self.assertIn("revert_conflict_candidate_modified", str(ctx.exception))

    def test_revert_rejects_non_superseded_tombstone_state(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        candidate = _candidate_path(self.root, elixir_id)
        original = candidate.read_text(encoding="utf-8")
        frontmatter = _parse_elixir_frontmatter(candidate)
        frontmatter["elixir_state"] = "candidate"
        _write_elixir_markdown(candidate, frontmatter=frontmatter, body=original.split("---", 2)[-1].lstrip("\n"))

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_revert(self.root, elixir_id=elixir_id)
        self.assertIn("unsupported_source_state", str(ctx.exception))

    def test_revert_failure_after_candidate_write_rolls_back_to_tombstone(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        candidate_path = _candidate_path(self.root, elixir_id)
        tombstone_before = candidate_path.read_text(encoding="utf-8")

        with patch.object(Path, "unlink", autospec=True, side_effect=OSError("unlink failed")):
            with self.assertRaises(OSError):
                revert_elixir(self.root, elixir_id=elixir_id)

        self.assertEqual(candidate_path.read_text(encoding="utf-8"), tombstone_before)
        self.assertTrue(_settled_path(self.root, elixir_id).exists())

    def test_revert_raises_halfwriteerror_when_rollback_also_fails(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        settled_path = _settled_path(self.root, elixir_id)
        candidate_path = _candidate_path(self.root, elixir_id)
        from aiwiki.execution import alchemy as alchemy_module

        original_write = alchemy_module._write_atomic_text
        calls = {"count": 0}

        def _flaky_write(path: Path, content: str) -> None:
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("rollback candidate write failed")
            original_write(path, content)

        with patch("aiwiki.execution.alchemy._write_atomic_text", side_effect=_flaky_write):
            with patch.object(Path, "unlink", autospec=True, side_effect=OSError("unlink failed")):
                with self.assertRaises(RevertHalfWriteError) as ctx:
                    revert_elixir(self.root, elixir_id=elixir_id)

        self.assertIn(str(settled_path), str(ctx.exception))
        self.assertIn(str(candidate_path), str(ctx.exception))

    def test_demote_deletes_settled_and_creates_candidate(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)

        result_path = run_alchemy_demote(self.root, elixir_id=elixir_id)

        self.assertEqual(result_path, _candidate_path(self.root, elixir_id))
        self.assertFalse(_settled_path(self.root, elixir_id).exists())
        self.assertTrue(_candidate_path(self.root, elixir_id).exists())
        frontmatter = _parse_elixir_frontmatter(_candidate_path(self.root, elixir_id))
        self.assertEqual(frontmatter["elixir_state"], "candidate")

    def test_demote_preserves_settled_content_as_candidate_body(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        settled = _settled_path(self.root, elixir_id)
        settled_text = settled.read_text(encoding="utf-8")
        settled.write_text(settled_text + "\nDemote body sentinel.\n", encoding="utf-8")

        run_alchemy_demote(self.root, elixir_id=elixir_id)

        candidate_text = _candidate_path(self.root, elixir_id).read_text(encoding="utf-8")
        self.assertIn("Demote body sentinel.", candidate_text)

    def test_demote_writes_receipt(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)

        run_alchemy_demote(self.root, elixir_id=elixir_id, note="demote")

        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_demotion", subject_id=elixir_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        receipt_path = self.root / str(latest["receipt_path"])
        self.assertTrue(receipt_path.exists())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["subject_kind"], "elixir_demotion")
        self.assertEqual(receipt["apply_mode"], "elixir-demote")
        self.assertEqual(receipt["operation"], "demote")
        self.assertEqual(receipt["generated_by"], "aiwiki-elixir-demote")
        self.assertRegex(str(receipt["action_id"]), rf"^elixir-demote-{slugify(elixir_id)}-\d{{13}}(?:-\d+)?$")
        self.assertEqual(receipt["bundle"].get("from_state"), "settled")
        self.assertEqual(receipt["bundle"].get("to_state"), "candidate")
        self.assertEqual(receipt["bundle"].get("candidate_path"), f"output/_candidates/elixirs/{elixir_id}.md")
        self.assertEqual(receipt["bundle"].get("wiki_path"), f"wiki/elixirs/{elixir_id}.md")
        self.assertEqual(receipt["bundle"].get("dependency_breaks"), [])
        self.assertEqual(receipt["note"], "demote")

    def test_demote_writes_dependency_breaks_in_bundle(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="demote-break-source")
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        dependent_id = "dependent-for-demote"
        self._write_stub_elixir(_settled_path(self.root, dependent_id), elixir_id=dependent_id, state="settled")
        self._update_frontmatter(
            _settled_path(self.root, dependent_id),
            derived_from=[f"wiki/elixirs/{elixir_id}.md", "wiki/derived/base.md"],
        )

        run_alchemy_demote(self.root, elixir_id=elixir_id)

        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_demotion", subject_id=elixir_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        bundle = latest.get("bundle")
        self.assertIsInstance(bundle, dict)
        assert isinstance(bundle, dict)
        self.assertEqual(
            bundle.get("dependency_breaks"),
            [{"dependent_elixir_id": dependent_id, "break_reason": "source_demoted"}],
        )

    def test_demote_with_no_dependents_writes_empty_breaks(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="demote-no-dependent")
        run_alchemy_promote(self.root, elixir_id=elixir_id)

        run_alchemy_demote(self.root, elixir_id=elixir_id)

        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_demotion", subject_id=elixir_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        bundle = latest.get("bundle")
        self.assertIsInstance(bundle, dict)
        assert isinstance(bundle, dict)
        self.assertEqual(bundle.get("dependency_breaks"), [])

    def test_demote_dependency_break_collection_failure_falls_back_to_empty_list(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="demote-break-collector-failure")
        run_alchemy_promote(self.root, elixir_id=elixir_id)

        with patch("aiwiki.execution.alchemy._collect_dependent_elixir_ids", side_effect=RuntimeError("boom")):
            run_alchemy_demote(self.root, elixir_id=elixir_id)

        latest = _latest_receipt_by_subject(self.root, subject_kind="elixir_demotion", subject_id=elixir_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        bundle = latest.get("bundle")
        self.assertIsInstance(bundle, dict)
        assert isinstance(bundle, dict)
        self.assertEqual(bundle.get("dependency_breaks"), [])

    def test_promote_does_not_write_dependency_breaks(self) -> None:
        elixir_id = self._start_candidate_elixir(topic="promote-no-breaks")

        result = run_alchemy_promote(self.root, elixir_id=elixir_id)

        receipt = json.loads((self.root / str(result["receipt_path"])).read_text(encoding="utf-8"))
        bundle = receipt.get("bundle")
        self.assertIsInstance(bundle, dict)
        assert isinstance(bundle, dict)
        self.assertNotIn("dependency_breaks", bundle)

    def test_demote_accepts_externally_modified_settled(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        settled = _settled_path(self.root, elixir_id)
        text = settled.read_text(encoding="utf-8")
        settled.write_text(text + "\nExternally edited settled text.\n", encoding="utf-8")

        result = run_alchemy_demote(self.root, elixir_id=elixir_id)

        self.assertEqual(result, _candidate_path(self.root, elixir_id))
        self.assertIn("Externally edited settled text.", _candidate_path(self.root, elixir_id).read_text(encoding="utf-8"))

    def test_demote_accepts_missing_tombstone(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        _candidate_path(self.root, elixir_id).unlink()

        result = run_alchemy_demote(self.root, elixir_id=elixir_id)

        self.assertEqual(result, _candidate_path(self.root, elixir_id))
        self.assertTrue(_candidate_path(self.root, elixir_id).exists())
        self.assertFalse(_settled_path(self.root, elixir_id).exists())

    def test_demote_rejects_non_settled_source(self) -> None:
        elixir_id = "demote-non-settled"
        self._write_stub_elixir(_settled_path(self.root, elixir_id), elixir_id=elixir_id, state="draft")

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_demote(self.root, elixir_id=elixir_id)
        self.assertIn("unsupported_source_state", str(ctx.exception))

    def test_demote_rejects_conflicting_candidate_plane_state(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        candidate = _candidate_path(self.root, elixir_id)
        original = candidate.read_text(encoding="utf-8")
        frontmatter = _parse_elixir_frontmatter(candidate)
        frontmatter["elixir_state"] = "candidate"
        _write_elixir_markdown(candidate, frontmatter=frontmatter, body=original.split("---", 2)[-1].lstrip("\n"))

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_demote(self.root, elixir_id=elixir_id)
        self.assertIn("demote_conflict_candidate_exists", str(ctx.exception))

    def test_demote_failure_after_candidate_write_rolls_back(self) -> None:
        elixir_id = self._start_candidate_elixir()
        run_alchemy_promote(self.root, elixir_id=elixir_id)
        candidate_path = _candidate_path(self.root, elixir_id)
        before = candidate_path.read_text(encoding="utf-8")

        with patch.object(Path, "unlink", autospec=True, side_effect=OSError("unlink failed")):
            with self.assertRaises(OSError):
                demote_elixir(self.root, elixir_id=elixir_id)

        self.assertEqual(candidate_path.read_text(encoding="utf-8"), before)
        self.assertTrue(_settled_path(self.root, elixir_id).exists())

    def test_find_latest_elixir_promotion_receipt_returns_most_recent(self) -> None:
        history_path = self.root / ".aiwiki" / "state" / "execution-receipts.jsonl"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            "not-json",
            json.dumps({"subject_kind": "other", "subject_id": "x", "applied_at": "2026-01-01T00:00:00+00:00"}),
            json.dumps({"subject_kind": "elixir_promotion", "subject_id": "elixir-a", "applied_at": "2026-01-01T00:00:00+00:00"}),
            json.dumps({"subject_kind": "elixir_promotion", "subject_id": "elixir-a", "applied_at": "2026-01-01T00:01:00+00:00"}),
        ]
        history_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

        latest = find_latest_elixir_promotion_receipt(self.root, elixir_id="elixir-a")

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest["applied_at"], "2026-01-01T00:01:00+00:00")

    def test_find_latest_elixir_promotion_receipt_skips_non_dict_lines(self) -> None:
        history_path = self.root / ".aiwiki" / "state" / "execution-receipts.jsonl"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        expected = {
            "subject_kind": "elixir_promotion",
            "subject_id": "elixir-a",
            "applied_at": "2026-01-01T00:02:00+00:00",
        }
        rows = [
            "[]",
            "null",
            json.dumps(expected),
        ]
        history_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

        latest = find_latest_elixir_promotion_receipt(self.root, elixir_id="elixir-a")

        self.assertEqual(latest, expected)

    def test_find_latest_elixir_promotion_receipt_handles_missing_history_file(self) -> None:
        history_path = self.root / ".aiwiki" / "state" / "execution-receipts.jsonl"
        history_path.unlink(missing_ok=True)

        latest = find_latest_elixir_promotion_receipt(self.root, elixir_id="elixir-a")

        self.assertIsNone(latest)


if __name__ == "__main__":
    unittest.main()
