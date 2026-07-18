"""Material routing / archive-candidates / material-archive state helpers.

Extracted from the legacy app_state hub. Owned by the content layer (routing + archive
state lives here; the archive *execution* path remains in execution.archive).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..memory.scoring import recency_score_for_timestamp, timestamp_is_newer
from ..protocol.runtime_config import ARCHIVE_CANDIDATE_STATUSES, ARCHIVE_QUERY_STALE_AFTER
from ..state.collections import active_records_by_key, normalize_versioned_record_list_state
from ..state.constants import DEFAULT_PROTOCOL
from ..state.io import load_json_document, save_json_document
from ..utils.time import parse_iso_datetime
from .paths import (
    archive_candidates_state_path,
    material_archive_state_path,
    material_routing_state_path,
)


def default_material_routing_state() -> dict[str, Any]:
    return {"version": 1, "computed_at": "", "active_protocol": DEFAULT_PROTOCOL, "entries": []}


def load_material_routing_state(root: Path) -> dict[str, Any]:
    document = load_json_document(material_routing_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_material_routing_state,
        list_key="entries",
        string_fields={"computed_at": "", "active_protocol": DEFAULT_PROTOCOL},
    )


def save_material_routing_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(material_routing_state_path(root), document)


def default_archive_candidates_state() -> dict[str, Any]:
    return {"version": 1, "generated_at": "", "entries": []}


def load_archive_candidates_state(root: Path) -> dict[str, Any]:
    document = load_json_document(archive_candidates_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_archive_candidates_state,
        list_key="entries",
        string_fields={"generated_at": ""},
    )


def save_archive_candidates_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(archive_candidates_state_path(root), document)


def default_material_archive_state() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def load_material_archive_state(root: Path) -> dict[str, Any]:
    document = load_json_document(material_archive_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_material_archive_state,
        list_key="entries",
    )


def save_material_archive_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(material_archive_state_path(root), document)


def active_material_archive_entries(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return active_records_by_key(document, list_key="entries", key="entry_id")


def active_archived_material_ids(root: Path) -> set[str]:
    return set(active_material_archive_entries(load_material_archive_state(root)))


def archive_candidate_reactivation_signals(
    material_entry: dict[str, Any],
    routing_snapshot: dict[str, Any],
    previous_candidate: dict[str, Any],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[str]:
    signals: list[str] = []
    previous_flagged_at = str(previous_candidate.get("last_flagged_at") or "")
    if material_entry.get("active_corpus_ids"):
        signals.append("active-corpus")
    if str(material_entry.get("last_query_hit_at") or "") and timestamp_is_newer(
        str(material_entry.get("last_query_hit_at") or ""),
        previous_flagged_at,
    ):
        signals.append("query-hit")
    if str(material_entry.get("last_review_reference_at") or "") and timestamp_is_newer(
        str(material_entry.get("last_review_reference_at") or ""),
        previous_flagged_at,
    ):
        signals.append("review-reference")
    if bool(routing_snapshot.get("is_bridge")):
        signals.append("bridge-evidence")
    if float(routing_snapshot.get("total_score", 0.0) or 0.0) >= 2.2:
        signals.append("routing-score-recovered")
    if bool(routing_snapshot.get("cross_protocol_bridge")):
        signals.append("cross-protocol-bridge")
    top_protocols = [
        str(item.get("protocol") or "")
        for item in routing_snapshot.get("top_protocols", [])
        if isinstance(item, dict) and str(item.get("protocol") or "")
    ]
    if any(protocol != active_protocol for protocol in top_protocols[:2]):
        signals.append("cross-protocol-top-rank")
    return signals


def build_archive_candidate_state(
    *,
    material_entries: list[dict[str, Any]],
    routing_entries: list[dict[str, Any]],
    active_judgment_ids: set[str],
    generated_at: str,
    previous_state: dict[str, Any],
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    previous_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in previous_state.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    routing_by_entry = {
        str(entry.get("entry_id") or ""): entry
        for entry in routing_entries
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    entries: list[dict[str, Any]] = []
    for material_entry in material_entries:
        entry_id = str(material_entry.get("entry_id") or "")
        if not entry_id:
            continue
        routing_snapshot = routing_by_entry.get(entry_id, {})
        previous_candidate = previous_by_entry.get(entry_id, {})
        blocked_by_judgment_ids = sorted(set(material_entry.get("supports_judgment_ids", [])) & active_judgment_ids)
        last_query_hit_at = parse_iso_datetime(str(material_entry.get("last_query_hit_at") or ""))
        query_stale = (
            last_query_hit_at is None or (datetime.now(timezone.utc) - last_query_hit_at) > ARCHIVE_QUERY_STALE_AFTER
        )
        touch_stale = recency_score_for_timestamp(str(material_entry.get("last_touched_at") or "")) <= 0.4
        total_score = float(routing_snapshot.get("total_score", 0.0) or 0.0)
        is_bridge = bool(routing_snapshot.get("is_bridge"))
        cross_protocol_bridge = bool(routing_snapshot.get("cross_protocol_bridge"))
        no_active_corpus = not material_entry.get("active_corpus_ids")
        candidate = (
            no_active_corpus
            and query_stale
            and touch_stale
            and not is_bridge
            and not cross_protocol_bridge
            and str(material_entry.get("temperature") or "") in {"warm", "cold"}
            and str(routing_snapshot.get("selected_as") or "") in {"cold-evidence", "archive-candidate"}
        )
        if candidate:
            reason_codes: list[str] = []
            if no_active_corpus:
                reason_codes.append("no-active-corpus")
            if query_stale:
                reason_codes.append("stale-no-query-hit")
            if touch_stale:
                reason_codes.append("stale-no-touch")
            if total_score < 2.0:
                reason_codes.append("low-routing-score")
            if str(material_entry.get("temperature") or "") == "cold":
                reason_codes.append("already-cold")
            recommended_temperature = (
                "archived" if str(material_entry.get("temperature") or "") == "cold" and total_score < 1.2 else "cold"
            )
            status = "suggested"
            if blocked_by_judgment_ids:
                status = "deferred"
            # Deferred means the candidate already crossed the archive bar once.
            # When the blocking judgments clear, it should resume at ready.
            elif previous_candidate and str(previous_candidate.get("status") or "") in {
                "suggested",
                "ready",
                "deferred",
            }:
                status = "ready"
            entries.append(
                {
                    "entry_id": entry_id,
                    "current_temperature": str(material_entry.get("temperature") or ""),
                    "recommended_temperature": recommended_temperature,
                    "reason_codes": reason_codes,
                    "first_flagged_at": str(previous_candidate.get("first_flagged_at") or generated_at),
                    "last_flagged_at": generated_at,
                    "blocked_by_judgment_ids": blocked_by_judgment_ids,
                    "reactivation_signals": list(previous_candidate.get("reactivation_signals", []))
                    if isinstance(previous_candidate.get("reactivation_signals"), list)
                    else [],
                    "status": status if status in ARCHIVE_CANDIDATE_STATUSES else "suggested",
                }
            )
            continue
        if previous_candidate:
            reactivation_signals = archive_candidate_reactivation_signals(
                material_entry,
                routing_snapshot,
                previous_candidate,
                active_protocol=active_protocol,
            )
            if reactivation_signals:
                entries.append(
                    {
                        "entry_id": entry_id,
                        "current_temperature": str(material_entry.get("temperature") or ""),
                        "recommended_temperature": str(previous_candidate.get("recommended_temperature") or "cold"),
                        "reason_codes": [],
                        "first_flagged_at": str(previous_candidate.get("first_flagged_at") or generated_at),
                        "last_flagged_at": str(previous_candidate.get("last_flagged_at") or generated_at),
                        "blocked_by_judgment_ids": blocked_by_judgment_ids,
                        "reactivation_signals": reactivation_signals,
                        "status": "reactivated",
                    }
                )
    return {"version": 1, "generated_at": generated_at, "entries": entries}
