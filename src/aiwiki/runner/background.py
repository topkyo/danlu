"""Background job manifests for long-running runner workflows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiwiki.utils.io import atomic_write_text


def background_jobs_dir(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "background-jobs"


def new_job_id(prefix: str = "ask-report") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}-{os.getpid()}-{time.monotonic_ns()}"


def job_manifest_path(root: Path, job_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(job_id or "")).strip("-")
    if not safe:
        raise ValueError("background job_id is required")
    return background_jobs_dir(root) / f"{safe}.json"


def write_job_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    job_id = str(manifest.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("background job manifest requires job_id")
    path = job_manifest_path(root, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return manifest


def load_job_manifest(root: Path, job_id: str) -> dict[str, Any]:
    path = job_manifest_path(root, job_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"background job manifest is not an object: {path}")
    return data


def update_job_manifest(root: Path, job_id: str, **updates: Any) -> dict[str, Any]:
    manifest = load_job_manifest(root, job_id)
    manifest.update(updates)
    manifest["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return write_job_manifest(root, manifest)


def spawn_background_resume(root: Path, job_id: str) -> dict[str, Any]:
    """Spawn a detached resume process and return observable process metadata."""

    log_dir = root / ".aiwiki" / "logs" / "background-jobs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{job_id}.stdout.log"
    stderr_path = log_dir / f"{job_id}.stderr.log"
    stdout_handle = stdout_path.open("ab")
    stderr_handle = stderr_path.open("ab")
    env = os.environ.copy()
    command = [
        sys.executable,
        "-m",
        "aiwiki.cli",
        "--root",
        str(root),
        "run-ask-resume",
        "--job-id",
        job_id,
    ]
    try:
        process = subprocess.Popen(  # noqa: S603 - command is fixed argv against current Python module.
            command,
            cwd=str(root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=True,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()
    return {
        "pid": process.pid,
        "command": command,
        "stdout_path": str(stdout_path.relative_to(root)) if stdout_path.is_relative_to(root) else str(stdout_path),
        "stderr_path": str(stderr_path.relative_to(root)) if stderr_path.is_relative_to(root) else str(stderr_path),
    }
