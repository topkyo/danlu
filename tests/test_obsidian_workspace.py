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

    def test_workspace_defaults_open_home_and_furnace_center(self) -> None:
        workspace = json.loads((self.root / ".obsidian" / "workspace.json").read_text(encoding="utf-8"))
        main_children = workspace["main"]["children"][0]["children"]
        self.assertEqual(main_children[0]["state"]["state"]["file"], "HOME.md")
        left_children = workspace["left"]["children"][0]["children"]
        left_titles = [child["state"].get("title") for child in left_children]
        self.assertEqual(
            left_titles,
            ["文件列表", "原料 raw", "wiki 知识", "输出 output", "规则 schema", "书签"],
        )
        right_children = workspace["right"]["children"][0]["children"]
        view_types = [child["state"]["type"] for child in right_children]
        self.assertIn("furnace-product-shell-furnace-center", view_types)
        self.assertIn("furnace-product-shell-review-center", view_types)
        self.assertIn("furnace-product-shell-execution-center", view_types)
        self.assertIn("furnace-product-shell-recent-runs", view_types)

    def test_home_dashboard_links_key_index_notes(self) -> None:
        home = (self.root / "HOME.md").read_text(encoding="utf-8")
        self.assertIn("[[wiki/indexes/Raw Inbox|", home)
        self.assertIn("[[wiki/indexes/Wiki Hub|", home)
        self.assertIn("[[docs/Furnace Agent Architecture|", home)
        self.assertIn("[[docs/Furnace Evolution Mechanics|", home)
        self.assertIn("[[docs/Furnace Elixir|", home)
        self.assertIn("[[wiki/indexes/furnace-center|", home)
        self.assertIn("[[wiki/indexes/protocols|", home)
        wiki_hub = (self.root / "wiki" / "indexes" / "Wiki Hub.md").read_text(encoding="utf-8")
        self.assertIn("[[docs/Furnace Agent Architecture|", wiki_hub)
        self.assertIn("[[docs/Furnace Evolution Mechanics|", wiki_hub)
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
            "docs/Furnace Agent Architecture.md",
            "docs/Furnace Evolution Mechanics.md",
            "docs/Furnace Elixir.md",
            "wiki/indexes/furnace-center.md",
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

    def test_agent_architecture_keeps_core_invariants_visible(self) -> None:
        text = (self.root / "docs" / "Furnace Agent Architecture.md").read_text(encoding="utf-8")
        self.assertIn("Single writer", text)
        self.assertIn("raw/", text)
        self.assertIn("Agent Loop", text)
        self.assertIn("L3", text)

    def test_evolution_mechanics_keeps_runtime_state_guards(self) -> None:
        evolution = (self.root / "docs" / "Furnace Evolution Mechanics.md").read_text(encoding="utf-8")
        self.assertIn("active-corpora.json", evolution)
        self.assertIn("runtime-history.jsonl", evolution)
        self.assertIn("wiki/elixirs/", evolution)
        self.assertIn("output/_proposals/", evolution)


if __name__ == "__main__":
    unittest.main()
