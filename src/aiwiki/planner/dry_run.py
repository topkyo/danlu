from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any

from .. import app_utils
from ..app_utils import relative_path, runtime_lock_path
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
    ),
    "light": (
        ("route", "Preview active corpus cooling and maintenance scope."),
        ("compile", "Preview metadata and index refresh only."),
        ("lint", "Preview read-only drift and aging checks."),
        ("nightly", "Preview deterministic nightly health refresh."),
    ),
}


def preview_alchemy_lane(
    root: Path,
    *,
    lane: str,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
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

    lock = _preview_runtime_lock(root)
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
            "selected_count": 0,
            "skipped_count": len(decisions),
            "scope_preview": _empty_scope_preview(),
            "primitive_plan": [],
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
        "selected_count": len(selected),
        "skipped_count": skipped_count,
        "scope_preview": scope_preview,
        "primitive_plan": _primitive_plan(normalized_lane, scope_preview),
        "budget": {
            "limits": budget_limits,
            "used": budget_used,
            "exceeded": budget_exceeded,
            "reason_codes": budget_reasons,
        },
        "lock": lock,
        "skip_examples": _limited_examples(signal_skip_examples + decision_skip_examples),
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
        plan.append(
            {
                "order": index,
                "primitive": primitive,
                "description": description,
                "dry_run_only": True,
                "signal_ids": signal_ids,
                "protocols": protocols,
            }
        )
    return plan


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


def _preview_runtime_lock(root: Path) -> dict[str, Any]:
    path = runtime_lock_path(root)
    path_label = _path_label(root, path)
    if not path.exists():
        return {"status": "available", "path": path_label, "would_acquire": True}

    local_state = app_utils._RUNTIME_LOCKS.get(str(root.resolve()))  # type: ignore[attr-defined]
    if local_state is not None and int(local_state.get("depth", 0) or 0) > 0:
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


__all__ = ["preview_alchemy_lane"]
