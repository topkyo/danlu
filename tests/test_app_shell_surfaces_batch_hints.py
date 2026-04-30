from __future__ import annotations

from aiwiki.app_shell.surfaces import (
    _BATCH_HINT_THRESHOLD,
    _collect_batch_hints,
    shell_suggested_next_actions,
)


def _action(kind: str, action_id: str, **overrides) -> dict:
    base = {
        "action_id": action_id,
        "kind": kind,
        "status": "proposed",
        "execution_band": "review-first",
        "can_apply": False,
        "title": f"{kind} {action_id}",
    }
    base.update(overrides)
    return base


def _page(kind: str, path: str, **overrides) -> dict:
    base = {
        "path": path,
        "kind": kind,
        "title": f"{kind} {path}",
        "default_transition": "tracking",
        "allowed_transitions": ["tracking"],
        "reasons": ["missing-invalidation"],
    }
    base.update(overrides)
    return base


def test_batch_hint_emits_for_pages_at_threshold() -> None:
    pages = [_page("judgment", f"wiki/judgments/j{i}.md") for i in range(_BATCH_HINT_THRESHOLD)]
    hints = _collect_batch_hints({"pages": pages}, {})

    assert any(h["kind"] == "batch-review" and "review-page --all-pending" in h["command"] for h in hints)
    assert all(h["batch_count"] >= _BATCH_HINT_THRESHOLD for h in hints)


def test_batch_hint_skips_pages_below_threshold() -> None:
    pages = [_page("judgment", f"wiki/judgments/j{i}.md") for i in range(_BATCH_HINT_THRESHOLD - 1)]
    hints = _collect_batch_hints({"pages": pages}, {})

    assert hints == []


def test_batch_hint_emits_per_action_kind_when_review_first_proposed() -> None:
    actions = [
        _action("split-overloaded-concept", f"a{i}") for i in range(_BATCH_HINT_THRESHOLD)
    ] + [
        _action("add-source-concept-link", f"b{i}") for i in range(_BATCH_HINT_THRESHOLD - 1)
    ]
    hints = _collect_batch_hints({}, {"actions": actions})

    kinds = [h["reason"] for h in hints]
    assert any("split-overloaded-concept" in k for k in kinds)
    assert all("add-source-concept-link" not in k for k in kinds)


def test_batch_hint_ignores_non_review_first_or_non_proposed_actions() -> None:
    actions = [_action("monitor-bridge-concept", f"a{i}", execution_band="history-only") for i in range(5)]
    actions += [_action("split-overloaded-concept", f"r{i}", status="resolved") for i in range(5)]
    hints = _collect_batch_hints({}, {"actions": actions})

    assert hints == []


def test_batch_hint_emits_apply_when_can_apply_meets_threshold() -> None:
    actions = [
        _action("split-overloaded-concept", f"a{i}", status="accepted", can_apply=True)
        for i in range(_BATCH_HINT_THRESHOLD)
    ]
    hints = _collect_batch_hints({}, {"actions": actions})

    assert any(h["kind"] == "batch-apply" and "apply-action --all-accepted-low-risk" in h["command"] for h in hints)


def test_shell_suggested_next_actions_prepends_batch_hints_and_dedupes_singletons() -> None:
    pages = [_page("judgment", f"wiki/judgments/j{i}.md") for i in range(_BATCH_HINT_THRESHOLD + 1)]
    actions = [
        _action("split-overloaded-concept", f"a{i}") for i in range(_BATCH_HINT_THRESHOLD)
    ]
    surface = shell_suggested_next_actions(
        planner_state={},
        review_controls={"pages": pages},
        execution_controls={"actions": actions},
    )

    assert surface, "expected at least one surfaced action"
    assert surface[0]["kind"] in {"batch-review", "batch-apply"}, "batch hint should be first"
    batch_count = sum(1 for s in surface if s["kind"].startswith("batch-"))
    assert batch_count >= 1
    assert len(surface) <= 8


def test_shell_suggested_next_actions_falls_back_to_singletons_when_no_batch() -> None:
    pages = [_page("judgment", "wiki/judgments/only.md")]
    surface = shell_suggested_next_actions(
        planner_state={},
        review_controls={"pages": pages},
        execution_controls={"actions": []},
    )

    assert surface, "single-page review should still surface"
    assert all(not s["kind"].startswith("batch-") for s in surface)
