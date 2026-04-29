"""Direct raw-material entry points for aiwiki."""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib import parse, request

from .app_protocol import ensure_layout
from .app_render import append_wiki_log
from .app_state import DEFAULT_PROTOCOL, append_runtime_history
from .app_utils import first_markdown_heading, relative_path, render_frontmatter, slugify, utc_now
from .config import LLMConfig
from .llm import LLMError, create_backend_client

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


def _append_run_event(root: Path, event: dict[str, Any]) -> None:
    from .runner.receipts import _append_log

    _append_log(root, event)
BROWSER_RENDER_TIMEOUT_SECONDS = 45
BROWSER_VIRTUAL_TIME_BUDGET_MS = 8000
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
    fetched = _fetch_url(url)
    display_title = title or fetched["title"] or _label_from_url(fetched["final_url"])
    asset_paths = _materialize_url_images(
        root,
        fetched["image_urls"],
        preferred_slug=display_title,
    )
    stem = _timestamped_stem(display_title)
    note_path = _unique_path(root / "raw" / "inbox", stem, ".md")
    page_assets = [f"- Stored asset: `{path}`" for path in asset_paths] or ["- No page images stored."]
    markdown = _render_raw_note(
        title=display_title,
        source_type="url-drop",
        original_path=fetched["final_url"],
        sections=[
            ("Source URL", [f"- Original URL: `{url}`", f"- Final URL: `{fetched['final_url']}`"]),
            (
                "Fetch Metadata",
                [
                    f"- Fetched at: `{utc_now()}`",
                    f"- Content type: `{fetched['content_type']}`",
                    f"- HTTP status: `{fetched['status']}`",
                    f"- Browser renderer: `{fetched['browser_backend'] or 'none'}`",
                    f"- Extraction mode: `{fetched['extraction_mode']}`",
                ],
            ),
            ("Description", [fetched["description"] or "- No meta description found."]),
            ("Page Assets", page_assets),
            ("Extracted Content", [fetched["text"] or "No text content extracted from the page."]),
        ],
        extra_frontmatter={"asset_files": asset_paths},
    )
    _write_text(note_path, markdown)
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
        note_path=note_path,
        original_path=url,
        source_type="url-drop",
        title=display_title,
    )
    return {
        "material": "url",
        "note_path": relative_path(root, note_path),
        "original_url": url,
        "final_url": fetched["final_url"],
        "asset_paths": asset_paths,
        "title": display_title,
    }


def drop_pdf(root: Path, source: str, title: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    asset_path, original_path = _materialize_binary_source(root, source, preferred_slug=title or Path(source).stem)
    if asset_path.suffix.lower() != ".pdf":
        renamed = asset_path.with_suffix(".pdf")
        asset_path.rename(renamed)
        asset_path = renamed
    extracted_text = _extract_pdf_text(asset_path)
    display_title = title or Path(original_path).stem or asset_path.stem
    stem = _timestamped_stem(display_title)
    note_path = _unique_path(root / "raw" / "inbox", stem, ".md")
    markdown = _render_raw_note(
        title=display_title,
        source_type="pdf-drop",
        original_path=original_path,
        sections=[
            ("PDF Asset", [f"- Stored PDF: `{relative_path(root, asset_path)}`"]),
            (
                "Import Metadata",
                [
                    f"- Imported at: `{utc_now()}`",
                    f"- File size: `{asset_path.stat().st_size}` bytes",
                ],
            ),
            (
                "Extracted Text",
                [
                    extracted_text
                    or "No PDF text could be extracted. This file may be image-only and need OCR."
                ],
            ),
        ],
        extra_frontmatter={"asset_files": [relative_path(root, asset_path)]},
    )
    _write_text(note_path, markdown)
    append_wiki_log(
        root,
        "ingest",
        display_title,
        [
            "source_type: `pdf-drop`",
            f"stored_note: `{relative_path(root, note_path)}`",
            f"asset_path: `{relative_path(root, asset_path)}`",
        ],
    )
    _append_raw_added_history(
        root,
        material="pdf",
        note_path=note_path,
        original_path=original_path,
        source_type="pdf-drop",
        title=display_title,
    )
    return {
        "material": "pdf",
        "note_path": relative_path(root, note_path),
        "asset_path": relative_path(root, asset_path),
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
    asset_path, original_path = _materialize_binary_source(root, source, preferred_slug=title or Path(source).stem)
    mime = _detect_mime_type(asset_path)
    width, height = _image_dimensions(asset_path)
    ocr_text = _extract_image_text(asset_path)
    vision_result = _analyze_image_asset(
        root,
        asset_path,
        mime=mime,
        width=width,
        height=height,
        ocr_text=ocr_text,
        client=client,
        enable_vision=enable_vision,
    )
    visual_analysis = vision_result["analysis"]
    vision_backend = vision_result["backend"]
    vision_status = vision_result["status"]
    display_title = title or Path(original_path).stem or asset_path.stem
    stem = _timestamped_stem(display_title)
    note_path = _unique_path(root / "raw" / "inbox", stem, ".md")
    dimension_text = f"{width}x{height}" if width and height else "unknown"
    extracted_text = ocr_text or "OCR is unavailable on this machine or no text was detected. Treat this as an image reference source."
    visual_lines = [visual_analysis] if visual_analysis else [
        "Visual analysis was not generated. Configure `codex-cli` if you want LLM-backed image understanding."
    ]
    markdown = _render_raw_note(
        title=display_title,
        source_type="image-drop",
        original_path=original_path,
        sections=[
            ("Image Asset", [f"- Stored image: `{relative_path(root, asset_path)}`"]),
            (
                "Image Metadata",
                [
                    f"- Imported at: `{utc_now()}`",
                    f"- MIME type: `{mime}`",
                    f"- Dimensions: `{dimension_text}`",
                    f"- File size: `{asset_path.stat().st_size}` bytes",
                    f"- Vision backend: `{vision_backend or 'none'}`",
                    f"- Vision status: `{vision_status}`",
                ],
            ),
            (
                "Extracted Text",
                [
                    extracted_text
                ],
            ),
            ("Visual Analysis", visual_lines),
        ],
        extra_frontmatter={
            "asset_files": [relative_path(root, asset_path)],
            "vision_backend": vision_backend,
            "vision_status": vision_status,
        },
    )
    _write_text(note_path, markdown)
    append_wiki_log(
        root,
        "ingest",
        display_title,
        [
            "source_type: `image-drop`",
            f"stored_note: `{relative_path(root, note_path)}`",
            f"asset_path: `{relative_path(root, asset_path)}`",
            f"vision_status: `{vision_status}`",
        ],
    )
    _append_raw_added_history(
        root,
        material="image",
        note_path=note_path,
        original_path=original_path,
        source_type="image-drop",
        title=display_title,
    )
    return {
        "material": "image",
        "note_path": relative_path(root, note_path),
        "asset_path": relative_path(root, asset_path),
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
    cleanup_path: Path | None = None
    repo_path: Path
    original_path = source
    if _looks_like_repo_url(source):
        cleanup_path = Path(tempfile.mkdtemp(prefix="aiwiki-repo-"))
        repo_path = cleanup_path / "repo"
        _clone_repo(source, repo_path)
        original_path = source
    else:
        repo_path = Path(source).expanduser().resolve()
        if not repo_path.is_dir():
            raise FileNotFoundError(f"Repository path not found: {source}")

    try:
        snapshot = _repo_snapshot(repo_path, max_files=max_files)
    finally:
        if cleanup_path is not None:
            shutil.rmtree(cleanup_path, ignore_errors=True)

    display_title = title or snapshot["name"]
    stem = _timestamped_stem(display_title)
    note_path = _unique_path(root / "raw" / "inbox", stem, ".md")
    sections = [
        ("Repository", [f"- Source: `{original_path}`"]),
        (
            "Repository Metadata",
            [
                f"- Snapshot at: `{utc_now()}`",
                f"- Commit: `{snapshot['commit'] or 'unknown'}`",
                f"- Origin: `{snapshot['origin'] or 'unknown'}`",
            ],
        ),
        ("README", [snapshot["readme"] or "No README text found."]),
        ("Repository Tree", snapshot["tree"] or ["- No files captured."]),
    ]
    if snapshot["files"]:
        file_lines = []
        for item in snapshot["files"]:
            file_lines.extend([f"### {item['path']}", item["content"], ""])
        sections.append(("Key File Excerpts", file_lines))
    markdown = _render_raw_note(
        title=display_title,
        source_type="repo-drop",
        original_path=original_path,
        sections=sections,
    )
    _write_text(note_path, markdown)
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
        note_path=note_path,
        original_path=original_path,
        source_type="repo-drop",
        title=display_title,
    )
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
    ensure_layout(root)
    note_kind = kind.strip().lower()
    if note_kind not in {"note", "transcript"}:
        raise ValueError(f"Unsupported note kind: {kind}")
    if source and text is not None:
        raise ValueError("Provide either a note file path or --text, not both.")
    if text is not None:
        captured_text = _normalize_text(text)
        original_path = "inline://note"
        capture_mode = "inline-text"
        fallback_title = note_kind.title()
    else:
        if not source:
            raise ValueError("Provide a markdown/text file path or --text for drop-note.")
        source_path = Path(source).expanduser()
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"Note file not found: {source}")
        captured_text = _normalize_text(source_path.read_text(encoding="utf-8", errors="replace"))
        original_path = str(source)
        capture_mode = "file"
        fallback_title = source_path.stem or note_kind.title()
    if not captured_text:
        raise RuntimeError("Note capture is empty.")
    if not allow_sensitive:
        _assert_no_sensitive_text(captured_text, source_label=original_path)
    display_title = title or _note_title(captured_text, fallback=fallback_title)
    stem = _timestamped_stem(display_title)
    note_path = _unique_path(root / "raw" / "inbox", stem, ".md")
    markdown = _render_raw_note(
        title=display_title,
        source_type="note-drop",
        original_path=original_path,
        sections=[
            (
                "Capture Metadata",
                [
                    f"- Captured at: `{utc_now()}`",
                    f"- Capture mode: `{capture_mode}`",
                    f"- Note kind: `{note_kind}`",
                ],
            ),
            ("Captured Note", [captured_text]),
        ],
        extra_frontmatter={"note_kind": note_kind},
    )
    _write_text(note_path, markdown)
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
        note_path=note_path,
        original_path=original_path,
        source_type="note-drop",
        title=display_title,
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
    note_path: Path,
    original_path: str,
    source_type: str,
    title: str,
) -> None:
    append_runtime_history(
        root,
        {
            "event_type": "raw-added",
            "occurred_at": utc_now(),
            "protocol": DEFAULT_PROTOCOL,
            "material": material,
            "stored_path": relative_path(root, note_path),
            "original_path": original_path,
            "source_type": source_type,
            "title": title,
        },
    )


def _fetch_url(url: str) -> dict[str, Any]:
    fetched = _http_fetch_url(url)
    final_url = fetched["final_url"]
    content_type = fetched["content_type"]
    status = fetched["status"]
    raw_text = fetched["text"]
    browser_backend = ""
    browser_html = ""
    if _should_try_browser_render(final_url, content_type):
        try:
            rendered = _render_url_in_browser(final_url)
        except RuntimeError:
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


def _http_fetch_url(url: str) -> dict[str, str]:
    try:
        req = request.Request(url, headers={"User-Agent": USER_AGENT})
        with request.urlopen(req, timeout=30) as response:
            payload = response.read()
            final_url = response.geturl()
            content_type = response.headers.get_content_type()
            charset = response.headers.get_content_charset() or "utf-8"
            status = getattr(response, "status", 200)
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
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=USER_AGENT)
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


def _resolve_asset_url(base_url: str, candidate: str) -> str:
    if not candidate:
        return ""
    if candidate.startswith("data:"):
        return ""
    resolved = parse.urljoin(base_url, candidate.strip())
    return resolved if parse.urlparse(resolved).scheme in {"http", "https", "file"} else ""


def _materialize_url_images(root: Path, image_urls: list[str], preferred_slug: str) -> list[str]:
    stored: list[str] = []
    for index, image_url in enumerate(image_urls[:MAX_URL_IMAGES], start=1):
        try:
            asset_path, _ = _download_asset_url(root, image_url, f"{preferred_slug}-image-{index}")
        except Exception as exc:
            _append_run_event(
                root,
                {
                    "event": "url_image_download_skipped",
                    "url": image_url,
                    "reason": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            continue
        stored.append(relative_path(root, asset_path))
    return stored


def _download_asset_url(root: Path, source: str, preferred_slug: str) -> tuple[Path, str]:
    asset_dir = root / "raw" / "assets"
    req = request.Request(source, headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=60) as response:
        payload = response.read()
        final_url = response.geturl()
        content_type = response.headers.get_content_type()
    suffix = _suffix_from_source(final_url, content_type)
    asset_path = _unique_path(asset_dir, _timestamped_stem(preferred_slug), suffix)
    _write_bytes(asset_path, payload)
    return asset_path, final_url


def _materialize_binary_source(root: Path, source: str, preferred_slug: str) -> tuple[Path, str]:
    asset_dir = root / "raw" / "assets"
    if source.startswith("http://") or source.startswith("https://"):
        asset_path, final_url = _download_asset_url(root, source, preferred_slug)
        return asset_path, final_url

    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Source not found: {source}")
    suffix = source_path.suffix.lower() or ".bin"
    asset_path = _unique_path(asset_dir, _timestamped_stem(preferred_slug), suffix)
    shutil.copy2(source_path, asset_path)
    return asset_path, str(source_path)


def _extract_pdf_text(path: Path) -> str:
    completed = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {completed.stderr.strip()}")
    return _truncate_text(_normalize_text(completed.stdout), MAX_TEXT_CHARS)


def _detect_mime_type(path: Path) -> str:
    completed = subprocess.run(
        ["file", "--brief", "--mime-type", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
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
    completed = subprocess.run(
        ["tesseract", str(path), "stdout"],
        capture_output=True,
        text=True,
        check=False,
    )
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
    user_prompt = "\n".join(
        [
            "Analyze this image asset for a source note.",
            f"- Asset path: `{relative_path(root, image_path)}`",
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
    if config.backend != "codex-cli":
        return None
    return create_backend_client(config, root)


def _client_backend_name(client: Any) -> str:
    config = getattr(client, "config", None)
    backend = getattr(config, "backend", "")
    return backend if isinstance(backend, str) else ""


def _looks_like_repo_url(source: str) -> bool:
    lowered = source.lower()
    return lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("git@")


def _clone_repo(source: str, destination: Path) -> None:
    completed = subprocess.run(
        ["git", "clone", "--depth", "1", source, str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
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
        if not path.is_file():
            continue
        entries.append(path.relative_to(repo_path).as_posix())
        if len(entries) >= max_files:
            break
    return entries


def _repo_key_files(repo_path: Path) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for relative in REPO_PRIORITY_FILES:
        candidate = repo_path / relative
        if candidate.is_file():
            value = candidate.relative_to(repo_path).as_posix()
            selected.append(value)
            seen.add(value)

    for path in sorted(repo_path.rglob("*")):
        if any(part in {".git", "node_modules", ".venv", "__pycache__", "dist", "build"} for part in path.parts):
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(repo_path).as_posix()
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
    completed = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _timestamped_stem(label: str) -> str:
    return f"{utc_now().replace(':', '').replace('-', '').replace('+00:00', 'z')}-{slugify(label)[:48]}"


def _unique_path(directory: Path, stem: str, suffix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}{suffix}"
    index = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{index}{suffix}"
        index += 1
    return candidate


def _write_text(path: Path, content: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content.rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_bytes(path: Path, content: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(content)
    tmp.replace(path)


def _render_raw_note(
    title: str,
    source_type: str,
    original_path: str,
    sections: list[tuple[str, list[str]]],
    extra_frontmatter: dict[str, Any] | None = None,
) -> str:
    frontmatter = {
        "title": title,
        "source_type": source_type,
        "original_path": original_path,
    }
    if extra_frontmatter:
        frontmatter.update(extra_frontmatter)
    lines = [render_frontmatter(frontmatter), "", f"# {title}", ""]
    for heading, body_lines in sections:
        lines.append(f"## {heading}")
        lines.extend(body_lines)
        lines.append("")
    return "\n".join(lines)


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
