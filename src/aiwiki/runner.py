"""LLM-backed execution helpers for compile, ask, and lint workflows."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .app_compile import (
    ask_question,
    compile_wiki,
    lint_wiki,
    nightly_health,
    promote_recurring_outputs,
    write_nightly_health,
)
from .app_content import (
    concept_summary_is_placeholder,
    placeholder_concept_slugs,
    preserved_section,
)
from .app_memory import store_concept_rewrite_candidate
from .app_protocol import CONCEPT_HARDNESS_LEVELS, ensure_layout, load_protocol_state
from .app_shell import rewrite_recovery_payload_for_paths
from .app_state import load_machine_memory, load_manifest
from .app_utils import (
    TEXT_EXTENSIONS,
    parse_frontmatter,
    read_text_preview,
    relative_path,
    render_scalar,
    runtime_write_lock,
    runtime_write_operation,
    sha256_bytes,
    slugify,
    utc_now,
)
from .config import LLMConfig
from .llm import (
    CompletionResult,
    LLMError,
    advance_client_model,
    classify_backend_error,
    create_backend_client,
    probe_available_backends,
    probe_backend,
)

RUN_ASK_FRONTDOOR_EVENT = "run-ask-frontdoor"
RUN_ASK_FALLBACK_ERROR_KINDS = {"quota", "timeout", "auth", "unavailable"}

ASK_INDEX_PAGES_BASE = (
    "wiki/indexes/index.md",
    "wiki/indexes/sources.md",
    "wiki/indexes/concepts.md",
    "wiki/indexes/concept-quality.md",
    "wiki/indexes/machine-memory.md",
    "wiki/indexes/log.md",
    "schema/index.md",
    "schema/protocols/index.md",
)
ASK_INDEX_PAGES_BY_FORMAT = {
    "decision-memo": ("wiki/indexes/decisions.md", "wiki/indexes/judgments.md"),
    "sop": ("wiki/indexes/decisions.md", "wiki/indexes/judgments.md"),
    "report": (),
    "slides": (),
    "figure": (),
}
ASK_PROTOCOL_PAGE_NAMES_BASE = ("index.md", "taxonomy.md", "query.md")
ASK_PROTOCOL_PAGE_NAMES_BY_FORMAT = {
    "decision-memo": ("decision.md", "judgment.md"),
    "sop": ("decision.md",),
    "report": (),
    "slides": (),
    "figure": (),
}
ASK_PROMPT_PROFILES = {
    "balanced": {
        "max_total_chars": 48000,
        "index_page_chars": 2200,
        "log_page_chars": 1800,
        "protocol_page_chars": 1600,
        "concept_page_chars": 2200,
        "source_page_chars": 2800,
        "max_index_pages": 8,
        "max_protocol_pages": 4,
        "max_concepts": 4,
        "max_sources": 5,
    },
    "lean": {
        "max_total_chars": 30000,
        "index_page_chars": 1400,
        "log_page_chars": 1200,
        "protocol_page_chars": 1200,
        "concept_page_chars": 1600,
        "source_page_chars": 2200,
        "max_index_pages": 5,
        "max_protocol_pages": 3,
        "max_concepts": 3,
        "max_sources": 4,
    },
}
COMPILE_PROMPT_PROFILES = {
    "balanced": {
        "max_total_chars": 24000,
        "current_page_chars": 3200,
        "raw_excerpt_chars": 4200,
        "schema_page_chars": 1600,
        "protocol_page_chars": 1400,
        "source_page_chars": 2200,
        "related_concept_chars": 1600,
        "max_source_pages": 3,
        "max_related_concepts": 3,
        "max_quality_signals": 4,
    },
}
LINT_PROMPT_PROFILES = {
    "balanced": {
        "max_total_chars": 24000,
        "deterministic_report_chars": 3200,
        "schema_page_chars": 1300,
        "protocol_page_chars": 1100,
        "index_page_chars": 1400,
        "log_page_chars": 1100,
        "wiki_page_chars": 1400,
        "max_index_pages": 8,
        "max_wiki_pages": 5,
    },
}


class SupportsComplete(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        ...


def llm_status() -> dict[str, Any]:
    return LLMConfig.status_from_env()


def llm_probe(root: Path, probe_all: bool = False, timeout_seconds: int = 20) -> dict[str, Any]:
    status = llm_status()
    result = dict(status)
    result["probe_timeout_seconds"] = timeout_seconds
    if not status.get("configured"):
        result["probe"] = None
        result["probes"] = []
        return result
    config = LLMConfig.from_env()
    if probe_all:
        probes = probe_available_backends(config, root, timeout_seconds=timeout_seconds)
        result["probes"] = probes
        result["probe"] = next((probe for probe in probes if probe.get("backend") == config.backend), probes[0] if probes else None)
        return result
    result["probe"] = probe_backend(config, root, timeout_seconds=timeout_seconds)
    result["probes"] = []
    return result


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
    from .execution.l3_proposals import create_l3_proposal

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
    from .execution.l3_proposals import list_l3_proposals

    return list_l3_proposals(root, kind=kind, state=state)


def run_l3_proposal_generation_preview(
    root: Path,
    *,
    planner_log_path: Path | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    from .execution.l3_proposals import preview_l3_proposal_generation

    return preview_l3_proposal_generation(root, planner_log_path=planner_log_path, limit=limit)


def run_l3_proposal_apply(root: Path, proposal_id: str, *, note: str | None = None) -> dict[str, Any]:
    from .execution.l3_proposals import apply_l3_proposal

    return apply_l3_proposal(root, proposal_id, note=note)


def run_l3_proposal_reject(root: Path, proposal_id: str, *, note: str | None = None) -> dict[str, Any]:
    from .execution.l3_proposals import reject_l3_proposal

    return reject_l3_proposal(root, proposal_id, note=note)


def run_l3_proposal_revert(root: Path, receipt_id: str, *, note: str | None = None) -> dict[str, Any]:
    from .execution.l3_proposals import revert_l3_proposal

    return revert_l3_proposal(root, receipt_id, note=note)


def run_alchemy_legacy_migration_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from .execution.alchemy import preview_legacy_elixir_migration

    return preview_legacy_elixir_migration(root, limit=limit)


def run_audit_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from .execution.audit_preview import preview_universal_audit_stream

    return preview_universal_audit_stream(root, limit=limit)


def run_audit_backfill(root: Path, *, limit: int = 50, apply: bool = False) -> dict[str, Any]:
    from .execution.audit_preview import backfill_universal_audit_stream

    return backfill_universal_audit_stream(root, limit=limit, apply=apply)


def run_planner_log_rollback_preview(
    root: Path,
    *,
    signal_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    from .planner.rollback import preview_planner_log_rollback

    return preview_planner_log_rollback(root, signal_id=signal_id, trace_id=trace_id, limit=limit)


def create_client(root: Path, timeout_seconds: int | None = None) -> SupportsComplete:
    config = LLMConfig.from_env()
    if timeout_seconds is not None:
        config = replace(config, timeout_seconds=timeout_seconds)
    return create_backend_client(config, root)


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
    from .execution.candidates import write_candidate_frontmatter

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
        from .execution.ask import load_previous_output_summary

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
    from .execution.candidates import promote_candidate

    return promote_candidate(root, artifact_ref)


@runtime_write_operation
def run_demote(root: Path, artifact_ref: str) -> dict[str, Any]:
    from .execution.candidates import demote_candidate

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
            from .execution.protocol_learnings import age_learnings

            protocol_learnings_age = age_learnings(root, apply=True, emitted_by="nightly")
        except Exception as age_exc:  # noqa: BLE001 - aging must not break nightly
            from .execution.protocol_learnings import AUDIT_STATE_PATH as _AUDIT_PATH
            from .execution.protocol_learnings import _atomic_write_text as _age_atomic_write

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
    from .execution.alchemy import start_elixir

    return start_elixir(root, corpus_id, protocol=protocol, topic=topic, include_elixir_ids=include_elixir_ids)


@runtime_write_operation
def run_alchemy_distill(root: Path, elixir_id: str, question: str, include_elixir_ids: list[str] | None = None) -> dict[str, Any]:
    from .execution.alchemy import distill_elixir

    return distill_elixir(root, elixir_id, question=question, include_elixir_ids=include_elixir_ids)


@runtime_write_operation
def run_alchemy_finalize(root: Path, *, elixir_id: str) -> dict[str, Any]:
    from .execution.alchemy import finalize_elixir

    return finalize_elixir(root, elixir_id=elixir_id)


@runtime_write_operation
def run_alchemy_promote(root: Path, *, elixir_id: str, note: str | None = None) -> dict[str, Any]:
    from .execution.alchemy import promote_elixir

    return promote_elixir(root, elixir_id=elixir_id, note=note)


def run_alchemy_revert(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    from .execution.alchemy import revert_elixir

    with runtime_write_lock(root):
        return revert_elixir(root, elixir_id=elixir_id, note=note)


def run_alchemy_demote(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    from .execution.alchemy import demote_elixir

    with runtime_write_lock(root):
        return demote_elixir(root, elixir_id=elixir_id, note=note)


@runtime_write_operation
def run_protocol_learn_add(root: Path, protocol: str, title: str, source_refs: list[str] | None) -> dict[str, Any]:
    from .execution.protocol_learnings import add_learning

    return add_learning(root, protocol, title=title, source_refs=source_refs)


def run_protocol_learn_list(
    root: Path,
    protocol: str | None = None,
    *,
    state_filter: str | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    from .execution.protocol_learnings import list_learnings

    return list_learnings(root, protocol, state_filter=state_filter, include_archived=include_archived)


def run_protocol_learn_show(root: Path, learning_id: str) -> dict[str, Any]:
    from .execution.protocol_learnings import show_learning

    return show_learning(root, learning_id)


def run_signals_list(
    root: Path,
    *,
    kind: str | None = None,
    trace_id: str | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from .inspection import read_signals

    return read_signals(
        root,
        kind=kind,
        trace_id=trace_id,
        since=since,
        limit=limit,
    )


def run_signals_show(root: Path, signal_id: str) -> dict[str, Any]:
    from .inspection import find_planner_decisions_for_signal, find_signal_by_id

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
    from .inspection import read_planner_decisions

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
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    from .planner import preview_alchemy_lane

    return preview_alchemy_lane(
        root,
        lane=lane,
        scope=scope,
        planner_log_path=planner_log_path,
        signals_path=signals_path,
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
    )


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
    max_signals: int | None = None,
    max_pages: int | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    from .app_compile import apply_machine_memory_actions_batch
    from .planner import preview_alchemy_lane

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
        max_signals=max_signals,
        max_pages=max_pages,
        max_tokens=max_tokens,
    )
    status = str(plan.get("status") or "")
    if status != "ok":
        raise RuntimeError(f"alchemy lane apply requires an ok dry-run plan (got {status})")
    if int(plan.get("selected_count") or 0) <= 0:
        raise RuntimeError("alchemy lane apply requires a non-empty dry-run plan")

    primitive_results = [
        _run_receipted_lane_primitive(
            root,
            lane=str(plan.get("lane") or lane),
            scope=str(plan.get("scope") or scope),
            primitive=primitive,
            plan=plan,
            note=note,
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


def _normalize_lane_primitives(primitives: list[str]) -> list[str]:
    allowed = {"compile", "lint", "nightly"}
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
) -> dict[str, Any]:
    plan_step = _lane_primitive_plan_step(plan, primitive)
    if plan_step is None:
        raise RuntimeError(f"primitive {primitive!r} is not present in the dry-run plan for lane {lane!r}")
    if plan_step.get("apply_supported") is not True:
        blocker = str(plan_step.get("apply_blocker") or "not_apply_supported")
        raise RuntimeError(f"primitive {primitive!r} is not apply-supported in the dry-run plan for lane {lane!r}: {blocker}")

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
    from .app_execution import append_execution_receipt_history
    from .app_state import execution_receipt_history_path
    from .render.paths import execution_receipt_path

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
    from .render.paths import execution_receipt_path

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
    from .execution.protocol_learnings import age_learnings

    return age_learnings(root, protocol=protocol, apply=apply)


@runtime_write_operation
def run_protocol_learn_verify(root: Path, learning_id: str) -> dict[str, Any]:
    from .execution.protocol_learnings import verify_learning

    return verify_learning(root, learning_id)


@runtime_write_operation
def run_protocol_learn_demote(root: Path, learning_id: str) -> dict[str, Any]:
    from .execution.protocol_learnings import demote_learning

    return demote_learning(root, learning_id)


@runtime_write_operation
def run_protocol_learn_archive(root: Path, learning_id: str) -> dict[str, Any]:
    from .execution.protocol_learnings import archive_learning

    return archive_learning(root, learning_id)


@runtime_write_operation
def run_protocol_learn_supersede(root: Path, replacement_id: str, superseded_ids: list[str]) -> dict[str, Any]:
    from .execution.protocol_learnings import supersede_learning

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


def _system_prompt(kind: str) -> str:
    if kind == "compile":
        return (
            "You maintain a local-first research wiki. "
            "Return only the full replacement markdown document for the target file. "
            "Do not wrap the answer in code fences."
        )
    if kind == "ask":
        return (
            "You answer research questions by editing markdown artifacts in place. "
            "Return only the full replacement artifact, grounded in the provided source pages."
        )
    return (
        "You review a research wiki for semantic issues. "
        "Return only the markdown report requested by the user prompt."
    )


def _build_compile_prompt(
    root: Path,
    entry: dict[str, Any],
    raw_path: Path,
    current_page: str,
    prompt_profile: str = "balanced",
) -> str:
    template = _load_prompt(root, "compile.md")
    profile = _compile_prompt_profile(prompt_profile)
    raw_excerpt = _read_context(raw_path, max_chars=profile["raw_excerpt_chars"])
    target_relative = relative_path(root, root / "wiki" / "sources" / f"{entry['id']}.md")
    note_kind = str(entry.get("note_kind") or "")
    note_kind_lines: list[str] = []
    if note_kind:
        note_kind_lines.append(f"- Material kind: `{note_kind}`.")
        if note_kind == "transcript":
            note_kind_lines.append(
                "- This raw source is a transcript. Preserve chronology, speaker attributions, decisions, action items, and unresolved questions."
            )
        elif note_kind == "note":
            note_kind_lines.append(
                "- This raw source is an operator note. Separate observed facts, interpretations, decisions, and open questions."
            )
    return "\n\n".join(
        [
            template,
            "## Target",
            f"- Replace file: `{target_relative}`",
            f"- Source file: `{entry['stored_path']}`",
            "",
            "## Hard Constraints",
            f"- Preserve frontmatter `id: {entry['id']}`.",
            "- Preserve `kind: source`.",
            f"- Preserve `source_files: [\"{entry['stored_path']}\"]`.",
            f"- Preserve `source_sha256: {entry['sha256']}`.",
            *note_kind_lines,
            "- Keep the `Source Record` section and update the `Summary` section with grounded prose.",
            "- If evidence is weak or truncated, say so explicitly.",
            "",
            "## Runtime Schema",
            _schema_context(root, ("index.md", "citations.md", "conflicts.md"), max_chars=profile["schema_page_chars"]),
            "",
            "## Active Protocol",
            _protocol_context(
                root,
                ("index.md", "taxonomy.md", "query.md"),
                max_chars=profile["protocol_page_chars"],
            ),
            "",
            "## Current Page",
            _fit_prompt_section(current_page, max_chars=profile["current_page_chars"]),
            "",
            "## Raw Source Excerpt",
            raw_excerpt,
        ]
    )


def _build_concept_compile_prompt(
    root: Path,
    target: Path,
    current_page: str,
    source_pages: list[str],
    related_slugs: list[str],
    quality_record: dict[str, Any] | None = None,
    prompt_profile: str = "balanced",
) -> str:
    template = _load_prompt(root, "compile.md")
    profile = _compile_prompt_profile(prompt_profile)
    source_sections: list[str] = []
    for relative in source_pages[: profile["max_source_pages"]]:
        page = root / relative
        if not page.exists():
            continue
        source_sections.extend(
            [
                f"### {relative}",
                _fit_prompt_section(
                    page.read_text(encoding="utf-8", errors="replace"),
                    max_chars=profile["source_page_chars"],
                ),
                "",
            ]
        )
    omitted_source_pages = max(0, len(source_pages) - profile["max_source_pages"])
    if omitted_source_pages:
        source_sections.append(f"- Omitted `{omitted_source_pages}` additional source page(s) for prompt profile `{prompt_profile}`.")
    related_sections: list[str] = []
    for slug in related_slugs[: profile["max_related_concepts"]]:
        page = root / "wiki" / "concepts" / f"{slug}.md"
        if not page.exists():
            continue
        related_sections.extend(
            [
                f"### wiki/concepts/{slug}.md",
                _fit_prompt_section(
                    page.read_text(encoding="utf-8", errors="replace"),
                    max_chars=profile["related_concept_chars"],
                ),
                "",
            ]
        )
    omitted_related = max(0, len(related_slugs) - profile["max_related_concepts"])
    if omitted_related:
        related_sections.append(f"- Omitted `{omitted_related}` additional related concept(s) for prompt profile `{prompt_profile}`.")
    frontmatter = parse_frontmatter(current_page)
    quality_lines = [
        f"- Rewrite priority: `{quality_record.get('priority', 'n/a')}`",
        f"- Issues: `{', '.join(quality_record.get('issues', [])) or 'none'}`",
        f"- Strategy: {quality_record.get('rewrite_strategy', 'Keep the concept grounded and explicit.')}",
    ] if quality_record else ["- No extra concept-quality signal was attached."]
    if quality_record and quality_record.get("conflict_signals"):
        for signal in quality_record.get("conflict_signals", [])[: profile["max_quality_signals"]]:
            quality_lines.append(
                f"- Conflict `{signal.get('label', 'n/a')}` from `{', '.join(signal.get('source_pages', [])) or 'none'}`"
            )
    if quality_record and quality_record.get("gap_signals"):
        for gap in quality_record.get("gap_signals", [])[: profile["max_quality_signals"]]:
            quality_lines.append(
                f"- Gap `{gap.get('kind', 'n/a')}` on `{gap.get('path', 'n/a')}`"
                f" with markers `{', '.join(gap.get('markers', [])) or 'none'}`"
            )
    return "\n\n".join(
        [
            template,
            "## Target",
            f"- Replace file: `{relative_path(root, target)}`",
            "",
            "## Hard Constraints",
            f"- Preserve frontmatter `id: concept-{target.stem}`.",
            "- Preserve `kind: concept`.",
            f"- Preserve `source_signature: {frontmatter.get('source_signature', '')}`.",
            f"- Preserve `source_pages: {json.dumps(source_pages)}`.",
            "- Keep explicit frontmatter `hardness: soft|medium|hard`; only upgrade it when the synthesis is grounded across the cited source pages.",
            "- Replace the fallback concept summary with grounded synthesis across the listed source pages.",
            "- Keep contradictions, weak evidence, and unresolved gaps explicit.",
            "- Preserve or improve explicit citations to `wiki/sources/*.md` when useful.",
            "",
            "## Runtime Schema",
            _schema_context(
                root,
                ("index.md", "citations.md", "conflicts.md", "taxonomy.md"),
                max_chars=profile["schema_page_chars"],
            ),
            "",
            "## Active Protocol",
            _protocol_context(
                root,
                ("index.md", "taxonomy.md", "query.md"),
                max_chars=profile["protocol_page_chars"],
            ),
            "",
            "## Concept Quality Signals",
            "\n".join(quality_lines),
            "",
            "## Current Concept Page",
            _fit_prompt_section(current_page, max_chars=profile["current_page_chars"]),
            "",
            "## Related Source Pages",
            "\n".join(source_sections) if source_sections else "- No source pages were available.",
            "",
            "## Related Concepts",
            "\n".join(related_sections) if related_sections else "- No related concept pages were available.",
        ]
    )


def _rewrite_candidate_slugs(memory: dict[str, Any], *, exclude: set[str]) -> list[str]:
    quality = memory.get("health", {}).get("concept_quality", {})
    candidates = quality.get("rewrite_candidates", [])
    slugs: list[str] = []
    for candidate in candidates:
        slug = str(candidate.get("slug") or "")
        if not slug or slug in exclude:
            continue
        slugs.append(slug)
    return slugs


def _rewrite_candidate_record(memory: dict[str, Any], slug: str) -> dict[str, Any]:
    quality = memory.get("health", {}).get("concept_quality", {})
    weak_by_slug = {
        str(record.get("slug") or ""): record
        for record in quality.get("weak_concepts", [])
        if isinstance(record, dict)
    }
    for candidate in quality.get("rewrite_candidates", []):
        if str(candidate.get("slug") or "") != slug:
            continue
        record = dict(candidate)
        weak_record = weak_by_slug.get(slug, {})
        if weak_record:
            record.setdefault("conflict_signals", weak_record.get("conflict_signals", []))
            record.setdefault("gap_signals", weak_record.get("gap_signals", []))
        return record
    return {}


def _build_ask_prompt(
    root: Path,
    target: Path,
    question: str,
    output_format: str,
    current_artifact: str,
    source_pages: list[tuple[dict[str, Any], str]],
    concept_pages: list[tuple[str, str]],
    protocol_pages: list[tuple[str, str]],
    index_pages: list[tuple[str, str]],
    machine_memory_query: dict[str, Any],
    previous_output_summary: str | None = None,
    prompt_profile: str = "balanced",
) -> str:
    template = _load_prompt(root, "ask.md")
    profile = _ask_prompt_profile(prompt_profile)
    sections = [
        template,
        "## Target",
        f"- Replace file: `{relative_path(root, target)}`",
        f"- Query: {render_scalar(question)}",
        f"- Format: `{output_format}`",
        "",
        "## Runtime Schema",
        _schema_context(root, ("index.md", "citations.md", "conflicts.md", "writeback.md")),
        "",
        "## Active Protocol",
        _protocol_context(root, ("index.md", "taxonomy.md", "decision.md", "judgment.md", "review.md", "nightly.md", "query.md")),
        "",
        "## Current Artifact",
        current_artifact,
        "",
    ]
    if previous_output_summary:
        sections.extend(["## Previous Output In Corpus", previous_output_summary, ""])
    sections.extend([
        "## Machine Memory Query Plan",
        _render_machine_query(machine_memory_query),
        "",
        "## Index Pages",
    ])
    included_chars = sum(len(section) for section in sections)
    selected_index_pages = _select_ask_index_pages(index_pages, machine_memory_query, output_format)
    if not selected_index_pages:
        sections.append("- No index pages were available.")
    else:
        included_chars += len(sections[-1])
        omitted = 0
        for index, (relative, content) in enumerate(selected_index_pages):
            if index >= profile["max_index_pages"]:
                omitted = len(selected_index_pages) - index
                break
            excerpt = (
                _fit_log_prompt_section(content, max_chars=profile["log_page_chars"])
                if relative.endswith("/log.md")
                else _fit_prompt_section(content, max_chars=profile["index_page_chars"])
            )
            block = "\n".join([f"### {relative}", excerpt, ""])
            if included_chars + len(block) > profile["max_total_chars"]:
                omitted = len(selected_index_pages) - index
                break
            sections.append(block)
            included_chars += len(block)
        if omitted:
            sections.append(f"- Omitted `{omitted}` additional index page(s) for prompt profile `{prompt_profile}`.")
    sections.extend(
        [
            "## Protocol Pages",
        ]
    )
    included_chars += len(sections[-1])
    selected_protocol_pages = _select_ask_protocol_pages(protocol_pages, output_format)
    if not selected_protocol_pages:
        sections.append("- No protocol pages were available.")
    else:
        omitted = 0
        for index, (relative, content) in enumerate(selected_protocol_pages):
            if index >= profile["max_protocol_pages"]:
                omitted = len(selected_protocol_pages) - index
                break
            block = "\n".join([f"### {relative}", _fit_prompt_section(content, max_chars=profile["protocol_page_chars"]), ""])
            if included_chars + len(block) > profile["max_total_chars"]:
                omitted = len(selected_protocol_pages) - index
                break
            sections.append(block)
            included_chars += len(block)
        if omitted:
            sections.append(f"- Omitted `{omitted}` additional protocol page(s) for prompt profile `{prompt_profile}`.")
    sections.extend(
        [
            "## Concept Pages",
        ]
    )
    included_chars += len(sections[-1])
    if not concept_pages:
        sections.append("- No ranked concept pages were available.")
    else:
        omitted = 0
        for index, (slug, content) in enumerate(concept_pages):
            if index >= profile["max_concepts"]:
                omitted = len(concept_pages) - index
                break
            block = "\n".join(
                [
                    f"### wiki/concepts/{slug}.md",
                    _fit_prompt_section(content, max_chars=profile["concept_page_chars"]),
                    "",
                ]
            )
            if included_chars + len(block) > profile["max_total_chars"]:
                omitted = len(concept_pages) - index
                break
            sections.append(block)
            included_chars += len(block)
        if omitted:
            sections.append(f"- Omitted `{omitted}` additional concept page(s) for prompt profile `{prompt_profile}`.")
    sections.extend(
        [
            "## Source Pages",
        ]
    )
    included_chars += len(sections[-1])
    if not source_pages:
        sections.append("- No ranked source pages were available. Keep the artifact cautious and explicit about missing evidence.")
    else:
        omitted = 0
        for index, (entry, content) in enumerate(source_pages):
            if index >= profile["max_sources"]:
                omitted = len(source_pages) - index
                break
            block = "\n".join(
                [
                    f"### wiki/sources/{entry['id']}.md",
                    _fit_prompt_section(content, max_chars=profile["source_page_chars"]),
                    "",
                ]
            )
            if included_chars + len(block) > profile["max_total_chars"]:
                omitted = len(source_pages) - index
                break
            sections.append(block)
            included_chars += len(block)
        if omitted:
            sections.append(
                "- Additional ranked source pages were omitted to keep the prompt responsive. "
                "Use the cited source pages already provided and stay explicit about uncertainty."
            )
    return "\n".join(sections)


def _ask_prompt_profile(name: str) -> dict[str, int]:
    profile = ASK_PROMPT_PROFILES.get(name) or ASK_PROMPT_PROFILES["balanced"]
    adjusted = dict(profile)
    adjusted["max_total_chars"] = max(int(profile["max_total_chars"]), _context_budget())
    return adjusted


def _select_ask_index_pages(
    index_pages: list[tuple[str, str]],
    machine_memory_query: dict[str, Any],
    output_format: str,
) -> list[tuple[str, str]]:
    available = {relative: (relative, content) for relative, content in index_pages}
    preferred: list[str] = list(ASK_INDEX_PAGES_BASE)
    preferred.extend(ASK_INDEX_PAGES_BY_FORMAT.get(output_format, ()))
    if machine_memory_query.get("relevant_actions"):
        preferred.extend(
            [
                "wiki/indexes/machine-memory-actions.md",
                "wiki/indexes/machine-memory-repair-plan.md",
            ]
        )
    if machine_memory_query.get("archive_recall_hints"):
        preferred.append("wiki/indexes/cognitive-history.md")
    selected: list[tuple[str, str]] = []
    for relative in preferred:
        item = available.get(relative)
        if item and item not in selected:
            selected.append(item)
    return selected


def _select_ask_protocol_pages(protocol_pages: list[tuple[str, str]], output_format: str) -> list[tuple[str, str]]:
    available = {relative.rsplit("/", 1)[-1]: (relative, content) for relative, content in protocol_pages}
    preferred_names = list(ASK_PROTOCOL_PAGE_NAMES_BASE)
    preferred_names.extend(ASK_PROTOCOL_PAGE_NAMES_BY_FORMAT.get(output_format, ()))
    selected: list[tuple[str, str]] = []
    for name in preferred_names:
        item = available.get(name)
        if item and item not in selected:
            selected.append(item)
    return selected


def _initial_ask_prompt_profile(client: SupportsComplete) -> str:
    return "balanced"


def _lean_ask_prompt_profile(client: SupportsComplete) -> str:
    del client
    return "lean"


def _select_initial_ask_prompt_profile(client: SupportsComplete, lean: bool = False) -> str:
    if lean:
        return _lean_ask_prompt_profile(client)
    return _initial_ask_prompt_profile(client)


def _retry_ask_prompt_profile(exc: Exception, current_profile: str, client: SupportsComplete) -> str:
    text = str(exc or "").lower()
    del client
    if current_profile == "balanced" and ("timed out" in text or "timeout" in text):
        return "lean"
    return ""


def _render_machine_query(machine_memory_query: dict[str, Any]) -> str:
    matched_terms = machine_memory_query.get("matched_terms", [])
    direct_source_ids = machine_memory_query.get("direct_source_ids", [])
    direct_concept_slugs = machine_memory_query.get("direct_concept_slugs", [])
    ranked_source_ids = machine_memory_query.get("ranked_source_ids", [])
    ranked_concept_slugs = machine_memory_query.get("ranked_concept_slugs", [])
    supporting_edges = machine_memory_query.get("supporting_edges", [])

    lines = [
        f"- Matched terms: `{', '.join(matched_terms) or 'none'}`",
        f"- Selected strategy: `{machine_memory_query.get('selected_strategy', 'concept-first')}`",
        f"- Selection reason: `{machine_memory_query.get('selection_reason', 'default-strategy')}`",
        f"- Source markers: `{', '.join(machine_memory_query.get('matched_source_markers', [])) or 'none'}`",
        f"- Graph markers: `{', '.join(machine_memory_query.get('matched_graph_markers', [])) or 'none'}`",
        f"- Direct source hits: `{', '.join(direct_source_ids) or 'none'}`",
        f"- Direct concept hits: `{', '.join(direct_concept_slugs) or 'none'}`",
        f"- Ranked source candidates: `{', '.join(ranked_source_ids) or 'none'}`",
        f"- Ranked concept candidates: `{', '.join(ranked_concept_slugs) or 'none'}`",
        f"- Bridge concepts: `{', '.join(machine_memory_query.get('bridge_concept_slugs', [])) or 'none'}`",
        f"- Touched components: `{', '.join(machine_memory_query.get('touched_component_ids', [])) or 'none'}`",
        "- Supporting edges:",
    ]
    if not supporting_edges:
        lines.append("  - none")
    else:
        for edge in supporting_edges[:12]:
            lines.append(f"  - {edge['type']}: `{edge['left']}` -> `{edge['right']}`")
        if len(supporting_edges) > 12:
            lines.append(f"  - ... {len(supporting_edges) - 12} more edge(s)")
    subgraph = machine_memory_query.get("query_subgraph", {})
    lines.append(f"- Query subgraph sources: `{', '.join(node['id'] for node in subgraph.get('sources', [])) or 'none'}`")
    lines.append(f"- Query subgraph concepts: `{', '.join(node['slug'] for node in subgraph.get('concepts', [])) or 'none'}`")
    lines.append(f"- Query subgraph edge count: `{len(subgraph.get('edges', []))}`")
    routes = machine_memory_query.get("query_routes", [])
    lines.append(f"- Query routes: `{len(routes)}`")
    if routes:
        lines.append("- Route summaries:")
        for route in routes[:4]:
            start = route.get("start", {})
            goal = route.get("goal", {})
            lines.append(
                f"  - `{start.get('title', start.get('id', ''))}` -> `{goal.get('title', goal.get('id', ''))}`"
                f" ({route.get('length', 0)} hop(s), strategy `{route.get('strategy', machine_memory_query.get('selected_strategy', 'concept-first'))}`)"
            )
    planner_next_action = machine_memory_query.get("planner_next_action", {})
    if planner_next_action:
        lines.append(
            f"- Planner next action: `{planner_next_action.get('action_id', '')}`"
            f" / `{planner_next_action.get('title', '')}`"
            f" / score `{planner_next_action.get('priority_score', 0)}`"
        )
    relevant_actions = machine_memory_query.get("relevant_actions", [])
    lines.append(f"- Relevant repair actions: `{len(relevant_actions)}`")
    if relevant_actions:
        lines.append("- Repair action summaries:")
        for action in relevant_actions[:6]:
            detail = f" | secondary `{action['secondary_path']}`" if action.get("secondary_path") else ""
            next_step = action.get("next_step", "")
            next_part = f" | next {next_step}" if next_step else ""
            proposal_targets = action.get("proposal_targets", [])
            proposal_part = (
                f" | proposal `{action.get('proposal_kind', 'manual-repair')}` -> `{', '.join(proposal_targets)}`"
                if proposal_targets
                else ""
            )
            strategy = action.get("proposal_summary", "")
            strategy_part = f" | strategy {strategy}" if strategy else ""
            lines.append(
                f"  - [{action.get('priority', 'unknown')}] {action.get('title', '')}"
                f" | status `{action.get('status', 'unknown')}`"
                f" | policy `{action.get('execution_policy', 'triage')}`"
                f" | primary `{action.get('primary_path', '')}`"
                f"{detail}"
                f"{next_part}"
                f"{proposal_part}"
                f"{strategy_part}"
            )
    return "\n".join(lines)


def _build_lint_prompt(root: Path, deterministic_report: str, prompt_profile: str = "balanced") -> str:
    template = _load_prompt(root, "lint.md")
    profile = _lint_prompt_profile(prompt_profile)
    max_total_chars = min(int(profile["max_total_chars"]), _context_budget())
    sections = [
        template,
        "## Deterministic Lint Report",
        _read_context(root / deterministic_report, max_chars=profile["deterministic_report_chars"]),
        "",
        "## Active Protocol",
        _protocol_context(root, ("index.md", "review.md", "nightly.md"), max_chars=profile["protocol_page_chars"]),
        "",
        "## Wiki Indexes",
    ]
    included_chars = sum(len(section) for section in sections)
    index_pages = (
        "wiki/indexes/index.md",
        "wiki/indexes/sources.md",
        "wiki/indexes/concepts.md",
        "wiki/indexes/compile-status.md",
        "wiki/indexes/machine-memory.md",
        "wiki/indexes/machine-memory-topology.md",
        "wiki/indexes/machine-memory-actions.md",
        "wiki/indexes/graph-health.md",
        "wiki/indexes/drift-report.md",
        "wiki/indexes/log.md",
    )
    omitted_indexes = 0
    for index, relative in enumerate(index_pages):
        path = root / relative
        if path.exists():
            if index >= profile["max_index_pages"]:
                omitted_indexes += 1
                continue
            excerpt = _read_context(
                path,
                max_chars=profile["log_page_chars"] if relative.endswith("/log.md") else profile["index_page_chars"],
            )
            block = f"### {relative}\n{excerpt}\n"
            if included_chars + len(block) > max_total_chars:
                omitted_indexes += 1
                continue
            sections.append(block)
            included_chars += len(block)
    if omitted_indexes:
        sections.append(f"- Omitted `{omitted_indexes}` additional index page(s) for prompt profile `{prompt_profile}`.")

    schema_context = _schema_context(
        root,
        ("index.md", "citations.md", "conflicts.md", "writeback.md"),
        max_chars=profile["schema_page_chars"],
    )
    if schema_context:
        block = "\n".join(["## Runtime Schema", schema_context, ""])
        if included_chars + len(block) <= max_total_chars:
            sections.append(block)
            included_chars += len(block)

    wiki_pages_added = 0
    omitted_wiki_pages = 0
    for group in ("wiki/concepts", "wiki/sources", "wiki/derived"):
        for path in sorted((root / group).glob("*.md")):
            if wiki_pages_added >= profile["max_wiki_pages"]:
                omitted_wiki_pages += 1
                continue
            excerpt = _read_context(path, max_chars=profile["wiki_page_chars"])
            next_block = f"### {relative_path(root, path)}\n{excerpt}\n"
            if included_chars + len(next_block) > max_total_chars:
                omitted_wiki_pages += 1
                continue
            sections.append(next_block)
            included_chars += len(next_block)
            wiki_pages_added += 1
    if omitted_wiki_pages:
        sections.append("- Additional wiki files were omitted to keep the lint prompt within the backend budget.")
    return "\n".join(sections)


def _load_prompt(root: Path, name: str) -> str:
    path = root / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    fallback = Path(__file__).resolve().parents[2] / "prompts" / name
    if fallback.exists():
        return fallback.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Missing prompt template `{name}` in `{path}` or runtime fallback `{fallback}`.")


def _schema_context(root: Path, names: tuple[str, ...], max_chars: int = 2200) -> str:
    sections: list[str] = []
    for name in names:
        path = root / "schema" / name
        if not path.exists():
            continue
        sections.extend([f"### schema/{name}", _read_context(path, max_chars=max_chars), ""])
    return "\n".join(sections).strip()


def _protocol_context(root: Path, names: tuple[str, ...], max_chars: int = 2200) -> str:
    state = load_protocol_state(root)
    active = state["active_protocol"]
    sections: list[str] = [f"- Active protocol: `{active}` ({state['state_path']})", ""]
    for name in names:
        path = root / "schema" / "protocols" / active / name
        if not path.exists():
            continue
        sections.extend([f"### schema/protocols/{active}/{name}", _read_context(path, max_chars=max_chars), ""])
    return "\n".join(sections).strip()


def _read_context(path: Path, max_chars: int) -> str:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        text = read_text_preview(path, limit_chars=max_chars)
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n...[truncated]"
    return text


def _normalize_markdown(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            cleaned = "\n".join(lines[1:-1]).strip()
    return cleaned + "\n"


def _validate_source_page(markdown: str, expected_id: str, expected_source_file: str, expected_source_sha: str) -> None:
    frontmatter = parse_frontmatter(markdown)
    if not frontmatter:
        raise RuntimeError("Compile response is missing frontmatter.")
    if frontmatter.get("id") != expected_id:
        raise RuntimeError("Compile response changed the source page id.")
    if frontmatter.get("kind") != "source":
        raise RuntimeError("Compile response changed the page kind.")
    if frontmatter.get("source_sha256") != expected_source_sha:
        raise RuntimeError("Compile response changed or dropped the source sha.")
    source_files = frontmatter.get("source_files", [])
    if expected_source_file not in source_files:
        raise RuntimeError("Compile response dropped the source file reference.")
    if preserved_section(markdown, "Summary", "").strip() == "- Pending LLM summary.":
        raise RuntimeError("Compile response left the source summary in placeholder state.")


def _validate_concept_page(
    markdown: str,
    expected_slug: str,
    expected_source_signature: str,
    expected_source_pages: list[str],
) -> None:
    frontmatter = parse_frontmatter(markdown)
    if not frontmatter:
        raise RuntimeError("Concept compile response is missing frontmatter.")
    if frontmatter.get("id") != f"concept-{expected_slug}":
        raise RuntimeError("Concept compile response changed the concept id.")
    if frontmatter.get("kind") != "concept":
        raise RuntimeError("Concept compile response changed the page kind.")
    if expected_source_signature and frontmatter.get("source_signature") != expected_source_signature:
        raise RuntimeError("Concept compile response changed or dropped the source signature.")
    source_pages = frontmatter.get("source_pages", [])
    for expected_source_page in expected_source_pages:
        if expected_source_page not in source_pages:
            raise RuntimeError("Concept compile response dropped a source page reference.")
    if str(frontmatter.get("hardness") or "").strip().lower() not in CONCEPT_HARDNESS_LEVELS:
        raise RuntimeError("Concept compile response is missing a valid `hardness` frontmatter value.")
    if concept_summary_is_placeholder(markdown):
        raise RuntimeError("Concept compile response left the concept summary in fallback state.")


def _fit_prompt_section(text: str, max_chars: int, tail: bool = False) -> str:
    if len(text) <= max_chars:
        return text
    if tail:
        return "...[truncated earlier content]\n" + text[-max_chars:].lstrip()
    return text[:max_chars].rstrip() + "\n...[truncated]"


def _fit_log_prompt_section(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    headings = [match.start() for match in re.finditer(r"(?m)^## ", text)]
    if headings:
        start = headings[max(0, len(headings) - 3)]
        excerpt = text[start:]
        if len(excerpt) <= max_chars:
            return "...[truncated earlier log entries]\n" + excerpt.lstrip()
        return "...[truncated earlier log entries]\n" + excerpt[-max_chars:].lstrip()
    return _fit_prompt_section(text, max_chars=max_chars, tail=True)


def _extract_related_concept_slugs(markdown: str) -> list[str]:
    slugs: list[str] = []
    for match in re.finditer(r"\(\./([a-z0-9][a-z0-9\-]*)\.md\)", markdown):
        slug = match.group(1)
        if slug not in slugs:
            slugs.append(slug)
    return slugs


def _validate_output_markdown(markdown: str, output_format: str, source_ids: list[str]) -> None:
    if output_format in {"report", "decision-memo", "sop", "figure"}:
        frontmatter = parse_frontmatter(markdown)
        if not frontmatter:
            raise RuntimeError("Ask response is missing frontmatter.")
    if source_ids and "wiki/sources/" not in markdown:
        raise RuntimeError("Ask response is missing explicit source-page citations.")


def _append_log(root: Path, event: dict[str, Any]) -> None:
    _append_jsonl_log(root, ".aiwiki/logs/runs.jsonl", event)


def _append_llm_receipt(root: Path, event: dict[str, Any]) -> None:
    _append_jsonl_log(root, ".aiwiki/logs/llm-receipts.jsonl", event)


def _append_jsonl_log(root: Path, relative_log_path: str, event: dict[str, Any]) -> None:
    ensure_layout(root)
    payload = {
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        **event,
    }
    log_path = root / relative_log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _context_budget() -> int:
    return LLMConfig.status_from_env()["max_context_chars"]


def _compile_prompt_profile(name: str) -> dict[str, int]:
    profile = COMPILE_PROMPT_PROFILES.get(name) or COMPILE_PROMPT_PROFILES["balanced"]
    adjusted = dict(profile)
    adjusted["max_total_chars"] = min(int(profile["max_total_chars"]), _context_budget())
    return adjusted


def _lint_prompt_profile(name: str) -> dict[str, int]:
    profile = LINT_PROMPT_PROFILES.get(name) or LINT_PROMPT_PROFILES["balanced"]
    adjusted = dict(profile)
    adjusted["max_total_chars"] = min(int(profile["max_total_chars"]), _context_budget())
    return adjusted


def _initial_compile_prompt_profile(client: SupportsComplete) -> str:
    del client
    return "balanced"


def _initial_lint_prompt_profile(client: SupportsComplete) -> str:
    del client
    return "balanced"


def _retry_compile_prompt_profile(exc: Exception, current_profile: str, client: SupportsComplete) -> str:
    del exc
    del current_profile
    del client
    return ""


def _retry_lint_prompt_profile(exc: Exception, current_profile: str, client: SupportsComplete) -> str:
    del exc
    del current_profile
    del client
    return ""


def _client_model_name(client: SupportsComplete) -> str:
    config = getattr(client, "config", None)
    model = getattr(config, "model", None)
    return str(model or "")


def _client_selected_model_name(client: SupportsComplete) -> str:
    configs = getattr(client, "client_configs", None)
    if isinstance(configs, list) and configs:
        return str(getattr(configs[0], "model", "") or "")
    primary_config = getattr(client, "primary_config", None)
    if primary_config is not None:
        return str(getattr(primary_config, "model", "") or "")
    return _client_model_name(client)


def _client_backend_requested(client: SupportsComplete) -> str:
    for config in (getattr(client, "primary_config", None), getattr(client, "config", None)):
        if config is None:
            continue
        requested = getattr(config, "backend_requested", None) or getattr(config, "backend", None)
        if requested:
            return str(requested)
    return ""


def _client_backend_name(client: SupportsComplete) -> str:
    for config in (getattr(client, "config", None), getattr(client, "primary_config", None)):
        if config is None:
            continue
        backend = getattr(config, "backend", None)
        if backend:
            return str(backend)
    return ""


def _append_fallback_stage(stages: list[str], stage: str) -> None:
    if stage and stage not in stages:
        stages.append(stage)


def _fallback_stage_label(stages: list[str]) -> str:
    return "+".join(stage for stage in stages if stage)


def _infer_delivery_mode(status: str, error: str = "", fallback_stage: str = "", explicit: str = "", skipped: bool = False) -> str:
    if explicit:
        return explicit
    if skipped:
        return "skipped"
    if status == "failed" or error:
        return "llm-failed"
    if status == "success" and fallback_stage:
        return "llm-fallback-chain"
    if status == "success":
        return "llm-success"
    return ""


def _empty_llm_audit() -> dict[str, Any]:
    return {
        "backend_requested": "",
        "backend_effective": "",
        "model_selected": "",
        "model_final": "",
        "fallback_stage": "",
        "fallback_reason": "",
        "contract_validated": False,
    }


def _build_llm_audit(
    client: SupportsComplete | None,
    *,
    model_selected: str = "",
    fallback_stages: list[str] | None = None,
    fallback_reason: str = "",
    contract_validated: bool = False,
) -> dict[str, Any]:
    audit = _empty_llm_audit()
    stages = fallback_stages or []
    audit["model_selected"] = model_selected
    audit["fallback_stage"] = _fallback_stage_label(stages)
    audit["fallback_reason"] = fallback_reason
    audit["contract_validated"] = contract_validated
    if client is None:
        return audit
    audit["backend_requested"] = _client_backend_requested(client)
    audit["backend_effective"] = _client_backend_name(client)
    audit["model_selected"] = model_selected or _client_model_name(client)
    audit["model_final"] = _client_model_name(client)
    return audit


def _merge_llm_audits(current: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = _empty_llm_audit()
    if isinstance(current, dict):
        merged.update(current)
    if not isinstance(update, dict):
        return merged
    if not merged["backend_requested"]:
        merged["backend_requested"] = str(update.get("backend_requested") or "")
    if str(update.get("backend_effective") or ""):
        merged["backend_effective"] = str(update.get("backend_effective") or "")
    if not merged["model_selected"]:
        merged["model_selected"] = str(update.get("model_selected") or "")
    if str(update.get("model_final") or ""):
        merged["model_final"] = str(update.get("model_final") or "")
    stages: list[str] = []
    for label in (str(merged.get("fallback_stage") or ""), str(update.get("fallback_stage") or "")):
        for stage in label.split("+"):
            _append_fallback_stage(stages, stage)
    merged["fallback_stage"] = _fallback_stage_label(stages)
    if str(update.get("fallback_reason") or ""):
        merged["fallback_reason"] = str(update.get("fallback_reason") or "")
    merged["contract_validated"] = bool(merged.get("contract_validated")) or bool(update.get("contract_validated"))
    return merged


def _llm_audit_from_result(result: dict[str, Any]) -> dict[str, Any]:
    audit = _empty_llm_audit()
    if not isinstance(result, dict):
        return audit
    for key in audit:
        if key == "contract_validated":
            audit[key] = bool(result.get(key))
        else:
            audit[key] = str(result.get(key) or "")
    return audit


def _append_llm_receipt_and_log(
    root: Path,
    base_event: dict[str, Any],
    llm_audit: dict[str, Any],
    *,
    status: str,
    error: str = "",
    response_id: str = "",
    usage: dict[str, Any] | None = None,
    skipped: bool = False,
) -> None:
    usage_payload = usage if isinstance(usage, dict) else {}
    normalized_event = {**llm_audit, **base_event}
    normalized_event["delivery_mode"] = _infer_delivery_mode(
        status,
        error=error,
        fallback_stage=str(normalized_event.get("fallback_stage") or ""),
        explicit=str(normalized_event.get("delivery_mode") or ""),
        skipped=skipped,
    )
    normalized_event.setdefault("fallback_used", False)
    if not normalized_event["fallback_used"]:
        normalized_event["fallback_used"] = bool(normalized_event.get("delivery_mode") == "deterministic-fallback" or str(normalized_event.get("fallback_stage") or ""))
    normalized_event.setdefault("fallback_from", "")
    normalized_event.setdefault("fallback_command", "")
    normalized_event.setdefault("primary_attempt_status", "")
    normalized_event.setdefault("primary_error", "")
    normalized_event.update({"status": status, "response_id": response_id, "usage": usage_payload})
    if error:
        normalized_event["error"] = error
    llm_audit.update({
        "delivery_mode": normalized_event.get("delivery_mode", ""),
        "fallback_used": bool(normalized_event.get("fallback_used", False)),
        "fallback_from": str(normalized_event.get("fallback_from") or ""),
        "fallback_command": str(normalized_event.get("fallback_command") or ""),
        "primary_attempt_status": str(normalized_event.get("primary_attempt_status") or ""),
        "primary_error": str(normalized_event.get("primary_error") or ""),
    })
    _append_llm_receipt(root, normalized_event)
    run_event = {
        **base_event,
        "backend": str(llm_audit.get("backend_effective") or ""),
        "model": str(llm_audit.get("model_final") or ""),
        **normalized_event,
    }
    if error:
        run_event["error"] = error
    _append_log(root, run_event)


def _fallback_to_next_model(client: SupportsComplete, operation: str, exc: Exception) -> bool:
    current_model = _client_model_name(client)
    if not advance_client_model(client):
        return False
    next_model = _client_model_name(client)
    logging.getLogger("aiwiki").warning(
        "%s failed with model %s: %s; retrying with model %s",
        operation,
        current_model or "(default)",
        exc,
        next_model or "(default)",
    )
    return True


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
