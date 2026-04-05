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
        self.assertIn("[[wiki/indexes/Raw Inbox]]", home)
        self.assertIn("[[wiki/indexes/Wiki Hub]]", home)
        self.assertIn("[[wiki/indexes/Outputs]]", home)
        self.assertIn("[[wiki/indexes/Search Presets]]", home)

    def test_index_notes_exist(self) -> None:
        for relative in (
            "wiki/indexes/Raw Inbox.md",
            "wiki/indexes/Wiki Hub.md",
            "wiki/indexes/Outputs.md",
            "wiki/indexes/Search Presets.md",
        ):
            self.assertTrue((self.root / relative).exists(), relative)


if __name__ == "__main__":
    unittest.main()
