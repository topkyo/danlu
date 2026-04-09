"""LLM-backed execution helpers for compile, ask, and lint workflows."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .app import (
    TEXT_EXTENSIONS,
    ask_question,
    compile_wiki,
    concept_summary_is_placeholder,
    ensure_layout,
    lint_wiki,
    load_protocol_state,
    load_machine_memory,
    nightly_health,
    load_manifest,
    parse_frontmatter,
    placeholder_concept_slugs,
    promote_recurring_outputs,
    preserved_section,
    read_text_preview,
    relative_path,
    render_scalar,
    runtime_write_operation,
    sha256_bytes,
    store_concept_rewrite_candidate,
    write_nightly_health,
)
from .config import LLMConfig
from .llm import CompletionResult, create_backend_client


class SupportsComplete(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        ...


def llm_status() -> dict[str, Any]:
    return LLMConfig.status_from_env()


def create_client(root: Path) -> SupportsComplete:
    return create_backend_client(LLMConfig.from_env(), root)


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
        }

    effective_client = client or create_client(root)

    for entry in pending[:limit]:
        target = root / "wiki" / "sources" / f"{entry['id']}.md"
        raw_path = root / entry["stored_path"]
        current_page = target.read_text(encoding="utf-8", errors="replace")
        prompt = _build_compile_prompt(root, entry, raw_path, current_page)
        result = effective_client.complete(_system_prompt("compile"), prompt)
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
        prompt = _build_concept_compile_prompt(root, target, current_page, source_pages, related_slugs)
        result = effective_client.complete(_system_prompt("compile"), prompt)
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
        prompt = _build_concept_compile_prompt(
            root,
            target,
            current_page,
            source_pages,
            related_slugs,
            quality_record=quality_record,
        )
        result = effective_client.complete(_system_prompt("compile"), prompt)
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
    }


@runtime_write_operation
def run_ask(
    root: Path,
    question: str,
    output_format: str,
    protocol: str | None = None,
    client: SupportsComplete | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
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
    )
    effective_client = client or create_client(root)
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
            "response_id": result.response_id,
            "usage": result.usage,
        },
    )
    return artifact


@runtime_write_operation
def run_lint(root: Path, client: SupportsComplete | None = None) -> dict[str, Any]:
    ensure_layout(root)
    deterministic = lint_wiki(root)
    report_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = root / "output" / "lint" / f"semantic-lint-{report_id}.md"
    prompt = _build_lint_prompt(root, deterministic["path"])
    effective_client = client or create_client(root)
    result = effective_client.complete(_system_prompt("lint"), prompt)
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
            "response_id": result.response_id,
            "usage": result.usage,
        },
    )
    return {
        "deterministic": deterministic,
        "semantic_report": relative_path(root, target),
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

    if llm_enabled and not deterministic_only:
        compile_result = run_compile(root, client=client, limit=compile_limit)
    else:
        compile_result = {
            "compile": compile_wiki(root),
            "updated_pages": [],
            "pending_pages": _pending_summary_count(root),
            "skipped_pages": 0,
        }

    if semantic_lint and llm_enabled and not deterministic_only:
        lint_result = run_lint(root, client=client)
    else:
        lint_result = {
            "deterministic": lint_wiki(root),
            "semantic_report": "",
        }

    snapshot = inbox_snapshot(root)
    result = {
        "processed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "llm_used": bool(llm_enabled and not deterministic_only),
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


def _build_compile_prompt(root: Path, entry: dict[str, Any], raw_path: Path, current_page: str) -> str:
    template = _load_prompt(root, "compile.md")
    raw_excerpt = _read_context(raw_path, max_chars=_context_budget())
    target_relative = relative_path(root, root / "wiki" / "sources" / f"{entry['id']}.md")
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
            "- Keep the `Source Record` section and update the `Summary` section with grounded prose.",
            "- If evidence is weak or truncated, say so explicitly.",
            "",
            "## Runtime Schema",
            _schema_context(root, ("index.md", "citations.md", "conflicts.md")),
            "",
            "## Active Protocol",
            _protocol_context(root, ("index.md", "taxonomy.md", "query.md")),
            "",
            "## Current Page",
            current_page,
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
) -> str:
    template = _load_prompt(root, "compile.md")
    source_sections: list[str] = []
    for relative in source_pages:
        page = root / relative
        if not page.exists():
            continue
        source_sections.extend([f"### {relative}", _fit_prompt_section(page.read_text(encoding='utf-8', errors='replace'), max_chars=3200), ""])
    related_sections: list[str] = []
    for slug in related_slugs[:4]:
        page = root / "wiki" / "concepts" / f"{slug}.md"
        if not page.exists():
            continue
        related_sections.extend([f"### wiki/concepts/{slug}.md", _fit_prompt_section(page.read_text(encoding='utf-8', errors='replace'), max_chars=2200), ""])
    frontmatter = parse_frontmatter(current_page)
    quality_lines = [
        f"- Rewrite priority: `{quality_record.get('priority', 'n/a')}`",
        f"- Issues: `{', '.join(quality_record.get('issues', [])) or 'none'}`",
        f"- Strategy: {quality_record.get('rewrite_strategy', 'Keep the concept grounded and explicit.')}",
    ] if quality_record else ["- No extra concept-quality signal was attached."]
    if quality_record and quality_record.get("conflict_signals"):
        for signal in quality_record.get("conflict_signals", [])[:4]:
            quality_lines.append(
                f"- Conflict `{signal.get('label', 'n/a')}` from `{', '.join(signal.get('source_pages', [])) or 'none'}`"
            )
    if quality_record and quality_record.get("gap_signals"):
        for gap in quality_record.get("gap_signals", [])[:4]:
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
            "- Replace the fallback concept summary with grounded synthesis across the listed source pages.",
            "- Keep contradictions, weak evidence, and unresolved gaps explicit.",
            "- Preserve or improve explicit citations to `wiki/sources/*.md` when useful.",
            "",
            "## Runtime Schema",
            _schema_context(root, ("index.md", "citations.md", "conflicts.md", "taxonomy.md")),
            "",
            "## Active Protocol",
            _protocol_context(root, ("index.md", "taxonomy.md", "query.md")),
            "",
            "## Concept Quality Signals",
            "\n".join(quality_lines),
            "",
            "## Current Concept Page",
            current_page,
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
) -> str:
    template = _load_prompt(root, "ask.md")
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
    if not index_pages:
        sections.append("- No index pages were available.")
    else:
        for relative, content in index_pages:
            excerpt = (
                _fit_log_prompt_section(content, max_chars=3000)
                if relative.endswith("/log.md")
                else _fit_prompt_section(content, max_chars=3500)
            )
            sections.extend([f"### {relative}", excerpt, ""])
    sections.extend(
        [
            "## Protocol Pages",
        ]
    )
    if not protocol_pages:
        sections.append("- No protocol pages were available.")
    else:
        for relative, content in protocol_pages:
            sections.extend([f"### {relative}", _fit_prompt_section(content, max_chars=2200), ""])
    sections.extend(
        [
            "## Concept Pages",
        ]
    )
    if not concept_pages:
        sections.append("- No ranked concept pages were available.")
    else:
        for slug, content in concept_pages:
            sections.extend([f"### wiki/concepts/{slug}.md", _fit_prompt_section(content, max_chars=3200), ""])
    sections.extend(
        [
        "## Source Pages",
        ]
    )
    if not source_pages:
        sections.append("- No ranked source pages were available. Keep the artifact cautious and explicit about missing evidence.")
    else:
        for entry, content in source_pages:
            sections.extend(
                [
                    f"### wiki/sources/{entry['id']}.md",
                    _fit_prompt_section(content, max_chars=4200),
                    "",
                ]
            )
    return "\n".join(sections)


def _render_machine_query(machine_memory_query: dict[str, Any]) -> str:
    matched_terms = machine_memory_query.get("matched_terms", [])
    direct_source_ids = machine_memory_query.get("direct_source_ids", [])
    direct_concept_slugs = machine_memory_query.get("direct_concept_slugs", [])
    ranked_source_ids = machine_memory_query.get("ranked_source_ids", [])
    ranked_concept_slugs = machine_memory_query.get("ranked_concept_slugs", [])
    supporting_edges = machine_memory_query.get("supporting_edges", [])

    lines = [
        f"- Matched terms: `{', '.join(matched_terms) or 'none'}`",
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
                f" ({route.get('length', 0)} hop(s))"
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


def _build_lint_prompt(root: Path, deterministic_report: str) -> str:
    template = _load_prompt(root, "lint.md")
    sections = [
        template,
        "## Deterministic Lint Report",
        _read_context(root / deterministic_report, max_chars=_context_budget()),
        "",
        "## Active Protocol",
        _protocol_context(root, ("index.md", "review.md", "nightly.md")),
        "",
        "## Wiki Indexes",
    ]
    for relative in (
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
    ):
        path = root / relative
        if path.exists():
            sections.extend([f"### {relative}", _read_context(path, max_chars=4000), ""])

    schema_context = _schema_context(root, ("index.md", "citations.md", "conflicts.md", "writeback.md"))
    if schema_context:
        sections.extend(["## Runtime Schema", schema_context, ""])

    included_chars = sum(len(section) for section in sections)
    for group in ("wiki/concepts", "wiki/sources", "wiki/derived"):
        for path in sorted((root / group).glob("*.md")):
            excerpt = _read_context(path, max_chars=3500)
            next_block = f"### {relative_path(root, path)}\n{excerpt}\n"
            if included_chars + len(next_block) > _context_budget() * 2:
                sections.append("- Additional wiki files omitted due to context budget.")
                return "\n".join(sections)
            sections.append(next_block)
            included_chars += len(next_block)
    return "\n".join(sections)


def _load_prompt(root: Path, name: str) -> str:
    path = root / "prompts" / name
    return path.read_text(encoding="utf-8")


def _schema_context(root: Path, names: tuple[str, ...]) -> str:
    sections: list[str] = []
    for name in names:
        path = root / "schema" / name
        if not path.exists():
            continue
        sections.extend([f"### schema/{name}", _read_context(path, max_chars=2200), ""])
    return "\n".join(sections).strip()


def _protocol_context(root: Path, names: tuple[str, ...]) -> str:
    state = load_protocol_state(root)
    active = state["active_protocol"]
    sections: list[str] = [f"- Active protocol: `{active}` ({state['state_path']})", ""]
    for name in names:
        path = root / "schema" / "protocols" / active / name
        if not path.exists():
            continue
        sections.extend([f"### schema/protocols/{active}/{name}", _read_context(path, max_chars=2200), ""])
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
    if output_format in {"report", "figure"}:
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
