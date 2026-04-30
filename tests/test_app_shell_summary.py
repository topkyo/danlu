from __future__ import annotations

import unittest

from aiwiki.app_shell.summary import (
    _action_review_backlog_counts,
    _counter_evidence_pages_from_memory,
)


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


class CounterEvidencePagesFromMemoryTests(unittest.TestCase):
    """Round 58 R3 regression: scan writer / reader schema mismatch silently
    dropped every counter-evidence card. Wrap as unittest.TestCase so
    `unittest discover` (used by `scripts/verify.sh`) catches regressions.
    """

    def _scan_with_writer_schema(self) -> dict[str, object]:
        return {
            "generated_at": "2026-04-30T17:00:00+00:00",
            "candidate_count": 1,
            "candidates": [],
            "pages": [
                {
                    "page_id": "judgment-x",
                    "page_path": "wiki/judgments/judgment-x.md",
                    "page_title": "Judgment X",
                    "page_kind": "judgment",
                    "page_status": "confirmed",
                    "protocol": "investing",
                    "candidate_count": 3,
                    "source_ids": ["src-1", "src-2", "src-3"],
                    "source_pages": [
                        "wiki/sources/src-1.md",
                        "wiki/sources/src-2.md",
                        "wiki/sources/src-3.md",
                    ],
                    "shared_terms": ["nvda", "thesis"],
                }
            ],
        }

    def test_reads_scan_writer_schema(self) -> None:
        out = _counter_evidence_pages_from_memory(self._scan_with_writer_schema())
        self.assertEqual(len(out), 1)
        page = out[0]
        self.assertEqual(page["path"], "wiki/judgments/judgment-x.md")
        self.assertEqual(page["subject"], "Judgment X")
        self.assertIn("3", page["summary"])
        self.assertEqual(page["protocol"], "investing")
        self.assertEqual(page["detected_at"], "2026-04-30T17:00:00+00:00")

    def test_back_compat_old_schema(self) -> None:
        out = _counter_evidence_pages_from_memory(
            {
                "pages": [
                    {
                        "path": "wiki/judgments/old.md",
                        "subject": "Old Subject",
                        "summary": "Old reason",
                        "detected_at": "2026-04-29T00:00:00+00:00",
                        "protocol": "research",
                    }
                ]
            }
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["path"], "wiki/judgments/old.md")
        self.assertEqual(out[0]["subject"], "Old Subject")
        self.assertEqual(out[0]["summary"], "Old reason")

    def test_skips_pathless_entries(self) -> None:
        out = _counter_evidence_pages_from_memory(
            {"pages": [{"page_title": "no-path"}, {"page_path": "wiki/judgments/a.md"}]}
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["path"], "wiki/judgments/a.md")


# Retain the original module-level pytest-style helpers as no-op aliases so
# `pytest tests/test_app_shell_summary.py` stays green for direct invocations.

def test_counter_evidence_pages_from_memory_reads_scan_writer_schema() -> None:
    """Round 58 R3 regression: scan writer emits `page_path / page_title /
    candidate_count`, reader was on `path / subject / summary`. Mismatch
    silently dropped every entry; today never surfaced counter-evidence cards
    even when 22 candidates existed (dogfood vault: NVDA judgment hit by
    AWS Trainium2 ALERT).
    """
    scan = {
        "generated_at": "2026-04-30T17:00:00+00:00",
        "candidate_count": 1,
        "candidates": [],
        "pages": [
            {
                "page_id": "judgment-x",
                "page_path": "wiki/judgments/judgment-x.md",
                "page_title": "Judgment X",
                "page_kind": "judgment",
                "page_status": "confirmed",
                "protocol": "investing",
                "candidate_count": 3,
                "source_ids": ["src-1", "src-2", "src-3"],
                "source_pages": [
                    "wiki/sources/src-1.md",
                    "wiki/sources/src-2.md",
                    "wiki/sources/src-3.md",
                ],
                "shared_terms": ["nvda", "thesis"],
            }
        ],
    }
    out = _counter_evidence_pages_from_memory(scan)
    assert len(out) == 1
    page = out[0]
    assert page["path"] == "wiki/judgments/judgment-x.md"
    assert page["subject"] == "Judgment X"
    assert "3" in page["summary"]
    assert page["protocol"] == "investing"
    assert page["detected_at"] == "2026-04-30T17:00:00+00:00"


def test_counter_evidence_pages_from_memory_back_compat_old_schema() -> None:
    """Old/alternate schema with explicit `path / subject / summary` keys still works."""
    scan = {
        "pages": [
            {
                "path": "wiki/judgments/old.md",
                "subject": "Old Subject",
                "summary": "Old reason",
                "detected_at": "2026-04-29T00:00:00+00:00",
                "protocol": "research",
            }
        ]
    }
    out = _counter_evidence_pages_from_memory(scan)
    assert len(out) == 1
    assert out[0]["path"] == "wiki/judgments/old.md"
    assert out[0]["subject"] == "Old Subject"
    assert out[0]["summary"] == "Old reason"


def test_counter_evidence_pages_from_memory_skips_pathless_entries() -> None:
    """Entries with neither path nor page_path must be filtered out."""
    out = _counter_evidence_pages_from_memory(
        {"pages": [{"page_title": "no-path"}, {"page_path": "wiki/judgments/a.md"}]}
    )
    assert len(out) == 1
    assert out[0]["path"] == "wiki/judgments/a.md"
