"""Markdown renderer for the furnace center surface."""

from __future__ import annotations

from typing import Any

from ..lifecycle.aging import collect_aging_signals
from ..lifecycle.knowledge import knowledge_lifecycle_governance_summary
from ..lifecycle.status import review_queue


def render_furnace_center(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    """Render the user first-screen panel.

    Kept deliberately slim: what to do today, recent outputs, and links to the
    live governance pages. Governance detail lives in review-queue.md (compile)
    and repair-backlog.md (nightly), not here.
    """
    active_protocol = protocol_state["active_protocol"]
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    health = memory.get("health", {})
    judgment_review_actions = health.get("judgment_review_actions", [])
    pending_items = queue.get("pending_decisions", []) + queue.get("pending_judgments", [])
    next_steps: list[str] = []
    if concept_backlog:
        next_steps.append(f"先处理 `{min(len(concept_backlog), 5)}` 个 lifecycle concept backlog。")
    if judgment_review_actions:
        next_steps.append(f"先清理 `{min(len(judgment_review_actions), 5)}` 个 judgment review action。")
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
        "用户首屏：今天该做什么、最近产出了什么、再去哪里。治理细节收在专页（审阅队列 / 修复待办等），不堆在这里。",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源 / 概念：`{len(memory.get('source_nodes', []))}` / `{len(memory.get('concept_nodes', []))}`",
        f"- 待审 / 到期 / 升级：`{len(pending_items)}` / `{len(aging.get('overdue', []))}` / `{len(aging.get('escalated', []))}`（详见 [审阅队列](./review-queue.md)）",
        "",
        "## 今天先做什么",
    ]
    for index, step in enumerate(next_steps, start=1):
        lines.append(f"{index}. {step}")

    lines.extend(["", "## 最近输出"])
    if not recent_outputs:
        lines.append("- 当前还没有 recent outputs。")
    else:
        for artifact in recent_outputs:
            lines.append(
                f"- [{artifact['title']}](../../{artifact['path']})"
                f" | format `{artifact['format'] or 'unknown'}`"
                f" | created `{artifact['created_at'] or 'unknown'}`"
            )

    lines.extend(
        [
            "",
            "## 快速跳转",
            "- [知识库总索引](./index.md)",
            "- [审阅队列](./review-queue.md)：decision / judgment 状态推进、aging、生命周期治理",
            "- [修复待办](./repair-backlog.md)：nightly 汇总的优先级修复队列",
            "- [判断资产](./judgment-assets.md)",
            "- [机器记忆摘要](./machine-memory.md)",
            "- [审阅中心](./review-center.md)",
            "- [图谱视图](./graph-view.md)",
            "- [协议总览](./protocols.md)",
            "- [编译状态](./compile-status.md)",
            "- 机器记忆 JSON：`.aiwiki/cache/machine-memory-graph.json`（compile 邻接导出；HTML 控制面已停写）",
        ]
    )
    return "\n".join(lines) + "\n"
