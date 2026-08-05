"""Material / active-corpora / manual-link state helpers.

Extracted from the legacy app_state hub. Owned by the content layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..corpus.link_state import (
    default_manual_link_state as default_manual_link_state,
)
from ..corpus.link_state import (
    load_manual_link_state as load_manual_link_state,
)
from ..corpus.link_state import (
    save_manual_link_state as save_manual_link_state,
)
from ..corpus.scoring import (
    protocol_hints_for_material,
    timestamp_is_newer,
    update_latest_timestamp,
)
from ..protocol.runtime_config import ACTIVE_CORPUS_STATUSES, ACTIVE_CORPUS_TTL
from ..protocol.scaffold import ensure_layout
from ..protocol.state import load_protocol_state
from ..state.collections import normalize_versioned_record_list_state
from ..state.constants import DEFAULT_PROTOCOL
from ..state.io import load_json_document, save_json_document
from ..state.manifest import load_manifest
from ..state.paths import material_state_path
from ..utils.hash import question_signature
from ..utils.markdown import read_text_preview
from ..utils.text import slugify
from ..utils.time import parse_iso_datetime
from .archive import (
    active_material_archive_entries,
    build_archive_candidate_state,
    load_archive_candidates_state,
    load_material_archive_state,
    save_archive_candidates_state,
    save_material_routing_state,
)
from .paths import active_corpora_state_path


def default_material_state() -> dict[str, Any]:
    return {"version": 1, "generated_at": "", "entries": []}


def load_material_state(root: Path) -> dict[str, Any]:
    document = load_json_document(material_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_material_state,
        list_key="entries",
        string_fields={"generated_at": ""},
    )


def save_material_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(material_state_path(root), document)


def default_active_corpora_state() -> dict[str, Any]:
    return {"version": 1, "corpora": []}


def load_active_corpora_state(root: Path) -> dict[str, Any]:
    document = load_json_document(active_corpora_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_active_corpora_state,
        list_key="corpora",
    )


def save_active_corpora_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(active_corpora_state_path(root), document)


def reconcile_active_corpora_state(
    root: Path,
    *,
    changed_at: str,
    nightly_cooldown: bool = False,
) -> dict[str, Any]:
    ensure_layout(root)
    state = load_active_corpora_state(root)
    changed = not active_corpora_state_path(root).exists()
    corpora: list[dict[str, Any]] = []
    for raw_corpus in state.get("corpora", []):
        corpus = dict(raw_corpus)
        status = str(corpus.get("status") or "active")
        if status not in ACTIVE_CORPUS_STATUSES:
            status = "active"
            changed = True
        expires_at = str(corpus.get("expires_at") or "")
        if expires_at and timestamp_is_newer(changed_at, expires_at):
            if status != "expired":
                status = "expired"
                changed = True
        elif nightly_cooldown and status == "active":
            status = "cooling"
            changed = True
        corpus["status"] = status
        corpora.append(corpus)
    if changed:
        save_active_corpora_state(root, {"version": 1, "corpora": corpora})
    return {"version": 1, "corpora": corpora, "changed": changed}


def refresh_material_state(
    root: Path,
    *,
    generated_at: str,
    machine_memory: dict[str, Any],
    entries: list[dict[str, Any]] | None = None,
    active_protocol: str | None = None,
) -> dict[str, Any]:
    documents = build_material_state_documents(
        root,
        generated_at=generated_at,
        machine_memory=machine_memory,
        entries=entries,
        active_protocol=active_protocol,
    )
    save_material_state(root, documents["material_state"])
    save_material_routing_state(root, documents["material_routing"])
    save_archive_candidates_state(root, documents["archive_candidates"])
    return documents["material_state"]


def build_material_state_documents(
    root: Path,
    *,
    generated_at: str,
    machine_memory: dict[str, Any],
    entries: list[dict[str, Any]] | None = None,
    active_protocol: str | None = None,
) -> dict[str, dict[str, Any]]:
    # Function-level imports: content.io imports load_manual_link_state from
    # this module, and compile.ranking imports from content.concepts which
    # imports from content.io/material — top-level imports would create
    # load-time cycles.
    from ..compile.ranking import (
        build_material_routing_entry,
        material_graph_context,
        temperature_from_routing,
    )
    from .io import scan_material_reference_state

    if not isinstance(machine_memory, dict):
        raise TypeError("machine_memory must be a dict (caller injects machine memory)")

    ensure_layout(root)
    manifest_entries = entries if entries is not None else load_manifest(root).get("entries", [])
    resolved_protocol = active_protocol or load_protocol_state(root)["active_protocol"]
    # Lazy: keep content loadable without pulling the execution package.
    from ..execution.history import load_runtime_history

    history = load_runtime_history(root)
    active_corpora = reconcile_active_corpora_state(root, changed_at=generated_at)["corpora"]
    reference_state = scan_material_reference_state(root, manifest_entries)
    graph_context = material_graph_context(machine_memory)
    previous_archive_candidates = load_archive_candidates_state(root)
    material_archive_state = load_material_archive_state(root)
    archived_entries = active_material_archive_entries(material_archive_state)
    last_query_hit_at: dict[str, str] = {}
    last_review_reference_at: dict[str, str] = {}

    for event in history:
        occurred_at = str(event.get("occurred_at") or "")
        event_type = str(event.get("event_type") or "")
        source_ids = [str(item) for item in event.get("source_ids", []) if isinstance(item, str)]
        if event_type == "query":
            for entry_id in source_ids:
                update_latest_timestamp(last_query_hit_at, entry_id, occurred_at)
        elif event_type == "review":
            for entry_id in source_ids:
                update_latest_timestamp(last_review_reference_at, entry_id, occurred_at)

    active_corpus_ids_by_entry: dict[str, list[str]] = {}
    for corpus in active_corpora:
        status = str(corpus.get("status") or "")
        if status not in {"active", "cooling"}:
            continue
        corpus_id = str(corpus.get("corpus_id") or "")
        if not corpus_id:
            continue
        source_ids = [
            str(item)
            for item in [*(corpus.get("source_ids", []) or []), *(corpus.get("bridge_evidence_ids", []) or [])]
            if isinstance(item, str)
        ]
        for entry_id in source_ids:
            active_corpus_ids_by_entry.setdefault(entry_id, [])
            if corpus_id not in active_corpus_ids_by_entry[entry_id]:
                active_corpus_ids_by_entry[entry_id].append(corpus_id)

    material_entries: list[dict[str, Any]] = []
    routing_entries: list[dict[str, Any]] = []
    for entry in manifest_entries:
        entry_id = str(entry.get("id") or "")
        stored_path = str(entry.get("stored_path") or "")
        preview = read_text_preview(root / stored_path) if stored_path and (root / stored_path).exists() else ""
        supports_judgment_ids = reference_state["supports_judgment_ids"].get(entry_id, [])
        citation_count = int(reference_state["citation_count_by_entry"].get(entry_id, 0))
        active_corpus_ids = sorted(active_corpus_ids_by_entry.get(entry_id, []))
        query_hit_at = last_query_hit_at.get(entry_id, "")
        review_hit_at = last_review_reference_at.get(entry_id, "")
        protocol_hints = protocol_hints_for_material(entry, preview)
        routing_entry = build_material_routing_entry(
            active_protocol=resolved_protocol,
            entry=entry,
            preview=preview,
            protocol_hints=protocol_hints,
            active_corpus_ids=active_corpus_ids,
            supports_judgment_ids=supports_judgment_ids,
            last_query_hit_at=query_hit_at,
            last_review_reference_at=review_hit_at,
            graph_context=graph_context,
            computed_at=generated_at,
        )
        routing_entries.append(routing_entry)
        archive_record = archived_entries.get(entry_id, {})
        temperature = temperature_from_routing(
            str(routing_entry.get("selected_as") or ""),
            supports_judgment_ids=supports_judgment_ids,
        )
        if archive_record:
            temperature = "archived"
        material_entries.append(
            {
                "entry_id": entry_id,
                "path": stored_path,
                "kind": str(entry.get("kind") or ""),
                "source_type": str(entry.get("source_type") or ""),
                "protocol_hints": protocol_hints,
                "temperature": temperature,
                "last_touched_at": str(entry.get("updated_at") or entry.get("imported_at") or ""),
                "last_query_hit_at": query_hit_at,
                "last_review_reference_at": review_hit_at,
                "citation_count": citation_count,
                "supports_judgment_ids": supports_judgment_ids,
                "active_corpus_ids": active_corpus_ids,
                "archive_override": bool(archive_record),
                "archived_at": str(archive_record.get("archived_at") or ""),
                "archive_receipt_path": str(archive_record.get("last_receipt_path") or ""),
                "archive_candidate": False,
            }
        )

    routing_document = {
        "version": 1,
        "computed_at": generated_at,
        "active_protocol": resolved_protocol,
        "entries": routing_entries,
    }
    archive_document = build_archive_candidate_state(
        material_entries=material_entries,
        routing_entries=routing_entries,
        active_judgment_ids=set(reference_state.get("active_judgment_ids", [])),
        generated_at=generated_at,
        previous_state=previous_archive_candidates,
        active_protocol=resolved_protocol,
    )
    active_archive_ids = {
        str(entry.get("entry_id") or "")
        for entry in archive_document.get("entries", [])
        if str(entry.get("status") or "") in {"suggested", "deferred", "ready"}
    }
    for material_entry in material_entries:
        material_entry["archive_candidate"] = material_entry.get("entry_id") in active_archive_ids
    material_document = {"version": 1, "generated_at": generated_at, "entries": material_entries}
    return {
        "material_state": material_document,
        "material_routing": routing_document,
        "archive_candidates": archive_document,
        "active_corpora_state": {"version": 1, "corpora": active_corpora},
    }


def upsert_active_corpus(
    root: Path,
    *,
    protocol: str,
    question: str,
    source_ids: list[str],
    concept_slugs: list[str],
    bridge_evidence_ids: list[str],
    output_ref: str,
    changed_at: str,
    corpus_id_override: str | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    state = reconcile_active_corpora_state(root, changed_at=changed_at)
    corpora = [dict(corpus) for corpus in state.get("corpora", [])]
    base_timestamp = parse_iso_datetime(changed_at) or datetime.now(timezone.utc)
    signature = question_signature(question)
    if corpus_id_override:
        corpus_id = corpus_id_override
    else:
        seed = slugify(question)[:40] or "question"
        corpus_id = f"{protocol}-{seed}-{signature.split(':', 1)[1][:8]}"
    target: dict[str, Any] | None = None
    for corpus in corpora:
        if str(corpus.get("corpus_id") or "") == corpus_id:
            target = corpus
            break
    if target is None:
        target = {"corpus_id": corpus_id, "created_at": changed_at}
        corpora.append(target)
    output_refs = [str(item) for item in target.get("output_refs", []) if isinstance(item, str)]
    if output_ref and output_ref not in output_refs:
        output_refs.append(output_ref)
    target.update(
        {
            "protocol": protocol,
            "focus_kind": "question",
            "focus_ref": question,
            "question_hash": signature,
            "source_ids": source_ids,
            "concept_slugs": concept_slugs,
            "bridge_evidence_ids": bridge_evidence_ids,
            "output_refs": output_refs[-8:],
            "status": "active",
            "last_used_at": changed_at,
            "expires_at": (base_timestamp + ACTIVE_CORPUS_TTL).replace(microsecond=0).isoformat(),
        }
    )
    save_active_corpora_state(root, {"version": 1, "corpora": corpora})
    return target


def routing_bridge_recall_ids(
    machine_query: dict[str, Any],
    routing_state: dict[str, Any],
    *,
    active_protocol: str,
    excluded_source_ids: set[str],
) -> list[str]:
    # Function-level import to avoid a load-time cycle through compile.ranking.
    from ..compile.ranking import cross_protocol_bridge_entry

    touched_component_ids = {
        str(component_id)
        for component_id in machine_query.get("touched_component_ids", [])
        if isinstance(component_id, str) and component_id
    }
    candidates: list[tuple[float, str]] = []
    for entry in routing_state.get("entries", []):
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("entry_id") or "")
        component_id = str(entry.get("component_id") or "")
        if not entry_id or entry_id in excluded_source_ids:
            continue
        if not touched_component_ids or component_id not in touched_component_ids:
            continue
        protocol_snapshots = [
            snapshot for snapshot in entry.get("protocol_snapshots", []) if isinstance(snapshot, dict)
        ]
        if not cross_protocol_bridge_entry(protocol_snapshots, active_protocol):
            continue
        non_active_scores = [
            float(snapshot.get("total_score", 0.0) or 0.0)
            for snapshot in protocol_snapshots
            if str(snapshot.get("protocol") or "") != active_protocol
        ]
        if not non_active_scores:
            continue
        best_score = max(non_active_scores)
        if best_score < 2.2:
            continue
        candidates.append((best_score, entry_id))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [entry_id for _score, entry_id in candidates[:3]]


def active_corpus_bridge_evidence_ids(
    machine_query: dict[str, Any],
    source_ids: list[str],
    *,
    routing_state: dict[str, Any] | None = None,
    active_protocol: str = DEFAULT_PROTOCOL,
    blocked_source_ids: set[str] | None = None,
) -> list[str]:
    blocked_source_ids = blocked_source_ids or set()
    bridge_concepts = set(machine_query.get("bridge_concept_slugs", []))
    source_set = set(source_ids) | {
        str(source_id)
        for source_id in machine_query.get("ranked_source_ids", [])
        if isinstance(source_id, str) and source_id and source_id not in blocked_source_ids
    }
    for node in machine_query.get("query_subgraph", {}).get("sources", []):
        if isinstance(node, dict):
            node_id = str(node.get("id") or "")
            if node_id and node_id not in blocked_source_ids:
                source_set.add(node_id)
    bridge_ids: list[str] = []
    seen: set[str] = set()
    if bridge_concepts:
        for edge in machine_query.get("query_subgraph", {}).get("edges", []):
            if not isinstance(edge, dict):
                continue
            if edge.get("type") != "HAS_CONCEPT":
                continue
            left = str(edge.get("left") or "")
            right = str(edge.get("right") or "")
            if left in source_set and left not in blocked_source_ids and right in bridge_concepts and left not in seen:
                seen.add(left)
                bridge_ids.append(left)
    if routing_state:
        excluded = set(source_set) | set(bridge_ids) | set(blocked_source_ids)
        for entry_id in routing_bridge_recall_ids(
            machine_query,
            routing_state,
            active_protocol=active_protocol,
            excluded_source_ids=excluded,
        ):
            if entry_id not in seen and entry_id not in blocked_source_ids:
                seen.add(entry_id)
                bridge_ids.append(entry_id)
    return bridge_ids
