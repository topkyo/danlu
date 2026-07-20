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


def execute_plan(root: Path, plan: Plan, original_payload: str) -> dict[str, Any]:
    """Execute a validated Plan against the vault root.

    Returns the same shape as the underlying drop_* handler for delegation
    actions, or an AskSignal for ask plans (caller re-dispatches to the ask
    path).
    """
    ensure_layout(root)
    if plan.action == "fetch_raw":
        return _execute_fetch_raw(root, plan, original_payload)
    if plan.action == "fetch_page":
        target = plan.targets[0] if plan.targets else original_payload
        return drop_url(root, target, title=plan.title or None)
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


def _execute_fetch_raw(root: Path, plan: Plan, original_payload: str) -> dict[str, Any]:
    """Fetch each target URL verbatim and write a single raw note with provenance.

    Uses safe_fetch for SSRF guard (allow_private follows AIWIKI_ALLOW_PRIVATE_FETCH
    via drop.common._allow_private_fetch). Content is written byte-for-byte
    (decoded utf-8 with errors=replace, truncated per-target) -- no LLM
    summarization, no HTML extraction. Each target gets its own ## Source section
    with the URL recorded for provenance.
    """
    from .drop.common import _allow_private_fetch

    display_title = plan.title or _derive_title_from_targets(plan.targets) or "raw fetch"
    stem = timestamped_stem(display_title)
    note_path = _unique_path(root / "raw" / "inbox", stem, ".md")
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
        "original_path": original_payload,
        "title": display_title,
        "planner_action": "fetch_raw",
        "targets": [item["url"] for item in fetched],
        "fetch_ok_count": sum(1 for item in fetched if item.get("ok")),
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
    """Reject LLM-rewritten local paths that escape the vault / original payload.

    Planner may choose read_local_* but must not turn an unrelated payload into
    an absolute path outside the workspace (confused-deputy). Allowed:
    - path resolves under vault root, or
    - path resolves to the same file/dir as the original_payload.
    """
    resolved = Path(target).expanduser()
    try:
        resolved = resolved.resolve(strict=False)
    except OSError as exc:
        raise ValueError(f"invalid local target: {target}") from exc
    try:
        safe_resolve_within(resolved, root)
        return
    except PathOutsideWorkspaceError:
        pass
    original = Path(original_payload).expanduser()
    try:
        original_resolved = original.resolve(strict=False)
    except OSError:
        original_resolved = None
    if original_resolved is not None and resolved == original_resolved:
        return
    raise PathOutsideWorkspaceError(
        f"local plan target escapes vault and is not the original payload: {target}"
    )


def _utc_now() -> str:
    import aiwiki.drop as _drop_pkg

    return _drop_pkg.utc_now()
