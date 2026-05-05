"""Phase 0 utility helpers extracted from aiwiki.app.

OWNER STATUS: legacy owner. CENTRAL HUB - extra caution required.
Imported by most modules; refactoring causes wide import churn.
Do not refactor this file casually. New large logic blocks should be extracted
to a dedicated subpackage rather than added here. See AGENTS.md migration policy.
"""

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
import socket
import ssl
import tempfile
import threading
import time
import urllib.request
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_RUNTIME_LOCK_GUARD = threading.RLock()


_RUNTIME_LOCKS: dict[str, dict[str, Any]] = {}


TEXT_EXTENSIONS = {
    ".csv",
    ".json",
    ".markdown",
    ".md",
    ".py",
    ".rst",
    ".text",
    ".toml",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}


STOP_WORDS = {
    "about",
    "after",
    "against",
    "and",
    "article",
    "articles",
    "batch",
    "brief",
    "browser",
    # Round 2 P4-9 additions: empirically observed noise tokens from dogfood
    # receipt v0 §F6 (28 dogfood concepts had 11 stop-word-tier slugs).
    "capture",
    "captured",
    "compare",
    "compiled",
    "fast",
    "file",
    "files",
    "figure",
    "five",
    "for",
    "four",
    "from",
    "full",
    "image",
    "images",
    "into",
    "kind",
    "lite",
    "mode",
    "must",
    "note",
    "notes",
    "one",
    "page",
    "pages",
    "question",
    "report",
    "rendered",
    "receipt",
    "receipts",
    "session",
    "slow",
    "smoke",
    "sota",
    "source",
    "sources",
    "slides",
    "sub",
    "task",
    "that",
    "the",
    "their",
    "there",
    "these",
    "three",
    "this",
    "two",
    "with",
    "wiki",
}


PROVENANCE_PATH_PATTERN = re.compile(r"(?:\.\./)*(wiki/sources/[^\s`)\]]+\.md|raw/[^\s`)\]]+)")


ISO_DATETIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\+\d{2}:\d{2}|Z)")


def runtime_lock_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "runtime.lock"


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
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
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


class AuditMirrorError(RuntimeError):
    """Audit mirror append failed; primary file successfully truncated back to pre-call size."""


class AuditMirrorRollbackError(RuntimeError):
    """Audit mirror append failed AND primary truncate also failed; primary in inconsistent state."""


def _durable_truncate(path: Path, size: int) -> None:
    """Durable truncate: open r+b, truncate, flush, fsync. Raises on any IO failure."""
    with open(path, "r+b") as handle:
        handle.truncate(size)
        handle.flush()
        os.fsync(handle.fileno())


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


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    fsync: bool = True,
) -> None:
    """Write text atomically: tmp + fsync + replace + dir fsync.

    Raises on any failure; never leaves half-written content at `path`.
    Cleans up tmp on failure. Does NOT acquire runtime_write_lock — caller
    must hold it (or call from inside @runtime_write_operation).
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


def atomic_append_jsonl(
    path: Path,
    record: dict[str, Any],
    *,
    fsync: bool = True,
) -> None:
    """Append a JSON object as a single line, fsync before return.

    Raises on non-dict, encode failure, or I/O failure. Does NOT acquire
    runtime_write_lock — caller must hold it.
    """
    if not isinstance(record, dict):
        raise TypeError(f"atomic_append_jsonl expects dict, got {type(record).__name__}")
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        if fsync:
            os.fsync(handle.fileno())


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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "item"


def detect_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".txt", ".rst"}:
        return "text"
    if suffix in {".json", ".yaml", ".yml", ".csv", ".tsv", ".toml"}:
        return "data"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if not suffix:
        return "file"
    return suffix.lstrip(".")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def question_signature(question: str) -> str:
    normalized = " ".join(question.lower().split())
    return f"sha256:{sha256_bytes(normalized.encode('utf-8'))}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def next_identifier(existing_ids: set[str], seed: str) -> str:
    candidate = seed
    index = 2
    while candidate in existing_ids:
        candidate = f"{seed}-{index}"
        index += 1
    return candidate


def next_available_stem(directory: Path, seed: str, suffix: str = ".md") -> str:
    candidate = seed
    index = 2
    while (directory / f"{candidate}{suffix}").exists():
        candidate = f"{seed}-{index}"
        index += 1
    return candidate


def read_text_preview(path: Path, limit_lines: int = 12, limit_chars: int = 1600) -> str:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return f"Preview unavailable for {path.suffix or 'unknown'} files."
    text = strip_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    preview = "\n".join(text.splitlines()[:limit_lines]).strip()
    if len(preview) > limit_chars:
        preview = preview[:limit_chars].rstrip() + "..."
    return preview or "(empty text file)"


def raw_note_metadata(path: Path) -> dict[str, str]:
    if path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        return {}
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    result: dict[str, str] = {}
    for key in ("title", "source_type", "original_path", "note_kind"):
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    return result


def render_scalar(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def render_frontmatter(mapping: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in mapping.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {render_scalar(item)}")
        else:
            lines.append(f"{key}: {render_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def parse_scalar(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value.strip('"')
    return value


def parse_frontmatter(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("  - ") and current_key is not None:
            data.setdefault(current_key, []).append(parse_scalar(line[4:]))
            continue
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        raw = raw.strip()
        if raw:
            data[key] = parse_scalar(raw)
            current_key = None
        else:
            data[key] = []
            current_key = key
    return data


def strip_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[index + 1 :]).lstrip()
    return text


def upsert_markdown_section(markdown: str, heading: str, content: str) -> str:
    section = content.strip()
    block = f"## {heading}\n{section}\n"
    pattern = rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    if re.search(pattern, markdown):
        updated = re.sub(pattern, block + "\n", markdown).strip()
        return updated + "\n"
    base = markdown.rstrip()
    if base:
        return base + "\n\n" + block
    return block


def normalize_workspace_path(value: str) -> str:
    normalized = value.strip().strip("'\"`")
    while normalized.startswith("../"):
        normalized = normalized[3:]
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip(".,;:")


def extract_provenance_paths(root: Path, markdown: str) -> list[str]:
    frontmatter = parse_frontmatter(markdown)
    candidates: list[str] = []
    for key in ("citations", "source_files"):
        value = frontmatter.get(key, [])
        if isinstance(value, list):
            candidates.extend(str(item) for item in value if isinstance(item, str))
    candidates.extend(match.group(1) for match in PROVENANCE_PATH_PATTERN.finditer(markdown))

    normalized_paths: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        path = normalize_workspace_path(candidate)
        if not path.startswith(("wiki/sources/", "raw/")):
            continue
        if not (root / path).exists():
            continue
        if path in seen:
            continue
        seen.add(path)
        normalized_paths.append(path)
    return normalized_paths


def evidence_path_digest(root: Path, relative: str) -> str:
    path = root / relative
    if not path.exists():
        return ""
    if relative.startswith("wiki/sources/"):
        return compiled_source_sha(path.read_text(encoding="utf-8", errors="replace"))
    if path.is_file():
        return sha256_file(path)
    return ""


def build_citation_snapshots(root: Path, citations: list[str]) -> list[str]:
    snapshots: list[str] = []
    seen: set[str] = set()
    for citation in citations:
        normalized = normalize_workspace_path(str(citation))
        if not normalized or normalized in seen:
            continue
        digest = evidence_path_digest(root, normalized)
        if not digest:
            continue
        seen.add(normalized)
        snapshots.append(f"{normalized}#{digest}")
    return snapshots


def parse_citation_snapshots(frontmatter: dict[str, Any]) -> dict[str, str]:
    snapshots: dict[str, str] = {}
    raw_value = frontmatter.get("citation_snapshots", [])
    if not isinstance(raw_value, list):
        return snapshots
    for item in raw_value:
        if not isinstance(item, str) or "#" not in item:
            continue
        relative, digest = item.rsplit("#", 1)
        relative = normalize_workspace_path(relative)
        if not relative or not digest:
            continue
        snapshots[relative] = digest
    return snapshots


def analyze_citation_snapshots(
    root: Path,
    citations: list[str],
    frontmatter: dict[str, Any],
) -> dict[str, Any]:
    current = {
        snapshot.rsplit("#", 1)[0]: snapshot.rsplit("#", 1)[1]
        for snapshot in build_citation_snapshots(root, citations)
        if "#" in snapshot
    }
    recorded = parse_citation_snapshots(frontmatter)
    drifted = sorted(path for path, digest in current.items() if recorded.get(path) and recorded[path] != digest)
    missing = sorted(path for path in current if path not in recorded)
    stale = sorted(path for path in recorded if path not in current)
    return {
        "current": current,
        "recorded": recorded,
        "drifted": drifted,
        "missing": missing,
        "stale": stale,
        "has_drift": bool(drifted or missing or stale),
    }


def replace_first_markdown_heading(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            lines[index] = f"# {title}"
            return "\n".join(lines).strip() + "\n"
    body = markdown.strip()
    if body:
        return f"# {title}\n\n{body}\n"
    return f"# {title}\n"


def first_markdown_heading(markdown: str) -> str:
    for line in strip_frontmatter(markdown).splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == content:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
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
    path.write_text(content, encoding="utf-8")
    return True, True


def render_json_document(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def normalize_generated_state_document(payload: Any) -> Any:
    if isinstance(payload, dict):
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            if key in {"generated_at", "computed_at"} and isinstance(value, str) and ISO_DATETIME_PATTERN.fullmatch(value):
                normalized[key] = "<ISO_DATETIME>"
            else:
                normalized[key] = normalize_generated_state_document(value)
        return normalized
    if isinstance(payload, list):
        return [normalize_generated_state_document(item) for item in payload]
    return payload


def write_json_document_if_changed_ignoring_generated_timestamps(path: Path, document: dict[str, Any]) -> tuple[bool, bool]:
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
    path.write_text(rendered, encoding="utf-8")
    return True, True


def compiled_source_sha(markdown: str) -> str:
    if not markdown:
        return ""
    frontmatter = parse_frontmatter(markdown)
    sha = frontmatter.get("source_sha256")
    if isinstance(sha, str) and sha:
        return sha
    match = re.search(r"(?m)^- SHA256: `([^`]+)`", markdown)
    if match:
        return match.group(1)
    return ""


def html_safe_json_literal(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


_BATCH_TAG_PATTERN = re.compile(r"^round\d+$")
_TIMESTAMP_FRAGMENT_PATTERN = re.compile(r"^\d{2,}t\d{2,}$")
# P4-INV-2 (Round 57): filter quarter tokens like `2024q1` / `q42025` that pollute
# investing-protocol concept extraction. Empirical: NVDA dogfood note surfaced
# `2025q4` as a concept slug, see dogfood-receipt-investing-v0 §F-INV-5.
_QUARTER_TAG_PATTERN = re.compile(r"^(?:[12]\d{3}q[1-4]|q[1-4][12]\d{3})$")


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [
        token
        for token in tokens
        if len(token) > 2
        and not token.isdigit()
        and token not in STOP_WORDS
        and not _BATCH_TAG_PATTERN.match(token)
        and not _TIMESTAMP_FRAGMENT_PATTERN.match(token)
        and not _QUARTER_TAG_PATTERN.match(token)
    ]


class FetchPolicyError(ValueError):
    """Raised when a fetch is rejected by safety policy (SSRF / size / scheme)."""


class PathOutsideWorkspaceError(ValueError):
    """Raised when a resolved path falls outside the allowed workspace root."""


class _PinnedAddress(NamedTuple):
    family: int
    ip: str


_PRIVATE_NETS_V4 = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
)
_PRIVATE_NETS_V6 = (
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::/128"),
)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, *args, _pinned_ips: list[str] | None = None, **kwargs):
        super().__init__(host, *args, **kwargs)
        self._pinned_ips = list(_pinned_ips) if _pinned_ips else []

    def connect(self):
        if not self._pinned_ips:
            raise FetchPolicyError("missing pinned IPs")
        last_exc: OSError | None = None
        sock = None
        for ip in self._pinned_ips:
            try:
                sock = socket.create_connection((ip, self.port), self.timeout, self.source_address)
                break
            except OSError as exc:
                last_exc = exc
                continue
        if sock is None:
            assert last_exc is not None
            raise last_exc
        self.sock = sock
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, *args, _pinned_ips: list[str] | None = None, **kwargs):
        super().__init__(host, *args, **kwargs)
        self._pinned_ips = list(_pinned_ips) if _pinned_ips else []

    def connect(self):
        if not self._pinned_ips:
            raise FetchPolicyError("missing pinned IPs")
        last_exc: OSError | None = None
        sock = None
        for ip in self._pinned_ips:
            try:
                sock = socket.create_connection((ip, self.port), self.timeout, self.source_address)
                break
            except OSError as exc:
                last_exc = exc
                continue
        if sock is None:
            assert last_exc is not None
            raise last_exc
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
            sock = self.sock
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, pinned_ips: list[str]):
        super().__init__()
        self._pinned_ips = list(pinned_ips)

    def http_open(self, req):
        return self.do_open(self._make_connection, req)

    def _make_connection(self, host, *args, **kwargs):
        return _PinnedHTTPConnection(host, *args, _pinned_ips=self._pinned_ips, **kwargs)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(
        self,
        pinned_ips: list[str],
        debuglevel: int = 0,
        context: ssl.SSLContext | None = None,
        check_hostname: bool | None = None,
    ):
        super().__init__(debuglevel=debuglevel, context=context, check_hostname=check_hostname)
        self._pinned_ips = list(pinned_ips)

    def https_open(self, req):
        return self.do_open(self._make_connection, req, context=self._context, check_hostname=self._check_hostname)

    def _make_connection(self, host, *args, **kwargs):
        return _PinnedHTTPSConnection(host, *args, _pinned_ips=self._pinned_ips, **kwargs)


def _ip_is_private_or_link_local(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in net for net in _PRIVATE_NETS_V4)
    return any(ip in net for net in _PRIVATE_NETS_V6)


def _resolve_and_check_host(host: str, port: int | None, *, allow_private: bool) -> list[_PinnedAddress]:
    """Resolve host once, reject private/link-local answers unless allowed, and return pinned IPs."""
    try:
        infos = socket.getaddrinfo(host, port)
    except socket.gaierror as exc:
        raise FetchPolicyError(f"DNS resolution failed for {host!r}: {exc}") from exc
    pinned: list[_PinnedAddress] = []
    seen: set[tuple[int, str]] = set()
    for family, _type, _proto, _canon, sockaddr in infos:
        addr = sockaddr[0].split("%")[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        # Normalize IPv4-mapped IPv6 (::ffff:x.x.x.x) to IPv4 to avoid bypass.
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
            family = socket.AF_INET
        if _ip_is_private_or_link_local(ip) and not allow_private:
            raise FetchPolicyError(f"private/link-local host rejected: {host}")
        item = (family, str(ip))
        if item not in seen:
            seen.add(item)
            pinned.append(_PinnedAddress(family=family, ip=str(ip)))
    if not pinned:
        raise FetchPolicyError(f"DNS resolution returned no usable addresses for {host!r}")
    return pinned


def _is_private_address(host: str) -> bool:
    """Resolve `host` and return True if any A/AAAA record is private/link-local."""
    try:
        _resolve_and_check_host(host, None, allow_private=False)
    except FetchPolicyError as exc:
        if "private/link-local" in str(exc):
            return True
        raise
    return False


def _get_safe_fetch_host_allowlist() -> frozenset[str]:
    raw = os.environ.get("AIWIKI_SAFE_FETCH_HOST_ALLOWLIST", "")
    return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())


def _validate_safe_url(
    url: str,
    *,
    allow_private: bool = False,
    enforce_allowlist: bool = False,
) -> tuple[str, list[_PinnedAddress]]:
    """Validate scheme + host policy. Returns normalized url and pinned addresses.

    `enforce_allowlist` is opt-in for `safe_fetch` only; browser renderer guards
    in `drop.py` keep their original behavior (allowlist is a fetch-only knob).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchPolicyError(f"only http(s) scheme allowed, got {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise FetchPolicyError(f"missing host in url: {url!r}")
    if enforce_allowlist:
        allowlist = _get_safe_fetch_host_allowlist()
        if allowlist and host.lower() not in allowlist:
            raise FetchPolicyError(f"host not in allowlist: {host}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return url, _resolve_and_check_host(host, port, allow_private=allow_private)


def safe_fetch(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    max_bytes: int,
    timeout: float,
    allow_private: bool = False,
    max_redirects: int = 5,
) -> tuple[bytes, str]:
    """HTTP/HTTPS fetch with SSRF defense + size cap."""
    from urllib.parse import urljoin

    def _strip_auth_headers(source: dict[str, str]) -> dict[str, str]:
        sensitive = {"authorization", "x-api-key", "cookie"}
        return {key: value for key, value in source.items() if key.lower() not in sensitive}

    current, pinned_list = _validate_safe_url(url, allow_private=allow_private, enforce_allowlist=True)
    current_headers = dict(headers or {})
    if not any(key.lower() == "user-agent" for key in current_headers):
        current_headers["User-Agent"] = "aiwiki/0.1 (+https://local)"
    redirects = 0
    previous_host: str | None = None
    while True:
        pinned_ips = [addr.ip for addr in pinned_list]
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirectHandler(),
            _PinnedHTTPHandler(pinned_ips),
            _PinnedHTTPSHandler(pinned_ips),
        )
        current_host = urlparse(current).hostname
        if previous_host is not None and current_host != previous_host:
            current_headers = _strip_auth_headers(current_headers)
        previous_host = current_host
        req = urllib.request.Request(current, data=data, method=method)
        for key, value in current_headers.items():
            req.add_header(key, value)
        try:
            raw_resp = opener.open(req, timeout=timeout)
        except HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                if redirects >= max_redirects:
                    raise FetchPolicyError(f"too many redirects (max_redirects={max_redirects})") from exc
                location = exc.headers.get("Location")
                if not location:
                    raise
                current, pinned_list = _validate_safe_url(urljoin(current, location), allow_private=allow_private, enforce_allowlist=True)
                redirects += 1
                continue
            raise
        with raw_resp as resp:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = resp.read(min(65536, max_bytes - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise FetchPolicyError(f"response exceeds max_bytes={max_bytes}")
                chunks.append(chunk)
            final_url = resp.geturl() if hasattr(resp, "geturl") else current
            safe_final_url, _ = _validate_safe_url(final_url, allow_private=allow_private, enforce_allowlist=True)
            return b"".join(chunks), safe_final_url


class _NoRedirectHandler(__import__("urllib.request", fromlist=["HTTPRedirectHandler"]).HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def safe_resolve_within(path, root) -> Path:
    """Resolve `path`, ensure it lies within `root.resolve()` after symlink resolution."""
    resolved = Path(path).expanduser().resolve()
    root_resolved = Path(root).resolve()
    if resolved == root_resolved:
        return resolved
    if root_resolved not in resolved.parents:
        raise PathOutsideWorkspaceError(f"{resolved} not within {root_resolved}")
    return resolved
