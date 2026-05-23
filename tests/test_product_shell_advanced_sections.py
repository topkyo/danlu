"""R91/C5: Advanced 抽屉子 section 重组测试。

锁住 operator-only 两组结构（系统状态 / 运行与历史）+ banner 外置 +
折叠态 settings 持久化 + summary 摘要 helper 存在。
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
PLUGIN = ROOT / ".obsidian/plugins/furnace-product-shell"
SRC = PLUGIN / "src"


class AdvancedSectionsStructureTests(unittest.TestCase):
    """render_advanced.js operator-only 两组结构 + banner 外置"""

    def test_render_advanced_drawer_uses_operator_only_sections(self) -> None:
        text = (SRC / "render_advanced.js").read_text(encoding="utf-8")
        self.assertIn('key: "status"', text)
        self.assertIn('key: "history"', text)
        self.assertNotIn('key: "devops"', text)
        self.assertIn('plugin.t("系统状态")', text)
        self.assertIn('plugin.t("运行与历史")', text)
        self.assertNotIn('plugin.t("开发者操作")', text)
        self.assertNotIn("renderLegacyAdvancedPanel", text)

    def test_dev_banner_is_outside_collapsible_sections(self) -> None:
        """dev banner 必须直接挂在 wrapper（外置），不在任一 section 内"""
        text = (SRC / "render_advanced.js").read_text(encoding="utf-8")
        # 找 wrapper.createEl 或类似 dev banner 渲染
        self.assertIn("furnace-advanced-dev-banner", text)
        # 在 renderAdvancedDrawer 函数内，dev banner 必须在 details 之前出现
        start = text.index("function renderAdvancedDrawer(")
        end = text.index("\nfunction ", start + 1)
        body = text[start:end]
        banner_pos = body.find("furnace-advanced-dev-banner")
        first_section_pos = body.find("renderAdvancedSection(plugin, body")
        self.assertGreater(banner_pos, 0)
        self.assertGreater(first_section_pos, 0)
        self.assertLess(banner_pos, first_section_pos, "dev banner 必须在第一个 section 之前渲染")

    def test_render_advanced_section_helper_exists(self) -> None:
        text = (SRC / "render_advanced.js").read_text(encoding="utf-8")
        self.assertIn("function renderAdvancedSection(", text)
        # 用 <details> 原生折叠，避免引第三方
        self.assertIn('createEl("details"', text)
        self.assertIn('createEl("summary"', text)
        # toggle 事件回写持久化
        self.assertIn('addEventListener("toggle"', text)
        self.assertIn("setAdvancedSectionExpanded", text)

    def test_section_summary_helpers_exist(self) -> None:
        text = (SRC / "render_advanced.js").read_text(encoding="utf-8")
        self.assertIn("function buildStatusSectionSummary(", text)
        self.assertIn("function buildHistorySectionSummary(", text)
        # 状态摘要不在折叠摘要里暴露 protocol/LLM 机制名
        self.assertIn("运行诊断 · 同步 {sync}", text)
        self.assertNotIn("协议 {protocol} · LLM {llm} · 同步 {sync}", text)
        # 历史摘要含运行/审/执行计数
        self.assertIn("最近运行 {n} 条 · 待审 {review} · 待执行 {execution}", text)


class AdvancedSectionsPersistenceTests(unittest.TestCase):
    """settings.advancedSectionsExpanded 默认 + getter/setter"""

    def test_default_settings_includes_advanced_sections_expanded(self) -> None:
        text = (SRC / "constants.js").read_text(encoding="utf-8")
        self.assertIn("advancedSectionsExpanded", text)
        # 默认全 false（默认折叠）
        self.assertIn("advancedSectionsExpanded: { status: false, history: false }", text)

    def test_plugin_exposes_get_set_advanced_section_expanded(self) -> None:
        text = (SRC / "plugin.js").read_text(encoding="utf-8")
        self.assertIn("getAdvancedSectionExpanded(key)", text)
        self.assertIn("async setAdvancedSectionExpanded(key, value)", text)
        # setter 必须 await savePluginState
        idx = text.index("async setAdvancedSectionExpanded(key, value)")
        body = text[idx : idx + 800]
        self.assertIn("savePluginState", body)
        self.assertIn("advancedSectionsExpanded", body)
        self.assertNotIn("devops", body)
        self.assertIn('key !== "status" && key !== "history"', body)

    def test_legacy_settings_are_normalized_on_load(self) -> None:
        text = (SRC / "plugin.js").read_text(encoding="utf-8")
        load_start = text.index("async loadPluginState()")
        load_body = text[load_start : load_start + 1800]
        self.assertIn('delete this.settings.showHtmlShortcuts', load_body)
        self.assertIn('delete this.settings.defaultAskMode', load_body)
        self.assertIn('migratedAdvancedSectionsExpanded = {', load_body)
        self.assertIn('status: Boolean(rawAdvancedSectionsExpanded.status)', load_body)
        self.assertIn('history: Boolean(rawAdvancedSectionsExpanded.history)', load_body)

    def test_removed_advanced_settings_do_not_leave_visible_toggles(self) -> None:
        settings_text = (SRC / "settings.js").read_text(encoding="utf-8")
        constants_text = (SRC / "constants.js").read_text(encoding="utf-8")
        self.assertNotIn("showHtmlShortcuts", settings_text)
        self.assertNotIn("Show HTML shortcuts", settings_text)
        self.assertNotIn("showHtmlShortcuts", constants_text)
        self.assertNotIn("Show HTML shortcuts", constants_text)

    def test_unbundled_deprecated_seams_are_removed(self) -> None:
        self.assertFalse((SRC / "state/settings-state.js").exists())
        self.assertFalse((SRC / "state/accessors.js").exists())
        self.assertFalse((SRC / "bridge/shell.js").exists())


class AdvancedSectionsTranslationsTests(unittest.TestCase):
    """中文翻译键齐备"""

    def test_section_titles_in_zh_dictionary(self) -> None:
        text = (SRC / "constants.js").read_text(encoding="utf-8")
        for key in ("系统状态", "运行与历史"):
            self.assertIn(f'"{key}":', text)
        self.assertNotIn('"开发者操作":', text)

    def test_summary_template_keys_present(self) -> None:
        text = (SRC / "constants.js").read_text(encoding="utf-8")
        self.assertIn('"运行诊断 · 同步 {sync}"', text)
        self.assertNotIn('"协议 {protocol} · LLM {llm} · 同步 {sync}"', text)
        self.assertIn('"最近运行 {n} 条 · 待审 {review} · 待执行 {execution}"', text)
        self.assertNotIn('"编译 / 同步 / 协议切换 / 日志等命令"', text)


class AdvancedSectionsBuiltMainTests(unittest.TestCase):
    """rebuild 后 main.js 包含 R91 标识"""

    def test_main_js_contains_advanced_sections_helpers(self) -> None:
        text = (PLUGIN / "main.js").read_text(encoding="utf-8")
        self.assertIn("renderAdvancedSection", text)
        self.assertIn("buildStatusSectionSummary", text)
        self.assertIn("buildHistorySectionSummary", text)
        self.assertIn("getAdvancedSectionExpanded", text)
        self.assertIn("setAdvancedSectionExpanded", text)


class AdvancedSectionsHistoryBodyTests(unittest.TestCase):
    """运行与历史 section body 含 3 个核心入口 + Latest LLM run"""

    def test_history_body_renders_three_entry_buttons(self) -> None:
        text = (SRC / "render_advanced.js").read_text(encoding="utf-8")
        self.assertIn("function renderHistorySectionBody(", text)
        self.assertIn("openRecentRunsView", text)
        self.assertIn("openReviewCenterView", text)
        self.assertIn("openExecutionCenterView", text)

    def test_history_body_includes_latest_llm_run_summary(self) -> None:
        text = (SRC / "render_advanced.js").read_text(encoding="utf-8")
        idx = text.index("function renderHistorySectionBody(")
        body = text[idx : idx + 3000]
        self.assertIn("latestLlmRun", body)
        self.assertIn("furnace-advanced-section-latest-llm", body)


class AdvancedSectionsNoOuterWrapperTests(unittest.TestCase):
    """R91/C5：去掉外层 Advanced details；DevOps panel 不再存在"""

    def test_render_advanced_drawer_has_no_outer_advanced_details(self) -> None:
        text = (SRC / "render_advanced.js").read_text(encoding="utf-8")
        idx = text.index("function renderAdvancedDrawer(")
        end = text.index("\nfunction ", idx + 1)
        body = text[idx:end]
        # R90 之前外层包了 details cls=furnace-shell-advanced；R91 round 2 必须去掉
        self.assertNotIn('createEl("details", { cls: "furnace-shell-advanced" })', body)

    def test_legacy_advanced_panel_is_not_part_of_product_shell(self) -> None:
        text = (SRC / "render_primitives.js").read_text(encoding="utf-8")
        self.assertNotIn("function renderLegacyAdvancedPanel(", text)
        plugin_text = (SRC / "plugin.js").read_text(encoding="utf-8")
        self.assertNotIn("renderLegacyAdvancedPanel(container)", plugin_text)


if __name__ == "__main__":
    unittest.main()
