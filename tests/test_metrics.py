from __future__ import annotations

import unittest
from datetime import datetime, timezone

from aiwiki.metrics import (
    Metric,
    MetricsSnapshot,
    ProposalMeta,
    ReceiptMeta,
    WikiPageMeta,
    compute_elixir_reuse_count,
    compute_metrics,
    compute_proposal_acceptance_rate,
    compute_provenance_completeness,
    compute_stale_ratio,
)


def _page(
    path: str,
    *,
    complete: bool = True,
    updated_at: str = "2026-04-20T00:00:00Z",
    mtime_epoch: float = 0,
) -> WikiPageMeta:
    return WikiPageMeta(
        path=path,
        has_source_url=complete,
        has_captured_at=complete,
        has_derived_from=complete,
        updated_at=updated_at,
        mtime_epoch=mtime_epoch,
    )


def _proposal(proposal_id: str, status: str) -> ProposalMeta:
    return ProposalMeta(proposal_id=proposal_id, status=status, created_at="", decided_at="")


def _receipt(
    receipt_path: str,
    *,
    operation: str = "note",
    subject_kind: str = "source",
    subject_id: str = "source-1",
    target_subject_id: str = "",
    applied_at: str = "2026-04-20T00:00:00Z",
) -> ReceiptMeta:
    return ReceiptMeta(
        operation=operation,
        subject_kind=subject_kind,
        subject_id=subject_id,
        target_subject_id=target_subject_id,
        applied_at=applied_at,
        receipt_path=receipt_path,
    )


class MetricsTests(unittest.TestCase):
    def assertAvailableMetric(self, metric: Metric, expected_unit: str) -> None:
        self.assertIn(metric.unit, {"ratio", "count", "percent"})
        self.assertEqual(metric.unit, expected_unit)
        self.assertIsNotNone(metric.value)
        self.assertEqual(metric.reason, "")

    def assertUnavailableMetric(self, metric: Metric, expected_unit: str) -> None:
        self.assertIn(metric.unit, {"ratio", "count", "percent"})
        self.assertEqual(metric.unit, expected_unit)
        self.assertIsNone(metric.value)
        self.assertNotEqual(metric.reason, "")

    def test_compute_metrics_returns_b1_metrics_in_stable_order(self) -> None:
        snapshot = MetricsSnapshot(
            wiki_pages=(_page("wiki/a.md"),),
            proposals=(_proposal("p1", "accepted"),),
            now_iso="2026-04-27T00:00:00Z",
        )

        metrics = compute_metrics(snapshot)

        self.assertEqual(
            [metric.key for metric in metrics],
            [
                "provenance_completeness",
                "stale_ratio",
                "proposal_acceptance_rate",
                "elixir_reuse_count",
            ],
        )

    def test_provenance_happy_three_of_four_complete(self) -> None:
        snapshot = MetricsSnapshot(
            wiki_pages=(
                _page("wiki/1.md"),
                _page("wiki/2.md"),
                _page("wiki/3.md"),
                _page("wiki/4.md", complete=False),
            )
        )

        metric = compute_provenance_completeness(snapshot)

        self.assertAvailableMetric(metric, "ratio")
        self.assertEqual(metric.value, 0.75)
        self.assertEqual(metric.sample_size, 4)

    def test_provenance_all_incomplete_is_zero(self) -> None:
        snapshot = MetricsSnapshot(wiki_pages=(_page("wiki/a.md", complete=False), _page("wiki/b.md", complete=False)))

        metric = compute_provenance_completeness(snapshot)

        self.assertAvailableMetric(metric, "ratio")
        self.assertEqual(metric.value, 0.0)

    def test_provenance_all_complete_is_one(self) -> None:
        snapshot = MetricsSnapshot(wiki_pages=(_page("wiki/a.md"), _page("wiki/b.md")))

        metric = compute_provenance_completeness(snapshot)

        self.assertAvailableMetric(metric, "ratio")
        self.assertEqual(metric.value, 1.0)

    def test_provenance_empty_wiki_unavailable(self) -> None:
        metric = compute_provenance_completeness(MetricsSnapshot())

        self.assertUnavailableMetric(metric, "ratio")
        self.assertEqual(metric.reason, "no wiki pages")

    def test_stale_happy_two_of_five_stale(self) -> None:
        snapshot = MetricsSnapshot(
            wiki_pages=(
                _page("wiki/1.md", updated_at="2026-03-01T00:00:00Z"),
                _page("wiki/2.md", updated_at="2026-03-20T23:59:59Z"),
                _page("wiki/3.md", updated_at="2026-03-22T00:00:01Z"),
                _page("wiki/4.md", updated_at="2026-04-01T00:00:00Z"),
                _page("wiki/5.md", updated_at="2026-04-26T00:00:00Z"),
            ),
            now_iso="2026-04-21T00:00:00Z",
        )

        metric = compute_stale_ratio(snapshot)

        self.assertAvailableMetric(metric, "ratio")
        self.assertEqual(metric.value, 0.4)
        self.assertEqual(metric.sample_size, 5)

    def test_stale_all_fresh_is_zero(self) -> None:
        snapshot = MetricsSnapshot(
            wiki_pages=(_page("wiki/a.md", updated_at="2026-04-20T00:00:00Z"),),
            now_iso="2026-04-21T00:00:00Z",
        )

        metric = compute_stale_ratio(snapshot)

        self.assertAvailableMetric(metric, "ratio")
        self.assertEqual(metric.value, 0.0)

    def test_stale_now_iso_empty_unavailable(self) -> None:
        snapshot = MetricsSnapshot(wiki_pages=(_page("wiki/a.md"),), now_iso="")

        metric = compute_stale_ratio(snapshot)

        self.assertUnavailableMetric(metric, "ratio")
        self.assertEqual(metric.reason, "now_iso missing")

    def test_stale_empty_wiki_unavailable(self) -> None:
        metric = compute_stale_ratio(MetricsSnapshot(now_iso="2026-04-21T00:00:00Z"))

        self.assertUnavailableMetric(metric, "ratio")
        self.assertEqual(metric.reason, "no wiki pages")

    def test_stale_no_dated_pages_unavailable(self) -> None:
        snapshot = MetricsSnapshot(wiki_pages=(_page("wiki/a.md", updated_at="", mtime_epoch=0),), now_iso="2026-04-21T00:00:00Z")

        metric = compute_stale_ratio(snapshot)

        self.assertUnavailableMetric(metric, "ratio")
        self.assertEqual(metric.reason, "no dated wiki pages")

    def test_stale_uses_mtime_fallback_when_updated_at_empty(self) -> None:
        mtime_epoch = datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp()
        snapshot = MetricsSnapshot(
            wiki_pages=(_page("wiki/a.md", updated_at="", mtime_epoch=mtime_epoch),),
            now_iso="2026-04-21T00:00:00Z",
        )

        metric = compute_stale_ratio(snapshot)

        self.assertAvailableMetric(metric, "ratio")
        self.assertEqual(metric.value, 1.0)

    def test_stale_malformed_updated_at_not_counted_in_numerator_or_denominator(self) -> None:
        snapshot = MetricsSnapshot(
            wiki_pages=(
                _page("wiki/bad.md", updated_at="not-a-date"),
                _page("wiki/fresh.md", updated_at="2026-04-20T00:00:00Z"),
            ),
            now_iso="2026-04-21T00:00:00Z",
        )

        metric = compute_stale_ratio(snapshot)

        self.assertAvailableMetric(metric, "ratio")
        self.assertEqual(metric.value, 0.0)
        self.assertEqual(metric.sample_size, 1)

    def test_stale_naive_iso_is_treated_as_utc(self) -> None:
        snapshot = MetricsSnapshot(
            wiki_pages=(_page("wiki/a.md", updated_at="2026-03-01T00:00:00"),),
            now_iso="2026-04-21T00:00:00Z",
        )

        metric = compute_stale_ratio(snapshot)

        self.assertAvailableMetric(metric, "ratio")
        self.assertEqual(metric.value, 1.0)

    def test_stale_invalid_mtime_fallback_unavailable(self) -> None:
        snapshot = MetricsSnapshot(
            wiki_pages=(_page("wiki/a.md", updated_at="", mtime_epoch=10**100),),
            now_iso="2026-04-21T00:00:00Z",
        )

        metric = compute_stale_ratio(snapshot)

        self.assertUnavailableMetric(metric, "ratio")
        self.assertEqual(metric.reason, "no dated wiki pages")

    def test_proposal_acceptance_three_accepted_one_rejected_two_pending(self) -> None:
        snapshot = MetricsSnapshot(
            proposals=(
                _proposal("p1", "accepted"),
                _proposal("p2", "accepted"),
                _proposal("p3", "accepted"),
                _proposal("p4", "rejected"),
                _proposal("p5", "pending"),
                _proposal("p6", "pending"),
            )
        )

        metric = compute_proposal_acceptance_rate(snapshot)

        self.assertAvailableMetric(metric, "ratio")
        self.assertEqual(metric.value, 0.75)
        self.assertEqual(metric.sample_size, 4)

    def test_proposal_acceptance_all_rejected_is_zero(self) -> None:
        snapshot = MetricsSnapshot(proposals=(_proposal("p1", "rejected"), _proposal("p2", "rejected")))

        metric = compute_proposal_acceptance_rate(snapshot)

        self.assertAvailableMetric(metric, "ratio")
        self.assertEqual(metric.value, 0.0)

    def test_proposal_acceptance_only_pending_unavailable(self) -> None:
        snapshot = MetricsSnapshot(proposals=(_proposal("p1", "pending"), _proposal("p2", "pending")))

        metric = compute_proposal_acceptance_rate(snapshot)

        self.assertUnavailableMetric(metric, "ratio")
        self.assertEqual(metric.reason, "no decided proposals")

    def test_elixir_reuse_counts_two_later_references(self) -> None:
        snapshot = MetricsSnapshot(
            receipts=(
                _receipt("r1", operation="finalize", subject_kind="elixir", subject_id="elixir-1", applied_at="2026-04-20T00:00:00Z"),
                _receipt("r2", target_subject_id="elixir-1", applied_at="2026-04-20T00:00:01Z"),
                _receipt("r3", target_subject_id="elixir-1", applied_at="2026-04-21T00:00:00Z"),
            )
        )

        metric = compute_elixir_reuse_count(snapshot)

        self.assertAvailableMetric(metric, "count")
        self.assertEqual(metric.value, 2)

    def test_elixir_reuse_finalize_without_later_reference_is_zero(self) -> None:
        snapshot = MetricsSnapshot(
            receipts=(
                _receipt("r1", operation="finalize", subject_kind="elixir", subject_id="elixir-1", applied_at="2026-04-20T00:00:00Z"),
            )
        )

        metric = compute_elixir_reuse_count(snapshot)

        self.assertAvailableMetric(metric, "count")
        self.assertEqual(metric.value, 0)

    def test_elixir_reuse_reference_before_finalize_not_counted(self) -> None:
        snapshot = MetricsSnapshot(
            receipts=(
                _receipt("r1", target_subject_id="elixir-1", applied_at="2026-04-19T00:00:00Z"),
                _receipt("r2", operation="finalize", subject_kind="elixir", subject_id="elixir-1", applied_at="2026-04-20T00:00:00Z"),
            )
        )

        metric = compute_elixir_reuse_count(snapshot)

        self.assertAvailableMetric(metric, "count")
        self.assertEqual(metric.value, 0)

    def test_elixir_reuse_same_timestamp_as_finalize_not_counted_as_later(self) -> None:
        snapshot = MetricsSnapshot(
            receipts=(
                _receipt("r1", operation="finalize", subject_kind="elixir", subject_id="elixir-1", applied_at="2026-04-20T00:00:00Z"),
                _receipt("r2", target_subject_id="elixir-1", applied_at="2026-04-20T00:00:00Z"),
            )
        )

        metric = compute_elixir_reuse_count(snapshot)

        self.assertAvailableMetric(metric, "count")
        self.assertEqual(metric.value, 0)


if __name__ == "__main__":
    unittest.main()
