"""LLM-backed ask workflows: run-ask and background jobs."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_queries import build_ask_used_refs
from aiwiki.app_state import load_machine_memory, load_manifest
from aiwiki.app_state import run_notes_path as run_notes_file_path
from aiwiki.app_utils import (
    _restore_file_bytes,
    _snapshot_file_bytes,
    atomic_write_text,
    next_available_stem,
    parse_frontmatter,
    relative_path,
    render_frontmatter,
    runtime_write_operation,
    slugify,
    strip_frontmatter,
    utc_now,
)
from aiwiki.execution.receipts import write_execution_receipt
from aiwiki.execution.run_notes import run_id_for_artifact, write_run_notes, write_run_notes_frontmatter
from aiwiki.input_router import is_obsidian_open_link
from aiwiki.llm import CompletionResult, LLMError, classify_backend_error
from aiwiki.notify import notify_report_generated
from aiwiki.render.paths import execution_receipts_dir
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
    clean_report_reference_question,
    extract_report_reference_paths,
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

from ..execution.ask import ask_question

_logger = logging.getLogger(__name__)

_CONTRACT_VALIDATION_PREFIXES = (
    "Ask response is missing",
    "Report ",
)

_REPORT_SKELETON_REFERENCE_HEADINGS = {"## 参考"}


def _refresh_shell_summary_fail_soft(root: Path) -> None:
    try:
        from aiwiki.app_shell import build_shell_summary, write_shell_summary

        write_shell_summary(root, build_shell_summary(root))
    except Exception as exc:
        _logger.warning(
            "shell summary refresh failed after run-ask background update: %s",
            exc,
        )


def _run_ask_failure_llm_status(exc: Exception) -> str:
    backend_error_class = classify_backend_error(str(exc))
    if backend_error_class in {"quota", "timeout", "unavailable"}:
        return "timeout_or_unavailable"
    message = str(exc)
    if any(message.startswith(prefix) for prefix in _CONTRACT_VALIDATION_PREFIXES):
        return "validation_failed"
    if _receipt_error_class(exc) == "parse_error":
        return "validation_failed"
    return "failed"

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

def _restore_run_ask_provenance_frontmatter(
    target: Path,
    deterministic_artifact: str,
    *,
    material_refs: list[str] | None = None,
    used_context_refs: list[str] | None = None,
    used_refs: list[str] | None = None,
) -> None:
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
    for key, refs in (
        ("material_refs", material_refs or []),
        ("used_context_refs", used_context_refs or []),
        ("used_refs", used_refs or []),
    ):
        merged = []
        for item in refs:
            normalized = str(item or "").strip()
            if normalized and normalized not in merged:
                merged.append(normalized)
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
    keys = {"derived_from", "source_files", "material_refs", "used_context_refs", "used_refs"}
    restored_lines = _runtime_provenance_field_lines(restored)
    if not has_frontmatter or close_idx is None:
        if not restored_lines:
            return
        updated_lines = ["---", *restored_lines, "---", *lines]
    else:
        header = _drop_frontmatter_keys(lines[1:close_idx], keys)
        updated_lines = [lines[0], *header, *restored_lines, lines[close_idx], *lines[close_idx + 1 :]]
    target.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")

def _strip_report_skeleton_reference_hints(markdown: str) -> str:
    lines = str(markdown or "").splitlines()
    if not lines:
        return markdown
    h2_positions: list[tuple[int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## ") and not line.startswith("### "):
            h2_positions.append((index, line.strip()))
    if not any(title in _REPORT_SKELETON_REFERENCE_HEADINGS for _index, title in h2_positions):
        return markdown
    remove_ranges: list[tuple[int, int]] = []
    for position_index, (line_index, title) in enumerate(h2_positions):
        if title not in _REPORT_SKELETON_REFERENCE_HEADINGS:
            continue
        end = h2_positions[position_index + 1][0] if position_index + 1 < len(h2_positions) else len(lines)
        remove_ranges.append((line_index, end))
    kept: list[str] = []
    for index, line in enumerate(lines):
        if any(start <= index < end for start, end in remove_ranges):
            continue
        kept.append(line)
    return "\n".join(kept).rstrip() + "\n"

def _append_visible_quoted_report_refs(markdown: str, refs: list[str]) -> str:
    quoted_refs: list[str] = []
    for ref in refs:
        text = str(ref or "").strip()
        if not text.startswith("output/reports/") or not text.endswith(".md"):
            continue
        if text not in quoted_refs:
            quoted_refs.append(text)
    if not quoted_refs:
        return markdown

    lines = str(markdown or "").splitlines()
    h2_positions: list[tuple[int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## ") and not line.startswith("### "):
            h2_positions.append((index, line.strip()))

    remove_ranges: list[tuple[int, int]] = []
    for position_index, (line_index, title) in enumerate(h2_positions):
        if title != "## 引用报告":
            continue
        end = h2_positions[position_index + 1][0] if position_index + 1 < len(h2_positions) else len(lines)
        remove_ranges.append((line_index, end))

    kept = [
        line
        for index, line in enumerate(lines)
        if not any(start <= index < end for start, end in remove_ranges)
    ]
    section = ["", "## 引用报告", *[f"- {ref}" for ref in quoted_refs]]
    return "\n".join(kept).rstrip() + "\n" + "\n".join(section).rstrip() + "\n"

def _load_compound_context_pages(
    root: Path,
    machine_query: dict[str, Any],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    subgraph = machine_query.get("query_subgraph", {}) or {}
    judgment_pages: list[tuple[str, str]] = []
    for node in subgraph.get("judgments", []) or []:
        if not isinstance(node, dict):
            continue
        page_id = str(node.get("page_id") or "").strip()
        path = str(node.get("path") or "").strip()
        if not page_id or not path:
            continue
        page = root / path
        if page.exists():
            judgment_pages.append((page_id, page.read_text(encoding="utf-8", errors="replace")))
    elixir_pages: list[tuple[str, str]] = []
    for node in subgraph.get("elixirs", []) or []:
        if not isinstance(node, dict):
            continue
        elixir_id = str(node.get("elixir_id") or "").strip()
        path = str(node.get("path") or "").strip()
        if not elixir_id or not path:
            continue
        page = root / path
        if page.exists():
            elixir_pages.append((elixir_id, page.read_text(encoding="utf-8", errors="replace")))
    return judgment_pages, elixir_pages


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
    machine_query = artifact.get("machine_memory_query", {}) or {}
    judgment_pages, elixir_pages = _load_compound_context_pages(root, machine_query)
    target = root / artifact["path"]
    current_artifact = _strip_run_notes_prompt_fields(target.read_text(encoding="utf-8", errors="replace"))
    return {
        "source_ids": source_ids,
        "source_pages": source_pages,
        "concept_pages": concept_pages,
        "protocol_pages": protocol_pages,
        "index_pages": index_pages,
        "judgment_pages": judgment_pages,
        "elixir_pages": elixir_pages,
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
    material_refs = [str(item) for item in artifact.get("material_refs", []) if str(item).strip()]
    material_context_refs: list[str] = []
    material_context = str(artifact.get("material_context") or "").strip()
    if material_context:
        material_context_refs = _context_ref_paths(
            [
                record
                for record in artifact.get("used_context_refs", [])
                if isinstance(record, dict)
            ]
        )
        if not material_context_refs:
            material_context_refs = list(dict.fromkeys(material_refs))
    if not material_context:
        material_context_payload = _read_material_context(root, material_refs, max_chars=12000) if material_refs else {}
        material_context = str(material_context_payload.get("text") or "")
        material_context_refs = _context_ref_paths(
            [
                record
                for record in material_context_payload.get("used_context_refs", [])
                if isinstance(record, dict)
            ]
        )
    provenance_event_fields: dict[str, Any] = {}
    if material_refs:
        provenance_event_fields["material_refs"] = material_refs
    if material_context_refs:
        provenance_event_fields["used_context_refs"] = material_context_refs
    compound_paths = [
        f"wiki/judgments/{page_id}.md"
        for page_id, _content in prepared.get("judgment_pages", [])
    ] + [
        f"wiki/elixirs/{elixir_id}.md"
        for elixir_id, _content in prepared.get("elixir_pages", [])
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
    target_snapshot = _snapshot_file_bytes(target)
    target.write_text(updated, encoding="utf-8")
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
        _mark_run_ask_background_artifact_complete(target, status="completed", job_id=background_job_id)
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
            run_ask_path="background-resume" if background_job_id else "report",
            extra={
                "backend_effective": backend_effective,
                "model_final": model_final,
                "fallback_stage": fallback_stage,
                "response_id": result.response_id,
                "usage": result.usage,
                "background_job_id": background_job_id or "",
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
    if is_obsidian_open_link(question):
        raise ValueError("obsidian open links are navigation targets, not questions")
    if output_format != "report":
        raise ValueError("run-ask-submit is only supported for report output.")
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("run-ask-submit timeout_seconds must be greater than 0.")
    effective_timeout_seconds = _effective_run_ask_timeout(output_format, timeout_seconds)

    from aiwiki.runner.preflight import preflight_check_backend_chain

    backend_compat = preflight_check_backend_chain(root)
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
    if material_refs:
        manifest["material_refs"] = material_refs
    write_job_manifest(root, manifest)
    _refresh_shell_summary_fail_soft(root)
    spawn_result = spawn_background_resume(root, job_id) if spawn else {}
    if spawn_result:
        if artifact.get("path"):
            _mark_run_ask_background_artifact_submitted(root / str(artifact["path"]), job_id=job_id, status="running")
        artifact["background_status"] = "running"
        manifest["artifact"] = artifact
        manifest.update({"status": "running", "spawn": spawn_result, "updated_at": utc_now()})
        write_job_manifest(root, manifest)
        _refresh_shell_summary_fail_soft(root)
    submitted_payload: dict[str, Any] = {
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
    if material_refs:
        submitted_payload["material_refs"] = material_refs
    return submitted_payload

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
        _refresh_shell_summary_fail_soft(root)
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
    _refresh_shell_summary_fail_soft(root)
    return {"job_id": job_id, **payload}

def _mark_run_ask_artifact_degraded(
    target: Path,
    *,
    reason: str,
    backend: str,
    model: str,
    llm_status: str = "timeout_or_unavailable",
) -> None:
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
            "llm_status": llm_status,
            "delivery_mode": "llm-failed",
            "background_status": "failed",
            "llm_failure_reason": reason,
            "llm_backend": backend,
            "llm_model": model,
        }
    )
    body = strip_frontmatter(current)
    references = body[body.find("## 参考") :].strip() if "## 参考" in body else body.strip()
    references = _strip_report_skeleton_reference_hints(references).strip()
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
    atomic_write_text(target, "\n".join(lines).rstrip() + "\n")

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

def _write_run_ask_output_receipt(
    root: Path,
    *,
    generated_by: str,
    artifact_ref: str,
    run_id: str,
    question: str,
    output_format: str,
    protocol: str,
    delivery_mode: str,
    run_ask_path: str,
    artifact_status: str = "completed",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    receipt_extra: dict[str, Any] = {
        "receipt_matrix_version": 1,
        "run_ask_path": run_ask_path,
        "artifact_status": artifact_status,
        "format": output_format,
        "question": question,
        "run_id": run_id,
        "llm_receipt_path": ".aiwiki/logs/llm-receipts.jsonl",
        "delivery_mode": delivery_mode,
    }
    if extra:
        receipt_extra.update(extra)
    return write_execution_receipt(
        root,
        operation="run-ask",
        generated_by=generated_by,
        subject_kind="output-artifact",
        subject_id=run_id or Path(artifact_ref).stem,
        target_file=artifact_ref,
        primary_path=artifact_ref,
        protocol=protocol,
        extra=receipt_extra,
    )


def _planned_run_ask_output_receipt_ref(root: Path, *, artifact_ref: str, run_id: str) -> str:
    receipt_dir = execution_receipts_dir(root)
    seed_target = Path(artifact_ref).stem or run_id or "run-ask"
    seed = slugify(f"run-ask-{seed_target}") or slugify("run-ask") or "execution-receipt"
    action_id = next_available_stem(receipt_dir, seed, suffix=".json")
    return relative_path(root, receipt_dir / f"{action_id}.json")

def _quoted_report_reference_paths(question: str) -> list[str]:
    return extract_report_reference_paths(question)

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
        if not resolved.exists() or not resolved.is_file():
            continue
        if resolved.suffix.lower() != ".md":
            continue
        if text in seen:
            continue
        seen.add(text)
        safe_refs.append(text)
    return safe_refs

def _quoted_report_material_refs(root: Path, question: str) -> list[str]:
    quoted_refs = _quoted_report_reference_paths(question)
    if not quoted_refs:
        return []
    safe_refs = _safe_quoted_report_reference_paths(root, quoted_refs)
    safe_set = set(safe_refs)
    invalid_refs = [ref for ref in quoted_refs if ref not in safe_set]
    if invalid_refs:
        missing = ", ".join(invalid_refs)
        raise ValueError(f"quoted report reference is missing or unsafe: {missing}")
    return safe_refs

def _clean_report_reference_question(question: str) -> str:
    return clean_report_reference_question(question)

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

def _read_material_context(root: Path, refs: list[str], *, max_chars: int = 6000) -> dict[str, Any]:
    snippets: list[str] = []
    used_context_refs: list[dict[str, Any]] = []
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
        used_context_refs.append(
            {
                "path": ref,
                "kind": _context_kind_for_path(ref),
                "excerpt_chars": len(excerpt),
                "selection_reason": "explicit-material-ref",
            }
        )
        remaining -= len(excerpt)
    return {
        "text": "\n\n".join(snippets).strip(),
        "used_context_refs": used_context_refs,
        "context_budget": {"explicit_material_refs": len(refs), "max_chars": max_chars},
    }

def _context_kind_for_path(relative: str) -> str:
    if relative.startswith("wiki/elixirs/"):
        return "elixir"
    if relative.startswith("wiki/judgments/"):
        return "judgment"
    if relative.startswith("wiki/decisions/"):
        return "decision"
    if relative.startswith("wiki/sources/"):
        return "source"
    if relative.startswith("wiki/concepts/"):
        return "concept"
    if relative.startswith("output/reports/"):
        return "material-report"
    if relative.startswith("raw/"):
        return "raw-material"
    return "material"

def _context_ref_paths(records: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for record in records:
        path = str(record.get("path") or "").strip()
        if path and path not in paths:
            paths.append(path)
    return paths

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
    lean: bool = False,
    timeout_seconds: int | None = None,
    no_cache: bool = False,
    corpus_id_override: str | None = None,
) -> dict[str, Any]:
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
