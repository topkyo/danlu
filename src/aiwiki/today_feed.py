"""M6.3 Today Feed builder — pure function, no IO, no schema mutation.

从 ShellSummary dict 派生统一 Today feed entries。
CLI today_command 与 Product Shell renderTodayFeed 共享同一排序契约。
JS mirror: .obsidian/plugins/furnace-product-shell/src/today_feed.js (M6.3 B3 落地)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

FeedKind = Literal["decision", "proposal", "report", "elixir", "automation", "action"]
FeedAudience = Literal["primary", "operator"]

# 固定优先级：数字越小越靠前。同 priority 内按 timestamp desc。
# Primary Today 只保留报告、待拍板异常和必要行动；operator feed 仍可显示自动化/指标状态。
_PRIORITY: dict[str, int] = {
    "report": 1,
    "automation": 2,
    "decision": 3,
    "proposal": 4,
    "elixir": 5,
    "action": 6,
}


def priority_for_kind(kind: str) -> int:
    """Return the shared Today Feed ordering priority for a feed kind."""

    return _PRIORITY[str(kind)]

_REVIEW_BUCKET_COPY: dict[str, tuple[str, str]] = {
    "counter_evidence_candidates": ("补充反证候选", "检查新来源是否足以反驳既有判断"),
    "escalated_actions": ("处理升级动作", "处理已升级、需要人工确认的动作"),
    "escalation_candidates": ("处理升级候选", "确认是否需要人工介入"),
    "judgment_review_actions": ("复核研究判断", "处理需要重新判断的结论"),
    "l3_proposals": ("处理 L3 提案", "确认采纳、拒绝或回滚提案"),
    "l3_proposal_attention": ("处理 L3 提案", "确认采纳、拒绝或回滚提案"),
    "machine_memory_actions": ("修复机器记忆", "处理可审计的记忆修复动作"),
    "overdue_actions": ("处理逾期动作", "确认是否继续执行或关闭"),
    "overdue_reviews": ("处理逾期复审", "确认旧判断是否仍成立"),
    "pending_decisions": ("处理待定决策", "确认待定判断与执行入口"),
    "pending_judgments": ("复核待定判断", "推进仍在等待复核的判断"),
    "ready_actions": ("确认待执行动作", "复核已经准备好的安全动作"),
}

# 这些才是普通用户首屏的“需要你确认”。
# Routine backlog（如 ready/overdue actions/reviews）仍保留在 review queue / Advanced，
# 不能在 primary Today 里伪装成需要人工处理的 exception。
_PRIMARY_REVIEW_BUCKETS: set[str] = {
    "counter_evidence_candidates",
    "escalated_actions",
    "escalation_candidates",
    "judgment_review_actions",
    "pending_decisions",
    "pending_judgments",
}

_ROUTINE_REVIEW_BUCKETS: set[str] = {
    "l3_proposal_attention",
    "l3_proposals",
    "machine_memory_actions",
    "overdue_actions",
    "overdue_reviews",
    "ready_actions",
}


def primary_review_bucket_keys() -> tuple[str, ...]:
    """Return review backlog buckets allowed in the primary Today exception queue."""

    return tuple(sorted(_PRIMARY_REVIEW_BUCKETS))


def routine_review_bucket_keys() -> tuple[str, ...]:
    """Return routine backlog buckets that must not re-enter primary Today."""

    return tuple(sorted(_ROUTINE_REVIEW_BUCKETS))


@dataclass(frozen=True)
class FeedEntry:
    kind: FeedKind
    title: str
    summary: str
    target: str
    timestamp: str
    protocol: str
    compound_suggest: dict[str, Any] | None = None


def build_today_feed(summary: dict[str, Any], *, audience: FeedAudience = "primary") -> list[FeedEntry]:
    """从 ShellSummary 派生统一 feed。pure function。"""
    if not isinstance(summary, dict):
        return []
    entries: list[FeedEntry] = []
    today_date = _today_date(summary)

    entries.extend(_build_decision_entries(summary, audience=audience))
    entries.extend(_build_counter_evidence_entries(summary))
    entries.extend(_build_drift_entries(summary))
    entries.extend(_build_proposal_entries(summary))
    entries.extend(_build_report_entries(summary, today_date))
    entries.extend(_build_compound_suggest_entries(summary))
    entries.extend(_build_elixir_entries(summary, today_date))
    if audience == "operator":
        entries.extend(_build_metric_alert_entries(summary))
        entries.extend(_build_agent_loop_entries(summary, today_date))
    entries.extend(_build_action_entries(summary, audience=audience))
    entries.extend(_build_raw_input_entries(summary, today_date))

    if audience == "primary":
        entries = _apply_snooze_filter(entries, summary, today_date)
    entries.sort(key=_sort_key)
    return entries


def _build_decision_entries(summary: dict[str, Any], *, audience: FeedAudience) -> list[FeedEntry]:
    counts = summary.get("review_backlog_counts")
    if not isinstance(counts, dict):
        return []
    timestamp = str(summary.get("generated_at") or "")
    entries: list[FeedEntry] = []
    for kind in sorted(counts):
        count = _as_count(counts.get(kind))
        if count <= 0:
            continue
        kind_text = str(kind).strip()
        if not kind_text:
            continue
        if audience == "primary" and kind_text not in _PRIMARY_REVIEW_BUCKETS:
            continue
        title, hint = _review_bucket_copy(kind_text)
        entries.append(
            FeedEntry(
                kind="decision",
                title=title,
                summary=f"{count} 项待处理 · {hint}",
                target=f"review:{kind_text}",
                timestamp=timestamp,
                protocol="",
            )
        )
    return entries


def _review_bucket_copy(kind_text: str) -> tuple[str, str]:
    copy = _REVIEW_BUCKET_COPY.get(kind_text)
    if copy:
        return copy
    label = kind_text.replace("_", " ").replace("-", " ").strip()
    title = f"处理审阅队列：{label}" if label else "处理审阅队列"
    return title, "进入审阅中心确认下一步"


def _build_counter_evidence_entries(summary: dict[str, Any]) -> list[FeedEntry]:
    """P0 — counter-evidence pages 浮入 Needs Review (kind=decision).

    源: summary.counter_evidence_pages（由 build_shell_summary 派生）。
    """
    pages = summary.get("counter_evidence_pages")
    if not isinstance(pages, list):
        return []
    entries: list[FeedEntry] = []
    for item in pages:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        subject = str(item.get("subject") or path)
        page_summary = str(item.get("summary") or "judgment 被反驳")
        entries.append(
            FeedEntry(
                kind="decision",
                title=f"反证待复核: {subject}",
                summary=page_summary,
                target=path,
                timestamp=str(item.get("detected_at") or ""),
                protocol=str(item.get("protocol") or ""),
            )
        )
    return entries


def _build_drift_entries(summary: dict[str, Any]) -> list[FeedEntry]:
    """P0 — drift / source-reference-break 浮入 Needs Review (kind=decision)."""
    warnings = summary.get("drift_warnings")
    if not isinstance(warnings, list):
        return []
    entries: list[FeedEntry] = []
    for item in warnings[:8]:
        if not isinstance(item, dict):
            continue
        kind_text = str(item.get("kind") or "").strip()
        path = str(item.get("path") or "").strip()
        message = str(item.get("message") or "").strip()
        if not path and not message:
            continue
        title_target = path or kind_text or "drift"
        entries.append(
            FeedEntry(
                kind="decision",
                title=f"知识漂移: {title_target}",
                summary=message or kind_text or "证据已变",
                target=path or kind_text,
                timestamp=str(item.get("detected_at") or ""),
                protocol=str(item.get("protocol") or ""),
            )
        )
    return entries


def _build_metric_alert_entries(summary: dict[str, Any]) -> list[FeedEntry]:
    """P0 — metrics history delta 浮入 Suggested Next Actions (kind=action).

    源: summary.metrics_history_delta.alerts。每个 alert 一条 entry。
    """
    delta = summary.get("metrics_history_delta")
    if not isinstance(delta, dict) or not delta.get("available"):
        return []
    alerts = delta.get("alerts")
    if not isinstance(alerts, list):
        return []
    window = str(delta.get("window") or "")
    baseline_ts = str(delta.get("baseline_ts") or "")
    entries: list[FeedEntry] = []
    for item in alerts:
        if not isinstance(item, dict):
            continue
        key = str(item.get("metric_key") or "").strip()
        if not key:
            continue
        direction = str(item.get("direction") or "")
        try:
            diff_value = float(item.get("diff", 0.0))
        except (TypeError, ValueError):
            diff_value = 0.0
        arrow = "↑" if direction == "up" else "↓"
        entries.append(
            FeedEntry(
                kind="action",
                title=f"指标变化: {key} {arrow}",
                summary=f"{window} 内 {key} 变化 {diff_value:+.3g}（vs {baseline_ts}）",
                target=f"metric:{key}",
                timestamp=baseline_ts,
                protocol="",
            )
        )
    return entries


def _build_agent_loop_entries(summary: dict[str, Any], today_date: str) -> list[FeedEntry]:
    nightly = summary.get("nightly")
    if not isinstance(nightly, dict):
        return []
    agent_loop = nightly.get("agent_loop")
    if not isinstance(agent_loop, dict):
        return []
    timestamp = str(agent_loop.get("generated_at") or nightly.get("generated_at") or "")
    if _date_part(timestamp) != today_date:
        return []
    status = str(agent_loop.get("status") or "")
    if status not in {"ok", "failed"}:
        return []

    if status == "failed":
        summary_text = "今日维护预演失败，需要人工查看"
    else:
        signals = agent_loop.get("signals") if isinstance(agent_loop.get("signals"), dict) else {}
        planner = agent_loop.get("planner") if isinstance(agent_loop.get("planner"), dict) else {}
        execute = planner.get("execute") if isinstance(planner.get("execute"), dict) else {}
        auto_preview = agent_loop.get("auto_preview") if isinstance(agent_loop.get("auto_preview"), dict) else {}
        auto_apply = agent_loop.get("auto_apply") if isinstance(agent_loop.get("auto_apply"), dict) else {}
        auto_adopt_l1 = agent_loop.get("auto_adopt_l1") if isinstance(agent_loop.get("auto_adopt_l1"), dict) else {}
        auto_adopt_l2 = agent_loop.get("auto_adopt_l2") if isinstance(agent_loop.get("auto_adopt_l2"), dict) else {}
        auto_adopt_judgments = agent_loop.get("auto_adopt_judgments") if isinstance(agent_loop.get("auto_adopt_judgments"), dict) else {}
        # Planner decisions are derived from signals; don't double-count the same change in user-facing copy.
        new_items = max(int(signals.get("new_count") or 0), int(execute.get("new_count") or 0))
        applied_count = int(auto_apply.get("applied_count") or 0)
        l1_adopted = sum(
            item.get("count", 0) for item in auto_adopt_l1.get("items", [])
            if isinstance(item, dict) and item.get("count", 0) > 0 and "error" not in item
        )
        l2_adopted = sum(
            item.get("count", 0) for item in auto_adopt_l2.get("items", [])
            if isinstance(item, dict) and item.get("count", 0) > 0 and "error" not in item
        )
        j_reviewed = int(auto_adopt_judgments.get("reviewed") or 0)
        total_adopted = applied_count + l1_adopted + l2_adopted
        if total_adopted > 0 or j_reviewed > 0:
            parts = [f"今日发现 {new_items} 个新变化"]
            if applied_count > 0:
                parts.append(f"已静默执行 {applied_count} 条维护路径")
            if l1_adopted > 0:
                parts.append(f"已自动消化 {l1_adopted} 条 L1 候选")
            if l2_adopted > 0:
                parts.append(f"已自动处理 {l2_adopted} 条 L2 动作")
            if j_reviewed > 0:
                parts.append(f"LLM 已复核 {j_reviewed} 条判断")
            summary_text = "，".join(parts)
            title = "已自动维护"
            target = "wiki/indexes/execution-audit.md"
        else:
            ready_count = int(auto_preview.get("ready_count") or 0)
            if ready_count > 0:
                summary_text = f"今日发现 {new_items} 个新变化，{ready_count} 条维护路径可人工确认"
            else:
                summary_text = "今日维护预演完成，暂不需要自动执行"
            title = "预演下一步维护"
            target = "wiki/indexes/repair-backlog.md"

    return [
        FeedEntry(
            kind="automation",
            title=title if status != "failed" else "预演下一步维护",
            summary=summary_text,
            target=target if status != "failed" else "wiki/indexes/repair-backlog.md",
            timestamp=timestamp,
            protocol=str(summary.get("active_protocol") or ""),
        )
    ]


def _build_proposal_entries(summary: dict[str, Any]) -> list[FeedEntry]:
    review_controls = summary.get("review_controls")
    source = review_controls.get("l3_proposals") if isinstance(review_controls, dict) else summary.get("l3_proposals")
    entries: list[FeedEntry] = []
    for item in _dict_items(source):
        if not item.get("needs_attention"):
            continue
        proposal_id = _first_text(item, "proposal_id", "id", "subject_id")
        title = _first_text(item, "title", "subject", "target_file", "proposal_id") or proposal_id
        target = _first_text(item, "proposal_path", "path", "target_file", "proposal_id")
        timestamp = _first_text(
            item,
            "updated_at",
            "created_at",
            "accepted_at",
            "rejected_at",
            "reverted_at",
            "stale_at",
            "revert_conflict_at",
        )
        if not title or not target:
            continue
        kind_text = _first_text(item, "kind") or "proposal"
        state = _first_text(item, "state", "current_status") or "pending"
        entries.append(
            FeedEntry(
                kind="proposal",
                title=title,
                summary=f"{kind_text} 建议等待处理（{state}）",
                target=target,
                timestamp=timestamp,
                protocol=_first_text(item, "protocol"),
            )
        )
    return entries


def _compound_suggest_items(summary: dict[str, Any]) -> list[dict[str, Any]]:
    compound = summary.get("compound_suggest")
    if not isinstance(compound, dict) or not compound.get("available"):
        return []
    raw_items = compound.get("items")
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, dict)]


def _compound_suggest_index(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in _compound_suggest_items(summary):
        report_path = _first_text(item, "report_path")
        if report_path:
            index[report_path] = item
    return index


def _build_compound_suggest_entries(summary: dict[str, Any]) -> list[FeedEntry]:
    timestamp = str(summary.get("generated_at") or "")
    entries: list[FeedEntry] = []
    for item in _compound_suggest_items(summary):
        title = _first_text(item, "title", "report_title")
        report_path = _first_text(item, "report_path")
        reason = _first_text(item, "reason", "signal") or "compound-suggest"
        if not title:
            continue
        entries.append(
            FeedEntry(
                kind="action",
                title=title,
                summary=f"复利建议：{reason}",
                target=report_path or _first_text(item, "command"),
                timestamp=timestamp,
                protocol=_first_text(item, "protocol"),
                compound_suggest=item,
            )
        )
    return entries


def _build_report_entries(summary: dict[str, Any], today_date: str) -> list[FeedEntry]:
    entries: list[FeedEntry] = []
    suggest_index = _compound_suggest_index(summary)
    for item in _dict_items(summary.get("recent_outputs")):
        if not _is_deliverable_report_output(item):
            continue
        timestamp = _first_text(item, "generated_at", "created_at")
        if _date_part(timestamp) != today_date:
            continue
        path = _first_text(item, "path", "artifact_path")
        title = _first_text(item, "title") or Path(path).name
        output_format = _first_text(item, "format") or "未知格式"
        if not path or not title:
            continue
        entries.append(
            FeedEntry(
                kind="report",
                title=title,
                summary=f"{output_format} 输出",
                target=path,
                timestamp=timestamp,
                protocol=_first_text(item, "protocol"),
                compound_suggest=suggest_index.get(path),
            )
        )
    return entries


def _is_deliverable_report_output(item: dict[str, Any]) -> bool:
    delivery_mode = _first_text(item, "delivery_mode")
    llm_status = _first_text(item, "llm_status")
    background_status = _first_text(item, "background_status")
    artifact_quality = _first_text(item, "artifact_quality")
    placeholder = _first_text(item, "contains_llm_placeholder").lower()
    title = _first_text(item, "title")
    if delivery_mode == "deterministic-fallback":
        return False
    if llm_status in {"timeout_or_unavailable", "validation_failed", "pending", "failed", "degraded"}:
        return False
    if background_status in {"submitted", "running", "degraded"}:
        return False
    if artifact_quality in {"degraded", "placeholder"}:
        return False
    if placeholder in {"1", "true", "yes"}:
        return False
    if title.startswith("LLM 未完成"):
        return False
    return True


def _build_elixir_entries(summary: dict[str, Any], today_date: str) -> list[FeedEntry]:
    entries: list[FeedEntry] = []
    for item in _dict_items(summary.get("recent_receipts")):
        timestamp = _first_text(item, "applied_at", "generated_at", "created_at")
        if _date_part(timestamp) != today_date:
            continue
        operation = _first_text(item, "operation")
        subject_kind = _first_text(item, "subject_kind")
        subject_id = _first_text(item, "subject_id")
        action_id = _first_text(item, "action_id")
        elixir_text = " ".join([operation, subject_kind, subject_id, action_id]).lower()
        if "elixir" not in elixir_text and not any(
            token in operation.lower() for token in ("promote", "demote", "revert", "finalize")
        ):
            continue
        title = _first_text(item, "title") or subject_id or action_id
        target = _first_text(item, "receipt_path", "path")
        if not title or not target:
            continue
        entries.append(
            FeedEntry(
                kind="elixir",
                title=title,
                summary=f"已完成 {operation or '更新'}",
                target=target,
                timestamp=timestamp,
                protocol=_first_text(item, "protocol"),
            )
        )
    return entries


def _build_action_entries(summary: dict[str, Any], *, audience: FeedAudience) -> list[FeedEntry]:
    entries: list[FeedEntry] = []
    generated_at = str(summary.get("generated_at") or "")
    for item in _dict_items(summary.get("suggested_next_actions")):
        if _first_text(item, "kind") == "compound-suggest":
            continue
        title = _first_text(item, "title", "label", "name")
        target = _first_text(item, "command", "cli", "action", "path")
        if not title or not target:
            continue
        reason = _first_text(item, "reason", "kind")
        if audience == "primary" and _is_maintenance_command_action(target=target, reason=reason):
            continue
        entries.append(
            FeedEntry(
                kind="action",
                title=title,
                summary=f"建议下一步：{reason or '继续处理'}",
                target=target,
                timestamp=_first_text(item, "timestamp", "updated_at", "created_at") or generated_at,
                protocol=_first_text(item, "protocol"),
            )
        )
    return entries


def _build_raw_input_entries(summary: dict[str, Any], today_date: str) -> list[FeedEntry]:
    recent_raw_inputs = summary.get("recent_raw_inputs")
    if not isinstance(recent_raw_inputs, list):
        return []
    entries: list[FeedEntry] = []
    for item in recent_raw_inputs:
        if not isinstance(item, dict):
            continue
        stored_path = _first_text(item, "stored_path")
        if not stored_path:
            continue
        occurred_at = _first_text(item, "occurred_at")
        if _date_part(occurred_at) != today_date:
            continue
        original_path = _first_text(item, "original_path")
        title = _first_text(item, "title")
        source_type = _first_text(item, "source_type")
        entries.append(
            FeedEntry(
                kind="action",
                title=f"已投料：{title or original_path or stored_path}",
                summary=f"已接收 {source_type or '材料'}，等待编译/刷新",
                target=stored_path,
                timestamp=occurred_at,
                protocol=_first_text(item, "protocol"),
            )
        )
    return entries


def _is_maintenance_command_action(*, target: str, reason: str) -> bool:
    """Return true for operator maintenance commands that should not be user-front-page tasks."""
    target_text = f" {target.strip()} "
    reason_text = reason.strip()
    if reason_text.startswith("batch-hint:"):
        return True
    maintenance_tokens = (
        " review-page ",
        " batch-review ",
    )
    return any(token in target_text for token in maintenance_tokens)


def _today_date(summary: dict[str, Any]) -> str:
    return _date_part(str(summary.get("generated_at") or ""))


def _apply_snooze_filter(entries: list[FeedEntry], summary: dict[str, Any], today_date: str) -> list[FeedEntry]:
    state = summary.get("today_snooze")
    if not isinstance(state, dict):
        return entries
    active_targets: set[str] = set()
    for item in state.get("items", []):
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or "").strip()
        until = _date_part(str(item.get("snoozed_until") or ""))
        if target and until and until >= today_date:
            active_targets.add(target)
    if not active_targets:
        return entries
    return [entry for entry in entries if entry.target not in active_targets]


def _date_part(value: str) -> str:
    text = str(value or "").strip()
    if "T" in text:
        return text.split("T", 1)[0]
    if " " in text:
        return text.split(" ", 1)[0]
    return text[:10]


def _dict_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _as_count(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _sort_key(entry: FeedEntry) -> tuple[int, str, str]:
    """priority asc, timestamp desc（用反向字符串实现），kind 顺序保险。"""
    return (priority_for_kind(entry.kind), _reverse_timestamp(entry.timestamp), entry.kind)


def _reverse_timestamp(ts: str) -> str:
    # ISO8601 字典序与时间序一致；反向排序用 negation trick: 取反 char by char
    if not ts:
        return "\x7f"  # 空串排最后（最大 sort key）
    return "".join(chr(0x7F - ord(c)) for c in ts)
