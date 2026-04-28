from __future__ import annotations

from aiwiki.app_shell.summary import _action_review_backlog_counts


def test_action_review_backlog_counts_follow_actionable_controls() -> None:
    counts = _action_review_backlog_counts(
        {
            "actions": [
                {"action_id": "proposed", "status": "proposed", "can_review": True},
                {"action_id": "accepted", "status": "accepted", "can_review": True},
                {"action_id": "apply", "status": "accepted", "can_apply": True},
                {"action_id": "inert", "status": "proposed"},
                {"action_id": "resolved", "status": "resolved", "can_revert": True},
            ]
        }
    )

    assert counts == {"machine_memory_actions": 3, "ready_actions": 2}


def test_action_review_backlog_counts_treat_bad_controls_as_empty() -> None:
    assert _action_review_backlog_counts({"actions": "bad"}) == {"machine_memory_actions": 0, "ready_actions": 0}
