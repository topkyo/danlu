from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

PLANNER_LOG_SCHEMA_VERSION: int = 1

DECISIONS: frozenset[str] = frozenset(
    {
        "ignore",
        "enqueue-light",
        "enqueue-heavy",
        "generate-proposal",
        "escalate-human",
    }
)

MODES: frozenset[str] = frozenset({"observe_only", "execute"})

PHASES: frozenset[str] = frozenset({"observe", "light", "heavy", "proposal", "human"})

EXECUTABLE_DECISIONS: frozenset[str] = frozenset({"enqueue-light", "enqueue-heavy", "generate-proposal"})

_PHASE_BY_DECISION: dict[str, str] = {
    "ignore": "observe",
    "enqueue-light": "light",
    "enqueue-heavy": "heavy",
    "generate-proposal": "proposal",
    "escalate-human": "human",
}

TOP_LEVEL_FIELD_ORDER: tuple[str, ...] = (
    "schema_version",
    "signal_id",
    "dedupe_key",
    "trace_id",
    "decision",
    "mode",
    "reason_codes",
    "budget_used",
    "locks_acquired",
    "primitive_refs",
    "side_effects_allowed",
    "decided_at",
)

_REQUIRED_FIELDS: frozenset[str] = frozenset(TOP_LEVEL_FIELD_ORDER)
_OPTIONAL_FIELDS: frozenset[str] = frozenset({"phase"})

_SIGNAL_ID_RE: re.Pattern[str] = re.compile(r"^sig-[0-9]{8}-[a-z0-9]{6,32}$")
_TRACE_ID_RE: re.Pattern[str] = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_DECIDED_AT_RE: re.Pattern[str] = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REASON_CODE_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...]


def validate_planner_log_record(record: dict[str, Any]) -> ValidationResult:
    if not isinstance(record, dict):
        return ValidationResult(ok=False, errors=("record must be an object",))

    errors: list[str] = []

    allowed_fields = _REQUIRED_FIELDS | _OPTIONAL_FIELDS
    for key in record:
        if key not in allowed_fields:
            errors.append(f"unknown top-level field: {key}")

    for field in _REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing required field: {field}")

    schema_version = record.get("schema_version")
    if "schema_version" in record and type(schema_version) is not int:
        errors.append("schema_version must be integer")
    elif type(schema_version) is int and schema_version != PLANNER_LOG_SCHEMA_VERSION:
        errors.append(f"schema_version must be {PLANNER_LOG_SCHEMA_VERSION}")

    signal_id = record.get("signal_id")
    if not isinstance(signal_id, str):
        errors.append("signal_id must be a string")
    elif signal_id == "":
        errors.append("signal_id must be non-empty")
    elif _SIGNAL_ID_RE.fullmatch(signal_id) is None:
        errors.append("signal_id format is invalid")

    dedupe_key = record.get("dedupe_key")
    if not isinstance(dedupe_key, str):
        errors.append("dedupe_key must be a string")
    elif dedupe_key == "":
        errors.append("dedupe_key must be non-empty")

    trace_id = record.get("trace_id")
    if not isinstance(trace_id, str):
        errors.append("trace_id must be a string")
    elif _TRACE_ID_RE.fullmatch(trace_id) is None:
        errors.append("trace_id must be a lowercase UUIDv4")

    decision = record.get("decision")
    if not isinstance(decision, str):
        errors.append("decision must be a string")
    elif decision not in DECISIONS:
        errors.append("decision must be one of the closed-set values")

    mode = record.get("mode")
    if not isinstance(mode, str):
        errors.append("mode must be a string")
    elif mode not in MODES:
        errors.append("mode must be one of the closed-set values")

    phase = record.get("phase")
    if "phase" in record:
        if not isinstance(phase, str):
            errors.append("phase must be a string")
        elif phase not in PHASES:
            errors.append("phase must be one of the closed-set values")
        elif isinstance(decision, str) and decision in _PHASE_BY_DECISION and phase != _PHASE_BY_DECISION[decision]:
            errors.append("phase must match the decision-derived phase")

    reason_codes = record.get("reason_codes")
    if not isinstance(reason_codes, list):
        errors.append("reason_codes must be a non-empty list of strings")
    elif not reason_codes:
        errors.append("reason_codes must be a non-empty list of strings")
    else:
        for index, item in enumerate(reason_codes):
            if not isinstance(item, str):
                errors.append(f"reason_codes[{index}] must be a string")
                continue
            if _REASON_CODE_RE.fullmatch(item) is None:
                errors.append(f"reason_codes[{index}] format is invalid")
        if all(isinstance(item, str) for item in reason_codes):
            if len(set(reason_codes)) != len(reason_codes):
                errors.append("reason_codes contains duplicate values")

    budget_used = record.get("budget_used")
    if not isinstance(budget_used, dict):
        errors.append("budget_used must be an object")
    else:
        for key, value in budget_used.items():
            if key not in {"max_pages", "max_tokens"}:
                errors.append(f"budget_used contains unsupported field: {key}")
                continue
            if type(value) is not int or value <= 0:
                errors.append(f"budget_used.{key} must be a positive integer")

    locks_acquired = record.get("locks_acquired")
    if not isinstance(locks_acquired, list):
        errors.append("locks_acquired must be a list")
    elif locks_acquired:
        errors.append("locks_acquired must be empty list in v1")

    primitive_refs = record.get("primitive_refs")
    if not isinstance(primitive_refs, list):
        errors.append("primitive_refs must be a list")
    elif primitive_refs:
        errors.append("primitive_refs must be empty list in v1")

    side_effects_allowed = record.get("side_effects_allowed")
    if type(side_effects_allowed) is not bool:
        errors.append("side_effects_allowed must be a strict boolean")
    elif mode == "observe_only" and side_effects_allowed is not False:
        errors.append("side_effects_allowed must be false in observe_only mode")
    elif (
        mode == "execute"
        and isinstance(decision, str)
        and not decision_allows_side_effects(decision, mode)
        and side_effects_allowed is not False
    ):
        errors.append("side_effects_allowed must be false for non-executable decisions")

    decided_at = record.get("decided_at")
    if not isinstance(decided_at, str):
        errors.append("decided_at must be a string")
    elif _DECIDED_AT_RE.fullmatch(decided_at) is None:
        errors.append("decided_at must match YYYY-MM-DDTHH:MM:SSZ")

    return ValidationResult(ok=not errors, errors=tuple(errors))


def canonical_dumps_planner_log(record: dict[str, Any]) -> str:
    ordered: dict[str, Any] = {}
    for field in TOP_LEVEL_FIELD_ORDER:
        if field not in record:
            continue
        value = record[field]
        if field == "reason_codes":
            ordered[field] = _canonicalize_reason_codes(value)
        else:
            ordered[field] = value

    for field in sorted(record):
        if field in ordered:
            continue
        value = record[field]
        ordered[field] = value

    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def compute_planner_log_dedupe_key(record: dict[str, Any]) -> str:
    return f"{record['signal_id']}:{record['mode']}"


def phase_for_decision(decision: str) -> str:
    return _PHASE_BY_DECISION.get(decision, "observe")


def decision_allows_side_effects(decision: str, mode: str) -> bool:
    return mode == "execute" and decision in EXECUTABLE_DECISIONS


def _canonicalize_reason_codes(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    if not all(isinstance(item, str) for item in value):
        return value
    return list(dict.fromkeys(value))


__all__ = [
    "DECISIONS",
    "EXECUTABLE_DECISIONS",
    "MODES",
    "PHASES",
    "PLANNER_LOG_SCHEMA_VERSION",
    "TOP_LEVEL_FIELD_ORDER",
    "ValidationResult",
    "canonical_dumps_planner_log",
    "compute_planner_log_dedupe_key",
    "decision_allows_side_effects",
    "phase_for_decision",
    "validate_planner_log_record",
]
