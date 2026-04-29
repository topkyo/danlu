from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
PLUGIN = ROOT / ".obsidian/plugins/furnace-product-shell"


class ProductShellTodayFeedContractTests(unittest.TestCase):
    def test_today_feed_present_in_built_main(self) -> None:
        text = (PLUGIN / "main.js").read_text(encoding="utf-8")
        self.assertIn("renderTodayFeed", text)
        self.assertIn("buildTodayFeed", text)
        for kind in ["decision", "proposal", "report", "elixir", "action"]:
            self.assertIn(kind, text, f"feed kind missing: {kind}")

    def test_today_feed_old_helpers_preserved(self) -> None:
        """旧 helper 保留作为 regression guard。"""
        text = (PLUGIN / "main.js").read_text(encoding="utf-8")
        self.assertIn("renderNeedsDecisionSection", text)
        self.assertIn("renderReportsPanel", text)
        self.assertIn("renderReportsGroup", text)

    def test_today_feed_js_mirror_aligned(self) -> None:
        """JS today_feed mirror 与 Python 排序契约对齐。"""
        text = (PLUGIN / "src/today_feed.js").read_text(encoding="utf-8")
        for kind in ["decision", "proposal", "report", "elixir", "action"]:
            self.assertIn(kind, text)
        self.assertTrue("today_feed.py" in text or "MIRROR" in text or "mirror" in text)

    def test_today_feed_styles_present(self) -> None:
        css = (PLUGIN / "styles.css").read_text(encoding="utf-8")
        self.assertIn("furnace-today-feed", css)
        self.assertIn("furnace-today-feed-actions", css)

    def test_today_feed_items_are_actionable(self) -> None:
        text = (PLUGIN / "src/render_today.js").read_text(encoding="utf-8")
        self.assertIn("renderTodayFeedItem", text)
        self.assertIn("todayFeedActions", text)
        self.assertIn("Open Review", text)
        self.assertIn("Copy command", text)
        self.assertIn("Copy target", text)

    def test_advanced_drawer_summary_exposes_counts(self) -> None:
        text = (PLUGIN / "src/render_advanced.js").read_text(encoding="utf-8")
        self.assertIn("advancedDrawerCounts", text)
        self.assertIn("Review {review_count} · execution {execution_count} · recent runs {run_count}", text)

    def test_today_feed_no_mechanism_words_in_main(self) -> None:
        """首屏 i18n 文案不通过 t() 暴露具体 artifact 机制词。"""
        text = (PLUGIN / "main.js").read_text(encoding="utf-8")
        suspicious_in_t_call = re.findall(r't\("[^"]*(?:review_backlog_counts|audit\.jsonl|planner-log)[^"]*"\)', text)
        self.assertFalse(suspicious_in_t_call, f"mechanism words in t() calls: {suspicious_in_t_call}")
