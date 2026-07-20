"""Deterministic executor for LLM-produced Plans.

The executor takes a validated Plan and performs the actual work: HTTP fetch,
filesystem read, raw note writing, manifest registration. It never summarizes
or paraphrases fetched content -- raw/ stays a faithful capture layer. The
LLM planner only decides WHAT to fetch; this module decides how to persist it
byte-for-byte with provenance.

Actions:
- fetch_raw: HTTP GET each target URL, write all contents verbatim into one
  raw note with per-target provenance sections. New capability (multi-URL
  raw capture, no HTML extraction, no clone).
- fetch_page: delegate to existing drop_url.
- read_local_repo: delegate to existing drop_repo.
- read_local_note: delegate to existing drop_note.
- ask: signal back to the caller to re-dispatch to the ask path (the executor
  does not run the LLM ask itself; that is a separate LLM stage).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .drop import drop_note, drop_repo, drop_url
from .drop.common import (
    _append_manifest_entry,
    _append_raw_added_history,
    _rollback_created_paths,
    _snapshot_append_files,
    _truncate_append_files,
    _truncate_text,
    _unique_path,
    _write_text,
)
from .drop_helpers import timestamped_stem
from .input_planner import Plan
from .protocol.scaffold import ensure_layout
from .render.paths import append_wiki_log
from .utils.io import runtime_write_lock
from .utils.path import relative_path
from .utils.security import FetchPolicyError, PathOutsideWorkspaceError, safe_fetch, safe_resolve_within

_LOGGER = logging.getLogger("aiwiki.executor")

_FETCH_RAW_MAX_BYTES = 5 * 1024 * 1024
_FETCH_RAW_TIMEOUT = 60
_FETCH_RAW_PER_TARGET_CHAR_LIMIT = 40000


class AskSignal(dict):
    """Marker subclass returned for ask plans so the caller can re-dispatch."""


def execute_plan(root: Path, plan: Plan, original_payload: str, refresh: bool = False) -> dict[str, Any]:
    """Execute a validated Plan against the vault root.

    Returns the same shape as the underlying drop_* handler for delegation
    actions, or an AskSignal for ask plans (caller re-dispatches to the ask
    path).
    """
    ensure_layout(root)
    if plan.action == "fetch_raw":
        return _execute_fetch_raw(root, plan, original_payload, refresh=refresh)
    if plan.action == "fetch_page":
        target = plan.targets[0] if plan.targets else original_payload
        return drop_url(root, target, title=plan.title or None, refresh=refresh)
    if plan.action == "read_local_repo":
        target = plan.targets[0] if plan.targets else original_payload
        _assert_local_target_allowed(root, target, original_payload)
        return drop_repo(root, target, title=plan.title or None)
    if plan.action == "read_local_note":
        target = plan.targets[0] if plan.targets else original_payload
        _assert_local_target_allowed(root, target, original_payload)
        return drop_note(root, target, title=plan.title or None)
    if plan.action == "ask":
        ask_payload = plan.targets[0] if plan.targets else original_payload
        return AskSignal({"action": "ask", "payload": ask_payload, "title": plan.title})
    raise ValueError(f"unsupported plan action: {plan.action}")


def _execute_fetch_raw(root: Path, plan: Plan, original_payload: str, *, refresh: bool = False) -> dict[str, Any]:
    """Fetch each target URL verbatim and write a single raw note with provenance.

    Uses safe_fetch for SSRF guard (allow_private follows AIWIKI_ALLOW_PRIVATE_FETCH
    via drop.common._allow_private_fetch). Content is written byte-for-byte
    (decoded utf-8 with errors=replace, truncated per-target) -- no LLM
    summarization, no HTML extraction. Each target gets its own ## Source section
    with the URL recorded for provenance.
    """
    from .drop.common import _allow_private_fetch
    from .drop.ingest_identity import find_manifest_entry_by_ingest_urls, resolve_manifest_stored_file

    lookup_urls = [original_payload]
    if plan.targets:
        lookup_urls.append(plan.targets[0])
    existing = find_manifest_entry_by_ingest_urls(root, *lookup_urls)
    if existing and not refresh:
        if resolve_manifest_stored_file(root, existing) is not None:
            return _reused_fetch_raw_payload(original_payload, existing)

    display_title = plan.title or _derive_title_from_targets(plan.targets) or "raw fetch"
    overwrite_path = resolve_manifest_stored_file(root, existing) if refresh and existing else None
    if overwrite_path is None:
        stem = timestamped_stem(display_title)
        note_path = _unique_path(root / "raw" / "inbox", stem, ".md")
    else:
        note_path = overwrite_path
    refreshed = overwrite_path is not None
    fetched: list[dict[str, str]] = []
    for target in plan.targets:
        try:
            payload_bytes, final_url = safe_fetch(
                target,
                max_bytes=_FETCH_RAW_MAX_BYTES,
                timeout=_FETCH_RAW_TIMEOUT,
                allow_private=_allow_private_fetch(),
            )
        except FetchPolicyError as exc:
            _LOGGER.warning("fetch_raw target blocked by policy: %s -> %s", target, exc)
            fetched.append({"url": target, "content": f"[fetch blocked: {exc}]", "ok": False})
            continue
        except Exception as exc:  # network errors, timeouts
            _LOGGER.warning("fetch_raw target failed: %s -> %s", target, exc)
            fetched.append({"url": target, "content": f"[fetch failed: {exc}]", "ok": False})
            continue
        text = payload_bytes.decode("utf-8", errors="replace").strip()
        text = _truncate_text(text, _FETCH_RAW_PER_TARGET_CHAR_LIMIT)
        fetched.append({"url": final_url, "content": text, "ok": True})

    ok_count = sum(1 for item in fetched if item.get("ok"))
    if ok_count == 0:
        # Match drop_url / drop_repo fail-loud: never persist a placeholder-only
        # note that compile would treat as real material.
        details = "; ".join(f"{item['url']}: {item['content']}" for item in fetched) or "no targets"
        raise RuntimeError(f"fetch_raw failed for all targets ({details})")

    markdown = _build_fetch_raw_note(display_title, fetched, original_payload, plan.reason)
    ingest_metadata = {
        "planner_action": "fetch_raw",
        "original_payload": original_payload,
        "targets": [item["url"] for item in fetched],
        "plan_reason": plan.reason,
        "fetched_at": _utc_now(),
    }
    created_paths: list[Path] = []
    append_file_sizes = _snapshot_append_files(root)
    with runtime_write_lock(root):
        try:
            _write_text(note_path, markdown)
            created_paths.append(note_path)
            entry = _append_manifest_entry(
                root,
                stored_path=note_path,
                original_path=original_payload,
                source_type="planner-fetch-raw",
                title=display_title,
                ingest_metadata=ingest_metadata,
            )
            append_wiki_log(
                root,
                "ingest",
                display_title,
                [
                    "source_type: `planner-fetch-raw`",
                    f"stored_note: `{relative_path(root, note_path)}`",
                    f"targets: `{len(fetched)}`",
                    f"original_payload: `{original_payload}`",
                ],
            )
            _append_raw_added_history(
                root,
                material="url",
                stored_path=note_path,
                original_path=original_payload,
                source_type="planner-fetch-raw",
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
        "path": relative_path(root, note_path),
        "stored_path": relative_path(root, note_path),
        "original_path": original_payload,
        "title": display_title,
        "planner_action": "fetch_raw",
        "targets": [item["url"] for item in fetched],
        "fetch_ok_count": sum(1 for item in fetched if item.get("ok")),
        "reused": False,
        "refreshed": refreshed,
    }


def _reused_fetch_raw_payload(original_payload: str, entry: dict[str, Any]) -> dict[str, Any]:
    stored_rel = str(entry.get("stored_path") or "")
    meta = entry.get("ingest_metadata") if isinstance(entry.get("ingest_metadata"), dict) else {}
    targets = meta.get("targets") if isinstance(meta.get("targets"), list) else []
    return {
        "material": "url",
        "note_path": stored_rel,
        "path": stored_rel,
        "stored_path": stored_rel,
        "original_path": original_payload,
        "title": str(entry.get("title") or ""),
        "planner_action": "fetch_raw",
        "targets": list(targets),
        "fetch_ok_count": len(targets),
        "reused": True,
        "refreshed": False,
        "duplicate_of": entry.get("id"),
    }


def _build_fetch_raw_note(
    display_title: str,
    fetched: list[dict[str, str]],
    original_payload: str,
    reason: str,
) -> str:
    lines = [f"# {display_title}", ""]
    if reason:
        lines.append(f"> planner reason: {reason}")
        lines.append("")
    lines.append(f"> original input: `{original_payload}`")
    lines.append("")
    for item in fetched:
        url = item["url"]
        content = item["content"]
        lines.append(f"## Source: {url}")
        lines.append("")
        if content:
            lines.append(content)
        else:
            lines.append("[no content]")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _derive_title_from_targets(targets: list[str]) -> str:
    if not targets:
        return ""
    first = targets[0]
    # For raw.githubusercontent.com/<owner>/<repo>/HEAD/<file>, use <repo>.
    if "raw.githubusercontent.com/" in first:
        parts = first.split("/")
        if len(parts) >= 6:
            return parts[5]
    # Fall back to the last path segment / netloc.
    from urllib.parse import urlparse

    parsed = urlparse(first)
    if parsed.path and parsed.path != "/":
        return parsed.path.rstrip("/").rsplit("/", 1)[-1] or parsed.netloc
    return parsed.netloc


def _assert_local_target_allowed(root: Path, target: str, original_payload: str) -> None:
    """Reject LLM-rewritten local paths (confused-deputy).

    Allowed only when:
    - target resolves to the same path as original_payload, or
    - original_payload itself is a local path under the vault and target is
      that path or a descendant within the vault.

    Vault-internal paths (``.aiwiki/``, ``wiki/``, ``output/``, …) are never
    allowed unless they are exactly the user-supplied original_payload.
    """
    _RUNTIME_OWNED_TOP = {".aiwiki", "wiki", "output", "schema", "prompts", "raw"}

    resolved = Path(target).expanduser()
    try:
        resolved = resolved.resolve(strict=False)
    except OSError as exc:
        raise ValueError(f"invalid local target: {target}") from exc

    root_resolved = root.resolve()
    original = Path(original_payload).expanduser()
    try:
        original_resolved = original.resolve(strict=False)
    except OSError:
        original_resolved = None

    if original_resolved is not None and resolved == original_resolved:
        return

    # Unrelated absolute/relative target that merely sits inside the vault.
    try:
        within = safe_resolve_within(resolved, root)
    except PathOutsideWorkspaceError as exc:
        raise PathOutsideWorkspaceError(
            f"local plan target escapes vault and is not the original payload: {target}"
        ) from exc

    rel = within.relative_to(root_resolved)
    top = rel.parts[0] if rel.parts else ""
    if top in _RUNTIME_OWNED_TOP:
        raise PathOutsideWorkspaceError(
            f"local plan target may not point at runtime-owned path `{top}/` unless it is the original payload: {target}"
        )

    # Target under vault is only OK if original_payload is also under vault and
    # is an ancestor of (or equal to) the target.
    if original_resolved is None:
        raise PathOutsideWorkspaceError(
            f"local plan target under vault is unrelated to original payload: {target}"
        )
    try:
        original_within = safe_resolve_within(original_resolved, root)
    except PathOutsideWorkspaceError as exc:
        raise PathOutsideWorkspaceError(
            f"local plan target under vault is unrelated to original payload: {target}"
        ) from exc
    if within != original_within and original_within not in within.parents:
        raise PathOutsideWorkspaceError(
            f"local plan target under vault is unrelated to original payload: {target}"
        )


def _utc_now() -> str:
    import aiwiki.drop as _drop_pkg

    return _drop_pkg.utc_now()
