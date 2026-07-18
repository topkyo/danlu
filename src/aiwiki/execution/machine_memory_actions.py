"""EP-018B6: machine-memory action execution owner.

Owns the four public execution entry points plus one private helper
that used to live at the top of ``aiwiki.app_compile``:

- ``resolve_machine_memory_action_query``
- ``review_machine_memory_action``
- ``review_machine_memory_actions_batch``
- ``apply_machine_memory_action``
- ``revert_machine_memory_action``
- ``_save_machine_memory_action_records``

Migration invariants (same as B1..B5):

- All dependencies are imported from their **true origin** module, not
  via a re-export chain. In particular:
  * ``append_wiki_log``, ``execution_bundle_path``,
    ``execution_receipt_path`` come from ``..app_render`` — they are
    double-defined in ``app_content`` but ``app_content.py:3061-3063``
    has a late re-bind that makes ``app_render`` the runtime-effective
    origin. B2 ``ask`` and B5 ``concept_rewrite`` already enforce this;
    B3 / B4 still route through ``app_content`` and should be realigned
    as cross-group tech debt.
  * ``compile_wiki`` comes from ``..compile.pipeline``, not from the
    ``..compile`` package ``__init__`` re-export (B4 oracle rule).
- ``utc_now`` is resolved lazily at **call time** via
  ``from .. import app_utils as _app_utils; _app_utils.utc_now()``
  so that ``patch("aiwiki.app_utils.utc_now", ...)`` patches
  (acceptance tests + downstream suites) continue to take effect after
  the owner flip.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..app_execution import (
    append_execution_receipt_history,
    build_execution_bundle,
    build_execution_receipt,
    execution_bundle_digest,
    load_execution_bundle,
    write_execution_bundle_document,
    write_execution_dry_run_document,
)
from ..app_lifecycle import (
    action_needs_review,
    evaluate_page_aging,
)
from ..app_protocol import (
    ACTION_STATUSES,
    PENDING_ACTION_STATUSES,
    ensure_layout,
    load_protocol_state,
    schedule_review_windows,
)
from ..app_state import (
    DEFAULT_PROTOCOL,
    append_runtime_history,
    execution_dry_run_path,
    execution_receipt_history_path,
    knowledge_lifecycle_override_state_path,
    knowledge_lifecycle_state_path,
    load_json_document_strict,
    load_machine_memory_action_state_strict,
    load_manual_link_state,
    machine_memory_action_state_path,
    manual_link_state_path,
    runtime_history_path,
    save_machine_memory_action_state,
    save_manual_link_state,
)
from ..app_utils import (
    atomic_write_text,
    parse_frontmatter,
    relative_path,
    render_frontmatter,
    runtime_write_operation,
    safe_resolve_within,
    strip_frontmatter,
)
from ..compile.pipeline import compile_wiki
from ..content.memory import (
    action_supports_low_risk_apply,
    build_page_patch_plan,
    repair_execution_proposals,
    safe_apply_preview,
    validate_low_risk_action_targets,
)
from ..render.paths import (
    append_wiki_log,
    execution_bundle_path,
    execution_proposal_path,
    execution_receipt_path,
)
from .audit_preview import AUDIT_STREAM_PATH

AUTO_RESOLUTION_RECEIPTS_DIR = Path(".aiwiki") / "state" / "execution-receipts" / "auto-resolution"
AUTO_RESOLUTION_GENERATED_BY = "aiwiki-auto-resolve-actions"
AUTO_RESOLUTION_RULE_ID = "machine-memory:auto-resolution:v1"

# -- R92-MM-ACTION-TX: transactional snapshot/rollback helpers --------------


class MachineMemoryActionReceiptError(RuntimeError):
    """Raised when receipt/history/action-state persistence failed and rollback succeeded.

    Pre-call file bytes have been restored; the caller can safely retry.
    """


class MachineMemoryActionHalfWriteError(RuntimeError):
    """Raised when rollback itself failed; manual repair required.

    This is a *loud* failure — never swallow it. Files may be in an
    inconsistent state and external operator action is needed.
    """


def _snapshot_file_bytes(path: Path) -> bytes | None:
    """Return current bytes of *path*, or ``None`` if it does not exist.

    The snapshot is taken eagerly so that callers can restore the file
    even if it is deleted before rollback runs.
    """
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _restore_file_bytes(path: Path, original: bytes | None) -> None:
    """Restore *path* to its snapshot. None means the file did not exist.

    Uses atomic tmp + ``os.replace`` for the data restore so a crash
    during rollback cannot leave a half-written file. If ``original`` is
    ``None`` and the file currently exists, it is unlinked.
    """
    import os
    import tempfile

    if original is None:
        if path.exists():
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".restore")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(original)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _rollback_snapshots(snapshots: list[tuple[Path, bytes | None]]) -> list[str]:
    """Restore all snapshots in reverse order. Returns list of restore failures."""
    failures: list[str] = []
    for path, original in reversed(snapshots):
        try:
            _restore_file_bytes(path, original)
        except Exception as exc:  # pragma: no cover - defensive
            failures.append(f"{path}: {type(exc).__name__}: {exc}")
    return failures


def _save_machine_memory_action_records(root: Path, actions: list[dict[str, Any]]) -> None:
    save_machine_memory_action_state(root, {"version": 1, "actions": actions})


def _clear_auto_resolution_exception_metadata(target: dict[str, Any]) -> None:
    for key in ("human_required", "human_required_reason", "auto_resolution", "revert_supported"):
        target.pop(key, None)


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
    if kind in {"monitor-bridge-concept", "split-overloaded-concept", "expand-singleton-concept", "connect-isolated-source"}:
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
            f"PYTHONPATH=src python3 -m aiwiki.cli --root . review-action {action_id} --status accepted"
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
    from .. import app_utils as _app_utils

    action_id = str(target.get("id") or "")
    generated_at = _app_utils.utc_now()
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
    review_note = note or f"Auto-resolved to deferred: {decision.get('human_required_reason', 'semantic_judgment_required')}."
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
    for action, decision in zip(candidates, decisions, strict=True):
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


def _validate_citation_page_path(root: Path, page_path: str) -> Path:
    """Resolve page_path under root and enforce judgment/decision page whitelist."""
    if not page_path:
        raise RuntimeError("citation-snapshot-refresh requires page_path")
    try:
        page = safe_resolve_within(root / page_path, root)
    except (ValueError, OSError) as exc:
        raise RuntimeError(
            f"citation-snapshot-refresh page_path escapes vault root: {page_path}"
        ) from exc
    allowed_prefixes = (
        (root / "wiki" / "judgments").resolve(),
        (root / "wiki" / "decisions").resolve(),
    )
    for prefix in allowed_prefixes:
        try:
            page.relative_to(prefix)
            return page
        except ValueError:
            continue
    raise RuntimeError(
        f"citation-snapshot-refresh page_path must be in wiki/judgments or wiki/decisions: {page_path}"
    )


def resolve_machine_memory_action_query(
    actions: list[dict[str, Any]],
    action_query: str,
) -> dict[str, Any]:
    normalized_query = action_query.strip()
    if not normalized_query:
        raise ValueError("Action id cannot be empty.")
    lowered_query = normalized_query.lower()

    def _match_stage(
        predicate: Any,
        *,
        skip_exact_id: bool = False,
        skip_exact_title: bool = False,
    ) -> dict[str, Any] | None:
        matches: list[dict[str, Any]] = []
        for action in actions:
            action_id = str(action.get("id") or "")
            action_title = str(action.get("title") or "").strip()
            lowered_id = action_id.lower()
            lowered_title = action_title.lower()
            if skip_exact_id and lowered_id == lowered_query:
                continue
            if skip_exact_title and lowered_title == lowered_query:
                continue
            if predicate(lowered_id, lowered_title):
                matches.append(action)
        if len(matches) == 1:
            return matches[0]
        if matches:
            candidates = ", ".join(
                f"{str(action.get('id') or '')} ({str(action.get('title') or '')})"
                for action in matches[:5]
            )
            raise RuntimeError(f"Machine-memory action is ambiguous: {action_query}. Candidates: {candidates}")
        return None

    exact_id_match = _match_stage(lambda lowered_id, lowered_title: lowered_id == lowered_query)
    if exact_id_match is not None:
        return exact_id_match
    exact_title_match = _match_stage(lambda lowered_id, lowered_title: lowered_title == lowered_query)
    if exact_title_match is not None:
        return exact_title_match
    prefix_match = _match_stage(
        lambda lowered_id, lowered_title: lowered_id.startswith(lowered_query) or lowered_title.startswith(lowered_query),
        skip_exact_title=True,
    )
    if prefix_match is not None:
        return prefix_match
    partial_match = _match_stage(
        lambda lowered_id, lowered_title: lowered_query in lowered_id or lowered_query in lowered_title,
        skip_exact_id=True,
        skip_exact_title=True,
    )
    if partial_match is not None:
        return partial_match
    raise FileNotFoundError(f"Machine-memory action not found: {action_query}")


def _update_action_review_state(
    root: Path,
    target: dict[str, Any],
    status: str,
    *,
    note: str | None,
    reviewed_at: str,
) -> None:
    _clear_auto_resolution_exception_metadata(target)
    target["status"] = status
    target["reviewed_at"] = reviewed_at
    target["status_updated_at"] = reviewed_at
    target["review_note"] = note or ""
    target["pending_review"] = "true" if action_needs_review(status) else "false"
    if status in PENDING_ACTION_STATUSES:
        revisit_after, escalate_after = schedule_review_windows(
            "action",
            status,
            reviewed_at,
            protocol=str(target.get("protocol") or DEFAULT_PROTOCOL),
            root=root,
        )
    else:
        revisit_after, escalate_after = "", ""
    target["revisit_after"] = revisit_after
    target["escalate_after"] = escalate_after
    target.update(evaluate_page_aging(target))


@runtime_write_operation
def review_machine_memory_action(
    root: Path,
    action_id: str,
    status: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    # Lazy-resolve utc_now so patch("aiwiki.app_utils.utc_now", ...) still
    # takes effect after B6 flip.
    from .. import app_utils as _app_utils

    ensure_layout(root)
    if status not in ACTION_STATUSES:
        raise ValueError(
            f"Unsupported machine-memory action status: {status!r}; "
            f"expected one of: {ACTION_STATUSES}"
        )
    state = load_machine_memory_action_state_strict(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    target = resolve_machine_memory_action_query(actions, action_id)
    resolved_action_id = str(target.get("id") or action_id.strip())
    reviewed_at = _app_utils.utc_now()
    _update_action_review_state(root, target, status, note=note, reviewed_at=reviewed_at)
    save_machine_memory_action_state(root, {"version": 1, "actions": actions})
    append_wiki_log(
        root,
        "action-review",
        str(target.get("title") or resolved_action_id),
        [
            f"action_id: `{resolved_action_id}`",
            f"status: `{status}`",
            f"primary: `{target.get('primary_path', '')}`",
            f"priority: `{target.get('priority', '')}`",
        ],
    )
    compile_wiki(root)
    return {
        "id": resolved_action_id,
        "status": status,
        "reviewed_at": reviewed_at,
        "active": bool(target.get("active", True)),
    }


@runtime_write_operation
def review_machine_memory_actions_batch(
    root: Path,
    action_ids: list[str],
    status: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    """Batch review machine-memory actions with one state write and compile.

    The single-action API compiles after each update. Batch triage is meant for
    review-first queues, so this owner updates every selected action first and
    then runs one compile to refresh derived policy/apply_ready fields and wiki
    surfaces.
    """
    from .. import app_utils as _app_utils

    ensure_layout(root)
    if status not in ACTION_STATUSES:
        raise ValueError(
            f"Unsupported machine-memory action status: {status!r}; "
            f"expected one of: {ACTION_STATUSES}"
        )
    ordered_ids: list[str] = []
    seen_ids: set[str] = set()
    for raw in action_ids:
        if not isinstance(raw, str):
            continue
        normalized = raw.strip()
        if not normalized or normalized in seen_ids:
            continue
        seen_ids.add(normalized)
        ordered_ids.append(normalized)
    if not ordered_ids:
        raise ValueError("Batch review-action requires at least one action id.")

    state = load_machine_memory_action_state_strict(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    targets: list[dict[str, Any]] = []
    resolved_ids: list[str] = []
    for action_id in ordered_ids:
        target = resolve_machine_memory_action_query(actions, action_id)
        resolved_id = str(target.get("id") or action_id)
        if resolved_id in resolved_ids:
            continue
        targets.append(target)
        resolved_ids.append(resolved_id)
    if not targets:
        raise ValueError("Batch review-action requires at least one resolved action.")

    reviewed_at = _app_utils.utc_now()
    receipts: list[dict[str, Any]] = []
    for target, resolved_id in zip(targets, resolved_ids, strict=True):
        _update_action_review_state(root, target, status, note=note, reviewed_at=reviewed_at)
        receipts.append(
            {
                "id": resolved_id,
                "status": status,
                "reviewed_at": reviewed_at,
                "active": bool(target.get("active", True)),
            }
        )
    save_machine_memory_action_state(root, {"version": 1, "actions": actions})
    append_wiki_log(
        root,
        "action-review-batch",
        f"{len(receipts)} actions",
        [
            f"status: `{status}`",
            f"actions: `{', '.join(resolved_ids[:5])}`",
            f"note: `{note or ''}`",
        ],
    )
    append_runtime_history(
        root,
        {
            "event_type": "action-review-batch",
            "occurred_at": reviewed_at,
            "action_ids": resolved_ids,
            "status": status,
            "count": len(receipts),
            "note": note or "",
        },
    )
    compile_wiki(root)
    return {
        "operation": "action-review-batch",
        "action_ids": resolved_ids,
        "status": status,
        "count": len(receipts),
        "reviewed_at": reviewed_at,
        "receipts": receipts,
    }


@runtime_write_operation
def apply_machine_memory_action(
    root: Path,
    action_id: str,
    *,
    note: str | None = None,
    dry_run: bool = False,
    bundle_path: str | None = None,
) -> dict[str, Any]:
    from .. import app_utils as _app_utils

    ensure_layout(root)
    state = load_machine_memory_action_state_strict(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    target = resolve_machine_memory_action_query(actions, action_id)
    resolved_action_id = str(target.get("id") or action_id.strip())
    if str(target.get("status") or "") != "accepted":
        raise RuntimeError("Machine-memory action must be accepted before apply.")
    kind = str(target.get("kind") or "")
    protocol = str(target.get("protocol") or load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    preview_proposals = repair_execution_proposals(root, [target], active_protocol=protocol)
    proposal = preview_proposals[0] if preview_proposals else {
        "action_id": resolved_action_id,
        "title": str(target.get("title") or resolved_action_id),
        "proposal_kind": "manual-repair",
        "risk": "low",
        "priority": str(target.get("priority") or "medium"),
        "protocol": protocol,
        "summary": str(target.get("reason") or ""),
        "target_paths": [
            path
            for path in (str(target.get("primary_path") or ""), str(target.get("secondary_path") or ""))
            if path
        ],
        "page_patch_plan": build_page_patch_plan(root, target, active_protocol=protocol),
        "safe_apply_preview": safe_apply_preview(root, target),
        "command_hint": str(target.get("command_hint") or ""),
        "bundle_path": relative_path(root, execution_bundle_path(root, resolved_action_id)),
        "proposal_path": relative_path(root, execution_proposal_path(root, resolved_action_id)),
    }
    preview = proposal.get("safe_apply_preview")
    if not isinstance(preview, dict):
        raise RuntimeError("Only accepted actions with a safe apply preview support semi-auto apply.")
    preview_apply_mode = str(preview.get("apply_mode") or "")
    if not preview_apply_mode:
        raise RuntimeError("Safe apply preview is missing an apply mode.")
    previewed_at = _app_utils.utc_now()
    bundle = build_execution_bundle(root, proposal, compiled_at=previewed_at)
    if dry_run:
        selected_bundle_path = safe_resolve_within(
            root
            / str(
                proposal.get("bundle_path")
                or relative_path(root, execution_bundle_path(root, resolved_action_id))
            ),
            root,
        )
        write_execution_bundle_document(selected_bundle_path, bundle)
        dry_run_path = execution_dry_run_path(root, resolved_action_id)
        dry_run_payload = {
            "version": 1,
            "kind": "execution-dry-run",
            "generated_by": "aiwiki-apply-action",
            "generated_at": previewed_at,
            "operation": "apply",
            "action_id": resolved_action_id,
            "title": str(target.get("title") or resolved_action_id),
            "status": str(target.get("status") or "accepted"),
            "apply_mode": preview_apply_mode,
            "proposal_path": str(proposal.get("proposal_path") or ""),
            "bundle_path": relative_path(root, selected_bundle_path),
            "preview": proposal.get("safe_apply_preview"),
            "bundle": bundle,
        }
        write_execution_dry_run_document(dry_run_path, dry_run_payload)
        append_runtime_history(
            root,
            {
                "event_type": "action-dry-run",
                "occurred_at": previewed_at,
                "action_id": resolved_action_id,
                "protocol": protocol,
                "bundle_path": relative_path(root, selected_bundle_path),
                "preview_path": relative_path(root, dry_run_path),
                "note": note or "",
            },
        )
        append_wiki_log(
            root,
            "action-dry-run",
            str(target.get("title") or resolved_action_id),
            [
                f"action_id: `{resolved_action_id}`",
                f"apply_mode: `{preview_apply_mode}`",
                f"bundle: `{relative_path(root, selected_bundle_path)}`",
            ],
        )
        return {
            "id": resolved_action_id,
            "dry_run": True,
            "apply_mode": preview_apply_mode,
            "status": str(target.get("status") or "accepted"),
            "bundle_path": relative_path(root, selected_bundle_path),
            "dry_run_path": relative_path(root, dry_run_path),
            "proposal_path": proposal.get("proposal_path", ""),
            "preview": proposal.get("safe_apply_preview"),
            "bundle": bundle,
        }

    selected_bundle_path = safe_resolve_within(
        root / bundle_path.strip()
        if bundle_path and bundle_path.strip()
        else root / str(proposal.get("bundle_path") or ""),
        root,
    )
    if not selected_bundle_path.is_file():
        raise FileNotFoundError(
            f"Execution bundle not found: {relative_path(root, selected_bundle_path)}. "
            "Run `aiwiki advanced compile`, then retry via nightly reconcile or `advanced review-page`."
        )
    stored_bundle = load_execution_bundle(selected_bundle_path)
    if str(stored_bundle.get("action_id") or "") != resolved_action_id:
        raise RuntimeError("Execution bundle action_id does not match the requested action.")
    if str(stored_bundle.get("digest") or "") != execution_bundle_digest(stored_bundle):
        raise RuntimeError("Execution bundle digest is invalid; regenerate the bundle before apply.")
    if str(stored_bundle.get("digest") or "") != str(bundle.get("digest") or ""):
        raise RuntimeError(
            "Execution bundle is stale; rerun `aiwiki advanced compile`, reconcile via nightly, "
            f"or use `advanced review-page` before retrying machine-memory apply for action {resolved_action_id}."
        )

    applied_at = _app_utils.utc_now()
    stored_preview = stored_bundle.get("safe_apply_preview")
    if not isinstance(stored_preview, dict):
        raise RuntimeError("Execution bundle is missing the safe apply preview.")
    apply_mode = str(stored_preview.get("apply_mode") or "")

    # R92-MM-ACTION-TX: snapshot every file we may mutate before any write.
    # Receipt path may not yet exist (None snapshot → restored by unlink).
    receipt_path = execution_receipt_path(root, resolved_action_id)
    receipt_history_path = execution_receipt_history_path(root)
    audit_stream_full_path = root / AUDIT_STREAM_PATH
    action_state_path = machine_memory_action_state_path(root)
    snapshots: list[tuple[Path, bytes | None]] = [
        (receipt_path, _snapshot_file_bytes(receipt_path)),
        (receipt_history_path, _snapshot_file_bytes(receipt_history_path)),
        (audit_stream_full_path, _snapshot_file_bytes(audit_stream_full_path)),
        (action_state_path, _snapshot_file_bytes(action_state_path)),
    ]
    if kind == "split-overloaded-concept":
        snapshots.extend(
            [
                (
                    knowledge_lifecycle_override_state_path(root),
                    _snapshot_file_bytes(knowledge_lifecycle_override_state_path(root)),
                ),
                (knowledge_lifecycle_state_path(root), _snapshot_file_bytes(knowledge_lifecycle_state_path(root))),
                (runtime_history_path(root), _snapshot_file_bytes(runtime_history_path(root))),
                (root / "wiki" / "indexes" / "log.md", _snapshot_file_bytes(root / "wiki" / "indexes" / "log.md")),
            ]
        )
    citation_page: Path | None = None
    if apply_mode == "manual-link-state":
        ml_path = manual_link_state_path(root)
        snapshots.append((ml_path, _snapshot_file_bytes(ml_path)))
    elif apply_mode == "citation-snapshot-refresh":
        # Snapshot citation page bytes too (taken before mutation below).
        page_path_str = str(stored_preview.get("page_path") or target.get("primary_path") or "")
        if page_path_str:
            try:
                citation_page = _validate_citation_page_path(root, page_path_str)
                snapshots.append((citation_page, _snapshot_file_bytes(citation_page)))
            except Exception:
                # Invalid page path will fail again inside the try-block below
                # with the original error message; do not snapshot.
                citation_page = None

    try:
        if apply_mode == "manual-link-state":
            source_id, concept_slug = validate_low_risk_action_targets(root, target)
            manual_state = load_manual_link_state(root)
            manual_links = [dict(item) for item in manual_state.get("source_to_concept", []) if isinstance(item, dict)]
            existing = next(
                (
                    item
                    for item in manual_links
                    if str(item.get("source_id") or "") == source_id
                    and str(item.get("concept_slug") or "") == concept_slug
                    and bool(item.get("active", True))
                ),
                None,
            )
            if existing is None:
                manual_links.append(
                    {
                        "source_id": source_id,
                        "concept_slug": concept_slug,
                        "active": True,
                        "created_at": applied_at,
                        "applied_at": applied_at,
                        "origin_action_id": resolved_action_id,
                        "note": note or "Applied accepted low-risk repair action.",
                    }
                )
            else:
                existing["active"] = True
                existing["applied_at"] = applied_at
                existing["origin_action_id"] = resolved_action_id
                existing["note"] = note or str(existing.get("note") or "")
            save_manual_link_state(root, {"version": 1, "source_to_concept": manual_links})
        elif apply_mode == "citation-snapshot-refresh":
            page_path = str(stored_preview.get("page_path") or target.get("primary_path") or "")
            page = _validate_citation_page_path(root, page_path)
            if not page.exists():
                raise FileNotFoundError(f"Judgment page not found: {page_path}")
            content = page.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            body = strip_frontmatter(content).strip()
            frontmatter["citation_snapshots"] = [
                str(item)
                for item in stored_preview.get("updated_citation_snapshots", [])
                if isinstance(item, str) and item.strip()
            ]
            atomic_write_text(
                page,
                f"{render_frontmatter(frontmatter)}\n\n{body}\n",
            )
        elif apply_mode == "resolve-monitor":
            pass  # no state mutation needed; receipt + status change is the outcome
        else:
            raise RuntimeError(f"Unsupported apply mode: {apply_mode}")

        # P4-19a: split-overloaded-concept apply 完成时联动 retire concept，
        # 让 noise / 过载概念退出默认 ranking。receipt/history 失败时随主
        # transaction 一起回滚，避免无人值守 L2 留下半写 lifecycle override。
        # F-new-13 (Round 6): active-corpus 概念不能直接 retire（lifecycle guard），
        # 此时记 `auto_retire_skipped_active_corpus=True` 并依赖 retroactive noise rebuild。
        auto_retired_concept: str | None = None
        auto_retire_error: str | None = None
        auto_retire_skipped_active_corpus = False
        if kind == "split-overloaded-concept":
            slug_candidates = [
                str(s).strip()
                for s in (target.get("concept_slugs") or [])
                if isinstance(s, str) and str(s).strip()
            ]
            if slug_candidates:
                slug_to_retire = slug_candidates[0]
                try:
                    from .lifecycle import retire_concept as _retire_concept

                    _retire_concept(
                        root,
                        slug_to_retire,
                        note=f"Auto-retired via machine-memory apply {resolved_action_id}.",
                    )
                    auto_retired_concept = slug_to_retire
                except RuntimeError as exc:
                    message = str(exc)
                    if "Active-corpus concept cannot transition to retired" in message:
                        auto_retire_skipped_active_corpus = True
                    else:
                        auto_retire_error = f"{type(exc).__name__}: {exc}"
                except Exception as exc:  # pragma: no cover - defensive
                    auto_retire_error = f"{type(exc).__name__}: {exc}"

        receipt = build_execution_receipt(root, target, applied_at=applied_at, note=note, proposal=proposal)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            receipt_path,
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        append_execution_receipt_history(root, receipt)

        target["status"] = "resolved"
        target["reviewed_at"] = applied_at
        target["status_updated_at"] = applied_at
        target["review_note"] = note or "Semi-auto apply completed."
        target["pending_review"] = "false"
        target["revisit_after"] = ""
        target["escalate_after"] = ""
        target["aging_state"] = ""
        target["overdue_review"] = "false"
        target["escalation_candidate"] = "false"
        target["last_receipt_path"] = relative_path(root, receipt_path)
        _clear_auto_resolution_exception_metadata(target)
        _save_machine_memory_action_records(root, actions)
    except Exception as exc:
        rollback_failures = _rollback_snapshots(snapshots)
        if rollback_failures:
            raise MachineMemoryActionHalfWriteError(
                "machine-memory apply transaction failed and rollback also failed; manual repair required: "
                f"original={type(exc).__name__}: {exc}; rollback_failures={rollback_failures}"
            ) from exc
        raise MachineMemoryActionReceiptError(
            f"machine-memory apply transaction failed and was rolled back: {type(exc).__name__}: {exc}"
        ) from exc

    append_wiki_log(
        root,
        "action-apply",
        str(target.get("title") or resolved_action_id),
        [
            f"action_id: `{resolved_action_id}`",
            f"kind: `{kind}`",
            f"apply_mode: `{apply_mode}`",
            f"primary: `{target.get('primary_path', '')}`",
        ],
    )
    try:
        compile_wiki(root)
    except Exception as verify_exc:
        from ..autonomy_policy import load_policy

        if load_policy(root).auto_revert_on_verify_failure:
            try:
                revert_result = revert_machine_memory_action(
                    root,
                    resolved_action_id,
                    note=f"auto-revert after apply verify failure: {type(verify_exc).__name__}: {verify_exc}",
                    verify=False,
                )
                append_runtime_history(
                    root,
                    {
                        "event_type": "action-auto-revert-on-verify-failure",
                        "occurred_at": _app_utils.utc_now(),
                        "action_id": resolved_action_id,
                        "apply_receipt_path": relative_path(root, receipt_path),
                        "revert_receipt_path": str(revert_result.get("receipt_path") or ""),
                        "verify_error": f"{type(verify_exc).__name__}: {verify_exc}",
                    },
                )
            except Exception as revert_exc:
                raise RuntimeError(
                    "machine-memory apply verify failed and auto-revert also failed: "
                    f"verify={type(verify_exc).__name__}: {verify_exc}; "
                    f"revert={type(revert_exc).__name__}: {revert_exc}. "
                    "Try `aiwiki advanced alchemy-revert` or manual repair."
                ) from verify_exc
            raise RuntimeError(
                "machine-memory apply verify failed; auto-revert completed: "
                f"{type(verify_exc).__name__}: {verify_exc}. "
                "Inspect receipts and retry via nightly reconcile or `advanced review-page`."
            ) from verify_exc
        raise
    response: dict[str, Any] = {
        "id": resolved_action_id,
        "status": "resolved",
        "applied_at": applied_at,
        "apply_mode": apply_mode,
        "receipt_path": relative_path(root, receipt_path),
    }
    if auto_retired_concept is not None:
        response["auto_retired_concept"] = auto_retired_concept
    if auto_retire_skipped_active_corpus:
        response["auto_retire_skipped_active_corpus"] = True
    if auto_retire_error is not None:
        response["auto_retire_error"] = auto_retire_error
    return response


@runtime_write_operation
def revert_machine_memory_action(
    root: Path,
    action_id: str,
    *,
    note: str | None = None,
    verify: bool = True,
) -> dict[str, Any]:
    from .. import app_utils as _app_utils

    ensure_layout(root)
    state = load_machine_memory_action_state_strict(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    target = resolve_machine_memory_action_query(actions, action_id)
    resolved_action_id = str(target.get("id") or action_id.strip())
    receipt_relative = str(target.get("last_receipt_path") or "")
    if not receipt_relative:
        raise RuntimeError("Machine-memory action has no execution receipt to revert.")
    receipt_path = root / receipt_relative
    if not receipt_path.exists():
        raise FileNotFoundError(f"Execution receipt not found: {receipt_relative}")
    receipt = load_json_document_strict(receipt_path)
    if not isinstance(receipt, dict) or str(receipt.get("kind") or "") != "execution-receipt":
        raise RuntimeError("Execution receipt is not valid.")
    if str(receipt.get("operation") or "") != "apply":
        raise RuntimeError("Only the latest apply receipt can be reverted.")
    if str(receipt.get("action_id") or "") != resolved_action_id:
        raise RuntimeError("Execution receipt action_id does not match the requested action.")
    preview = receipt.get("safe_apply_preview")
    if not isinstance(preview, dict):
        raise RuntimeError("Execution receipt is missing the safe apply preview.")
    reverted_at = _app_utils.utc_now()
    apply_mode = str(preview.get("apply_mode") or "")

    # R92-MM-ACTION-TX: snapshot every file we may mutate before any write.
    revert_receipt_path = receipt_path.parent / "reverts" / receipt_path.name
    receipt_history_path = execution_receipt_history_path(root)
    audit_stream_full_path = root / AUDIT_STREAM_PATH
    action_state_path = machine_memory_action_state_path(root)
    snapshots: list[tuple[Path, bytes | None]] = [
        (revert_receipt_path, _snapshot_file_bytes(revert_receipt_path)),
        (receipt_history_path, _snapshot_file_bytes(receipt_history_path)),
        (audit_stream_full_path, _snapshot_file_bytes(audit_stream_full_path)),
        (action_state_path, _snapshot_file_bytes(action_state_path)),
    ]
    if apply_mode == "manual-link-state":
        ml_path = manual_link_state_path(root)
        snapshots.append((ml_path, _snapshot_file_bytes(ml_path)))
    elif apply_mode == "citation-snapshot-refresh":
        page_path_pre = str(preview.get("page_path") or target.get("primary_path") or "")
        if page_path_pre:
            try:
                page_pre = _validate_citation_page_path(root, page_path_pre)
                snapshots.append((page_pre, _snapshot_file_bytes(page_pre)))
            except Exception as exc:
                logging.getLogger("aiwiki.machine_memory").warning(
                    "revert citation-snapshot-refresh: page path %r invalid, snapshot skipped: %s",
                    page_path_pre, exc,
                )

    try:
        if apply_mode == "manual-link-state":
            manual_state = load_manual_link_state(root)
            manual_links = [dict(item) for item in manual_state.get("source_to_concept", []) if isinstance(item, dict)]
            active_entry: dict[str, Any] | None = None
            for item in manual_links:
                if str(item.get("origin_action_id") or "") != resolved_action_id:
                    continue
                if bool(item.get("active", True)):
                    active_entry = item
                    break
            if active_entry is None:
                raise RuntimeError("No active safe-apply state exists for this action.")
            active_entry["active"] = False
            active_entry["reverted_at"] = reverted_at
            active_entry["revert_note"] = note or "Safe apply reverted."
            save_manual_link_state(root, {"version": 1, "source_to_concept": manual_links})
        elif apply_mode == "citation-snapshot-refresh":
            page_path = str(preview.get("page_path") or target.get("primary_path") or "")
            if not page_path:
                raise RuntimeError("Execution receipt is missing the judgment page path.")
            page = _validate_citation_page_path(root, page_path)
            if not page.exists():
                raise FileNotFoundError(f"Judgment page not found: {page_path}")
            content = page.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            body = strip_frontmatter(content).strip()
            frontmatter["citation_snapshots"] = [
                str(item)
                for item in preview.get("previous_citation_snapshots", [])
                if isinstance(item, str) and item.strip()
            ]
            atomic_write_text(
                page,
                f"{render_frontmatter(frontmatter)}\n\n{body}\n",
            )
        elif apply_mode == "resolve-monitor":
            pass  # no state to revert; status change below handles it
        else:
            raise RuntimeError(f"Unsupported revert apply mode: {apply_mode}")

        protocol = str(target.get("protocol") or load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
        reverted_target = {
            **dict(target),
            "protocol": protocol,
            "status": "proposed",
            "execution_policy": "triage",
            "execution_band": "review-first",
            "reviewed_at": reverted_at,
            "status_updated_at": reverted_at,
            "review_note": note or "Safe apply reverted.",
            "pending_review": "true",
            "last_receipt_path": relative_path(root, receipt_path),
            "command_hint": f'PYTHONPATH=src python3 -m aiwiki.cli --root . review-action {resolved_action_id} --status accepted --note "Resume reverted repair."',
            "next_step": "回滚后重新 review，确认是否要再次 accepted 再执行。",
        }
        preview_proposals = repair_execution_proposals(root, [reverted_target], active_protocol=protocol)
        proposal = preview_proposals[0] if preview_proposals else {
            "action_id": resolved_action_id,
            "title": str(reverted_target.get("title") or resolved_action_id),
            "proposal_kind": "manual-repair",
            "risk": "low",
            "priority": str(reverted_target.get("priority") or "medium"),
            "protocol": protocol,
            "status": "proposed",
            "execution_policy": "triage",
            "summary": str(reverted_target.get("reason") or ""),
            "target_paths": [
                path
                for path in (str(reverted_target.get("primary_path") or ""), str(reverted_target.get("secondary_path") or ""))
                if path
            ],
            "page_patch_plan": build_page_patch_plan(root, reverted_target, active_protocol=protocol),
            "safe_apply_preview": safe_apply_preview(root, reverted_target),
            "command_hint": str(reverted_target.get("command_hint") or ""),
            "bundle_path": relative_path(root, execution_bundle_path(root, resolved_action_id)),
            "proposal_path": relative_path(root, execution_proposal_path(root, resolved_action_id)),
        }
        revert_receipt = build_execution_receipt(
            root,
            reverted_target,
            applied_at=reverted_at,
            note=note,
            proposal=proposal,
            operation="revert",
            resulting_status="proposed",
        )
        revert_receipt["receipt_path"] = relative_path(root, revert_receipt_path)
        atomic_write_text(
            revert_receipt_path,
            json.dumps(revert_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        reverted_target["last_receipt_path"] = relative_path(root, revert_receipt_path)
        append_execution_receipt_history(root, revert_receipt)

        target["status"] = str(reverted_target["status"])
        target["reviewed_at"] = str(reverted_target["reviewed_at"])
        target["status_updated_at"] = str(reverted_target["status_updated_at"])
        target["review_note"] = str(reverted_target["review_note"])
        target["pending_review"] = str(reverted_target["pending_review"])
        target["last_receipt_path"] = str(reverted_target["last_receipt_path"])
        _clear_auto_resolution_exception_metadata(target)
        revisit_after, escalate_after = schedule_review_windows(
            "action",
            "proposed",
            reverted_at,
            protocol=str(target.get("protocol") or DEFAULT_PROTOCOL),
            root=root,
        )
        target["revisit_after"] = revisit_after
        target["escalate_after"] = escalate_after
        target.update(evaluate_page_aging(target))
        _save_machine_memory_action_records(root, actions)
    except Exception as exc:
        rollback_failures = _rollback_snapshots(snapshots)
        if rollback_failures:
            raise MachineMemoryActionHalfWriteError(
                "machine-memory revert transaction failed and rollback also failed; manual repair required: "
                f"original={type(exc).__name__}: {exc}; rollback_failures={rollback_failures}. "
                "Try `aiwiki advanced alchemy-revert` if alchemy state is involved."
            ) from exc
        raise MachineMemoryActionReceiptError(
            f"machine-memory revert transaction failed and was rolled back: {type(exc).__name__}: {exc}"
        ) from exc

    append_wiki_log(
        root,
        "action-revert",
        str(target.get("title") or resolved_action_id),
        [
            f"action_id: `{resolved_action_id}`",
            f"receipt: `{relative_path(root, revert_receipt_path)}`",
            f"primary: `{target.get('primary_path', '')}`",
        ],
    )
    if verify:
        compile_wiki(root)
    return {
        "id": resolved_action_id,
        "status": "proposed",
        "reverted_at": reverted_at,
        "receipt_path": relative_path(root, revert_receipt_path),
    }
