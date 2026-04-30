"""Execution center / audit + concept quality / rewrite proposal renderers.

EP-017B step 4: extracted from ``aiwiki.app_memory_surfaces``. Contains 12
public renderers that emit the execution-center Markdown/HTML pages, the
execution-audit pages, the concept-quality index, and the concept-rewrite
reconciliation + page/index renderers. Imports are scoped to the minimal
set actually used by these 12 functions; no sibling ``aiwiki.memory.*``
imports are required.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from ..app_content import (
    action_priority_rank,
    action_supports_low_risk_apply,
    display_action_status,
    display_rewrite_proposal_status,
    execution_band_label,
    execution_policy_profile,
    load_execution_policy_decision_history,
    load_execution_receipt_history,
    rewrite_proposal_is_apply_ready,
    rewrite_proposal_needs_review,
    rewrite_proposal_status_rank,
    safe_apply_preview,
)
from ..app_memory_query import concept_page_snapshot, recent_execution_dry_runs
from ..app_protocol import (
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    PENDING_ACTION_STATUSES,
    REWRITE_PROPOSAL_STATUSES,
    protocol_title,
)
from ..app_state import (
    DEFAULT_PROTOCOL,
    concept_rewrite_proposal_page_path,
    concept_rewrite_state_path,
    execution_policy_log_path,
    execution_receipt_history_path,
    load_concept_rewrite_state,
    load_manual_link_state,
    save_concept_rewrite_state,
)
from ..app_utils import (
    parse_frontmatter,
    relative_path,
    render_frontmatter,
    sha256_bytes,
    slugify,
)


def render_execution_proposal_page(proposal: dict[str, Any], *, compiled_at: str) -> str:
    frontmatter = render_frontmatter(
        {
            "title": str(proposal.get("title") or proposal.get("action_id") or "Execution Proposal"),
            "kind": "execution-proposal",
            "status": str(proposal.get("status") or "proposed"),
            "action_id": str(proposal.get("action_id") or ""),
            "proposal_kind": str(proposal.get("proposal_kind") or "manual-repair"),
            "risk": str(proposal.get("risk") or "medium"),
            "priority": str(proposal.get("priority") or "medium"),
            "protocol": str(proposal.get("protocol") or DEFAULT_PROTOCOL),
            "policy_decision": str(proposal.get("policy_decision") or ""),
            "policy_rule_id": str(proposal.get("policy_rule_id") or ""),
            "priority_score": int(proposal.get("priority_score", 0) or 0),
            "impact_score": int(proposal.get("impact_score", 0) or 0),
            "target_paths": list(proposal.get("target_paths", [])),
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
        }
    )
    lines = [
        f"# {proposal.get('title') or proposal.get('action_id')}",
        "",
        "## Overview",
        f"- Action id: `{proposal.get('action_id', '')}`",
        f"- Status: `{display_action_status(str(proposal.get('status') or 'proposed'))}`",
        f"- Kind: `{proposal.get('proposal_kind', 'manual-repair')}`",
        f"- Risk: `{proposal.get('risk', 'medium')}`",
        f"- Protocol: `{proposal.get('protocol', DEFAULT_PROTOCOL)}`",
        f"- Priority: `{proposal.get('priority', 'medium')}`",
        f"- Priority score: `{proposal.get('priority_score', 0)}`",
        f"- Impact score: `{proposal.get('impact_score', 0)}`",
        f"- Policy decision: `{proposal.get('policy_decision', '') or 'none'}`",
        f"- Policy rule: `{proposal.get('policy_rule_id', '') or 'none'}`",
        f"- Targets: `{', '.join(proposal.get('target_paths', [])) or 'none'}`",
        f"- Bundle: `{proposal.get('bundle_path', '') or 'none'}`",
        "",
        "## Strategy",
        f"- {proposal.get('summary', 'n/a')}",
        f"- Rollback: {proposal.get('rollback_summary', 'n/a')}",
        "",
        "## Suggested Edits",
    ]
    edits = proposal.get("suggested_edits", [])
    if not edits:
        lines.append("- 当前没有额外建议。")
    else:
        lines.extend(f"- {edit}" for edit in edits)
    lines.extend(["", "## Page-Level Patch Plan"])
    patch_plan = proposal.get("page_patch_plan", [])
    if not patch_plan:
        lines.append("- 当前没有页级 patch step。")
    else:
        for patch in patch_plan:
            sections = ", ".join(patch.get("sections", [])) or "none"
            lines.append(
                f"- `{patch.get('path', '')}`"
                f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                f" | mode `{patch.get('mode', 'update')}`"
                f" | exists `{patch.get('exists', False)}`"
                f" | sections `{sections}`"
            )
            lines.append(f"  - {patch.get('summary', '检查相关页面并补充修复说明。')}")
    lines.extend(["", "## Commands"])
    if proposal.get("bundle_path"):
        lines.append(
            f"- Suggested apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {proposal.get('action_id', '')} --bundle {proposal.get('bundle_path', '')}`"
        )
    if proposal.get("command_hint"):
        lines.append(f"- Suggested next step: `{proposal['command_hint']}`")
    else:
        lines.append("- 当前没有直接命令提示。")
    safe_preview = proposal.get("safe_apply_preview")
    lines.extend(["", "## Safe Apply Preview"])
    if not safe_preview:
        lines.append("- 当前 proposal 不支持低风险 safe apply。")
    else:
        entry = safe_preview.get("entry", {})
        lines.append(f"- Apply mode: `{safe_preview.get('apply_mode', 'manual')}`")
        if safe_preview.get("state_path"):
            lines.append(f"- State path: `{safe_preview.get('state_path', '')}`")
        if entry:
            lines.append(
                f"- Manual link entry: source `{entry.get('source_id', '')}` -> concept `{entry.get('concept_slug', '')}`"
            )
        if safe_preview.get("page_path"):
            lines.append(f"- Target page: `{safe_preview.get('page_path', '')}`")
        if safe_preview.get("updated_citation_snapshots"):
            lines.append(
                f"- Updated citation snapshots: `{', '.join(safe_preview.get('updated_citation_snapshots', []))}`"
            )
        lines.append(f"- Affected paths: `{', '.join(safe_preview.get('affected_paths', [])) or 'none'}`")
        lines.append(f"- Follow-up: {safe_preview.get('follow_up', 'n/a')}")
    lines.extend(
        [
            "",
            "## Related Links",
            "- [执行中心](../indexes/execution-center.md)",
            "- [机器记忆修复计划](../indexes/machine-memory-repair-plan.md)",
            "- [机器记忆动作队列](../indexes/machine-memory-actions.md)",
            "- [炉心面板](../indexes/furnace-center.md)",
            f"- [Execution Bundle](../../{proposal.get('bundle_path', '')})" if proposal.get("bundle_path") else "- Execution Bundle: none",
        ]
    )
    return f"{frontmatter}\n\n" + "\n".join(lines).strip() + "\n"


def render_execution_center(root: Path, memory: dict[str, Any], *, compiled_at: str, active_protocol: str) -> str:
    plan = memory.get("health", {}).get("repair_plan", {})
    proposals = plan.get("execution_proposals", [])
    ready_actions = plan.get("ready_actions", [])
    all_actions = [*memory.get("health", {}).get("actions", []), *memory.get("health", {}).get("inactive_actions", [])]
    recent_receipts = sorted(
        [
            action
            for action in all_actions
            if action.get("last_receipt_path")
        ],
        key=lambda item: str(item.get("status_updated_at") or item.get("reviewed_at") or ""),
        reverse=True,
    )
    recent_dry_runs = recent_execution_dry_runs(root, limit=8)
    revert_ready_actions = [
        action for action in recent_receipts if str(action.get("status") or "") == "resolved"
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in proposals)
    lines = [
        "# 执行中心",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- Ready actions：`{plan.get('counts', {}).get('ready', 0)}`",
        f"- 可安全执行动作：`{len(apply_ready_actions)}`",
        f"- Execution proposals：`{plan.get('counts', {}).get('proposals', 0)}`",
        f"- Page-level patch steps：`{patch_steps}`",
        "- 本地执行面板：`output/control/execution-center.html`",
        "",
        "## Safe Apply Now",
    ]
    if not apply_ready_actions:
        lines.append("- 当前没有可直接 `apply-action` 的低风险动作。")
    else:
        for action in apply_ready_actions[:10]:
            lines.append(
                f"- `{action['title']}` | band `{action.get('execution_band', 'bundle-safe-apply')}` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action.get('id', '')} --bundle output/control/execution-bundles/{slugify(str(action.get('id') or ''))}.json` | primary `{action.get('primary_path', '')}`"
            )
    lines.extend(["", "## Revert Safe Apply"])
    if not revert_ready_actions:
        lines.append("- 当前没有可回滚的 safe apply。")
    else:
        for action in revert_ready_actions[:10]:
            lines.append(
                f"- `{action['title']}` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {action.get('id', '')}` | receipt `{action.get('last_receipt_path', '')}`"
            )
    lines.extend(["", "## Execution Proposals"])
    if not proposals:
        lines.append("- 当前没有 execution proposal。")
    else:
        for proposal in proposals[:12]:
            lines.append(
                f"- [{proposal['title']}](../execution-proposals/{slugify(str(proposal.get('action_id') or ''))}.md)"
                f" | risk `{proposal.get('risk', 'medium')}`"
                f" | patch `{len(proposal.get('page_patch_plan', []))}`"
                f" | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
                f" | bundle `{proposal.get('bundle_path', '') or 'none'}`"
            )
    lines.extend(["", "## Recent Receipts"])
    if not recent_receipts:
        lines.append("- 当前还没有 safe execution receipt。")
    else:
        for action in recent_receipts[:8]:
            lines.append(
                f"- `{action['title']}`"
                f" | receipt `{action.get('last_receipt_path', '')}`"
                f" | updated `{action.get('status_updated_at', '') or action.get('reviewed_at', '') or 'none'}`"
            )
    lines.extend(["", "## Recent Dry Runs"])
    if not recent_dry_runs:
        lines.append("- 当前还没有 dry-run 历史。")
    else:
        for dry_run in recent_dry_runs:
            lines.append(
                f"- `{dry_run['title']}`"
                f" | mode `{dry_run.get('apply_mode', '') or dry_run.get('event_type', 'dry-run')}`"
                f" | preview `{dry_run.get('preview_path', '') or 'none'}`"
                f" | bundle `{dry_run.get('bundle_path', '') or 'none'}`"
                f" | updated `{dry_run.get('occurred_at', '') or 'none'}`"
            )
            if dry_run.get("affected_paths"):
                lines.append(
                    "  - affected: `"
                    + ", ".join(str(path) for path in dry_run.get("affected_paths", [])[:3])
                    + "`"
                )
    lines.extend(
        [
            "",
            "## Quick Links",
            "- [机器记忆修复计划](./machine-memory-repair-plan.md)",
            "- [机器记忆动作队列](./machine-memory-actions.md)",
            "- [执行审计](./execution-audit.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [审阅中心](./review-center.md)",
            "- [炉心面板](./furnace-center.md)",
            "- `output/control/execution-center.html`：本地执行面板（浏览器 / 系统 HTML 入口）",
            "- `output/control/execution-audit.html`：本地执行审计面板（浏览器 / 系统 HTML 入口）",
        ]
    )
    return "\n".join(lines) + "\n"


def render_execution_center_html(root: Path, memory: dict[str, Any], *, compiled_at: str, active_protocol: str) -> str:
    plan = memory.get("health", {}).get("repair_plan", {})
    proposals = plan.get("execution_proposals", [])
    ready_actions = plan.get("ready_actions", [])
    all_actions = [*memory.get("health", {}).get("actions", []), *memory.get("health", {}).get("inactive_actions", [])]
    recent_receipts = sorted(
        [
            action
            for action in all_actions
            if action.get("last_receipt_path")
        ],
        key=lambda item: str(item.get("status_updated_at") or item.get("reviewed_at") or ""),
        reverse=True,
    )
    recent_dry_runs = recent_execution_dry_runs(root, limit=8)
    revert_ready_actions = [
        action for action in recent_receipts if str(action.get("status") or "") == "resolved"
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in proposals)
    summary_cards = [
        ("Ready Actions", str(plan.get("counts", {}).get("ready", 0))),
        ("Safe Apply", str(len(apply_ready_actions))),
        ("Proposals", str(plan.get("counts", {}).get("proposals", 0))),
        ("Patch Steps", str(patch_steps)),
    ]
    safe_apply_markup = "".join(
        f"<li><strong>{html.escape(str(action.get('title') or 'unnamed action'))}</strong>"
        f"<div><code>{html.escape(str(action.get('command_hint') or ''))}</code></div>"
        f"<div class=\"item-meta\">{html.escape(str(action.get('primary_path') or ''))}</div></li>"
        for action in apply_ready_actions[:8]
    ) or "<li>当前没有可直接 safe apply 的动作。</li>"
    revert_markup = "".join(
        f"<li><strong>{html.escape(str(action.get('title') or 'unnamed action'))}</strong>"
        f"<div><code>PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {html.escape(str(action.get('id') or ''))}</code></div>"
        f"<div class=\"item-meta\">{html.escape(str(action.get('last_receipt_path') or ''))}</div></li>"
        for action in revert_ready_actions[:8]
    ) or "<li>当前没有可回滚的 safe apply。</li>"
    proposal_markup = "".join(
        f"<li><strong><a href=\"../../wiki/execution-proposals/{html.escape(slugify(str(proposal.get('action_id') or '')))}.md\">{html.escape(str(proposal.get('title') or 'proposal'))}</a></strong>"
        f" <span class=\"item-meta\">risk {html.escape(str(proposal.get('risk') or 'medium'))} / patch {len(proposal.get('page_patch_plan', []))}</span>"
        f"<div>{html.escape(str(proposal.get('summary') or ''))}</div>"
        f"<div class=\"item-meta\"><a href=\"../../{html.escape(str(proposal.get('bundle_path') or ''))}\">Execution Bundle</a></div></li>"
        for proposal in proposals[:10]
    ) or "<li>当前没有 execution proposal。</li>"
    receipt_markup = "".join(
        f"<li><strong>{html.escape(str(action.get('title') or 'unnamed action'))}</strong>"
        f"<div class=\"item-meta\"><a href=\"../../{html.escape(str(action.get('last_receipt_path') or ''))}\">Execution Receipt</a></div></li>"
        for action in recent_receipts[:8]
    ) or "<li>当前还没有 safe execution receipt。</li>"
    dry_run_markup = "".join(
        f"<li><strong>{html.escape(str(item.get('title') or 'dry run'))}</strong>"
        f"<div class=\"item-meta\">mode {html.escape(str(item.get('apply_mode') or item.get('event_type') or 'dry-run'))}</div>"
        f"<div class=\"item-meta\"><a href=\"../../{html.escape(str(item.get('preview_path') or ''))}\">Dry Run Preview</a></div>"
        f"<div class=\"item-meta\"><a href=\"../../{html.escape(str(item.get('bundle_path') or ''))}\">Execution Bundle</a></div></li>"
        for item in recent_dry_runs[:8]
    ) or "<li>当前还没有 dry-run 历史。</li>"
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Execution Center</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f8fafc; --ink: #0f172a; --muted: #475569; --panel: rgba(255,255,255,0.94); --line: #cbd5e1; }",
            "    body { margin: 0; padding: 24px; background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1100px; margin: 0 auto; }",
            "    .panel, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .panel { padding: 18px; margin-bottom: 18px; }",
            "    .meta, .grid { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin-top: 18px; }",
            "    .grid { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #1d4ed8; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 6px 0; }",
            "    a { color: #1d4ed8; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    .item-meta { color: var(--muted); font-size: 12px; }",
            "    code { background: #eff6ff; padding: 1px 6px; border-radius: 6px; }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="panel">',
            "    <h1>Execution Center</h1>",
            f"    <p>编译时间：<code>{html.escape(compiled_at)}</code>。当前协议：<code>{html.escape(active_protocol)}</code>。这里把 safe apply、execution proposal 和 patch-step 执行工作区收敛到一个地方。</p>",
            '    <div class="meta">',
            *[
                f'      <div class="card"><div class="metric">{html.escape(value)}</div><div class="metric-label">{html.escape(label)}</div></div>'
                for label, value in summary_cards
            ],
            "    </div>",
            "  </section>",
            '  <section class="grid">',
            f'    <div class="panel"><h2>Safe Apply Actions</h2><ul>{safe_apply_markup}</ul></div>',
            f'    <div class="panel"><h2>Revert Safe Apply</h2><ul>{revert_markup}</ul></div>',
            f'    <div class="panel"><h2>Execution Proposals</h2><ul>{proposal_markup}</ul></div>',
            f'    <div class="panel"><h2>Recent Receipts</h2><ul>{receipt_markup}</ul></div>',
            f'    <div class="panel"><h2>Recent Dry Runs</h2><ul>{dry_run_markup}</ul></div>',
            '    <div class="panel"><h2>相关入口</h2><ul>'
            '      <li><a href="../../wiki/indexes/execution-center.md">Markdown 执行中心</a></li>'
            '      <li><a href="../../wiki/indexes/execution-audit.md">执行审计</a></li>'
            '      <li><a href="../../wiki/indexes/machine-memory-repair-plan.md">修复计划</a></li>'
            '      <li><a href="../../wiki/indexes/machine-memory-actions.md">动作队列</a></li>'
            '      <li><a href="../../wiki/indexes/review-center.md">审阅中心</a></li>'
            '      <li><a href="../../wiki/indexes/furnace-center.md">炉心面板</a></li>'
            '      <li><a href="../../output/control/execution-audit.html">审计 HTML</a></li>'
            "    </ul></div>",
            "  </section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def collect_execution_consistency_signals(
    root: Path,
    actions: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> list[dict[str, str]]:
    manual_state = load_manual_link_state(root)
    active_manual_links: dict[str, list[dict[str, Any]]] = {}
    for item in manual_state.get("source_to_concept", []):
        if not isinstance(item, dict) or not bool(item.get("active", True)):
            continue
        origin_action_id = str(item.get("origin_action_id") or "")
        if not origin_action_id:
            continue
        active_manual_links.setdefault(origin_action_id, []).append(item)
    latest_receipt_by_action: dict[str, dict[str, Any]] = {}
    for record in history:
        action_id = str(record.get("action_id") or "")
        if action_id and action_id not in latest_receipt_by_action:
            latest_receipt_by_action[action_id] = record

    signals: list[dict[str, str]] = []
    for action in actions:
        action_id = str(action.get("id") or "")
        if not action_id:
            continue
        status = str(action.get("status") or "proposed")
        latest = latest_receipt_by_action.get(action_id)
        latest_operation = str(latest.get("operation") or "") if latest else ""
        latest_preview = latest.get("safe_apply_preview") if isinstance(latest, dict) else None
        if isinstance(latest_preview, dict):
            preview = latest_preview
        elif str(action.get("kind") or "") in LOW_RISK_APPLYABLE_ACTION_KINDS:
            preview = {"apply_mode": "manual-link-state"}
        else:
            preview = safe_apply_preview(root, action)
        if not isinstance(preview, dict):
            continue
        apply_mode = str(preview.get("apply_mode") or "")
        has_active_manual_link = bool(active_manual_links.get(action_id))
        title = str(action.get("title") or action_id)
        primary_path = str(action.get("primary_path") or "")

        if status == "resolved" and latest_operation != "apply" and apply_mode in {
            "manual-link-state",
            "citation-snapshot-refresh",
        }:
            signals.append(
                {
                    "severity": "error",
                    "action_id": action_id,
                    "title": title,
                    "path": primary_path,
                    "message": "动作标记为 resolved，但最新 execution receipt 不是 apply。",
                }
            )
        if apply_mode == "manual-link-state":
            if status == "resolved" and not has_active_manual_link:
                signals.append(
                    {
                        "severity": "error",
                        "action_id": action_id,
                        "title": title,
                        "path": primary_path,
                        "message": "动作标记为 resolved，但 active manual-link state 缺失。",
                    }
                )
            if latest_operation == "revert" and has_active_manual_link:
                signals.append(
                    {
                        "severity": "error",
                        "action_id": action_id,
                        "title": title,
                        "path": primary_path,
                        "message": "最新 receipt 已是 revert，但 manual-link state 仍然 active。",
                    }
                )
            if status in PENDING_ACTION_STATUSES and has_active_manual_link:
                signals.append(
                    {
                        "severity": "warn",
                        "action_id": action_id,
                        "title": title,
                        "path": primary_path,
                        "message": "动作仍在待处理状态，但 manual-link state 仍然 active；需要确认是否应先 revert 或直接 resolve。",
                    }
                )
            continue
        if apply_mode != "citation-snapshot-refresh":
            continue
        page_path = str(preview.get("page_path") or primary_path)
        current_snapshots: list[str] = []
        if page_path and (root / page_path).exists():
            frontmatter = parse_frontmatter((root / page_path).read_text(encoding="utf-8", errors="replace"))
            current_snapshots = [
                str(item)
                for item in frontmatter.get("citation_snapshots", [])
                if isinstance(item, str) and item.strip()
            ]
        expected_snapshots = [
            str(item)
            for item in preview.get("updated_citation_snapshots", [])
            if isinstance(item, str) and item.strip()
        ]
        previous_snapshots = [
            str(item)
            for item in preview.get("previous_citation_snapshots", [])
            if isinstance(item, str) and item.strip()
        ]
        if status == "resolved" and expected_snapshots and current_snapshots != expected_snapshots:
            signals.append(
                {
                    "severity": "error",
                    "action_id": action_id,
                    "title": title,
                    "path": page_path,
                    "message": "动作标记为 resolved，但当前 judgment page 的 citation_snapshots 与 apply receipt 不一致。",
                }
            )
        if latest_operation == "revert" and expected_snapshots and current_snapshots == expected_snapshots:
            signals.append(
                {
                    "severity": "error",
                    "action_id": action_id,
                    "title": title,
                    "path": page_path,
                    "message": "最新 receipt 已是 revert，但 judgment page 仍保留 apply 后的 citation_snapshots。",
                }
            )
        if latest_operation == "revert" and previous_snapshots and current_snapshots != previous_snapshots:
            signals.append(
                {
                    "severity": "warn",
                    "action_id": action_id,
                    "title": title,
                    "path": page_path,
                    "message": "最新 receipt 已是 revert，但 judgment page 的 citation_snapshots 没有恢复到 receipt 里的 previous state。",
                }
            )
        if status in PENDING_ACTION_STATUSES and expected_snapshots and current_snapshots == expected_snapshots:
            signals.append(
                {
                    "severity": "warn",
                    "action_id": action_id,
                    "title": title,
                    "path": page_path,
                    "message": "动作仍在待处理状态，但 judgment page 已经处于 apply 后的 citation_snapshots；需要确认是否应先 revert 或直接 resolve。",
                }
            )
    signals.sort(
        key=lambda item: (
            0 if item.get("severity") == "error" else 1,
            str(item.get("title") or "").lower(),
            str(item.get("message") or ""),
        )
    )
    return signals


def build_execution_audit_snapshot(root: Path, memory: dict[str, Any], *, active_protocol: str) -> dict[str, Any]:
    health = memory.get("health", {})
    actions = [dict(action) for action in health.get("actions", []) if isinstance(action, dict)]
    inactive_actions = [dict(action) for action in health.get("inactive_actions", []) if isinstance(action, dict)]
    all_actions = actions + inactive_actions
    history = load_execution_receipt_history(root)
    policy_history = load_execution_policy_decision_history(root, limit=16)
    recent_apply = [record for record in history if str(record.get("operation") or "") == "apply"][:8]
    recent_revert = [record for record in history if str(record.get("operation") or "") == "revert"][:8]
    recent_by_protocol: dict[str, dict[str, list[dict[str, Any]]]] = {
        "recent_apply": {},
        "recent_revert": {},
    }
    band_counts: dict[str, int] = {}
    protocol_counts: dict[str, int] = {}
    receipt_counts: dict[str, int] = {}
    for record in history:
        protocol = str(record.get("protocol") or DEFAULT_PROTOCOL)
        protocol_counts[protocol] = protocol_counts.get(protocol, 0) + 1
        action_id = str(record.get("action_id") or "")
        if action_id:
            receipt_counts[action_id] = receipt_counts.get(action_id, 0) + 1
        operation = str(record.get("operation") or "")
        if operation in {"apply", "revert"}:
            bucket_name = "recent_apply" if operation == "apply" else "recent_revert"
            scoped = recent_by_protocol[bucket_name].setdefault(protocol, [])
            if len(scoped) < 8:
                scoped.append(record)
    action_rows: list[dict[str, Any]] = []
    for action in all_actions:
        profile = execution_policy_profile(action, root=root)
        band = str(action.get("execution_band") or profile.get("execution_band") or "review-first")
        band_counts[band] = band_counts.get(band, 0) + 1
        action_id = str(action.get("id") or "")
        capabilities = action.get("execution_capability_list")
        if not isinstance(capabilities, list):
            capabilities = list(profile.get("capabilities") or [])
        action_rows.append(
            {
                "id": action_id,
                "title": str(action.get("title") or action_id),
                "status": display_action_status(str(action.get("status") or "proposed")),
                "execution_band": band,
                "execution_band_label": execution_band_label(band),
                "execution_policy": str(action.get("execution_policy") or profile.get("execution_policy") or "triage"),
                "policy_decision": str(action.get("policy_decision") or profile.get("policy_decision") or ""),
                "policy_rule_id": str(action.get("policy_rule_id") or profile.get("policy_rule_id") or ""),
                "execution_capabilities": [str(item) for item in capabilities if isinstance(item, str) and item],
                "policy_summary": str(action.get("policy_summary") or profile.get("policy_summary") or ""),
                "receipt_count": receipt_counts.get(action_id, 0),
                "last_receipt_path": str(action.get("last_receipt_path") or ""),
                "primary_path": str(action.get("primary_path") or ""),
            }
        )
    action_rows.sort(
        key=lambda item: (
            0 if item.get("execution_band") == "bundle-safe-apply" else 1,
            0 if item.get("status") == display_action_status("accepted") else 1,
            str(item.get("title") or "").lower(),
        )
    )
    band_rows = [
        {"band": band, "label": execution_band_label(band), "count": band_counts.get(band, 0)}
        for band in ("bundle-safe-apply", "review-first", "manual-repair", "deferred", "closed", "history-only")
        if band_counts.get(band, 0)
    ]
    protocol_rows = [
        {"protocol": protocol, "title": protocol_title(protocol), "count": count}
        for protocol, count in sorted(protocol_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    consistency_signals = collect_execution_consistency_signals(root, all_actions, history)
    return {
        "compiled_at": str(memory.get("compiled_at") or ""),
        "active_protocol": active_protocol,
        "receipt_history_path": relative_path(root, execution_receipt_history_path(root)),
        "policy_history_path": relative_path(root, execution_policy_log_path(root)),
        "counts": {
            "actions": len(all_actions),
            "receipts": len(history),
            "apply": len([record for record in history if str(record.get("operation") or "") == "apply"]),
            "revert": len([record for record in history if str(record.get("operation") or "") == "revert"]),
            "bundle_safe": band_counts.get("bundle-safe-apply", 0),
            "policy_decisions": len(policy_history),
        },
        "policy_bands": band_rows,
        "protocols": protocol_rows,
        "recent_policy_decisions": policy_history,
        "recent_apply": recent_apply,
        "recent_revert": recent_revert,
        "recent_by_protocol": recent_by_protocol,
        "actions": action_rows[:16],
        "consistency_signals": consistency_signals[:16],
        "consistency_counts": {
            "errors": sum(1 for item in consistency_signals if item.get("severity") == "error"),
            "warns": sum(1 for item in consistency_signals if item.get("severity") == "warn"),
        },
    }


def render_execution_audit(audit: dict[str, Any]) -> str:
    lines = [
        "# 执行审计",
        "",
        f"- 最近编译时间：`{audit.get('compiled_at', '')}`",
        f"- 当前协议：`{audit.get('active_protocol', DEFAULT_PROTOCOL)}` ({protocol_title(str(audit.get('active_protocol') or DEFAULT_PROTOCOL))})",
        f"- 动作总数：`{audit.get('counts', {}).get('actions', 0)}`",
        f"- Receipt 总数：`{audit.get('counts', {}).get('receipts', 0)}`",
        f"- Apply / Revert：`{audit.get('counts', {}).get('apply', 0)}` / `{audit.get('counts', {}).get('revert', 0)}`",
        f"- Bundle-safe actions：`{audit.get('counts', {}).get('bundle_safe', 0)}`",
        f"- Policy decisions：`{audit.get('counts', {}).get('policy_decisions', 0)}`",
        f"- Receipt history：`{audit.get('receipt_history_path', '.aiwiki/state/execution-receipts.jsonl')}`",
        f"- Policy history：`{audit.get('policy_history_path', '.aiwiki/state/execution-policy-decisions.jsonl')}`",
        "",
        "## Policy Bands",
    ]
    band_rows = audit.get("policy_bands", [])
    if not band_rows:
        lines.append("- 当前还没有可审计的 execution policy band。")
    else:
        for row in band_rows:
            lines.append(f"- `{row['band']}` | {row['label']} | count `{row['count']}`")
    lines.extend(["", "## Recent Apply"])
    recent_apply = audit.get("recent_apply", [])
    if not recent_apply:
        lines.append("- 当前还没有 apply receipt。")
    else:
        for receipt in recent_apply:
            lines.append(
                f"- `{receipt.get('title', receipt.get('action_id', 'receipt'))}`"
                f" | action `{receipt.get('action_id', '')}`"
                f" | protocol `{receipt.get('protocol', DEFAULT_PROTOCOL)}`"
                f" | applied `{receipt.get('applied_at', '')}`"
            )
    lines.extend(["", "## Recent Revert"])
    recent_revert = audit.get("recent_revert", [])
    if not recent_revert:
        lines.append("- 当前还没有 revert receipt。")
    else:
        for receipt in recent_revert:
            lines.append(
                f"- `{receipt.get('title', receipt.get('action_id', 'receipt'))}`"
                f" | action `{receipt.get('action_id', '')}`"
                f" | protocol `{receipt.get('protocol', DEFAULT_PROTOCOL)}`"
                f" | reverted `{receipt.get('applied_at', '')}`"
            )
    lines.extend(["", "## Protocol Breakdown"])
    protocols = audit.get("protocols", [])
    if not protocols:
        lines.append("- 当前还没有 protocol 级 execution history。")
    else:
        for row in protocols:
            lines.append(f"- `{row['protocol']}` ({row['title']}) | receipts `{row['count']}`")
    lines.extend(["", "## Recent Policy Decisions"])
    recent_policy_decisions = audit.get("recent_policy_decisions", [])
    if not recent_policy_decisions:
        lines.append("- 当前还没有 execution policy decision 记录。")
    else:
        for record in recent_policy_decisions[:8]:
            lines.append(
                f"- `{record.get('title', record.get('action_id', 'action'))}`"
                f" | action `{record.get('action_id', '')}`"
                f" | decision `{record.get('policy_decision', '') or 'none'}`"
                f" | rule `{record.get('policy_rule_id', '') or 'none'}`"
                f" | occurred `{record.get('occurred_at', '')}`"
            )
    lines.extend(["", "## Consistency Signals"])
    consistency_signals = audit.get("consistency_signals", [])
    if not consistency_signals:
        lines.append("- 当前没有 execution consistency signal。")
    else:
        for signal in consistency_signals:
            lines.append(
                f"- [{signal.get('severity', 'warn')}] `{signal.get('title', signal.get('action_id', 'signal'))}`"
                f" | action `{signal.get('action_id', '')}`"
                f" | {signal.get('message', '')}"
            )
    lines.extend(["", "## Action Audit"])
    actions = audit.get("actions", [])
    if not actions:
        lines.append("- 当前还没有 action audit rows。")
    else:
        for action in actions:
            capabilities = ", ".join(action.get("execution_capabilities", [])) or "none"
            lines.append(
                f"- `{action['title']}`"
                f" | status `{action['status']}`"
                f" | band `{action['execution_band']}`"
                f" | policy `{action['execution_policy']}`"
                f" | decision `{action.get('policy_decision', '') or 'none'}`"
                f" | receipts `{action['receipt_count']}`"
            )
            lines.append(f"  - capabilities: {capabilities}")
            lines.append(f"  - summary: {action.get('policy_summary', 'n/a')}")
            if action.get("policy_rule_id"):
                lines.append(f"  - rule: `{action['policy_rule_id']}`")
            if action.get("last_receipt_path"):
                lines.append(f"  - last receipt: `{action['last_receipt_path']}`")
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [执行中心](./execution-center.md)",
            "- [机器记忆修复计划](./machine-memory-repair-plan.md)",
            "- [机器记忆动作队列](./machine-memory-actions.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [炉心面板](./furnace-center.md)",
            "- `output/control/execution-audit.html`：本地执行审计面板（浏览器 / 系统 HTML 入口）",
        ]
    )
    return "\n".join(lines) + "\n"


def render_execution_audit_html(audit: dict[str, Any]) -> str:
    summary_cards = [
        ("Receipts", str(audit.get("counts", {}).get("receipts", 0))),
        ("Apply", str(audit.get("counts", {}).get("apply", 0))),
        ("Revert", str(audit.get("counts", {}).get("revert", 0))),
        ("Bundle Safe", str(audit.get("counts", {}).get("bundle_safe", 0))),
    ]
    band_markup = "".join(
        f"<li><strong>{html.escape(str(row.get('label') or row.get('band') or 'band'))}</strong>"
        f" <span class=\"item-meta\">{html.escape(str(row.get('band') or ''))}</span>"
        f"<div class=\"metric-inline\">count {html.escape(str(row.get('count') or 0))}</div></li>"
        for row in audit.get("policy_bands", [])
    ) or "<li>当前还没有可审计的 execution policy band。</li>"
    apply_markup = "".join(
        f"<li><strong>{html.escape(str(item.get('title') or item.get('action_id') or 'receipt'))}</strong>"
        f"<div class=\"item-meta\">{html.escape(str(item.get('action_id') or ''))} / {html.escape(str(item.get('protocol') or DEFAULT_PROTOCOL))}</div>"
        f"<div>{html.escape(str(item.get('applied_at') or ''))}</div></li>"
        for item in audit.get("recent_apply", [])
    ) or "<li>当前还没有 apply receipt。</li>"
    revert_markup = "".join(
        f"<li><strong>{html.escape(str(item.get('title') or item.get('action_id') or 'receipt'))}</strong>"
        f"<div class=\"item-meta\">{html.escape(str(item.get('action_id') or ''))} / {html.escape(str(item.get('protocol') or DEFAULT_PROTOCOL))}</div>"
        f"<div>{html.escape(str(item.get('applied_at') or ''))}</div></li>"
        for item in audit.get("recent_revert", [])
    ) or "<li>当前还没有 revert receipt。</li>"
    protocol_markup = "".join(
        f"<li><strong>{html.escape(str(row.get('title') or row.get('protocol') or 'protocol'))}</strong>"
        f" <span class=\"item-meta\">{html.escape(str(row.get('protocol') or ''))}</span>"
        f"<div>receipts {html.escape(str(row.get('count') or 0))}</div></li>"
        for row in audit.get("protocols", [])
    ) or "<li>当前还没有 protocol 级 execution history。</li>"
    action_markup = "".join(
        f"<li><strong>{html.escape(str(action.get('title') or action.get('id') or 'action'))}</strong>"
        f"<div class=\"item-meta\">{html.escape(str(action.get('execution_band_label') or action.get('execution_band') or ''))}"
        f" / {html.escape(str(action.get('execution_policy') or 'triage'))}"
        f" / receipts {html.escape(str(action.get('receipt_count') or 0))}</div>"
        f"<div>{html.escape(str(action.get('policy_summary') or ''))}</div></li>"
        for action in audit.get("actions", [])
    ) or "<li>当前还没有 action audit rows。</li>"
    consistency_markup = "".join(
        f"<li><strong>{html.escape(str(signal.get('title') or signal.get('action_id') or 'signal'))}</strong>"
        f" <span class=\"item-meta\">{html.escape(str(signal.get('severity') or 'warn'))}</span>"
        f"<div>{html.escape(str(signal.get('message') or ''))}</div></li>"
        for signal in audit.get("consistency_signals", [])
    ) or "<li>当前没有 execution consistency signal。</li>"
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Execution Audit</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f8fafc; --ink: #0f172a; --muted: #475569; --panel: rgba(255,255,255,0.94); --line: #cbd5e1; }",
            "    body { margin: 0; padding: 24px; background: linear-gradient(180deg, #f8fafc 0%, #ecfeff 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1100px; margin: 0 auto; }",
            "    .panel, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .panel { padding: 18px; margin-bottom: 18px; }",
            "    .meta, .grid { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin-top: 18px; }",
            "    .grid { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #0f766e; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    .metric-inline { color: #0f766e; font-weight: 700; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 6px 0; }",
            "    a { color: #0f766e; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    .item-meta { color: var(--muted); font-size: 12px; }",
            "    code { background: #ecfeff; padding: 1px 6px; border-radius: 6px; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <section class=\"panel\">",
            "      <h1>Execution Audit</h1>",
            f"      <p>当前协议 <strong>{html.escape(str(audit.get('active_protocol') or DEFAULT_PROTOCOL))}</strong> · 最近编译 {html.escape(str(audit.get('compiled_at') or ''))}</p>",
            "      <p><a href=\"../../wiki/indexes/execution-audit.md\">Markdown 审计页</a> · <a href=\"../../wiki/indexes/execution-center.md\">执行中心</a> · <a href=\"../../wiki/indexes/furnace-center.md\">炉心面板</a></p>",
            "      <div class=\"meta\">",
            *[
                "\n".join(
                    [
                        '        <div class="card">',
                        f'          <div class="metric-label">{html.escape(label)}</div>',
                        f'          <div class="metric">{html.escape(value)}</div>',
                        "        </div>",
                    ]
                )
                for label, value in summary_cards
            ],
            "      </div>",
            "    </section>",
            "    <section class=\"grid\">",
            f'      <div class="card"><h2>Policy Bands</h2><ul>{band_markup}</ul></div>',
            f'      <div class="card"><h2>Protocol Breakdown</h2><ul>{protocol_markup}</ul></div>',
            f'      <div class="card"><h2>Recent Apply</h2><ul>{apply_markup}</ul></div>',
            f'      <div class="card"><h2>Recent Revert</h2><ul>{revert_markup}</ul></div>',
            f'      <div class="card"><h2>Consistency Signals</h2><ul>{consistency_markup}</ul></div>',
            f'      <div class="card"><h2>Action Audit</h2><ul>{action_markup}</ul></div>',
            "    </section>",
            "  </main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def render_concept_quality(memory: dict[str, Any]) -> str:
    quality = memory.get("health", {}).get("concept_quality", {})
    rewrite_state = memory.get("health", {}).get("concept_rewrite", {})
    counts = quality.get("counts", {})
    hard_concepts = quality.get("hard_concepts", [])
    weak_concepts = quality.get("weak_concepts", [])
    stable_concepts = quality.get("stable_concepts", [])
    merge_candidates = quality.get("merge_candidates", [])
    rewrite_candidates = quality.get("rewrite_candidates", [])
    conflict_signals = quality.get("conflict_signals", [])
    gap_signals = quality.get("gap_signals", [])
    lines = [
        "# 概念质量",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        f"- 弱概念页：`{counts.get('weak', 0)}`",
        f"- 稳定概念页：`{counts.get('stable', 0)}`",
        f"- 占位概念页：`{counts.get('placeholders', 0)}`",
        f"- 合并候选：`{counts.get('merge_candidates', 0)}`",
        f"- 重写候选：`{counts.get('rewrite_candidates', 0)}`",
        f"- 冲突信号：`{counts.get('conflict_signals', 0)}`",
        f"- 证据缺口：`{counts.get('gap_signals', 0)}`",
        f"- 平均质量分：`{quality.get('average_quality_score', 0)}`",
        (
            "- Quality bands："
            f" strong `{counts.get('strong_quality', 0)}`"
            f" / stable `{counts.get('stable_quality', 0)}`"
            f" / watch `{counts.get('watch_quality', 0)}`"
            f" / fragile `{counts.get('fragile_quality', 0)}`"
        ),
        (
            "- Hardness："
            f" hard `{counts.get('hard_hardness', 0)}`"
            f" / medium `{counts.get('medium_hardness', 0)}`"
            f" / soft `{counts.get('soft_hardness', 0)}`"
        ),
        f"- Rewrite 提案：`{rewrite_state.get('counts', {}).get('active', 0)}`",
        f"- 待审提案：`{rewrite_state.get('counts', {}).get('pending_review', 0)}`",
        f"- 可应用提案：`{rewrite_state.get('counts', {}).get('apply_ready', 0)}`",
        f"- 已验证提案：`{rewrite_state.get('counts', {}).get('verified_passed', 0)}`",
        f"- 可回滚提案：`{rewrite_state.get('counts', {}).get('revert_ready', 0)}`",
        "",
        "## Hard Concepts",
    ]
    if not hard_concepts:
        lines.append("- 当前还没有 `hardness` >= `medium` 的概念页。")
    else:
        for concept in hard_concepts[:12]:
            lines.append(
                f"- [{concept['title']}](../concepts/{concept['slug']}.md)"
                f" | hardness `{concept.get('hardness', 'soft')}`"
                f" | confidence `{concept.get('confidence', 'n/a') or 'n/a'}`"
                f" | sources `{concept.get('source_count', 0)}`"
                f" | quality `{concept.get('quality_score', 0)}`"
            )
    lines.extend([
        "",
        "## Rewrite Now",
    ])
    if not weak_concepts:
        lines.append("- 当前没有需要立即重写的概念页。")
    else:
        for concept in weak_concepts[:12]:
            lines.append(
                f"- [{concept['title']}](../concepts/{concept['slug']}.md)"
                f" | hardness `{concept.get('hardness', 'soft')}`"
                f" | issues `{', '.join(concept.get('issues', [])) or 'none'}`"
                f" | sources `{concept.get('source_count', 0)}`"
                f" | related `{concept.get('related_count', 0)}`"
                f" | quality `{concept.get('quality_score', 0)}`"
                f" | band `{concept.get('quality_band', 'n/a')}`"
            )
            metrics = concept.get("quality_metrics", {})
            lines.append(
                "  - metrics: "
                f"coverage `{metrics.get('source_coverage', 0)}`"
                f" / consistency `{metrics.get('consistency', 0)}`"
                f" / evidence `{metrics.get('evidence_depth', 0)}`"
                f" / recency `{metrics.get('recency', 0)}`"
            )
    lines.extend(["", "## Quality Distribution"])
    lines.append(
        f"- Strong / Stable / Watch / Fragile："
        f" `{counts.get('strong_quality', 0)}` / `{counts.get('stable_quality', 0)}` /"
        f" `{counts.get('watch_quality', 0)}` / `{counts.get('fragile_quality', 0)}`"
    )
    lines.extend(["", "## Rewrite Priority"])
    if not rewrite_candidates:
        lines.append("- 当前没有新的重写候选。")
    else:
        for candidate in rewrite_candidates[:10]:
            lines.append(
                f"- [{candidate['title']}](../concepts/{candidate['slug']}.md)"
                f" | priority `{candidate.get('priority', 'n/a')}`"
                f" | score `{candidate.get('score', 0)}`"
                f" | quality `{candidate.get('quality_score', 0)}`"
                f" | band `{candidate.get('quality_band', 'n/a')}`"
                f" | issues `{', '.join(candidate.get('issues', [])) or 'none'}`"
            )
            lines.append(f"  - strategy: {candidate.get('rewrite_strategy', 'n/a')}")
    lines.extend(["", "## Rewrite Proposals"])
    if not rewrite_state.get("proposals"):
        lines.append("- 当前还没有 concept rewrite proposal。先运行 `run-compile` 或等待下一次 rewrite proposal 生成。")
    else:
        for proposal in rewrite_state.get("proposals", [])[:10]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | status `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`"
                f" | priority `{proposal.get('priority', 'n/a')}`"
                f" | apply_ready `{proposal.get('apply_ready', False)}`"
                f" | verification `{proposal.get('verification_status', 'pending') or 'pending'}`"
            )
            if proposal.get("rewrite_strategy"):
                lines.append(f"  - strategy: {proposal['rewrite_strategy']}")
    lines.extend(["", "## Conflict Signals"])
    if not conflict_signals:
        lines.append("- 当前没有显式概念冲突信号。")
    else:
        for signal in conflict_signals[:10]:
            lines.append(
                f"- [{signal['title']}](../concepts/{signal['slug']}.md)"
                f" | signal `{signal.get('label', 'n/a')}`"
                f" | sources `{', '.join(signal.get('source_pages', [])) or 'none'}`"
            )
    lines.extend(["", "## Evidence Gaps"])
    if not gap_signals:
        lines.append("- 当前没有显式证据缺口。")
    else:
        for gap in gap_signals[:10]:
            lines.append(
                f"- [{gap['title']}](../concepts/{gap['slug']}.md)"
                f" | kind `{gap.get('kind', 'n/a')}`"
                f" | source `{gap.get('path', 'n/a')}`"
                f" | markers `{', '.join(gap.get('markers', [])) or 'none'}`"
            )
    lines.extend(["", "## Merge Candidates"])
    if not merge_candidates:
        lines.append("- 当前没有明显的概念合并候选。")
    else:
        for candidate in merge_candidates[:10]:
            lines.append(
                f"- [{candidate['left_title']}](../concepts/{candidate['left_slug']}.md)"
                f" <-> [{candidate['right_title']}](../concepts/{candidate['right_slug']}.md)"
                f" | shared_sources `{len(candidate.get('shared_sources', []))}`"
                f" | shared_tokens `{', '.join(candidate.get('shared_tokens', [])) or 'none'}`"
            )
    lines.extend(["", "## Stable Concepts"])
    if not stable_concepts:
        lines.append("- 当前还没有稳定概念页。")
    else:
        for concept in stable_concepts[:10]:
            lines.append(
                f"- [{concept['title']}](../concepts/{concept['slug']}.md)"
                f" | sources `{concept.get('source_count', 0)}`"
                f" | related `{concept.get('related_count', 0)}`"
                f" | quality `{concept.get('quality_score', 0)}`"
            )
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [概念索引](./concepts.md)",
            "- [机器记忆](./machine-memory.md)",
            "- [动作队列](./machine-memory-actions.md)",
            "- [修复计划](./machine-memory-repair-plan.md)",
            "- [Rewrite Proposals](./rewrite-proposals.md)",
            "- [修复待办](./repair-backlog.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def concept_rewrite_proposal_digest(candidate_markdown: str) -> str:
    if not candidate_markdown:
        return ""
    return sha256_bytes(candidate_markdown.encode("utf-8"))


def reconcile_concept_rewrite_proposals(
    root: Path,
    quality: dict[str, Any],
    *,
    compiled_at: str,
) -> dict[str, Any]:
    previous_state = load_concept_rewrite_state(root)
    previous_by_slug = {
        str(proposal.get("slug") or ""): proposal
        for proposal in previous_state.get("proposals", [])
        if proposal.get("slug")
    }
    active_records: list[dict[str, Any]] = []
    inactive_records: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    for candidate in quality.get("rewrite_candidates", []):
        slug = str(candidate.get("slug") or "").strip()
        if not slug:
            continue
        snapshot = concept_page_snapshot(root, slug)
        previous = previous_by_slug.get(slug, {})
        source_signature = str(candidate.get("source_signature") or snapshot.get("source_signature") or "")
        status = str(previous.get("status") or "proposed")
        if status not in REWRITE_PROPOSAL_STATUSES:
            status = "proposed"
        previous_signature = str(previous.get("source_signature") or "")
        signature_changed = bool(previous_signature and previous_signature != source_signature)
        if signature_changed and status in {"applied", "rejected"}:
            status = "proposed"
        candidate_markdown = str(previous.get("candidate_markdown") or "")
        candidate_digest = str(previous.get("candidate_digest") or concept_rewrite_proposal_digest(candidate_markdown))
        first_proposed_at = str(previous.get("first_proposed_at") or compiled_at)
        occurrences = int(previous.get("occurrences") or 0) + 1
        reviewed_at = str(previous.get("reviewed_at") or "")
        review_note = str(previous.get("review_note") or "")
        applied_at = str(previous.get("applied_at") or "")
        reverted_at = str(previous.get("reverted_at") or "")
        revert_note = str(previous.get("revert_note") or "")
        previous_markdown = str(previous.get("previous_markdown") or "")
        previous_digest = str(previous.get("previous_digest") or "")
        verification_status = str(previous.get("verification_status") or "")
        verification_checked_at = str(previous.get("verification_checked_at") or "")
        verification_summary = str(previous.get("verification_summary") or "")
        verification_issues = [
            str(item)
            for item in previous.get("verification_issues", [])
            if isinstance(item, str) and item
        ]
        last_applied_at = str(previous.get("last_applied_at") or applied_at)
        if signature_changed:
            status = "proposed"
            candidate_markdown = ""
            candidate_digest = ""
            reviewed_at = ""
            review_note = ""
            applied_at = ""
            reverted_at = ""
            revert_note = ""
            previous_markdown = ""
            previous_digest = ""
            verification_status = ""
            verification_checked_at = ""
            verification_summary = ""
            verification_issues = []
            last_applied_at = ""
        record = {
            "slug": slug,
            "title": str(candidate.get("title") or snapshot.get("title") or slug),
            "priority": str(candidate.get("priority") or "medium"),
            "score": int(candidate.get("score") or 0),
            "quality_score": int(candidate.get("quality_score") or 0),
            "quality_band": str(candidate.get("quality_band") or ""),
            "issues": list(candidate.get("issues") or []),
            "rewrite_strategy": str(candidate.get("rewrite_strategy") or ""),
            "target_path": str(candidate.get("path") or snapshot.get("path") or f"wiki/concepts/{slug}.md"),
            "proposal_path": relative_path(root, concept_rewrite_proposal_page_path(root, slug)),
            "source_signature": source_signature,
            "source_pages": list(candidate.get("source_pages") or snapshot.get("source_pages") or []),
            "status": status,
            "active": True,
            "first_proposed_at": first_proposed_at,
            "last_proposed_at": compiled_at,
            "occurrences": occurrences,
            "reviewed_at": reviewed_at,
            "review_note": review_note,
            "applied_at": applied_at,
            "last_applied_at": last_applied_at,
            "reverted_at": reverted_at,
            "revert_note": revert_note,
            "pending_review": "true" if rewrite_proposal_needs_review(status) else "false",
            "candidate_markdown": candidate_markdown,
            "candidate_digest": candidate_digest,
            "apply_ready": False,
            "current_summary": str(snapshot.get("summary") or ""),
            "previous_markdown": previous_markdown,
            "previous_digest": previous_digest,
            "verification_status": verification_status,
            "verification_checked_at": verification_checked_at,
            "verification_summary": verification_summary,
            "verification_issues": verification_issues,
        }
        record["apply_ready"] = rewrite_proposal_is_apply_ready(root, record)
        active_records.append(record)
        seen_slugs.add(slug)

    for slug, previous in previous_by_slug.items():
        if slug in seen_slugs:
            continue
        target_path = root / str(previous.get("target_path") or f"wiki/concepts/{slug}.md")
        proposal_path = root / str(previous.get("proposal_path") or f"wiki/rewrite-proposals/{slug}.md")
        if not target_path.exists() or not proposal_path.exists():
            continue
        record = dict(previous)
        record["active"] = False
        record["pending_review"] = "false"
        record["apply_ready"] = False
        inactive_records.append(record)

    active_records.sort(
        key=lambda item: (
            rewrite_proposal_status_rank(str(item.get("status") or "")),
            action_priority_rank(str(item.get("priority") or "")),
            -int(item.get("score", 0)),
            str(item.get("title", "")).lower(),
        )
    )
    inactive_records.sort(
        key=lambda item: (
            str(item.get("applied_at") or item.get("reviewed_at") or item.get("last_proposed_at") or ""),
            str(item.get("title", "")).lower(),
        ),
        reverse=True,
    )
    document = {
        "version": 1,
        "compiled_at": compiled_at,
        "proposals": active_records + inactive_records,
    }
    save_concept_rewrite_state(root, document)
    counts = {
        "active": len(active_records),
        "inactive": len(inactive_records),
        "pending_review": sum(1 for proposal in active_records if proposal.get("pending_review") == "true"),
        "apply_ready": sum(1 for proposal in active_records if proposal.get("apply_ready")),
        "verified_passed": sum(1 for proposal in active_records + inactive_records if proposal.get("verification_status") == "passed"),
        "revert_ready": sum(
            1
            for proposal in active_records + inactive_records
            if proposal.get("status") == "applied" and str(proposal.get("previous_markdown") or "")
        ),
        "by_status": {
            status: sum(1 for proposal in active_records if proposal.get("status") == status)
            for status in REWRITE_PROPOSAL_STATUSES
        },
    }
    return {
        "all_proposals": active_records + inactive_records,
        "proposals": active_records[:12],
        "inactive_proposals": inactive_records[:8],
        "counts": counts,
        "state_path": relative_path(root, concept_rewrite_state_path(root)),
    }


def render_concept_rewrite_proposal_page(proposal: dict[str, Any]) -> str:
    verification_status = str(proposal.get("verification_status") or "")
    if not verification_status:
        verification_status = "pending" if proposal.get("status") == "applied" else "not-run"
    verification_issues = [
        str(item)
        for item in proposal.get("verification_issues", [])
        if isinstance(item, str) and item
    ]
    frontmatter = render_frontmatter(
        {
            "id": f"rewrite-proposal-{proposal['slug']}",
            "kind": "rewrite-proposal",
            "status": proposal.get("status", "proposed"),
            "title": proposal["title"],
            "target_path": proposal.get("target_path", ""),
            "source_signature": proposal.get("source_signature", ""),
            "generated_by": "aiwiki-run-compile",
            "last_compiled_at": proposal.get("last_proposed_at", ""),
        }
    )
    lines = [
        frontmatter,
        "",
        f"# Rewrite Proposal · {proposal['title']}",
        "",
        "## Proposal Status",
        f"- Status: `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`",
        f"- Priority: `{proposal.get('priority', 'n/a')}`",
        f"- Score: `{proposal.get('score', 0)}`",
        f"- Quality score: `{proposal.get('quality_score', 0)}`",
        f"- Quality band: `{proposal.get('quality_band', 'n/a') or 'n/a'}`",
        f"- Apply ready: `{proposal.get('apply_ready', False)}`",
        f"- First proposed: `{proposal.get('first_proposed_at', '') or 'none'}`",
        f"- Last proposed: `{proposal.get('last_proposed_at', '') or 'none'}`",
        f"- Reviewed at: `{proposal.get('reviewed_at', '') or 'none'}`",
        f"- Applied at: `{proposal.get('applied_at', '') or 'none'}`",
        f"- Reverted at: `{proposal.get('reverted_at', '') or 'none'}`",
        "",
        "## Target",
        f"- Target page: `{proposal.get('target_path', '')}`",
        f"- Source signature: `{proposal.get('source_signature', '')}`",
        f"- Source pages: `{', '.join(proposal.get('source_pages', [])) or 'none'}`",
        "",
        "## Current Summary Snapshot",
        proposal.get("current_summary", "") or "- No summary snapshot captured.",
        "",
        "## Rewrite Strategy",
        f"- Issues: `{', '.join(proposal.get('issues', [])) or 'none'}`",
        f"- Strategy: {proposal.get('rewrite_strategy', 'n/a')}",
        "",
        "## Verification",
        f"- Status: `{verification_status}`",
        f"- Checked at: `{proposal.get('verification_checked_at', '') or 'none'}`",
        f"- Summary: {proposal.get('verification_summary', '') or 'Verification has not run yet.'}",
        f"- Issues: `{', '.join(verification_issues) or 'none'}`",
        "",
        "## Rollback",
        f"- Previous snapshot available: `{bool(proposal.get('previous_markdown'))}`",
        f"- Last applied at: `{proposal.get('last_applied_at', '') or proposal.get('applied_at', '') or 'none'}`",
        f"- Revert note: {proposal.get('revert_note', '') or 'none'}",
        "",
        "## Commands",
        f"- Review: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite {proposal['slug']} --status accepted`",
        f"- Apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {proposal['slug']}`",
        f"- Verify: `PYTHONPATH=src python3 -m aiwiki.cli --root . verify-rewrite {proposal['slug']}`",
        f"- Revert: `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-rewrite {proposal['slug']}`",
        "",
        "## Proposed Markdown",
    ]
    if proposal.get("candidate_markdown"):
        lines.extend(
            [
                "```markdown",
                str(proposal["candidate_markdown"]).strip(),
                "```",
            ]
        )
    else:
        lines.append("- 当前还没有生成候选重写内容。先运行 `run-compile`。")
    return "\n".join(lines) + "\n"


def render_concept_rewrite_index(state: dict[str, Any], compiled_at: str) -> str:
    proposals = state.get("proposals", [])
    inactive = state.get("inactive_proposals", [])
    all_proposals = state.get("all_proposals", proposals)
    counts = state.get("counts", {})
    revert_ready = [
        proposal
        for proposal in all_proposals
        if proposal.get("status") == "applied" and str(proposal.get("previous_markdown") or "")
    ]
    lines = [
        "# Rewrite Proposals",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- Active proposals：`{counts.get('active', 0)}`",
        f"- Pending review：`{counts.get('pending_review', 0)}`",
        f"- Apply ready：`{counts.get('apply_ready', 0)}`",
        f"- Verified passed：`{counts.get('verified_passed', 0)}`",
        f"- Revert ready：`{counts.get('revert_ready', 0)}`",
        f"- 状态文件：`{state.get('state_path', '.aiwiki/state/concept-rewrite-proposals.json')}`",
        "",
        "## Pending Review",
    ]
    pending = [proposal for proposal in proposals if proposal.get("pending_review") == "true"]
    if not pending:
        lines.append("- 当前没有待审的 rewrite proposal。")
    else:
        for proposal in pending[:12]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | status `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`"
                f" | priority `{proposal.get('priority', 'n/a')}`"
                f" | apply_ready `{proposal.get('apply_ready', False)}`"
            )
    lines.extend(["", "## Apply Ready"])
    apply_ready = [proposal for proposal in proposals if proposal.get("apply_ready")]
    if not apply_ready:
        lines.append("- 当前没有可直接应用的 rewrite proposal。")
    else:
        for proposal in apply_ready[:12]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | command `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {proposal['slug']}`"
            )
    lines.extend(["", "## Revert Ready"])
    if not revert_ready:
        lines.append("- 当前没有可回滚的已应用 rewrite proposal。")
    else:
        for proposal in revert_ready[:12]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | applied `{proposal.get('applied_at', '') or 'none'}`"
                f" | verify `{proposal.get('verification_status', '') or 'pending'}`"
                f" | command `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-rewrite {proposal['slug']}`"
            )
    lines.extend(["", "## Recently Closed"])
    if not inactive:
        lines.append("- 当前没有已关闭的 rewrite proposal。")
    else:
        for proposal in inactive[:8]:
            lines.append(
                f"- [{proposal['title']}](../rewrite-proposals/{proposal['slug']}.md)"
                f" | status `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`"
                f" | applied `{proposal.get('applied_at', '') or 'none'}`"
            )
    return "\n".join(lines) + "\n"
