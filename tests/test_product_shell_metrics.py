import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
PLUGIN = ROOT / ".obsidian/plugins/furnace-product-shell"

METRIC_KEYS = [
    "provenance_completeness",
    "stale_ratio",
    "review_closure_rate",
    "proposal_acceptance_rate",
    "judgment_revisit_rate",
    "output_file_back_rate",
    "elixir_reuse_count",
]


def _function_body_after(text: str, name: str) -> str:
    start = text.index(f"function {name}(")
    next_function = text.find("\nfunction ", start + 1)
    if next_function == -1:
        return text[start:]
    return text[start:next_function]


class ProductShellMetricsContractTests(unittest.TestCase):
    def test_metrics_panel_present_in_built_main(self) -> None:
        text = (PLUGIN / "main.js").read_text(encoding="utf-8")
        self.assertIn("renderAdvancedMetricsPanel", text)
        self.assertIn("formatMetricValue", text)
        for key in METRIC_KEYS:
            self.assertIn(key, text, f"metric key missing: {key}")

    def test_metrics_panel_unit_handling(self) -> None:
        text = (PLUGIN / "main.js").read_text(encoding="utf-8")
        for unit in ["ratio", "count", "percent"]:
            self.assertTrue(f'"{unit}"' in text or f"'{unit}'" in text)

    def test_metrics_panel_styles_present(self) -> None:
        css = (PLUGIN / "styles.css").read_text(encoding="utf-8")
        self.assertIn("furnace-advanced-metrics", css)
        self.assertIn("furnace-advanced-metrics-list", css)
        self.assertIn("furnace-advanced-metrics-item", css)

    def test_metrics_panel_not_in_today_feed(self) -> None:
        """首屏 Today feed 不暴露 metrics（contract Stop Line）。"""
        text = (PLUGIN / "src/render_today.js").read_text(encoding="utf-8")
        body = _function_body_after(text, "renderTodayFeed")
        self.assertNotIn("renderAdvancedMetricsPanel", body)
        self.assertNotIn("provenance_completeness", body)
        self.assertNotIn("elixir_reuse_count", body)

    def test_advanced_drawer_invokes_metrics_panel(self) -> None:
        """Advanced 抽屉调用 renderAdvancedMetricsPanel。"""
        text = (PLUGIN / "src/render.js").read_text(encoding="utf-8")
        body = _function_body_after(text, "renderAdvancedDrawer")
        self.assertIn("renderAdvancedMetricsPanel", body)
