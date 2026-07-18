"""HTML item renderers for the review center surface."""

from __future__ import annotations

import html
from typing import Any

from ..app_lifecycle import (
    collect_aging_signals,
    display_action_status,
    display_curated_status,
    display_judgment_lifecycle_state,
    display_knowledge_lifecycle_state,
    display_rewrite_proposal_status,
    knowledge_lifecycle_governance_summary,
    review_queue,
)
from ..lifecycle.knowledge import default_knowledge_lifecycle_state
from ..memory.action_core import action_supports_low_risk_apply
from ..state.constants import DEFAULT_PROTOCOL
from .html_theme import html_meta_theme, html_theme_css


def render_review_center_page_item(page: dict[str, str]) -> str:
    path = html.escape(f"../../{page['path']}")
    status = html.escape(display_curated_status(page.get("status", "") or "unknown"))
    revisit = html.escape(page.get("revisit_after", "") or "none")
    return f'<li><a href="{path}">{html.escape(page["title"])}</a> | status {status} | revisit {revisit}</li>'


def render_review_center_action_item(action: dict[str, Any]) -> str:
    primary = html.escape(str(action.get("primary_path") or ""))
    status = html.escape(display_action_status(str(action.get("status") or "proposed")))
    priority = html.escape(str(action.get("priority") or "medium"))
    detail = ""
    if action.get("secondary_path"):
        detail = f" | secondary <code>{html.escape(str(action['secondary_path']))}</code>"
    command = ""
    if action.get("command_hint"):
        command = f" | command <code>{html.escape(str(action['command_hint']))}</code>"
    return (
        f"<li>{html.escape(str(action.get('title') or 'unnamed action'))}"
        f" | priority {priority}"
        f" | status {status}"
        f" | primary <code>{primary}</code>{detail}{command}</li>"
    )


def render_review_center_concept_item(item: dict[str, Any]) -> str:
    slug = html.escape(str(item.get("slug") or ""))
    title = html.escape(str(item.get("title") or slug))
    issues = html.escape(", ".join(item.get("issues", [])) or "none")
    return (
        f'<li><a href="../../wiki/concepts/{slug}.md">{title}</a>'
        f" | issues {issues}"
        f" | sources {int(item.get('source_count', 0))}</li>"
    )


def render_review_center_rewrite_item(item: dict[str, Any]) -> str:
    slug = html.escape(str(item.get("slug") or ""))
    title = html.escape(str(item.get("title") or slug))
    status = html.escape(display_rewrite_proposal_status(str(item.get("status") or "proposed")))
    return (
        f'<li><a href="../../wiki/rewrite-proposals/{slug}.md">{title}</a>'
        f" | status {status}"
        f" | apply_ready {html.escape(str(bool(item.get('apply_ready'))).lower())}</li>"
    )


def render_review_center_review_action_item(action: dict[str, Any]) -> str:
    command = html.escape(str(action.get("review_command") or ""))
    return (
        f'<li><a href="../../{html.escape(str(action.get("page_path") or ""))}">'
        f"{html.escape(str(action.get('title') or 'review action'))}</a>"
        f" | priority {html.escape(str(action.get('priority') or 'medium'))}"
        f" | reasons {html.escape(', '.join(action.get('reason_codes', [])) or 'none')}"
        f"{f' | command <code>{command}</code>' if command else ''}</li>"
    )


def render_review_center_lifecycle_item(entry: dict[str, Any]) -> str:
    path = str(entry.get("path") or "")
    kind = str(entry.get("kind") or "")
    title = html.escape(str(entry.get("title") or entry.get("page_id") or "unknown"))
    state = html.escape(display_knowledge_lifecycle_state(str(entry.get("lifecycle_state") or "")))
    judgment_state = ""
    if kind in {"decision", "judgment"} and str(entry.get("judgment_lifecycle_state") or ""):
        judgment_state = " | judgment " + html.escape(
            display_judgment_lifecycle_state(str(entry.get("judgment_lifecycle_state") or ""))
        )
    override = ""
    if bool(entry.get("override_active")):
        override = (
            f" | override {html.escape(str(entry.get('override_state') or entry.get('lifecycle_state') or 'unknown'))}"
        )
    invalidation_signals = entry.get("invalidation_signals", [])
    invalidation = ""
    if isinstance(invalidation_signals, list) and invalidation_signals:
        invalidation = f" | invalidation {html.escape(', '.join(str(item) for item in invalidation_signals[:3]))}"
    active_corpus_ids = entry.get("active_corpus_ids", [])
    active_corpora = ""
    if isinstance(active_corpus_ids, list) and active_corpus_ids:
        active_corpora = f" | active corpora {html.escape(str(len(active_corpus_ids)))}"
    if path:
        return (
            f'<li><a href="../../{html.escape(path)}">{title}</a>'
            f" | state {state}{judgment_state}{override}{invalidation}{active_corpora}</li>"
        )
    return f"<li>{title} | state {state}{judgment_state}{override}{invalidation}{active_corpora}</li>"


def render_review_center_html(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    judgment_review_actions = health.get("judgment_review_actions", [])
    pending_items = queue.get("pending_decisions", []) + queue.get("pending_judgments", [])
    ready_actions = plan.get("ready_actions", [])
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    rewrite_candidates = concept_quality.get("rewrite_candidates", [])
    conflict_signals = concept_quality.get("conflict_signals", [])
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]
    judgment_lifecycle_focus = lifecycle_summary.get("under_review_judgments", []) + lifecycle_summary.get(
        "revised_judgments", []
    )

    pending_list = (
        "".join(render_review_center_page_item(page) for page in pending_items[:12]) or "<li>当前没有待审项目。</li>"
    )
    overdue_list = (
        "".join(render_review_center_page_item(page) for page in aging.get("overdue", [])[:10])
        or "<li>当前没有已到期待复审页面。</li>"
    )
    escalated_list = (
        "".join(render_review_center_page_item(page) for page in aging.get("escalated", [])[:10])
        or "<li>当前没有需要升级处理的页面。</li>"
    )
    lifecycle_backlog_list = (
        "".join(
            render_review_center_lifecycle_item(entry) for entry in lifecycle_summary.get("concept_backlog", [])[:10]
        )
        or "<li>当前没有 lifecycle concept backlog。</li>"
    )
    retired_concept_list = (
        "".join(
            render_review_center_lifecycle_item(entry) for entry in lifecycle_summary.get("retired_concepts", [])[:10]
        )
        or "<li>当前没有 retired concept。</li>"
    )
    ready_action_list = (
        "".join(render_review_center_action_item(action) for action in ready_actions[:10])
        or "<li>当前没有 ready repair action。</li>"
    )
    apply_ready_action_list = (
        "".join(render_review_center_action_item(action) for action in apply_ready_actions[:8])
        or "<li>当前没有可直接 semi-auto apply 的低风险动作。</li>"
    )
    rewrite_list = (
        "".join(render_review_center_concept_item(item) for item in rewrite_candidates[:10])
        or "<li>当前没有高优先级弱概念页。</li>"
    )
    conflict_list = (
        "".join(render_review_center_concept_item(item) for item in conflict_signals[:10])
        or "<li>当前没有显式概念冲突信号。</li>"
    )
    rewrite_proposal_list = (
        "".join(render_review_center_rewrite_item(item) for item in rewrite_proposals[:10])
        or "<li>当前没有 rewrite proposal。</li>"
    )
    judgment_action_list = (
        "".join(render_review_center_review_action_item(action) for action in judgment_review_actions[:10])
        or "<li>当前没有 judgment review action。</li>"
    )
    judgment_lifecycle_list = (
        "".join(render_review_center_lifecycle_item(entry) for entry in judgment_lifecycle_focus[:10])
        or "<li>当前没有 judgment lifecycle 焦点。</li>"
    )

    summary_cards = [
        ("待审项目", str(len(pending_items))),
        ("已到期复审", str(len(aging.get("overdue", [])))),
        ("升级项", str(len(aging.get("escalated", [])))),
        ("Judgment 复审中", str(lifecycle_summary.get("counts", {}).get("under_review_judgments", 0))),
        ("Judgment 修订态", str(lifecycle_summary.get("counts", {}).get("revised_judgments", 0))),
        ("生命周期待审", str(lifecycle_summary.get("counts", {}).get("concept_backlog", 0))),
        ("已退役概念", str(lifecycle_summary.get("counts", {}).get("retired_concepts", 0))),
        ("证据漂移", str(sum(1 for page in decisions + judgments if page.get("citation_drift") == "true"))),
        ("Judgment Actions", str(len(judgment_review_actions))),
        ("ready actions", str(plan.get("counts", {}).get("ready", 0))),
        ("重写候选", str(concept_quality.get("counts", {}).get("rewrite_candidates", 0))),
        ("冲突信号", str(concept_quality.get("counts", {}).get("conflict_signals", 0))),
        ("rewrite 提案", str(rewrite_state.get("counts", {}).get("active", 0))),
        ("可应用 rewrite", str(len(apply_ready_rewrites))),
        ("可应用动作", str(len(apply_ready_actions))),
    ]

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            html_meta_theme(),
            "  <title>Review Center</title>",
            "  <style>",
            html_theme_css(),
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="panel">',
            "    <h1>Review Center</h1>",
            f"    <p>编译时间：<code>{html.escape(compiled_at)}</code>。当前协议焦点：<code>{html.escape(active_protocol)}</code>。这是炼丹炉的人用审阅 cockpit：把 review、aging、repair 和 concept rewrite 收在一个地方。</p>",
            '    <div class="meta">',
            *[
                f'      <div class="card"><div class="metric">{html.escape(value)}</div><div class="metric-label">{html.escape(label)}</div></div>'
                for label, value in summary_cards
            ],
            "    </div>",
            "  </section>",
            '  <section class="lists">',
            '    <div class="panel"><h2>待审项目</h2><ul>',
            f"{pending_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>已到期 / 需升级</h2><ul>',
            f"{overdue_list}",
            f"{escalated_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Judgment Lifecycle Focus</h2><ul>',
            f"{judgment_lifecycle_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Judgment Review Actions</h2><ul>',
            f"{judgment_action_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>生命周期概念待审</h2><ul>',
            f"{lifecycle_backlog_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>已退役概念</h2><ul>',
            f"{retired_concept_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Ready Repair Actions</h2><ul>',
            f"{ready_action_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Safe Apply Actions</h2><ul>',
            f"{apply_ready_action_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>概念重写优先级</h2><ul>',
            f"{rewrite_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>概念冲突信号</h2><ul>',
            f"{conflict_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Rewrite Proposals</h2><ul>',
            f"{rewrite_proposal_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>相关入口</h2><ul>',
            '      <li><a href="../../wiki/indexes/furnace-center.md">炉心面板</a></li>',
            '      <li><a href="../../wiki/indexes/review-center.md">Review Center Dashboard</a></li>',
            '      <li><a href="../../wiki/indexes/review-queue.md">审阅队列</a></li>',
            '      <li><a href="../../wiki/indexes/aging-report.md">Aging 报告</a></li>',
            '      <li><a href="../../wiki/indexes/cognitive-history.md">认知历史</a></li>',
            '      <li><a href="../../wiki/indexes/machine-memory-actions.md">机器记忆动作队列</a></li>',
            '      <li><a href="../../wiki/indexes/machine-memory-repair-plan.md">机器记忆修复计划</a></li>',
            '      <li><a href="../../wiki/indexes/judgment-assets.md">判断资产</a></li>',
            '      <li><a href="../../wiki/indexes/concept-quality.md">概念质量</a></li>',
            '      <li><a href="../../wiki/indexes/rewrite-proposals.md">Rewrite Proposals</a></li>',
            "    </ul></div>",
            "  </section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )
