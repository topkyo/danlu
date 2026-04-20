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
from .app_state import load_machine_memory, load_manifest
from .app_utils import (
    TEXT_EXTENSIONS,
    parse_frontmatter,
    read_text_preview,
    relative_path,
    render_scalar,
    runtime_write_operation,
    sha256_bytes,
)
from .config import BACKEND_GITHUB_MODELS_API, LLMConfig
from .llm import CompletionResult, LLMError, create_backend_client, probe_available_backends, probe_backend

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
    "github-models": {
        "max_total_chars": 14000,
        "index_page_chars": 900,
        "log_page_chars": 700,
        "protocol_page_chars": 900,
        "concept_page_chars": 900,
        "source_page_chars": 1200,
        "max_index_pages": 4,
        "max_protocol_pages": 2,
        "max_concepts": 2,
        "max_sources": 3,
    },
    "github-models-minimal": {
        "max_total_chars": 9000,
        "index_page_chars": 650,
        "log_page_chars": 500,
        "protocol_page_chars": 700,
        "concept_page_chars": 700,
        "source_page_chars": 900,
        "max_index_pages": 3,
        "max_protocol_pages": 2,
        "max_concepts": 2,
        "max_sources": 2,
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
    "github-models": {
        "max_total_chars": 14000,
        "current_page_chars": 1600,
        "raw_excerpt_chars": 1800,
        "schema_page_chars": 750,
        "protocol_page_chars": 750,
        "source_page_chars": 1100,
        "related_concept_chars": 900,
        "max_source_pages": 2,
        "max_related_concepts": 2,
        "max_quality_signals": 3,
    },
    "github-models-minimal": {
        "max_total_chars": 9000,
        "current_page_chars": 1100,
        "raw_excerpt_chars": 1200,
        "schema_page_chars": 600,
        "protocol_page_chars": 600,
        "source_page_chars": 800,
        "related_concept_chars": 700,
        "max_source_pages": 2,
        "max_related_concepts": 1,
        "max_quality_signals": 2,
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
    "github-models": {
        "max_total_chars": 14000,
        "deterministic_report_chars": 1800,
        "schema_page_chars": 700,
        "protocol_page_chars": 700,
        "index_page_chars": 800,
        "log_page_chars": 650,
        "wiki_page_chars": 850,
        "max_index_pages": 6,
        "max_wiki_pages": 3,
    },
    "github-models-minimal": {
        "max_total_chars": 9000,
        "deterministic_report_chars": 1200,
        "schema_page_chars": 550,
        "protocol_page_chars": 550,
        "index_page_chars": 650,
        "log_page_chars": 500,
        "wiki_page_chars": 650,
        "max_index_pages": 4,
        "max_wiki_pages": 2,
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
    if (not pending and not pending_concept_slugs and not pending_rewrite_candidates) or limit <= 0:
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
            "pending_rewrite_concept_pages": len(pending_rewrite_candidates),
            "skipped_rewrite_concept_pages": skipped_rewrite_candidates,
            "prompt_profile": "",
            "retry_prompt_profile": "",
        }

    effective_client = client or create_client(root)
    prompt_profile = _initial_compile_prompt_profile(effective_client)
    retry_prompt_profile = ""

    for entry in pending[:limit]:
        target = root / "wiki" / "sources" / f"{entry['id']}.md"
        raw_path = root / entry["stored_path"]
        current_page = target.read_text(encoding="utf-8", errors="replace")
        item_profile = prompt_profile
        prompt = _build_compile_prompt(root, entry, raw_path, current_page, prompt_profile=item_profile)
        item_retry_profile = ""
        try:
            result = effective_client.complete(_system_prompt("compile"), prompt)
        except LLMError as exc:
            item_retry_profile = _retry_compile_prompt_profile(exc, item_profile, effective_client)
            if not item_retry_profile:
                raise
            logging.getLogger("aiwiki").warning(
                "run-compile failed with %s prompt; retrying with %s prompt",
                item_profile,
                item_retry_profile,
            )
            prompt = _build_compile_prompt(root, entry, raw_path, current_page, prompt_profile=item_retry_profile)
            result = effective_client.complete(_system_prompt("compile"), prompt)
            prompt_profile = item_retry_profile
            retry_prompt_profile = item_retry_profile
        used_profile = item_retry_profile or item_profile
        updated = _normalize_markdown(result.text)
        _validate_source_page(updated, entry["id"], entry["stored_path"], entry["sha256"])
        target.write_text(updated, encoding="utf-8")
        updated_pages.append(relative_path(root, target))
        _append_log(
            root,
            {
                "event": "run-compile",
                "target": relative_path(root, target),
                "source": entry["stored_path"],
                "model": _client_model_name(effective_client),
                "prompt_profile": used_profile,
                "retry_prompt_profile": item_retry_profile,
                "response_id": result.response_id,
                "usage": result.usage,
            },
        )

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
        try:
            result = effective_client.complete(_system_prompt("compile"), prompt)
        except LLMError as exc:
            item_retry_profile = _retry_compile_prompt_profile(exc, item_profile, effective_client)
            if not item_retry_profile:
                raise
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
            result = effective_client.complete(_system_prompt("compile"), prompt)
            prompt_profile = item_retry_profile
            retry_prompt_profile = item_retry_profile
        used_profile = item_retry_profile or item_profile
        updated = _normalize_markdown(result.text)
        _validate_concept_page(updated, slug, frontmatter.get("source_signature", ""), source_pages)
        target.write_text(updated, encoding="utf-8")
        updated_placeholder_concept_pages.append(relative_path(root, target))
        _append_log(
            root,
            {
                "event": "run-compile-concept",
                "target": relative_path(root, target),
                "source_pages": source_pages,
                "model": _client_model_name(effective_client),
                "prompt_profile": used_profile,
                "retry_prompt_profile": item_retry_profile,
                "response_id": result.response_id,
                "usage": result.usage,
            },
        )

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
        try:
            result = effective_client.complete(_system_prompt("compile"), prompt)
        except LLMError as exc:
            item_retry_profile = _retry_compile_prompt_profile(exc, item_profile, effective_client)
            if not item_retry_profile:
                raise
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
            result = effective_client.complete(_system_prompt("compile"), prompt)
            prompt_profile = item_retry_profile
            retry_prompt_profile = item_retry_profile
        used_profile = item_retry_profile or item_profile
        updated = _normalize_markdown(result.text)
        _validate_concept_page(updated, slug, frontmatter.get("source_signature", ""), source_pages)
        proposal = store_concept_rewrite_candidate(
            root,
            slug,
            quality_record=quality_record,
            candidate_markdown=updated,
            generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )
        updated_rewrite_proposal_pages.append(str(proposal["proposal_path"]))
        _append_log(
            root,
            {
                "event": "run-compile-concept-rewrite-proposal",
                "target": str(proposal["proposal_path"]),
                "concept_page": relative_path(root, target),
                "source_pages": source_pages,
                "quality_priority": quality_record.get("priority", ""),
                "quality_issues": quality_record.get("issues", []),
                "model": _client_model_name(effective_client),
                "prompt_profile": used_profile,
                "retry_prompt_profile": item_retry_profile,
                "response_id": result.response_id,
                "usage": result.usage,
            },
        )

    if updated_rewrite_proposal_pages:
        compile_result = compile_wiki(root)

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
        "pending_rewrite_concept_pages": len(pending_rewrite_candidates),
        "skipped_rewrite_concept_pages": skipped_rewrite_candidates,
        "prompt_profile": prompt_profile,
        "retry_prompt_profile": retry_prompt_profile,
    }


@runtime_write_operation
def run_ask(
    root: Path,
    question: str,
    output_format: str,
    protocol: str | None = None,
    client: SupportsComplete | None = None,
    lean: bool = False,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("run-ask timeout_seconds must be greater than 0.")
    artifact = ask_question(root, question, output_format, protocol=protocol)
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
    prompt_profile = _select_initial_ask_prompt_profile(effective_client, lean=lean)
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
        prompt_profile=prompt_profile,
    )
    retry_profile = ""
    try:
        result = effective_client.complete(_system_prompt("ask"), prompt)
    except LLMError as exc:
        retry_profile = _retry_ask_prompt_profile(exc, prompt_profile, effective_client)
        if not retry_profile:
            raise
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
            prompt_profile=retry_profile,
        )
        result = effective_client.complete(_system_prompt("ask"), prompt)
    updated = _normalize_markdown(result.text)
    _validate_output_markdown(updated, output_format, source_ids)
    target.write_text(updated, encoding="utf-8")
    _append_log(
        root,
        {
            "event": "run-ask",
            "target": artifact["path"],
            "question": question,
            "format": output_format,
            "protocol": artifact.get("protocol", ""),
            "ranked_sources": source_ids,
            "model": _client_model_name(effective_client),
            "prompt_profile": retry_profile or prompt_profile,
            "retry_prompt_profile": retry_profile,
            "timeout_seconds": getattr(getattr(effective_client, "config", None), "timeout_seconds", timeout_seconds),
            "response_id": result.response_id,
            "usage": result.usage,
        },
    )
    return {
        **artifact,
        "prompt_profile": retry_profile or prompt_profile,
        "retry_prompt_profile": retry_profile,
        "timeout_seconds": getattr(getattr(effective_client, "config", None), "timeout_seconds", timeout_seconds),
    }


@runtime_write_operation
def run_lint(root: Path, client: SupportsComplete | None = None) -> dict[str, Any]:
    ensure_layout(root)
    deterministic = lint_wiki(root)
    report_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = root / "output" / "lint" / f"semantic-lint-{report_id}.md"
    effective_client = client or create_client(root)
    prompt_profile = _initial_lint_prompt_profile(effective_client)
    prompt = _build_lint_prompt(root, deterministic["path"], prompt_profile=prompt_profile)
    retry_prompt_profile = ""
    try:
        result = effective_client.complete(_system_prompt("lint"), prompt)
    except LLMError as exc:
        retry_prompt_profile = _retry_lint_prompt_profile(exc, prompt_profile, effective_client)
        if not retry_prompt_profile:
            raise
        logging.getLogger("aiwiki").warning(
            "run-lint failed with %s prompt; retrying with %s prompt",
            prompt_profile,
            retry_prompt_profile,
        )
        prompt = _build_lint_prompt(root, deterministic["path"], prompt_profile=retry_prompt_profile)
        result = effective_client.complete(_system_prompt("lint"), prompt)
        prompt_profile = retry_prompt_profile
    updated = _normalize_markdown(result.text)
    if not updated.startswith("#") and not updated.startswith("---"):
        raise RuntimeError("Semantic lint response must be markdown.")
    target.write_text(updated, encoding="utf-8")
    _append_log(
        root,
        {
            "event": "run-lint",
            "target": relative_path(root, target),
            "deterministic_report": deterministic["path"],
            "model": _client_model_name(effective_client),
            "prompt_profile": prompt_profile,
            "retry_prompt_profile": retry_prompt_profile,
            "response_id": result.response_id,
            "usage": result.usage,
        },
    )
    return {
        "deterministic": deterministic,
        "semantic_report": relative_path(root, target),
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
    compile_result = run_compile(root, client=effective_client, limit=compile_limit)
    promotion_result = promote_recurring_outputs(root)
    if promotion_result["count"]:
        compile_result["compile"] = compile_wiki(root)
    if semantic_lint:
        lint_result = run_lint(root, client=effective_client)
    else:
        lint_result = {
            "deterministic": lint_wiki(root),
            "semantic_report": "",
        }
    state = write_nightly_health(
        root,
        compile_result["compile"],
        lint_result["deterministic"],
        promotion_result=promotion_result,
        semantic_report=lint_result["semantic_report"],
        llm_used=True,
    )
    return {
        "compile": compile_result,
        "lint": lint_result,
        "promotions": promotion_result,
        "aging": state["aging"],
        "repair_backlog": state["repair_backlog"]["path"],
        "state_path": relative_path(root, root / ".aiwiki" / "state" / "nightly-health.json"),
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
        "## Machine Memory Query Plan",
        _render_machine_query(machine_memory_query),
        "",
        "## Index Pages",
    ]
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
    backend = str(getattr(getattr(client, "config", None), "backend", "") or "")
    if backend == BACKEND_GITHUB_MODELS_API:
        return "github-models"
    return "balanced"


def _lean_ask_prompt_profile(client: SupportsComplete) -> str:
    backend = str(getattr(getattr(client, "config", None), "backend", "") or "")
    if backend == BACKEND_GITHUB_MODELS_API:
        return "github-models-minimal"
    return "lean"


def _select_initial_ask_prompt_profile(client: SupportsComplete, lean: bool = False) -> str:
    if lean:
        return _lean_ask_prompt_profile(client)
    return _initial_ask_prompt_profile(client)


def _retry_ask_prompt_profile(exc: Exception, current_profile: str, client: SupportsComplete) -> str:
    text = str(exc or "").lower()
    backend = str(getattr(getattr(client, "config", None), "backend", "") or "")
    if backend == BACKEND_GITHUB_MODELS_API:
        if current_profile == "github-models" and any(
            marker in text for marker in ("tokens_limit_reached", "request body too large", "http 413", "timed out", "timeout")
        ):
            return "github-models-minimal"
        return ""
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
    ensure_layout(root)
    payload = {
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        **event,
    }
    log_path = root / ".aiwiki" / "logs" / "runs.jsonl"
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
    backend = str(getattr(getattr(client, "config", None), "backend", "") or "")
    if backend == BACKEND_GITHUB_MODELS_API:
        return "github-models"
    return "balanced"


def _initial_lint_prompt_profile(client: SupportsComplete) -> str:
    backend = str(getattr(getattr(client, "config", None), "backend", "") or "")
    if backend == BACKEND_GITHUB_MODELS_API:
        return "github-models"
    return "balanced"


def _retry_compile_prompt_profile(exc: Exception, current_profile: str, client: SupportsComplete) -> str:
    backend = str(getattr(getattr(client, "config", None), "backend", "") or "")
    if backend == BACKEND_GITHUB_MODELS_API and current_profile == "github-models" and _is_budget_retryable_error(exc):
        return "github-models-minimal"
    return ""


def _retry_lint_prompt_profile(exc: Exception, current_profile: str, client: SupportsComplete) -> str:
    backend = str(getattr(getattr(client, "config", None), "backend", "") or "")
    if backend == BACKEND_GITHUB_MODELS_API and current_profile == "github-models" and _is_budget_retryable_error(exc):
        return "github-models-minimal"
    return ""


def _is_budget_retryable_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return any(
        marker in text for marker in ("tokens_limit_reached", "request body too large", "http 413", "timed out", "timeout")
    )


def _client_model_name(client: SupportsComplete) -> str:
    config = getattr(client, "config", None)
    model = getattr(config, "model", None)
    return str(model or "")


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
