"""Note / transcript drop handler (markdown + plain text ingestion)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..drop_helpers import timestamped_stem
from ..protocol.scaffold import ensure_layout
from ..utils.io import atomic_copy_file, atomic_write_text, runtime_write_lock
from ..utils.path import relative_path
from .common import SensitiveContentError, _append_manifest_entry, _append_raw_added_history, _note_title, _unique_path

SENSITIVE_SCAN_CONTEXT_CHARS = 60000

_SENSITIVE_VALUE_PATTERN = re.compile(
    r"""
    (?:
        \b(?:password|passwd|pwd|token|secret|api[_ -]?key|private[_ -]?key|access[_ -]?key|github[_ -]?token|ssh[_ -]?key|sudo[_ -]?password)\b
        |(?:密码|口令|令牌|密钥|私钥)
    )
    \s*(?:[:=：]|is|为)\s*
    (?P<value>.+)
    """,
    re.IGNORECASE | re.VERBOSE,
)
_PRIVATE_KEY_BLOCK_PATTERN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
_SENSITIVE_PLACEHOLDERS = {
    "",
    "-",
    "none",
    "null",
    "n/a",
    "no",
    "false",
    "redacted",
    "[redacted]",
    "<redacted>",
    "***",
    "****",
    "xxxxx",
    "xxxxxx",
    "todo",
    "tbd",
}


def drop_note(
    root: Path,
    source: str | None = None,
    *,
    title: str | None = None,
    text: str | None = None,
    kind: str = "note",
    allow_sensitive: bool = False,
) -> dict[str, Any]:
    with runtime_write_lock(root):
        return _drop_note_unlocked(root, source, title=title, text=text, kind=kind, allow_sensitive=allow_sensitive)


def _drop_note_unlocked(
    root: Path,
    source: str | None = None,
    *,
    title: str | None = None,
    text: str | None = None,
    kind: str = "note",
    allow_sensitive: bool = False,
) -> dict[str, Any]:
    ensure_layout(root)
    note_kind = kind.strip().lower()
    if note_kind not in {"note", "transcript"}:
        raise ValueError(f"Unsupported note kind: {kind}")
    if source and text is not None:
        raise ValueError("Provide either a note file path or --text, not both.")
    if text is not None:
        captured_text = text
        original_path = "inline://note"
        capture_mode = "inline-text"
        fallback_title = note_kind.title()
        source_path = None
    else:
        if not source:
            raise ValueError("Provide a markdown/text file path or --text for drop-note.")
        source_path = Path(source).expanduser()
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"Note file not found: {source}")
        captured_text = source_path.read_text(encoding="utf-8", errors="replace")
        original_path = str(source)
        capture_mode = "file"
        fallback_title = source_path.stem or note_kind.title()
    if not captured_text:
        raise RuntimeError("Note capture is empty.")
    if not allow_sensitive:
        _assert_no_sensitive_text(captured_text, source_label=original_path)
    display_title = title or _note_title(captured_text, fallback=fallback_title)
    stem = timestamped_stem(display_title)
    suffix = source_path.suffix.lower() if source_path is not None and source_path.suffix else ".md"
    note_path = _unique_path(root / "raw" / "inbox", stem, suffix)
    if source_path is None:
        atomic_write_text(note_path, captured_text, fsync=True)
    else:
        atomic_copy_file(source_path, note_path, fsync=True)
    entry = _append_manifest_entry(
        root,
        stored_path=note_path,
        original_path=original_path,
        source_type="note-drop",
        title=display_title,
        note_kind=note_kind,
    )
    _append_raw_added_history(
        root,
        material="note",
        stored_path=note_path,
        original_path=original_path,
        source_type="note-drop",
        title=display_title,
        entry_id=entry["id"],
        note_kind=note_kind,
        capture_mode=capture_mode,
    )
    return {
        "material": "note",
        "note_path": relative_path(root, note_path),
        "note_kind": note_kind,
        "original_path": original_path,
        "title": display_title,
    }


def _assert_no_sensitive_text(text: str, *, source_label: str) -> None:
    findings = _sensitive_text_findings(text)
    if not findings:
        return
    rendered = ", ".join(f"line {line_no} `{kind}`" for line_no, kind in findings[:4])
    extra = "" if len(findings) <= 4 else f", +{len(findings) - 4} more"
    raise SensitiveContentError(
        f"Sensitive content detected in note input `{source_label}` ({rendered}{extra}). "
        "Remove credentials before ingestion or rerun with --allow-sensitive for an intentional local-only secret vault."
    )


def _sensitive_text_findings(text: str) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    scanned = text[:SENSITIVE_SCAN_CONTEXT_CHARS]
    for line_no, line in enumerate(scanned.splitlines(), start=1):
        if _PRIVATE_KEY_BLOCK_PATTERN.search(line):
            findings.append((line_no, "private-key"))
            continue
        match = _SENSITIVE_VALUE_PATTERN.search(line)
        if not match:
            continue
        value = _normalized_sensitive_value(match.group("value"))
        if value in _SENSITIVE_PLACEHOLDERS:
            continue
        findings.append((line_no, "credential-field"))
    return findings


def _normalized_sensitive_value(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.split(r"\s+#|\s+//", cleaned, maxsplit=1)[0].strip()
    cleaned = cleaned.strip('`"')
    return cleaned.lower()
