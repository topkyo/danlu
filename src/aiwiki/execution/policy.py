"""Execution policy domain logic (EP-017C step 4a).

Owns best-effort history loaders, decision-record construction, and append.
Profile / band labels and strict audit loaders live in ``memory.action_policy``
/ ``memory.execution_audit_io`` and are re-exported here for public callers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..memory.action_policy import execution_band_label, execution_policy_profile
from ..memory.execution_audit_io import (
    load_execution_policy_decision_history_strict,
    load_execution_receipt_history_strict,
)
from ..state.constants import DEFAULT_PROTOCOL
from ..utils.io import atomic_append_jsonl, runtime_write_operation
from .paths import execution_policy_log_path, execution_receipt_history_path

logger = logging.getLogger(__name__)


def execution_policy_decision_record(
    action: dict[str, Any],
    *,
    occurred_at: str,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "execution-policy-decision",
        "occurred_at": occurred_at,
        "action_id": str(action.get("id") or ""),
        "title": str(action.get("title") or action.get("id") or ""),
        "action_kind": str(action.get("kind") or ""),
        "status": str(action.get("status") or "proposed"),
        "protocol": str(action.get("protocol") or active_protocol or DEFAULT_PROTOCOL),
        "policy_decision": str(action.get("policy_decision") or ""),
        "policy_rule_id": str(action.get("policy_rule_id") or ""),
        "execution_policy": str(action.get("execution_policy") or ""),
        "execution_band": str(action.get("execution_band") or ""),
        "apply_ready": str(action.get("apply_ready") or "false"),
        "active": bool(action.get("active", True)),
        "primary_path": str(action.get("primary_path") or ""),
        "secondary_path": str(action.get("secondary_path") or ""),
        "component_id": str(action.get("component_id") or ""),
    }


def load_execution_policy_decision_history(root: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Best-effort execution-policy decision history loader.

    Failure mode: malformed JSONL rows or non-dict records are skipped and
    exposed via logger.warning. The function never raises those row-level
    corruption errors to callers; it returns the remaining valid records.
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
                logger.warning(
                    "execution-policy decisions JSONL skip corrupt line: path=%s line_no=%d reason=%s",
                    path,
                    line_no,
                    type(exc).__name__,
                )
                continue
            if isinstance(record, dict):
                records.append(record)
            else:
                logger.warning(
                    "execution-policy decisions JSONL skip non-dict line: path=%s line_no=%d type=%s",
                    path,
                    line_no,
                    type(record).__name__,
                )
    records.reverse()
    if limit is None:
        return records
    return records[:limit]


@runtime_write_operation
def append_execution_policy_decisions(root: Path, decisions: list[dict[str, Any]]) -> None:
    if not decisions:
        return
    path = execution_policy_log_path(root)
    for decision in decisions:
        atomic_append_jsonl(path, decision)


def load_execution_receipt_history(root: Path) -> list[dict[str, Any]]:
    """Best-effort execution receipt history loader.

    Failure mode: malformed JSONL rows, replacement-decoded bad UTF-8, or
    non-dict records are skipped and exposed via logger.warning. The function
    never raises those row-level corruption errors to callers; it returns the
    remaining valid execution-receipt records.
    """
    path = execution_receipt_history_path(root)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning(
                "execution-receipts JSONL skip corrupt line: path=%s line_no=%d reason=%s",
                path,
                line_no,
                type(exc).__name__,
            )
            continue
        if isinstance(payload, dict) and str(payload.get("kind") or "") == "execution-receipt":
            records.append(payload)
        elif not isinstance(payload, dict):
            logger.warning(
                "execution-receipts JSONL skip non-dict line: path=%s line_no=%d type=%s",
                path,
                line_no,
                type(payload).__name__,
            )
    return list(reversed(records))
