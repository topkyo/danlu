"""Ask execution owner (炼丹炉 EP-018B group 2).

Owns the query-facing ``ask_question`` surface previously defined inline in
``aiwiki.app_compile``: compile-if-needed, rank sources + concepts, render the
requested output artifact, update active corpus, runtime history, query-route
telemetry, material state, knowledge lifecycle, shell summary, and wiki log.

``file_back`` lives in ``execution.file_back``. Graph-anchor helpers remain here
for ask + ``run_ask`` write-back.

Note: ``utc_now`` is imported lazily from ``aiwiki.utils.time`` inside each
function body so that ``patch("aiwiki.utils.time.utc_now")`` in acceptance
tests + downstream suites still intercepts the call.

``rank_concepts`` is owned by ``aiwiki.compile.ranking`` — we import it
lazily from that owner for the same hot-patch symmetry reason.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_shell.meta import write_shell_summary
from ..app_shell.summary import build_shell_summary
from ..compile import compile_wiki
from ..compile.content_step import wiki_requires_compile
from ..compile.ranking import compound_rank_boosts, rank_sources, ranked_compound_page_paths
from ..content.archive import active_archived_material_ids, load_archive_candidates_state, load_material_routing_state
from ..content.io import sync_manifest_with_raw
from ..content.material import (
    active_corpus_bridge_evidence_ids,
    load_active_corpora_state,
    load_material_state,
    refresh_material_state,
    upsert_active_corpus,
)
from ..input_router import is_obsidian_open_link
from ..lifecycle.knowledge import refresh_knowledge_lifecycle_state
from ..memory.graph_query import build_machine_memory_query
from ..memory.state import load_machine_memory
from ..notify import notify_report_generated
from ..planner.state import record_query_route_telemetry
from ..protocol.descriptors import protocol_paths
from ..protocol.scaffold import ensure_layout
from ..protocol.state import load_protocol_state, resolve_protocol
from ..render.ask_report import build_ask_used_refs, render_report
from ..render.paths import append_wiki_log
from ..state.manifest import load_manifest
from ..utils.hash import question_signature
from ..utils.io import atomic_write_text, runtime_write_operation
from ..utils.markdown import (
    frontmatter_string_list,
    parse_frontmatter,
    strip_frontmatter,
    upsert_markdown_section,
)
from ..utils.path import next_available_stem, relative_path
from ..utils.text import human_query_title
from .candidates import upsert_output_candidate
from .file_back import _readable_filename_stem
from .history import append_runtime_history, load_runtime_history
from .run_notes import run_id_for_artifact, write_run_notes, write_run_notes_frontmatter


def _output_artifact_seed(question: str, output_format: str) -> str:
    if output_format != "report":
        raise ValueError(f"Unsupported format: {output_format}")
    return _readable_filename_stem(human_query_title(question), fallback="report")


# ``utc_now`` is resolved lazily via ``aiwiki.utils.time`` inside each
# function body. Reason: ``utc_now`` is a hot-patch target
# (``patch("aiwiki.utils.time.utc_now", ...)``). A module-level
# ``from ..utils.time import utc_now`` would bind ``ask.utc_now`` to the
# original callable at import time and defeat that patch everywhere in
# this module.
#
# ``rank_concepts`` is imported lazily from ``aiwiki.compile.ranking``
# (its owner since the reverse-dependency cleanup) inside the function
# body for symmetry with ``utc_now``.


def _append_run_event(root: Path, event: dict[str, Any]) -> None:
    from ..runner.receipts import _append_log

    _append_log(root, event)


# Round 49: report ↔ graph anchor metadata.
# Cap to 8 anchors so frontmatter stays readable; pick top-ranked sources and
# concepts first, then include up to 2 judgments tied to those sources so the
# anchor list reflects the same evidence chain the report just rendered.
_GRAPH_ANCHOR_LIMIT = 8
_CURATED_PROVENANCE_LIMIT = 4




def _collect_curated_provenance_refs(
    root: Path,
    memory: dict[str, Any],
    machine_query: dict[str, Any],
    ranked_sources: list[dict[str, Any]],
    *,
    limit: int = _CURATED_PROVENANCE_LIMIT,
) -> list[str]:
    source_ids: list[str] = []
    for entry in ranked_sources:
        source_id = str(entry.get("id") or "").strip()
        if source_id and source_id not in source_ids:
            source_ids.append(source_id)
    for source_id in machine_query.get("ranked_source_ids", []):
        normalized = str(source_id or "").strip()
        if normalized and normalized not in source_ids:
            source_ids.append(normalized)

    refs: list[str] = []
    edges = memory.get("edges", {}).get("source_to_judgment", [])
    for source_id in source_ids:
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            if str(edge.get("source_id") or "").strip() != source_id:
                continue
            page_id = str(edge.get("page_id") or "").strip()
            if not page_id:
                continue
            ref = f"wiki/judgments/{page_id}.md"
            if not (root / ref).exists() or ref in refs:
                continue
            refs.append(ref)
            if len(refs) >= limit:
                return refs
    return refs


def _merge_source_files_frontmatter(path: Path, refs: list[str]) -> None:
    _merge_frontmatter_string_list(path, "source_files", refs, merge_existing=True)


def _merge_frontmatter_string_list(path: Path, key: str, refs: list[str], *, merge_existing: bool = False) -> None:
    cleaned: list[str] = []
    for ref in refs:
        normalized = str(ref).strip()
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    if not cleaned and not merge_existing:
        return

    original = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(original)
    merged: list[str] = []
    existing = frontmatter_string_list(frontmatter, key) if merge_existing else []
    for ref in [*existing, *cleaned]:
        if ref not in merged:
            merged.append(ref)
    if not merged:
        return

    block = [f"{key}:", *[f'  - "{ref}"' for ref in merged]]
    lines = original.splitlines()
    has_frontmatter = bool(lines) and lines[0].strip() == "---"
    close_idx: int | None = None
    if has_frontmatter:
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                close_idx = idx
                break
    if not has_frontmatter or close_idx is None:
        synthesized = ["---", *block, "---", *lines]
        atomic_write_text(path, "\n".join(synthesized).rstrip() + "\n")
        return

    filtered: list[str] = lines[:1]
    skip_list_items = False
    for line in lines[1:close_idx]:
        if line.startswith(f"{key}:"):
            skip_list_items = True
            continue
        if skip_list_items and line.startswith("  - "):
            continue
        skip_list_items = False
        filtered.append(line)
    new_close_idx = len(filtered)
    filtered.append(lines[close_idx])
    filtered.extend(lines[close_idx + 1 :])
    for offset, line in enumerate(block):
        filtered.insert(new_close_idx + offset, line)
    atomic_write_text(path, "\n".join(filtered).rstrip() + "\n")


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
            str(entry.get("id")) for entry in ranked_sources[:4] if isinstance(entry, dict) and entry.get("id")
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


def _obsidian_wikilink(vault_path: str, title: str) -> str:
    clean = str(vault_path or "").replace("\\", "/").strip()
    if clean.endswith(".md"):
        clean = clean[:-3]
    alias = str(title or clean).strip() or clean
    return f"[[{clean}|{alias}]]"


def _resolve_anchor_md_link(anchor: str, memory: dict[str, Any], base: Path) -> str | None:
    """Resolve a ``kind:id`` anchor to an Obsidian wikilink for the native graph view.

    Returns ``None`` when the anchor cannot be resolved to an .md file.
    """
    del base  # vault-relative links do not depend on the artifact directory.
    if ":" not in anchor:
        return None
    kind, identifier = anchor.split(":", 1)
    if kind == "source":
        for node in memory.get("source_nodes", []):
            if isinstance(node, dict) and str(node.get("id") or "") == identifier:
                title = str(node.get("title") or identifier)
                return f"- {_obsidian_wikilink(f'wiki/sources/{identifier}.md', title)}"
    elif kind == "concept":
        for node in memory.get("concept_nodes", []):
            if isinstance(node, dict) and str(node.get("slug") or "") == identifier:
                title = str(node.get("title") or identifier)
                return f"- {_obsidian_wikilink(f'wiki/concepts/{identifier}.md', title)}"
    elif kind == "judgment":
        for node in memory.get("judgment_nodes", []):
            if isinstance(node, dict) and str(node.get("page_id") or "") == identifier:
                title = str(node.get("title") or identifier)
                path = str(node.get("path") or f"wiki/judgments/{identifier}.md")
                return f"- {_obsidian_wikilink(path, title)}"
    return None


def _append_graph_anchor_section(destination: Path, *, anchors: list[str], memory: dict[str, Any]) -> None:
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
    atomic_write_text(destination, body.rstrip() + "\n")


def apply_graph_anchors_to_artifact(destination: Path, *, anchors: list[str], memory: dict[str, Any]) -> None:
    """Write graph anchor frontmatter and the human-readable anchor section.

    Used by deterministic ``ask_question`` immediately and by ``run_ask``
    after the LLM has replaced the artifact body.
    """
    if not anchors:
        return
    from ..vault_obsidian_graph import apply_native_graph_anchor_section, native_graph_anchor_ids
    from .candidates import write_graph_anchor_frontmatter, write_machine_memory_anchor_frontmatter

    native = native_graph_anchor_ids(anchors)
    if anchors and any(str(item).startswith("concept:") for item in anchors):
        write_machine_memory_anchor_frontmatter(destination, anchors=anchors)
    write_graph_anchor_frontmatter(
        destination,
        anchors=native,
        force=bool(anchors) and native != anchors,
    )
    apply_native_graph_anchor_section(destination, anchors=native, memory=memory)


def _prepare_ask_query_context(
    root: Path,
    question: str,
    protocol: str | None,
    *,
    no_cache: bool,
    output_format: str,
) -> dict[str, Any]:
    from ..compile.ranking import rank_concepts
    from ..utils.time import utc_now

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
    compound_source_boosts, compound_concept_boosts = compound_rank_boosts(memory, machine_query)
    ranked_concepts = rank_concepts(
        root,
        question,
        boost_concept_slugs=set(machine_query["ranked_concept_slugs"]) | compound_concept_boosts,
        protocol=active_protocol,
    )
    boosted_ids: set[str] = set(machine_query["ranked_source_ids"]) | compound_source_boosts
    for concept in ranked_concepts:
        for source_page in concept.get("source_pages", []):
            if isinstance(source_page, str) and source_page.startswith("wiki/sources/") and source_page.endswith(".md"):
                boosted_ids.add(Path(source_page).stem)
    ranked = rank_sources(root, entries, question, boost_source_ids=boosted_ids, protocol=active_protocol)
    created_at = utc_now()
    artifact_seed = _output_artifact_seed(question, output_format)
    return {
        "manifest": manifest,
        "entries": entries,
        "active_protocol": active_protocol,
        "protocol_state": protocol_state,
        "blocked_source_ids": blocked_source_ids,
        "material_state": material_state,
        "routing_state": routing_state,
        "memory": memory,
        "machine_query": machine_query,
        "ranked_concepts": ranked_concepts,
        "ranked": ranked,
        "created_at": created_at,
        "artifact_seed": artifact_seed,
    }


def _materialize_ask_report_artifact(
    root: Path,
    ctx: dict[str, Any],
    question: str,
    output_format: str,
    *,
    corpus_id_override: str | None,
    write_graph_anchors: bool,
) -> dict[str, Any]:
    active_protocol = ctx["active_protocol"]
    protocol_state = ctx["protocol_state"]
    blocked_source_ids = ctx["blocked_source_ids"]
    routing_state = ctx["routing_state"]
    memory = ctx["memory"]
    machine_query = ctx["machine_query"]
    ranked_concepts = ctx["ranked_concepts"]
    ranked = ctx["ranked"]
    created_at = ctx["created_at"]
    artifact_seed = ctx["artifact_seed"]

    if output_format != "report":
        raise ValueError(f"Unsupported format: {output_format}")
    directory = root / "output" / "reports"
    artifact_id = next_available_stem(directory, artifact_seed)
    destination = directory / f"{artifact_id}.md"
    content = render_report(
        root,
        question,
        ranked,
        ranked_concepts,
        machine_query,
        protocol_state,
        created_at,
        artifact_id,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, content)
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
    curated_provenance_refs = _collect_curated_provenance_refs(
        root,
        memory,
        machine_query,
        ranked,
    )
    _merge_source_files_frontmatter(destination, curated_provenance_refs)
    compound_paths = ranked_compound_page_paths(machine_query)
    used_refs = build_ask_used_refs(
        ranked_sources=ranked,
        ranked_concepts=ranked_concepts,
        compound_paths=compound_paths,
    )
    _merge_frontmatter_string_list(destination, "used_refs", used_refs)
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
    return {
        "destination": destination,
        "artifact_id": artifact_id,
        "artifact_ref": artifact_ref,
        "active_corpus": active_corpus,
        "bridge_evidence_ids": bridge_evidence_ids,
        "used_refs": used_refs,
        "anchors": anchors,
    }


def _finalize_ask_question(
    root: Path,
    ctx: dict[str, Any],
    artifact: dict[str, Any],
    question: str,
    output_format: str,
    *,
    no_cache: bool,
    notify: bool,
) -> dict[str, Any]:
    manifest = ctx["manifest"]
    active_protocol = ctx["active_protocol"]
    memory = ctx["memory"]
    machine_query = ctx["machine_query"]
    ranked_concepts = ctx["ranked_concepts"]
    ranked = ctx["ranked"]
    created_at = ctx["created_at"]
    destination = artifact["destination"]
    artifact_ref = artifact["artifact_ref"]
    active_corpus = artifact["active_corpus"]
    bridge_evidence_ids = artifact["bridge_evidence_ids"]
    used_refs = artifact["used_refs"]
    anchors = artifact["anchors"]

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
            key: value for key, value in last_route_entry.items() if key not in {"occurred_at", "question_preview"}
        }
    else:
        machine_query["route_telemetry"] = dict(machine_query.get("route_telemetry") or {})
    refresh_material_state(
        root,
        generated_at=created_at,
        active_protocol=active_protocol,
        machine_memory=load_machine_memory(root),
    )
    refresh_knowledge_lifecycle_state(
        root,
        generated_at=created_at,
        entries=manifest["entries"],
        active_corpora_state=load_active_corpora_state(root),
        memory=memory,
    )
    write_shell_summary(root, build_shell_summary(root, generated_at=created_at))
    if notify:
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
        "used_refs": used_refs,
        "graph_anchor_node_ids": anchors,
        "machine_memory_query": machine_query,
        "index_pages": [
            "wiki/indexes/index.md",
            "wiki/indexes/sources.md",
            "wiki/indexes/concepts.md",
            "wiki/indexes/decisions.md",
            "wiki/indexes/judgments.md",
            "wiki/indexes/judgment-assets.md",
            "wiki/indexes/protocols.md",
            "wiki/indexes/review-queue.md",
            "wiki/indexes/review-center.md",
            "wiki/indexes/compile-status.md",
            "wiki/indexes/machine-memory.md",
            "wiki/indexes/graph-view.md",
            "wiki/indexes/repair-backlog.md",
            "schema/index.md",
            "schema/protocols/index.md",
        ],
        "protocol_pages": protocol_paths(root, active_protocol),
    }


@runtime_write_operation
def ask_question(
    root: Path,
    question: str,
    output_format: str,
    protocol: str | None = None,
    *,
    no_cache: bool = False,
    corpus_id_override: str | None = None,
    write_graph_anchors: bool = True,
    notify: bool = True,
) -> dict[str, Any]:
    if is_obsidian_open_link(question):
        raise ValueError("obsidian open links are navigation targets, not questions")

    ctx = _prepare_ask_query_context(
        root,
        question,
        protocol,
        no_cache=no_cache,
        output_format=output_format,
    )
    artifact = _materialize_ask_report_artifact(
        root,
        ctx,
        question,
        output_format,
        corpus_id_override=corpus_id_override,
        write_graph_anchors=write_graph_anchors,
    )
    return _finalize_ask_question(
        root,
        ctx,
        artifact,
        question,
        output_format,
        no_cache=no_cache,
        notify=notify,
    )


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



__all__ = ["ask_question", "apply_graph_anchors_to_artifact", "load_previous_output_summary"]
