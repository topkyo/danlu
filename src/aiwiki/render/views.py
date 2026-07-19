"""Dashboard view renderers extracted from app_render.

20 symbols (curated/judgment/review/aging + agent + furnace + master index +
pilots index + thin wrappers around app_surfaces).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..lifecycle.aging import collect_aging_signals
from ..lifecycle.knowledge import (
    default_knowledge_lifecycle_state,
    judgment_lifecycle_profile,
    knowledge_lifecycle_governance_summary,
    render_knowledge_lifecycle_entry_summary,
    select_knowledge_lifecycle_entries,
    sort_knowledge_lifecycle_entries,
)
from ..lifecycle.status import display_curated_status, review_queue
from ..protocol.descriptors import protocol_title
from ..protocol.focus_scoring import page_focus_score
from ..protocol.library import PROTOCOL_LIBRARY
from ..state.constants import DEFAULT_PROTOCOL, JUDGMENT_LIFECYCLE_STATES
from ..utils.markdown import render_frontmatter
from ..utils.text import human_query_title, slugify
from .packs import workspace_link


def render_curated_page_summary(page: dict[str, str]) -> str:
    suffix_parts = [f"状态 `{display_curated_status(page.get('status', '') or 'unknown')}`"]
    protocol = page.get("protocol", "")
    if protocol:
        suffix_parts.append(f"协议 `{protocol}`")
    confidence = page.get("confidence", "")
    if confidence:
        suffix_parts.append(f"置信度 `{confidence}`")
    reviewed_at = page.get("reviewed_at", "")
    if reviewed_at:
        suffix_parts.append(f"审阅时间 `{reviewed_at}`")
    revisit_after = page.get("revisit_after", "")
    if revisit_after:
        suffix_parts.append(f"复审截止 `{revisit_after}`")
    if page.get("asset_score"):
        suffix_parts.append(f"资产 `{page.get('asset_score')}/4`")
    review_history_entries = int(page.get("review_history_entries", "0") or "0")
    if review_history_entries:
        suffix_parts.append(f"复审历史 `{review_history_entries}`")
    citation_drift_count = int(page.get("citation_drift_count", "0") or "0")
    citation_snapshot_gap_count = int(page.get("citation_snapshot_gap_count", "0") or "0")
    if page.get("citation_drift") == "true":
        suffix_parts.append(f"证据漂移 `{citation_drift_count or 1}`")
    if citation_snapshot_gap_count:
        suffix_parts.append(f"快照缺口 `{citation_snapshot_gap_count}`")
    if page.get("overdue_review") == "true":
        suffix_parts.append("已到期待复审")
    if page.get("escalation_candidate") == "true":
        suffix_parts.append("需要升级处理")
    return f"- [{page['title']}](../../{page['path']}) | " + " | ".join(suffix_parts)


def judgment_asset_gap_codes(page: dict[str, str]) -> list[str]:
    if str(page.get("kind") or "") not in {"decision", "judgment"}:
        return []
    reasons: list[str] = []
    if page.get("has_counter_evidence") != "true":
        reasons.append("missing-counter-evidence")
    if page.get("has_invalidation") != "true":
        reasons.append("missing-invalidation")
    if page.get("has_next_signals") != "true":
        reasons.append("missing-next-signals")
    if page.get("has_review_history") != "true":
        reasons.append("missing-review-history")
    if page.get("citation_drift") == "true":
        reasons.append("citation-drift")
    if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0:
        reasons.append("citation-snapshot-gap")
    if page.get("has_counter_evidence_metadata") != "true":
        reasons.append("missing-counter-evidence-metadata")
    if page.get("has_invalidation_rule_metadata") != "true":
        reasons.append("missing-invalidation-rule-metadata")
    if page.get("has_next_signals_metadata") != "true":
        reasons.append("missing-next-signals-metadata")
    if page.get("has_formed_at_metadata") != "true":
        reasons.append("missing-formed-at-metadata")
    if page.get("has_last_reviewed_metadata") != "true":
        reasons.append("missing-last-reviewed-metadata")
    return reasons


def judgment_asset_shell_record(
    page: dict[str, str],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    asset_gaps = judgment_asset_gap_codes(page)
    judgment_lifecycle_state, judgment_lifecycle_reason_codes = judgment_lifecycle_profile(page)
    attention_reasons: list[str] = []
    if page.get("escalation_candidate") == "true":
        attention_reasons.append("escalation-candidate")
    if page.get("overdue_review") == "true":
        attention_reasons.append("overdue-review")
    if page.get("pending_review") == "true":
        attention_reasons.append("pending-review")
    if page.get("aging_state") == "scheduled":
        attention_reasons.append("scheduled-review")
    for reason_code in asset_gaps:
        if reason_code not in attention_reasons:
            attention_reasons.append(reason_code)
    return {
        "page_id": str(page.get("page_id") or ""),
        "title": str(page.get("title") or page.get("path") or ""),
        "path": str(page.get("path") or ""),
        "kind": str(page.get("kind") or ""),
        "status": str(page.get("status") or ""),
        "current_status": str(page.get("status") or ""),
        "protocol": str(page.get("protocol") or ""),
        "confidence": str(page.get("confidence") or ""),
        "formed_at": str(page.get("formed_at") or ""),
        "last_reviewed": str(page.get("last_reviewed") or page.get("reviewed_at") or ""),
        "reviewed_at": str(page.get("reviewed_at") or ""),
        "updated_at": str(page.get("updated_at") or ""),
        "revisit_after": str(page.get("revisit_after") or ""),
        "escalate_after": str(page.get("escalate_after") or ""),
        "aging_state": str(page.get("aging_state") or ""),
        "pending_review": str(page.get("pending_review") or "") == "true",
        "overdue_review": str(page.get("overdue_review") or "") == "true",
        "escalation_candidate": str(page.get("escalation_candidate") or "") == "true",
        "focus_score": page_focus_score(active_protocol, page),
        "asset_score": int(page.get("asset_score", "0") or "0"),
        "has_counter_evidence": str(page.get("has_counter_evidence") or "") == "true",
        "has_invalidation": str(page.get("has_invalidation") or "") == "true",
        "has_next_signals": str(page.get("has_next_signals") or "") == "true",
        "has_review_history": str(page.get("has_review_history") or "") == "true",
        "has_counter_evidence_metadata": str(page.get("has_counter_evidence_metadata") or "") == "true",
        "has_invalidation_rule_metadata": str(page.get("has_invalidation_rule_metadata") or "") == "true",
        "has_next_signals_metadata": str(page.get("has_next_signals_metadata") or "") == "true",
        "has_formed_at_metadata": str(page.get("has_formed_at_metadata") or "") == "true",
        "has_last_reviewed_metadata": str(page.get("has_last_reviewed_metadata") or "") == "true",
        "has_structured_counter_evidence": str(page.get("has_structured_counter_evidence") or "") == "true",
        "has_structured_invalidation_rule": str(page.get("has_structured_invalidation_rule") or "") == "true",
        "has_structured_next_signals": str(page.get("has_structured_next_signals") or "") == "true",
        "counter_evidence_count": int(page.get("counter_evidence_count", "0") or "0"),
        "next_signal_count": int(page.get("next_signal_count", "0") or "0"),
        "invalidation_rule": str(page.get("invalidation_rule") or ""),
        "review_history_entries": int(page.get("review_history_entries", "0") or "0"),
        "latest_review_history_entry": str(page.get("latest_review_history_entry") or ""),
        "citation_drift": str(page.get("citation_drift") or "") == "true",
        "citation_drift_count": int(page.get("citation_drift_count", "0") or "0"),
        "citation_snapshot_gap_count": int(page.get("citation_snapshot_gap_count", "0") or "0"),
        "judgment_lifecycle_state": judgment_lifecycle_state,
        "judgment_lifecycle_reason_codes": judgment_lifecycle_reason_codes,
        "asset_gaps": asset_gaps,
        "attention_reasons": attention_reasons,
    }


def judgment_asset_attention_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        0 if record.get("escalation_candidate") else 1,
        0 if record.get("overdue_review") else 1,
        0 if record.get("pending_review") else 1,
        0 if record.get("citation_drift") else 1,
        0 if int(record.get("citation_snapshot_gap_count", 0) or 0) > 0 else 1,
        -len(record.get("asset_gaps", [])),
        int(record.get("asset_score", 0) or 0),
        -int(record.get("focus_score", 0) or 0),
        str(record.get("revisit_after") or record.get("escalate_after") or "9999"),
        str(record.get("title") or "").lower(),
    )


def judgment_asset_summary(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    pages = sorted(
        decisions + judgments,
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            -(int(page.get("asset_score", "0") or "0")),
            page.get("title", "").lower(),
        ),
    )
    strong_assets = [page for page in pages if int(page.get("asset_score", "0") or "0") >= 3]
    missing_counter = [page for page in pages if page.get("has_counter_evidence") != "true"]
    missing_invalidation = [page for page in pages if page.get("has_invalidation") != "true"]
    missing_next_signals = [page for page in pages if page.get("has_next_signals") != "true"]
    missing_history = [page for page in pages if page.get("has_review_history") != "true"]
    drifted = [page for page in pages if page.get("citation_drift") == "true"]
    snapshot_gaps = [page for page in pages if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0]
    missing_counter_metadata = [page for page in pages if page.get("has_counter_evidence_metadata") != "true"]
    missing_invalidation_metadata = [page for page in pages if page.get("has_invalidation_rule_metadata") != "true"]
    missing_next_signal_metadata = [page for page in pages if page.get("has_next_signals_metadata") != "true"]
    missing_formed_at_metadata = [page for page in pages if page.get("has_formed_at_metadata") != "true"]
    missing_last_reviewed_metadata = [page for page in pages if page.get("has_last_reviewed_metadata") != "true"]
    shell_records = {
        str(page.get("path") or ""): judgment_asset_shell_record(page, active_protocol=active_protocol)
        for page in pages
        if str(page.get("path") or "")
    }
    attention_pages = [
        page for page in pages if shell_records.get(str(page.get("path") or ""), {}).get("attention_reasons")
    ]
    attention_records = [
        shell_records[str(page.get("path") or "")]
        for page in attention_pages
        if str(page.get("path") or "") in shell_records
    ]
    attention_records.sort(key=judgment_asset_attention_sort_key)
    strong_records = [
        shell_records[str(page.get("path") or "")]
        for page in strong_assets
        if str(page.get("path") or "") in shell_records
    ]
    lifecycle_counts = {state: 0 for state in JUDGMENT_LIFECYCLE_STATES}
    for record in shell_records.values():
        lifecycle_state = str(record.get("judgment_lifecycle_state") or "")
        if lifecycle_state in lifecycle_counts:
            lifecycle_counts[lifecycle_state] += 1
    return {
        "counts": {
            "pages": len(pages),
            "decisions": len(decisions),
            "judgments": len(judgments),
            "strong_assets": len(strong_assets),
            "attention_pages": len(attention_pages),
            "missing_counter_evidence": len(missing_counter),
            "missing_invalidation": len(missing_invalidation),
            "missing_next_signals": len(missing_next_signals),
            "missing_review_history": len(missing_history),
            "missing_counter_evidence_metadata": len(missing_counter_metadata),
            "missing_invalidation_rule_metadata": len(missing_invalidation_metadata),
            "missing_next_signals_metadata": len(missing_next_signal_metadata),
            "missing_formed_at_metadata": len(missing_formed_at_metadata),
            "missing_last_reviewed_metadata": len(missing_last_reviewed_metadata),
            "citation_drift": len(drifted),
            "citation_snapshot_gaps": len(snapshot_gaps),
            "pending_review": sum(1 for page in pages if page.get("pending_review") == "true"),
            "overdue_review": sum(1 for page in pages if page.get("overdue_review") == "true"),
            "scheduled_review": sum(1 for page in pages if page.get("aging_state") == "scheduled"),
            "escalation_candidates": sum(1 for page in pages if page.get("escalation_candidate") == "true"),
            "formed_lifecycle": lifecycle_counts["formed"],
            "active_lifecycle": lifecycle_counts["active"],
            "under_review_lifecycle": lifecycle_counts["under-review"],
            "revised_lifecycle": lifecycle_counts["revised"],
            "retired_lifecycle": lifecycle_counts["retired"],
        },
        "lists": {
            "pages": pages,
            "attention_pages": attention_pages,
            "strong_assets": strong_assets,
            "missing_counter_evidence": missing_counter,
            "missing_invalidation": missing_invalidation,
            "missing_next_signals": missing_next_signals,
            "missing_review_history": missing_history,
            "missing_counter_evidence_metadata": missing_counter_metadata,
            "missing_invalidation_rule_metadata": missing_invalidation_metadata,
            "missing_next_signals_metadata": missing_next_signal_metadata,
            "missing_formed_at_metadata": missing_formed_at_metadata,
            "missing_last_reviewed_metadata": missing_last_reviewed_metadata,
            "citation_drift": drifted,
            "citation_snapshot_gaps": snapshot_gaps,
            "escalation_candidates": [page for page in pages if page.get("escalation_candidate") == "true"],
        },
        "attention_pages": attention_records,
        "decision_focus": [record for record in attention_records if record.get("kind") == "decision"],
        "judgment_focus": [record for record in attention_records if record.get("kind") == "judgment"],
        "strong_assets": strong_records,
    }


def render_curated_index(
    heading: str,
    section_name: str,
    pages: list[dict[str, str]],
    compiled_at: str,
) -> str:
    pending_review = sum(1 for page in pages if page.get("pending_review") == "true")
    overdue_review = sum(1 for page in pages if page.get("overdue_review") == "true")
    escalated = sum(1 for page in pages if page.get("escalation_candidate") == "true")
    drifted = [page for page in pages if page.get("citation_drift") == "true"]
    snapshot_gaps = [page for page in pages if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0]
    status_counts: dict[str, int] = {}
    for page in pages:
        status = page.get("status", "") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    lines = [
        f"# {heading}",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 页面总数：`{len(pages)}`",
        f"- 待审阅数量：`{pending_review}`",
        f"- 已到期数量：`{overdue_review}`",
        f"- 需要升级：`{escalated}`",
        f"- 证据漂移：`{len(drifted)}`",
        f"- 快照缺口：`{len(snapshot_gaps)}`",
        "",
        "## 状态统计",
    ]
    if not status_counts:
        lines.append("- 还没有相关页面。")
    else:
        for status, count in sorted(status_counts.items()):
            lines.append(f"- `{display_curated_status(status)}`：`{count}`")
    lines.extend(
        [
            "",
            f"## {section_name}",
        ]
    )
    if not pages:
        lines.append(f"- 还没有{section_name}。")
    else:
        for page in pages:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 证据漂移"])
    if not drifted:
        lines.append("- 当前没有检测到 citation drift。")
    else:
        for page in drifted[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## Snapshot 缺口"])
    if not snapshot_gaps:
        lines.append("- 当前没有 citation snapshot 缺口。")
    else:
        for page in snapshot_gaps[:12]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def render_judgment_assets(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> str:
    from .judgment_assets import render_judgment_assets as _render_judgment_assets

    return _render_judgment_assets(
        root,
        decisions,
        judgments,
        compiled_at,
        active_protocol=active_protocol,
    )


def render_cognitive_history(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    from .cognitive_history import render_cognitive_history as _render_cognitive_history

    return _render_cognitive_history(
        root,
        decisions,
        judgments,
        compiled_at,
        active_protocol=active_protocol,
        knowledge_lifecycle=knowledge_lifecycle,
    )


def render_domain_pilots_index(domain_pilots: dict[str, Any], compiled_at: str, active_protocol: str) -> str:
    lines = [
        "# 领域 Pilot 总览",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 协议总数：`{len(domain_pilots.get('scorecards', []))}`",
        "",
        "## 协议 Scorecards",
    ]
    for scorecard in domain_pilots.get("scorecards", []):
        metrics = scorecard.get("metrics", {})
        lines.append(
            f"- {workspace_link(scorecard['path'], scorecard['title'])}"
            f" | stage `{scorecard.get('stage', 'seed')}`"
            f" | curated `{int(metrics.get('decisions', 0)) + int(metrics.get('judgments', 0))}`"
            f" | outputs `{metrics.get('outputs', 0)}`"
            f" | receipts `{metrics.get('receipts', 0)}`"
            f" | lifecycle backlog `{metrics.get('lifecycle_concept_backlog', 0)}`"
            f" | retired `{metrics.get('lifecycle_retired_concepts', 0)}`"
            f" | dominant/mixed/bridge `{metrics.get('lifecycle_dominant_concepts', 0)}/{metrics.get('lifecycle_mixed_concepts', 0)}/{metrics.get('lifecycle_bridge_concepts', 0)}`"
        )
        lines.append(f"  - {scorecard.get('summary', '')}")
    lines.extend(
        [
            "",
            "## 相关入口",
            "- [协议总览](./protocols.md)",
            "- [输出 Pack 总览](./output-packs.md)",
            "- [炉心面板](./furnace-center.md)",
            "- [审阅中心](./review-center.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_agent_pack(
    role: str,
    title: str,
    mission: str,
    protocol: str,
    compiled_at: str,
    focus: list[str],
    actions: list[str],
    links: list[str],
) -> str:
    frontmatter = render_frontmatter(
        {
            "id": slugify(role),
            "kind": "agent-pack",
            "agent_role": role,
            "title": title,
            "protocol": protocol,
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {title}",
        "",
        f"- Agent role: `{role}`",
        f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
        f"- Compiled at: `{compiled_at}`",
        "",
        "## Mission",
        f"- {mission}",
        "",
        "## Current Focus",
    ]
    if not focus:
        lines.append("- 当前没有额外焦点。")
    else:
        lines.extend(f"- {item}" for item in focus)
    lines.extend(["", "## Suggested Actions"])
    if not actions:
        lines.append("- 当前没有新的建议动作。")
    else:
        lines.extend(f"- {item}" for item in actions)
    lines.extend(["", "## Related Links"])
    if not links:
        lines.append("- 当前没有相关链接。")
    else:
        lines.extend(f"- {item}" for item in links)
    return "\n".join(lines) + "\n"


def render_agent_workbench(
    packs: list[dict[str, str]],
    compiled_at: str,
    active_protocol: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    lifecycle_counts = lifecycle_summary.get("counts", {})
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    dispatch_hints: list[str] = []
    if concept_backlog:
        dispatch_hints.append(
            f"先调 [Review Agent](../../.aiwiki/derived/agents/review-agent.md)，处理 `{len(concept_backlog)}` 个 lifecycle concept backlog。"
        )
    if lifecycle_counts.get("review_concepts", 0) or lifecycle_counts.get("revisit_concepts", 0):
        dispatch_hints.append(
            f"需要概念整理时，再调 [Concept Agent](../../.aiwiki/derived/agents/concept-agent.md)，消化 `{lifecycle_counts.get('review_concepts', 0) + lifecycle_counts.get('revisit_concepts', 0)}` 个 review / revisit concept。"
        )
    if retired_concepts:
        dispatch_hints.append(
            f"确认 `{min(len(retired_concepts), 3)}` 个 retired concept 是否要恢复进入工作面，优先走 [Review Agent](../../.aiwiki/derived/agents/review-agent.md)。"
        )
    if not dispatch_hints:
        dispatch_hints.append("当前 lifecycle governance 较干净，按输出、执行或 ingest 压力决定要调度哪个角色。")
    lines = [
        "# Agent Workbench",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- Agent packs：`{len(packs)}`",
        f"- lifecycle concept backlog / retired：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}` / `{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        "",
        "## 角色总览",
    ]
    if not packs:
        lines.append("- 当前还没有 agent packs。")
    else:
        for pack in packs:
            lines.append(f"- [{pack['title']}](../../{pack['path']}) | role `{pack['role']}` | {pack['mission']}")
    lines.extend(
        [
            "",
            "## Lifecycle Governance Summary",
            f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
            f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
            f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
            "",
            "## Lifecycle Dispatch Hints",
        ]
    )
    lines.extend(f"- {hint}" for hint in dispatch_hints)
    lines.extend(["", "## Lifecycle Concept Backlog"])
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(
        [
            "",
            "## 如何使用",
            "1. Human Owner 先在炉心面板里决定今天要调度哪个角色。",
            "2. 进入对应 agent pack，看当前焦点、建议动作和相关链接。",
            "3. 角色之间共享同一个 `raw / wiki / machine memory / decision / judgment`，不维护私有真相。",
            "",
            "## 相关入口",
            "- [炉心面板](./furnace-center.md)",
            "- [审阅中心](./review-center.md)",
            "- [执行审计](./execution-audit.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [图谱视图](./graph-view.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_review_queue(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
    counter_evidence_scan: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    counter_evidence_scan = counter_evidence_scan or {}
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    counter_evidence_pages = [dict(item) for item in counter_evidence_scan.get("pages", []) if isinstance(item, dict)]
    concept_backlog = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"review", "revisit"},
        ),
        active_protocol=active_protocol,
    )
    retired_concepts = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"retired"},
        ),
        active_protocol=active_protocol,
    )
    lines = [
        "# 审阅队列",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 待审决策：`{len(queue['pending_decisions'])}`",
        f"- 待审判断：`{len(queue['pending_judgments'])}`",
        f"- 最近已审项目：`{len(queue['recently_reviewed'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- Counter-evidence candidates：`{len(counter_evidence_pages)}`",
        f"- lifecycle concept backlog：`{len(concept_backlog)}`",
        f"- retired concepts：`{len(retired_concepts)}`",
        "",
        "## 协议审阅焦点",
        *[f"- {line}" for line in PROTOCOL_LIBRARY.get(active_protocol, {}).get("review", [])],
        "",
        "## 待审决策",
    ]
    if not queue["pending_decisions"]:
        lines.append("- 当前没有待审决策。")
    else:
        for page in queue["pending_decisions"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 待审判断"])
    if not queue["pending_judgments"]:
        lines.append("- 当前没有待审判断。")
    else:
        for page in queue["pending_judgments"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 已到期待复审"])
    if not aging["overdue"]:
        lines.append("- 当前没有已到期的决策或判断页面。")
    else:
        for page in aging["overdue"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 需要升级处理"])
    if not aging["escalated"]:
        lines.append("- 当前没有需要升级处理的页面。")
    else:
        for page in aging["escalated"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## Counter-evidence Candidates"])
    if not counter_evidence_pages:
        lines.append("- 当前没有新的 counter-evidence candidate。")
    else:
        for candidate in counter_evidence_pages[:12]:
            lines.append(
                f"- [{candidate.get('page_title') or candidate.get('page_path') or 'unknown'}](../../{candidate.get('page_path', '')})"
                f" | kind `{candidate.get('page_kind', 'unknown')}`"
                f" | candidates `{candidate.get('candidate_count', 0)}`"
                f" | sources `{', '.join(candidate.get('source_ids', [])) or 'none'}`"
                f" | shared `{', '.join(candidate.get('shared_terms', [])) or 'none'}`"
                f" | reason `counter-evidence-candidate`"
            )
    lines.extend(["", "## 生命周期概念待审"])
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle state 标记为 `review` / `revisit` 的 concept。")
    else:
        for entry in concept_backlog[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 已退役概念"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 最近已审"])
    if not queue["recently_reviewed"]:
        lines.append("- 还没有已审阅的决策或判断页面。")
    else:
        for page in queue["recently_reviewed"][:12]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def render_aging_report(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    pages = decisions + judgments
    lifecycle_revisit_entries = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            states={"revisit"},
        ),
        active_protocol=active_protocol,
    )
    retired_concepts = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"retired"},
        ),
        active_protocol=active_protocol,
    )
    lines = [
        "# Aging 报告",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- 已排期复审：`{len(aging['scheduled'])}`",
        f"- 生命周期待回看项：`{len(lifecycle_revisit_entries)}`",
        f"- retired concepts：`{len(retired_concepts)}`",
        "",
        "## 需要升级处理",
    ]
    if not aging["escalated"]:
        lines.append("- 当前没有升级处理项。")
    else:
        for page in aging["escalated"][:20]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 已到期待复审"])
    if not aging["overdue"]:
        lines.append("- 当前没有已到期页面。")
    else:
        for page in aging["overdue"][:20]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 已排期复审"])
    if not aging["scheduled"]:
        lines.append("- 当前没有已排期的复审页面。")
    else:
        for page in aging["scheduled"][:20]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 生命周期待回看项"])
    if not lifecycle_revisit_entries:
        lines.append("- 当前没有 lifecycle state 标记为 `revisit` 的知识项。")
    else:
        for entry in lifecycle_revisit_entries[:20]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 已退役概念"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:20]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 建议动作"])
    if aging["escalated"]:
        lines.append("- 优先处理升级项，补证据、更新状态或明确下一次复审窗口。")
    if aging["overdue"] and not aging["escalated"]:
        lines.append("- 先清理已到期页面，避免 review queue 长期堆积。")
    if lifecycle_revisit_entries:
        lines.append("- 把 lifecycle `revisit` 项和时间窗口型 overdue 项一起看，避免只盯 review date 而忽略证据失效。")
    if not aging["overdue"] and not aging["escalated"]:
        lines.append("- 当前 aging 状态健康，继续通过 nightly 跟踪。")
    stale_reviewed = [page for page in pages if page.get("pending_review") != "true" and page.get("revisit_after")]
    if stale_reviewed:
        lines.append("- 已审页面如仍保留复审窗口，必要时在下一次 review 中收紧或清空。")
    return "\n".join(lines) + "\n"


def render_review_center_html(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    from .review_center import render_review_center_html as _render_review_center_html

    return _render_review_center_html(
        decisions,
        judgments,
        memory,
        compiled_at,
        active_protocol=active_protocol,
        knowledge_lifecycle=knowledge_lifecycle,
    )


def protocol_execution_receipts(
    execution_audit: dict[str, Any], protocol: str, *, limit: int = 8
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    protocol_buckets = execution_audit.get("recent_by_protocol", {})
    for bucket_name, label in (("recent_apply", "apply"), ("recent_revert", "revert")):
        bucket_rows = []
        if isinstance(protocol_buckets, dict):
            scoped = protocol_buckets.get(bucket_name, {})
            if isinstance(scoped, dict):
                protocol_rows = scoped.get(protocol, [])
                if isinstance(protocol_rows, list):
                    bucket_rows = protocol_rows
        if not bucket_rows:
            bucket_rows = execution_audit.get(bucket_name, [])
        for record in bucket_rows:
            if str(record.get("protocol") or DEFAULT_PROTOCOL) != protocol:
                continue
            rows.append(
                {
                    "kind": label,
                    "title": str(record.get("title") or record.get("action_id") or "receipt"),
                    "action_id": str(record.get("action_id") or ""),
                    "receipt_path": str(record.get("receipt_path") or ""),
                    "applied_at": str(record.get("applied_at") or ""),
                }
            )
    rows.sort(key=lambda item: (item["applied_at"], item["title"].lower()), reverse=True)
    return rows[:limit]


def furnace_quick_commands(
    active_protocol: str,
    apply_ready_actions: list[dict[str, Any]],
    apply_ready_rewrites: list[dict[str, Any]],
) -> list[str]:
    _ = (active_protocol, apply_ready_actions, apply_ready_rewrites)
    commands = [
        'PYTHONPATH=src python3 -m aiwiki.cli --root . advanced ask "对当前主题做协议化总结" --format report',
        "PYTHONPATH=src python3 -m aiwiki.cli --root . advanced compile",
        "PYTHONPATH=src python3 -m aiwiki.cli --root . advanced nightly",
        "PYTHONPATH=src python3 -m aiwiki.cli --root . advanced review-queue --json",
    ]
    return commands[:6]


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
    from .furnace_center import render_furnace_center as _render_furnace_center

    return _render_furnace_center(
        decisions,
        judgments,
        memory,
        compiled_at,
        protocol_state,
        recent_outputs,
        output_packs,
        domain_pilots,
        execution_audit,
        knowledge_lifecycle=knowledge_lifecycle,
    )


def render_furnace_center_html(
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
    from .furnace_center import render_furnace_center_html as _render_furnace_center_html

    return _render_furnace_center_html(
        decisions,
        judgments,
        memory,
        compiled_at,
        protocol_state,
        recent_outputs,
        output_packs,
        domain_pilots,
        execution_audit,
        knowledge_lifecycle=knowledge_lifecycle,
    )


def render_compile_status(
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    protocol_state: dict[str, Any],
    compiled_at: str,
    *,
    compile_state: dict[str, Any] | None = None,
) -> str:
    from .compile_status import render_compile_status as _render_compile_status

    return _render_compile_status(
        entries,
        concepts,
        decisions,
        judgments,
        protocol_state,
        compiled_at,
        compile_state=compile_state,
    )


def render_master_index(
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    protocol_state: dict[str, Any],
    compiled_at: str,
) -> str:
    queue = review_queue(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    aging = collect_aging_signals(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    lines = [
        "# 知识库总索引",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源页：`{len(entries)}`",
        f"- 概念页：`{len(concepts)}`",
        f"- 决策页：`{len(decisions)}`",
        f"- 判断页：`{len(judgments)}`",
        f"- 当前 active protocol：`{protocol_state['active_protocol']}` ({protocol_title(protocol_state['active_protocol'])})",
        f"- 待审项目：`{len(queue['pending_decisions']) + len(queue['pending_judgments'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- 证据漂移：`{sum(1 for page in decisions + judgments if page.get('citation_drift') == 'true')}`",
        "",
        "## 核心页面",
        "- [来源索引](./sources.md)",
        "- [概念索引](./concepts.md)",
        "- [概念质量](./concept-quality.md)",
        "- [决策索引](./decisions.md)",
        "- [判断索引](./judgments.md)",
        "- [判断资产](./judgment-assets.md)",
        "- [Agent Workbench](./agent-workbench.md)",
        "- [认知历史](./cognitive-history.md)",
        "- [协议总览](./protocols.md)",
        "- [炉心面板](./furnace-center.md)",
        "- [输出 Pack 总览](./output-packs.md)",
        "- [领域 Pilot 总览](./domain-pilots.md)",
        "- [审阅队列](./review-queue.md)",
        "- [审阅中心](./review-center.md)",
        "- [Aging 报告](./aging-report.md)",
        "- [编译状态](./compile-status.md)",
        "- [机器记忆](./machine-memory.md)",
        "- [图谱视图](./graph-view.md)",
        "- [机器记忆拓扑](./machine-memory-topology.md)",
        "- [机器记忆动作队列](./machine-memory-actions.md)",
        "- [机器记忆修复计划](./machine-memory-repair-plan.md)",
        "- [Rewrite Proposals](./rewrite-proposals.md)",
        "- [图谱健康](./graph-health.md)",
        "- [漂移报告](./drift-report.md)",
        "- [修复待办](./repair-backlog.md)",
        "- [操作日志](./log.md)",
        "- [运行时规则](../../schema/index.md)",
        "- [协议规则](../../schema/protocols/index.md)",
        "",
        "## 最近来源",
    ]
    if not entries:
        lines.append("- 还没有登记任何来源。")
    else:
        for entry in sorted(entries, key=lambda item: item["imported_at"], reverse=True)[:8]:
            lines.append(f"- [{entry['title']}](../sources/{entry['id']}.md)")
    lines.extend(["", "## 重点概念"])
    if not concepts:
        lines.append("- 还没有编译出概念页。")
    else:
        for concept in concepts[:10]:
            lines.append(f"- [{concept['title']}](../concepts/{concept['slug']}.md)")
    lines.extend(["", "## 待审项目"])
    if not queue["pending_decisions"] and not queue["pending_judgments"]:
        lines.append("- 当前没有等待审阅的决策或判断页面。")
    else:
        for page in (queue["pending_decisions"] + queue["pending_judgments"])[:8]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 最近决策"])
    if not decisions:
        lines.append("- 还没有回流的决策页面。")
    else:
        for page in decisions[:8]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 最近判断"])
    if not judgments:
        lines.append("- 还没有回流的判断页面。")
    else:
        for page in judgments[:8]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def machine_memory_query_plan_lines(machine_query: dict[str, Any]) -> list[str]:
    lines = [
        f"- 命中词：`{', '.join(machine_query.get('matched_terms', [])) or 'none'}`",
        f"- 路由策略：`{str(machine_query.get('selected_strategy') or 'concept-first')}`",
        f"- 路由原因：`{str(machine_query.get('selection_reason') or 'default-strategy')}`",
        f"- 来源意图词：`{', '.join(machine_query.get('matched_source_markers', [])) or 'none'}`",
        f"- 图谱意图词：`{', '.join(machine_query.get('matched_graph_markers', [])) or 'none'}`",
        f"- 提升权重的来源：`{', '.join(machine_query.get('ranked_source_ids', [])) or 'none'}`",
        f"- 提升权重的概念：`{', '.join(machine_query.get('ranked_concept_slugs', [])) or 'none'}`",
        f"- 提升权重的判断：`{', '.join(machine_query.get('ranked_judgment_ids', [])) or 'none'}`",
        f"- 提升权重的金丹：`{', '.join(machine_query.get('ranked_elixir_ids', [])) or 'none'}`",
        f"- 协议 shard 来源：`{', '.join(machine_query.get('protocol_shard_source_ids', [])) or 'none'}`",
        f"- 时间偏置：`{str(machine_query.get('time_focus') or 'none')}`",
        f"- 时间意图词：`{', '.join(machine_query.get('time_focus_markers', [])) or 'none'}`",
        f"- 时间 shard 来源：`{', '.join(machine_query.get('time_shard_source_ids', [])) or 'none'}`",
        f"- 桥接概念：`{', '.join(machine_query.get('bridge_concept_slugs', [])) or 'none'}`",
        f"- 查询子图边数：`{len(machine_query.get('query_subgraph', {}).get('edges', []))}`",
        f"- 查询路径数：`{len(machine_query.get('query_routes', []))}`",
        f"- 触达分量：`{', '.join(machine_query.get('touched_component_ids', [])) or 'none'}`",
        f"- 命中的修复动作：`{len(machine_query.get('relevant_actions', []))}`",
    ]
    archive_hints = machine_query.get("archive_recall_hints", []) or []
    if archive_hints:
        hint_labels = []
        for hint in archive_hints[:3]:
            title = str(hint.get("title") or hint.get("entry_id") or "")
            temperature = str(hint.get("temperature") or "")
            archive_status = str(hint.get("archive_status") or "")
            state_label = "/".join(part for part in (temperature, archive_status) if part) or "hint"
            hint_labels.append(f"{title} [{state_label}]")
        lines.append(f"- 归档召回提示：`{', '.join(hint_labels)}`")
    else:
        lines.append("- 归档召回提示：`none`")
    planner_next_action = machine_query.get("planner_next_action", {}) or {}
    if planner_next_action:
        lines.append(
            f"- Planner next action：`{planner_next_action.get('action_id', '')}`"
            f" / `{planner_next_action.get('title', '')}`"
            f" / score `{planner_next_action.get('priority_score', 0)}`"
        )
    else:
        lines.append("- Planner next action：`none`")
    return lines


def compact_machine_memory_focus_lines(machine_query: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    matched_terms = [str(term).strip() for term in machine_query.get("matched_terms", []) if str(term).strip()]
    if matched_terms:
        lines.append(f"- 命中词：`{', '.join(matched_terms[:5])}`")
    strategy = str(machine_query.get("selected_strategy") or "").strip()
    reason = str(machine_query.get("selection_reason") or "").strip()
    if strategy:
        suffix = f" / `{reason}`" if reason else ""
        lines.append(f"- 查询入口：`{strategy}`{suffix}")
    bridge_concepts = [str(slug).strip() for slug in machine_query.get("bridge_concept_slugs", []) if str(slug).strip()]
    if bridge_concepts:
        lines.append(f"- 桥接概念：`{', '.join(bridge_concepts[:4])}`")
    archive_hints = machine_query.get("archive_recall_hints", []) or []
    if archive_hints:
        hint_labels = []
        for hint in archive_hints[:2]:
            title = str(hint.get("title") or hint.get("entry_id") or "").strip()
            temperature = str(hint.get("temperature") or "").strip()
            archive_status = str(hint.get("archive_status") or "").strip()
            state_label = "/".join(part for part in (temperature, archive_status) if part) or "hint"
            if title:
                hint_labels.append(f"{title} [{state_label}]")
        if hint_labels:
            lines.append(f"- 归档召回提示：`{', '.join(hint_labels)}`")
    planner_next_action = machine_query.get("planner_next_action", {}) or {}
    if not bridge_concepts:
        planner_title = str(planner_next_action.get("title") or planner_next_action.get("action_id") or "").strip()
        if planner_title:
            lines.append(f"- 下一动作提示：`{planner_title}`")
    if not lines:
        return ["- 当前没有明显的机器记忆命中，先从优先来源开始。"]
    return lines[:4]


def compact_concept_link_lines(
    concepts: list[dict[str, Any]],
    *,
    limit: int = 5,
    empty_message: str = "- 还没有排好序的概念页。",
) -> list[str]:
    if not concepts:
        return [empty_message]
    return [f"- [{concept['title']}](../../{concept['path']})" for concept in concepts[:limit]]


def compact_source_link_lines(
    entries: list[dict[str, Any]],
    *,
    limit: int = 5,
    empty_message: str = "- 还没有排好序的来源。先在 ingest 后运行 `aiwiki compile`。",
) -> list[str]:
    if not entries:
        return [empty_message]
    return [f"- [{entry['title']}](../../wiki/sources/{entry['id']}.md)" for entry in entries[:limit]]


def build_ask_used_refs(
    *,
    ranked_sources: list[dict[str, Any]] | None = None,
    ranked_concepts: list[dict[str, Any]] | None = None,
    compound_paths: list[str] | None = None,
    material_paths: list[str] | None = None,
) -> list[str]:
    refs: list[str] = []
    for entry in ranked_sources or []:
        if not isinstance(entry, dict):
            continue
        source_id = str(entry.get("id") or "").strip()
        if source_id:
            path = f"wiki/sources/{source_id}.md"
            if path not in refs:
                refs.append(path)
    for concept in ranked_concepts or []:
        if not isinstance(concept, dict):
            continue
        path = str(concept.get("path") or "").strip()
        if not path and concept.get("slug"):
            path = f"wiki/concepts/{concept['slug']}.md"
        if path and path not in refs:
            refs.append(path)
    for path in compound_paths or []:
        normalized = str(path or "").strip()
        if normalized and normalized not in refs:
            refs.append(normalized)
    for path in material_paths or []:
        normalized = str(path or "").strip()
        if normalized and normalized not in refs:
            refs.append(normalized)
    return refs


def compact_judgment_link_lines(
    machine_query: dict[str, Any],
    *,
    limit: int = 3,
    empty_message: str = "- 当前没有命中的已确认判断。",
) -> list[str]:
    nodes = (machine_query.get("query_subgraph", {}) or {}).get("judgments", []) or []
    if not nodes:
        return [empty_message]
    lines: list[str] = []
    for node in nodes[:limit]:
        if not isinstance(node, dict):
            continue
        title = str(node.get("title") or node.get("page_id") or "").strip()
        path = str(node.get("path") or "").strip()
        if title and path:
            lines.append(f"- [{title}](../../{path})")
    return lines or [empty_message]


def compact_elixir_link_lines(
    machine_query: dict[str, Any],
    *,
    limit: int = 2,
    empty_message: str = "- 当前没有命中的 settled 金丹。",
) -> list[str]:
    nodes = (machine_query.get("query_subgraph", {}) or {}).get("elixirs", []) or []
    if not nodes:
        return [empty_message]
    lines: list[str] = []
    for node in nodes[:limit]:
        if not isinstance(node, dict):
            continue
        title = str(node.get("title") or node.get("elixir_id") or "").strip()
        path = str(node.get("path") or "").strip()
        if title and path:
            lines.append(f"- [{title}](../../{path})")
    return lines or [empty_message]


def render_report(
    root: Path,
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    protocol_state: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    title = human_query_title(question)
    focus_lines = compact_machine_memory_focus_lines(machine_query)
    frontmatter = render_frontmatter(
        {
            "kind": "output",
            "format": "report",
            "cssclasses": ["aiwiki-output"],
            "protocol": active_protocol,
            "query": question,
            "created_at": created_at,
            "generated_by": "aiwiki-ask",
            "_id": artifact_id,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {title}",
        "",
        "## 参考",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})。",
        "",
    ]
    if focus_lines and focus_lines != ["- 当前没有明显的机器记忆命中，先从优先来源开始。"]:
        lines.extend(["", "_机器记忆提示：_"])
        lines.extend(focus_lines)
    lines.extend(
        [
            "",
            "_优先来源：_",
        ]
    )
    lines.extend(compact_source_link_lines(entries))
    lines.extend(
        [
            "",
            "_优先概念：_",
        ]
    )
    lines.extend(compact_concept_link_lines(concepts))
    if machine_query.get("ranked_judgment_ids") or (machine_query.get("query_subgraph", {}) or {}).get("judgments"):
        lines.extend(
            [
                "",
                "_优先判断：_",
            ]
        )
        lines.extend(compact_judgment_link_lines(machine_query))
    if machine_query.get("ranked_elixir_ids") or (machine_query.get("query_subgraph", {}) or {}).get("elixirs"):
        lines.extend(
            [
                "",
                "_优先金丹：_",
            ]
        )
        lines.extend(compact_elixir_link_lines(machine_query))
    return "\n".join(lines) + "\n"
