"""Machine-memory action execution-policy profile (no execution-package deps).

Moved from ``execution.policy`` so ``memory.action_core`` / surfaces can
label bands without importing the execution package. ``execution.policy``
re-exports these symbols for existing callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..protocol.runtime_config import EXECUTION_BAND_LABELS, protocol_execution_policy_rule
from ..state.constants import DEFAULT_PROTOCOL


def execution_band_label(band: str) -> str:
    return EXECUTION_BAND_LABELS.get(band, band or "unknown")


def execution_policy_profile(action: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    # Lazy: action_core imports this module for profile/label at load time.
    from .action_core import action_supports_low_risk_apply

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
        if action_supports_low_risk_apply(action):
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
