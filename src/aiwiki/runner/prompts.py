"""Prompt profiles, builders, context readers, validators for runner workflows."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from aiwiki.app_content import concept_summary_is_placeholder, preserved_section
from aiwiki.app_protocol import CONCEPT_HARDNESS_LEVELS, load_protocol_state
from aiwiki.app_utils import (
    TEXT_EXTENSIONS,
    parse_frontmatter,
    read_text_preview,
    relative_path,
    render_scalar,
)
from aiwiki.config import LLMConfig
from aiwiki.runner.interfaces import SupportsComplete

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
}



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
    previous_output_summary: str | None = None,
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
    ]
    if previous_output_summary:
        sections.extend(["## Previous Output In Corpus", previous_output_summary, ""])
    sections.extend([
        "## Machine Memory Query Plan",
        _render_machine_query(machine_memory_query),
        "",
        "## Index Pages",
    ])
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
    return "balanced"


def _lean_ask_prompt_profile(client: SupportsComplete) -> str:
    del client
    return "lean"


def _select_initial_ask_prompt_profile(client: SupportsComplete, lean: bool = False) -> str:
    if lean:
        return _lean_ask_prompt_profile(client)
    return _initial_ask_prompt_profile(client)


def _retry_ask_prompt_profile(exc: Exception, current_profile: str, client: SupportsComplete) -> str:
    text = str(exc or "").lower()
    del client
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
    fallback = Path(__file__).resolve().parents[3] / "prompts" / name
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
    source_files = _require_frontmatter_string_list(
        frontmatter,
        "source_files",
        "Compile response must keep `source_files` as a frontmatter list.",
    )
    if expected_source_file not in source_files:
        raise RuntimeError("Compile response dropped the source file reference.")
    if "Pending LLM summary." in preserved_section(markdown, "Summary", ""):
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
    source_pages = _require_frontmatter_string_list(
        frontmatter,
        "source_pages",
        "Concept compile response must keep `source_pages` as a frontmatter list.",
    )
    for expected_source_page in expected_source_pages:
        if expected_source_page not in source_pages:
            raise RuntimeError("Concept compile response dropped a source page reference.")
    if str(frontmatter.get("hardness") or "").strip().lower() not in CONCEPT_HARDNESS_LEVELS:
        raise RuntimeError("Concept compile response is missing a valid `hardness` frontmatter value.")
    if concept_summary_is_placeholder(markdown):
        raise RuntimeError("Concept compile response left the concept summary in fallback state.")


def _require_frontmatter_string_list(frontmatter: dict[str, Any], key: str, message: str) -> list[str]:
    value = frontmatter.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise RuntimeError(message)
    return value


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
    if output_format == "report":
        _validate_report_sections(markdown)


_REPORT_REQUIRED_SECTIONS: tuple[str, ...] = (
    "## 结论",
    "## 关键证据",
    "## 反证与不确定性",
    "## 行动建议",
    "## 下次观察信号",
    "## 引用",
)

_REPORT_SECTION_BULLET_MINIMUMS: dict[str, int] = {
    "## 关键证据": 3,
    "## 反证与不确定性": 1,
    "## 行动建议": 1,
    "## 下次观察信号": 1,
    "## 引用": 1,
}

_REPORT_PLACEHOLDER_MARKER = "_LLM:"

_REPORT_CITATION_PATTERN = re.compile(r"wiki/sources/[a-z0-9._-]+\.md")


def _validate_report_sections(markdown: str) -> None:
    """Enforce decision-grade report skeleton + per-section bullet minimums.

    Steps (in order):
      1. Scan line-anchored H2 headings outside fenced code blocks; require
         the six required sections in fixed order. Inline body matches,
         fenced-code occurrences, and longer lookalikes such as
         ``## 结论补充`` are rejected.
      2. Reject any unfilled ``_LLM:`` placeholder marker anywhere in the
         document (outside fenced code blocks). LLM is expected to replace
         every hint line before returning.
      3. For each required section listed in ``_REPORT_SECTION_BULLET_MINIMUMS``,
         count column-0 ``- `` bullets in its body (the lines between its H2
         and the next H2 or end-of-document), excluding fenced code blocks,
         empty bullets, and ``_LLM:`` placeholder lines. Sub-bullets,
         numbered lists, and continuation lines do not count.
      4. Citation integrity:
         - Dedup: every ``wiki/sources/*.md`` path under ``## 引用`` is
           unique (fence-aware; ``## 引用`` body stops at the next H2 to
           exclude the trailing ``## 参考`` block rendered by the skeleton).
         - Body ⊆ Citations: every citation path appearing in the report
           body between ``## 结论`` and ``## 引用`` (fence-aware) must also
           appear under ``## 引用``.
    """
    lines = markdown.splitlines()
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

    h2_titles = [title for _, title in h2_positions]
    cursor = 0
    matched_positions: dict[str, int] = {}
    for heading in _REPORT_REQUIRED_SECTIONS:
        try:
            found = h2_titles.index(heading, cursor)
        except ValueError as exc:
            raise RuntimeError(f"Report missing required section: {heading}") from exc
        matched_positions[heading] = h2_positions[found][0]
        cursor = found + 1

    in_fence = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith(_REPORT_PLACEHOLDER_MARKER):
            raise RuntimeError(
                f"Report contains unfilled placeholder marker '{_REPORT_PLACEHOLDER_MARKER}'."
            )

    section_ranges: dict[str, tuple[int, int]] = {}
    for position_index, (line_index, title) in enumerate(h2_positions):
        if title not in _REPORT_REQUIRED_SECTIONS:
            continue
        body_start = line_index + 1
        if position_index + 1 < len(h2_positions):
            body_end = h2_positions[position_index + 1][0]
        else:
            body_end = len(lines)
        # Record only the first occurrence (R98.1 Note 1 deferred).
        section_ranges.setdefault(title, (body_start, body_end))

    for heading, minimum in _REPORT_SECTION_BULLET_MINIMUMS.items():
        body_start, body_end = section_ranges[heading]
        bullet_count = _count_report_bullets(lines[body_start:body_end])
        if bullet_count < minimum:
            raise RuntimeError(
                f"Report section {heading} needs at least {minimum} '- ' bullets;"
                f" found {bullet_count}."
            )

    # Phase 4: citation integrity.
    # Use matched_positions (ordered match) — NOT section_ranges — to avoid
    # mismatch when a stray duplicate "## 引用" appears before the ordered
    # match. citations range is computed fresh: next H2 after the matched
    # "## 引用" line, or EOF.
    conclusion_idx = matched_positions["## 结论"]
    citations_idx = matched_positions["## 引用"]
    body_start = conclusion_idx + 1
    body_end = citations_idx
    citations_start = citations_idx + 1
    citations_end = len(lines)
    for line_index, _title in h2_positions:
        if line_index > citations_idx:
            citations_end = line_index
            break

    citation_paths = _extract_report_citations(lines[citations_start:citations_end])
    seen: set[str] = set()
    for path in citation_paths:
        if path in seen:
            raise RuntimeError(
                f"Report ## 引用 has duplicate citation path: {path}"
            )
        seen.add(path)

    body_paths = _extract_report_citations(lines[body_start:body_end])
    citation_set = set(citation_paths)
    for path in body_paths:
        if path not in citation_set:
            raise RuntimeError(
                f"Report body cites path not listed under ## 引用: {path}"
            )


def _count_report_bullets(section_lines: list[str]) -> int:
    """Count column-0 ``- `` bullets in a section body.

    Skips fenced code blocks, empty bullets (``- `` with no content), and
    ``_LLM:`` placeholder lines. Numbered lists, sub-bullets, and
    continuation lines are not counted.
    """
    count = 0
    in_fence = False
    for line in section_lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.startswith("- "):
            continue
        body = line[2:].strip()
        if not body:
            continue
        if body.startswith(_REPORT_PLACEHOLDER_MARKER):
            continue
        count += 1
    return count


def _extract_report_citations(section_lines: list[str]) -> list[str]:
    """Extract ``wiki/sources/*.md`` citation paths in order, fence-aware.

    Skips fenced code blocks (``` or ~~~). Matches are returned in line
    order; multiple matches on the same line preserve left-to-right order.
    Case-sensitive; only lowercase paths are recognized (matches existing
    fixture/skeleton conventions).
    """
    paths: list[str] = []
    in_fence = False
    for line in section_lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        paths.extend(_REPORT_CITATION_PATTERN.findall(line))
    return paths


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
    del client
    return "balanced"


def _initial_lint_prompt_profile(client: SupportsComplete) -> str:
    del client
    return "balanced"


def _retry_compile_prompt_profile(exc: Exception, current_profile: str, client: SupportsComplete) -> str:
    del exc
    del current_profile
    del client
    return ""


def _retry_lint_prompt_profile(exc: Exception, current_profile: str, client: SupportsComplete) -> str:
    del exc
    del current_profile
    del client
    return ""
