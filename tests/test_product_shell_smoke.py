"""M6.5 B1: Product Shell UI smoke tests — 现状冻结。

String-level contract tests, 防止首屏退化为 dashboard。
不引入浏览器自动化或大依赖。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
PLUGIN = ROOT / ".obsidian/plugins/furnace-product-shell"
MAIN_JS = PLUGIN / "main.js"
STYLES_CSS = PLUGIN / "styles.css"


class ProductShellEmptyStateContract(unittest.TestCase):
    """首屏空状态有 fallback 字符串。"""

    def test_today_feed_empty_fallback(self) -> None:
        text = MAIN_JS.read_text(encoding="utf-8")
        self.assertTrue(
            "(nothing for today)" in text or "no reports today" in text,
            "today feed empty fallback missing",
        )

    def test_reports_empty_fallback(self) -> None:
        text = MAIN_JS.read_text(encoding="utf-8")
        self.assertIn("(no reports today)", text)

    def test_metrics_unavailable_fallback(self) -> None:
        text = MAIN_JS.read_text(encoding="utf-8")
        self.assertIn("metrics unavailable", text.lower())

    def test_universal_input_placeholder_keywords(self) -> None:
        text = MAIN_JS.read_text(encoding="utf-8")
        for keyword in ["URL", "PDF", "image", "repo", "note", "question"]:
            self.assertIn(keyword, text, f"universal input placeholder keyword missing: {keyword}")

    def test_runtime_unavailable_fallback(self) -> None:
        text = MAIN_JS.read_text(encoding="utf-8")
        self.assertIn("Vault runtime unavailable", text)


class ProductShellButtonContract(unittest.TestCase):
    """主要按钮 / 控件存在。"""

    def test_refresh_control_present(self) -> None:
        text = MAIN_JS.read_text(encoding="utf-8")
        self.assertTrue(
            "Refresh Furnace Shell" in text or "Refresh" in text or "refresh" in text,
            "Refresh control missing in main.js",
        )

    def test_universal_input_submit_button_present(self) -> None:
        text = MAIN_JS.read_text(encoding="utf-8")
        self.assertIn("furnace-universal-input-button", text)
        self.assertIn("Submit", text)

    def test_universal_input_submit_handler_present(self) -> None:
        text = MAIN_JS.read_text(encoding="utf-8")
        self.assertIn("runUniversalInputCommand", text)

    def test_advanced_drawer_present(self) -> None:
        text = MAIN_JS.read_text(encoding="utf-8")
        self.assertIn("renderAdvancedDrawer", text)


class ProductShellLongTextContract(unittest.TestCase):
    """长文本 wrap CSS 规则存在。"""

    def test_word_break_rule_present(self) -> None:
        css = STYLES_CSS.read_text(encoding="utf-8")
        self.assertRegex(css, re.compile(r"word-break\s*:\s*break-(?:word|all)"))

    def test_text_overflow_ellipsis_rule_present(self) -> None:
        css = STYLES_CSS.read_text(encoding="utf-8")
        self.assertRegex(css, re.compile(r"text-overflow\s*:\s*ellipsis"))

    def test_overflow_or_max_width_rule_present(self) -> None:
        css = STYLES_CSS.read_text(encoding="utf-8")
        self.assertTrue(
            "overflow" in css or "max-width" in css,
            "no overflow/max-width rule in styles.css",
        )


class ProductShellResponsiveContract(unittest.TestCase):
    """移动宽度响应式规则。"""

    def test_media_query_present(self) -> None:
        css = STYLES_CSS.read_text(encoding="utf-8")
        self.assertIn("@media", css, "no @media rule in styles.css (responsive missing)")

    def test_at_least_one_mobile_breakpoint(self) -> None:
        """至少 1 个 max-width breakpoint 用于 mobile/tablet。"""
        css = STYLES_CSS.read_text(encoding="utf-8")
        # B1 探查：已有 max-width: 900px / 640px
        breakpoints = re.findall(r"@media\s*\([^)]*max-width:\s*(\d+)px\s*\)", css)
        self.assertTrue(
            any(int(bp) <= 900 for bp in breakpoints),
            f"no mobile/tablet breakpoint found; breakpoints={breakpoints}",
        )


class ProductShellCollapseContract(unittest.TestCase):
    """Advanced 折叠 / 抽屉控件。"""

    def test_details_summary_used(self) -> None:
        text = MAIN_JS.read_text(encoding="utf-8")
        # B1 探查：已用 details/summary 标签
        self.assertIn("details", text)
        self.assertIn("summary", text)

    def test_advanced_drawer_collapse_pattern(self) -> None:
        """Advanced drawer 用 details 或 collapsed class 实现折叠。"""
        text = MAIN_JS.read_text(encoding="utf-8")
        # 任一 pattern 满足
        has_details_in_advanced = bool(
            re.search(r"renderAdvancedDrawer[\s\S]{0,3000}details", text)
        )
        has_collapsed_class = "collapsed" in text or "is-collapsed" in text
        self.assertTrue(
            has_details_in_advanced or has_collapsed_class,
            "Advanced drawer has no collapse mechanism (no details near renderAdvancedDrawer; no collapsed class)",
        )
