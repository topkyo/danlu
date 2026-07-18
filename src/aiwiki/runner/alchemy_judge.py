"""Alchemy judge primitive orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from aiwiki.execution.history import append_execution_receipt_history, append_runtime_history
from aiwiki.execution.l3_proposals import STAGING_JUDGE_PROPOSAL_DIR
from aiwiki.execution.paths import execution_receipt_history_path
from aiwiki.render.paths import execution_receipt_path
from aiwiki.runner import alchemy_materialize as materialize
from aiwiki.runner import alchemy_support as support
from aiwiki.utils.io import atomic_write_text
from aiwiki.utils.path import relative_path
from aiwiki.utils.time import utc_now

PreviewRunner = Callable[..., dict[str, Any]]


def run_judge_preview(
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
    allow_current_writer_lock: bool = False,
) -> dict[str, Any]:
    from aiwiki.planner import preview_judge_primitive

    return preview_judge_primitive(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
        allow_current_writer_lock=allow_current_writer_lock,
    )


def run_judge_apply(
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
    preview_runner: PreviewRunner,
) -> dict[str, Any]:
    preview = preview_runner(
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
    preview, candidates = support.apply_preview_candidates(
        preview,
        status_error_template="alchemy judge apply requires an ok dry-run preview (got {status})",
        empty_error_message="alchemy judge apply requires at least one apply-supported judgment candidate",
        kind="judgment_refresh",
        require_apply_supported=True,
    )

    refreshed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        result = materialize.materialize_alchemy_judge_refresh(root, preview=preview, candidate=candidate)
        if result["status"] == "skipped":
            skipped.append(result)
        else:
            refreshed.append(result)

    applied_at = utc_now()
    action_id = support.unique_alchemy_judge_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = support.preview_trace_ids(preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    idempotency_key = support.alchemy_judge_idempotency_key(
        scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids
    )
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-judge",
        "applied_at": applied_at,
        "operation": "alchemy-judge-refresh",
        "action_id": action_id,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "title": f"Alchemy judge refresh {scope}",
        "status": "applied",
        "protocol": support.first_preview_protocol(preview),
        "subject_kind": "alchemy_judgment_page",
        "subject_id": f"judge:{scope}",
        "apply_mode": "alchemy-judge",
        "note": note or "",
        "primary_path": "wiki/judgments",
        "secondary_path": "wiki/decisions",
        "receipt_path": relative_path(root, receipt_path),
        "scope": scope,
        "primitive": "judge",
        "candidate_ids": candidate_ids,
        "candidate_count": len(candidates),
        "refreshed_count": len(refreshed),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "idempotency_key": idempotency_key,
        "changed": any(item.get("changed") for item in refreshed),
        "revert_supported": False,
        "revert_policy": "non_revertible_refresh_marker: reapply a newer judge preview to replace the managed marker; semantic judgment edits remain explicit",
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
        "source_preview": support.judge_preview_receipt_summary(preview, candidates),
        "result_summary": {"refreshed": refreshed, "skipped": skipped},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    append_execution_receipt_history(root, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "alchemy-judge-refreshed",
            "recorded_at": applied_at,
            "status": "completed",
            "scope": scope,
            "candidate_count": len(candidates),
            "candidate_ids": candidate_ids,
            "refreshed_count": len(refreshed),
            "skipped_count": len(skipped),
            "receipt_path": relative_path(root, receipt_path),
            "trace_id": trace_id,
            "trace_ids": trace_ids,
            "subject_kind": "alchemy_judgment_page",
            "subject_id": f"judge:{scope}",
        },
    )
    return {
        "status": "applied",
        "primitive": "judge",
        "scope": scope,
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "refreshed_count": len(refreshed),
        "refreshed": refreshed,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "receipt_path": relative_path(root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": any(item.get("changed") for item in refreshed),
        "preview": preview,
    }


def run_judge_propose(
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
    preview_runner: PreviewRunner,
) -> dict[str, Any]:
    preview = preview_runner(
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
    preview, candidates = support.apply_preview_candidates(
        preview,
        status_error_template="alchemy judge propose requires an ok dry-run preview (got {status})",
        empty_error_message="alchemy judge propose requires at least one existing judgment candidate",
        kind="judgment_refresh",
        require_apply_supported=True,
    )

    generated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        result = materialize.materialize_alchemy_judge_proposal(root, preview=preview, candidate=candidate)
        if result["status"] == "skipped":
            skipped.append(result)
        else:
            generated.append(result)

    applied_at = utc_now()
    action_id = support.unique_alchemy_judge_proposal_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = support.preview_trace_ids(preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    proposal_ids = [str(item.get("proposal_id") or "") for item in [*generated, *skipped] if item.get("proposal_id")]
    idempotency_key = support.alchemy_judge_proposal_idempotency_key(
        scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids
    )
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-judge-proposal",
        "applied_at": applied_at,
        "operation": "alchemy-judge-proposal-preview",
        "action_id": action_id,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "title": f"Alchemy judge proposal preview {scope}",
        "status": "applied",
        "protocol": support.first_preview_protocol(preview),
        "subject_kind": "alchemy_judge_proposal",
        "subject_id": f"judge-proposal:{scope}",
        "apply_mode": "alchemy-judge-propose",
        "note": note or "",
        "primary_path": STAGING_JUDGE_PROPOSAL_DIR,
        "secondary_path": "",
        "receipt_path": relative_path(root, receipt_path),
        "scope": scope,
        "primitive": "judge",
        "candidate_ids": candidate_ids,
        "candidate_count": len(candidates),
        "proposal_ids": proposal_ids,
        "generated_count": len(generated),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "idempotency_key": idempotency_key,
        "changed": bool(generated),
        "llm_invoked": False,
        "semantic_content_generated": False,
        "human_accept_required": True,
        "revert_supported": False,
        "revert_policy": "non_revertible_proposal_preview: reject or ignore generated proposal artifacts; target judgment pages are unchanged",
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
        "source_preview": support.judge_preview_receipt_summary(preview, candidates),
        "result_summary": {"generated": generated, "skipped": skipped},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    append_execution_receipt_history(root, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "alchemy-judge-proposal-created",
            "recorded_at": applied_at,
            "status": "completed",
            "scope": scope,
            "candidate_count": len(candidates),
            "candidate_ids": candidate_ids,
            "generated_count": len(generated),
            "proposal_ids": proposal_ids,
            "receipt_path": relative_path(root, receipt_path),
            "trace_id": trace_id,
            "trace_ids": trace_ids,
            "subject_kind": "alchemy_judge_proposal",
            "subject_id": f"judge-proposal:{scope}",
            "llm_invoked": False,
            "semantic_content_generated": False,
        },
    )
    return {
        "status": "applied",
        "primitive": "judge",
        "mode": "propose",
        "scope": scope,
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "generated_count": len(generated),
        "proposal_ids": proposal_ids,
        "generated": generated,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "receipt_path": relative_path(root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": bool(generated),
        "llm_invoked": False,
        "semantic_content_generated": False,
        "human_accept_required": True,
        "preview": preview,
    }
