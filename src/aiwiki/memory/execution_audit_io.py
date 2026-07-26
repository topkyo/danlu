"""Strict execution audit history loaders for memory surfaces (no execution deps).

Moved from ``execution.policy`` so ``memory.execution_surfaces`` can build
audit snapshots without importing the execution package. Best-effort loaders
and append writers remain in ``execution.policy``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..state.io import CorruptStateError
from .paths import execution_policy_log_path, execution_receipt_history_path


def load_execution_policy_decision_history_strict(root: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Strict variant for fact-layer / decision paths.

    Raises CorruptStateError on malformed JSONL or non-dict records. Missing
    file returns []; that is not corruption.
    """
    path = execution_policy_log_path(root)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CorruptStateError(
                    path=path,
                    reason=f"corrupt execution-policy decisions JSONL at {path}:{line_no}: {exc}",
                    line_number=line_no,
                ) from exc
            if not isinstance(record, dict):
                raise CorruptStateError(
                    path=path,
                    reason=f"non-dict execution-policy decisions JSONL row at {path}:{line_no}",
                    line_number=line_no,
                )
            records.append(record)
    records.reverse()
    if limit is None:
        return records
    return records[:limit]


def load_execution_receipt_history_strict(root: Path) -> list[dict[str, Any]]:
    """Strict variant for fact-layer / decision paths.

    Raises CorruptStateError on malformed JSONL or non-dict records. Missing
    file returns []; that is not corruption. Invalid UTF-8 raises
    UnicodeDecodeError naturally.
    """
    path = execution_receipt_history_path(root)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CorruptStateError(
                    path=path,
                    reason=f"corrupt execution-receipts JSONL at {path}:{line_no}: {exc}",
                    line_number=line_no,
                ) from exc
            if not isinstance(payload, dict):
                raise CorruptStateError(
                    path=path,
                    reason=f"non-dict execution-receipts JSONL row at {path}:{line_no}",
                    line_number=line_no,
                )
            if str(payload.get("kind") or "") == "execution-receipt":
                records.append(payload)
    return list(reversed(records))
