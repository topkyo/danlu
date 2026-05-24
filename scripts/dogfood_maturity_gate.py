#!/usr/bin/env python3
"""Repo-local dogfood maturity gate collector/runner/summarizer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

DEFAULT_VAULT_ROOT = Path("/home/tim/danlu/炼丹炉")
MATURITY_GATE_REL_DIR = Path("output") / "control" / "maturity-gate"
PLANNER_LOG_REL_PATH = Path(".aiwiki") / "state" / "planner-log.jsonl"
PROMPTS_ASK_REL_PATH = Path("prompts") / "ask.md"
SNAPSHOT_KIND = "dogfood-maturity-snapshot"
RUN_RECEIPT_KIND = "dogfood-maturity-run-receipt"
GENERATED_BY = "aiwiki-dogfood-maturity-gate"
REQUIRED_SNAPSHOT_FIELDS = (
    "backlog_total",
    "l3_proposal_counts_by_state",
    "judgment_review_receipt_counts",
    "prompts_ask_sha256",
)
COMPOUNDING_REUSE_REF_PREFIXES = (
    "wiki/judgments/",
    "wiki/decisions/",
    "wiki/elixirs/",
)
ELIXIR_REUSE_REF_PREFIX = "wiki/elixirs/"
COMPOUNDING_SAMPLE_OPERATIONS = {
    "ask",
    "file-back",
    "run-ask",
}
FAILED_RECEIPT_STATUSES = {"blocked", "error", "failed", "reverted"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve_root(root: str | None = None, *, env: dict[str, str] | None = None) -> Path:
    if root:
        return Path(root).expanduser().resolve()
    env_map = env if env is not None else os.environ
    for key in ("AIWIKI_DOGFOOD_VAULT", "AIWIKI_VAULT"):
        value = str(env_map.get(key) or "").strip()
        if value:
            return Path(value).expanduser().resolve()
    return DEFAULT_VAULT_ROOT.resolve()


def maturity_gate_dir(root: Path) -> Path:
    return root / MATURITY_GATE_REL_DIR


def _json_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dump(payload), encoding="utf-8")
    return path


def _sha256_path(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sum_int_values(payload: dict[str, Any]) -> int:
    total = 0
    for value in payload.values():
        if isinstance(value, bool):
            total += int(value)
        elif isinstance(value, int):
            total += value
    return total


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _excerpt(text: str, *, limit: int = 1200) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _load_planner_log_counts(root: Path) -> dict[str, Any]:
    from aiwiki.app_state import load_jsonl_documents

    path = root / PLANNER_LOG_REL_PATH
    mode_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    total_records = 0
    for record in load_jsonl_documents(path):
        total_records += 1
        mode_counts[str(record.get("mode") or "(missing)")] += 1
        decision_counts[str(record.get("decision") or "(missing)")] += 1
    return {
        "path": str(PLANNER_LOG_REL_PATH),
        "exists": path.is_file(),
        "total_records": total_records,
        "mode_counts": dict(sorted(mode_counts.items())),
        "decision_counts": dict(sorted(decision_counts.items())),
    }


def _load_judgment_review_receipt_counts(root: Path) -> dict[str, Any]:
    from aiwiki.app_state import execution_receipt_history_path, load_jsonl_documents

    path = execution_receipt_history_path(root)
    operation_counts: Counter[str] = Counter()
    review_ids: set[str] = set()
    latest: list[dict[str, str]] = []
    total = 0
    for record in load_jsonl_documents(path):
        if str(record.get("subject_kind") or "") != "judgment_review":
            continue
        total += 1
        operation_counts[str(record.get("operation") or "(missing)")] += 1
        review_id = str(record.get("subject_id") or "").strip()
        if review_id:
            review_ids.add(review_id)
        latest.append(
            {
                "subject_id": review_id,
                "action_id": str(record.get("action_id") or ""),
                "target_file": str(record.get("target_file") or ""),
                "receipt_path": str(record.get("receipt_path") or ""),
                "applied_at": str(record.get("applied_at") or record.get("occurred_at") or ""),
            }
        )
    return {
        "path": ".aiwiki/state/execution-receipts.jsonl",
        "exists": path.is_file(),
        "total": total,
        "operation_counts": dict(sorted(operation_counts.items())),
        "unique_subject_ids": len(review_ids),
        "latest": latest[-10:],
    }


def _load_judgment_lane_report(root: Path) -> dict[str, Any]:
    from aiwiki.app_state import (
        execution_receipt_history_path,
        load_json_document,
        load_jsonl_documents,
        nightly_health_state_path,
    )

    nightly = load_json_document(nightly_health_state_path(root))
    agent_loop = nightly.get("agent_loop") if isinstance(nightly.get("agent_loop"), dict) else {}
    auto_judgments = agent_loop.get("auto_adopt_judgments") if isinstance(agent_loop.get("auto_adopt_judgments"), dict) else {}
    receipts = [
        item
        for item in load_jsonl_documents(execution_receipt_history_path(root))
        if isinstance(item, dict) and str(item.get("subject_kind") or "") == "judgment_review"
    ]
    confidence_counts: Counter[str] = Counter()
    conclusion_counts: Counter[str] = Counter()
    target_paths: set[str] = set()
    review_ids: set[str] = set()
    receipt_confidence_by_review_id: dict[str, str] = {}
    receipt_conclusion_by_review_id: dict[str, str] = {}
    for receipt in receipts:
        confidence = str(receipt.get("confidence") or "").strip() or "(missing)"
        conclusion = str(receipt.get("conclusion") or "").strip() or "(missing)"
        confidence_counts[confidence] += 1
        conclusion_counts[conclusion] += 1
        target = str(receipt.get("target_file") or "").strip()
        if target:
            target_paths.add(target)
        review_id = str(receipt.get("subject_id") or "").strip()
        if review_id:
            review_ids.add(review_id)
            receipt_confidence_by_review_id[review_id] = confidence
            receipt_conclusion_by_review_id[review_id] = conclusion
    current_run_confidence_counts: Counter[str] = Counter()
    current_run_conclusion_counts: Counter[str] = Counter()
    for item in auto_judgments.get("items", []) if isinstance(auto_judgments.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        confidence = str(item.get("confidence") or "").strip()
        conclusion = str(item.get("conclusion") or "").strip()
        review_id = str(item.get("review_id") or "").strip()
        # New receipts already carry conclusion/confidence, so only use nightly
        # item metadata as a compatibility bridge for older receipts or pending
        # exception-only items without a receipt row.
        if confidence:
            if review_id and receipt_confidence_by_review_id.get(review_id) not in {None, "(missing)"}:
                pass
            else:
                current_run_confidence_counts[confidence] += 1
                if review_id and receipt_confidence_by_review_id.get(review_id) == "(missing)":
                    confidence_counts["(missing)"] -= 1
        if conclusion:
            if review_id and receipt_conclusion_by_review_id.get(review_id) not in {None, "(missing)"}:
                pass
            else:
                current_run_conclusion_counts[conclusion] += 1
                if review_id and receipt_conclusion_by_review_id.get(review_id) == "(missing)":
                    conclusion_counts["(missing)"] -= 1
    confidence_counts.update(current_run_confidence_counts)
    conclusion_counts.update(current_run_conclusion_counts)
    exception_queue = auto_judgments.get("exception_queue") if isinstance(auto_judgments.get("exception_queue"), list) else []
    total_candidates = _coerce_int(auto_judgments.get("total_candidates"))
    reviewed = _coerce_int(auto_judgments.get("reviewed"))
    failed = _coerce_int(auto_judgments.get("failed"))
    exceptions = _coerce_int(auto_judgments.get("exception_count"), len(exception_queue))
    return {
        "version": 1,
        "status": "ok",
        "limit": _coerce_int(auto_judgments.get("limit"), 5),
        "total_candidates": total_candidates,
        "reviewed": reviewed,
        "failed": failed,
        "exception_count": exceptions,
        "processing_rate": round(reviewed / total_candidates, 4) if total_candidates else 0.0,
        "failure_rate": round(failed / total_candidates, 4) if total_candidates else 0.0,
        "exception_rate": round(exceptions / total_candidates, 4) if total_candidates else 0.0,
        "exception_queue": exception_queue[-10:],
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "conclusion_counts": dict(sorted(conclusion_counts.items())),
        "receipt_count": len(receipts),
        "unique_review_ids": len(review_ids),
        "unique_target_paths": len(target_paths),
    }


def _load_l3_proposal_counts_by_state(root: Path) -> dict[str, int]:
    from aiwiki.execution.l3_proposals import load_l3_proposal_state

    counts: Counter[str] = Counter()
    for proposal in load_l3_proposal_state(root).get("proposals", []):
        if not isinstance(proposal, dict):
            continue
        counts[str(proposal.get("state") or "(missing)")] += 1
    return dict(sorted(counts.items()))


def _preview_l3_generation_summary(root: Path, *, limit: int) -> dict[str, Any]:
    from aiwiki.execution.l3_proposals import preview_l3_proposal_generation

    preview = preview_l3_proposal_generation(root, limit=limit)
    blocker_counts: Counter[str] = Counter()
    eligible_count = 0
    for candidate in preview.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        if bool(candidate.get("eligible")):
            eligible_count += 1
        for blocker in candidate.get("blockers", []):
            if isinstance(blocker, str):
                blocker_counts[blocker] += 1
    return {
        "status": str(preview.get("status") or ""),
        "planner_log_path": str(preview.get("planner_log_path") or ""),
        "raw_candidate_count": int(preview.get("raw_candidate_count") or preview.get("candidate_count") or 0),
        "candidate_count": int(preview.get("candidate_count") or 0),
        "blocked_count": int(preview.get("blocked_count") or 0),
        "returned_count": int(preview.get("returned_count") or 0),
        "eligible_count": eligible_count,
        "limit": int(preview.get("limit") or limit),
        "blocker_counts": dict(sorted(blocker_counts.items())),
    }


def _coerce_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _proposal_evidence_count(proposal: dict[str, Any]) -> int:
    trigger = proposal.get("trigger") if isinstance(proposal.get("trigger"), dict) else {}
    return _coerce_int(proposal.get("evidence_count", trigger.get("evidence_count", 0)))


def _load_l3_debt_report(root: Path, *, preview_limit: int) -> dict[str, Any]:
    from aiwiki.config import l3_auto_adopt_min_evidence_from_env
    from aiwiki.execution.l3_proposals import (
        l3_candidate_issue_key,
        l3_proposal_issue_key,
        load_l3_proposal_state,
        preview_l3_proposal_generation,
    )

    threshold = l3_auto_adopt_min_evidence_from_env()
    proposals = [item for item in load_l3_proposal_state(root).get("proposals", []) if isinstance(item, dict)]
    preview = preview_l3_proposal_generation(root, limit=preview_limit)
    proposal_ids = {str(item.get("proposal_id") or "") for item in proposals}
    proposal_issue_keys = {key for key in (l3_proposal_issue_key(item) for item in proposals) if key}
    state_counts: Counter[str] = Counter(str(item.get("state") or "(missing)") for item in proposals)
    dedupe_counts: Counter[str] = Counter()
    low_evidence = 0
    duplicate_existing = 0
    preview_blocker_counts: Counter[str] = Counter()
    preview_eligible = 0
    preview_not_eligible = 0

    for proposal in proposals:
        dedupe_key = str(
            proposal.get("dedupe_key")
            or (proposal.get("trigger") if isinstance(proposal.get("trigger"), dict) else {}).get("dedupe_key")
            or ""
        ).strip()
        if dedupe_key:
            dedupe_counts[dedupe_key] += 1
        if str(proposal.get("state") or "") == "candidate" and _proposal_evidence_count(proposal) < threshold:
            low_evidence += 1

    duplicate_state = sum(count - 1 for count in dedupe_counts.values() if count > 1)
    preview_returned = [item for item in preview.get("candidates", []) if isinstance(item, dict)]
    for candidate in preview_returned:
        if bool(candidate.get("eligible")):
            preview_eligible += 1
        proposal_id = str(candidate.get("proposal_id") or "")
        blockers = [blocker for blocker in candidate.get("blockers", []) if isinstance(blocker, str)]
        if blockers:
            preview_not_eligible += 1
        elif proposal_id and proposal_id in proposal_ids:
            duplicate_existing += 1
        else:
            issue_key = str(candidate.get("issue_key") or l3_candidate_issue_key(candidate))
            if issue_key and issue_key in proposal_issue_keys:
                duplicate_existing += 1
        for blocker in blockers:
            if isinstance(blocker, str):
                preview_blocker_counts[blocker] += 1

    preview_candidate_count = _coerce_int(preview.get("candidate_count"))
    not_eligible = max(_coerce_int(preview.get("blocked_count")), preview_not_eligible)
    effective_preview_candidates = max(preview_eligible - duplicate_existing, 0)
    effective_attention = max(_coerce_int(state_counts.get("candidate")) - low_evidence - duplicate_state, 0)
    preview_noise = min(duplicate_existing + not_eligible, preview_candidate_count)
    preview_noise_ratio = (preview_noise / preview_candidate_count) if preview_candidate_count else 0.0
    state_candidate_count = _coerce_int(state_counts.get("candidate"))
    attention_noise = min(low_evidence + duplicate_state, state_candidate_count)
    attention_noise_ratio = (attention_noise / state_candidate_count) if state_candidate_count else 0.0
    return {
        "version": 1,
        "status": "ok",
        "thresholds": {"low_evidence_below": threshold},
        "state_counts": dict(sorted(state_counts.items())),
        "preview_candidate_count": preview_candidate_count,
        "preview_raw_candidate_count": _coerce_int(preview.get("raw_candidate_count"), preview_candidate_count),
        "preview_returned_count": len(preview_returned),
        "preview_eligible_count": preview_eligible,
        "preview_not_eligible_count": not_eligible,
        "preview_blocker_counts": dict(sorted(preview_blocker_counts.items())),
        "duplicate_existing_count": duplicate_existing,
        "duplicate_state_count": duplicate_state,
        "low_evidence_candidate_count": low_evidence,
        "effective_preview_candidate_count": effective_preview_candidates,
        "effective_attention_count": effective_attention,
        "dedupe_or_noise_count": preview_noise,
        "dedupe_or_noise_ratio": round(preview_noise_ratio, 4),
        "attention_noise_count": attention_noise,
        "attention_noise_ratio": round(attention_noise_ratio, 4),
    }


def _build_knowledge_compounding_proof(root: Path, *, human_required_report: dict[str, Any]) -> dict[str, Any]:
    """Build an evidence-first proof report for knowledge compounding.

    AOS-004 intentionally separates "mechanisms exist" from "compounding was
    observed".  The report only returns ``pass`` when the filesystem contains a
    trace/provenance-backed sample that reuses a prior judgment/decision/elixir;
    otherwise the metrics are still emitted with a ``not-yet`` verdict.
    """

    from aiwiki.app_state import execution_receipt_history_path, load_manifest
    from aiwiki.metrics import compute_metrics
    from aiwiki.metrics_io import build_metrics_snapshot

    manifest = load_manifest(root)
    manifest_entries = manifest.get("entries")
    entries = manifest_entries if isinstance(manifest_entries, list) else []
    raw_to_wiki_count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id") or "").strip()
        if entry_id and (root / "wiki" / "sources" / f"{entry_id}.md").is_file():
            raw_to_wiki_count += 1

    metrics_snapshot = build_metrics_snapshot(root)
    metric_by_key = {metric.key: metric for metric in compute_metrics(metrics_snapshot)}
    output_file_back_metric = metric_by_key.get("output_file_back_rate")
    elixir_reuse_metric = metric_by_key.get("elixir_reuse_count")
    output_file_back_rate = output_file_back_metric.value if output_file_back_metric is not None else None

    output_reuse = _collect_judgment_or_elixir_output_reuse(root)
    elixir_reuse_count = _coerce_int(elixir_reuse_metric.value if elixir_reuse_metric is not None else 0)
    judgment_or_elixir_reuse_count = len(output_reuse) + elixir_reuse_count
    receipt_records = _knowledge_compounding_receipt_records(root)
    sample = _select_compounding_sample(output_reuse, receipt_records)
    elixir_sample = _select_compounding_sample(
        output_reuse,
        receipt_records,
        required_ref_prefix=ELIXIR_REUSE_REF_PREFIX,
    )
    settled_elixir_count = _count_settled_elixirs(root)
    elixir_output_reuse_count = _count_output_reuse_refs(output_reuse, prefix=ELIXIR_REUSE_REF_PREFIX)
    human_required_exception_count = _coerce_int(
        human_required_report.get("human_required_count"),
        _coerce_int(human_required_report.get("exception_count")),
    )

    missing: list[str] = []
    if raw_to_wiki_count <= 0:
        missing.append("raw_to_wiki_count")
    if output_file_back_rate in {None, 0}:
        missing.append("output_file_back_rate")
    if judgment_or_elixir_reuse_count <= 0:
        missing.append("judgment_or_elixir_reuse_count")
    if len(receipt_records) <= 0:
        missing.append("receipt_backed_actions")
    if sample is None:
        missing.append("trace_provenance_backed_compounding_sample")

    elixir_missing: list[str] = []
    if settled_elixir_count <= 0:
        elixir_missing.append("settled_elixir_count")
    if elixir_output_reuse_count + elixir_reuse_count <= 0:
        elixir_missing.append("elixir_reuse_count")
    if len(receipt_records) <= 0:
        elixir_missing.append("receipt_backed_actions")
    if elixir_sample is None:
        elixir_missing.append("trace_provenance_backed_elixir_compounding_sample")
    elixir_status = "pass" if not elixir_missing else "not-yet"

    status = "pass" if not missing else "not-yet"
    return {
        "kind": "knowledge-compounding-proof-report",
        "version": 1,
        "status": status,
        "verdict": status,
        "reason": "trace/provenance-backed compounding sample observed" if status == "pass" else "insufficient receipt-backed compounding evidence",
        "metrics": {
            "raw_to_wiki_count": {
                "value": raw_to_wiki_count,
                "source": ".aiwiki/state/manifest.json + wiki/sources/*.md",
            },
            "judgment_or_elixir_reuse_count": {
                "value": judgment_or_elixir_reuse_count,
                "source": "output frontmatter derived_from + elixir reuse metric",
                "output_reuse_count": len(output_reuse),
                "elixir_reuse_count": elixir_reuse_count,
            },
            "output_file_back_rate": {
                "value": output_file_back_rate,
                "unit": (output_file_back_metric.unit if output_file_back_metric is not None else "ratio"),
                "sample_size": (output_file_back_metric.sample_size if output_file_back_metric is not None else 0),
                "source": "aiwiki.metrics_io output metadata",
            },
            "receipt_backed_actions": {
                "value": len(receipt_records),
                "source": "output/control execution receipts + .aiwiki/state/execution-receipts.jsonl",
            },
            "human_required_exception_count": {
                "value": human_required_exception_count,
                "source": "human_required_report",
                "exception_count": _coerce_int(human_required_report.get("exception_count")),
            },
        },
        "compounding_sample": sample,
        "elixir_compounding_proof": {
            "kind": "elixir-compounding-proof-report",
            "version": 1,
            "status": elixir_status,
            "verdict": elixir_status,
            "reason": "receipt-backed settled elixir reuse observed"
            if elixir_status == "pass"
            else "insufficient receipt-backed settled elixir reuse evidence",
            "metrics": {
                "settled_elixir_count": {
                    "value": settled_elixir_count,
                    "source": "wiki/elixirs/*.md",
                },
                "elixir_output_reuse_count": {
                    "value": elixir_output_reuse_count,
                    "source": "output frontmatter derived_from/source_files",
                },
                "elixir_reuse_metric_count": {
                    "value": elixir_reuse_count,
                    "source": "aiwiki metrics elixir_reuse_count",
                },
                "receipt_backed_actions": {
                    "value": len(receipt_records),
                    "source": "output/control execution receipts + .aiwiki/state/execution-receipts.jsonl",
                },
            },
            "compounding_sample": elixir_sample,
            "missing_evidence": elixir_missing,
        },
        "missing_evidence": missing,
        "mechanism_evidence": {
            "manifest_entries": len(entries),
            "metrics_snapshot_outputs": len(metrics_snapshot.outputs),
            "metrics_snapshot_receipts": len(metrics_snapshot.receipts),
            "execution_receipt_history_path": str(execution_receipt_history_path(root).relative_to(root)),
        },
    }


def _collect_judgment_or_elixir_output_reuse(root: Path) -> list[dict[str, Any]]:
    from aiwiki.app_utils import parse_frontmatter, relative_path

    output_root = root / "output"
    records: list[dict[str, Any]] = []
    try:
        paths = sorted(output_root.glob("**/*.md")) if output_root.exists() else []
    except OSError:
        paths = []
    for path in paths:
        if not path.is_file() or "control" in path.relative_to(output_root).parts:
            continue
        try:
            frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, UnicodeError):
            continue
        refs = _as_string_list(frontmatter.get("derived_from")) or _as_string_list(frontmatter.get("source_files"))
        reuse_refs = [ref for ref in refs if ref.startswith(COMPOUNDING_REUSE_REF_PREFIXES)]
        if not reuse_refs:
            continue
        records.append(
            {
                "path": relative_path(root, path),
                "reused_refs": reuse_refs,
                "source_refs": refs,
                "generated_at": str(frontmatter.get("generated_at") or frontmatter.get("created_at") or ""),
            }
        )
    return records


def _count_settled_elixirs(root: Path) -> int:
    directory = root / "wiki" / "elixirs"
    try:
        return sum(1 for path in directory.glob("*.md") if path.is_file()) if directory.exists() else 0
    except OSError:
        return 0


def _count_output_reuse_refs(output_reuse: list[dict[str, Any]], *, prefix: str) -> int:
    count = 0
    for item in output_reuse:
        for ref in item.get("reused_refs") or []:
            if str(ref).startswith(prefix):
                count += 1
    return count


def _count_legacy_empty_status_receipts(root: Path) -> dict[str, Any]:
    """Warn-only count of execution receipts missing explicit status (legacy compat)."""

    from aiwiki.app_state import execution_receipt_history_path, load_jsonl_documents
    from aiwiki.metrics_io import _receipt_json_paths

    legacy_json = 0
    legacy_history = 0
    for path in _receipt_json_paths(root):
        payload = _read_json_file(path)
        if not payload:
            continue
        status = str(payload.get("status") or "").strip()
        if not status:
            legacy_json += 1
    for item in load_jsonl_documents(execution_receipt_history_path(root)):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip()
        if not status:
            legacy_history += 1
    total = legacy_json + legacy_history
    return {
        "kind": "legacy-empty-status-receipt-report",
        "version": 1,
        "count": total,
        "json_receipt_count": legacy_json,
        "history_line_count": legacy_history,
        "warn_only": True,
        "note": "Empty status is treated as success for compatibility; hard fail is deferred.",
    }


def _knowledge_compounding_receipt_records(root: Path) -> list[dict[str, str]]:
    from aiwiki.app_state import execution_receipt_history_path, load_jsonl_documents
    from aiwiki.metrics_io import _receipt_json_paths

    records: list[dict[str, str]] = []
    seen_receipt_paths: set[str] = set()
    for path in _receipt_json_paths(root):
        payload = _read_json_file(path)
        if not payload:
            continue
        receipt_path = str(payload.get("receipt_path") or path.relative_to(root))
        seen_receipt_paths.add(receipt_path)
        records.append(
            {
                "receipt_path": receipt_path,
                "operation": str(payload.get("operation") or ""),
                "status": str(payload.get("status") or ""),
                "subject_kind": str(payload.get("subject_kind") or ""),
                "target": str(payload.get("target_file") or payload.get("target_subject_id") or payload.get("primary_path") or ""),
            }
        )

    history_path = execution_receipt_history_path(root)
    for index, payload in enumerate(load_jsonl_documents(history_path), start=1):
        if not isinstance(payload, dict):
            continue
        payload_receipt_path = str(payload.get("receipt_path") or "").strip()
        if payload_receipt_path and payload_receipt_path in seen_receipt_paths:
            continue
        receipt_path = payload_receipt_path or f"{history_path.relative_to(root)}#L{index}"
        seen_receipt_paths.add(receipt_path)
        records.append(
            {
                "receipt_path": receipt_path,
                "operation": str(payload.get("operation") or ""),
                "status": str(payload.get("status") or ""),
                "subject_kind": str(payload.get("subject_kind") or ""),
                "target": str(payload.get("target_file") or payload.get("target_subject_id") or payload.get("primary_path") or ""),
            }
        )
    return records


def _is_successful_compounding_receipt(record: dict[str, str]) -> bool:
    operation = str(record.get("operation") or "").strip()
    status = str(record.get("status") or "").strip().lower()
    if operation not in COMPOUNDING_SAMPLE_OPERATIONS:
        return False
    return status not in FAILED_RECEIPT_STATUSES


def _is_background_pending_output(frontmatter: dict[str, Any]) -> bool:
    delivery_mode = str(frontmatter.get("delivery_mode") or "").strip().lower()
    background_status = str(frontmatter.get("background_status") or "").strip().lower()
    llm_status = str(frontmatter.get("llm_status") or "").strip().lower()
    return delivery_mode == "background-pending" or background_status in {"submitted", "running"} or llm_status == "pending"


def _is_degraded_llm_output(frontmatter: dict[str, Any]) -> bool:
    delivery_mode = str(frontmatter.get("delivery_mode") or "").strip().lower()
    background_status = str(frontmatter.get("background_status") or "").strip().lower()
    llm_status = str(frontmatter.get("llm_status") or "").strip().lower()
    title = str(frontmatter.get("title") or "").strip()
    return (
        delivery_mode in {"llm-failed", "deterministic-fallback"}
        or background_status in {"degraded", "failed"}
        or llm_status in {"timeout_or_unavailable", "failed"}
        or title.startswith("LLM 未完成")
    )


def _is_deterministic_baseline_output(frontmatter: dict[str, Any], *, run_notes_status: str) -> bool:
    generated_by = str(frontmatter.get("generated_by") or "").strip()
    delivery_mode = str(frontmatter.get("delivery_mode") or "").strip().lower()
    background_status = str(frontmatter.get("background_status") or "").strip().lower()
    llm_status = str(frontmatter.get("llm_status") or "").strip().lower()
    return (
        generated_by == "aiwiki-ask"
        and run_notes_status == "deterministic-ready"
        and not delivery_mode
        and not background_status
        and not llm_status
    )


def _build_receipt_coverage_report(
    root: Path,
    *,
    legacy_empty_status_receipts: dict[str, Any],
    preview_limit: int = 20,
) -> dict[str, Any]:
    from aiwiki.app_state import load_llm_receipt_history
    from aiwiki.app_utils import parse_frontmatter, relative_path

    receipt_by_target: dict[str, dict[str, str]] = {}
    for record in _knowledge_compounding_receipt_records(root):
        target = str(record.get("target") or "").strip()
        status = str(record.get("status") or "").strip().lower()
        if not target or status in FAILED_RECEIPT_STATUSES:
            continue
        receipt_by_target.setdefault(target, record)

    llm_targets = {
        str(record.get("target") or "").strip()
        for record in load_llm_receipt_history(root)
        if str(record.get("target") or "").strip()
    }
    output_paths: list[Path] = []
    for directory_name in ("reports", "slides", "figures"):
        directory = root / "output" / directory_name
        try:
            output_paths.extend(sorted(directory.glob("*.md")) if directory.exists() else [])
        except OSError:
            continue

    missing_counts: Counter[str] = Counter()
    complete_count = 0
    exempt_count = 0
    issue_samples: list[dict[str, Any]] = []
    complete_samples: list[dict[str, Any]] = []
    sample_limit = max(0, int(preview_limit))
    outputs_checked = 0
    for path in output_paths:
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
        except (OSError, UnicodeError):
            continue
        if str(frontmatter.get("kind") or "").strip() != "output":
            continue
        if str(frontmatter.get("generated_by") or "").strip() == "aiwiki-compile":
            continue
        outputs_checked += 1
        artifact_ref = relative_path(root, path)
        generated_by = str(frontmatter.get("generated_by") or "").strip()
        delivery_mode = str(frontmatter.get("delivery_mode") or "").strip()
        background_status = str(frontmatter.get("background_status") or "").strip()
        llm_status = str(frontmatter.get("llm_status") or "").strip()
        run_notes_ref = str(frontmatter.get("run_notes_path") or "").strip()
        run_notes_path = Path(run_notes_ref)
        has_run_notes = bool(run_notes_ref) and not run_notes_path.is_absolute() and (root / run_notes_path).is_file()
        run_notes_status = ""
        if has_run_notes:
            try:
                run_notes_frontmatter = parse_frontmatter((root / run_notes_path).read_text(encoding="utf-8", errors="replace"))
                run_notes_status = str(run_notes_frontmatter.get("status") or "").strip()
            except (OSError, UnicodeError):
                run_notes_status = ""
        has_execution_receipt = artifact_ref in receipt_by_target
        has_llm_receipt = artifact_ref in llm_targets
        source_refs = _as_string_list(frontmatter.get("derived_from")) or _as_string_list(frontmatter.get("source_files"))
        has_artifact_provenance = bool(
            generated_by
            and (
                source_refs
                or str(frontmatter.get("created_at") or frontmatter.get("generated_at") or "").strip()
                or run_notes_ref
            )
        )

        missing: list[str] = []
        exemptions: list[str] = []
        pending = _is_background_pending_output(frontmatter)
        degraded = _is_degraded_llm_output(frontmatter)
        deterministic_baseline = _is_deterministic_baseline_output(frontmatter, run_notes_status=run_notes_status)
        if pending:
            exemptions.append("background_pending")
        if degraded:
            exemptions.append("failed_or_degraded_llm_artifact")
        if deterministic_baseline:
            exemptions.append("deterministic_baseline_output")

        execution_receipt_exempt = pending or degraded or deterministic_baseline
        llm_receipt_exempt = pending or deterministic_baseline
        if not has_execution_receipt and not execution_receipt_exempt:
            missing.append("execution_receipt")
        if not has_llm_receipt and not llm_receipt_exempt:
            missing.append("llm_receipt")
        if not has_run_notes:
            missing.append("run_notes")
        if not has_artifact_provenance:
            missing.append("artifact_provenance")
        for key in missing:
            missing_counts[key] += 1
        if not missing:
            complete_count += 1
        if exemptions:
            exempt_count += 1
        sample = {
            "path": artifact_ref,
            "status": "complete" if not missing else "missing",
            "generated_by": generated_by,
            "delivery_mode": delivery_mode,
            "background_status": background_status,
            "llm_status": llm_status,
            "has_execution_receipt": has_execution_receipt,
            "execution_receipt_path": str(receipt_by_target.get(artifact_ref, {}).get("receipt_path") or ""),
            "has_llm_receipt": has_llm_receipt,
            "has_run_notes": has_run_notes,
            "has_artifact_provenance": has_artifact_provenance,
            "missing": missing,
            "exemptions": exemptions,
        }
        if missing or exemptions:
            if len(issue_samples) < sample_limit:
                issue_samples.append(sample)
        elif len(complete_samples) < sample_limit:
            complete_samples.append(sample)

    missing_total = sum(missing_counts.values())
    samples = (issue_samples + complete_samples)[:sample_limit]
    return {
        "kind": "receipt-coverage-report",
        "version": 1,
        "status": "pass" if missing_total == 0 else "warn",
        "outputs_checked": outputs_checked,
        "complete_count": complete_count,
        "incomplete_count": outputs_checked - complete_count,
        "exempt_count": exempt_count,
        "missing_execution_receipt_count": missing_counts.get("execution_receipt", 0),
        "missing_llm_receipt_count": missing_counts.get("llm_receipt", 0),
        "missing_run_notes_count": missing_counts.get("run_notes", 0),
        "missing_artifact_provenance_count": missing_counts.get("artifact_provenance", 0),
        "missing_counts": dict(sorted(missing_counts.items())),
        "legacy_empty_status_receipts": legacy_empty_status_receipts,
        "samples": samples,
        "note": "Warn-only coverage explanation; pending/degraded/deterministic-baseline outputs are explicitly classified instead of hidden.",
    }


def _select_compounding_sample(
    output_reuse: list[dict[str, Any]],
    receipt_records: list[dict[str, str]],
    *,
    required_ref_prefix: str | None = None,
) -> dict[str, Any] | None:
    if not output_reuse or not receipt_records:
        return None
    receipt_by_target = {
        str(record.get("target") or ""): record
        for record in receipt_records
        if str(record.get("target") or "").strip()
    }
    for item in output_reuse:
        path = str(item.get("path") or "")
        matched_receipt = receipt_by_target.get(path)
        if matched_receipt is None or not _is_successful_compounding_receipt(matched_receipt):
            continue
        reused_refs = [str(ref) for ref in item.get("reused_refs") or [] if str(ref)]
        if required_ref_prefix is not None:
            reused_refs = [ref for ref in reused_refs if ref.startswith(required_ref_prefix)]
        if not reused_refs:
            continue
        return {
            "artifact_path": path,
            "reused_ref": reused_refs[0],
            "source_refs": item.get("source_refs") or [],
            "receipt_path": str((matched_receipt or {}).get("receipt_path") or ""),
            "receipt_subject_kind": str((matched_receipt or {}).get("subject_kind") or ""),
            "receipt_operation": str((matched_receipt or {}).get("operation") or ""),
            "provenance": "output frontmatter derived_from/source_files + receipt path",
        }
    return None


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _auto_resolution_receipt_records(root: Path) -> list[dict[str, Any]]:
    receipt_dir = root / "output" / "control" / "execution-receipts" / "auto-resolution"
    records: list[dict[str, Any]] = []
    for path in sorted(receipt_dir.glob("*.json")):
        payload = _read_json_file(path)
        if payload is None:
            continue
        payload.setdefault("receipt_path", str(path.relative_to(root)))
        records.append(payload)
    return records


def _load_auto_resolution_report(root: Path) -> dict[str, Any]:
    from aiwiki.app_state import execution_receipt_history_path, load_jsonl_documents, load_machine_memory_action_state

    state = load_machine_memory_action_state(root)
    actions = [item for item in state.get("actions", []) if isinstance(item, dict)]
    active_actions = [item for item in actions if bool(item.get("active", True))]
    human_required_actions = [
        item
        for item in active_actions
        if str(item.get("human_required") or "").lower() == "true"
        or bool(str(item.get("human_required_reason") or "").strip())
    ]
    human_reason_counts: Counter[str] = Counter(
        str(item.get("human_required_reason") or "(missing)") for item in human_required_actions
    )
    state_counts: Counter[str] = Counter(str(item.get("status") or "(missing)") for item in active_actions)
    receipt_records = _auto_resolution_receipt_records(root)
    receipt_operation_counts: Counter[str] = Counter(str(item.get("operation") or "(missing)") for item in receipt_records)
    auto_resolution_history = [
        item
        for item in load_jsonl_documents(execution_receipt_history_path(root))
        if isinstance(item, dict)
        and (
            str(item.get("generated_by") or "") == "aiwiki-auto-resolve-actions"
            or str(item.get("policy_rule_id") or "") == "machine-memory:auto-resolution:v1"
            or "machine-memory:auto-resolution:v1" in str(item.get("note") or "")
        )
    ]
    history_operation_counts: Counter[str] = Counter(str(item.get("operation") or "(missing)") for item in auto_resolution_history)
    resolved_operations = {"apply", "close", "reject", "resolve", "resolved"}
    auto_resolved_count = sum(
        count for operation, count in history_operation_counts.items() if operation in resolved_operations
    ) + sum(count for operation, count in receipt_operation_counts.items() if operation in resolved_operations)
    return {
        "version": 1,
        "status": "ok",
        "action_state_path": ".aiwiki/state/machine-memory-actions.json",
        "human_required_count": len(human_required_actions),
        "human_required_reason_counts": dict(sorted(human_reason_counts.items())),
        "active_action_count": len(active_actions),
        "active_action_state_counts": dict(sorted(state_counts.items())),
        "auto_resolution_receipt_count": len(receipt_records),
        "auto_resolution_operation_counts": dict(sorted(receipt_operation_counts.items())),
        "auto_resolution_history_count": len(auto_resolution_history),
        "auto_resolution_history_operation_counts": dict(sorted(history_operation_counts.items())),
        "auto_resolved_count": auto_resolved_count,
        "latest_human_required": [
            {
                "id": str(item.get("id") or ""),
                "kind": str(item.get("kind") or ""),
                "status": str(item.get("status") or ""),
                "human_required_reason": str(item.get("human_required_reason") or ""),
                "last_receipt_path": str(item.get("last_receipt_path") or ""),
            }
            for item in human_required_actions[:10]
        ],
    }


def _build_human_required_report(root: Path, review_backlog_counts: dict[str, Any]) -> dict[str, Any]:
    from aiwiki.today_feed import build_today_feed, primary_review_bucket_keys, routine_review_bucket_keys

    primary_buckets = set(primary_review_bucket_keys())
    routine_buckets = set(routine_review_bucket_keys())
    minimal_summary = {
        "generated_at": utc_now(),
        "review_backlog_counts": review_backlog_counts,
    }
    primary_review_counts: dict[str, int] = {}
    routine_primary_counts: dict[str, int] = {}
    for entry in build_today_feed(minimal_summary, audience="primary"):
        target = str(entry.target or "")
        if not target.startswith("review:"):
            continue
        bucket = target.split(":", 1)[1]
        count = _coerce_int(review_backlog_counts.get(bucket))
        if bucket in routine_buckets:
            routine_primary_counts[bucket] = count
        else:
            primary_review_counts[bucket] = count
    auto_resolution = _load_auto_resolution_report(root)
    primary_exception_count = sum(primary_review_counts.values())
    routine_primary_debt_count = sum(routine_primary_counts.values())
    human_required_count = _coerce_int(auto_resolution.get("human_required_count"))
    auto_resolved_count = _coerce_int(auto_resolution.get("auto_resolved_count"))
    return {
        "version": 1,
        "status": "ok",
        "primary_review_buckets": sorted(primary_buckets),
        "routine_review_buckets": sorted(routine_buckets),
        "primary_exception_counts": dict(sorted(primary_review_counts.items())),
        "primary_exception_count": primary_exception_count,
        "routine_primary_debt_counts": dict(sorted(routine_primary_counts.items())),
        "routine_primary_debt_count": routine_primary_debt_count,
        "human_required_count": human_required_count,
        "exception_count": primary_exception_count + human_required_count,
        "auto_resolved_count": auto_resolved_count,
        "auto_resolution_report": auto_resolution,
    }


def collect_metrics(root: Path, *, preview_limit: int = 20) -> dict[str, Any]:
    from aiwiki.app_content import (
        collect_aging_signals,
        collect_curated_pages,
        knowledge_lifecycle_governance_summary,
        review_queue,
    )
    from aiwiki.app_protocol import DEFAULT_PROTOCOL
    from aiwiki.app_shell.controls import shell_execution_controls, shell_review_controls
    from aiwiki.app_shell.summary import _action_review_backlog_counts
    from aiwiki.app_state import (
        load_json_document,
        load_knowledge_lifecycle_state,
        load_machine_memory,
        load_planner_state,
        nightly_health_state_path,
    )

    decisions = collect_curated_pages(root, "decisions", "decision")
    judgments = collect_curated_pages(root, "judgments", "judgment")
    active_protocol = str(load_planner_state(root).get("active_protocol") or DEFAULT_PROTOCOL)
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    memory = load_machine_memory(root)
    knowledge_lifecycle = load_knowledge_lifecycle_state(root)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    counter_evidence_scan = memory.get("health", {}).get("counter_evidence_scan", {})
    judgment_review_actions = memory.get("health", {}).get("judgment_review_actions", [])
    review_backlog_counts = {
        "pending_decisions": len(queue["pending_decisions"]),
        "pending_judgments": len(queue["pending_judgments"]),
        "overdue_reviews": len(aging["overdue"]),
        "escalation_candidates": len(aging["escalated"]),
        "counter_evidence_candidates": len(counter_evidence_scan.get("pages", [])) if isinstance(counter_evidence_scan, dict) else 0,
        "judgment_review_actions": len(judgment_review_actions) if isinstance(judgment_review_actions, list) else 0,
        "concept_backlog": lifecycle_summary.get("counts", {}).get("concept_backlog", 0),
        "review_concepts": lifecycle_summary.get("counts", {}).get("review_concepts", 0),
        "revisit_concepts": lifecycle_summary.get("counts", {}).get("revisit_concepts", 0),
        "retired_concepts": lifecycle_summary.get("counts", {}).get("retired_concepts", 0),
        "machine_memory_actions": memory.get("health", {}).get("action_counts", {}).get("total", 0),
        "ready_actions": memory.get("health", {}).get("repair_plan", {}).get("counts", {}).get("ready", 0),
        "overdue_actions": len(memory.get("health", {}).get("overdue_actions", [])),
        "escalated_actions": len(memory.get("health", {}).get("escalated_actions", [])),
    }
    review_controls = shell_review_controls(
        root,
        queue=queue,
        aging=aging,
        active_protocol=active_protocol,
        counter_evidence_scan=counter_evidence_scan if isinstance(counter_evidence_scan, dict) else {},
        review_actions=judgment_review_actions if isinstance(judgment_review_actions, list) else [],
    )
    l3_review_controls = list(review_controls.get("l3_proposals", [])) if isinstance(review_controls.get("l3_proposals", []), list) else []
    review_backlog_counts["l3_proposals"] = len(l3_review_controls)
    review_backlog_counts["l3_proposal_attention"] = sum(
        1 for proposal in l3_review_controls if isinstance(proposal, dict) and proposal.get("needs_attention")
    )
    review_backlog_counts.update(_action_review_backlog_counts(shell_execution_controls(root, memory)))
    human_required_report = _build_human_required_report(root, review_backlog_counts)
    knowledge_compounding_proof = _build_knowledge_compounding_proof(
        root,
        human_required_report=human_required_report,
    )
    legacy_empty_status_receipts = _count_legacy_empty_status_receipts(root)
    nightly = load_json_document(nightly_health_state_path(root))
    return {
        "kind": SNAPSHOT_KIND,
        "version": 1,
        "generated_by": GENERATED_BY,
        "generated_at": utc_now(),
        "root": str(root),
        "review_backlog_counts": review_backlog_counts,
        "backlog_total": _sum_int_values(review_backlog_counts),
        "human_required_report": human_required_report,
        "knowledge_compounding_proof": knowledge_compounding_proof,
        "legacy_empty_status_receipts": legacy_empty_status_receipts,
        "receipt_coverage": _build_receipt_coverage_report(
            root,
            legacy_empty_status_receipts=legacy_empty_status_receipts,
            preview_limit=preview_limit,
        ),
        "nightly_agent_loop": dict(nightly.get("agent_loop") or {}),
        "l3_proposal_counts_by_state": _load_l3_proposal_counts_by_state(root),
        "l3_generation_preview_summary": _preview_l3_generation_summary(root, limit=preview_limit),
        "l3_debt_report": _load_l3_debt_report(root, preview_limit=preview_limit),
        "planner_log_counts": _load_planner_log_counts(root),
        "judgment_review_receipt_counts": _load_judgment_review_receipt_counts(root),
        "judgment_lane_report": _load_judgment_lane_report(root),
        "prompts_ask_sha256": _sha256_path(root / PROMPTS_ASK_REL_PATH),
    }


def write_snapshot(root: Path, snapshot: dict[str, Any]) -> Path:
    path = maturity_gate_dir(root) / f"snapshot-{timestamp_slug()}.json"
    return _write_json(path, snapshot)


def _safe_collect(root: Path, *, preview_limit: int) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    try:
        return collect_metrics(root, preview_limit=preview_limit), None
    except Exception as exc:  # pragma: no cover - defensive receipt preservation
        return None, {"error_class": exc.__class__.__name__, "error_message": str(exc)}


def prepare_nightly_env(
    root: Path,
    *,
    deterministic_only: bool = False,
    no_semantic_lint: bool = False,
    compile_limit: int | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    prepared = dict(env if env is not None else os.environ)
    prepared["AIWIKI_VAULT"] = str(root)
    prepared["AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT"] = "1"
    prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_L1"] = "1"
    prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_L2"] = "1"
    prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_L3"] = "1"
    prepared["AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS"] = "1"
    prepared["AIWIKI_NIGHTLY_DETERMINISTIC_ONLY"] = "1" if deterministic_only else "0"
    prepared["AIWIKI_NIGHTLY_REQUIRE_LLM"] = "0" if deterministic_only else "1"
    if no_semantic_lint:
        prepared["AIWIKI_NIGHTLY_NO_SEMANTIC_LINT"] = "1"
    if compile_limit is not None:
        prepared["AIWIKI_NIGHTLY_COMPILE_LIMIT"] = str(compile_limit)
    return prepared


def _is_truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def classify_nightly_failure(returncode: int, stdout: str, stderr: str) -> str:
    if returncode == 0:
        return "pass"
    combined = f"{stdout}\n{stderr}".lower()
    blocked_tokens = (
        "not configured",
        "credential",
        "api key",
        "auth",
        "permission denied",
        "timeout",
        "timed out",
    )
    if any(token in combined for token in blocked_tokens):
        return "blocked"
    return "failed"


def run_nightly_subprocess(
    root: Path,
    *,
    deterministic_only: bool = False,
    no_semantic_lint: bool = False,
    compile_limit: int | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    prepared_env = prepare_nightly_env(
        root,
        deterministic_only=deterministic_only,
        no_semantic_lint=no_semantic_lint,
        compile_limit=compile_limit,
        env=env,
    )
    command = [str(REPO_ROOT / "scripts" / "run_nightly.sh")]
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        env=prepared_env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "status": classify_nightly_failure(completed.returncode, completed.stdout, completed.stderr),
        "deterministic_only": _is_truthy(prepared_env.get("AIWIKI_NIGHTLY_DETERMINISTIC_ONLY")),
        "require_llm": _is_truthy(prepared_env.get("AIWIKI_NIGHTLY_REQUIRE_LLM")),
        "stdout_excerpt": _excerpt(completed.stdout),
        "stderr_excerpt": _excerpt(completed.stderr),
    }


def _summarize_l3_generation_result(result: dict[str, Any]) -> dict[str, Any]:
    skipped = [item for item in result.get("skipped", []) if isinstance(item, dict)]
    skipped_reason_counts: Counter[str] = Counter()
    for item in skipped:
        skipped_reason_counts[str(item.get("reason") or "(missing)")] += 1
    return {
        "status": str(result.get("status") or "ok"),
        "generation_mode": str(result.get("generation_mode") or ""),
        "side_effects_allowed": bool(result.get("side_effects_allowed", False)),
        "raw_candidate_count": int(result.get("raw_candidate_count") or result.get("candidate_count") or 0),
        "candidate_count": int(result.get("candidate_count") or 0),
        "blocked_count": int(result.get("blocked_count") or 0),
        "returned_count": int(result.get("returned_count") or 0),
        "generated_count": int(result.get("generated_count") or 0),
        "skipped_count": int(result.get("skipped_count") or 0),
        "already_exists_count": skipped_reason_counts.get("already_exists", 0),
        "skipped_reason_counts": dict(sorted(skipped_reason_counts.items())),
    }


def run_gate(
    root: Path,
    *,
    preview_limit: int = 20,
    l3_limit: int = 20,
    deterministic_only: bool = False,
    no_semantic_lint: bool = False,
    compile_limit: int | None = None,
    apply_l3_generate: bool = False,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    from aiwiki.execution.l3_proposals import generate_l3_proposals_from_planner, preview_l3_proposal_generation

    before, before_error = _safe_collect(root, preview_limit=preview_limit)
    nightly = run_nightly_subprocess(
        root,
        deterministic_only=deterministic_only,
        no_semantic_lint=no_semantic_lint,
        compile_limit=compile_limit,
        env=env,
    )
    l3_generation: dict[str, Any]
    if not apply_l3_generate:
        try:
            l3_generation = _summarize_l3_generation_result(preview_l3_proposal_generation(root, limit=l3_limit))
        except Exception as exc:  # pragma: no cover - defensive receipt preservation
            l3_generation = {
                "status": "failed",
                "error_class": exc.__class__.__name__,
                "error_message": str(exc),
            }
    elif nightly["returncode"] != 0:
        l3_generation = {"status": "skipped", "reason": "nightly_failed"}
    else:
        try:
            l3_generation = _summarize_l3_generation_result(
                generate_l3_proposals_from_planner(root, limit=l3_limit)
            )
        except Exception as exc:  # pragma: no cover - defensive receipt preservation
            l3_generation = {
                "status": "failed",
                "error_class": exc.__class__.__name__,
                "error_message": str(exc),
            }
    after, after_error = _safe_collect(root, preview_limit=preview_limit)
    status = str(nightly.get("status") or "failed")
    if before_error is not None or after_error is not None:
        status = "failed"
    elif str(l3_generation.get("status") or "") == "failed":
        status = "failed"
    prompt_hash_unchanged = (before or {}).get("prompts_ask_sha256", "") == (after or {}).get("prompts_ask_sha256", "")
    if before is not None and after is not None and not prompt_hash_unchanged:
        status = "failed"
    receipt = {
        "kind": RUN_RECEIPT_KIND,
        "version": 1,
        "generated_by": GENERATED_BY,
        "generated_at": utc_now(),
        "root": str(root),
        "status": status,
        "settings": {
            "preview_limit": preview_limit,
            "l3_limit": l3_limit,
            "deterministic_only": deterministic_only,
            "no_semantic_lint": no_semantic_lint,
            "compile_limit": compile_limit,
            "skip_l3_generate": not apply_l3_generate,
            "apply_l3_generate": apply_l3_generate,
        },
        "before": before,
        "before_error": before_error,
        "nightly": nightly,
        "l3_generation": l3_generation,
        "after": after,
        "after_error": after_error,
        "prompt_hash_invariant": {
            "before": (before or {}).get("prompts_ask_sha256", ""),
            "after": (after or {}).get("prompts_ask_sha256", ""),
            "unchanged": prompt_hash_unchanged,
        },
    }
    path = maturity_gate_dir(root) / f"run-{timestamp_slug()}.json"
    written = _write_json(path, receipt)
    receipt["receipt_path"] = str(written.relative_to(root))
    _write_json(written, receipt)
    return receipt


def _load_run_receipt(path: Path, root: Path) -> dict[str, Any] | None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if str(payload.get("kind") or "") != RUN_RECEIPT_KIND:
        return None
    payload.setdefault("receipt_path", str(path.relative_to(root)))
    return payload


def load_run_receipts(root: Path, *, limit: int = 3, by_days: bool = False) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    seen_days: set[str] = set()
    for path in sorted(maturity_gate_dir(root).glob("run-*.json"), reverse=True):
        payload = _load_run_receipt(path, root)
        if payload is None:
            continue
        if by_days:
            day = _receipt_day(payload)
            if not day or day in seen_days:
                continue
            seen_days.add(day)
        receipts.append(payload)
        if len(receipts) >= limit:
            break
    receipts.reverse()
    return receipts


def _nested_int(payload: dict[str, Any] | None, *keys: str) -> int:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return 0
        current = current.get(key)
    if isinstance(current, bool):
        return int(current)
    if isinstance(current, int):
        return current
    return 0


def _receipt_day(receipt: dict[str, Any]) -> str:
    generated_at = str(receipt.get("generated_at") or "")
    return generated_at[:10] if len(generated_at) >= 10 else ""


def _validate_receipt_fields(receipt: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for side in ("before", "after"):
        snapshot = receipt.get(side)
        if not isinstance(snapshot, dict):
            missing.append(side)
            continue
        for field in REQUIRED_SNAPSHOT_FIELDS:
            if field not in snapshot:
                missing.append(f"{side}.{field}")
    l3_generation = receipt.get("l3_generation")
    if not isinstance(l3_generation, dict):
        missing.append("l3_generation")
    else:
        for field in ("candidate_count", "blocked_count", "generated_count", "skipped_count", "already_exists_count"):
            if field not in l3_generation:
                missing.append(f"l3_generation.{field}")
    return missing


def _receipt_deterministic_only(receipt: dict[str, Any]) -> bool:
    settings_payload = receipt.get("settings")
    settings = settings_payload if isinstance(settings_payload, dict) else {}
    nightly_payload = receipt.get("nightly")
    nightly = nightly_payload if isinstance(nightly_payload, dict) else {}
    return _is_truthy(settings.get("deterministic_only")) or _is_truthy(nightly.get("deterministic_only"))


def _consecutive_days(days: list[str], *, expected_count: int) -> bool:
    unique_days = sorted({day for day in days if day})
    if len(unique_days) < expected_count:
        return False
    selected = unique_days[-expected_count:]
    parsed = [datetime.strptime(day, "%Y-%m-%d").date() for day in selected]
    return all((right - left) == timedelta(days=1) for left, right in zip(parsed, parsed[1:], strict=False))


def summarize_run_receipts(receipts: list[dict[str, Any]], *, recent: int = 3) -> dict[str, Any]:
    status_counts: Counter[str] = Counter(str(item.get("status") or "unknown") for item in receipts)
    failed = [
        item
        for item in receipts
        if str(item.get("status") or "") in {"failed", "blocked"}
    ]
    prompt_hash_changed = [
        item
        for item in receipts
        if isinstance(item.get("prompt_hash_invariant"), dict)
        and item.get("prompt_hash_invariant", {}).get("unchanged") is False
    ]
    deterministic_runs = [item for item in receipts if _receipt_deterministic_only(item)]
    missing_required_fields = {
        str(item.get("receipt_path") or index): _validate_receipt_fields(item)
        for index, item in enumerate(receipts)
    }
    missing_required_fields = {path: fields for path, fields in missing_required_fields.items() if fields}
    days = [_receipt_day(item) for item in receipts]
    consecutive_days = _consecutive_days(days, expected_count=recent) if len(receipts) >= recent else False
    first = receipts[0] if receipts else {}
    last = receipts[-1] if receipts else {}
    backlog_total_delta = _nested_int(last.get("after"), "backlog_total") - _nested_int(
        first.get("before"), "backlog_total"
    )
    l3_candidate_delta = _nested_int(
        last.get("after"), "l3_proposal_counts_by_state", "candidate"
    ) - _nested_int(first.get("before"), "l3_proposal_counts_by_state", "candidate")
    judgment_review_receipts_delta = _nested_int(
        last.get("after"), "judgment_review_receipt_counts", "total"
    ) - _nested_int(first.get("before"), "judgment_review_receipt_counts", "total")
    l3_generated_total = sum(_nested_int(item, "l3_generation", "generated_count") for item in receipts)
    l3_skipped_total = sum(_nested_int(item, "l3_generation", "skipped_count") for item in receipts)
    l3_already_exists_total = sum(
        _nested_int(item, "l3_generation", "already_exists_count") for item in receipts
    )
    l3_not_eligible_total = sum(_nested_int(item, "l3_generation", "skipped_reason_counts", "not_eligible") for item in receipts)
    l3_dedupe_or_converged = l3_already_exists_total > 0 or l3_candidate_delta <= 0
    latest_l3_debt = last.get("after", {}).get("l3_debt_report") if isinstance(last.get("after"), dict) else {}
    if not isinstance(latest_l3_debt, dict):
        latest_l3_debt = {}
    latest_judgment_lane = last.get("after", {}).get("judgment_lane_report") if isinstance(last.get("after"), dict) else {}
    if not isinstance(latest_judgment_lane, dict):
        latest_judgment_lane = {}
    latest_human_required = last.get("after", {}).get("human_required_report") if isinstance(last.get("after"), dict) else {}
    if not isinstance(latest_human_required, dict):
        latest_human_required = {}
    latest_compounding_proof = last.get("after", {}).get("knowledge_compounding_proof") if isinstance(last.get("after"), dict) else {}
    if not isinstance(latest_compounding_proof, dict):
        latest_compounding_proof = {
            "kind": "knowledge-compounding-proof-report",
            "version": 1,
            "status": "not-yet",
            "verdict": "not-yet",
            "reason": "latest run receipt has no knowledge compounding proof report",
            "metrics": {},
            "compounding_sample": None,
            "missing_evidence": ["knowledge_compounding_proof"],
        }
    semantic_path_observed = judgment_review_receipts_delta > 0
    if failed or prompt_hash_changed or missing_required_fields or deterministic_runs:
        status = "fail"
    elif len(receipts) < recent:
        status = "warn"
    elif not consecutive_days:
        status = "warn"
    elif backlog_total_delta <= 0 and l3_candidate_delta <= 0 and l3_dedupe_or_converged and semantic_path_observed:
        status = "pass"
    else:
        status = "warn"
    operational_maturity = _build_operational_maturity_report(
        receipts,
        recent=recent,
        status=status,
        backlog_total_delta=backlog_total_delta,
        l3_candidate_delta=l3_candidate_delta,
        l3_dedupe_or_converged=l3_dedupe_or_converged,
        judgment_review_receipts_delta=judgment_review_receipts_delta,
    )
    return {
        "kind": "dogfood-maturity-summary",
        "version": 1,
        "generated_by": GENERATED_BY,
        "generated_at": utc_now(),
        "recent": recent,
        "receipt_count": len(receipts),
        "receipt_paths": [str(item.get("receipt_path") or "") for item in receipts],
        "status": status,
        "status_counts": dict(sorted(status_counts.items())),
        "backlog_total_delta": backlog_total_delta,
        "l3_candidate_delta": l3_candidate_delta,
        "l3_generated_total": l3_generated_total,
        "l3_skipped_total": l3_skipped_total,
        "l3_already_exists_total": l3_already_exists_total,
        "l3_not_eligible_total": l3_not_eligible_total,
        "l3_dedupe_or_converged": l3_dedupe_or_converged,
        "l3_debt_report": latest_l3_debt,
        "l3_effective_candidate_count": _coerce_int(latest_l3_debt.get("effective_preview_candidate_count")),
        "l3_dedupe_or_noise_ratio": latest_l3_debt.get("dedupe_or_noise_ratio", 0.0),
        "judgment_review_processed_delta": judgment_review_receipts_delta,
        "judgment_review_new_receipts": max(judgment_review_receipts_delta, 0),
        "judgment_lane_report": latest_judgment_lane,
        "human_required_report": latest_human_required,
        "knowledge_compounding_proof": latest_compounding_proof,
        "knowledge_compounding_status": str(latest_compounding_proof.get("status") or "not-yet"),
        "knowledge_compounding_missing_evidence": list(latest_compounding_proof.get("missing_evidence") or []),
        "knowledge_compounding_sample": latest_compounding_proof.get("compounding_sample"),
        "human_required_count": _coerce_int(latest_human_required.get("human_required_count")),
        "routine_primary_debt_count": _coerce_int(latest_human_required.get("routine_primary_debt_count")),
        "exception_count": _coerce_int(latest_human_required.get("exception_count")),
        "auto_resolved_count": _coerce_int(latest_human_required.get("auto_resolved_count")),
        "judgment_review_failure_rate": latest_judgment_lane.get("failure_rate", 0.0),
        "judgment_review_exception_rate": latest_judgment_lane.get("exception_rate", 0.0),
        "semantic_path_observed": semantic_path_observed,
        "days": days,
        "consecutive_days": consecutive_days,
        "missing_required_fields": missing_required_fields,
        "failed_runs": [str(item.get("receipt_path") or "") for item in failed],
        "deterministic_only_runs": [str(item.get("receipt_path") or "") for item in deterministic_runs],
        "prompt_hash_changed_runs": [str(item.get("receipt_path") or "") for item in prompt_hash_changed],
        "operational_maturity": operational_maturity,
    }


def _build_operational_maturity_report(
    receipts: list[dict[str, Any]],
    *,
    recent: int,
    status: str,
    backlog_total_delta: int,
    l3_candidate_delta: int,
    l3_dedupe_or_converged: bool,
    judgment_review_receipts_delta: int,
) -> dict[str, Any]:
    latest = receipts[-1] if receipts else {}
    latest_after = latest.get("after") if isinstance(latest.get("after"), dict) else {}
    if not isinstance(latest_after, dict):
        latest_after = {}
    l3_debt_payload = latest_after.get("l3_debt_report")
    l3_debt = l3_debt_payload if isinstance(l3_debt_payload, dict) else {}
    judgment_lane_payload = latest_after.get("judgment_lane_report")
    judgment_lane = judgment_lane_payload if isinstance(judgment_lane_payload, dict) else {}
    human_required_payload = latest_after.get("human_required_report")
    human_required = human_required_payload if isinstance(human_required_payload, dict) else {}
    failed_receipts = sum(1 for item in receipts if str(item.get("status") or "") in {"failed", "blocked"})
    deterministic_runs = [item for item in receipts if _receipt_deterministic_only(item)]
    exception_count = _coerce_int(judgment_lane.get("exception_count"))
    failure_rate = float(judgment_lane.get("failure_rate") or 0.0)
    exception_rate = float(judgment_lane.get("exception_rate") or 0.0)
    anomaly_budget = {
        "max_failed_runs": 0,
        "max_judgment_failure_rate": 0.0,
        "max_judgment_exception_rate": 0.2,
        "max_effective_l3_candidates": 0,
        "max_routine_primary_debt_count": 0,
        "requires_consecutive_days": recent,
    }
    budget_violations: list[str] = []
    if failed_receipts > anomaly_budget["max_failed_runs"]:
        budget_violations.append("failed_runs")
    if failure_rate > anomaly_budget["max_judgment_failure_rate"]:
        budget_violations.append("judgment_failure_rate")
    if exception_rate > anomaly_budget["max_judgment_exception_rate"]:
        budget_violations.append("judgment_exception_rate")
    if _coerce_int(l3_debt.get("effective_preview_candidate_count")) > anomaly_budget["max_effective_l3_candidates"]:
        budget_violations.append("effective_l3_candidates")
    if _coerce_int(human_required.get("routine_primary_debt_count")) > anomaly_budget["max_routine_primary_debt_count"]:
        budget_violations.append("routine_primary_debt")
    prompt_hash_changed = [
        item
        for item in receipts
        if isinstance(item.get("prompt_hash_invariant"), dict)
        and item.get("prompt_hash_invariant", {}).get("unchanged") is False
    ]
    missing_required_fields = {
        str(item.get("receipt_path") or index): _validate_receipt_fields(item)
        for index, item in enumerate(receipts)
    }
    missing_required_fields = {path: fields for path, fields in missing_required_fields.items() if fields}
    consecutive_receipts = _consecutive_days([_receipt_day(item) for item in receipts], expected_count=recent)
    receipt_integrity_ok = (
        len(receipts) >= recent
        and consecutive_receipts
        and failed_receipts == 0
        and not deterministic_runs
        and not prompt_hash_changed
        and not missing_required_fields
    )
    human_only_exceptions = receipt_integrity_ok and not budget_violations
    if human_only_exceptions:
        reason = "required receipts and anomaly budget pass"
    elif not receipt_integrity_ok:
        reason = "insufficient consecutive proof or receipt integrity not met"
    else:
        reason = "anomaly budget not met"
    return {
        "version": 1,
        "status": "pass" if human_only_exceptions else "not-yet",
        "human_only_exceptions": human_only_exceptions,
        "reason": reason,
        "anomaly_budget": anomaly_budget,
        "budget_violations": budget_violations,
        "receipt_integrity": {
            "status": "pass" if receipt_integrity_ok else "not-yet",
            "receipt_count": len(receipts),
            "consecutive_days": consecutive_receipts,
            "missing_required_fields": missing_required_fields,
            "deterministic_only_runs": [str(item.get("receipt_path") or "") for item in deterministic_runs],
            "prompt_hash_changed_runs": [str(item.get("receipt_path") or "") for item in prompt_hash_changed],
        },
        "latest": {
            "failed_runs": failed_receipts,
            "judgment_exception_count": exception_count,
            "judgment_failure_rate": failure_rate,
            "judgment_exception_rate": exception_rate,
            "effective_l3_candidates": _coerce_int(l3_debt.get("effective_preview_candidate_count")),
            "l3_dedupe_or_noise_ratio": l3_debt.get("dedupe_or_noise_ratio", 0.0),
            "human_required_count": _coerce_int(human_required.get("human_required_count")),
            "routine_primary_debt_count": _coerce_int(human_required.get("routine_primary_debt_count")),
            "exception_count": _coerce_int(human_required.get("exception_count")),
            "auto_resolved_count": _coerce_int(human_required.get("auto_resolved_count")),
        },
        "trend_windows": {
            str(recent): {
                "receipt_count": len(receipts),
                "backlog_total_delta": backlog_total_delta,
                "l3_candidate_delta": l3_candidate_delta,
                "l3_dedupe_or_converged": l3_dedupe_or_converged,
                "judgment_review_processed_delta": judgment_review_receipts_delta,
                "judgment_failure_rate": failure_rate,
                "judgment_exception_rate": exception_rate,
            },
            "7": _summarize_operational_window(receipts[-7:]),
            "14": _summarize_operational_window(receipts[-14:]),
        },
    }


def _summarize_operational_window(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    if not receipts:
        return {"receipt_count": 0, "backlog_total_delta": 0, "l3_candidate_delta": 0}
    first = receipts[0]
    last = receipts[-1]
    last_after_payload = last.get("after")
    last_after = last_after_payload if isinstance(last_after_payload, dict) else {}
    judgment_lane_payload = last_after.get("judgment_lane_report")
    judgment_lane = judgment_lane_payload if isinstance(judgment_lane_payload, dict) else {}
    l3_debt_payload = last_after.get("l3_debt_report")
    l3_debt = l3_debt_payload if isinstance(l3_debt_payload, dict) else {}
    return {
        "receipt_count": len(receipts),
        "backlog_total_delta": _nested_int(last.get("after"), "backlog_total") - _nested_int(first.get("before"), "backlog_total"),
        "l3_candidate_delta": _nested_int(last.get("after"), "l3_proposal_counts_by_state", "candidate") - _nested_int(first.get("before"), "l3_proposal_counts_by_state", "candidate"),
        "l3_dedupe_or_noise_ratio": l3_debt.get("dedupe_or_noise_ratio", 0.0),
        "judgment_failure_rate": judgment_lane.get("failure_rate", 0.0),
        "judgment_exception_rate": judgment_lane.get("exception_rate", 0.0),
    }


def summarize_recent_run_receipts(root: Path, *, recent: int = 3, by_days: bool = False) -> dict[str, Any]:
    receipts = load_run_receipts(root, limit=recent, by_days=by_days)
    summary = summarize_run_receipts(receipts, recent=recent)
    if not by_days:
        return summary
    operational_maturity = summary.get("operational_maturity")
    if not isinstance(operational_maturity, dict):
        return summary
    trend_windows = operational_maturity.get("trend_windows")
    if not isinstance(trend_windows, dict):
        return summary
    trend_windows["7"] = _summarize_operational_window(load_run_receipts(root, limit=7, by_days=True))
    trend_windows["14"] = _summarize_operational_window(load_run_receipts(root, limit=14, by_days=True))
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Dogfood vault root override.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="Collect read-only maturity metrics.")
    collect_parser.add_argument("--root", default=argparse.SUPPRESS, help="Dogfood vault root override.")
    collect_parser.add_argument("--preview-limit", type=int, default=20)
    collect_parser.add_argument("--write", action="store_true")

    run_parser = subparsers.add_parser("run", help="Run nightly plus maturity sampling.")
    run_parser.add_argument("--root", default=argparse.SUPPRESS, help="Dogfood vault root override.")
    run_parser.add_argument("--preview-limit", type=int, default=20)
    run_parser.add_argument("--l3-limit", type=int, default=20)
    run_parser.add_argument("--compile-limit", type=int)
    run_parser.add_argument("--deterministic-only", action="store_true")
    run_parser.add_argument("--no-semantic-lint", action="store_true")
    run_parser.add_argument(
        "--apply-l3-generate",
        action="store_true",
        help="Allow the gate itself to create eligible L3 proposal candidates after nightly. Default is preview-only.",
    )

    summarize_parser = subparsers.add_parser("summarize", help="Summarize recent run receipts.")
    summarize_parser.add_argument("--root", default=argparse.SUPPRESS, help="Dogfood vault root override.")
    summarize_parser.add_argument("--recent", type=int, default=3)
    summarize_parser.add_argument("--days", type=int, help="Summarize the latest receipt from each of N consecutive calendar days.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = resolve_root(args.root)

    if args.command == "collect":
        snapshot = collect_metrics(root, preview_limit=args.preview_limit)
        if args.write:
            path = write_snapshot(root, snapshot)
            snapshot = {**snapshot, "snapshot_path": str(path.relative_to(root))}
        print(_json_dump(snapshot), end="")
        return 0

    if args.command == "run":
        receipt = run_gate(
            root,
            preview_limit=args.preview_limit,
            l3_limit=args.l3_limit,
            deterministic_only=args.deterministic_only,
            no_semantic_lint=args.no_semantic_lint,
            compile_limit=args.compile_limit,
            apply_l3_generate=args.apply_l3_generate,
        )
        print(_json_dump(receipt), end="")
        return 0 if receipt.get("status") == "pass" else 1

    if args.command == "summarize":
        by_days = args.days is not None
        summary = summarize_recent_run_receipts(root, recent=args.days if by_days else args.recent, by_days=by_days)
        print(_json_dump(summary), end="")
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
