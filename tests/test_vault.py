from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from aiwiki.app_vault import bootstrap_new_vault


class VaultBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_root = Path(__file__).resolve().parents[1]
        self.tempdir = tempfile.TemporaryDirectory()
        self.target = Path(self.tempdir.name) / "demo-vault"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_bootstrap_new_vault_creates_launcher_plugin_and_shell_summary(self) -> None:
        result = bootstrap_new_vault(self.runtime_root, self.target)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["launcher_path"], "scripts/aiwiki-launcher.sh")
        self.assertTrue((self.target / "HOME.md").exists())
        self.assertTrue((self.target / "README.md").exists())
        self.assertTrue((self.target / ".obsidian" / "app.json").exists())
        self.assertTrue((self.target / ".obsidian" / "appearance.json").exists())
        self.assertTrue((self.target / ".obsidian" / "workspace.json").exists())
        self.assertTrue((self.target / ".obsidian" / "community-plugins.json").exists())
        self.assertTrue((self.target / ".obsidian" / "snippets" / "danlu-zh-folders.css").exists())
        self.assertTrue((self.target / ".obsidian" / "plugins" / "furnace-product-shell" / "main.js").exists())
        self.assertTrue((self.target / "output" / "control" / "shell-summary.json").exists())

        launcher = self.target / "scripts" / "aiwiki-launcher.sh"
        self.assertTrue(os.access(launcher, os.X_OK))

        home = (self.target / "HOME.md").read_text(encoding="utf-8")
        readme = (self.target / "README.md").read_text(encoding="utf-8")
        appearance = json.loads((self.target / ".obsidian" / "appearance.json").read_text(encoding="utf-8"))
        snippet = (self.target / ".obsidian" / "snippets" / "danlu-zh-folders.css").read_text(encoding="utf-8")
        plugin_source = (self.target / ".obsidian" / "plugins" / "furnace-product-shell" / "main.js").read_text(encoding="utf-8")
        plugin_data = json.loads((self.target / ".obsidian" / "plugins" / "furnace-product-shell" / "data.json").read_text(encoding="utf-8"))
        workspace = json.loads((self.target / ".obsidian" / "workspace.json").read_text(encoding="utf-8"))
        self.assertIn("[[wiki/indexes/furnace-center|", home)
        self.assertIn("./scripts/aiwiki-launcher.sh compile", home)
        self.assertIn("默认界面语言是中文", home)
        self.assertIn("gpt-5.4", home)
        self.assertIn("单写约束", home)
        self.assertIn("single writer, many readers", readme)
        self.assertIn("默认界面语言为中文", readme)
        self.assertIn("gpt-5.4", readme)
        self.assertIn("drop-note --title", readme)
        self.assertIn("runtime contract", readme)
        self.assertEqual(appearance["enabledCssSnippets"], ["danlu-zh-folders"])
        self.assertIn('.tree-item-self[data-path="raw"] > .tree-item-inner', snippet)
        self.assertIn('.nav-folder-title[data-path="output/control"] > .nav-folder-title-content', snippet)
        self.assertIn('content: "研发协议 research";', snippet)
        self.assertIn("Capture Note", plugin_source)
        self.assertIn("drop-note", plugin_source)
        self.assertEqual(plugin_data["settings"]["locale"], "zh")
        self.assertEqual(
            [child["state"]["title"] for child in workspace["left"]["children"][0]["children"]],
            ["文件列表", "原料 raw", "wiki 知识", "输出 output", "规则 schema"],
        )
        self.assertIn(
            "furnace-product-shell-review-center",
            [child["state"]["type"] for child in workspace["right"]["children"][0]["children"]],
        )

    def test_bootstrap_new_vault_launcher_runs_shell_status(self) -> None:
        bootstrap_new_vault(self.runtime_root, self.target)

        result = subprocess.run(
            [str(self.target / "scripts" / "aiwiki-launcher.sh"), "shell-status"],
            cwd=self.target,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["active_protocol"], "general")
        self.assertTrue((self.target / "output" / "control" / "product-shell.html").exists())

    def test_bootstrap_new_vault_rejects_non_empty_target_without_force(self) -> None:
        self.target.mkdir(parents=True, exist_ok=True)
        (self.target / "keep.txt").write_text("existing\n", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            bootstrap_new_vault(self.runtime_root, self.target)


if __name__ == "__main__":
    unittest.main()
