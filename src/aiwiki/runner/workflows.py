"""LLM-backed primary workflows: compile, ask, lint, nightly."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiwiki.app_compile import (
    compile_wiki,
    lint_wiki,
    promote_recurring_outputs,
    write_nightly_health,
)
from aiwiki.app_memory import store_concept_rewrite_candidate
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_shell import rewrite_recovery_payload_for_paths
from aiwiki.app_state import load_machine_memory, load_manifest, nightly_health_state_path
from aiwiki.app_utils import (
    atomic_write_text,
    parse_frontmatter,
    relative_path,
    runtime_write_operation,
    utc_now,
)
from aiwiki.content.memory import concept_summary_is_placeholder, placeholder_concept_slugs
from aiwiki.execution.audit_reconciliation import reconcile_execution_receipts
from aiwiki.llm import CompletionResult, LLMError
from aiwiki.runner.clients import (
    _append_fallback_stage,
    _client_model_name,
    _fallback_to_next_model_with_stage,
    create_client,
)
from aiwiki.runner.interfaces import SupportsComplete
from aiwiki.runner.prompts import (
    _build_compile_prompt,
    _build_concept_compile_prompt,
    _build_lint_prompt,
    _extract_related_concept_slugs,
    _initial_compile_prompt_profile,
    _initial_lint_prompt_profile,
    _normalize_markdown,
    _retry_compile_prompt_profile,
    _retry_lint_prompt_profile,
    _rewrite_candidate_record,
    _rewrite_candidate_slugs,
    _system_prompt,
    _validate_concept_page,
    _validate_source_page,
)
from aiwiki.runner.receipts import (
    _build_llm_audit,
    _empty_llm_audit,
    _llm_audit_from_result,
    _merge_llm_audits,
    record_llm_attempt,
)
from aiwiki.runner.workflow_shared import _env_flag, _raw_response_path, _receipt_error_class

_REPORT_REFERENCE_RE = re.compile(
    r"(?im)^\s*(?:#\s*)?引用报告\s*[：:]\s*`?(output/reports/[^\s`]+?\.md)`?\s*"
)


def _normalize_run_compile_paths(paths: list[str] | None) -> set[str] | None:
    """Build a normalized lookup set for `run_compile(paths=...)` filtering.

    P4-INV-1 (Round 59): accept any of these forms per element and return a
    deduplicated set of normalized tokens (lowercased, ``./`` stripped):

    - source id (``discovered-...``)
    - ``wiki/sources/<id>.md`` or absolute equivalent
    - ``raw/inbox/<file>``: matched against entry's source_files
    - bare basename (``<id>.md``)

    Empty / blank entries are dropped. Returning ``None`` means "no filter
    requested" (legacy behavior).
    """

    if paths is None:
        return None
    cleaned: set[str] = set()
    for raw in paths:
        text = str(raw or "").strip()
        if not text:
            continue
        text = text.lstrip("./")
        cleaned.add(text)
        cleaned.add(text.lower())
        # Common dialects callers might emit.
        if text.endswith(".md"):
            cleaned.add(text[:-3])
            cleaned.add(text[:-3].lower())
    return cleaned or None


def _entry_matches_path_filter(
    entry: dict[str, Any], page: Path, filter_tokens: set[str]
) -> bool:
    """Return True when an LLM enrichment entry matches an explicit --paths token."""

    entry_id = str(entry.get("id") or "").strip()
    if entry_id and (entry_id in filter_tokens or entry_id.lower() in filter_tokens):
        return True
    page_rel = ""
    try:
        page_rel = page.resolve().relative_to(page.parent.parent.parent.resolve()).as_posix()
    except (ValueError, OSError):
        page_rel = ""
    candidates = {
        page_rel,
        page_rel.lower() if page_rel else "",
        f"wiki/sources/{entry_id}.md" if entry_id else "",
        f"wiki/sources/{entry_id}.md".lower() if entry_id else "",
        page.name,
        page.name.lower(),
        page.stem,
        page.stem.lower(),
    }
    for source_file in entry.get("source_files", []) or []:
        candidates.add(str(source_file))
        candidates.add(str(source_file).lower())
    return bool(candidates & filter_tokens)


# F-INV-NEW-1: real Chinese annual-report PDFs (270+ pages) overrun the default
# 120s LLM timeout. Estimate ~30KB of raw text per "page" and give 60s per page,
# clamped to [240s, 1800s]. The result is per-job (not a global default change);
# explicit ``AIWIKI_LLM_TIMEOUT`` env still wins at client creation time.
_ADAPTIVE_COMPILE_BYTES_PER_PAGE = 30_000
_ADAPTIVE_COMPILE_SECONDS_PER_PAGE = 60
_ADAPTIVE_COMPILE_TIMEOUT_FLOOR = 240
_ADAPTIVE_COMPILE_TIMEOUT_CEIL = 1800


def _compute_adaptive_compile_timeout(root: Path, pending: list[dict[str, Any]]) -> int | None:
    """Return adaptive ``timeout_seconds`` for run-compile based on largest pending raw size.

    Returns ``None`` when there is nothing to adapt to — empty ``pending`` or an
    explicit ``AIWIKI_LLM_TIMEOUT`` env override — so ``LLMConfig.from_env``
    keeps its env-or-default behavior. When ``pending`` is non-empty but no raw
    is stat-able inside ``root``, falls back to the floor so we still upgrade
    past the historical 120s default for the typical Chinese-PDF case.
    """

    if os.environ.get("AIWIKI_LLM_TIMEOUT", "").strip():
        # User pinned an explicit timeout — never override.
        return None
    if not pending:
        return None
    try:
        root_resolved = root.resolve()
    except OSError:
        return _ADAPTIVE_COMPILE_TIMEOUT_FLOOR
    max_bytes = 0
    for entry in pending:
        stored = entry.get("stored_path") if isinstance(entry, dict) else None
        if not stored:
            continue
        raw_path = root / str(stored)
        try:
            raw_resolved = raw_path.resolve()
        except OSError:
            continue
        try:
            raw_resolved.relative_to(root_resolved)
        except ValueError:
            # Reject absolute / .. paths that escape the vault root.
            continue
        try:
            size = raw_resolved.stat().st_size
        except OSError:
            continue
        if size > max_bytes:
            max_bytes = size
    if max_bytes <= 0:
        return _ADAPTIVE_COMPILE_TIMEOUT_FLOOR
    pages = max(1, (max_bytes + _ADAPTIVE_COMPILE_BYTES_PER_PAGE - 1) // _ADAPTIVE_COMPILE_BYTES_PER_PAGE)
    estimated = pages * _ADAPTIVE_COMPILE_SECONDS_PER_PAGE
    return max(_ADAPTIVE_COMPILE_TIMEOUT_FLOOR, min(_ADAPTIVE_COMPILE_TIMEOUT_CEIL, estimated))


def _unique_run_compile_action_id(root: Path, started_at_ms: int) -> str:
    """Return a per-job action id for a run-compile failure receipt.

    Mirrors the alchemy pattern (``<kind>-<epoch_ms>`` + ``-<n>`` suffix on
    same-millisecond collisions) so receipt filenames are stable and unique
    inside ``output/control/execution-receipts/``.
    """

    candidate = f"run-compile-{started_at_ms}"
    n = 2
    while (root / "output" / "control" / "execution-receipts" / f"{candidate}.json").exists():
        candidate = f"run-compile-{started_at_ms}-{n}"
        n += 1
    return candidate


def _write_run_compile_failure_receipt(
    root: Path,
    *,
    subject_kind: str,
    subject_id: str,
    target_file: str,
    source: str,
    item_audit: dict[str, Any],
    item_result: CompletionResult | None,
    exc: Exception,
    started_at_ms: int,
    duration_ms: int,
    used_profile: str,
    item_retry_profile: str,
    fallback_stages: list[str],
    fallback_reason: str,
    extra: dict[str, Any] | None = None,
) -> str:
    """Persist a per-job ``run-compile-<id>.json`` receipt to
    ``output/control/execution-receipts/`` on fail-fast.

    Returns the vault-relative receipt path (empty string on write failure)
    so callers can stamp it into the JSONL record. Never raises — the
    original LLM exception must remain the visible failure for the caller.
    """

    try:
        action_id = _unique_run_compile_action_id(root, started_at_ms)
        receipt_path = root / "output" / "control" / "execution-receipts" / f"{action_id}.json"
        applied_at = datetime.fromtimestamp(started_at_ms / 1000.0, tz=timezone.utc).isoformat()
        receipt: dict[str, Any] = {
            "version": 1,
            "kind": "execution-receipt",
            "generated_by": "aiwiki-run-compile",
            "applied_at": applied_at,
            "operation": "compile",
            "status": "failed",
            "action_id": action_id,
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "target_file": target_file,
            "source": source,
            "prompt_profile": used_profile,
            "retry_prompt_profile": item_retry_profile,
            "duration_ms": duration_ms,
            "error_class": _receipt_error_class(exc),
            "error_message": str(exc),
            "fallback_stages": list(fallback_stages),
            "fallback_reason": fallback_reason,
            "llm_audit": dict(item_audit),
            "response_id": getattr(item_result, "response_id", "") if item_result is not None else "",
            "usage": dict(getattr(item_result, "usage", {}) or {}) if item_result is not None else {},
            "revert_supported": False,
        }
        if extra:
            receipt.update(extra)
        receipt_rel = relative_path(root, receipt_path)
        receipt["receipt_path"] = receipt_rel
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            receipt_path,
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        return receipt_rel
    except Exception as receipt_exc:  # noqa: BLE001 — best-effort, must not mask exc
        logging.getLogger("aiwiki").warning(
            "run-compile fail-fast receipt write failed: %s", receipt_exc
        )
        return ""


@runtime_write_operation
def run_compile(
    root: Path,
    client: SupportsComplete | None = None,
    limit: int = 5,
    paths: list[str] | None = None,
) -> dict[str, Any]:
    """Compile manifest entries and run the LLM enrichment queue.

    P4-INV-1 (Round 59): when ``paths`` is provided the LLM-enrichment queue
    is restricted to entries that match any of the supplied identifiers /
    paths. Without it the legacy behavior — full backlog — is preserved.
    """

    ensure_layout(root)
    backend_compat: dict[str, Any] = {}
    if client is None:
        from aiwiki.runner.preflight import preflight_check_backend

        backend_compat = preflight_check_backend(root)

    def _stamped_record(base_event: dict[str, Any], llm_audit: dict[str, Any], **kwargs: Any) -> None:
        if backend_compat:
            base_event = dict(base_event)
            base_event["backend_compat"] = dict(backend_compat)
        record_llm_attempt(root, base_event, llm_audit, **kwargs)

    compile_result = compile_wiki(root)
    manifest = load_manifest(root)
    path_filter = _normalize_run_compile_paths(paths)
    pending = []
    for entry in manifest["entries"]:
        page = root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
            continue
        if path_filter is not None and not _entry_matches_path_filter(entry, page, path_filter):
            continue
        content = page.read_text(encoding="utf-8", errors="replace")
        if "Pending LLM summary." in content:
            pending.append(entry)

    updated_pages: list[str] = []
    updated_placeholder_concept_pages: list[str] = []
    updated_rewrite_proposal_pages: list[str] = []
    skipped = max(0, len(pending) - limit)
    pending_concept_slugs = placeholder_concept_slugs(root)
    remaining_budget = max(0, limit)
    skipped_concepts = max(0, len(pending_concept_slugs) - remaining_budget)
    memory = load_machine_memory(root)
    pending_rewrite_candidates = _rewrite_candidate_slugs(memory, exclude=set(pending_concept_slugs))
    skipped_rewrite_candidates = max(0, len(pending_rewrite_candidates) - remaining_budget)
    started = time.monotonic()
    prompt_profile = ""
    retry_prompt_profile = ""
    attempted_pages = 0
    failed_pages = 0
    attempted_concept_pages = 0
    failed_concept_pages = 0
    attempted_rewrite_concept_pages = 0
    failed_rewrite_concept_pages = 0
    page_stage_total = len(pending[:limit]) if limit > 0 else 0
    concept_stage_total = len(pending_concept_slugs[:remaining_budget]) if limit > 0 else 0
    rewrite_stage_total = len(pending_rewrite_candidates[:remaining_budget]) if limit > 0 else 0

    def summary_base_event(duration_ms: int) -> dict[str, Any]:
        return {
            "event": "run-compile-summary",
            "limit": limit,
            "updated_pages": list(updated_pages),
            "pending_pages": len(pending),
            "skipped_pages": skipped,
            "attempted_pages": attempted_pages,
            "succeeded_pages": len(updated_pages),
            "failed_pages": failed_pages,
            "remaining_pages": max(0, page_stage_total - attempted_pages) if failed_pages else 0,
            "updated_concept_pages": list(updated_placeholder_concept_pages),
            "pending_concept_pages": len(pending_concept_slugs),
            "skipped_concept_pages": skipped_concepts,
            "attempted_concept_pages": attempted_concept_pages,
            "succeeded_concept_pages": len(updated_placeholder_concept_pages),
            "failed_concept_pages": failed_concept_pages,
            "remaining_concept_pages": max(0, concept_stage_total - attempted_concept_pages) if failed_concept_pages else 0,
            "updated_rewrite_concept_pages": [],
            "updated_rewrite_proposal_pages": list(updated_rewrite_proposal_pages),
            "pending_rewrite_concept_pages": len(pending_rewrite_candidates),
            "skipped_rewrite_concept_pages": skipped_rewrite_candidates,
            "attempted_rewrite_concept_pages": attempted_rewrite_concept_pages,
            "succeeded_rewrite_concept_pages": len(updated_rewrite_proposal_pages),
            "failed_rewrite_concept_pages": failed_rewrite_concept_pages,
            "remaining_rewrite_concept_pages": max(0, rewrite_stage_total - attempted_rewrite_concept_pages)
            if failed_rewrite_concept_pages
            else 0,
            "prompt_profile": prompt_profile,
            "retry_prompt_profile": retry_prompt_profile,
            "duration_ms": duration_ms,
        }

    def fail_fast_counters() -> dict[str, int]:
        return {
            "attempted_pages": attempted_pages,
            "succeeded_pages": len(updated_pages),
            "failed_pages": failed_pages,
            "remaining_pages": max(0, page_stage_total - attempted_pages) if failed_pages else 0,
            "attempted_concept_pages": attempted_concept_pages,
            "succeeded_concept_pages": len(updated_placeholder_concept_pages),
            "failed_concept_pages": failed_concept_pages,
            "remaining_concept_pages": max(0, concept_stage_total - attempted_concept_pages) if failed_concept_pages else 0,
            "attempted_rewrite_concept_pages": attempted_rewrite_concept_pages,
            "succeeded_rewrite_concept_pages": len(updated_rewrite_proposal_pages),
            "failed_rewrite_concept_pages": failed_rewrite_concept_pages,
            "remaining_rewrite_concept_pages": max(0, rewrite_stage_total - attempted_rewrite_concept_pages)
            if failed_rewrite_concept_pages
            else 0,
        }

    if (not pending and not pending_concept_slugs and not pending_rewrite_candidates) or limit <= 0:
        llm_audit = _empty_llm_audit()
        rewrite_payload = rewrite_recovery_payload_for_paths(root, updated_rewrite_proposal_pages)
        _stamped_record(
            summary_base_event(int((time.monotonic() - started) * 1000)),
            llm_audit,
            status="success",
            skipped=True,
        )
        return {
            "compile": compile_result,
            "updated_pages": updated_pages,
            "pending_pages": len(pending),
            "skipped_pages": skipped,
            **fail_fast_counters(),
            "updated_concept_pages": updated_placeholder_concept_pages,
            "pending_concept_pages": len(pending_concept_slugs),
            "skipped_concept_pages": skipped_concepts,
            "updated_rewrite_concept_pages": [],
            "updated_rewrite_proposal_pages": updated_rewrite_proposal_pages,
            **rewrite_payload,
            "pending_rewrite_concept_pages": len(pending_rewrite_candidates),
            "skipped_rewrite_concept_pages": skipped_rewrite_candidates,
            **llm_audit,
            "delivery_mode": llm_audit["delivery_mode"],
            "fallback_used": llm_audit["fallback_used"],
            "prompt_profile": "",
            "retry_prompt_profile": "",
        }

    effective_client = client or create_client(root, timeout_seconds=_compute_adaptive_compile_timeout(root, pending))
    model_selected = _client_model_name(effective_client)
    aggregate_audit = _empty_llm_audit()
    prompt_profile = _initial_compile_prompt_profile(effective_client)
    retry_prompt_profile = ""
    try:
        for entry in pending[:limit]:
            attempted_pages += 1
            target = root / "wiki" / "sources" / f"{entry['id']}.md"
            raw_path = root / entry["stored_path"]
            current_page = target.read_text(encoding="utf-8", errors="replace")
            item_profile = prompt_profile
            prompt = _build_compile_prompt(root, entry, raw_path, current_page, prompt_profile=item_profile)
            item_retry_profile = ""
            item_model_selected = _client_model_name(effective_client)
            item_fallback_stages: list[str] = []
            item_fallback_reason = ""
            item_result: CompletionResult | None = None
            item_started = time.monotonic()
            try:
                while True:
                    try:
                        item_result = effective_client.complete(_system_prompt("compile"), prompt)
                    except LLMError as exc:
                        next_retry_profile = _retry_compile_prompt_profile(exc, item_profile, effective_client)
                        if next_retry_profile:
                            item_retry_profile = next_retry_profile
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, "prompt-profile")
                            logging.getLogger("aiwiki").warning(
                                "run-compile failed with %s prompt; retrying with %s prompt",
                                item_profile,
                                item_retry_profile,
                            )
                            prompt = _build_compile_prompt(
                                root,
                                entry,
                                raw_path,
                                current_page,
                                prompt_profile=item_retry_profile,
                            )
                            item_profile = item_retry_profile
                            prompt_profile = item_retry_profile
                            retry_prompt_profile = item_retry_profile
                            continue
                        item_fallback_stage = _fallback_to_next_model_with_stage(effective_client, "run-compile", exc)
                        if item_fallback_stage:
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, item_fallback_stage)
                            continue
                        raise
                    updated = _normalize_markdown(item_result.text)
                    try:
                        _validate_source_page(updated, entry["id"], entry["stored_path"], entry["sha256"])
                    except RuntimeError as exc:
                        item_fallback_stage = _fallback_to_next_model_with_stage(effective_client, "run-compile", exc)
                        if item_fallback_stage:
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, item_fallback_stage)
                            continue
                        raise
                    break
                used_profile = item_retry_profile or item_profile
                target.write_text(updated, encoding="utf-8")
                updated_pages.append(relative_path(root, target))
                item_audit = _build_llm_audit(
                    effective_client,
                    model_selected=item_model_selected,
                    fallback_stages=item_fallback_stages,
                    fallback_reason=item_fallback_reason,
                    contract_validated=True,
                )
                aggregate_audit = _merge_llm_audits(aggregate_audit, item_audit)
                _stamped_record(
                    {
                        "event": "run-compile",
                        "target": relative_path(root, target),
                        "source": entry["stored_path"],
                        "prompt_profile": used_profile,
                        "retry_prompt_profile": item_retry_profile,
                        "duration_ms": int((time.monotonic() - item_started) * 1000),
                        **fail_fast_counters(),
                    },
                    item_audit,
                    status="success",
                    response_id=item_result.response_id,
                    usage=item_result.usage,
                    raw_response_path=_raw_response_path(root, item_result),
                )
            except Exception as exc:
                failed_pages += 1
                used_profile = item_retry_profile or item_profile
                item_audit = _build_llm_audit(
                    effective_client,
                    model_selected=item_model_selected,
                    fallback_stages=item_fallback_stages,
                    fallback_reason=item_fallback_reason or str(exc),
                    contract_validated=False,
                )
                aggregate_audit = _merge_llm_audits(aggregate_audit, item_audit)
                _failure_duration_ms = int((time.monotonic() - item_started) * 1000)
                _failure_started_at_ms = int((time.time() - _failure_duration_ms / 1000.0) * 1000)
                _failure_receipt_path = _write_run_compile_failure_receipt(
                    root,
                    subject_kind="source_page",
                    subject_id=str(entry.get("id", "")),
                    target_file=relative_path(root, target),
                    source=str(entry.get("stored_path", "")),
                    item_audit=item_audit,
                    item_result=item_result,
                    exc=exc,
                    started_at_ms=_failure_started_at_ms,
                    duration_ms=_failure_duration_ms,
                    used_profile=used_profile,
                    item_retry_profile=item_retry_profile,
                    fallback_stages=item_fallback_stages,
                    fallback_reason=item_fallback_reason,
                )
                _stamped_record(
                    {
                        "event": "run-compile",
                        "target": relative_path(root, target),
                        "source": entry["stored_path"],
                        "prompt_profile": used_profile,
                        "retry_prompt_profile": item_retry_profile,
                        "duration_ms": _failure_duration_ms,
                        "receipt_path": _failure_receipt_path,
                        **fail_fast_counters(),
                    },
                    item_audit,
                    status="failed",
                    error=str(exc),
                    response_id=getattr(item_result, "response_id", "") if item_result is not None else "",
                    usage=getattr(item_result, "usage", {}) if item_result is not None else {},
                    raw_response_path=_raw_response_path(root, item_result, exc),
                    error_class=_receipt_error_class(exc),
                )
                raise

        if updated_pages:
            compile_result = compile_wiki(root)
            pending_concept_slugs = placeholder_concept_slugs(root)
            memory = load_machine_memory(root)
        remaining_budget = max(0, limit - len(updated_pages))
        skipped_concepts = max(0, len(pending_concept_slugs) - remaining_budget)
        concept_stage_total = len(pending_concept_slugs[:remaining_budget])

        for slug in pending_concept_slugs[:remaining_budget]:
            attempted_concept_pages += 1
            target = root / "wiki" / "concepts" / f"{slug}.md"
            if not target.exists():
                continue
            current_page = target.read_text(encoding="utf-8", errors="replace")
            if not concept_summary_is_placeholder(current_page):
                continue
            frontmatter = parse_frontmatter(current_page)
            source_pages = frontmatter.get("source_pages", [])
            if not isinstance(source_pages, list):
                source_pages = []
            related_slugs = _extract_related_concept_slugs(current_page)
            item_profile = prompt_profile
            prompt = _build_concept_compile_prompt(
                root,
                target,
                current_page,
                source_pages,
                related_slugs,
                prompt_profile=item_profile,
            )
            item_retry_profile = ""
            item_model_selected = _client_model_name(effective_client)
            item_fallback_stages: list[str] = []
            item_fallback_reason = ""
            item_result: CompletionResult | None = None
            item_started = time.monotonic()
            try:
                while True:
                    try:
                        item_result = effective_client.complete(_system_prompt("compile"), prompt)
                    except LLMError as exc:
                        next_retry_profile = _retry_compile_prompt_profile(exc, item_profile, effective_client)
                        if next_retry_profile:
                            item_retry_profile = next_retry_profile
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, "prompt-profile")
                            logging.getLogger("aiwiki").warning(
                                "run-compile concept failed with %s prompt; retrying with %s prompt",
                                item_profile,
                                item_retry_profile,
                            )
                            prompt = _build_concept_compile_prompt(
                                root,
                                target,
                                current_page,
                                source_pages,
                                related_slugs,
                                prompt_profile=item_retry_profile,
                            )
                            item_profile = item_retry_profile
                            prompt_profile = item_retry_profile
                            retry_prompt_profile = item_retry_profile
                            continue
                        item_fallback_stage = _fallback_to_next_model_with_stage(effective_client, "run-compile-concept", exc)
                        if item_fallback_stage:
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, item_fallback_stage)
                            continue
                        raise
                    updated = _normalize_markdown(item_result.text)
                    try:
                        _validate_concept_page(updated, slug, frontmatter.get("source_signature", ""), source_pages)
                    except RuntimeError as exc:
                        item_fallback_stage = _fallback_to_next_model_with_stage(effective_client, "run-compile-concept", exc)
                        if item_fallback_stage:
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, item_fallback_stage)
                            continue
                        raise
                    break
                used_profile = item_retry_profile or item_profile
                target.write_text(updated, encoding="utf-8")
                updated_placeholder_concept_pages.append(relative_path(root, target))
                item_audit = _build_llm_audit(
                    effective_client,
                    model_selected=item_model_selected,
                    fallback_stages=item_fallback_stages,
                    fallback_reason=item_fallback_reason,
                    contract_validated=True,
                )
                aggregate_audit = _merge_llm_audits(aggregate_audit, item_audit)
                _stamped_record(
                    {
                        "event": "run-compile-concept",
                        "target": relative_path(root, target),
                        "source_pages": source_pages,
                        "prompt_profile": used_profile,
                        "retry_prompt_profile": item_retry_profile,
                        "duration_ms": int((time.monotonic() - item_started) * 1000),
                        **fail_fast_counters(),
                    },
                    item_audit,
                    status="success",
                    response_id=item_result.response_id,
                    usage=item_result.usage,
                    raw_response_path=_raw_response_path(root, item_result),
                )
            except Exception as exc:
                failed_concept_pages += 1
                used_profile = item_retry_profile or item_profile
                item_audit = _build_llm_audit(
                    effective_client,
                    model_selected=item_model_selected,
                    fallback_stages=item_fallback_stages,
                    fallback_reason=item_fallback_reason or str(exc),
                    contract_validated=False,
                )
                aggregate_audit = _merge_llm_audits(aggregate_audit, item_audit)
                _failure_duration_ms = int((time.monotonic() - item_started) * 1000)
                _failure_started_at_ms = int((time.time() - _failure_duration_ms / 1000.0) * 1000)
                _failure_receipt_path = _write_run_compile_failure_receipt(
                    root,
                    subject_kind="concept_page",
                    subject_id=str(slug),
                    target_file=relative_path(root, target),
                    source="",
                    item_audit=item_audit,
                    item_result=item_result,
                    exc=exc,
                    started_at_ms=_failure_started_at_ms,
                    duration_ms=_failure_duration_ms,
                    used_profile=used_profile,
                    item_retry_profile=item_retry_profile,
                    fallback_stages=item_fallback_stages,
                    fallback_reason=item_fallback_reason,
                    extra={"source_pages": list(source_pages)},
                )
                _stamped_record(
                    {
                        "event": "run-compile-concept",
                        "target": relative_path(root, target),
                        "source_pages": source_pages,
                        "prompt_profile": used_profile,
                        "retry_prompt_profile": item_retry_profile,
                        "duration_ms": _failure_duration_ms,
                        "receipt_path": _failure_receipt_path,
                        **fail_fast_counters(),
                    },
                    item_audit,
                    status="failed",
                    error=str(exc),
                    response_id=getattr(item_result, "response_id", "") if item_result is not None else "",
                    usage=getattr(item_result, "usage", {}) if item_result is not None else {},
                    raw_response_path=_raw_response_path(root, item_result, exc),
                    error_class=_receipt_error_class(exc),
                )
                raise

        if updated_placeholder_concept_pages:
            compile_result = compile_wiki(root)
            memory = load_machine_memory(root)

        remaining_budget = max(0, limit - len(updated_pages) - len(updated_placeholder_concept_pages))
        pending_rewrite_candidates = _rewrite_candidate_slugs(
            memory,
            exclude=set(pending_concept_slugs) | {Path(path).stem for path in updated_placeholder_concept_pages},
        )
        skipped_rewrite_candidates = max(0, len(pending_rewrite_candidates) - remaining_budget)
        rewrite_stage_total = len(pending_rewrite_candidates[:remaining_budget])

        for slug in pending_rewrite_candidates[:remaining_budget]:
            attempted_rewrite_concept_pages += 1
            target = root / "wiki" / "concepts" / f"{slug}.md"
            if not target.exists():
                continue
            current_page = target.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(current_page)
            source_pages = frontmatter.get("source_pages", [])
            if not isinstance(source_pages, list):
                source_pages = []
            related_slugs = _extract_related_concept_slugs(current_page)
            quality_record = _rewrite_candidate_record(memory, slug)
            item_profile = prompt_profile
            prompt = _build_concept_compile_prompt(
                root,
                target,
                current_page,
                source_pages,
                related_slugs,
                quality_record=quality_record,
                prompt_profile=item_profile,
            )
            item_retry_profile = ""
            item_model_selected = _client_model_name(effective_client)
            item_fallback_stages: list[str] = []
            item_fallback_reason = ""
            item_result: CompletionResult | None = None
            item_started = time.monotonic()
            try:
                while True:
                    try:
                        item_result = effective_client.complete(_system_prompt("compile"), prompt)
                    except LLMError as exc:
                        next_retry_profile = _retry_compile_prompt_profile(exc, item_profile, effective_client)
                        if next_retry_profile:
                            item_retry_profile = next_retry_profile
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, "prompt-profile")
                            logging.getLogger("aiwiki").warning(
                                "run-compile rewrite failed with %s prompt; retrying with %s prompt",
                                item_profile,
                                item_retry_profile,
                            )
                            prompt = _build_concept_compile_prompt(
                                root,
                                target,
                                current_page,
                                source_pages,
                                related_slugs,
                                quality_record=quality_record,
                                prompt_profile=item_retry_profile,
                            )
                            item_profile = item_retry_profile
                            prompt_profile = item_retry_profile
                            retry_prompt_profile = item_retry_profile
                            continue
                        item_fallback_stage = _fallback_to_next_model_with_stage(effective_client, "run-compile-rewrite", exc)
                        if item_fallback_stage:
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, item_fallback_stage)
                            continue
                        raise
                    updated = _normalize_markdown(item_result.text)
                    try:
                        _validate_concept_page(updated, slug, frontmatter.get("source_signature", ""), source_pages)
                    except RuntimeError as exc:
                        item_fallback_stage = _fallback_to_next_model_with_stage(effective_client, "run-compile-rewrite", exc)
                        if item_fallback_stage:
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, item_fallback_stage)
                            continue
                        raise
                    break
                used_profile = item_retry_profile or item_profile
                proposal = store_concept_rewrite_candidate(
                    root,
                    slug,
                    quality_record=quality_record,
                    candidate_markdown=updated,
                    generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                )
                updated_rewrite_proposal_pages.append(str(proposal["proposal_path"]))
                item_audit = _build_llm_audit(
                    effective_client,
                    model_selected=item_model_selected,
                    fallback_stages=item_fallback_stages,
                    fallback_reason=item_fallback_reason,
                    contract_validated=True,
                )
                aggregate_audit = _merge_llm_audits(aggregate_audit, item_audit)
                _stamped_record(
                    {
                        "event": "run-compile-concept-rewrite-proposal",
                        "target": str(proposal["proposal_path"]),
                        "concept_page": relative_path(root, target),
                        "source_pages": source_pages,
                        "quality_priority": quality_record.get("priority", ""),
                        "quality_issues": quality_record.get("issues", []),
                        "prompt_profile": used_profile,
                        "retry_prompt_profile": item_retry_profile,
                        "duration_ms": int((time.monotonic() - item_started) * 1000),
                        **fail_fast_counters(),
                    },
                    item_audit,
                    status="success",
                    response_id=item_result.response_id,
                    usage=item_result.usage,
                    raw_response_path=_raw_response_path(root, item_result),
                )
            except Exception as exc:
                failed_rewrite_concept_pages += 1
                used_profile = item_retry_profile or item_profile
                item_audit = _build_llm_audit(
                    effective_client,
                    model_selected=item_model_selected,
                    fallback_stages=item_fallback_stages,
                    fallback_reason=item_fallback_reason or str(exc),
                    contract_validated=False,
                )
                aggregate_audit = _merge_llm_audits(aggregate_audit, item_audit)
                _failure_duration_ms = int((time.monotonic() - item_started) * 1000)
                _failure_started_at_ms = int((time.time() - _failure_duration_ms / 1000.0) * 1000)
                _failure_receipt_path = _write_run_compile_failure_receipt(
                    root,
                    subject_kind="concept_rewrite_proposal",
                    subject_id=str(slug),
                    target_file=f"wiki/rewrite-proposals/{slug}.md",
                    source="",
                    item_audit=item_audit,
                    item_result=item_result,
                    exc=exc,
                    started_at_ms=_failure_started_at_ms,
                    duration_ms=_failure_duration_ms,
                    used_profile=used_profile,
                    item_retry_profile=item_retry_profile,
                    fallback_stages=item_fallback_stages,
                    fallback_reason=item_fallback_reason,
                    extra={
                        "source_pages": list(source_pages),
                        "concept_page": relative_path(root, target),
                        "quality_priority": quality_record.get("priority", ""),
                        "quality_issues": list(quality_record.get("issues", []) or []),
                    },
                )
                _stamped_record(
                    {
                        "event": "run-compile-concept-rewrite-proposal",
                        "target": f"wiki/rewrite-proposals/{slug}.md",
                        "concept_page": relative_path(root, target),
                        "source_pages": source_pages,
                        "quality_priority": quality_record.get("priority", ""),
                        "quality_issues": quality_record.get("issues", []),
                        "prompt_profile": used_profile,
                        "retry_prompt_profile": item_retry_profile,
                        "duration_ms": _failure_duration_ms,
                        "receipt_path": _failure_receipt_path,
                        **fail_fast_counters(),
                    },
                    item_audit,
                    status="failed",
                    error=str(exc),
                    response_id=getattr(item_result, "response_id", "") if item_result is not None else "",
                    usage=getattr(item_result, "usage", {}) if item_result is not None else {},
                    raw_response_path=_raw_response_path(root, item_result, exc),
                    error_class=_receipt_error_class(exc),
                )
                raise

        if updated_rewrite_proposal_pages:
            compile_result = compile_wiki(root)
    except Exception as exc:
        failed_audit = _merge_llm_audits(
            _build_llm_audit(effective_client, model_selected=model_selected, contract_validated=False),
            aggregate_audit,
        )
        failed_audit["fallback_reason"] = str(exc)
        failed_audit["contract_validated"] = False
        _stamped_record(
            summary_base_event(int((time.monotonic() - started) * 1000)),
            failed_audit,
            status="failed",
            error=str(exc),
            raw_response_path=getattr(exc, "raw_response_path", "") or "",
            error_class=_receipt_error_class(exc),
        )
        raise

    llm_audit = _merge_llm_audits(
        _build_llm_audit(
            effective_client,
            model_selected=model_selected,
            contract_validated=bool(aggregate_audit.get("contract_validated")),
        ),
        aggregate_audit,
    )
    _stamped_record(
        summary_base_event(int((time.monotonic() - started) * 1000)),
        llm_audit,
        status="success",
    )
    rewrite_payload = rewrite_recovery_payload_for_paths(root, updated_rewrite_proposal_pages)
    return {
        "compile": compile_result,
        "updated_pages": updated_pages,
        "pending_pages": len(pending),
        "skipped_pages": skipped,
        **fail_fast_counters(),
        "updated_concept_pages": updated_placeholder_concept_pages,
        "pending_concept_pages": len(pending_concept_slugs),
        "skipped_concept_pages": skipped_concepts,
        "updated_rewrite_concept_pages": [],
        "updated_rewrite_proposal_pages": updated_rewrite_proposal_pages,
        **rewrite_payload,
        "pending_rewrite_concept_pages": len(pending_rewrite_candidates),
        "skipped_rewrite_concept_pages": skipped_rewrite_candidates,
        **llm_audit,
        "prompt_profile": prompt_profile,
        "retry_prompt_profile": retry_prompt_profile,
    }


def _reinject_candidate_frontmatter(target: Path, *, corpus_id: str = "") -> None:
    """LLM 覆盖 artifact 后，重新注入 candidate_state 与 corpus_id 字段。

    薄 wrapper：委托给 ``execution.candidates.write_candidate_frontmatter``，
    保留既有调用点接口不变。frontmatter 写入的唯一权威入口在 candidates 模块。
    """
    from aiwiki.execution.candidates import write_candidate_frontmatter

    write_candidate_frontmatter(target, candidate_state="pending", corpus_id=corpus_id)


@runtime_write_operation
def run_lint(root: Path, client: SupportsComplete | None = None) -> dict[str, Any]:
    ensure_layout(root)
    deterministic = lint_wiki(root)
    report_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = root / "output" / "lint" / f"semantic-lint-{report_id}.md"
    effective_client = client or create_client(root)
    model_selected = _client_model_name(effective_client)
    prompt_profile = _initial_lint_prompt_profile(effective_client)
    prompt = _build_lint_prompt(root, deterministic["path"], prompt_profile=prompt_profile)
    retry_prompt_profile = ""
    fallback_stages: list[str] = []
    fallback_reason = ""
    result: CompletionResult | None = None
    started = time.monotonic()
    try:
        while True:
            try:
                result = effective_client.complete(_system_prompt("lint"), prompt)
            except LLMError as exc:
                next_retry_prompt_profile = _retry_lint_prompt_profile(exc, prompt_profile, effective_client)
                if next_retry_prompt_profile:
                    retry_prompt_profile = next_retry_prompt_profile
                    fallback_reason = str(exc)
                    _append_fallback_stage(fallback_stages, "prompt-profile")
                    logging.getLogger("aiwiki").warning(
                        "run-lint failed with %s prompt; retrying with %s prompt",
                        prompt_profile,
                        retry_prompt_profile,
                    )
                    prompt = _build_lint_prompt(root, deterministic["path"], prompt_profile=retry_prompt_profile)
                    prompt_profile = retry_prompt_profile
                    continue
                fallback_stage = _fallback_to_next_model_with_stage(effective_client, "run-lint", exc)
                if fallback_stage:
                    fallback_reason = str(exc)
                    _append_fallback_stage(fallback_stages, fallback_stage)
                    continue
                raise
            updated = _normalize_markdown(result.text)
            if not updated.startswith("#") and not updated.startswith("---"):
                exc = RuntimeError("Semantic lint response must be markdown.")
                fallback_stage = _fallback_to_next_model_with_stage(effective_client, "run-lint", exc)
                if fallback_stage:
                    fallback_reason = str(exc)
                    _append_fallback_stage(fallback_stages, fallback_stage)
                    continue
                raise exc
            break
    except Exception as exc:
        failed_audit = _build_llm_audit(
            effective_client,
            model_selected=model_selected,
            fallback_stages=fallback_stages,
            fallback_reason=fallback_reason or str(exc),
            contract_validated=False,
        )
        record_llm_attempt(
            root,
            {
                "event": "run-lint",
                "target": relative_path(root, target),
                "deterministic_report": deterministic["path"],
                "prompt_profile": prompt_profile,
                "retry_prompt_profile": retry_prompt_profile,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
            failed_audit,
            status="failed",
            error=str(exc),
            response_id=getattr(result, "response_id", "") if result is not None else "",
            usage=getattr(result, "usage", {}) if result is not None else {},
            raw_response_path=_raw_response_path(root, result, exc),
            error_class=_receipt_error_class(exc),
        )
        raise
    target.write_text(updated, encoding="utf-8")
    llm_audit = _build_llm_audit(
        effective_client,
        model_selected=model_selected,
        fallback_stages=fallback_stages,
        fallback_reason=fallback_reason,
        contract_validated=True,
    )
    record_llm_attempt(
        root,
        {
            "event": "run-lint",
            "target": relative_path(root, target),
            "deterministic_report": deterministic["path"],
            "prompt_profile": prompt_profile,
            "retry_prompt_profile": retry_prompt_profile,
            "duration_ms": int((time.monotonic() - started) * 1000),
        },
        llm_audit,
        status="success",
        response_id=result.response_id,
        usage=result.usage,
        raw_response_path=_raw_response_path(root, result),
    )
    return {
        "deterministic": deterministic,
        "semantic_report": relative_path(root, target),
        **llm_audit,
        "prompt_profile": prompt_profile,
        "retry_prompt_profile": retry_prompt_profile,
    }


@runtime_write_operation
def run_nightly(
    root: Path,
    client: SupportsComplete | None = None,
    compile_limit: int = 5,
    semantic_lint: bool = True,
) -> dict[str, Any]:
    ensure_layout(root)
    effective_client = client or create_client(root)
    started = time.monotonic()
    compile_result: dict[str, Any] | None = None
    lint_result: dict[str, Any] | None = None
    model_selected = _client_model_name(effective_client)
    try:
        compile_result = run_compile(root, client=effective_client, limit=compile_limit)
        promotion_result = promote_recurring_outputs(root)
        if semantic_lint:
            lint_result = run_lint(root, client=effective_client)
        else:
            lint_result = {
                "deterministic": lint_wiki(root),
                "semantic_report": "",
                **_empty_llm_audit(),
                "prompt_profile": "",
                "retry_prompt_profile": "",
            }
        # contract EP-029 Step 3 §5: nightly auto-applies active -> stale, never demote/archive.
        # Non-fatal: aging failure is logged but does not block nightly; audit file always emitted.
        try:
            from aiwiki.execution.protocol_learnings import age_learnings

            protocol_learnings_age = age_learnings(root, apply=True, emitted_by="nightly")
        except Exception as age_exc:  # noqa: BLE001 - aging must not break nightly
            from aiwiki.execution.protocol_learnings import AUDIT_STATE_PATH as _AUDIT_PATH
            from aiwiki.execution.protocol_learnings import _atomic_write_text as _age_atomic_write

            protocol_learnings_age = {
                "apply": True,
                "run_at": utc_now(),
                "aged": [],
                "aged_ids": [],
                "skipped": [],
                "errors": [{"reason": f"aging failed: {age_exc}"}],
                "error": str(age_exc),
            }
            try:
                audit_path = root / _AUDIT_PATH
                audit_path.parent.mkdir(parents=True, exist_ok=True)
                _age_atomic_write(
                    audit_path,
                    json.dumps(protocol_learnings_age, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                )
            except Exception as audit_exc:  # noqa: BLE001 - last-ditch audit write
                # AGENTS.md: no silent swallow. Surface on stderr + retain in-memory payload
                # so the nightly result dict carries the failure reason for downstream visibility.
                import sys as _sys

                print(
                    f"[nightly] protocol-learnings aging audit write failed: {audit_exc}",
                    file=_sys.stderr,
                )
                protocol_learnings_age["audit_write_error"] = str(audit_exc)
        llm_audit = _merge_llm_audits(
            _llm_audit_from_result(compile_result),
            _llm_audit_from_result(lint_result),
        )
        llm_used = bool(compile_result.get("contract_validated") or lint_result.get("contract_validated"))
        state = write_nightly_health(
            root,
            compile_result["compile"],
            lint_result["deterministic"],
            promotion_result=promotion_result,
            semantic_report=lint_result["semantic_report"],
            llm_used=llm_used,
            runtime_history_extra={
                "compile_limit": compile_limit,
                "semantic_lint": semantic_lint,
                "llm_used": llm_used,
            },
        )
        from aiwiki.agent_loop import attach_agent_loop_to_nightly_state, run_nightly_agent_loop

        # R95.4: audit reconciliation gate (best-effort)
        try:
            reconciliation_result = reconcile_execution_receipts(root)
        except Exception as recon_exc:  # noqa: BLE001
            import sys

            print(f"[nightly] audit reconciliation failed: {recon_exc}", file=sys.stderr)
            reconciliation_result = {"status": "failed", "error": str(recon_exc)}
        state["audit_reconciliation"] = reconciliation_result
        # Persist updated state so nightly health reflects reconciliation.
        atomic_write_text(
            nightly_health_state_path(root),
            json.dumps(state, indent=2, sort_keys=True) + "\n",
        )

        auto_apply_light = _env_flag("AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT")
        auto_adopt_l1 = _env_flag("AIWIKI_NIGHTLY_AUTO_ADOPT_L1")
        auto_adopt_l2 = _env_flag("AIWIKI_NIGHTLY_AUTO_ADOPT_L2")
        auto_adopt_l3 = _env_flag("AIWIKI_NIGHTLY_AUTO_ADOPT_L3")
        auto_adopt_judgments = _env_flag("AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS")
        agent_loop = run_nightly_agent_loop(
            root,
            apply_light=auto_apply_light,
            auto_adopt_l1=auto_adopt_l1,
            auto_adopt_l2=auto_adopt_l2,
            auto_adopt_l3=auto_adopt_l3,
            auto_adopt_judgments=auto_adopt_judgments,
        )
        state = attach_agent_loop_to_nightly_state(root, state, agent_loop)
    except Exception as exc:
        failed_audit = _merge_llm_audits(
            _build_llm_audit(effective_client, model_selected=model_selected, contract_validated=False),
            _merge_llm_audits(_llm_audit_from_result(compile_result or {}), _llm_audit_from_result(lint_result or {})),
        )
        failed_audit["fallback_reason"] = str(exc)
        failed_audit["contract_validated"] = False
        record_llm_attempt(
            root,
            {
                "event": "run-nightly",
                "compile_limit": compile_limit,
                "semantic_lint": semantic_lint,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
            failed_audit,
            status="failed",
            error=str(exc),
            raw_response_path=getattr(exc, "raw_response_path", "") or "",
            error_class=_receipt_error_class(exc),
        )
        raise
    record_llm_attempt(
        root,
        {
            "event": "run-nightly",
            "compile_limit": compile_limit,
            "semantic_lint": semantic_lint,
            "compile_prompt_profile": str(compile_result.get("prompt_profile") or ""),
            "compile_retry_prompt_profile": str(compile_result.get("retry_prompt_profile") or ""),
            "lint_prompt_profile": str(lint_result.get("prompt_profile") or ""),
            "lint_retry_prompt_profile": str(lint_result.get("retry_prompt_profile") or ""),
            "llm_used": llm_used,
            "repair_backlog": state["repair_backlog"]["path"],
            "state_path": relative_path(root, root / ".aiwiki" / "state" / "nightly-health.json"),
            "agent_loop_status": str(state.get("agent_loop", {}).get("status") or ""),
            "agent_loop_dry_run": bool(state.get("agent_loop", {}).get("dry_run", False)),
            "agent_loop_auto_apply_light": _env_flag("AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT"),
            "agent_loop_auto_adopt_l1": _env_flag("AIWIKI_NIGHTLY_AUTO_ADOPT_L1"),
            "agent_loop_auto_adopt_l2": _env_flag("AIWIKI_NIGHTLY_AUTO_ADOPT_L2"),
            "agent_loop_auto_adopt_l3": _env_flag("AIWIKI_NIGHTLY_AUTO_ADOPT_L3"),
            "agent_loop_auto_adopt_judgments": _env_flag("AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS"),
            "duration_ms": int((time.monotonic() - started) * 1000),
        },
        llm_audit,
        status="success",
    )
    return {
        "compile": compile_result,
        "lint": lint_result,
        "promotions": promotion_result,
        "protocol_learnings_age": protocol_learnings_age,
        "agent_loop": state.get("agent_loop", {}),
        "aging": state["aging"],
        "repair_backlog": state["repair_backlog"]["path"],
        "state_path": relative_path(root, root / ".aiwiki" / "state" / "nightly-health.json"),
        "llm_used": llm_used,
        **llm_audit,
        "delivery_mode": llm_audit.get("delivery_mode", ""),
        "fallback_used": bool(llm_audit.get("fallback_used", False)),
        "fallback_from": str(llm_audit.get("fallback_from") or ""),
        "fallback_command": str(llm_audit.get("fallback_command") or ""),
        "primary_attempt_status": str(llm_audit.get("primary_attempt_status") or ""),
        "primary_error": str(llm_audit.get("primary_error") or ""),
    }


from aiwiki.runner.workflows_ask import (  # noqa: E402
    _effective_run_ask_timeout,
    _safe_quoted_report_reference_paths,
    run_ask,
    run_ask_resume,
    run_ask_submit,
)
