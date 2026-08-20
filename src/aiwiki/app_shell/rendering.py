from __future__ import annotations

import html
import os
from typing import Any

from ..state.constants import DEFAULT_PROTOCOL
from .types import ShellSummary


def render_product_shell_html(summary: ShellSummary) -> str:
    def shell_href(target: str) -> str:
        if not target:
            return ""
        return os.path.relpath(target, start="output/control").replace(os.sep, "/")

    locale_text = {
        "zh": {
            "Furnace Product Shell": "炼丹炉 Product Shell",
            "Protocol": "协议",
            "Generated": "生成于",
            "Quick Links": "快捷链接",
            "Suggested Next Actions": "建议下一步动作",
            "Drift Warnings": "漂移告警",
            "Recent Receipts": "最近回执",
            "Furnace Center": "炉心面板",
            "Graph View": "图谱视图",
            "Shell Summary": "Shell 摘要",
            "LLM backend (effective)": "LLM 后端（生效）",
            "LLM backend (requested)": "LLM 后端（请求）",
            "LLM model (effective)": "LLM 模型（生效）",
            "LLM model (requested)": "LLM 模型（请求）",
            "Usage visibility": "Usage 可见性",
            "Usage accounting": "Usage 计费口径",
            "Auth mode": "认证方式",
            "Message": "提示",
            "action": "动作",
            "reason": "原因",
            "none": "无",
            "warning": "告警",
            "drift": "漂移",
            "receipt": "回执",
            "Pending review": "待审阅",
            "Ready actions": "可执行动作",
            "Overdue reviews": "逾期审阅",
            "Counter evidence": "反证候选",
            "No execution receipts yet.": "当前还没有执行回执。",
            "No suggested actions yet.": "当前还没有建议动作。",
            "No drift warnings.": "当前没有漂移告警。",
            "general": "通用",
            "response-usage": "返回 usage",
            "result-usage": "返回 usage",
            "deepseek-api": "DeepSeek API",
            "api-key": "API Key",
            "apply": "应用",
        }
    }

    def text(locale: str, key: str) -> str:
        base = str(key or "")
        if locale == "zh":
            return locale_text["zh"].get(base, base)
        return base

    def value_text(locale: str, value: Any, *, fallback: str = "none") -> str:
        raw = str(value or "").strip()
        token = raw or fallback
        return text(locale, token)

    def escape_value(locale: str, value: Any, *, fallback: str = "none") -> str:
        return html.escape(value_text(locale, value, fallback=fallback))

    links = summary.get("links", {})
    review_counts = summary.get("review_backlog_counts", {})
    recent_receipts = summary.get("recent_receipts", [])
    llm_status = summary.get("llm_status", {})
    summary_cards = [
        ("Pending review", review_counts.get("pending_decisions", 0) + review_counts.get("pending_judgments", 0)),
        ("Overdue reviews", review_counts.get("overdue_reviews", 0)),
        ("Counter evidence", review_counts.get("counter_evidence_candidates", 0)),
    ]
    quick_links = [
        ("Graph View (Obsidian)", "wiki/indexes/graph-view.md"),
        ("Machine Memory JSON", ".aiwiki/cache/machine-memory-graph.json"),
        (
            "Furnace Center (Obsidian)",
            str(links.get("furnace_center_markdown") or "wiki/indexes/furnace-center.md"),
        ),
        (
            "Shell Summary",
            str(links.get("summary_path") or summary.get("summary_path") or ""),
        ),
    ]
    suggested_actions = summary.get("suggested_next_actions", [])
    drift_warnings = summary.get("drift_warnings") if isinstance(summary.get("drift_warnings"), list) else []

    def render_cards(locale: str) -> str:
        return "".join(
            f"<article class='card'><h2>{html.escape(text(locale, title))}</h2><strong>{html.escape(str(value))}</strong></article>"
            for title, value in summary_cards
        )

    def render_links(locale: str) -> str:
        return "".join(
            f"<li><a href='{html.escape(shell_href(target))}'>{html.escape(text(locale, label))}</a></li>"
            for label, target in quick_links
            if target
        )

    def render_receipts(locale: str) -> str:
        return (
            "".join(
                f"<li><code>{escape_value(locale, receipt.get('operation'), fallback='apply')}</code>"
                f" · {html.escape(str(receipt.get('title') or receipt.get('action_id') or text(locale, 'receipt')))}"
                f" · {html.escape(str(receipt.get('applied_at') or ''))}</li>"
                for receipt in recent_receipts[:6]
                if isinstance(receipt, dict)
            )
            or f"<li>{html.escape(text(locale, 'No execution receipts yet.'))}</li>"
        )

    def render_suggested(locale: str) -> str:
        return (
            "".join(
                f"<li><strong>{html.escape(str(action.get('title') or text(locale, 'action')))}</strong>"
                f" · <code>{html.escape(str(action.get('command') or ''))}</code></li>"
                for action in suggested_actions[:6]
                if isinstance(action, dict)
            )
            or f"<li>{html.escape(text(locale, 'No suggested actions yet.'))}</li>"
        )

    def render_drift(locale: str) -> str:
        return (
            "".join(
                f"<li><code>{escape_value(locale, item.get('kind'), fallback='drift')}</code>"
                f" · {html.escape(str(item.get('message') or item.get('path') or text(locale, 'warning')))}</li>"
                for item in drift_warnings[:6]
                if isinstance(item, dict)
            )
            or f"<li>{html.escape(text(locale, 'No drift warnings.'))}</li>"
        )

    def render_llm(locale: str) -> str:
        rows = [
            ("LLM backend (effective)", llm_status.get("backend")),
            ("LLM backend (requested)", llm_status.get("backend_requested")),
            ("LLM model (effective)", llm_status.get("effective_model") or llm_status.get("model")),
            ("LLM model (requested)", llm_status.get("model_requested")),
            ("Usage visibility", llm_status.get("usage_visibility")),
            ("Usage accounting", llm_status.get("usage_accounting")),
            ("Auth mode", llm_status.get("auth_mode")),
        ]
        if llm_status.get("message"):
            rows.append(("Message", llm_status.get("message")))
        return "".join(
            f"<p><span class='meta-label'>{html.escape(text(locale, label))}</span> <code>{escape_value(locale, value)}</code></p>"
            for label, value in rows
        )

    def render_panel(locale: str) -> str:
        return "\n".join(
            [
                "      <div class='hero'>",
                "        <div>",
                f"          <h1>{html.escape(text(locale, 'Furnace Product Shell'))}</h1>",
                (
                    f"          <p>{html.escape(text(locale, 'Protocol'))} "
                    f"<code>{escape_value(locale, summary.get('active_protocol') or DEFAULT_PROTOCOL)}</code>"
                    f" · {html.escape(text(locale, 'Generated'))} "
                    f"<code>{html.escape(str(summary.get('generated_at') or ''))}</code></p>"
                ),
                "        </div>",
                "        <div class='llm-box'>",
                render_llm(locale),
                "        </div>",
                "      </div>",
                f"      <div class='cards'>{render_cards(locale)}</div>",
                "      <div class='grid'>",
                "        <section>",
                f"          <h2>{html.escape(text(locale, 'Quick Links'))}</h2>",
                f"          <ul>{render_links(locale)}</ul>",
                "        </section>",
                "        <section>",
                f"          <h2>{html.escape(text(locale, 'Suggested Next Actions'))}</h2>",
                f"          <ul>{render_suggested(locale)}</ul>",
                "        </section>",
                "        <section>",
                f"          <h2>{html.escape(text(locale, 'Drift Warnings'))}</h2>",
                f"          <ul>{render_drift(locale)}</ul>",
                "        </section>",
                "        <section>",
                f"          <h2>{html.escape(text(locale, 'Recent Receipts'))}</h2>",
                f"          <ul>{render_receipts(locale)}</ul>",
                "        </section>",
                "      </div>",
            ]
        )

    return "\n".join(
        [
            "<!DOCTYPE html>",
            "<html lang='zh' data-default-locale='zh'>",
            "<head>",
            "  <meta charset='utf-8' />",
            "  <meta name='viewport' content='width=device-width, initial-scale=1' />",
            "  <title>炼丹炉 Product Shell</title>",
            "  <style>",
            "    body { font-family: Inter, system-ui, sans-serif; margin: 0; background: #0b1020; color: #e5eefc; }",
            "    main { max-width: 1100px; margin: 0 auto; padding: 24px 20px 48px; }",
            "    .toolbar { display: flex; justify-content: flex-end; margin-bottom: 12px; }",
            "    .locale-switch { display: inline-flex; gap: 8px; }",
            "    .locale-switch button { background: #111833; color: #e5eefc; border: 1px solid #243255; border-radius: 999px; padding: 6px 12px; cursor: pointer; }",
            "    .locale-switch button.active { background: #2f6feb; border-color: #2f6feb; }",
            "    .locale-panel { display: none; }",
            "    .locale-panel.active { display: block; }",
            "    .hero { display: flex; justify-content: space-between; gap: 24px; flex-wrap: wrap; margin-bottom: 24px; }",
            "    .llm-box { min-width: 280px; }",
            "    .meta-label { display: inline-block; min-width: 160px; color: #aebbd6; }",
            "    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0 28px; }",
            "    .card, section { background: #111833; border: 1px solid #243255; border-radius: 14px; padding: 16px; }",
            "    h1, h2 { margin: 0 0 12px; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    a { color: #8cc4ff; }",
            "    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }",
            "    code { color: #ffd580; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <div class='toolbar'>",
            "      <div class='locale-switch'>",
            "        <button type='button' data-locale-btn='zh' class='active'>中文</button>",
            "        <button type='button' data-locale-btn='en'>English</button>",
            "      </div>",
            "    </div>",
            "    <section class='locale-panel active' data-locale-panel='zh'>",
            render_panel("zh"),
            "    </section>",
            "    <section class='locale-panel' data-locale-panel='en'>",
            render_panel("en"),
            "    </section>",
            "  </main>",
            "  <script>",
            "    (() => {",
            "      const setLocale = (locale) => {",
            "        document.querySelectorAll('[data-locale-panel]').forEach((panel) => {",
            "          panel.classList.toggle('active', panel.getAttribute('data-locale-panel') === locale);",
            "        });",
            "        document.querySelectorAll('[data-locale-btn]').forEach((button) => {",
            "          button.classList.toggle('active', button.getAttribute('data-locale-btn') === locale);",
            "        });",
            "        document.documentElement.lang = locale === 'en' ? 'en' : 'zh';",
            "      };",
            "      document.querySelectorAll('[data-locale-btn]').forEach((button) => {",
            "        button.addEventListener('click', () => setLocale(button.getAttribute('data-locale-btn') || 'zh'));",
            "      });",
            "      setLocale(document.documentElement.getAttribute('data-default-locale') || 'zh');",
            "    })();",
            "  </script>",
            "</body>",
            "</html>",
            "",
        ]
    )
