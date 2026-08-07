"""PDF drop handler (local + remote PDF ingestion with pdftotext extraction)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ..drop_helpers import timestamped_stem
from ..protocol.scaffold import ensure_layout
from ..utils.io import atomic_copy_file, runtime_write_lock
from ..utils.path import relative_path
from .common import (
    _LOCAL_PDF_MAX_BYTES,
    _append_manifest_entry,
    _append_raw_added_history,
    _assert_file_size,
    _assert_pdf_asset,
    _cleanup_tmp_dir,
    _collect_binary_to_tmp,
    _normalize_text,
    _rollback_created_paths,
    _snapshot_append_files,
    _truncate_append_files,
    _truncate_text,
    _unique_path,
)

PDF_EXTRACT_TIMEOUT_SECONDS = 60


def drop_pdf(root: Path, source: str, title: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    collection = _collect_pdf(root, source, title)
    try:
        _validate_pdf(collection)
        with runtime_write_lock(root):
            return _materialize_pdf(root, source, title, collection)
    finally:
        _cleanup_tmp_dir(collection["tmp_dir"])


def _collect_pdf(root: Path, source: str, title: str | None = None) -> dict[str, Any]:
    return _collect_binary_to_tmp(root, source, prefix="aiwiki-drop-pdf-", preferred_slug=title or Path(source).stem)


def _validate_pdf(collection: dict[str, Any]) -> None:
    tmp_path = collection["tmp_path"]
    if tmp_path.suffix.lower() != ".pdf":
        renamed = tmp_path.with_suffix(".pdf")
        tmp_path.rename(renamed)
        collection["tmp_path"] = renamed
        tmp_path = renamed
    _assert_file_size(tmp_path, _LOCAL_PDF_MAX_BYTES, "PDF asset")
    _assert_pdf_asset(tmp_path)


def _materialize_pdf(root: Path, source: str, title: str | None, collection: dict[str, Any]) -> dict[str, Any]:
    del source
    tmp_path = collection["tmp_path"]
    original_path = collection["original_path"]
    display_title = title or Path(original_path).stem or tmp_path.stem
    asset_path = _unique_path(root / "raw" / "assets", timestamped_stem(display_title), ".pdf")
    created_paths: list[Path] = []
    append_file_sizes = _snapshot_append_files(root)
    try:
        atomic_copy_file(tmp_path, asset_path, fsync=True)
        created_paths.append(asset_path)
        entry = _append_manifest_entry(
            root,
            stored_path=asset_path,
            original_path=original_path,
            source_type="pdf-drop",
            title=display_title,
        )
        _append_raw_added_history(
            root,
            material="pdf",
            stored_path=asset_path,
            original_path=original_path,
            source_type="pdf-drop",
            title=display_title,
            entry_id=entry["id"],
        )
    except Exception:
        _rollback_created_paths(created_paths)
        _truncate_append_files(append_file_sizes)
        raise
    return {
        "material": "pdf",
        "asset_path": relative_path(root, asset_path),
        "stored_path": relative_path(root, asset_path),
        "original_path": original_path,
        "title": display_title,
    }


def _extract_pdf_text(path: Path) -> str:
    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
            timeout=PDF_EXTRACT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"pdftotext timed out after {PDF_EXTRACT_TIMEOUT_SECONDS}s") from exc
    if completed.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {completed.stderr.strip()}")
    return _truncate_text(_normalize_text(completed.stdout), 120000)
