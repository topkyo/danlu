"""Pure helpers for alchemy execution."""

from __future__ import annotations

from typing import Any

_CONFIDENCE_LEVELS = {"low", "medium", "high"}


def validate_promote_gate(frontmatter: dict[str, Any]) -> None:
    """Validate promotion-only counter-evidence and confidence frontmatter."""
    if "counter_evidence" not in frontmatter:
        raise ValueError("counter_evidence_required: counter_evidence is required")
    counter_evidence = frontmatter.get("counter_evidence")
    if not isinstance(counter_evidence, list):
        raise ValueError("counter_evidence_invalid_format: counter_evidence must be a list")
    if not counter_evidence:
        raise ValueError("counter_evidence_required: counter_evidence cannot be empty")
    for item in counter_evidence:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("counter_evidence_invalid_format: counter_evidence items must be non-empty strings")

    confidence_level = str(frontmatter.get("confidence_level") or "").strip()
    has_none_found = any(item.strip() == "NONE_FOUND" for item in counter_evidence)
    if has_none_found:
        if len(counter_evidence) > 1:
            raise ValueError("counter_evidence_invalid_format: NONE_FOUND must be the only counter_evidence item")
        if counter_evidence[0].strip() != "NONE_FOUND":
            raise ValueError("counter_evidence_invalid_format: NONE_FOUND must be the only counter_evidence item")
        if confidence_level != "low":
            raise ValueError("none_found_requires_low_confidence: [NONE_FOUND] requires confidence_level=low")
        return
    if confidence_level not in _CONFIDENCE_LEVELS:
        raise ValueError("confidence_level_required: confidence_level must be one of low/medium/high")
