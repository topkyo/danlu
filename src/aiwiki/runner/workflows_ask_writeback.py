"""Write-back helpers for run-ask success / failure / unreadable-material paths.

Extracted from ``workflows_ask`` (hub single seam 2026-08-05 P1).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from aiwiki.execution.run_notes import run_id_for_artifact, write_run_notes_frontmatter
from aiwiki.llm import CompletionResult
from aiwiki.memory.state import load_machine_memory
from aiwiki.notify import notify_report_generated
from aiwiki.runner.ask_quality import filter_web_refs_in_body
from aiwiki.runner.clients import (
    _client_backend_name,
    _client_model_name,
    _fallback_stage_label,
)
from aiwiki.runner.interfaces import SupportsComplete
from aiwiki.runner.receipts import record_llm_attempt
from aiwiki.runner.workflow_shared import _raw_response_path, _receipt_error_class, reinject_candidate_frontmatter
from aiwiki.runner.workflows_ask_context import (
    _build_unreadable_material_ask_markdown,
)
from aiwiki.runner.workflows_ask_frontmatter import (
    _ensure_output_cssclass,
    _restore_run_ask_provenance_frontmatter,
)
from aiwiki.runner.workflows_ask_receipts import (
    _planned_run_ask_output_receipt_ref,
    _refresh_shell_summary_fail_soft,
    _write_run_ask_output_receipt,
)
from aiwiki.runner.workflows_ask_status import (
    _mark_run_ask_artifact_degraded,
    _run_ask_failure_llm_status,
    _stamp_run_ask_artifact_complete,
)
from aiwiki.utils.io import (
    _restore_file_bytes,
    _snapshot_file_bytes,
    atomic_write_text,
    runtime_write_lock,
)
from aiwiki.utils.markdown import parse_frontmatter


def _web_search_receipt_fields(result: CompletionResult) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "web_search_used": bool(result.web_search_used),
        "used_web_refs": list(result.used_web_refs),
    }
    if result.web_search_calls:
        fields["web_search_calls"] = list(result.web_search_calls)
    return fields


def _stamped_record(
    root: Path,
    backend_compat: dict[str, Any],
    base_event: dict[str, Any],
    llm_audit: dict[str, Any],
    **kwargs: Any,
) -> None:
    if backend_compat:
        base_event = dict(base_event)
        base_event["backend_compat"] = dict(backend_compat)
    record_llm_attempt(root, base_event, llm_audit, **kwargs)


def _apply_graph_anchors_to_target(root: Path, target: Path, artifact: dict[str, Any]) -> None:
    anchors = [str(item) for item in artifact.get("graph_anchor_node_ids", []) if str(item).strip()]
    if not anchors:
        return
    from aiwiki.execution.ask import apply_graph_anchors_to_artifact

    apply_graph_anchors_to_artifact(target, anchors=anchors, memory=load_machine_memory(root))


def _write_run_ask_material_unreadable(
    root: Path,
    *,
    artifact: dict[str, Any],
    question: str,
    output_format: str,
    no_cache: bool,
    backend_requested: str,
    model_selected: str,
    material_refs: list[str],
    provenance_event_fields: dict[str, Any],
    target: Path,
    current_artifact: str,
    backend_compat: dict[str, Any],
    effective_client: SupportsComplete,
    timeout_seconds: int | None,
) -> dict[str, Any]:
    """Write the honest degraded artifact when explicit material refs are unreadable."""

    started = time.monotonic()
    with runtime_write_lock(root):
        target_snapshot = _snapshot_file_bytes(target)
        current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        frontmatter = parse_frontmatter(current)
        frontmatter.update(
            {
                "llm_status": "material_unreadable",
                "delivery_mode": "llm-degraded",
                "material_refs": material_refs,
                "used_context_refs": [],
                "used_refs": material_refs,
                "llm_backend": backend_requested,
                "llm_model": model_selected,
            }
        )
        updated = _build_unreadable_material_ask_markdown(
            question=question,
            material_refs=material_refs,
            frontmatter=frontmatter,
        )
        try:
            atomic_write_text(target, updated)
            artifact_ref = str(artifact.get("path") or "")
            run_id = str(artifact.get("run_id") or run_id_for_artifact(artifact_ref))
            llm_audit = {
                "backend_requested": backend_requested,
                "backend_effective": backend_requested,
                "model_selected": model_selected,
                "model_final": model_selected,
                "fallback_stage": "",
                "fallback_reason": "material_unreadable",
                "contract_validated": True,
                "delivery_mode": "llm-degraded",
            }
            _restore_run_ask_provenance_frontmatter(
                target,
                current_artifact,
                material_refs=material_refs,
                used_context_refs=[],
                used_refs=material_refs,
            )
            reinject_candidate_frontmatter(target, corpus_id=str(artifact.get("active_corpus_id") or ""))
            _apply_graph_anchors_to_target(root, target, artifact)
            _stamped_record(
                root,
                backend_compat,
                {
                    "event": "run-ask",
                    "target": artifact_ref,
                    "question": question,
                    "format": output_format,
                    "protocol": artifact.get("protocol", ""),
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "prompt_profile": "skipped-unreadable-material",
                    "retry_prompt_profile": "",
                    "no_cache": no_cache,
                    **provenance_event_fields,
                    "used_context_refs": [],
                    "used_refs": material_refs,
                },
                llm_audit,
                status="success",
                response_id="",
                usage={},
                raw_response_path="",
            )
            write_run_notes_frontmatter(target, run_id=run_id)
            run_notes = {"run_id": run_id, "run_notes_path": ""}
            _ensure_output_cssclass(target)
            _write_run_ask_output_receipt(
                root,
                generated_by="aiwiki-run-ask",
                artifact_ref=artifact_ref,
                run_id=run_id,
                question=question,
                output_format=output_format,
                protocol=str(artifact.get("protocol") or ""),
                delivery_mode="llm-degraded",
                run_ask_path="report",
                extra={
                    "backend_effective": backend_requested,
                    "model_final": model_selected,
                    "fallback_stage": "",
                    "response_id": "",
                    "usage": {},
                    **provenance_event_fields,
                    "used_context_refs": [],
                    "used_refs": material_refs,
                    "llm_status": "material_unreadable",
                },
            )
            _refresh_shell_summary_fail_soft(root)
        except Exception:
            # restore-then-raise (not silent swallow): undo partial artifact write
            _restore_file_bytes(target, target_snapshot)
            raise
        return {
            **artifact,
            **run_notes,
            **llm_audit,
            "prompt_profile": "skipped-unreadable-material",
            "retry_prompt_profile": "",
            "timeout_seconds": getattr(getattr(effective_client, "config", None), "timeout_seconds", timeout_seconds),
            "no_cache": no_cache,
        }


def _record_run_ask_failure(
    root: Path,
    *,
    artifact: dict[str, Any],
    question: str,
    output_format: str,
    no_cache: bool,
    exc: Exception,
    result: CompletionResult | None,
    started: float,
    effective_client: SupportsComplete,
    backend_requested: str,
    model_selected: str,
    fallback_stages: list[str],
    fallback_reason: str,
    retry_profile: str,
    used_prompt_profile: str,
    provenance_event_fields: dict[str, Any],
    target: Path,
    current_artifact: str,
    material_refs: list[str],
    material_context_refs: list[str],
    used_refs: list[str],
    source_ids: list[str],
    backend_compat: dict[str, Any],
) -> None:
    """Record failure receipt / degraded artifact / run notes; caller re-raises ``exc``."""

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
            root,
            backend_compat,
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
        _apply_graph_anchors_to_target(root, target, artifact)
        artifact_ref = str(artifact.get("path") or "")
        run_id = str(artifact.get("run_id") or run_id_for_artifact(artifact_ref))
        write_run_notes_frontmatter(target, run_id=run_id)
        _ensure_output_cssclass(target)
        _refresh_shell_summary_fail_soft(root)


def _run_ask_success_llm_audit(
    *,
    effective_client: SupportsComplete,
    backend_requested: str,
    model_selected: str,
    fallback_stages: list[str],
    fallback_reason: str,
) -> dict[str, Any]:
    return {
        "backend_requested": backend_requested,
        "backend_effective": _client_backend_name(effective_client),
        "model_selected": model_selected,
        "model_final": _client_model_name(effective_client),
        "fallback_stage": _fallback_stage_label(fallback_stages),
        "fallback_reason": fallback_reason,
        "contract_validated": True,
    }


def _commit_run_ask_success_mutations(
    root: Path,
    *,
    target: Path,
    artifact: dict[str, Any],
    question: str,
    output_format: str,
    protocol: str | None,
    no_cache: bool,
    result: CompletionResult,
    started: float,
    retry_profile: str,
    used_prompt_profile: str,
    provenance_event_fields: dict[str, Any],
    current_artifact: str,
    material_refs: list[str],
    material_context_refs: list[str],
    used_refs: list[str],
    source_ids: list[str],
    backend_compat: dict[str, Any],
    artifact_ref: str,
    run_id: str,
    planned_receipt_path: str,
    llm_audit: dict[str, Any],
) -> dict[str, Any]:
    """Frontmatter / receipts / run-notes / notify for a validated LLM success write."""

    backend_effective = str(llm_audit["backend_effective"])
    model_final = str(llm_audit["model_final"])
    fallback_stage = str(llm_audit["fallback_stage"])
    web_search_fields = _web_search_receipt_fields(result)
    used_web_refs = filter_web_refs_in_body(target.read_text(encoding="utf-8", errors="replace"), list(result.used_web_refs))
    web_search_fields["used_web_refs"] = used_web_refs
    _restore_run_ask_provenance_frontmatter(
        target,
        current_artifact,
        material_refs=material_refs,
        used_context_refs=material_context_refs,
        used_refs=used_refs,
        web_search_used=bool(result.web_search_used),
        used_web_refs=used_web_refs,
    )
    reinject_candidate_frontmatter(target, corpus_id=str(artifact.get("active_corpus_id") or ""))
    _apply_graph_anchors_to_target(root, target, artifact)
    _stamped_record(
        root,
        backend_compat,
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
            **web_search_fields,
        },
        llm_audit,
        status="success",
        response_id=result.response_id,
        usage=result.usage,
        raw_response_path=_raw_response_path(root, result),
    )
    write_run_notes_frontmatter(target, run_id=run_id)
    run_notes = {"run_id": run_id, "run_notes_path": ""}
    _stamp_run_ask_artifact_complete(
        target,
        backend=backend_effective,
        model=model_final,
    )
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
            **web_search_fields,
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
    return run_notes


def _write_run_ask_success(
    root: Path,
    *,
    artifact: dict[str, Any],
    question: str,
    output_format: str,
    protocol: str | None,
    no_cache: bool,
    updated: str,
    result: CompletionResult,
    started: float,
    effective_client: SupportsComplete,
    backend_requested: str,
    model_selected: str,
    fallback_stages: list[str],
    fallback_reason: str,
    retry_profile: str,
    used_prompt_profile: str,
    effective_timeout_seconds: int | None,
    provenance_event_fields: dict[str, Any],
    target: Path,
    current_artifact: str,
    material_refs: list[str],
    material_context_refs: list[str],
    used_refs: list[str],
    source_ids: list[str],
    backend_compat: dict[str, Any],
) -> dict[str, Any]:
    """Lock, write LLM markdown, commit mutations (or restore), return payload."""

    with runtime_write_lock(root):
        target_snapshot = _snapshot_file_bytes(target)
        atomic_write_text(target, updated)
        artifact_ref = str(artifact.get("path") or "")
        run_id = str(artifact.get("run_id") or run_id_for_artifact(artifact_ref))
        planned_receipt_path = _planned_run_ask_output_receipt_ref(root, artifact_ref=artifact_ref, run_id=run_id)
        llm_audit = _run_ask_success_llm_audit(
            effective_client=effective_client,
            backend_requested=backend_requested,
            model_selected=model_selected,
            fallback_stages=fallback_stages,
            fallback_reason=fallback_reason,
        )
        try:
            run_notes = _commit_run_ask_success_mutations(
                root,
                target=target,
                artifact=artifact,
                question=question,
                output_format=output_format,
                protocol=protocol,
                no_cache=no_cache,
                result=result,
                started=started,
                retry_profile=retry_profile,
                used_prompt_profile=used_prompt_profile,
                provenance_event_fields=provenance_event_fields,
                current_artifact=current_artifact,
                material_refs=material_refs,
                material_context_refs=material_context_refs,
                used_refs=used_refs,
                source_ids=source_ids,
                backend_compat=backend_compat,
                artifact_ref=artifact_ref,
                run_id=run_id,
                planned_receipt_path=planned_receipt_path,
                llm_audit=llm_audit,
            )
        except Exception:
            # restore-then-raise (not silent swallow): undo target partial writes
            _restore_file_bytes(target, target_snapshot)
            raise
        return {
            **artifact,
            **run_notes,
            **llm_audit,
            "used_refs": used_refs,
            "prompt_profile": retry_profile or used_prompt_profile,
            "retry_prompt_profile": retry_profile,
            "timeout_seconds": effective_timeout_seconds,
            "no_cache": no_cache,
        }


