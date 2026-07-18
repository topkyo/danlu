"""Attach curated judgment and decision assets to machine memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_state import DEFAULT_PROTOCOL, load_manifest
from ..app_utils import analyze_citation_snapshots, parse_frontmatter, strip_frontmatter, tokenize
from ..content.io import preserved_section
from ..execution.alchemy import ELIXIR_DIR


def _empty_term_bucket() -> dict[str, set[str]]:
    return {
        "source_ids": set(),
        "concept_slugs": set(),
        "judgment_page_ids": set(),
        "elixir_ids": set(),
    }


def _normalize_term_index(term_index: dict[str, Any]) -> dict[str, dict[str, set[str]]]:
    normalized: dict[str, dict[str, set[str]]] = {}
    for term, payload in term_index.items():
        if not isinstance(payload, dict):
            continue
        bucket = _empty_term_bucket()
        for key in bucket:
            bucket[key] = {
                str(item)
                for item in payload.get(key, [])
                if isinstance(item, str) and str(item).strip()
            }
        normalized[str(term)] = bucket
    return normalized


def _serialize_term_index(term_index: dict[str, dict[str, set[str]]]) -> dict[str, dict[str, list[str]]]:
    return {
        term: {
            "source_ids": sorted(payload["source_ids"]),
            "concept_slugs": sorted(payload["concept_slugs"]),
            "judgment_page_ids": sorted(payload["judgment_page_ids"]),
            "elixir_ids": sorted(payload["elixir_ids"]),
        }
        for term, payload in sorted(term_index.items())
    }


def _index_compounding_text(
    term_index: dict[str, dict[str, set[str]]],
    text: str,
    *,
    judgment_page_id: str | None = None,
    elixir_id: str | None = None,
) -> None:
    for token in tokenize(text):
        bucket = term_index.setdefault(token, _empty_term_bucket())
        if judgment_page_id:
            bucket["judgment_page_ids"].add(judgment_page_id)
        if elixir_id:
            bucket["elixir_ids"].add(elixir_id)


def _is_confirmed_judgment(node: dict[str, Any]) -> bool:
    return str(node.get("kind") or "") == "judgment" and str(node.get("status") or "") == "confirmed"


def _compounding_index_text(root: Path, page_path: str, title: str) -> str:
    target = root / page_path
    if not target.exists():
        return title
    content = target.read_text(encoding="utf-8", errors="replace")
    body = strip_frontmatter(content)
    summary = preserved_section(body, "Summary", "").strip()
    if not summary:
        summary = body[:1200]
    return f"{title}\n{summary}"


def _resolve_elixir_derived_ref(
    reference: str,
    *,
    source_ids: set[str],
    judgment_page_ids: set[str],
    elixir_ids: set[str],
) -> tuple[str, str] | None:
    candidate = reference.strip().replace("\\", "/")
    if not candidate:
        return None
    if candidate.startswith("wiki/sources/") and candidate.endswith(".md"):
        source_id = Path(candidate).stem
        if source_id in source_ids:
            return ("source", source_id)
    if candidate.startswith("wiki/judgments/") and candidate.endswith(".md"):
        page_id = Path(candidate).stem
        if page_id in judgment_page_ids:
            return ("judgment", page_id)
    if candidate.startswith(f"{ELIXIR_DIR}/") and candidate.endswith(".md"):
        elixir_id = Path(candidate).stem
        if elixir_id in elixir_ids:
            return ("elixir", elixir_id)
    stem = Path(candidate).stem
    if stem in source_ids:
        return ("source", stem)
    if stem in judgment_page_ids:
        return ("judgment", stem)
    if stem in elixir_ids:
        return ("elixir", stem)
    return None


def _attach_settled_elixirs_to_memory(
    root: Path,
    memory: dict[str, Any],
    term_index: dict[str, dict[str, set[str]]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    confirmed_judgment_ids = {
        str(node.get("page_id") or "")
        for node in memory.get("judgment_nodes", [])
        if _is_confirmed_judgment(node) and node.get("page_id")
    }
    source_ids = {str(node.get("id") or "") for node in memory.get("source_nodes", []) if node.get("id")}
    elixir_nodes: list[dict[str, Any]] = []
    elixir_derived_from: list[dict[str, str]] = []
    elixir_dir = root / ELIXIR_DIR
    if not elixir_dir.exists():
        return elixir_nodes, elixir_derived_from

    for page in sorted(elixir_dir.glob("*.md")):
        try:
            content = page.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        frontmatter = parse_frontmatter(content)
        state = str(frontmatter.get("elixir_state") or "settled").strip() or "settled"
        if state != "settled":
            continue
        elixir_id = str(frontmatter.get("id") or page.stem).strip() or page.stem
        title = str(frontmatter.get("title") or elixir_id)
        page_path = f"{ELIXIR_DIR}/{page.name}"
        derived_from = _frontmatter_string_list(frontmatter, "derived_from")
        elixir_nodes.append(
            {
                "elixir_id": elixir_id,
                "title": title,
                "path": page_path,
                "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                "elixir_state": state,
                "derived_from": derived_from,
            }
        )
        _index_compounding_text(
            term_index,
            _compounding_index_text(root, page_path, title),
            elixir_id=elixir_id,
        )

    elixir_ids = {str(node.get("elixir_id") or "") for node in elixir_nodes if node.get("elixir_id")}
    seen_edges: set[tuple[str, str, str]] = set()
    for node in elixir_nodes:
        elixir_id = str(node.get("elixir_id") or "")
        if not elixir_id:
            continue
        for reference in list(node.get("derived_from") or []):
            resolved = _resolve_elixir_derived_ref(
                str(reference),
                source_ids=source_ids,
                judgment_page_ids=confirmed_judgment_ids,
                elixir_ids=elixir_ids,
            )
            if not resolved:
                continue
            from_kind, from_id = resolved
            edge_key = (elixir_id, from_kind, from_id)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            elixir_derived_from.append(
                {
                    "elixir_id": elixir_id,
                    "from_kind": from_kind,
                    "from_id": from_id,
                }
            )
    return elixir_nodes, elixir_derived_from


def _index_compounding_assets_in_memory(root: Path, memory: dict[str, Any]) -> dict[str, Any]:
    term_index = _normalize_term_index(memory.get("term_index", {}))
    for node in memory.get("judgment_nodes", []):
        if not isinstance(node, dict) or not _is_confirmed_judgment(node):
            continue
        page_id = str(node.get("page_id") or "")
        page_path = str(node.get("path") or "")
        title = str(node.get("title") or page_id)
        if not page_id or not page_path:
            continue
        _index_compounding_text(
            term_index,
            _compounding_index_text(root, page_path, title),
            judgment_page_id=page_id,
        )
    elixir_nodes, elixir_derived_from = _attach_settled_elixirs_to_memory(root, memory, term_index)
    updated = dict(memory)
    updated["term_index"] = _serialize_term_index(term_index)
    updated["elixir_nodes"] = sorted(elixir_nodes, key=lambda item: item["elixir_id"])
    edges = dict(memory.get("edges", {}))
    edges["elixir_derived_from"] = sorted(
        elixir_derived_from,
        key=lambda item: (item["elixir_id"], item["from_kind"], item["from_id"]),
    )
    updated["edges"] = edges
    return updated


def _frontmatter_string_list(frontmatter: dict[str, Any], key: str) -> list[str]:
    value = frontmatter.get(key, [])
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]


def _resolve_curated_relation_id(
    reference: str,
    *,
    current_path: str,
    page_ids: set[str],
    path_to_page_id: dict[str, str],
) -> str:
    candidate = reference.strip()
    if not candidate:
        return ""
    if candidate in page_ids:
        return candidate
    if candidate in path_to_page_id:
        return path_to_page_id[candidate]
    if candidate.endswith(".md") and not candidate.startswith("wiki/"):
        relative_candidate = (Path(current_path).parent / candidate).as_posix()
        if relative_candidate in path_to_page_id:
            return path_to_page_id[relative_candidate]
    stem = Path(candidate).stem
    if stem in path_to_page_id:
        return path_to_page_id[stem]
    return ""


def attach_judgment_assets_to_machine_memory(
    root: Path,
    memory: dict[str, Any],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
) -> dict[str, Any]:
    manifest_entries = load_manifest(root).get("entries", [])
    path_to_entry_id: dict[str, str] = {}
    for entry in manifest_entries:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            continue
        path_to_entry_id[f"wiki/sources/{entry_id}.md"] = entry_id
        stored_path = str(entry.get("stored_path") or "")
        if stored_path:
            path_to_entry_id[stored_path] = entry_id

    page_records: list[dict[str, Any]] = []
    path_to_page_id: dict[str, str] = {}
    page_kind_by_id: dict[str, str] = {}
    for page in decisions + judgments:
        page_path = str(page.get("path") or "")
        if not page_path:
            continue
        target = root / page_path
        content = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        frontmatter = parse_frontmatter(content)
        citations = _frontmatter_string_list(frontmatter, "citations")
        citation_snapshot_state = analyze_citation_snapshots(root, citations, frontmatter)
        source_ids = sorted(
            {
                entry_id
                for entry_id in (path_to_entry_id.get(citation) for citation in citations)
                if isinstance(entry_id, str) and entry_id
            }
        )
        page_id = str(page.get("page_id") or frontmatter.get("id") or Path(page_path).stem)
        page_kind = str(page.get("kind") or frontmatter.get("kind") or "")
        record = {
            "page_id": page_id,
            "title": str(page.get("title") or frontmatter.get("title") or page_id),
            "path": page_path,
            "kind": page_kind,
            "status": str(page.get("status") or frontmatter.get("status") or ""),
            "protocol": str(page.get("protocol") or frontmatter.get("protocol") or DEFAULT_PROTOCOL),
            "confidence": str(page.get("confidence") or frontmatter.get("confidence") or ""),
            "citations": citations,
            "source_ids": source_ids,
            "counter_evidence": _frontmatter_string_list(frontmatter, "counter_evidence"),
            "invalidation_rule": str(frontmatter.get("invalidation_rule") or "").strip(),
            "next_signals": _frontmatter_string_list(frontmatter, "next_signals"),
            "reviewed_at": str(page.get("reviewed_at") or frontmatter.get("reviewed_at") or ""),
            "revisit_after": str(page.get("revisit_after") or frontmatter.get("revisit_after") or ""),
            "escalate_after": str(page.get("escalate_after") or frontmatter.get("escalate_after") or ""),
            "formed_at": str(
                page.get("formed_at") or frontmatter.get("formed_at") or frontmatter.get("last_compiled_at") or ""
            ),
            "last_reviewed": str(
                page.get("last_reviewed") or frontmatter.get("last_reviewed") or frontmatter.get("reviewed_at") or ""
            ),
            "asset_score": int(page.get("asset_score", "0") or 0),
            "citation_drift": "true" if citation_snapshot_state["has_drift"] else "false",
            "citation_drift_count": len(citation_snapshot_state["drifted"]),
            "citation_snapshot_gap_count": len(citation_snapshot_state["missing"])
            + len(citation_snapshot_state["stale"]),
            "related_judgments_raw": _frontmatter_string_list(frontmatter, "related_judgments"),
            "supports_raw": _frontmatter_string_list(frontmatter, "supports"),
            "contradicts_raw": _frontmatter_string_list(frontmatter, "contradicts"),
        }
        page_records.append(record)
        path_to_page_id[page_path] = page_id
        path_to_page_id[Path(page_path).name] = page_id
        path_to_page_id[Path(page_path).stem] = page_id
        page_kind_by_id[page_id] = page_kind

    judgment_nodes: list[dict[str, Any]] = []
    source_to_judgment: list[dict[str, str]] = []
    judgment_to_judgment: list[dict[str, str]] = []
    judgment_to_decision: list[dict[str, str]] = []
    page_ids = set(page_kind_by_id)
    seen_judgment_edges: set[tuple[str, str, str]] = set()
    seen_decision_edges: set[tuple[str, str, str]] = set()
    for record in page_records:
        page_id = str(record["page_id"])
        page_path = str(record["path"])
        related_judgments = [
            target_id
            for target_id in (
                _resolve_curated_relation_id(
                    reference,
                    current_path=page_path,
                    page_ids=page_ids,
                    path_to_page_id=path_to_page_id,
                )
                for reference in list(record.get("related_judgments_raw") or [])
            )
            if target_id and target_id != page_id
        ]
        supports = [
            target_id
            for target_id in (
                _resolve_curated_relation_id(
                    reference,
                    current_path=page_path,
                    page_ids=page_ids,
                    path_to_page_id=path_to_page_id,
                )
                for reference in list(record.get("supports_raw") or [])
            )
            if target_id and target_id != page_id
        ]
        contradicts = [
            target_id
            for target_id in (
                _resolve_curated_relation_id(
                    reference,
                    current_path=page_path,
                    page_ids=page_ids,
                    path_to_page_id=path_to_page_id,
                )
                for reference in list(record.get("contradicts_raw") or [])
            )
            if target_id and target_id != page_id
        ]
        judgment_nodes.append(
            {
                **record,
                "related_judgments": sorted(dict.fromkeys(related_judgments)),
                "supports": sorted(dict.fromkeys(supports)),
                "contradicts": sorted(dict.fromkeys(contradicts)),
            }
        )
        for source_id in list(record.get("source_ids") or []):
            source_to_judgment.append({"source_id": source_id, "page_id": page_id})
        relation_targets = (
            [("related", target_id) for target_id in related_judgments]
            + [("supports", target_id) for target_id in supports]
            + [("contradicts", target_id) for target_id in contradicts]
        )
        current_kind = str(record.get("kind") or "")
        for relation, target_id in relation_targets:
            target_kind = str(page_kind_by_id.get(target_id) or "")
            if "decision" in {current_kind, target_kind} and "judgment" in {current_kind, target_kind}:
                edge_key = (page_id, target_id, relation)
                if edge_key in seen_decision_edges:
                    continue
                seen_decision_edges.add(edge_key)
                judgment_to_decision.append(
                    {
                        "from": page_id,
                        "to": target_id,
                        "relation": relation,
                        "judgment_id": page_id if current_kind == "judgment" else target_id,
                        "decision_id": page_id if current_kind == "decision" else target_id,
                    }
                )
                continue
            edge_key = (page_id, target_id, relation)
            if edge_key in seen_judgment_edges:
                continue
            seen_judgment_edges.add(edge_key)
            judgment_to_judgment.append(
                {
                    "from": page_id,
                    "to": target_id,
                    "relation": relation,
                }
            )

    updated = dict(memory)
    updated["judgment_nodes"] = sorted(judgment_nodes, key=lambda item: (item["kind"], item["page_id"]))
    edges = dict(memory.get("edges", {}))
    edges["source_to_judgment"] = sorted(source_to_judgment, key=lambda item: (item["source_id"], item["page_id"]))
    edges["judgment_to_judgment"] = sorted(
        judgment_to_judgment,
        key=lambda item: (item["relation"], item["from"], item["to"]),
    )
    edges["judgment_to_decision"] = sorted(
        judgment_to_decision,
        key=lambda item: (item["relation"], item["from"], item["to"]),
    )
    updated["edges"] = edges
    return _index_compounding_assets_in_memory(root, updated)
