from __future__ import annotations

from aiwiki.app_lifecycle import (
    display_knowledge_lifecycle_state as legacy_display_knowledge_lifecycle_state,
)
from aiwiki.lifecycle.knowledge import (
    display_judgment_lifecycle_state,
    display_knowledge_lifecycle_state,
    display_protocol_relevance_ambiguity,
    display_protocol_relevance_mode,
    knowledge_lifecycle_counts,
    render_knowledge_lifecycle_entry_summary,
    select_knowledge_lifecycle_entries,
    sort_knowledge_lifecycle_entries,
)


def test_knowledge_lifecycle_counts_groups_state_kind_and_signals() -> None:
    counts = knowledge_lifecycle_counts(
        [
            {
                "kind": "concept",
                "lifecycle_state": "review",
                "invalidation_signals": ["missing-source"],
                "active_corpus_ids": ["corpus-a"],
            },
            {"kind": "judgment", "lifecycle_state": "active"},
            {"kind": "unknown", "lifecycle_state": "unknown"},
        ]
    )

    assert counts["total"] == 3
    assert counts["by_state"]["review"] == 1
    assert counts["by_kind"]["concept"]["total"] == 1
    assert counts["invalidated"] == 1
    assert counts["active_corpus_linked"] == 1


def test_display_helpers_keep_labels_and_fallbacks() -> None:
    assert display_knowledge_lifecycle_state("review") == "待审"
    assert display_judgment_lifecycle_state("under-review") == "复审中"
    assert display_protocol_relevance_mode("cross-protocol-bridge") == "bridge-top2"
    assert display_protocol_relevance_ambiguity("mixed") == "mixed"
    assert display_knowledge_lifecycle_state("") == "unknown"


def test_select_and_sort_knowledge_lifecycle_entries_are_stable() -> None:
    selected = select_knowledge_lifecycle_entries(
        {
            "entries": [
                {"kind": "concept", "lifecycle_state": "active", "title": "Z"},
                "bad",
                {
                    "kind": "concept",
                    "lifecycle_state": "review",
                    "title": "A",
                    "protocol": "product",
                    "override_active": True,
                    "invalidation_signals": ["missing-source"],
                },
                {"kind": "decision", "lifecycle_state": "review", "title": "B"},
            ]
        },
        kinds={"concept"},
        states={"active", "review"},
    )

    assert len(selected) == 2
    assert [entry["title"] for entry in sort_knowledge_lifecycle_entries(selected, active_protocol="product")] == [
        "A",
        "Z",
    ]


def test_render_knowledge_lifecycle_entry_summary_includes_governance_context() -> None:
    summary = render_knowledge_lifecycle_entry_summary(
        {
            "kind": "judgment",
            "title": "Decision Quality",
            "path": "wiki/judgments/decision-quality.md",
            "lifecycle_state": "review",
            "judgment_lifecycle_state": "under-review",
            "override_active": True,
            "override_state": "retired",
            "invalidation_signals": ["missing-source"],
            "active_corpus_ids": ["corpus-a", "corpus-b"],
            "review_signal_codes": ["stale"],
            "reason_codes": ["manual-override"],
            "protocol_relevance_primary_mode": "source-top1",
            "protocol_relevance_ambiguity": "dominant",
        }
    )

    assert summary.startswith("- [Decision Quality](../../wiki/judgments/decision-quality.md)")
    assert "state `待审`" in summary
    assert "judgment_state `复审中`" in summary
    assert "override `retired`" in summary
    assert "active_corpora `2`" in summary
    assert "protocol_relevance `top1`" in summary


def test_app_lifecycle_reexports_knowledge_helpers_for_compatibility() -> None:
    assert legacy_display_knowledge_lifecycle_state("review") == display_knowledge_lifecycle_state("review")
