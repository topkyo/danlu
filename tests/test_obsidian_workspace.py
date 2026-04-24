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
        left_titles = [child["state"]["title"] for child in left_children]
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
        self.assertIn("[[docs/Alchemy Furnace|", home)
        self.assertIn("[[docs/Furnace Ultimate Architecture|", home)
        self.assertIn("[[docs/Furnace Material Scaling|", home)
        self.assertIn("[[wiki/indexes/furnace-center|", home)
        self.assertIn("[[wiki/indexes/protocols|", home)
        wiki_hub = (self.root / "wiki" / "indexes" / "Wiki Hub.md").read_text(encoding="utf-8")
        self.assertIn("[[docs/Furnace Protocols|", wiki_hub)
        self.assertIn("[[docs/Furnace Material State Model|", wiki_hub)
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
            "docs/Alchemy Furnace.md",
            "docs/Furnace Ultimate Architecture.md",
            "docs/Furnace Material Scaling.md",
            "docs/Furnace Material State Model.md",
            "docs/Furnace Protocols.md",
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

    def test_ultimate_architecture_keeps_core_layers_visible(self) -> None:
        text = (self.root / "docs" / "Furnace Ultimate Architecture.md").read_text(encoding="utf-8")
        self.assertIn("Schema / Protocol Layer", text)
        self.assertIn("Outputs Layer", text)
        self.assertIn("execution-center", text)

    def test_material_scaling_docs_keep_runtime_state_guards(self) -> None:
        state_model = (self.root / "docs" / "Furnace Material State Model.md").read_text(encoding="utf-8")
        scaling = (self.root / "docs" / "Furnace Material Scaling.md").read_text(encoding="utf-8")
        self.assertIn("manifest `entries[*].id`", state_model)
        self.assertIn("runtime-history.jsonl", state_model)
        self.assertIn("active_corpus_ids", state_model)
        self.assertIn("空/缺省", state_model)
        self.assertIn("统一落在 machine-readable 的 runtime history 文件里", scaling)


if __name__ == "__main__":
    unittest.main()
