from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / ".obsidian/plugins/furnace-product-shell"


class ProductShellUniversalInputContractTests(unittest.TestCase):
    def test_universal_input_present_in_built_main(self) -> None:
        text = (PLUGIN_ROOT / "main.js").read_text(encoding="utf-8")

        for marker in ["renderUniversalInput", "runUniversalInputCommand", "Universal Input"]:
            self.assertIn(marker, text)

        for keyword in ["URL", "PDF", "image", "repo", "note", "question"]:
            self.assertIn(keyword, text, f"placeholder missing keyword: {keyword}")

        self.assertIn("renderDropZone", text)

    def test_universal_input_uses_backend_drop_router(self) -> None:
        text = (PLUGIN_ROOT / "main.js").read_text(encoding="utf-8")

        self.assertIn('const args = ["drop", normalizedPayload]', text)
        self.assertIn("async function resolvePluginFileSource", text)
        self.assertIn(".aiwiki", text)
        self.assertIn("product-shell-drop", text)
        self.assertIn("const source = await resolvePluginFileSource(plugin, file);", text)
        self.assertNotIn('await plugin.runUniversalInputCommand({ payload: file.path || file.name || "", title: value });', text)
        self.assertIn('await plugin.runAskCommand({', text)
        self.assertIn('kind: "auto-ask"', text)
        self.assertNotIn("classifyUniversalInput", text)

    def test_drop_plus_question_auto_runs_single_run_ask_with_material_paths(self) -> None:
        text = (PLUGIN_ROOT / "main.js").read_text(encoding="utf-8")

        self.assertIn("async runDroppedFilesWithAutoAsk", text)
        self.assertIn("async runDroppedPayloadsWithAutoAsk", text)
        self.assertIn("function splitTextMaterialQuestion", text)
        self.assertIn("collectMaterialPathsFromPayload(payload)", text)
        self.assertIn("buildAutoAskQuestion(normalizedQuestion, normalizedMaterialPaths)", text)
        self.assertIn("inferAutoAskFormat(normalizedQuestion, normalizedMaterialPaths)", text)
        self.assertIn("材料路径供系统路由使用：", text)
        self.assertIn('await this.runAskCommand({', text)
        self.assertIn('mode: "run-ask"', text)
        self.assertIn('format: askFormat', text)
        self.assertIn('const canUseDirect = format === "note" && !directQuestion.includes("材料路径供系统路由使用：")', text)
        self.assertIn('--direct', text)
        self.assertIn('--lean', text)
        self.assertNotIn('args.push("--timeout", "45")', text)
        self.assertIn('--fallback-to-ask', text)
        self.assertIn('longRunning', text)
        self.assertIn('Long report task', text)
        self.assertIn('autoAsk: Boolean(normalizedQuestion)', text)
        self.assertIn('question: normalizedQuestion', text)

    def test_direct_questions_infer_note_instead_of_persisted_report(self) -> None:
        text = (PLUGIN_ROOT / "main.js").read_text(encoding="utf-8")

        self.assertIn("inferAutoAskFormat(normalizedQuestion, [])", text)
        self.assertNotIn('const askFormat = String(plugin.settings && plugin.settings.defaultAskFormat || "note").trim() || "note";', text)
        self.assertIn('formatSelect.value = "note"', text)

    def test_retry_logic_preserves_auto_ask_metadata(self) -> None:
        text = (PLUGIN_ROOT / "main.js").read_text(encoding="utf-8")

        self.assertIn("updatePendingSubmissionRetryArgs(id, retryArgs)", text)
        self.assertIn("materialPaths:", text)
        self.assertIn("askQuestion:", text)
        self.assertIn("runDroppedFilesWithAutoAsk({", text)

    def test_universal_input_styles_present(self) -> None:
        text = (PLUGIN_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn("furnace-universal-input", text)
