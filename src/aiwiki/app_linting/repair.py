"""Lint and nightly health helpers extracted from app_compile."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..lifecycle.status import (
    display_action_status,
    display_curated_status,
    display_rewrite_proposal_status,
)
from ..memory.action_core import (
    action_supports_low_risk_apply,
)
from ..protocol.descriptors import protocol_title
from ..protocol.library import PROTOCOL_LIBRARY


@dataclass(frozen=True)
class RepairBacklogContext:
    compile_result: dict[str, Any]
    lint_result: dict[str, Any]
    active_protocol: str
    promotion_result: dict[str, Any]
    pending_sources: list[str]
    placeholder_concepts: list[str]
    pending_review_decisions: list[dict[str, str]]
    pending_review_judgments: list[dict[str, str]]
    overdue_pages: list[dict[str, str]]
    escalated_pages: list[dict[str, str]]
    semantic_report: str
    generated_at: str
    health: dict[str, Any]
    transition: dict[str, Any]
    error_findings: list[dict[str, Any]]
    warn_findings: list[dict[str, Any]]
    sources_without_concepts: list[str]
    isolated_sources: list[str]
    singleton_concepts: list[str]
    bridge_concepts: list[str]
    overloaded_concepts: list[str]
    actions: list[dict[str, Any]]
    overdue_actions: list[dict[str, Any]]
    escalated_actions: list[dict[str, Any]]
    inactive_actions: list[dict[str, Any]]
    repair_plan: dict[str, Any]
    concept_quality: dict[str, Any]
    rewrite_state: dict[str, Any]
    rewrite_proposals: list[dict[str, Any]]
    apply_ready_rewrites: list[dict[str, Any]]
    apply_ready_actions: list[dict[str, Any]]
    execution_proposals: list[dict[str, Any]]
    counter_evidence_pages: list[Any]
    judgment_review_actions: list[Any]
    promotions: list[dict[str, Any]]


def render_repair_backlog(
    compile_result: dict[str, Any],
    lint_result: dict[str, Any],
    memory: dict[str, Any],
    active_protocol: str,
    promotion_result: dict[str, Any],
    pending_sources: list[str],
    placeholder_concepts: list[str],
    pending_review_decisions: list[dict[str, str]],
    pending_review_judgments: list[dict[str, str]],
    overdue_pages: list[dict[str, str]],
    escalated_pages: list[dict[str, str]],
    semantic_report: str,
    generated_at: str,
) -> str:
    drift = memory.get("drift", {})
    health = memory.get("health", {})
    transition = memory.get("transition", {})
    findings = lint_result.get("findings", [])
    error_findings = [finding for finding in findings if finding["severity"] == "error"]
    warn_findings = [finding for finding in findings if finding["severity"] == "warn"]
    sources_without_concepts = drift.get("sources_without_concepts", [])
    isolated_sources = health.get("isolated_source_ids", [])
    singleton_concepts = health.get("singleton_concept_slugs", [])
    bridge_concepts = health.get("bridge_concept_slugs", [])
    overloaded_concepts = health.get("overloaded_concept_slugs", [])
    actions = health.get("actions", [])
    overdue_actions = health.get("overdue_actions", [])
    escalated_actions = health.get("escalated_actions", [])
    inactive_actions = health.get("inactive_actions", [])
    repair_plan = health.get("repair_plan", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]
    apply_ready_actions = [action for action in actions if action_supports_low_risk_apply(action)]
    execution_proposals = repair_plan.get("execution_proposals", [])
    counter_evidence_scan = health.get("counter_evidence_scan", {})
    counter_evidence_pages = counter_evidence_scan.get("pages", []) if isinstance(counter_evidence_scan, dict) else []
    judgment_review_actions = health.get("judgment_review_actions", [])
    promotions = promotion_result.get("pages", [])
    ctx = RepairBacklogContext(
        compile_result=compile_result,
        lint_result=lint_result,
        active_protocol=active_protocol,
        promotion_result=promotion_result,
        pending_sources=pending_sources,
        placeholder_concepts=placeholder_concepts,
        pending_review_decisions=pending_review_decisions,
        pending_review_judgments=pending_review_judgments,
        overdue_pages=overdue_pages,
        escalated_pages=escalated_pages,
        semantic_report=semantic_report,
        generated_at=generated_at,
        health=health,
        transition=transition,
        error_findings=error_findings,
        warn_findings=warn_findings,
        sources_without_concepts=sources_without_concepts,
        isolated_sources=isolated_sources,
        singleton_concepts=singleton_concepts,
        bridge_concepts=bridge_concepts,
        overloaded_concepts=overloaded_concepts,
        actions=actions,
        overdue_actions=overdue_actions,
        escalated_actions=escalated_actions,
        inactive_actions=inactive_actions,
        repair_plan=repair_plan,
        concept_quality=concept_quality,
        rewrite_state=rewrite_state,
        rewrite_proposals=rewrite_proposals,
        apply_ready_rewrites=apply_ready_rewrites,
        apply_ready_actions=apply_ready_actions,
        execution_proposals=execution_proposals,
        counter_evidence_pages=counter_evidence_pages,
        judgment_review_actions=judgment_review_actions,
        promotions=promotions,
    )
    return _render_backlog_markdown(ctx)


def _render_backlog_markdown(ctx: RepairBacklogContext) -> str:
    lines = [
        "# 修复待办",
        "",
        f"- 生成时间：`{ctx.generated_at}`",
        f"- 当前协议焦点：`{ctx.active_protocol}` ({protocol_title(ctx.active_protocol)})",
        f"- 本轮编译改动页数：`{ctx.compile_result.get('changed_pages', 0)}`",
        f"- 机器记忆是否变化：`{ctx.compile_result.get('machine_memory_changed', False)}`",
        f"- Lint 错误：`{ctx.lint_result['counts']['errors']}`",
        f"- Lint 警告：`{ctx.lint_result['counts']['warnings']}`",
        f"- 待补来源摘要：`{len(ctx.pending_sources)}`",
        f"- 占位概念摘要：`{len(ctx.placeholder_concepts)}`",
        f"- 待审决策：`{len(ctx.pending_review_decisions)}`",
        f"- 待审判断：`{len(ctx.pending_review_judgments)}`",
        f"- 已到期复审：`{len(ctx.overdue_pages)}`",
        f"- 升级处理项：`{len(ctx.escalated_pages)}`",
        f"- 自动晋升页面：`{ctx.promotion_result.get('count', 0)}`",
        f"- 图谱修复动作：`{len(ctx.actions)}`",
        f"- 动作已到期：`{len(ctx.overdue_actions)}`",
        f"- 动作需升级：`{len(ctx.escalated_actions)}`",
        f"- 最近清除动作：`{len(ctx.inactive_actions)}`",
        f"- Ready 动作：`{ctx.repair_plan.get('counts', {}).get('ready', 0)}`",
        f"- 待分流动作：`{ctx.repair_plan.get('counts', {}).get('triage', 0)}`",
        f"- 执行批次：`{ctx.repair_plan.get('counts', {}).get('batches', 0)}`",
        f"- 执行提案：`{ctx.repair_plan.get('counts', {}).get('proposals', 0)}`",
        f"- 弱概念页：`{ctx.concept_quality.get('counts', {}).get('weak', 0)}`",
        f"- Soft 概念页：`{ctx.concept_quality.get('counts', {}).get('soft_hardness', 0)}`",
        f"- Medium+/Hard 概念页：`{ctx.concept_quality.get('counts', {}).get('medium_or_hard', 0)}`",
        f"- 概念合并候选：`{ctx.concept_quality.get('counts', {}).get('merge_candidates', 0)}`",
        f"- 概念冲突信号：`{ctx.concept_quality.get('counts', {}).get('conflict_signals', 0)}`",
        f"- 概念证据缺口：`{ctx.concept_quality.get('counts', {}).get('gap_signals', 0)}`",
        f"- Rewrite 提案：`{ctx.rewrite_state.get('counts', {}).get('active', 0)}`",
        f"- 待审 Rewrite：`{ctx.rewrite_state.get('counts', {}).get('pending_review', 0)}`",
        f"- 可应用 Rewrite：`{len(ctx.apply_ready_rewrites)}`",
        f"- 可安全执行动作：`{len(ctx.apply_ready_actions)}`",
        f"- Counter-evidence candidates：`{len(ctx.counter_evidence_pages)}`",
        f"- Judgment review actions：`{len(ctx.judgment_review_actions)}`",
        f"- 图谱修复候选：`{len(ctx.health.get('link_suggestions', []))}`",
        f"- 无概念覆盖来源：`{len(ctx.sources_without_concepts)}`",
        f"- 图谱分量数：`{ctx.health.get('component_count', 0)}`",
        f"- 孤立来源：`{len(ctx.isolated_sources)}`",
        f"- 单节点概念：`{len(ctx.singleton_concepts)}`",
        f"- 桥接概念：`{len(ctx.bridge_concepts)}`",
        f"- 过载概念：`{len(ctx.overloaded_concepts)}`",
        "",
        "## 优先队列",
    ]
    if PROTOCOL_LIBRARY.get(ctx.active_protocol, {}).get("nightly"):
        lines.extend(["### 协议 Nightly 焦点"])
        for focus in PROTOCOL_LIBRARY.get(ctx.active_protocol, {}).get("nightly", []):
            lines.append(f"- {focus}")
        lines.append("")
    if ctx.error_findings:
        lines.append(f"1. 先解决 `{len(ctx.error_findings)}` 个 lint 错误，再继续依赖下游输出。")
    if ctx.pending_sources:
        lines.append(f"2. 补齐 `{len(ctx.pending_sources)}` 个仍是占位摘要的来源页。")
    if ctx.placeholder_concepts:
        lines.append(f"3. 重写 `{len(ctx.placeholder_concepts)}` 个仍使用回退摘要的概念页。")
    if ctx.concept_quality.get("counts", {}).get("weak", 0):
        lines.append(f"3a. 按概念质量看板优先处理 `{ctx.concept_quality.get('counts', {}).get('weak', 0)}` 个弱概念页。")
    if ctx.concept_quality.get("counts", {}).get("soft_hardness", 0):
        lines.append(
            f"3d. 把 `{ctx.concept_quality.get('counts', {}).get('soft_hardness', 0)}` 个仍停留在 `hardness: soft` 的概念页提升到更可复用的结构层。"
        )
    if ctx.rewrite_state.get("counts", {}).get("pending_review", 0):
        lines.append(
            f"3b. 先审 `{ctx.rewrite_state.get('counts', {}).get('pending_review', 0)}` 个 concept rewrite proposal。"
        )
    if ctx.apply_ready_rewrites:
        lines.append(f"3c. 应用 `{len(ctx.apply_ready_rewrites)}` 个已接受的 concept rewrite proposal，让概念页先收敛。")
    if ctx.pending_review_decisions:
        lines.append(f"4. 审阅 `{len(ctx.pending_review_decisions)}` 个等待批准或复审的决策页。")
    if ctx.pending_review_judgments:
        lines.append(f"5. 审阅 `{len(ctx.pending_review_judgments)}` 个仍处于暂定或跟踪状态的判断页。")
    if ctx.overdue_pages:
        lines.append(f"6. 先清理 `{len(ctx.overdue_pages)}` 个已到期但还没复审的页面。")
    if ctx.escalated_pages:
        lines.append(f"7. 提升 `{len(ctx.escalated_pages)}` 个已经超过升级阈值的页面优先级。")
    if ctx.counter_evidence_pages:
        lines.append(f"7a. 审阅 `{len(ctx.counter_evidence_pages)}` 个新 source 触发的 counter-evidence candidate。")
    if ctx.judgment_review_actions:
        lines.append(
            f"7b. 执行 `{len(ctx.judgment_review_actions)}` 个 judgment review action，把升级项推进进显式 review workflow。"
        )
    if ctx.promotions:
        lines.append(f"8. 检查本轮自动晋升的 `{len(ctx.promotions)}` 个页面，确认是否需要补证据和审阅。")
    if ctx.actions:
        lines.append(f"9. 按动作队列处理 `{len(ctx.actions)}` 个 machine-memory 修复动作。")
    if ctx.repair_plan.get("counts", {}).get("ready", 0):
        lines.append(
            f"9a. 先执行 `{ctx.repair_plan.get('counts', {}).get('ready', 0)}` 个已接受动作和 `{ctx.repair_plan.get('counts', {}).get('batches', 0)}` 个批次。"
        )
    if ctx.repair_plan.get("counts", {}).get("proposals", 0):
        lines.append(f"9b. 参考 `{ctx.repair_plan.get('counts', {}).get('proposals', 0)}` 个页级执行提案决定下一批修复。")
    if ctx.apply_ready_actions:
        lines.append(f"9c. 其中 `{len(ctx.apply_ready_actions)}` 个低风险动作可在 advanced review-queue 中查看。")
    if ctx.overdue_actions:
        lines.append(f"10. 优先清理 `{len(ctx.overdue_actions)}` 个已到期待处理的 machine-memory 动作。")
    if ctx.escalated_actions:
        lines.append(f"11. 先处理 `{len(ctx.escalated_actions)}` 个已升级的 machine-memory 动作。")
    if ctx.concept_quality.get("counts", {}).get("conflict_signals", 0):
        lines.append(
            f"11a. 先把 `{ctx.concept_quality.get('counts', {}).get('conflict_signals', 0)}` 个概念冲突信号显式写进相关概念页。"
        )
    if ctx.health.get("link_suggestions", []):
        lines.append(f"12. 审阅 `{len(ctx.health.get('link_suggestions', []))}` 个机器记忆补链候选，决定是否补链接。")
    if ctx.sources_without_concepts:
        lines.append(f"13. 检查 `{len(ctx.sources_without_concepts)}` 个没有概念覆盖的来源。")
    if ctx.isolated_sources:
        lines.append(f"14. 把 `{len(ctx.isolated_sources)}` 个孤立来源节点接入概念图谱。")
    if ctx.singleton_concepts:
        lines.append(f"15. 复查 `{len(ctx.singleton_concepts)}` 个还没接入更大上下文的单节点概念。")
    if ctx.overloaded_concepts:
        lines.append(f"16. 考虑拆分 `{len(ctx.overloaded_concepts)}` 个过载概念。")
    if ctx.transition.get("changed"):
        lines.append("17. 在下一轮研究前先检查最新的机器记忆漂移。")
    if not any(
        (
            ctx.error_findings,
            ctx.pending_sources,
            ctx.placeholder_concepts,
            ctx.pending_review_decisions,
            ctx.pending_review_judgments,
            ctx.overdue_pages,
            ctx.escalated_pages,
            ctx.promotions,
            ctx.sources_without_concepts,
            ctx.isolated_sources,
            ctx.singleton_concepts,
            ctx.overloaded_concepts,
            ctx.transition.get("changed"),
        )
    ):
        lines.append("1. 当前没有紧急修复项，继续观察 nightly 漂移和 lint 输出。")
    lines.extend(
        [
            "",
            "## 可执行事项",
        ]
    )
    if ctx.error_findings:
        lines.append("### Lint 错误")
        for finding in ctx.error_findings[:10]:
            lines.append(f"- `{finding['path']}`: {finding['message']}")
    if ctx.warn_findings:
        lines.append("")
        lines.append("### Lint 警告")
        for finding in ctx.warn_findings[:10]:
            lines.append(f"- `{finding['path']}`: {finding['message']}")
    if ctx.pending_sources:
        lines.append("")
        lines.append("### 待补来源摘要")
        for source_id in ctx.pending_sources[:10]:
            lines.append(f"- `wiki/sources/{source_id}.md`")
    if ctx.placeholder_concepts:
        lines.append("")
        lines.append("### 占位概念摘要")
        for slug in ctx.placeholder_concepts[:10]:
            lines.append(f"- `wiki/concepts/{slug}.md`")
    if ctx.pending_review_decisions or ctx.pending_review_judgments:
        lines.append("")
        lines.append("### 审阅队列")
        for page in ctx.pending_review_decisions[:10]:
            lines.append(f"- 决策：`{page['path']}` 状态 `{display_curated_status(page['status'])}`")
        for page in ctx.pending_review_judgments[:10]:
            lines.append(f"- 判断：`{page['path']}` 状态 `{display_curated_status(page['status'])}`")
    if ctx.overdue_pages or ctx.escalated_pages:
        lines.append("")
        lines.append("### Aging 信号")
        for page in ctx.escalated_pages[:10]:
            lines.append(f"- 升级：`{page['path']}` | 状态 `{display_curated_status(page['status'])}`")
        for page in ctx.overdue_pages[:10]:
            if page in ctx.escalated_pages[:10]:
                continue
            lines.append(f"- 到期：`{page['path']}` | 状态 `{display_curated_status(page['status'])}`")
    if ctx.counter_evidence_pages:
        lines.append("")
        lines.append("### Counter-evidence Candidates")
        for candidate in ctx.counter_evidence_pages[:10]:
            if not isinstance(candidate, dict):
                continue
            lines.append(
                f"- `{candidate.get('page_path', '')}`"
                f" | candidates `{candidate.get('candidate_count', 0)}`"
                f" | sources `{', '.join(candidate.get('source_ids', [])) or 'none'}`"
                f" | shared `{', '.join(candidate.get('shared_terms', [])) or 'none'}`"
            )
    if ctx.judgment_review_actions:
        lines.append("")
        lines.append("### Judgment Review Actions")
        for action in ctx.judgment_review_actions[:10]:
            if not isinstance(action, dict):
                continue
            command = str(action.get("review_command") or "")
            command_suffix = f" | command `{command}`" if command else ""
            lines.append(
                f"- `{action.get('title', 'review action')}`"
                f" | priority `{action.get('priority', 'medium')}`"
                f" | reasons `{', '.join(action.get('reason_codes', [])) or 'none'}`"
                f"{command_suffix}"
            )
    if ctx.promotions:
        lines.append("")
        lines.append("### 本轮自动晋升")
        for promotion in ctx.promotions[:10]:
            label = "决策" if promotion["kind"] == "decision" else "判断"
            lines.append(
                f"- {label}：`{promotion['path']}` | 动作 `{promotion['action']}` | 重复次数 `{promotion['occurrences']}`"
            )
    lines.append("")
    lines.append("### Machine Memory 动作")
    if ctx.actions:
        for action in ctx.actions[:10]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            action_status = display_action_status(str(action.get("status")))
            lines.append(
                f"- [{action['priority']}] `{action['primary_path']}`"
                f"{detail}"
                f" | {action['title']}"
                f" | status `{action_status}`"
                f" | seen `{action.get('occurrences', 0)}`"
            )
    else:
        lines.append("- 当前没有 machine-memory 动作。")
    if ctx.escalated_actions or ctx.overdue_actions:
        lines.append("")
        lines.append("### Action Aging")
        for action in ctx.escalated_actions[:10]:
            action_status = display_action_status(str(action.get("status")))
            lines.append(f"- 升级：`{action['id']}` | {action['title']} | status `{action_status}`")
        for action in ctx.overdue_actions[:10]:
            if any(action["id"] == escalated["id"] for escalated in ctx.escalated_actions[:10]):
                continue
            lines.append(
                f"- 到期：`{action['id']}` | {action['title']} | revisit `{action.get('revisit_after', '') or 'none'}`"
            )
    if ctx.inactive_actions:
        lines.append("")
        lines.append("### 最近清除动作")
        for action in ctx.inactive_actions[:10]:
            lines.append(
                f"- 清除：`{action['id']}` | {action['title']} | inactive_since `{action.get('inactive_since', '') or 'none'}`"
            )
    if ctx.concept_quality.get("weak_concepts"):
        lines.append("")
        lines.append("### 弱概念页")
        for concept in ctx.concept_quality.get("weak_concepts", [])[:10]:
            lines.append(
                f"- `{concept['path']}` | issues `{', '.join(concept.get('issues', [])) or 'none'}`"
                f" | sources `{concept.get('source_count', 0)}`"
            )
    if ctx.concept_quality.get("rewrite_candidates"):
        lines.append("")
        lines.append("### 概念重写优先级")
        for candidate in ctx.concept_quality.get("rewrite_candidates", [])[:8]:
            lines.append(
                f"- `{candidate['path']}` | priority `{candidate.get('priority', 'n/a')}`"
                f" | strategy `{candidate.get('rewrite_strategy', 'n/a')}`"
            )
    if ctx.rewrite_proposals:
        lines.append("")
        lines.append("### Rewrite Proposals")
        for proposal in ctx.rewrite_proposals[:8]:
            command = f"advanced review-queue — proposal `{proposal['slug']}`"
            if proposal.get("status") == "applied" and str(proposal.get("previous_markdown") or ""):
                command = f"library receipt / `advanced alchemy-revert` — proposal `{proposal['slug']}`"
            elif proposal.get("apply_ready"):
                command = f"advanced review-queue — proposal `{proposal['slug']}` (operator review)"
            lines.append(
                f"- `{proposal['target_path']}` | status `{display_rewrite_proposal_status(str(proposal.get('status') or 'proposed'))}`"
                f" | quality `{proposal.get('quality_score', 0)}`"
                f" | verify `{proposal.get('verification_status', '') or 'pending'}`"
                f" | strategy `{proposal.get('rewrite_strategy', 'n/a')}` | command `{command}`"
            )
    if ctx.concept_quality.get("conflict_signals"):
        lines.append("")
        lines.append("### 概念冲突信号")
        for signal in ctx.concept_quality.get("conflict_signals", [])[:8]:
            lines.append(
                f"- `{signal['slug']}` | signal `{signal.get('label', 'n/a')}`"
                f" | sources `{', '.join(signal.get('source_pages', [])) or 'none'}`"
            )
    if ctx.concept_quality.get("merge_candidates"):
        lines.append("")
        lines.append("### 概念合并候选")
        for candidate in ctx.concept_quality.get("merge_candidates", [])[:8]:
            lines.append(
                f"- `{candidate['left_slug']}` <-> `{candidate['right_slug']}`"
                f" | shared_sources `{len(candidate.get('shared_sources', []))}`"
                f" | shared_tokens `{', '.join(candidate.get('shared_tokens', [])) or 'none'}`"
            )
    if ctx.repair_plan.get("execution_batches"):
        lines.append("")
        lines.append("### 执行批次")
        for batch in ctx.repair_plan.get("execution_batches", [])[:8]:
            lines.append(
                f"- {batch['label']} | actions `{len(batch.get('actions', []))}`"
                f" | escalated `{batch.get('escalated', False)}`"
                f" | overdue `{batch.get('overdue', False)}`"
                f" | primary `{', '.join(batch.get('primary_paths', [])) or 'none'}`"
            )
    if ctx.execution_proposals:
        lines.append("")
        lines.append("### Repair Execution Proposals")
        for proposal in ctx.execution_proposals[:8]:
            lines.append(
                f"- `{proposal['action_id']}` | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
                f" | risk `{proposal.get('risk', 'medium')}`"
                f" | strategy `{proposal.get('summary', 'n/a')}`"
            )
    if ctx.apply_ready_actions:
        lines.append("")
        lines.append("### Safe Apply Actions")
        for action in ctx.apply_ready_actions[:8]:
            lines.append(
                f"- `{action['id']}` | `{action['title']}`"
                f" | command `{action.get('command_hint', '')}`"
                f" | primary `{action.get('primary_path', '')}`"
            )
    if ctx.health.get("link_suggestions", []):
        lines.append("")
        lines.append("### 图谱修复候选")
        for suggestion in ctx.health.get("link_suggestions", [])[:10]:
            lines.append(
                f"- `{suggestion['source_page']}` -> `{suggestion['concept_page']}`"
                f" | shared `{', '.join(suggestion['shared_terms'][:6])}`"
                f" | score `{suggestion['score']}`"
            )
    if ctx.sources_without_concepts:
        lines.append("")
        lines.append("### 无概念覆盖来源")
        for source_id in ctx.sources_without_concepts[:10]:
            lines.append(f"- `wiki/sources/{source_id}.md`")
    lines.append("")
    lines.append("### 图谱修复建议")
    if ctx.isolated_sources:
        for source_id in ctx.isolated_sources[:10]:
            lines.append(f"- 将孤立来源 `wiki/sources/{source_id}.md` 至少连接到一个稳定概念。")
    if ctx.singleton_concepts:
        for slug in ctx.singleton_concepts[:10]:
            lines.append(f"- 检查单节点概念 `wiki/concepts/{slug}.md` 是否缺少相关概念或来源链接。")
    if ctx.overloaded_concepts:
        for slug in ctx.overloaded_concepts[:10]:
            lines.append(f"- 考虑把过宽的概念 `wiki/concepts/{slug}.md` 拆成更窄的页面。")
    if ctx.bridge_concepts:
        lines.append(f"- 保留桥接概念：`{', '.join(ctx.bridge_concepts[:10])}`，因为它们连接了多个簇。")
    if not any((ctx.isolated_sources, ctx.singleton_concepts, ctx.overloaded_concepts, ctx.bridge_concepts)):
        lines.append("- 当前没有图谱专项修复项。")
    if ctx.transition.get("changed"):
        lines.append("")
        lines.append("### 结构漂移")
        lines.append(f"- 上一版摘要：`{ctx.transition.get('previous_digest', '') or 'none'}`")
        lines.append(f"- 当前摘要：`{ctx.transition.get('current_digest', '') or 'none'}`")
        lines.append(f"- 新增来源节点：`{len(ctx.transition.get('added_source_ids', []))}`")
        lines.append(f"- 新增概念节点：`{len(ctx.transition.get('added_concept_slugs', []))}`")
        lines.append(f"- 新增边：`{ctx.transition.get('added_edges', 0)}`")
        lines.append(f"- 移除边：`{ctx.transition.get('removed_edges', 0)}`")
    lines.extend(
        [
            "",
            "## 相关产物",
            f"- Lint 报告：`{ctx.lint_result['path']}`",
            "- 机器记忆：`wiki/indexes/machine-memory.md`",
            "- 审阅队列：`wiki/indexes/review-queue.md`",
            "- 规则索引：`schema/index.md`",
        ]
    )
    if ctx.semantic_report:
        lines.append(f"- 语义 lint：`{ctx.semantic_report}`")
    return "\n".join(lines) + "\n"
