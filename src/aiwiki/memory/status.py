"""Machine-memory status / health / index / actions / repair-plan renderers.

EP-017B step 3: extracted from app_memory_surfaces.py. Re-exported via the
facade at aiwiki.app_memory_surfaces for backward compatibility.
"""

from __future__ import annotations

from typing import Any

from ..app_lifecycle import display_action_status
from ..app_protocol import ACTION_STATUSES
from ..app_state import DEFAULT_PROTOCOL


def render_drift_report(memory: dict[str, Any], transition: dict[str, Any]) -> str:
    drift = memory["drift"]
    lines = [
        "# 漂移报告",
        "",
        f"- 编译时间：`{memory['compiled_at']}`",
        f"- 当前摘要：`{memory['digest']}`",
        f"- 图谱摘要：`{memory['graph_digest']}`",
        "",
        "## 变化摘要",
    ]
    if not transition["has_previous_snapshot"]:
        lines.append("- 目前没有可对比的上一版机器记忆快照。")
    elif not transition["changed"]:
        lines.append("- 相比上一版快照，没有检测到结构性漂移。")
    else:
        lines.extend(
            [
                f"- 上一版摘要：`{transition['previous_digest']}`",
                f"- 新增来源节点：`{len(transition['added_source_ids'])}`",
                f"- 移除来源节点：`{len(transition['removed_source_ids'])}`",
                f"- 新增概念节点：`{len(transition['added_concept_slugs'])}`",
                f"- 移除概念节点：`{len(transition['removed_concept_slugs'])}`",
                f"- 新增边：`{transition['added_edges']}`",
                f"- 移除边：`{transition['removed_edges']}`",
                f"- 新增索引词（样本）：`{', '.join(transition['added_terms']) or 'none'}`",
                f"- 移除索引词（样本）：`{', '.join(transition['removed_terms']) or 'none'}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 当前漂移检查",
            f"- 缺失 raw 文件：`{len(drift['missing_raw_files'])}`",
            f"- 缺失来源页：`{len(drift['missing_source_pages'])}`",
            f"- 缺失概念页：`{len(drift['missing_concept_pages'])}`",
            f"- 无概念覆盖的来源：`{len(drift['sources_without_concepts'])}`",
            "",
            "## 机器记忆产物",
            "- 状态文件：`.aiwiki/state/machine-memory.json`",
            "- 图谱导出：`.aiwiki/cache/machine-memory-graph.json`",
            "- 历史记录：`.aiwiki/state/machine-memory-history.jsonl`",
        ]
    )
    return "\n".join(lines) + "\n"


def render_graph_health(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    lines = [
        "# 图谱健康",
        "",
        f"- 编译时间：`{memory['compiled_at']}`",
        f"- 连通分量数：`{health.get('component_count', 0)}`",
        f"- 分量大小：`{', '.join(str(size) for size in health.get('component_sizes', [])) or 'none'}`",
        f"- 孤立来源：`{len(health.get('isolated_source_ids', []))}`",
        f"- 单节点概念：`{len(health.get('singleton_concept_slugs', []))}`",
        f"- 桥接概念：`{len(health.get('bridge_concept_slugs', []))}`",
        f"- 过载概念：`{len(health.get('overloaded_concept_slugs', []))}`",
        f"- 修复动作：`{health.get('action_counts', {}).get('total', 0)}`",
        f"- 动作已到期：`{health.get('action_counts', {}).get('overdue', 0)}`",
        f"- 动作需升级：`{health.get('action_counts', {}).get('escalated', 0)}`",
        f"- 执行批次：`{health.get('repair_plan', {}).get('counts', {}).get('batches', 0)}`",
        f"- 执行提案：`{health.get('repair_plan', {}).get('counts', {}).get('proposals', 0)}`",
        f"- 页级 patch step：`{health.get('repair_plan', {}).get('counts', {}).get('patch_steps', 0)}`",
        f"- Judgment 关系边：`{health.get('judgment_relation_counts', {}).get('judgment_to_judgment', 0)}`",
        f"- Judgment-Decision 边：`{health.get('judgment_relation_counts', {}).get('judgment_to_decision', 0)}`",
        "",
        "## 修复信号",
        f"- 孤立来源：`{', '.join(health.get('isolated_source_ids', [])[:10]) or 'none'}`",
        f"- 单节点概念：`{', '.join(health.get('singleton_concept_slugs', [])[:10]) or 'none'}`",
        f"- 桥接概念：`{', '.join(health.get('bridge_concept_slugs', [])[:10]) or 'none'}`",
        f"- 过载概念：`{', '.join(health.get('overloaded_concept_slugs', [])[:10]) or 'none'}`",
        f"- 修复候选：`{len(health.get('link_suggestions', []))}`",
        "",
        "## 最大分量",
    ]
    components = health.get("components", [])
    if not components:
        lines.append("- 暂无分量数据。")
    else:
        for component in components[:5]:
            lines.append(
                f"- `{component['id']}` size `{component['size']}`"
                f" | sources `{', '.join(component.get('source_ids', [])[:4]) or 'none'}`"
                f" | concepts `{', '.join(component.get('concept_slugs', [])[:4]) or 'none'}`"
                f" | judgments `{', '.join(component.get('judgment_ids', [])[:3]) or 'none'}`"
            )
    lines.extend(
        [
            "",
        "## 相关链接",
        "- [机器记忆](./machine-memory.md)",
        "- [拓扑视图](./machine-memory-topology.md)",
        "- [动作队列](./machine-memory-actions.md)",
        "- [修复计划](./machine-memory-repair-plan.md)",
        "- [漂移报告](./drift-report.md)",
        "- [修复待办](./repair-backlog.md)",
        "- [决策索引](./decisions.md)",
        "- [判断索引](./judgments.md)",
        "- [审阅队列](./review-queue.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_machine_memory_index(memory: dict[str, Any]) -> str:
    concept_nodes = memory["concept_nodes"]
    judgment_nodes = memory.get("judgment_nodes", [])
    edges = memory["edges"]
    drift = memory["drift"]
    health = memory.get("health", {})
    lines = [
        "# 机器记忆",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        "- 运行时状态文件：`.aiwiki/state/machine-memory.json`",
        "- 图谱导出文件：`.aiwiki/cache/machine-memory-graph.json`",
        "- 漂移报告：`wiki/indexes/drift-report.md`",
        f"- 来源节点：`{len(memory['source_nodes'])}`",
        f"- 判断节点：`{len(judgment_nodes)}`",
        f"- 概念节点：`{len(concept_nodes)}`",
        f"- 来源到判断的边：`{len(edges.get('source_to_judgment', []))}`",
        f"- Judgment 到 Judgment 的边：`{len(edges.get('judgment_to_judgment', []))}`",
        f"- Judgment 到 Decision 的边：`{len(edges.get('judgment_to_decision', []))}`",
        f"- 来源到概念的边：`{len(edges['source_to_concept'])}`",
        f"- 概念到概念的边：`{len(edges['concept_to_concept'])}`",
        f"- 索引词数量：`{len(memory['term_index'])}`",
        f"- 机器摘要：`{memory['digest']}`",
        f"- 图谱摘要：`{memory['graph_digest']}`",
        "",
        "## 图谱健康",
        f"- 连通分量：`{health.get('component_count', 0)}`",
        f"- 孤立来源：`{len(health.get('isolated_source_ids', []))}`",
        f"- 单节点概念：`{len(health.get('singleton_concept_slugs', []))}`",
        f"- 桥接概念：`{len(health.get('bridge_concept_slugs', []))}`",
        f"- 过载概念：`{len(health.get('overloaded_concept_slugs', []))}`",
        f"- 已索引分量：`{len(health.get('components', []))}`",
        f"- Hub 概念：`{len(health.get('hub_concepts', []))}`",
        f"- Hub 来源：`{len(health.get('hub_sources', []))}`",
        f"- 修复候选：`{len(health.get('link_suggestions', []))}`",
        f"- 修复动作：`{health.get('action_counts', {}).get('total', 0)}`",
        f"- 动作已到期：`{health.get('action_counts', {}).get('overdue', 0)}`",
        f"- 动作需升级：`{health.get('action_counts', {}).get('escalated', 0)}`",
        f"- 执行批次：`{health.get('repair_plan', {}).get('counts', {}).get('batches', 0)}`",
        f"- 执行提案：`{health.get('repair_plan', {}).get('counts', {}).get('proposals', 0)}`",
        f"- 页级 patch step：`{health.get('repair_plan', {}).get('counts', {}).get('patch_steps', 0)}`",
        f"- 概念冲突信号：`{health.get('concept_quality', {}).get('counts', {}).get('conflict_signals', 0)}`",
        f"- 概念重写候选：`{health.get('concept_quality', {}).get('counts', {}).get('rewrite_candidates', 0)}`",
        f"- Rewrite 提案：`{health.get('concept_rewrite', {}).get('counts', {}).get('active', 0)}`",
        f"- 可应用 Rewrite：`{health.get('concept_rewrite', {}).get('counts', {}).get('apply_ready', 0)}`",
        "",
        "## 判断层",
        f"- Judgment asset 节点：`{len(judgment_nodes)}`",
        f"- Judgment review actions：`{len(health.get('judgment_review_actions', []))}`",
        "- 决策索引：`wiki/indexes/decisions.md`",
        "- 判断索引：`wiki/indexes/judgments.md`",
        "- 审阅队列：`wiki/indexes/review-queue.md`",
        "",
        "## 漂移摘要",
        f"- 缺失 raw 文件：`{len(drift['missing_raw_files'])}`",
        f"- 缺失来源页：`{len(drift['missing_source_pages'])}`",
        f"- 缺失概念页：`{len(drift['missing_concept_pages'])}`",
        f"- 无概念覆盖来源：`{len(drift['sources_without_concepts'])}`",
        "",
        "## 相关链接",
        "- [图谱健康](./graph-health.md)",
        "- [拓扑视图](./machine-memory-topology.md)",
        "- [动作队列](./machine-memory-actions.md)",
        "- [修复计划](./machine-memory-repair-plan.md)",
        "- [漂移报告](./drift-report.md)",
        "- [修复待办](./repair-backlog.md)",
        "- [概念质量](./concept-quality.md)",
        "- [Rewrite Proposals](./rewrite-proposals.md)",
        "",
        "## Action Workflow",
        f"- 状态文件：`{health.get('action_state_path', '.aiwiki/state/machine-memory-actions.json')}`",
        "- 通过 `review-queue --bucket mm_actions` 查看 machine-memory action 状态。",
        "- nightly 会继续追踪 action 的 occurrences、aging 和 escalation。",
        "- repair 计划页：`wiki/indexes/machine-memory-repair-plan.md`",
        "",
        "## 查询加速",
        "- `ask` 和 `run-ask` 先用机器记忆 term index 做第一轮查询规划。",
        "- source-to-concept 和 concept-to-concept 边会在组装 prompt 前扩展候选范围。",
        "- 查询规划还会提取最短图路径和触达分量，支持更深的检索。",
        "- 图谱导出主要给 agent / tooling 使用，不建议直接人工修改。",
        "",
        "## 重点概念",
    ]
    if not concept_nodes:
        lines.append("- 还没有编译出概念节点。")
    else:
        for node in sorted(
            concept_nodes,
            key=lambda item: (-len(item["source_pages"]), item["title"].lower()),
        )[:10]:
            lines.append(
                f"- [{node['title']}](../concepts/{node['slug']}.md) "
                f"({len(node['source_pages'])} source(s), {len(node['related_slugs'])} related concept(s))"
            )
    lines.extend(
        [
            "",
            "## 运行时规则",
            "- [规则索引](../../schema/index.md)",
            "- [引用规则](../../schema/citations.md)",
            "- [冲突规则](../../schema/conflicts.md)",
            "- [审阅规则](../../schema/review.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_machine_memory_actions(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    actions = health.get("actions", [])
    inactive_actions = health.get("inactive_actions", [])
    overdue_actions = health.get("overdue_actions", [])
    escalated_actions = health.get("escalated_actions", [])
    planner_state = health.get("repair_plan", {}).get("planner_state", {})
    planner_queue = planner_state.get("priority_queue", [])
    planner_next_action = planner_state.get("next_action", {})
    recent_receipts = sorted(
        [
            action
            for action in [*actions, *inactive_actions]
            if action.get("last_receipt_path")
        ],
        key=lambda item: str(item.get("status_updated_at") or item.get("reviewed_at") or ""),
        reverse=True,
    )
    counts = health.get("action_counts", {})
    by_priority = counts.get("by_priority", {})
    by_status = counts.get("by_status", {})
    kind_labels = {
        "add-source-concept-link": "补链动作",
        "connect-isolated-source": "孤立来源动作",
        "expand-singleton-concept": "单节点概念动作",
        "split-overloaded-concept": "过载概念动作",
        "monitor-bridge-concept": "桥接概念观察",
        "refresh-citation-snapshots": "引用快照刷新",
    }
    lines = [
        "# 机器记忆动作队列",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        f"- 动作总数：`{counts.get('total', 0)}`",
        f"- 高优先级：`{by_priority.get('high', 0)}`",
        f"- 中优先级：`{by_priority.get('medium', 0)}`",
        f"- 低优先级：`{by_priority.get('low', 0)}`",
        f"- 已到期：`{counts.get('overdue', 0)}`",
        f"- 已升级：`{counts.get('escalated', 0)}`",
        f"- 已清除：`{counts.get('inactive', 0)}`",
        f"- 状态文件：`{health.get('action_state_path', '.aiwiki/state/machine-memory-actions.json')}`",
        "",
        "## 状态分布",
    ]
    for status in ACTION_STATUSES:
        lines.append(f"- `{display_action_status(status)}`：`{by_status.get(status, 0)}`")
    lines.extend(["", "## Planner"])
    lines.append(
        f"- Planner state：`{planner_state.get('state_path', '.aiwiki/state/planner-state.json') or '.aiwiki/state/planner-state.json'}`"
    )
    lines.append(f"- Pending proposals：`{planner_state.get('counts', {}).get('pending_proposals', 0)}`")
    lines.append(f"- Blocked proposals：`{planner_state.get('counts', {}).get('blocked', 0)}`")
    if planner_next_action:
        lines.append(
            f"- Next action：`{planner_next_action.get('action_id', '')}`"
            f" | {planner_next_action.get('title', '')}"
            f" | score `{planner_next_action.get('priority_score', 0)}`"
        )
    else:
        lines.append("- Next action：`none`")
    if planner_queue:
        lines.append("- Planner queue:")
        for item in planner_queue[:4]:
            lines.append(
                f"  - `{item.get('action_id', '')}`"
                f" | {item.get('title', '')}"
                f" | score `{item.get('priority_score', 0)}`"
                f" | blocked `{item.get('blocked', False)}`"
            )
    lines.extend(
        [
            "",
            "## 已升级动作",
        ]
    )
    if not escalated_actions:
        lines.append("- 当前没有需要升级处理的动作。")
    else:
        for action in escalated_actions[:8]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f"{detail}"
                f" | occurrences `{action.get('occurrences', 0)}`"
            )
    lines.extend(
        [
            "",
            "## 已到期动作",
        ]
    )
    if not overdue_actions:
        lines.append("- 当前没有已到期待处理的动作。")
    else:
        for action in overdue_actions[:8]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f"{detail}"
                f" | revisit `{action.get('revisit_after', '') or 'none'}`"
            )
    lines.extend(
        [
            "",
        "## 优先队列",
        ]
    )
    if not actions:
        lines.append("- 当前没有 machine-memory 动作。")
    else:
        for action in actions[:12]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            action_status = display_action_status(str(action.get("status")))
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | status `{action_status}`"
                f" | band `{action.get('execution_band', 'review-first')}`"
                f" | policy `{action.get('execution_policy', 'triage')}`"
                f" | primary `{action['primary_path']}`"
                f"{detail}"
                f" | occurrences `{action.get('occurrences', 0)}`"
                f" | component `{action.get('component_id') or 'none'}`"
            )
    for kind, label in kind_labels.items():
        lines.extend(["", f"## {label}"])
        kind_actions = [action for action in actions if action.get("kind") == kind]
        if not kind_actions:
            lines.append("- 当前没有此类动作。")
            continue
        for action in kind_actions[:8]:
            paths = [f"primary `{action['primary_path']}`"]
            if action.get("secondary_path"):
                paths.append(f"secondary `{action['secondary_path']}`")
            action_status = display_action_status(str(action.get("status")))
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | status `{action_status}`"
                f" | band `{action.get('execution_band', 'review-first')}`"
                f" | policy `{action.get('execution_policy', 'triage')}`"
                f" | {' | '.join(paths)}"
                f" | first `{action.get('first_seen_at', '') or 'none'}`"
                f" | seen `{action.get('occurrences', 0)}`"
                f" | {action.get('reason', '') or 'no reason'}"
            )
    lines.extend(["", "## 最近清除"])
    if not inactive_actions:
        lines.append("- 当前没有最近清除的动作。")
    else:
        for action in inactive_actions[:8]:
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | last_seen `{action.get('last_seen_at', '') or 'none'}`"
                f" | inactive_since `{action.get('inactive_since', '') or 'none'}`"
            )
    lines.extend(["", "## 最近执行回执"])
    if not recent_receipts:
        lines.append("- 当前还没有 safe execution receipt。")
    else:
        for action in recent_receipts[:8]:
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | receipt `{action.get('last_receipt_path', '')}`"
                f" | updated `{action.get('status_updated_at', '') or action.get('reviewed_at', '') or 'none'}`"
            )
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [机器记忆](./machine-memory.md)",
            "- [拓扑视图](./machine-memory-topology.md)",
            "- [修复计划](./machine-memory-repair-plan.md)",
            "- [图谱健康](./graph-health.md)",
            "- [修复待办](./repair-backlog.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_machine_memory_repair_plan(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    counts = plan.get("counts", {})
    ready_actions = plan.get("ready_actions", [])
    triage_actions = plan.get("triage_actions", [])
    deferred_actions = plan.get("deferred_actions", [])
    inactive_actions = plan.get("inactive_actions", [])
    execution_batches = plan.get("execution_batches", [])
    execution_proposals = plan.get("execution_proposals", [])
    planner_state = plan.get("planner_state", {})
    lines = [
        "# 机器记忆修复计划",
        "",
        f"- 最近编译时间：`{memory['compiled_at']}`",
        f"- Ready 动作：`{counts.get('ready', 0)}`",
        f"- 待分流动作：`{counts.get('triage', 0)}`",
        f"- 暂缓动作：`{counts.get('deferred', 0)}`",
        f"- 最近清除：`{counts.get('inactive', 0)}`",
        f"- 执行批次：`{counts.get('batches', 0)}`",
        f"- 执行提案：`{counts.get('proposals', 0)}`",
        f"- 页级 patch step：`{counts.get('patch_steps', 0)}`",
        f"- Blocked proposals：`{counts.get('blocked_proposals', 0)}`",
        f"- 状态文件：`{health.get('action_state_path', '.aiwiki/state/machine-memory-actions.json')}`",
        "",
        "## Planner State",
    ]
    if not planner_state:
        lines.append("- 当前还没有 planner state。")
    else:
        next_action = planner_state.get("next_action", {})
        lines.append(
            f"- Planner state：`{planner_state.get('state_path', '.aiwiki/state/planner-state.json') or '.aiwiki/state/planner-state.json'}`"
        )
        lines.append(f"- Pending proposals：`{planner_state.get('counts', {}).get('pending_proposals', 0)}`")
        lines.append(f"- Unblocked：`{planner_state.get('counts', {}).get('unblocked', 0)}`")
        lines.append(f"- Blocked：`{planner_state.get('counts', {}).get('blocked', 0)}`")
        if next_action:
            lines.append(
                f"- Next action：`{next_action.get('action_id', '')}`"
                f" | {next_action.get('title', '')}"
                f" | score `{next_action.get('priority_score', 0)}`"
                f" | blocked `{next_action.get('blocked', False)}`"
            )
        queue = planner_state.get("priority_queue", [])
        if queue:
            lines.append("- Priority queue:")
            for item in queue[:6]:
                lines.append(
                    f"  - `{item.get('action_id', '')}`"
                    f" | {item.get('title', '')}"
                    f" | score `{item.get('priority_score', 0)}`"
                    f" | impact `{item.get('impact_score', 0)}`"
                    f" | blocked `{item.get('blocked', False)}`"
                )
    lines.extend(
        [
            "",
        "## Ready Now",
        ]
    )
    if not ready_actions:
        lines.append("- 当前没有 ready action。")
    else:
        for action in ready_actions[:10]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            command_hint = action.get("command_hint", "")
            command_part = f" | command `{command_hint}`" if command_hint else ""
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f"{detail}"
                f" | band `{action.get('execution_band', 'review-first')}`"
                f" | next {action.get('next_step', 'n/a')}"
                f"{command_part}"
            )
    lines.extend(["", "## Need Triage"])
    if not triage_actions:
        lines.append("- 当前没有待分流动作。")
    else:
        for action in triage_actions[:10]:
            command_hint = action.get("command_hint", "")
            command_part = f" | command `{command_hint}`" if command_hint else ""
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f" | band `{action.get('execution_band', 'review-first')}`"
                f" | next {action.get('next_step', 'n/a')}"
                f"{command_part}"
            )
    lines.extend(["", "## Deferred"])
    if not deferred_actions:
        lines.append("- 当前没有暂缓动作。")
    else:
        for action in deferred_actions[:10]:
            command_hint = action.get("command_hint", "")
            command_part = f" | command `{command_hint}`" if command_hint else ""
            lines.append(
                f"- [{action['priority']}] {action['title']}"
                f" | primary `{action['primary_path']}`"
                f" | revisit `{action.get('revisit_after', '') or 'none'}`"
                f" | band `{action.get('execution_band', 'review-first')}`"
                f"{command_part}"
            )
    lines.extend(["", "## Execution Batches"])
    if not execution_batches:
        lines.append("- 当前没有可执行批次。")
    else:
        for batch in execution_batches[:8]:
            lines.append(
                f"- {batch['label']}"
                f" | actions `{len(batch.get('actions', []))}`"
                f" | escalated `{batch.get('escalated', False)}`"
                f" | overdue `{batch.get('overdue', False)}`"
                f" | primary `{', '.join(batch.get('primary_paths', [])) or 'none'}`"
            )
            for action in batch.get("actions", [])[:4]:
                command_hint = action.get("command_hint", "")
                command_part = f" | command `{command_hint}`" if command_hint else ""
                lines.append(
                    f"  action [{action['priority']}] {action['title']}"
                    f" | status `{display_action_status(str(action.get('status')))}`"
                    f" | next {action.get('next_step', 'n/a')}"
                    f"{command_part}"
                )
    lines.extend(["", "## Execution Proposals"])
    if not execution_proposals:
        lines.append("- 当前没有页级执行提案。")
    else:
        for proposal in execution_proposals[:10]:
            command_part = f" | command `{proposal['command_hint']}`" if proposal.get("command_hint") else ""
            lines.append(
                f"- [{proposal['priority']}] {proposal['title']}"
                f" | status `{display_action_status(str(proposal.get('status')))}`"
                f" | kind `{proposal.get('proposal_kind', 'manual-repair')}`"
                f" | risk `{proposal.get('risk', 'medium')}`"
                f" | score `{proposal.get('priority_score', 0)}`"
                f" | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
                f"{command_part}"
            )
            lines.append(f"  - strategy: {proposal.get('summary', 'n/a')}")
            lines.append(f"  - bundle: `{proposal.get('bundle_path', '') or 'none'}`")
            lines.append(f"  - rollback: {proposal.get('rollback_summary', 'n/a')}")
            if proposal.get("depends_on"):
                lines.append(f"  - depends_on: `{', '.join(proposal.get('depends_on', []))}`")
            for edit in proposal.get("suggested_edits", [])[:3]:
                lines.append(f"  - edit: {edit}")
            patch_plan = proposal.get("page_patch_plan", [])
            if patch_plan:
                for patch in patch_plan[:4]:
                    sections = ", ".join(patch.get("sections", [])) or "none"
                    lines.append(
                        f"  - patch `{patch.get('path', '')}`"
                        f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                        f" | mode `{patch.get('mode', 'update')}`"
                        f" | sections `{sections}`"
                    )
    lines.extend(["", "## Page-Level Patch Plans"])
    if not execution_proposals:
        lines.append("- 当前没有页级 patch plan。")
    else:
        for proposal in execution_proposals[:8]:
            patch_plan = proposal.get("page_patch_plan", [])
            if not patch_plan:
                continue
            lines.append(
                f"### `{proposal.get('action_id', 'proposal')}` · {proposal.get('title', 'unnamed proposal')}"
            )
            lines.append(f"- Summary: {proposal.get('summary', 'n/a')}")
            lines.append(f"- Risk: `{proposal.get('risk', 'medium')}` | Protocol: `{proposal.get('protocol', DEFAULT_PROTOCOL)}`")
            for patch in patch_plan:
                sections = ", ".join(patch.get("sections", [])) or "none"
                command_hint = str(patch.get("command_hint") or "")
                lines.append(
                    f"- `{patch.get('path', '')}`"
                    f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                    f" | mode `{patch.get('mode', 'update')}`"
                    f" | sections `{sections}`"
                    f" | exists `{patch.get('exists', False)}`"
                )
                lines.append(f"  - {patch.get('summary', '检查相关页面并补充修复说明。')}")
                if command_hint:
                    lines.append(f"  - command: `{command_hint}`")
    lines.extend(["", "## Recently Cleared"])
    if not inactive_actions:
        lines.append("- 当前没有最近清除动作。")
    else:
        for action in inactive_actions[:10]:
            command_hint = action.get("command_hint", "")
            command_part = f" | command `{command_hint}`" if command_hint else ""
            lines.append(
                f"- [{display_action_status(str(action.get('status')))}] {action['title']}"
                f" | inactive_since `{action.get('inactive_since', '') or 'none'}`"
                f" | next {action.get('next_step', 'n/a')}"
                f"{command_part}"
            )
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [动作队列](./machine-memory-actions.md)",
            "- [机器记忆](./machine-memory.md)",
            "- [图谱健康](./graph-health.md)",
            "- [修复待办](./repair-backlog.md)",
        ]
    )
    return "\n".join(lines) + "\n"

