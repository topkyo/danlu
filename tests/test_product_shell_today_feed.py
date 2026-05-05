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
        for kind in ["decision", "proposal", "report", "elixir", "automation", "action"]:
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
        for kind in ["decision", "proposal", "report", "elixir", "automation", "action"]:
            self.assertIn(kind, text)
        self.assertTrue("today_feed.py" in text or "MIRROR" in text or "mirror" in text)
        self.assertIn("REVIEW_BUCKET_COPY", text)
        self.assertIn("PRIMARY_REVIEW_BUCKETS", text)
        self.assertIn("isMaintenanceCommandAction", text)
        self.assertIn("补充反证候选", text)
        self.assertIn("buildCounterEvidenceEntries", text)
        self.assertIn("buildDriftEntries", text)
        self.assertIn("buildMetricAlertEntries", text)
        self.assertIn("buildAgentLoopEntries", text)
        self.assertIn("预演下一步维护", text)
        self.assertIn("已自动维护", text)
        self.assertIn("alchemy auto --dry-run", text)
        self.assertNotIn("待审议: ${kindText}", text)

    def test_today_feed_agent_loop_present_in_built_main(self) -> None:
        text = (PLUGIN / "main.js").read_text(encoding="utf-8")
        self.assertIn("buildAgentLoopEntries", text)
        self.assertIn("预演下一步维护", text)
        self.assertIn("已自动维护", text)
        self.assertIn("alchemy auto --dry-run", text)

    def test_today_feed_styles_present(self) -> None:
        css = (PLUGIN / "styles.css").read_text(encoding="utf-8")
        self.assertIn("furnace-today-feed", css)
        self.assertIn("furnace-today-feed-actions", css)

    def test_today_feed_items_are_actionable(self) -> None:
        text = (PLUGIN / "src/render_today.js").read_text(encoding="utf-8")
        self.assertIn("renderTodayFeedItem", text)
        self.assertIn("todayFeedActions", text)
        self.assertIn("todayFeedTargetLabel", text)
        self.assertIn("workspaceTargetDisplayLabel", text)
        self.assertIn("if (isWorkspaceTarget(target))", text)
        self.assertIn("Open Review", text)
        self.assertIn("Snooze", text)
        self.assertIn("runTodaySnoozeCommand", (PLUGIN / "src/plugin.js").read_text(encoding="utf-8"))
        self.assertIn("Open report", text)
        # R89: groupSpecs 标题改为中文
        self.assertIn("新报告", text)
        self.assertIn("系统动态", text)
        self.assertIn("需要你确认", text)
        self.assertIn("Copy command", text)
        self.assertIn("Copy target", text)
        self.assertIn("reviewBucketDisplayLabel", text)
        self.assertIn("待审队列", text)
        self.assertIn("Report", text)
        self.assertIn("Workspace page", text)
        self.assertIn("待确认操作", text)

    def test_today_feed_hides_runtime_paths_behind_product_labels(self) -> None:
        text = (PLUGIN / "src/render_today.js").read_text(encoding="utf-8")
        self.assertIn('text.startsWith("output/reports/")', text)
        self.assertIn('return plugin.t("Report")', text)
        self.assertIn('return plugin.t("Decision page")', text)
        self.assertIn('return plugin.t("Judgment page")', text)
        self.assertIn('return plugin.t("Proposal page")', text)

    def test_advanced_drawer_summary_exposes_counts(self) -> None:
        text = (PLUGIN / "src/render_advanced.js").read_text(encoding="utf-8")
        self.assertIn("advancedDrawerCounts", text)
        # 计数文案：中文化 + 全 0 时回退为通用描述
        self.assertIn("待复核 {review_count} · 待执行 {execution_count} · 近期运行 {run_count}", text)
        self.assertIn("系统状态、模型、运行历史等高级面板", text)

    def test_today_feed_no_mechanism_words_in_main(self) -> None:
        """首屏 i18n 文案不通过 t() 暴露具体 artifact 机制词。"""
        text = (PLUGIN / "main.js").read_text(encoding="utf-8")
        suspicious_in_t_call = re.findall(r't\("[^"]*(?:review_backlog_counts|audit\.jsonl|planner-log)[^"]*"\)', text)
        self.assertFalse(suspicious_in_t_call, f"mechanism words in t() calls: {suspicious_in_t_call}")

    # ---- R90 Today 顶部 refresh + last updated ----
    def test_r90_today_head_has_refresh_button(self) -> None:
        text = (PLUGIN / "src/render_today.js").read_text(encoding="utf-8")
        self.assertIn("furnace-today-feed-head", text)
        self.assertIn("furnace-today-refresh-btn", text)
        self.assertIn('plugin.t("刷新炉子")', text)
        self.assertIn("refreshShellSummaryCommand", text)

    def test_r90_today_head_shows_last_updated(self) -> None:
        text = (PLUGIN / "src/render_today.js").read_text(encoding="utf-8")
        self.assertIn("furnace-today-last-updated", text)
        self.assertIn("getLastSummaryRefreshLabel", text)

    def test_r90_plugin_exposes_last_summary_refresh_label(self) -> None:
        plugin_js = (PLUGIN / "src/plugin.js").read_text(encoding="utf-8")
        self.assertIn("getLastSummaryRefreshLabel", plugin_js)
        # 4 档相对时间 + 兜底
        for key in ["刚刚", "分钟前", "小时前", "天前", "未刷新"]:
            self.assertIn(key, plugin_js)
