"""Machine-memory scoring and time-focus helpers extracted from app_memory."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from ..protocol.focus_scoring import protocol_focus_score
from ..protocol.library import PROTOCOL_LIBRARY
from ..state.constants import DEFAULT_PROTOCOL
from ..utils.time import parse_iso_datetime


def timestamp_is_newer(candidate: str, current: str) -> bool:
    candidate_dt = parse_iso_datetime(candidate)
    current_dt = parse_iso_datetime(current)
    if candidate_dt is None:
        return False
    if current_dt is None:
        return True
    return candidate_dt > current_dt


def update_latest_timestamp(mapping: dict[str, str], key: str, timestamp: str) -> None:
    if not key or not timestamp:
        return
    if timestamp_is_newer(timestamp, mapping.get(key, "")):
        mapping[key] = timestamp


def protocol_hints_for_material(entry: dict[str, Any], preview: str) -> list[str]:
    text = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("source_type") or ""),
            preview,
        ]
    )
    scored: list[tuple[int, str]] = []
    for protocol in sorted(PROTOCOL_LIBRARY):
        if protocol == DEFAULT_PROTOCOL:
            continue
        score = protocol_focus_score(protocol, text)
        if score > 0:
            scored.append((score, protocol))
    scored.sort(key=lambda item: (-item[0], item[1]))
    hints = [protocol for _score, protocol in scored[:2]]
    return hints or [DEFAULT_PROTOCOL]


def recency_score_for_timestamp(timestamp: str) -> float:
    parsed = parse_iso_datetime(timestamp)
    if parsed is None:
        return 0.0
    now = datetime.now(timezone.utc)
    age = now - parsed
    if age <= timedelta(days=3):
        return 1.0
    if age <= timedelta(days=7):
        return 0.7
    if age <= timedelta(days=30):
        return 0.4
    return 0.1


QUERY_TIME_FOCUS_MARKERS: dict[str, tuple[str, ...]] = {
    "recent": ("latest", "recent", "current", "new", "newest", "updated", "today", "fresh"),
    "historical": ("history", "historical", "legacy", "old", "older", "previous", "prior", "archive", "archived"),
}


def machine_memory_query_time_focus(question: str) -> dict[str, Any]:
    normalized = " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", question.lower()))
    recent_hits = [marker for marker in QUERY_TIME_FOCUS_MARKERS["recent"] if marker in normalized]
    historical_hits = [marker for marker in QUERY_TIME_FOCUS_MARKERS["historical"] if marker in normalized]
    if historical_hits and len(historical_hits) >= len(recent_hits):
        return {"focus": "historical", "markers": historical_hits[:4]}
    if recent_hits:
        return {"focus": "recent", "markers": recent_hits[:4]}
    return {"focus": "", "markers": []}
