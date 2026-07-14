from __future__ import annotations

from aiwiki.render.review_center import (
    render_review_center_action_item,
    render_review_center_lifecycle_item,
    render_review_center_page_item,
    render_review_center_review_action_item,
    render_review_center_rewrite_item,
)


def test_render_review_center_page_item_escapes_title_and_links_path() -> None:
    item = render_review_center_page_item(
        {
            "path": "wiki/judgments/j1.md",
            "title": "Judgment <One>",
            "status": "tentative",
            "revisit_after": "2026-05-25",
        }
    )

    assert 'href="../../wiki/judgments/j1.md"' in item
    assert "Judgment &lt;One&gt;" in item
    assert "status 暂定判断" in item


def test_render_review_center_action_item_includes_paths_and_command() -> None:
    item = render_review_center_action_item(
        {
            "title": "Repair <Link>",
            "status": "accepted",
            "priority": "low",
            "primary_path": "wiki/sources/a.md",
            "secondary_path": "wiki/concepts/b.md",
            "command_hint": "apply-action action-1",
        }
    )

    assert "Repair &lt;Link&gt;" in item
    assert "status 已接受" in item
    assert "<code>wiki/sources/a.md</code>" in item
    assert "<code>wiki/concepts/b.md</code>" in item
    assert "<code>apply-action action-1</code>" in item


def test_render_review_center_rewrite_item_marks_apply_ready() -> None:
    item = render_review_center_rewrite_item(
        {
            "slug": "concept-a",
            "title": "Concept A",
            "status": "accepted",
            "apply_ready": True,
        }
    )

    assert 'href="../../wiki/rewrite-proposals/concept-a.md"' in item
    assert "Concept A" in item
    assert "apply_ready true" in item


def test_render_review_center_review_action_item_includes_reason_codes() -> None:
    item = render_review_center_review_action_item(
        {
            "page_path": "wiki/judgments/j1.md",
            "title": "Review J1",
            "priority": "high",
            "reason_codes": ["missing-invalidation", "stale"],
            "review_command": "review-page wiki/judgments/j1.md",
        }
    )

    assert 'href="../../wiki/judgments/j1.md"' in item
    assert "missing-invalidation, stale" in item
    assert "<code>review-page wiki/judgments/j1.md</code>" in item


def test_render_review_center_lifecycle_item_includes_judgment_override_and_signals() -> None:
    item = render_review_center_lifecycle_item(
        {
            "path": "wiki/judgments/j1.md",
            "kind": "judgment",
            "title": "Judgment J1",
            "lifecycle_state": "review",
            "judgment_lifecycle_state": "under_review",
            "override_active": True,
            "override_state": "active",
            "invalidation_signals": ["drift", "conflict", "third", "ignored"],
            "active_corpus_ids": ["c1", "c2"],
        }
    )

    assert 'href="../../wiki/judgments/j1.md"' in item
    assert "Judgment J1" in item
    assert "judgment" in item
    assert "override active" in item
    assert "invalidation drift, conflict, third" in item
    assert "active corpora 2" in item
