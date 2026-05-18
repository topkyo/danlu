"""Ask / file-back execution owners (炼丹炉 EP-018B group 2).

Owns the two query-facing execution surfaces previously defined inline in
``aiwiki.app_compile``:

- ``ask_question``: full query pipeline — compile-if-needed, rank sources +
  concepts, render the requested output artifact, update active corpus,
  runtime history, query-route telemetry, material state, knowledge
  lifecycle, shell summary, and wiki log.
- ``file_back``: import a derived / decision / judgment artifact from
  ``output/`` back into the curated ``wiki/`` tree with frontmatter,
  citations, review schedule, and wiki log entry; recompiles at the end.

These functions stay importable as ``aiwiki.app_compile.ask_question`` and
``aiwiki.app_compile.file_back`` through the PEP 562 compat seam at the
bottom of ``app_compile.py`` (``_LAZY_OWNERS`` now points these two names at
this module). No caller needs to change.

Note: ``utc_now`` is imported from ``aiwiki.app_compile`` (not
``aiwiki.app_utils``) because ``tests/test_app.py`` patches
``aiwiki.app_compile.utc_now`` as a hot-patch seam. Resolving through the
re-export keeps those patches effective.

``rank_concepts`` stays in ``aiwiki.app_compile`` (out of EP-018B scope) —
we import it lazily via the seam for the same reason.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_lifecycle import (
    curated_page_template,
    default_curated_status,
    refresh_knowledge_lifecycle_state,
)
from ..app_memory_query import record_query_route_telemetry
from ..app_protocol import (
    ensure_layout,
    load_protocol_state,
    protocol_paths,
    resolve_protocol,
    schedule_review_windows,
)
from ..app_queries import (
    human_query_title,
    rank_sources,
    render_decision_memo_query,
    render_figure_brief,
    render_note_answer,
    render_report,
    render_slides,
    render_sop_query,
    wiki_requires_compile,
)
from ..app_render import append_wiki_log
from ..app_routing import (
    active_corpus_bridge_evidence_ids,
    refresh_material_state,
    upsert_active_corpus,
)
from ..app_shell import build_shell_summary, write_shell_summary
from ..app_state import (
    active_archived_material_ids,
    append_runtime_history,
    load_active_corpora_state,
    load_archive_candidates_state,
    load_machine_memory,
    load_manifest,
    load_material_routing_state,
    load_material_state,
    load_output_candidates_state,
    load_runtime_history,
    output_candidates_state_path,
    upsert_output_candidate,
)
from ..app_utils import (
    _restore_file_bytes,
    _snapshot_file_bytes,
    build_citation_snapshots,
    extract_provenance_paths,
    next_available_stem,
    parse_frontmatter,
    question_signature,
    relative_path,
    render_frontmatter,
    runtime_write_operation,
    slugify,
    strip_frontmatter,
    upsert_markdown_section,
)
from ..compile import compile_wiki
from ..content.io import sync_manifest_with_raw
from ..memory.graph import build_machine_memory_query
from ..notify import notify_report_generated
from .protocol_learnings import load_learnings_for_protocol
from .receipts import write_execution_receipt
from .run_notes import run_id_for_artifact, write_run_notes, write_run_notes_frontmatter

NEXT_STEP_HINTS = {
    "derived": (
        "wiki/derived 是机器记忆终态层；不进入 review-page 工作流。"
        "如需人工审阅，请用 file-back --kind judgment 或 --kind decision。"
        "如需进入金丹链路（alchemy-start），请先用 aiwiki promote <output_ref> 注册 corpus candidate；"
        "file-back --kind derived 不写 corpus candidate plane。"
    ),
    "judgment": (
        "next: aiwiki review-page {path} "
        "--status <tentative|tracking|confirmed|rejected>"
    ),
    "decision": (
        "next: aiwiki review-page {path} "
        "--status <proposed|approved|needs-revisit|superseded>"
    ),
}

READABLE_FILENAME_MAX_CHARS = 72
OUTPUT_FORMAT_FILENAME_SUFFIXES = {
    "decision-memo": "decision-memo",
    "sop": "sop",
    "slides": "slides",
    "figure": "figure",
    "note": "note",
}


def _readable_filename_stem(label: str, *, fallback: str, max_chars: int = READABLE_FILENAME_MAX_CHARS) -> str:
    parts: list[str] = []
    pending_separator = False
    for char in label.strip():
        if char.isalnum():
            if pending_separator and parts:
                parts.append("-")
            parts.append(char.lower() if char.isascii() else char)
            pending_separator = False
        elif char in {"-", "_"} or char.isspace() or not char.isprintable() or char in {"/", "\\"}:
            pending_separator = True
        else:
            pending_separator = True
    stem = "".join(parts).strip("-_")
    if len(stem) > max_chars:
        stem = stem[:max_chars].rstrip("-_")
    return stem or fallback


def _output_artifact_seed(question: str, output_format: str) -> str:
    fallback = OUTPUT_FORMAT_FILENAME_SUFFIXES.get(output_format, output_format or "output")
    stem = _readable_filename_stem(human_query_title(question), fallback=fallback)
    suffix = OUTPUT_FORMAT_FILENAME_SUFFIXES.get(output_format)
    if suffix:
        return f"{stem}-{suffix}"
    return stem


def _file_back_entry_seed(kind: str, title: str) -> str:
    stem = _readable_filename_stem(title, fallback=kind)
    return f"{kind}-{stem}"

# ``utc_now`` and ``rank_concepts`` are resolved lazily via
# ``aiwiki.app_compile`` inside each function body. Reasons:
#
# - ``utc_now`` is a hot-patch target. ``tests/test_app.py`` patches it as
#   ``patch("aiwiki.app_compile.utc_now", ...)``. A module-level
#   ``from ..app_compile import utc_now`` would bind ``ask.utc_now`` to the
#   original callable at import time and defeat that patch everywhere in
#   this module.
# - ``rank_concepts`` is still defined in ``aiwiki.app_compile`` (out of
#   EP-018B scope). If a future EP flips it to a new owner, the lazy
#   lookup keeps working without touching this file.
#
# The same rationale applies to ``apply_machine_memory_action`` in
# ``execution/runtime_surfaces.py``; see that module for the matching
# pattern.


def _append_run_event(root: Path, event: dict[str, Any]) -> None:
    from ..runner.receipts import _append_log

    _append_log(root, event)


# Round 49: report ↔ graph anchor metadata.
# Cap to 8 anchors so frontmatter stays readable; pick top-ranked sources and
# concepts first, then include up to 2 judgments tied to those sources so the
# anchor list reflects the same evidence chain the report just rendered.
_GRAPH_ANCHOR_LIMIT = 8


def _build_graph_anchor_node_ids(
    machine_query: dict[str, Any],
    memory: dict[str, Any],
    *,
    ranked_sources: list[dict[str, Any]] | None = None,
    ranked_concepts: list[dict[str, Any]] | None = None,
) -> list[str]:
    source_ids = list(machine_query.get("ranked_source_ids", []))[:4]
    concept_slugs = list(machine_query.get("ranked_concept_slugs", []))[:4]
    # When the machine query did not find direct term matches, fall back to
    # the ranked sources/concepts the report actually rendered. Without this
    # fallback, broad questions like "compare X and Y" would yield empty
    # anchors despite the report citing real evidence.
    if not source_ids and ranked_sources:
        source_ids = [
            str(entry.get("id"))
            for entry in ranked_sources[:4]
            if isinstance(entry, dict) and entry.get("id")
        ]
    if not concept_slugs and ranked_concepts:
        concept_slugs = [
            str(concept.get("slug"))
            for concept in ranked_concepts[:4]
            if isinstance(concept, dict) and concept.get("slug")
        ]
    judgment_ids: list[str] = []
    if source_ids:
        source_set = set(source_ids)
        for edge in memory.get("edges", {}).get("source_to_judgment", []):
            if not isinstance(edge, dict):
                continue
            if str(edge.get("source_id") or "") in source_set:
                page_id = str(edge.get("page_id") or "")
                if page_id and page_id not in judgment_ids:
                    judgment_ids.append(page_id)
            if len(judgment_ids) >= 2:
                break
    anchors: list[str] = []
    for source_id in source_ids:
        anchors.append(f"source:{source_id}")
    for slug in concept_slugs:
        anchors.append(f"concept:{slug}")
    for page_id in judgment_ids:
        anchors.append(f"judgment:{page_id}")
    deduped: list[str] = []
    seen: set[str] = set()
    for anchor in anchors:
        if anchor in seen:
            continue
        seen.add(anchor)
        deduped.append(anchor)
        if len(deduped) >= _GRAPH_ANCHOR_LIMIT:
            break
    return deduped


def _resolve_anchor_md_link(anchor: str, memory: dict[str, Any], base: Path) -> str | None:
    """Resolve a ``kind:id`` anchor to a clickable Obsidian wiki-style markdown link.

    Returns ``None`` when the anchor cannot be resolved to an .md file.
    """
    if ":" not in anchor:
        return None
    kind, identifier = anchor.split(":", 1)
    if kind == "source":
        for node in memory.get("source_nodes", []):
            if isinstance(node, dict) and str(node.get("id") or "") == identifier:
                title = str(node.get("title") or identifier)
                path = f"wiki/sources/{identifier}.md"
                return f"- [{title}](../../{path})"
    elif kind == "concept":
        for node in memory.get("concept_nodes", []):
            if isinstance(node, dict) and str(node.get("slug") or "") == identifier:
                title = str(node.get("title") or identifier)
                path = f"wiki/concepts/{identifier}.md"
                return f"- [{title}](../../{path})"
    elif kind == "judgment":
        for node in memory.get("judgment_nodes", []):
            if isinstance(node, dict) and str(node.get("page_id") or "") == identifier:
                title = str(node.get("title") or identifier)
                path = str(node.get("path") or f"wiki/judgments/{identifier}.md")
                return f"- [{title}](../../{path})"
    return None


def _append_graph_anchor_section(
    destination: Path, *, anchors: list[str], memory: dict[str, Any]
) -> None:
    """Upsert a 关系图谱锚点 section with clickable .md links into the artifact body."""
    if not anchors:
        return
    lines = ["相关来源与概念（点击跳转）："]
    lines.append("")
    for anchor in anchors:
        link = _resolve_anchor_md_link(anchor, memory, destination.parent)
        if link:
            lines.append(link)
        else:
            lines.append(f"- `{anchor}`")
    body = destination.read_text(encoding="utf-8", errors="replace")
    body = upsert_markdown_section(body, "关系图谱锚点", "\n".join(lines))
    destination.write_text(body.rstrip() + "\n", encoding="utf-8")


def apply_graph_anchors_to_artifact(
    destination: Path, *, anchors: list[str], memory: dict[str, Any]
) -> None:
    """Write graph anchor frontmatter and the human-readable anchor section.

    Used by deterministic ``ask_question`` immediately and by ``run_ask``
    after the LLM has replaced the artifact body.
    """
    if not anchors:
        return
    from .candidates import write_graph_anchor_frontmatter

    write_graph_anchor_frontmatter(destination, anchors=anchors)
    _append_graph_anchor_section(destination, anchors=anchors, memory=memory)


@runtime_write_operation
def ask_question(
    root: Path,
    question: str,
    output_format: str,
    protocol: str | None = None,
    *,
    no_cache: bool = False,
    corpus_id_override: str | None = None,
    load_protocol_learnings: bool = False,
    write_graph_anchors: bool = True,
) -> dict[str, Any]:
    from .. import app_compile as _app_compile

    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    if wiki_requires_compile(root, entries):
        compile_wiki(root)
        manifest = load_manifest(root)
        entries = manifest["entries"]
    protocol_state = load_protocol_state(root)
    active_protocol = resolve_protocol(root, protocol)
    if active_protocol != protocol_state["active_protocol"]:
        protocol_state = {
            **protocol_state,
            "active_protocol": active_protocol,
        }
    blocked_source_ids = active_archived_material_ids(root)
    material_state = load_material_state(root)
    routing_state = load_material_routing_state(root)
    archive_candidates = load_archive_candidates_state(root)
    memory = load_machine_memory(root)
    machine_query = build_machine_memory_query(
        memory,
        question,
        root=root,
        protocol=active_protocol,
        material_state=material_state,
        routing_state=routing_state,
        archive_candidates=archive_candidates,
        no_cache=no_cache,
    )
    ranked_concepts = _app_compile.rank_concepts(
        root,
        question,
        boost_concept_slugs=set(machine_query["ranked_concept_slugs"]),
        protocol=active_protocol,
    )
    boosted_ids: set[str] = set(machine_query["ranked_source_ids"])
    for concept in ranked_concepts:
        for source_page in concept.get("source_pages", []):
            if isinstance(source_page, str) and source_page.startswith("wiki/sources/") and source_page.endswith(".md"):
                boosted_ids.add(Path(source_page).stem)
    ranked = rank_sources(root, entries, question, boost_source_ids=boosted_ids, protocol=active_protocol)
    created_at = _app_compile.utc_now()
    artifact_seed = _output_artifact_seed(question, output_format)

    if output_format == "report":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_report(root, question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    elif output_format == "decision-memo":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_decision_memo_query(
            root,
            question,
            ranked,
            ranked_concepts,
            machine_query,
            protocol_state,
            created_at,
            artifact_id,
        )
    elif output_format == "sop":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_sop_query(
            root,
            question,
            ranked,
            ranked_concepts,
            machine_query,
            protocol_state,
            created_at,
            artifact_id,
        )
    elif output_format == "note":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_note_answer(
            root,
            question,
            ranked,
            ranked_concepts,
            machine_query,
            protocol_state,
            created_at,
            artifact_id,
        )
    elif output_format == "slides":
        directory = root / "output" / "slides"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_slides(root, question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    elif output_format == "figure":
        directory = root / "output" / "figures"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_figure_brief(root, question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    else:
        raise ValueError(f"Unsupported format: {output_format}")

    if load_protocol_learnings:
        learnings = load_learnings_for_protocol(root, active_protocol)
        if learnings:
            block_lines = ["", "## Protocol Learnings", ""]
            for learning in learnings:
                block_lines.append(f"- [{learning['learning_id']}] {learning['title']}: {learning['lesson']}")
            block = "\n".join(block_lines) + "\n"
            insert_at = content.find("\n## ")
            if insert_at >= 0:
                content = content[:insert_at] + block + content[insert_at:]
            else:
                content += block

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    artifact_ref = relative_path(root, destination)
    bridge_evidence_ids = active_corpus_bridge_evidence_ids(
        machine_query,
        [entry["id"] for entry in ranked],
        routing_state=routing_state,
        active_protocol=active_protocol,
        blocked_source_ids=blocked_source_ids,
    )
    active_corpus = upsert_active_corpus(
        root,
        protocol=active_protocol,
        question=question,
        source_ids=[entry["id"] for entry in ranked],
        concept_slugs=[concept["slug"] for concept in ranked_concepts],
        bridge_evidence_ids=bridge_evidence_ids,
        output_ref=artifact_ref,
        changed_at=created_at,
        corpus_id_override=corpus_id_override,
    )
    # 在已有 frontmatter 闭合前插入 candidate_state，避免 round-trip 破坏
    # raw YAML literal（如 slides 的 `marp: true`）；无 frontmatter 时合成最小 header。
    from .candidates import write_candidate_frontmatter

    write_candidate_frontmatter(
        destination,
        candidate_state="pending",
        corpus_id=active_corpus["corpus_id"],
    )
    anchors = _build_graph_anchor_node_ids(
        machine_query,
        memory,
        ranked_sources=ranked,
        ranked_concepts=ranked_concepts,
    )
    # ``run_ask`` calls ``ask_question`` first to produce a deterministic
    # baseline, then overwrites the file with LLM output. Writing anchors here
    # would also poison ``current_artifact`` fed into the LLM prompt. The
    # caller in run_ask passes ``write_graph_anchors=False`` and re-applies
    # via ``apply_graph_anchors_to_artifact`` after the LLM step.
    if write_graph_anchors and anchors:
        apply_graph_anchors_to_artifact(destination, anchors=anchors, memory=memory)
    run_id = run_id_for_artifact(artifact_ref)
    run_notes = write_run_notes(
        root,
        run_id=run_id,
        status="deterministic-ready",
        question=question,
        output_format=output_format,
        protocol=active_protocol,
        output_path=artifact_ref,
        source_count=len(ranked),
        concept_count=len(ranked_concepts),
        stages=[
            "Received request and selected the active protocol.",
            f"Ranked {len(ranked)} source pages and {len(ranked_concepts)} concept pages for context.",
            "Rendered deterministic output artifact with provenance references.",
        ],
    )
    write_run_notes_frontmatter(destination, run_id=run_id, run_notes_ref=run_notes["run_notes_path"])
    upsert_output_candidate(
        root,
        artifact_ref=artifact_ref,
        candidate_state="pending",
        created_at=created_at,
        updated_at=created_at,
        format=output_format,
        protocol=active_protocol,
        corpus_id=active_corpus["corpus_id"],
        question=question,
    )
    append_runtime_history(
        root,
        {
            "event_type": "query",
            "occurred_at": created_at,
            "protocol": active_protocol,
            "corpus_id": active_corpus["corpus_id"],
            "focus_kind": "question",
            "focus_ref": question,
            "question_hash": question_signature(question),
            "output_format": output_format,
            "output_ref": artifact_ref,
            "run_id": run_notes["run_id"],
            "run_notes_path": run_notes["run_notes_path"],
            "source_ids": [entry["id"] for entry in ranked],
            "concept_slugs": [concept["slug"] for concept in ranked_concepts],
            "bridge_evidence_ids": bridge_evidence_ids,
            "touched_component_ids": machine_query.get("touched_component_ids", []),
            "time_focus": str(machine_query.get("time_focus") or ""),
            "archive_recall_hint_ids": [
                str(item.get("entry_id") or "")
                for item in machine_query.get("archive_recall_hints", [])
                if isinstance(item, dict) and item.get("entry_id")
            ],
        },
    )
    route_telemetry = record_query_route_telemetry(
        root,
        question=question,
        machine_query=machine_query,
        protocol=active_protocol,
        occurred_at=created_at,
    )
    last_route_entry = route_telemetry.get("last_entry") if isinstance(route_telemetry, dict) else {}
    if isinstance(last_route_entry, dict):
        machine_query["route_telemetry"] = {
            key: value
            for key, value in last_route_entry.items()
            if key not in {"occurred_at", "question_preview"}
        }
    else:
        machine_query["route_telemetry"] = dict(machine_query.get("route_telemetry") or {})
    refresh_material_state(root, generated_at=created_at, active_protocol=active_protocol)
    refresh_knowledge_lifecycle_state(
        root,
        generated_at=created_at,
        entries=manifest["entries"],
        active_corpora_state=load_active_corpora_state(root),
        memory=memory,
    )
    write_shell_summary(root, build_shell_summary(root, generated_at=created_at))
    try:
        notify_report_generated(
            root,
            {
                "path": artifact_ref,
                "title": question,
                "protocol": active_protocol,
                "format": output_format,
                "created_at": created_at,
            },
        )
    except Exception as exc:
        _append_run_event(
            root,
            {
                "event": "notify_dispatch_failed",
                "reason": str(exc),
                "error_type": type(exc).__name__,
                "artifact": artifact_ref,
                "protocol": active_protocol,
            },
        )
    append_wiki_log(
        root,
        "query",
        question,
        [
            f"format: `{output_format}`",
            f"artifact: `{artifact_ref}`",
            f"ranked_sources: `{len(ranked)}`",
            f"ranked_concepts: `{len(ranked_concepts)}`",
            f"protocol: `{active_protocol}`",
            f"active_corpus: `{active_corpus['corpus_id']}`",
            f"machine_terms: `{len(machine_query['matched_terms'])}`",
            f"machine_hits: `{len(machine_query['ranked_source_ids'])}/{len(machine_query['ranked_concept_slugs'])}`",
            f"time_focus: `{str(machine_query.get('time_focus') or 'none')}`",
            f"protocol_shard_sources: `{len(machine_query.get('protocol_shard_source_ids', []))}`",
            f"time_shard_sources: `{len(machine_query.get('time_shard_source_ids', []))}`",
            f"archive_recall_hints: `{len(machine_query.get('archive_recall_hints', []))}`",
            f"bridge_concepts: `{len(machine_query['bridge_concept_slugs'])}`",
            f"query_routes: `{len(machine_query['query_routes'])}`",
            f"route_strategy: `{machine_query.get('selected_strategy', 'concept-first')}`",
        ],
    )
    return {
        "path": artifact_ref,
        **run_notes,
        "format": output_format,
        "protocol": active_protocol,
        "no_cache": no_cache,
        "active_corpus_id": active_corpus["corpus_id"],
        "ranked_sources": [entry["id"] for entry in ranked],
        "ranked_concepts": [concept["slug"] for concept in ranked_concepts],
        "graph_anchor_node_ids": anchors,
        "machine_memory_query": machine_query,
        "index_pages": [
            "wiki/indexes/index.md",
            "wiki/indexes/sources.md",
            "wiki/indexes/concepts.md",
            "wiki/indexes/decisions.md",
            "wiki/indexes/judgments.md",
            "wiki/indexes/judgment-assets.md",
            "wiki/indexes/agent-workbench.md",
            "wiki/indexes/cognitive-history.md",
            "wiki/indexes/output-packs.md",
            "wiki/indexes/domain-pilots.md",
            "wiki/indexes/protocols.md",
            "wiki/indexes/review-queue.md",
            "wiki/indexes/review-center.md",
            "wiki/indexes/aging-report.md",
            "wiki/indexes/compile-status.md",
            "wiki/indexes/concept-quality.md",
            "wiki/indexes/machine-memory.md",
            "wiki/indexes/graph-view.md",
            "wiki/indexes/machine-memory-topology.md",
            "wiki/indexes/machine-memory-actions.md",
            "wiki/indexes/machine-memory-repair-plan.md",
            "wiki/indexes/graph-health.md",
            "wiki/indexes/drift-report.md",
            "wiki/indexes/repair-backlog.md",
            "wiki/indexes/log.md",
            "schema/index.md",
            "schema/protocols/index.md",
        ],
        "protocol_pages": protocol_paths(root, active_protocol),
    }


def load_previous_output_summary(root: Path, corpus_id: str, *, exclude_artifact_ref: str | None = None) -> str | None:
    """从 runtime history 找 corpus_id 最近一轮 output，读出摘要（frontmatter + 首段）。"""

    for event in reversed(load_runtime_history(root)):
        if not isinstance(event, dict):
            continue
        if str(event.get("corpus_id") or "") != corpus_id:
            continue
        output_ref = str(event.get("output_ref") or "")
        if not output_ref or output_ref == exclude_artifact_ref:
            continue
        output_path = root / output_ref
        if not output_path.exists():
            continue
        text = output_path.read_text(encoding="utf-8", errors="replace")
        body = strip_frontmatter(text)
        lines_text = text.splitlines()
        frontmatter_lines: list[str] = []
        if lines_text and lines_text[0].strip() == "---":
            for index, line in enumerate(lines_text[1:], start=1):
                if line.strip() == "---":
                    frontmatter_lines = lines_text[1:index]
                    break
        lines = [f"来源：{output_ref}", "---", "\n".join(frontmatter_lines).strip() or "(no frontmatter)", "---"]
        paragraph: list[str] = []
        for line in body.splitlines():
            if line.startswith("#"):
                if paragraph:
                    break
                continue
            if line.strip():
                paragraph.append(line)
            elif paragraph:
                break
        lines.extend(paragraph[:20] or ["(no body)"])
        return "\n".join(lines)
    return None


@runtime_write_operation
def file_back(
    root: Path,
    artifact: str,
    title: str | None = None,
    kind: str = "derived",
    protocol: str | None = None,
) -> dict[str, Any]:
    from .. import app_compile as _app_compile

    ensure_layout(root)
    candidate = Path(artifact)
    artifact_path = candidate if candidate.is_absolute() else (root / candidate)
    artifact_path = artifact_path.resolve()
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Artifact not found: {artifact}")
    if artifact_path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        raise ValueError("Only markdown or text artifacts can be filed back in the MVP.")
    if kind not in {"derived", "decision", "judgment"}:
        raise ValueError(f"Unsupported filed-back kind: {kind}")

    filed_at = _app_compile.utc_now()
    artifact_ref = (
        relative_path(root, artifact_path) if artifact_path.is_relative_to(root) else str(artifact_path)
    )
    original = artifact_path.read_text(encoding="utf-8", errors="replace")
    original_frontmatter = parse_frontmatter(original)
    citations = extract_provenance_paths(root, original)
    citation_snapshots = build_citation_snapshots(root, citations)
    source_protocol = str(original_frontmatter.get("protocol") or "").strip()
    resolved_protocol = resolve_protocol(root, protocol or source_protocol or None)
    entry_seed = _file_back_entry_seed(kind, title or artifact_path.stem)
    directory = {
        "derived": root / "wiki" / "derived",
        "decision": root / "wiki" / "decisions",
        "judgment": root / "wiki" / "judgments",
    }[kind]
    directory.mkdir(parents=True, exist_ok=True)
    entry_id = next_available_stem(directory, entry_seed)
    destination = directory / f"{entry_id}.md"
    revisit_after = ""
    escalate_after = ""
    if kind in {"decision", "judgment"}:
        revisit_after, escalate_after = schedule_review_windows(
            kind,
            default_curated_status(kind),
            filed_at,
            protocol=resolved_protocol,
            root=root,
        )
    from aiwiki.app_protocol import protocol_judgment_extra_fields

    frontmatter_payload: dict[str, Any] = {
        "id": entry_id,
        "kind": kind,
        "status": default_curated_status(kind),
        "title": title or artifact_path.stem,
        "protocol": resolved_protocol,
        "source_files": [artifact_ref],
        "citations": citations,
        "citation_snapshots": citation_snapshots,
        "generated_by": "aiwiki-file-back",
        "last_compiled_at": filed_at,
        "confidence": "medium",
        "counter_evidence": [],
        "invalidation_rule": "",
        "next_signals": [],
        "formed_at": filed_at,
        "last_reviewed": "",
        "reviewed_at": "",
        "revisit_after": revisit_after,
        "escalate_after": escalate_after,
    }
    # P4-INV-3 (Round 59): inject protocol-specific frontmatter slots so that
    # investing pages get thesis / catalyst / risk / invalidation_threshold,
    # research gets hypothesis / falsification, etc. Empty values are
    # intentional placeholders — lint stays happy, downstream consumers see
    # the schema slot.
    frontmatter_payload.update(
        protocol_judgment_extra_fields(resolved_protocol, kind)
    )
    frontmatter = render_frontmatter(frontmatter_payload)
    stripped = strip_frontmatter(original).strip()
    body_lines = curated_page_template(
        kind=kind,
        protocol=resolved_protocol,
        title=title or artifact_path.stem,
        artifact_ref=artifact_ref,
        filed_at=filed_at,
        revisit_after=revisit_after,
        escalate_after=escalate_after,
        supporting_body=stripped,
    )
    payload = "\n".join([frontmatter, "", *body_lines]).rstrip() + "\n"
    destination_snapshot = _snapshot_file_bytes(destination)
    output_candidates_snapshot = _snapshot_file_bytes(output_candidates_state_path(root))
    wiki_log_snapshot = _snapshot_file_bytes(root / "wiki" / "indexes" / "log.md")
    destination.write_text(payload, encoding="utf-8")
    try:
        candidate_state = load_output_candidates_state(root)
        for candidate in candidate_state.get("candidates", []):
            if candidate.get("artifact_ref") == artifact_ref:
                upsert_output_candidate(
                    root,
                    artifact_ref=artifact_ref,
                    candidate_state="promoted",
                    created_at=str(candidate.get("created_at") or filed_at),
                    updated_at=filed_at,
                    format=str(candidate.get("format") or ""),
                    protocol=str(candidate.get("protocol") or resolved_protocol),
                    corpus_id=str(candidate.get("corpus_id") or ""),
                    question=str(candidate.get("question") or ""),
                    promoted_to=relative_path(root, destination),
                    promoted_at=filed_at,
                    promotion_origin=str(candidate.get("promotion_origin") or "manual"),
                )
                break
        append_wiki_log(
            root,
            "file-back",
            title or artifact_path.stem,
            [
                f"kind: `{kind}`",
                f"protocol: `{resolved_protocol}`",
                f"from: `{artifact_ref}`",
                f"destination: `{relative_path(root, destination)}`",
            ],
        )
        compile_wiki(root)
        destination_ref = relative_path(root, destination)
        write_execution_receipt(
            root,
            operation="file-back",
            generated_by="aiwiki-file-back",
            subject_kind="output-artifact",
            subject_id=str(original_frontmatter.get("id") or original_frontmatter.get("_id") or artifact_path.stem),
            target_file=artifact_ref,
            primary_path=artifact_ref,
            secondary_path=destination_ref,
            protocol=resolved_protocol,
            extra={
                "filed_kind": kind,
                "title": title or artifact_path.stem,
            },
        )
    except Exception:
        _restore_file_bytes(root / "wiki" / "indexes" / "log.md", wiki_log_snapshot)
        _restore_file_bytes(output_candidates_state_path(root), output_candidates_snapshot)
        _restore_file_bytes(destination, destination_snapshot)
        raise
    next_step_hint = NEXT_STEP_HINTS[kind]
    if kind in {"decision", "judgment"}:
        next_step_hint = next_step_hint.format(path=destination_ref)
    return {"path": destination_ref, "protocol": resolved_protocol, "next_step_hint": next_step_hint}


__all__ = ["ask_question", "file_back"]
