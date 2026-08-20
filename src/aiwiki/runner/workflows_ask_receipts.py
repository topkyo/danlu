"""Receipt / timeout / shell-summary refresh helpers for run-ask workflows."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from aiwiki.execution.receipts import write_execution_receipt
from aiwiki.render.paths import execution_receipts_dir
from aiwiki.runner.workflow_shared import DEFAULT_REPORT_TIMEOUT_SECONDS
from aiwiki.utils.path import next_available_stem, relative_path
from aiwiki.utils.text import slugify

_logger = logging.getLogger(__name__)


def _refresh_shell_summary_fail_soft(root: Path) -> None:
    try:
        from aiwiki.app_shell.meta import write_shell_summary
        from aiwiki.app_shell.summary import build_shell_summary

        write_shell_summary(root, build_shell_summary(root))
    except Exception as exc:
        _logger.warning(
            "shell summary refresh failed after run-ask background update: %s",
            exc,
        )


def _effective_run_ask_timeout(output_format: str, timeout_seconds: int | None) -> int | None:
    if timeout_seconds is not None:
        return timeout_seconds
    if output_format == "report" and not os.environ.get("AIWIKI_LLM_TIMEOUT", "").strip():
        return DEFAULT_REPORT_TIMEOUT_SECONDS
    return None


def _write_run_ask_output_receipt(
    root: Path,
    *,
    generated_by: str,
    artifact_ref: str,
    run_id: str,
    question: str,
    output_format: str,
    protocol: str,
    delivery_mode: str,
    run_ask_path: str,
    artifact_status: str = "completed",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    receipt_extra: dict[str, Any] = {
        "receipt_matrix_version": 1,
        "run_ask_path": run_ask_path,
        "artifact_status": artifact_status,
        "format": output_format,
        "question": question,
        "run_id": run_id,
        "llm_receipt_path": ".aiwiki/logs/llm-receipts.jsonl",
        "delivery_mode": delivery_mode,
    }
    if extra:
        receipt_extra.update(extra)
    return write_execution_receipt(
        root,
        operation="run-ask",
        generated_by=generated_by,
        subject_kind="output-artifact",
        subject_id=run_id or Path(artifact_ref).stem,
        target_file=artifact_ref,
        primary_path=artifact_ref,
        protocol=protocol,
        extra=receipt_extra,
    )


def _planned_run_ask_output_receipt_ref(root: Path, *, artifact_ref: str, run_id: str) -> str:
    receipt_dir = execution_receipts_dir(root)
    seed_target = Path(artifact_ref).stem or run_id or "run-ask"
    seed = slugify(f"run-ask-{seed_target}") or slugify("run-ask") or "execution-receipt"
    action_id = next_available_stem(receipt_dir, seed, suffix=".json")
    return relative_path(root, receipt_dir / f"{action_id}.json")
