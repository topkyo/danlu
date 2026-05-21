"""Shared helpers for runner workflow modules."""

from __future__ import annotations

import os
from pathlib import Path

from aiwiki.llm import CompletionResult, _write_raw_response, classify_backend_error


def reinject_candidate_frontmatter(target: Path, *, corpus_id: str = "") -> None:
    from aiwiki.execution.candidates import write_candidate_frontmatter

    write_candidate_frontmatter(target, candidate_state="pending", corpus_id=corpus_id)


DEFAULT_REPORT_TIMEOUT_SECONDS = 240

def _env_flag(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}

def _receipt_error_class(exc: Exception | str) -> str:
    message = str(exc)
    classified = classify_backend_error(message)
    if classified == "timeout":
        return "timeout"
    lowered = message.lower()
    if "frontmatter" in lowered or "parse" in lowered or "invalid json" in lowered:
        return "parse_error"
    if "exit code" in lowered or "non-zero" in lowered or "nonzero" in lowered:
        return "non_zero_exit"
    return "other"

def _raw_response_path(root: Path, result: CompletionResult | None, exc: Exception | None = None) -> str:
    if exc is not None:
        path = getattr(exc, "raw_response_path", None)
        if isinstance(path, str) and path:
            return path
    if result is None:
        return ""
    if result.raw_response_path:
        return result.raw_response_path
    return _write_raw_response(root, result.text)
