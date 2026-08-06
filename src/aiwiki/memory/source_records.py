"""Machine-memory source runtime record construction."""

from __future__ import annotations

from typing import Any

from ..corpus.parse import routing_snapshot_for_protocol
from ..corpus.scoring import recency_score_for_timestamp


def machine_memory_source_runtime_record(
    source_id: str,
    *,
    base_score: float,
    source_nodes: dict[str, dict[str, Any]],
    material_by_entry: dict[str, dict[str, Any]],
    routing_by_entry: dict[str, dict[str, Any]],
    archive_candidates_by_entry: dict[str, dict[str, Any]],
    protocol: str,
    time_focus: str,
) -> dict[str, Any]:
    material_entry = material_by_entry.get(source_id, {})
    routing_entry = routing_by_entry.get(source_id, {})
    routing_snapshot = routing_snapshot_for_protocol(routing_entry, protocol)
    archive_candidate = archive_candidates_by_entry.get(source_id, {})
    temperature = str(material_entry.get("temperature") or "")

    protocol_bonus = 0.0
    top_protocols = [
        str(item.get("protocol") or "")
        for item in routing_entry.get("top_protocols", [])
        if isinstance(item, dict) and str(item.get("protocol") or "")
    ]
    protocol_is_top = top_protocols[:1] == [protocol]
    protocol_in_top2 = protocol in top_protocols[:2]
    selected_as = str(routing_snapshot.get("selected_as") or "")
    selected_bonus = 0.0
    if selected_as == "hot-evidence":
        selected_bonus = 0.9
    elif selected_as == "warm-evidence":
        selected_bonus = 0.6
    elif selected_as == "cold-evidence":
        selected_bonus = 0.3
    total_score = float(routing_snapshot.get("total_score", 0.0) or 0.0)
    if protocol_is_top:
        protocol_bonus += 2.5 + selected_bonus + min(1.0, total_score * 0.25)
    elif protocol_in_top2:
        protocol_bonus += 1.2 + min(0.25, selected_bonus * 0.4) + min(0.4, total_score * 0.1)

    activity_score = max(
        recency_score_for_timestamp(str(material_entry.get("last_touched_at") or "")),
        recency_score_for_timestamp(str(material_entry.get("last_query_hit_at") or "")),
        recency_score_for_timestamp(str(material_entry.get("last_review_reference_at") or "")),
    )
    time_bonus = 0.0
    if time_focus == "recent":
        time_bonus += activity_score * 4.0
        if temperature == "hot":
            time_bonus += 0.4
        elif temperature == "warm":
            time_bonus += 0.2
        elif temperature == "cold":
            time_bonus -= 0.35
        elif temperature == "archived":
            time_bonus -= 1.0
    elif time_focus == "historical":
        time_bonus += (1.0 - activity_score) * 4.0
        if temperature == "cold":
            time_bonus += 0.8
        elif temperature == "archived":
            time_bonus += 1.4
        elif temperature == "hot":
            time_bonus -= 0.25
        if archive_candidate:
            time_bonus += 0.6

    protocol_shard = protocol_is_top or (protocol_in_top2 and selected_as in {"hot-evidence", "warm-evidence"})
    time_shard = bool(time_focus) and time_bonus > 1.0
    archive_status = "archived" if temperature == "archived" else str(archive_candidate.get("status") or "")
    archive_hint = bool(
        temperature == "archived"
        or (time_focus == "historical" and (temperature == "cold" or bool(archive_candidate)))
        or (archive_candidate and str(archive_candidate.get("recommended_temperature") or "") == "archived")
    )
    archive_hint_score = base_score + protocol_bonus + max(0.0, time_bonus)
    if temperature == "archived":
        archive_hint_score += 1.0
    elif archive_candidate:
        archive_hint_score += 0.6
    elif temperature == "cold":
        archive_hint_score += 0.3

    return {
        "entry_id": source_id,
        "title": str(source_nodes.get(source_id, {}).get("title") or source_id),
        "path": str(source_nodes.get(source_id, {}).get("source_page") or f"wiki/sources/{source_id}.md"),
        "base_score": float(base_score),
        "protocol_bonus": round(protocol_bonus, 3),
        "time_bonus": round(time_bonus, 3),
        "combined_score": round(float(base_score) + protocol_bonus + time_bonus, 3),
        "protocol_shard": protocol_shard,
        "time_shard": time_shard,
        "temperature": temperature,
        "archive_status": archive_status,
        "archive_hint": archive_hint,
        "archive_hint_score": round(archive_hint_score, 3),
        "recommended_temperature": str(archive_candidate.get("recommended_temperature") or ""),
        "reason_codes": [
            str(reason) for reason in archive_candidate.get("reason_codes", []) if isinstance(reason, str) and reason
        ],
    }
