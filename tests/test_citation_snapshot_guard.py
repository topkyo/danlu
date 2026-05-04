from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aiwiki.execution.machine_memory_actions import _validate_citation_page_path


class CitationSnapshotGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_citation_snapshot_allows_wiki_judgments(self) -> None:
        page = self.root / "wiki" / "judgments" / "foo.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("---\ntitle: Foo\n---\n\nBody\n", encoding="utf-8")

        resolved = _validate_citation_page_path(self.root, "wiki/judgments/foo.md")

        self.assertEqual(resolved, page.resolve())

    def test_citation_snapshot_allows_wiki_decisions(self) -> None:
        page = self.root / "wiki" / "decisions" / "bar.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("---\ntitle: Bar\n---\n\nBody\n", encoding="utf-8")

        resolved = _validate_citation_page_path(self.root, "wiki/decisions/bar.md")

        self.assertEqual(resolved, page.resolve())

    def test_citation_snapshot_rejects_wiki_sources(self) -> None:
        page = self.root / "wiki" / "sources" / "x.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("source\n", encoding="utf-8")

        with self.assertRaises(RuntimeError) as ctx:
            _validate_citation_page_path(self.root, "wiki/sources/x.md")

        self.assertIn("wiki/judgments or wiki/decisions", str(ctx.exception))

    def test_citation_snapshot_rejects_traversal(self) -> None:
        outside = self.root.parent / "outside-citation.md"
        outside.write_text("outside\n", encoding="utf-8")
        try:
            with self.assertRaises(RuntimeError) as ctx:
                _validate_citation_page_path(self.root, "../outside-citation.md")
        finally:
            outside.unlink(missing_ok=True)

        self.assertIn("escapes vault root", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
