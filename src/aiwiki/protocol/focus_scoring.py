"""Protocol focus scoring helpers extracted from app_protocol."""

from __future__ import annotations

import re
from typing import Any

from .runtime_config import PROTOCOL_ACTION_KIND_WEIGHTS, PROTOCOL_FOCUS_KEYWORDS


def protocol_focus_score(protocol: str, text: str) -> int:
    normalized = " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.lower()))
    return sum(1 for marker in PROTOCOL_FOCUS_KEYWORDS.get(protocol, ()) if marker in normalized)


def page_focus_score(active_protocol: str, page: dict[str, str]) -> int:
    score = protocol_focus_score(
        active_protocol,
        " ".join(
            [
                str(page.get("title") or ""),
                str(page.get("path") or ""),
                str(page.get("status") or ""),
            ]
        ),
    )
    if str(page.get("protocol") or "") == active_protocol:
        score += 10
    return score


def action_focus_score(active_protocol: str, action: dict[str, Any]) -> int:
    score = protocol_focus_score(
        active_protocol,
        " ".join(
            [
                str(action.get("title") or ""),
                str(action.get("reason") or ""),
                str(action.get("primary_path") or ""),
                str(action.get("secondary_path") or ""),
            ]
        ),
    )
    score += PROTOCOL_ACTION_KIND_WEIGHTS.get(active_protocol, {}).get(str(action.get("kind") or ""), 0)
    return score


def entry_focus_score(active_protocol: str, entry: dict[str, Any], summary_or_preview: str) -> int:
    return protocol_focus_score(
        active_protocol,
        " ".join(
            [
                str(entry.get("title") or ""),
                str(entry.get("source_type") or ""),
                summary_or_preview,
            ]
        ),
    )


def concept_focus_score(active_protocol: str, title: str, content: str) -> int:
    return protocol_focus_score(active_protocol, f"{title}\n{content}")
