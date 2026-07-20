"""Alchemy runner — orchestration layer.

Owns: command entry points (`run_alchemy_*`), workflow sequencing, receipted
lane primitives, telemetry. Calls into ``aiwiki.execution.alchemy`` for the
actual filesystem mutations (write/replace/unlink).

Boundary: orchestration only. Mutations live in ``execution/alchemy.py``.
Transactional helpers (``_snapshot_file_bytes`` / ``_restore_file_bytes``) live
in ``aiwiki.utils.io`` and are imported by both layers.

Follow-up (SC-003b, not in this milestone): some apply/revert paths still
perform filesystem mutations directly from the runner; future work should
migrate those into ``execution/`` to fully respect the boundary.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from aiwiki.app_linting.core import lint_wiki
from aiwiki.compile.pipeline import compile_wiki
from aiwiki.execution import machine_memory_batch as _machine_memory_batch
from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH
from aiwiki.execution.history import append_execution_receipt_history, append_runtime_history
from aiwiki.execution.paths import execution_receipt_history_path
from aiwiki.execution.receipts import compute_file_sha256
from aiwiki.execution.runtime_surfaces import nightly_health
from aiwiki.protocol.scaffold import ensure_layout
from aiwiki.render.paths import execution_receipt_path
from aiwiki.runner import alchemy_distill as _alchemy_distill
from aiwiki.runner import alchemy_judge as _alchemy_judge
from aiwiki.runner import alchemy_lanes as _alchemy_lanes
from aiwiki.runner import alchemy_materialize as _alchemy_materialize
from aiwiki.runner import alchemy_propose as _alchemy_propose
from aiwiki.runner import alchemy_review as _alchemy_review
from aiwiki.runner import alchemy_support as _alchemy_support
from aiwiki.runner.alchemy_errors import (
    AlchemyDistillApplyError,
    AlchemyDistillApplyHalfWriteError,
    AlchemyJudgeProposalApplyError,
    AlchemyJudgeProposalApplyHalfWriteError,
    AlchemyLanePrimitiveReceiptError,
    AlchemyLanePrimitiveReceiptHalfWriteError,
    AlchemyProposeApplyReceiptError,
    AlchemyProposeApplyReceiptHalfWriteError,
    AlchemyReviewApplyError,
    AlchemyReviewApplyHalfWriteError,
)
from aiwiki.utils.hash import sha256_bytes
from aiwiki.utils.io import (
    _durable_truncate,
    _restore_file_bytes,
    _snapshot_file_bytes,
    atomic_write_text,
    runtime_write_lock,
    runtime_write_operation,
)
from aiwiki.utils.markdown import parse_frontmatter, render_frontmatter, strip_frontmatter
from aiwiki.utils.path import relative_path
from aiwiki.utils.text import slugify
from aiwiki.utils.time import utc_now

_ALCHEMY_JUDGE_REFRESH_START = _alchemy_support.ALCHEMY_JUDGE_REFRESH_START
_ALCHEMY_JUDGE_REFRESH_END = _alchemy_support.ALCHEMY_JUDGE_REFRESH_END
_ALCHEMY_JUDGE_ACCEPTED_REFRESH_START = _alchemy_support.ALCHEMY_JUDGE_ACCEPTED_REFRESH_START
_ALCHEMY_JUDGE_ACCEPTED_REFRESH_END = _alchemy_support.ALCHEMY_JUDGE_ACCEPTED_REFRESH_END
_ALCHEMY_JUDGE_ACCEPTED_TARGET_START = _alchemy_support.ALCHEMY_JUDGE_ACCEPTED_TARGET_START
_ALCHEMY_JUDGE_ACCEPTED_TARGET_END = _alchemy_support.ALCHEMY_JUDGE_ACCEPTED_TARGET_END
_extract_marker_section = _alchemy_support.extract_marker_section
_first_preview_protocol = _alchemy_support.first_preview_protocol
_preview_trace_ids = _alchemy_support.preview_trace_ids
_normalize_preview_lock_status = _alchemy_support.normalize_preview_lock_status
_walk_preview_lock_status = _alchemy_support.walk_preview_lock_status
_apply_preview_candidates = _alchemy_support.apply_preview_candidates
_replace_marker_section = _alchemy_support.replace_marker_section
_replace_managed_section = _alchemy_support.replace_review_queue_section
_string_values = _alchemy_support.string_values
_render_alchemy_judge_accepted_target_section = _alchemy_support.render_alchemy_judge_accepted_target_section
_render_alchemy_judge_proposal_page = _alchemy_support.render_alchemy_judge_proposal_page
_render_alchemy_judge_refresh_section = _alchemy_support.render_alchemy_judge_refresh_section
_render_alchemy_review_queue_section = _alchemy_support.render_alchemy_review_queue_section
_review_preview_receipt_summary = _alchemy_support.review_preview_receipt_summary
_propose_preview_receipt_summary = _alchemy_support.propose_preview_receipt_summary
_distill_preview_receipt_summary = _alchemy_support.distill_preview_receipt_summary
_judge_preview_receipt_summary = _alchemy_support.judge_preview_receipt_summary
_alchemy_review_idempotency_key = _alchemy_support.alchemy_review_idempotency_key
_alchemy_propose_idempotency_key = _alchemy_support.alchemy_propose_idempotency_key
_alchemy_distill_idempotency_key = _alchemy_support.alchemy_distill_idempotency_key
_alchemy_judge_idempotency_key = _alchemy_support.alchemy_judge_idempotency_key
_alchemy_judge_proposal_idempotency_key = _alchemy_support.alchemy_judge_proposal_idempotency_key
_alchemy_distill_target_id = _alchemy_support.alchemy_distill_target_id
_alchemy_distill_question = _alchemy_support.alchemy_distill_question
_alchemy_distill_history_questions = _alchemy_support.alchemy_distill_history_questions
_alchemy_propose_prompt_content = _alchemy_support.alchemy_propose_prompt_content
_unique_alchemy_propose_action_id = _alchemy_support.unique_alchemy_propose_action_id
_unique_alchemy_distill_action_id = _alchemy_support.unique_alchemy_distill_action_id
_unique_alchemy_judge_action_id = _alchemy_support.unique_alchemy_judge_action_id
_unique_alchemy_judge_proposal_action_id = _alchemy_support.unique_alchemy_judge_proposal_action_id
_unique_alchemy_judge_proposal_apply_action_id = _alchemy_support.unique_alchemy_judge_proposal_apply_action_id
_unique_alchemy_review_action_id = _alchemy_support.unique_alchemy_review_action_id
_first_plan_protocol = _alchemy_support.first_plan_protocol
_lane_primitive_plan_step = _alchemy_support.lane_primitive_plan_step
_lane_receipt_plan_summary = _alchemy_support.lane_receipt_plan_summary
_lane_receipt_result_summary = _alchemy_support.lane_receipt_result_summary
_lane_receipt_trace_ids = _alchemy_support.lane_receipt_trace_ids
_lane_primitive_scope = _alchemy_support.lane_primitive_scope
_lane_primitive_receipt_payload = _alchemy_support.lane_primitive_receipt_payload
_alchemy_auto_runtime_event_payload = _alchemy_support.alchemy_auto_runtime_event_payload
_alchemy_lane_runtime_event_payload = _alchemy_support.alchemy_lane_runtime_event_payload
_normalize_auto_lanes = _alchemy_support.normalize_auto_lanes
_normalize_lane_primitives = _alchemy_support.normalize_lane_primitives
_auto_primitives_for_lane = _alchemy_support.auto_primitives_for_lane
_auto_skip_reason = _alchemy_support.auto_skip_reason
_primary_result_path = _alchemy_support.primary_result_path
_unique_lane_primitive_action_id = _alchemy_support.unique_lane_primitive_action_id
_materialize_alchemy_judge_refresh = _alchemy_materialize.materialize_alchemy_judge_refresh
_materialize_alchemy_judge_proposal = _alchemy_materialize.materialize_alchemy_judge_proposal
_materialize_alchemy_review_queue = _alchemy_materialize.materialize_alchemy_review_queue
_resolve_alchemy_judge_proposal_path = _alchemy_materialize.resolve_alchemy_judge_proposal_path

logger = logging.getLogger(__name__)


_PLANNER_LOG_REL_PATH = ".aiwiki/state/planner-log.jsonl"
_ALCHEMY_PROPOSE_COLD_START_ERROR = (
    "planner-log not initialized: alchemy propose --apply requires execute-mode planner decisions. "
    "Run `aiwiki nightly` or `aiwiki auto-once` first to populate planner-log.jsonl, "
    "or use `aiwiki l3-proposal-create` for manual fixtures."
)


def _resolve_alchemy_planner_log_path(root: Path, planner_log_path: Path | None) -> Path:
    if planner_log_path is None:
        return root / _PLANNER_LOG_REL_PATH
    if planner_log_path.is_absolute():
        return planner_log_path
    return root / planner_log_path


def run_alchemy_legacy_migration_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from aiwiki.execution.alchemy_migration import preview_legacy_elixir_migration

    return preview_legacy_elixir_migration(root, limit=limit)


@runtime_write_operation
def run_alchemy_legacy_migration_apply(root: Path, *, limit: int = 50, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy_migration import apply_legacy_elixir_migration

    return apply_legacy_elixir_migration(root, limit=limit, note=note)


def run_alchemy_superseded_cleanup_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from aiwiki.execution.alchemy_cleanup import preview_superseded_elixir_cleanup

    return preview_superseded_elixir_cleanup(root, limit=limit)


@runtime_write_operation
def run_alchemy_superseded_cleanup_apply(root: Path, *, limit: int = 50, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy_cleanup import apply_superseded_elixir_cleanup

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


_DISTILL_SYNTHESIS_SYSTEM_PROMPT = (
    "你是炼丹炉 (aiwiki) 的金丹提炼器。给定一个提炼问题和若干来源材料，"
    "综合出一份结构化、简洁的金丹正文 (markdown)，包含 ## Thesis / ## Evidence / ## Open Questions 三节。"
    "只依据来源材料下判断，保留来源引用；不要编造材料中没有的事实。只输出 markdown 正文，不要额外说明。"
)
_DISTILL_SOURCE_CHAR_BUDGET = 12000


def _llm_distill_enabled() -> bool:
    import os

    return os.environ.get("AIWIKI_LLM_DISTILL", "1").strip().lower() not in {"0", "false", "no", "off"}


def _llm_distill_synthesizer(root: Path):
    """Return an LLM-backed body synthesizer, or None when disabled.

    The returned callable takes (question, source_refs) and returns a
    synthesized elixir body, or None on any failure so the mutation layer
    falls back to the deterministic seed. LLM lives in this orchestration
    layer; the mutation layer stays deterministic given the injected body.
    """
    if not _llm_distill_enabled():
        return None

    def _synthesize(question: str, source_refs: list[str]) -> str | None:
        from aiwiki.llm import LLMError
        from aiwiki.utils.markdown import strip_frontmatter

        source_texts: list[str] = []
        budget = _DISTILL_SOURCE_CHAR_BUDGET
        for ref in source_refs:
            path = root / ref
            if not path.is_file():
                continue
            try:
                text = strip_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            chunk = text[:budget]
            source_texts.append(f"## Source: {ref}\n\n{chunk}")
            budget -= len(chunk)
            if budget <= 0:
                break
        if not source_texts:
            return None
        try:
            from aiwiki.runner.clients import create_client

            client = create_client(root)
        except Exception as exc:  # noqa: BLE001 - any client failure -> deterministic fallback
            logging.getLogger("aiwiki").info("distill LLM synthesis unavailable, using deterministic seed: %s", exc)
            return None
        user_prompt = "提炼问题: {q}\n\n来源材料:\n{s}\n\n输出金丹正文 (markdown):".format(
            q=question, s="\n\n".join(source_texts)
        )
        try:
            result = client.complete(_DISTILL_SYNTHESIS_SYSTEM_PROMPT, user_prompt)
        except LLMError as exc:
            logging.getLogger("aiwiki").info("distill LLM synthesis failed, using deterministic seed: %s", exc)
            return None
        body = (result.text or "").strip()
        return body or None

    return _synthesize


def _distill_source_refs_for_synthesis(root: Path, elixir_id: str) -> list[str]:
    """Read-only peek of candidate derived_from for LLM synthesis outside the write lock."""
    from aiwiki.execution.alchemy_helpers import _candidate_path, _parse_elixir_frontmatter, _resolve_elixir_id

    try:
        normalized_id = _resolve_elixir_id(root, elixir_id)
        candidate = _candidate_path(root, normalized_id)
        if not candidate.is_file():
            return []
        frontmatter = _parse_elixir_frontmatter(candidate)
    except Exception:  # noqa: BLE001 - synthesis peek is best-effort
        return []
    return [str(item) for item in frontmatter.get("derived_from", []) if isinstance(item, str)]


def run_alchemy_distill(
    root: Path, elixir_id: str, question: str, include_elixir_ids: list[str] | None = None
) -> dict[str, Any]:
    """Distill with LLM synthesis outside the single-writer lock.

    Network LLM calls must not hold `runtime_write_lock`. Mutation stays locked;
    synthesizer output is injected as a precomputed body.
    """
    from aiwiki.execution.alchemy import distill_elixir
    from aiwiki.utils.io import runtime_write_lock

    precomputed_body: str | None = None
    llm_invoked = False
    generation_mode = "deterministic_seed"
    synth = _llm_distill_synthesizer(root)
    if synth is not None:
        source_refs = _distill_source_refs_for_synthesis(root, elixir_id)
        if include_elixir_ids:
            # include refs are elixir ids; synthesizer only needs wiki paths —
            # peek list is enough for primary sources already on the candidate.
            pass
        body = synth(question, source_refs) if source_refs else None
        if body and str(body).strip():
            precomputed_body = str(body).strip()
            llm_invoked = True
            generation_mode = "llm"

    def _fixed_body(_question: str, _source_refs: list[str]) -> str | None:
        return precomputed_body

    with runtime_write_lock(root):
        result = distill_elixir(
            root,
            elixir_id,
            question=question,
            include_elixir_ids=include_elixir_ids,
            body_synthesizer=_fixed_body if precomputed_body else None,
        )
    result["llm_invoked"] = llm_invoked
    result["generation_mode"] = generation_mode
    result["semantic_content_generated_by_runtime"] = llm_invoked
    return result


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
    allow_current_writer_lock: bool = False,
) -> dict[str, Any]:
    return _alchemy_judge.run_judge_preview(
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


@runtime_write_operation
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
    return _alchemy_judge.run_judge_apply(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
        note=note,
        preview_runner=run_alchemy_judge_preview,
    )


@runtime_write_operation
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
    return _alchemy_judge.run_judge_propose(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
        note=note,
        preview_runner=run_alchemy_judge_preview,
    )


@runtime_write_operation
def run_alchemy_judge_proposal_apply(
    root: Path,
    proposal: str | Path,
    *,
    note: str | None = None,
) -> dict[str, Any]:
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
    target_snapshot = _snapshot_file_bytes(target)
    proposal_snapshot = _snapshot_file_bytes(proposal_path)

    applied_at = utc_now()
    action_id = _unique_alchemy_judge_proposal_apply_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    updated_target = f"{render_frontmatter(target_frontmatter)}\n\n{updated_body.strip()}\n"
    changed = updated_target != original_target
    after_hash = sha256_bytes(updated_target.encode("utf-8"))

    proposal_frontmatter["state"] = "applied"
    proposal_frontmatter["applied_at"] = applied_at
    proposal_frontmatter["receipt_path"] = relative_path(root, receipt_path)
    proposal_body = strip_frontmatter(original_proposal).strip()
    updated_proposal = f"{render_frontmatter(proposal_frontmatter)}\n\n{proposal_body}\n"
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
    history_path = execution_receipt_history_path(root)
    history_size_before = history_path.stat().st_size if history_path.exists() else 0
    audit_jsonl_path = root / AUDIT_STREAM_PATH
    audit_size_before = audit_jsonl_path.stat().st_size if audit_jsonl_path.exists() else 0
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if changed:
            atomic_write_text(target, updated_target)
        atomic_write_text(proposal_path, updated_proposal)
        atomic_write_text(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        append_execution_receipt_history(root, receipt)
    except Exception as tx_exc:
        try:
            if history_path.exists():
                _durable_truncate(history_path, history_size_before)
            if audit_jsonl_path.exists():
                _durable_truncate(audit_jsonl_path, audit_size_before)
            if receipt_path.exists():
                receipt_path.unlink()
            _restore_file_bytes(proposal_path, proposal_snapshot)
            _restore_file_bytes(target, target_snapshot)
        except Exception as rollback_exc:
            raise AlchemyJudgeProposalApplyHalfWriteError(
                f"judge_proposal_apply rollback failed for {proposal_id}: tx_error={tx_exc}; "
                f"rollback_error={rollback_exc}"
            ) from rollback_exc
        raise AlchemyJudgeProposalApplyError(
            f"judge_proposal_apply failed for {proposal_id}; mutation rolled back"
        ) from tx_exc

    try:
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
    except Exception as exc:
        logger.warning("judge_proposal_apply runtime-history append failed for %s: %s", proposal_id, exc)
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
    allow_current_writer_lock: bool = False,
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
        allow_current_writer_lock=allow_current_writer_lock,
    )


@runtime_write_operation
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
    return _alchemy_distill.run_alchemy_distill_apply_impl(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
        note=note,
        deps={
            "preview_runner": run_alchemy_distill_preview,
            "apply_preview_candidates": _apply_preview_candidates,
            "ensure_layout": ensure_layout,
            "utc_now": utc_now,
            "unique_action_id": _unique_alchemy_distill_action_id,
            "execution_receipt_history_path": execution_receipt_history_path,
            "relative_path": relative_path,
            "preview_trace_ids": _preview_trace_ids,
            "idempotency_key": _alchemy_distill_idempotency_key,
            "first_preview_protocol": _first_preview_protocol,
            "distill_preview_receipt_summary": _distill_preview_receipt_summary,
            "target_id": _alchemy_distill_target_id,
            "question": _alchemy_distill_question,
            "history_questions": _alchemy_distill_history_questions,
            "snapshot_file_bytes": _snapshot_file_bytes,
            "compute_file_sha256": compute_file_sha256,
            "distill_runner": run_alchemy_distill,
            "atomic_write_text": atomic_write_text,
            "append_execution_receipt_history": append_execution_receipt_history,
            "append_runtime_history": append_runtime_history,
            "restore_file_bytes": _restore_file_bytes,
            "durable_truncate": _durable_truncate,
            "error_cls": AlchemyDistillApplyError,
            "half_write_error_cls": AlchemyDistillApplyHalfWriteError,
        },
    )


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
    allow_current_writer_lock: bool = False,
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
        allow_current_writer_lock=allow_current_writer_lock,
    )


@runtime_write_operation
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
    return _alchemy_review.run_alchemy_review_apply_impl(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
        note=note,
        deps={
            "preview_runner": run_alchemy_review_preview,
            "apply_preview_candidates": _apply_preview_candidates,
            "utc_now": utc_now,
            "unique_action_id": _unique_alchemy_review_action_id,
            "execution_receipt_history_path": execution_receipt_history_path,
            "relative_path": relative_path,
            "snapshot_file_bytes": _snapshot_file_bytes,
            "preview_trace_ids": _preview_trace_ids,
            "idempotency_key": _alchemy_review_idempotency_key,
            "materialize_review_queue": _materialize_alchemy_review_queue,
            "first_preview_protocol": _first_preview_protocol,
            "review_preview_receipt_summary": _review_preview_receipt_summary,
            "atomic_write_text": atomic_write_text,
            "append_execution_receipt_history": append_execution_receipt_history,
            "durable_truncate": _durable_truncate,
            "restore_file_bytes": _restore_file_bytes,
            "append_runtime_history": append_runtime_history,
            "error_cls": AlchemyReviewApplyError,
            "half_write_error_cls": AlchemyReviewApplyHalfWriteError,
            "logger": logger,
        },
    )


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
    allow_current_writer_lock: bool = False,
) -> dict[str, Any]:
    from aiwiki.planner import preview_propose_primitive

    resolved_planner_log_path = _resolve_alchemy_planner_log_path(root, planner_log_path)
    preview = preview_propose_primitive(
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
    preview["cold_start"] = not resolved_planner_log_path.exists()
    return preview


@runtime_write_operation
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
    return _alchemy_propose.run_alchemy_propose_apply_impl(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
        note=note,
        deps={
            "resolve_planner_log_path": _resolve_alchemy_planner_log_path,
            "cold_start_error": _ALCHEMY_PROPOSE_COLD_START_ERROR,
            "preview_runner": run_alchemy_propose_preview,
            "apply_preview_candidates": _apply_preview_candidates,
            "ensure_layout": ensure_layout,
            "slugify": slugify,
            "prompt_content": _alchemy_propose_prompt_content,
            "utc_now": utc_now,
            "unique_action_id": _unique_alchemy_propose_action_id,
            "execution_receipt_history_path": execution_receipt_history_path,
            "relative_path": relative_path,
            "preview_trace_ids": _preview_trace_ids,
            "idempotency_key": _alchemy_propose_idempotency_key,
            "first_preview_protocol": _first_preview_protocol,
            "propose_preview_receipt_summary": _propose_preview_receipt_summary,
            "atomic_write_text": atomic_write_text,
            "append_execution_receipt_history": append_execution_receipt_history,
            "append_runtime_history": append_runtime_history,
            "durable_truncate": _durable_truncate,
            "error_cls": AlchemyProposeApplyReceiptError,
            "half_write_error_cls": AlchemyProposeApplyReceiptHalfWriteError,
        },
    )


def run_alchemy_lane_dry_run(
    root: Path,
    *,
    lane: str,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    allow_current_writer_lock: bool = False,
) -> dict[str, Any]:
    return _alchemy_lanes.run_lane_dry_run(
        root,
        lane=lane,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        allow_current_writer_lock=allow_current_writer_lock,
    )


def _alchemy_lane_dependencies() -> dict[str, Any]:
    return {
        "review_apply": run_alchemy_review_apply,
        "distill_apply": run_alchemy_distill_apply,
        "propose_apply": run_alchemy_propose_apply,
        "compile_runner": compile_wiki,
        "lint_runner": lint_wiki,
        "nightly_runner": nightly_health,
        "apply_machine_memory_actions_batch": _machine_memory_batch.apply_machine_memory_actions_batch,
        "append_runtime_history": append_runtime_history,
        "append_execution_receipt_history": append_execution_receipt_history,
        "atomic_write_text": atomic_write_text,
        "durable_truncate": _durable_truncate,
        "receipt_error_cls": AlchemyLanePrimitiveReceiptError,
        "receipt_half_write_error_cls": AlchemyLanePrimitiveReceiptHalfWriteError,
        "normalize_auto_lanes": _normalize_auto_lanes,
        "normalize_lane_primitives": _normalize_lane_primitives,
        "auto_primitives_for_lane": _auto_primitives_for_lane,
        "auto_skip_reason": _auto_skip_reason,
        "utc_now": utc_now,
        "logger": logger,
    }


@runtime_write_operation
def run_alchemy_lane_apply(
    root: Path,
    *,
    lane: str,
    scope: str,
    action_ids: list[str] | None = None,
    primitives: list[str] | None = None,
    note: str | None = None,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    allow_current_writer_lock: bool = False,
) -> dict[str, Any]:
    return _alchemy_lanes.run_lane_apply(
        root,
        lane=lane,
        scope=scope,
        action_ids=action_ids,
        primitives=primitives,
        note=note,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        allow_current_writer_lock=allow_current_writer_lock,
        deps=_alchemy_lane_dependencies(),
    )


@runtime_write_operation
def run_alchemy_auto(
    root: Path,
    *,
    apply: bool = False,
    lanes: list[str] | None = None,
    scope: str = "all",
    primitives: list[str] | None = None,
    note: str | None = None,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    allow_current_writer_lock: bool = False,
) -> dict[str, Any]:
    return _alchemy_lanes.run_auto(
        root,
        apply=apply,
        lanes=lanes,
        scope=scope,
        primitives=primitives,
        note=note,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        allow_current_writer_lock=allow_current_writer_lock,
        lane_dry_run_runner=run_alchemy_lane_dry_run,
        lane_apply_runner=run_alchemy_lane_apply,
        deps=_alchemy_lane_dependencies(),
    )


def _append_alchemy_auto_runtime_event(
    root: Path,
    *,
    scope: str,
    lanes: list[str],
    primitives: list[str],
    lane_results: list[dict[str, Any]],
    applied_results: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> None:
    _alchemy_lanes.append_auto_runtime_event(
        root,
        scope=scope,
        lanes=lanes,
        primitives=primitives,
        lane_results=lane_results,
        applied_results=applied_results,
        skipped=skipped,
        deps=_alchemy_lane_dependencies(),
    )


def _append_alchemy_lane_runtime_event(
    root: Path,
    *,
    event_type: str,
    lane: str,
    scope: str,
    action_ids: list[str],
    primitives: list[str],
    plan: dict[str, Any],
    status: str,
    primitive_results: list[dict[str, Any]] | None = None,
    apply_result: dict[str, Any] | None = None,
) -> None:
    _alchemy_lanes.append_lane_runtime_event(
        root,
        event_type=event_type,
        lane=lane,
        scope=scope,
        action_ids=action_ids,
        primitives=primitives,
        plan=plan,
        status=status,
        primitive_results=primitive_results,
        apply_result=apply_result,
        deps=_alchemy_lane_dependencies(),
    )


def _run_receipted_lane_primitive(
    root: Path,
    *,
    lane: str,
    scope: str,
    primitive: str,
    plan: dict[str, Any],
    note: str | None,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    return _alchemy_lanes.run_receipted_lane_primitive(
        root,
        lane=lane,
        scope=scope,
        primitive=primitive,
        plan=plan,
        note=note,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        deps=_alchemy_lane_dependencies(),
    )
