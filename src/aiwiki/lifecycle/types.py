"""Lifecycle domain TypedDict contracts."""

from __future__ import annotations

from typing import TypedDict


class AgingSignal(TypedDict, total=False):
    page_id: str
    title: str
    path: str
    kind: str
    status: str
    protocol: str
    reviewed_at: str
    updated_at: str
    revisit_after: str
    escalate_after: str
    pending_review: str
    overdue_review: str
    escalation_candidate: str
    aging_state: str
    citation_drift: str
    citation_drift_count: str
    citation_snapshot_gap_count: str
    asset_score: str
    confidence: str


class JudgmentAsset(TypedDict, total=False):
    page_id: str
    title: str
    path: str
    kind: str
    status: str
    protocol: str
    citations: list[str]
    confidence: str
    counter_evidence: list[str]
    invalidation_rule: str
    next_signals: list[str]
    revisit_after: str
    escalate_after: str
    formed_at: str
    last_reviewed: str


class JudgmentReviewAction(TypedDict, total=False):
    id: str
    title: str
    page_id: str
    page_path: str
    page_kind: str
    protocol: str
    status: str
    priority: str
    reason_codes: list[str]
    candidate_count: int
    review_command: str
