"""LLM-backed primary workflows: compile, ask, lint, nightly."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiwiki.app_compile import (
    ask_question,
    compile_wiki,
    lint_wiki,
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
from aiwiki.app_state import load_machine_memory, load_manifest
from aiwiki.app_utils import (
    parse_frontmatter,
    relative_path,
    runtime_write_operation,
    utc_now,
)
from aiwiki.llm import CompletionResult, LLMError, classify_backend_error
from aiwiki.runner.clients import (
    _append_fallback_stage,
    _client_backend_name,
    _client_backend_requested,
    _client_model_name,
    _client_selected_model_name,
    _fallback_stage_label,
    _fallback_to_next_model,
    create_client,
)
from aiwiki.runner.interfaces import SupportsComplete
from aiwiki.runner.prompts import (
    _build_ask_prompt,
    _build_compile_prompt,
    _build_concept_compile_prompt,
    _build_lint_prompt,
    _extract_related_concept_slugs,
    _initial_compile_prompt_profile,
    _initial_lint_prompt_profile,
    _normalize_markdown,
    _retry_ask_prompt_profile,
    _retry_compile_prompt_profile,
    _retry_lint_prompt_profile,
    _rewrite_candidate_record,
    _rewrite_candidate_slugs,
    _select_initial_ask_prompt_profile,
    _system_prompt,
    _validate_concept_page,
    _validate_output_markdown,
    _validate_source_page,
)
from aiwiki.runner.receipts import (
    _build_llm_audit,
    _empty_llm_audit,
    _llm_audit_from_result,
    _merge_llm_audits,
    record_llm_attempt,
)

RUN_ASK_FRONTDOOR_EVENT = "run-ask-frontdoor"
RUN_ASK_FALLBACK_ERROR_KINDS = {"quota", "timeout", "auth", "unavailable"}

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
        record_llm_attempt(
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
                record_llm_attempt(
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
                record_llm_attempt(
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
                record_llm_attempt(
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
                record_llm_attempt(
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
                record_llm_attempt(
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
                record_llm_attempt(
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
        record_llm_attempt(
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
    record_llm_attempt(
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
        record_llm_attempt(
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
                record_llm_attempt(
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
            record_llm_attempt(
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
    record_llm_attempt(
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
        record_llm_attempt(
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
