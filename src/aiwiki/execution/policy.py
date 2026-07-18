"""Execution policy domain logic (EP-017C step 4a).

Split out of ``aiwiki.content.memory``: execution-policy profile / band
labels, decision-record construction, decision / receipt history loaders
(best-effort and strict), and decision append.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..app_protocol import (
    DEFAULT_PROTOCOL,
    EXECUTION_BAND_LABELS,
    protocol_execution_policy_rule,
)
from ..app_state_paths import execution_policy_log_path, execution_receipt_history_path
from ..state.io import CorruptStateError
from ..utils.io import atomic_append_jsonl, runtime_write_operation

logger = logging.getLogger(__name__)


def _action_supports_low_risk_apply(action: dict[str, Any]) -> bool:
    # Lazy import to avoid a module-load cycle:
    # ``aiwiki.memory.action_core`` imports this module for
    # ``execution_policy_profile`` / ``execution_band_label``, and
    # ``execution_policy_profile`` below needs ``action_supports_low_risk_apply``
    # which lives in ``aiwiki.memory.action_core``. The lazy import keeps the
    # dependency direction one-way at module-load time.
    from ..memory.action_core import action_supports_low_risk_apply

    return action_supports_low_risk_apply(action)


def execution_policy_profile(action: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    status = str(action.get("status") or "proposed")
    active = bool(action.get("active", True))
    if not active:
        return {
            "execution_policy": "inactive-history",
            "execution_band": "history-only",
            "policy_decision": "history",
            "policy_rule_id": "inactive-history",
            "capabilities": ["history"],
            "policy_summary": "信号已消失，只保留历史与审计价值。",
        }
    if status == "proposed":
        return {
            "execution_policy": "triage",
            "execution_band": "review-first",
            "policy_decision": "review",
            "policy_rule_id": "proposed-triage",
            "capabilities": ["review"],
            "policy_summary": "先 review / triage，再决定是否进入 accepted。",
        }
    if status == "accepted":
        if root is not None:
            protocol = str(action.get("protocol") or DEFAULT_PROTOCOL)
            kind = str(action.get("kind") or "")
            rule = protocol_execution_policy_rule(root, protocol, kind)
            if rule:
                return {
                    "execution_policy": str(rule.get("execution_policy") or "manual-repair"),
                    "execution_band": str(rule.get("execution_band") or "manual-repair"),
                    "policy_decision": str(rule.get("decision") or "review"),
                    "policy_rule_id": f"{protocol}:{kind}",
                    "capabilities": [
                        str(item) for item in rule.get("capabilities", []) if isinstance(item, str) and item
                    ],
                    "policy_summary": str(rule.get("policy_summary") or ""),
                }
        if _action_supports_low_risk_apply(action):
            return {
                "execution_policy": "semi-auto-apply",
                "execution_band": "bundle-safe-apply",
                "policy_decision": "allow",
                "policy_rule_id": f"legacy:{str(action.get('kind') or '')}",
                "capabilities": ["dry-run", "bundle-apply", "revert-safe", "history"],
                "policy_summary": "支持 dry-run、bundle-driven apply 和 receipt 驱动回滚。",
            }
        return {
            "execution_policy": "manual-repair",
            "execution_band": "manual-repair",
            "policy_decision": "review",
            "policy_rule_id": f"legacy:{str(action.get('kind') or '')}",
            "capabilities": ["manual-edit", "review"],
            "policy_summary": "只能走人工修复与 review，不开放 safe apply。",
        }
    if status == "deferred":
        return {
            "execution_policy": "parked",
            "execution_band": "deferred",
            "policy_decision": "history",
            "policy_rule_id": "deferred-parked",
            "capabilities": ["resume-review", "history"],
            "policy_summary": "动作已暂缓，保留复查与恢复入口。",
        }
    return {
        "execution_policy": "closed",
        "execution_band": "closed",
        "policy_decision": "history",
        "policy_rule_id": "closed-history",
        "capabilities": ["history"],
        "policy_summary": "动作已关闭，仅保留审计与历史记录。",
    }


def execution_band_label(band: str) -> str:
    return EXECUTION_BAND_LABELS.get(band, band or "unknown")


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


def load_execution_policy_decision_history_strict(root: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Strict variant for fact-layer / decision paths.

    Raises CorruptStateError on malformed JSONL or non-dict records. Missing
    file returns []; that is not corruption. Use only on fact-layer paths
    (nightly aggregation, lint phases, execution-audit surfaces). UI/dashboard
    should keep best-effort load_execution_policy_decision_history.
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


def load_execution_receipt_history_strict(root: Path) -> list[dict[str, Any]]:
    """Strict variant for fact-layer / decision paths.

    Raises CorruptStateError on malformed JSONL or non-dict records. Missing
    file returns []; that is not corruption. Invalid UTF-8 raises
    UnicodeDecodeError naturally. UI/dashboard should keep best-effort
    load_execution_receipt_history.
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
