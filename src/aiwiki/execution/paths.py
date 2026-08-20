"""Execution path helpers extracted from aiwiki.app_state_paths."""

from __future__ import annotations

from pathlib import Path


def execution_receipt_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-receipts.jsonl"


def run_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "logs" / "runs.jsonl"


def llm_receipt_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "logs" / "llm-receipts.jsonl"


def execution_policy_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-policy-decisions.jsonl"


def runtime_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "runtime-history.jsonl"
