"""Nightly auto-adoption of L1 / L2 / L3 governance backlog.

Extends the nightly agent loop beyond deterministic light-primitive apply
(compile / lint / nightly) into *semantic-candidate adoption*. The original
boundary kept L1 candidate-only and L2/L3 gate-only; this module changes the
design so that 炼丹炉 can silently auto-adopt safe-category items by default.

Opt-in per level via env vars:
- ``AIWIKI_NIGHTLY_AUTO_ADOPT_L1=1`` — auto-adopt L1 semantic candidates
- ``AIWIKI_NIGHTLY_AUTO_ADOPT_L2=1`` — auto-adopt L2 machine-memory actions
- ``AIWIKI_NIGHTLY_AUTO_ADOPT_L3=1`` — auto-adopt L3 proposals (prompt / policy)
- ``AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS=1`` — auto-adopt judgment reviews

Policy (aligned with 炼丹炉 self-evolution philosophy):
  L1 — concept backlog / revisit / source-concept links
  L2 — concept splits (deterministic overloaded-concept proposals)
  L3 — prompt / policy / schema proposals (auto-adopted with receipt for audit/revert)
  Judgment — counter-evidence / judgment review (LLM-powered, nightly path)

All auto-adopted items write receipts and support revert.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from ..app_execution import append_execution_receipt_history
from ..app_shell.controls import shell_execution_controls, shell_review_controls
from ..app_state import (
    CorruptStateError,
    append_runtime_history,
    execution_receipt_history_path,
    load_jsonl_documents_strict,
    load_machine_memory,
    load_planner_state,
)
from ..app_utils import _restore_file_bytes, _snapshot_file_bytes, relative_path, runtime_write_operation, utc_now
from ..config import l3_auto_adopt_min_evidence_from_env
from ..execution.lifecycle import review_concepts_batch
from ..execution.machine_memory_actions import review_machine_memory_actions_batch
from ..execution.machine_memory_batch import apply_machine_memory_actions_batch
from ..render.paths import execution_receipt_path


def _build_controls(root: Path):
    """Load the review and execution control surfaces."""
    from ..app_compile import collect_aging_signals, review_queue
    from ..app_state import (
        DEFAULT_PROTOCOL,
        load_compile_state,
    )

    compile_state = load_compile_state(root)
    memory = load_machine_memory(root)
    planner_state = load_planner_state(root)
    decisions = compile_state.get("decisions", [])
    judgments = compile_state.get("judgments", [])
    active_protocol = str(planner_state.get("active_protocol") or DEFAULT_PROTOCOL)
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    counter_evidence_scan = memory.get("health", {}).get("counter_evidence_scan", {})
    judgment_review_actions = memory.get("health", {}).get("judgment_review_actions", [])
    review_ctrl = shell_review_controls(
        root,
        queue=queue,
        aging=aging,
        active_protocol=active_protocol,
        counter_evidence_scan=counter_evidence_scan if isinstance(counter_evidence_scan, dict) else {},
        review_actions=judgment_review_actions if isinstance(judgment_review_actions, list) else [],
    )
    exec_ctrl = shell_execution_controls(root, memory)
    return review_ctrl, exec_ctrl

_logger = logging.getLogger(__name__)

_L1_CONCEPT_STATUS = "active"
_L1_REVISIT_STATUS = "deferred"
_L1_ACTION_STATUS = "accepted"
_L2_CONCEPT_SPLIT_STATUS = "accepted"


class JudgmentReviewAuditError(RuntimeError):
    def __init__(self, action_id: str, failed_step: str, *, target_path: str, before_hash: str, after_hash: str):
        super().__init__(f"Judgment review succeeded but audit step '{failed_step}' failed for {action_id}")
        self.action_id = action_id
        self.failed_step = failed_step
        self.target_path = target_path
        self.before_hash = before_hash
        self.after_hash = after_hash


def _env_flag(name: str) -> bool:
    import os

    value = os.environ.get(name, "0")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@runtime_write_operation
def auto_adopt_l1(root: Path) -> dict[str, Any]:
    """Auto-adopt L1 semantic candidates.

    Covers: concept backlog, revisit concepts, source-concept link actions.
    Counter-evidence is handled by LLM-powered judgment review, not here.
    """
    results: dict[str, Any] = {"level": "L1", "applied": False, "items": []}
    try:
        review_ctrl, exec_ctrl = _build_controls(root)
    except Exception as exc:
        results["error"] = f"control surface unavailable: {exc}"
        results["degraded"] = True
        return results

    # --- L1a: concept backlog → active ---
    concept_backlog = [
        item.get("slug", "")
        for item in review_ctrl.get("concept_backlog", [])
        if isinstance(item, dict) and item.get("slug")
    ]
    results["concept_backlog_pending"] = len(concept_backlog)
    if concept_backlog:
        try:
            r = review_concepts_batch(root, concept_backlog, status=_L1_CONCEPT_STATUS, note="nightly L1 auto-adopt: concept backlog → active")
            results["items"].append({"kind": "concept_backlog", "count": r.get("count", 0), "status": _L1_CONCEPT_STATUS})
            if int(r.get("count", 0) or 0) > 0:
                results["applied"] = True
        except Exception as exc:
            results["items"].append({"kind": "concept_backlog", "error": str(exc)})
            results["degraded"] = True
            return results

    # --- L1b: revisit concepts → deferred ---
    revisit = [
        item.get("slug", "")
        for item in review_ctrl.get("revisit_concepts", [])
        if isinstance(item, dict) and item.get("slug")
    ]
    results["revisit_concepts_pending"] = len(revisit)
    if revisit:
        try:
            r = review_concepts_batch(root, revisit, status=_L1_REVISIT_STATUS, note="nightly L1 auto-adopt: revisit → deferred")
            results["items"].append({"kind": "revisit_concepts", "count": r.get("count", 0), "status": _L1_REVISIT_STATUS})
            if int(r.get("count", 0) or 0) > 0:
                results["applied"] = True
        except Exception as exc:
            results["items"].append({"kind": "revisit_concepts", "error": str(exc)})
            results["degraded"] = True
            return results

    # --- L1c: source-concept link actions → accepted + apply ---
    link_actions = [
        a.get("action_id", "")
        for a in exec_ctrl.get("actions", [])
        if isinstance(a, dict)
        and a.get("kind") == "add-source-concept-link"
        and a.get("status") == "proposed"
        and str(a.get("can_review", "")).lower() in {"true", "1", "yes"}
    ]
    link_actions = [aid for aid in link_actions if aid]
    results["source_concept_links_pending"] = len(link_actions)
    if link_actions:
        try:
            r = review_machine_memory_actions_batch(root, link_actions, status=_L1_ACTION_STATUS, note="nightly L1 auto-adopt: source-concept link accepted")
            results["items"].append({"kind": "source_concept_links", "status": _L1_ACTION_STATUS, "count": r.get("count", 0)})
            if int(r.get("count", 0) or 0) > 0:
                results["applied"] = True
        except Exception as exc:
            results["items"].append({"kind": "source_concept_links", "error": str(exc)})
            results["degraded"] = True
            return results

    # Apply only links accepted in this run, after reloading execution state.
    apply_source = exec_ctrl
    if link_actions:
        try:
            _, apply_source = _build_controls(root)
        except Exception as exc:
            results["items"].append({"kind": "apply_accepted", "error": str(exc)})
            results["degraded"] = True
            return results
    accepted_link_ids = set(link_actions)
    apply_ids = [
        a.get("action_id", "")
        for a in apply_source.get("actions", [])
        if isinstance(a, dict) and a.get("action_id") in accepted_link_ids and str(a.get("can_apply", "")).lower() in {"true", "1", "yes"}
    ]
    apply_ids = [aid for aid in apply_ids if aid]
    if apply_ids:
        try:
            r = apply_machine_memory_actions_batch(root, apply_ids, note="nightly L1 auto-adopt: apply accepted low-risk", dry_run=False)
            results["items"].append({"kind": "apply_accepted", "count": r.get("applied_count", r.get("count", 0))})
            if int(r.get("applied_count", r.get("count", 0)) or 0) > 0:
                results["applied"] = True
        except Exception as exc:
            results["items"].append({"kind": "apply_accepted", "error": str(exc)})
            results["degraded"] = True
            return results

    applied = any(item.get("count", 0) > 0 for item in results["items"] if "count" in item)
    results["applied"] = applied
    return results


@runtime_write_operation
def auto_adopt_l2(root: Path) -> dict[str, Any]:
    """Auto-adopt L2 machine-memory actions (concept splits only).

    Concept splits are deterministic proposals from the overloaded-concept
    detector. They are low-risk structural changes.
    """
    results: dict[str, Any] = {"level": "L2", "applied": False, "items": []}
    try:
        _review_ctrl, exec_ctrl = _build_controls(root)
    except Exception as exc:
        results["error"] = f"execution control unavailable: {exc}"
        results["degraded"] = True
        return results

    split_actions = [
        a.get("action_id", "")
        for a in exec_ctrl.get("actions", [])
        if isinstance(a, dict)
        and a.get("kind") == "split-overloaded-concept"
        and a.get("status") == "proposed"
        and str(a.get("can_review", "")).lower() in {"true", "1", "yes"}
    ]
    results["concept_splits_pending"] = len(split_actions)
    if split_actions:
        try:
            r = review_machine_memory_actions_batch(root, split_actions, status=_L2_CONCEPT_SPLIT_STATUS, note="nightly L2 auto-adopt: concept split accepted")
            results["items"].append({"kind": "concept_splits_accepted", "count": r.get("count", 0)})
            if int(r.get("count", 0) or 0) > 0:
                results["applied"] = True
        except Exception as exc:
            results["items"].append({"kind": "concept_splits_accepted", "error": str(exc)})
            results["degraded"] = True
            return results

    # Apply only splits accepted in this run, after reloading execution state.
    apply_source = exec_ctrl
    if split_actions:
        try:
            _, apply_source = _build_controls(root)
        except Exception as exc:
            results["items"].append({"kind": "concept_splits_applied", "error": str(exc)})
            results["degraded"] = True
            return results
    accepted_split_ids = set(split_actions)
    apply_ids = [
        a.get("action_id", "")
        for a in apply_source.get("actions", [])
        if isinstance(a, dict)
        and a.get("action_id") in accepted_split_ids
        and a.get("kind") == "split-overloaded-concept"
        and str(a.get("can_apply", "")).lower() in {"true", "1", "yes"}
    ]
    if apply_ids:
        try:
            r = apply_machine_memory_actions_batch(root, apply_ids, note="nightly L2 auto-adopt: apply concept splits", dry_run=False)
            results["items"].append({"kind": "concept_splits_applied", "count": r.get("applied_count", r.get("count", 0))})
            if int(r.get("applied_count", r.get("count", 0)) or 0) > 0:
                results["applied"] = True
        except Exception as exc:
            results["items"].append({"kind": "concept_splits_applied", "error": str(exc)})
            results["degraded"] = True
            return results

    applied = any(item.get("count", 0) > 0 for item in results["items"] if "count" in item)
    results["applied"] = applied
    return results


@runtime_write_operation
def auto_adopt_judgments(
    root: Path,
    client: Any,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """LLM-powered judgment review for counter-evidence pages.

    Reads each judgment page, the new sources that may refute it, and asks the
    LLM to produce a structured review. The review is appended as a review
    history entry on the judgment page.

    Args:
        root: Vault root path.
        client: An LLM client implementing ``SupportsComplete``.
        limit: Max pages to review per nightly run (default 5).
    """
    import json as _json

    results: dict[str, Any] = {"level": "Judgment", "applied": False, "items": [], "limit": limit, "exception_queue": []}

    try:
        from ..app_state import load_machine_memory

        memory = load_machine_memory(root)
    except Exception as exc:
        results["error"] = f"memory unavailable: {exc}"
        return results

    scan = memory.get("health", {}).get("counter_evidence_scan", {})
    pages = scan.get("pages") if isinstance(scan, dict) else []
    if not isinstance(pages, list) or not pages:
        results["message"] = "no counter-evidence pages to review"
        return results

    reviewed = 0
    failed = 0
    exception_count = 0
    confidence_counts: Counter[str] = Counter()
    conclusion_counts: Counter[str] = Counter()
    scan_generated_at = str(scan.get("generated_at") or "") if isinstance(scan, dict) else ""
    scan_id = scan.get("id") if isinstance(scan, dict) else None
    reviewer_model = "judgment-llm"
    for page in pages[:limit]:
        if not isinstance(page, dict):
            continue
        page_path_str = str(page.get("page_path") or "").strip()
        source_ids = page.get("source_ids")
        if not page_path_str or not isinstance(source_ids, list) or not source_ids:
            continue

        page_path = root / page_path_str
        if not page_path.exists():
            continue

        if not scan_generated_at:
            _record_judgment_review_failed(
                root,
                page_path=page_path_str,
                scan_id=scan_id,
                reviewer_model=reviewer_model,
                failure_reason="missing_scan_generated_at",
                error="counter_evidence_scan.generated_at is required",
            )
            results["items"].append({"page": page_path_str, "status": "missing_scan_generated_at"})
            failed += 1
            continue

        try:
            judgment_text = page_path.read_text(encoding="utf-8")
            sources_text = _read_source_pages(root, source_ids, max_chars=8000)
            conclusion = _llm_review_judgment(client, judgment_text, sources_text, str(page.get("page_title") or page_path_str))
            conclusion_value = str(conclusion.get("conclusion") or "")
            confidence_value = str(conclusion.get("confidence") or "")
            confidence_counts[confidence_value or "(missing)"] += 1
            conclusion_counts[conclusion_value or "(missing)"] += 1
            if conclusion_value in {"error", "unparsed"}:
                item = {
                    "page": page_path_str,
                    "status": "llm_failed" if conclusion_value == "error" else "llm_unparsed",
                    "conclusion": conclusion_value,
                }
                if conclusion.get("error"):
                    item["error"] = conclusion.get("error")
                if conclusion.get("raw"):
                    item["raw"] = conclusion.get("raw")
                results["items"].append(item)
                exception_count += 1
                _append_judgment_exception(
                    results,
                    page_path=page_path_str,
                    reason=item["status"],
                    conclusion=conclusion_value,
                    confidence=confidence_value,
                    review_id="",
                )
                _record_judgment_review_failed(
                    root,
                    page_path=page_path_str,
                    scan_id=scan_id,
                    reviewer_model=reviewer_model,
                    failure_reason=item["status"],
                    error=conclusion.get("error"),
                    raw=conclusion.get("raw"),
                )
                failed += 1
                continue
            write_result = _write_review_entry(
                root,
                page_path_str,
                conclusion,
                scan_generated_at=scan_generated_at,
                reviewer_model=reviewer_model,
            )
            results["items"].append({
                "page": page_path_str,
                "status": write_result.get("status", "applied"),
                "conclusion": conclusion.get("conclusion", "?"),
                "confidence": conclusion.get("confidence", "?"),
                **({"review_id": write_result.get("review_id")} if write_result.get("review_id") else {}),
            })
            if write_result.get("status") == "receipt_history_corrupt":
                exception_count += 1
                _append_judgment_exception(
                    results,
                    page_path=page_path_str,
                    reason="receipt_history_corrupt",
                    conclusion=conclusion_value,
                    confidence=confidence_value,
                    review_id=str(write_result.get("review_id") or ""),
                )
                _record_judgment_review_failed(
                    root,
                    page_path=page_path_str,
                    scan_id=scan_id,
                    reviewer_model=reviewer_model,
                    failure_reason="receipt_history_corrupt",
                    error="execution receipt history is corrupt; fail-closed to avoid duplicate judgment review write",
                )
                failed += 1
                continue
            if write_result.get("status") == "applied":
                reviewed += 1
                exception_reason = _judgment_review_exception_reason(conclusion_value, confidence_value)
                if exception_reason:
                    exception_count += 1
                    _append_judgment_exception(
                        results,
                        page_path=page_path_str,
                        reason=exception_reason,
                        conclusion=conclusion_value,
                        confidence=confidence_value,
                        review_id=str(write_result.get("review_id") or ""),
                    )
        except Exception as exc:
            results["items"].append({"page": page_path_str, "status": "failed", "error": str(exc)})
            failed += 1
            exception_count += 1
            _append_judgment_exception(
                results,
                page_path=page_path_str,
                reason="failed",
                conclusion="error",
                confidence="low",
                review_id="",
            )
            if isinstance(exc, JudgmentReviewAuditError):
                results["degraded"] = True

    results["reviewed"] = reviewed
    results["failed"] = failed
    results["exception_count"] = exception_count
    results["exception_rate"] = round(exception_count / len(pages), 4) if pages else 0.0
    results["confidence_counts"] = dict(sorted(confidence_counts.items()))
    results["conclusion_counts"] = dict(sorted(conclusion_counts.items()))
    if failed > 0:
        results["degraded"] = True
    results["total_candidates"] = len(pages)
    results["applied"] = reviewed > 0
    return results


def _judgment_review_exception_reason(conclusion: str, confidence: str) -> str:
    if conclusion in {"weakened", "refuted"}:
        return conclusion
    if str(confidence or "").lower() == "low":
        return "low-confidence"
    return ""


def _append_judgment_exception(
    results: dict[str, Any],
    *,
    page_path: str,
    reason: str,
    conclusion: str,
    confidence: str,
    review_id: str,
) -> None:
    queue = results.setdefault("exception_queue", [])
    if isinstance(queue, list):
        queue.append(
            {
                "page": page_path,
                "reason": reason,
                "conclusion": conclusion,
                "confidence": confidence,
                "review_id": review_id,
            }
        )


def _record_judgment_review_failed(
    root: Path,
    *,
    page_path: str,
    scan_id: Any,
    reviewer_model: str,
    failure_reason: str,
    error: Any = None,
    raw: Any = None,
) -> None:
    try:
        append_runtime_history(
            root,
            {
                "event_type": "judgment-review-failed",
                "occurred_at": utc_now(),
                "page_path": page_path,
                "scan_id": scan_id,
                "reviewer_model": reviewer_model,
                "failure_reason": failure_reason,
                "error": str(error)[:500] if error else None,
                "raw_excerpt": str(raw)[:200] if raw else None,
            },
        )
    except Exception as exc:
        print(f"warning: failed to write judgment-review-failed audit: {exc}")


def _read_source_pages(root: Path, source_ids: list[str], max_chars: int = 8000) -> str:
    """Read up to 4 new source pages, truncating to ``max_chars`` total."""
    parts: list[str] = []
    total = 0
    for sid in source_ids[:4]:
        if not isinstance(sid, str) or not sid.strip():
            continue
        # Normalize: source_ids may be bare ids or wiki/sources/<id>.md paths
        source_path = root / "wiki" / "sources" / f"{sid}.md"
        if not source_path.exists():
            # Try as-is path
            source_path = root / sid
        if not source_path.exists():
            continue
        content = source_path.read_text(encoding="utf-8")
        remaining = max_chars - total
        if remaining <= 0:
            break
        if len(content) > remaining:
            content = content[:remaining] + "\n…(truncated)"
        parts.append(f"--- 来源: {sid} ---\n{content}")
        total += len(content)
    return "\n\n".join(parts) if parts else "(无新来源内容可读)"


_JUDGMENT_SYSTEM_PROMPT = """你是炼丹炉的判断复核 Agent。读取一个已有的判断页和可能反驳它的新来源材料，分析新证据是否动摇了原始判断。

返回纯 JSON（不要 markdown 包裹）：
{
  "conclusion": "upheld" | "weakened" | "refuted",
  "confidence": "high" | "medium" | "low",
  "counter_evidence_found": true | false,
  "key_findings": ["发现1", "发现2"],
  "recommendation": "一句话建议：是否需要人工复审，或判断是否仍然成立"
}

判断标准：
- upheld：新来源与原始判断一致或无关，判断仍然成立
- weakened：新来源引入了一些不确定性，但不足以推翻原始判断
- refuted：新来源明确反驳了原始判断的核心论点
"""


def _llm_review_judgment(
    client: Any,
    judgment_text: str,
    sources_text: str,
    title: str,
) -> dict[str, Any]:
    """Call the LLM to review a judgment with new evidence."""
    import json as _json
    import re

    user_prompt = f"""## 原始判断

{judgment_text[:12000]}

## 新来源材料

{sources_text}

请分析新来源是否反驳了原始判断，返回 JSON。"""
    try:
        result = client.complete(
            system_prompt=_JUDGMENT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        text = str(getattr(result, "text", "") or "")
    except Exception as exc:
        return {"conclusion": "error", "confidence": "low", "error": str(exc)}

    # Extract JSON from potential markdown fences
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {"conclusion": "unparsed", "confidence": "low", "raw": text[:500]}
    try:
        return _json.loads(match.group(0))
    except (_json.JSONDecodeError, TypeError):
        return {"conclusion": "unparsed", "confidence": "low", "raw": text[:500]}


def _has_judgment_review_receipt(root: Path, review_id: str) -> tuple[str, bool | None]:
    try:
        records = load_jsonl_documents_strict(execution_receipt_history_path(root))
    except CorruptStateError:
        return "corrupt", None
    for record in records:
        if record.get("subject_kind") == "judgment_review" and record.get("subject_id") == review_id:
            return "ok", True
    return "ok", False


def _apply_judgment_review_with_receipt(target: Path, mutate_fn: Callable[[str], str], receipt_meta: dict[str, Any]) -> dict[str, Any]:
    root = Path(receipt_meta["root"])
    target_snapshot = _snapshot_file_bytes(target)
    receipt_path: Path
    receipt_snapshot: bytes | None
    history_snapshot = _snapshot_file_bytes(execution_receipt_history_path(root))
    runtime_history_snapshot = _snapshot_file_bytes(root / ".aiwiki" / "state" / "runtime-history.jsonl")
    original = target_snapshot.decode("utf-8") if target_snapshot is not None else ""
    before_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
    new_content = mutate_fn(original)
    after_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
    action_id = f"judgment-review-{receipt_meta['review_id']}"
    receipt_path = execution_receipt_path(root, action_id)
    receipt_snapshot = _snapshot_file_bytes(receipt_path)
    target_rel = relative_path(root, target)
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-judgment-review",
        "applied_at": receipt_meta["occurred_at"],
        "operation": "apply",
        "action_id": action_id,
        "subject_kind": "judgment_review",
        "subject_id": str(receipt_meta["review_id"]),
        "judgment_id": str(receipt_meta["judgment_id"]),
        "target_file": target_rel,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "before_content": original,
        "after_content": new_content,
        "note": "nightly judgment review",
        "revert_supported": False,
        "revert_policy": "manual_only",
        "revert_note": "Judgment review pages must be reverted manually; automated revert not yet supported.",
        "receipt_path": relative_path(root, receipt_path),
        "scan_generated_at": str(receipt_meta.get("scan_generated_at") or ""),
        "reviewer_model": str(receipt_meta.get("reviewer_model") or ""),
        "conclusion": str(receipt_meta.get("conclusion") or ""),
        "confidence": str(receipt_meta.get("confidence") or ""),
    }
    def rollback() -> None:
        _restore_file_bytes(target, target_snapshot)
        _restore_file_bytes(receipt_path, receipt_snapshot)
        _restore_file_bytes(execution_receipt_history_path(root), history_snapshot)
        _restore_file_bytes(root / ".aiwiki" / "state" / "runtime-history.jsonl", runtime_history_snapshot)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content, encoding="utf-8")
    except Exception:
        rollback()
        raise

    try:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        rollback()
        raise

    try:
        append_execution_receipt_history(root, receipt)
    except Exception as exc:
        rollback()
        raise JudgmentReviewAuditError(
            action_id,
            "append_execution_receipt_history",
            target_path=target_rel,
            before_hash=before_hash,
            after_hash=after_hash,
        ) from exc

    try:
        append_runtime_history(
            root,
            {
                "event_type": "judgment-review",
                "action_id": action_id,
                "sha256": after_hash,
                "target_path": target_rel,
                **{key: value for key, value in receipt_meta.items() if key != "root"},
            },
        )
    except Exception as exc:
        rollback()
        raise JudgmentReviewAuditError(
            action_id,
            "append_runtime_history",
            target_path=target_rel,
            before_hash=before_hash,
            after_hash=after_hash,
        ) from exc
    return {"status": "applied", "sha256": after_hash, "target_path": str(target), "receipt_path": relative_path(root, receipt_path), "action_id": action_id}


def _write_review_entry(
    root: Path,
    page_path: str,
    conclusion: dict[str, Any],
    *,
    scan_generated_at: str = "",
    reviewer_model: str = "unknown",
) -> dict[str, Any]:
    """Append a review history entry to a judgment page."""
    page = root / page_path
    if not page.exists():
        return {"status": "skipped_missing"}
    scan_at = str(conclusion.get("scan_generated_at") or scan_generated_at or "")
    if not scan_at:
        raise ValueError("scan_generated_at is required for judgment review idempotency")
    model = str(conclusion.get("reviewer_model") or reviewer_model or "unknown")
    judgment_id = page.stem
    review_id = hashlib.sha256(f"{judgment_id}{scan_at}{model}".encode("utf-8")).hexdigest()[:16]
    receipt_status, has_receipt = _has_judgment_review_receipt(root, review_id)
    if receipt_status == "corrupt":
        return {"status": "receipt_history_corrupt", "review_id": review_id}
    if has_receipt:
        return {"status": "skipped_idempotent", "review_id": review_id}
    now = utc_now()
    conclusion_text = str(conclusion.get("conclusion") or "unknown")
    confidence_text = str(conclusion.get("confidence") or "unknown")
    findings = conclusion.get("key_findings", [])
    if isinstance(findings, list):
        findings_str = "; ".join(str(f) for f in findings[:3])
    else:
        findings_str = ""
    recommendation = str(conclusion.get("recommendation") or "")

    entry = (
        f"- {now} | AI-reviewed (counter-evidence) | conclusion: {conclusion_text} "
        f"| confidence: {confidence_text} | review_id={review_id}"
    )
    if findings_str:
        entry += f" | findings: {findings_str}"
    if recommendation:
        entry += f" | recommendation: {recommendation}"

    def mutate(existing: str) -> str:
        if "## Review History" in existing:
            return existing.replace("## Review History", f"## Review History\n{entry}", 1)
        if "## 审阅历史" in existing:
            return existing.replace("## 审阅历史", f"## 审阅历史\n{entry}", 1)
        return existing + f"\n\n## Review History\n{entry}\n"

    result = _apply_judgment_review_with_receipt(
        page,
        mutate,
        {
            "root": root,
            "occurred_at": now,
            "review_id": review_id,
            "judgment_id": judgment_id,
            "scan_generated_at": scan_at,
            "reviewer_model": model,
            "conclusion": conclusion_text,
            "confidence": confidence_text,
        },
    )
    return {**result, "review_id": review_id}


@runtime_write_operation
def auto_adopt_l3(root: Path, *, limit: int | None = None) -> dict[str, Any]:
    """Auto-adopt L3 proposals (candidate → accepted + applied).

    L3 proposals are prompt/policy/schema changes. With ``AIWIKI_NIGHTLY_AUTO_ADOPT_L3=1``,
    they are auto-accepted and applied during nightly, with receipts for audit/revert.
    """
    try:
        parsed_limit = int(limit) if limit is not None else 0
    except (TypeError, ValueError):
        parsed_limit = 0
    effective_limit = parsed_limit if parsed_limit > 0 else None
    results: dict[str, Any] = {"level": "L3", "applied": False, "items": []}
    if effective_limit is not None:
        results["limit"] = effective_limit
    try:
        from ..execution.l3_proposals import (
            L3PostApplyAuditError,
            L3RevertError,
            apply_l3_proposal,
            load_l3_proposal_state,
        )

        proposals = load_l3_proposal_state(root).get("proposals", [])
        threshold = l3_auto_adopt_min_evidence_from_env()
        candidates: list[str] = []
        for proposal in proposals:
            if not isinstance(proposal, dict) or proposal.get("state") != "candidate":
                continue
            proposal_id = str(proposal.get("proposal_id") or "")
            trigger = proposal.get("trigger") if isinstance(proposal.get("trigger"), dict) else {}
            try:
                evidence_count = int(proposal.get("evidence_count") or trigger.get("evidence_count") or 0)
            except (TypeError, ValueError):
                results["items"].append({"proposal_id": proposal_id, "status": "failed_invalid_evidence", "evidence_count": proposal.get("evidence_count") or trigger.get("evidence_count")})
                results["degraded"] = True
                results["failed"] = int(results.get("failed", 0) or 0) + 1
                continue
            if evidence_count < threshold:
                results["items"].append({
                    "proposal_id": proposal_id,
                    "status": "skipped_low_evidence",
                    "evidence_count": evidence_count,
                    "threshold": threshold,
                })
                try:
                    append_runtime_history(
                        root,
                        {
                            "event_type": "l3-proposal-skipped-low-evidence",
                            "occurred_at": utc_now(),
                            "proposal_id": proposal_id,
                            "evidence_count": evidence_count,
                            "threshold": threshold,
                        },
                    )
                except Exception as exc:
                    print(f"warning: failed to write l3 low-evidence skip audit: {exc}")
                continue
            candidates.append(proposal_id)
        results["candidates_count"] = len(candidates)
        if effective_limit is not None and len(candidates) > effective_limit:
            results["skipped_by_limit"] = len(candidates) - effective_limit
            candidates = candidates[:effective_limit]
    except CorruptStateError:
        # SC-001: fail-closed propagation. Corrupt L3 proposal state must not
        # be downgraded to a soft "degraded" result, otherwise auto-adopt would
        # silently skip a damaged registry and lose governance traceability.
        raise
    except Exception as exc:
        results["error"] = f"L3 proposal state unavailable: {exc}"
        results["degraded"] = True
        return results

    if not candidates:
        return results

    for proposal_id in candidates:
        try:
            r = apply_l3_proposal(root, proposal_id, note="nightly L3 auto-adopt")
            results["items"].append({
                "proposal_id": proposal_id,
                "status": r.get("state", "accepted"),
                "receipt_path": r.get("receipt_path", ""),
                "target_file": r.get("target_file", ""),
            })
        except Exception as exc:
            status = "failed"
            if isinstance(exc, L3PostApplyAuditError):
                status = "auto_reverted"
            elif isinstance(exc, L3RevertError):
                status = "audit_revert_failed"
            try:
                if isinstance(exc, (L3PostApplyAuditError, L3RevertError)):
                    auto_revert_event = {
                        "event_type": "l3-proposal-auto-revert",
                        "occurred_at": utc_now(),
                        "proposal_id": proposal_id,
                        "status": status,
                        "error": str(exc),
                    }
                    if isinstance(exc, L3PostApplyAuditError):
                        auto_revert_event.update(
                            {
                                "action_id": exc.action_id,
                                "failed_step": exc.failed_step,
                                "target_file": exc.target_file,
                                "before_hash": exc.before_hash,
                                "after_hash": exc.after_hash,
                                "target_reverted": exc.target_reverted,
                                "deleted_receipt_path": exc.deleted_receipt_path,
                            }
                        )
                    append_runtime_history(
                        root,
                        auto_revert_event,
                    )
            except Exception as audit_exc:
                print(f"warning: failed to write l3 auto-revert audit: {audit_exc}")
            results["items"].append({
                "proposal_id": proposal_id,
                "status": status,
                **({"revert_status": status} if isinstance(exc, (L3PostApplyAuditError, L3RevertError)) else {}),
                "error": str(exc),
            })
            results["degraded"] = True
            results["failed"] = int(results.get("failed", 0) or 0) + 1
            _logger.warning("L3 auto-adopt failed for %s: %s", proposal_id, exc)

    applied = any(
        item.get("status") in {"accepted", "auto_reverted"}
        for item in results["items"]
    )
    results["applied"] = applied
    return results


__all__ = ["auto_adopt_l1", "auto_adopt_l2", "auto_adopt_l3", "auto_adopt_judgments", "_env_flag"]
