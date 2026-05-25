"""Attach curated judgment and decision assets to machine memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_state import DEFAULT_PROTOCOL, load_manifest
from ..app_utils import analyze_citation_snapshots, parse_frontmatter


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
    return updated
