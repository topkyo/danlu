from __future__ import annotations

from aiwiki import app_memory
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import load_machine_memory_action_state_strict, save_machine_memory_action_state
from aiwiki.memory.actions import reconcile_machine_memory_actions


def test_app_memory_action_reconcile_facade_matches_owner_and_reopens_inactive_action(tmp_path):
    owner_root = tmp_path / "owner"
    facade_root = tmp_path / "facade"
    for root in (owner_root, facade_root):
        ensure_layout(root)
        save_machine_memory_action_state(
            root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "act-1",
                        "kind": "connect-isolated-source",
                        "title": "Connect Source",
                        "reason": "Source has no concepts.",
                        "priority": "medium",
                        "score": 4,
                        "status": "resolved",
                        "active": False,
                        "protocol": "general",
                        "first_seen_at": "2026-05-24T00:00:00+00:00",
                        "last_seen_at": "2026-05-24T00:00:00+00:00",
                        "occurrences": 2,
                        "primary_path": "wiki/sources/source-a.md",
                    }
                ],
            },
        )

    health = {
        "actions": [
            {
                "id": "act-1",
                "kind": "connect-isolated-source",
                "title": "Connect Source",
                "reason": "Source has no concepts.",
                "priority": "medium",
                "score": 4,
                "primary_path": "wiki/sources/source-a.md",
            }
        ]
    }
    compiled_at = "2026-05-25T00:00:00+00:00"

    owner = reconcile_machine_memory_actions(owner_root, health, compiled_at=compiled_at)
    facade = app_memory.reconcile_machine_memory_actions(facade_root, health, compiled_at=compiled_at)

    assert facade == owner
    assert owner["action_counts"]["total"] == 1
    assert owner["action_counts"]["inactive"] == 0
    action = load_machine_memory_action_state_strict(owner_root)["actions"][0]
    assert action["id"] == "act-1"
    assert action["active"] is True
    assert action["status"] == "proposed"
    assert action["reopened_count"] == 1
    assert action["reopened_from"] == "resolved"
    assert action["occurrences"] == 3
