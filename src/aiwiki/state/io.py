"""Generic JSON / JSONL state I/O primitives extracted from the legacy app_state hub.

These are cross-layer primitives: every state owner module builds on top of them.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..utils.io import atomic_write_text, render_json_document

logger = logging.getLogger(__name__)


class CorruptStateError(RuntimeError):
    """Raised by strict state loaders when the on-disk JSON/JSONL is unreadable.

    M9-P0.4: hard boundary for callers that cannot tolerate silent fallback to
    empty state (e.g. authoritative reads where missing data == data loss).
    """

    def __init__(self, *, path: Path, reason: str, line_number: int | None = None) -> None:
        self.path = path
        self.reason = reason
        self.line_number = line_number
        loc = f"{path}" + (f":{line_number}" if line_number else "")
        super().__init__(f"corrupt state at {loc}: {reason}")


def load_json_document(path: Path) -> dict[str, Any]:
    """Best-effort JSON loader. Logs a warning on corruption and returns {} as fallback.

    Use this only when the caller's contract explicitly tolerates missing/corrupt state
    (e.g. preview, telemetry, drift hints). Authoritative reads must use
    `load_json_document_strict` instead.
    """
    if not path.exists():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning(
            "corrupt JSON state at %s (line=%d col=%d): %s; returning empty document",
            path,
            getattr(exc, "lineno", -1),
            getattr(exc, "colno", -1),
            exc.msg,
        )
        return {}
    if not isinstance(document, dict):
        logger.warning(
            "non-object JSON top-level at %s (got %s); returning empty document",
            path,
            type(document).__name__,
        )
        return {}
    return document


def load_json_document_strict(path: Path) -> dict[str, Any]:
    """Strict JSON loader. Raises `CorruptStateError` if the file exists but is unparseable.

    M9-P0.4: use this in authoritative read paths where silent fallback to {} would
    constitute data loss or hide drift.
    """
    if not path.exists():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorruptStateError(
            path=path,
            reason=f"json decode failed: {exc.msg}",
            line_number=getattr(exc, "lineno", None),
        ) from exc
    if not isinstance(document, dict):
        raise CorruptStateError(
            path=path,
            reason=f"expected JSON object, got {type(document).__name__}",
        )
    return document


def save_json_document(path: Path, document: dict[str, Any]) -> None:
    atomic_write_text(path, render_json_document(document))


def load_jsonl_documents(path: Path) -> list[dict[str, Any]]:
    """Best-effort JSONL loader. Logs a warning per corrupt line and skips it.

    Use this only when the caller can tolerate partial truth. Authoritative reads must
    use `load_jsonl_documents_strict`.
    """
    if not path.exists():
        return []
    documents: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                document = json.loads(payload)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "corrupt JSONL line at %s:%d: %s; skipping",
                    path,
                    index,
                    exc.msg,
                )
                continue
            if isinstance(document, dict):
                documents.append(document)
            else:
                logger.warning(
                    "non-object JSONL record at %s:%d (got %s); skipping",
                    path,
                    index,
                    type(document).__name__,
                )
    return documents


def load_jsonl_documents_strict(path: Path) -> list[dict[str, Any]]:
    """Strict JSONL loader. Raises `CorruptStateError` on the first unparseable record.

    M9-P0.4: use this for authoritative streams (receipts, audit, runtime history) where
    silent skipping of records would hide system state.
    """
    if not path.exists():
        return []
    documents: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                document = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise CorruptStateError(
                    path=path,
                    reason=f"json decode failed: {exc.msg}",
                    line_number=index,
                ) from exc
            if not isinstance(document, dict):
                raise CorruptStateError(
                    path=path,
                    reason=f"expected JSON object, got {type(document).__name__}",
                    line_number=index,
                )
            documents.append(document)
    return documents


def _next_jsonl_line_number(path: Path) -> int:
    if not path.exists():
        return 1
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count + 1
