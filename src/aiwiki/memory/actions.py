"""Machine-memory action reconciliation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..app_lifecycle import action_needs_review, evaluate_page_aging
from ..app_protocol import (
    ACTION_STATUSES,
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    PENDING_ACTION_STATUSES,
    RESOLVABLE_MONITOR_ACTION_KINDS,
    schedule_review_windows,
)
from ..app_state import (
    DEFAULT_PROTOCOL,
    load_machine_memory_action_state_strict,
    machine_memory_action_state_path,
    save_machine_memory_action_state,
)
from ..app_utils import parse_iso_datetime, relative_path
from ..content.memory import (
    action_priority_rank,
    action_status_rank,
    describe_machine_memory_action,
    safe_apply_preview,
    validate_low_risk_action_targets,
)


def reconcile_machine_memory_actions(
    root: Path,
    health: dict[str, Any],
    *,
    compiled_at: str,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    previous_state = load_machine_memory_action_state_strict(root)
    previous_by_id = {
        str(action.get("id")): action for action in previous_state.get("actions", []) if action.get("id")
    }
    now = parse_iso_datetime(compiled_at) or datetime.now(timezone.utc)
    active_records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for action in health.get("actions", []):
        action_id = str(action.get("id") or "").strip()
        if not action_id:
            continue
        previous = previous_by_id.get(action_id, {})
        previous_status = str(previous.get("status") or "proposed")
        protocol = str(previous.get("protocol") or action.get("protocol") or active_protocol or DEFAULT_PROTOCOL)
        status = previous_status if previous_status in ACTION_STATUSES else "proposed"
        reopened_count = int(previous.get("reopened_count") or 0)
        reopened_from = ""
        if previous and previous.get("active") is False and status in {"resolved", "rejected"}:
            reopened_from = status
            reopened_count += 1
            status = "proposed"
        first_seen_at = str(previous.get("first_seen_at") or compiled_at)
        occurrences = int(previous.get("occurrences") or 0)
        if occurrences <= 0:
            occurrences = 1
        else:
            occurrences += 1
        status_updated_at = str(previous.get("status_updated_at") or first_seen_at)
        if status != previous_status or not status_updated_at:
            status_updated_at = compiled_at
        reviewed_at = str(previous.get("reviewed_at") or "")
        review_note = str(previous.get("review_note") or "")
        last_receipt_path = str(previous.get("last_receipt_path") or "")
        auto_resolution = previous.get("auto_resolution") if isinstance(previous.get("auto_resolution"), dict) else None
        keep_auto_exception = (
            status == "deferred"
            and str(previous.get("human_required") or "").lower() == "true"
            and str(previous.get("human_required_reason") or "").strip()
        )
        human_required = str(previous.get("human_required") or "") if keep_auto_exception else ""
        human_required_reason = str(previous.get("human_required_reason") or "") if keep_auto_exception else ""
        revert_supported = str(previous.get("revert_supported") or "") if keep_auto_exception else ""
        revisit_after = str(previous.get("revisit_after") or "")
        escalate_after = str(previous.get("escalate_after") or "")
        if status in PENDING_ACTION_STATUSES:
            if not revisit_after and not escalate_after:
                base_timestamp = reviewed_at or status_updated_at or first_seen_at
                revisit_after, escalate_after = schedule_review_windows(
                    "action",
                    status,
                    base_timestamp,
                    protocol=protocol,
                    root=root,
                )
        else:
            revisit_after, escalate_after = "", ""
        record = {
            **action,
            "protocol": protocol,
            "status": status,
            "active": True,
            "first_seen_at": first_seen_at,
            "last_seen_at": compiled_at,
            "occurrences": occurrences,
            "status_updated_at": status_updated_at,
            "reviewed_at": reviewed_at,
            "review_note": review_note,
            "last_receipt_path": last_receipt_path,
            "revisit_after": revisit_after,
            "escalate_after": escalate_after,
            "reopened_count": reopened_count,
            "reopened_from": reopened_from,
            "inactive_since": "",
            "pending_review": "true" if action_needs_review(status) else "false",
        }
        if keep_auto_exception:
            record["human_required"] = human_required
            record["human_required_reason"] = human_required_reason
            record["revert_supported"] = revert_supported
        if keep_auto_exception and auto_resolution is not None:
            record["auto_resolution"] = dict(auto_resolution)
        record.update(evaluate_page_aging(record, now=now))
        active_records.append(record)
        seen_ids.add(action_id)

    inactive_records: list[dict[str, Any]] = []
    for action_id, previous in previous_by_id.items():
        if action_id in seen_ids:
            continue
        preserved_pending = (
            bool(previous.get("active", True))
            and str(previous.get("status") or "") in PENDING_ACTION_STATUSES
        )
        if preserved_pending:
            preview = safe_apply_preview(root, previous)
            kind = str(previous.get("kind") or "")
            if kind in LOW_RISK_APPLYABLE_ACTION_KINDS:
                try:
                    validate_low_risk_action_targets(root, previous)
                except RuntimeError:
                    preserved_pending = False
            elif kind in RESOLVABLE_MONITOR_ACTION_KINDS:
                # Monitor actions are signal-driven: if they disappear from the
                # current candidate set the underlying signal is gone.
                preserved_pending = False
            elif not isinstance(preview, dict):
                preserved_pending = False
        if preserved_pending:
            status = str(previous.get("status") or "proposed")
            reviewed_at = str(previous.get("reviewed_at") or "")
            first_seen_at = str(previous.get("first_seen_at") or compiled_at)
            status_updated_at = str(previous.get("status_updated_at") or first_seen_at)
            revisit_after = str(previous.get("revisit_after") or "")
            escalate_after = str(previous.get("escalate_after") or "")
            if not revisit_after and not escalate_after:
                base_timestamp = reviewed_at or status_updated_at or first_seen_at
                revisit_after, escalate_after = schedule_review_windows(
                    "action",
                    status,
                    base_timestamp,
                    protocol=str(previous.get("protocol") or active_protocol or DEFAULT_PROTOCOL),
                    root=root,
                )
            record = {
                **dict(previous),
                "protocol": str(previous.get("protocol") or active_protocol or DEFAULT_PROTOCOL),
                "status": status,
                "active": True,
                "last_seen_at": compiled_at,
                "inactive_since": "",
                "pending_review": "true" if action_needs_review(status) else "false",
                "revisit_after": revisit_after,
                "escalate_after": escalate_after,
            }
            record.update(evaluate_page_aging(record, now=now))
            active_records.append(record)
            seen_ids.add(action_id)
            continue
        record = dict(previous)
        record["protocol"] = str(previous.get("protocol") or active_protocol or DEFAULT_PROTOCOL)
        record["active"] = False
        record["inactive_since"] = str(previous.get("inactive_since") or compiled_at)
        record["pending_review"] = "false"
        record["aging_state"] = ""
        record["overdue_review"] = "false"
        record["escalation_candidate"] = "false"
        inactive_records.append(record)

    active_records.sort(
        key=lambda item: (
            action_status_rank(str(item.get("status"))),
            action_priority_rank(str(item.get("priority"))),
            -int(item.get("occurrences", 0)),
            -int(item.get("score", 0)),
            str(item.get("title", "")).lower(),
        )
    )
    inactive_records.sort(
        key=lambda item: (
            str(item.get("inactive_since") or item.get("last_seen_at") or ""),
            str(item.get("title", "")).lower(),
        ),
        reverse=True,
    )
    overdue_actions = [record for record in active_records if record.get("overdue_review") == "true"]
    escalated_actions = [record for record in active_records if record.get("escalation_candidate") == "true"]
    active_records = [{**record, **describe_machine_memory_action(record, root=root)} for record in active_records]
    inactive_records = [{**record, **describe_machine_memory_action(record, root=root)} for record in inactive_records]
    overdue_actions = [{**record, **describe_machine_memory_action(record, root=root)} for record in overdue_actions]
    escalated_actions = [{**record, **describe_machine_memory_action(record, root=root)} for record in escalated_actions]
    counts = {
        "total": len(active_records),
        "inactive": len(inactive_records),
        "overdue": len(overdue_actions),
        "escalated": len(escalated_actions),
        "by_priority": {
            priority: sum(1 for action in active_records if action.get("priority") == priority)
            for priority in ("high", "medium", "low")
        },
        "by_status": {
            status: sum(1 for action in active_records if action.get("status") == status)
            for status in ACTION_STATUSES
        },
        "by_kind": {
            kind: sum(1 for action in active_records if action.get("kind") == kind)
            for kind in (
                "add-source-concept-link",
                "connect-isolated-source",
                "expand-singleton-concept",
                "split-overloaded-concept",
                "monitor-bridge-concept",
            )
        },
    }
    state_document = {
        "version": 1,
        "compiled_at": compiled_at,
        "actions": active_records + inactive_records,
    }
    save_machine_memory_action_state(root, state_document)
    return {
        "actions": active_records[:20],
        "inactive_actions": inactive_records[:12],
        "overdue_actions": overdue_actions[:10],
        "escalated_actions": escalated_actions[:10],
        "action_counts": counts,
        "action_state_path": relative_path(root, machine_memory_action_state_path(root)),
    }
