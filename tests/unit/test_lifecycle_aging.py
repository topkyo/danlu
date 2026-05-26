from __future__ import annotations

from datetime import datetime, timezone

from aiwiki.app_lifecycle import collect_aging_signals as legacy_collect_aging_signals
from aiwiki.app_lifecycle import evaluate_page_aging as legacy_evaluate_page_aging
from aiwiki.lifecycle.aging import collect_aging_signals, evaluate_page_aging


def test_evaluate_page_aging_marks_scheduled_overdue_and_escalated() -> None:
    now = datetime(2026, 5, 25, tzinfo=timezone.utc)

    scheduled = evaluate_page_aging({"revisit_after": "2026-05-26T00:00:00+00:00"}, now=now)
    overdue = evaluate_page_aging({"revisit_after": "2026-05-24T00:00:00+00:00"}, now=now)
    escalated = evaluate_page_aging(
        {
            "revisit_after": "2026-05-24T00:00:00+00:00",
            "escalate_after": "2026-05-24T12:00:00+00:00",
        },
        now=now,
    )

    assert scheduled["aging_state"] == "scheduled"
    assert scheduled["overdue_review"] == "false"
    assert overdue["aging_state"] == "overdue"
    assert overdue["overdue_review"] == "true"
    assert escalated["aging_state"] == "escalated"
    assert escalated["escalation_candidate"] == "true"


def test_collect_aging_signals_sorts_by_protocol_focus_and_due_date() -> None:
    judgments = [
        {
            "title": "General later",
            "overdue_review": "true",
            "revisit_after": "2026-05-27",
            "protocol": "general",
        },
        {
            "title": "Product sooner",
            "overdue_review": "true",
            "revisit_after": "2026-05-26",
            "protocol": "product",
        },
        {
            "title": "Scheduled",
            "aging_state": "scheduled",
            "revisit_after": "2026-05-30",
            "protocol": "product",
        },
    ]

    signals = collect_aging_signals([], judgments, active_protocol="product")

    assert [page["title"] for page in signals["overdue"]] == ["Product sooner", "General later"]
    assert [page["title"] for page in signals["scheduled"]] == ["Scheduled"]
    assert signals["escalated"] == []


def test_app_lifecycle_reexports_aging_helpers_for_compatibility() -> None:
    now = datetime(2026, 5, 25, tzinfo=timezone.utc)
    page = {"revisit_after": "2026-05-24T00:00:00+00:00", "title": "A"}

    assert legacy_evaluate_page_aging(page, now=now) == evaluate_page_aging(page, now=now)
    assert legacy_collect_aging_signals([], [{**page, "overdue_review": "true"}]) == collect_aging_signals(
        [],
        [{**page, "overdue_review": "true"}],
    )
