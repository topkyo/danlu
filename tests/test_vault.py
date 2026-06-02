from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from aiwiki.app_vault import bootstrap_new_vault, sync_product_shell_plugin


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
        self.assertTrue((self.target / ".obsidian" / "graph.json").exists())
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
        app_config = json.loads((self.target / ".obsidian" / "app.json").read_text(encoding="utf-8"))
        graph_config = json.loads((self.target / ".obsidian" / "graph.json").read_text(encoding="utf-8"))
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
        self.assertIn("drop markdown --title", readme)
        self.assertIn("runtime contract", readme)
        self.assertIn('$HOME/.local/npm/bin', launcher_text)
        self.assertIn("export PATH", launcher_text)
        self.assertIn('PLUGIN_DATA="$VAULT_ROOT/.obsidian/plugins/furnace-product-shell/data.json"', launcher_text)
        self.assertIn('AIWIKI_DEEPSEEK_API_KEY', launcher_text)
        self.assertIn('AIWIKI_OPENCODE_API_KEY', launcher_text)
        self.assertIn('unset "$env_name"', launcher_text)
        self.assertNotIn("os.environ.get(env_name)", launcher_text)
        self.assertNotIn('AIWIKI_NVIDIA_NIM_API_KEY', launcher_text)
        self.assertEqual(appearance["enabledCssSnippets"], ["danlu-zh-folders"])
        self.assertIn("output/lint/", app_config["userIgnoreFilters"])
        self.assertIn("output/packs/", app_config["userIgnoreFilters"])
        self.assertIn("wiki/indexes/", app_config["userIgnoreFilters"])
        self.assertIn('path:"output/reports"', graph_config["search"])
        self.assertIn('path:"wiki/sources"', graph_config["search"])
        self.assertIn('-path:"wiki/concepts"', graph_config["search"])
        self.assertNotIn('OR path:"wiki/concepts"', graph_config["search"])
        self.assertIn('path:"raw/assets"', graph_config["search"])
        self.assertFalse(graph_config["hideUnresolved"])
        self.assertTrue(graph_config["showOrphans"])
        self.assertIn('path:"output/reports"', [group["query"] for group in graph_config["colorGroups"]])
        self.assertIn('path:"raw/inbox"', [group["query"] for group in graph_config["colorGroups"]])
        self.assertNotIn('/* hide raw from the daily file tree */', snippet)
        self.assertIn('content: "原料";', snippet)
        self.assertIn('content: "收件箱";', snippet)
        self.assertIn('content: "附件";', snippet)
        self.assertNotIn('content: "原料 raw";', snippet)
        self.assertNotIn("raw/assets/", app_config["userIgnoreFilters"])
        self.assertNotIn('/* hide raw/assets from the daily file tree */', snippet)
        self.assertIn('.nav-folder[data-path="raw/normalized"],', snippet)
        self.assertIn('.nav-folder[data-path="wiki"],', snippet)
        self.assertIn('.nav-folder[data-path="output/graph"],', snippet)
        self.assertIn('display: none !important;', snippet)
        self.assertIn('content: "报告";', snippet)
        self.assertNotIn('content: "全部报告";', snippet)
        self.assertIn('flatten output/reports', snippet)
        self.assertIn('.nav-folder[data-path="output/reports"] > .nav-folder-title', snippet)
        self.assertIn('.tree-item[data-path="output/reports"] > .tree-item-self', snippet)
        self.assertNotIn('/* hide output/reports from the daily file tree */', snippet)
        self.assertIn('.nav-folder-title[data-path="output/control"] > .nav-folder-title-content', snippet)
        self.assertIn('content: "策略 policies";', snippet)
        self.assertIn('content: "研发协议 research";', snippet)
        self.assertIn("投文字材料", plugin_source)
        self.assertNotIn("drop-note / drop-url", plugin_source)
        self.assertEqual(plugin_data["settings"]["locale"], "zh")
        self.assertEqual(plugin_data["settings"]["defaultAskFormat"], "report")
        self.assertNotIn("defaultAskMode", plugin_data["settings"])
        self.assertNotIn("showHtmlShortcuts", plugin_data["settings"])
        self.assertNotIn("devops", plugin_data["settings"].get("advancedSectionsExpanded", {}))
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

    def test_bootstrap_new_vault_launcher_inherits_deepseek_plugin_llm_settings(self) -> None:
        bootstrap_new_vault(self.runtime_root, self.target)
        plugin_data_path = self.target / ".obsidian" / "plugins" / "furnace-product-shell" / "data.json"
        plugin_data = json.loads(plugin_data_path.read_text(encoding="utf-8"))
        plugin_data["settings"]["llmBackend"] = "deepseek-api"
        plugin_data["settings"]["llmModel"] = "deepseek-chat"
        plugin_data["settings"]["llmDeepseekApiKey"] = "deepseek_fake_key"
        plugin_data_path.write_text(json.dumps(plugin_data, ensure_ascii=False, indent=2), encoding="utf-8")

        env = os.environ.copy()
        for key in (
            "AIWIKI_LLM_BACKEND",
            "AIWIKI_LLM_MODEL",
            "AIWIKI_DEEPSEEK_API_KEY",
            "AIWIKI_DEEPSEEK_BASE_URL",
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
        self.assertEqual(payload["backend_requested"], "deepseek-api")
        self.assertEqual(payload["backend"], "deepseek-api")
        self.assertEqual(payload["effective_model"], "deepseek-chat")

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

    def test_bootstrap_new_vault_launcher_prefers_plugin_settings_over_stale_env(self) -> None:
        bootstrap_new_vault(self.runtime_root, self.target)
        plugin_data_path = self.target / ".obsidian" / "plugins" / "furnace-product-shell" / "data.json"
        plugin_data = json.loads(plugin_data_path.read_text(encoding="utf-8"))
        plugin_data["settings"]["llmBackend"] = "opencode-api"
        plugin_data["settings"]["llmModel"] = "deepseek-v4-pro"
        plugin_data["settings"]["llmOpencodeApiKey"] = "opencode_ui_key"
        plugin_data_path.write_text(json.dumps(plugin_data, ensure_ascii=False, indent=2), encoding="utf-8")

        env = os.environ.copy()
        env.update(
            {
                "AIWIKI_LLM_BACKEND": "deepseek-api",
                "AIWIKI_LLM_MODEL": "deepseek-chat",
                "AIWIKI_DEEPSEEK_API_KEY": "stale_deepseek_key",
                "AIWIKI_OPENCODE_API_KEY": "stale_opencode_key",
                "AIWIKI_LLM_API_KEY": "stale_generic_key",
            }
        )

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

    def test_sync_product_shell_plugin_updates_release_files_and_preserves_data(self) -> None:
        bootstrap_new_vault(self.runtime_root, self.target)
        plugin_root = self.target / ".obsidian" / "plugins" / "furnace-product-shell"
        data_path = plugin_root / "data.json"
        preserved_data = {
            "settings": {
                "llmBackend": "deepseek-api",
                "llmDeepseekApiKey": "local-secret-placeholder",
                "locale": "zh",
            }
        }
        data_path.write_text(json.dumps(preserved_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (plugin_root / "main.js").write_text("// old bundle\n", encoding="utf-8")

        result = sync_product_shell_plugin(self.runtime_root, self.target)

        self.assertEqual(result["status"], "ok")
        self.assertIn(".obsidian/plugins/furnace-product-shell/main.js", result["changed_files"])
        self.assertIn(".obsidian/plugins/furnace-product-shell/data.json", result["preserved_files"])
        self.assertEqual(json.loads(data_path.read_text(encoding="utf-8")), preserved_data)
        self.assertEqual(
            (plugin_root / "main.js").read_text(encoding="utf-8"),
            (self.runtime_root / ".obsidian" / "plugins" / "furnace-product-shell" / "main.js").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
