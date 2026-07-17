"""Direct raw-material entry points for aiwiki."""

from __future__ import annotations

import contextlib
import hashlib
import html
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib import parse

from .app_protocol import ensure_layout, save_manifest
from .app_state import DEFAULT_PROTOCOL, append_runtime_history, load_manifest, manifest_path, runtime_history_path
from .app_utils import (
    FetchPolicyError,
    _validate_safe_url,
    atomic_copy_file,
    atomic_write_bytes,
    atomic_write_text,
    detect_kind,
    first_markdown_heading,
    next_identifier,
    relative_path,
    runtime_write_lock,
    safe_fetch,
    safe_resolve_within,
    sha256_file,
    slugify,
    utc_now,
)
from .config import LLMConfig, _backend_supports_image_analysis
from .drop_helpers import strip_leading_title_echo, timestamped_stem
from .llm import LLMError, create_backend_client
from .render.paths import append_wiki_log

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - optional dependency
    BeautifulSoup = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional dependency
    sync_playwright = None


USER_AGENT = "aiwiki/0.1 (+https://local)"
MAX_TEXT_CHARS = 120000
MAX_URL_IMAGES = 6
SENSITIVE_SCAN_CONTEXT_CHARS = 60000
_HTML_MAX_BYTES = 5 * 1024 * 1024
_ASSET_MAX_BYTES = 50 * 1024 * 1024
# Local PDF ingestion reuses the remote asset cap; images get a tighter OCR/vision cap.
_LOCAL_PDF_MAX_BYTES = _ASSET_MAX_BYTES
_LOCAL_IMAGE_MAX_BYTES = 25 * 1024 * 1024
_SUPPORTED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}

_LOGGER = logging.getLogger(__name__)

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


def _normalize_repo_max_files(max_files: int) -> int:
    if not isinstance(max_files, int) or max_files < 1 or max_files > 1000:
        raise ValueError(f"max_files must be 1..1000, got {max_files}")
    return max_files


def _append_run_event(root: Path, event: dict[str, Any]) -> None:
    from .runner.receipts import _append_log

    _append_log(root, event)
BROWSER_RENDER_TIMEOUT_SECONDS = 45
BROWSER_VIRTUAL_TIME_BUDGET_MS = 8000
ALLOW_BROWSER_NO_SANDBOX_ENV = "AIWIKI_ALLOW_BROWSER_NO_SANDBOX"
PDF_EXTRACT_TIMEOUT_SECONDS = 60
MIME_DETECT_TIMEOUT_SECONDS = 5
IMAGE_OCR_TIMEOUT_SECONDS = 60
GIT_METADATA_TIMEOUT_SECONDS = 15
TEXT_FILE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".go",
    ".java",
    ".js",
    ".json",
    ".md",
    ".py",
    ".rb",
    ".rs",
    ".rst",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
REPO_PRIORITY_FILES = (
    "README.md",
    "README.rst",
    "README.txt",
    "README",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
    "Dockerfile",
    "Makefile",
    "setup.py",
)


def drop_url(root: Path, url: str, title: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    collection = _collect_url(root, url)
    _validate_url_collection(collection)
    with runtime_write_lock(root):
        result = _materialize_url(root, url, title, collection)
        for event in collection.get("skip_events", []):
            _append_run_event(root, event)
    return result


def _collect_url(root: Path, url: str) -> dict[str, Any]:
    fetched = _fetch_url(url, root=root)
    inline_images: list[dict[str, Any]] = []
    skip_events: list[dict[str, Any]] = []
    for image_url in fetched["image_urls"][:MAX_URL_IMAGES]:
        try:
            payload, final_url = _collect_asset_bytes(root, image_url, max_bytes=_ASSET_MAX_BYTES)
        except Exception as exc:
            skip_events.append(
                {
                    "event": "url_image_download_skipped",
                    "url": image_url,
                    "reason": str(exc),
                    "error_type": type(exc).__name__,
                }
            )
            continue
        inline_images.append(
            {
                "bytes": payload,
                "suffix": _suffix_from_source(final_url, ""),
                "source": final_url,
            }
        )
    return {"fetched": fetched, "inline_images": inline_images, "skip_events": skip_events}


def _validate_url_collection(collection: dict[str, Any]) -> None:
    del collection


def _prior_url_drop_hints(root: Path, *, original_url: str, final_url: str) -> list[dict[str, str]]:
    """List earlier url-drop manifest entries for the same original/final URL (non-blocking)."""
    targets = {
        str(original_url or "").strip(),
        str(final_url or "").strip(),
    }
    targets.discard("")
    if not targets:
        return []
    hints: list[dict[str, str]] = []
    for entry in load_manifest(root).get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("source_type") or "") != "url-drop":
            continue
        meta = entry.get("ingest_metadata") if isinstance(entry.get("ingest_metadata"), dict) else {}
        prior_urls = {
            str(meta.get("original_url") or "").strip(),
            str(meta.get("final_url") or "").strip(),
            str(entry.get("original_path") or "").strip(),
        }
        prior_urls.discard("")
        if not (targets & prior_urls):
            continue
        stored = str(entry.get("stored_path") or "").strip()
        if not stored:
            continue
        hints.append(
            {
                "entry_id": str(entry.get("id") or "").strip(),
                "stored_path": stored,
                "title": str(entry.get("title") or "").strip(),
            }
        )
    return hints


def _materialize_url(root: Path, url: str, title: str | None, collection: dict[str, Any]) -> dict[str, Any]:
    fetched = collection["fetched"]
    display_title = title or fetched["title"] or _label_from_url(fetched["final_url"])
    created_paths: list[Path] = []
    asset_paths: list[str] = []
    asset_dir = root / "raw" / "assets"
    stem = timestamped_stem(display_title)
    note_path = _unique_path(root / "raw" / "inbox", stem, ".md")
    prior_url_drops = _prior_url_drop_hints(
        root,
        original_url=url,
        final_url=str(fetched.get("final_url") or ""),
    )
    append_file_sizes = _snapshot_append_files(root)
    try:
        for index, image in enumerate(collection["inline_images"], start=1):
            asset_path = _unique_path(
                asset_dir,
                timestamped_stem(f"{display_title}-image-{index}"),
                image["suffix"],
            )
            _write_bytes(asset_path, image["bytes"])
            created_paths.append(asset_path)
            asset_paths.append(relative_path(root, asset_path))
        ingest_metadata = {
            "original_url": url,
            "final_url": fetched["final_url"],
            "content_type": fetched["content_type"],
            "http_status": fetched["status"],
            "browser_backend": fetched["browser_backend"] or "",
            "extraction_mode": fetched["extraction_mode"],
            "description": fetched["description"] or "",
            "asset_files": asset_paths,
            "fetched_at": utc_now(),
        }
        markdown = _write_url_note_body(display_title, fetched, asset_paths)
        _write_text(note_path, markdown)
        created_paths.append(note_path)
        entry = _append_manifest_entry(
            root,
            stored_path=note_path,
            original_path=url,
            source_type="url-drop",
            title=display_title,
            ingest_metadata=ingest_metadata,
        )
        append_wiki_log(
            root,
            "ingest",
            display_title,
            [
                "source_type: `url-drop`",
                f"original_url: `{url}`",
                f"stored_note: `{relative_path(root, note_path)}`",
                f"asset_files: `{len(asset_paths)}`",
            ],
        )
        _append_raw_added_history(
            root,
            material="url",
            stored_path=note_path,
            original_path=url,
            source_type="url-drop",
            title=display_title,
            entry_id=entry["id"],
            ingest_metadata=ingest_metadata,
        )
    except Exception:
        _rollback_created_paths(created_paths)
        _truncate_append_files(append_file_sizes)
        raise
    return {
        "material": "url",
        "note_path": relative_path(root, note_path),
        "original_url": url,
        "final_url": fetched["final_url"],
        "asset_paths": asset_paths,
        "title": display_title,
        "prior_url_drop_count": len(prior_url_drops),
        **(
            {
                "prior_url_drops": prior_url_drops,
                "duplicate_url_hint": (
                    f"URL already present in raw ({len(prior_url_drops)} earlier drop(s)); "
                    "new note created without merging."
                ),
            }
            if prior_url_drops
            else {}
        ),
    }


def _write_url_note_body(display_title: str, fetched: dict[str, Any], asset_paths: list[str]) -> str:
    """Write fetched page text to raw/inbox without frontmatter or capture-metadata sections."""
    lines = [f"# {display_title}", ""]
    body = strip_leading_title_echo(str(fetched.get("text") or ""), display_title)
    if body:
        lines.append(body)
        lines.append("")
    elif fetched.get("description"):
        lines.append(str(fetched["description"]).strip())
        lines.append("")
    else:
        lines.append("No text content extracted from the page.")
        lines.append("")
    if asset_paths:
        lines.append("## Assets")
        lines.extend(f"- `{path}`" for path in asset_paths)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _write_repo_note_body(display_title: str, snapshot: dict[str, Any]) -> str:
    """Write repo snapshot text to raw/inbox without frontmatter or capture-metadata sections."""
    lines = [f"# {display_title}", ""]
    readme = strip_leading_title_echo(str(snapshot.get("readme") or ""), display_title)
    if readme:
        lines.append(readme)
        lines.append("")
    tree_lines = snapshot.get("tree") or []
    if tree_lines:
        lines.append("## Repository Tree")
        lines.extend(str(item) for item in tree_lines)
        lines.append("")
    for item in snapshot.get("files") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        content = str(item.get("content") or "").strip()
        if not path:
            continue
        lines.append(f"## {path}")
        if content:
            lines.append(content)
        lines.append("")
    if len(lines) <= 2:
        lines.append("No repository text captured.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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
        append_wiki_log(
            root,
            "ingest",
            display_title,
            [
                "source_type: `pdf-drop`",
                f"asset_path: `{relative_path(root, asset_path)}`",
            ],
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


def drop_image(
    root: Path,
    source: str,
    title: str | None = None,
    enable_vision: bool = True,
    client: Any | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    collection = _collect_image(root, source, title, enable_vision, client)
    try:
        _validate_image(collection)
        with runtime_write_lock(root):
            return _materialize_image(root, source, title, collection)
    finally:
        _cleanup_tmp_dir(collection["tmp_dir"])


def _collect_image(
    root: Path,
    source: str,
    title: str | None = None,
    enable_vision: bool = True,
    client: Any | None = None,
) -> dict[str, Any]:
    collection = _collect_binary_to_tmp(root, source, prefix="aiwiki-drop-image-", preferred_slug=title or Path(source).stem)
    try:
        tmp_path = collection["tmp_path"]
        mime = _detect_mime_type(tmp_path)
        _assert_supported_image_mime(mime)
        _assert_file_size(tmp_path, _LOCAL_IMAGE_MAX_BYTES, "image asset")
        width, height = _image_dimensions(tmp_path)
        ocr_text = _extract_image_text(tmp_path)
        vision_result = _analyze_image_asset(
            root,
            tmp_path,
            mime=mime,
            width=width,
            height=height,
            ocr_text=ocr_text,
            client=client,
            enable_vision=enable_vision,
        )
    except Exception:
        _cleanup_tmp_dir(collection["tmp_dir"])
        raise
    collection.update(
        {
            "mime": mime,
            "width": width,
            "height": height,
            "ocr_text": ocr_text,
            "vision_result": vision_result,
        }
    )
    return collection


def _validate_image(collection: dict[str, Any]) -> None:
    _assert_supported_image_mime(collection["mime"])
    _assert_file_size(collection["tmp_path"], _LOCAL_IMAGE_MAX_BYTES, "image asset")


def _materialize_image(root: Path, source: str, title: str | None, collection: dict[str, Any]) -> dict[str, Any]:
    del source
    tmp_path = collection["tmp_path"]
    original_path = collection["original_path"]
    mime = collection["mime"]
    width = collection["width"]
    height = collection["height"]
    ocr_text = collection["ocr_text"]
    vision_result = collection["vision_result"]
    visual_analysis = vision_result["analysis"]
    vision_backend = vision_result["backend"]
    vision_status = vision_result["status"]
    display_title = title or Path(original_path).stem or tmp_path.stem
    asset_path = _unique_path(root / "raw" / "assets", timestamped_stem(display_title), tmp_path.suffix.lower() or ".bin")
    created_paths: list[Path] = []
    append_file_sizes = _snapshot_append_files(root)
    try:
        atomic_copy_file(tmp_path, asset_path, fsync=True)
        created_paths.append(asset_path)
        entry = _append_manifest_entry(
            root,
            stored_path=asset_path,
            original_path=original_path,
            source_type="image-drop",
            title=display_title,
        )
        append_wiki_log(
            root,
            "ingest",
            display_title,
            [
                "source_type: `image-drop`",
                f"asset_path: `{relative_path(root, asset_path)}`",
                f"vision_status: `{vision_status}`",
            ],
        )
        _append_raw_added_history(
            root,
            material="image",
            stored_path=asset_path,
            original_path=original_path,
            source_type="image-drop",
            title=display_title,
            entry_id=entry["id"],
        )
    except Exception:
        _rollback_created_paths(created_paths)
        _truncate_append_files(append_file_sizes)
        raise
    return {
        "material": "image",
        "asset_path": relative_path(root, asset_path),
        "stored_path": relative_path(root, asset_path),
        "original_path": original_path,
        "mime_type": mime,
        "dimensions": {"width": width, "height": height},
        "ocr_text_present": bool(ocr_text),
        "visual_analysis_present": bool(visual_analysis),
        "vision_backend": vision_backend,
        "vision_status": vision_status,
        "title": display_title,
    }


def drop_repo(root: Path, source: str, title: str | None = None, max_files: int = 200) -> dict[str, Any]:
    ensure_layout(root)
    collection = _collect_repo(root, source, max_files)
    _validate_repo(collection)
    with runtime_write_lock(root):
        return _materialize_repo(root, source, title, collection)


def _collect_repo(root: Path, source: str, max_files: int = 200) -> dict[str, Any]:
    max_files = _normalize_repo_max_files(max_files)
    cleanup_path: Path | None = None
    original_path = source
    try:
        if _is_remote_repo_source(source):
            if os.environ.get("AIWIKI_ALLOW_REMOTE_REPO_DROP") != "1":
                raise ValueError("remote repo drop disabled; set AIWIKI_ALLOW_REMOTE_REPO_DROP=1 to enable")
            cleanup_path = Path(tempfile.mkdtemp(prefix="aiwiki-repo-"))
            repo_path = cleanup_path / "repo"
            _clone_repo(source, repo_path)
        else:
            repo_path = safe_resolve_within(Path(source).expanduser().resolve(), root)
            if not repo_path.is_dir():
                raise FileNotFoundError(f"Repository path not found: {source}")
        snapshot = _repo_snapshot(repo_path, max_files=max_files)
    finally:
        if cleanup_path is not None:
            _cleanup_tmp_dir(cleanup_path)
    return {"snapshot": snapshot, "original_path": original_path}


def _validate_repo(collection: dict[str, Any]) -> None:
    del collection


def _materialize_repo(root: Path, source: str, title: str | None, collection: dict[str, Any]) -> dict[str, Any]:
    del source
    snapshot = collection["snapshot"]
    original_path = collection["original_path"]
    display_title = title or snapshot["name"]
    stem = timestamped_stem(display_title)
    note_path = _unique_path(root / "raw" / "inbox", stem, ".md")
    ingest_metadata = {
        "repo_source": original_path,
        "snapshot_at": utc_now(),
        "commit": snapshot["commit"] or "",
        "origin": snapshot["origin"] or "",
    }
    markdown = _write_repo_note_body(display_title, snapshot)
    created_paths: list[Path] = []
    append_file_sizes = _snapshot_append_files(root)
    try:
        _write_text(note_path, markdown)
        created_paths.append(note_path)
        entry = _append_manifest_entry(
            root,
            stored_path=note_path,
            original_path=original_path,
            source_type="repo-drop",
            title=display_title,
            ingest_metadata=ingest_metadata,
        )
        append_wiki_log(
            root,
            "ingest",
            display_title,
            [
                "source_type: `repo-drop`",
                f"stored_note: `{relative_path(root, note_path)}`",
                f"source: `{original_path}`",
            ],
        )
        _append_raw_added_history(
            root,
            material="repo",
            stored_path=note_path,
            original_path=original_path,
            source_type="repo-drop",
            title=display_title,
            entry_id=entry["id"],
            ingest_metadata=ingest_metadata,
        )
    except Exception:
        _rollback_created_paths(created_paths)
        _truncate_append_files(append_file_sizes)
        raise
    return {
        "material": "repo",
        "note_path": relative_path(root, note_path),
        "original_path": original_path,
        "title": display_title,
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
    append_wiki_log(
        root,
        "ingest",
        display_title,
        [
            "source_type: `note-drop`",
            f"note_kind: `{note_kind}`",
            f"stored_note: `{relative_path(root, note_path)}`",
        ],
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
    cleaned = cleaned.strip("`\"")
    return cleaned.lower()


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
        "occurred_at": utc_now(),
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
            updated_at = utc_now()
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
    seed = f"source-{slug}" if slug and slug != "item" else f"source-{hashlib.sha256(relative.encode()).hexdigest()[:12]}"
    entry_id = next_identifier(existing_ids, seed)
    imported_at = utc_now()
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


def _fetch_url(url: str, *, root: Path) -> dict[str, Any]:
    fetched = _http_fetch_url(url, root=root)
    final_url = fetched["final_url"]
    content_type = fetched["content_type"]
    status = fetched["status"]
    raw_text = fetched["text"]
    browser_backend = ""
    browser_html = ""
    if _should_try_browser_render(final_url, content_type):
        try:
            _validate_safe_url(final_url, allow_private=_allow_private_fetch())
            rendered = _render_url_in_browser(final_url)
        except (FetchPolicyError, RuntimeError):
            rendered = {"html": "", "backend": ""}
        browser_html = rendered["html"]
        browser_backend = rendered["backend"]

    html_text = browser_html or raw_text
    if html_text and ("html" in content_type or browser_html):
        extracted = _extract_html_document(html_text, final_url)
        title = extracted["title"]
        description = extracted["description"]
        body = extracted["text"]
        image_urls = extracted["image_urls"]
        if browser_html:
            extraction_mode = f"chromium-rendered+{extracted['mode']}"
        else:
            extraction_mode = extracted["mode"]
        if not content_type:
            content_type = "text/html"
        if not status:
            status = "browser-rendered"
    elif raw_text:
        title = _label_from_url(final_url)
        description = ""
        body = raw_text
        image_urls = []
        extraction_mode = "plain-text"
    else:
        details = fetched["error"] or "unknown fetch failure"
        raise RuntimeError(f"Failed to fetch URL `{url}`: {details}")
    body = _truncate_text(_normalize_text(body), MAX_TEXT_CHARS)
    return {
        "final_url": final_url,
        "content_type": content_type,
        "status": str(status or "unknown"),
        "title": title,
        "description": _truncate_text(_normalize_text(description), 2000),
        "text": body,
        "image_urls": image_urls,
        "browser_backend": browser_backend if browser_html else "",
        "extraction_mode": extraction_mode,
    }


def _http_fetch_url(url: str, *, root: Path) -> dict[str, str]:
    try:
        parsed = parse.urlparse(url)
        if parsed.scheme == "file":
            local_path = safe_resolve_within(Path(parse.unquote(parsed.path)), root)
            payload = local_path.read_bytes()
            if len(payload) > _HTML_MAX_BYTES:
                raise FetchPolicyError(f"response exceeds max_bytes={_HTML_MAX_BYTES}")
            final_url = url
        else:
            payload, final_url = safe_fetch(
                url,
                max_bytes=_HTML_MAX_BYTES,
                timeout=30,
                allow_private=_allow_private_fetch(),
            )
        content_type = "text/html"
        charset = "utf-8"
        status = 200
        text = payload.decode(charset, errors="replace")
        return {
            "final_url": final_url,
            "content_type": content_type,
            "status": str(status),
            "text": text,
            "error": "",
        }
    except Exception as exc:
        return {
            "final_url": url,
            "content_type": "",
            "status": "",
            "text": "",
            "error": str(exc),
        }


def _should_try_browser_render(url: str, content_type: str) -> bool:
    parsed = parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return not content_type or "html" in content_type


def _browser_command() -> str:
    for candidate in ("chromium-browser", "chromium", "google-chrome", "google-chrome-stable"):
        path = shutil.which(candidate)
        if path:
            return path
    return ""


def _render_url_in_browser(url: str) -> dict[str, str]:
    if sync_playwright is not None:
        try:
            html_text = _render_url_with_playwright(url)
        except RuntimeError:
            html_text = ""
        if html_text:
            return {"html": html_text, "backend": "playwright-chromium"}

    browser_command = _browser_command()
    if not browser_command:
        return {"html": "", "backend": ""}

    html_text = _render_url_with_browser_cli(url, browser_command)
    if html_text:
        return {"html": html_text, "backend": Path(browser_command).name}
    return {"html": "", "backend": ""}


def _render_url_with_playwright(url: str) -> str:
    if sync_playwright is None:
        return ""
    allow_private = _allow_private_fetch()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=USER_AGENT)

                def _guard(route, request):  # type: ignore[no-untyped-def]
                    try:
                        _validate_safe_url(request.url, allow_private=allow_private)
                    except FetchPolicyError:
                        route.abort()
                        return
                    route.continue_()

                page.route("**/*", _guard)
                page.goto(url, wait_until="networkidle", timeout=BROWSER_RENDER_TIMEOUT_SECONDS * 1000)
                return page.content()
            finally:
                browser.close()
    except Exception as exc:
        raise RuntimeError(f"Playwright render failed: {exc}") from exc


def _render_url_with_browser_cli(url: str, browser_command: str) -> str:
    user_data_dir = Path(tempfile.mkdtemp(prefix="aiwiki-browser-"))
    command = [
        browser_command,
        "--headless",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        f"--virtual-time-budget={BROWSER_VIRTUAL_TIME_BUDGET_MS}",
        f"--user-data-dir={user_data_dir}",
        f"--user-agent={USER_AGENT}",
        "--dump-dom",
        url,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=BROWSER_RENDER_TIMEOUT_SECONDS,
            check=False,
        )
        if completed.returncode != 0:
            details = completed.stderr.strip() or completed.stdout.strip()
            if "--no-sandbox" not in command and "sandbox" in details.lower():
                if not _allow_browser_no_sandbox():
                    raise RuntimeError(
                        f"{Path(browser_command).name} render failed because browser sandboxing is unavailable. "
                        f"Set {ALLOW_BROWSER_NO_SANDBOX_ENV}=1 to explicitly allow Chromium --no-sandbox fallback."
                    )
                return _render_url_with_browser_cli_no_sandbox(url, browser_command, user_data_dir)
            raise RuntimeError(f"{Path(browser_command).name} render failed: {details}")
        return completed.stdout
    finally:
        shutil.rmtree(user_data_dir, ignore_errors=True)


def _render_url_with_browser_cli_no_sandbox(url: str, browser_command: str, user_data_dir: Path) -> str:
    command = [
        browser_command,
        "--headless",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        f"--virtual-time-budget={BROWSER_VIRTUAL_TIME_BUDGET_MS}",
        f"--user-data-dir={user_data_dir}",
        f"--user-agent={USER_AGENT}",
        "--dump-dom",
        url,
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=BROWSER_RENDER_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{Path(browser_command).name} render failed: {details}")
    return completed.stdout


def _allow_browser_no_sandbox() -> bool:
    return os.environ.get(ALLOW_BROWSER_NO_SANDBOX_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _extract_html_title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    return _normalize_text(html.unescape(match.group(1))) if match else ""


def _extract_html_description(text: str) -> str:
    patterns = [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return _normalize_text(html.unescape(match.group(1)))
    return ""


def _extract_html_text(text: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style|noscript|svg|template).*?>.*?</\1>", " ", text)
    cleaned = re.sub(r"(?i)</(p|div|section|article|main|li|ul|ol|h1|h2|h3|h4|h5|h6|br|tr)>", "\n", cleaned)
    cleaned = re.sub(r"(?i)<li[^>]*>", "- ", cleaned)
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    return html.unescape(cleaned)


def _extract_html_document(text: str, base_url: str) -> dict[str, Any]:
    if BeautifulSoup is None:
        return {
            "title": _extract_html_title(text),
            "description": _extract_html_description(text),
            "text": _extract_html_text(text),
            "image_urls": _extract_image_urls_fallback(text, base_url),
            "mode": "regex-fallback",
        }

    soup = BeautifulSoup(text, "html.parser")
    title = _soup_title(soup) or _extract_html_title(text)
    description = _soup_description(soup) or _extract_html_description(text)
    main_node = _pick_main_node(soup)
    _strip_noise(main_node)
    extracted_text = _extract_text_from_node(main_node) or _extract_html_text(text)
    image_urls = _extract_image_urls(main_node, soup, base_url)
    return {
        "title": title,
        "description": description,
        "text": extracted_text,
        "image_urls": image_urls,
        "mode": "bs4-main-content",
    }


def _soup_title(soup: Any) -> str:
    for key, value in (
        ("property", "og:title"),
        ("name", "twitter:title"),
    ):
        tag = soup.find("meta", attrs={key: value})
        if tag and tag.get("content"):
            return _normalize_text(tag["content"])
    if soup.title and soup.title.string:
        return _normalize_text(soup.title.string)
    return ""


def _soup_description(soup: Any) -> str:
    for key, value in (
        ("name", "description"),
        ("property", "og:description"),
        ("name", "twitter:description"),
    ):
        tag = soup.find("meta", attrs={key: value})
        if tag and tag.get("content"):
            return _normalize_text(tag["content"])
    return ""


def _pick_main_node(soup: Any) -> Any:
    preferred = [
        "article",
        "main",
        '[role="main"]',
        ".post-content",
        ".entry-content",
        ".article-content",
        ".article-body",
        ".post-body",
        ".content",
    ]
    candidates = []
    for selector in preferred:
        candidates.extend(soup.select(selector))
    if not candidates and soup.body:
        candidates = list(soup.body.find_all(["section", "div"], recursive=True))
    if soup.body:
        candidates.append(soup.body)
    if not candidates:
        return soup
    return max(candidates, key=_score_node)


def _score_node(node: Any) -> int:
    text = _normalize_text(node.get_text("\n", strip=True))
    paragraphs = len(node.find_all("p")) if hasattr(node, "find_all") else 0
    headings = len(node.find_all(re.compile(r"^h[1-6]$"))) if hasattr(node, "find_all") else 0
    lists = len(node.find_all("li")) if hasattr(node, "find_all") else 0
    return len(text) + (paragraphs * 200) + (headings * 120) + (lists * 40)


def _strip_noise(node: Any) -> None:
    for selector in (
        "script",
        "style",
        "noscript",
        "svg",
        "template",
        "nav",
        "footer",
        "header",
        "aside",
        "form",
        "button",
        "input",
    ):
        for child in node.select(selector):
            child.decompose()


def _extract_text_from_node(node: Any) -> str:
    block_names = {"p", "li", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}
    lines: list[str] = []
    for element in node.find_all(list(block_names)):
        if _has_block_ancestor(element, node, block_names):
            continue
        text = _normalize_text(element.get_text(" ", strip=True))
        if not text:
            continue
        if element.name == "li":
            lines.append(f"- {text}")
        elif element.name and re.fullmatch(r"h[1-6]", element.name):
            lines.append(f"{'#' * int(element.name[1])} {text}")
        else:
            lines.append(text)
    if not lines:
        return _normalize_text(node.get_text("\n", strip=True))
    return _normalize_text("\n\n".join(lines))


def _has_block_ancestor(element: Any, root: Any, block_names: set[str]) -> bool:
    current = element.parent
    while current is not None and current is not root:
        if getattr(current, "name", None) in block_names:
            return True
        current = current.parent
    return False


def _extract_image_urls(node: Any, soup: Any, base_url: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for target in (node, soup):
        for image in target.find_all("img"):
            source = _best_image_source(image)
            resolved = _resolve_asset_url(base_url, source)
            if not resolved or resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(resolved)
    for meta in (
        soup.find("meta", attrs={"property": "og:image"}),
        soup.find("meta", attrs={"name": "twitter:image"}),
    ):
        if not meta or not meta.get("content"):
            continue
        resolved = _resolve_asset_url(base_url, meta["content"])
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        candidates.append(resolved)
    return candidates[:MAX_URL_IMAGES]


def _extract_image_urls_fallback(text: str, base_url: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    patterns = [
        r'<img[^>]+src=["\'](.*?)["\']',
        r'<img[^>]+data-src=["\'](.*?)["\']',
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](.*?)["\']',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            resolved = _resolve_asset_url(base_url, html.unescape(match.group(1)))
            if not resolved or resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(resolved)
            if len(candidates) >= MAX_URL_IMAGES:
                return candidates
    return candidates


def _best_image_source(tag: Any) -> str:
    for attribute in ("src", "data-src", "data-original"):
        value = tag.get(attribute)
        if value:
            return value
    srcset = tag.get("srcset")
    if srcset:
        first = srcset.split(",")[0].strip().split(" ")[0]
        if first:
            return first
    return ""


def _resolve_asset_url(base_url: str, candidate: str = "", *, root: Path | None = None) -> str:
    if not candidate:
        candidate = base_url
    if candidate.startswith("data:"):
        return ""
    resolved = parse.urljoin(base_url, candidate.strip())
    parsed = parse.urlparse(resolved)
    if parsed.scheme in {"http", "https"}:
        return resolved
    if parsed.scheme == "file":
        base_parsed = parse.urlparse(base_url)
        if root is None and base_parsed.scheme != "file":
            raise FetchPolicyError("file:// asset URL requires file:// base URL")
        workspace_root = root or Path(parse.unquote(base_parsed.path)).parent
        return safe_resolve_within(Path(parse.unquote(parsed.path)), workspace_root).as_uri()
    return ""


def _allow_private_fetch() -> bool:
    return os.environ.get("AIWIKI_ALLOW_PRIVATE_FETCH", "").strip().lower() in {"1", "true", "yes"}


def _collect_asset_bytes(root: Path, source: str, *, max_bytes: int) -> tuple[bytes, str]:
    parsed = parse.urlparse(source)
    if parsed.scheme == "file":
        source_path = safe_resolve_within(Path(parse.unquote(parsed.path)), root)
        if not source_path.is_file():
            raise FileNotFoundError(f"Source not found: {source}")
        if source_path.stat().st_size > max_bytes:
            raise ValueError(f"asset exceeds size limit: {source_path.stat().st_size} > {max_bytes} bytes")
        return source_path.read_bytes(), str(source_path)
    return safe_fetch(source, max_bytes=max_bytes, timeout=60, allow_private=_allow_private_fetch())


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
        return {"tmp_dir": tmp_dir, "tmp_path": tmp_path, "original_path": original_path, "suffix": tmp_path.suffix.lower() or ".bin"}
    except Exception:
        _cleanup_tmp_dir(tmp_dir)
        raise


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
        raise RuntimeError(
            f"pdftotext timed out after {PDF_EXTRACT_TIMEOUT_SECONDS}s"
        ) from exc
    if completed.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {completed.stderr.strip()}")
    return _truncate_text(_normalize_text(completed.stdout), MAX_TEXT_CHARS)


def _detect_mime_type(path: Path) -> str:
    try:
        completed = subprocess.run(
            ["file", "--brief", "--mime-type", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=MIME_DETECT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return "application/octet-stream"
    mime = completed.stdout.strip()
    return mime or "application/octet-stream"


def _image_dimensions(path: Path) -> tuple[int | None, int | None]:
    with path.open("rb") as handle:
        data = handle.read(32)
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    if data.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(path)
    return None, None


def _jpeg_dimensions(path: Path) -> tuple[int | None, int | None]:
    with path.open("rb") as handle:
        handle.read(2)
        while True:
            marker_prefix = handle.read(1)
            if marker_prefix != b"\xff":
                return None, None
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if marker in {b"\xc0", b"\xc1", b"\xc2", b"\xc3", b"\xc5", b"\xc6", b"\xc7", b"\xc9", b"\xca", b"\xcb"}:
                segment_length = int.from_bytes(handle.read(2), "big")
                handle.read(1)
                height = int.from_bytes(handle.read(2), "big")
                width = int.from_bytes(handle.read(2), "big")
                return width, height
            if marker in {b"\xd8", b"\xd9"}:
                return None, None
            segment_length = int.from_bytes(handle.read(2), "big")
            handle.seek(segment_length - 2, os.SEEK_CUR)


def _extract_image_text(path: Path) -> str:
    if shutil.which("tesseract") is None:
        return ""
    try:
        completed = subprocess.run(
            ["tesseract", str(path), "stdout"],
            capture_output=True,
            text=True,
            check=False,
            timeout=IMAGE_OCR_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return ""
    if completed.returncode != 0:
        return ""
    return _truncate_text(_normalize_text(completed.stdout), 20000)


def _analyze_image_asset(
    root: Path,
    image_path: Path,
    *,
    mime: str,
    width: int | None,
    height: int | None,
    ocr_text: str,
    client: Any | None,
    enable_vision: bool,
) -> dict[str, str]:
    if not enable_vision:
        return {"analysis": "", "backend": "", "status": "disabled"}
    effective_client = client or _maybe_create_image_client(root)
    if effective_client is None or not hasattr(effective_client, "analyze_image"):
        return {"analysis": "", "backend": "", "status": "skipped"}

    system_prompt = (
        "You analyze images for a local-first research wiki. "
        "Return only markdown. "
        "Describe observable content, readable text, layout, chart or diagram structure, and notable signals. "
        "Do not invent details that are not visible in the image."
    )
    try:
        asset_label = relative_path(root, image_path)
    except ValueError:
        asset_label = str(image_path)
    user_prompt = "\n".join(
        [
            "Analyze this image asset for a source note.",
            f"- Asset path: `{asset_label}`",
            f"- MIME type: `{mime}`",
            f"- Dimensions: `{width or 'unknown'}x{height or 'unknown'}`",
            "",
            "Use 4 to 8 markdown bullet points, then finish with `- Confidence: low|medium|high`.",
            "If OCR text is provided, you may use it as supporting evidence but should still focus on what is visually observable.",
            "",
            "OCR excerpt:",
            ocr_text or "(none)",
        ]
    )
    backend_name = _client_backend_name(effective_client)
    try:
        result = effective_client.analyze_image(system_prompt, user_prompt, image_path)
    except (LLMError, RuntimeError, OSError):
        return {"analysis": "", "backend": backend_name, "status": "failed"}
    analysis = _normalize_text(result.text)
    if not analysis:
        return {"analysis": "", "backend": backend_name, "status": "failed"}
    return {"analysis": analysis, "backend": backend_name, "status": "generated"}


def _maybe_create_image_client(root: Path) -> Any | None:
    try:
        config = LLMConfig.from_env()
    except RuntimeError:
        return None
    if not _backend_supports_image_analysis(config.backend, config.model):
        return None
    return create_backend_client(config, root)


def _client_backend_name(client: Any) -> str:
    config = getattr(client, "config", None)
    backend = getattr(config, "backend", "")
    return backend if isinstance(backend, str) else ""


def _looks_like_repo_url(source: str) -> bool:
    lowered = source.lower()
    return lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("git@")


def _is_remote_repo_source(source: str) -> bool:
    lowered = source.lower()
    return _looks_like_repo_url(source) or lowered.startswith("git://")


def _clone_repo(source: str, destination: Path) -> None:
    try:
        completed = subprocess.run(
            ["git", "clone", "--depth", "1", source, str(destination)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise RuntimeError(f"git clone timed out after 60s: {source}") from exc
    if completed.returncode != 0:
        raise RuntimeError(f"git clone failed: {completed.stderr.strip() or completed.stdout.strip()}")


def _repo_snapshot(repo_path: Path, max_files: int) -> dict[str, Any]:
    name = repo_path.name
    commit = _git_output(repo_path, ["rev-parse", "HEAD"])
    origin = _git_output(repo_path, ["config", "--get", "remote.origin.url"])
    tree_entries = _repo_tree(repo_path, max_files=max_files)
    text_files = _repo_key_files(repo_path)
    readme = ""
    excerpts: list[dict[str, str]] = []
    for relative in text_files:
        content = _read_text_file(repo_path / relative)
        if not content:
            continue
        if not readme and relative.lower().startswith("readme"):
            readme = content
            continue
        excerpts.append({"path": relative, "content": content})
    return {
        "name": name,
        "commit": commit,
        "origin": origin,
        "readme": readme,
        "tree": [f"- `{entry}`" for entry in tree_entries],
        "files": excerpts[:8],
    }


def _repo_tree(repo_path: Path, max_files: int) -> list[str]:
    entries: list[str] = []
    for path in sorted(repo_path.rglob("*")):
        if any(part in {".git", "node_modules", ".venv", "__pycache__", "dist", "build"} for part in path.parts):
            continue
        if path.is_symlink():
            continue
        if not path.is_file():
            continue
        safe_path = safe_resolve_within(path, repo_path)
        entries.append(relative_path(repo_path, safe_path))
        if len(entries) >= max_files:
            break
    return entries


# NOTE (R92-INPUT-SAFETY): max_files caps the main file walk in _repo_tree
# but _repo_key_files does its own bounded walk (caps at 12 selected files
# via the early-return in the loop). For a hard total walk bound, see future
# R92-INPUT-SAFETY-WIDE.
def _repo_key_files(repo_path: Path) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for relative in REPO_PRIORITY_FILES:
        candidate = repo_path / relative
        if candidate.is_symlink():
            continue
        if candidate.is_file():
            value = relative_path(repo_path, safe_resolve_within(candidate, repo_path))
            selected.append(value)
            seen.add(value)

    for path in sorted(repo_path.rglob("*")):
        if any(part in {".git", "node_modules", ".venv", "__pycache__", "dist", "build"} for part in path.parts):
            continue
        if path.is_symlink():
            continue
        if not path.is_file():
            continue
        relative = relative_path(repo_path, safe_resolve_within(path, repo_path))
        if relative in seen:
            continue
        if path.suffix.lower() not in TEXT_FILE_SUFFIXES and path.name not in {"Dockerfile", "Makefile"}:
            continue
        selected.append(relative)
        seen.add(relative)
        if len(selected) >= 12:
            break
    return selected


def _read_text_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return _truncate_text(text.strip(), 4000)


def _git_output(repo_path: Path, args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_METADATA_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


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
