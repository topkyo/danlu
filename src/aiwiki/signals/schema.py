from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...]


SCHEMA_VERSION: int = 1

KINDS: frozenset[str] = frozenset(
    {
        "raw_added",
        "counter_evidence",
        "drift",
        "review_feedback",
        "runtime_failure",
        "schedule_tick",
        "learning_threshold",
        "elixir_dependency_break",
    }
)

SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "runtime_history",
        "llm_receipt",
        "review_outcome",
        "archive_event",
        "protocol_learning_event",
    }
)

EMITTED_BY: frozenset[str] = frozenset({"nightly", "user", "compile", "external"})

PROTOCOLS: frozenset[str] = frozenset({"general", "investing", "research", "product", "ops"})

SEVERITIES: frozenset[str] = frozenset({"low", "medium", "high", "critical"})

TOP_LEVEL_FIELD_ORDER: tuple[str, ...] = (
    "schema_version",
    "signal_id",
    "dedupe_key",
    "kind",
    "scope",
    "severity",
    "evidence_refs",
    "budget_hint",
    "emitted_at",
    "emitted_by",
    "source_kind",
    "source_event_ref",
    "trace_id",
)

SCOPE_FIELD_ORDER: tuple[str, ...] = (
    "protocol",
    "corpus_id",
    "source_ids",
    "concept_slugs",
    "elixir_refs",
    "judgment_refs",
)

BUDGET_HINT_FIELD_ORDER: tuple[str, ...] = (
    "max_pages",
    "max_tokens",
)

SORTED_LIST_FIELDS: frozenset[str] = frozenset(
    {
        "evidence_refs",
        "scope.source_ids",
        "scope.concept_slugs",
        "scope.elixir_refs",
        "scope.judgment_refs",
    }
)

VOLATILE_FIELDS: frozenset[str] = frozenset(
    {
        "signal_id",
        "severity",
        "evidence_refs",
        "budget_hint",
        "emitted_at",
        "emitted_by",
        "source_event_ref",
        "trace_id",
    }
)

REQUIRED_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "schema_version",
        "signal_id",
        "dedupe_key",
        "kind",
        "scope",
        "severity",
        "evidence_refs",
        "emitted_at",
        "emitted_by",
        "source_kind",
        "source_event_ref",
        "trace_id",
    }
)

OPTIONAL_TOP_LEVEL: frozenset[str] = frozenset({"budget_hint"})

SIGNAL_ID_RE: re.Pattern[str] = re.compile(r"^sig-[0-9]{8}-[a-z0-9]{6,32}$")
TRACE_ID_RE: re.Pattern[str] = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
EMITTED_AT_RE: re.Pattern[str] = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SOURCE_EVENT_REF_LINE_RE: re.Pattern[str] = re.compile(r"^(?P<path>.+)#L(?P<line>[1-9][0-9]*)$")
_SOURCE_EVENT_REF_ROW_RE: re.Pattern[str] = re.compile(r"^(?P<path>.+):(?P<row_or_id>[^:#\s][^#\s]*)$")

_SCOPE_REQUIRED: frozenset[str] = frozenset(
    {
        "protocol",
        "source_ids",
        "concept_slugs",
        "elixir_refs",
        "judgment_refs",
    }
)
_SCOPE_OPTIONAL: frozenset[str] = frozenset({"corpus_id"})
_BUDGET_FIELDS: frozenset[str] = frozenset({"max_pages", "max_tokens"})


def validate(record: dict[str, Any]) -> ValidationResult:
    """按 §2.5 fail-fast 规则校验 signal record。"""
    if not isinstance(record, dict):
        return ValidationResult(ok=False, errors=("record must be an object",))

    errors: list[str] = []
    _collect_v1_forbidden_values(record, "$", errors)

    known_top_level = REQUIRED_TOP_LEVEL | OPTIONAL_TOP_LEVEL
    for key in record:
        if key not in known_top_level:
            errors.append(f"unknown top-level field: {key}")

    for field in REQUIRED_TOP_LEVEL:
        if field not in record:
            errors.append(f"missing required field: {field}")

    schema_version = record.get("schema_version")
    if "schema_version" in record and type(schema_version) is not int:
        errors.append("schema_version must be integer")
    elif type(schema_version) is int and schema_version != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    _validate_string_field(record, "signal_id", errors)
    signal_id = record.get("signal_id")
    if isinstance(signal_id, str) and not SIGNAL_ID_RE.fullmatch(signal_id):
        errors.append("signal_id format is invalid")

    _validate_string_field(record, "dedupe_key", errors)

    _validate_string_field(record, "kind", errors)
    kind = record.get("kind")
    if isinstance(kind, str) and kind not in KINDS:
        errors.append("kind must be one of the closed-set values")

    scope = record.get("scope")
    if "scope" in record and not isinstance(scope, dict):
        errors.append("scope must be an object")
    elif isinstance(scope, dict):
        _validate_scope(scope, errors)

    _validate_string_field(record, "severity", errors)
    severity = record.get("severity")
    if isinstance(severity, str) and severity not in SEVERITIES:
        errors.append("severity must be one of the closed-set values")

    _validate_string_list("evidence_refs", record.get("evidence_refs"), errors)

    if "budget_hint" in record:
        budget_hint = record.get("budget_hint")
        if not isinstance(budget_hint, dict):
            errors.append("budget_hint must be an object")
        else:
            _validate_budget_hint(budget_hint, errors)

    _validate_string_field(record, "emitted_at", errors)
    emitted_at = record.get("emitted_at")
    if isinstance(emitted_at, str) and not EMITTED_AT_RE.fullmatch(emitted_at):
        errors.append("emitted_at must match YYYY-MM-DDTHH:MM:SSZ")

    _validate_string_field(record, "emitted_by", errors)
    emitted_by = record.get("emitted_by")
    if isinstance(emitted_by, str) and emitted_by not in EMITTED_BY:
        errors.append("emitted_by must be one of the closed-set values")

    _validate_string_field(record, "source_kind", errors)
    source_kind = record.get("source_kind")
    if isinstance(source_kind, str) and source_kind not in SOURCE_KINDS:
        errors.append("source_kind must be one of the closed-set values")

    _validate_string_field(record, "source_event_ref", errors)
    source_event_ref = record.get("source_event_ref")
    if isinstance(source_kind, str) and isinstance(source_event_ref, str):
        _validate_source_event_ref(source_kind, source_event_ref, errors)

    _validate_string_field(record, "trace_id", errors)
    trace_id = record.get("trace_id")
    if isinstance(trace_id, str):
        try:
            parse_trace_id(trace_id)
        except ValueError as exc:
            errors.append(str(exc))

    return ValidationResult(ok=not errors, errors=tuple(errors))


def canonical_dumps(record: dict[str, Any]) -> str:
    """按 §2.2 序列化为 canonical JSON 单行字符串。"""
    canonical = _canonicalize_top_level(record)
    return json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def compute_dedupe_key(record: dict[str, Any], source_identity: str) -> str:
    """按 §2.3 生成 dedupe_key。"""
    if not isinstance(source_identity, str) or source_identity == "":
        raise ValueError("source_identity must be a non-empty string")

    kind = record.get("kind")
    source_kind = record.get("source_kind")
    scope = record.get("scope")
    protocol = scope.get("protocol") if isinstance(scope, dict) else None

    if not isinstance(kind, str):
        raise ValueError("record.kind must be a string")
    if not isinstance(protocol, str):
        raise ValueError("record.scope.protocol must be a string")
    if not isinstance(source_kind, str):
        raise ValueError("record.source_kind must be a string")

    return f"{kind}:{protocol}:{source_kind}:{source_identity}"


def parse_trace_id(raw: str) -> str:
    """按 §2.4 校验 lowercase UUIDv4。"""
    if not isinstance(raw, str):
        raise ValueError("trace_id must be a string")
    if not TRACE_ID_RE.fullmatch(raw):
        raise ValueError("trace_id must be a lowercase UUIDv4")

    parsed = uuid.UUID(raw)
    if parsed.version != 4 or str(parsed) != raw:
        raise ValueError("trace_id must be a lowercase UUIDv4")
    return raw


def detect_trace_id_conflict(existing_records: Iterable[dict[str, Any]], new_record: dict[str, Any]) -> bool:
    """同 dedupe_key 不同 trace_id 时返回 True。"""
    new_dedupe_key = new_record.get("dedupe_key")
    new_trace_id = new_record.get("trace_id")
    if not isinstance(new_dedupe_key, str) or not isinstance(new_trace_id, str):
        return False

    for existing in existing_records:
        if not isinstance(existing, dict):
            continue
        existing_dedupe_key = existing.get("dedupe_key")
        existing_trace_id = existing.get("trace_id")
        if isinstance(existing_dedupe_key, str) and existing_dedupe_key == new_dedupe_key and existing_trace_id != new_trace_id:
            return True
    return False


def _validate_scope(scope: dict[str, Any], errors: list[str]) -> None:
    known_scope_fields = _SCOPE_REQUIRED | _SCOPE_OPTIONAL
    for key in scope:
        if key not in known_scope_fields:
            errors.append(f"unknown nested field in scope: {key}")

    for field in _SCOPE_REQUIRED:
        if field not in scope:
            errors.append(f"missing required field: scope.{field}")

    protocol = scope.get("protocol")
    if "protocol" in scope and not isinstance(protocol, str):
        errors.append("scope.protocol must be a string")
    elif isinstance(protocol, str) and protocol not in PROTOCOLS:
        errors.append("scope.protocol must be one of the closed-set values")

    corpus_id = scope.get("corpus_id")
    if "corpus_id" in scope and not isinstance(corpus_id, str):
        errors.append("scope.corpus_id must be a string")

    _validate_string_list("scope.source_ids", scope.get("source_ids"), errors)
    _validate_string_list("scope.concept_slugs", scope.get("concept_slugs"), errors)
    _validate_string_list("scope.elixir_refs", scope.get("elixir_refs"), errors)
    _validate_string_list("scope.judgment_refs", scope.get("judgment_refs"), errors)


def _validate_budget_hint(budget_hint: dict[str, Any], errors: list[str]) -> None:
    for key in budget_hint:
        if key not in _BUDGET_FIELDS:
            errors.append(f"unknown nested field in budget_hint: {key}")

    has_max_pages = "max_pages" in budget_hint
    has_max_tokens = "max_tokens" in budget_hint
    if not has_max_pages and not has_max_tokens:
        errors.append("budget_hint must contain at least one of max_pages/max_tokens")

    if has_max_pages and not _is_positive_int(budget_hint.get("max_pages")):
        errors.append("budget_hint.max_pages must be a positive integer")

    if has_max_tokens and not _is_positive_int(budget_hint.get("max_tokens")):
        errors.append("budget_hint.max_tokens must be a positive integer")


def _validate_source_event_ref(source_kind: str, source_event_ref: str, errors: list[str]) -> None:
    path = _parse_source_event_ref_path(source_kind, source_event_ref, errors)
    if path is None:
        return

    if _is_unsafe_source_event_ref_path(path):
        errors.append("source_event_ref path must be relative and cannot contain '..'")
        return

    ref = path.lower()
    allowed_substrings = {
        "runtime_history": ("runtime-history.jsonl", "runtime_history.jsonl"),
        "llm_receipt": (
            "llm-receipts.jsonl",
            "llm_receipts.jsonl",
            "llm-receipt.jsonl",
            "llm_receipt.jsonl",
        ),
        "review_outcome": ("review",),
        "archive_event": ("archive",),
        "protocol_learning_event": (
            "protocol_learning",
            "protocol-learning",
            "protocol_learnings",
        ),
    }

    allowed = allowed_substrings.get(source_kind)
    if allowed is None:
        return
    if not any(fragment in ref for fragment in allowed):
        errors.append(f"source_event_ref mismatches source_kind={source_kind}")


def _parse_source_event_ref_path(source_kind: str, source_event_ref: str, errors: list[str]) -> str | None:
    line_match = _SOURCE_EVENT_REF_LINE_RE.fullmatch(source_event_ref)
    if line_match is not None:
        return line_match.group("path")

    row_match = _SOURCE_EVENT_REF_ROW_RE.fullmatch(source_event_ref)
    if row_match is not None:
        if source_kind != "protocol_learning_event":
            errors.append("source_event_ref must end with #L<positive integer> for this source_kind")
            return None
        return row_match.group("path")

    if source_kind == "protocol_learning_event":
        errors.append("source_event_ref must end with #L<positive integer> or :<row_or_id>")
    else:
        errors.append("source_event_ref must end with #L<positive integer>")
    return None


def _is_unsafe_source_event_ref_path(path: str) -> bool:
    if path.startswith("/"):
        return True

    for segment in path.split("/"):
        if segment == "..":
            return True

    return False


def _validate_string_field(record: dict[str, Any], field: str, errors: list[str]) -> None:
    if field not in record:
        return
    value = record.get(field)
    if value is None:
        errors.append(f"required field {field} cannot be null")
        return
    if not isinstance(value, str):
        errors.append(f"{field} must be a string")


def _validate_string_list(field: str, value: Any, errors: list[str]) -> None:
    if value is None:
        errors.append(f"required field {field} cannot be null")
        return
    if not isinstance(value, list):
        errors.append(f"{field} must be a list of strings")
        return

    for index, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{field}[{index}] must be a string")

    if not all(isinstance(item, str) for item in value):
        return

    unique_sorted = sorted(set(value))
    if len(unique_sorted) != len(value):
        errors.append(f"{field} contains duplicate values")
    if value != unique_sorted:
        errors.append(f"{field} must be sorted lexicographically with duplicates removed")


def _collect_v1_forbidden_values(value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        errors.append(f"v1 forbids null value at {path}")
        return
    if type(value) is float:
        errors.append(f"v1 forbids float value at {path}")
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            child_path = f"{path}.{key}"
            _collect_v1_forbidden_values(nested, child_path, errors)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            child_path = f"{path}[{index}]"
            _collect_v1_forbidden_values(nested, child_path, errors)


def _is_positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _canonicalize_top_level(record: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for field in TOP_LEVEL_FIELD_ORDER:
        if field not in record:
            continue
        value = record[field]
        if field == "scope" and isinstance(value, dict):
            ordered[field] = _canonicalize_scope(value)
        elif field == "budget_hint" and isinstance(value, dict):
            ordered[field] = _canonicalize_budget_hint(value)
        elif field == "evidence_refs":
            ordered[field] = _canonicalize_sorted_list(value)
        else:
            ordered[field] = value

    for field in sorted(record):
        if field in ordered:
            continue
        value = record[field]
        if field == "scope" and isinstance(value, dict):
            ordered[field] = _canonicalize_scope(value)
        elif field == "budget_hint" and isinstance(value, dict):
            ordered[field] = _canonicalize_budget_hint(value)
        elif field == "evidence_refs":
            ordered[field] = _canonicalize_sorted_list(value)
        else:
            ordered[field] = value
    return ordered


def _canonicalize_scope(scope: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for field in SCOPE_FIELD_ORDER:
        if field not in scope:
            continue
        value = scope[field]
        if f"scope.{field}" in SORTED_LIST_FIELDS:
            ordered[field] = _canonicalize_sorted_list(value)
        else:
            ordered[field] = value

    for field in sorted(scope):
        if field in ordered:
            continue
        value = scope[field]
        if f"scope.{field}" in SORTED_LIST_FIELDS:
            ordered[field] = _canonicalize_sorted_list(value)
        else:
            ordered[field] = value
    return ordered


def _canonicalize_budget_hint(budget_hint: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for field in BUDGET_HINT_FIELD_ORDER:
        if field in budget_hint:
            ordered[field] = budget_hint[field]

    for field in sorted(budget_hint):
        if field in ordered:
            continue
        ordered[field] = budget_hint[field]
    return ordered


def _canonicalize_sorted_list(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    if not all(isinstance(item, str) for item in value):
        return value
    return sorted(set(value))


__all__ = [
    "BUDGET_HINT_FIELD_ORDER",
    "EMITTED_AT_RE",
    "EMITTED_BY",
    "KINDS",
    "OPTIONAL_TOP_LEVEL",
    "PROTOCOLS",
    "REQUIRED_TOP_LEVEL",
    "SCHEMA_VERSION",
    "SEVERITIES",
    "SIGNAL_ID_RE",
    "SCOPE_FIELD_ORDER",
    "SORTED_LIST_FIELDS",
    "SOURCE_KINDS",
    "TOP_LEVEL_FIELD_ORDER",
    "TRACE_ID_RE",
    "VOLATILE_FIELDS",
    "ValidationResult",
    "canonical_dumps",
    "compute_dedupe_key",
    "detect_trace_id_conflict",
    "parse_trace_id",
    "validate",
]
