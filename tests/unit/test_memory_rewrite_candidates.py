from __future__ import annotations

from aiwiki import app_memory
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import load_concept_rewrite_state, save_concept_rewrite_state
from aiwiki.memory.execution_surfaces import concept_rewrite_proposal_digest
from aiwiki.memory.rewrite_candidates import store_concept_rewrite_candidate


def _prepare_root(root):
    ensure_layout(root)
    concept_dir = root / "wiki" / "concepts"
    concept_dir.mkdir(parents=True, exist_ok=True)
    (concept_dir / "alpha.md").write_text(
        "\n".join(
            [
                "---",
                "title: Alpha",
                "source_signature: sig-alpha",
                "source_pages:",
                "  - wiki/sources/source-a.md",
                "---",
                "# Alpha",
                "",
                "## Summary",
                "Current alpha summary.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    save_concept_rewrite_state(
        root,
        {
            "version": 1,
            "proposals": [
                {
                    "slug": "alpha",
                    "title": "Alpha",
                    "status": "accepted",
                    "first_proposed_at": "2026-05-24T00:00:00+00:00",
                    "reviewed_at": "2026-05-24T01:00:00+00:00",
                    "review_note": "Accepted old candidate.",
                    "applied_at": "2026-05-24T02:00:00+00:00",
                    "last_applied_at": "2026-05-24T02:00:00+00:00",
                    "reverted_at": "2026-05-24T03:00:00+00:00",
                    "revert_note": "Old revert.",
                    "previous_markdown": "# Old Alpha\n",
                    "previous_digest": "old-previous",
                    "verification_status": "passed",
                    "verification_checked_at": "2026-05-24T04:00:00+00:00",
                    "verification_summary": "Old verification.",
                    "verification_issues": ["old issue"],
                    "candidate_markdown": "# Old Candidate\n",
                    "candidate_digest": concept_rewrite_proposal_digest("# Old Candidate\n"),
                    "occurrences": 2,
                }
            ],
        },
    )


def test_app_memory_rewrite_candidate_facade_matches_owner_and_resets_changed_review(tmp_path):
    owner_root = tmp_path / "owner"
    facade_root = tmp_path / "facade"
    _prepare_root(owner_root)
    _prepare_root(facade_root)
    quality_record = {
        "title": "Alpha",
        "priority": "high",
        "score": 9,
        "quality_score": 30,
        "quality_band": "weak",
        "issues": ["placeholder-summary"],
        "rewrite_strategy": "replace-summary",
        "path": "wiki/concepts/alpha.md",
        "source_signature": "sig-alpha",
        "source_pages": ["wiki/sources/source-a.md"],
    }
    candidate_markdown = "# New Candidate\n\nRewritten alpha.\n"
    generated_at = "2026-05-25T00:00:00+00:00"

    owner = store_concept_rewrite_candidate(
        owner_root,
        "alpha",
        quality_record=quality_record,
        candidate_markdown=candidate_markdown,
        generated_at=generated_at,
    )
    facade = app_memory.store_concept_rewrite_candidate(
        facade_root,
        "alpha",
        quality_record=quality_record,
        candidate_markdown=candidate_markdown,
        generated_at=generated_at,
    )

    assert facade == owner
    proposal = load_concept_rewrite_state(owner_root)["proposals"][0]
    assert proposal["status"] == "proposed"
    assert proposal["reviewed_at"] == ""
    assert proposal["review_note"] == ""
    assert proposal["applied_at"] == ""
    assert proposal["last_applied_at"] == ""
    assert proposal["verification_issues"] == []
    assert proposal["pending_review"] == "true"
    assert proposal["occurrences"] == 3
    assert proposal["candidate_markdown"] == candidate_markdown
    assert proposal["current_summary"] == "Current alpha summary."
    assert (owner_root / owner["proposal_path"]).exists()
