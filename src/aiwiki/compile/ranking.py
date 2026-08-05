"""Ranking state and concept ranking helpers.

Migrated out of ``aiwiki.app_compile`` to break the reverse dependency from
``aiwiki.compile.runtime_step`` and ``aiwiki.app_queries`` back to
``aiwiki.app_compile``. These functions own the ranking build-state lifecycle
(source/concept record reuse, input signatures) plus the concept ranking used
by the ask execution surface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..content.archive import active_archived_material_ids, load_material_routing_state
from ..content.concepts import concept_source_pages, entry_concept_terms
from ..content.io import active_manual_source_concept_links, routing_snapshot_for_protocol, source_summary_or_preview
from ..content.material import load_material_state
from ..corpus.scoring import recency_score_for_timestamp
from ..lifecycle.knowledge import load_knowledge_lifecycle_state
from ..protocol.focus_scoring import concept_focus_score, entry_focus_score, protocol_focus_score
from ..protocol.library import PROTOCOL_LIBRARY
from ..state.constants import DEFAULT_PROTOCOL
from ..utils.hash import sha256_bytes
from ..utils.markdown import parse_frontmatter, read_text_preview, strip_frontmatter
from ..utils.path import relative_path
from ..utils.text import tokenize
from .build import load_ranking_build_state


def ranking_source_record_is_reusable(record: dict[str, Any]) -> bool:
    return (
        isinstance(record, dict)
        and isinstance(record.get("summary_or_preview"), str)
        and isinstance(record.get("concept_terms"), list)
    )


def ranking_concept_record_is_reusable(record: dict[str, Any]) -> bool:
    return (
        isinstance(record, dict)
        and isinstance(record.get("title"), str)
        and isinstance(record.get("path"), str)
        and isinstance(record.get("source_pages"), list)
        and isinstance(record.get("content"), str)
    )


def ranking_source_summary_or_preview(root: Path, entry: dict[str, Any]) -> str:
    source_file = root / str(entry.get("stored_path") or "")
    preview = read_text_preview(source_file, limit_lines=8) if source_file.exists() else ""
    return source_summary_or_preview(root, entry, preview)


def ranking_source_input_signature(
    entry: dict[str, Any],
    summary_or_preview: str,
    manual_slugs: list[str] | None = None,
) -> str:
    payload = {
        "entry_id": str(entry.get("id") or ""),
        "title": str(entry.get("title") or ""),
        "source_type": str(entry.get("source_type") or ""),
        "kind": str(entry.get("kind") or ""),
        "stored_path": str(entry.get("stored_path") or ""),
        "sha256": str(entry.get("sha256") or ""),
        "summary_or_preview": summary_or_preview,
        "manual_slugs": sorted(str(slug) for slug in (manual_slugs or []) if str(slug)),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def ranking_source_concept_terms(
    entry: dict[str, Any],
    summary_or_preview: str,
    *,
    manual_slugs: list[str] | None = None,
) -> list[str]:
    terms = entry_concept_terms(entry, summary_or_preview, max_terms=4)
    for manual_slug in sorted(str(slug) for slug in (manual_slugs or []) if str(slug)):
        manual_label = manual_slug.replace("-", " ")
        if manual_label not in terms:
            terms.append(manual_label)
    return terms


def build_ranking_source_record(
    entry: dict[str, Any],
    summary_or_preview: str,
    *,
    input_signature: str = "",
    manual_slugs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "input_signature": input_signature or ranking_source_input_signature(entry, summary_or_preview, manual_slugs),
        "summary_or_preview": summary_or_preview,
        "concept_terms": ranking_source_concept_terms(
            entry,
            summary_or_preview,
            manual_slugs=manual_slugs,
        ),
    }


def ranking_concept_input_signature(record: dict[str, Any]) -> str:
    payload = {
        "slug": str(record.get("slug") or ""),
        "title": str(record.get("title") or ""),
        "source_signature": str(record.get("source_signature") or ""),
        "render_signature": str(record.get("render_signature") or ""),
        "source_pages": concept_source_pages(record),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def build_ranking_concept_record(
    root: Path,
    path: Path,
    *,
    input_signature: str = "",
    fallback_title: str = "",
    fallback_source_pages: list[str] | None = None,
) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    source_pages = frontmatter.get("source_pages", fallback_source_pages or [])
    if not isinstance(source_pages, list):
        source_pages = fallback_source_pages or []
    return {
        "input_signature": input_signature,
        "title": str(frontmatter.get("title") or fallback_title or path.stem),
        "path": relative_path(root, path),
        "source_pages": [str(source_page) for source_page in source_pages if str(source_page)],
        "content": strip_frontmatter(content),
    }


def build_ranking_state(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    previous_state = load_ranking_build_state(root)
    previous_source_records = previous_state.get("source_records", {})
    previous_concept_records = previous_state.get("concept_records", {})
    if not isinstance(previous_source_records, dict):
        previous_source_records = {}
    if not isinstance(previous_concept_records, dict):
        previous_concept_records = {}

    source_records: dict[str, dict[str, Any]] = {}
    dirty_source_ids: list[str] = []
    clean_source_ids: list[str] = []
    manual_links = active_manual_source_concept_links(root)
    for entry in entries:
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            continue
        summary_or_preview = ranking_source_summary_or_preview(root, entry)
        manual_slugs = sorted(manual_links.get(entry_id, set()))
        input_signature = ranking_source_input_signature(entry, summary_or_preview, manual_slugs)
        previous_record = previous_source_records.get(entry_id, {})
        if (
            ranking_source_record_is_reusable(previous_record)
            and str(previous_record.get("input_signature") or "") == input_signature
        ):
            source_records[entry_id] = {
                "input_signature": input_signature,
                "summary_or_preview": str(previous_record.get("summary_or_preview") or ""),
                "concept_terms": [str(term) for term in previous_record.get("concept_terms", []) if str(term)],
            }
            clean_source_ids.append(entry_id)
        else:
            source_records[entry_id] = build_ranking_source_record(
                entry,
                summary_or_preview,
                input_signature=input_signature,
                manual_slugs=manual_slugs,
            )
            dirty_source_ids.append(entry_id)

    concept_records: dict[str, dict[str, Any]] = {}
    dirty_concept_slugs: list[str] = []
    clean_concept_slugs: list[str] = []
    for record in concepts:
        slug = str(record.get("slug") or "")
        if not slug:
            continue
        input_signature = ranking_concept_input_signature(record)
        previous_record = previous_concept_records.get(slug, {})
        if (
            ranking_concept_record_is_reusable(previous_record)
            and str(previous_record.get("input_signature") or "") == input_signature
        ):
            concept_records[slug] = {
                "input_signature": input_signature,
                "title": str(previous_record.get("title") or slug),
                "path": str(previous_record.get("path") or f"wiki/concepts/{slug}.md"),
                "source_pages": [str(path) for path in previous_record.get("source_pages", []) if str(path)],
                "content": str(previous_record.get("content") or ""),
            }
            clean_concept_slugs.append(slug)
        else:
            concept_records[slug] = build_ranking_concept_record(
                root,
                root / "wiki" / "concepts" / f"{slug}.md",
                input_signature=input_signature,
                fallback_title=str(record.get("title") or slug),
                fallback_source_pages=concept_source_pages(record),
            )
            dirty_concept_slugs.append(slug)

    removed_source_ids = sorted(set(previous_source_records) - set(source_records))
    removed_concept_slugs = sorted(set(previous_concept_records) - set(concept_records))
    return {
        "state_document": {
            "version": 1,
            "generated_at": generated_at,
            "source_records": source_records,
            "concept_records": concept_records,
        },
        "dirty_source_ids": dirty_source_ids,
        "clean_source_ids": clean_source_ids,
        "dirty_concept_slugs": dirty_concept_slugs,
        "clean_concept_slugs": clean_concept_slugs,
        "removed_source_ids": removed_source_ids,
        "removed_concept_slugs": removed_concept_slugs,
        "inputs_clean": not (dirty_source_ids or dirty_concept_slugs or removed_source_ids or removed_concept_slugs),
    }


def rank_concepts(
    root: Path,
    question: str,
    boost_concept_slugs: set[str] | None = None,
    *,
    protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    boost_concept_slugs = boost_concept_slugs or set()
    ranked: list[tuple[int, dict[str, Any]]] = []
    ranking_state = load_ranking_build_state(root)
    concept_records = ranking_state.get("concept_records", {})
    if not isinstance(concept_records, dict):
        concept_records = {}
    lifecycle = load_knowledge_lifecycle_state(root)
    retired_paths = {
        str(entry.get("path") or "")
        for entry in lifecycle.get("entries", [])
        if isinstance(entry, dict)
        and str(entry.get("kind") or "") == "concept"
        and str(entry.get("lifecycle_state") or "") == "retired"
    }
    for path in sorted((root / "wiki" / "concepts").glob("*.md")):
        if relative_path(root, path) in retired_paths:
            continue
        record = concept_records.get(path.stem, {})
        if not ranking_concept_record_is_reusable(record):
            record = build_ranking_concept_record(root, path)
        title = str(record.get("title") or path.stem)
        content = str(record.get("content") or "")
        source_pages = record.get("source_pages", [])
        if not isinstance(source_pages, list):
            source_pages = []
        haystack = f"{title}\n{content}".lower()
        score = 0
        for token in question_tokens:
            score += haystack.count(token)
        score += concept_focus_score(protocol, title, content)
        if path.stem in boost_concept_slugs:
            score += 5
        if score:
            ranked.append(
                (
                    score,
                    {
                        "slug": path.stem,
                        "title": title,
                        "path": str(record.get("path") or relative_path(root, path)),
                        "source_pages": [str(source_page) for source_page in source_pages if str(source_page)],
                    },
                )
            )
    ranked.sort(key=lambda item: (-item[0], item[1]["title"].lower()))
    return [item for _score, item in ranked[:5]]


def material_protocol_score(
    active_protocol: str,
    *,
    protocol_hints: list[str],
    entry: dict[str, Any],
    preview: str,
) -> float:
    text = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("source_type") or ""),
            preview,
        ]
    )
    focus_score = protocol_focus_score(active_protocol, text)
    non_default_hints = [hint for hint in protocol_hints if hint and hint != DEFAULT_PROTOCOL]
    if active_protocol == DEFAULT_PROTOCOL:
        base = 0.4 if not non_default_hints else 0.25
    elif active_protocol in protocol_hints:
        base = 0.75
    else:
        base = 0.2
    return round(min(1.0, base + min(0.25, focus_score * 0.05)), 3)


def material_graph_context(memory: dict[str, Any]) -> dict[str, Any]:
    health = memory.get("health", {})
    bridge_concepts = set(health.get("bridge_concept_slugs", []))
    concept_count_by_entry: dict[str, int] = {}
    bridge_source_ids: set[str] = set()
    source_component_ids = {
        str(source_id): str(component_id)
        for source_id, component_id in health.get("source_component_ids", {}).items()
        if isinstance(source_id, str) and isinstance(component_id, str)
    }
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        source_id = str(edge.get("source_id") or "")
        concept_slug = str(edge.get("concept_slug") or "")
        if not source_id or not concept_slug:
            continue
        concept_count_by_entry[source_id] = concept_count_by_entry.get(source_id, 0) + 1
        if concept_slug in bridge_concepts:
            bridge_source_ids.add(source_id)
    action_pressure_by_entry: dict[str, float] = {}
    for action in health.get("actions", []):
        if not isinstance(action, dict):
            continue
        weight = 0.2
        if str(action.get("priority") or "") == "high":
            weight += 0.15
        if str(action.get("status") or "") in {"accepted", "proposed"}:
            weight += 0.1
        for source_id in action.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id:
                action_pressure_by_entry[source_id] = action_pressure_by_entry.get(source_id, 0.0) + weight
    for action in health.get("overdue_actions", []):
        if not isinstance(action, dict):
            continue
        for source_id in action.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id:
                action_pressure_by_entry[source_id] = action_pressure_by_entry.get(source_id, 0.0) + 0.2
    for action in health.get("escalated_actions", []):
        if not isinstance(action, dict):
            continue
        for source_id in action.get("source_ids", []) or []:
            if isinstance(source_id, str) and source_id:
                action_pressure_by_entry[source_id] = action_pressure_by_entry.get(source_id, 0.0) + 0.25
    return {
        "concept_count_by_entry": concept_count_by_entry,
        "bridge_source_ids": bridge_source_ids,
        "action_pressure_by_entry": action_pressure_by_entry,
        "sources_without_concepts": set(memory.get("drift", {}).get("sources_without_concepts", [])),
        "source_component_ids": source_component_ids,
    }


def material_routing_selected_as(total_score: float, *, active_corpus_ids: list[str]) -> str:
    if active_corpus_ids or total_score >= 3.2:
        return "hot-evidence"
    if total_score >= 2.2:
        return "warm-evidence"
    if total_score >= 1.2:
        return "cold-evidence"
    return "archive-candidate"


def temperature_from_routing(selected_as: str, *, supports_judgment_ids: list[str]) -> str:
    if selected_as == "hot-evidence":
        return "hot"
    if selected_as == "warm-evidence":
        return "warm"
    if supports_judgment_ids:
        return "warm"
    return "cold"


def build_material_routing_snapshot(
    *,
    active_protocol: str,
    entry: dict[str, Any],
    preview: str,
    protocol_hints: list[str],
    active_corpus_ids: list[str],
    supports_judgment_ids: list[str],
    last_query_hit_at: str,
    last_review_reference_at: str,
    graph_context: dict[str, Any],
    computed_at: str,
) -> dict[str, Any]:
    entry_id = str(entry.get("id") or "")
    concept_count = int(graph_context.get("concept_count_by_entry", {}).get(entry_id, 0))
    is_bridge = entry_id in graph_context.get("bridge_source_ids", set())
    graph_score = 0.0
    graph_score += min(0.55, concept_count * 0.18)
    if active_corpus_ids:
        graph_score += 0.25
    if is_bridge:
        graph_score += 0.2
    graph_score = round(min(1.0, graph_score), 3)

    judgment_score = round(min(1.0, len(supports_judgment_ids) * 0.35), 3)
    recency_score = round(
        min(
            1.0,
            max(
                recency_score_for_timestamp(str(entry.get("updated_at") or entry.get("imported_at") or "")),
                recency_score_for_timestamp(last_query_hit_at),
                recency_score_for_timestamp(last_review_reference_at),
            ),
        ),
        3,
    )

    drift_score = 0.0
    if entry_id in graph_context.get("sources_without_concepts", set()):
        drift_score += 0.4
    drift_score += float(graph_context.get("action_pressure_by_entry", {}).get(entry_id, 0.0))
    drift_score = round(min(1.0, drift_score), 3)

    protocol_score = material_protocol_score(
        active_protocol,
        protocol_hints=protocol_hints,
        entry=entry,
        preview=preview,
    )
    total_score = round(protocol_score + graph_score + judgment_score + recency_score + drift_score, 3)
    selected_as = material_routing_selected_as(total_score, active_corpus_ids=active_corpus_ids)
    return {
        "entry_id": entry_id,
        "protocol": active_protocol,
        "component_id": str(graph_context.get("source_component_ids", {}).get(entry_id, "") or ""),
        "scores": {
            "protocol_score": protocol_score,
            "graph_score": graph_score,
            "judgment_score": judgment_score,
            "recency_score": recency_score,
            "drift_score": drift_score,
        },
        "total_score": total_score,
        "selected_as": selected_as,
        "is_bridge": is_bridge,
        "computed_at": computed_at,
    }


def material_top_protocols(protocol_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        [snapshot for snapshot in protocol_snapshots if isinstance(snapshot, dict)],
        key=lambda item: (-float(item.get("total_score", 0.0) or 0.0), str(item.get("protocol") or "")),
    )
    return [
        {
            "protocol": str(snapshot.get("protocol") or ""),
            "total_score": float(snapshot.get("total_score", 0.0) or 0.0),
            "selected_as": str(snapshot.get("selected_as") or ""),
        }
        for snapshot in ranked[:3]
    ]


def cross_protocol_bridge_entry(protocol_snapshots: list[dict[str, Any]], active_protocol: str) -> bool:
    for snapshot in protocol_snapshots:
        if not isinstance(snapshot, dict):
            continue
        if str(snapshot.get("protocol") or "") == active_protocol:
            continue
        if bool(snapshot.get("is_bridge")) and float(snapshot.get("total_score", 0.0) or 0.0) >= 2.2:
            return True
    return False


def build_material_routing_entry(
    *,
    active_protocol: str,
    entry: dict[str, Any],
    preview: str,
    protocol_hints: list[str],
    active_corpus_ids: list[str],
    supports_judgment_ids: list[str],
    last_query_hit_at: str,
    last_review_reference_at: str,
    graph_context: dict[str, Any],
    computed_at: str,
) -> dict[str, Any]:
    protocol_snapshots = [
        build_material_routing_snapshot(
            active_protocol=protocol,
            entry=entry,
            preview=preview,
            protocol_hints=protocol_hints,
            active_corpus_ids=active_corpus_ids,
            supports_judgment_ids=supports_judgment_ids,
            last_query_hit_at=last_query_hit_at,
            last_review_reference_at=last_review_reference_at,
            graph_context=graph_context,
            computed_at=computed_at,
        )
        for protocol in sorted(PROTOCOL_LIBRARY)
    ]
    active_snapshot = next(
        (snapshot for snapshot in protocol_snapshots if str(snapshot.get("protocol") or "") == active_protocol),
        protocol_snapshots[0],
    )
    return {
        **active_snapshot,
        "protocol_snapshots": protocol_snapshots,
        "top_protocols": material_top_protocols(protocol_snapshots),
        "cross_protocol_bridge": cross_protocol_bridge_entry(protocol_snapshots, active_protocol),
    }


def rank_sources(
    root: Path,
    entries: list[dict[str, Any]],
    question: str,
    boost_source_ids: set[str] | None = None,
    *,
    protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    scored: list[tuple[float, int, float, dict[str, Any]]] = []
    boost_source_ids = boost_source_ids or set()
    ranking_state = load_ranking_build_state(root)
    source_records = ranking_state.get("source_records", {})
    if not isinstance(source_records, dict):
        source_records = {}
    material_state = load_material_state(root)
    material_by_id = {
        str(item.get("entry_id") or ""): item
        for item in material_state.get("entries", [])
        if isinstance(item, dict) and item.get("entry_id")
    }
    routing_state = load_material_routing_state(root)
    routing_by_id = {
        str(item.get("entry_id") or ""): item
        for item in routing_state.get("entries", [])
        if isinstance(item, dict) and item.get("entry_id")
    }
    archived_source_ids = active_archived_material_ids(root)
    manual_source_links = active_manual_source_concept_links(root)
    for entry in entries:
        entry_id = str(entry.get("id") or "")
        material_entry = material_by_id.get(entry_id, {})
        if entry_id in archived_source_ids or str(material_entry.get("temperature") or "") == "archived":
            continue
        ranking_record = source_records.get(entry_id, {})
        if ranking_source_record_is_reusable(ranking_record):
            summary_or_preview = str(ranking_record.get("summary_or_preview") or "")
            concept_terms = [str(term) for term in ranking_record.get("concept_terms", []) if str(term)]
        else:
            summary_or_preview = ranking_source_summary_or_preview(root, entry)
            ranking_record = build_ranking_source_record(
                entry,
                summary_or_preview,
                manual_slugs=sorted(manual_source_links.get(entry_id, set())),
            )
            concept_terms = [str(term) for term in ranking_record.get("concept_terms", []) if str(term)]
        haystack = " ".join([entry["title"], summary_or_preview]).lower()
        score = 0
        for token in question_tokens:
            score += haystack.count(token)
        for concept in concept_terms:
            for token in question_tokens:
                score += concept.lower().count(token)
        score += entry_focus_score(protocol, entry, summary_or_preview)
        if entry_id in boost_source_ids:
            score += 5
        if not score:
            continue

        routing_entry = routing_by_id.get(entry_id, {})
        routing_snapshot = routing_snapshot_for_protocol(routing_entry, protocol)
        runtime_score = 0.0
        if material_entry.get("active_corpus_ids"):
            runtime_score += 3.0
        temperature = str(material_entry.get("temperature") or "")
        if temperature == "hot":
            runtime_score += 2.0
        elif temperature == "warm":
            runtime_score += 1.0
        if material_entry.get("supports_judgment_ids"):
            runtime_score += 0.5

        selected_as = str(routing_snapshot.get("selected_as") or "")
        if selected_as == "hot-evidence":
            runtime_score += 2.5
        elif selected_as == "warm-evidence":
            runtime_score += 1.5
        elif selected_as == "cold-evidence":
            runtime_score += 0.5
        elif selected_as == "archive-candidate":
            runtime_score -= 0.5
        runtime_score += min(1.5, float(routing_snapshot.get("total_score", 0.0) or 0.0) * 0.35)

        top_protocols = [
            str(item.get("protocol") or "")
            for item in routing_entry.get("top_protocols", [])
            if isinstance(item, dict) and str(item.get("protocol") or "")
        ]
        if top_protocols[:1] == [protocol]:
            runtime_score += 1.0
        elif protocol in top_protocols[:2]:
            runtime_score += 0.5

        combined_score = float(score * 5) + runtime_score
        scored.append((combined_score, score, runtime_score, entry))
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]["title"].lower()))
    return [entry for _combined, _base, _runtime, entry in scored[:5]]


def compound_rank_boosts(
    memory: dict[str, Any],
    machine_query: dict[str, Any],
) -> tuple[set[str], set[str]]:
    """Derive source/concept boost ids from ranked confirmed judgments and settled elixirs."""

    ranked_judgments = {
        str(page_id).strip() for page_id in machine_query.get("ranked_judgment_ids", []) or [] if str(page_id).strip()
    }
    ranked_elixirs = {
        str(elixir_id).strip()
        for elixir_id in machine_query.get("ranked_elixir_ids", []) or []
        if str(elixir_id).strip()
    }
    boost_sources: set[str] = set()
    edges = memory.get("edges", {})
    source_to_concepts: dict[str, set[str]] = {}
    for edge in edges.get("source_to_concept", []):
        if not isinstance(edge, dict):
            continue
        source_id = str(edge.get("source_id") or "").strip()
        concept_slug = str(edge.get("concept_slug") or "").strip()
        if source_id and concept_slug:
            source_to_concepts.setdefault(source_id, set()).add(concept_slug)

    for node in memory.get("judgment_nodes", []):
        if not isinstance(node, dict):
            continue
        page_id = str(node.get("page_id") or "").strip()
        if page_id not in ranked_judgments:
            continue
        for source_id in node.get("source_ids", []) or []:
            normalized = str(source_id or "").strip()
            if normalized:
                boost_sources.add(normalized)

    for edge in edges.get("source_to_judgment", []):
        if not isinstance(edge, dict):
            continue
        page_id = str(edge.get("page_id") or "").strip()
        source_id = str(edge.get("source_id") or "").strip()
        if page_id in ranked_judgments and source_id:
            boost_sources.add(source_id)

    for edge in edges.get("elixir_derived_from", []):
        if not isinstance(edge, dict):
            continue
        elixir_id = str(edge.get("elixir_id") or "").strip()
        if elixir_id not in ranked_elixirs:
            continue
        if str(edge.get("from_kind") or "").strip() == "source":
            from_id = str(edge.get("from_id") or "").strip()
            if from_id:
                boost_sources.add(from_id)

    boost_concepts: set[str] = set()
    for source_id in boost_sources:
        boost_concepts.update(source_to_concepts.get(source_id, set()))
    return boost_sources, boost_concepts


def ranked_compound_page_paths(
    machine_query: dict[str, Any],
    *,
    judgment_limit: int = 3,
    elixir_limit: int = 2,
) -> list[str]:
    subgraph = machine_query.get("query_subgraph", {}) or {}
    refs: list[str] = []
    for node in subgraph.get("judgments", []) or []:
        if not isinstance(node, dict):
            continue
        path = str(node.get("path") or "").strip()
        if path and path not in refs:
            refs.append(path)
        if len([item for item in refs if item.startswith("wiki/judgments/")]) >= judgment_limit:
            break
    for node in subgraph.get("elixirs", []) or []:
        if not isinstance(node, dict):
            continue
        path = str(node.get("path") or "").strip()
        if path and path not in refs:
            refs.append(path)
        if len([item for item in refs if item.startswith("wiki/elixirs/")]) >= elixir_limit:
            break
    return refs


__all__ = [
    "build_material_routing_entry",
    "build_material_routing_snapshot",
    "build_ranking_concept_record",
    "build_ranking_source_record",
    "build_ranking_state",
    "compound_rank_boosts",
    "cross_protocol_bridge_entry",
    "material_graph_context",
    "material_protocol_score",
    "material_routing_selected_as",
    "material_top_protocols",
    "rank_concepts",
    "rank_sources",
    "ranked_compound_page_paths",
    "ranking_concept_input_signature",
    "ranking_concept_record_is_reusable",
    "ranking_source_concept_terms",
    "ranking_source_input_signature",
    "ranking_source_record_is_reusable",
    "ranking_source_summary_or_preview",
    "temperature_from_routing",
]
