"""Repo drop handler (local + remote git repository snapshots)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import aiwiki.drop as _drop_pkg

from ..drop_helpers import strip_leading_title_echo, timestamped_stem
from ..protocol.scaffold import ensure_layout
from ..utils.io import runtime_write_lock
from ..utils.path import relative_path
from ..utils.security import safe_resolve_within
from .common import (
    _append_manifest_entry,
    _append_raw_added_history,
    _cleanup_tmp_dir,
    _rollback_created_paths,
    _snapshot_append_files,
    _truncate_append_files,
    _truncate_text,
    _unique_path,
    _write_text,
)

GIT_METADATA_TIMEOUT_SECONDS = 15
TEXT_FILE_SUFFIXES = {
    ".c",
    ".cc",
    ".cfg",
    ".clj",
    ".cpp",
    ".css",
    ".ex",
    ".go",
    ".gradle",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".ipynb",
    ".java",
    ".js",
    ".json",
    ".kt",
    ".lua",
    ".md",
    ".php",
    ".py",
    ".r",
    ".rb",
    ".rs",
    ".rst",
    ".scala",
    ".scm",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
REPO_PRIORITY_FILES = (
    "README.md",
    "README.rst",
    "README.txt",
    "README",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "INSTALL.md",
    "LICENSE",
    "LICENSE.md",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
    "Dockerfile",
    "Makefile",
    "setup.py",
)


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
        "snapshot_at": _drop_pkg.utc_now(),
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


def _normalize_repo_max_files(max_files: int) -> int:
    if not isinstance(max_files, int) or max_files < 1 or max_files > 1000:
        raise ValueError(f"max_files must be 1..1000, got {max_files}")
    return max_files


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
