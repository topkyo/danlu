"""M6.4 Knowledge Compounding Metrics — pure builder.

No IO, no schema mutation. Filesystem readers build ``MetricsSnapshot`` in
``metrics_io.py`` (B2); this module only derives metrics from the snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

MetricUnit = Literal["ratio", "count", "percent"]


@dataclass(frozen=True)
class Metric:
    key: str
    value: float | int | None
    unit: MetricUnit
    reason: str = ""
    sample_size: int = 0


@dataclass(frozen=True)
class WikiPageMeta:
    """Single wiki page metadata, populated by B2 metrics_io."""

    path: str
    has_source_url: bool
    has_captured_at: bool
    has_derived_from: bool
    updated_at: str
    mtime_epoch: float


@dataclass(frozen=True)
class ReceiptMeta:
    """Single execution receipt metadata."""

    operation: str
    subject_kind: str
    subject_id: str
    target_subject_id: str
    applied_at: str
    receipt_path: str


@dataclass(frozen=True)
class ProposalMeta:
    """L3 proposal metadata."""

    proposal_id: str
    status: str
    created_at: str
    decided_at: str


@dataclass(frozen=True)
class OutputMeta:
    """output/ artifact metadata."""

    path: str
    derived_from: list[str]
    generated_at: str


@dataclass(frozen=True)
class MetricsSnapshot:
    """All data needed to compute knowledge compounding metrics."""

    wiki_pages: tuple[WikiPageMeta, ...] = ()
    review_counts: tuple[tuple[str, int], ...] = ()
    receipts: tuple[ReceiptMeta, ...] = ()
    proposals: tuple[ProposalMeta, ...] = ()
    outputs: tuple[OutputMeta, ...] = ()
    stale_threshold_days: int = 30
    now_iso: str = ""


def compute_metrics(snapshot: MetricsSnapshot) -> list[Metric]:
    """Derive the M6.4 metrics list from ``snapshot``."""

    return [
        compute_provenance_completeness(snapshot),
        compute_stale_ratio(snapshot),
        compute_review_closure_rate(snapshot),
        compute_proposal_acceptance_rate(snapshot),
        compute_judgment_revisit_rate(snapshot),
        compute_output_file_back_rate(snapshot),
        compute_elixir_reuse_count(snapshot),
    ]


def compute_provenance_completeness(snapshot: MetricsSnapshot) -> Metric:
    """Return the ratio of wiki pages with complete provenance fields."""

    sample_size = len(snapshot.wiki_pages)
    if sample_size == 0:
        return Metric("provenance_completeness", None, "ratio", "no wiki pages", 0)
    complete = sum(
        1
        for page in snapshot.wiki_pages
        if page.has_source_url and page.has_captured_at and page.has_derived_from
    )
    return Metric("provenance_completeness", round(complete / sample_size, 4), "ratio", "", sample_size)


def compute_stale_ratio(snapshot: MetricsSnapshot) -> Metric:
    """Return the ratio of dated wiki pages older than the stale threshold."""

    if len(snapshot.wiki_pages) == 0:
        return Metric("stale_ratio", None, "ratio", "no wiki pages", 0)
    now = _parse_iso_datetime(snapshot.now_iso)
    if now is None:
        return Metric("stale_ratio", None, "ratio", "now_iso missing", 0)

    stale = 0
    sample_size = 0
    threshold_seconds = max(snapshot.stale_threshold_days, 0) * 24 * 60 * 60
    for page in snapshot.wiki_pages:
        updated = _page_updated_datetime(page)
        if updated is None:
            continue
        sample_size += 1
        if (now - updated).total_seconds() > threshold_seconds:
            stale += 1

    if sample_size == 0:
        return Metric("stale_ratio", None, "ratio", "no dated wiki pages", 0)
    return Metric("stale_ratio", round(stale / sample_size, 4), "ratio", "", sample_size)


def compute_proposal_acceptance_rate(snapshot: MetricsSnapshot) -> Metric:
    """Return accepted / (accepted + rejected) for decided L3 proposals."""

    accepted = sum(1 for proposal in snapshot.proposals if proposal.status == "accepted")
    rejected = sum(1 for proposal in snapshot.proposals if proposal.status == "rejected")
    sample_size = accepted + rejected
    if sample_size == 0:
        return Metric("proposal_acceptance_rate", None, "ratio", "no decided proposals", 0)
    return Metric("proposal_acceptance_rate", round(accepted / sample_size, 4), "ratio", "", sample_size)


def compute_review_closure_rate(snapshot: MetricsSnapshot) -> Metric:
    """Return close events in the last 7 days / (closed + current pending reviews)."""

    now = _parse_iso_datetime(snapshot.now_iso)
    if now is None:
        return Metric("review_closure_rate", None, "ratio", "now_iso missing", 0)

    window_seconds = 7 * 24 * 60 * 60
    close_operations = {"close", "resolve", "approve", "reject"}
    close_events_7d = 0
    for receipt in snapshot.receipts:
        if receipt.subject_kind != "review" or receipt.operation not in close_operations:
            continue
        applied_at = _parse_iso_datetime(receipt.applied_at)
        if applied_at is None:
            continue
        age_seconds = (now - applied_at).total_seconds()
        if 0 <= age_seconds <= window_seconds:
            close_events_7d += 1

    pending_now = sum(max(count, 0) for _name, count in snapshot.review_counts)
    sample_size = close_events_7d + pending_now
    if sample_size == 0:
        return Metric("review_closure_rate", None, "ratio", "no review activity", 0)
    return Metric("review_closure_rate", round(close_events_7d / sample_size, 4), "ratio", "", sample_size)


def compute_judgment_revisit_rate(snapshot: MetricsSnapshot) -> Metric:
    """Return ratio of judgment subjects that have receipts at two or more times."""

    receipt_times_by_subject: dict[str, set[datetime]] = {}
    for receipt in snapshot.receipts:
        if receipt.subject_kind != "judgment":
            continue
        subject_id = receipt.target_subject_id or receipt.subject_id
        if not subject_id:
            continue
        applied_at = _parse_iso_datetime(receipt.applied_at)
        if applied_at is None:
            continue
        receipt_times_by_subject.setdefault(subject_id, set()).add(applied_at)

    sample_size = len(receipt_times_by_subject)
    if sample_size == 0:
        return Metric("judgment_revisit_rate", None, "ratio", "no judgment receipts", 0)
    revisited = sum(1 for times in receipt_times_by_subject.values() if len(times) >= 2)
    return Metric("judgment_revisit_rate", round(revisited / sample_size, 4), "ratio", "", sample_size)


def compute_output_file_back_rate(snapshot: MetricsSnapshot) -> Metric:
    """Return ratio of output artifacts carrying any derived_from provenance."""

    sample_size = len(snapshot.outputs)
    if sample_size == 0:
        return Metric("output_file_back_rate", None, "ratio", "no outputs", 0)
    backed = sum(1 for output in snapshot.outputs if output.derived_from)
    return Metric("output_file_back_rate", round(backed / sample_size, 4), "ratio", "", sample_size)


def compute_elixir_reuse_count(snapshot: MetricsSnapshot) -> Metric:
    """Count later receipts that target an already finalized elixir."""

    timed_receipts = [
        (applied_at, receipt)
        for receipt in snapshot.receipts
        if (applied_at := _parse_iso_datetime(receipt.applied_at)) is not None
    ]
    timed_receipts.sort(key=lambda item: (item[0], item[1].receipt_path))

    active_finalized: set[str] = set()
    reuse_count = 0
    index = 0
    while index < len(timed_receipts):
        current_time = timed_receipts[index][0]
        group: list[ReceiptMeta] = []
        while index < len(timed_receipts) and timed_receipts[index][0] == current_time:
            group.append(timed_receipts[index][1])
            index += 1

        reuse_count += sum(1 for receipt in group if receipt.target_subject_id in active_finalized)
        for receipt in group:
            if _is_elixir_finalized_receipt(receipt) and receipt.subject_id:
                active_finalized.add(receipt.subject_id)
                if receipt.target_subject_id:
                    active_finalized.add(receipt.target_subject_id)
                active_finalized.add(f"wiki/elixirs/{receipt.subject_id}.md")

    return Metric("elixir_reuse_count", reuse_count, "count", "", len(snapshot.receipts))


def _is_elixir_finalized_receipt(receipt: ReceiptMeta) -> bool:
    return (receipt.operation == "finalize" and receipt.subject_kind == "elixir") or (
        receipt.operation == "promote" and receipt.subject_kind == "elixir_promotion"
    )


def _page_updated_datetime(page: WikiPageMeta) -> datetime | None:
    updated = _parse_iso_datetime(page.updated_at)
    if updated is not None:
        return updated
    if page.updated_at.strip():
        return None
    if page.mtime_epoch <= 0:
        return None
    try:
        return datetime.fromtimestamp(page.mtime_epoch, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _parse_iso_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
