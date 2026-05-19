"""LLM-backed primary workflows: compile, ask, lint, nightly."""

from __future__ import annotations

import json
import logging
import os
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
from aiwiki.app_queries import human_query_title
from aiwiki.app_shell import rewrite_recovery_payload_for_paths
from aiwiki.app_state import load_machine_memory, load_manifest, nightly_health_state_path
from aiwiki.app_utils import (
    _restore_file_bytes,
    _snapshot_file_bytes,
    atomic_write_text,
    next_available_stem,
    parse_frontmatter,
    relative_path,
    render_frontmatter,
    runtime_write_operation,
    strip_frontmatter,
    utc_now,
)
from aiwiki.execution.ask import _output_artifact_seed
from aiwiki.execution.audit_reconciliation import reconcile_execution_receipts
from aiwiki.execution.receipts import write_execution_receipt
from aiwiki.execution.run_notes import run_id_for_artifact, write_run_notes, write_run_notes_frontmatter
from aiwiki.llm import CompletionResult, LLMError, _write_raw_response, classify_backend_error
from aiwiki.runner.background import (
    job_manifest_path,
    new_job_id,
    spawn_background_resume,
    update_job_manifest,
    write_job_manifest,
)
from aiwiki.runner.clients import (
    _append_fallback_stage,
    _client_backend_name,
    _client_backend_requested,
    _client_model_name,
    _client_selected_model_name,
    _fallback_stage_label,
    _fallback_to_next_model_with_stage,
    create_client,
)
from aiwiki.runner.interfaces import SupportsComplete
from aiwiki.runner.prompts import (
    _build_ask_prompt,
    _build_compile_prompt,
    _build_concept_compile_prompt,
    _build_lint_prompt,
    _dedupe_report_citations,
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


def _frontmatter_string_list(frontmatter: dict[str, Any], key: str) -> list[str]:
    value = frontmatter.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _runtime_provenance_field_lines(fields: dict[str, list[str]]) -> list[str]:
    if not fields:
        return []
    rendered = render_frontmatter(fields).splitlines()
    return rendered[1:-1]


def _drop_frontmatter_keys(header_lines: list[str], keys: set[str]) -> list[str]:
    filtered: list[str] = []
    skip_list_items = False
    for line in header_lines:
        if skip_list_items and line.startswith("  - "):
            continue
        skip_list_items = False
        if ":" not in line:
            filtered.append(line)
            continue
        key, _raw = line.split(":", 1)
        if key.strip() in keys:
            skip_list_items = True
            continue
        filtered.append(line)
    return filtered


def _restore_run_ask_provenance_frontmatter(target: Path, deterministic_artifact: str) -> None:
    """Restore runtime-owned provenance fields after LLM overwrites an artifact.

    The LLM is allowed to rewrite the markdown body/frontmatter, but provenance used by
    audit gates is owned by the runtime. Restore these fields strictly from the
    deterministic artifact; LLM-provided provenance is dropped instead of trusted.
    """

    deterministic_frontmatter = parse_frontmatter(deterministic_artifact)
    current = target.read_text(encoding="utf-8", errors="replace")
    restored: dict[str, list[str]] = {}
    for key in ("derived_from", "source_files"):
        merged: list[str] = []
        for item in _frontmatter_string_list(deterministic_frontmatter, key):
            if item not in merged:
                merged.append(item)
        if merged:
            restored[key] = merged

    lines = current.splitlines()
    has_frontmatter = bool(lines) and lines[0].strip() == "---"
    close_idx: int | None = None
    if has_frontmatter:
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                close_idx = idx
                break
    keys = {"derived_from", "source_files"}
    restored_lines = _runtime_provenance_field_lines(restored)
    if not has_frontmatter or close_idx is None:
        if not restored_lines:
            return
        updated_lines = ["---", *restored_lines, "---", *lines]
    else:
        header = _drop_frontmatter_keys(lines[1:close_idx], keys)
        updated_lines = [lines[0], *header, *restored_lines, lines[close_idx], *lines[close_idx + 1 :]]
    target.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")


def _run_ask_prepared_context(root: Path, question: str, artifact: dict[str, Any]) -> dict[str, Any]:
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
    current_artifact = _strip_run_notes_prompt_fields(target.read_text(encoding="utf-8", errors="replace"))
    return {
        "source_ids": source_ids,
        "source_pages": source_pages,
        "concept_pages": concept_pages,
        "protocol_pages": protocol_pages,
        "index_pages": index_pages,
        "target": target,
        "current_artifact": current_artifact,
        "question": question,
    }


def _complete_run_ask_artifact(
    root: Path,
    *,
    artifact: dict[str, Any],
    question: str,
    output_format: str,
    protocol: str | None = None,
    client: SupportsComplete | None = None,
    lean: bool = False,
    timeout_seconds: int | None = None,
    no_cache: bool = False,
    fallback_to_ask: bool = False,
    backend_compat: dict[str, Any] | None = None,
) -> dict[str, Any]:
    backend_compat = dict(backend_compat or {})
    background_job_id = str(artifact.get("background_job_id") or "")

    def _stamped_record(base_event: dict[str, Any], llm_audit: dict[str, Any], **kwargs: Any) -> None:
        if backend_compat:
            base_event = dict(base_event)
            base_event["backend_compat"] = dict(backend_compat)
        record_llm_attempt(root, base_event, llm_audit, **kwargs)

    prepared = _run_ask_prepared_context(root, question, artifact)
    source_ids = prepared["source_ids"]
    target = prepared["target"]
    current_artifact = prepared["current_artifact"]

    def _apply_graph_anchors_to_target() -> None:
        anchors = [str(item) for item in artifact.get("graph_anchor_node_ids", []) if str(item).strip()]
        if not anchors:
            return
        from aiwiki.execution.ask import apply_graph_anchors_to_artifact

        apply_graph_anchors_to_artifact(target, anchors=anchors, memory=load_machine_memory(root))

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
        prepared["source_pages"],
        prepared["concept_pages"],
        prepared["protocol_pages"],
        prepared["index_pages"],
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
                        prepared["source_pages"],
                        prepared["concept_pages"],
                        prepared["protocol_pages"],
                        prepared["index_pages"],
                        artifact.get("machine_memory_query", {}),
                        previous_output_summary=previous_output_summary,
                        prompt_profile=retry_profile,
                    )
                    prompt_profile = retry_profile
                    used_prompt_profile = retry_profile
                    continue
                fallback_stage = _fallback_to_next_model_with_stage(effective_client, "run-ask", exc)
                if fallback_stage:
                    fallback_reason = str(exc)
                    _append_fallback_stage(fallback_stages, fallback_stage)
                    continue
                raise
            updated = _normalize_markdown(result.text)
            if output_format == "report":
                updated = _dedupe_report_citations(updated)
            try:
                _validate_output_markdown(updated, output_format, source_ids)
            except RuntimeError as exc:
                fallback_stage = _fallback_to_next_model_with_stage(effective_client, "run-ask", exc)
                if fallback_stage:
                    fallback_reason = str(exc)
                    _append_fallback_stage(fallback_stages, fallback_stage)
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
        _stamped_record(
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
            raw_response_path=_raw_response_path(root, result, exc),
            error_class=_receipt_error_class(exc),
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
                _stamped_record(
                    {
                        **frontdoor_base_event,
                        "delivery_mode": "deterministic-fallback",
                        "fallback_used": True,
                        "fallback_from": "run-ask",
                        "fallback_command": "ask",
                    },
                    {**failed_audit, "delivery_mode": "deterministic-fallback", "fallback_used": True, "fallback_from": "run-ask", "fallback_command": "ask"},
                    status="degraded",
                    error=str(exc),
                    response_id=getattr(result, "response_id", "") if result is not None else "",
                    usage=getattr(result, "usage", {}) if result is not None else {},
                    raw_response_path=_raw_response_path(root, result, exc),
                    error_class=_receipt_error_class(exc),
                )
                _mark_run_ask_artifact_degraded(
                    target,
                    reason=str(exc),
                    backend=str(failed_audit.get("backend_effective") or ""),
                    model=str(failed_audit.get("model_final") or ""),
                )
                _apply_graph_anchors_to_target()
                run_notes = write_run_notes(
                    root,
                    run_id=str(artifact.get("run_id") or ""),
                    status="deterministic-fallback",
                    question=question,
                    output_format=output_format,
                    protocol=str(artifact.get("protocol") or ""),
                    output_path=str(artifact.get("path") or ""),
                    source_count=len(source_ids),
                    concept_count=len(artifact.get("ranked_concepts", [])),
                    receipt_path=".aiwiki/logs/llm-receipts.jsonl",
                    backend=str(failed_audit.get("backend_effective") or ""),
                    model=str(failed_audit.get("model_final") or ""),
                    fallback_stage=str(failed_audit.get("fallback_stage") or ""),
                    failure_class=_receipt_error_class(exc),
                    stages=[
                        "Prepared deterministic context for the request.",
                        "The primary LLM run did not complete; deterministic fallback output remained available.",
                        "Recorded fallback receipt and recovery metadata.",
                    ],
                )
                write_run_notes_frontmatter(target, run_id=run_notes["run_id"], run_notes_ref=run_notes["run_notes_path"])
                return {
                    **artifact,
                    **run_notes,
                    **failed_audit,
                    "status": "degraded",
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
            _stamped_record(
                frontdoor_base_event,
                failed_audit,
                status="failed",
                error=str(exc),
                response_id=getattr(result, "response_id", "") if result is not None else "",
                usage=getattr(result, "usage", {}) if result is not None else {},
                raw_response_path=_raw_response_path(root, result, exc),
                error_class=_receipt_error_class(exc),
            )
        raise

    assert result is not None
    target_snapshot = _snapshot_file_bytes(target)
    target.write_text(updated, encoding="utf-8")
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
    try:
        _restore_run_ask_provenance_frontmatter(target, current_artifact)
        _reinject_candidate_frontmatter(target, corpus_id=str(artifact.get("active_corpus_id") or ""))
        _apply_graph_anchors_to_target()
        _stamped_record(
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
            raw_response_path=_raw_response_path(root, result),
        )
        _mark_run_ask_background_artifact_complete(target, status="completed", job_id=background_job_id)
        execution_receipt = write_execution_receipt(
            root,
            operation="run-ask",
            generated_by="aiwiki-run-ask",
            subject_kind="output-artifact",
            subject_id=str(artifact.get("run_id") or Path(str(artifact.get("path") or "")).stem),
            target_file=str(artifact["path"]),
            primary_path=str(artifact["path"]),
            protocol=str(artifact.get("protocol") or ""),
            extra={
                "format": output_format,
                "question": question,
                "run_id": str(artifact.get("run_id") or ""),
                "llm_receipt_path": ".aiwiki/logs/llm-receipts.jsonl",
                "backend_effective": backend_effective,
                "model_final": model_final,
                "fallback_stage": fallback_stage,
                "response_id": result.response_id,
                "usage": result.usage,
            },
        )
    except Exception:
        _restore_file_bytes(target, target_snapshot)
        raise
    run_notes = write_run_notes(
        root,
        run_id=str(artifact.get("run_id") or ""),
        status="llm-complete",
        question=question,
        output_format=output_format,
        protocol=str(artifact.get("protocol") or ""),
        output_path=str(artifact.get("path") or ""),
        source_count=len(source_ids),
        concept_count=len(artifact.get("ranked_concepts", [])),
        receipt_path=str(execution_receipt.get("receipt_path") or ""),
        backend=backend_effective,
        model=model_final,
        fallback_stage=fallback_stage,
        stages=[
            "Prepared deterministic context for the request.",
            "Requested an LLM draft using the selected backend and prompt profile.",
            "Validated the returned markdown contract and updated the output artifact.",
            "Recorded authoritative execution receipt and LLM attempt metadata for audit and recovery.",
        ],
    )
    write_run_notes_frontmatter(target, run_id=run_notes["run_id"], run_notes_ref=run_notes["run_notes_path"])
    payload = {
        **artifact,
        **run_notes,
        **llm_audit,
        "prompt_profile": retry_profile or used_prompt_profile,
        "retry_prompt_profile": retry_profile,
        "timeout_seconds": effective_timeout_seconds,
        "no_cache": no_cache,
    }
    if fallback_to_ask:
        _stamped_record(
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
            raw_response_path=_raw_response_path(root, result),
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
def run_ask_submit(
    root: Path,
    question: str,
    output_format: str,
    protocol: str | None = None,
    *,
    lean: bool = False,
    timeout_seconds: int | None = None,
    no_cache: bool = False,
    fallback_to_ask: bool = False,
    corpus_id_override: str | None = None,
    spawn: bool = True,
) -> dict[str, Any]:
    """Prepare a long-running report job and optionally spawn background resume."""

    ensure_layout(root)
    if output_format != "report":
        raise ValueError("run-ask-submit is only supported for report output.")
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("run-ask-submit timeout_seconds must be greater than 0.")

    from aiwiki.runner.preflight import preflight_check_backend_chain

    backend_compat = preflight_check_backend_chain(root)
    ask_kwargs = {"protocol": protocol, "no_cache": no_cache, "write_graph_anchors": False}
    if corpus_id_override is not None:
        ask_kwargs["corpus_id_override"] = corpus_id_override
    artifact = ask_question(root, question, output_format, **ask_kwargs)
    job_id = new_job_id("ask-report")
    artifact["background_job_id"] = job_id
    artifact["background_status"] = "submitted"
    if artifact.get("path"):
        _mark_run_ask_background_artifact_submitted(root / str(artifact["path"]), job_id=job_id)
    now = utc_now()
    manifest = {
        "kind": "run-ask-background-job",
        "version": 1,
        "job_id": job_id,
        "status": "submitted",
        "created_at": now,
        "updated_at": now,
        "question": question,
        "output_format": output_format,
        "protocol": protocol or "",
        "lean": lean,
        "timeout_seconds": timeout_seconds,
        "no_cache": no_cache,
        "fallback_to_ask": fallback_to_ask,
        "corpus_id_override": corpus_id_override or "",
        "artifact": artifact,
        "path": str(artifact.get("path") or ""),
        "run_id": str(artifact.get("run_id") or ""),
        "run_notes_path": str(artifact.get("run_notes_path") or ""),
        "backend_preflight": backend_compat,
    }
    write_job_manifest(root, manifest)
    spawn_result = spawn_background_resume(root, job_id) if spawn else {}
    if spawn_result:
        if artifact.get("path"):
            _mark_run_ask_background_artifact_submitted(root / str(artifact["path"]), job_id=job_id, status="running")
        artifact["background_status"] = "running"
        manifest["artifact"] = artifact
        manifest.update({"status": "running", "spawn": spawn_result, "updated_at": utc_now()})
        write_job_manifest(root, manifest)
    return {
        "kind": "run-ask-background-job",
        "status": "submitted",
        "job_id": job_id,
        "path": manifest["path"],
        "run_id": manifest["run_id"],
        "run_notes_path": manifest["run_notes_path"],
        "format": output_format,
        "protocol": str(artifact.get("protocol") or protocol or ""),
        "question": question,
        "backend_preflight": backend_compat,
        "spawn": spawn_result,
        "job_manifest_path": relative_path(root, job_manifest_path(root, job_id)),
    }


@runtime_write_operation
def run_ask_resume(root: Path, job_id: str, client: SupportsComplete | None = None) -> dict[str, Any]:
    manifest = update_job_manifest(root, job_id, status="running")
    try:
        payload = _complete_run_ask_artifact(
            root,
            artifact=dict(manifest.get("artifact") or {}),
            question=str(manifest.get("question") or ""),
            output_format=str(manifest.get("output_format") or "report"),
            protocol=str(manifest.get("protocol") or "") or None,
            client=client,
            lean=bool(manifest.get("lean")),
            timeout_seconds=manifest.get("timeout_seconds") if isinstance(manifest.get("timeout_seconds"), int) else None,
            no_cache=bool(manifest.get("no_cache")),
            fallback_to_ask=bool(manifest.get("fallback_to_ask")),
            backend_compat=dict(manifest.get("backend_preflight") or {}),
        )
    except Exception as exc:
        update_job_manifest(root, job_id, status="failed", error=str(exc))
        raise
    update_job_manifest(
        root,
        job_id,
        status=str(payload.get("status") or "completed"),
        result=payload,
        path=str(payload.get("path") or manifest.get("path") or ""),
        run_id=str(payload.get("run_id") or manifest.get("run_id") or ""),
        run_notes_path=str(payload.get("run_notes_path") or manifest.get("run_notes_path") or ""),
    )
    return {"job_id": job_id, **payload}


def _mark_run_ask_artifact_degraded(target: Path, *, reason: str, backend: str, model: str) -> None:
    """Replace the deterministic placeholder artifact with an explicit degraded notice."""

    current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    frontmatter = parse_frontmatter(current)
    title = "LLM 未完成：请重试或切换模型"
    query = str(frontmatter.get("query") or "").strip()
    if query:
        try:
            from aiwiki.app_queries import human_query_title

            title = f"LLM 未完成：{human_query_title(query)}"
        except Exception:
            title = "LLM 未完成：请重试或切换模型"
    frontmatter.update(
        {
            "llm_status": "timeout_or_unavailable",
            "delivery_mode": "deterministic-fallback",
            "background_status": "degraded",
            "llm_failure_reason": reason,
            "llm_backend": backend,
            "llm_model": model,
        }
    )
    body = strip_frontmatter(current)
    references = body[body.find("## 参考") :].strip() if "## 参考" in body else body.strip()
    lines = [
        render_frontmatter(frontmatter),
        "",
        f"# {title}",
        "",
        "## 当前状态",
        "- LLM 没有在本次超时时间内返回可用内容；本文件不是最终报告。",
        f"- 失败原因：`{reason}`。",
        f"- 后端 / 模型：`{backend or 'unknown'}` / `{model or 'unknown'}`。",
        "- 材料投喂、引用解析或上下文准备已完成；可以重试、切换模型，或使用更短的问题。",
        "",
        "## 下一步",
        "- 点击重试 run-ask，或在 Product Shell 设置里切换到更稳定的 backend/model。",
        "- 如果问题来自超长 PDF，优先问一个更具体的问题，避免一次性要求完整分析。",
    ]
    if references:
        lines.extend(["", "## 可用上下文", references])
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _mark_run_ask_background_artifact_submitted(target: Path, *, job_id: str, status: str = "submitted") -> None:
    current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    frontmatter = parse_frontmatter(current)
    frontmatter.update(
        {
            "background_job_id": job_id,
            "background_status": status,
            "delivery_mode": "background-pending",
            "llm_status": "pending",
        }
    )
    body = strip_frontmatter(current)
    target.write_text(render_frontmatter(frontmatter).rstrip() + "\n\n" + body.lstrip(), encoding="utf-8")


def _mark_run_ask_background_artifact_complete(target: Path, *, status: str, job_id: str = "") -> None:
    current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    frontmatter = parse_frontmatter(current)
    if job_id:
        frontmatter["background_job_id"] = job_id
    frontmatter["background_status"] = status
    body = strip_frontmatter(current)
    target.write_text(render_frontmatter(frontmatter).rstrip() + "\n\n" + body.lstrip(), encoding="utf-8")


def _direct_ask_artifact_markdown(
    *,
    artifact_id: str,
    question: str,
    protocol: str,
    created_at: str,
    answer: str,
    backend: str,
    model: str,
) -> str:
    title = human_query_title(question)
    frontmatter = {
        "id": artifact_id,
        "kind": "output",
        "format": "note",
        "query": question,
        "protocol": protocol,
        "generated_by": "aiwiki-run-ask-direct",
        "created_at": created_at,
        "delivery_mode": "llm-direct",
        "llm_backend": backend,
        "llm_model": model,
    }
    return render_frontmatter(frontmatter) + f"\n# {title}\n\n## 回答\n\n{answer.strip()}\n"


def _direct_ask_system_prompt() -> str:
    return (
        "你是炼丹炉的直接问答助手。用中文简洁回答用户问题。"
        "不要编造本地仓库、文件或隐藏系统状态；如果问题询问你是什么模型，"
        "说明你是当前配置的外部 LLM 后端返回的回答，并可提及具体模型取决于运行配置。"
    )


def _direct_answer_validation_error(answer: str) -> str:
    text = str(answer or "").strip()
    if not text:
        return "LLM returned an empty direct answer."
    lowered = text.lower()
    if "_llm:" in lowered:
        return "LLM returned a deterministic template marker instead of an answer."
    if "请用 2–5 段自然语言直接回答" in text or "请用 2-5 段自然语言直接回答" in text:
        return "LLM returned the note-answer instruction template instead of an answer."
    if lowered.startswith("---") and "generated_by: aiwiki-ask" in lowered:
        return "LLM returned an aiwiki deterministic artifact template instead of an answer."
    return ""


def _is_simple_direct_ask(question: str, output_format: str, direct: bool) -> bool:
    if output_format != "note":
        return False
    text = str(question or "").strip()
    if not text:
        return False
    if any(marker in text for marker in ("raw/", "wiki/", "output/", ".aiwiki/", "材料路径供系统路由使用", "本次投喂材料路径")):
        return False
    if direct:
        return True
    return len(text) <= 240


def _is_material_hint_note_ask(question: str, output_format: str) -> bool:
    if output_format != "note":
        return False
    text = str(question or "")
    return any(marker in text for marker in ("材料路径供系统路由使用", "本次投喂材料路径"))


def _material_hint_paths(question: str) -> list[str]:
    text = str(question or "")
    paths: list[str] = []
    for marker in ("材料路径供系统路由使用：", "本次投喂材料路径："):
        if marker not in text:
            continue
        tail = text.split(marker, 1)[1]
        tail = tail.split("用户问题：", 1)[0]
        for raw_item in tail.replace("、", "\n").replace(",", "\n").splitlines():
            item = raw_item.strip().lstrip("- ").strip()
            if item and any(item.startswith(prefix) for prefix in ("raw/", "wiki/", "output/", ".aiwiki/")):
                paths.append(item.strip("`"))
    return paths


def _read_material_context_snippets(root: Path, refs: list[str], *, max_chars: int = 6000) -> str:
    snippets: list[str] = []
    remaining = max_chars
    for ref in refs:
        if remaining <= 0:
            break
        path = root / ref
        if not path.exists() or path.is_dir():
            continue
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        text = strip_frontmatter(path.read_text(encoding="utf-8", errors="replace")).strip()
        if not text:
            continue
        excerpt = text[:remaining]
        snippets.append(f"## {ref}\n\n{excerpt}")
        remaining -= len(excerpt)
    return "\n\n".join(snippets).strip()


def _material_direct_system_prompt() -> str:
    return (
        "你是炼丹炉的材料问答助手。用户会给出一个问题和已经抽取成文本的材料摘录。"
        "请优先依据材料回答，用中文给出直接结论和关键依据；如果材料不足，明确说明不足。"
        "不要编造未在材料中出现的事实。"
    )


def _material_direct_user_prompt(question: str, context: str) -> str:
    title = human_query_title(question)
    return f"用户问题：{title}\n\n材料摘录：\n{context}"


def _material_context_preview(context: str, *, max_lines: int = 12, max_chars: int = 1800) -> str:
    """Return a deterministic, clearly-labeled preview for degraded material asks."""

    lines: list[str] = []
    for raw_line in str(context or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## raw/") or line.startswith("## wiki/") or line.startswith("## output/"):
            continue
        if line in {"## PDF Asset", "## Image Asset", "## Import Metadata", "## Image Metadata"}:
            continue
        if line.startswith("- Stored ") or line.startswith("- Imported at:") or line.startswith("- File size:"):
            continue
        lines.append(line)
        if len(lines) >= max_lines:
            break
    preview = "\n".join(f"- {line}" for line in lines)
    return preview[:max_chars].rstrip()


def _degraded_direct_ask_artifact_markdown(
    *,
    artifact_id: str,
    question: str,
    protocol: str,
    created_at: str,
    reason: str,
    backend: str,
    model: str,
    material_context: str = "",
) -> str:
    title = human_query_title(question)
    frontmatter = {
        "id": artifact_id,
        "kind": "output",
        "format": "note",
        "query": question,
        "protocol": protocol,
        "generated_by": "aiwiki-run-ask-direct",
        "created_at": created_at,
        "delivery_mode": "deterministic-fallback",
        "llm_status": "timeout_or_unavailable",
        "llm_failure_reason": reason,
        "llm_backend": backend,
        "llm_model": model,
    }
    lines = [
        render_frontmatter(frontmatter),
        "",
        f"# LLM 未完成：{title}",
        "",
        "## 当前状态",
        f"- LLM 没有在本次超时时间内返回可用内容：`{reason}`。",
        f"- 后端 / 模型：`{backend or 'unknown'}` / `{model or 'unknown'}`。",
        "- 本文件是降级说明，不是完整 LLM 分析。",
    ]
    preview = _material_context_preview(material_context) if material_context else ""
    if preview:
        lines.extend(
            [
                "",
                "## 本地材料预览（非 LLM 分析）",
                preview,
            ]
        )
    lines.extend(
        [
            "",
            "## 下一步",
            "- 直接重试；如果仍超时，切换更稳定的 backend/model。",
            "- 对长 PDF，先问更窄的问题，例如“只总结核心结论和风险”。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _env_flag(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _receipt_error_class(exc: Exception | str) -> str:
    message = str(exc)
    classified = classify_backend_error(message)
    if classified == "timeout":
        return "timeout"
    lowered = message.lower()
    if "frontmatter" in lowered or "parse" in lowered or "invalid json" in lowered:
        return "parse_error"
    if "exit code" in lowered or "non-zero" in lowered or "nonzero" in lowered:
        return "non_zero_exit"
    return "other"


def _strip_run_notes_prompt_fields(markdown: str) -> str:
    lines = str(markdown or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return markdown
    close_idx: int | None = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            close_idx = idx
            break
    if close_idx is None:
        return markdown
    control_prefixes = (
        "run_id:",
        "run_notes_path:",
        "background_job_id:",
        "background_status:",
        "delivery_mode:",
        "llm_status:",
        "llm_failure_reason:",
        "llm_backend:",
        "llm_model:",
    )
    filtered = [
        line
        for line in lines[: close_idx + 1]
        if not line.startswith(control_prefixes)
    ]
    filtered.extend(lines[close_idx + 1 :])
    return "\n".join(filtered) + ("\n" if markdown.endswith("\n") else "")


def _raw_response_path(root: Path, result: CompletionResult | None, exc: Exception | None = None) -> str:
    if exc is not None:
        path = getattr(exc, "raw_response_path", None)
        if isinstance(path, str) and path:
            return path
    if result is None:
        return ""
    if result.raw_response_path:
        return result.raw_response_path
    return _write_raw_response(root, result.text)

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
def run_ask(
    root: Path,
    question: str,
    output_format: str,
    protocol: str | None = None,
    client: SupportsComplete | None = None,
    direct: bool = False,
    lean: bool = False,
    timeout_seconds: int | None = None,
    no_cache: bool = False,
    fallback_to_ask: bool = False,
    corpus_id_override: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("run-ask timeout_seconds must be greater than 0.")
    backend_compat: dict[str, Any] = {}
    if client is None:
        from aiwiki.runner.preflight import preflight_check_backend

        backend_compat = preflight_check_backend(root)

    def _stamped_record(base_event: dict[str, Any], llm_audit: dict[str, Any], **kwargs: Any) -> None:
        if backend_compat:
            base_event = dict(base_event)
            base_event["backend_compat"] = dict(backend_compat)
        record_llm_attempt(root, base_event, llm_audit, **kwargs)

    material_refs = _material_hint_paths(question) if _is_material_hint_note_ask(question, output_format) else []
    material_context = _read_material_context_snippets(root, material_refs) if material_refs else ""
    direct_mode = _is_simple_direct_ask(question, output_format, direct) or bool(material_context)
    if direct_mode:
        effective_client = client or create_client(root, timeout_seconds=timeout_seconds)
        backend_requested = _client_backend_requested(effective_client)
        model_selected = _client_selected_model_name(effective_client)
        effective_timeout_seconds = getattr(getattr(effective_client, "config", None), "timeout_seconds", timeout_seconds)
        started = time.monotonic()
        result: CompletionResult | None = None
        fallback_stages: list[str] = []
        fallback_reason = ""
        system_prompt = _material_direct_system_prompt() if material_context else _direct_ask_system_prompt()
        user_prompt = _material_direct_user_prompt(question, material_context) if material_context else question
        try:
            while True:
                try:
                    result = effective_client.complete(system_prompt, user_prompt)
                    normalized_answer = _normalize_markdown(result.text)
                    validation_error = _direct_answer_validation_error(normalized_answer)
                    if validation_error:
                        raise LLMError(validation_error)
                except LLMError as exc:
                    fallback_stage = _fallback_to_next_model_with_stage(effective_client, "run-ask-direct", exc)
                    if fallback_stage:
                        fallback_reason = str(exc)
                        _append_fallback_stage(fallback_stages, fallback_stage)
                        continue
                    raise
                break
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            from aiwiki.app_protocol import resolve_protocol

            active_protocol = resolve_protocol(root, protocol)
            backend_effective = _client_backend_name(effective_client)
            model_final = _client_model_name(effective_client)
            artifact_ref = ""
            run_notes_path = ""
            run_id = ""
            if fallback_to_ask:
                directory = root / "output" / "reports"
                directory.mkdir(parents=True, exist_ok=True)
                artifact_seed = _output_artifact_seed(question, "note")
                artifact_id = next_available_stem(directory, artifact_seed)
                destination = directory / f"{artifact_id}.md"
                artifact_ref = relative_path(root, destination)
                destination.write_text(
                    _degraded_direct_ask_artifact_markdown(
                        artifact_id=artifact_id,
                        question=question,
                        protocol=active_protocol,
                        created_at=utc_now(),
                        reason=str(exc),
                        backend=backend_effective,
                        model=model_final,
                        material_context=material_context,
                    ),
                    encoding="utf-8",
                )
                run_notes = write_run_notes(
                    root,
                    run_id=run_id_for_artifact(artifact_ref),
                    status="deterministic-fallback",
                    question=question,
                    output_format="note",
                    protocol=active_protocol,
                    output_path=artifact_ref,
                    receipt_path=".aiwiki/logs/llm-receipts.jsonl",
                    backend=backend_effective,
                    model=model_final,
                    fallback_stage=_fallback_stage_label(fallback_stages),
                    stages=[
                        "Detected a simple note/material question and used the lightweight direct-answer LLM path.",
                        "Primary LLM call did not complete; wrote an explicit degraded artifact instead of a placeholder answer.",
                    ],
                    failure_class=_receipt_error_class(exc),
                )
                write_run_notes_frontmatter(
                    destination, run_id=run_notes["run_id"], run_notes_ref=run_notes["run_notes_path"]
                )
                run_id = run_notes["run_id"]
                run_notes_path = run_notes["run_notes_path"]
            failed_audit = {
                "backend_requested": backend_requested,
                "backend_effective": backend_effective,
                "model_selected": model_selected,
                "model_final": model_final,
                "fallback_stage": _fallback_stage_label(fallback_stages),
                "fallback_reason": fallback_reason or str(exc),
                "contract_validated": False,
                "delivery_mode": "deterministic-fallback" if fallback_to_ask else "llm-direct",
            }
            _stamped_record(
                {
                    "event": "run-ask-direct",
                    "target": artifact_ref,
                    "question": question,
                    "format": "note",
                    "protocol": active_protocol,
                    "duration_ms": duration_ms,
                    "timeout_seconds": effective_timeout_seconds,
                    "no_cache": no_cache,
                    "material_refs": material_refs,
                },
                failed_audit,
                status="degraded" if fallback_to_ask else "failed",
                error=str(exc),
                response_id=getattr(result, "response_id", "") if result is not None else "",
                usage=getattr(result, "usage", {}) if result is not None else {},
                raw_response_path=_raw_response_path(root, result, exc),
                error_class=_receipt_error_class(exc),
            )
            if fallback_to_ask:
                return {
                    "path": artifact_ref,
                    "format": "note",
                    "protocol": active_protocol,
                    "question": question,
                    "status": "degraded",
                    "delivery_mode": "deterministic-fallback",
                    "fallback_used": True,
                    "fallback_from": "run-ask-direct",
                    "fallback_reason": fallback_reason or str(exc),
                    "fallback_stage": _fallback_stage_label(fallback_stages),
                    "backend_requested": backend_requested,
                    "backend_effective": backend_effective,
                    "model_selected": model_selected,
                    "model_final": model_final,
                    "timeout_seconds": effective_timeout_seconds,
                    "run_id": run_id,
                    "run_notes_path": run_notes_path,
                    "no_cache": no_cache,
                    "contract_validated": False,
                    "material_refs": material_refs,
                }
            raise
        assert result is not None
        ensure_layout(root)
        from aiwiki.app_protocol import resolve_protocol

        active_protocol = resolve_protocol(root, protocol)
        directory = root / "output" / "reports"
        directory.mkdir(parents=True, exist_ok=True)
        artifact_seed = _output_artifact_seed(question, "note")
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        artifact_ref = relative_path(root, destination)
        backend_effective = _client_backend_name(effective_client)
        model_final = _client_model_name(effective_client)
        content = _direct_ask_artifact_markdown(
            artifact_id=artifact_id,
            question=question,
            protocol=active_protocol,
            created_at=utc_now(),
            answer=normalized_answer,
            backend=backend_effective,
            model=model_final,
        )
        destination.write_text(content, encoding="utf-8")
        run_id = run_id_for_artifact(artifact_ref)
        run_notes = write_run_notes(
            root,
            run_id=run_id,
            status="llm-direct-complete",
            question=question,
            output_format="note",
            protocol=active_protocol,
            output_path=artifact_ref,
            receipt_path=".aiwiki/logs/llm-receipts.jsonl",
            backend=backend_effective,
            model=model_final,
            fallback_stage=_fallback_stage_label(fallback_stages),
            stages=[
                "Detected a simple note/material question and used the lightweight direct-answer LLM path.",
                "Recorded LLM receipt metadata for audit and recovery.",
            ],
        )
        write_run_notes_frontmatter(destination, run_id=run_notes["run_id"], run_notes_ref=run_notes["run_notes_path"])
        llm_audit = {
            "backend_requested": backend_requested,
            "backend_effective": backend_effective,
            "model_selected": model_selected,
            "model_final": model_final,
            "fallback_stage": _fallback_stage_label(fallback_stages),
            "fallback_reason": fallback_reason,
            "contract_validated": True,
            "delivery_mode": "llm-direct",
        }
        _stamped_record(
            {
                "event": "run-ask-direct",
                "target": artifact_ref,
                "question": question,
                "format": "note",
                "protocol": active_protocol,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "timeout_seconds": effective_timeout_seconds,
                "no_cache": no_cache,
                "material_refs": material_refs,
            },
            llm_audit,
            status="success",
            response_id=result.response_id,
            usage=result.usage,
            raw_response_path=_raw_response_path(root, result),
        )
        return {
            "path": artifact_ref,
            "format": "note",
            "protocol": active_protocol,
            "question": question,
            "status": "success",
            "delivery_mode": "llm-direct",
            "backend_requested": backend_requested,
            "backend_effective": backend_effective,
            "model_selected": model_selected,
            "model_final": model_final,
            "fallback_stage": _fallback_stage_label(fallback_stages),
            "fallback_reason": fallback_reason,
            "timeout_seconds": effective_timeout_seconds,
            "run_id": run_notes["run_id"],
            "run_notes_path": run_notes["run_notes_path"],
            "no_cache": no_cache,
            "contract_validated": True,
            "material_refs": material_refs,
        }

    ask_kwargs = {"protocol": protocol, "no_cache": no_cache, "write_graph_anchors": False}
    if corpus_id_override is not None:
        ask_kwargs["corpus_id_override"] = corpus_id_override
    artifact = ask_question(root, question, output_format, **ask_kwargs)
    return _complete_run_ask_artifact(
        root,
        artifact=artifact,
        question=question,
        output_format=output_format,
        protocol=protocol,
        client=client,
        lean=lean,
        timeout_seconds=timeout_seconds,
        no_cache=no_cache,
        fallback_to_ask=fallback_to_ask,
        backend_compat=backend_compat,
    )

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
