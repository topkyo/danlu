"""Pure helpers for dogfood maturity proof reporting."""

from __future__ import annotations

from typing import Any


def build_semantic_path_report(
    *,
    latest_compounding_proof: dict[str, Any],
    judgment_review_receipts_delta: int,
    latest_judgment_review_receipts_total: int,
) -> dict[str, Any]:
    """Report whether the maturity window still has a semantic review path."""

    proof_status = str(latest_compounding_proof.get("status") or "not-yet")
    sample = latest_compounding_proof.get("compounding_sample")
    has_compounding_sample = isinstance(sample, dict) and bool(sample.get("receipt_path")) and bool(sample.get("reused_ref"))
    if judgment_review_receipts_delta > 0:
        observed = True
        reason = "judgment review receipt count increased in the summary window"
        evidence = "window_delta"
    elif latest_judgment_review_receipts_total > 0 and proof_status == "pass" and has_compounding_sample:
        observed = True
        reason = "latest state retains reviewed judgment receipts and a receipt-backed compounding sample"
        evidence = "latest_state"
    else:
        observed = False
        reason = "no judgment review progress or retained receipt-backed compounding path observed"
        evidence = "missing"
    return {
        "version": 1,
        "observed": observed,
        "reason": reason,
        "evidence": evidence,
        "judgment_review_receipts_delta": judgment_review_receipts_delta,
        "latest_judgment_review_receipts_total": latest_judgment_review_receipts_total,
        "knowledge_compounding_status": proof_status,
        "compounding_sample_present": has_compounding_sample,
    }
