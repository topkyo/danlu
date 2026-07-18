"""Review apply orchestration for alchemy runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aiwiki.runner.alchemy_shared import _apply_paths, _capture_sizes, _rollback_truncate, _trace_summary


def run_alchemy_review_apply_impl(
    root: Path,
    *,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    limit: int = 50,
    note: str | None = None,
    deps: dict[str, Any],
) -> dict[str, Any]:
    preview = deps["preview_runner"](
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
        allow_current_writer_lock=True,
    )
    preview, candidates = deps["apply_preview_candidates"](
        preview,
        status_error_template="alchemy review apply requires an ok dry-run preview (got {status})",
        empty_error_message="alchemy review apply requires a non-empty dry-run preview",
    )

    applied_at = deps["utc_now"]()
    action_id = deps["unique_action_id"](root, applied_at=applied_at)

    receipt_path, history_path, audit_path = _apply_paths(root, action_id, deps)
    audit_jsonl_path, history_size_before, audit_size_before = _capture_sizes(root, history_path)
    queue_path = root / "wiki" / "indexes" / "review-queue.md"
    queue_existed_before = queue_path.exists()
    queue_snapshot = deps["snapshot_file_bytes"](queue_path)
    trace_ids, trace_id, candidate_ids = _trace_summary(deps, preview, candidates)
    idempotency_key = deps["idempotency_key"](scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
    queue_result: dict[str, Any] = {}
    try:
        queue_result = deps["materialize_review_queue"](root, preview=preview, candidates=candidates)
        receipt = {
            "version": 1,
            "kind": "execution-receipt",
            "generated_by": "aiwiki-alchemy-review",
            "applied_at": applied_at,
            "operation": "alchemy-review-enqueue",
            "action_id": action_id,
            "trace_id": trace_id,
            "trace_ids": trace_ids,
            "title": f"Alchemy review enqueue {scope}",
            "status": "applied",
            "protocol": deps["first_preview_protocol"](preview),
            "subject_kind": "alchemy_review_queue",
            "subject_id": f"review:{scope}",
            "apply_mode": "alchemy-review",
            "note": note or "",
            "primary_path": queue_result["path"],
            "secondary_path": "",
            "receipt_path": deps["relative_path"](root, receipt_path),
            "scope": scope,
            "primitive": "review",
            "candidate_ids": candidate_ids,
            "candidate_count": len(candidates),
            "idempotency_key": idempotency_key,
            "before_hash": queue_result["before_hash"],
            "after_hash": queue_result["after_hash"],
            "changed": queue_result["changed"],
            "revert_supported": False,
            "revert_policy": "non_revertible_derived_index: rerun compile or reapply a newer review preview to replace the managed section",
            "audit_stream": "execution_receipts",
            "audit_event": "execution_receipt_history_append",
            "audit_path": audit_path,
            "source_preview": deps["review_preview_receipt_summary"](preview, candidates),
            "result_summary": queue_result,
        }
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        deps["atomic_write_text"](
            receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        deps["append_execution_receipt_history"](root, receipt)
    except Exception as tx_exc:
        try:
            _rollback_truncate(deps, history_path, history_size_before, audit_jsonl_path, audit_size_before)
            if receipt_path.exists():
                receipt_path.unlink()
            if queue_existed_before:
                deps["restore_file_bytes"](queue_path, queue_snapshot)
            elif queue_path.exists():
                queue_path.unlink()
        except Exception as rollback_exc:
            raise deps["half_write_error_cls"](
                f"review_apply rollback failed for {scope}: tx_error={tx_exc}; rollback_error={rollback_exc}"
            ) from rollback_exc
        raise deps["error_cls"](f"review_apply failed for {scope}; mutation rolled back") from tx_exc
    try:
        deps["append_runtime_history"](
            root,
            {
                "event_type": "alchemy-review-enqueued",
                "recorded_at": applied_at,
                "status": "completed",
                "scope": scope,
                "candidate_count": len(candidates),
                "candidate_ids": candidate_ids,
                "review_queue_path": queue_result["path"],
                "receipt_path": deps["relative_path"](root, receipt_path),
                "trace_id": trace_id,
                "trace_ids": trace_ids,
                "subject_kind": "alchemy_review_queue",
                "subject_id": f"review:{scope}",
            },
        )
    except Exception as exc:
        deps["logger"].warning("review_apply runtime-history append failed for %s: %s", scope, exc)
    return {
        "status": "applied",
        "primitive": "review",
        "scope": scope,
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "review_queue_path": queue_result["path"],
        "receipt_path": deps["relative_path"](root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": queue_result["changed"],
        "preview": preview,
    }
