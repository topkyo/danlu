"""M6.3 Today Feed builder — pure function, no IO, no schema mutation.

从 ShellSummary dict 派生统一 Today feed entries。
CLI today_command 与 Product Shell renderTodayFeed 共享同一排序契约。
JS mirror: .obsidian/plugins/furnace-product-shell/src/today_feed.js (M6.3 B3 落地)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

FeedKind = Literal["decision", "proposal", "report", "elixir", "action"]

# 固定优先级：数字越小越靠前。同 priority 内按 timestamp desc。
_PRIORITY: dict[str, int] = {
    "decision": 1,
    "proposal": 2,
    "report": 3,
    "elixir": 4,
    "action": 5,
}

_REVIEW_BUCKET_COPY: dict[str, tuple[str, str]] = {
    "counter_evidence_candidates": ("补充反证候选", "检查新来源是否足以反驳既有判断"),
    "judgment_review_actions": ("复核研究判断", "处理需要重新判断的结论"),
    "l3_proposals": ("处理 L3 提案", "确认采纳、拒绝或回滚提案"),
    "machine_memory_actions": ("修复机器记忆", "处理可审计的记忆修复动作"),
    "pending_decisions": ("处理待定决策", "确认待定判断与执行入口"),
    "pending_judgments": ("复核待定判断", "推进仍在等待复核的判断"),
    "ready_actions": ("确认待执行动作", "复核已经准备好的安全动作"),
}


@dataclass(frozen=True)
class FeedEntry:
    kind: FeedKind
    title: str
    summary: str
    target: str
    timestamp: str
    protocol: str


def build_today_feed(summary: dict[str, Any]) -> list[FeedEntry]:
    """从 ShellSummary 派生统一 feed。pure function。"""
    if not isinstance(summary, dict):
        return []
    entries: list[FeedEntry] = []
    today_date = _today_date(summary)

    entries.extend(_build_decision_entries(summary))
    entries.extend(_build_counter_evidence_entries(summary))
    entries.extend(_build_drift_entries(summary))
    entries.extend(_build_proposal_entries(summary))
    entries.extend(_build_report_entries(summary, today_date))
    entries.extend(_build_elixir_entries(summary, today_date))
    entries.extend(_build_metric_alert_entries(summary))
    entries.extend(_build_action_entries(summary))

    entries.sort(key=_sort_key)
    return entries


def _build_decision_entries(summary: dict[str, Any]) -> list[FeedEntry]:
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


def _build_report_entries(summary: dict[str, Any], today_date: str) -> list[FeedEntry]:
    entries: list[FeedEntry] = []
    for item in _dict_items(summary.get("recent_outputs")):
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
            )
        )
    return entries


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


def _build_action_entries(summary: dict[str, Any]) -> list[FeedEntry]:
    entries: list[FeedEntry] = []
    generated_at = str(summary.get("generated_at") or "")
    for item in _dict_items(summary.get("suggested_next_actions")):
        title = _first_text(item, "title", "label", "name")
        target = _first_text(item, "command", "cli", "action", "path")
        if not title or not target:
            continue
        reason = _first_text(item, "reason", "kind")
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


def _today_date(summary: dict[str, Any]) -> str:
    return _date_part(str(summary.get("generated_at") or ""))


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
    return (_PRIORITY[entry.kind], _reverse_timestamp(entry.timestamp), entry.kind)


def _reverse_timestamp(ts: str) -> str:
    # ISO8601 字典序与时间序一致；反向排序用 negation trick: 取反 char by char
    if not ts:
        return "\x7f"  # 空串排最后（最大 sort key）
    return "".join(chr(0x7F - ord(c)) for c in ts)
