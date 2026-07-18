"""LLM-backed primary workflows: ask, nightly."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from aiwiki.app_linting.core import lint_wiki
from aiwiki.app_linting.nightly import write_nightly_health
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state_paths import nightly_health_state_path
from aiwiki.compile.pipeline import compile_wiki
from aiwiki.execution.audit_reconciliation import reconcile_execution_receipts
from aiwiki.execution.receipts import write_execution_receipt
from aiwiki.runner.clients import create_client  # noqa: F401 — acceptance replay patch seam
from aiwiki.runner.receipts import _empty_llm_audit, record_llm_attempt
from aiwiki.runner.workflow_shared import _receipt_error_class
from aiwiki.utils.io import atomic_write_text, runtime_write_lock
from aiwiki.utils.path import relative_path


def _reinject_candidate_frontmatter(target: Path, *, corpus_id: str = "") -> None:
    """LLM 覆盖 artifact 后，重新注入 candidate_state 与 corpus_id 字段。

    薄 wrapper：委托给 ``execution.candidates.write_candidate_frontmatter``，
    保留既有调用点接口不变。frontmatter 写入的唯一权威入口在 candidates 模块。
    """
    from aiwiki.execution.candidates import write_candidate_frontmatter

    write_candidate_frontmatter(target, candidate_state="pending", corpus_id=corpus_id)


def run_nightly(
    root: Path,
    compile_limit: int = 5,
) -> dict[str, Any]:
    """Deterministic compile + lint plus nightly health write."""
    ensure_layout(root)
    started = time.monotonic()
    compile_result: dict[str, Any] | None = None
    lint_result: dict[str, Any] | None = None
    try:
        compile_wiki_result = compile_wiki(root)
        lint_wiki_result = lint_wiki(root)
        compile_result = {
            "compile": compile_wiki_result,
            "updated_pages": [],
            **_empty_llm_audit(),
        }
        lint_result = {
            "deterministic": lint_wiki_result,
            "semantic_report": "",
            **_empty_llm_audit(),
            "prompt_profile": "",
            "retry_prompt_profile": "",
        }
        llm_audit = _empty_llm_audit()
        llm_used = False
        state = write_nightly_health(
            root,
            compile_wiki_result,
            lint_wiki_result,
            semantic_report="",
            llm_used=False,
            runtime_history_extra={
                "compile_limit": compile_limit,
                "semantic_lint": False,
                "llm_used": False,
            },
        )

        # R95.4: audit reconciliation gate (best-effort)
        try:
            reconciliation_result = reconcile_execution_receipts(root)
        except Exception as recon_exc:  # noqa: BLE001
            import sys

            print(f"[nightly] audit reconciliation failed: {recon_exc}", file=sys.stderr)
            reconciliation_result = {"status": "failed", "error": str(recon_exc)}
        state["audit_reconciliation"] = reconciliation_result
        run_status = "success"
        with runtime_write_lock(root):
            atomic_write_text(
                nightly_health_state_path(root),
                json.dumps(state, indent=2, sort_keys=True) + "\n",
            )
    except Exception as exc:
        failed_audit = _empty_llm_audit()
        failed_audit["fallback_reason"] = str(exc)
        failed_audit["contract_validated"] = False
        with runtime_write_lock(root):
            record_llm_attempt(
                root,
                {
                    "event": "run-nightly",
                    "compile_limit": compile_limit,
                    "semantic_lint": False,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                },
                failed_audit,
                status="failed",
                error=str(exc),
                raw_response_path=getattr(exc, "raw_response_path", "") or "",
                error_class=_receipt_error_class(exc),
            )
        raise
    with runtime_write_lock(root):
        record_llm_attempt(
            root,
            {
                "event": "run-nightly",
                "compile_limit": compile_limit,
                "semantic_lint": False,
                "llm_used": llm_used,
                "repair_backlog": state["repair_backlog"]["path"],
                "state_path": relative_path(root, root / ".aiwiki" / "state" / "nightly-health.json"),
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
            llm_audit,
            status=run_status,
        )
        nightly_receipt = write_execution_receipt(
            root,
            operation="run-nightly",
            generated_by="aiwiki-run-nightly",
            subject_kind="runtime-state",
            subject_id="nightly-health",
            target_file=relative_path(root, nightly_health_state_path(root)),
            status=run_status,
            primary_path=relative_path(root, nightly_health_state_path(root)),
            protocol=str(state.get("protocol", {}).get("active_protocol") or ""),
            extra={
                "compile_limit": compile_limit,
                "semantic_lint": False,
                "llm_receipt_path": ".aiwiki/logs/llm-receipts.jsonl",
                "llm_used": llm_used,
                "delivery_mode": llm_audit.get("delivery_mode", ""),
                "backend_effective": llm_audit.get("backend_effective", ""),
                "model_final": llm_audit.get("model_final", ""),
                "autonomy_domain": "maintenance",
                "llm_governed": False,
                "decision_confidence": "",
                "evidence_refs": [relative_path(root, nightly_health_state_path(root))],
                "counter_evidence_refs": [],
                "validator_status": "passed" if run_status == "success" else run_status,
                "state_path": relative_path(root, nightly_health_state_path(root)),
            },
        )
    return {
        "compile": compile_result,
        "lint": lint_result,
        "aging": state["aging"],
        "repair_backlog": state["repair_backlog"]["path"],
        "state_path": relative_path(root, root / ".aiwiki" / "state" / "nightly-health.json"),
        "receipt_path": nightly_receipt["receipt_path"],
        "llm_used": llm_used,
        **llm_audit,
        "delivery_mode": llm_audit.get("delivery_mode", ""),
        "fallback_used": bool(llm_audit.get("fallback_used", False)),
        "fallback_from": str(llm_audit.get("fallback_from") or ""),
        "fallback_command": str(llm_audit.get("fallback_command") or ""),
        "primary_attempt_status": str(llm_audit.get("primary_attempt_status") or ""),
        "primary_error": str(llm_audit.get("primary_error") or ""),
    }


from aiwiki.runner.workflows_ask import (  # noqa: E402
    _effective_run_ask_timeout,
    _safe_quoted_report_reference_paths,
    run_ask,
    run_ask_resume,
    run_ask_submit,
)
