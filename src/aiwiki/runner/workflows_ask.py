"""LLM-backed ask workflows: synchronous run-ask.

This module is the orchestration entry point for run-ask.
Helper logic lives in ``workflows_ask_context`` / ``workflows_ask_frontmatter`` /
``workflows_ask_status`` / ``workflows_ask_receipts``.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from aiwiki.execution.ask import ask_question
from aiwiki.execution.paths import run_notes_path as run_notes_file_path
from aiwiki.execution.run_notes import run_id_for_artifact, write_run_notes, write_run_notes_frontmatter
from aiwiki.input_router import is_obsidian_open_link
from aiwiki.llm import CompletionResult, LLMError
from aiwiki.memory.state import load_machine_memory
from aiwiki.notify import notify_report_generated
from aiwiki.protocol.scaffold import ensure_layout
from aiwiki.render.views import build_ask_used_refs
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
    _dedupe_report_citations,
    _normalize_markdown,
    _retry_ask_prompt_profile,
    _select_initial_ask_prompt_profile,
    _system_prompt,
    _validate_output_markdown,
)
from aiwiki.runner.receipts import record_llm_attempt
from aiwiki.runner.workflow_shared import _raw_response_path, _receipt_error_class, reinject_candidate_frontmatter
from aiwiki.runner.workflows_ask_context import (
    _clean_report_reference_question,
    _context_ref_paths,
    _material_hint_paths,
    _quoted_report_material_refs,
    _read_material_context,
    _run_ask_prepared_context,
)
from aiwiki.runner.workflows_ask_frontmatter import (
    _append_visible_quoted_report_refs,
    _ensure_output_cssclass,
    _restore_run_ask_provenance_frontmatter,
    _strip_report_skeleton_reference_hints,
)
from aiwiki.runner.workflows_ask_receipts import (
    _effective_run_ask_timeout,
    _planned_run_ask_output_receipt_ref,
    _refresh_shell_summary_fail_soft,
    _write_run_ask_output_receipt,
)
from aiwiki.runner.workflows_ask_status import (
    _mark_run_ask_artifact_degraded,
    _run_ask_failure_llm_status,
)
from aiwiki.utils.io import (
    _restore_file_bytes,
    _snapshot_file_bytes,
    atomic_write_text,
    runtime_write_lock,
)


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
    backend_compat: dict[str, Any] | None = None,
) -> dict[str, Any]:
    backend_compat = dict(backend_compat or {})

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

        previous_output_summary = load_previous_output_summary(
            root, corpus_id, exclude_artifact_ref=artifact.get("path")
        )
    material_refs = [str(item) for item in artifact.get("material_refs", []) if str(item).strip()]
    material_context_refs: list[str] = []
    material_context = str(artifact.get("material_context") or "").strip()
    if material_context:
        material_context_refs = _context_ref_paths(
            [record for record in artifact.get("used_context_refs", []) if isinstance(record, dict)]
        )
        if not material_context_refs:
            material_context_refs = list(dict.fromkeys(material_refs))
    if not material_context:
        material_context_payload = _read_material_context(root, material_refs, max_chars=12000) if material_refs else {}
        material_context = str(material_context_payload.get("text") or "")
        material_context_refs = _context_ref_paths(
            [record for record in material_context_payload.get("used_context_refs", []) if isinstance(record, dict)]
        )
    provenance_event_fields: dict[str, Any] = {}
    if material_refs:
        provenance_event_fields["material_refs"] = material_refs
    if material_context_refs:
        provenance_event_fields["used_context_refs"] = material_context_refs
    compound_paths = [f"wiki/judgments/{page_id}.md" for page_id, _content in prepared.get("judgment_pages", [])] + [
        f"wiki/elixirs/{elixir_id}.md" for elixir_id, _content in prepared.get("elixir_pages", [])
    ]
    if not compound_paths:
        compound_paths = [
            str(ref).strip()
            for ref in artifact.get("used_refs", []) or []
            if str(ref).startswith(("wiki/judgments/", "wiki/elixirs/"))
        ]
    used_refs = build_ask_used_refs(
        ranked_sources=[{"id": source_id} for source_id in source_ids],
        ranked_concepts=[{"slug": slug} for slug in artifact.get("ranked_concepts", [])],
        compound_paths=compound_paths,
        material_paths=material_context_refs,
    )
    if used_refs:
        provenance_event_fields["used_refs"] = used_refs
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
        material_context=material_context,
        prompt_profile=prompt_profile,
        judgment_pages=prepared.get("judgment_pages", []),
        elixir_pages=prepared.get("elixir_pages", []),
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
                        material_context=material_context,
                        prompt_profile=retry_profile,
                        judgment_pages=prepared.get("judgment_pages", []),
                        elixir_pages=prepared.get("elixir_pages", []),
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
                updated = _strip_report_skeleton_reference_hints(updated)
                updated = _append_visible_quoted_report_refs(updated, material_context_refs or material_refs)
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
        with runtime_write_lock(root):
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
                    **provenance_event_fields,
                },
                failed_audit,
                status="failed",
                error=str(exc),
                response_id=getattr(result, "response_id", "") if result is not None else "",
                usage=getattr(result, "usage", {}) if result is not None else {},
                raw_response_path=_raw_response_path(root, result, exc),
                error_class=_receipt_error_class(exc),
            )
            llm_status = _run_ask_failure_llm_status(exc)
            _mark_run_ask_artifact_degraded(
                target,
                reason=str(exc),
                backend=str(failed_audit.get("backend_effective") or ""),
                model=str(failed_audit.get("model_final") or ""),
                llm_status=llm_status,
            )
            _restore_run_ask_provenance_frontmatter(
                target,
                current_artifact,
                material_refs=material_refs,
                used_context_refs=material_context_refs,
                used_refs=used_refs,
            )
            _apply_graph_anchors_to_target()
            run_notes = write_run_notes(
                root,
                run_id=str(artifact.get("run_id") or ""),
                status="llm-failed",
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
                    "The LLM run failed or timed out.",
                    "Recorded failure metadata without writing a fallback answer.",
                ],
                context_refs=material_context_refs,
            )
            write_run_notes_frontmatter(target, run_id=run_notes["run_id"], run_notes_ref=run_notes["run_notes_path"])
            _ensure_output_cssclass(target)
            _refresh_shell_summary_fail_soft(root)
        raise

    assert result is not None
    with runtime_write_lock(root):
        target_snapshot = _snapshot_file_bytes(target)
        atomic_write_text(target, updated)
        artifact_ref = str(artifact.get("path") or "")
        run_id = str(artifact.get("run_id") or run_id_for_artifact(artifact_ref))
        planned_receipt_path = _planned_run_ask_output_receipt_ref(root, artifact_ref=artifact_ref, run_id=run_id)
        notes_path = run_notes_file_path(root, run_id)
        notes_snapshot = _snapshot_file_bytes(notes_path)
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
            _restore_run_ask_provenance_frontmatter(
                target,
                current_artifact,
                material_refs=material_refs,
                used_context_refs=material_context_refs,
                used_refs=used_refs,
            )
            reinject_candidate_frontmatter(target, corpus_id=str(artifact.get("active_corpus_id") or ""))
            _apply_graph_anchors_to_target()
            _stamped_record(
                {
                    "event": "run-ask",
                    "target": artifact_ref,
                    "question": question,
                    "format": output_format,
                    "protocol": artifact.get("protocol", ""),
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "prompt_profile": retry_profile or used_prompt_profile,
                    "retry_prompt_profile": retry_profile,
                    "no_cache": no_cache,
                    **provenance_event_fields,
                },
                llm_audit,
                status="success",
                response_id=result.response_id,
                usage=result.usage,
                raw_response_path=_raw_response_path(root, result),
            )
            run_notes = write_run_notes(
                root,
                run_id=run_id,
                status="llm-complete",
                question=question,
                output_format=output_format,
                protocol=str(artifact.get("protocol") or ""),
                output_path=artifact_ref,
                source_count=len(source_ids),
                concept_count=len(artifact.get("ranked_concepts", [])),
                receipt_path=planned_receipt_path,
                backend=backend_effective,
                model=model_final,
                fallback_stage=fallback_stage,
                stages=[
                    "Prepared deterministic context for the request.",
                    "Requested an LLM draft using the selected backend and prompt profile.",
                    "Validated the returned markdown contract and updated the output artifact.",
                    "Recorded authoritative execution receipt and LLM attempt metadata for audit and recovery.",
                ],
                context_refs=material_context_refs,
            )
            write_run_notes_frontmatter(target, run_id=run_notes["run_id"], run_notes_ref=run_notes["run_notes_path"])
            _ensure_output_cssclass(target)
            _write_run_ask_output_receipt(
                root,
                generated_by="aiwiki-run-ask",
                artifact_ref=artifact_ref,
                run_id=run_id,
                question=question,
                output_format=output_format,
                protocol=str(artifact.get("protocol") or ""),
                delivery_mode="llm-complete",
                run_ask_path="report",
                extra={
                    "backend_effective": backend_effective,
                    "model_final": model_final,
                    "fallback_stage": fallback_stage,
                    "response_id": result.response_id,
                    "usage": result.usage,
                    **provenance_event_fields,
                },
            )
            notify_report_generated(
                root,
                {
                    "path": artifact_ref,
                    "title": question,
                    "protocol": str(artifact.get("protocol") or protocol or ""),
                    "format": output_format,
                    "created_at": str(artifact.get("created_at") or ""),
                },
            )
            _refresh_shell_summary_fail_soft(root)
        except Exception:
            _restore_file_bytes(target, target_snapshot)
            _restore_file_bytes(notes_path, notes_snapshot)
            raise
        payload = {
            **artifact,
            **run_notes,
            **llm_audit,
            "prompt_profile": retry_profile or used_prompt_profile,
            "retry_prompt_profile": retry_profile,
            "timeout_seconds": effective_timeout_seconds,
            "no_cache": no_cache,
        }
        return payload


def run_ask(
    root: Path,
    question: str,
    output_format: str,
    protocol: str | None = None,
    client: SupportsComplete | None = None,
    lean: bool = False,
    timeout_seconds: int | None = None,
    no_cache: bool = False,
    corpus_id_override: str | None = None,
) -> dict[str, Any]:
    """Run ask with LLM synthesis outside the single-writer lock.

    ``ask_question`` still takes the write lock for deterministic scaffold;
    network ``complete()`` runs unlocked inside ``_complete_run_ask_artifact``.
    """
    ensure_layout(root)
    if is_obsidian_open_link(question):
        raise ValueError("obsidian open links are navigation targets, not questions")
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("run-ask timeout_seconds must be greater than 0.")
    effective_timeout_seconds = _effective_run_ask_timeout(output_format, timeout_seconds)
    backend_compat: dict[str, Any] = {}
    if client is None:
        from aiwiki.runner.preflight import preflight_check_backend

        backend_compat = preflight_check_backend(root)
    material_refs = _material_hint_paths(question)
    material_refs.extend(_quoted_report_material_refs(root, question))
    material_refs = list(dict.fromkeys(material_refs))
    clean_question = _clean_report_reference_question(question) if material_refs else question
    ask_kwargs = {"protocol": protocol, "no_cache": no_cache, "write_graph_anchors": False, "notify": False}
    if corpus_id_override is not None:
        ask_kwargs["corpus_id_override"] = corpus_id_override
    artifact = ask_question(root, clean_question, output_format, **ask_kwargs)
    if material_refs:
        artifact["material_refs"] = material_refs
    return _complete_run_ask_artifact(
        root,
        artifact=artifact,
        question=clean_question,
        output_format=output_format,
        protocol=protocol,
        client=client,
        lean=lean,
        timeout_seconds=effective_timeout_seconds,
        no_cache=no_cache,
        backend_compat=backend_compat,
    )
