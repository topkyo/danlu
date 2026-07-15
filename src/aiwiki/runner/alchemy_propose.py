"""Propose apply orchestration for alchemy runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aiwiki import autonomy_policy
from aiwiki.execution.l3_proposals import create_l3_proposal, load_l3_proposal_state
from aiwiki.runner.alchemy_shared import _apply_paths, _capture_sizes, _rollback_truncate, _trace_summary


def run_alchemy_propose_apply_impl(
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
    reason = autonomy_policy.disabled_reason(root, "disable_alchemy_auto")
    if reason is not None:
        return {
            "status": "skipped",
            "flag": "disable_alchemy_auto",
            "reason": reason,
            "scope": scope,
        }

    if not deps["resolve_planner_log_path"](root, planner_log_path).exists():
        raise ValueError(deps["cold_start_error"])

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
        status_error_template="alchemy propose apply requires an ok dry-run preview (got {status})",
        empty_error_message="alchemy propose apply requires a non-empty dry-run preview",
    )

    deps["ensure_layout"](root)
    existing_ids = {
        str(item.get("proposal_id") or "")
        for item in load_l3_proposal_state(root).get("proposals", [])
        if isinstance(item, dict)
    }
    generated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    planner_log_ref = str(preview.get("planner_log_path") or "")

    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        proposal_id = deps["slugify"](f"alchemy-{candidate_id or 'propose'}")
        if proposal_id in existing_ids:
            skipped.append({"candidate_id": candidate_id, "proposal_id": proposal_id, "reason": "already_exists"})
            continue
        target_file = str(candidate.get("apply_target_file") or "prompts/ask.md")
        signal_ids = [str(item) for item in candidate.get("signal_ids", []) if isinstance(item, str) and item.strip()]
        evidence_refs = [f"{planner_log_ref}#{signal_id}" for signal_id in signal_ids if planner_log_ref]
        content = deps["prompt_content"](root, target_file=target_file, candidate=candidate, scope=scope)
        result = create_l3_proposal(
            root,
            kind=str(candidate.get("apply_proposal_kind") or "prompt_proposal"),
            proposal_id=proposal_id,
            target_file=target_file,
            content=content,
            rationale=f"Generated from scoped alchemy propose preview candidate {candidate_id}. Manual accept is required.",
            evidence_refs=evidence_refs,
            signal_ids=signal_ids,
            pattern="failure_cluster",
        )
        result["candidate_id"] = candidate_id
        generated.append(result)
        existing_ids.add(proposal_id)

    applied_at = deps["utc_now"]()
    action_id = deps["unique_action_id"](root, applied_at=applied_at)
    receipt_path, history_path, audit_path = _apply_paths(root, action_id, deps)
    trace_ids, trace_id, candidate_ids = _trace_summary(deps, preview, candidates)
    proposal_ids = [str(item.get("proposal_id") or "") for item in generated if item.get("proposal_id")]
    idempotency_key = deps["idempotency_key"](scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-propose",
        "applied_at": applied_at,
        "operation": "alchemy-propose-generate",
        "action_id": action_id,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "title": f"Alchemy propose generate {scope}",
        "status": "applied",
        "protocol": deps["first_preview_protocol"](preview),
        "subject_kind": "alchemy_proposal_plane",
        "subject_id": f"propose:{scope}",
        "apply_mode": "alchemy-propose",
        "note": note or "",
        "primary_path": "output/_proposals/prompt",
        "secondary_path": ".aiwiki/state/l3-proposals.json",
        "receipt_path": deps["relative_path"](root, receipt_path),
        "scope": scope,
        "primitive": "propose",
        "candidate_ids": candidate_ids,
        "candidate_count": len(candidates),
        "proposal_ids": proposal_ids,
        "generated_count": len(generated),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "idempotency_key": idempotency_key,
        "changed": bool(generated),
        "revert_supported": False,
        "revert_policy": "non_revertible_proposal_generation: reject generated L3 proposal candidates through review proposal workflow; target-file apply remains receipt-gated",
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
        "source_preview": deps["propose_preview_receipt_summary"](preview, candidates),
        "result_summary": {"generated": generated, "skipped": skipped},
    }
    audit_jsonl_path, history_size_before, audit_size_before = _capture_sizes(root, history_path)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        deps["atomic_write_text"](receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        deps["append_execution_receipt_history"](root, receipt)
        deps["append_runtime_history"](
            root,
            {
                "event_type": "alchemy-propose-generated",
                "recorded_at": applied_at,
                "status": "completed",
                "scope": scope,
                "candidate_count": len(candidates),
                "candidate_ids": candidate_ids,
                "generated_count": len(generated),
                "proposal_ids": proposal_ids,
                "receipt_path": deps["relative_path"](root, receipt_path),
                "trace_id": trace_id,
                "trace_ids": trace_ids,
                "subject_kind": "alchemy_proposal_plane",
                "subject_id": f"propose:{scope}",
            },
        )
    except Exception as tx_exc:
        try:
            _rollback_truncate(deps, history_path, history_size_before, audit_jsonl_path, audit_size_before)
            receipt_path.unlink(missing_ok=True)
        except Exception as rollback_exc:
            raise deps["half_write_error_cls"](
                f"propose_apply receipt rollback failed for {scope}: tx_error={tx_exc}; rollback_error={rollback_exc}"
            ) from rollback_exc
        raise deps["error_cls"](
            f"propose_apply receipt persistence failed for {scope}; receipt-tier residue rolled back (successful proposals retained)"
        ) from tx_exc
    return {
        "status": "applied",
        "primitive": "propose",
        "scope": scope,
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "generated_count": len(generated),
        "proposal_ids": proposal_ids,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "receipt_path": deps["relative_path"](root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": bool(generated),
        "preview": preview,
    }
