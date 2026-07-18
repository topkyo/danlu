"""Automation watcher: auto_process_once, watch_inbox, inbox_snapshot, automation state."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiwiki.app_linting.core import lint_wiki
from aiwiki.app_protocol import ensure_layout
from aiwiki.compile.pipeline import compile_wiki
from aiwiki.runner.receipts import _append_log
from aiwiki.state.manifest import load_manifest
from aiwiki.utils.hash import sha256_bytes
from aiwiki.utils.io import atomic_write_text, is_atomic_write_tmp_path, runtime_write_lock
from aiwiki.utils.path import relative_path


def auto_process_once(
    root: Path,
    compile_limit: int = 5,
) -> dict[str, Any]:
    ensure_layout(root)
    with runtime_write_lock(root):
        compile_result = {
            "compile": compile_wiki(root),
            "updated_pages": [],
            "pending_pages": _pending_summary_count(root),
            "skipped_pages": 0,
        }
        lint_result = {
            "deterministic": lint_wiki(root),
            "semantic_report": "",
        }
        snapshot = inbox_snapshot(root)
        result = {
            "processed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "mode": "deterministic-only",
            "deterministic_only": True,
            "semantic_lint": False,
            "compile_limit": compile_limit,
            "llm_used": False,
            "llm_fallback": False,
            "compile": compile_result,
            "lint": lint_result,
            "inbox_snapshot": snapshot,
        }
        _write_automation_state(root, result)
        _append_log(
            root,
            {
                "event": "auto-process",
                "llm_used": False,
                "llm_fallback": False,
                "compile_limit": compile_limit,
                "inbox_digest": snapshot["digest"],
            },
        )
    return result


def watch_inbox(
    root: Path,
    interval_seconds: float = 5.0,
    compile_limit: int = 5,
    process_initial: bool = True,
    max_cycles: int | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    processed_runs: list[dict[str, Any]] = []
    cycles = 0
    last_snapshot = inbox_snapshot(root)

    if process_initial:
        processed_runs.append(
            auto_process_once(
                root,
                compile_limit=compile_limit,
            )
        )
        last_snapshot = inbox_snapshot(root)

    while max_cycles is None or cycles < max_cycles:
        time.sleep(interval_seconds)
        cycles += 1
        current_snapshot = inbox_snapshot(root)
        if current_snapshot["digest"] == last_snapshot["digest"]:
            continue
        processed_runs.append(
            auto_process_once(
                root,
                compile_limit=compile_limit,
            )
        )
        last_snapshot = inbox_snapshot(root)

    return {
        "watch_cycles": cycles,
        "processed_runs": len(processed_runs),
        "last_result": processed_runs[-1] if processed_runs else None,
    }


def inbox_snapshot(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    files: list[dict[str, Any]] = []
    for path in sorted((root / "raw" / "inbox").glob("*")):
        if not path.is_file():
            continue
        # Orphan atomic-write tmp files are not real inbox content; ignore
        # them so watcher digests don't churn on crashed-writer residue.
        if is_atomic_write_tmp_path(path):
            continue
        stat = path.stat()
        files.append(
            {
                "path": relative_path(root, path),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    digest = sha256_bytes(json.dumps(files, sort_keys=True).encode("utf-8"))
    return {"digest": digest, "files": files}


def _pending_summary_count(root: Path) -> int:
    manifest = load_manifest(root)
    pending = 0
    for entry in manifest["entries"]:
        page = root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
            continue
        content = page.read_text(encoding="utf-8", errors="replace")
        if "Pending LLM summary." in content:
            pending += 1
    return pending


def _write_automation_state(root: Path, result: dict[str, Any]) -> None:
    ensure_layout(root)
    path = root / ".aiwiki" / "state" / "automation.json"
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, rendered, fsync=False)
