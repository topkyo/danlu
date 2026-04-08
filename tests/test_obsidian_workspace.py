from __future__ import annotations

import json
import unittest
from pathlib import Path


class ObsidianWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]

    def test_obsidian_json_files_are_valid(self) -> None:
        for relative in (
            ".obsidian/app.json",
            ".obsidian/core-plugins.json",
            ".obsidian/workspace.json",
        ):
            path = self.root / relative
            self.assertTrue(path.exists(), relative)
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertIsNotNone(payload)

    def test_home_dashboard_links_key_index_notes(self) -> None:
        home = (self.root / "HOME.md").read_text(encoding="utf-8")
        self.assertIn("[[wiki/indexes/Raw Inbox|", home)
        self.assertIn("[[wiki/indexes/Wiki Hub|", home)
        self.assertIn("[[wiki/indexes/Alchemy Furnace|", home)
        self.assertIn("[[wiki/indexes/protocols|", home)
        self.assertIn("[[wiki/indexes/Furnace Protocols|", (self.root / "wiki" / "indexes" / "Wiki Hub.md").read_text(encoding="utf-8"))
        self.assertIn("[[wiki/indexes/review-center|", home)
        self.assertIn("[[wiki/indexes/graph-view|", home)
        self.assertIn("[[wiki/indexes/machine-memory|", home)
        self.assertIn("[[wiki/indexes/graph-health|", home)
        self.assertIn("[[wiki/indexes/drift-report|", home)
        self.assertIn("[[wiki/indexes/repair-backlog|", home)
        self.assertIn("[[wiki/indexes/review-queue|", home)
        self.assertIn("[[schema/index|", home)
        self.assertIn("[[schema/protocols/index|", home)
        self.assertIn("[[wiki/indexes/Outputs|", home)
        self.assertIn("[[wiki/indexes/Search Presets|", home)

    def test_index_notes_exist(self) -> None:
        for relative in (
            "wiki/indexes/Raw Inbox.md",
            "wiki/indexes/Wiki Hub.md",
            "wiki/indexes/Alchemy Furnace.md",
            "wiki/indexes/Furnace Protocols.md",
            "wiki/indexes/protocols.md",
            "wiki/indexes/review-center.md",
            "wiki/indexes/graph-view.md",
            "wiki/indexes/graph-health.md",
            "wiki/indexes/repair-backlog.md",
            "wiki/indexes/review-queue.md",
            "wiki/indexes/Outputs.md",
            "wiki/indexes/Search Presets.md",
        ):
            self.assertTrue((self.root / relative).exists(), relative)


if __name__ == "__main__":
    unittest.main()
