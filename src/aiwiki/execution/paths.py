"""Execution path helpers extracted from aiwiki.app_state_paths.

Top-level import of ``render.paths.execution_bundles_dir`` is safe:
``render.paths`` does not import from ``execution``.
"""

from __future__ import annotations

from pathlib import Path

from ..render.paths import execution_bundles_dir
from ..utils.text import slugify


def execution_receipt_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-receipts.jsonl"


def execution_batches_dir(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-batches"


def execution_batch_receipt_path(root: Path, batch_id: str) -> Path:
    return execution_batches_dir(root) / f"{slugify(batch_id)}.json"


def execution_dry_run_path(root: Path, action_id: str) -> Path:
    return execution_bundles_dir(root) / f"{slugify(action_id)}-dry-run.json"


def run_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "logs" / "runs.jsonl"


def llm_receipt_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "logs" / "llm-receipts.jsonl"


def run_notes_path(root: Path, run_id: str) -> Path:
    """Legacy path for retired run-progress notes (no longer written)."""

    return root / "output" / "control" / "runs" / slugify(run_id) / "thinking.md"


def material_archive_action_id(entry_id: str) -> str:
    return f"archive-{entry_id}"


def archive_dry_run_path(root: Path, entry_id: str) -> Path:
    return execution_bundles_dir(root) / f"{slugify(material_archive_action_id(entry_id))}-dry-run.json"


def rewrite_dry_run_path(root: Path, slug: str) -> Path:
    return execution_bundles_dir(root) / f"{slugify(f'rewrite-{slug}')}-dry-run.json"


def execution_policy_log_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "execution-policy-decisions.jsonl"


def runtime_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "runtime-history.jsonl"
