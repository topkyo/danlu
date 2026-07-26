"""Machine-memory auto-resolution policy and batch runner.

Extracted from ``machine_memory_actions`` to shrink the TX/apply/revert owner.
Public symbols remain re-exported from ``machine_memory_actions``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..compile.pipeline import compile_wiki
from ..execution.history import append_execution_receipt_history
from ..memory.action_core import action_supports_low_risk_apply, safe_apply_preview
from ..memory.action_state import load_machine_memory_action_state_strict
from ..memory.paths import machine_memory_action_state_path
from ..protocol.runtime_config import PENDING_ACTION_STATUSES
from ..protocol.scaffold import ensure_layout
from ..protocol.state import load_protocol_state
from ..render.paths import append_wiki_log
from ..state.constants import DEFAULT_PROTOCOL
from ..utils.io import atomic_write_text, runtime_write_operation
from ..utils.path import relative_path
from .audit_preview import AUDIT_STREAM_PATH
from .history import append_runtime_history
from .paths import execution_receipt_history_path, runtime_history_path

AUTO_RESOLUTION_RECEIPTS_DIR = Path(".aiwiki") / "state" / "execution-receipts" / "auto-resolution"
AUTO_RESOLUTION_GENERATED_BY = "aiwiki-auto-resolve-actions"
AUTO_RESOLUTION_RULE_ID = "machine-memory:auto-resolution:v1"

def _auto_resolution_receipt_path(root: Path, action_id: str) -> Path:
    return root / AUTO_RESOLUTION_RECEIPTS_DIR / f"{action_id}.json"


def _fallback_policy_fields(action: dict[str, Any]) -> dict[str, str]:
    kind = str(action.get("kind") or "")
    if action_supports_low_risk_apply(action):
        return {
            "policy_decision": "allow",
            "execution_band": "bundle-safe-apply",
            "policy_rule_id": f"legacy:{kind}",
        }
    if kind in {
        "monitor-bridge-concept",
        "split-overloaded-concept",
        "expand-singleton-concept",
        "connect-isolated-source",
    }:
        return {
            "policy_decision": "review",
            "execution_band": "review-first",
            "policy_rule_id": f"legacy:{kind}",
        }
    return {
        "policy_decision": "review",
        "execution_band": "manual-repair",
        "policy_rule_id": f"legacy:{kind}",
    }


def _policy_fields(action: dict[str, Any]) -> dict[str, str]:
    fallback = _fallback_policy_fields(action)
    return {
        "policy_decision": str(action.get("policy_decision") or fallback["policy_decision"]),
        "execution_band": str(action.get("execution_band") or fallback["execution_band"]),
        "policy_rule_id": str(action.get("policy_rule_id") or fallback["policy_rule_id"]),
    }


def machine_memory_action_auto_resolution_policy(
    root: Path,
    action: dict[str, Any],
) -> dict[str, Any]:
    status = str(action.get("status") or "proposed")
    action_id = str(action.get("id") or "")
    kind = str(action.get("kind") or "")
    active = bool(action.get("active", True))
    policy = _policy_fields(action)
    decision: dict[str, Any] = {
        "action_id": action_id,
        "title": str(action.get("title") or action_id),
        "action_kind": kind,
        "status_before": status,
        "active": active,
        **policy,
    }
    if not active or status in {"resolved", "rejected"}:
        return {
            **decision,
            "operation": "skip",
            "status_after": status,
            "reason_code": "inactive_or_closed",
            "revert_supported": False,
        }
    if (
        status == "deferred"
        and str(action.get("human_required") or "").lower() == "true"
        and str(action.get("human_required_reason") or "").strip()
    ):
        return {
            **decision,
            "operation": "skip",
            "status_after": status,
            "reason_code": "already_human_required_exception",
            "human_required": True,
            "human_required_reason": str(action.get("human_required_reason") or ""),
            "revert_supported": False,
        }
    if status == "accepted" and action_supports_low_risk_apply(action):
        return {
            **decision,
            "operation": "apply",
            "status_after": "resolved",
            "reason_code": "accepted_bundle_safe_apply",
            "revert_supported": True,
        }
    human_required_reason = "semantic_judgment_required"
    preview = safe_apply_preview(root, action)
    if status == "accepted" and not isinstance(preview, dict):
        human_required_reason = "revert_unsupported"
    elif not str(policy["execution_band"] or "").strip() or str(policy["policy_decision"] or "") == "review":
        human_required_reason = "semantic_judgment_required"
    return {
        **decision,
        "operation": "escalate",
        "status_after": "deferred",
        "reason_code": "human_review_required",
        "human_required": True,
        "human_required_reason": human_required_reason,
        "revert_supported": False,
    }


def _build_auto_resolution_escalation_receipt(
    root: Path,
    action: dict[str, Any],
    *,
    generated_at: str,
    decision: dict[str, Any],
    note: str | None,
) -> dict[str, Any]:
    action_id = str(action.get("id") or "")
    receipt_path = _auto_resolution_receipt_path(root, action_id)
    primary_path = str(action.get("primary_path") or "")
    secondary_path = str(action.get("secondary_path") or "")
    affected_paths = [path for path in (primary_path, secondary_path) if path]
    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": AUTO_RESOLUTION_GENERATED_BY,
        "generated_at": generated_at,
        "applied_at": generated_at,
        "operation": "escalate",
        "action_id": action_id,
        "title": str(action.get("title") or action_id),
        "status": "deferred",
        "status_before": str(decision.get("status_before") or action.get("status") or "proposed"),
        "status_after": "deferred",
        "action_kind": str(action.get("kind") or ""),
        "protocol": str(action.get("protocol") or load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL),
        "automatic": True,
        "policy_rule_id": str(decision.get("policy_rule_id") or ""),
        "policy_decision": str(decision.get("policy_decision") or "review"),
        "execution_band": str(decision.get("execution_band") or "manual-repair"),
        "reason_code": str(decision.get("reason_code") or "human_review_required"),
        "human_required": True,
        "human_required_reason": str(decision.get("human_required_reason") or "semantic_judgment_required"),
        "revert_supported": False,
        "human_recovery_path": (
            "PYTHONPATH=src python3 -m aiwiki.cli --root . advanced review-queue"
            f'  # action_id: {action_id} — 在 review-queue 中处理，无 review-action 子命令'
        ),
        "primary_path": primary_path,
        "secondary_path": secondary_path,
        "receipt_path": relative_path(root, receipt_path),
        "affected_paths": affected_paths,
        "note": note or "",
        "policy_rule": AUTO_RESOLUTION_RULE_ID,
    }


def _apply_auto_resolution_escalation(
    root: Path,
    actions: list[dict[str, Any]],
    target: dict[str, Any],
    *,
    decision: dict[str, Any],
    note: str | None,
) -> dict[str, Any]:
    from ..utils.time import utc_now
    from .machine_memory_actions import (
        MachineMemoryActionHalfWriteError,
        MachineMemoryActionReceiptError,
        _rollback_snapshots,
        _save_machine_memory_action_records,
        _snapshot_file_bytes,
        _update_action_review_state,
    )

    action_id = str(target.get("id") or "")
    generated_at = utc_now()
    receipt_path = _auto_resolution_receipt_path(root, action_id)
    receipt_history = execution_receipt_history_path(root)
    audit_stream = root / AUDIT_STREAM_PATH
    action_state = machine_memory_action_state_path(root)
    runtime_history = runtime_history_path(root)
    wiki_log = root / "wiki" / "indexes" / "log.md"
    snapshots: list[tuple[Path, bytes | None]] = [
        (receipt_path, _snapshot_file_bytes(receipt_path)),
        (receipt_history, _snapshot_file_bytes(receipt_history)),
        (audit_stream, _snapshot_file_bytes(audit_stream)),
        (action_state, _snapshot_file_bytes(action_state)),
        (runtime_history, _snapshot_file_bytes(runtime_history)),
        (wiki_log, _snapshot_file_bytes(wiki_log)),
    ]
    receipt = _build_auto_resolution_escalation_receipt(
        root,
        target,
        generated_at=generated_at,
        decision=decision,
        note=note,
    )
    review_note = (
        note or f"Auto-resolved to deferred: {decision.get('human_required_reason', 'semantic_judgment_required')}."
    )
    try:
        _update_action_review_state(root, target, "deferred", note=review_note, reviewed_at=generated_at)
        target["human_required"] = "true"
        target["human_required_reason"] = str(decision.get("human_required_reason") or "semantic_judgment_required")
        target["revert_supported"] = "false"
        target["escalation_candidate"] = "true"
        target["overdue_review"] = "false"
        target["auto_resolution"] = {
            "automatic": True,
            "operation": "escalate",
            "policy_rule_id": str(decision.get("policy_rule_id") or ""),
            "policy_decision": str(decision.get("policy_decision") or "review"),
            "execution_band": str(decision.get("execution_band") or "manual-repair"),
            "reason_code": str(decision.get("reason_code") or "human_review_required"),
            "human_required_reason": str(decision.get("human_required_reason") or "semantic_judgment_required"),
            "resolved_at": generated_at,
        }
        target["last_receipt_path"] = receipt["receipt_path"]
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        append_execution_receipt_history(root, receipt)
        _save_machine_memory_action_records(root, actions)
        append_runtime_history(
            root,
            {
                "event_type": "action-auto-resolve",
                "occurred_at": generated_at,
                "action_id": action_id,
                "operation": "escalate",
                "status": "deferred",
                "reason_code": str(decision.get("reason_code") or "human_review_required"),
                "human_required_reason": str(decision.get("human_required_reason") or "semantic_judgment_required"),
                "receipt_path": receipt["receipt_path"],
                "automatic": True,
                "note": note or "",
            },
        )
        append_wiki_log(
            root,
            "action-auto-resolve",
            str(target.get("title") or action_id),
            [
                f"action_id: `{action_id}`",
                "operation: `escalate`",
                f"human_required_reason: `{target.get('human_required_reason', '')}`",
                f"receipt: `{receipt['receipt_path']}`",
            ],
        )
    except Exception as exc:
        rollback_failures = _rollback_snapshots(snapshots)
        if rollback_failures:
            raise MachineMemoryActionHalfWriteError(
                "auto-resolve transaction failed and rollback also failed; manual repair required: "
                f"original={type(exc).__name__}: {exc}; rollback_failures={rollback_failures}"
            ) from exc
        raise MachineMemoryActionReceiptError(
            f"auto-resolve transaction failed and was rolled back: {type(exc).__name__}: {exc}"
        ) from exc
    return {
        "id": action_id,
        "status": "deferred",
        "receipt_path": receipt["receipt_path"],
        "human_required_reason": str(target.get("human_required_reason") or ""),
        "operation": "escalate",
    }


@runtime_write_operation
def auto_resolve_machine_memory_actions(
    root: Path,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    include_proposed: bool = True,
    escalate_unsupported: bool = True,
    note: str | None = None,
) -> dict[str, Any]:
    from .machine_memory_actions import apply_machine_memory_action, resolve_machine_memory_action_query

    ensure_layout(root)
    state = load_machine_memory_action_state_strict(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    selected_statuses = {"accepted"} if not include_proposed else PENDING_ACTION_STATUSES
    candidates = [
        action
        for action in actions
        if bool(action.get("active", True)) and str(action.get("status") or "proposed") in selected_statuses
    ]
    if limit is not None and limit >= 0:
        candidates = candidates[:limit]

    decisions = [machine_memory_action_auto_resolution_policy(root, action) for action in candidates]
    items: list[dict[str, Any]] = []
    counts = {
        "evaluated": len(decisions),
        "would_apply": 0,
        "would_escalate": 0,
        "applied": 0,
        "escalated": 0,
        "skipped": 0,
        "failed": 0,
    }
    if dry_run:
        for decision in decisions:
            operation = str(decision.get("operation") or "skip")
            if operation == "apply":
                counts["would_apply"] += 1
            elif operation == "escalate" and escalate_unsupported:
                counts["would_escalate"] += 1
            else:
                counts["skipped"] += 1
            item = dict(decision)
            if operation == "escalate" and not escalate_unsupported:
                item["operation"] = "skip"
                item["skipped_operation"] = "escalate"
                item["reason_code"] = "escalation_disabled"
            items.append(item)
        return {
            "operation": "auto-resolve-actions",
            "dry_run": True,
            "counts": counts,
            "items": items,
        }

    changed = False
    if len(candidates) != len(decisions):
        raise ValueError(
            f"auto-resolution length mismatch: {len(candidates)} candidates vs {len(decisions)} decisions"
        )
    for action, decision in zip(candidates, decisions):
        operation = str(decision.get("operation") or "skip")
        item = dict(decision)
        action_id = str(action.get("id") or "")
        try:
            if operation == "apply":
                auto_note = note or "Auto-resolved accepted low-risk action via machine-memory:auto-resolution:v1."
                dry = apply_machine_memory_action(root, action_id, note=auto_note, dry_run=True)
                result = apply_machine_memory_action(
                    root,
                    action_id,
                    note=auto_note,
                    bundle_path=str(dry.get("bundle_path") or ""),
                )
                counts["applied"] += 1
                changed = True
                item["result"] = result
            elif operation == "escalate" and escalate_unsupported:
                # A prior item in the same run may have applied machine-memory actions, which
                # reloads and saves machine-memory action state. Reload before each
                # escalation so a later state-only receipt cannot overwrite earlier
                # apply results with the initial in-memory action snapshot.
                current_state = load_machine_memory_action_state_strict(root)
                current_actions = [
                    dict(current_action)
                    for current_action in current_state.get("actions", [])
                    if isinstance(current_action, dict)
                ]
                current_target = resolve_machine_memory_action_query(current_actions, action_id)
                current_decision = machine_memory_action_auto_resolution_policy(root, current_target)
                if str(current_decision.get("operation") or "") != "escalate":
                    counts["skipped"] += 1
                    item["result"] = {
                        "operation": "skip",
                        "reason": "current_state_no_longer_requires_escalation",
                        "current_decision": current_decision,
                    }
                else:
                    result = _apply_auto_resolution_escalation(
                        root,
                        current_actions,
                        current_target,
                        decision=current_decision,
                        note=note,
                    )
                    counts["escalated"] += 1
                    changed = True
                    item["result"] = result
            else:
                counts["skipped"] += 1
                if operation == "escalate" and not escalate_unsupported:
                    item["operation"] = "skip"
                    item["skipped_operation"] = "escalate"
                    item["reason_code"] = "escalation_disabled"
            items.append(item)
        except Exception as exc:
            counts["failed"] += 1
            item["error"] = {"type": type(exc).__name__, "message": str(exc)}
            items.append(item)
            raise
    if changed:
        compile_wiki(root)
    return {
        "operation": "auto-resolve-actions",
        "dry_run": False,
        "counts": counts,
        "items": items,
    }
