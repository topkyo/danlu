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


class ProductShellSmokeScriptContract(unittest.TestCase):
    """真实 vault smoke 不能把 run-ask backend 失败伪装成 deterministic success。"""

    def test_run_ask_backend_resolution_failure_is_degraded(self) -> None:
        text = (ROOT / "scripts/product_shell_smoke.sh").read_text(encoding="utf-8")
        self.assertIn("llm_backend_unavailable", text)
        self.assertIn("LLM backend resolution failed".lower(), text)
        self.assertIn("smoke failed without deterministic fallback", text)
        self.assertNotIn('run_json "ask-fallback" ask "$RUN_ASK_QUERY" --format report', text)

    def test_drop_note_smoke_reports_reconcile_path(self) -> None:
        text = (ROOT / "scripts/product_shell_smoke.sh").read_text(encoding="utf-8")
        self.assertIn('payload.get("note_path")', text)
        self.assertIn('payload.get("stored_path")', text)


class ProductShellFirstScreenContract(unittest.TestCase):
    """M7.2/C5: 首屏 surface convergence — renderFurnaceCenter 默认只挂 Universal Input + Today。

    防止首屏退化为多入口 dashboard（重新挂 AskBox / DropZone 等独立面板）。
    AskBox / DropZone 仍可作为 modal/legacy helpers 存在，但不挂在首屏主 view 上。
    """

    def _read_render_furnace_center_body(self) -> str:
        text = MAIN_JS.read_text(encoding="utf-8")
        marker = "function renderFurnaceCenter"
        start = text.find(marker)
        self.assertGreater(start, -1, "renderFurnaceCenter not found in main.js")
        # 限定到该函数 body：从 marker 起取 1000 字符够了（实际函数 ~25 行）。
        end = text.find("\n// --- src/", start)
        self.assertGreater(end, start, "renderFurnaceCenter body terminator not found")
        return text[start:end]

    def test_first_screen_mounts_universal_input(self) -> None:
        body = self._read_render_furnace_center_body()
        self.assertIn("renderUniversalInput(plugin, contentEl)", body)

    def test_first_screen_mounts_today_feed(self) -> None:
        body = self._read_render_furnace_center_body()
        self.assertIn("renderTodayFeed(plugin, contentEl)", body)

    def test_first_screen_does_not_mount_start_guide(self) -> None:
        body = self._read_render_furnace_center_body()
        self.assertNotIn("renderStartGuide", body)

    def test_first_screen_gates_advanced_drawer(self) -> None:
        body = self._read_render_furnace_center_body()
        self.assertIn("showAdvancedCommands", body)
        self.assertIn("renderAdvancedDrawer(plugin, contentEl)", body)

    def test_first_screen_does_not_mount_ask_box(self) -> None:
        body = self._read_render_furnace_center_body()
        self.assertNotIn("renderAskBox(", body)

    def test_first_screen_does_not_mount_drop_zone(self) -> None:
        body = self._read_render_furnace_center_body()
        self.assertNotIn("renderDropZone(", body)


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

class UniversalInputPillContract(unittest.TestCase):
    """M6.7.4: Universal Input Attachment Pill contracts."""

    def test_pill_dom_class(self):
        css = STYLES_CSS.read_text(encoding="utf-8")
        self.assertIn(".furnace-input-attachment", css)
        self.assertIn(".furnace-input-attachment-remove", css)
        js = MAIN_JS.read_text(encoding="utf-8")
        self.assertIn("furnace-input-attachment", js)

    def test_remove_behavior(self):
        js = MAIN_JS.read_text(encoding="utf-8")
        self.assertIn("attachedFiles.splice(index, 1)", js)

    def test_multiple_attachments(self):
        js = MAIN_JS.read_text(encoding="utf-8")
        self.assertIn("attachedFiles.push(", js)

    def test_empty_state_hidden(self):
        js = MAIN_JS.read_text(encoding="utf-8")
        self.assertIn("attachmentsContainer.style.display = \"none\"", js)

    def test_modal_preserved_for_other_call_sites(self):
        js = MAIN_JS.read_text(encoding="utf-8")
        self.assertIn("new DropFileModal", js)

class TodayFeedTypographyContract(unittest.TestCase):
    """M6.7.5: Typography token + Today Feed visual weight."""

    def test_typography_tokens_exist(self):
        """(a) styles.css含 --furnace-type- 至少 4 个 token"""
        css = STYLES_CSS.read_text(encoding="utf-8")
        tokens = re.findall(r"--furnace-type-[\w-]+", css)
        self.assertGreaterEqual(len(set(tokens)), 4, "Should have at least 4 --furnace-type- tokens")

    def test_today_feed_uses_tokens(self):
        """(b) Today Feed render 中至少 3 处使用 var(--furnace-type-*)"""
        css = STYLES_CSS.read_text(encoding="utf-8")
        # Extract the today feed section roughly
        today_feed_css = re.search(r"/\*\s*Today Feed.*?(?=\/\*|$)", css, re.DOTALL)
        self.assertIsNotNone(today_feed_css, "Today feed section missing in CSS")
        usages = re.findall(r"var\(--furnace-(?:type|weight)-[\w-]+\)", today_feed_css.group(0))
        self.assertGreaterEqual(len(usages), 3, "Today feed should use tokens at least 3 times")

    def test_no_new_raw_colors(self):
        """(c) 不引入新 raw color (today feed 范围内)"""
        css = STYLES_CSS.read_text(encoding="utf-8")
        today_feed_css = re.search(r"/\*\s*Today Feed.*?(?=\/\*|$)", css, re.DOTALL).group(0)
        # Should only have the 2 old hardcoded colors or vars, no new hex/rgb besides what was there
        hex_colors = re.findall(r"#[0-9a-fA-F]{3,6}", today_feed_css)
        self.assertLessEqual(len(hex_colors), 2, "Should not introduce new raw colors")

    def test_today_feed_classes_exist(self):
        """(d) Today Feed 各层 class 仍存在"""
        js = MAIN_JS.read_text(encoding="utf-8")
        css = STYLES_CSS.read_text(encoding="utf-8")
        for cls in ["furnace-today-feed-title", "furnace-today-feed-summary", "furnace-today-feed-target"]:
            self.assertIn(cls, js, f"Class {cls} missing from JS")
            self.assertIn(f".{cls}", css, f"Class {cls} missing from CSS")

    def test_no_selector_conflict_with_attachment_pill(self):
        """(e) 与 attachment pill 无 selector 冲突"""
        css = STYLES_CSS.read_text(encoding="utf-8")
        # Just ensure both sections exist independently and one didn't overwrite the other
        self.assertIn(".furnace-today-feed-title", css)
        self.assertIn(".furnace-input-attachment", css)
        self.assertNotIn(".furnace-input-attachment .furnace-today-feed", css)
