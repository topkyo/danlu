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
    entries.extend(_build_proposal_entries(summary))
    entries.extend(_build_report_entries(summary, today_date))
    entries.extend(_build_elixir_entries(summary, today_date))
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
        entries.append(
            FeedEntry(
                kind="decision",
                title=f"待审议: {kind_text}",
                summary=f"{count} 项待审",
                target=f"review:{kind_text}",
                timestamp=timestamp,
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
