"""Execution path helpers extracted from aiwiki.app_state_paths."""

from __future__ import annotations

from pathlib import Path

from ..utils.text import slugify


def execution_receipt_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-receipts.jsonl"


def run_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "logs" / "runs.jsonl"


def llm_receipt_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "logs" / "llm-receipts.jsonl"


def run_notes_path(root: Path, run_id: str) -> Path:
    """Legacy path for retired run-progress notes (no longer written)."""

    return root / "output" / "control" / "runs" / slugify(run_id) / "thinking.md"


def execution_policy_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-policy-decisions.jsonl"


def runtime_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "runtime-history.jsonl"
