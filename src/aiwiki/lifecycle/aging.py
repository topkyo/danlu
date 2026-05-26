"""Lifecycle aging signal helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from ..app_protocol import page_focus_score
from ..app_state import DEFAULT_PROTOCOL
from ..app_utils import parse_iso_datetime


def evaluate_page_aging(page: dict[str, str], now: datetime | None = None) -> dict[str, str]:
    now = now or datetime.now(timezone.utc)
    revisit_after = parse_iso_datetime(page.get("revisit_after", ""))
    escalate_after = parse_iso_datetime(page.get("escalate_after", ""))
    overdue = bool(revisit_after and revisit_after <= now)
    escalated = bool(escalate_after and escalate_after <= now)
    aging_state = ""
    if escalated:
        aging_state = "escalated"
    elif overdue:
        aging_state = "overdue"
    elif revisit_after:
        aging_state = "scheduled"
    return {
        "revisit_after": revisit_after.replace(microsecond=0).isoformat() if revisit_after else "",
        "escalate_after": escalate_after.replace(microsecond=0).isoformat() if escalate_after else "",
        "aging_state": aging_state,
        "overdue_review": "true" if overdue else "false",
        "escalation_candidate": "true" if escalated else "false",
    }


def collect_aging_signals(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, list[dict[str, str]]]:
    pages = decisions + judgments
    overdue = sorted(
        [page for page in pages if page.get("overdue_review") == "true"],
        key=lambda page: (
            -page_focus_score(active_protocol, page),
            page.get("revisit_after", "") or "9999",
            page["title"].lower(),
        ),
    )
    escalated = sorted(
        [page for page in pages if page.get("escalation_candidate") == "true"],
        key=lambda page: (
            -page_focus_score(active_protocol, page),
            page.get("escalate_after", "") or "9999",
            page["title"].lower(),
        ),
    )
    scheduled = sorted(
        [page for page in pages if page.get("aging_state") == "scheduled"],
        key=lambda page: (
            -page_focus_score(active_protocol, page),
            page.get("revisit_after", "") or "9999",
            page["title"].lower(),
        ),
    )
    return {
        "overdue": overdue,
        "escalated": escalated,
        "scheduled": scheduled,
    }

