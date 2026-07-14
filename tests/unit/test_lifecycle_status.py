from __future__ import annotations

from aiwiki.app_lifecycle import (
    action_transition_profile as legacy_action_transition_profile,
)
from aiwiki.app_lifecycle import (
    display_curated_status as legacy_display_curated_status,
)
from aiwiki.lifecycle.status import (
    action_needs_review,
    action_transition_profile,
    archive_transition_profile,
    curated_page_transition_profile,
    default_curated_status,
    display_action_status,
    display_curated_status,
    display_rewrite_proposal_status,
    page_needs_review,
    rewrite_proposal_needs_review,
    rewrite_proposal_status_rank,
    rewrite_transition_profile,
    transition_profile,
    valid_curated_statuses,
)


def test_curated_status_helpers_match_expected_status_sets() -> None:
    assert default_curated_status("decision") == "proposed"
    assert default_curated_status("judgment") == "tentative"
    assert default_curated_status("derived") == "filed"
    assert "approved" in valid_curated_statuses("decision")
    assert "confirmed" in valid_curated_statuses("judgment")
    assert valid_curated_statuses("source") == ()
    assert page_needs_review("decision", "proposed")
    assert page_needs_review("judgment", "tentative")
    assert not page_needs_review("derived", "filed")


def test_display_helpers_keep_human_labels_and_unknown_fallback() -> None:
    assert display_curated_status("confirmed") == "已确认"
    assert display_curated_status("") == "unknown"
    assert display_action_status("accepted") == "已接受"
    assert display_rewrite_proposal_status("applied") == "已应用"
    assert display_rewrite_proposal_status("custom") == "custom"


def test_transition_profile_filters_invalid_preferred_and_defaults() -> None:
    profile = transition_profile(
        [" accepted ", "", "rejected"],
        preferred_transitions=["missing", "rejected"],
        default_transition="missing",
    )

    assert profile == {
        "allowed_transitions": ["accepted", "rejected"],
        "preferred_transitions": ["rejected"],
        "default_transition": "rejected",
    }


def test_curated_rewrite_action_and_archive_profiles() -> None:
    assert curated_page_transition_profile("decision", "proposed")["default_transition"] == "approved"
    assert curated_page_transition_profile("judgment", "tracking")["allowed_transitions"] == [
        "confirmed",
        "rejected",
    ]
    assert rewrite_transition_profile("deferred")["default_transition"] == "accepted"
    assert action_transition_profile("accepted")["default_transition"] == "resolved"
    assert archive_transition_profile(can_apply=True, can_revert=True)["allowed_transitions"] == ["apply"]
    assert archive_transition_profile(can_apply=False, can_revert=True)["allowed_transitions"] == ["revert"]


def test_review_and_rank_helpers() -> None:
    assert action_needs_review("proposed")
    assert rewrite_proposal_needs_review("accepted")
    assert not rewrite_proposal_needs_review("applied")
    assert rewrite_proposal_status_rank("proposed") < rewrite_proposal_status_rank("rejected")
    assert rewrite_proposal_status_rank("unknown") == 9


def test_app_lifecycle_reexports_status_helpers_for_compatibility() -> None:
    assert legacy_display_curated_status("confirmed") == display_curated_status("confirmed")
    assert legacy_action_transition_profile("accepted") == action_transition_profile("accepted")
