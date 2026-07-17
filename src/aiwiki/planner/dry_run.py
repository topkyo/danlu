from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any

from .. import app_utils
from ..app_utils import relative_path, runtime_lock_path, slugify
from .schema import validate_planner_log_record

_PLANNER_LOG_REL_PATH = ".aiwiki/state/planner-log.jsonl"
_SIGNALS_REL_PATH = ".aiwiki/state/signals.jsonl"
_SKIP_EXAMPLES_LIMIT = 5

_LANE_DECISION = {
    "heavy": "enqueue-heavy",
    "light": "enqueue-light",
}

_DEFAULT_BUDGETS = {
    "heavy": {
        "max_signals": 50,
        "max_pages": 500,
        "max_tokens": 50000,
    },
    "light": {
        "max_signals": 200,
        "max_pages": 200,
        "max_tokens": 10000,
    },
}

_PRIMITIVE_PLANS = {
    "heavy": (
        ("route", "Compute dirty scope from selected planner decisions."),
        ("compile", "Preview targeted compile for dirty sources and concepts."),
        ("judge", "Preview judgment refresh for dirty scope."),
        ("distill", "Preview optional candidate elixir refresh."),
        ("lint", "Preview scoped drift and contract checks."),
        ("review", "Preview review queue entries for high-severity outputs."),
        ("propose", "Preview L3 proposal candidates for recurring failures and feedback."),
    ),
    "light": (
        ("route", "Preview active corpus cooling and maintenance scope."),
        ("compile", "Preview metadata and index refresh only."),
        ("lint", "Preview read-only drift and aging checks."),
        ("nightly", "Preview deterministic nightly health refresh."),
    ),
}

_APPLY_SUPPORTED_PRIMITIVES = {
    "heavy": {"compile", "distill", "lint", "review", "propose"},
    "light": {"compile", "lint", "nightly"},
}

_DEFERRED_PRIMITIVES = {
    "heavy": (
        (
            "judge",
            "Refresh dirty-scope judgment and decision assets.",
            "missing_receipted_scoped_contract",
            "Define a scoped judgment refresh primitive with dry-run, receipt, audit, and revert semantics.",
        ),
    ),
    "light": (
        (
            "judge",
            "Refresh judgment and decision assets.",
            "not_allowed_for_light_lane",
            "Route meaning-changing judgment work through heavy lane after a receipted scoped contract exists.",
        ),
        (
            "distill",
            "Refresh candidate elixir iterations.",
            "not_allowed_for_light_lane",
            "Route elixir distillation through explicit elixir lifecycle commands or heavy lane contracts.",
        ),
        (
            "review",
            "Generate or update review queue entries.",
            "not_allowed_for_light_lane",
            "Keep light lane to low-risk hygiene; scoped review apply stays explicit and heavy-only.",
        ),
        (
            "propose",
            "Generate prompt or policy proposals.",
            "not_allowed_for_light_lane",
            "Keep L3 proposal generation out of light lane until proposal review/apply/revert is implemented.",
        ),
    ),
}

_DEFERRED_APPLY_CONTRACTS = {
    "judge": {
        "status": "executable",
        "primitive": "judge",
        "write_surfaces": [
            "wiki/judgments/",
            "wiki/decisions/",
            ".aiwiki/state/execution-receipts/",
            ".aiwiki/state/execution-receipts.jsonl",
            ".aiwiki/state/runtime-history.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
        "receipt_schema": "execution-receipt v1; subject_kind=alchemy_judgment_page; operation=alchemy-judge-refresh",
        "audit_event_schema": "execution_receipt_history_append plus runtime_history direct append",
        "revert_policy": "non_revertible_refresh_marker: managed marker can be replaced by a newer judge apply; semantic judgment edits remain human/model explicit",
        "idempotency_key": "primitive + scope + candidate_ids + trace_ids",
        "backend_policy": "no LLM required for deterministic refresh marker; semantic judgment generation must be explicit",
    },
    "distill": {
        "status": "executable",
        "primitive": "distill",
        "write_surfaces": [
            ".aiwiki/staging/elixirs/",
            ".aiwiki/state/execution-receipts/",
            ".aiwiki/state/execution-receipts.jsonl",
            ".aiwiki/state/runtime-history.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
        "receipt_schema": "execution-receipt v1; subject_kind=alchemy_elixir_candidate; operation=alchemy-distill-refresh",
        "audit_event_schema": "execution_receipt_history_append plus runtime_history direct append",
        "revert_policy": "non_revertible_candidate_iteration: re-run distill/finalize/promote lifecycle with receipt evidence; before/after hashes document each refreshed candidate",
        "idempotency_key": "primitive + scope + candidate_ids + deterministic_question + trace_ids",
        "backend_policy": "no LLM required for deterministic scoped refresh question; any future model-generated question must be explicit",
    },
    "review": {
        "status": "executable",
        "primitive": "review",
        "write_surfaces": [
            "wiki/indexes/review-queue.md",
            ".aiwiki/state/execution-receipts/",
            ".aiwiki/state/execution-receipts.jsonl",
            ".aiwiki/state/runtime-history.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
        "receipt_schema": "execution-receipt v1; subject_kind=alchemy_review_queue; operation=alchemy-review-enqueue",
        "audit_event_schema": "execution_receipt_history_append plus runtime_history direct append",
        "revert_policy": "non_revertible_derived_index: rerun compile or apply a newer review preview to replace managed queue section",
        "idempotency_key": "primitive + scope + candidate_ids + trace_ids",
        "backend_policy": "no LLM required for enqueue; any optional model use must be explicit",
    },
    "propose": {
        "status": "executable",
        "primitive": "propose",
        "write_surfaces": [
            ".aiwiki/staging/proposals/prompt/",
            ".aiwiki/staging/proposals/policy/",
            ".aiwiki/state/l3-proposals.json",
            ".aiwiki/state/execution-receipts/",
            ".aiwiki/state/execution-receipts.jsonl",
            ".aiwiki/state/runtime-history.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
        "receipt_schema": "execution-receipt v1; subject_kind=alchemy_proposal_plane; operation=alchemy-propose-generate",
        "audit_event_schema": "execution_receipt_history_append plus runtime_history direct append",
        "revert_policy": "non_revertible_proposal_generation: reject generated L3 proposal candidates through the existing review proposal workflow; target-file apply remains receipt-gated",
        "idempotency_key": "primitive + scope + candidate_ids + trace_ids",
        "backend_policy": "no LLM required for deterministic scoped proposal candidate generation; L3 target writes still require human accept",
    },
}

_LANE_APPLY_CONTRACTS = {
    "compile": {
        "status": "executable",
        "primitive": "compile",
        "write_surfaces": [
            "wiki/sources/",
            "wiki/concepts/",
            "wiki/indexes/",
            "wiki/derived/",
            ".aiwiki/state/compile-state.json",
            ".aiwiki/state/execution-receipts/",
            ".aiwiki/state/execution-receipts.jsonl",
            ".aiwiki/state/runtime-history.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
        "receipt_schema": "execution-receipt v1; subject_kind=alchemy_lane_primitive; operation=alchemy-lane-primitive",
        "audit_event_schema": "execution_receipt_history_append plus runtime_history direct append",
        "revert_policy": "non_revertible_derived_rebuild: rerun compile or apply a newer compile preview",
        "idempotency_key": "primitive + scope + trace_ids",
        "backend_policy": "deterministic compile baseline; scoped LLM sub-jobs must be explicit",
    },
    "lint": {
        "status": "executable",
        "primitive": "lint",
        "write_surfaces": [
            ".aiwiki/lint/",
            ".aiwiki/state/execution-receipts/",
            ".aiwiki/state/execution-receipts.jsonl",
            ".aiwiki/state/runtime-history.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
        "receipt_schema": "execution-receipt v1; subject_kind=alchemy_lane_primitive; operation=alchemy-lane-primitive",
        "audit_event_schema": "execution_receipt_history_append plus runtime_history direct append",
        "revert_policy": "non_revertible_operator_report: rerun lint or apply a newer lint preview",
        "idempotency_key": "primitive + scope + trace_ids",
        "backend_policy": "deterministic lint baseline; semantic lint via run-lint must be explicit",
    },
    "nightly": {
        "status": "executable",
        "primitive": "nightly",
        "write_surfaces": [
            ".aiwiki/state/nightly-health.json",
            "wiki/indexes/repair-backlog.md",
            ".aiwiki/state/execution-receipts/",
            ".aiwiki/state/execution-receipts.jsonl",
            ".aiwiki/state/runtime-history.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
        "receipt_schema": "execution-receipt v1; subject_kind=alchemy_lane_primitive; operation=alchemy-lane-primitive",
        "audit_event_schema": "execution_receipt_history_append plus runtime_history direct append",
        "revert_policy": "non_revertible_health_snapshot: rerun nightly or apply a newer nightly preview",
        "idempotency_key": "primitive + scope + trace_ids",
        "backend_policy": "deterministic nightly health refresh; no implicit LLM",
    },
}


def preview_alchemy_lane(
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
    normalized_lane = _normalize_lane(lane)
    normalized_scope = scope.strip() or "all"
    planner_path = _resolve_path(root, planner_log_path, _PLANNER_LOG_REL_PATH)
    signal_path = _resolve_path(root, signals_path, _SIGNALS_REL_PATH)
    budget_limits = _budget_limits(normalized_lane, max_signals=max_signals, max_pages=max_pages, max_tokens=max_tokens)

    signals, signal_skip_examples = _load_signals(signal_path)
    decisions, decision_skip_examples = _load_planner_decisions(planner_path)
    selected: list[dict[str, Any]] = []
    skipped_count = 0
    target_decision = _LANE_DECISION[normalized_lane]

    for decision in decisions:
        if decision_mode is not None and decision.get("mode") != decision_mode:
            skipped_count += 1
            continue
        if decision.get("decision") != target_decision:
            skipped_count += 1
            continue
        signal = signals.get(str(decision.get("signal_id") or ""))
        if signal is None:
            skipped_count += 1
            continue
        if not _matches_scope(signal, normalized_scope):
            skipped_count += 1
            continue
        selected.append({"decision": decision, "signal": signal})

    lock = _preview_runtime_lock(root, allow_current_writer=allow_current_writer_lock)
    if lock["status"] == "conflict":
        return {
            "status": "skipped",
            "reason": "lock_conflict",
            "lane": normalized_lane,
            "scope": normalized_scope,
            "dry_run": True,
            "side_effects_allowed": False,
            "planner_log_path": _path_label(root, planner_path),
            "signals_path": _path_label(root, signal_path),
            "decision_mode": decision_mode or "",
            "selected_count": 0,
            "skipped_count": len(decisions),
            "scope_preview": _empty_scope_preview(),
            "primitive_plan": [],
            "deferred_primitives": _deferred_primitives(normalized_lane),
            "budget": {
                "limits": budget_limits,
                "used": _empty_budget_used(),
                "exceeded": False,
                "reason_codes": [],
            },
            "lock": lock,
            "skip_examples": _limited_examples(signal_skip_examples + decision_skip_examples),
        }

    scope_preview = _build_scope_preview(selected)
    budget_used = _build_budget_used(selected)
    budget_exceeded, budget_reasons = _budget_exceeded(budget_limits, budget_used)
    status = "budget_exceeded" if budget_exceeded else "ok"

    return {
        "status": status,
        "lane": normalized_lane,
        "scope": normalized_scope,
        "dry_run": True,
        "side_effects_allowed": False,
        "planner_log_path": _path_label(root, planner_path),
        "signals_path": _path_label(root, signal_path),
        "decision_mode": decision_mode or "",
        "selected_count": len(selected),
        "skipped_count": skipped_count,
        "scope_preview": scope_preview,
        "primitive_plan": _primitive_plan(normalized_lane, scope_preview),
        "deferred_primitives": _deferred_primitives(normalized_lane),
        "budget": {
            "limits": budget_limits,
            "used": budget_used,
            "exceeded": budget_exceeded,
            "reason_codes": budget_reasons,
        },
        "lock": lock,
        "skip_examples": _limited_examples(signal_skip_examples + decision_skip_examples),
    }


def preview_judge_primitive(
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
    if limit < 0:
        raise ValueError("limit must be non-negative")

    lane_plan = preview_alchemy_lane(
        root,
        lane="heavy",
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        allow_current_writer_lock=allow_current_writer_lock,
    )
    scope_preview = lane_plan.get("scope_preview") if isinstance(lane_plan.get("scope_preview"), dict) else _empty_scope_preview()
    all_candidates = _judge_preview_candidates(str(lane_plan.get("scope") or scope), scope_preview)
    candidates = all_candidates[:limit]
    applicable_count = sum(1 for item in all_candidates if item.get("apply_supported") is True)

    return {
        "status": lane_plan.get("status"),
        "primitive": "judge",
        "lane": "heavy",
        "scope": lane_plan.get("scope") or (scope.strip() or "all"),
        "dry_run": True,
        "side_effects_allowed": False,
        "apply_supported": True,
        "apply_blocker": "",
        "lane_apply_supported": False,
        "lane_apply_blocker": _apply_blocker_for_primitive("heavy", "judge"),
        "llm_required_for_apply": False,
        "receipt_required_for_apply": True,
        "audit_required_for_apply": True,
        "revert_policy_required_for_apply": False,
        "apply_contract": _deferred_apply_contract("judge"),
        "planner_log_path": lane_plan.get("planner_log_path"),
        "signals_path": lane_plan.get("signals_path"),
        "decision_mode": lane_plan.get("decision_mode") or "",
        "selected_count": lane_plan.get("selected_count", 0),
        "skipped_count": lane_plan.get("skipped_count", 0),
        "scope_preview": scope_preview,
        "candidate_count": len(all_candidates),
        "applicable_candidate_count": applicable_count,
        "returned_count": len(candidates),
        "truncated": len(candidates) < len(all_candidates),
        "candidates": candidates,
        "budget": lane_plan.get("budget", {}),
        "lock": lane_plan.get("lock", {}),
        "source_lane_preview": {
            "status": lane_plan.get("status"),
            "selected_count": lane_plan.get("selected_count", 0),
            "deferred_primitives": [
                item
                for item in lane_plan.get("deferred_primitives", [])
                if isinstance(item, dict) and item.get("primitive") == "judge"
            ],
        },
        "skip_examples": lane_plan.get("skip_examples", []),
    }


def preview_distill_primitive(
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
    if limit < 0:
        raise ValueError("limit must be non-negative")

    lane_plan = preview_alchemy_lane(
        root,
        lane="heavy",
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        allow_current_writer_lock=allow_current_writer_lock,
    )
    scope_preview = lane_plan.get("scope_preview") if isinstance(lane_plan.get("scope_preview"), dict) else _empty_scope_preview()
    all_candidates = _distill_preview_candidates(str(lane_plan.get("scope") or scope), scope_preview)
    candidates = all_candidates[:limit]
    applicable_count = sum(1 for item in all_candidates if item.get("apply_supported") is True)

    return {
        "status": lane_plan.get("status"),
        "primitive": "distill",
        "lane": "heavy",
        "scope": lane_plan.get("scope") or (scope.strip() or "all"),
        "dry_run": True,
        "side_effects_allowed": False,
        "apply_supported": True,
        "apply_blocker": "",
        "lane_apply_supported": True,
        "lane_apply_blocker": "",
        "llm_required_for_apply": False,
        "receipt_required_for_apply": True,
        "audit_required_for_apply": True,
        "revert_policy_required_for_apply": False,
        "candidate_plane_required_for_apply": True,
        "apply_contract": _deferred_apply_contract("distill"),
        "planner_log_path": lane_plan.get("planner_log_path"),
        "signals_path": lane_plan.get("signals_path"),
        "decision_mode": lane_plan.get("decision_mode") or "",
        "selected_count": lane_plan.get("selected_count", 0),
        "skipped_count": lane_plan.get("skipped_count", 0),
        "scope_preview": scope_preview,
        "candidate_count": len(all_candidates),
        "applicable_candidate_count": applicable_count,
        "returned_count": len(candidates),
        "truncated": len(candidates) < len(all_candidates),
        "candidates": candidates,
        "budget": lane_plan.get("budget", {}),
        "lock": lane_plan.get("lock", {}),
        "source_lane_preview": {
            "status": lane_plan.get("status"),
            "selected_count": lane_plan.get("selected_count", 0),
            "deferred_primitives": [
                item
                for item in lane_plan.get("deferred_primitives", [])
                if isinstance(item, dict) and item.get("primitive") == "distill"
            ],
        },
        "skip_examples": lane_plan.get("skip_examples", []),
    }


def preview_review_primitive(
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
    if limit < 0:
        raise ValueError("limit must be non-negative")

    lane_plan = preview_alchemy_lane(
        root,
        lane="heavy",
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        allow_current_writer_lock=allow_current_writer_lock,
    )
    scope_preview = lane_plan.get("scope_preview") if isinstance(lane_plan.get("scope_preview"), dict) else _empty_scope_preview()
    all_candidates = _review_preview_candidates(str(lane_plan.get("scope") or scope), scope_preview)
    candidates = all_candidates[:limit]

    return {
        "status": lane_plan.get("status"),
        "primitive": "review",
        "lane": "heavy",
        "scope": lane_plan.get("scope") or (scope.strip() or "all"),
        "dry_run": True,
        "side_effects_allowed": False,
        "apply_supported": True,
        "apply_blocker": "",
        "lane_apply_supported": True,
        "lane_apply_blocker": "",
        "llm_required_for_apply": False,
        "receipt_required_for_apply": True,
        "audit_required_for_apply": True,
        "revert_policy_required_for_apply": True,
        "review_queue_write_required_for_apply": True,
        "apply_contract": _deferred_apply_contract("review"),
        "planner_log_path": lane_plan.get("planner_log_path"),
        "signals_path": lane_plan.get("signals_path"),
        "decision_mode": lane_plan.get("decision_mode") or "",
        "selected_count": lane_plan.get("selected_count", 0),
        "skipped_count": lane_plan.get("skipped_count", 0),
        "scope_preview": scope_preview,
        "candidate_count": len(all_candidates),
        "returned_count": len(candidates),
        "truncated": len(candidates) < len(all_candidates),
        "candidates": candidates,
        "budget": lane_plan.get("budget", {}),
        "lock": lane_plan.get("lock", {}),
        "source_lane_preview": {
            "status": lane_plan.get("status"),
            "selected_count": lane_plan.get("selected_count", 0),
            "deferred_primitives": [
                item
                for item in lane_plan.get("deferred_primitives", [])
                if isinstance(item, dict) and item.get("primitive") == "review"
            ],
        },
        "skip_examples": lane_plan.get("skip_examples", []),
    }


def preview_propose_primitive(
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
    if limit < 0:
        raise ValueError("limit must be non-negative")

    lane_plan = preview_alchemy_lane(
        root,
        lane="heavy",
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        allow_current_writer_lock=allow_current_writer_lock,
    )
    scope_preview = lane_plan.get("scope_preview") if isinstance(lane_plan.get("scope_preview"), dict) else _empty_scope_preview()
    all_candidates = _propose_preview_candidates(str(lane_plan.get("scope") or scope), scope_preview)
    candidates = all_candidates[:limit]

    return {
        "status": lane_plan.get("status"),
        "primitive": "propose",
        "lane": "heavy",
        "scope": lane_plan.get("scope") or (scope.strip() or "all"),
        "dry_run": True,
        "side_effects_allowed": False,
        "apply_supported": True,
        "apply_blocker": "",
        "lane_apply_supported": True,
        "lane_apply_blocker": "",
        "llm_required_for_apply": False,
        "receipt_required_for_apply": True,
        "audit_required_for_apply": True,
        "revert_policy_required_for_apply": False,
        "proposal_plane_write_required_for_apply": True,
        "human_accept_required_after_apply": True,
        "apply_contract": _deferred_apply_contract("propose"),
        "planner_log_path": lane_plan.get("planner_log_path"),
        "signals_path": lane_plan.get("signals_path"),
        "decision_mode": lane_plan.get("decision_mode") or "",
        "selected_count": lane_plan.get("selected_count", 0),
        "skipped_count": lane_plan.get("skipped_count", 0),
        "scope_preview": scope_preview,
        "candidate_count": len(all_candidates),
        "returned_count": len(candidates),
        "truncated": len(candidates) < len(all_candidates),
        "candidates": candidates,
        "budget": lane_plan.get("budget", {}),
        "lock": lane_plan.get("lock", {}),
        "source_lane_preview": {
            "status": lane_plan.get("status"),
            "selected_count": lane_plan.get("selected_count", 0),
            "deferred_primitives": [
                item
                for item in lane_plan.get("deferred_primitives", [])
                if isinstance(item, dict) and item.get("primitive") == "propose"
            ],
        },
        "skip_examples": lane_plan.get("skip_examples", []),
    }


def _normalize_lane(lane: str) -> str:
    normalized = lane.strip().lower()
    if normalized not in _LANE_DECISION:
        raise ValueError(f"unsupported alchemy lane: {lane}")
    return normalized


def _resolve_path(root: Path, value: Path | None, default_rel: str) -> Path:
    if value is None:
        return root / default_rel
    if value.is_absolute():
        return value
    return root / value


def _path_label(root: Path, path: Path) -> str:
    try:
        return relative_path(root, path)
    except ValueError:
        return str(path)


def _budget_limits(
    lane: str,
    *,
    max_signals: int | None,
    max_pages: int | None,
    max_tokens: int | None,
) -> dict[str, int]:
    defaults = _DEFAULT_BUDGETS[lane]
    limits = {
        "max_signals": defaults["max_signals"] if max_signals is None else max_signals,
        "max_pages": defaults["max_pages"] if max_pages is None else max_pages,
        "max_tokens": defaults["max_tokens"] if max_tokens is None else max_tokens,
    }
    for key, value in limits.items():
        if value < 0:
            raise ValueError(f"{key} must be non-negative")
    return limits


def _load_signals(path: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    records: dict[str, dict[str, Any]] = {}
    skip_examples: list[dict[str, Any]] = []
    if not path.exists():
        return records, skip_examples

    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            payload = raw_line.strip()
            if not payload:
                continue
            try:
                record = json.loads(payload)
            except json.JSONDecodeError:
                _append_skip(skip_examples, "signal_malformed_json", line_no)
                continue
            if not isinstance(record, dict):
                _append_skip(skip_examples, "signal_non_object", line_no)
                continue
            signal_id = record.get("signal_id")
            if not isinstance(signal_id, str) or not signal_id:
                _append_skip(skip_examples, "signal_missing_signal_id", line_no)
                continue
            records[signal_id] = record
    return records, skip_examples


def _load_planner_decisions(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    skip_examples: list[dict[str, Any]] = []
    if not path.exists():
        return records, skip_examples

    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            payload = raw_line.strip()
            if not payload:
                continue
            try:
                record = json.loads(payload)
            except json.JSONDecodeError:
                _append_skip(skip_examples, "planner_log_malformed_json", line_no)
                continue
            if not isinstance(record, dict):
                _append_skip(skip_examples, "planner_log_non_object", line_no)
                continue
            validation = validate_planner_log_record(record)
            if not validation.ok:
                _append_skip(skip_examples, "planner_log_invalid_record", line_no, errors=list(validation.errors))
                continue
            records.append(record)
    return records, skip_examples


def _append_skip(skip_examples: list[dict[str, Any]], reason: str, line_no: int, **extra: Any) -> None:
    if len(skip_examples) >= _SKIP_EXAMPLES_LIMIT:
        return
    item = {"reason": reason, "line": line_no}
    item.update(extra)
    skip_examples.append(item)


def _matches_scope(signal: dict[str, Any], scope: str) -> bool:
    if scope in {"all", "planner-log"}:
        return True

    signal_scope = signal.get("scope")
    if not isinstance(signal_scope, dict):
        return False

    if scope.startswith("protocol:"):
        return str(signal_scope.get("protocol") or "") == scope.split(":", 1)[1]
    if scope.startswith("source:"):
        return scope.split(":", 1)[1] in _string_list(signal_scope.get("source_ids"))
    if scope.startswith("concept:"):
        return scope.split(":", 1)[1] in _string_list(signal_scope.get("concept_slugs"))
    if scope.startswith("elixir:"):
        return scope.split(":", 1)[1] in _string_list(signal_scope.get("elixir_refs"))
    if scope.startswith("judgment:"):
        return scope.split(":", 1)[1] in _string_list(signal_scope.get("judgment_refs"))

    return str(signal_scope.get("protocol") or "") == scope


def _build_scope_preview(selected: list[dict[str, Any]]) -> dict[str, Any]:
    protocols: set[str] = set()
    source_ids: set[str] = set()
    concept_slugs: set[str] = set()
    elixir_refs: set[str] = set()
    judgment_refs: set[str] = set()
    signal_ids: set[str] = set()
    trace_ids: set[str] = set()
    severities: set[str] = set()

    for item in selected:
        signal = item["signal"]
        decision = item["decision"]
        signal_ids.add(str(decision.get("signal_id") or ""))
        trace_ids.add(str(decision.get("trace_id") or ""))
        severities.add(str(signal.get("severity") or ""))
        signal_scope = signal.get("scope")
        if not isinstance(signal_scope, dict):
            continue
        _add_optional(protocols, signal_scope.get("protocol"))
        source_ids.update(_string_list(signal_scope.get("source_ids")))
        concept_slugs.update(_string_list(signal_scope.get("concept_slugs")))
        elixir_refs.update(_string_list(signal_scope.get("elixir_refs")))
        judgment_refs.update(_string_list(signal_scope.get("judgment_refs")))

    return {
        "signal_ids": _sorted_clean(signal_ids),
        "trace_ids": _sorted_clean(trace_ids),
        "protocols": _sorted_clean(protocols),
        "source_ids": _sorted_clean(source_ids),
        "concept_slugs": _sorted_clean(concept_slugs),
        "elixir_refs": _sorted_clean(elixir_refs),
        "judgment_refs": _sorted_clean(judgment_refs),
        "severities": _sorted_clean(severities),
    }


def _empty_scope_preview() -> dict[str, Any]:
    return {
        "signal_ids": [],
        "trace_ids": [],
        "protocols": [],
        "source_ids": [],
        "concept_slugs": [],
        "elixir_refs": [],
        "judgment_refs": [],
        "severities": [],
    }


def _primitive_plan(lane: str, scope_preview: dict[str, Any]) -> list[dict[str, Any]]:
    signal_ids = list(scope_preview.get("signal_ids") or [])
    protocols = list(scope_preview.get("protocols") or [])
    plan: list[dict[str, Any]] = []
    for index, (primitive, description) in enumerate(_PRIMITIVE_PLANS[lane], start=1):
        apply_supported = primitive in _APPLY_SUPPORTED_PRIMITIVES[lane]
        entry = {
            "order": index,
            "primitive": primitive,
            "description": description,
            "dry_run_only": True,
            "apply_supported": apply_supported,
            "apply_blocker": "" if apply_supported else _apply_blocker_for_primitive(lane, primitive),
            "signal_ids": signal_ids,
            "protocols": protocols,
        }
        if apply_supported:
            entry["apply_contract"] = _deferred_apply_contract(primitive)
        plan.append(entry)
    return plan


def _apply_blocker_for_primitive(lane: str, primitive: str) -> str:
    if primitive == "route":
        return "route_is_dry_run_scope_planning"
    for item in _DEFERRED_PRIMITIVES[lane]:
        if item[0] == primitive:
            return item[2]
    return "not_in_lane_apply_contract"


def _deferred_primitives(lane: str) -> list[dict[str, Any]]:
    return [
        {
            "primitive": primitive,
            "description": description,
            "reason_code": reason_code,
            "unlock_condition": unlock_condition,
            "apply_supported": False,
            "apply_contract": _deferred_apply_contract(primitive),
        }
        for primitive, description, reason_code, unlock_condition in _DEFERRED_PRIMITIVES[lane]
    ]


def _deferred_apply_contract(primitive: str) -> dict[str, Any]:
    contract = _DEFERRED_APPLY_CONTRACTS.get(primitive) or _LANE_APPLY_CONTRACTS.get(primitive, {})
    if not contract:
        return {}
    return json.loads(json.dumps(contract, ensure_ascii=False))


def _judge_preview_candidates(scope: str, scope_preview: dict[str, Any]) -> list[dict[str, Any]]:
    if not list(scope_preview.get("signal_ids") or []):
        return []

    common = {
        "llm_required_for_apply": False,
        "receipt_required_for_apply": True,
        "audit_required_for_apply": True,
        "revert_policy_required_for_apply": False,
        "apply_contract": _deferred_apply_contract("judge"),
        "signal_ids": list(scope_preview.get("signal_ids") or []),
        "trace_ids": list(scope_preview.get("trace_ids") or []),
        "source_ids": list(scope_preview.get("source_ids") or []),
        "concept_slugs": list(scope_preview.get("concept_slugs") or []),
        "elixir_refs": list(scope_preview.get("elixir_refs") or []),
        "severities": list(scope_preview.get("severities") or []),
    }
    judgment_refs = list(scope_preview.get("judgment_refs") or [])
    protocols = list(scope_preview.get("protocols") or [])

    candidates: list[dict[str, Any]] = []
    for ref in judgment_refs:
        candidates.append(
            {
                **common,
                "reason_codes": ["heavy_lane_dirty_scope", "scoped_judge_apply_supported"],
                "apply_supported": True,
                "apply_blocker": "",
                "lane_apply_supported": False,
                "lane_apply_blocker": _apply_blocker_for_primitive("heavy", "judge"),
                "candidate_id": f"judge-refresh-{slugify(ref)}",
                "kind": "judgment_refresh",
                "target_ref": ref,
                "protocol": "",
                "judgment_refs": [ref],
            }
        )

    if candidates:
        return candidates

    protocol_items = protocols or [""]
    scope_slug = slugify(scope)
    for index, protocol in enumerate(protocol_items, start=1):
        target = protocol or scope
        candidates.append(
            {
                **common,
                "reason_codes": ["heavy_lane_dirty_scope", "missing_judgment_ref_for_direct_apply"],
                "apply_supported": False,
                "apply_blocker": "missing_judgment_ref_for_direct_apply",
                "lane_apply_supported": False,
                "lane_apply_blocker": _apply_blocker_for_primitive("heavy", "judge"),
                "candidate_id": f"judge-scope-{slugify(target) or scope_slug}-{index}",
                "kind": "judgment_scope_refresh",
                "target_ref": target,
                "protocol": protocol,
                "judgment_refs": [],
            }
        )
    return candidates


def _distill_preview_candidates(scope: str, scope_preview: dict[str, Any]) -> list[dict[str, Any]]:
    if not list(scope_preview.get("signal_ids") or []):
        return []

    common = {
        "llm_required_for_apply": False,
        "receipt_required_for_apply": True,
        "audit_required_for_apply": True,
        "revert_policy_required_for_apply": False,
        "candidate_plane_required_for_apply": True,
        "apply_contract": _deferred_apply_contract("distill"),
        "signal_ids": list(scope_preview.get("signal_ids") or []),
        "trace_ids": list(scope_preview.get("trace_ids") or []),
        "source_ids": list(scope_preview.get("source_ids") or []),
        "concept_slugs": list(scope_preview.get("concept_slugs") or []),
        "judgment_refs": list(scope_preview.get("judgment_refs") or []),
        "severities": list(scope_preview.get("severities") or []),
    }
    elixir_refs = list(scope_preview.get("elixir_refs") or [])
    protocols = list(scope_preview.get("protocols") or [])

    candidates: list[dict[str, Any]] = []
    for ref in elixir_refs:
        candidates.append(
            {
                **common,
                "reason_codes": ["heavy_lane_dirty_scope", "scoped_distill_apply_supported"],
                "apply_supported": True,
                "apply_blocker": "",
                "lane_apply_supported": True,
                "lane_apply_blocker": "",
                "candidate_id": f"distill-refresh-{slugify(ref)}",
                "kind": "elixir_candidate_refresh",
                "target_ref": ref,
                "protocol": "",
                "elixir_refs": [ref],
            }
        )

    if candidates:
        return candidates

    protocol_items = protocols or [""]
    scope_slug = slugify(scope)
    for index, protocol in enumerate(protocol_items, start=1):
        target = protocol or scope
        candidates.append(
            {
                **common,
                "reason_codes": ["heavy_lane_dirty_scope", "missing_elixir_ref_for_direct_apply"],
                "apply_supported": False,
                "apply_blocker": "missing_elixir_ref_for_direct_apply",
                "lane_apply_supported": False,
                "lane_apply_blocker": _apply_blocker_for_primitive("heavy", "distill"),
                "candidate_id": f"distill-scope-{slugify(target) or scope_slug}-{index}",
                "kind": "elixir_scope_refresh",
                "target_ref": target,
                "protocol": protocol,
                "elixir_refs": [],
            }
        )
    return candidates


def _review_preview_candidates(scope: str, scope_preview: dict[str, Any]) -> list[dict[str, Any]]:
    if not list(scope_preview.get("signal_ids") or []):
        return []

    common = {
        "reason_codes": ["heavy_lane_dirty_scope", "scoped_review_apply_supported"],
        "apply_supported": True,
        "apply_blocker": "",
        "lane_apply_supported": True,
        "lane_apply_blocker": "",
        "llm_required_for_apply": False,
        "receipt_required_for_apply": True,
        "audit_required_for_apply": True,
        "revert_policy_required_for_apply": True,
        "review_queue_write_required_for_apply": True,
        "apply_contract": _deferred_apply_contract("review"),
        "signal_ids": list(scope_preview.get("signal_ids") or []),
        "trace_ids": list(scope_preview.get("trace_ids") or []),
        "source_ids": list(scope_preview.get("source_ids") or []),
        "concept_slugs": list(scope_preview.get("concept_slugs") or []),
        "severities": list(scope_preview.get("severities") or []),
    }
    judgment_refs = list(scope_preview.get("judgment_refs") or [])
    elixir_refs = list(scope_preview.get("elixir_refs") or [])
    protocols = list(scope_preview.get("protocols") or [])

    candidates: list[dict[str, Any]] = []
    for ref in judgment_refs:
        candidates.append(
            {
                **common,
                "candidate_id": f"review-judgment-{slugify(ref)}",
                "kind": "judgment_review_enqueue",
                "target_ref": ref,
                "protocol": "",
                "judgment_refs": [ref],
                "elixir_refs": [],
            }
        )
    for ref in elixir_refs:
        candidates.append(
            {
                **common,
                "candidate_id": f"review-elixir-{slugify(ref)}",
                "kind": "elixir_review_enqueue",
                "target_ref": ref,
                "protocol": "",
                "judgment_refs": [],
                "elixir_refs": [ref],
            }
        )

    if candidates:
        return candidates

    protocol_items = protocols or [""]
    scope_slug = slugify(scope)
    for index, protocol in enumerate(protocol_items, start=1):
        target = protocol or scope
        candidates.append(
            {
                **common,
                "candidate_id": f"review-scope-{slugify(target) or scope_slug}-{index}",
                "kind": "scope_review_enqueue",
                "target_ref": target,
                "protocol": protocol,
                "judgment_refs": [],
                "elixir_refs": [],
            }
        )
    return candidates


def _propose_preview_candidates(scope: str, scope_preview: dict[str, Any]) -> list[dict[str, Any]]:
    if not list(scope_preview.get("signal_ids") or []):
        return []

    protocols = list(scope_preview.get("protocols") or [])
    common = {
        "reason_codes": ["heavy_lane_dirty_scope", "scoped_propose_apply_supported"],
        "apply_supported": True,
        "apply_blocker": "",
        "lane_apply_supported": True,
        "lane_apply_blocker": "",
        "llm_required_for_apply": False,
        "receipt_required_for_apply": True,
        "audit_required_for_apply": True,
        "revert_policy_required_for_apply": False,
        "proposal_plane_write_required_for_apply": True,
        "human_accept_required_after_apply": True,
        "apply_proposal_kind": "prompt_proposal",
        "apply_target_file": "prompts/ask.md",
        "apply_contract": _deferred_apply_contract("propose"),
        "signal_ids": list(scope_preview.get("signal_ids") or []),
        "trace_ids": list(scope_preview.get("trace_ids") or []),
        "source_ids": list(scope_preview.get("source_ids") or []),
        "concept_slugs": list(scope_preview.get("concept_slugs") or []),
        "judgment_refs": list(scope_preview.get("judgment_refs") or []),
        "elixir_refs": list(scope_preview.get("elixir_refs") or []),
        "severities": list(scope_preview.get("severities") or []),
    }

    candidates: list[dict[str, Any]] = []
    protocol_items = protocols or [""]
    scope_slug = slugify(scope)
    for index, protocol in enumerate(protocol_items, start=1):
        target = protocol or scope
        candidates.append(
            {
                **common,
                "candidate_id": f"propose-scope-{slugify(target) or scope_slug}-{index}",
                "kind": "proposal_opportunity",
                "target_ref": target,
                "protocol": protocol,
                "proposal_kinds": ["prompt_proposal", "policy_proposal"],
                "source_decision": "enqueue-heavy",
                "consumes_generate_proposal_decisions": False,
            }
        )
    return candidates


def _build_budget_used(selected: list[dict[str, Any]]) -> dict[str, int]:
    max_pages = 0
    max_tokens = 0
    for item in selected:
        signal = item["signal"]
        hint = signal.get("budget_hint")
        if not isinstance(hint, dict):
            continue
        max_pages += _non_negative_int(hint.get("max_pages"))
        max_tokens += _non_negative_int(hint.get("max_tokens"))
    return {
        "signals": len(selected),
        "max_pages": max_pages,
        "max_tokens": max_tokens,
    }


def _empty_budget_used() -> dict[str, int]:
    return {
        "signals": 0,
        "max_pages": 0,
        "max_tokens": 0,
    }


def _budget_exceeded(limits: dict[str, int], used: dict[str, int]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if used["signals"] > limits["max_signals"]:
        reasons.append("max_signals_exceeded")
    if used["max_pages"] > limits["max_pages"]:
        reasons.append("max_pages_exceeded")
    if used["max_tokens"] > limits["max_tokens"]:
        reasons.append("max_tokens_exceeded")
    return bool(reasons), reasons


def _preview_runtime_lock(root: Path, *, allow_current_writer: bool = False) -> dict[str, Any]:
    path = runtime_lock_path(root)
    path_label = _path_label(root, path)
    if not path.exists():
        return {"status": "available", "path": path_label, "would_acquire": True}

    local_state = app_utils._RUNTIME_LOCKS.get(str(root.resolve()))  # type: ignore[attr-defined]
    if local_state is not None and int(local_state.get("depth", 0) or 0) > 0:
        if allow_current_writer:
            return {
                "status": "held_by_current_process",
                "path": path_label,
                "would_acquire": False,
            }
        return {
            "status": "conflict",
            "path": path_label,
            "would_acquire": False,
        }

    with path.open("r", encoding="utf-8") as handle:
        owner = _read_lock_owner(handle)
        acquired = False
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            return {
                "status": "conflict",
                "path": path_label,
                "would_acquire": False,
                "owner": owner,
            }
        finally:
            if acquired:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
    return {"status": "available", "path": path_label, "would_acquire": True}


def _read_lock_owner(handle: Any) -> dict[str, Any]:
    try:
        handle.seek(0)
        payload = handle.read().strip()
    except OSError:
        return {}
    if not payload:
        return {}
    try:
        owner = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    if not isinstance(owner, dict):
        return {}
    return owner


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (str(item).strip() for item in value) if item]


def _add_optional(target: set[str], value: Any) -> None:
    if isinstance(value, str) and value.strip():
        target.add(value.strip())


def _sorted_clean(values: set[str]) -> list[str]:
    return sorted(item for item in values if item)


def _non_negative_int(value: Any) -> int:
    if type(value) is int and value > 0:
        return value
    return 0


def _limited_examples(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return items[:_SKIP_EXAMPLES_LIMIT]


__all__ = [
    "preview_alchemy_lane",
    "preview_distill_primitive",
    "preview_judge_primitive",
    "preview_propose_primitive",
    "preview_review_primitive",
]
