from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / ".obsidian/plugins/furnace-product-shell"


class ProductShellUniversalInputContractTests(unittest.TestCase):
    def test_universal_input_present_in_built_main(self) -> None:
        text = (PLUGIN_ROOT / "main.js").read_text(encoding="utf-8")

        for marker in ["renderUniversalInput", "runUniversalInputCommand", "classifyUniversalInput"]:
            self.assertIn(marker, text)

        for keyword in ["URL", "PDF", "image", "repo", "note", "question"]:
            self.assertIn(keyword, text, f"placeholder missing keyword: {keyword}")

        self.assertIn("renderAskBox", text)
        self.assertIn("renderDropZone", text)

    def test_universal_input_router_mirror_aligned(self) -> None:
        text = (PLUGIN_ROOT / "src/input_router.js").read_text(encoding="utf-8")

        for route_value in ["url", "pdf", "image", "repo", "note", "ask"]:
            self.assertTrue(f'"{route_value}"' in text or f"'{route_value}'" in text)

        self.assertTrue("input_router.py" in text or "MIRROR" in text or "mirror" in text)

    def test_universal_input_styles_present(self) -> None:
        text = (PLUGIN_ROOT / "styles.css").read_text(encoding="utf-8")

        self.assertIn("furnace-universal-input", text)
