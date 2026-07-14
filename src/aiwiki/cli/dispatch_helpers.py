"""Helper functions for aiwiki CLI dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..today_feed import FeedEntry, priority_for_kind


def _dispatch_module():
    return sys.modules["aiwiki.cli.dispatch"]


class _DispatchProxy:
    def __init__(self, name: str) -> None:
        self._name = name

    def __call__(self, *args, **kwargs):
        return getattr(_dispatch_module(), self._name)(*args, **kwargs)


build_shell_summary = _DispatchProxy("build_shell_summary")
build_today_feed = _DispatchProxy("build_today_feed")
load_today_snooze_state = _DispatchProxy("load_today_snooze_state")
save_today_snooze_state = _DispatchProxy("save_today_snooze_state")
review_pages_batch = _DispatchProxy("review_pages_batch")
review_page = _DispatchProxy("review_page")
review_machine_memory_actions_batch = _DispatchProxy("review_machine_memory_actions_batch")
apply_machine_memory_actions_batch = _DispatchProxy("apply_machine_memory_actions_batch")
load_machine_memory_action_state = _DispatchProxy("load_machine_memory_action_state")
resolve_machine_memory_action_query = _DispatchProxy("resolve_machine_memory_action_query")
action_supports_low_risk_apply = _DispatchProxy("action_supports_low_risk_apply")
auto_process_once = _DispatchProxy("auto_process_once")
build_parser = _DispatchProxy("build_parser")


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


def _latest_run_compile_summary(root: Path) -> dict[str, object]:
    path = root / ".aiwiki" / "logs" / "runs.jsonl"
    if not path.exists():
        return {}
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("event") == "run-compile-summary":
            return payload
    return {}


def _print_run_compile_fail_fast_breadcrumb(result: dict[str, object]) -> None:
    for stage, prefix in [
        ("pages", "pages"),
        ("concept_pages", "concept_pages"),
        ("rewrite_concept_pages", "rewrite_concept_pages"),
    ]:
        failed = int(result.get(f"failed_{prefix}", 0) or 0)
        remaining = int(result.get(f"remaining_{prefix}", 0) or 0)
        attempted = int(result.get(f"attempted_{prefix}", 0) or 0)
        succeeded = int(result.get(f"succeeded_{prefix}", 0) or 0)
        if failed > 0 or remaining > 0:
            print(
                f"aiwiki: → run-compile aborted at {stage}: "
                f"attempted={attempted} succeeded={succeeded} "
                f"failed={failed} remaining={remaining} (fail-fast). "
                f"Re-run after addressing the failure.",
                file=sys.stderr,
            )

def today_command(root: Path, *, as_json: bool = False) -> int:
    summary = build_shell_summary(root)
    feed = build_today_feed(summary)
    if as_json:
        print(json.dumps(_today_feed_to_json(feed, summary), indent=2, ensure_ascii=False))
        return 0
    print(_render_today_text(feed, summary))
    return 0


def today_snooze_command(root: Path, *, target: str, days: int = 1, note: str = "") -> dict[str, object]:
    target_text = str(target or "").strip()
    if not target_text:
        raise ValueError("today-snooze requires a non-empty target.")
    if days <= 0:
        raise ValueError("--days must be greater than 0.")
    state = load_today_snooze_state(root)
    now = datetime.now(timezone.utc)
    # Inclusive date filter in today_feed means days=1 should hide only today.
    snoozed_until = (now + timedelta(days=days - 1)).date().isoformat()
    items = [
        dict(item)
        for item in state.get("items", [])
        if isinstance(item, dict) and str(item.get("target") or "").strip() != target_text
    ]
    item = {
        "target": target_text,
        "snoozed_at": now.isoformat(),
        "snoozed_until": snoozed_until,
        "note": str(note or ""),
    }
    items.append(item)
    save_today_snooze_state(root, {"version": 1, "items": items})
    return {"operation": "today-snooze", "status": "snoozed", **item}


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
    return f"PYTHONPATH=src python3 -m aiwiki.cli --root . review-page {path} --status {transition}"


def _action_command(item: dict[str, object]) -> str:
    action_id = str(item.get("action_id") or item.get("id") or "").strip()
    if not action_id:
        return ""
    if bool(item.get("can_apply")):
        return f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run"
    if bool(item.get("can_review")):
        transition = (
            str(item.get("default_transition") or "").strip()
            or _first_string(item.get("preferred_transitions"))
            or _first_string(item.get("allowed_transitions"))
        )
        if transition:
            return f"PYTHONPATH=src python3 -m aiwiki.cli --root . review-action {action_id} --status {transition}"
    if bool(item.get("can_revert")):
        return f"PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {action_id}"
    return ""


def _l3_command(item: dict[str, object]) -> str:
    hints = item.get("command_hints")
    if not isinstance(hints, dict):
        return ""
    for key in ("apply", "reject", "revert"):
        command = hints.get(key)
        if isinstance(command, str) and command.strip():
            return command.strip()
    return ""


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
        "id": "batch-apply-all-accepted-low-risk",
        "title": f"批量预览 {apply_count} 条 accepted low-risk actions",
        "summary": "batch-helper · dry-run first",
        "target": "review:ready_actions",
        "timestamp": "",
        "protocol": "",
        "kind": "batch-helper",
        "status": "suggested",
        "command": "PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action --all-accepted-low-risk --dry-run",
        "can_review": False,
        "can_apply": True,
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


def _l3_review_item(item: dict[str, object]) -> dict[str, object]:
    proposal_id = str(item.get("proposal_id") or "").strip()
    return {
        "id": proposal_id,
        "title": str(item.get("target_file") or proposal_id),
        "summary": f"{item.get('kind') or 'proposal'} · {item.get('current_status') or item.get('state') or ''}".strip(),
        "target": str(item.get("proposal_path") or item.get("target_file") or proposal_id),
        "timestamp": str(item.get("created_at") or item.get("accepted_at") or item.get("reverted_at") or ""),
        "protocol": str(item.get("protocol") or ""),
        "kind": str(item.get("kind") or "proposal"),
        "status": str(item.get("current_status") or item.get("state") or ""),
        "command": _l3_command(item),
        "can_review": bool(item.get("can_review")),
        "can_apply": bool(item.get("can_apply")),
    }


def _review_queue_detail_buckets(summary: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    buckets: dict[str, list[dict[str, object]]] = {}
    review_controls = summary.get("review_controls")
    execution_controls = summary.get("execution_controls")
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
        l3_proposals = [item for item in review_controls.get("l3_proposals", []) if isinstance(item, dict)]

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
        if has_backlog("l3_proposals"):
            buckets["l3_proposals"] = [_l3_review_item(item) for item in l3_proposals if bool(item.get("needs_attention"))]

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
    summary = build_shell_summary(root)
    feed = build_today_feed(summary, audience="operator")
    decisions = [e for e in feed if e.kind == "decision"]

    buckets: dict[str, list[dict[str, object]]] = {}
    for entry in decisions:
        sub = _classify_review_bucket(entry)
        buckets.setdefault(sub, []).append(_feed_entry_to_review_item(entry))
    buckets.update(_review_queue_detail_buckets(summary))

    if bucket:
        bucket_key = bucket.strip()
        buckets = {bucket_key: buckets.get(bucket_key, [])}

    if limit is not None and limit >= 0:
        buckets = {k: v[:limit] for k, v in buckets.items()}

    if as_json:
        out = {
            "generated_at": str(summary.get("generated_at") or ""),
            "active_protocol": str(summary.get("active_protocol") or ""),
            "buckets": {
                k: v
                for k, v in sorted(buckets.items())
            },
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
    """把 today feed 桶化成结构化 dict，对应 _render_today_text 的 5 个 section。

    Bucket key 与 _render_today_text 的 section 对齐：
    - todays_reports / automation_status / needs_review / completed_elixirs / l3_proposals / suggested_next_actions
    """
    buckets: dict[str, list[FeedEntry]] = {
        "report": [],
        "automation": [],
        "decision": [],
        "elixir": [],
        "proposal": [],
        "action": [],
    }
    for entry in feed:
        buckets.setdefault(entry.kind, []).append(entry)
    section_map = [
        ("todays_reports", "report"),
        ("automation_status", "automation"),
        ("needs_review", "decision"),
        ("completed_elixirs", "elixir"),
        ("l3_proposals", "proposal"),
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
    numeric_metrics = {
        str(m.key): float(m.value)
        for m in metrics
        if isinstance(m.value, (int, float))
    }
    # Full history record keeps all 7 keys (None becomes null in JSONL) so
    # later samples can always line up against the same schema.
    history_record = {
        str(m.key): (float(m.value) if isinstance(m.value, (int, float)) else None)
        for m in metrics
    }
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


def autonomy_status_command(root: Path, *, as_json: bool = False) -> int:
    from aiwiki import autonomy_policy

    status = autonomy_policy.policy_status(root)
    if as_json:
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0
    lines = [
        f"policy file : {status['policy_path']}",
        f"file exists : {status['policy_file_exists']}",
        f"global env  : {status['global_override_env']} = {'1 (active)' if status['global_override_active'] else 'unset'}",
        "flags:",
    ]
    for name, info in status["flags"].items():
        marker = "DISABLED" if info["effective"] else "enabled "
        reason = f"  ({info['reason']})" if info["reason"] else ""
        lines.append(f"  [{marker}] {name}  file_value={info['file_value']}{reason}")
    print("\n".join(lines))
    return 0


def autonomy_set_command(root: Path, *, flag: str, value: bool) -> int:
    import sys

    from aiwiki import autonomy_policy

    if flag not in autonomy_policy.KNOWN_FLAGS:
        print(
            f"Unknown autonomy flag: {flag}. Known flags: {', '.join(autonomy_policy.KNOWN_FLAGS)}",
            file=sys.stderr,
        )
        return 2
    autonomy_policy.set_flag(root, flag, value)
    action = "disabled" if value else "enabled"
    print(f"autonomy flag {flag} → {action} (file: {autonomy_policy.policy_path(root)})")
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
        "proposal": [],
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
        ("L3 Proposals", "proposal", "(no L3 proposals need attention)"),
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
            "Run `aiwiki advanced ...` for system status, receipts, audit, repair, lanes, and debugging.",
            "Run `aiwiki metrics` for knowledge compounding metrics.",
        ]
    )
    return "\n".join(lines)


def _format_feed_entry_line(entry: FeedEntry) -> str:
    """统一 entry 渲染：- [{protocol}] {title} — {summary} — {target}"""
    protocol = entry.protocol or "?"
    return f"- [{protocol}] {entry.title} — {entry.summary} — {entry.target}"


def _format_signal_summary_line(record: dict[str, object]) -> str:
    scope_protocol = ""
    scope = record.get("scope")
    if isinstance(scope, dict):
        scope_protocol = str(scope.get("protocol") or "")
    return "  ".join(
        [
            str(record.get("signal_id") or ""),
            str(record.get("kind") or ""),
            str(record.get("severity") or ""),
            str(record.get("emitted_at") or ""),
            scope_protocol,
            str(record.get("source_event_ref") or ""),
        ]
    )


def _format_planner_decision_summary_line(record: dict[str, object]) -> str:
    reason_codes = record.get("reason_codes")
    if isinstance(reason_codes, list):
        rendered_reasons = json.dumps(reason_codes, ensure_ascii=False)
    else:
        rendered_reasons = str(reason_codes or "[]")
    return "  ".join(
        [
            str(record.get("decided_at") or ""),
            str(record.get("decision") or ""),
            str(record.get("mode") or ""),
            str(record.get("signal_id") or ""),
            rendered_reasons,
        ]
    )


def _format_l3_proposal_summary_line(record: dict[str, object]) -> str:
    return "  ".join(
        [
            str(record.get("proposal_id") or ""),
            str(record.get("kind") or ""),
            str(record.get("state") or ""),
            str(record.get("target_file") or ""),
            str(record.get("proposal_path") or ""),
        ]
    )


def _format_l3_generation_preview_line(record: dict[str, object]) -> str:
    blockers = record.get("blockers")
    if isinstance(blockers, list):
        rendered_blockers = json.dumps(blockers, ensure_ascii=False)
    else:
        rendered_blockers = str(blockers or "[]")
    return "  ".join(
        [
            str(record.get("decided_at") or ""),
            str(record.get("signal_id") or ""),
            str(record.get("proposal_kind") or "unknown"),
            "blocked",
            rendered_blockers,
        ]
    )


def _format_signal_show_text(signal: dict[str, object], planner_decisions: list[object]) -> str:
    lines = [f"Signal: {str(signal.get('signal_id') or '')}"]
    for key in sorted(signal):
        value = signal[key]
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            rendered = str(value)
        lines.append(f"  {key}: {rendered}")
    lines.append("Related planner decisions:")
    decisions = [item for item in planner_decisions if isinstance(item, dict)]
    if not decisions:
        lines.append("  (none)")
    else:
        for decision in decisions:
            lines.append(f"  - {_format_planner_decision_summary_line(decision)}")
    return "\n".join(lines)



_LEGACY_DROP_REPLACEMENTS = {
    "drop-url": "drop url",
    "drop-pdf": "drop pdf",
    "drop-image": "drop image",
    "drop-repo": "drop repo",
    "drop-note": "drop markdown",
}


def _emit_legacy_drop_deprecation_warning(args: argparse.Namespace) -> None:
    if args.handler_command not in _LEGACY_DROP_REPLACEMENTS:
        return
    if args.command != args.handler_command:
        return
    replacement = _LEGACY_DROP_REPLACEMENTS[args.handler_command]
    print(
        f"[deprecated] `aiwiki {args.handler_command}` is deprecated; use `aiwiki {replacement}` instead.",
        file=sys.stderr,
    )


def _maybe_auto_process(root: Path, result: dict[str, object], args: argparse.Namespace) -> dict[str, object]:
    if not getattr(args, "auto", False):
        return result
    deterministic_only = not bool(getattr(args, "with_llm", False)) or bool(getattr(args, "deterministic_only", False))
    auto_result = auto_process_once(
        root,
        deterministic_only=deterministic_only,
        semantic_lint=not getattr(args, "no_semantic_lint", False),
    )
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


def _pending_review_pages(root: Path) -> list[str]:
    summary = build_shell_summary(root)
    review_controls = summary.get("review_controls", {})
    if not isinstance(review_controls, dict):
        review_controls = {}
    pending: list[str] = []
    for candidate in review_controls.get("pages", []):
        if not isinstance(candidate, dict) or not candidate.get("can_review"):
            continue
        candidate_path = str(candidate.get("path") or "")
        if candidate_path:
            pending.append(candidate_path)
    return pending


def _handle_batch_review_alias(root: Path, args: argparse.Namespace) -> dict[str, object]:
    note = (getattr(args, "note", None) or "").strip()
    if not note:
        raise ValueError("batch-review --note is required (audit trail).")
    target = getattr(args, "target", "") or ""
    annotated_note = f"[batch-alias] {note}"
    if target == "pages":
        pages = _dispatch_module()._resolve_review_pages(root, None, use_next=False, batch=None, all_pending=True)
        if not pages:
            raise RuntimeError("No pending review pages.")
        status = (getattr(args, "status", None) or "tracking").strip() or "tracking"
        result = review_pages_batch(root, pages, status, note=annotated_note, confidence=None)
    elif target == "action":
        kind = (getattr(args, "kind", None) or "").strip()
        if not kind:
            raise ValueError("batch-review action requires --kind.")
        execution_band = (getattr(args, "execution_band", None) or "review-first").strip() or "review-first"
        action_ids = _dispatch_module()._resolve_review_action_ids(
            root,
            [],
            all_pending=True,
            kind=kind,
            execution_band=execution_band,
        )
        if not action_ids:
            raise RuntimeError(f"No pending {kind} actions in execution_band={execution_band}.")
        status = (getattr(args, "status", None) or "accepted").strip() or "accepted"
        result = review_machine_memory_actions_batch(root, action_ids, status, note=annotated_note)
    elif target == "apply-low-risk":
        action_ids = _dispatch_module()._resolve_action_ids(
            root,
            None,
            batch=None,
            all_accepted_low_risk=True,
        )
        if not action_ids:
            raise RuntimeError("No accepted low-risk actions ready for batch apply.")
        result = apply_machine_memory_actions_batch(
            root,
            action_ids,
            note=annotated_note,
            dry_run=bool(getattr(args, "dry_run", False)),
        )
    else:
        raise ValueError(f"Unknown batch-review target: {target!r}.")
    if isinstance(result, dict):
        result.setdefault("triggered_by", "batch-alias")
        result.setdefault("alias_target", target)
    return result


def _format_review_next_surface(page: dict[str, object]) -> str:
    title = str(page.get("title") or page.get("path") or "review-page")
    path = str(page.get("path") or "")
    page_kind = str(page.get("kind") or "page")
    default_transition = str(page.get("default_transition") or "")
    allowed = page.get("allowed_transitions") or []
    if not isinstance(allowed, list):
        allowed = []
    reasons = page.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = []
    lines = [
        f"=== {title}",
        f"  path     : {path}",
        f"  kind     : {page_kind}",
        f"  reasons  : {', '.join(str(r) for r in reasons[:5]) or '-'}",
        f"  default  : {default_transition or '-'}",
        f"  allowed  : {', '.join(str(a) for a in allowed[:6]) or '-'}",
    ]
    return "\n".join(lines)


_REVIEW_NEXT_CHOICES: dict[str, str] = {
    "a": "accepted",
    "r": "rejected",
    "t": "tracking",
}


def _handle_review_next(root: Path, args: argparse.Namespace) -> dict[str, object]:
    limit = max(1, int(getattr(args, "limit", 1) or 1))
    non_interactive = bool(getattr(args, "non_interactive", False))
    note = getattr(args, "note", None)
    annotated_note = f"[review-next] {note.strip()}" if isinstance(note, str) and note.strip() else "[review-next]"

    summary = build_shell_summary(root)
    review_controls = summary.get("review_controls", {}) if isinstance(summary, dict) else {}
    pages_raw = review_controls.get("pages", []) if isinstance(review_controls, dict) else []
    pending = [p for p in pages_raw if isinstance(p, dict) and p.get("can_review") and p.get("path")]
    pending = pending[:limit]

    surfaces: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    for page in pending:
        block = _format_review_next_surface(page)
        surfaces.append({"path": str(page.get("path") or ""), "surface": block, "default_transition": str(page.get("default_transition") or "")})
        if non_interactive:
            print(block, file=sys.stderr)
            print("  prompt    : [a]ccept / [r]eject / [t]rack / [s]kip / [q]uit", file=sys.stderr)
            continue

        print(block, file=sys.stderr)
        choice = input("  [a]ccept / [r]eject / [t]rack / [s]kip / [q]uit > ").strip().lower()
        if choice in {"q", "quit"}:
            break
        if choice in {"s", "skip", ""}:
            decisions.append({"path": page.get("path"), "skipped": True})
            continue
        target_status = _REVIEW_NEXT_CHOICES.get(choice[:1])
        if not target_status:
            allowed = page.get("allowed_transitions") or []
            target_status = str(page.get("default_transition") or (allowed[0] if isinstance(allowed, list) and allowed else "tracking"))
        receipt = review_page(
            root,
            str(page.get("path") or ""),
            target_status,
            note=annotated_note,
            confidence=None,
        )
        if isinstance(receipt, dict):
            receipt.setdefault("triggered_by", "review-next")
        decisions.append({"path": page.get("path"), "status": target_status, "receipt": receipt})

    return {
        "operation": "review-next",
        "non_interactive": non_interactive,
        "limit": limit,
        "surfaced_count": len(surfaces),
        "surfaces": surfaces,
        "decisions": decisions,
        "triggered_by": "review-next",
    }


def _resolve_review_pages(
    root: Path,
    page: str | None,
    *,
    use_next: bool,
    batch: list[str] | None,
    all_pending: bool,
) -> list[str]:
    selected_modes = int(bool(use_next)) + int(bool(batch)) + int(bool(all_pending))
    if page and selected_modes:
        raise ValueError("Use PAGE by itself, or choose exactly one of --next/--batch/--all-pending.")
    if selected_modes > 1:
        raise ValueError("Choose only one of --next, --batch, or --all-pending.")
    if use_next:
        pending = _pending_review_pages(root)
        if not pending:
            raise RuntimeError("No review page is ready for --next.")
        return [pending[0]]
    if batch:
        return [item for item in batch if item.strip()]
    if all_pending:
        pending = _pending_review_pages(root)
        if not pending:
            raise RuntimeError("No review pages are currently pending.")
        return pending
    if page:
        return [page]
    raise ValueError("Provide a review page path or use --next/--batch/--all-pending.")


def _resolve_review_concept_slugs(
    root: Path,
    slugs: list[str],
    *,
    all_pending: bool,
) -> list[str]:
    """Resolve concept slugs for ``review-concept``.

    - Mutually exclusive: explicit slugs vs ``--all-pending``.
    - ``--all-pending`` enumerates concepts whose heuristic
      ``lifecycle_state`` is currently ``revisit`` or ``review`` (the two
      buckets that this command is built to drain).
    - Override-active concepts are skipped (no point re-acking).
    """
    cleaned = [s.strip() for s in slugs if isinstance(s, str) and s.strip()]
    if all_pending and cleaned:
        raise ValueError("Pass slugs OR --all-pending, not both.")
    if cleaned:
        return cleaned
    if not all_pending:
        raise ValueError("Provide at least one slug or pass --all-pending.")
    # Lazy import to avoid heavy app_compile import at module load time.
    from ..execution.lifecycle import refresh_knowledge_lifecycle_runtime as _refresh

    lifecycle = _refresh(root)
    pending: list[str] = []
    for entry in lifecycle.get("entries", []) or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("kind") or "") != "concept":
            continue
        if bool(entry.get("override_active")):
            continue
        if str(entry.get("lifecycle_state") or "") not in {"revisit", "review"}:
            continue
        slug = str(entry.get("slug") or "").strip()
        if not slug:
            # Lifecycle concept entries currently expose only ``path`` (e.g.
            # ``wiki/concepts/foo.md``); derive slug from the file stem.
            path = str(entry.get("path") or "")
            if path:
                slug = Path(path).stem
        if slug:
            pending.append(slug)
    if not pending:
        raise RuntimeError("No concepts are currently in the revisit/review buckets.")
    # Stable order: by lifecycle_state then slug.
    pending.sort()
    return pending


def _resolve_action_id(root: Path, action_query: str) -> str:
    normalized_query = action_query.strip()
    if not normalized_query:
        raise ValueError("Action id cannot be empty.")
    state = load_machine_memory_action_state(root)
    actions = [action for action in state.get("actions", []) if isinstance(action, dict)]
    if not actions:
        return normalized_query
    return str(resolve_machine_memory_action_query(actions, normalized_query).get("id") or normalized_query)


def _resolve_review_action_ids(
    root: Path,
    action_queries: list[str],
    *,
    all_pending: bool,
    kind: str | None,
    execution_band: str | None,
) -> list[str]:
    cleaned = [item.strip() for item in action_queries if isinstance(item, str) and item.strip()]
    if all_pending and cleaned:
        raise ValueError("Pass action ids OR --all-pending, not both.")
    if cleaned:
        return [_resolve_action_id(root, item) for item in cleaned]
    if not all_pending:
        raise ValueError("Provide at least one action id or pass --all-pending with --kind.")
    normalized_kind = (kind or "").strip()
    if not normalized_kind:
        raise ValueError("review-action --all-pending requires --kind to avoid broad action triage.")
    normalized_band = (execution_band or "review-first").strip() or "review-first"
    state = load_machine_memory_action_state(root)
    action_ids = [
        str(action.get("id") or "")
        for action in state.get("actions", [])
        if isinstance(action, dict)
        and str(action.get("id") or "")
        and bool(action.get("active", True))
        and str(action.get("status") or "") == "proposed"
        and str(action.get("policy_decision") or "") == "review"
        and str(action.get("kind") or "") == normalized_kind
        and str(action.get("execution_band") or "") == normalized_band
    ]
    if not action_ids:
        raise RuntimeError(
            "No proposed machine-memory actions match "
            f"kind={normalized_kind!r} execution_band={normalized_band!r}."
        )
    return action_ids


def _resolve_action_ids(
    root: Path,
    action_id: str | None,
    *,
    batch: list[str] | None,
    all_accepted_low_risk: bool,
) -> list[str]:
    selected_modes = int(bool(action_id)) + int(bool(batch)) + int(bool(all_accepted_low_risk))
    if selected_modes != 1:
        raise ValueError("Provide one action id, or use exactly one of --batch/--all-accepted-low-risk.")
    if action_id:
        return [_resolve_action_id(root, action_id)]
    if batch:
        return [_resolve_action_id(root, item) for item in batch if item.strip()]
    state = load_machine_memory_action_state(root)
    action_ids = [
        str(action.get("id") or "")
        for action in state.get("actions", [])
        if isinstance(action, dict)
        and action_supports_low_risk_apply(action)
    ]
    if not action_ids:
        raise RuntimeError("No accepted low-risk actions are ready for batch apply.")
    return action_ids
