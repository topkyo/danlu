"""Recurring-output classification and promotion helpers extracted from app_content (EP-017C step 3)."""

from __future__ import annotations

import re

from ..app_protocol import (
    DECISION_QUERY_MARKERS,
    JUDGMENT_QUERY_MARKERS,
    PROTOCOL_CLASSIFICATION_MARKERS,
    PROTOCOL_PROMOTION_PREFIXES,
)
from ..app_state import DEFAULT_PROTOCOL


def normalize_query_signature(query: str) -> str:
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", query.lower())
    signature = "-".join(tokens).strip("-")
    return signature[:160] or "query"


def classify_recurring_output_kind(query: str, protocol: str = DEFAULT_PROTOCOL) -> str:
    normalized = " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", query.lower()))
    protocol_markers = PROTOCOL_CLASSIFICATION_MARKERS.get(protocol, PROTOCOL_CLASSIFICATION_MARKERS[DEFAULT_PROTOCOL])
    decision_markers = DECISION_QUERY_MARKERS + tuple(protocol_markers.get("decision", ()))
    judgment_markers = JUDGMENT_QUERY_MARKERS + tuple(protocol_markers.get("judgment", ()))
    decision_score = sum(1 for marker in decision_markers if marker in normalized)
    judgment_score = sum(1 for marker in judgment_markers if marker in normalized)
    if decision_score <= 0 and judgment_score <= 0:
        return ""
    if decision_score >= judgment_score:
        return "decision"
    return "judgment"


def promotion_page_title(kind: str, query: str, protocol: str = DEFAULT_PROTOCOL) -> str:
    prefix = PROTOCOL_PROMOTION_PREFIXES.get(protocol, PROTOCOL_PROMOTION_PREFIXES[DEFAULT_PROTOCOL]).get(
        kind,
        "决策沉淀" if kind == "decision" else "判断沉淀",
    )
    return f"{prefix}：{query}"
