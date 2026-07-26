"""Markdown renderer for the furnace center surface."""

from __future__ import annotations

from typing import Any

from ..lifecycle.aging import collect_aging_signals
from ..lifecycle.knowledge import (
    knowledge_lifecycle_governance_summary,
    render_knowledge_lifecycle_entry_summary,
)
from ..lifecycle.status import display_curated_status, review_queue
from ..memory.action_core import action_supports_low_risk_apply
from ..protocol.descriptors import protocol_title
from ..state.constants import DEFAULT_PROTOCOL
from .markdown_links import compact_section_lines, protocol_output_pack_rows
from .pilots import protocol_scorecard
from .views import furnace_quick_commands, protocol_execution_receipts


def render_furnace_center(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    domain_pilots: dict[str, Any],
    execution_audit: dict[str, Any],
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    lifecycle_counts = lifecycle_summary.get("counts", {})
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    rewrite_state = health.get("concept_rewrite", {})
    judgment_review_actions = health.get("judgment_review_actions", [])
    pending_items = queue.get("pending_decisions", []) + queue.get("pending_judgments", [])
    citation_drift_count = sum(1 for page in decisions + judgments if page.get("citation_drift") == "true")
    ready_actions = [
        action
        for action in plan.get("ready_actions", [])
        if isinstance(action, dict) and str(action.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]
    execution_proposals = [
        proposal
        for proposal in plan.get("execution_proposals", [])
        if isinstance(proposal, dict) and str(proposal.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    judgment_lifecycle_focus = lifecycle_summary.get("under_review_judgments", []) + lifecycle_summary.get(
        "revised_judgments", []
    )
    page_patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in execution_proposals)
    recent_reviewed = queue.get("recently_reviewed", [])[:6]
    scorecard = protocol_scorecard(domain_pilots, active_protocol)
    scorecard_metrics = scorecard.get("metrics", {}) if isinstance(scorecard, dict) else {}
    pack_rows = protocol_output_pack_rows(output_packs, active_protocol)
    receipt_rows = protocol_execution_receipts(execution_audit, active_protocol)
    quick_commands = furnace_quick_commands(active_protocol, apply_ready_actions, apply_ready_rewrites)
    next_steps: list[str] = []
    if concept_backlog:
        next_steps.append(f"先处理 `{min(len(concept_backlog), 5)}` 个 lifecycle concept backlog。")
    if judgment_review_actions:
        next_steps.append(f"先清理 `{min(len(judgment_review_actions), 5)}` 个 judgment review action。")
    if apply_ready_actions:
        next_steps.append(f"先处理 `{len(apply_ready_actions)}` 个低风险 machine-memory 动作（见 `advanced review-queue`）。")
    if apply_ready_rewrites:
        next_steps.append(f"审阅 `{len(apply_ready_rewrites)}` 个已接受的 concept rewrite proposal（见 `advanced review-queue`）。")
    if aging.get("escalated"):
        next_steps.append(f"优先复查 `{len(aging.get('escalated', []))}` 个升级项。")
    if pending_items:
        next_steps.append(f"继续审 `{len(pending_items)}` 个 decision / judgment 页面。")
    if retired_concepts and not concept_backlog:
        next_steps.append(f"检查 `{min(len(retired_concepts), 3)}` 个 retired concept 是否需要重新激活。")
    if not next_steps:
        next_steps.append("当前没有紧急执行项，优先看最新输出和图谱漂移。")

    lines = [
        "# 炉心面板",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 来源节点：`{len(memory.get('source_nodes', []))}`",
        f"- 概念节点：`{len(memory.get('concept_nodes', []))}`",
        f"- 待审项目：`{len(pending_items)}`",
        f"- 已到期 / 升级：`{len(aging.get('overdue', []))}` / `{len(aging.get('escalated', []))}`",
        f"- Judgment formed / active / under-review / revised / retired：`{lifecycle_counts.get('formed_judgments', 0)}` / `{lifecycle_counts.get('active_judgments', 0)}` / `{lifecycle_counts.get('under_review_judgments', 0)}` / `{lifecycle_counts.get('revised_judgments', 0)}` / `{lifecycle_counts.get('retired_judgments', 0)}`",
        f"- 生命周期概念待审 / 已退役：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}` / `{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        f"- 证据漂移：`{citation_drift_count}`",
        f"- Judgment review actions：`{len(judgment_review_actions)}`",
        f"- Ready repair actions：`{len(ready_actions)}`",
        f"- 可直接 apply 的动作：`{len(apply_ready_actions)}`",
        f"- Rewrite 提案：`{rewrite_state.get('counts', {}).get('active', 0)}`",
        f"- 可直接 apply 的 rewrite：`{len(apply_ready_rewrites)}`",
        f"- 页级 patch step：`{page_patch_steps}`",
        f"- 当前协议 stage：`{scorecard.get('stage', 'seed') if scorecard else 'unknown'}`",
        f"- 当前协议 outputs / receipts：`{scorecard_metrics.get('outputs', 0)}` / `{scorecard_metrics.get('receipts', 0)}`",
        f"- 当前协议 review packs / memos / SOP：`{scorecard_metrics.get('review_packs', 0)}` / `{scorecard_metrics.get('decision_memos', 0)}` / `{scorecard_metrics.get('sop_drafts', 0)}`",
        f"- 最近输出：`{len(recent_outputs)}`",
        "- 机器记忆 JSON：`.aiwiki/cache/machine-memory-graph.json`（Obsidian 证据链 + compile 邻接导出；HTML 控制面已停写）",
        "",
        "## 今天先做什么",
    ]
    for index, step in enumerate(next_steps, start=1):
        lines.append(f"{index}. {step}")

    lines.extend(["", "## 即刻可执行"])
    if apply_ready_actions:
        lines.append("### Safe Apply Actions")
        for action in apply_ready_actions[:8]:
            lines.append(
                f"- `{action['title']}` | command `{action.get('command_hint', '')}`"
                f" | primary `{action.get('primary_path', '')}`"
            )
    if apply_ready_rewrites:
        lines.append("")
        lines.append("### Apply-Ready Rewrites")
        for proposal in apply_ready_rewrites[:8]:
            lines.append(f"- `{proposal['target_path']}` | proposal `{proposal['slug']}`")
    if execution_proposals:
        lines.append("")
        lines.append("### Execution Proposals")
        for proposal in execution_proposals[:8]:
            lines.append(
                f"- `{proposal['action_id']}` | risk `{proposal.get('risk', 'medium')}`"
                f" | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
            )
        lines.append("")
        lines.append("### Page-Level Patch Plan")
        for proposal in execution_proposals[:4]:
            patch_plan = proposal.get("page_patch_plan", [])
            if not patch_plan:
                continue
            lines.append(f"- `{proposal['action_id']}` | patch step `{len(patch_plan)}`")
            for patch in patch_plan[:3]:
                lines.append(
                    f"  - `{patch.get('path', '')}`"
                    f" | mode `{patch.get('mode', 'update')}`"
                    f" | sections `{', '.join(patch.get('sections', [])) or 'none'}`"
                )
    if not any((apply_ready_actions, apply_ready_rewrites, execution_proposals)):
        lines.append("- 当前没有即刻可执行项。")

    lines.extend(["", "## 最近输出"])
    if not recent_outputs:
        lines.append("- 当前还没有 recent outputs。")
    else:
        for artifact in recent_outputs:
            lines.append(
                f"- [{artifact['title']}](../../{artifact['path']})"
                f" | format `{artifact['format'] or 'unknown'}`"
                f" | protocol `{artifact['protocol'] or DEFAULT_PROTOCOL}`"
                f" | created `{artifact['created_at'] or 'unknown'}`"
            )

    lines.extend(["", "## 当前协议 Pilot"])
    if not scorecard:
        lines.append("- 当前协议还没有 pilot scorecard。")
    else:
        lines.append(
            f"- [{scorecard['title']}](../../{scorecard['path']})"
            f" | stage `{scorecard.get('stage', 'seed')}`"
            f" | {scorecard.get('summary', '')}"
        )
        gaps = compact_section_lines(
            scorecard.get("content", ""), "Gaps", fallback="- 当前没有明显结构性缺口。", limit=4
        )
        lines.append("")
        lines.append("### 当前缺口")
        lines.extend(gaps)
        next_moves_lines = compact_section_lines(
            scorecard.get("content", ""), "Next Moves", fallback="- 当前没有额外 next moves。", limit=4
        )
        lines.append("")
        lines.append("### 下一动作")
        lines.extend(next_moves_lines)

    lines.extend(["", "## Lifecycle 治理摘要"])
    lines.extend(
        [
            f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
            f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
            f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
            f"- formed judgments：`{lifecycle_counts.get('formed_judgments', 0)}`",
            f"- active judgments：`{lifecycle_counts.get('active_judgments', 0)}`",
            f"- under-review judgments：`{lifecycle_counts.get('under_review_judgments', 0)}`",
            f"- revised judgments：`{lifecycle_counts.get('revised_judgments', 0)}`",
            f"- retired judgments：`{lifecycle_counts.get('retired_judgments', 0)}`",
            "",
            "### Lifecycle Concept Backlog",
        ]
    )
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "### Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "### Judgment Lifecycle Focus"])
    if not judgment_lifecycle_focus:
        lines.append("- 当前没有 judgment lifecycle 焦点。")
    else:
        for entry in judgment_lifecycle_focus[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "### Judgment Review Actions"])
    if not judgment_review_actions:
        lines.append("- 当前没有 judgment review action。")
    else:
        for action in judgment_review_actions[:10]:
            command = str(action.get("review_command") or "")
            command_suffix = f" | command `{command}`" if command else ""
            lines.append(
                f"- `{action.get('title', 'review action')}`"
                f" | priority `{action.get('priority', 'medium')}`"
                f" | reasons `{', '.join(action.get('reason_codes', [])) or 'none'}`"
                f"{command_suffix}"
            )

    lines.extend(["", "## 最新输出 Packs"])
    if not pack_rows:
        lines.append("- 当前协议还没有 review pack / decision memo / SOP draft。")
    else:
        for pack in pack_rows:
            lines.append(
                f"- [{pack['title']}](../../{pack['path']}) | kind `{pack['kind']}` | meta `{pack['meta'] or 'n/a'}`"
            )

    lines.extend(["", "## 最近执行回执"])
    if not receipt_rows:
        lines.append("- 当前协议还没有 execution receipt。")
    else:
        for receipt in receipt_rows:
            receipt_path = receipt["receipt_path"] or ".aiwiki/state/execution-receipts.jsonl"
            lines.append(
                f"- `{receipt['title']}`"
                f" | kind `{receipt['kind']}`"
                f" | action `{receipt['action_id']}`"
                f" | receipt `{receipt_path}`"
                f" | at `{receipt['applied_at'] or 'unknown'}`"
            )

    lines.extend(["", "## 最近已审 / 已沉淀"])
    if recent_reviewed:
        for page in recent_reviewed:
            lines.append(
                f"- [{page['title']}](../../{page['path']})"
                f" | status `{display_curated_status(page.get('status', 'unknown'))}`"
                f" | reviewed `{page.get('reviewed_at', '') or 'unknown'}`"
            )
    else:
        lines.append("- 当前还没有最近已审项目。")

    lines.extend(["", "## 快速命令"])
    for command in quick_commands:
        lines.append(f"- `{command}`")

    lines.extend(
        [
            "",
            "## 快速跳转",
            "- [审阅中心](./review-center.md)",
            "- [执行审计](./execution-audit.md)",
            "- [Agent Workbench](./agent-workbench.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [输出 Pack 总览](./output-packs.md)",
            "- [领域 Pilot 总览](./domain-pilots.md)",
            "- [判断资产](./judgment-assets.md)",
            "- [图谱视图](./graph-view.md)",
            "- [修复待办](./repair-backlog.md)",
            "- [协议总览](./protocols.md)",
            "- [输出面板](../../wiki/indexes/Outputs.md)",
            "- 机器记忆 JSON：`.aiwiki/cache/machine-memory-graph.json`（compile 邻接导出；**HTML 控制面已停写**）",
            "- Obsidian 图谱：[[wiki/indexes/graph-view|图谱视图]]（证据链主入口）",
        ]
    )
    return "\n".join(lines) + "\n"
