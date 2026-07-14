"""Pure knowledge lifecycle selection, display, and summary helpers."""

from __future__ import annotations

from typing import Any

from ..app_state import DEFAULT_PROTOCOL, KNOWLEDGE_LIFECYCLE_KINDS, KNOWLEDGE_LIFECYCLE_STATES


def knowledge_lifecycle_counts(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_state = {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}
    by_kind = {
        kind: {"total": 0, "by_state": {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}}
        for kind in KNOWLEDGE_LIFECYCLE_KINDS
    }
    invalidated = 0
    active_corpus_linked = 0
    for entry in entries:
        lifecycle_state = str(entry.get("lifecycle_state") or "")
        kind = str(entry.get("kind") or "")
        if lifecycle_state in by_state:
            by_state[lifecycle_state] += 1
        if kind in by_kind:
            by_kind[kind]["total"] += 1
            if lifecycle_state in by_kind[kind]["by_state"]:
                by_kind[kind]["by_state"][lifecycle_state] += 1
        if entry.get("invalidation_signals"):
            invalidated += 1
        if entry.get("active_corpus_ids"):
            active_corpus_linked += 1
    return {
        "total": len(entries),
        "by_state": by_state,
        "by_kind": by_kind,
        "invalidated": invalidated,
        "active_corpus_linked": active_corpus_linked,
    }


def display_knowledge_lifecycle_state(state: str) -> str:
    mapping = {
        "active": "活跃",
        "review": "待审",
        "deferred": "暂挂",
        "retired": "已退役",
        "revisit": "待回看",
    }
    return mapping.get(state, state or "unknown")


def display_judgment_lifecycle_state(state: str) -> str:
    mapping = {
        "formed": "已形成",
        "active": "活跃",
        "under-review": "复审中",
        "revised": "已修订",
        "retired": "已退役",
    }
    return mapping.get(state, state or "unknown")


def display_protocol_relevance_mode(mode: str) -> str:
    mapping = {
        "source-top1": "top1",
        "strong-top2": "strong-top2",
        "cross-protocol-bridge": "bridge-top2",
    }
    return mapping.get(mode, mode or "unknown")


def display_protocol_relevance_ambiguity(state: str) -> str:
    mapping = {
        "dominant": "dominant",
        "mixed": "mixed",
        "bridge": "bridge",
    }
    return mapping.get(state, state or "unknown")


def select_knowledge_lifecycle_entries(
    knowledge_lifecycle: dict[str, Any],
    *,
    kinds: set[str] | None = None,
    states: set[str] | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for entry in knowledge_lifecycle.get("entries", []):
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "")
        lifecycle_state = str(entry.get("lifecycle_state") or "")
        if kinds is not None and kind not in kinds:
            continue
        if states is not None and lifecycle_state not in states:
            continue
        selected.append(dict(entry))
    return selected


def sort_knowledge_lifecycle_entries(
    entries: list[dict[str, Any]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    state_rank = {"revisit": 0, "review": 1, "active": 2, "deferred": 3, "retired": 4}
    return sorted(
        entries,
        key=lambda entry: (
            state_rank.get(str(entry.get("lifecycle_state") or ""), 9),
            0 if str(entry.get("protocol") or "") == active_protocol and active_protocol else 1,
            0 if bool(entry.get("override_active")) else 1,
            -len(entry.get("invalidation_signals", []) if isinstance(entry.get("invalidation_signals"), list) else []),
            -len(entry.get("active_corpus_ids", []) if isinstance(entry.get("active_corpus_ids"), list) else []),
            str(entry.get("title") or "").lower(),
        ),
    )


def render_knowledge_lifecycle_entry_summary(entry: dict[str, Any]) -> str:
    title = str(entry.get("title") or entry.get("page_id") or "unknown")
    path = str(entry.get("path") or "")
    kind = str(entry.get("kind") or "knowledge")
    lifecycle_state = str(entry.get("lifecycle_state") or "")
    parts = [
        f"kind `{kind}`",
        f"state `{display_knowledge_lifecycle_state(lifecycle_state)}`",
    ]
    judgment_lifecycle_state = str(entry.get("judgment_lifecycle_state") or "")
    if kind in {"decision", "judgment"} and judgment_lifecycle_state:
        parts.append(f"judgment_state `{display_judgment_lifecycle_state(judgment_lifecycle_state)}`")
    if bool(entry.get("override_active")):
        parts.append(f"override `{str(entry.get('override_state') or lifecycle_state or 'unknown')}`")
    invalidation_signals = entry.get("invalidation_signals", [])
    if isinstance(invalidation_signals, list) and invalidation_signals:
        parts.append(f"invalidation `{','.join(str(item) for item in invalidation_signals[:3])}`")
    active_corpus_ids = entry.get("active_corpus_ids", [])
    if isinstance(active_corpus_ids, list) and active_corpus_ids:
        parts.append(f"active_corpora `{len(active_corpus_ids)}`")
    review_signal_codes = entry.get("review_signal_codes", [])
    if isinstance(review_signal_codes, list) and review_signal_codes:
        parts.append(f"review_signals `{','.join(str(item) for item in review_signal_codes[:3])}`")
    reason_codes = entry.get("reason_codes", [])
    if isinstance(reason_codes, list) and reason_codes:
        parts.append(f"reasons `{','.join(str(item) for item in reason_codes[:3])}`")
    protocol_relevance_mode = str(entry.get("protocol_relevance_primary_mode") or "")
    if protocol_relevance_mode:
        parts.append(f"protocol_relevance `{display_protocol_relevance_mode(protocol_relevance_mode)}`")
    protocol_relevance_ambiguity = str(entry.get("protocol_relevance_ambiguity") or "")
    if protocol_relevance_ambiguity:
        parts.append(f"protocol_ambiguity `{display_protocol_relevance_ambiguity(protocol_relevance_ambiguity)}`")
    return f"- [{title}](../../{path}) | " + " | ".join(parts)
