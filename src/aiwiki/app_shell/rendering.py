from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

from ..compile.state import load_compile_state
from ..config import LLMConfig
from ..content.archive import (
    active_material_archive_entries,
    load_archive_candidates_state,
    load_material_archive_state,
)
from ..content.io import (
    collect_recent_output_artifacts,
    summarize_runtime_event_for_shell,
)
from ..content.rewrite import load_concept_rewrite_state
from ..execution.history import load_llm_receipt_history, load_runtime_history
from ..execution.paths import llm_receipt_log_path, run_log_path
from ..execution.policy import load_execution_receipt_history
from ..lifecycle.aging import collect_aging_signals
from ..lifecycle.knowledge import knowledge_lifecycle_governance_summary, load_knowledge_lifecycle_state
from ..lifecycle.paths import nightly_health_state_path
from ..lifecycle.status import (
    action_transition_profile,
    archive_transition_profile,
    collect_curated_pages,
    curated_page_transition_profile,
    review_queue,
    rewrite_proposal_status_rank,
    rewrite_transition_profile,
    transition_profile,
    valid_curated_statuses,
)
from ..llm import classify_backend_error
from ..memory.action_core import (
    action_priority_rank,
    action_status_rank,
    action_supports_low_risk_apply,
)
from ..memory.state import load_machine_memory
from ..planner.state import load_planner_state, load_query_route_telemetry
from ..protocol.library import PROTOCOL_LIBRARY
from ..protocol.runtime_config import ACTION_STATUSES, REWRITE_PROPOSAL_STATUSES
from ..protocol.scaffold import ensure_layout
from ..protocol.state import load_protocol_state
from ..protocol.types import ProtocolState
from ..render.paths import (
    agent_workbench_path,
    domain_pilots_path,
    execution_audit_html_path,
    execution_audit_path,
    execution_bundle_path,
    execution_proposal_path,
    furnace_center_html_path,
    machine_memory_graph_html_path,
    output_packs_index_path,
    product_shell_html_path,
    review_center_html_path,
    shell_summary_path,
)
from ..render.views import (
    judgment_asset_attention_sort_key,
    judgment_asset_shell_record,
    judgment_asset_summary,
)
from ..state.constants import DEFAULT_PROTOCOL
from ..state.io import load_json_document
from ..state.manifest import load_manifest
from ..utils.io import (
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from ..utils.markdown import parse_frontmatter, strip_frontmatter
from ..utils.path import relative_path
from ..utils.text import tokenize
from ..utils.time import utc_now
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
            "Planner": "规划器",
            "Query Routing": "查询路由",
            "Suggested Next Actions": "建议下一步动作",
            "Drift Warnings": "漂移告警",
            "Recent Runs": "最近运行",
            "Recent Receipts": "最近回执",
            "Furnace Center": "炉心面板",
            "Execution Audit": "执行审计",
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
            "score": "分数",
            "reason": "原因",
            "query": "查询",
            "none": "无",
            "warning": "告警",
            "drift": "漂移",
            "runtime": "运行",
            "receipt": "回执",
            "review": "审阅",
            "Pending review": "待审阅",
            "Ready actions": "可执行动作",
            "Planner blocked": "规划阻塞",
            "Recent routes": "最近路由",
            "No planner action is queued yet.": "当前还没有排队中的规划动作。",
            "No query route telemetry has been recorded yet.": "当前还没有记录查询路由遥测。",
            "No runtime events yet.": "当前还没有运行事件。",
            "No execution receipts yet.": "当前还没有执行回执。",
            "No suggested actions yet.": "当前还没有建议动作。",
            "No drift warnings.": "当前没有漂移告警。",
            "general": "通用",
            "response-usage": "返回 usage",
            "result-usage": "返回 usage",
            "deepseek-api": "DeepSeek API",
            "api-key": "API Key",
            "apply": "应用",
            "review-page": "审阅页面",
            "archive-apply": "归档应用",
            "archive-revert": "归档回滚",
            "knowledge-lifecycle-override": "生命周期覆盖",
            "nightly": "夜间巡检",
            "default": "默认",
            "success": "成功",
            "failed": "失败",
            "running": "运行中",
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
    dashboard = summary.get("dashboard", {})
    planner = summary.get("planner", {})
    planner_next_action = planner.get("next_action", {}) if isinstance(planner, dict) else {}
    route_telemetry = summary.get("route_telemetry", {})
    last_route = route_telemetry.get("last_entry", {}) if isinstance(route_telemetry, dict) else {}
    recent_runs = summary.get("recent_runs", [])
    recent_receipts = summary.get("recent_receipts", [])
    llm_status = summary.get("llm_status", {})
    dashboard_cards = dashboard.get("cards", []) if isinstance(dashboard, dict) else []
    summary_cards = [
        (
            str(card.get("label") or ""),
            card.get("value", 0),
        )
        for card in dashboard_cards
        if isinstance(card, dict)
    ] or [
        ("Pending review", review_counts.get("pending_decisions", 0) + review_counts.get("pending_judgments", 0)),
        ("Ready actions", review_counts.get("ready_actions", 0)),
        ("Planner blocked", planner.get("counts", {}).get("blocked", 0) if isinstance(planner, dict) else 0),
        ("Recent routes", len(route_telemetry.get("entries", [])) if isinstance(route_telemetry, dict) else 0),
    ]
    quick_links = [
        ("Graph View (Obsidian)", str(links.get("graph_view_markdown") or "")),
        ("Machine Memory JSON", str(links.get("machine_memory_graph_json") or "")),
        ("Furnace Center (Obsidian)", str(links.get("furnace_center_markdown") or "")),
        ("Shell Summary", str(links.get("summary_path") or "")),
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

    def render_planner(locale: str) -> str:
        if planner_next_action:
            return (
                f"<p><strong>{html.escape(str(planner_next_action.get('title') or text(locale, 'none')))}</strong>"
                f" · {html.escape(text(locale, 'action'))} <code>{escape_value(locale, planner_next_action.get('action_id'))}</code>"
                f" · {html.escape(text(locale, 'score'))} <code>{html.escape(str(planner_next_action.get('priority_score', 0)))}</code></p>"
            )
        return f"<p>{html.escape(text(locale, 'No planner action is queued yet.'))}</p>"

    def render_route(locale: str) -> str:
        if last_route:
            return (
                f"<p><strong>{escape_value(locale, last_route.get('selected_strategy'))}</strong>"
                f" · {html.escape(text(locale, 'reason'))} <code>{escape_value(locale, last_route.get('selection_reason'))}</code>"
                f" · {html.escape(text(locale, 'query'))} <code>{escape_value(locale, last_route.get('query_signature'))}</code></p>"
            )
        return f"<p>{html.escape(text(locale, 'No query route telemetry has been recorded yet.'))}</p>"

    def render_runs(locale: str) -> str:
        return (
            "".join(
                f"<li><code>{escape_value(locale, run.get('event_type'), fallback='runtime')}</code>"
                f" · {html.escape(str(run.get('occurred_at') or ''))}"
                f" · {html.escape(str(run.get('title') or run.get('summary') or ''))}</li>"
                for run in recent_runs[:6]
                if isinstance(run, dict)
            )
            or f"<li>{html.escape(text(locale, 'No runtime events yet.'))}</li>"
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
                f"          <h2>{html.escape(text(locale, 'Planner'))}</h2>",
                f"          {render_planner(locale)}",
                "        </section>",
                "        <section>",
                f"          <h2>{html.escape(text(locale, 'Query Routing'))}</h2>",
                f"          {render_route(locale)}",
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
                f"          <h2>{html.escape(text(locale, 'Recent Runs'))}</h2>",
                f"          <ul>{render_runs(locale)}</ul>",
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
