"""R88 — pending submissions + empty-state CTA + advanced wording 契约。

锁定本轮 PM/UX 三件套不被回退：
  #1 Today 空态有可点击 CTA 按钮（聚焦 universal input textarea）
  #2 提交后插入"处理中"卡片 + 失败重试 + 自动 reconcile
  #3 Advanced/通用面板暴露给用户的机制词被替换为白话
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
PLUGIN = ROOT / ".obsidian/plugins/furnace-product-shell"
SRC = PLUGIN / "src"


class PendingSubmissionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.main = (PLUGIN / "main.js").read_text(encoding="utf-8")

    # ---- #2 pending submission state machine ----
    def test_plugin_exposes_pending_helpers(self) -> None:
        plugin_js = (SRC / "plugin.js").read_text(encoding="utf-8")
        self.assertIn("pendingSubmissions", plugin_js)
        self.assertIn("pushPendingSubmission", plugin_js)
        self.assertIn("markPendingSubmissionDone", plugin_js)
        self.assertIn("markPendingSubmissionFailed", plugin_js)
        self.assertIn("removePendingSubmission", plugin_js)
        self.assertIn("reconcilePendingSubmissions", plugin_js)

    def test_pending_helpers_built_into_main(self) -> None:
        for needle in (
            "pendingSubmissions",
            "pushPendingSubmission",
            "markPendingSubmissionDone",
            "markPendingSubmissionFailed",
            "reconcilePendingSubmissions",
        ):
            self.assertIn(needle, self.main, f"missing in main.js: {needle}")

    def test_render_input_pushes_pending_on_submit(self) -> None:
        text = (SRC / "render_input.js").read_text(encoding="utf-8")
        self.assertIn("pushPendingSubmission", text)
        # R89: handleSubmit 成功 → markReceived；失败 → markFailed
        self.assertIn("markPendingSubmissionReceived", text)
        self.assertIn("markPendingSubmissionFailed", text)

    def test_today_renders_pending_group(self) -> None:
        text = (SRC / "render_today.js").read_text(encoding="utf-8")
        self.assertIn("renderPendingSubmissionsGroup", text)
        self.assertIn("furnace-today-feed-pending", text)
        self.assertIn("furnace-pending-card", text)
        self.assertIn("处理中", text)
        # 失败态有重试 + dismiss
        self.assertIn("重试", text)
        self.assertIn("Dismiss", text)

    def test_reconcile_hooked_into_summary_updates(self) -> None:
        plugin_js = (SRC / "plugin.js").read_text(encoding="utf-8")
        # processShellSummaryUpdates 必须在顶部调用 reconcile
        idx_proc = plugin_js.find("processShellSummaryUpdates(summary) {")
        self.assertGreater(idx_proc, 0)
        window = plugin_js[idx_proc : idx_proc + 400]
        self.assertIn("reconcilePendingSubmissions", window)

    # ---- #1 empty-state CTA ----
    def test_today_empty_state_has_cta_button(self) -> None:
        text = (SRC / "render_today.js").read_text(encoding="utf-8")
        self.assertIn("furnace-today-cta-submit", text)
        self.assertIn("投一份材料", text)
        # 按钮 click 必须聚焦 universal input textarea
        self.assertIn("furnace-universal-input-textarea", text)
        self.assertIn(".focus()", text)

    # ---- #3 advanced/user-facing wording de-jargonization ----
    def test_user_facing_wording_dejargonized(self) -> None:
        # 这些用户层文件不应再含 shell-summary.json / Click Refresh first 等机制词
        offenders = (
            (SRC / "render_execution.js", "shell-summary.json is not available"),
            (SRC / "render_review.js", "shell-summary.json is not available"),
            (SRC / "render_primitives.js", "Click Refresh first so shell-summary"),
            (SRC / "state/health-state.js", "shell-summary.json has not been generated"),
            (SRC / "render_today.js", "shell-summary.json"),
        )
        for path, jargon in offenders:
            content = path.read_text(encoding="utf-8")
            self.assertNotIn(jargon, content, f"jargon leaked into {path.name}: {jargon}")

    # ---- P1 round 2: reconcile robustness ----
    def test_reconcile_uses_timestamp_and_extra_fields(self) -> None:
        plugin_js = (SRC / "plugin.js").read_text(encoding="utf-8")
        idx = plugin_js.find("reconcilePendingSubmissions(summary) {")
        self.assertGreater(idx, 0)
        end = plugin_js.find("\n  }\n", idx)
        self.assertGreater(end, idx)
        body = plugin_js[idx:end]
        # 时间戳门槛
        for needle in ("created_at", "generated_at", "SKEW_MS", "candMs"):
            self.assertIn(needle, body, f"reconcile missing timestamp guard: {needle}")
        # 字段扩展
        for field in ("receipt_path", "output_path", "query", "target"):
            self.assertIn(f"cand.{field}", body, f"reconcile missing field: {field}")
        # 短指纹 exact 匹配分支
        self.assertIn("useExact", body)

    def test_reconcile_keeps_running_past_window(self) -> None:
        plugin_js = (SRC / "plugin.js").read_text(encoding="utf-8")
        idx = plugin_js.find("reconcilePendingSubmissions(summary) {")
        end = plugin_js.find("\n  }\n", idx)
        body = plugin_js[idx:end]
        self.assertIn("RECONCILE_WINDOW_MS", body)
        self.assertRegex(
            body,
            r"now - startMs > RECONCILE_WINDOW_MS\)\s*\{\s*remaining\.push\(entry\)",
        )

    def test_pending_dedupe_on_double_submit(self) -> None:
        # 同 fingerprint 的 running 卡片不应重复入栈
        plugin_js = (SRC / "plugin.js").read_text(encoding="utf-8")
        idx = plugin_js.find("pushPendingSubmission(displayText, opts")
        self.assertGreater(idx, 0)
        window = plugin_js[idx : idx + 1500]
        self.assertIn("payloadFingerprint", window)
        # 必须有 dup 检测分支
        self.assertRegex(window, r"status === \"running\"")
        self.assertIn("return dup.id", window)

    def test_retry_resets_card_in_place(self) -> None:
        # 重试不应 remove 卡片；改回 running 状态原地循环
        plugin_js = (SRC / "plugin.js").read_text(encoding="utf-8")
        self.assertIn("resetPendingSubmissionForRetry", plugin_js)
        today_js = (SRC / "render_today.js").read_text(encoding="utf-8")
        self.assertIn("resetPendingSubmissionForRetry", today_js)
        # render_today 重试路径不再调 removePendingSubmission
        retry_idx = today_js.find("retryBtn.addEventListener")
        self.assertGreater(retry_idx, 0)
        retry_block = today_js[retry_idx : retry_idx + 900]
        # 重试 handler 自身不应再 removePendingSubmission；改回 running
        self.assertNotIn("removePendingSubmission(entry.id);\n          plugin.markPending", retry_block)
        self.assertIn("resetPendingSubmissionForRetry", retry_block)
        # 必须收口到 markReceived（R89 两段式：成功=已接收，等 reconcile 升 done）/markFailed
        self.assertIn("markPendingSubmissionReceived", retry_block)
        self.assertIn("markPendingSubmissionFailed", retry_block)

    def test_today_empty_cta_covers_no_summary_branch(self) -> None:
        # !summary 分支也必须渲染 CTA（提取 helper）
        today_js = (SRC / "render_today.js").read_text(encoding="utf-8")
        self.assertIn("renderTodayEmptyCta", today_js)
        # !summary 分支 return 前必须调 helper
        no_sum_idx = today_js.find("if (!summary)")
        self.assertGreater(no_sum_idx, 0)
        block = today_js[no_sum_idx : no_sum_idx + 800]
        self.assertIn("renderTodayEmptyCta", block)

    # ---- R89 #1 持久化 ----
    def test_plugin_persists_pending_to_settings(self) -> None:
        plugin_js = (SRC / "plugin.js").read_text(encoding="utf-8")
        # 序列化器
        self.assertIn("serializePendingSubmissions", plugin_js)
        # savePluginState 把 persistedPendingSubmissions 写进 settings
        save_idx = plugin_js.find("async savePluginState()")
        self.assertGreater(save_idx, 0)
        save_body = plugin_js[save_idx : save_idx + 500]
        self.assertIn("persistedPendingSubmissions", save_body)
        self.assertIn("serializePendingSubmissions", save_body)

    def test_plugin_hydrates_pending_with_ttl(self) -> None:
        plugin_js = (SRC / "plugin.js").read_text(encoding="utf-8")
        self.assertIn("hydratePendingSubmissions", plugin_js)
        hyd_idx = plugin_js.find("hydratePendingSubmissions(raw)")
        self.assertGreater(hyd_idx, 0)
        body = plugin_js[hyd_idx : hyd_idx + 2000]
        # TTL 24h 常量
        self.assertIn("24 * 60 * 60 * 1000", body)
        # stale running → failed
        self.assertIn('nextStatus = "failed"', body)
        # 错误文案
        self.assertIn("上次提交可能仍在处理或已完成", body)

    def test_loadstate_calls_hydrate(self) -> None:
        plugin_js = (SRC / "plugin.js").read_text(encoding="utf-8")
        load_idx = plugin_js.find("async loadPluginState()")
        self.assertGreater(load_idx, 0)
        body = plugin_js[load_idx : load_idx + 5000]
        self.assertIn("hydratePendingSubmissions", body)
        self.assertIn("persistedPendingSubmissions", body)

    # ---- R89 #2 两段式语义 ----
    def test_plugin_exposes_received_state_helper(self) -> None:
        plugin_js = (SRC / "plugin.js").read_text(encoding="utf-8")
        self.assertIn("markPendingSubmissionReceived", plugin_js)

    def test_render_input_calls_received_not_done(self) -> None:
        text = (SRC / "render_input.js").read_text(encoding="utf-8")
        # 成功路径 → markReceived（不再 markDone）
        self.assertIn("markPendingSubmissionReceived", text)
        # 成功 succeeded = true 之后不应直接 markDone
        suc_idx = text.find("succeeded = true;")
        self.assertGreater(suc_idx, 0)
        window = text[suc_idx : suc_idx + 200]
        self.assertIn("markPendingSubmissionReceived", window)
        self.assertNotIn("markPendingSubmissionDone", window)

    def test_today_renders_received_status(self) -> None:
        text = (SRC / "render_today.js").read_text(encoding="utf-8")
        self.assertIn('entry.status === "received"', text)
        self.assertIn("已接收，等待生成报告", text)
        self.assertIn("报告已生成", text)
        self.assertIn("已记录", text)
        # 区分 outputs / receipts
        self.assertIn('reconcileTarget === "receipts"', text)

    def test_reconcile_routes_target_to_markdone(self) -> None:
        plugin_js = (SRC / "plugin.js").read_text(encoding="utf-8")
        idx = plugin_js.find("reconcilePendingSubmissions(summary) {")
        self.assertGreater(idx, 0)
        end = plugin_js.find("\n  }\n", idx)
        body = plugin_js[idx:end]
        # 目标分流
        self.assertIn('target = "outputs"', body)
        self.assertIn('target = "receipts"', body)
        # 命中后调 markDone（带 target）
        self.assertIn("markPendingSubmissionDone", body)

    # ---- R89 #3 文案中文化 + Advanced 分隔 + 失败 hint ----
    def test_today_groups_use_chinese(self) -> None:
        text = (SRC / "render_today.js").read_text(encoding="utf-8")
        # 不应再用旧英文 key 当显示文本
        self.assertIn('plugin.t("新报告")', text)
        self.assertIn('plugin.t("系统动态")', text)
        self.assertIn('plugin.t("需要你确认")', text)
        self.assertIn('plugin.t("已完成")', text)
        self.assertIn('plugin.t("下一步建议")', text)

    def test_advanced_drawer_has_dev_banner(self) -> None:
        text = (SRC / "render_advanced.js").read_text(encoding="utf-8")
        self.assertIn("furnace-advanced-dev-banner", text)
        self.assertIn("以下为开发者诊断信息", text)
        # 必须在 advanced body 内（render 顺序：body createDiv → banner → mainHeader）
        body_idx = text.find('createDiv({ cls: "furnace-shell-advanced-body" })')
        banner_idx = text.find("furnace-advanced-dev-banner")
        self.assertGreater(banner_idx, body_idx)

    def test_failed_card_has_user_facing_hint(self) -> None:
        text = (SRC / "render_today.js").read_text(encoding="utf-8")
        self.assertIn("furnace-pending-card-hint", text)
        self.assertIn("这次没成功。可以点重试，或检查输入是否完整。", text)

    def test_styles_define_received_and_dev_banner(self) -> None:
        css = (PLUGIN / "styles.css").read_text(encoding="utf-8")
        self.assertIn(".furnace-pending-received", css)
        self.assertIn(".furnace-advanced-dev-banner", css)
        self.assertIn(".furnace-pending-card-hint", css)


if __name__ == "__main__":
    unittest.main()
