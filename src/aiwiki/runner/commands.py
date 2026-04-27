"""Thin command façades for L3 proposals, audit, planner rollback, candidates, protocol learn, signals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiwiki.app_utils import runtime_write_operation


def run_l3_proposal_create(
    root: Path,
    *,
    kind: str,
    target_file: str,
    content: str,
    proposal_id: str | None = None,
    rationale: str = "",
    evidence_refs: list[str] | None = None,
    signal_ids: list[str] | None = None,
    pattern: str = "manual_fixture",
) -> dict[str, Any]:
    from aiwiki.execution.l3_proposals import create_l3_proposal

    return create_l3_proposal(
        root,
        kind=kind,
        target_file=target_file,
        content=content,
        proposal_id=proposal_id,
        rationale=rationale,
        evidence_refs=evidence_refs,
        signal_ids=signal_ids,
        pattern=pattern,
    )


def run_l3_proposal_list(root: Path, *, kind: str | None = None, state: str | None = None) -> list[dict[str, Any]]:
    from aiwiki.execution.l3_proposals import list_l3_proposals

    return list_l3_proposals(root, kind=kind, state=state)


def run_l3_proposal_generation_preview(
    root: Path,
    *,
    planner_log_path: Path | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    from aiwiki.execution.l3_proposals import preview_l3_proposal_generation

    return preview_l3_proposal_generation(root, planner_log_path=planner_log_path, limit=limit)


def run_l3_proposal_generate(
    root: Path,
    *,
    planner_log_path: Path | None = None,
    limit: int = 20,
    apply: bool = False,
) -> dict[str, Any]:
    if not apply:
        return run_l3_proposal_generation_preview(root, planner_log_path=planner_log_path, limit=limit)
    from aiwiki.execution.l3_proposals import generate_l3_proposals_from_planner

    return generate_l3_proposals_from_planner(root, planner_log_path=planner_log_path, limit=limit)


def run_l3_proposal_apply(root: Path, proposal_id: str, *, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.l3_proposals import apply_l3_proposal

    return apply_l3_proposal(root, proposal_id, note=note)


def run_l3_proposal_reject(root: Path, proposal_id: str, *, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.l3_proposals import reject_l3_proposal

    return reject_l3_proposal(root, proposal_id, note=note)


def run_l3_proposal_revert(root: Path, receipt_id: str, *, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.l3_proposals import revert_l3_proposal

    return revert_l3_proposal(root, receipt_id, note=note)


def run_audit_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from aiwiki.execution.audit_preview import preview_universal_audit_stream

    return preview_universal_audit_stream(root, limit=limit)


def run_audit_backfill(root: Path, *, limit: int = 50, apply: bool = False) -> dict[str, Any]:
    from aiwiki.execution.audit_preview import backfill_universal_audit_stream

    return backfill_universal_audit_stream(root, limit=limit, apply=apply)


def run_planner_log_rollback_preview(
    root: Path,
    *,
    signal_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    from aiwiki.planner.rollback import preview_planner_log_rollback

    return preview_planner_log_rollback(root, signal_id=signal_id, trace_id=trace_id, limit=limit)


def run_planner_log_rollback(
    root: Path,
    *,
    signal_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 20,
    apply: bool = False,
) -> dict[str, Any]:
    from aiwiki.planner.rollback import apply_planner_log_rollback_marker

    return apply_planner_log_rollback_marker(root, signal_id=signal_id, trace_id=trace_id, limit=limit, apply=apply)


@runtime_write_operation
def run_promote(root: Path, artifact_ref: str) -> dict[str, Any]:
    from aiwiki.execution.candidates import promote_candidate

    return promote_candidate(root, artifact_ref)


@runtime_write_operation
def run_demote(root: Path, artifact_ref: str) -> dict[str, Any]:
    from aiwiki.execution.candidates import demote_candidate

    return demote_candidate(root, artifact_ref)


@runtime_write_operation
def run_protocol_learn_add(root: Path, protocol: str, title: str, source_refs: list[str] | None) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import add_learning

    return add_learning(root, protocol, title=title, source_refs=source_refs)


def run_protocol_learn_list(
    root: Path,
    protocol: str | None = None,
    *,
    state_filter: str | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    from aiwiki.execution.protocol_learnings import list_learnings

    return list_learnings(root, protocol, state_filter=state_filter, include_archived=include_archived)


def run_protocol_learn_show(root: Path, learning_id: str) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import show_learning

    return show_learning(root, learning_id)


def run_signals_list(
    root: Path,
    *,
    kind: str | None = None,
    trace_id: str | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from aiwiki.inspection import read_signals

    return read_signals(
        root,
        kind=kind,
        trace_id=trace_id,
        since=since,
        limit=limit,
    )


def run_signals_show(root: Path, signal_id: str) -> dict[str, Any]:
    from aiwiki.inspection import find_planner_decisions_for_signal, find_signal_by_id

    signal = find_signal_by_id(root, signal_id)
    if signal is None:
        return {"status": "not_found", "signal_id": signal_id}
    decisions = find_planner_decisions_for_signal(root, signal_id)
    return {
        "status": "ok",
        "signal": signal,
        "planner_decisions": decisions,
    }


def run_planner_log_list(
    root: Path,
    *,
    decision: str | None = None,
    signal_id: str | None = None,
    trace_id: str | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from aiwiki.inspection import read_planner_decisions

    return read_planner_decisions(
        root,
        decision=decision,
        signal_id=signal_id,
        trace_id=trace_id,
        since=since,
        limit=limit,
    )


@runtime_write_operation
def run_protocol_learn_age(root: Path, protocol: str | None = None, apply: bool = False) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import age_learnings

    return age_learnings(root, protocol=protocol, apply=apply)


@runtime_write_operation
def run_protocol_learn_verify(root: Path, learning_id: str) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import verify_learning

    return verify_learning(root, learning_id)


@runtime_write_operation
def run_protocol_learn_revert_activate(root: Path, learning_id: str, *, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import revert_learning_activation

    return revert_learning_activation(root, learning_id, note=note)


@runtime_write_operation
def run_protocol_learn_demote(root: Path, learning_id: str) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import demote_learning

    return demote_learning(root, learning_id)


@runtime_write_operation
def run_protocol_learn_archive(root: Path, learning_id: str) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import archive_learning

    return archive_learning(root, learning_id)


@runtime_write_operation
def run_protocol_learn_supersede(root: Path, replacement_id: str, superseded_ids: list[str]) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import supersede_learning

    return supersede_learning(root, replacement_id, superseded_ids)
