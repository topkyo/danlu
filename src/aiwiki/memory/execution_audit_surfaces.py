"""Execution audit snapshot + consistency signals + audit page renderer.

Extracted from ``memory.execution_surfaces`` so the remaining surfaces module
owns proposal/quality/rewrite rendering only. Public symbols remain
re-exported from ``execution_surfaces``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..corpus.link_state import load_manual_link_state
from ..lifecycle.status import display_action_status
from ..protocol.descriptors import protocol_title
from ..protocol.runtime_config import LOW_RISK_APPLYABLE_ACTION_KINDS, PENDING_ACTION_STATUSES
from ..state.constants import DEFAULT_PROTOCOL
from ..utils.markdown import parse_frontmatter
from ..utils.path import relative_path
from .action_core import safe_apply_preview
from .action_policy import execution_band_label, execution_policy_profile
from .execution_audit_io import (
    load_execution_policy_decision_history_strict,
    load_execution_receipt_history_strict,
)
from .paths import execution_policy_log_path, execution_receipt_history_path


def collect_execution_consistency_signals(
    root: Path,
    actions: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> list[dict[str, str]]:
    manual_state = load_manual_link_state(root)
    active_manual_links: dict[str, list[dict[str, Any]]] = {}
    for item in manual_state.get("source_to_concept", []):
        if not isinstance(item, dict) or not bool(item.get("active", True)):
            continue
        origin_action_id = str(item.get("origin_action_id") or "")
        if not origin_action_id:
            continue
        active_manual_links.setdefault(origin_action_id, []).append(item)
    latest_receipt_by_action: dict[str, dict[str, Any]] = {}
    for record in history:
        action_id = str(record.get("action_id") or "")
        if action_id and action_id not in latest_receipt_by_action:
            latest_receipt_by_action[action_id] = record

    signals: list[dict[str, str]] = []
    for action in actions:
        action_id = str(action.get("id") or "")
        if not action_id:
            continue
        status = str(action.get("status") or "proposed")
        latest = latest_receipt_by_action.get(action_id)
        latest_operation = str(latest.get("operation") or "") if latest else ""
        latest_preview = latest.get("safe_apply_preview") if isinstance(latest, dict) else None
        if isinstance(latest_preview, dict):
            preview = latest_preview
        elif str(action.get("kind") or "") in LOW_RISK_APPLYABLE_ACTION_KINDS:
            preview = {"apply_mode": "manual-link-state"}
        else:
            preview = safe_apply_preview(root, action)
        if not isinstance(preview, dict):
            continue
        apply_mode = str(preview.get("apply_mode") or "")
        has_active_manual_link = bool(active_manual_links.get(action_id))
        title = str(action.get("title") or action_id)
        primary_path = str(action.get("primary_path") or "")

        if (
            status == "resolved"
            and latest_operation != "apply"
            and apply_mode
            in {
                "manual-link-state",
                "citation-snapshot-refresh",
            }
        ):
            signals.append(
                {
                    "severity": "error",
                    "action_id": action_id,
                    "title": title,
                    "path": primary_path,
                    "message": "动作标记为 resolved，但最新 execution receipt 不是 apply。",
                }
            )
        if apply_mode == "manual-link-state":
            if status == "resolved" and not has_active_manual_link:
                signals.append(
                    {
                        "severity": "error",
                        "action_id": action_id,
                        "title": title,
                        "path": primary_path,
                        "message": "动作标记为 resolved，但 active manual-link state 缺失。",
                    }
                )
            if latest_operation == "revert" and has_active_manual_link:
                signals.append(
                    {
                        "severity": "error",
                        "action_id": action_id,
                        "title": title,
                        "path": primary_path,
                        "message": "最新 receipt 已是 revert，但 manual-link state 仍然 active。",
                    }
                )
            if status in PENDING_ACTION_STATUSES and has_active_manual_link:
                signals.append(
                    {
                        "severity": "warn",
                        "action_id": action_id,
                        "title": title,
                        "path": primary_path,
                        "message": "动作仍在待处理状态，但 manual-link state 仍然 active；需要确认是否应先 revert 或直接 resolve。",
                    }
                )
            continue
        if apply_mode != "citation-snapshot-refresh":
            continue
        page_path = str(preview.get("page_path") or primary_path)
        current_snapshots: list[str] = []
        if page_path and (root / page_path).exists():
            frontmatter = parse_frontmatter((root / page_path).read_text(encoding="utf-8", errors="replace"))
            current_snapshots = [
                str(item)
                for item in frontmatter.get("citation_snapshots", [])
                if isinstance(item, str) and item.strip()
            ]
        expected_snapshots = [
            str(item)
            for item in preview.get("updated_citation_snapshots", [])
            if isinstance(item, str) and item.strip()
        ]
        previous_snapshots = [
            str(item)
            for item in preview.get("previous_citation_snapshots", [])
            if isinstance(item, str) and item.strip()
        ]
        if status == "resolved" and expected_snapshots and current_snapshots != expected_snapshots:
            signals.append(
                {
                    "severity": "error",
                    "action_id": action_id,
                    "title": title,
                    "path": page_path,
                    "message": "动作标记为 resolved，但当前 judgment page 的 citation_snapshots 与 apply receipt 不一致。",
                }
            )
        if latest_operation == "revert" and expected_snapshots and current_snapshots == expected_snapshots:
            signals.append(
                {
                    "severity": "error",
                    "action_id": action_id,
                    "title": title,
                    "path": page_path,
                    "message": "最新 receipt 已是 revert，但 judgment page 仍保留 apply 后的 citation_snapshots。",
                }
            )
        if latest_operation == "revert" and previous_snapshots and current_snapshots != previous_snapshots:
            signals.append(
                {
                    "severity": "warn",
                    "action_id": action_id,
                    "title": title,
                    "path": page_path,
                    "message": "最新 receipt 已是 revert，但 judgment page 的 citation_snapshots 没有恢复到 receipt 里的 previous state。",
                }
            )
        if status in PENDING_ACTION_STATUSES and expected_snapshots and current_snapshots == expected_snapshots:
            signals.append(
                {
                    "severity": "warn",
                    "action_id": action_id,
                    "title": title,
                    "path": page_path,
                    "message": "动作仍在待处理状态，但 judgment page 已经处于 apply 后的 citation_snapshots；需要确认是否应先 revert 或直接 resolve。",
                }
            )
    signals.sort(
        key=lambda item: (
            0 if item.get("severity") == "error" else 1,
            str(item.get("title") or "").lower(),
            str(item.get("message") or ""),
        )
    )
    return signals


def build_execution_audit_snapshot(root: Path, memory: dict[str, Any], *, active_protocol: str) -> dict[str, Any]:
    health = memory.get("health", {})
    actions = [dict(action) for action in health.get("actions", []) if isinstance(action, dict)]
    inactive_actions = [dict(action) for action in health.get("inactive_actions", []) if isinstance(action, dict)]
    all_actions = actions + inactive_actions
    history = load_execution_receipt_history_strict(root)
    policy_history = load_execution_policy_decision_history_strict(root, limit=16)
    recent_apply = [record for record in history if str(record.get("operation") or "") == "apply"][:8]
    recent_revert = [record for record in history if str(record.get("operation") or "") == "revert"][:8]
    recent_by_protocol: dict[str, dict[str, list[dict[str, Any]]]] = {
        "recent_apply": {},
        "recent_revert": {},
    }
    band_counts: dict[str, int] = {}
    protocol_counts: dict[str, int] = {}
    receipt_counts: dict[str, int] = {}
    for record in history:
        protocol = str(record.get("protocol") or DEFAULT_PROTOCOL)
        protocol_counts[protocol] = protocol_counts.get(protocol, 0) + 1
        action_id = str(record.get("action_id") or "")
        if action_id:
            receipt_counts[action_id] = receipt_counts.get(action_id, 0) + 1
        operation = str(record.get("operation") or "")
        if operation in {"apply", "revert"}:
            bucket_name = "recent_apply" if operation == "apply" else "recent_revert"
            scoped = recent_by_protocol[bucket_name].setdefault(protocol, [])
            if len(scoped) < 8:
                scoped.append(record)
    action_rows: list[dict[str, Any]] = []
    for action in all_actions:
        profile = execution_policy_profile(action, root=root)
        band = str(action.get("execution_band") or profile.get("execution_band") or "review-first")
        band_counts[band] = band_counts.get(band, 0) + 1
        action_id = str(action.get("id") or "")
        capabilities = action.get("execution_capability_list")
        if not isinstance(capabilities, list):
            capabilities = list(profile.get("capabilities") or [])
        action_rows.append(
            {
                "id": action_id,
                "title": str(action.get("title") or action_id),
                "status": display_action_status(str(action.get("status") or "proposed")),
                "execution_band": band,
                "execution_band_label": execution_band_label(band),
                "execution_policy": str(action.get("execution_policy") or profile.get("execution_policy") or "triage"),
                "policy_decision": str(action.get("policy_decision") or profile.get("policy_decision") or ""),
                "policy_rule_id": str(action.get("policy_rule_id") or profile.get("policy_rule_id") or ""),
                "execution_capabilities": [str(item) for item in capabilities if isinstance(item, str) and item],
                "policy_summary": str(action.get("policy_summary") or profile.get("policy_summary") or ""),
                "receipt_count": receipt_counts.get(action_id, 0),
                "last_receipt_path": str(action.get("last_receipt_path") or ""),
                "primary_path": str(action.get("primary_path") or ""),
            }
        )
    action_rows.sort(
        key=lambda item: (
            0 if item.get("execution_band") == "bundle-safe-apply" else 1,
            0 if item.get("status") == display_action_status("accepted") else 1,
            str(item.get("title") or "").lower(),
        )
    )
    band_rows = [
        {"band": band, "label": execution_band_label(band), "count": band_counts.get(band, 0)}
        for band in ("bundle-safe-apply", "review-first", "manual-repair", "deferred", "closed", "history-only")
        if band_counts.get(band, 0)
    ]
    protocol_rows = [
        {"protocol": protocol, "title": protocol_title(protocol), "count": count}
        for protocol, count in sorted(protocol_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    consistency_signals = collect_execution_consistency_signals(root, all_actions, history)
    return {
        "compiled_at": str(memory.get("compiled_at") or ""),
        "active_protocol": active_protocol,
        "receipt_history_path": relative_path(root, execution_receipt_history_path(root)),
        "policy_history_path": relative_path(root, execution_policy_log_path(root)),
        "counts": {
            "actions": len(all_actions),
            "receipts": len(history),
            "apply": len([record for record in history if str(record.get("operation") or "") == "apply"]),
            "revert": len([record for record in history if str(record.get("operation") or "") == "revert"]),
            "bundle_safe": band_counts.get("bundle-safe-apply", 0),
            "policy_decisions": len(policy_history),
        },
        "policy_bands": band_rows,
        "protocols": protocol_rows,
        "recent_policy_decisions": policy_history,
        "recent_apply": recent_apply,
        "recent_revert": recent_revert,
        "recent_by_protocol": recent_by_protocol,
        "actions": action_rows[:16],
        "consistency_signals": consistency_signals[:16],
        "consistency_counts": {
            "errors": sum(1 for item in consistency_signals if item.get("severity") == "error"),
            "warns": sum(1 for item in consistency_signals if item.get("severity") == "warn"),
        },
    }


def render_execution_audit(audit: dict[str, Any]) -> str:
    lines = [
        "# 执行审计",
        "",
        f"- 最近编译时间：`{audit.get('compiled_at', '')}`",
        f"- 当前协议：`{audit.get('active_protocol', DEFAULT_PROTOCOL)}` ({protocol_title(str(audit.get('active_protocol') or DEFAULT_PROTOCOL))})",
        f"- 动作总数：`{audit.get('counts', {}).get('actions', 0)}`",
        f"- Receipt 总数：`{audit.get('counts', {}).get('receipts', 0)}`",
        f"- Apply / Revert：`{audit.get('counts', {}).get('apply', 0)}` / `{audit.get('counts', {}).get('revert', 0)}`",
        f"- Bundle-safe actions：`{audit.get('counts', {}).get('bundle_safe', 0)}`",
        f"- Policy decisions：`{audit.get('counts', {}).get('policy_decisions', 0)}`",
        f"- Receipt history：`{audit.get('receipt_history_path', '.aiwiki/state/execution-receipts.jsonl')}`",
        f"- Policy history：`{audit.get('policy_history_path', '.aiwiki/state/execution-policy-decisions.jsonl')}`",
        "",
        "## Policy Bands",
    ]
    band_rows = audit.get("policy_bands", [])
    if not band_rows:
        lines.append("- 当前还没有可审计的 execution policy band。")
    else:
        for row in band_rows:
            lines.append(f"- `{row['band']}` | {row['label']} | count `{row['count']}`")
    lines.extend(["", "## Recent Apply"])
    recent_apply = audit.get("recent_apply", [])
    if not recent_apply:
        lines.append("- 当前还没有 apply receipt。")
    else:
        for receipt in recent_apply:
            lines.append(
                f"- `{receipt.get('title', receipt.get('action_id', 'receipt'))}`"
                f" | action `{receipt.get('action_id', '')}`"
                f" | protocol `{receipt.get('protocol', DEFAULT_PROTOCOL)}`"
                f" | applied `{receipt.get('applied_at', '')}`"
            )
    lines.extend(["", "## Recent Revert"])
    recent_revert = audit.get("recent_revert", [])
    if not recent_revert:
        lines.append("- 当前还没有 revert receipt。")
    else:
        for receipt in recent_revert:
            lines.append(
                f"- `{receipt.get('title', receipt.get('action_id', 'receipt'))}`"
                f" | action `{receipt.get('action_id', '')}`"
                f" | protocol `{receipt.get('protocol', DEFAULT_PROTOCOL)}`"
                f" | reverted `{receipt.get('applied_at', '')}`"
            )
    lines.extend(["", "## Protocol Breakdown"])
    protocols = audit.get("protocols", [])
    if not protocols:
        lines.append("- 当前还没有 protocol 级 execution history。")
    else:
        for row in protocols:
            lines.append(f"- `{row['protocol']}` ({row['title']}) | receipts `{row['count']}`")
    lines.extend(["", "## Recent Policy Decisions"])
    recent_policy_decisions = audit.get("recent_policy_decisions", [])
    if not recent_policy_decisions:
        lines.append("- 当前还没有 execution policy decision 记录。")
    else:
        for record in recent_policy_decisions[:8]:
            lines.append(
                f"- `{record.get('title', record.get('action_id', 'action'))}`"
                f" | action `{record.get('action_id', '')}`"
                f" | decision `{record.get('policy_decision', '') or 'none'}`"
                f" | rule `{record.get('policy_rule_id', '') or 'none'}`"
                f" | occurred `{record.get('occurred_at', '')}`"
            )
    lines.extend(["", "## Consistency Signals"])
    consistency_signals = audit.get("consistency_signals", [])
    if not consistency_signals:
        lines.append("- 当前没有 execution consistency signal。")
    else:
        for signal in consistency_signals:
            lines.append(
                f"- [{signal.get('severity', 'warn')}] `{signal.get('title', signal.get('action_id', 'signal'))}`"
                f" | action `{signal.get('action_id', '')}`"
                f" | {signal.get('message', '')}"
            )
    lines.extend(["", "## Action Audit"])
    actions = audit.get("actions", [])
    if not actions:
        lines.append("- 当前还没有 action audit rows。")
    else:
        for action in actions:
            capabilities = ", ".join(action.get("execution_capabilities", [])) or "none"
            lines.append(
                f"- `{action['title']}`"
                f" | status `{action['status']}`"
                f" | band `{action['execution_band']}`"
                f" | policy `{action['execution_policy']}`"
                f" | decision `{action.get('policy_decision', '') or 'none'}`"
                f" | receipts `{action['receipt_count']}`"
            )
            lines.append(f"  - capabilities: {capabilities}")
            lines.append(f"  - summary: {action.get('policy_summary', 'n/a')}")
            if action.get("policy_rule_id"):
                lines.append(f"  - rule: `{action['policy_rule_id']}`")
            if action.get("last_receipt_path"):
                lines.append(f"  - last receipt: `{action['last_receipt_path']}`")
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [机器记忆修复计划](./machine-memory-repair-plan.md)",
            "- [机器记忆动作队列](./machine-memory-actions.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [炉心面板](./furnace-center.md)",
        ]
    )
    return "\n".join(lines) + "\n"

