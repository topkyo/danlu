"""Memory path helpers."""

from __future__ import annotations

from pathlib import Path


def machine_memory_action_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory-actions.json"


def machine_memory_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory-history.jsonl"


def execution_receipt_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-receipts.jsonl"


def execution_policy_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-policy-decisions.jsonl"
