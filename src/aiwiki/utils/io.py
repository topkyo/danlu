from __future__ import annotations

import contextlib
import fcntl
import functools
import hashlib
import html
import http.client
import ipaddress
import json
import logging
import os
import re
import shutil
import socket
import ssl
import tempfile
import threading
import time
import urllib.request
from collections import deque
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
_RUNTIME_LOCK_GUARD = threading.RLock()
_RUNTIME_LOCKS: dict[str, dict[str, Any]] = {}
_LOCK_TIMEOUT_DEFAULT_SEC = 300


class LockTimeoutError(RuntimeError):
    pass


ISO_DATETIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\+\d{2}:\d{2}|Z)")


def runtime_lock_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "runtime.lock"


def _resolve_lock_timeout() -> float:
    raw = os.environ.get("AIWIKI_RUNTIME_LOCK_TIMEOUT")
    if raw is None:
        return float(_LOCK_TIMEOUT_DEFAULT_SEC)
    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        return float(_LOCK_TIMEOUT_DEFAULT_SEC)
    return float(max(1, min(3600, timeout)))


@contextmanager
def runtime_write_lock(root: Path):
    resolved_root = str(root.resolve())
    with _RUNTIME_LOCK_GUARD:
        state = _RUNTIME_LOCKS.get(resolved_root)
        if state is not None:
            state["depth"] = int(state.get("depth", 0)) + 1
            handle = state["handle"]
        else:
            lock_path = runtime_lock_path(root)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            handle = lock_path.open("a+", encoding="utf-8")
            timeout = _resolve_lock_timeout()
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        handle.close()
                        raise LockTimeoutError(
                            f"runtime write lock timeout after {timeout:.0f}s for {root}; "
                            f"unset AIWIKI_RUNTIME_LOCK_TIMEOUT or wait for the holder to release"
                        ) from None
                    time.sleep(0.1)
            handle.seek(0)
            handle.truncate()
            handle.write(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "root": resolved_root,
                        "acquired_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()
            _RUNTIME_LOCKS[resolved_root] = {"handle": handle, "depth": 1}
    try:
        yield
    finally:
        with _RUNTIME_LOCK_GUARD:
            state = _RUNTIME_LOCKS.get(resolved_root)
            if state is not None:
                state["depth"] = int(state.get("depth", 0)) - 1
                if state["depth"] <= 0:
                    handle = state["handle"]
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    finally:
                        handle.close()
                        _RUNTIME_LOCKS.pop(resolved_root, None)


def runtime_write_operation(func):
    @functools.wraps(func)
    def wrapper(root: Path, *args, **kwargs):
        with runtime_write_lock(root):
            return func(root, *args, **kwargs)

    return wrapper


def _durable_truncate(path: Path, size: int) -> None:
    """Durable truncate: open r+b, truncate, flush, fsync. Raises on any IO failure."""
    with open(path, "r+b") as handle:
        handle.truncate(size)
        handle.flush()
        os.fsync(handle.fileno())


def _restore_file_bytes(path: Path, snapshot: bytes | None) -> None:
    """Restore a file to its pre-mutation state.

    Snapshot semantics:
        None  → file did not exist before; ensure it does not exist now.
        bytes → file existed; restore exact bytes via atomic rename.
    """
    if snapshot is None:
        try:
            path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        return
    tmp = path.with_suffix(path.suffix + ".restore.tmp")
    tmp.write_bytes(snapshot)
    os.replace(tmp, path)


def _snapshot_file_bytes(path: Path) -> bytes | None:
    if not path.exists():
        return None
    return path.read_bytes()


def _restore_snapshots(snapshots: Mapping[Path, bytes | None]) -> None:
    """Restore a batch of files from snapshots in reverse-insertion order.

    Best-effort across the batch: collects rollback exceptions and raises the
    first one only after attempting every entry, matching the prior ad-hoc
    rollback closures used by transactional mutation callers.
    """
    errors: list[Exception] = []
    for path, snapshot in reversed(list(snapshots.items())):
        try:
            _restore_file_bytes(path, snapshot)
        except Exception as exc:  # noqa: BLE001 - aggregate then re-raise
            errors.append(exc)
    if errors:
        raise errors[0]


def _durable_restore_or_remove(path: Path, snapshot: bytes | None) -> None:
    """Restore single-file primary to snapshot state.

    snapshot is None → file did not exist before; remove it (return to non-exist).
    snapshot is bytes → write snapshot durably (tmp + fsync + replace).
    Raises on any IO failure.
    """
    if snapshot is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(snapshot)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def is_atomic_write_tmp_path(path: Path) -> bool:
    """Return True iff `path.name` matches the atomic-write tmp convention.

    `atomic_write_text` and `atomic_copy_file` create tmp files named
    `<final>.tmp.<pid>.<monotonic_ns>` in the destination directory. On
    normal exceptions the helper unlinks them; on hard process kill they
    may persist as orphans. Consumers that enumerate directories owned by
    these helpers must skip files matching this pattern so orphans are
    never treated as authoritative content.

    Pattern is strict: trailing `.tmp.<digits>.<digits>` so legitimate
    user filenames like `report.tmp.notes.md` are NOT skipped.
    """
    return _ATOMIC_TMP_RE.search(path.name) is not None


_ATOMIC_TMP_RE = re.compile(r"\.tmp\.\d+\.\d+$")


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    fsync: bool = True,
) -> None:
    """Write text atomically: tmp + fsync + replace + best-effort dir fsync.

    Raises on any failure up to and including `os.replace`; never leaves
    half-written content at `path`. Cleans up tmp on failure.

    Directory fsync (durability of the rename) is best-effort: a dir fsync
    failure after a successful replace is logged but not re-raised, since
    the new file is already visible at `path`. Callers needing strict
    crash-durability should layer their own sync.

    Does NOT acquire runtime_write_lock — caller must hold it (or call
    from inside @runtime_write_operation).

    Note: tmp file lives in `path.parent` as `<name>.tmp.<pid>.<ns>`. If
    the writer process is killed mid-write, the tmp may persist. Callers
    that scan the parent directory must skip files matching
    `is_atomic_write_tmp_path()` (strict trailing `.tmp.<digits>.<digits>`).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp.{os.getpid()}.{time.monotonic_ns()}"
    try:
        with tmp.open("w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            if fsync:
                os.fsync(handle.fileno())
        os.replace(tmp, path)
        if fsync:
            try:
                dir_fd = os.open(path.parent, os.O_DIRECTORY)
            except OSError:
                return  # platform without O_DIRECTORY; file fsync already done
            try:
                os.fsync(dir_fd)
            except OSError as exc:
                logger.warning("dir fsync failed for %s: %s", path.parent, exc)
            finally:
                os.close(dir_fd)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


def atomic_write_bytes(
    path: Path,
    content: bytes,
    *,
    fsync: bool = True,
) -> None:
    """Byte-level twin of `atomic_write_text`. Use for rollback paths or for
    writers that must round-trip arbitrary (possibly non-UTF-8) source bytes.

    Same atomicity guarantees: tmp + fsync + replace + best-effort dir fsync,
    cleanup-on-failure, raises up to and including `os.replace`. Caller must
    hold the runtime write lock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp.{os.getpid()}.{time.monotonic_ns()}"
    try:
        with tmp.open("wb") as handle:
            handle.write(content)
            handle.flush()
            if fsync:
                os.fsync(handle.fileno())
        os.replace(tmp, path)
        if fsync:
            try:
                dir_fd = os.open(path.parent, os.O_DIRECTORY)
            except OSError:
                return
            try:
                os.fsync(dir_fd)
            except OSError as exc:
                logger.warning("dir fsync failed for %s: %s", path.parent, exc)
            finally:
                os.close(dir_fd)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


def atomic_copy_file(src: Path, dst: Path, *, fsync: bool = True) -> None:
    """Copy file atomically: tmp copy + fsync + replace + best-effort dir fsync.

    Like atomic_write_text but for file-to-file copy. Does NOT preserve
    src mtime/permissions — ingest pipelines compute their own imported_at
    and permissions are not part of raw-layer semantics. Raises on any
    failure up to and including `os.replace`; cleans tmp.

    Directory fsync is best-effort (logged, not re-raised) once replace
    succeeds. See atomic_write_text for the same caveat.

    Caller must hold runtime_write_lock when writing to authoritative
    state (e.g. raw/). Same tmp-residue caveat as atomic_write_text:
    consumers scanning the destination directory must skip files matching
    `is_atomic_write_tmp_path()` (strict trailing `.tmp.<digits>.<digits>`).
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.parent / f"{dst.name}.tmp.{os.getpid()}.{time.monotonic_ns()}"
    try:
        with src.open("rb") as src_handle, tmp.open("wb") as tmp_handle:
            shutil.copyfileobj(src_handle, tmp_handle)
            tmp_handle.flush()
            if fsync:
                os.fsync(tmp_handle.fileno())
        os.replace(tmp, dst)
        if fsync:
            try:
                dir_fd = os.open(dst.parent, os.O_DIRECTORY)
            except OSError:
                return  # platform without O_DIRECTORY; file fsync already done
            try:
                os.fsync(dir_fd)
            except OSError as exc:
                logger.warning("dir fsync failed for %s: %s", dst.parent, exc)
            finally:
                os.close(dir_fd)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


def atomic_append_jsonl(
    path: Path,
    record: dict[str, Any],
    *,
    fsync: bool = True,
) -> None:
    """Append a JSON object as a single line, fsync before return.

    Uses a single ``os.write`` syscall with ``O_APPEND``. Concurrent
    writers are **not** made safe by PIPE_BUF size; callers that share a
    JSONL stream must hold ``runtime_write_lock`` (single-writer model).
    This function does not acquire the lock.

    On partial write / fsync / I/O failure after bytes were appended, the
    file is truncated back to the pre-call size so callers never observe
    a half-written JSONL line from a failed append.

    Raises on non-dict, encode failure, partial write, or I/O failure.
    """
    if not isinstance(record, dict):
        raise TypeError(f"atomic_append_jsonl expects dict, got {type(record).__name__}")
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    size_before = path.stat().st_size if path.exists() else 0
    created = not path.exists()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        try:
            written = os.write(fd, line)
            if written != len(line):
                raise OSError(f"partial write: {written}/{len(line)} bytes")
            if fsync:
                os.fsync(fd)
        except Exception as append_exc:
            os.close(fd)
            fd = -1
            try:
                if created and size_before == 0:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        _durable_truncate(path, 0)
                else:
                    _durable_truncate(path, size_before)
            except Exception as rollback_exc:
                raise OSError(
                    "atomic_append_jsonl failed and rollback also failed: "
                    f"append={append_exc!r}; rollback={rollback_exc!r}"
                ) from append_exc
            raise
    finally:
        if fd >= 0:
            os.close(fd)


def atomic_append_line(
    path: Path,
    line: str,
    *,
    fsync: bool = True,
) -> None:
    """Append a single text line to JSONL file atomically with fsync.

    The line must NOT contain trailing newline; this helper appends it.
    The line must NOT contain embedded newlines (raises ValueError).
    Use this for writers that need a custom serializer (canonical key order, etc.).
    Use atomic_append_jsonl for default sort_keys serialization.
    """
    if "\n" in line:
        raise ValueError("atomic_append_line: line must not contain embedded newlines")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        if fsync:
            os.fsync(handle.fileno())


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == content:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, content, fsync=False)
    return True


def normalize_generated_artifact_content(content: str) -> str:
    return ISO_DATETIME_PATTERN.sub("<ISO_DATETIME>", content)


def write_if_changed_ignoring_timestamps(path: Path, content: str) -> tuple[bool, bool]:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == content:
            return False, False
        if normalize_generated_artifact_content(current) == normalize_generated_artifact_content(content):
            return False, False
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, content, fsync=False)
    return True, True


def render_json_document(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def normalize_generated_state_document(payload: Any) -> Any:
    if isinstance(payload, dict):
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            if (
                key in {"generated_at", "computed_at"}
                and isinstance(value, str)
                and ISO_DATETIME_PATTERN.fullmatch(value)
            ):
                normalized[key] = "<ISO_DATETIME>"
            else:
                normalized[key] = normalize_generated_state_document(value)
        return normalized
    if isinstance(payload, list):
        return [normalize_generated_state_document(item) for item in payload]
    return payload


def write_json_document_if_changed_ignoring_generated_timestamps(
    path: Path, document: dict[str, Any]
) -> tuple[bool, bool]:
    rendered = render_json_document(document)
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == rendered:
            return False, False
        try:
            current_document = json.loads(current)
        except json.JSONDecodeError:
            current_document = None
        if isinstance(current_document, dict):
            if normalize_generated_state_document(current_document) == normalize_generated_state_document(document):
                return False, False
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, rendered, fsync=False)
    return True, True
