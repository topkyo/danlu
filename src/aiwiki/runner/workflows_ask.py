"""LLM-backed ask workflows: run-ask, background jobs, direct ask."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiwiki.app_compile import ask_question
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_queries import human_query_title
from aiwiki.app_state import load_machine_memory, load_manifest
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
    tokenize,
    utc_now,
)
from aiwiki.execution.ask import _output_artifact_seed
from aiwiki.execution.receipts import write_execution_receipt
from aiwiki.execution.run_notes import run_id_for_artifact, write_run_notes, write_run_notes_frontmatter
from aiwiki.llm import CompletionResult, LLMError, classify_backend_error
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
from aiwiki.runner.local_stats import (
    OUTPUT_OBSIDIAN_CSSCLASS,
    OUTPUT_REPORT_LEAF_CSSCLASS,
    clean_local_intent_question,
    clean_report_reference_question,
    collect_elixir_counts,
    collect_markdown_counts,
    is_elixir_count_question,
    is_markdown_count_question,
    local_elixir_count_artifact_markdown,
    local_markdown_count_artifact_markdown,
)
from aiwiki.runner.prompts import (
    _build_ask_prompt,
    _dedupe_report_citations,
    _normalize_markdown,
    _retry_ask_prompt_profile,
    _select_initial_ask_prompt_profile,
    _system_prompt,
    _validate_output_markdown,
)
from aiwiki.runner.receipts import (
    _build_llm_audit,
    _empty_llm_audit,
    _llm_audit_from_result,
    _merge_llm_audits,
    record_llm_attempt,
)
from aiwiki.runner.workflow_shared import (
    DEFAULT_REPORT_TIMEOUT_SECONDS,
    _raw_response_path,
    _receipt_error_class,
    reinject_candidate_frontmatter,
)

_logger = logging.getLogger(__name__)

_REPORT_REFERENCE_RE = re.compile(
    r"引用报告\s*[:：]\s*(?:`?)(output/reports/[^\s`]+(?:\.md)?)(?:`?)",
    flags=re.IGNORECASE,
)

def _effective_run_ask_timeout(output_format: str, timeout_seconds: int | None) -> int | None:
    if timeout_seconds is not None:
        return timeout_seconds
    if output_format == "report" and not os.environ.get("AIWIKI_LLM_TIMEOUT", "").strip():
        return DEFAULT_REPORT_TIMEOUT_SECONDS
    return None

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

def _ensure_output_cssclass(target: Path) -> None:
    """Ensure generated output hides Obsidian properties without dropping audit metadata."""

    if not target.exists():
        raise FileNotFoundError(f"output artifact not found: {target}")
    original = target.read_text(encoding="utf-8", errors="replace")
    lines = original.splitlines()
    has_frontmatter = bool(lines) and lines[0].strip() == "---"
    close_idx: int | None = None
    if has_frontmatter:
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                close_idx = idx
                break
    if not has_frontmatter or close_idx is None:
        updated = render_frontmatter({"cssclasses": [OUTPUT_OBSIDIAN_CSSCLASS]}).splitlines() + lines
        target.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
        return
    current = parse_frontmatter(original)
    raw_classes = current.get("cssclasses", [])
    classes = [str(item).strip() for item in raw_classes if str(item).strip()] if isinstance(raw_classes, list) else []
    if isinstance(raw_classes, str) and raw_classes.strip():
        classes = [raw_classes.strip()]
    if OUTPUT_OBSIDIAN_CSSCLASS in classes:
        needs_report_leaf = "output/reports/" in target.as_posix() and OUTPUT_REPORT_LEAF_CSSCLASS not in classes
        if not needs_report_leaf:
            return
    else:
        classes.append(OUTPUT_OBSIDIAN_CSSCLASS)
    if "output/reports/" in target.as_posix() and OUTPUT_REPORT_LEAF_CSSCLASS not in classes:
        classes.append(OUTPUT_REPORT_LEAF_CSSCLASS)
    header = _drop_frontmatter_keys(lines[1:close_idx], {"cssclasses"})
    css_lines = _runtime_provenance_field_lines({"cssclasses": classes})
    updated_lines = [lines[0], *header, *css_lines, lines[close_idx], *lines[close_idx + 1 :]]
    target.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")

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
    material_context = str(artifact.get("material_context") or "").strip()
    if not material_context:
        material_refs = [str(item) for item in artifact.get("material_refs", []) if str(item).strip()]
        material_context = _read_material_context_snippets(root, material_refs, max_chars=12000) if material_refs else ""
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
        )
        write_run_notes_frontmatter(target, run_id=run_notes["run_id"], run_notes_ref=run_notes["run_notes_path"])
        _ensure_output_cssclass(target)
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
        reinject_candidate_frontmatter(target, corpus_id=str(artifact.get("active_corpus_id") or ""))
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
    _ensure_output_cssclass(target)
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
    corpus_id_override: str | None = None,
    spawn: bool = True,
) -> dict[str, Any]:
    """Prepare a long-running report job and optionally spawn background resume."""

    ensure_layout(root)
    if output_format != "report":
        raise ValueError("run-ask-submit is only supported for report output.")
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("run-ask-submit timeout_seconds must be greater than 0.")
    effective_timeout_seconds = _effective_run_ask_timeout(output_format, timeout_seconds)

    from aiwiki.runner.preflight import preflight_check_backend_chain

    backend_compat = preflight_check_backend_chain(root)
    material_refs = _material_hint_paths(question)
    material_refs.extend(_safe_quoted_report_reference_paths(root, _quoted_report_reference_paths(question)))
    material_refs = list(dict.fromkeys(material_refs))
    clean_question = _clean_report_reference_question(question) if material_refs else question
    ask_kwargs = {"protocol": protocol, "no_cache": no_cache, "write_graph_anchors": False}
    if corpus_id_override is not None:
        ask_kwargs["corpus_id_override"] = corpus_id_override
    artifact = ask_question(root, clean_question, output_format, **ask_kwargs)
    if material_refs:
        artifact["material_refs"] = material_refs
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
        "question": clean_question,
        "raw_question": question,
        "output_format": output_format,
        "protocol": protocol or "",
        "lean": lean,
        "timeout_seconds": effective_timeout_seconds,
        "no_cache": no_cache,
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
        "question": clean_question,
        "raw_question": question,
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
    """Replace the deterministic placeholder artifact with an explicit failed notice."""

    current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    frontmatter = parse_frontmatter(current)
    title = "LLM 失败：请重试或切换模型"
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
            "delivery_mode": "llm-failed",
            "background_status": "failed",
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
        "- LLM 没有返回可用内容；本文件是失败说明，不是最终报告，也不是 fallback 占位答案。",
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
        "cssclasses": [OUTPUT_OBSIDIAN_CSSCLASS],
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

def _quoted_report_reference_paths(question: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for match in _REPORT_REFERENCE_RE.finditer(str(question or "")):
        path = match.group(1).strip().strip("` ")
        if not path or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths

def _safe_quoted_report_reference_paths(root: Path, refs: list[str]) -> list[str]:
    safe_refs: list[str] = []
    seen: set[str] = set()
    try:
        root_resolved = root.resolve()
        reports_root = (root / "output" / "reports").resolve()
    except OSError:
        return []
    for ref in refs:
        text = str(ref or "").strip().strip("` ")
        if not text or "\\" in text or text.startswith("/"):
            continue
        if not text.startswith("output/reports/") or not text.endswith(".md"):
            continue
        candidate = root / text
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root_resolved)
            resolved.relative_to(reports_root)
        except (OSError, ValueError):
            continue
        if resolved.suffix.lower() != ".md":
            continue
        if text in seen:
            continue
        seen.add(text)
        safe_refs.append(text)
    return safe_refs

def _clean_report_reference_question(question: str) -> str:
    return clean_report_reference_question(question)

def _clean_local_intent_question(question: str) -> str:
    return clean_local_intent_question(question)

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
    try:
        root_resolved = root.resolve()
    except OSError:
        root_resolved = root
    for ref in refs:
        if remaining <= 0:
            break
        path = root / ref
        try:
            path = path.resolve()
            path.relative_to(root_resolved)
        except (OSError, ValueError):
            continue
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

def _question_terms(question: str) -> set[str]:
    text = _clean_report_reference_question(question).lower()
    terms = set(tokenize(text))
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(chunk) <= 8:
            terms.add(chunk)
        for size in range(2, min(6, len(chunk)) + 1):
            for index in range(0, len(chunk) - size + 1):
                term = chunk[index : index + size]
                if term not in {"当前", "哪些", "多少", "一下", "关系", "相关"}:
                    terms.add(term)
    return {term for term in terms if len(term) >= 2}

def _collect_vault_knowledge_context(root: Path, question: str, *, max_refs: int = 6, max_chars: int = 9000) -> str:
    terms = _question_terms(question)
    if not terms:
        return ""
    search_roots = [root / "wiki" / name for name in ("sources", "judgments", "decisions", "concepts", "elixirs")]
    scored: list[tuple[int, str, str]] = []
    for directory in search_roots:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            try:
                relative = relative_path(root, path)
            except ValueError:
                continue
            text = strip_frontmatter(path.read_text(encoding="utf-8", errors="replace")).strip()
            if not text:
                continue
            haystack = f"{relative}\n{text}".lower()
            score = sum(haystack.count(term.lower()) for term in terms)
            if score <= 0:
                continue
            scored.append((score, relative, text))
    scored.sort(key=lambda item: (-item[0], item[1]))
    snippets: list[str] = []
    remaining = max_chars
    for _score, relative, text in scored[:max_refs]:
        if remaining <= 0:
            break
        excerpt = text[:remaining]
        snippets.append(f"## {relative}\n\n{excerpt}")
        remaining -= len(excerpt)
    context = "\n\n".join(snippets).strip()
    if context and any(marker in _clean_report_reference_question(question) for marker in ("联网", "网上", "web", "搜索", "调研")):
        context = (
            "## runtime-note\n\n当前 runtime 未配置实时联网检索结果；以下是本地 vault 可访问的知识摘录。"
            "回答时不要声称已联网，只能基于这些本地材料给出分析，并明确联网缺口。\n\n"
            + context
        )
    return context

def _material_direct_system_prompt() -> str:
    return (
        "你是炼丹炉的材料问答助手。用户会给出一个问题和已经抽取成文本的材料摘录。"
        "请优先依据材料回答，用中文给出直接结论和关键依据；如果材料不足，明确说明不足。"
        "不要编造未在材料中出现的事实。材料可能来自用户引用的报告、投料文件，或 runtime 自动检索到的本地 vault 页面。"
    )

def _material_direct_user_prompt(question: str, context: str) -> str:
    title = human_query_title(question)
    return f"用户问题：{title}\n\n材料摘录：\n{context}"

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
    corpus_id_override: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("run-ask timeout_seconds must be greater than 0.")
    effective_timeout_seconds = _effective_run_ask_timeout(output_format, timeout_seconds)
    backend_compat: dict[str, Any] = {}

    def _stamped_record(base_event: dict[str, Any], llm_audit: dict[str, Any], **kwargs: Any) -> None:
        if backend_compat:
            base_event = dict(base_event)
            base_event["backend_compat"] = dict(backend_compat)
        record_llm_attempt(root, base_event, llm_audit, **kwargs)

    material_refs = _material_hint_paths(question)
    material_refs.extend(_safe_quoted_report_reference_paths(root, _quoted_report_reference_paths(question)))
    material_refs = list(dict.fromkeys(material_refs))
    material_context = _read_material_context_snippets(root, material_refs) if material_refs else ""
    if output_format == "note" and is_elixir_count_question(question):
        from aiwiki.app_protocol import resolve_protocol

        active_protocol = resolve_protocol(root, protocol)
        directory = root / "output" / "reports"
        directory.mkdir(parents=True, exist_ok=True)
        artifact_seed = _output_artifact_seed(_clean_local_intent_question(question), "note")
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        artifact_ref = relative_path(root, destination)
        stats = collect_elixir_counts(root)
        destination.write_text(
            local_elixir_count_artifact_markdown(
                artifact_id=artifact_id,
                question=question,
                protocol=active_protocol,
                created_at=utc_now(),
                stats=stats,
            ),
            encoding="utf-8",
        )
        run_id = run_id_for_artifact(artifact_ref)
        run_notes = write_run_notes(
            root,
            run_id=run_id,
            status="local-deterministic-complete",
            question=question,
            output_format="note",
            protocol=active_protocol,
            output_path=artifact_ref,
            receipt_path=".aiwiki/logs/llm-receipts.jsonl",
            backend="local",
            model="elixir-stats",
            stages=[
                "Detected a local elixir count question before the direct LLM path.",
                "Counted settled and candidate elixir markdown files deterministically.",
            ],
        )
        write_run_notes_frontmatter(destination, run_id=run_notes["run_id"], run_notes_ref=run_notes["run_notes_path"])
        _ensure_output_cssclass(destination)
        _stamped_record(
            {
                "event": "run-ask-local-elixir-stats",
                "target": artifact_ref,
                "question": question,
                "clean_question": _clean_local_intent_question(question),
                "format": "note",
                "protocol": active_protocol,
                "settled_elixir_count": len(stats.get("settled", [])),
                "candidate_elixir_count": len(stats.get("candidates", [])),
            },
            {
                "backend_requested": "local",
                "backend_effective": "local",
                "model_selected": "elixir-stats",
                "model_final": "elixir-stats",
                "fallback_stage": "",
                "fallback_reason": "",
                "contract_validated": True,
                "delivery_mode": "local-deterministic",
            },
            status="success",
        )
        return {
            "path": artifact_ref,
            "format": "note",
            "protocol": active_protocol,
            "question": question,
            "clean_question": _clean_local_intent_question(question),
            "status": "success",
            "delivery_mode": "local-deterministic",
            "settled_elixir_count": len(stats.get("settled", [])),
            "candidate_elixir_count": len(stats.get("candidates", [])),
            "run_id": run_notes["run_id"],
            "run_notes_path": run_notes["run_notes_path"],
            "no_cache": no_cache,
            "contract_validated": True,
        }
    if output_format == "note" and is_markdown_count_question(question):
        from aiwiki.app_protocol import resolve_protocol

        active_protocol = resolve_protocol(root, protocol)
        directory = root / "output" / "reports"
        directory.mkdir(parents=True, exist_ok=True)
        artifact_seed = _output_artifact_seed(_clean_local_intent_question(question), "note")
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        artifact_ref = relative_path(root, destination)
        stats = collect_markdown_counts(root)
        destination.write_text(
            local_markdown_count_artifact_markdown(
                artifact_id=artifact_id,
                question=question,
                protocol=active_protocol,
                created_at=utc_now(),
                stats=stats,
            ),
            encoding="utf-8",
        )
        run_id = run_id_for_artifact(artifact_ref)
        run_notes = write_run_notes(
            root,
            run_id=run_id,
            status="local-deterministic-complete",
            question=question,
            output_format="note",
            protocol=active_protocol,
            output_path=artifact_ref,
            receipt_path=".aiwiki/logs/llm-receipts.jsonl",
            backend="local",
            model="markdown-stats",
            stages=[
                "Detected a local markdown count question before the direct LLM path.",
                "Counted visible markdown files deterministically inside the vault.",
            ],
        )
        write_run_notes_frontmatter(destination, run_id=run_notes["run_id"], run_notes_ref=run_notes["run_notes_path"])
        _ensure_output_cssclass(destination)
        _stamped_record(
            {
                "event": "run-ask-local-markdown-stats",
                "target": artifact_ref,
                "question": question,
                "clean_question": _clean_local_intent_question(question),
                "format": "note",
                "protocol": active_protocol,
                "markdown_file_count": int(stats.get("total") or 0),
            },
            {
                "backend_requested": "local",
                "backend_effective": "local",
                "model_selected": "markdown-stats",
                "model_final": "markdown-stats",
                "fallback_stage": "",
                "fallback_reason": "",
                "contract_validated": True,
                "delivery_mode": "local-deterministic",
            },
            status="success",
        )
        return {
            "path": artifact_ref,
            "format": "note",
            "protocol": active_protocol,
            "question": question,
            "clean_question": _clean_local_intent_question(question),
            "status": "success",
            "delivery_mode": "local-deterministic",
            "markdown_file_count": int(stats.get("total") or 0),
            "run_id": run_notes["run_id"],
            "run_notes_path": run_notes["run_notes_path"],
            "no_cache": no_cache,
            "contract_validated": True,
        }
    if client is None:
        from aiwiki.runner.preflight import preflight_check_backend

        backend_compat = preflight_check_backend(root)
    direct_mode = _is_simple_direct_ask(question, output_format, direct) or (output_format == "note" and bool(material_context))
    if direct_mode and output_format == "note" and not material_context:
        material_context = _collect_vault_knowledge_context(root, question)
    if direct_mode:
        effective_client = client or create_client(root, timeout_seconds=effective_timeout_seconds)
        backend_requested = _client_backend_requested(effective_client)
        model_selected = _client_selected_model_name(effective_client)
        effective_timeout_seconds = getattr(getattr(effective_client, "config", None), "timeout_seconds", timeout_seconds)
        started = time.monotonic()
        result: CompletionResult | None = None
        fallback_stages: list[str] = []
        fallback_reason = ""
        system_prompt = _material_direct_system_prompt() if material_context else _direct_ask_system_prompt()
        user_prompt = (
            _material_direct_user_prompt(_clean_report_reference_question(question), material_context)
            if material_context
            else _clean_report_reference_question(question)
        )
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
            failed_audit = {
                "backend_requested": backend_requested,
                "backend_effective": backend_effective,
                "model_selected": model_selected,
                "model_final": model_final,
                "fallback_stage": _fallback_stage_label(fallback_stages),
                "fallback_reason": fallback_reason or str(exc),
                "contract_validated": False,
                "delivery_mode": "llm-failed",
            }
            _stamped_record(
                {
                    "event": "run-ask-direct",
                    "target": "",
                    "question": question,
                    "format": "note",
                    "protocol": active_protocol,
                    "duration_ms": duration_ms,
                    "timeout_seconds": effective_timeout_seconds,
                    "no_cache": no_cache,
                    "material_refs": material_refs,
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
        assert result is not None
        ensure_layout(root)
        from aiwiki.app_protocol import resolve_protocol

        active_protocol = resolve_protocol(root, protocol)
        directory = root / "output" / "reports"
        directory.mkdir(parents=True, exist_ok=True)
        artifact_seed = _output_artifact_seed(_clean_report_reference_question(question), "note")
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        artifact_ref = relative_path(root, destination)
        backend_effective = _client_backend_name(effective_client)
        model_final = _client_model_name(effective_client)
        content = _direct_ask_artifact_markdown(
            artifact_id=artifact_id,
            question=_clean_report_reference_question(question),
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
        _ensure_output_cssclass(destination)
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

    clean_question = _clean_report_reference_question(question) if material_refs else question
    ask_kwargs = {"protocol": protocol, "no_cache": no_cache, "write_graph_anchors": False}
    if corpus_id_override is not None:
        ask_kwargs["corpus_id_override"] = corpus_id_override
    artifact = ask_question(root, clean_question, output_format, **ask_kwargs)
    if material_refs:
        artifact["material_refs"] = material_refs
        artifact["material_context"] = material_context
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
