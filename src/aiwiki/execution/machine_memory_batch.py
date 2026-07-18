"""EP-018B7: machine-memory batch execution owner.

Owns the batch execution entry points plus two private helpers that
used to live in ``aiwiki.app_compile``:

- ``review_pages_batch``
- ``apply_machine_memory_actions_batch``
- ``revert_machine_memory_action_batch``
- ``_build_batch_id``
- ``_load_latest_action_apply_batch_receipt``

Dependencies come from true owner modules (``render.paths``, ``utils.time``,
sibling execution owners). ``utc_now`` is resolved lazily via ``utils.time``
so ``patch("aiwiki.utils.time.utc_now", ...)`` remains effective.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..execution.receipts import (
    build_execution_batch_receipt,
    write_execution_batch_receipt_document,
)
from ..memory.action_core import action_supports_low_risk_apply
from ..memory.action_state import load_machine_memory_action_state_strict
from ..protocol.scaffold import ensure_layout
from ..render.paths import append_wiki_log
from ..state.io import load_json_document_strict
from ..utils.io import runtime_write_operation
from ..utils.path import relative_path
from ..utils.text import slugify
from . import machine_memory_actions as _machine_memory_actions
from . import review as _review
from .alchemy import _restore_file_bytes, _snapshot_file_bytes
from .audit_preview import AUDIT_STREAM_PATH
from .history import append_runtime_history, load_runtime_history_strict
from .paths import execution_batch_receipt_path, runtime_history_path


class MachineMemoryActionApplyBatchReceiptError(RuntimeError):
    pass


class MachineMemoryActionApplyBatchReceiptHalfWriteError(RuntimeError):
    pass


def _build_batch_id(prefix: str, subjects: list[str]) -> str:
    from ..utils.time import utc_now

    first_subject = next((subject for subject in subjects if subject), "item")
    return f"{prefix}-{utc_now()}-{slugify(first_subject)}"


def _load_latest_action_apply_batch_receipt(root: Path, batch_id: str | None) -> dict[str, Any]:
    if batch_id:
        receipt = load_json_document_strict(execution_batch_receipt_path(root, batch_id))
        if not isinstance(receipt, dict) or not receipt:
            raise FileNotFoundError(f"Batch receipt not found: {batch_id}")
        return receipt
    history = [event for event in load_runtime_history_strict(root) if isinstance(event, dict)]
    reverted_batch_ids = {
        str(event.get("reverted_batch_id") or "")
        for event in history
        if str(event.get("event_type") or "") == "action-revert-batch" and str(event.get("reverted_batch_id") or "")
    }
    for event in reversed(history):
        if str(event.get("event_type") or "") != "action-apply-batch":
            continue
        candidate_batch_id = str(event.get("batch_id") or "")
        if not candidate_batch_id or candidate_batch_id in reverted_batch_ids:
            continue
        receipt_path = root / str(event.get("receipt_path") or "")
        receipt = load_json_document_strict(receipt_path)
        if isinstance(receipt, dict):
            return receipt
    raise RuntimeError("No unreverted action apply batch found.")


@runtime_write_operation
def review_pages_batch(
    root: Path,
    pages: list[str],
    status: str,
    *,
    note: str | None = None,
    confidence: str | None = None,
) -> dict[str, Any]:
    from ..utils.time import utc_now

    ensure_layout(root)
    ordered_pages: list[str] = []
    seen_pages: set[str] = set()
    for page in pages:
        normalized = page.strip()
        if not normalized or normalized in seen_pages:
            continue
        seen_pages.add(normalized)
        ordered_pages.append(normalized)
    if not ordered_pages:
        raise ValueError("Batch review requires at least one page.")
    items = [_review.review_page(root, page, status, note=note, confidence=confidence) for page in ordered_pages]
    generated_at = utc_now()
    batch_id = _build_batch_id("review-page-batch", ordered_pages)
    receipt = build_execution_batch_receipt(
        root,
        batch_id=batch_id,
        operation="review-page-batch",
        generated_at=generated_at,
        items=items,
        note=note,
        revert_supported=False,
    )
    receipt_path = execution_batch_receipt_path(root, batch_id)
    write_execution_batch_receipt_document(receipt_path, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "page-review-batch",
            "occurred_at": generated_at,
            "batch_id": batch_id,
            "receipt_path": relative_path(root, receipt_path),
            "page_paths": [str(item.get("path") or "") for item in items],
            "status": status,
            "count": len(items),
        },
    )
    append_wiki_log(
        root,
        "review-batch",
        f"{len(items)} pages",
        [
            f"status: `{status}`",
            f"receipt: `{relative_path(root, receipt_path)}`",
            f"pages: `{', '.join(str(item.get('path') or '') for item in items[:4])}`",
        ],
    )
    return {
        "batch_id": batch_id,
        "operation": "review-page-batch",
        "status": status,
        "count": len(items),
        "receipt_path": relative_path(root, receipt_path),
        "items": items,
    }


@runtime_write_operation
def apply_machine_memory_actions_batch(
    root: Path,
    action_ids: list[str],
    *,
    note: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    from ..utils.time import utc_now

    ensure_layout(root)
    ordered_ids: list[str] = []
    seen_ids: set[str] = set()
    for action_id in action_ids:
        normalized = action_id.strip()
        if not normalized or normalized in seen_ids:
            continue
        seen_ids.add(normalized)
        ordered_ids.append(normalized)
    if not ordered_ids:
        raise ValueError("Batch apply requires at least one action.")
    state = load_machine_memory_action_state_strict(root)
    actions = {
        str(action.get("id") or ""): action
        for action in state.get("actions", [])
        if isinstance(action, dict) and str(action.get("id") or "")
    }
    missing = [action_id for action_id in ordered_ids if action_id not in actions]
    if missing:
        raise FileNotFoundError(f"Machine-memory action not found: {missing[0]}")
    unsupported = [action_id for action_id in ordered_ids if not action_supports_low_risk_apply(actions[action_id])]
    if unsupported:
        raise RuntimeError(f"Machine-memory action is not ready for low-risk batch apply: {unsupported[0]}")
    items: list[dict[str, Any]] = []
    operation = "action-dry-run-batch" if dry_run else "action-apply-batch"
    for action_id in ordered_ids:
        preview = _machine_memory_actions.apply_machine_memory_action(root, action_id, note=note, dry_run=True)
        if dry_run:
            items.append(preview)
            continue
        applied = _machine_memory_actions.apply_machine_memory_action(
            root,
            action_id,
            note=note,
            bundle_path=str(preview.get("bundle_path") or ""),
        )
        items.append(applied)
    generated_at = utc_now()
    batch_id = _build_batch_id(operation, ordered_ids)
    receipt = build_execution_batch_receipt(
        root,
        batch_id=batch_id,
        operation=operation,
        generated_at=generated_at,
        items=items,
        note=note,
        revert_supported=not dry_run,
    )
    receipt_path = execution_batch_receipt_path(root, batch_id)
    wiki_log_path = root / "wiki" / "indexes" / "log.md"
    runtime_path = runtime_history_path(root)
    audit_path = root / AUDIT_STREAM_PATH
    # snapshot order matches write order: receipt → runtime (+audit mirror via append_runtime_history) → wiki_log.
    # rollback uses reversed(snapshots), so we restore in reverse: wiki_log → audit → runtime → receipt.
    snapshots: list[tuple[Path, bytes | None]] = [
        (receipt_path, _snapshot_file_bytes(receipt_path) if receipt_path.exists() else None),
        (runtime_path, _snapshot_file_bytes(runtime_path) if runtime_path.exists() else None),
        (audit_path, _snapshot_file_bytes(audit_path) if audit_path.exists() else None),
        (wiki_log_path, _snapshot_file_bytes(wiki_log_path) if wiki_log_path.exists() else None),
    ]
    try:
        write_execution_batch_receipt_document(receipt_path, receipt)
        append_runtime_history(
            root,
            {
                "event_type": operation,
                "occurred_at": generated_at,
                "batch_id": batch_id,
                "receipt_path": relative_path(root, receipt_path),
                "action_ids": ordered_ids,
                "count": len(items),
                "dry_run": dry_run,
            },
        )
        append_wiki_log(
            root,
            "action-batch",
            f"{len(items)} actions",
            [
                f"operation: `{operation}`",
                f"receipt: `{relative_path(root, receipt_path)}`",
                f"actions: `{', '.join(ordered_ids[:5])}`",
            ],
        )
    except Exception as tx_exc:
        try:
            for path, snapshot in reversed(snapshots):
                if snapshot is None:
                    path.unlink(missing_ok=True)
                else:
                    _restore_file_bytes(path, snapshot)
        except Exception as rollback_exc:
            raise MachineMemoryActionApplyBatchReceiptHalfWriteError(
                f"action-apply-batch receipt transaction half-write: tx_error={tx_exc}; rollback_error={rollback_exc}"
            ) from rollback_exc
        raise MachineMemoryActionApplyBatchReceiptError(
            "action-apply-batch receipt persistence failed; successful actions retained"
        ) from tx_exc
    return {
        "batch_id": batch_id,
        "operation": operation,
        "dry_run": dry_run,
        "count": len(items),
        "receipt_path": relative_path(root, receipt_path),
        "items": items,
    }


@runtime_write_operation
def revert_machine_memory_action_batch(
    root: Path,
    *,
    batch_id: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    from ..utils.time import utc_now

    ensure_layout(root)
    target_receipt = _load_latest_action_apply_batch_receipt(root, batch_id)
    if str(target_receipt.get("kind") or "") != "execution-batch-receipt":
        raise RuntimeError("Batch receipt is not valid.")
    if str(target_receipt.get("operation") or "") != "action-apply-batch":
        raise RuntimeError("Only action apply batches can be reverted.")
    target_batch_id = str(target_receipt.get("batch_id") or batch_id or "")
    action_ids = [
        str(item.get("id") or item.get("action_id") or "")
        for item in target_receipt.get("items", [])
        if isinstance(item, dict) and (item.get("id") or item.get("action_id"))
    ]
    if not action_ids:
        raise RuntimeError("Action apply batch receipt is empty.")
    items = [
        _machine_memory_actions.revert_machine_memory_action(root, action_id, note=note)
        for action_id in reversed(action_ids)
    ]
    generated_at = utc_now()
    revert_batch_id = _build_batch_id("action-revert-batch", action_ids)
    receipt = build_execution_batch_receipt(
        root,
        batch_id=revert_batch_id,
        operation="action-revert-batch",
        generated_at=generated_at,
        items=items,
        note=note,
        revert_supported=False,
        reverted_batch_id=target_batch_id,
    )
    receipt_path = execution_batch_receipt_path(root, revert_batch_id)
    write_execution_batch_receipt_document(receipt_path, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "action-revert-batch",
            "occurred_at": generated_at,
            "batch_id": revert_batch_id,
            "reverted_batch_id": target_batch_id,
            "receipt_path": relative_path(root, receipt_path),
            "action_ids": action_ids,
            "count": len(items),
        },
    )
    append_wiki_log(
        root,
        "action-batch-revert",
        f"{len(items)} actions",
        [
            f"reverted_batch: `{target_batch_id}`",
            f"receipt: `{relative_path(root, receipt_path)}`",
            f"actions: `{', '.join(action_ids[:5])}`",
        ],
    )
    return {
        "batch_id": revert_batch_id,
        "operation": "action-revert-batch",
        "reverted_batch_id": target_batch_id,
        "count": len(items),
        "receipt_path": relative_path(root, receipt_path),
        "items": items,
    }
