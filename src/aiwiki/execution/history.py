"""Runtime / run-log / LLM-receipt history loaders + universal audit append.

Extracted from the legacy app_state hub. Owned by the execution layer; the
`append_runtime_history` writer mirrors each event into the universal audit stream
via the sibling `execution.audit_preview` module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_state_paths import (
    llm_receipt_log_path,
    run_log_path,
    runtime_history_path,
)
from ..state.io import (
    _next_jsonl_line_number,
    load_jsonl_documents,
    load_jsonl_documents_strict,
)
from ..utils.audit import AuditMirrorError, AuditMirrorRollbackError
from ..utils.io import _durable_truncate, atomic_append_jsonl, runtime_write_operation
from ..utils.path import relative_path


def load_runtime_history(root: Path) -> list[dict[str, Any]]:
    return load_jsonl_documents(runtime_history_path(root))


def load_runtime_history_strict(root: Path) -> list[dict[str, Any]]:
    """Strict variant of load_runtime_history for execution decision paths.

    Raises CorruptStateError on malformed JSONL. Use only on fact-layer /
    decision paths; dashboard/preview should keep best-effort load_runtime_history.
    """
    return load_jsonl_documents_strict(runtime_history_path(root))


def load_run_log_history(root: Path) -> list[dict[str, Any]]:
    return load_jsonl_documents(run_log_path(root))


def load_llm_receipt_history(root: Path) -> list[dict[str, Any]]:
    return load_jsonl_documents(llm_receipt_log_path(root))


@runtime_write_operation
def append_runtime_history(root: Path, event: dict[str, Any]) -> None:
    path = runtime_history_path(root)
    size_before = path.stat().st_size if path.exists() else 0
    line_number = _next_jsonl_line_number(path)
    atomic_append_jsonl(path, event)
    from .audit_preview import append_universal_audit_record

    try:
        append_universal_audit_record(
            root,
            source_stream="runtime_history",
            source_ref=f"{relative_path(root, path)}#L{line_number}",
            document=event,
        )
    except Exception as audit_exc:
        try:
            _durable_truncate(path, size_before)
        except Exception as truncate_exc:
            raise AuditMirrorRollbackError(
                "audit mirror append failed and primary truncate also failed: "
                f"audit={audit_exc!r}; truncate={truncate_exc!r}"
            ) from audit_exc
        raise AuditMirrorError(f"universal audit append failed; primary truncated: {audit_exc!r}") from audit_exc
