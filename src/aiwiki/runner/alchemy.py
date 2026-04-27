"""Alchemy lifecycle wrappers and (in later batches) scoped primitives, lane orchestration, auto scheduler."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import append_runtime_history
from aiwiki.app_utils import (
    parse_frontmatter,
    relative_path,
    render_frontmatter,
    runtime_write_lock,
    runtime_write_operation,
    sha256_bytes,
    slugify,
    strip_frontmatter,
    utc_now,
)


def run_alchemy_legacy_migration_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from aiwiki.execution.alchemy import preview_legacy_elixir_migration

    return preview_legacy_elixir_migration(root, limit=limit)


def run_alchemy_legacy_migration_apply(root: Path, *, limit: int = 50, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy import apply_legacy_elixir_migration

    return apply_legacy_elixir_migration(root, limit=limit, note=note)


def run_alchemy_superseded_cleanup_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from aiwiki.execution.alchemy import preview_superseded_elixir_cleanup

    return preview_superseded_elixir_cleanup(root, limit=limit)


def run_alchemy_superseded_cleanup_apply(root: Path, *, limit: int = 50, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy import apply_superseded_elixir_cleanup

    return apply_superseded_elixir_cleanup(root, limit=limit, note=note)


@runtime_write_operation
def run_alchemy_start(
    root: Path,
    corpus_id: str,
    topic: str,
    *,
    protocol: str | None = None,
    include_elixir_ids: list[str] | None = None,
) -> dict[str, Any]:
    from aiwiki.execution.alchemy import start_elixir

    return start_elixir(root, corpus_id, protocol=protocol, topic=topic, include_elixir_ids=include_elixir_ids)


@runtime_write_operation
def run_alchemy_distill(root: Path, elixir_id: str, question: str, include_elixir_ids: list[str] | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy import distill_elixir

    return distill_elixir(root, elixir_id, question=question, include_elixir_ids=include_elixir_ids)


@runtime_write_operation
def run_alchemy_finalize(root: Path, *, elixir_id: str) -> dict[str, Any]:
    from aiwiki.execution.alchemy import finalize_elixir

    return finalize_elixir(root, elixir_id=elixir_id)


@runtime_write_operation
def run_alchemy_promote(root: Path, *, elixir_id: str, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy import promote_elixir

    return promote_elixir(root, elixir_id=elixir_id, note=note)


def run_alchemy_revert(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    from aiwiki.execution.alchemy import revert_elixir

    with runtime_write_lock(root):
        return revert_elixir(root, elixir_id=elixir_id, note=note)


def run_alchemy_demote(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    from aiwiki.execution.alchemy import demote_elixir

    with runtime_write_lock(root):
        return demote_elixir(root, elixir_id=elixir_id, note=note)


def run_alchemy_judge_preview(
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
    )


def run_alchemy_judge_apply(
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
) -> dict[str, Any]:
    preview = run_alchemy_judge_preview(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )
    status = str(preview.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy judge apply requires an ok dry-run preview (got {status})")
    candidates = [
        item
        for item in preview.get("candidates", [])
        if isinstance(item, dict) and item.get("apply_supported") is True and item.get("kind") == "judgment_refresh"
    ]
    if not candidates:
        raise RuntimeError("alchemy judge apply requires at least one apply-supported judgment candidate")

    from aiwiki.app_execution import append_execution_receipt_history
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.render.paths import execution_receipt_path

    refreshed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        result = _materialize_alchemy_judge_refresh(root, preview=preview, candidate=candidate)
        if result["status"] == "skipped":
            skipped.append(result)
        else:
            refreshed.append(result)

    applied_at = utc_now()
    action_id = _unique_alchemy_judge_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = _preview_trace_ids(preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    idempotency_key = _alchemy_judge_idempotency_key(scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
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
        "protocol": _first_preview_protocol(preview),
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
        "source_preview": _judge_preview_receipt_summary(preview, candidates),
        "result_summary": {"refreshed": refreshed, "skipped": skipped},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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


def run_alchemy_judge_propose(
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
) -> dict[str, Any]:
    preview = run_alchemy_judge_preview(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )
    status = str(preview.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy judge propose requires an ok dry-run preview (got {status})")
    candidates = [
        item
        for item in preview.get("candidates", [])
        if isinstance(item, dict) and item.get("apply_supported") is True and item.get("kind") == "judgment_refresh"
    ]
    if not candidates:
        raise RuntimeError("alchemy judge propose requires at least one existing judgment candidate")

    from aiwiki.app_execution import append_execution_receipt_history
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.render.paths import execution_receipt_path

    generated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        result = _materialize_alchemy_judge_proposal(root, preview=preview, candidate=candidate)
        if result["status"] == "skipped":
            skipped.append(result)
        else:
            generated.append(result)

    applied_at = utc_now()
    action_id = _unique_alchemy_judge_proposal_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = _preview_trace_ids(preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    proposal_ids = [
        str(item.get("proposal_id") or "")
        for item in [*generated, *skipped]
        if item.get("proposal_id")
    ]
    idempotency_key = _alchemy_judge_proposal_idempotency_key(scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
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
        "protocol": _first_preview_protocol(preview),
        "subject_kind": "alchemy_judge_proposal",
        "subject_id": f"judge-proposal:{scope}",
        "apply_mode": "alchemy-judge-propose",
        "note": note or "",
        "primary_path": "output/_proposals/judge",
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
        "source_preview": _judge_preview_receipt_summary(preview, candidates),
        "result_summary": {"generated": generated, "skipped": skipped},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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


def run_alchemy_judge_proposal_apply(
    root: Path,
    proposal: str | Path,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    from aiwiki.app_execution import append_execution_receipt_history
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.render.paths import execution_receipt_path

    proposal_path = _resolve_alchemy_judge_proposal_path(root, proposal)
    original_proposal = proposal_path.read_text(encoding="utf-8", errors="replace")
    proposal_frontmatter = parse_frontmatter(original_proposal)
    proposal_id = str(proposal_frontmatter.get("proposal_id") or proposal_path.stem)
    if str(proposal_frontmatter.get("kind") or "") != "alchemy-judge-proposal":
        raise ValueError("judge proposal apply requires kind=alchemy-judge-proposal.")
    if str(proposal_frontmatter.get("state") or "") != "accepted":
        raise RuntimeError("judge proposal apply requires proposal state=accepted.")
    target_ref = str(proposal_frontmatter.get("target_file") or "").strip()
    if not target_ref:
        raise ValueError("judge proposal apply requires target_file.")
    expected_hash = str(proposal_frontmatter.get("before_hash") or "").strip()
    if not expected_hash:
        raise ValueError("judge proposal apply requires before_hash.")
    accepted_body = _extract_marker_section(
        original_proposal,
        start_marker=_ALCHEMY_JUDGE_ACCEPTED_REFRESH_START,
        end_marker=_ALCHEMY_JUDGE_ACCEPTED_REFRESH_END,
    )
    if not accepted_body.strip():
        raise ValueError("judge proposal apply requires a non-empty accepted refresh block.")

    target = (root / target_ref).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("judge proposal target_file must stay within the workspace.") from exc
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"judge proposal target not found: {target_ref}")
    original_target = target.read_text(encoding="utf-8", errors="replace")
    target_frontmatter = parse_frontmatter(original_target)
    target_kind = str(target_frontmatter.get("kind") or "")
    if target_kind not in {"decision", "judgment"}:
        raise ValueError("judge proposal target must be a judgment or decision page.")
    before_hash = sha256_bytes(original_target.encode("utf-8"))
    if before_hash != expected_hash:
        raise RuntimeError("judge proposal target is stale; before_hash does not match current target.")

    target_body = strip_frontmatter(original_target).strip()
    section = _render_alchemy_judge_accepted_target_section(
        proposal_id=proposal_id,
        proposal_path=relative_path(root, proposal_path),
        accepted_body=accepted_body,
    )
    updated_body = _replace_marker_section(
        target_body,
        section,
        start_marker=_ALCHEMY_JUDGE_ACCEPTED_TARGET_START,
        end_marker=_ALCHEMY_JUDGE_ACCEPTED_TARGET_END,
    )
    updated_target = f"{render_frontmatter(target_frontmatter)}\n\n{updated_body.strip()}\n"
    changed = updated_target != original_target
    if changed:
        target.write_text(updated_target, encoding="utf-8")
    after_hash = sha256_bytes(updated_target.encode("utf-8"))

    applied_at = utc_now()
    action_id = _unique_alchemy_judge_proposal_apply_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    proposal_frontmatter["state"] = "applied"
    proposal_frontmatter["applied_at"] = applied_at
    proposal_frontmatter["receipt_path"] = relative_path(root, receipt_path)
    proposal_body = strip_frontmatter(original_proposal).strip()
    updated_proposal = f"{render_frontmatter(proposal_frontmatter)}\n\n{proposal_body}\n"
    proposal_path.write_text(updated_proposal, encoding="utf-8")
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-judge-proposal-apply",
        "applied_at": applied_at,
        "operation": "alchemy-judge-proposal-apply",
        "action_id": action_id,
        "title": f"Apply judge proposal {proposal_id}",
        "status": "applied",
        "subject_kind": "alchemy_judgment_page",
        "subject_id": target_ref,
        "apply_mode": "alchemy-judge-proposal",
        "note": note or "",
        "proposal_id": proposal_id,
        "proposal_path": relative_path(root, proposal_path),
        "target_file": target_ref,
        "target_kind": target_kind,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "changed": changed,
        "llm_invoked": False,
        "semantic_content_generated_by_runtime": False,
        "receipt_path": relative_path(root, receipt_path),
        "revert_supported": False,
        "revert_policy": "non_revertible_managed_section: restore target from before_hash manually or apply a newer accepted judge proposal",
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "alchemy-judge-proposal-applied",
            "recorded_at": applied_at,
            "status": "completed",
            "proposal_id": proposal_id,
            "proposal_path": relative_path(root, proposal_path),
            "target_file": target_ref,
            "receipt_path": relative_path(root, receipt_path),
            "subject_kind": "alchemy_judgment_page",
            "subject_id": target_ref,
            "changed": changed,
            "llm_invoked": False,
        },
    )
    return {
        "status": "applied",
        "primitive": "judge",
        "mode": "proposal-apply",
        "proposal_id": proposal_id,
        "proposal_path": relative_path(root, proposal_path),
        "target_file": target_ref,
        "target_kind": target_kind,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "changed": changed,
        "receipt_path": relative_path(root, receipt_path),
        "audit_path": audit_path,
        "llm_invoked": False,
    }


def run_alchemy_distill_preview(
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
) -> dict[str, Any]:
    from aiwiki.planner import preview_distill_primitive

    return preview_distill_primitive(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )


def run_alchemy_distill_apply(
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
) -> dict[str, Any]:
    preview = run_alchemy_distill_preview(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )
    status = str(preview.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy distill apply requires an ok dry-run preview (got {status})")
    candidates = [
        item
        for item in preview.get("candidates", [])
        if isinstance(item, dict) and item.get("apply_supported") is True and item.get("kind") == "elixir_candidate_refresh"
    ]
    if not candidates:
        raise RuntimeError("alchemy distill apply requires at least one apply-supported elixir candidate")

    from aiwiki.app_execution import append_execution_receipt_history, compute_file_sha256
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.render.paths import execution_receipt_path

    ensure_layout(root)
    refreshed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        target_ref = str(candidate.get("target_ref") or "")
        target_id = _alchemy_distill_target_id(target_ref)
        if not target_id:
            skipped.append({"candidate_id": candidate_id, "target_ref": target_ref, "reason": "missing_target_ref"})
            continue
        candidate_path = root / "output" / "_candidates" / "elixirs" / f"{target_id}.md"
        if not candidate_path.exists():
            skipped.append({"candidate_id": candidate_id, "target_ref": target_ref, "elixir_id": target_id, "reason": "target_missing"})
            continue
        question = _alchemy_distill_question(candidate)
        if question in _alchemy_distill_history_questions(candidate_path):
            skipped.append({"candidate_id": candidate_id, "target_ref": target_ref, "elixir_id": target_id, "reason": "already_distilled"})
            continue
        before_hash = compute_file_sha256(candidate_path)
        result = run_alchemy_distill(root, target_id, question)
        result_path = root / str(result.get("path") or relative_path(root, candidate_path))
        after_hash = compute_file_sha256(result_path)
        refreshed.append(
            {
                "candidate_id": candidate_id,
                "target_ref": target_ref,
                "elixir_id": target_id,
                "path": relative_path(root, result_path),
                "question": question,
                "before_hash": before_hash,
                "after_hash": after_hash,
                "iteration": result.get("iteration"),
            }
        )

    applied_at = utc_now()
    action_id = _unique_alchemy_distill_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = _preview_trace_ids(preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    idempotency_key = _alchemy_distill_idempotency_key(scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
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
        "protocol": _first_preview_protocol(preview),
        "subject_kind": "alchemy_elixir_candidate",
        "subject_id": f"distill:{scope}",
        "apply_mode": "alchemy-distill",
        "note": note or "",
        "primary_path": "output/_candidates/elixirs",
        "secondary_path": "",
        "receipt_path": relative_path(root, receipt_path),
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
        "source_preview": _distill_preview_receipt_summary(preview, candidates),
        "result_summary": {"refreshed": refreshed, "skipped": skipped},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    append_runtime_history(
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
            "receipt_path": relative_path(root, receipt_path),
            "trace_id": trace_id,
            "trace_ids": trace_ids,
            "subject_kind": "alchemy_elixir_candidate",
            "subject_id": f"distill:{scope}",
        },
    )
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
        "receipt_path": relative_path(root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": bool(refreshed),
        "preview": preview,
    }


def run_alchemy_review_preview(
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
) -> dict[str, Any]:
    from aiwiki.planner import preview_review_primitive

    return preview_review_primitive(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )


def run_alchemy_review_apply(
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
) -> dict[str, Any]:
    preview = run_alchemy_review_preview(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )
    status = str(preview.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy review apply requires an ok dry-run preview (got {status})")
    candidates = [item for item in preview.get("candidates", []) if isinstance(item, dict)]
    if not candidates:
        raise RuntimeError("alchemy review apply requires a non-empty dry-run preview")

    queue_result = _materialize_alchemy_review_queue(root, preview=preview, candidates=candidates)
    applied_at = utc_now()
    action_id = _unique_alchemy_review_action_id(root, applied_at=applied_at)

    from aiwiki.app_execution import append_execution_receipt_history
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.render.paths import execution_receipt_path

    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = _preview_trace_ids(preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    idempotency_key = _alchemy_review_idempotency_key(scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
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
        "protocol": _first_preview_protocol(preview),
        "subject_kind": "alchemy_review_queue",
        "subject_id": f"review:{scope}",
        "apply_mode": "alchemy-review",
        "note": note or "",
        "primary_path": queue_result["path"],
        "secondary_path": "",
        "receipt_path": relative_path(root, receipt_path),
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
        "source_preview": _review_preview_receipt_summary(preview, candidates),
        "result_summary": queue_result,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "alchemy-review-enqueued",
            "recorded_at": applied_at,
            "status": "completed",
            "scope": scope,
            "candidate_count": len(candidates),
            "candidate_ids": candidate_ids,
            "review_queue_path": queue_result["path"],
            "receipt_path": relative_path(root, receipt_path),
            "trace_id": trace_id,
            "trace_ids": trace_ids,
            "subject_kind": "alchemy_review_queue",
            "subject_id": f"review:{scope}",
        },
    )
    return {
        "status": "applied",
        "primitive": "review",
        "scope": scope,
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "review_queue_path": queue_result["path"],
        "receipt_path": relative_path(root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": queue_result["changed"],
        "preview": preview,
    }


def run_alchemy_propose_preview(
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
) -> dict[str, Any]:
    from aiwiki.planner import preview_propose_primitive

    return preview_propose_primitive(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )


def run_alchemy_propose_apply(
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
) -> dict[str, Any]:
    preview = run_alchemy_propose_preview(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )
    status = str(preview.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy propose apply requires an ok dry-run preview (got {status})")
    candidates = [item for item in preview.get("candidates", []) if isinstance(item, dict)]
    if not candidates:
        raise RuntimeError("alchemy propose apply requires a non-empty dry-run preview")

    from aiwiki.app_execution import append_execution_receipt_history
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.execution.l3_proposals import create_l3_proposal, load_l3_proposal_state
    from aiwiki.render.paths import execution_receipt_path

    ensure_layout(root)
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
        proposal_id = slugify(f"alchemy-{candidate_id or 'propose'}")
        if proposal_id in existing_ids:
            skipped.append({"candidate_id": candidate_id, "proposal_id": proposal_id, "reason": "already_exists"})
            continue
        target_file = str(candidate.get("apply_target_file") or "prompts/ask.md")
        signal_ids = [str(item) for item in candidate.get("signal_ids", []) if isinstance(item, str) and item.strip()]
        evidence_refs = [f"{planner_log_ref}#{signal_id}" for signal_id in signal_ids if planner_log_ref]
        content = _alchemy_propose_prompt_content(root, target_file=target_file, candidate=candidate, scope=scope)
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

    applied_at = utc_now()
    action_id = _unique_alchemy_propose_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = _preview_trace_ids(preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    proposal_ids = [str(item.get("proposal_id") or "") for item in generated if item.get("proposal_id")]
    idempotency_key = _alchemy_propose_idempotency_key(scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
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
        "protocol": _first_preview_protocol(preview),
        "subject_kind": "alchemy_proposal_plane",
        "subject_id": f"propose:{scope}",
        "apply_mode": "alchemy-propose",
        "note": note or "",
        "primary_path": "output/_proposals/prompt",
        "secondary_path": ".aiwiki/state/l3-proposals.json",
        "receipt_path": relative_path(root, receipt_path),
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
        "source_preview": _propose_preview_receipt_summary(preview, candidates),
        "result_summary": {"generated": generated, "skipped": skipped},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    append_runtime_history(
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
            "receipt_path": relative_path(root, receipt_path),
            "trace_id": trace_id,
            "trace_ids": trace_ids,
            "subject_kind": "alchemy_proposal_plane",
            "subject_id": f"propose:{scope}",
        },
    )
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
        "receipt_path": relative_path(root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": bool(generated),
        "preview": preview,
    }


_ALCHEMY_REVIEW_QUEUE_START = "<!-- aiwiki:alchemy-review-enqueue:start -->"
_ALCHEMY_REVIEW_QUEUE_END = "<!-- aiwiki:alchemy-review-enqueue:end -->"
_ALCHEMY_JUDGE_REFRESH_START = "<!-- aiwiki:alchemy-judge-refresh:start -->"
_ALCHEMY_JUDGE_REFRESH_END = "<!-- aiwiki:alchemy-judge-refresh:end -->"
_ALCHEMY_JUDGE_PROPOSAL_START = "<!-- aiwiki:alchemy-judge-proposal:start -->"
_ALCHEMY_JUDGE_PROPOSAL_END = "<!-- aiwiki:alchemy-judge-proposal:end -->"
_ALCHEMY_JUDGE_ACCEPTED_REFRESH_START = "<!-- aiwiki:accepted-judge-refresh:start -->"
_ALCHEMY_JUDGE_ACCEPTED_REFRESH_END = "<!-- aiwiki:accepted-judge-refresh:end -->"
_ALCHEMY_JUDGE_ACCEPTED_TARGET_START = "<!-- aiwiki:alchemy-accepted-judge-refresh:start -->"
_ALCHEMY_JUDGE_ACCEPTED_TARGET_END = "<!-- aiwiki:alchemy-accepted-judge-refresh:end -->"


def _materialize_alchemy_judge_refresh(
    root: Path,
    *,
    preview: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    target_ref = str(candidate.get("target_ref") or "")
    candidate_id = str(candidate.get("candidate_id") or "")
    target = (root / target_ref).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return {"status": "skipped", "candidate_id": candidate_id, "target_ref": target_ref, "reason": "target_outside_root"}
    if not target.exists():
        return {"status": "skipped", "candidate_id": candidate_id, "target_ref": target_ref, "reason": "target_missing"}
    original = target.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(original)
    kind = str(frontmatter.get("kind") or "")
    if kind not in {"decision", "judgment"}:
        return {"status": "skipped", "candidate_id": candidate_id, "target_ref": target_ref, "reason": "not_judgment_asset"}
    before_hash = sha256_bytes(original.encode("utf-8"))
    body = strip_frontmatter(original).strip()
    section = _render_alchemy_judge_refresh_section(preview=preview, candidate=candidate)
    updated_body = _replace_marker_section(
        body,
        section,
        start_marker=_ALCHEMY_JUDGE_REFRESH_START,
        end_marker=_ALCHEMY_JUDGE_REFRESH_END,
    )
    updated = f"{render_frontmatter(frontmatter)}\n\n{updated_body.strip()}\n"
    changed = updated != original
    if changed:
        target.write_text(updated, encoding="utf-8")
    after_hash = sha256_bytes(updated.encode("utf-8"))
    return {
        "status": "refreshed",
        "candidate_id": candidate_id,
        "target_ref": target_ref,
        "path": relative_path(root, target),
        "kind": kind,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "changed": changed,
    }


def _render_alchemy_judge_refresh_section(*, preview: dict[str, Any], candidate: dict[str, Any]) -> str:
    lines = [
        _ALCHEMY_JUDGE_REFRESH_START,
        "## Alchemy Judge Refresh",
        "",
        f"- candidate_id: `{_markdown_cell(str(candidate.get('candidate_id') or ''))}`",
        f"- target_ref: `{_markdown_cell(str(candidate.get('target_ref') or ''))}`",
        f"- signal_ids: `{_markdown_cell(', '.join(_string_values(candidate.get('signal_ids'))) or 'none')}`",
        f"- trace_ids: `{_markdown_cell(', '.join(_string_values(candidate.get('trace_ids'))) or 'none')}`",
        f"- source_ids: `{_markdown_cell(', '.join(_string_values(candidate.get('source_ids'))) or 'none')}`",
        f"- concept_slugs: `{_markdown_cell(', '.join(_string_values(candidate.get('concept_slugs'))) or 'none')}`",
        "",
        "This marker records a scoped judge refresh opportunity. It does not rewrite the judgment conclusion.",
        _ALCHEMY_JUDGE_REFRESH_END,
        "",
    ]
    return "\n".join(lines)


def _materialize_alchemy_judge_proposal(
    root: Path,
    *,
    preview: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    target_ref = str(candidate.get("target_ref") or "")
    candidate_id = str(candidate.get("candidate_id") or "")
    proposal_id = slugify(f"alchemy-judge-proposal-{candidate_id or target_ref or 'candidate'}")
    proposal_path = root / "output" / "_proposals" / "judge" / f"{proposal_id}.md"
    target = (root / target_ref).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return {
            "status": "skipped",
            "candidate_id": candidate_id,
            "target_ref": target_ref,
            "proposal_id": proposal_id,
            "reason": "target_outside_root",
        }
    if not target.exists():
        return {
            "status": "skipped",
            "candidate_id": candidate_id,
            "target_ref": target_ref,
            "proposal_id": proposal_id,
            "reason": "target_missing",
        }
    original = target.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(original)
    kind = str(frontmatter.get("kind") or "")
    if kind not in {"decision", "judgment"}:
        return {
            "status": "skipped",
            "candidate_id": candidate_id,
            "target_ref": target_ref,
            "proposal_id": proposal_id,
            "reason": "not_judgment_asset",
        }
    before_hash = sha256_bytes(original.encode("utf-8"))
    if proposal_path.exists():
        return {
            "status": "skipped",
            "candidate_id": candidate_id,
            "target_ref": target_ref,
            "path": relative_path(root, proposal_path),
            "proposal_id": proposal_id,
            "before_hash": before_hash,
            "reason": "already_exists",
        }
    proposal = _render_alchemy_judge_proposal_page(
        root,
        preview=preview,
        candidate=candidate,
        target_ref=target_ref,
        proposal_id=proposal_id,
        target_kind=kind,
        before_hash=before_hash,
    )
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_path.write_text(proposal, encoding="utf-8")
    return {
        "status": "generated",
        "candidate_id": candidate_id,
        "target_ref": target_ref,
        "path": relative_path(root, proposal_path),
        "proposal_id": proposal_id,
        "kind": kind,
        "before_hash": before_hash,
        "changed": True,
        "llm_invoked": False,
        "semantic_content_generated": False,
    }


def _render_alchemy_judge_proposal_page(
    root: Path,
    *,
    preview: dict[str, Any],
    candidate: dict[str, Any],
    target_ref: str,
    proposal_id: str,
    target_kind: str,
    before_hash: str,
) -> str:
    trace_ids = _string_values(candidate.get("trace_ids"))
    signal_ids = _string_values(candidate.get("signal_ids"))
    frontmatter = {
        "kind": "alchemy-judge-proposal",
        "proposal_id": proposal_id,
        "state": "candidate",
        "target_file": target_ref,
        "target_kind": target_kind,
        "before_hash": before_hash,
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "created_at": utc_now(),
        "llm_invoked": "false",
        "semantic_content_generated": "false",
        "human_accept_required": "true",
    }
    lines = [
        render_frontmatter(frontmatter),
        "",
        f"# Judge Proposal: {proposal_id}",
        "",
        _ALCHEMY_JUDGE_PROPOSAL_START,
        "## Target",
        "",
        f"- target_file: `{_markdown_cell(target_ref)}`",
        f"- target_kind: `{_markdown_cell(target_kind)}`",
        f"- before_hash: `{_markdown_cell(before_hash)}`",
        "",
        "## Provenance",
        "",
        f"- candidate_id: `{_markdown_cell(str(candidate.get('candidate_id') or ''))}`",
        f"- signal_ids: `{_markdown_cell(', '.join(signal_ids) or 'none')}`",
        f"- trace_ids: `{_markdown_cell(', '.join(trace_ids) or 'none')}`",
        f"- source_ids: `{_markdown_cell(', '.join(_string_values(candidate.get('source_ids'))) or 'none')}`",
        f"- concept_slugs: `{_markdown_cell(', '.join(_string_values(candidate.get('concept_slugs'))) or 'none')}`",
        f"- scope: `{_markdown_cell(str(preview.get('scope') or ''))}`",
        "",
        "## Semantic Refresh Contract",
        "",
        "- llm_invoked: `false`",
        "- semantic_content_generated: `false`",
        "- human_accept_required: `true`",
        "- target_page_mutation: `false`",
        "- next_step: `fill this proposal through an explicit human/model contract, then apply in a separate accepted-proposal milestone`",
        "",
        "## Proposed Change Preview",
        "",
        "No judgment conclusion has been generated in this baseline. This artifact reserves a reviewable proposal slot and records the exact target hash that a future accepted semantic refresh must validate before applying.",
        "",
        "## Candidate Prompt Package",
        "",
        "```text",
        "Review the target judgment or decision page against the scoped evidence.",
        "Return a proposed semantic refresh as a separate proposal diff.",
        "Do not apply changes directly to the target page.",
        f"Target: {target_ref}",
        f"Before hash: {before_hash}",
        f"Signals: {', '.join(signal_ids) or 'none'}",
        f"Traces: {', '.join(trace_ids) or 'none'}",
        "```",
        _ALCHEMY_JUDGE_PROPOSAL_END,
        "",
    ]
    return "\n".join(lines)


def _replace_marker_section(existing: str, section: str, *, start_marker: str, end_marker: str) -> str:
    if start_marker in existing and end_marker in existing:
        before, rest = existing.split(start_marker, 1)
        _, after = rest.split(end_marker, 1)
        return before.rstrip() + "\n\n" + section + after.lstrip()
    if existing.strip():
        return existing.rstrip() + "\n\n" + section
    return section


def _extract_marker_section(existing: str, *, start_marker: str, end_marker: str) -> str:
    if start_marker not in existing or end_marker not in existing:
        return ""
    _, rest = existing.split(start_marker, 1)
    body, _ = rest.split(end_marker, 1)
    return body.strip()


def _render_alchemy_judge_accepted_target_section(*, proposal_id: str, proposal_path: str, accepted_body: str) -> str:
    lines = [
        _ALCHEMY_JUDGE_ACCEPTED_TARGET_START,
        "## Accepted Judge Refresh",
        "",
        f"- proposal_id: `{_markdown_cell(proposal_id)}`",
        f"- proposal_path: `{_markdown_cell(proposal_path)}`",
        "",
        accepted_body.strip(),
        _ALCHEMY_JUDGE_ACCEPTED_TARGET_END,
        "",
    ]
    return "\n".join(lines)


def _materialize_alchemy_review_queue(
    root: Path,
    *,
    preview: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    path = root / "wiki" / "indexes" / "review-queue.md"
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    before_hash = sha256_bytes(before.encode("utf-8")) if path.exists() else ""
    section = _render_alchemy_review_queue_section(preview=preview, candidates=candidates)
    after = _replace_managed_section(before, section)
    changed = after != before
    path.parent.mkdir(parents=True, exist_ok=True)
    if changed or not path.exists():
        path.write_text(after, encoding="utf-8")
    after_hash = sha256_bytes(after.encode("utf-8"))
    return {
        "path": relative_path(root, path),
        "before_hash": before_hash,
        "after_hash": after_hash,
        "changed": changed,
        "candidate_count": len(candidates),
    }


def _render_alchemy_review_queue_section(*, preview: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    scope = str(preview.get("scope") or "")
    trace_ids = _preview_trace_ids(preview)
    lines = [
        _ALCHEMY_REVIEW_QUEUE_START,
        "## Alchemy scoped review enqueue",
        "",
        f"- scope: `{_markdown_cell(scope)}`",
        f"- candidate_count: `{len(candidates)}`",
        f"- trace_ids: `{', '.join(trace_ids)}`",
        "",
        "| Candidate | Kind | Protocol | Target | Signals |",
        "| --- | --- | --- | --- | --- |",
    ]
    for candidate in candidates:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(str(candidate.get("candidate_id") or "")),
                    _markdown_cell(str(candidate.get("kind") or "")),
                    _markdown_cell(str(candidate.get("protocol") or "")),
                    _markdown_cell(str(candidate.get("target_ref") or "")),
                    _markdown_cell(", ".join(_string_values(candidate.get("signal_ids")))),
                ]
            )
            + " |"
        )
    lines.extend(["", _ALCHEMY_REVIEW_QUEUE_END, ""])
    return "\n".join(lines)


def _replace_managed_section(existing: str, section: str) -> str:
    if _ALCHEMY_REVIEW_QUEUE_START in existing and _ALCHEMY_REVIEW_QUEUE_END in existing:
        before, rest = existing.split(_ALCHEMY_REVIEW_QUEUE_START, 1)
        _, after = rest.split(_ALCHEMY_REVIEW_QUEUE_END, 1)
        return before.rstrip() + "\n\n" + section + after.lstrip()
    if existing.strip():
        return existing.rstrip() + "\n\n" + section
    return "# Review Queue\n\n" + section


def _review_preview_receipt_summary(preview: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": str(preview.get("status") or ""),
        "scope": str(preview.get("scope") or ""),
        "selected_count": int(preview.get("selected_count") or 0),
        "candidate_count": len(candidates),
        "candidate_ids": [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")],
        "scope_preview": preview.get("scope_preview") if isinstance(preview.get("scope_preview"), dict) else {},
        "apply_contract": preview.get("apply_contract") if isinstance(preview.get("apply_contract"), dict) else {},
    }


def _propose_preview_receipt_summary(preview: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": str(preview.get("status") or ""),
        "scope": str(preview.get("scope") or ""),
        "selected_count": int(preview.get("selected_count") or 0),
        "candidate_count": len(candidates),
        "candidate_ids": [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")],
        "scope_preview": preview.get("scope_preview") if isinstance(preview.get("scope_preview"), dict) else {},
        "apply_contract": preview.get("apply_contract") if isinstance(preview.get("apply_contract"), dict) else {},
        "human_accept_required_after_apply": True,
    }


def _distill_preview_receipt_summary(preview: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": str(preview.get("status") or ""),
        "scope": str(preview.get("scope") or ""),
        "selected_count": int(preview.get("selected_count") or 0),
        "candidate_count": len(candidates),
        "candidate_ids": [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")],
        "scope_preview": preview.get("scope_preview") if isinstance(preview.get("scope_preview"), dict) else {},
        "apply_contract": preview.get("apply_contract") if isinstance(preview.get("apply_contract"), dict) else {},
        "direct_apply_only": False,
        "lane_apply_supported": True,
    }


def _judge_preview_receipt_summary(preview: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": str(preview.get("status") or ""),
        "scope": str(preview.get("scope") or ""),
        "selected_count": int(preview.get("selected_count") or 0),
        "candidate_count": len(candidates),
        "candidate_ids": [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")],
        "scope_preview": preview.get("scope_preview") if isinstance(preview.get("scope_preview"), dict) else {},
        "apply_contract": preview.get("apply_contract") if isinstance(preview.get("apply_contract"), dict) else {},
        "semantic_rewrite": False,
        "lane_apply_supported": False,
    }


def _preview_trace_ids(preview: dict[str, Any]) -> list[str]:
    scope_preview = preview.get("scope_preview")
    if not isinstance(scope_preview, dict):
        return []
    return _string_values(scope_preview.get("trace_ids"))


def _first_preview_protocol(preview: dict[str, Any]) -> str:
    scope_preview = preview.get("scope_preview")
    if isinstance(scope_preview, dict):
        protocols = _string_values(scope_preview.get("protocols"))
        if protocols:
            return protocols[0]
    candidates = preview.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("protocol"):
                return str(candidate.get("protocol") or "")
    return ""


def _alchemy_review_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    payload = {
        "primitive": "review",
        "scope": scope,
        "candidate_ids": sorted(candidate_ids),
        "trace_ids": sorted(trace_ids),
    }
    digest = sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return f"alchemy-review:{digest}"


def _alchemy_propose_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    payload = {
        "primitive": "propose",
        "scope": scope,
        "candidate_ids": sorted(candidate_ids),
        "trace_ids": sorted(trace_ids),
    }
    digest = sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return f"alchemy-propose:{digest}"


def _alchemy_distill_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    payload = {
        "primitive": "distill",
        "scope": scope,
        "candidate_ids": sorted(candidate_ids),
        "question_template": "scoped_elixir_candidate_refresh",
        "trace_ids": sorted(trace_ids),
    }
    digest = sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return f"alchemy-distill:{digest}"


def _alchemy_judge_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    payload = {
        "primitive": "judge",
        "scope": scope,
        "candidate_ids": sorted(candidate_ids),
        "marker": "scoped_judge_refresh_marker",
        "trace_ids": sorted(trace_ids),
    }
    digest = sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return f"alchemy-judge:{digest}"


def _alchemy_judge_proposal_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    payload = {
        "primitive": "judge",
        "mode": "proposal_preview",
        "scope": scope,
        "candidate_ids": sorted(candidate_ids),
        "trace_ids": sorted(trace_ids),
    }
    digest = sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return f"alchemy-judge-proposal:{digest}"


def _resolve_alchemy_judge_proposal_path(root: Path, proposal: str | Path) -> Path:
    raw = str(proposal).strip().strip("'\"`")
    if not raw:
        raise ValueError("judge proposal path or id is required.")
    candidate = Path(raw)
    if not candidate.suffix and "/" not in raw and "\\" not in raw:
        candidate = Path("output") / "_proposals" / "judge" / f"{slugify(raw)}.md"
    resolved = candidate if candidate.is_absolute() else root / candidate
    resolved = resolved.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("judge proposal path must stay within the workspace.") from exc
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"judge proposal not found: {proposal}")
    return resolved


def _alchemy_distill_target_id(target_ref: str) -> str:
    normalized = target_ref.strip()
    if not normalized:
        return ""
    return Path(normalized).stem


def _alchemy_distill_question(candidate: dict[str, Any]) -> str:
    candidate_id = str(candidate.get("candidate_id") or "distill")
    target_ref = str(candidate.get("target_ref") or "")
    signal_ids = ",".join(_string_values(candidate.get("signal_ids"))) or "none"
    return f"Alchemy scoped distill refresh for {candidate_id} ({target_ref}); signals={signal_ids}"


def _alchemy_distill_history_questions(path: Path) -> set[str]:
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    raw = frontmatter.get("distill_history_json")
    if not isinstance(raw, str) or not raw.strip():
        return set()
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(decoded, list):
        return set()
    questions: set[str] = set()
    for item in decoded:
        if isinstance(item, dict) and isinstance(item.get("question"), str):
            questions.add(str(item["question"]))
    return questions


def _alchemy_propose_prompt_content(root: Path, *, target_file: str, candidate: dict[str, Any], scope: str) -> str:
    target = root / target_file
    current = target.read_text(encoding="utf-8", errors="replace")
    signal_ids = ", ".join(_string_values(candidate.get("signal_ids"))) or "none"
    candidate_id = str(candidate.get("candidate_id") or "")
    target_ref = str(candidate.get("target_ref") or "")
    block = "\n".join(
        [
            "",
            "<!-- aiwiki:alchemy-propose:start -->",
            f"<!-- scope: {scope} -->",
            f"<!-- candidate_id: {candidate_id} -->",
            f"<!-- target_ref: {target_ref} -->",
            f"<!-- signal_ids: {signal_ids} -->",
            "<!-- Manual review is required before accepting this proposal. -->",
            "<!-- aiwiki:alchemy-propose:end -->",
        ]
    )
    return current.rstrip() + block + "\n"


def _unique_alchemy_propose_action_id(root: Path, *, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-propose-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _unique_alchemy_distill_action_id(root: Path, *, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-distill-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _unique_alchemy_judge_action_id(root: Path, *, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-judge-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _unique_alchemy_judge_proposal_action_id(root: Path, *, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-judge-proposal-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _unique_alchemy_judge_proposal_apply_action_id(root: Path, *, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-judge-proposal-apply-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _unique_alchemy_review_action_id(root: Path, *, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-review-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate



def _string_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item.strip() for item in value if isinstance(item, str) and item.strip()})


def _markdown_cell(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|")
