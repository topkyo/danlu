from __future__ import annotations

from aiwiki.app_lifecycle import curated_page_template as legacy_curated_page_template
from aiwiki.lifecycle.templates import curated_page_template


def _render(kind: str, protocol: str = "general") -> str:
    return "\n".join(
        curated_page_template(
            kind=kind,
            protocol=protocol,
            title="Title",
            artifact_ref="output/reports/a.md",
            filed_at="2026-05-26T00:00:00Z",
            revisit_after="2026-06-01",
            escalate_after="2026-06-08",
            supporting_body="Supporting body",
        )
    )


def test_derived_template_keeps_origin_and_filed_content() -> None:
    rendered = _render("derived")

    assert rendered.startswith("# Title")
    assert "## Origin" in rendered
    assert "- Filed from: `output/reports/a.md`" in rendered
    assert "## Filed Content\nSupporting body" in rendered


def test_decision_template_uses_protocol_specific_sections_and_review_contract() -> None:
    rendered = _render("decision", "product")

    assert "## Product Decision" in rendered
    assert "## User Problem And Bet" in rendered
    assert "- Current status: `proposed`" in rendered
    assert "## Review Notes" in rendered
    assert "Supporting body" in rendered


def test_judgment_template_uses_protocol_specific_sections_and_review_contract() -> None:
    rendered = _render("judgment", "ops")

    assert "## Ops Judgment" in rendered
    assert "## Incident Evidence" in rendered
    assert "- Current status: `tentative`" in rendered
    assert "- Default revisit window: `2026-06-01`" in rendered
    assert "- Default escalation window: `2026-06-08`" in rendered


def test_app_lifecycle_reexports_curated_page_template_for_compatibility() -> None:
    assert legacy_curated_page_template is curated_page_template
