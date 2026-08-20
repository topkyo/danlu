"""LLM-backed ask workflows: synchronous run-ask.

This module is the orchestration entry point for run-ask.
Helper logic lives in ``workflows_ask_context`` / ``workflows_ask_frontmatter`` /
``workflows_ask_status`` / ``workflows_ask_receipts`` / ``workflows_ask_writeback``.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from aiwiki.execution.ask import ask_question
from aiwiki.input_router import is_obsidian_open_link
from aiwiki.llm import CompletionResult, LLMError
from aiwiki.protocol.scaffold import ensure_layout
from aiwiki.render.ask_report import build_ask_used_refs
from aiwiki.runner.ask_quality import extract_cited_vault_paths
from aiwiki.runner.clients import (
    _append_fallback_stage,
    _client_backend_requested,
    _client_selected_model_name,
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
from aiwiki.runner.workflows_ask_context import (
    _clean_report_reference_question,
    _context_ref_paths,
    _material_hint_paths,
    _material_refs_unreadable,
    _quoted_report_material_refs,
    _read_material_context,
    _run_ask_prepared_context,
)
from aiwiki.runner.workflows_ask_frontmatter import (
    _append_visible_quoted_report_refs,
    _strip_report_skeleton_reference_hints,
    rewrite_report_relative_links,
)
from aiwiki.runner.workflows_ask_receipts import (
    _effective_run_ask_timeout,
)
from aiwiki.runner.workflows_ask_writeback import (
    _record_run_ask_failure,
    _write_run_ask_material_unreadable,
    _write_run_ask_success,
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

    prepared = _run_ask_prepared_context(root, question, artifact)
    source_ids = prepared["source_ids"]
    target = prepared["target"]
    current_artifact = prepared["current_artifact"]

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

    if _material_refs_unreadable(root, material_refs, material_context):
        return _write_run_ask_material_unreadable(
            root,
            artifact=artifact,
            question=question,
            output_format=output_format,
            no_cache=no_cache,
            backend_requested=backend_requested,
            model_selected=model_selected,
            material_refs=material_refs,
            provenance_event_fields=provenance_event_fields,
            target=target,
            current_artifact=current_artifact,
            backend_compat=backend_compat,
            effective_client=effective_client,
            timeout_seconds=timeout_seconds,
        )

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
        client=effective_client,
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
                        client=effective_client,
                    )
                    prompt_profile = retry_profile
                    used_prompt_profile = retry_profile
                    continue
                raise
            updated = _normalize_markdown(result.text)
            if output_format == "report":
                updated = _dedupe_report_citations(updated)
                updated = _strip_report_skeleton_reference_hints(updated)
                updated = _append_visible_quoted_report_refs(updated, material_context_refs or material_refs)
                updated = rewrite_report_relative_links(updated, report_path=target, root=root)
            used_refs = extract_cited_vault_paths(updated, root=root)
            provenance_event_fields["used_refs"] = used_refs
            _validate_output_markdown(updated, output_format, source_ids)
            break
    except Exception as exc:
        _record_run_ask_failure(
            root,
            artifact=artifact,
            question=question,
            output_format=output_format,
            no_cache=no_cache,
            exc=exc,
            result=result,
            started=started,
            effective_client=effective_client,
            backend_requested=backend_requested,
            model_selected=model_selected,
            fallback_stages=fallback_stages,
            fallback_reason=fallback_reason,
            retry_profile=retry_profile,
            used_prompt_profile=used_prompt_profile,
            provenance_event_fields=provenance_event_fields,
            target=target,
            current_artifact=current_artifact,
            material_refs=material_refs,
            material_context_refs=material_context_refs,
            used_refs=used_refs,
            source_ids=source_ids,
            backend_compat=backend_compat,
        )
        raise

    assert result is not None
    return _write_run_ask_success(
        root,
        artifact=artifact,
        question=question,
        output_format=output_format,
        protocol=protocol,
        no_cache=no_cache,
        updated=updated,
        result=result,
        started=started,
        effective_client=effective_client,
        backend_requested=backend_requested,
        model_selected=model_selected,
        fallback_stages=fallback_stages,
        fallback_reason=fallback_reason,
        retry_profile=retry_profile,
        used_prompt_profile=used_prompt_profile,
        effective_timeout_seconds=effective_timeout_seconds,
        provenance_event_fields=provenance_event_fields,
        target=target,
        current_artifact=current_artifact,
        material_refs=material_refs,
        material_context_refs=material_context_refs,
        used_refs=used_refs,
        source_ids=source_ids,
        backend_compat=backend_compat,
    )


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
