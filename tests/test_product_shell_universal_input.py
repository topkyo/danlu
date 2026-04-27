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

        self.assertIn("renderAskBox", text)
        self.assertIn("renderDropZone", text)

    def test_universal_input_uses_backend_drop_router(self) -> None:
        text = (PLUGIN_ROOT / "main.js").read_text(encoding="utf-8")

        self.assertIn('const args = ["drop", normalizedPayload]', text)
        self.assertIn('await plugin.runUniversalInputCommand({ payload: file.path, title: value });', text)
        self.assertIn('await plugin.runUniversalInputCommand({ payload: value });', text)
        self.assertNotIn("classifyUniversalInput", text)

    def test_universal_input_styles_present(self) -> None:
        text = (PLUGIN_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn("furnace-universal-input", text)
