"""URL drop handler (HTTP fetch + browser-render + HTML extraction)."""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib import parse

import aiwiki.drop as _drop_pkg

from ..drop_helpers import strip_leading_title_echo, timestamped_stem
from ..protocol.scaffold import ensure_layout
from ..render.paths import append_wiki_log
from ..state.manifest import load_manifest, save_manifest
from ..utils.io import atomic_write_bytes, runtime_write_lock
from ..utils.path import relative_path
from ..utils.security import FetchPolicyError, _validate_safe_url, safe_fetch, safe_resolve_within
from .common import (
    _ASSET_MAX_BYTES,
    _HTML_MAX_BYTES,
    _allow_private_fetch,
    _append_manifest_entry,
    _append_raw_added_history,
    _append_run_event,
    _cleanup_tmp_dir,
    _label_from_url,
    _normalize_text,
    _rollback_created_paths,
    _snapshot_append_files,
    _suffix_from_source,
    _truncate_append_files,
    _truncate_text,
    _unique_path,
    _write_bytes,
    _write_text,
)

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - optional dependency
    BeautifulSoup = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional dependency
    sync_playwright = None

USER_AGENT = "aiwiki/0.1 (+https://local)"
MAX_URL_IMAGES = 6
BROWSER_RENDER_TIMEOUT_SECONDS = 45
BROWSER_VIRTUAL_TIME_BUDGET_MS = 8000
ALLOW_BROWSER_NO_SANDBOX_ENV = "AIWIKI_ALLOW_BROWSER_NO_SANDBOX"
# SSRF: Chromium CLI follows redirects without route guard; opt-in only.
ALLOW_UNGUARDED_BROWSER_CLI_ENV = "AIWIKI_ALLOW_UNGUARDED_BROWSER_CLI"
MAX_TEXT_CHARS = 120000


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
    fetched = _drop_pkg._fetch_url(url, root=root)
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
            "fetched_at": _drop_pkg.utc_now(),
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

    if not _allow_unguarded_browser_cli():
        return {"html": "", "backend": ""}

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


def _allow_unguarded_browser_cli() -> bool:
    return os.environ.get(ALLOW_UNGUARDED_BROWSER_CLI_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


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
        ".markdown-body",
        ".readme",
        ".readme-content",
        '[data-testid="readme"]',
        ".documentation",
        ".docs-body",
        ".prose",
        "#content",
        "#main-content",
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
