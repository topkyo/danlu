"""Signal schema utilities."""

from .schema import (
    SCHEMA_VERSION,
    ValidationResult,
    canonical_dumps,
    compute_dedupe_key,
    detect_trace_id_conflict,
    parse_trace_id,
    validate,
)

__all__ = [
    "SCHEMA_VERSION",
    "ValidationResult",
    "canonical_dumps",
    "compute_dedupe_key",
    "detect_trace_id_conflict",
    "parse_trace_id",
    "validate",
]
