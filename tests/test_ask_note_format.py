"""EP-002a: `note` output format — render + validator + parser choices lock.

Scope:
- `render_note_answer` produces frontmatter (`format: note`) + `# {question}` +
  `## 回答` + `## 优先来源` / `## 优先概念` blocks; not subject to report's 6-section
  skeleton.
- `_validate_output_markdown` for `note`:
  - PASS: has frontmatter + at least one `wiki/sources/...` citation.
  - FAIL: missing frontmatter raises.
  - FAIL: source_ids present but no `wiki/sources/` citation raises.
  - PASS: empty source_ids skips citation check.
- CLI parsers (`ask`, `run-ask`) expose `note` in --format choices; default
  is `note` (EP-002b flipped default from `report`); explicit `--format report`
  still resolves to `report` and runs the R97-98.3 decision-grade path.
"""

import argparse
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aiwiki.app_queries import render_note_answer
from aiwiki.cli.parsers import build_parser
from aiwiki.runner.prompts import _validate_output_markdown


def _protocol_state() -> dict:
    return {
        "active_protocol": "general",
        "protocols": {"general": {"title": "General", "owner": "ops"}},
    }


def _machine_query() -> dict:
    return {
        "ranked_source_ids": [],
        "ranked_concept_slugs": [],
        "focus_terms": [],
    }


class RenderNoteAnswerTests(unittest.TestCase):
    def test_frontmatter_and_required_blocks_present(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = render_note_answer(
                root,
                "What is X?",
                entries=[],
                concepts=[],
                machine_query=_machine_query(),
                protocol_state=_protocol_state(),
                created_at="2025-01-01T00:00:00Z",
                artifact_id="what-is-x-note",
            )
        self.assertIn('format: "note"', content)
        self.assertIn('kind: "output"', content)
        self.assertIn('id: "what-is-x-note"', content)
        self.assertIn("# What is X?", content)
        self.assertIn("## 回答", content)
        self.assertIn("## 优先来源", content)
        self.assertIn("## 优先概念", content)
        # Note format must NOT carry the report 6-section skeleton.
        self.assertNotIn("## 结论", content)
        self.assertNotIn("## 关键证据", content)
        self.assertNotIn("## 反证与不确定性", content)


class ValidateNoteOutputTests(unittest.TestCase):
    _BODY_WITH_CITATION = (
        "---\nformat: note\n---\n\n# Q\n\n## 回答\n答案见 wiki/sources/source-1.md。\n"
    )

    def test_valid_note_passes(self) -> None:
        _validate_output_markdown(self._BODY_WITH_CITATION, "note", ["source-1"])

    def test_missing_frontmatter_raises(self) -> None:
        bad = "# Q\n\n## 回答\n答案见 wiki/sources/source-1.md。\n"
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "note", ["source-1"])
        self.assertIn("frontmatter", str(ctx.exception))

    def test_missing_citation_when_sources_present_raises(self) -> None:
        bad = "---\nformat: note\n---\n\n# Q\n\n## 回答\n答案。\n"
        with self.assertRaises(RuntimeError) as ctx:
            _validate_output_markdown(bad, "note", ["source-1"])
        self.assertIn("citation", str(ctx.exception).lower())

    def test_empty_sources_skips_citation_check(self) -> None:
        body = "---\nformat: note\n---\n\n# Q\n\n## 回答\n纯判断。\n"
        # Must NOT raise.
        _validate_output_markdown(body, "note", [])

    def test_note_does_not_require_report_sections(self) -> None:
        # Bare note body without any report section must pass.
        body = "---\nformat: note\n---\n\n# Q\n\n## 回答\n见 wiki/sources/a.md。\n"
        _validate_output_markdown(body, "note", ["a"])


class AskParserChoicesLockTests(unittest.TestCase):
    """Lock that `note` is a registered --format choice for both ask entries,
    that default is `note` (EP-002b), and that explicit `--format report`
    still works so the decision-grade path remains accessible."""

    def _ns(self, argv: list[str]) -> argparse.Namespace:
        parser = build_parser()
        return parser.parse_args(argv)

    def test_ask_accepts_note(self) -> None:
        ns = self._ns(["ask", "Q", "--format", "note"])
        self.assertEqual(ns.format, "note")

    def test_ask_default_is_note(self) -> None:
        # EP-002b: default flipped from "report" to "note".
        ns = self._ns(["ask", "Q"])
        self.assertEqual(ns.format, "note")

    def test_ask_explicit_report_still_works(self) -> None:
        # EP-002b regression: report path remains accessible via explicit flag.
        ns = self._ns(["ask", "Q", "--format", "report"])
        self.assertEqual(ns.format, "report")

    def test_run_ask_accepts_note(self) -> None:
        ns = self._ns(["run-ask", "Q", "--format", "note"])
        self.assertEqual(ns.format, "note")

    def test_run_ask_default_is_note(self) -> None:
        ns = self._ns(["run-ask", "Q"])
        self.assertEqual(ns.format, "note")

    def test_run_ask_explicit_report_still_works(self) -> None:
        ns = self._ns(["run-ask", "Q", "--format", "report"])
        self.assertEqual(ns.format, "report")

    def test_ask_rejects_unknown_format(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["ask", "Q", "--format", "bogus"])


if __name__ == "__main__":
    unittest.main()
