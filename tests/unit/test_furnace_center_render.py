from __future__ import annotations

from aiwiki.render.furnace_center import (
    render_furnace_center_action_item,
    render_furnace_center_output_item,
    render_furnace_center_page_item,
    render_furnace_center_proposal_item,
    render_furnace_center_review_action_item,
    render_furnace_center_rewrite_item,
)


def test_render_furnace_center_page_item_uses_dashboard_link_style() -> None:
    item = render_furnace_center_page_item(
        {"path": "wiki/judgments/j1.md", "title": "Judgment <One>", "status": "tentative"}
    )

    assert 'href="../../wiki/judgments/j1.md"' in item
    assert "Judgment &lt;One&gt;" in item
    assert "item-meta" in item
    assert "暂定判断" in item


def test_render_furnace_center_action_item_includes_command_block() -> None:
    item = render_furnace_center_action_item(
        {
            "title": "Apply <Link>",
            "priority": "low",
            "status": "accepted",
            "primary_path": "wiki/sources/a.md",
            "command_hint": "apply-action action-1",
        }
    )

    assert "Apply &lt;Link&gt;" in item
    assert "low / 已接受" in item
    assert "<code>wiki/sources/a.md</code>" in item
    assert "<code>apply-action action-1</code>" in item


def test_render_furnace_center_rewrite_item_includes_apply_command() -> None:
    item = render_furnace_center_rewrite_item(
        {
            "slug": "concept-a",
            "title": "Concept A",
            "target_path": "wiki/concepts/concept-a.md",
            "status": "accepted",
        }
    )

    assert 'href="../../wiki/rewrite-proposals/concept-a.md"' in item
    assert "<code>wiki/concepts/concept-a.md</code>" in item
    assert "apply-rewrite concept-a" in item


def test_render_furnace_center_review_action_item_includes_reasons() -> None:
    item = render_furnace_center_review_action_item(
        {
            "page_path": "wiki/judgments/j1.md",
            "title": "Review J1",
            "priority": "high",
            "reason_codes": ["missing-counter-evidence"],
            "review_command": "review-page wiki/judgments/j1.md",
        }
    )

    assert 'href="../../wiki/judgments/j1.md"' in item
    assert "missing-counter-evidence" in item
    assert "<code>review-page wiki/judgments/j1.md</code>" in item


def test_render_furnace_center_output_item_defaults_protocol() -> None:
    item = render_furnace_center_output_item(
        {
            "path": "output/reports/a.md",
            "title": "Report A",
            "format": "note",
            "protocol": "",
            "created_at": "",
        }
    )

    assert 'href="../../output/reports/a.md"' in item
    assert "note / general / unknown" in item


def test_render_furnace_center_proposal_item_counts_patch_steps() -> None:
    item = render_furnace_center_proposal_item(
        {
            "action_id": "proposal-1",
            "risk": "low",
            "summary": "Patch pages",
            "target_paths": ["wiki/a.md", "wiki/b.md"],
            "page_patch_plan": [{"path": "wiki/a.md"}, {"path": "wiki/b.md"}],
        }
    )

    assert "proposal-1" in item
    assert "risk low" in item
    assert "<code>wiki/a.md, wiki/b.md</code>" in item
    assert "patch steps 2" in item
