"""Review window scheduling helpers extracted from app_protocol."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..state.constants import DEFAULT_PROTOCOL
from ..utils.time import parse_iso_datetime
from .runtime_config import AGING_WINDOWS_DAYS, PROTOCOL_REVIEW_WINDOWS
from .runtime_schema import load_protocol_runtime_schema


def schedule_review_windows(
    kind: str,
    status: str,
    base_timestamp: str,
    *,
    protocol: str = DEFAULT_PROTOCOL,
    root: Path | None = None,
) -> tuple[str, str]:
    windows = AGING_WINDOWS_DAYS.get((kind, status))
    if root is not None:
        runtime_schema = load_protocol_runtime_schema(root, protocol)
        review_windows = runtime_schema.get("review_windows", {}) if isinstance(runtime_schema, dict) else {}
        candidate = review_windows.get(f"{kind}:{status}") if isinstance(review_windows, dict) else None
        if isinstance(candidate, list) and len(candidate) == 2 and all(isinstance(item, int) for item in candidate):
            windows = (candidate[0], candidate[1])
    elif protocol in PROTOCOL_REVIEW_WINDOWS:
        windows = PROTOCOL_REVIEW_WINDOWS.get(protocol, {}).get((kind, status), windows)
    if not windows:
        return "", ""
    base = parse_iso_datetime(base_timestamp) or datetime.now(timezone.utc)
    revisit_days, escalate_days = windows
    revisit_after = (base + timedelta(days=revisit_days)).replace(microsecond=0).isoformat()
    escalate_after = (base + timedelta(days=escalate_days)).replace(microsecond=0).isoformat()
    return revisit_after, escalate_after
