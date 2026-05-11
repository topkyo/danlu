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
        launcher_text = launcher.read_text(encoding="utf-8")

        home = (self.target / "HOME.md").read_text(encoding="utf-8")
        readme = (self.target / "README.md").read_text(encoding="utf-8")
        appearance = json.loads((self.target / ".obsidian" / "appearance.json").read_text(encoding="utf-8"))
        snippet = (self.target / ".obsidian" / "snippets" / "danlu-zh-folders.css").read_text(encoding="utf-8")
        plugin_source = (self.target / ".obsidian" / "plugins" / "furnace-product-shell" / "main.js").read_text(encoding="utf-8")
        plugin_data = json.loads((self.target / ".obsidian" / "plugins" / "furnace-product-shell" / "data.json").read_text(encoding="utf-8"))
        workspace = json.loads((self.target / ".obsidian" / "workspace.json").read_text(encoding="utf-8"))
        self.assertIn("[[wiki/indexes/furnace-center|", home)
        self.assertIn("./scripts/aiwiki-launcher.sh compile", home)
        self.assertIn("Product Shell", home)
        self.assertIn("输入端", home)
        self.assertIn("输出端", home)
        self.assertIn("单写约束", home)
        self.assertIn("single writer, many readers", readme)
        self.assertIn("默认界面语言为中文", readme)
        self.assertIn("opencode-api/deepseek-v4-pro", readme)
        self.assertIn("drop note --title", readme)
        self.assertIn("runtime contract", readme)
        self.assertIn('$HOME/.local/npm/bin', launcher_text)
        self.assertIn("export PATH", launcher_text)
        self.assertIn('PLUGIN_DATA="$VAULT_ROOT/.obsidian/plugins/furnace-product-shell/data.json"', launcher_text)
        self.assertIn('AIWIKI_OPENCODE_API_KEY', launcher_text)
        self.assertIn('AIWIKI_NVIDIA_NIM_API_KEY', launcher_text)
        self.assertEqual(appearance["enabledCssSnippets"], ["danlu-zh-folders"])
        self.assertIn('.nav-folder[data-path="raw"],', snippet)
        self.assertIn('.nav-folder[data-path="wiki"],', snippet)
        self.assertIn('.nav-folder[data-path="output/graph"],', snippet)
        self.assertIn('display: none !important;', snippet)
        self.assertIn('content: "报告";', snippet)
        self.assertIn('content: "全部报告";', snippet)
        self.assertIn('.nav-folder-title[data-path="output/control"] > .nav-folder-title-content', snippet)
        self.assertIn('content: "策略 policies";', snippet)
        self.assertIn('content: "研发协议 research";', snippet)
        self.assertIn("Capture Note", plugin_source)
        self.assertNotIn("drop-note / drop-url", plugin_source)
        self.assertEqual(plugin_data["settings"]["locale"], "zh")
        self.assertEqual(workspace["active"], "main-furnace-center")
        self.assertEqual(workspace["main"]["children"][0]["children"][0]["state"]["type"], "furnace-product-shell-furnace-center")
        self.assertTrue(workspace["left"].get("collapsed"))
        self.assertTrue(workspace["right"].get("collapsed"))
        self.assertEqual(
            [child["state"]["title"] for child in workspace["left"]["children"][0]["children"]],
            ["文件列表", "书签"],
        )
        self.assertEqual(
            [child["state"]["type"] for child in workspace["right"]["children"][0]["children"]],
            ["outline", "backlink"],
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

    def test_bootstrap_new_vault_launcher_inherits_plugin_llm_settings(self) -> None:
        bootstrap_new_vault(self.runtime_root, self.target)
        plugin_data_path = self.target / ".obsidian" / "plugins" / "furnace-product-shell" / "data.json"
        plugin_data = json.loads(plugin_data_path.read_text(encoding="utf-8"))
        plugin_data["settings"]["llmBackend"] = "nvidia-nim-api"
        plugin_data["settings"]["llmNvidiaNimApiKey"] = "nvapi_fake_key"
        plugin_data_path.write_text(json.dumps(plugin_data, ensure_ascii=False, indent=2), encoding="utf-8")

        env = os.environ.copy()
        for key in (
            "AIWIKI_LLM_BACKEND",
            "AIWIKI_LLM_MODEL",
            "AIWIKI_NVIDIA_NIM_API_KEY",
            "AIWIKI_NVIDIA_NIM_BASE_URL",
        ):
            env.pop(key, None)

        result = subprocess.run(
            [str(self.target / "scripts" / "aiwiki-launcher.sh"), "llm-check"],
            cwd=self.target,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["configured"])
        self.assertEqual(payload["backend_requested"], "nvidia-nim-api")
        self.assertEqual(payload["backend"], "nvidia-nim-api")
        self.assertEqual(payload["effective_model"], "openai/gpt-oss-120b")

    def test_bootstrap_new_vault_launcher_inherits_opencode_plugin_key(self) -> None:
        bootstrap_new_vault(self.runtime_root, self.target)
        plugin_data_path = self.target / ".obsidian" / "plugins" / "furnace-product-shell" / "data.json"
        plugin_data = json.loads(plugin_data_path.read_text(encoding="utf-8"))
        plugin_data["settings"]["llmBackend"] = "opencode-api"
        plugin_data["settings"]["llmModel"] = "deepseek-v4-pro"
        plugin_data["settings"]["llmOpencodeApiKey"] = "opencode_fake_key"
        plugin_data_path.write_text(json.dumps(plugin_data, ensure_ascii=False, indent=2), encoding="utf-8")

        env = os.environ.copy()
        for key in (
            "AIWIKI_LLM_BACKEND",
            "AIWIKI_LLM_MODEL",
            "AIWIKI_OPENCODE_API_KEY",
            "AIWIKI_LLM_API_KEY",
        ):
            env.pop(key, None)

        result = subprocess.run(
            [str(self.target / "scripts" / "aiwiki-launcher.sh"), "llm-check"],
            cwd=self.target,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["configured"])
        self.assertEqual(payload["backend_requested"], "opencode-api")
        self.assertEqual(payload["backend"], "opencode-api")
        self.assertEqual(payload["effective_model"], "deepseek-v4-pro")

    def test_bootstrap_new_vault_rejects_non_empty_target_without_force(self) -> None:
        self.target.mkdir(parents=True, exist_ok=True)
        (self.target / "keep.txt").write_text("existing\n", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            bootstrap_new_vault(self.runtime_root, self.target)


if __name__ == "__main__":
    unittest.main()
