"""Helper functions for aiwiki CLI dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .parsers import build_parser

if TYPE_CHECKING:
    from ..today_feed import FeedEntry


def _flatten_model_retry_args(values: list[str]) -> list[str]:
    models: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in str(value or "").split(","):
            model = item.strip()
            if not model or model in seen:
                continue
            seen.add(model)
            models.append(model)
    return models


# Compat alias for older imports/tests.
_flatten_model_fallback_args = _flatten_model_retry_args


def today_command(root: Path, *, as_json: bool = False) -> int:
    from ..app_shell.summary import build_shell_summary
    from ..today_feed import build_today_feed

    summary = build_shell_summary(root)
    feed = build_today_feed(summary)
    if as_json:
        print(json.dumps(_today_feed_to_json(feed, summary), indent=2, ensure_ascii=False))
        return 0
    print(_render_today_text(feed, summary))
    return 0


def _classify_review_bucket(entry: FeedEntry) -> str:
    """把 needs_review entry (kind=decision) 归到子 bucket。

    Sub-bucket 来源：
    - target 形如 "review:<x>" → "<x>" (e.g. concept_backlog, revisit, mm_actions, judgment_review)
    - title 以 "反证待复核" 开头 → "counter_evidence"
    - title 以 "知识漂移" 开头 → "drift"
    - 其他 → "other"
    """
    target = entry.target or ""
    if target.startswith("review:"):
        return target.split(":", 1)[1].strip() or "other"
    title = entry.title or ""
    if title.startswith("反证待复核"):
        return "counter_evidence"
    if title.startswith("知识漂移"):
        return "drift"
    return "other"


def _feed_entry_to_review_item(entry: FeedEntry) -> dict[str, object]:
    return {
        "title": entry.title,
        "summary": entry.summary,
        "target": entry.target,
        "timestamp": entry.timestamp,
        "protocol": entry.protocol,
        "command": "",
    }


def _first_string(values: object) -> str:
    if not isinstance(values, list):
        return ""
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _review_page_command(item: dict[str, object]) -> str:
    path = str(item.get("path") or "").strip()
    if not path or not bool(item.get("can_review")):
        return ""
    transition = (
        str(item.get("default_transition") or "").strip()
        or _first_string(item.get("preferred_transitions"))
        or _first_string(item.get("allowed_transitions"))
    )
    if not transition:
        return ""
    return f"PYTHONPATH=src python3 -m aiwiki.cli --root . advanced review-page {path} --status {transition}"


def _action_command(item: dict[str, object]) -> str:
    _ = item
    return "PYTHONPATH=src python3 -m aiwiki.cli --root . review-queue --bucket mm_actions --json"


def _page_review_item(item: dict[str, object]) -> dict[str, object]:
    path = str(item.get("path") or "").strip()
    return {
        "id": str(item.get("page_id") or Path(path).stem),
        "title": str(item.get("title") or path),
        "summary": ",".join(str(reason) for reason in item.get("reasons", []) if isinstance(reason, str)),
        "target": path,
        "timestamp": str(item.get("updated_at") or item.get("reviewed_at") or item.get("formed_at") or ""),
        "protocol": str(item.get("protocol") or ""),
        "kind": str(item.get("kind") or ""),
        "status": str(item.get("current_status") or item.get("status") or ""),
        "command": _review_page_command(item),
        "can_review": bool(item.get("can_review")),
        "can_apply": False,
    }


def _action_review_item(item: dict[str, object]) -> dict[str, object]:
    action_id = str(item.get("action_id") or item.get("id") or "").strip()
    target = str(item.get("proposal_path") or item.get("primary_path") or item.get("secondary_path") or action_id)
    return {
        "id": action_id,
        "title": str(item.get("title") or action_id),
        "summary": f"{item.get('kind') or 'action'} · {item.get('current_status') or item.get('status') or ''}".strip(),
        "target": target,
        "timestamp": str(item.get("status_updated_at") or item.get("reviewed_at") or ""),
        "protocol": str(item.get("protocol") or ""),
        "kind": str(item.get("kind") or ""),
        "status": str(item.get("current_status") or item.get("status") or ""),
        "command": _action_command(item),
        "can_review": bool(item.get("can_review")),
        "can_apply": bool(item.get("can_apply")),
    }


def _ready_actions_batch_helper(items: list[dict[str, object]]) -> dict[str, object] | None:
    apply_count = sum(1 for item in items if bool(item.get("can_apply")))
    if apply_count <= 1:
        return None
    return {
        "id": "review-queue-ready-actions",
        "title": f"查看 {apply_count} 条 accepted low-risk actions",
        "summary": "batch-helper · review-queue",
        "target": "review:ready_actions",
        "timestamp": "",
        "protocol": "",
        "kind": "batch-helper",
        "status": "suggested",
        "command": "PYTHONPATH=src python3 -m aiwiki.cli --root . review-queue --bucket ready_actions --json",
        "can_review": True,
        "can_apply": False,
    }


def _review_action_item(item: dict[str, object]) -> dict[str, object]:
    action_id = str(item.get("id") or "").strip()
    return {
        "id": action_id,
        "title": str(item.get("title") or action_id),
        "summary": ",".join(str(reason) for reason in item.get("reason_codes", []) if isinstance(reason, str)),
        "target": str(item.get("page_path") or action_id),
        "timestamp": "",
        "protocol": str(item.get("protocol") or ""),
        "kind": str(item.get("page_kind") or "review-action"),
        "status": str(item.get("status") or ""),
        "command": str(item.get("review_command") or ""),
        "can_review": bool(str(item.get("review_command") or "").strip()),
        "can_apply": False,
    }


def _review_queue_detail_buckets(
    root: Path,
    summary: dict[str, object],
) -> dict[str, list[dict[str, object]]]:
    from ..app_shell.summary import build_review_queue_controls

    buckets: dict[str, list[dict[str, object]]] = {}
    review_controls, execution_controls = build_review_queue_controls(root)
    counts = summary.get("review_backlog_counts")
    review_counts = counts if isinstance(counts, dict) else {}

    def has_backlog(name: str) -> bool:
        try:
            return int(review_counts.get(name, 0) or 0) > 0
        except (TypeError, ValueError):
            return False

    if isinstance(review_controls, dict):
        judgment_pages = [item for item in review_controls.get("judgment_pages", []) if isinstance(item, dict)]
        decision_pages = [item for item in review_controls.get("decision_pages", []) if isinstance(item, dict)]
        review_actions = [item for item in review_controls.get("review_actions", []) if isinstance(item, dict)]

        if has_backlog("pending_judgments"):
            buckets["pending_judgments"] = [_page_review_item(item) for item in judgment_pages]
        if has_backlog("pending_decisions"):
            buckets["pending_decisions"] = [_page_review_item(item) for item in decision_pages]
        if has_backlog("judgment_review_actions"):
            buckets["judgment_review_actions"] = [_review_action_item(item) for item in review_actions]
        if has_backlog("counter_evidence_candidates"):
            buckets["counter_evidence_candidates"] = [
                _review_action_item(item)
                for item in review_actions
                if "counter-evidence-candidate" in {str(reason) for reason in item.get("reason_codes", [])}
            ]
    if isinstance(execution_controls, dict):
        actions = [item for item in execution_controls.get("actions", []) if isinstance(item, dict)]
        actionable = [item for item in actions if bool(item.get("can_apply")) or bool(item.get("can_review"))]
        if has_backlog("machine_memory_actions"):
            buckets["machine_memory_actions"] = [_action_review_item(item) for item in actionable]
        if has_backlog("ready_actions"):
            ready_actions = [
                _action_review_item(item)
                for item in actions
                if str(item.get("current_status") or item.get("status") or "") == "accepted"
                and (bool(item.get("can_apply")) or bool(item.get("can_review")) or bool(item.get("can_revert")))
            ]
            batch_helper = _ready_actions_batch_helper(ready_actions)
            if batch_helper:
                ready_actions.append(batch_helper)
            buckets["ready_actions"] = ready_actions

    return {key: value for key, value in buckets.items() if value}


def review_queue_command(
    root: Path,
    *,
    bucket: str | None = None,
    limit: int | None = None,
    as_json: bool = False,
) -> int:
    """P4-16a: review-queue — 桶化展示 needs_review，与 today 共用 build_today_feed。"""
    from ..app_shell.summary import build_shell_summary
    from ..today_feed import build_today_feed

    summary = build_shell_summary(root)
    feed = build_today_feed(summary, audience="operator")
    decisions = [e for e in feed if e.kind == "decision"]

    buckets: dict[str, list[dict[str, object]]] = {}
    for entry in decisions:
        sub = _classify_review_bucket(entry)
        buckets.setdefault(sub, []).append(_feed_entry_to_review_item(entry))
    buckets.update(_review_queue_detail_buckets(root, summary))

    if bucket:
        bucket_key = bucket.strip()
        buckets = {bucket_key: buckets.get(bucket_key, [])}

    if limit is not None and limit >= 0:
        buckets = {k: v[:limit] for k, v in buckets.items()}

    if as_json:
        out = {
            "generated_at": str(summary.get("generated_at") or ""),
            "active_protocol": str(summary.get("active_protocol") or ""),
            "buckets": {k: v for k, v in sorted(buckets.items())},
            "total": sum(len(v) for v in buckets.values()),
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    lines: list[str] = []
    lines.append("# Review Queue")
    lines.append("")
    lines.append(f"generated_at : {summary.get('generated_at') or ''}")
    lines.append(f"protocol     : {summary.get('active_protocol') or ''}")
    total = sum(len(v) for v in buckets.values())
    lines.append(f"total        : {total}")
    lines.append("")
    if total == 0:
        lines.append("(no pending review)")
    else:
        for bucket_name in sorted(buckets):
            entries = buckets[bucket_name]
            if not entries:
                continue
            lines.append(f"## {bucket_name} ({len(entries)})")
            for e in entries:
                lines.append(f"- {e.get('title') or ''} — {e.get('summary') or ''}")
                if e.get("target"):
                    lines.append(f"    target: {e.get('target')}")
                if e.get("command"):
                    lines.append(f"    command: {e.get('command')}")
            lines.append("")
    print("\n".join(lines).rstrip() + "\n")
    return 0


def _today_feed_to_json(feed: list[FeedEntry], summary: dict[str, object]) -> dict[str, object]:
    """把 today feed 桶化成结构化 dict，对应 _render_today_text 的 section。

    Bucket key 与 _render_today_text 的 section 对齐：
    - todays_reports / automation_status / needs_review / completed_elixirs / suggested_next_actions
    """
    from ..today_feed import priority_for_kind

    buckets: dict[str, list[FeedEntry]] = {
        "report": [],
        "automation": [],
        "decision": [],
        "elixir": [],
        "action": [],
    }
    for entry in feed:
        buckets.setdefault(entry.kind, []).append(entry)
    section_map = [
        ("todays_reports", "report"),
        ("automation_status", "automation"),
        ("needs_review", "decision"),
        ("completed_elixirs", "elixir"),
        ("suggested_next_actions", "action"),
    ]
    out: dict[str, object] = {
        "generated_at": str(summary.get("generated_at") or ""),
        "active_protocol": str(summary.get("active_protocol") or ""),
    }
    for json_key, feed_kind in section_map:
        out[json_key] = [
            {
                "kind": e.kind,
                "title": e.title,
                "summary": e.summary,
                "target": e.target,
                "timestamp": e.timestamp,
                "priority": priority_for_kind(e.kind),
                "protocol": e.protocol,
            }
            for e in buckets.get(feed_kind, [])
        ]
    return out


def trace_command(
    root: Path,
    asset_id: str,
    *,
    direction: str = "up",
    depth: int = 5,
    as_json: bool = False,
) -> int:
    """证据链追溯：渲染 ASCII 树或 JSON。"""
    from aiwiki.trace import render_trace_text, resolve_trace

    node = resolve_trace(root, asset_id, direction=direction, max_depth=depth)
    if as_json:
        print(json.dumps(node.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(render_trace_text(node, direction=direction))
    return 0


def metrics_command(root: Path, *, as_json: bool = False, delta: str | None = None) -> int:
    from aiwiki import metrics_history
    from aiwiki.metrics import compute_metrics
    from aiwiki.metrics_io import build_metrics_snapshot

    snapshot = build_metrics_snapshot(root)
    metrics = compute_metrics(snapshot)

    # M7.3.1 Stage B: append history snapshot (best-effort).
    now_iso = snapshot.now_iso
    # Numeric subset for delta math.
    numeric_metrics = {str(m.key): float(m.value) for m in metrics if isinstance(m.value, (int, float))}
    # Full history record keeps all 7 keys (None becomes null in JSONL) so
    # later samples can always line up against the same schema.
    history_record = {str(m.key): (float(m.value) if isinstance(m.value, (int, float)) else None) for m in metrics}
    metrics_history.append_snapshot(root, now_iso, history_record)

    if as_json:
        print(json.dumps([_metric_to_dict(metric) for metric in metrics], indent=2, ensure_ascii=False))
    else:
        print(_render_metrics_text(metrics))

    if delta:
        window_days = 7 if delta == "7d" else 30
        baseline = metrics_history.find_baseline(root, now_iso, window_days)
        block = metrics_history.format_delta_block(
            window_label=delta,
            baseline=baseline,
            current=numeric_metrics,
        )
        print()
        print(block)

    return 0


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _metric_to_dict(metric) -> dict[str, object]:
    return {
        "key": metric.key,
        "value": metric.value,
        "unit": metric.unit,
        "reason": metric.reason,
        "sample_size": metric.sample_size,
    }


def _render_metrics_text(metrics) -> str:
    lines = ["炼丹炉 Knowledge Compounding Metrics", ""]
    labels = {
        "provenance_completeness": "知识溯源完整度",
        "stale_ratio": "过期页面占比",
        "review_closure_rate": "审议关闭率（7d）",
        "proposal_acceptance_rate": "提案接受率",
        "judgment_revisit_rate": "判断重访率",
        "output_file_back_rate": "输出回流率",
        "elixir_reuse_count": "Elixir 复用次数",
    }
    for metric in metrics:
        key = str(metric.key)
        name = labels.get(key, key)
        value = metric.value
        reason = metric.reason
        unit = metric.unit
        sample_size = metric.sample_size
        if value is None:
            lines.append(f"- {name} ({key}): 不可用 — {reason}")
        else:
            lines.append(f"- {name} ({key}): {value} {unit} (n={sample_size})")
    lines.append("")
    return "\n".join(lines)


def _render_today_text(feed: list[FeedEntry], summary: dict[str, object]) -> str:
    generated_at = str(summary.get("generated_at") or "")
    active_protocol = str(summary.get("active_protocol") or "")
    lines = [
        "炼丹炉 Today",
        f"Generated: {generated_at}",
        f"Active protocol: {active_protocol}",
        "",
    ]

    grouped: dict[str, list[FeedEntry]] = {
        "report": [],
        "automation": [],
        "decision": [],
        "elixir": [],
        "action": [],
    }
    for entry in feed:
        grouped.setdefault(entry.kind, []).append(entry)

    section_specs = [
        ("Today's Reports", "report", "(no reports today)"),
        ("Automation", "automation", "(automation idle)"),
        ("Needs Review", "decision", "(no pending review)"),
        ("Completed Elixirs", "elixir", "(no completed elixirs today)"),
        ("Suggested Next Actions", "action", "(no suggested next actions)"),
    ]

    for heading, kind, empty_msg in section_specs:
        lines.append(heading)
        kind_entries = grouped[kind]
        if kind_entries:
            for entry in kind_entries:
                lines.append(_format_feed_entry_line(entry))
        else:
            lines.append(empty_msg)
        lines.append("")

    lines.extend(
        [
            "Advanced",
            "Run `aiwiki advanced ...` for system status, receipts, audit, repair, and debugging.",
            "Periodic diagnostics: `aiwiki advanced metrics` (compounding snapshot; not a daily path).",
        ]
    )
    return "\n".join(lines)


def _format_feed_entry_line(entry: FeedEntry) -> str:
    """统一 entry 渲染：- [{protocol}] {title} — {summary} — {target}"""
    protocol = entry.protocol or "?"
    return f"- [{protocol}] {entry.title} — {entry.summary} — {entry.target}"


def _maybe_auto_process(root: Path, result: dict[str, object], args: argparse.Namespace) -> dict[str, object]:
    if getattr(args, "no_auto", False):
        return result
    from ..runner.automation import auto_process_once

    auto_result = auto_process_once(root)
    return {
        **result,
        "auto_process": auto_result,
    }


def _read_text_argument(root: Path, value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return path.read_text(encoding="utf-8")
    workspace_path = root / value
    if workspace_path.exists():
        return workspace_path.read_text(encoding="utf-8")
    return path.read_text(encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    return build_parser()
