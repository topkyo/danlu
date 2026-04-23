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

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..app_content import sync_manifest_with_raw
from ..app_lifecycle import (
    curated_page_template,
    default_curated_status,
    refresh_knowledge_lifecycle_state,
)
from ..app_memory_query import record_query_route_telemetry
from ..app_memory_surfaces import build_machine_memory_query
from ..app_protocol import (
    ensure_layout,
    load_protocol_state,
    protocol_paths,
    resolve_protocol,
    schedule_review_windows,
)
from ..app_queries import (
    rank_sources,
    render_decision_memo_query,
    render_figure_brief,
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
)
from ..app_utils import (
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
)
from ..compile import compile_wiki

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


@runtime_write_operation
def ask_question(
    root: Path,
    question: str,
    output_format: str,
    protocol: str | None = None,
    *,
    no_cache: bool = False,
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
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_seed = f"query-{stamp}-{slugify(question)[:48]}"

    if output_format == "report":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, artifact_seed)
        destination = directory / f"{artifact_id}.md"
        content = render_report(root, question, ranked, ranked_concepts, machine_query, protocol_state, created_at, artifact_id)
    elif output_format == "decision-memo":
        directory = root / "output" / "reports"
        artifact_id = next_available_stem(directory, f"{artifact_seed}-decision-memo")
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
        artifact_id = next_available_stem(directory, f"{artifact_seed}-sop")
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
        "format": output_format,
        "protocol": active_protocol,
        "no_cache": no_cache,
        "active_corpus_id": active_corpus["corpus_id"],
        "ranked_sources": [entry["id"] for entry in ranked],
        "ranked_concepts": [concept["slug"] for concept in ranked_concepts],
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
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_ref = (
        relative_path(root, artifact_path) if artifact_path.is_relative_to(root) else str(artifact_path)
    )
    original = artifact_path.read_text(encoding="utf-8", errors="replace")
    original_frontmatter = parse_frontmatter(original)
    citations = extract_provenance_paths(root, original)
    citation_snapshots = build_citation_snapshots(root, citations)
    source_protocol = str(original_frontmatter.get("protocol") or "").strip()
    resolved_protocol = resolve_protocol(root, protocol or source_protocol or None)
    entry_seed = f"{kind}-{stamp}-{slugify(title or artifact_path.stem)[:48]}"
    directory = {
        "derived": root / "wiki" / "derived",
        "decision": root / "wiki" / "decisions",
        "judgment": root / "wiki" / "judgments",
    }[kind]
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
    frontmatter = render_frontmatter(
        {
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
    )
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
    destination.write_text(payload, encoding="utf-8")
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
    return {"path": relative_path(root, destination), "protocol": resolved_protocol}


__all__ = ["ask_question", "file_back"]
