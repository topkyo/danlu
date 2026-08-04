from __future__ import annotations

import http.client
import ipaddress
import os
import socket
import ssl
import urllib.request
from pathlib import Path
from typing import NamedTuple
from urllib.error import HTTPError
from urllib.parse import urlparse


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
        return self.do_open(self._make_connection, req, context=self._context)

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
                current, pinned_list = _validate_safe_url(
                    urljoin(current, location), allow_private=allow_private, enforce_allowlist=True
                )
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
