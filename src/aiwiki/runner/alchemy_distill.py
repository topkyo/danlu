"""Distill apply orchestration for alchemy runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aiwiki.runner.alchemy_shared import _apply_paths, _capture_sizes, _rollback_truncate, _trace_summary


def run_alchemy_distill_apply_impl(
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
        status_error_template="alchemy distill apply requires an ok dry-run preview (got {status})",
        empty_error_message="alchemy distill apply requires at least one apply-supported elixir candidate",
        kind="elixir_candidate_refresh",
        require_apply_supported=True,
    )

    deps["ensure_layout"](root)
    refreshed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    applied_at = deps["utc_now"]()
    action_id = deps["unique_action_id"](root, applied_at=applied_at)
    receipt_path, history_path, audit_path = _apply_paths(root, action_id, deps)
    audit_jsonl_path, history_size_before, audit_size_before = _capture_sizes(root, history_path)
    touched_path_snapshots: dict[Path, bytes | None] = {}
    trace_ids, trace_id, candidate_ids = _trace_summary(deps, preview, candidates)
    idempotency_key = deps["idempotency_key"](scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-distill",
        "applied_at": applied_at,
        "operation": "alchemy-distill-refresh",
        "action_id": action_id,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "title": f"Alchemy distill refresh {scope}",
        "status": "applied",
        "protocol": deps["first_preview_protocol"](preview),
        "subject_kind": "alchemy_elixir_candidate",
        "subject_id": f"distill:{scope}",
        "apply_mode": "alchemy-distill",
        "note": note or "",
        "primary_path": "output/_candidates/elixirs",
        "secondary_path": "",
        "receipt_path": deps["relative_path"](root, receipt_path),
        "scope": scope,
        "primitive": "distill",
        "candidate_ids": candidate_ids,
        "candidate_count": len(candidates),
        "refreshed_count": len(refreshed),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "idempotency_key": idempotency_key,
        "changed": bool(refreshed),
        "revert_supported": False,
        "revert_policy": "non_revertible_candidate_iteration: re-run distill/finalize/promote lifecycle with receipt evidence; before/after hashes document refreshed candidates",
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
        "source_preview": deps["distill_preview_receipt_summary"](preview, candidates),
        "result_summary": {"refreshed": refreshed, "skipped": skipped},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        for candidate in candidates:
            candidate_id = str(candidate.get("candidate_id") or "")
            target_ref = str(candidate.get("target_ref") or "")
            target_id = deps["target_id"](target_ref)
            if not target_id:
                skipped.append({"candidate_id": candidate_id, "target_ref": target_ref, "reason": "missing_target_ref"})
                continue
            candidate_path = root / "output" / "_candidates" / "elixirs" / f"{target_id}.md"
            if not candidate_path.exists():
                skipped.append(
                    {
                        "candidate_id": candidate_id,
                        "target_ref": target_ref,
                        "elixir_id": target_id,
                        "reason": "target_missing",
                    }
                )
                continue
            question = deps["question"](candidate)
            if question in deps["history_questions"](candidate_path):
                skipped.append(
                    {
                        "candidate_id": candidate_id,
                        "target_ref": target_ref,
                        "elixir_id": target_id,
                        "reason": "already_distilled",
                    }
                )
                continue
            if candidate_path not in touched_path_snapshots:
                touched_path_snapshots[candidate_path] = deps["snapshot_file_bytes"](candidate_path)
            before_hash = deps["compute_file_sha256"](candidate_path)
            result = deps["distill_runner"](root, target_id, question)
            result_path = root / str(result.get("path") or deps["relative_path"](root, candidate_path))
            after_hash = deps["compute_file_sha256"](result_path)
            refreshed.append(
                {
                    "candidate_id": candidate_id,
                    "target_ref": target_ref,
                    "elixir_id": target_id,
                    "path": deps["relative_path"](root, result_path),
                    "question": question,
                    "before_hash": before_hash,
                    "after_hash": after_hash,
                    "iteration": result.get("iteration"),
                }
            )
        receipt["refreshed_count"] = len(refreshed)
        receipt["skipped_count"] = len(skipped)
        receipt["skipped"] = skipped
        receipt["changed"] = bool(refreshed)
        receipt["result_summary"] = {"refreshed": refreshed, "skipped": skipped}
        deps["atomic_write_text"](receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        deps["append_execution_receipt_history"](root, receipt)
        deps["append_runtime_history"](
            root,
            {
                "event_type": "alchemy-distill-refreshed",
                "recorded_at": applied_at,
                "status": "completed",
                "scope": scope,
                "candidate_count": len(candidates),
                "candidate_ids": candidate_ids,
                "refreshed_count": len(refreshed),
                "skipped_count": len(skipped),
                "receipt_path": deps["relative_path"](root, receipt_path),
                "trace_id": trace_id,
                "trace_ids": trace_ids,
                "subject_kind": "alchemy_elixir_candidate",
                "subject_id": f"distill:{scope}",
            },
        )
    except Exception as tx_exc:
        try:
            for path, snapshot in reversed(touched_path_snapshots.items()):
                if snapshot is None:
                    path.unlink(missing_ok=True)
                else:
                    deps["restore_file_bytes"](path, snapshot)
            _rollback_truncate(deps, history_path, history_size_before, audit_jsonl_path, audit_size_before)
            receipt_path.unlink(missing_ok=True)
        except Exception as rollback_exc:
            raise deps["half_write_error_cls"](
                f"distill_apply rollback failed for {scope}: tx_error={tx_exc}; rollback_error={rollback_exc}"
            ) from rollback_exc
        raise deps["error_cls"](f"distill_apply failed for {scope}; mutation rolled back") from tx_exc
    return {
        "status": "applied",
        "primitive": "distill",
        "scope": scope,
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "refreshed_count": len(refreshed),
        "refreshed": refreshed,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "receipt_path": deps["relative_path"](root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": bool(refreshed),
        "preview": preview,
    }
