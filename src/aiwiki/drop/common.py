"""Shared helpers for the drop package (raw-material ingestion internals).

These helpers are used by every drop handler (url/pdf/image/repo/note) and are
kept here so each handler module stays focused on its own collection and
materialization logic. Public entry points live in the sibling handler modules
and are re-exported by ``aiwiki.drop`` (the package ``__init__``).
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from urllib import parse

# ``aiwiki.drop`` is imported lazily as a module-level alias so internal calls
# to monkeypatched names (``utc_now`` and ``_fetch_url``) resolve through the
# package namespace at call time. ``tests/acceptance/case_runner.py`` patches
# ``aiwiki.drop.utc_now`` and ``aiwiki.drop._fetch_url``; if handlers resolved
# these via their own submodule globals the patches would not propagate.
# The import is safe (no attribute access at import time) even though
# ``aiwiki.drop`` is still being initialized when this module loads.
import aiwiki.drop as _drop_pkg

from ..drop_helpers import timestamped_stem
from ..execution.history import append_runtime_history
from ..execution.paths import runtime_history_path
from ..state.constants import DEFAULT_PROTOCOL
from ..state.manifest import load_manifest, save_manifest
from ..state.paths import manifest_path
from ..utils.hash import sha256_file
from ..utils.io import atomic_write_bytes, atomic_write_text
from ..utils.markdown import first_markdown_heading
from ..utils.path import next_identifier, relative_path
from ..utils.security import safe_fetch, safe_resolve_within
from ..utils.text import detect_kind, slugify

MAX_TEXT_CHARS = 120000
_HTML_MAX_BYTES = 5 * 1024 * 1024
_ASSET_MAX_BYTES = 50 * 1024 * 1024
# Local PDF ingestion reuses the remote asset cap; images get a tighter OCR/vision cap.
_LOCAL_PDF_MAX_BYTES = _ASSET_MAX_BYTES
_LOCAL_IMAGE_MAX_BYTES = 25 * 1024 * 1024
_SUPPORTED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}

_LOGGER = logging.getLogger("aiwiki.drop")


class SensitiveContentError(ValueError):
    """Raised when a raw note appears to contain credentials or secrets."""


def _assert_file_size(path: Path, max_bytes: int, label: str) -> None:
    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(f"{label} exceeds size limit: {size} > {max_bytes} bytes")


def _assert_pdf_asset(path: Path) -> None:
    with path.open("rb") as handle:
        magic = handle.read(5)
    if magic != b"%PDF-":
        raise ValueError("File does not look like a PDF (magic bytes missing)")


def _assert_supported_image_mime(mime: str) -> None:
    if mime not in _SUPPORTED_IMAGE_MIME_TYPES:
        raise ValueError(f"Unsupported image MIME type: {mime}; allowed: {sorted(_SUPPORTED_IMAGE_MIME_TYPES)}")


def _append_run_event(root: Path, event: dict[str, Any]) -> None:
    from ..runner.receipts import _append_log

    _append_log(root, event)


def _append_raw_added_history(
    root: Path,
    *,
    material: str,
    stored_path: Path,
    original_path: str,
    source_type: str,
    title: str,
    entry_id: str = "",
    note_kind: str = "",
    capture_mode: str = "",
    ingest_metadata: dict[str, Any] | None = None,
) -> None:
    event: dict[str, Any] = {
        "event_type": "raw-added",
        "occurred_at": _drop_pkg.utc_now(),
        "protocol": DEFAULT_PROTOCOL,
        "material": material,
        "stored_path": relative_path(root, stored_path),
        "original_path": original_path,
        "source_type": source_type,
        "title": title,
    }
    if entry_id:
        event["entry_id"] = entry_id
        event["source_ids"] = [entry_id]
    if note_kind:
        event["note_kind"] = note_kind
    if capture_mode:
        event["capture_mode"] = capture_mode
    if ingest_metadata:
        event["ingest_metadata"] = ingest_metadata
    append_runtime_history(root, event)


def _append_manifest_entry(
    root: Path,
    *,
    stored_path: Path,
    original_path: str,
    source_type: str,
    title: str,
    note_kind: str = "",
    ingest_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    relative = relative_path(root, stored_path)
    for entry in entries:
        if entry.get("stored_path") == relative:
            updated_at = _drop_pkg.utc_now()
            entry.update(
                {
                    "title": title,
                    "source_type": source_type,
                    "note_kind": note_kind,
                    "original_path": original_path,
                    "kind": detect_kind(stored_path),
                    "sha256": sha256_file(stored_path),
                    "updated_at": updated_at,
                }
            )
            if ingest_metadata:
                entry["ingest_metadata"] = ingest_metadata
            save_manifest(root, manifest)
            return entry
    existing_ids = {str(entry.get("id") or "") for entry in entries}
    slug = slugify(title or stored_path.stem)
    seed = (
        f"source-{slug}" if slug and slug != "item" else f"source-{hashlib.sha256(relative.encode()).hexdigest()[:12]}"
    )
    entry_id = next_identifier(existing_ids, seed)
    imported_at = _drop_pkg.utc_now()
    entry = {
        "id": entry_id,
        "title": title,
        "source_type": source_type,
        "note_kind": note_kind,
        "original_path": original_path,
        "stored_path": relative,
        "kind": detect_kind(stored_path),
        "sha256": sha256_file(stored_path),
        "imported_at": imported_at,
        "updated_at": imported_at,
    }
    if ingest_metadata:
        entry["ingest_metadata"] = ingest_metadata
    entries.append(entry)
    save_manifest(root, manifest)
    return entry


def _rollback_created_paths(created_paths: list[Path]) -> None:
    for path in reversed(created_paths):
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            _LOGGER.warning("drop rollback unlink failed for %s: %s", path, exc)


def _cleanup_tmp_dir(tmp_dir: Path) -> None:
    """Best-effort remove a drop collect tmp dir; warn on failure, never raise.

    Used by collect helpers to clear scratch dirs after materialize success or
    on collect exception paths. Cleanup failures must not mask the original
    error nor break the public drop API contract (no raise from cleanup).
    """
    try:
        shutil.rmtree(tmp_dir)
    except FileNotFoundError:
        return
    except OSError as exc:
        _LOGGER.warning("drop tmp cleanup failed for %s: %s", tmp_dir, exc)


def _snapshot_append_files(root: Path) -> dict[Path, tuple[bool, int]]:
    candidates = [runtime_history_path(root), manifest_path(root)]
    sizes: dict[Path, tuple[bool, int]] = {}
    for path in candidates:
        try:
            if path.exists():
                sizes[path] = (True, path.stat().st_size)
            else:
                sizes[path] = (False, 0)
        except OSError as exc:
            _LOGGER.warning("drop rollback snapshot stat failed for %s: %s", path, exc)
            continue
    return sizes


def _truncate_append_files(snapshots: dict[Path, tuple[bool, int]]) -> None:
    for path, (existed, size) in snapshots.items():
        try:
            if not existed:
                with contextlib.suppress(FileNotFoundError):
                    path.unlink()
                continue
            if path.exists():
                with path.open("rb+") as handle:
                    handle.truncate(size)
        except OSError as exc:
            _LOGGER.warning("drop rollback truncate failed for %s: %s", path, exc)


def _allow_private_fetch() -> bool:
    import os

    return os.environ.get("AIWIKI_ALLOW_PRIVATE_FETCH", "").strip().lower() in {"1", "true", "yes"}


def _collect_binary_to_tmp(root: Path, source: str, *, prefix: str, preferred_slug: str) -> dict[str, Any]:
    del preferred_slug
    tmp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        parsed = parse.urlparse(source)
        source_scheme = parsed.scheme.lower()
        if source_scheme in {"http", "https"}:
            payload, final_url = safe_fetch(
                source,
                max_bytes=_ASSET_MAX_BYTES,
                timeout=60,
                allow_private=_allow_private_fetch(),
            )
            suffix = _suffix_from_source(final_url, "")
            tmp_path = tmp_dir / f"asset{suffix}"
            tmp_path.write_bytes(payload)
            original_path = final_url
        else:
            if source_scheme == "file":
                source_path = safe_resolve_within(Path(parse.unquote(parsed.path)), root)
            else:
                source_path = Path(source).expanduser().resolve()
            if not source_path.is_file():
                raise FileNotFoundError(f"Source not found: {source}")
            suffix = source_path.suffix.lower() or ".bin"
            tmp_path = tmp_dir / f"asset{suffix}"
            shutil.copyfile(source_path, tmp_path)
            original_path = str(source_path)
        return {
            "tmp_dir": tmp_dir,
            "tmp_path": tmp_path,
            "original_path": original_path,
            "suffix": tmp_path.suffix.lower() or ".bin",
        }
    except Exception:
        _cleanup_tmp_dir(tmp_dir)
        raise


def _unique_path(directory: Path, stem: str, suffix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}{suffix}"
    index = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{index}{suffix}"
        index += 1
    return candidate


def _write_text(path: Path, content: str) -> None:
    atomic_write_text(path, content.rstrip() + "\n", fsync=True)


def _write_bytes(path: Path, content: bytes) -> None:
    atomic_write_bytes(path, content, fsync=True)


def _label_from_url(url: str) -> str:
    parsed = parse.urlparse(url)
    label = Path(parsed.path).stem or parsed.netloc or url
    return label.replace("-", " ").replace("_", " ").strip() or "web page"


def _note_title(text: str, *, fallback: str) -> str:
    heading = first_markdown_heading(text)
    if heading:
        return heading
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:80]
    return fallback


def _normalize_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


def _suffix_from_source(source: str, content_type: str) -> str:
    suffix = Path(parse.urlparse(source).path).suffix.lower()
    if suffix:
        return suffix
    mapping = {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "text/html": ".html",
        "text/plain": ".txt",
    }
    return mapping.get(content_type, ".bin")


# ``timestamped_stem`` is re-exported here so handler modules can import it from
# a single shared location (it originates in ``drop_helpers``).
__all__ = [
    "MAX_TEXT_CHARS",
    "SensitiveContentError",
    "_ASSET_MAX_BYTES",
    "_HTML_MAX_BYTES",
    "_LOCAL_IMAGE_MAX_BYTES",
    "_LOCAL_PDF_MAX_BYTES",
    "_SUPPORTED_IMAGE_MIME_TYPES",
    "_allow_private_fetch",
    "_append_manifest_entry",
    "_append_raw_added_history",
    "_append_run_event",
    "_assert_file_size",
    "_assert_pdf_asset",
    "_assert_supported_image_mime",
    "_cleanup_tmp_dir",
    "_collect_binary_to_tmp",
    "_label_from_url",
    "_note_title",
    "_normalize_text",
    "_rollback_created_paths",
    "_snapshot_append_files",
    "_suffix_from_source",
    "_truncate_append_files",
    "_truncate_text",
    "_unique_path",
    "_write_bytes",
    "_write_text",
    "timestamped_stem",
]
