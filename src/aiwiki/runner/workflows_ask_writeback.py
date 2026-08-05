"""Write-back helpers for run-ask success / failure / unreadable-material paths.

Extracted from ``workflows_ask`` (hub single seam 2026-08-05 P1).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from aiwiki.execution.paths import run_notes_path as run_notes_file_path
from aiwiki.execution.run_notes import run_id_for_artifact, write_run_notes, write_run_notes_frontmatter
from aiwiki.llm import CompletionResult
from aiwiki.memory.state import load_machine_memory
from aiwiki.notify import notify_report_generated
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
            planned_receipt_path = _planned_run_ask_output_receipt_ref(root, artifact_ref=artifact_ref, run_id=run_id)
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
            run_notes = write_run_notes(
                root,
                run_id=run_id,
                status="llm-degraded",
                question=question,
                output_format=output_format,
                protocol=str(artifact.get("protocol") or ""),
                output_path=artifact_ref,
                source_count=0,
                concept_count=0,
                receipt_path=planned_receipt_path,
                backend=str(backend_requested or ""),
                model=str(model_selected or ""),
                fallback_stage="",
                stages=[
                    "Detected explicit material refs with no readable textual context.",
                    "Wrote an honest short answer without synthesizing unrelated wiki sources.",
                ],
                context_refs=[],
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
    """Persist the validated LLM output plus receipts / run notes, then return the payload."""

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


