"""LLM-backed execution helpers for compile, ask, and lint workflows."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiwiki.app_compile import (
    ask_question,
    compile_wiki,
    lint_wiki,
    nightly_health,
    promote_recurring_outputs,
    write_nightly_health,
)
from aiwiki.app_content import (
    concept_summary_is_placeholder,
    placeholder_concept_slugs,
)
from aiwiki.app_memory import store_concept_rewrite_candidate
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_shell import rewrite_recovery_payload_for_paths
from aiwiki.app_state import append_runtime_history, load_machine_memory, load_manifest
from aiwiki.app_utils import (
    parse_frontmatter,
    relative_path,
    render_frontmatter,
    runtime_write_lock,
    runtime_write_operation,
    sha256_bytes,
    slugify,
    strip_frontmatter,
    utc_now,
)
from aiwiki.llm import (
    CompletionResult,
    LLMError,
    classify_backend_error,
)
from aiwiki.runner.clients import (  # noqa: F401
    _append_fallback_stage,
    _client_backend_name,
    _client_backend_requested,
    _client_model_name,
    _client_selected_model_name,
    _fallback_stage_label,
    _fallback_to_next_model,
    create_client,
    llm_probe,
    llm_status,
)
from aiwiki.runner.interfaces import SupportsComplete  # noqa: F401
from aiwiki.runner.prompts import (  # noqa: F401
    ASK_INDEX_PAGES_BASE,
    ASK_INDEX_PAGES_BY_FORMAT,
    ASK_PROMPT_PROFILES,
    ASK_PROTOCOL_PAGE_NAMES_BASE,
    ASK_PROTOCOL_PAGE_NAMES_BY_FORMAT,
    COMPILE_PROMPT_PROFILES,
    LINT_PROMPT_PROFILES,
    _ask_prompt_profile,
    _build_ask_prompt,
    _build_compile_prompt,
    _build_concept_compile_prompt,
    _build_lint_prompt,
    _compile_prompt_profile,
    _context_budget,
    _extract_related_concept_slugs,
    _fit_log_prompt_section,
    _fit_prompt_section,
    _initial_ask_prompt_profile,
    _initial_compile_prompt_profile,
    _initial_lint_prompt_profile,
    _lean_ask_prompt_profile,
    _lint_prompt_profile,
    _load_prompt,
    _normalize_markdown,
    _protocol_context,
    _read_context,
    _render_machine_query,
    _retry_ask_prompt_profile,
    _retry_compile_prompt_profile,
    _retry_lint_prompt_profile,
    _rewrite_candidate_record,
    _rewrite_candidate_slugs,
    _schema_context,
    _select_ask_index_pages,
    _select_ask_protocol_pages,
    _select_initial_ask_prompt_profile,
    _system_prompt,
    _validate_concept_page,
    _validate_output_markdown,
    _validate_source_page,
)
from aiwiki.runner.receipts import (  # noqa: F401
    _append_jsonl_log,
    _append_llm_receipt,
    _append_llm_receipt_and_log,
    _append_log,
    _build_llm_audit,
    _empty_llm_audit,
    _infer_delivery_mode,
    _llm_audit_from_result,
    _merge_llm_audits,
    _next_jsonl_line_number,
)

RUN_ASK_FRONTDOOR_EVENT = "run-ask-frontdoor"
RUN_ASK_FALLBACK_ERROR_KINDS = {"quota", "timeout", "auth", "unavailable"}


def run_l3_proposal_create(
    root: Path,
    *,
    kind: str,
    target_file: str,
    content: str,
    proposal_id: str | None = None,
    rationale: str = "",
    evidence_refs: list[str] | None = None,
    signal_ids: list[str] | None = None,
    pattern: str = "manual_fixture",
) -> dict[str, Any]:
    from aiwiki.execution.l3_proposals import create_l3_proposal

    return create_l3_proposal(
        root,
        kind=kind,
        target_file=target_file,
        content=content,
        proposal_id=proposal_id,
        rationale=rationale,
        evidence_refs=evidence_refs,
        signal_ids=signal_ids,
        pattern=pattern,
    )


def run_l3_proposal_list(root: Path, *, kind: str | None = None, state: str | None = None) -> list[dict[str, Any]]:
    from aiwiki.execution.l3_proposals import list_l3_proposals

    return list_l3_proposals(root, kind=kind, state=state)


def run_l3_proposal_generation_preview(
    root: Path,
    *,
    planner_log_path: Path | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    from aiwiki.execution.l3_proposals import preview_l3_proposal_generation

    return preview_l3_proposal_generation(root, planner_log_path=planner_log_path, limit=limit)


def run_l3_proposal_generate(
    root: Path,
    *,
    planner_log_path: Path | None = None,
    limit: int = 20,
    apply: bool = False,
) -> dict[str, Any]:
    if not apply:
        return run_l3_proposal_generation_preview(root, planner_log_path=planner_log_path, limit=limit)
    from aiwiki.execution.l3_proposals import generate_l3_proposals_from_planner

    return generate_l3_proposals_from_planner(root, planner_log_path=planner_log_path, limit=limit)


def run_l3_proposal_apply(root: Path, proposal_id: str, *, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.l3_proposals import apply_l3_proposal

    return apply_l3_proposal(root, proposal_id, note=note)


def run_l3_proposal_reject(root: Path, proposal_id: str, *, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.l3_proposals import reject_l3_proposal

    return reject_l3_proposal(root, proposal_id, note=note)


def run_l3_proposal_revert(root: Path, receipt_id: str, *, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.l3_proposals import revert_l3_proposal

    return revert_l3_proposal(root, receipt_id, note=note)


def run_alchemy_legacy_migration_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from aiwiki.execution.alchemy import preview_legacy_elixir_migration

    return preview_legacy_elixir_migration(root, limit=limit)


def run_alchemy_legacy_migration_apply(root: Path, *, limit: int = 50, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy import apply_legacy_elixir_migration

    return apply_legacy_elixir_migration(root, limit=limit, note=note)


def run_alchemy_superseded_cleanup_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from aiwiki.execution.alchemy import preview_superseded_elixir_cleanup

    return preview_superseded_elixir_cleanup(root, limit=limit)


def run_alchemy_superseded_cleanup_apply(root: Path, *, limit: int = 50, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy import apply_superseded_elixir_cleanup

    return apply_superseded_elixir_cleanup(root, limit=limit, note=note)


def run_audit_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from aiwiki.execution.audit_preview import preview_universal_audit_stream

    return preview_universal_audit_stream(root, limit=limit)


def run_audit_backfill(root: Path, *, limit: int = 50, apply: bool = False) -> dict[str, Any]:
    from aiwiki.execution.audit_preview import backfill_universal_audit_stream

    return backfill_universal_audit_stream(root, limit=limit, apply=apply)


def run_planner_log_rollback_preview(
    root: Path,
    *,
    signal_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    from aiwiki.planner.rollback import preview_planner_log_rollback

    return preview_planner_log_rollback(root, signal_id=signal_id, trace_id=trace_id, limit=limit)


def run_planner_log_rollback(
    root: Path,
    *,
    signal_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 20,
    apply: bool = False,
) -> dict[str, Any]:
    from aiwiki.planner.rollback import apply_planner_log_rollback_marker

    return apply_planner_log_rollback_marker(root, signal_id=signal_id, trace_id=trace_id, limit=limit, apply=apply)


@runtime_write_operation
def run_compile(root: Path, client: SupportsComplete | None = None, limit: int = 5) -> dict[str, Any]:
    ensure_layout(root)
    compile_result = compile_wiki(root)
    manifest = load_manifest(root)
    pending = []
    for entry in manifest["entries"]:
        page = root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
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

    def summary_base_event(duration_ms: int) -> dict[str, Any]:
        return {
            "event": "run-compile-summary",
            "limit": limit,
            "updated_pages": list(updated_pages),
            "pending_pages": len(pending),
            "skipped_pages": skipped,
            "updated_concept_pages": list(updated_placeholder_concept_pages),
            "pending_concept_pages": len(pending_concept_slugs),
            "skipped_concept_pages": skipped_concepts,
            "updated_rewrite_concept_pages": [],
            "updated_rewrite_proposal_pages": list(updated_rewrite_proposal_pages),
            "pending_rewrite_concept_pages": len(pending_rewrite_candidates),
            "skipped_rewrite_concept_pages": skipped_rewrite_candidates,
            "prompt_profile": prompt_profile,
            "retry_prompt_profile": retry_prompt_profile,
            "duration_ms": duration_ms,
        }

    if (not pending and not pending_concept_slugs and not pending_rewrite_candidates) or limit <= 0:
        llm_audit = _empty_llm_audit()
        rewrite_payload = rewrite_recovery_payload_for_paths(root, updated_rewrite_proposal_pages)
        _append_llm_receipt_and_log(
            root,
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

    effective_client = client or create_client(root)
    model_selected = _client_model_name(effective_client)
    aggregate_audit = _empty_llm_audit()
    prompt_profile = _initial_compile_prompt_profile(effective_client)
    retry_prompt_profile = ""
    try:
        for entry in pending[:limit]:
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
                        if _fallback_to_next_model(effective_client, "run-compile", exc):
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, "model-chain")
                            continue
                        raise
                    updated = _normalize_markdown(item_result.text)
                    try:
                        _validate_source_page(updated, entry["id"], entry["stored_path"], entry["sha256"])
                    except RuntimeError as exc:
                        if _fallback_to_next_model(effective_client, "run-compile", exc):
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, "model-chain")
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
                _append_llm_receipt_and_log(
                    root,
                    {
                        "event": "run-compile",
                        "target": relative_path(root, target),
                        "source": entry["stored_path"],
                        "prompt_profile": used_profile,
                        "retry_prompt_profile": item_retry_profile,
                        "duration_ms": int((time.monotonic() - item_started) * 1000),
                    },
                    item_audit,
                    status="success",
                    response_id=item_result.response_id,
                    usage=item_result.usage,
                )
            except Exception as exc:
                used_profile = item_retry_profile or item_profile
                item_audit = _build_llm_audit(
                    effective_client,
                    model_selected=item_model_selected,
                    fallback_stages=item_fallback_stages,
                    fallback_reason=item_fallback_reason or str(exc),
                    contract_validated=False,
                )
                aggregate_audit = _merge_llm_audits(aggregate_audit, item_audit)
                _append_llm_receipt_and_log(
                    root,
                    {
                        "event": "run-compile",
                        "target": relative_path(root, target),
                        "source": entry["stored_path"],
                        "prompt_profile": used_profile,
                        "retry_prompt_profile": item_retry_profile,
                        "duration_ms": int((time.monotonic() - item_started) * 1000),
                    },
                    item_audit,
                    status="failed",
                    error=str(exc),
                    response_id=getattr(item_result, "response_id", "") if item_result is not None else "",
                    usage=getattr(item_result, "usage", {}) if item_result is not None else {},
                )
                raise

        if updated_pages:
            compile_result = compile_wiki(root)
            pending_concept_slugs = placeholder_concept_slugs(root)
            memory = load_machine_memory(root)
        remaining_budget = max(0, limit - len(updated_pages))
        skipped_concepts = max(0, len(pending_concept_slugs) - remaining_budget)

        for slug in pending_concept_slugs[:remaining_budget]:
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
                        if _fallback_to_next_model(effective_client, "run-compile-concept", exc):
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, "model-chain")
                            continue
                        raise
                    updated = _normalize_markdown(item_result.text)
                    try:
                        _validate_concept_page(updated, slug, frontmatter.get("source_signature", ""), source_pages)
                    except RuntimeError as exc:
                        if _fallback_to_next_model(effective_client, "run-compile-concept", exc):
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, "model-chain")
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
                _append_llm_receipt_and_log(
                    root,
                    {
                        "event": "run-compile-concept",
                        "target": relative_path(root, target),
                        "source_pages": source_pages,
                        "prompt_profile": used_profile,
                        "retry_prompt_profile": item_retry_profile,
                        "duration_ms": int((time.monotonic() - item_started) * 1000),
                    },
                    item_audit,
                    status="success",
                    response_id=item_result.response_id,
                    usage=item_result.usage,
                )
            except Exception as exc:
                used_profile = item_retry_profile or item_profile
                item_audit = _build_llm_audit(
                    effective_client,
                    model_selected=item_model_selected,
                    fallback_stages=item_fallback_stages,
                    fallback_reason=item_fallback_reason or str(exc),
                    contract_validated=False,
                )
                aggregate_audit = _merge_llm_audits(aggregate_audit, item_audit)
                _append_llm_receipt_and_log(
                    root,
                    {
                        "event": "run-compile-concept",
                        "target": relative_path(root, target),
                        "source_pages": source_pages,
                        "prompt_profile": used_profile,
                        "retry_prompt_profile": item_retry_profile,
                        "duration_ms": int((time.monotonic() - item_started) * 1000),
                    },
                    item_audit,
                    status="failed",
                    error=str(exc),
                    response_id=getattr(item_result, "response_id", "") if item_result is not None else "",
                    usage=getattr(item_result, "usage", {}) if item_result is not None else {},
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

        for slug in pending_rewrite_candidates[:remaining_budget]:
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
                        if _fallback_to_next_model(effective_client, "run-compile-rewrite", exc):
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, "model-chain")
                            continue
                        raise
                    updated = _normalize_markdown(item_result.text)
                    try:
                        _validate_concept_page(updated, slug, frontmatter.get("source_signature", ""), source_pages)
                    except RuntimeError as exc:
                        if _fallback_to_next_model(effective_client, "run-compile-rewrite", exc):
                            item_fallback_reason = str(exc)
                            _append_fallback_stage(item_fallback_stages, "model-chain")
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
                _append_llm_receipt_and_log(
                    root,
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
                    },
                    item_audit,
                    status="success",
                    response_id=item_result.response_id,
                    usage=item_result.usage,
                )
            except Exception as exc:
                used_profile = item_retry_profile or item_profile
                item_audit = _build_llm_audit(
                    effective_client,
                    model_selected=item_model_selected,
                    fallback_stages=item_fallback_stages,
                    fallback_reason=item_fallback_reason or str(exc),
                    contract_validated=False,
                )
                aggregate_audit = _merge_llm_audits(aggregate_audit, item_audit)
                _append_llm_receipt_and_log(
                    root,
                    {
                        "event": "run-compile-concept-rewrite-proposal",
                        "target": f"wiki/rewrite-proposals/{slug}.md",
                        "concept_page": relative_path(root, target),
                        "source_pages": source_pages,
                        "quality_priority": quality_record.get("priority", ""),
                        "quality_issues": quality_record.get("issues", []),
                        "prompt_profile": used_profile,
                        "retry_prompt_profile": item_retry_profile,
                        "duration_ms": int((time.monotonic() - item_started) * 1000),
                    },
                    item_audit,
                    status="failed",
                    error=str(exc),
                    response_id=getattr(item_result, "response_id", "") if item_result is not None else "",
                    usage=getattr(item_result, "usage", {}) if item_result is not None else {},
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
        _append_llm_receipt_and_log(
            root,
            summary_base_event(int((time.monotonic() - started) * 1000)),
            failed_audit,
            status="failed",
            error=str(exc),
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
    _append_llm_receipt_and_log(
        root,
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
def run_ask(
    root: Path,
    question: str,
    output_format: str,
    protocol: str | None = None,
    client: SupportsComplete | None = None,
    lean: bool = False,
    timeout_seconds: int | None = None,
    no_cache: bool = False,
    fallback_to_ask: bool = False,
    corpus_id_override: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("run-ask timeout_seconds must be greater than 0.")
    ask_kwargs = {"protocol": protocol, "no_cache": no_cache}
    if corpus_id_override is not None:
        ask_kwargs["corpus_id_override"] = corpus_id_override
    artifact = ask_question(root, question, output_format, **ask_kwargs)
    manifest = load_manifest(root)
    entry_map = {entry["id"]: entry for entry in manifest["entries"]}
    source_ids = artifact["ranked_sources"]
    source_pages = []
    for source_id in source_ids:
        entry = entry_map.get(source_id)
        if entry is None:
            continue
        page = root / "wiki" / "sources" / f"{source_id}.md"
        if page.exists():
            source_pages.append((entry, page.read_text(encoding="utf-8", errors="replace")))
    concept_pages = []
    for slug in artifact.get("ranked_concepts", []):
        page = root / "wiki" / "concepts" / f"{slug}.md"
        if page.exists():
            concept_pages.append((slug, page.read_text(encoding="utf-8", errors="replace")))
    protocol_pages = []
    for relative in artifact.get("protocol_pages", []):
        page = root / relative
        if page.exists():
            protocol_pages.append((relative, page.read_text(encoding="utf-8", errors="replace")))
    index_pages = []
    for relative in artifact.get("index_pages", []):
        page = root / relative
        if page.exists():
            index_pages.append((relative, page.read_text(encoding="utf-8", errors="replace")))

    target = root / artifact["path"]
    current_artifact = target.read_text(encoding="utf-8", errors="replace")
    effective_client = client or create_client(root, timeout_seconds=timeout_seconds)
    backend_requested = _client_backend_requested(effective_client)
    model_selected = _client_selected_model_name(effective_client)
    prompt_profile = _select_initial_ask_prompt_profile(effective_client, lean=lean)
    previous_output_summary = None
    corpus_id = str(artifact.get("active_corpus_id") or "")
    if corpus_id:
        from aiwiki.execution.ask import load_previous_output_summary

        previous_output_summary = load_previous_output_summary(root, corpus_id, exclude_artifact_ref=artifact.get("path"))
    prompt = _build_ask_prompt(
        root,
        target,
        question,
        output_format,
        current_artifact,
        source_pages,
        concept_pages,
        protocol_pages,
        index_pages,
        artifact.get("machine_memory_query", {}),
        previous_output_summary=previous_output_summary,
        prompt_profile=prompt_profile,
    )
    retry_profile = ""
    fallback_stages: list[str] = []
    fallback_reason = ""
    started = time.monotonic()
    result: CompletionResult | None = None
    used_prompt_profile = prompt_profile
    effective_timeout_seconds = getattr(getattr(effective_client, "config", None), "timeout_seconds", timeout_seconds)
    try:
        while True:
            try:
                result = effective_client.complete(_system_prompt("ask"), prompt)
            except LLMError as exc:
                next_retry_profile = _retry_ask_prompt_profile(exc, prompt_profile, effective_client)
                if next_retry_profile:
                    retry_profile = next_retry_profile
                    fallback_reason = str(exc)
                    _append_fallback_stage(fallback_stages, "prompt-profile")
                    logging.getLogger("aiwiki").warning(
                        "run-ask failed with %s prompt; retrying with %s prompt",
                        prompt_profile,
                        retry_profile,
                    )
                    prompt = _build_ask_prompt(
                        root,
                        target,
                        question,
                        output_format,
                        current_artifact,
                        source_pages,
                        concept_pages,
                        protocol_pages,
                        index_pages,
                        artifact.get("machine_memory_query", {}),
                        previous_output_summary=previous_output_summary,
                        prompt_profile=retry_profile,
                    )
                    prompt_profile = retry_profile
                    used_prompt_profile = retry_profile
                    continue
                if _fallback_to_next_model(effective_client, "run-ask", exc):
                    fallback_reason = str(exc)
                    _append_fallback_stage(fallback_stages, "model-chain")
                    continue
                raise
            updated = _normalize_markdown(result.text)
            try:
                _validate_output_markdown(updated, output_format, source_ids)
            except RuntimeError as exc:
                if _fallback_to_next_model(effective_client, "run-ask", exc):
                    fallback_reason = str(exc)
                    _append_fallback_stage(fallback_stages, "model-chain")
                    continue
                raise
            break
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        failed_audit = {
            "backend_requested": backend_requested,
            "backend_effective": _client_backend_name(effective_client),
            "model_selected": model_selected,
            "model_final": _client_model_name(effective_client),
            "fallback_stage": _fallback_stage_label(fallback_stages),
            "fallback_reason": fallback_reason or str(exc),
            "contract_validated": False,
        }
        _append_llm_receipt_and_log(
            root,
            {
                "event": "run-ask",
                "target": artifact["path"],
                "question": question,
                "format": output_format,
                "protocol": artifact.get("protocol", ""),
                "duration_ms": duration_ms,
                "prompt_profile": retry_profile or used_prompt_profile,
                "retry_prompt_profile": retry_profile,
                "no_cache": no_cache,
            },
            failed_audit,
            status="failed",
            error=str(exc),
            response_id=getattr(result, "response_id", "") if result is not None else "",
            usage=getattr(result, "usage", {}) if result is not None else {},
        )
        if fallback_to_ask:
            frontdoor_base_event = {
                "event": RUN_ASK_FRONTDOOR_EVENT,
                "target": artifact["path"],
                "question": question,
                "format": output_format,
                "protocol": artifact.get("protocol", ""),
                "duration_ms": duration_ms,
                "prompt_profile": retry_profile or used_prompt_profile,
                "retry_prompt_profile": retry_profile,
                "timeout_seconds": effective_timeout_seconds,
                "no_cache": no_cache,
                "primary_attempt_status": "failed",
                "primary_error": str(exc),
            }
            if classify_backend_error(str(exc)) in RUN_ASK_FALLBACK_ERROR_KINDS:
                _append_llm_receipt_and_log(
                    root,
                    {
                        **frontdoor_base_event,
                        "delivery_mode": "deterministic-fallback",
                        "fallback_used": True,
                        "fallback_from": "run-ask",
                        "fallback_command": "ask",
                    },
                    {**failed_audit, "delivery_mode": "deterministic-fallback", "fallback_used": True, "fallback_from": "run-ask", "fallback_command": "ask"},
                    status="success",
                    error=str(exc),
                    response_id=getattr(result, "response_id", "") if result is not None else "",
                    usage=getattr(result, "usage", {}) if result is not None else {},
                )
                return {
                    **artifact,
                    **failed_audit,
                    "status": "success",
                    "prompt_profile": retry_profile or used_prompt_profile,
                    "retry_prompt_profile": retry_profile,
                    "timeout_seconds": effective_timeout_seconds,
                    "no_cache": no_cache,
                    "delivery_mode": "deterministic-fallback",
                    "primary_attempt_status": "failed",
                    "primary_error": str(exc),
                    "fallback_used": True,
                    "fallback_from": "run-ask",
                    "fallback_command": "ask",
                }
            _append_llm_receipt_and_log(
                root,
                frontdoor_base_event,
                failed_audit,
                status="failed",
                error=str(exc),
                response_id=getattr(result, "response_id", "") if result is not None else "",
                usage=getattr(result, "usage", {}) if result is not None else {},
            )
        raise
    target.write_text(updated, encoding="utf-8")
    # LLM 覆盖了整个 artifact，需要重新注入 candidate_state 与 corpus_id frontmatter 字段
    # 让 EP-029 candidate 队列语义在 run-ask 全链路保持一致（与 ask_question 内的插入逻辑同款）。
    _reinject_candidate_frontmatter(target, corpus_id=corpus_id)
    backend_effective = _client_backend_name(effective_client)
    model_final = _client_model_name(effective_client)
    fallback_stage = _fallback_stage_label(fallback_stages)
    llm_audit = {
        "backend_requested": backend_requested,
        "backend_effective": backend_effective,
        "model_selected": model_selected,
        "model_final": model_final,
        "fallback_stage": fallback_stage,
        "fallback_reason": fallback_reason,
        "contract_validated": True,
    }
    _append_llm_receipt_and_log(
        root,
        {
            "event": "run-ask",
            "target": artifact["path"],
            "question": question,
            "format": output_format,
            "protocol": artifact.get("protocol", ""),
            "duration_ms": int((time.monotonic() - started) * 1000),
            "prompt_profile": retry_profile or used_prompt_profile,
            "retry_prompt_profile": retry_profile,
            "no_cache": no_cache,
        },
        llm_audit,
        status="success",
        response_id=result.response_id,
        usage=result.usage,
    )
    payload = {
        **artifact,
        **llm_audit,
        "prompt_profile": retry_profile or used_prompt_profile,
        "retry_prompt_profile": retry_profile,
        "timeout_seconds": effective_timeout_seconds,
        "no_cache": no_cache,
    }
    if fallback_to_ask:
        _append_llm_receipt_and_log(
            root,
            {
                "event": RUN_ASK_FRONTDOOR_EVENT,
                "target": artifact["path"],
                "question": question,
                "format": output_format,
                "protocol": artifact.get("protocol", ""),
                "duration_ms": int((time.monotonic() - started) * 1000),
                "prompt_profile": retry_profile or used_prompt_profile,
                "retry_prompt_profile": retry_profile,
                "timeout_seconds": effective_timeout_seconds,
                "no_cache": no_cache,
                "delivery_mode": "llm",
                "primary_attempt_status": "success",
                "primary_error": "",
                "fallback_used": False,
                "fallback_from": "",
                "fallback_command": "",
            },
            llm_audit,
            status="success",
            response_id=result.response_id,
            usage=result.usage,
        )
        return {
            **payload,
            "status": "success",
            "delivery_mode": "llm",
            "primary_attempt_status": "success",
            "primary_error": "",
            "fallback_used": False,
            "fallback_from": "",
            "fallback_command": "",
        }
    return payload


@runtime_write_operation
def run_promote(root: Path, artifact_ref: str) -> dict[str, Any]:
    from aiwiki.execution.candidates import promote_candidate

    return promote_candidate(root, artifact_ref)


@runtime_write_operation
def run_demote(root: Path, artifact_ref: str) -> dict[str, Any]:
    from aiwiki.execution.candidates import demote_candidate

    return demote_candidate(root, artifact_ref)


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
                if _fallback_to_next_model(effective_client, "run-lint", exc):
                    fallback_reason = str(exc)
                    _append_fallback_stage(fallback_stages, "model-chain")
                    continue
                raise
            updated = _normalize_markdown(result.text)
            if not updated.startswith("#") and not updated.startswith("---"):
                exc = RuntimeError("Semantic lint response must be markdown.")
                if _fallback_to_next_model(effective_client, "run-lint", exc):
                    fallback_reason = str(exc)
                    _append_fallback_stage(fallback_stages, "model-chain")
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
        _append_llm_receipt_and_log(
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
    _append_llm_receipt_and_log(
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
    except Exception as exc:
        failed_audit = _merge_llm_audits(
            _build_llm_audit(effective_client, model_selected=model_selected, contract_validated=False),
            _merge_llm_audits(_llm_audit_from_result(compile_result or {}), _llm_audit_from_result(lint_result or {})),
        )
        failed_audit["fallback_reason"] = str(exc)
        failed_audit["contract_validated"] = False
        _append_llm_receipt_and_log(
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
        )
        raise
    _append_llm_receipt_and_log(
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


@runtime_write_operation
def auto_process_once(
    root: Path,
    client: SupportsComplete | None = None,
    compile_limit: int = 5,
    deterministic_only: bool = False,
    semantic_lint: bool = True,
) -> dict[str, Any]:
    ensure_layout(root)
    llm_enabled = bool(client) or (not deterministic_only and llm_status()["configured"])
    llm_failed = False

    if llm_enabled and not deterministic_only:
        try:
            compile_result = run_compile(root, client=client, limit=compile_limit)
        except Exception as exc:
            logging.getLogger("aiwiki").warning("LLM compile failed, falling back to deterministic: %s", exc)
            llm_failed = True
            compile_result = {
                "compile": compile_wiki(root),
                "updated_pages": [],
                "pending_pages": _pending_summary_count(root),
                "skipped_pages": 0,
            }
    else:
        compile_result = {
            "compile": compile_wiki(root),
            "updated_pages": [],
            "pending_pages": _pending_summary_count(root),
            "skipped_pages": 0,
        }

    if semantic_lint and llm_enabled and not deterministic_only and not llm_failed:
        try:
            lint_result = run_lint(root, client=client)
        except Exception as exc:
            logging.getLogger("aiwiki").warning("LLM lint failed, falling back to deterministic: %s", exc)
            llm_failed = True
            lint_result = {
                "deterministic": lint_wiki(root),
                "semantic_report": "",
            }
    else:
        lint_result = {
            "deterministic": lint_wiki(root),
            "semantic_report": "",
        }

    snapshot = inbox_snapshot(root)
    actually_used_llm = bool(llm_enabled and not deterministic_only and not llm_failed)
    result = {
        "processed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "llm_used": actually_used_llm,
        "llm_fallback": llm_failed,
        "compile": compile_result,
        "lint": lint_result,
        "inbox_snapshot": snapshot,
    }
    _write_automation_state(root, result)
    _append_log(
        root,
        {
            "event": "auto-process",
            "llm_used": result["llm_used"],
            "llm_fallback": llm_failed,
            "compile_limit": compile_limit,
            "inbox_digest": snapshot["digest"],
        },
    )
    return result


@runtime_write_operation
def run_alchemy_start(
    root: Path,
    corpus_id: str,
    topic: str,
    *,
    protocol: str | None = None,
    include_elixir_ids: list[str] | None = None,
) -> dict[str, Any]:
    from aiwiki.execution.alchemy import start_elixir

    return start_elixir(root, corpus_id, protocol=protocol, topic=topic, include_elixir_ids=include_elixir_ids)


@runtime_write_operation
def run_alchemy_distill(root: Path, elixir_id: str, question: str, include_elixir_ids: list[str] | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy import distill_elixir

    return distill_elixir(root, elixir_id, question=question, include_elixir_ids=include_elixir_ids)


@runtime_write_operation
def run_alchemy_finalize(root: Path, *, elixir_id: str) -> dict[str, Any]:
    from aiwiki.execution.alchemy import finalize_elixir

    return finalize_elixir(root, elixir_id=elixir_id)


@runtime_write_operation
def run_alchemy_promote(root: Path, *, elixir_id: str, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy import promote_elixir

    return promote_elixir(root, elixir_id=elixir_id, note=note)


def run_alchemy_revert(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    from aiwiki.execution.alchemy import revert_elixir

    with runtime_write_lock(root):
        return revert_elixir(root, elixir_id=elixir_id, note=note)


def run_alchemy_demote(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    from aiwiki.execution.alchemy import demote_elixir

    with runtime_write_lock(root):
        return demote_elixir(root, elixir_id=elixir_id, note=note)


@runtime_write_operation
def run_protocol_learn_add(root: Path, protocol: str, title: str, source_refs: list[str] | None) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import add_learning

    return add_learning(root, protocol, title=title, source_refs=source_refs)


def run_protocol_learn_list(
    root: Path,
    protocol: str | None = None,
    *,
    state_filter: str | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    from aiwiki.execution.protocol_learnings import list_learnings

    return list_learnings(root, protocol, state_filter=state_filter, include_archived=include_archived)


def run_protocol_learn_show(root: Path, learning_id: str) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import show_learning

    return show_learning(root, learning_id)


def run_signals_list(
    root: Path,
    *,
    kind: str | None = None,
    trace_id: str | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from aiwiki.inspection import read_signals

    return read_signals(
        root,
        kind=kind,
        trace_id=trace_id,
        since=since,
        limit=limit,
    )


def run_signals_show(root: Path, signal_id: str) -> dict[str, Any]:
    from aiwiki.inspection import find_planner_decisions_for_signal, find_signal_by_id

    signal = find_signal_by_id(root, signal_id)
    if signal is None:
        return {"status": "not_found", "signal_id": signal_id}
    decisions = find_planner_decisions_for_signal(root, signal_id)
    return {
        "status": "ok",
        "signal": signal,
        "planner_decisions": decisions,
    }


def run_planner_log_list(
    root: Path,
    *,
    decision: str | None = None,
    signal_id: str | None = None,
    trace_id: str | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from aiwiki.inspection import read_planner_decisions

    return read_planner_decisions(
        root,
        decision=decision,
        signal_id=signal_id,
        trace_id=trace_id,
        since=since,
        limit=limit,
    )


def run_alchemy_lane_dry_run(
    root: Path,
    *,
    lane: str,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    from aiwiki.planner import preview_alchemy_lane

    return preview_alchemy_lane(
        root,
        lane=lane,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
    )


def run_alchemy_judge_preview(
    root: Path,
    *,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    from aiwiki.planner import preview_judge_primitive

    return preview_judge_primitive(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )


def run_alchemy_judge_apply(
    root: Path,
    *,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    limit: int = 50,
    note: str | None = None,
) -> dict[str, Any]:
    preview = run_alchemy_judge_preview(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )
    status = str(preview.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy judge apply requires an ok dry-run preview (got {status})")
    candidates = [
        item
        for item in preview.get("candidates", [])
        if isinstance(item, dict) and item.get("apply_supported") is True and item.get("kind") == "judgment_refresh"
    ]
    if not candidates:
        raise RuntimeError("alchemy judge apply requires at least one apply-supported judgment candidate")

    from aiwiki.app_execution import append_execution_receipt_history
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.render.paths import execution_receipt_path

    refreshed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        result = _materialize_alchemy_judge_refresh(root, preview=preview, candidate=candidate)
        if result["status"] == "skipped":
            skipped.append(result)
        else:
            refreshed.append(result)

    applied_at = utc_now()
    action_id = _unique_alchemy_judge_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = _preview_trace_ids(preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    idempotency_key = _alchemy_judge_idempotency_key(scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-judge",
        "applied_at": applied_at,
        "operation": "alchemy-judge-refresh",
        "action_id": action_id,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "title": f"Alchemy judge refresh {scope}",
        "status": "applied",
        "protocol": _first_preview_protocol(preview),
        "subject_kind": "alchemy_judgment_page",
        "subject_id": f"judge:{scope}",
        "apply_mode": "alchemy-judge",
        "note": note or "",
        "primary_path": "wiki/judgments",
        "secondary_path": "wiki/decisions",
        "receipt_path": relative_path(root, receipt_path),
        "scope": scope,
        "primitive": "judge",
        "candidate_ids": candidate_ids,
        "candidate_count": len(candidates),
        "refreshed_count": len(refreshed),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "idempotency_key": idempotency_key,
        "changed": any(item.get("changed") for item in refreshed),
        "revert_supported": False,
        "revert_policy": "non_revertible_refresh_marker: reapply a newer judge preview to replace the managed marker; semantic judgment edits remain explicit",
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
        "source_preview": _judge_preview_receipt_summary(preview, candidates),
        "result_summary": {"refreshed": refreshed, "skipped": skipped},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "alchemy-judge-refreshed",
            "recorded_at": applied_at,
            "status": "completed",
            "scope": scope,
            "candidate_count": len(candidates),
            "candidate_ids": candidate_ids,
            "refreshed_count": len(refreshed),
            "skipped_count": len(skipped),
            "receipt_path": relative_path(root, receipt_path),
            "trace_id": trace_id,
            "trace_ids": trace_ids,
            "subject_kind": "alchemy_judgment_page",
            "subject_id": f"judge:{scope}",
        },
    )
    return {
        "status": "applied",
        "primitive": "judge",
        "scope": scope,
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "refreshed_count": len(refreshed),
        "refreshed": refreshed,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "receipt_path": relative_path(root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": any(item.get("changed") for item in refreshed),
        "preview": preview,
    }


def run_alchemy_judge_propose(
    root: Path,
    *,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    limit: int = 50,
    note: str | None = None,
) -> dict[str, Any]:
    preview = run_alchemy_judge_preview(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )
    status = str(preview.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy judge propose requires an ok dry-run preview (got {status})")
    candidates = [
        item
        for item in preview.get("candidates", [])
        if isinstance(item, dict) and item.get("apply_supported") is True and item.get("kind") == "judgment_refresh"
    ]
    if not candidates:
        raise RuntimeError("alchemy judge propose requires at least one existing judgment candidate")

    from aiwiki.app_execution import append_execution_receipt_history
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.render.paths import execution_receipt_path

    generated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        result = _materialize_alchemy_judge_proposal(root, preview=preview, candidate=candidate)
        if result["status"] == "skipped":
            skipped.append(result)
        else:
            generated.append(result)

    applied_at = utc_now()
    action_id = _unique_alchemy_judge_proposal_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = _preview_trace_ids(preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    proposal_ids = [
        str(item.get("proposal_id") or "")
        for item in [*generated, *skipped]
        if item.get("proposal_id")
    ]
    idempotency_key = _alchemy_judge_proposal_idempotency_key(scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-judge-proposal",
        "applied_at": applied_at,
        "operation": "alchemy-judge-proposal-preview",
        "action_id": action_id,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "title": f"Alchemy judge proposal preview {scope}",
        "status": "applied",
        "protocol": _first_preview_protocol(preview),
        "subject_kind": "alchemy_judge_proposal",
        "subject_id": f"judge-proposal:{scope}",
        "apply_mode": "alchemy-judge-propose",
        "note": note or "",
        "primary_path": "output/_proposals/judge",
        "secondary_path": "",
        "receipt_path": relative_path(root, receipt_path),
        "scope": scope,
        "primitive": "judge",
        "candidate_ids": candidate_ids,
        "candidate_count": len(candidates),
        "proposal_ids": proposal_ids,
        "generated_count": len(generated),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "idempotency_key": idempotency_key,
        "changed": bool(generated),
        "llm_invoked": False,
        "semantic_content_generated": False,
        "human_accept_required": True,
        "revert_supported": False,
        "revert_policy": "non_revertible_proposal_preview: reject or ignore generated proposal artifacts; target judgment pages are unchanged",
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
        "source_preview": _judge_preview_receipt_summary(preview, candidates),
        "result_summary": {"generated": generated, "skipped": skipped},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "alchemy-judge-proposal-created",
            "recorded_at": applied_at,
            "status": "completed",
            "scope": scope,
            "candidate_count": len(candidates),
            "candidate_ids": candidate_ids,
            "generated_count": len(generated),
            "proposal_ids": proposal_ids,
            "receipt_path": relative_path(root, receipt_path),
            "trace_id": trace_id,
            "trace_ids": trace_ids,
            "subject_kind": "alchemy_judge_proposal",
            "subject_id": f"judge-proposal:{scope}",
            "llm_invoked": False,
            "semantic_content_generated": False,
        },
    )
    return {
        "status": "applied",
        "primitive": "judge",
        "mode": "propose",
        "scope": scope,
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "generated_count": len(generated),
        "proposal_ids": proposal_ids,
        "generated": generated,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "receipt_path": relative_path(root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": bool(generated),
        "llm_invoked": False,
        "semantic_content_generated": False,
        "human_accept_required": True,
        "preview": preview,
    }


def run_alchemy_judge_proposal_apply(
    root: Path,
    proposal: str | Path,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    from aiwiki.app_execution import append_execution_receipt_history
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.render.paths import execution_receipt_path

    proposal_path = _resolve_alchemy_judge_proposal_path(root, proposal)
    original_proposal = proposal_path.read_text(encoding="utf-8", errors="replace")
    proposal_frontmatter = parse_frontmatter(original_proposal)
    proposal_id = str(proposal_frontmatter.get("proposal_id") or proposal_path.stem)
    if str(proposal_frontmatter.get("kind") or "") != "alchemy-judge-proposal":
        raise ValueError("judge proposal apply requires kind=alchemy-judge-proposal.")
    if str(proposal_frontmatter.get("state") or "") != "accepted":
        raise RuntimeError("judge proposal apply requires proposal state=accepted.")
    target_ref = str(proposal_frontmatter.get("target_file") or "").strip()
    if not target_ref:
        raise ValueError("judge proposal apply requires target_file.")
    expected_hash = str(proposal_frontmatter.get("before_hash") or "").strip()
    if not expected_hash:
        raise ValueError("judge proposal apply requires before_hash.")
    accepted_body = _extract_marker_section(
        original_proposal,
        start_marker=_ALCHEMY_JUDGE_ACCEPTED_REFRESH_START,
        end_marker=_ALCHEMY_JUDGE_ACCEPTED_REFRESH_END,
    )
    if not accepted_body.strip():
        raise ValueError("judge proposal apply requires a non-empty accepted refresh block.")

    target = (root / target_ref).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("judge proposal target_file must stay within the workspace.") from exc
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"judge proposal target not found: {target_ref}")
    original_target = target.read_text(encoding="utf-8", errors="replace")
    target_frontmatter = parse_frontmatter(original_target)
    target_kind = str(target_frontmatter.get("kind") or "")
    if target_kind not in {"decision", "judgment"}:
        raise ValueError("judge proposal target must be a judgment or decision page.")
    before_hash = sha256_bytes(original_target.encode("utf-8"))
    if before_hash != expected_hash:
        raise RuntimeError("judge proposal target is stale; before_hash does not match current target.")

    target_body = strip_frontmatter(original_target).strip()
    section = _render_alchemy_judge_accepted_target_section(
        proposal_id=proposal_id,
        proposal_path=relative_path(root, proposal_path),
        accepted_body=accepted_body,
    )
    updated_body = _replace_marker_section(
        target_body,
        section,
        start_marker=_ALCHEMY_JUDGE_ACCEPTED_TARGET_START,
        end_marker=_ALCHEMY_JUDGE_ACCEPTED_TARGET_END,
    )
    updated_target = f"{render_frontmatter(target_frontmatter)}\n\n{updated_body.strip()}\n"
    changed = updated_target != original_target
    if changed:
        target.write_text(updated_target, encoding="utf-8")
    after_hash = sha256_bytes(updated_target.encode("utf-8"))

    applied_at = utc_now()
    action_id = _unique_alchemy_judge_proposal_apply_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    proposal_frontmatter["state"] = "applied"
    proposal_frontmatter["applied_at"] = applied_at
    proposal_frontmatter["receipt_path"] = relative_path(root, receipt_path)
    proposal_body = strip_frontmatter(original_proposal).strip()
    updated_proposal = f"{render_frontmatter(proposal_frontmatter)}\n\n{proposal_body}\n"
    proposal_path.write_text(updated_proposal, encoding="utf-8")
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-judge-proposal-apply",
        "applied_at": applied_at,
        "operation": "alchemy-judge-proposal-apply",
        "action_id": action_id,
        "title": f"Apply judge proposal {proposal_id}",
        "status": "applied",
        "subject_kind": "alchemy_judgment_page",
        "subject_id": target_ref,
        "apply_mode": "alchemy-judge-proposal",
        "note": note or "",
        "proposal_id": proposal_id,
        "proposal_path": relative_path(root, proposal_path),
        "target_file": target_ref,
        "target_kind": target_kind,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "changed": changed,
        "llm_invoked": False,
        "semantic_content_generated_by_runtime": False,
        "receipt_path": relative_path(root, receipt_path),
        "revert_supported": False,
        "revert_policy": "non_revertible_managed_section: restore target from before_hash manually or apply a newer accepted judge proposal",
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "alchemy-judge-proposal-applied",
            "recorded_at": applied_at,
            "status": "completed",
            "proposal_id": proposal_id,
            "proposal_path": relative_path(root, proposal_path),
            "target_file": target_ref,
            "receipt_path": relative_path(root, receipt_path),
            "subject_kind": "alchemy_judgment_page",
            "subject_id": target_ref,
            "changed": changed,
            "llm_invoked": False,
        },
    )
    return {
        "status": "applied",
        "primitive": "judge",
        "mode": "proposal-apply",
        "proposal_id": proposal_id,
        "proposal_path": relative_path(root, proposal_path),
        "target_file": target_ref,
        "target_kind": target_kind,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "changed": changed,
        "receipt_path": relative_path(root, receipt_path),
        "audit_path": audit_path,
        "llm_invoked": False,
    }


def run_alchemy_distill_preview(
    root: Path,
    *,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    from aiwiki.planner import preview_distill_primitive

    return preview_distill_primitive(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )


def run_alchemy_distill_apply(
    root: Path,
    *,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    limit: int = 50,
    note: str | None = None,
) -> dict[str, Any]:
    preview = run_alchemy_distill_preview(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )
    status = str(preview.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy distill apply requires an ok dry-run preview (got {status})")
    candidates = [
        item
        for item in preview.get("candidates", [])
        if isinstance(item, dict) and item.get("apply_supported") is True and item.get("kind") == "elixir_candidate_refresh"
    ]
    if not candidates:
        raise RuntimeError("alchemy distill apply requires at least one apply-supported elixir candidate")

    from aiwiki.app_execution import append_execution_receipt_history, compute_file_sha256
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.render.paths import execution_receipt_path

    ensure_layout(root)
    refreshed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        target_ref = str(candidate.get("target_ref") or "")
        target_id = _alchemy_distill_target_id(target_ref)
        if not target_id:
            skipped.append({"candidate_id": candidate_id, "target_ref": target_ref, "reason": "missing_target_ref"})
            continue
        candidate_path = root / "output" / "_candidates" / "elixirs" / f"{target_id}.md"
        if not candidate_path.exists():
            skipped.append({"candidate_id": candidate_id, "target_ref": target_ref, "elixir_id": target_id, "reason": "target_missing"})
            continue
        question = _alchemy_distill_question(candidate)
        if question in _alchemy_distill_history_questions(candidate_path):
            skipped.append({"candidate_id": candidate_id, "target_ref": target_ref, "elixir_id": target_id, "reason": "already_distilled"})
            continue
        before_hash = compute_file_sha256(candidate_path)
        result = run_alchemy_distill(root, target_id, question)
        result_path = root / str(result.get("path") or relative_path(root, candidate_path))
        after_hash = compute_file_sha256(result_path)
        refreshed.append(
            {
                "candidate_id": candidate_id,
                "target_ref": target_ref,
                "elixir_id": target_id,
                "path": relative_path(root, result_path),
                "question": question,
                "before_hash": before_hash,
                "after_hash": after_hash,
                "iteration": result.get("iteration"),
            }
        )

    applied_at = utc_now()
    action_id = _unique_alchemy_distill_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = _preview_trace_ids(preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    idempotency_key = _alchemy_distill_idempotency_key(scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-distill",
        "applied_at": applied_at,
        "operation": "alchemy-distill-refresh",
        "action_id": action_id,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "title": f"Alchemy distill refresh {scope}",
        "status": "applied",
        "protocol": _first_preview_protocol(preview),
        "subject_kind": "alchemy_elixir_candidate",
        "subject_id": f"distill:{scope}",
        "apply_mode": "alchemy-distill",
        "note": note or "",
        "primary_path": "output/_candidates/elixirs",
        "secondary_path": "",
        "receipt_path": relative_path(root, receipt_path),
        "scope": scope,
        "primitive": "distill",
        "candidate_ids": candidate_ids,
        "candidate_count": len(candidates),
        "refreshed_count": len(refreshed),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "idempotency_key": idempotency_key,
        "changed": bool(refreshed),
        "revert_supported": False,
        "revert_policy": "non_revertible_candidate_iteration: re-run distill/finalize/promote lifecycle with receipt evidence; before/after hashes document refreshed candidates",
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
        "source_preview": _distill_preview_receipt_summary(preview, candidates),
        "result_summary": {"refreshed": refreshed, "skipped": skipped},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "alchemy-distill-refreshed",
            "recorded_at": applied_at,
            "status": "completed",
            "scope": scope,
            "candidate_count": len(candidates),
            "candidate_ids": candidate_ids,
            "refreshed_count": len(refreshed),
            "skipped_count": len(skipped),
            "receipt_path": relative_path(root, receipt_path),
            "trace_id": trace_id,
            "trace_ids": trace_ids,
            "subject_kind": "alchemy_elixir_candidate",
            "subject_id": f"distill:{scope}",
        },
    )
    return {
        "status": "applied",
        "primitive": "distill",
        "scope": scope,
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "refreshed_count": len(refreshed),
        "refreshed": refreshed,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "receipt_path": relative_path(root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": bool(refreshed),
        "preview": preview,
    }


def run_alchemy_review_preview(
    root: Path,
    *,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    from aiwiki.planner import preview_review_primitive

    return preview_review_primitive(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )


def run_alchemy_review_apply(
    root: Path,
    *,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    limit: int = 50,
    note: str | None = None,
) -> dict[str, Any]:
    preview = run_alchemy_review_preview(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )
    status = str(preview.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy review apply requires an ok dry-run preview (got {status})")
    candidates = [item for item in preview.get("candidates", []) if isinstance(item, dict)]
    if not candidates:
        raise RuntimeError("alchemy review apply requires a non-empty dry-run preview")

    queue_result = _materialize_alchemy_review_queue(root, preview=preview, candidates=candidates)
    applied_at = utc_now()
    action_id = _unique_alchemy_review_action_id(root, applied_at=applied_at)

    from aiwiki.app_execution import append_execution_receipt_history
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.render.paths import execution_receipt_path

    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = _preview_trace_ids(preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    idempotency_key = _alchemy_review_idempotency_key(scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-review",
        "applied_at": applied_at,
        "operation": "alchemy-review-enqueue",
        "action_id": action_id,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "title": f"Alchemy review enqueue {scope}",
        "status": "applied",
        "protocol": _first_preview_protocol(preview),
        "subject_kind": "alchemy_review_queue",
        "subject_id": f"review:{scope}",
        "apply_mode": "alchemy-review",
        "note": note or "",
        "primary_path": queue_result["path"],
        "secondary_path": "",
        "receipt_path": relative_path(root, receipt_path),
        "scope": scope,
        "primitive": "review",
        "candidate_ids": candidate_ids,
        "candidate_count": len(candidates),
        "idempotency_key": idempotency_key,
        "before_hash": queue_result["before_hash"],
        "after_hash": queue_result["after_hash"],
        "changed": queue_result["changed"],
        "revert_supported": False,
        "revert_policy": "non_revertible_derived_index: rerun compile or reapply a newer review preview to replace the managed section",
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
        "source_preview": _review_preview_receipt_summary(preview, candidates),
        "result_summary": queue_result,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "alchemy-review-enqueued",
            "recorded_at": applied_at,
            "status": "completed",
            "scope": scope,
            "candidate_count": len(candidates),
            "candidate_ids": candidate_ids,
            "review_queue_path": queue_result["path"],
            "receipt_path": relative_path(root, receipt_path),
            "trace_id": trace_id,
            "trace_ids": trace_ids,
            "subject_kind": "alchemy_review_queue",
            "subject_id": f"review:{scope}",
        },
    )
    return {
        "status": "applied",
        "primitive": "review",
        "scope": scope,
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "review_queue_path": queue_result["path"],
        "receipt_path": relative_path(root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": queue_result["changed"],
        "preview": preview,
    }


def run_alchemy_propose_preview(
    root: Path,
    *,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    from aiwiki.planner import preview_propose_primitive

    return preview_propose_primitive(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )


def run_alchemy_propose_apply(
    root: Path,
    *,
    scope: str,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
    limit: int = 50,
    note: str | None = None,
) -> dict[str, Any]:
    preview = run_alchemy_propose_preview(
        root,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
        limit=limit,
    )
    status = str(preview.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy propose apply requires an ok dry-run preview (got {status})")
    candidates = [item for item in preview.get("candidates", []) if isinstance(item, dict)]
    if not candidates:
        raise RuntimeError("alchemy propose apply requires a non-empty dry-run preview")

    from aiwiki.app_execution import append_execution_receipt_history
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.execution.l3_proposals import create_l3_proposal, load_l3_proposal_state
    from aiwiki.render.paths import execution_receipt_path

    ensure_layout(root)
    existing_ids = {
        str(item.get("proposal_id") or "")
        for item in load_l3_proposal_state(root).get("proposals", [])
        if isinstance(item, dict)
    }
    generated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    planner_log_ref = str(preview.get("planner_log_path") or "")

    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        proposal_id = slugify(f"alchemy-{candidate_id or 'propose'}")
        if proposal_id in existing_ids:
            skipped.append({"candidate_id": candidate_id, "proposal_id": proposal_id, "reason": "already_exists"})
            continue
        target_file = str(candidate.get("apply_target_file") or "prompts/ask.md")
        signal_ids = [str(item) for item in candidate.get("signal_ids", []) if isinstance(item, str) and item.strip()]
        evidence_refs = [f"{planner_log_ref}#{signal_id}" for signal_id in signal_ids if planner_log_ref]
        content = _alchemy_propose_prompt_content(root, target_file=target_file, candidate=candidate, scope=scope)
        result = create_l3_proposal(
            root,
            kind=str(candidate.get("apply_proposal_kind") or "prompt_proposal"),
            proposal_id=proposal_id,
            target_file=target_file,
            content=content,
            rationale=f"Generated from scoped alchemy propose preview candidate {candidate_id}. Manual accept is required.",
            evidence_refs=evidence_refs,
            signal_ids=signal_ids,
            pattern="failure_cluster",
        )
        result["candidate_id"] = candidate_id
        generated.append(result)
        existing_ids.add(proposal_id)

    applied_at = utc_now()
    action_id = _unique_alchemy_propose_action_id(root, applied_at=applied_at)
    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = _preview_trace_ids(preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    proposal_ids = [str(item.get("proposal_id") or "") for item in generated if item.get("proposal_id")]
    idempotency_key = _alchemy_propose_idempotency_key(scope=scope, candidate_ids=candidate_ids, trace_ids=trace_ids)
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-propose",
        "applied_at": applied_at,
        "operation": "alchemy-propose-generate",
        "action_id": action_id,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "title": f"Alchemy propose generate {scope}",
        "status": "applied",
        "protocol": _first_preview_protocol(preview),
        "subject_kind": "alchemy_proposal_plane",
        "subject_id": f"propose:{scope}",
        "apply_mode": "alchemy-propose",
        "note": note or "",
        "primary_path": "output/_proposals/prompt",
        "secondary_path": ".aiwiki/state/l3-proposals.json",
        "receipt_path": relative_path(root, receipt_path),
        "scope": scope,
        "primitive": "propose",
        "candidate_ids": candidate_ids,
        "candidate_count": len(candidates),
        "proposal_ids": proposal_ids,
        "generated_count": len(generated),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "idempotency_key": idempotency_key,
        "changed": bool(generated),
        "revert_supported": False,
        "revert_policy": "non_revertible_proposal_generation: reject generated L3 proposal candidates through review proposal workflow; target-file apply remains receipt-gated",
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
        "source_preview": _propose_preview_receipt_summary(preview, candidates),
        "result_summary": {"generated": generated, "skipped": skipped},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    append_runtime_history(
        root,
        {
            "event_type": "alchemy-propose-generated",
            "recorded_at": applied_at,
            "status": "completed",
            "scope": scope,
            "candidate_count": len(candidates),
            "candidate_ids": candidate_ids,
            "generated_count": len(generated),
            "proposal_ids": proposal_ids,
            "receipt_path": relative_path(root, receipt_path),
            "trace_id": trace_id,
            "trace_ids": trace_ids,
            "subject_kind": "alchemy_proposal_plane",
            "subject_id": f"propose:{scope}",
        },
    )
    return {
        "status": "applied",
        "primitive": "propose",
        "scope": scope,
        "candidate_count": len(candidates),
        "candidate_ids": candidate_ids,
        "generated_count": len(generated),
        "proposal_ids": proposal_ids,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "receipt_path": relative_path(root, receipt_path),
        "audit_path": audit_path,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "idempotency_key": idempotency_key,
        "changed": bool(generated),
        "preview": preview,
    }


def run_alchemy_lane_apply(
    root: Path,
    *,
    lane: str,
    scope: str,
    action_ids: list[str] | None = None,
    primitives: list[str] | None = None,
    note: str | None = None,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    from aiwiki.app_compile import apply_machine_memory_actions_batch
    from aiwiki.planner import preview_alchemy_lane

    normalized_action_ids = [item.strip() for item in (action_ids or []) if item.strip()]
    normalized_primitives = _normalize_lane_primitives(primitives or [])
    if not normalized_action_ids and not normalized_primitives:
        raise ValueError("alchemy lane --apply requires at least one --action-id or --primitive")

    plan = preview_alchemy_lane(
        root,
        lane=lane,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        decision_mode=decision_mode,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
    )
    status = str(plan.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy lane apply requires an ok dry-run plan (got {status})")
    if int(plan.get("selected_count") or 0) <= 0:
        raise RuntimeError("alchemy lane apply requires a non-empty dry-run plan")

    _append_alchemy_lane_runtime_event(
        root,
        event_type="alchemy-lane-started",
        lane=str(plan.get("lane") or lane),
        scope=str(plan.get("scope") or scope),
        action_ids=normalized_action_ids,
        primitives=normalized_primitives,
        plan=plan,
        status="started",
    )
    primitive_results = [
        _run_receipted_lane_primitive(
            root,
            lane=str(plan.get("lane") or lane),
            scope=str(plan.get("scope") or scope),
            primitive=primitive,
            plan=plan,
            note=note,
            planner_log_path=planner_log_path,
            signals_path=signals_path,
            decision_mode=decision_mode,
            max_signals=max_signals,
            max_pages=max_pages,
            max_tokens=max_tokens,
        )
        for primitive in normalized_primitives
    ]
    apply_result = None
    if normalized_action_ids:
        apply_result = apply_machine_memory_actions_batch(
            root,
            normalized_action_ids,
            note=note or f"alchemy {lane} apply for scope {scope}",
            dry_run=False,
        )
    _append_alchemy_lane_runtime_event(
        root,
        event_type="alchemy-lane-completed",
        lane=str(plan.get("lane") or lane),
        scope=str(plan.get("scope") or scope),
        action_ids=normalized_action_ids,
        primitives=normalized_primitives,
        plan=plan,
        status="completed",
        primitive_results=primitive_results,
        apply_result=apply_result,
    )
    return {
        "status": "applied",
        "lane": str(plan.get("lane") or lane),
        "scope": str(plan.get("scope") or scope),
        "action_ids": normalized_action_ids,
        "primitives": normalized_primitives,
        "plan": plan,
        "primitive_results": primitive_results,
        "apply_result": apply_result,
    }


def run_alchemy_auto(
    root: Path,
    *,
    apply: bool = False,
    lanes: list[str] | None = None,
    scope: str = "all",
    primitives: list[str] | None = None,
    note: str | None = None,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    normalized_lanes = _normalize_auto_lanes(lanes or ["heavy", "light"])
    requested_primitives = _normalize_lane_primitives(primitives or []) if primitives else []
    lane_results: list[dict[str, Any]] = []
    applied_results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for lane in normalized_lanes:
        plan = run_alchemy_lane_dry_run(
            root,
            lane=lane,
            scope=scope,
            planner_log_path=planner_log_path,
            signals_path=signals_path,
            decision_mode="execute",
            max_signals=max_signals,
            max_pages=max_pages,
            max_tokens=max_tokens,
        )
        selected_primitives = _auto_primitives_for_lane(lane, plan, requested_primitives=requested_primitives)
        lane_result: dict[str, Any] = {
            "lane": lane,
            "scope": scope,
            "plan": plan,
            "selected_primitives": selected_primitives,
        }
        skip_reason = _auto_skip_reason(plan, selected_primitives)
        if skip_reason:
            lane_result["status"] = "skipped"
            lane_result["reason"] = skip_reason
            skipped.append({"lane": lane, "reason": skip_reason})
        elif apply:
            apply_result = run_alchemy_lane_apply(
                root,
                lane=lane,
                scope=scope,
                primitives=selected_primitives,
                note=note or "alchemy auto scheduler",
                planner_log_path=planner_log_path,
                signals_path=signals_path,
                decision_mode="execute",
                max_signals=max_signals,
                max_pages=max_pages,
                max_tokens=max_tokens,
            )
            lane_result["status"] = "applied"
            lane_result["apply_result"] = apply_result
            applied_results.append(apply_result)
        else:
            lane_result["status"] = "ready"
        lane_results.append(lane_result)

    if apply:
        _append_alchemy_auto_runtime_event(
            root,
            scope=scope,
            lanes=normalized_lanes,
            primitives=requested_primitives,
            lane_results=lane_results,
            applied_results=applied_results,
            skipped=skipped,
        )

    return {
        "status": "applied" if apply and applied_results else ("noop" if apply else "preview"),
        "mode": "apply" if apply else "dry_run",
        "dry_run": not apply,
        "side_effects_allowed": apply,
        "scope": scope,
        "decision_mode": "execute",
        "lanes": normalized_lanes,
        "requested_primitives": requested_primitives,
        "applied_count": len(applied_results),
        "skipped_count": len(skipped),
        "lane_results": lane_results,
    }


def _normalize_auto_lanes(lanes: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in lanes:
        lane = item.strip().lower()
        if lane not in {"heavy", "light"}:
            raise ValueError(f"unsupported alchemy auto lane: {item}")
        if lane in seen:
            continue
        seen.add(lane)
        normalized.append(lane)
    if not normalized:
        raise ValueError("alchemy auto requires at least one lane")
    return normalized


def _auto_primitives_for_lane(
    lane: str,
    plan: dict[str, Any],
    *,
    requested_primitives: list[str],
) -> list[str]:
    defaults = {"heavy": ["compile", "lint"], "light": ["compile", "lint", "nightly"]}[lane]
    wanted = requested_primitives or defaults
    auto_supported_primitives = {"compile", "lint", "nightly"}
    if requested_primitives and lane == "heavy":
        auto_supported_primitives.add("distill")
        auto_supported_primitives.add("review")
        auto_supported_primitives.add("propose")
    supported = {
        str(item.get("primitive") or "")
        for item in plan.get("primitive_plan", [])
        if (
            isinstance(item, dict)
            and item.get("apply_supported") is True
            and str(item.get("primitive") or "") in auto_supported_primitives
        )
    }
    return [primitive for primitive in wanted if primitive in supported]


def _auto_skip_reason(plan: dict[str, Any], selected_primitives: list[str]) -> str:
    status = str(plan.get("status") or "")
    if status != "ok":
        return f"plan_{status or 'unknown'}"
    if int(plan.get("selected_count") or 0) <= 0:
        return "empty_execute_plan"
    if not selected_primitives:
        return "no_apply_supported_primitives"
    return ""


def _append_alchemy_auto_runtime_event(
    root: Path,
    *,
    scope: str,
    lanes: list[str],
    primitives: list[str],
    lane_results: list[dict[str, Any]],
    applied_results: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> None:
    trace_ids: set[str] = set()
    for lane_result in lane_results:
        plan = lane_result.get("plan")
        if not isinstance(plan, dict):
            continue
        trace_ids.update(_lane_receipt_trace_ids(plan))
    sorted_trace_ids = sorted(trace_ids)
    append_runtime_history(
        root,
        {
            "event_type": "alchemy-auto-scheduler",
            "recorded_at": utc_now(),
            "status": "completed",
            "scope": scope,
            "lanes": lanes,
            "requested_primitives": primitives,
            "applied_count": len(applied_results),
            "skipped_count": len(skipped),
            "skipped": skipped,
            "trace_id": sorted_trace_ids[0] if sorted_trace_ids else "",
            "trace_ids": sorted_trace_ids,
            "subject_kind": "alchemy_auto_scheduler",
            "subject_id": scope,
        },
    )


def _append_alchemy_lane_runtime_event(
    root: Path,
    *,
    event_type: str,
    lane: str,
    scope: str,
    action_ids: list[str],
    primitives: list[str],
    plan: dict[str, Any],
    status: str,
    primitive_results: list[dict[str, Any]] | None = None,
    apply_result: dict[str, Any] | None = None,
) -> None:
    trace_ids = _lane_receipt_trace_ids(plan)
    event: dict[str, Any] = {
        "event_type": event_type,
        "recorded_at": utc_now(),
        "status": status,
        "lane": lane,
        "scope": scope,
        "action_ids": action_ids,
        "primitives": primitives,
        "selected_count": int(plan.get("selected_count") or 0),
        "trace_id": trace_ids[0] if trace_ids else "",
        "trace_ids": trace_ids,
        "subject_kind": "alchemy_lane",
        "subject_id": f"{lane}:{scope}",
    }
    if primitive_results is not None:
        event["primitive_count"] = len(primitive_results)
        event["primitive_receipts"] = [
            str(item.get("receipt_path") or "") for item in primitive_results if isinstance(item, dict) and item.get("receipt_path")
        ]
    if apply_result is not None:
        event["action_batch_receipt"] = str(apply_result.get("receipt_path") or apply_result.get("batch_receipt_path") or "")
    append_runtime_history(root, event)


_ALCHEMY_REVIEW_QUEUE_START = "<!-- aiwiki:alchemy-review-enqueue:start -->"
_ALCHEMY_REVIEW_QUEUE_END = "<!-- aiwiki:alchemy-review-enqueue:end -->"
_ALCHEMY_JUDGE_REFRESH_START = "<!-- aiwiki:alchemy-judge-refresh:start -->"
_ALCHEMY_JUDGE_REFRESH_END = "<!-- aiwiki:alchemy-judge-refresh:end -->"
_ALCHEMY_JUDGE_PROPOSAL_START = "<!-- aiwiki:alchemy-judge-proposal:start -->"
_ALCHEMY_JUDGE_PROPOSAL_END = "<!-- aiwiki:alchemy-judge-proposal:end -->"
_ALCHEMY_JUDGE_ACCEPTED_REFRESH_START = "<!-- aiwiki:accepted-judge-refresh:start -->"
_ALCHEMY_JUDGE_ACCEPTED_REFRESH_END = "<!-- aiwiki:accepted-judge-refresh:end -->"
_ALCHEMY_JUDGE_ACCEPTED_TARGET_START = "<!-- aiwiki:alchemy-accepted-judge-refresh:start -->"
_ALCHEMY_JUDGE_ACCEPTED_TARGET_END = "<!-- aiwiki:alchemy-accepted-judge-refresh:end -->"


def _materialize_alchemy_judge_refresh(
    root: Path,
    *,
    preview: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    target_ref = str(candidate.get("target_ref") or "")
    candidate_id = str(candidate.get("candidate_id") or "")
    target = (root / target_ref).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return {"status": "skipped", "candidate_id": candidate_id, "target_ref": target_ref, "reason": "target_outside_root"}
    if not target.exists():
        return {"status": "skipped", "candidate_id": candidate_id, "target_ref": target_ref, "reason": "target_missing"}
    original = target.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(original)
    kind = str(frontmatter.get("kind") or "")
    if kind not in {"decision", "judgment"}:
        return {"status": "skipped", "candidate_id": candidate_id, "target_ref": target_ref, "reason": "not_judgment_asset"}
    before_hash = sha256_bytes(original.encode("utf-8"))
    body = strip_frontmatter(original).strip()
    section = _render_alchemy_judge_refresh_section(preview=preview, candidate=candidate)
    updated_body = _replace_marker_section(
        body,
        section,
        start_marker=_ALCHEMY_JUDGE_REFRESH_START,
        end_marker=_ALCHEMY_JUDGE_REFRESH_END,
    )
    updated = f"{render_frontmatter(frontmatter)}\n\n{updated_body.strip()}\n"
    changed = updated != original
    if changed:
        target.write_text(updated, encoding="utf-8")
    after_hash = sha256_bytes(updated.encode("utf-8"))
    return {
        "status": "refreshed",
        "candidate_id": candidate_id,
        "target_ref": target_ref,
        "path": relative_path(root, target),
        "kind": kind,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "changed": changed,
    }


def _render_alchemy_judge_refresh_section(*, preview: dict[str, Any], candidate: dict[str, Any]) -> str:
    lines = [
        _ALCHEMY_JUDGE_REFRESH_START,
        "## Alchemy Judge Refresh",
        "",
        f"- candidate_id: `{_markdown_cell(str(candidate.get('candidate_id') or ''))}`",
        f"- target_ref: `{_markdown_cell(str(candidate.get('target_ref') or ''))}`",
        f"- signal_ids: `{_markdown_cell(', '.join(_string_values(candidate.get('signal_ids'))) or 'none')}`",
        f"- trace_ids: `{_markdown_cell(', '.join(_string_values(candidate.get('trace_ids'))) or 'none')}`",
        f"- source_ids: `{_markdown_cell(', '.join(_string_values(candidate.get('source_ids'))) or 'none')}`",
        f"- concept_slugs: `{_markdown_cell(', '.join(_string_values(candidate.get('concept_slugs'))) or 'none')}`",
        "",
        "This marker records a scoped judge refresh opportunity. It does not rewrite the judgment conclusion.",
        _ALCHEMY_JUDGE_REFRESH_END,
        "",
    ]
    return "\n".join(lines)


def _materialize_alchemy_judge_proposal(
    root: Path,
    *,
    preview: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    target_ref = str(candidate.get("target_ref") or "")
    candidate_id = str(candidate.get("candidate_id") or "")
    proposal_id = slugify(f"alchemy-judge-proposal-{candidate_id or target_ref or 'candidate'}")
    proposal_path = root / "output" / "_proposals" / "judge" / f"{proposal_id}.md"
    target = (root / target_ref).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return {
            "status": "skipped",
            "candidate_id": candidate_id,
            "target_ref": target_ref,
            "proposal_id": proposal_id,
            "reason": "target_outside_root",
        }
    if not target.exists():
        return {
            "status": "skipped",
            "candidate_id": candidate_id,
            "target_ref": target_ref,
            "proposal_id": proposal_id,
            "reason": "target_missing",
        }
    original = target.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(original)
    kind = str(frontmatter.get("kind") or "")
    if kind not in {"decision", "judgment"}:
        return {
            "status": "skipped",
            "candidate_id": candidate_id,
            "target_ref": target_ref,
            "proposal_id": proposal_id,
            "reason": "not_judgment_asset",
        }
    before_hash = sha256_bytes(original.encode("utf-8"))
    if proposal_path.exists():
        return {
            "status": "skipped",
            "candidate_id": candidate_id,
            "target_ref": target_ref,
            "path": relative_path(root, proposal_path),
            "proposal_id": proposal_id,
            "before_hash": before_hash,
            "reason": "already_exists",
        }
    proposal = _render_alchemy_judge_proposal_page(
        root,
        preview=preview,
        candidate=candidate,
        target_ref=target_ref,
        proposal_id=proposal_id,
        target_kind=kind,
        before_hash=before_hash,
    )
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_path.write_text(proposal, encoding="utf-8")
    return {
        "status": "generated",
        "candidate_id": candidate_id,
        "target_ref": target_ref,
        "path": relative_path(root, proposal_path),
        "proposal_id": proposal_id,
        "kind": kind,
        "before_hash": before_hash,
        "changed": True,
        "llm_invoked": False,
        "semantic_content_generated": False,
    }


def _render_alchemy_judge_proposal_page(
    root: Path,
    *,
    preview: dict[str, Any],
    candidate: dict[str, Any],
    target_ref: str,
    proposal_id: str,
    target_kind: str,
    before_hash: str,
) -> str:
    trace_ids = _string_values(candidate.get("trace_ids"))
    signal_ids = _string_values(candidate.get("signal_ids"))
    frontmatter = {
        "kind": "alchemy-judge-proposal",
        "proposal_id": proposal_id,
        "state": "candidate",
        "target_file": target_ref,
        "target_kind": target_kind,
        "before_hash": before_hash,
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "created_at": utc_now(),
        "llm_invoked": "false",
        "semantic_content_generated": "false",
        "human_accept_required": "true",
    }
    lines = [
        render_frontmatter(frontmatter),
        "",
        f"# Judge Proposal: {proposal_id}",
        "",
        _ALCHEMY_JUDGE_PROPOSAL_START,
        "## Target",
        "",
        f"- target_file: `{_markdown_cell(target_ref)}`",
        f"- target_kind: `{_markdown_cell(target_kind)}`",
        f"- before_hash: `{_markdown_cell(before_hash)}`",
        "",
        "## Provenance",
        "",
        f"- candidate_id: `{_markdown_cell(str(candidate.get('candidate_id') or ''))}`",
        f"- signal_ids: `{_markdown_cell(', '.join(signal_ids) or 'none')}`",
        f"- trace_ids: `{_markdown_cell(', '.join(trace_ids) or 'none')}`",
        f"- source_ids: `{_markdown_cell(', '.join(_string_values(candidate.get('source_ids'))) or 'none')}`",
        f"- concept_slugs: `{_markdown_cell(', '.join(_string_values(candidate.get('concept_slugs'))) or 'none')}`",
        f"- scope: `{_markdown_cell(str(preview.get('scope') or ''))}`",
        "",
        "## Semantic Refresh Contract",
        "",
        "- llm_invoked: `false`",
        "- semantic_content_generated: `false`",
        "- human_accept_required: `true`",
        "- target_page_mutation: `false`",
        "- next_step: `fill this proposal through an explicit human/model contract, then apply in a separate accepted-proposal milestone`",
        "",
        "## Proposed Change Preview",
        "",
        "No judgment conclusion has been generated in this baseline. This artifact reserves a reviewable proposal slot and records the exact target hash that a future accepted semantic refresh must validate before applying.",
        "",
        "## Candidate Prompt Package",
        "",
        "```text",
        "Review the target judgment or decision page against the scoped evidence.",
        "Return a proposed semantic refresh as a separate proposal diff.",
        "Do not apply changes directly to the target page.",
        f"Target: {target_ref}",
        f"Before hash: {before_hash}",
        f"Signals: {', '.join(signal_ids) or 'none'}",
        f"Traces: {', '.join(trace_ids) or 'none'}",
        "```",
        _ALCHEMY_JUDGE_PROPOSAL_END,
        "",
    ]
    return "\n".join(lines)


def _replace_marker_section(existing: str, section: str, *, start_marker: str, end_marker: str) -> str:
    if start_marker in existing and end_marker in existing:
        before, rest = existing.split(start_marker, 1)
        _, after = rest.split(end_marker, 1)
        return before.rstrip() + "\n\n" + section + after.lstrip()
    if existing.strip():
        return existing.rstrip() + "\n\n" + section
    return section


def _extract_marker_section(existing: str, *, start_marker: str, end_marker: str) -> str:
    if start_marker not in existing or end_marker not in existing:
        return ""
    _, rest = existing.split(start_marker, 1)
    body, _ = rest.split(end_marker, 1)
    return body.strip()


def _render_alchemy_judge_accepted_target_section(*, proposal_id: str, proposal_path: str, accepted_body: str) -> str:
    lines = [
        _ALCHEMY_JUDGE_ACCEPTED_TARGET_START,
        "## Accepted Judge Refresh",
        "",
        f"- proposal_id: `{_markdown_cell(proposal_id)}`",
        f"- proposal_path: `{_markdown_cell(proposal_path)}`",
        "",
        accepted_body.strip(),
        _ALCHEMY_JUDGE_ACCEPTED_TARGET_END,
        "",
    ]
    return "\n".join(lines)


def _materialize_alchemy_review_queue(
    root: Path,
    *,
    preview: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    path = root / "wiki" / "indexes" / "review-queue.md"
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    before_hash = sha256_bytes(before.encode("utf-8")) if path.exists() else ""
    section = _render_alchemy_review_queue_section(preview=preview, candidates=candidates)
    after = _replace_managed_section(before, section)
    changed = after != before
    path.parent.mkdir(parents=True, exist_ok=True)
    if changed or not path.exists():
        path.write_text(after, encoding="utf-8")
    after_hash = sha256_bytes(after.encode("utf-8"))
    return {
        "path": relative_path(root, path),
        "before_hash": before_hash,
        "after_hash": after_hash,
        "changed": changed,
        "candidate_count": len(candidates),
    }


def _render_alchemy_review_queue_section(*, preview: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    scope = str(preview.get("scope") or "")
    trace_ids = _preview_trace_ids(preview)
    lines = [
        _ALCHEMY_REVIEW_QUEUE_START,
        "## Alchemy scoped review enqueue",
        "",
        f"- scope: `{_markdown_cell(scope)}`",
        f"- candidate_count: `{len(candidates)}`",
        f"- trace_ids: `{', '.join(trace_ids)}`",
        "",
        "| Candidate | Kind | Protocol | Target | Signals |",
        "| --- | --- | --- | --- | --- |",
    ]
    for candidate in candidates:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(str(candidate.get("candidate_id") or "")),
                    _markdown_cell(str(candidate.get("kind") or "")),
                    _markdown_cell(str(candidate.get("protocol") or "")),
                    _markdown_cell(str(candidate.get("target_ref") or "")),
                    _markdown_cell(", ".join(_string_values(candidate.get("signal_ids")))),
                ]
            )
            + " |"
        )
    lines.extend(["", _ALCHEMY_REVIEW_QUEUE_END, ""])
    return "\n".join(lines)


def _replace_managed_section(existing: str, section: str) -> str:
    if _ALCHEMY_REVIEW_QUEUE_START in existing and _ALCHEMY_REVIEW_QUEUE_END in existing:
        before, rest = existing.split(_ALCHEMY_REVIEW_QUEUE_START, 1)
        _, after = rest.split(_ALCHEMY_REVIEW_QUEUE_END, 1)
        return before.rstrip() + "\n\n" + section + after.lstrip()
    if existing.strip():
        return existing.rstrip() + "\n\n" + section
    return "# Review Queue\n\n" + section


def _review_preview_receipt_summary(preview: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": str(preview.get("status") or ""),
        "scope": str(preview.get("scope") or ""),
        "selected_count": int(preview.get("selected_count") or 0),
        "candidate_count": len(candidates),
        "candidate_ids": [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")],
        "scope_preview": preview.get("scope_preview") if isinstance(preview.get("scope_preview"), dict) else {},
        "apply_contract": preview.get("apply_contract") if isinstance(preview.get("apply_contract"), dict) else {},
    }


def _propose_preview_receipt_summary(preview: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": str(preview.get("status") or ""),
        "scope": str(preview.get("scope") or ""),
        "selected_count": int(preview.get("selected_count") or 0),
        "candidate_count": len(candidates),
        "candidate_ids": [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")],
        "scope_preview": preview.get("scope_preview") if isinstance(preview.get("scope_preview"), dict) else {},
        "apply_contract": preview.get("apply_contract") if isinstance(preview.get("apply_contract"), dict) else {},
        "human_accept_required_after_apply": True,
    }


def _distill_preview_receipt_summary(preview: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": str(preview.get("status") or ""),
        "scope": str(preview.get("scope") or ""),
        "selected_count": int(preview.get("selected_count") or 0),
        "candidate_count": len(candidates),
        "candidate_ids": [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")],
        "scope_preview": preview.get("scope_preview") if isinstance(preview.get("scope_preview"), dict) else {},
        "apply_contract": preview.get("apply_contract") if isinstance(preview.get("apply_contract"), dict) else {},
        "direct_apply_only": False,
        "lane_apply_supported": True,
    }


def _judge_preview_receipt_summary(preview: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": str(preview.get("status") or ""),
        "scope": str(preview.get("scope") or ""),
        "selected_count": int(preview.get("selected_count") or 0),
        "candidate_count": len(candidates),
        "candidate_ids": [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")],
        "scope_preview": preview.get("scope_preview") if isinstance(preview.get("scope_preview"), dict) else {},
        "apply_contract": preview.get("apply_contract") if isinstance(preview.get("apply_contract"), dict) else {},
        "semantic_rewrite": False,
        "lane_apply_supported": False,
    }


def _preview_trace_ids(preview: dict[str, Any]) -> list[str]:
    scope_preview = preview.get("scope_preview")
    if not isinstance(scope_preview, dict):
        return []
    return _string_values(scope_preview.get("trace_ids"))


def _first_preview_protocol(preview: dict[str, Any]) -> str:
    scope_preview = preview.get("scope_preview")
    if isinstance(scope_preview, dict):
        protocols = _string_values(scope_preview.get("protocols"))
        if protocols:
            return protocols[0]
    candidates = preview.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("protocol"):
                return str(candidate.get("protocol") or "")
    return ""


def _alchemy_review_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    payload = {
        "primitive": "review",
        "scope": scope,
        "candidate_ids": sorted(candidate_ids),
        "trace_ids": sorted(trace_ids),
    }
    digest = sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return f"alchemy-review:{digest}"


def _alchemy_propose_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    payload = {
        "primitive": "propose",
        "scope": scope,
        "candidate_ids": sorted(candidate_ids),
        "trace_ids": sorted(trace_ids),
    }
    digest = sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return f"alchemy-propose:{digest}"


def _alchemy_distill_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    payload = {
        "primitive": "distill",
        "scope": scope,
        "candidate_ids": sorted(candidate_ids),
        "question_template": "scoped_elixir_candidate_refresh",
        "trace_ids": sorted(trace_ids),
    }
    digest = sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return f"alchemy-distill:{digest}"


def _alchemy_judge_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    payload = {
        "primitive": "judge",
        "scope": scope,
        "candidate_ids": sorted(candidate_ids),
        "marker": "scoped_judge_refresh_marker",
        "trace_ids": sorted(trace_ids),
    }
    digest = sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return f"alchemy-judge:{digest}"


def _alchemy_judge_proposal_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    payload = {
        "primitive": "judge",
        "mode": "proposal_preview",
        "scope": scope,
        "candidate_ids": sorted(candidate_ids),
        "trace_ids": sorted(trace_ids),
    }
    digest = sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return f"alchemy-judge-proposal:{digest}"


def _resolve_alchemy_judge_proposal_path(root: Path, proposal: str | Path) -> Path:
    raw = str(proposal).strip().strip("'\"`")
    if not raw:
        raise ValueError("judge proposal path or id is required.")
    candidate = Path(raw)
    if not candidate.suffix and "/" not in raw and "\\" not in raw:
        candidate = Path("output") / "_proposals" / "judge" / f"{slugify(raw)}.md"
    resolved = candidate if candidate.is_absolute() else root / candidate
    resolved = resolved.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("judge proposal path must stay within the workspace.") from exc
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"judge proposal not found: {proposal}")
    return resolved


def _alchemy_distill_target_id(target_ref: str) -> str:
    normalized = target_ref.strip()
    if not normalized:
        return ""
    return Path(normalized).stem


def _alchemy_distill_question(candidate: dict[str, Any]) -> str:
    candidate_id = str(candidate.get("candidate_id") or "distill")
    target_ref = str(candidate.get("target_ref") or "")
    signal_ids = ",".join(_string_values(candidate.get("signal_ids"))) or "none"
    return f"Alchemy scoped distill refresh for {candidate_id} ({target_ref}); signals={signal_ids}"


def _alchemy_distill_history_questions(path: Path) -> set[str]:
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    raw = frontmatter.get("distill_history_json")
    if not isinstance(raw, str) or not raw.strip():
        return set()
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(decoded, list):
        return set()
    questions: set[str] = set()
    for item in decoded:
        if isinstance(item, dict) and isinstance(item.get("question"), str):
            questions.add(str(item["question"]))
    return questions


def _alchemy_propose_prompt_content(root: Path, *, target_file: str, candidate: dict[str, Any], scope: str) -> str:
    target = root / target_file
    current = target.read_text(encoding="utf-8", errors="replace")
    signal_ids = ", ".join(_string_values(candidate.get("signal_ids"))) or "none"
    candidate_id = str(candidate.get("candidate_id") or "")
    target_ref = str(candidate.get("target_ref") or "")
    block = "\n".join(
        [
            "",
            "<!-- aiwiki:alchemy-propose:start -->",
            f"<!-- scope: {scope} -->",
            f"<!-- candidate_id: {candidate_id} -->",
            f"<!-- target_ref: {target_ref} -->",
            f"<!-- signal_ids: {signal_ids} -->",
            "<!-- Manual review is required before accepting this proposal. -->",
            "<!-- aiwiki:alchemy-propose:end -->",
        ]
    )
    return current.rstrip() + block + "\n"


def _unique_alchemy_propose_action_id(root: Path, *, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-propose-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _unique_alchemy_distill_action_id(root: Path, *, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-distill-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _unique_alchemy_judge_action_id(root: Path, *, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-judge-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _unique_alchemy_judge_proposal_action_id(root: Path, *, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-judge-proposal-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _unique_alchemy_judge_proposal_apply_action_id(root: Path, *, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-judge-proposal-apply-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _unique_alchemy_review_action_id(root: Path, *, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-review-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _string_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item.strip() for item in value if isinstance(item, str) and item.strip()})


def _markdown_cell(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|")


def _normalize_lane_primitives(primitives: list[str]) -> list[str]:
    allowed = {"compile", "distill", "lint", "nightly", "review", "propose"}
    normalized: list[str] = []
    seen: set[str] = set()
    for item in primitives:
        primitive = item.strip().lower()
        if not primitive:
            continue
        if primitive not in allowed:
            raise ValueError(f"unsupported alchemy lane primitive: {item}")
        if primitive in seen:
            continue
        seen.add(primitive)
        normalized.append(primitive)
    return normalized


def _run_receipted_lane_primitive(
    root: Path,
    *,
    lane: str,
    scope: str,
    primitive: str,
    plan: dict[str, Any],
    note: str | None,
    planner_log_path: Path | None = None,
    signals_path: Path | None = None,
    decision_mode: str | None = None,
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    plan_step = _lane_primitive_plan_step(plan, primitive)
    if plan_step is None:
        raise RuntimeError(f"primitive {primitive!r} is not present in the dry-run plan for lane {lane!r}")
    if plan_step.get("apply_supported") is not True:
        blocker = str(plan_step.get("apply_blocker") or "not_apply_supported")
        raise RuntimeError(f"primitive {primitive!r} is not apply-supported in the dry-run plan for lane {lane!r}: {blocker}")

    if primitive == "review":
        result = run_alchemy_review_apply(
            root,
            scope=scope,
            planner_log_path=planner_log_path,
            signals_path=signals_path,
            decision_mode=decision_mode,
            max_signals=max_signals,
            max_pages=max_pages,
            max_tokens=max_tokens,
            note=note,
        )
        return {
            "primitive": primitive,
            "trace_id": str(result.get("trace_id") or ""),
            "audit_path": str(result.get("audit_path") or ""),
            "receipt_path": str(result.get("receipt_path") or ""),
            "result": result,
        }
    if primitive == "distill":
        result = run_alchemy_distill_apply(
            root,
            scope=scope,
            planner_log_path=planner_log_path,
            signals_path=signals_path,
            decision_mode=decision_mode,
            max_signals=max_signals,
            max_pages=max_pages,
            max_tokens=max_tokens,
            note=note,
        )
        return {
            "primitive": primitive,
            "trace_id": str(result.get("trace_id") or ""),
            "audit_path": str(result.get("audit_path") or ""),
            "receipt_path": str(result.get("receipt_path") or ""),
            "result": result,
        }
    if primitive == "propose":
        result = run_alchemy_propose_apply(
            root,
            scope=scope,
            planner_log_path=planner_log_path,
            signals_path=signals_path,
            decision_mode=decision_mode,
            max_signals=max_signals,
            max_pages=max_pages,
            max_tokens=max_tokens,
            note=note,
        )
        return {
            "primitive": primitive,
            "trace_id": str(result.get("trace_id") or ""),
            "audit_path": str(result.get("audit_path") or ""),
            "receipt_path": str(result.get("receipt_path") or ""),
            "result": result,
        }
    if primitive == "compile":
        result = compile_wiki(root)
    elif primitive == "lint":
        result = lint_wiki(root)
    elif primitive == "nightly":
        result = nightly_health(root)
    else:  # pragma: no cover - guarded by _normalize_lane_primitives
        raise ValueError(f"unsupported alchemy lane primitive: {primitive}")

    applied_at = utc_now()
    action_id = _unique_lane_primitive_action_id(root, lane=lane, primitive=primitive, applied_at=applied_at)
    from aiwiki.app_execution import append_execution_receipt_history
    from aiwiki.app_state import execution_receipt_history_path
    from aiwiki.render.paths import execution_receipt_path

    receipt_path = execution_receipt_path(root, action_id)
    audit_path = relative_path(root, execution_receipt_history_path(root))
    trace_ids = _lane_receipt_trace_ids(plan)
    trace_id = trace_ids[0] if trace_ids else ""
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-lane",
        "applied_at": applied_at,
        "operation": "alchemy-lane-primitive",
        "action_id": action_id,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "title": f"Alchemy {lane} {primitive}",
        "status": "applied",
        "protocol": _first_plan_protocol(plan),
        "subject_kind": "alchemy_lane_primitive",
        "subject_id": f"{lane}:{scope}:{primitive}",
        "apply_mode": f"alchemy-{lane}-{primitive}",
        "note": note or "",
        "primary_path": _primary_result_path(result),
        "secondary_path": "",
        "receipt_path": relative_path(root, receipt_path),
        "lane": lane,
        "scope": scope,
        "primitive": primitive,
        "revert_supported": False,
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
        "source_plan": _lane_receipt_plan_summary(plan),
        "result_summary": _lane_receipt_result_summary(result),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    return {
        "primitive": primitive,
        "trace_id": trace_id,
        "audit_path": audit_path,
        "receipt_path": relative_path(root, receipt_path),
        "result": result,
    }


def _unique_lane_primitive_action_id(root: Path, *, lane: str, primitive: str, applied_at: str) -> str:
    from aiwiki.render.paths import execution_receipt_path

    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"alchemy-{lane}-{primitive}-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _lane_primitive_plan_step(plan: dict[str, Any], primitive: str) -> dict[str, Any] | None:
    for item in plan.get("primitive_plan", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("primitive") or "") == primitive:
            return item
    return None


def _first_plan_protocol(plan: dict[str, Any]) -> str:
    scope_preview = plan.get("scope_preview")
    if isinstance(scope_preview, dict):
        protocols = scope_preview.get("protocols")
        if isinstance(protocols, list) and protocols:
            return str(protocols[0])
    return ""


def _lane_receipt_trace_ids(plan: dict[str, Any]) -> list[str]:
    scope_preview = plan.get("scope_preview")
    if not isinstance(scope_preview, dict):
        return []
    trace_ids = scope_preview.get("trace_ids")
    if not isinstance(trace_ids, list):
        return []
    normalized = sorted({item.strip() for item in trace_ids if isinstance(item, str) and item.strip()})
    return normalized


def _primary_result_path(result: dict[str, Any]) -> str:
    for key in ("state_path", "path", "semantic_report"):
        value = result.get(key)
        if isinstance(value, str) and value:
            return value
    repair_backlog = result.get("repair_backlog")
    if isinstance(repair_backlog, str) and repair_backlog:
        return repair_backlog
    return ""


def _lane_receipt_plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane": str(plan.get("lane") or ""),
        "scope": str(plan.get("scope") or ""),
        "selected_count": int(plan.get("selected_count") or 0),
        "scope_preview": plan.get("scope_preview") if isinstance(plan.get("scope_preview"), dict) else {},
        "primitive_plan": list(plan.get("primitive_plan") or []),
    }


def _lane_receipt_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("state_path", "repair_backlog", "semantic_report", "llm_used"):
        if key in result:
            summary[key] = result[key]
    if "updated_source_pages" in result:
        summary["updated_source_pages_count"] = len(result.get("updated_source_pages") or [])
    if "updated_concept_pages" in result:
        summary["updated_concept_pages_count"] = len(result.get("updated_concept_pages") or [])
    if "counts" in result and isinstance(result.get("counts"), dict):
        summary["counts"] = result["counts"]
    return summary


@runtime_write_operation
def run_protocol_learn_age(root: Path, protocol: str | None = None, apply: bool = False) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import age_learnings

    return age_learnings(root, protocol=protocol, apply=apply)


@runtime_write_operation
def run_protocol_learn_verify(root: Path, learning_id: str) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import verify_learning

    return verify_learning(root, learning_id)


@runtime_write_operation
def run_protocol_learn_revert_activate(root: Path, learning_id: str, *, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import revert_learning_activation

    return revert_learning_activation(root, learning_id, note=note)


@runtime_write_operation
def run_protocol_learn_demote(root: Path, learning_id: str) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import demote_learning

    return demote_learning(root, learning_id)


@runtime_write_operation
def run_protocol_learn_archive(root: Path, learning_id: str) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import archive_learning

    return archive_learning(root, learning_id)


@runtime_write_operation
def run_protocol_learn_supersede(root: Path, replacement_id: str, superseded_ids: list[str]) -> dict[str, Any]:
    from aiwiki.execution.protocol_learnings import supersede_learning

    return supersede_learning(root, replacement_id, superseded_ids)


def watch_inbox(
    root: Path,
    interval_seconds: float = 5.0,
    client: SupportsComplete | None = None,
    compile_limit: int = 5,
    deterministic_only: bool = False,
    semantic_lint: bool = True,
    process_initial: bool = True,
    max_cycles: int | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    processed_runs: list[dict[str, Any]] = []
    cycles = 0
    last_snapshot = inbox_snapshot(root)

    if process_initial:
        processed_runs.append(
            auto_process_once(
                root,
                client=client,
                compile_limit=compile_limit,
                deterministic_only=deterministic_only,
                semantic_lint=semantic_lint,
            )
        )
        last_snapshot = inbox_snapshot(root)

    while max_cycles is None or cycles < max_cycles:
        time.sleep(interval_seconds)
        cycles += 1
        current_snapshot = inbox_snapshot(root)
        if current_snapshot["digest"] == last_snapshot["digest"]:
            continue
        processed_runs.append(
            auto_process_once(
                root,
                client=client,
                compile_limit=compile_limit,
                deterministic_only=deterministic_only,
                semantic_lint=semantic_lint,
            )
        )
        last_snapshot = inbox_snapshot(root)

    return {
        "watch_cycles": cycles,
        "processed_runs": len(processed_runs),
        "last_result": processed_runs[-1] if processed_runs else None,
    }


def inbox_snapshot(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    files: list[dict[str, Any]] = []
    for path in sorted((root / "raw" / "inbox").glob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        files.append(
            {
                "path": relative_path(root, path),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    digest = sha256_bytes(json.dumps(files, sort_keys=True).encode("utf-8"))
    return {"digest": digest, "files": files}


def _pending_summary_count(root: Path) -> int:
    manifest = load_manifest(root)
    pending = 0
    for entry in manifest["entries"]:
        page = root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
            continue
        content = page.read_text(encoding="utf-8", errors="replace")
        if "Pending LLM summary." in content:
            pending += 1
    return pending


def _write_automation_state(root: Path, result: dict[str, Any]) -> None:
    ensure_layout(root)
    path = root / ".aiwiki" / "state" / "automation.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
