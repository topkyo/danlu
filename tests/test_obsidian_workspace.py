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
        self.assertEqual(workspace["active"], "main-furnace-center")
        self.assertEqual(main_children[0]["state"]["type"], "furnace-product-shell-furnace-center")
        self.assertEqual(main_children[1]["state"]["state"]["file"], "HOME.md")
        self.assertTrue(workspace["left"].get("collapsed"))
        self.assertTrue(workspace["right"].get("collapsed"))
        left_children = workspace["left"]["children"][0]["children"]
        left_titles = [child["state"].get("title") for child in left_children]
        self.assertEqual(left_titles, ["文件列表", "书签"])
        right_children = workspace["right"]["children"][0]["children"]
        view_types = [child["state"]["type"] for child in right_children]
        self.assertEqual(view_types, ["outline", "backlink"])

    def test_home_dashboard_links_key_index_notes(self) -> None:
        home = (self.root / "HOME.md").read_text(encoding="utf-8")
        self.assertIn("Product Shell", home)
        self.assertIn("输入端", home)
        self.assertIn("输出端", home)
        self.assertIn("更多工具", home)
        self.assertIn("[[wiki/indexes/README|", home)
        self.assertIn("compile", home)
        self.assertNotIn("[[wiki/indexes/furnace-center|", home)
        self.assertNotIn("[[wiki/indexes/Outputs|", home)
        self.assertNotIn("## 今日信号", home)

    def test_index_notes_exist(self) -> None:
        # Generated wiki/indexes pages are compile outputs and are not tracked in git.
        # Only the handwritten strategy page remains checked in.
        self.assertTrue((self.root / "wiki" / "indexes" / "README.md").exists())
        for relative in (
            "wiki/indexes/furnace-center.md",
            "wiki/indexes/Outputs.md",
            "wiki/indexes/Wiki Hub.md",
        ):
            # May exist after a local compile, but must not be required as committed SoT.
            path = self.root / relative
            if path.exists():
                self.assertTrue(path.is_file())

    def test_folder_label_snippet_hides_docs_from_file_tree(self) -> None:
        from aiwiki.app_vault import _render_folder_label_snippet

        snippet = _render_folder_label_snippet()
        self.assertIn("hide docs from the daily file tree", snippet)
        self.assertIn('.nav-folder[data-path="docs"]', snippet)


if __name__ == "__main__":
    unittest.main()
