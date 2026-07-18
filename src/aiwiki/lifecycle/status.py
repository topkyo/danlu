"""Pure lifecycle status and transition helpers."""

from __future__ import annotations

from typing import Any

from ..app_protocol import (
    DECISION_STATUSES,
    JUDGMENT_STATUSES,
    PENDING_ACTION_STATUSES,
    PENDING_DECISION_REVIEW_STATUSES,
    PENDING_JUDGMENT_REVIEW_STATUSES,
    PENDING_REWRITE_PROPOSAL_STATUSES,
)

THIN_REVIEW_TRANSITIONS = ("pending-review", "confirmed", "discarded")

_PENDING_CURATED_STATUSES = frozenset({"proposed", "needs-revisit", "tentative", "tracking"})
_CONFIRMED_CURATED_STATUSES = frozenset({"approved", "confirmed"})
_DISCARDED_CURATED_STATUSES = frozenset({"superseded", "rejected"})


def default_curated_status(kind: str) -> str:
    if kind == "decision":
        return "proposed"
    if kind == "judgment":
        return "tentative"
    return "filed"


def valid_curated_statuses(kind: str) -> tuple[str, ...]:
    if kind == "decision":
        return DECISION_STATUSES
    if kind == "judgment":
        return JUDGMENT_STATUSES
    return ()


def page_needs_review(kind: str, status: str) -> bool:
    if kind == "decision":
        return status in PENDING_DECISION_REVIEW_STATUSES
    if kind == "judgment":
        return status in PENDING_JUDGMENT_REVIEW_STATUSES
    return False


def thin_curated_status_group(status: str) -> str:
    normalized = str(status or "").strip()
    if normalized in _PENDING_CURATED_STATUSES:
        return "pending-review"
    if normalized in _CONFIRMED_CURATED_STATUSES:
        return "confirmed"
    if normalized in _DISCARDED_CURATED_STATUSES:
        return "discarded"
    return normalized


def display_curated_status(status: str) -> str:
    thin = thin_curated_status_group(status)
    mapping = {
        "pending-review": "待审",
        "confirmed": "已确认",
        "discarded": "废弃",
        "filed": "已归档",
    }
    if thin in mapping:
        return mapping[thin]
    return status or "unknown"


def resolve_thin_review_transition(kind: str, current_status: str, transition: str) -> str:
    """Map thin review transition tokens (or legacy canonical statuses) to curated status."""
    normalized_kind = str(kind or "").strip()
    normalized_transition = str(transition or "").strip()
    normalized_current = str(current_status or "").strip()
    valid_statuses = valid_curated_statuses(normalized_kind)
    if normalized_transition in valid_statuses:
        return normalized_transition
    if normalized_kind == "decision":
        resolved = {
            "pending-review": "needs-revisit",
            "confirmed": "approved",
            "discarded": "superseded",
        }.get(normalized_transition)
    elif normalized_kind == "judgment":
        resolved = {
            "pending-review": "tracking",
            "confirmed": "confirmed",
            "discarded": "rejected",
        }.get(normalized_transition)
    else:
        resolved = None
    if not resolved or resolved not in valid_statuses:
        thin_hint = ", ".join(THIN_REVIEW_TRANSITIONS)
        canonical_hint = ", ".join(valid_statuses)
        raise ValueError(
            f"Unsupported review transition for {normalized_kind}: {normalized_transition!r}; "
            f"expected one of: ({thin_hint}) or canonical ({canonical_hint}) "
            f"from current status {normalized_current!r}"
        )
    allowed = curated_page_transition_profile(normalized_kind, normalized_current).get("allowed_transitions", [])
    thin_token = normalized_transition if normalized_transition in THIN_REVIEW_TRANSITIONS else None
    if thin_token and thin_token not in allowed:
        raise ValueError(
            f"Review transition {normalized_transition!r} is not allowed from current status "
            f"{normalized_current!r} for {normalized_kind} pages."
        )
    return resolved


def action_needs_review(status: str) -> bool:
    return status in PENDING_ACTION_STATUSES


def display_action_status(status: str) -> str:
    mapping = {
        "proposed": "待处理",
        "accepted": "已接受",
        "deferred": "暂缓",
        "resolved": "已解决",
        "rejected": "已拒绝",
    }
    return mapping.get(status, status or "unknown")


def rewrite_proposal_needs_review(status: str) -> bool:
    return status in PENDING_REWRITE_PROPOSAL_STATUSES


def display_rewrite_proposal_status(status: str) -> str:
    mapping = {
        "proposed": "待审提案",
        "accepted": "已接受提案",
        "deferred": "暂缓提案",
        "applied": "已应用",
        "rejected": "已拒绝",
    }
    return mapping.get(status, status or "unknown")


def rewrite_proposal_status_rank(status: str) -> int:
    return {"proposed": 0, "accepted": 1, "deferred": 2, "applied": 3, "rejected": 4}.get(status, 9)


def transition_profile(
    allowed_transitions: list[str],
    *,
    preferred_transitions: list[str] | None = None,
    default_transition: str = "",
) -> dict[str, Any]:
    allowed = [str(item).strip() for item in allowed_transitions if str(item).strip()]
    preferred = [str(item).strip() for item in (preferred_transitions or []) if str(item).strip() in allowed]
    default_value = str(default_transition or "").strip()
    if default_value not in allowed:
        default_value = preferred[0] if preferred else (allowed[0] if allowed else "")
    return {
        "allowed_transitions": allowed,
        "preferred_transitions": preferred,
        "default_transition": default_value,
    }


def curated_page_transition_profile(kind: str, status: str) -> dict[str, Any]:
    normalized_kind = str(kind or "").strip()
    normalized_status = str(status or "").strip()
    if normalized_kind not in {"decision", "judgment"}:
        return transition_profile([])

    confirmed_status = "approved" if normalized_kind == "decision" else "confirmed"
    discarded_status = "superseded" if normalized_kind == "decision" else "rejected"
    pending_statuses = {"proposed", "needs-revisit"} if normalized_kind == "decision" else {"tentative", "tracking"}

    if normalized_status == discarded_status:
        return transition_profile([])

    allowed: list[str] = []
    preferred: list[str] = []
    default_transition = ""

    if normalized_status != confirmed_status:
        allowed.append("confirmed")
        preferred.append("confirmed")
        default_transition = "confirmed"

    allowed.append("discarded")

    if normalized_status not in pending_statuses:
        allowed.append("pending-review")
        if not default_transition:
            default_transition = "pending-review"

    return transition_profile(
        allowed,
        preferred_transitions=preferred,
        default_transition=default_transition,
    )


def rewrite_transition_profile(status: str) -> dict[str, Any]:
    if status == "proposed":
        return transition_profile(
            ["accepted", "deferred", "rejected"],
            preferred_transitions=["accepted", "deferred"],
            default_transition="accepted",
        )
    if status == "accepted":
        return transition_profile(
            ["deferred", "rejected"],
            preferred_transitions=["deferred"],
            default_transition="deferred",
        )
    if status == "deferred":
        return transition_profile(
            ["accepted", "rejected"],
            preferred_transitions=["accepted"],
            default_transition="accepted",
        )
    return transition_profile([])


def action_transition_profile(status: str) -> dict[str, Any]:
    if status == "proposed":
        return transition_profile(
            ["accepted", "deferred", "rejected"],
            preferred_transitions=["accepted", "deferred"],
            default_transition="accepted",
        )
    if status == "accepted":
        return transition_profile(
            ["resolved", "deferred", "rejected"],
            preferred_transitions=["resolved", "deferred"],
            default_transition="resolved",
        )
    if status == "deferred":
        return transition_profile(
            ["accepted", "resolved", "rejected"],
            preferred_transitions=["accepted", "resolved"],
            default_transition="accepted",
        )
    return transition_profile([])


def archive_transition_profile(*, can_apply: bool, can_revert: bool) -> dict[str, Any]:
    if can_apply:
        return transition_profile(["apply"], preferred_transitions=["apply"], default_transition="apply")
    if can_revert:
        return transition_profile(["revert"], preferred_transitions=["revert"], default_transition="revert")
    return transition_profile([])
