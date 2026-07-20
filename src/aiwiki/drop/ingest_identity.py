"""Canonical ingest URL identity for dedup manifest lookup."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib import parse

from ..input_router import rewrite_github_raw_url
from ..state.manifest import load_manifest
from ..utils.security import PathOutsideWorkspaceError, safe_resolve_within

_TRACKING_QUERY_KEYS = frozenset({"fbclid", "gclid", "ref", "source"})


def _is_tracking_query_key(key: str) -> bool:
    lowered = key.lower()
    if lowered.startswith("utm_"):
        return True
    return lowered in _TRACKING_QUERY_KEYS


def _strip_tracking_query(query: str) -> str:
    if not query:
        return ""
    kept = [(key, value) for key, value in parse.parse_qsl(query, keep_blank_values=True) if not _is_tracking_query_key(key)]
    return parse.urlencode(kept)


def normalize_ingest_url(url: str) -> str | None:
    """Return a canonical http(s) key for ingest dedup, or None when not a URL."""
    text = (url or "").strip()
    if not text:
        return None
    parsed = parse.urlparse(text)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return None

    rewritten = rewrite_github_raw_url(text)
    canonical = rewritten if rewritten else text
    parsed = parse.urlparse(canonical)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    query = _strip_tracking_query(parsed.query)
    return parse.urlunparse((scheme, netloc, path, "", query, ""))


def _iter_ingest_url_candidates(entry: dict[str, Any]) -> list[str]:
    candidates: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, str):
            text = value.strip()
            if text:
                candidates.append(text)

    add(entry.get("original_path"))
    meta = entry.get("ingest_metadata")
    if isinstance(meta, dict):
        add(meta.get("original_payload"))
        add(meta.get("original_url"))
        add(meta.get("final_url"))
        targets = meta.get("targets")
        if isinstance(targets, list):
            for item in targets:
                add(item)
    return candidates


def find_manifest_entry_by_ingest_url(root: Path, url: str) -> dict[str, Any] | None:
    """Find the first manifest entry whose ingest URL candidates match ``url``."""
    target_key = normalize_ingest_url(url)
    if target_key is None:
        return None
    for entry in load_manifest(root).get("entries") or []:
        if not isinstance(entry, dict):
            continue
        for candidate in _iter_ingest_url_candidates(entry):
            candidate_key = normalize_ingest_url(candidate)
            if candidate_key == target_key:
                return entry
    return None


def find_manifest_entry_by_ingest_urls(root: Path, *urls: str) -> dict[str, Any] | None:
    """Return the first manifest hit across multiple URL candidates."""
    for url in urls:
        entry = find_manifest_entry_by_ingest_url(root, url)
        if entry is not None:
            return entry
    return None


def resolve_manifest_stored_file(root: Path, entry: dict[str, Any]) -> Path | None:
    """Resolve ``stored_path`` to an existing file under ``root``, or None."""
    stored = str(entry.get("stored_path") or "").strip()
    if not stored:
        return None
    try:
        path = safe_resolve_within(root / stored, root)
    except PathOutsideWorkspaceError:
        return None
    return path if path.is_file() else None
