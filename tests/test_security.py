"""Offline tests for aiwiki.utils.security — the repo's SSRF / fetch-policy boundary.

Strategy: absolutely no real network or DNS. ``socket.getaddrinfo`` and
``urllib.request.build_opener`` are patched (via the ``aiwiki.utils.security``
module namespace, which holds references to the real stdlib modules) and
``socket.create_connection`` is faked for the pinned-connection classes.

Covers:
- scheme / host / allowlist validation in ``_validate_safe_url``
- DNS resolution + private/link-local rejection (incl. IPv4-mapped IPv6
  normalization) in ``_resolve_and_check_host``
- ``safe_fetch`` happy path, max_bytes cap, redirect auth-header stripping,
  redirect limits, redirect revalidation, POST passthrough
- pinned HTTP/HTTPS connection classes (pinned-IP dial, failover, tunneling)
- ``safe_resolve_within`` symlink-aware containment
- ``_is_private_address`` helper
"""

from __future__ import annotations

import socket
from unittest import mock
from urllib.error import HTTPError

import pytest

from aiwiki.utils.security import (
    FetchPolicyError,
    PathOutsideWorkspaceError,
    _is_private_address,
    _NoRedirectHandler,
    _PinnedAddress,
    _PinnedHTTPConnection,
    _PinnedHTTPHandler,
    _PinnedHTTPSConnection,
    _PinnedHTTPSHandler,
    _resolve_and_check_host,
    _validate_safe_url,
    safe_fetch,
    safe_resolve_within,
)

_GETADDRINFO = "aiwiki.utils.security.socket.getaddrinfo"
_CREATE_CONNECTION = "aiwiki.utils.security.socket.create_connection"
_BUILD_OPENER = "aiwiki.utils.security.urllib.request.build_opener"

# Documentation-range IPs (RFC 5737 / RFC 3849): public per this module's
# private-net lists, and never routable so nothing leaks even if a patch fails.
PUBLIC_V4 = "192.0.2.1"
PUBLIC_V4_B = "192.0.2.2"
PUBLIC_V6 = "2001:db8::1"


@pytest.fixture(autouse=True)
def _clear_allowlist_env(monkeypatch):
    """Keep the developer's shell env from leaking into fetch-policy tests."""
    monkeypatch.delenv("AIWIKI_SAFE_FETCH_HOST_ALLOWLIST", raising=False)


def _gai_entries(*ips: str) -> list[tuple]:
    """Build fake getaddrinfo() results for the given IP literals."""
    infos = []
    for ip in ips:
        if ":" in ip:
            infos.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 0, 0, 0)))
        else:
            infos.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)))
    return infos


def _resolver(mapping: dict[str, list[str]]):
    """getaddrinfo side_effect resolving hosts from a static mapping."""

    def _resolve(host, port):
        if host not in mapping:
            raise socket.gaierror(f"Name or service not known: {host}")
        return _gai_entries(*mapping[host])

    return _resolve


class _FakeResponse:
    """Minimal addinfourl stand-in: read() chunks, geturl(), context manager."""

    def __init__(self, chunks: list[bytes], url: str):
        self._chunks = list(chunks)
        self._url = url

    def read(self, size: int = -1) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeOpener:
    """Opener stand-in: plays a scripted list of responses / exceptions."""

    def __init__(self, actions: list):
        self._actions = list(actions)
        self.requests: list = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        action = self._actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


def _redirect(location: str | None, code: int = 302) -> HTTPError:
    headers = {"Location": location} if location else {}
    return HTTPError("http://example.com/", code, "Found", headers, None)


def _run_fetch(opener: _FakeOpener, mapping: dict[str, list[str]], **kwargs):
    with mock.patch(_GETADDRINFO, side_effect=_resolver(mapping)):
        with mock.patch(_BUILD_OPENER, return_value=opener):
            return safe_fetch(**kwargs)


def _header_dict(req) -> dict[str, str]:
    return {key.lower(): value for key, value in req.headers.items()}


class TestValidateSafeUrl:
    def test_rejects_ftp_scheme(self):
        with pytest.raises(FetchPolicyError, match="only http"):
            _validate_safe_url("ftp://example.com/file")

    def test_rejects_file_scheme(self):
        with pytest.raises(FetchPolicyError, match="only http"):
            _validate_safe_url("file:///etc/passwd")

    def test_rejects_missing_host(self):
        with pytest.raises(FetchPolicyError, match="missing host"):
            _validate_safe_url("http:///path-only")

    @pytest.mark.parametrize(
        "ip",
        ["127.0.0.1", "10.1.2.3", "192.168.1.1", "172.16.5.5", "169.254.1.1", "0.1.2.3"],
    )
    def test_rejects_private_ipv4(self, ip):
        with mock.patch(_GETADDRINFO, return_value=_gai_entries(ip)):
            with pytest.raises(FetchPolicyError, match="private/link-local"):
                _validate_safe_url("http://internal.example/")

    @pytest.mark.parametrize("ip", ["::1", "fc00::1", "fd00::1", "fe80::1", "fe80::1%eth0"])
    def test_rejects_private_ipv6(self, ip):
        with mock.patch(_GETADDRINFO, return_value=_gai_entries(ip)):
            with pytest.raises(FetchPolicyError, match="private/link-local"):
                _validate_safe_url("http://internal.example/")

    def test_rejects_ipv4_mapped_ipv6_loopback(self):
        # ::ffff:127.0.0.1 must be normalized to IPv4 and rejected, not waved through.
        with mock.patch(_GETADDRINFO, return_value=_gai_entries("::ffff:127.0.0.1")):
            with pytest.raises(FetchPolicyError, match="private/link-local"):
                _validate_safe_url("http://sneaky.example/")

    def test_accepts_ipv4_mapped_public_and_normalizes_family(self):
        with mock.patch(_GETADDRINFO, return_value=_gai_entries("::ffff:192.0.2.1")):
            _url, pinned = _validate_safe_url("http://example.com/")
        assert pinned == [_PinnedAddress(family=socket.AF_INET, ip=PUBLIC_V4)]

    def test_dns_failure_raises_fetch_policy_error(self):
        with mock.patch(_GETADDRINFO, side_effect=socket.gaierror("boom")):
            with pytest.raises(FetchPolicyError, match="DNS resolution failed"):
                _validate_safe_url("http://nope.example/")

    def test_no_usable_addresses_raises(self):
        infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("not-an-ip", 0))]
        with mock.patch(_GETADDRINFO, return_value=infos):
            with pytest.raises(FetchPolicyError, match="no usable addresses"):
                _validate_safe_url("http://weird.example/")

    def test_public_ip_accepted_and_duplicates_collapsed(self):
        entries = _gai_entries(PUBLIC_V4, PUBLIC_V4, PUBLIC_V4_B)
        with mock.patch(_GETADDRINFO, return_value=entries):
            url, pinned = _validate_safe_url("http://example.com/path?q=1")
        assert url == "http://example.com/path?q=1"
        assert pinned == [
            _PinnedAddress(family=socket.AF_INET, ip=PUBLIC_V4),
            _PinnedAddress(family=socket.AF_INET, ip=PUBLIC_V4_B),
        ]

    def test_public_ipv6_accepted(self):
        with mock.patch(_GETADDRINFO, return_value=_gai_entries(PUBLIC_V6)):
            _url, pinned = _validate_safe_url("http://example.com/")
        assert pinned == [_PinnedAddress(family=socket.AF_INET6, ip=PUBLIC_V6)]

    def test_https_default_port_443(self):
        with mock.patch(_GETADDRINFO, return_value=_gai_entries(PUBLIC_V4)) as mocked:
            _validate_safe_url("https://example.com/")
        mocked.assert_called_once_with("example.com", 443)

    def test_explicit_port_passed_through(self):
        with mock.patch(_GETADDRINFO, return_value=_gai_entries(PUBLIC_V4)) as mocked:
            _validate_safe_url("http://example.com:8080/")
        mocked.assert_called_once_with("example.com", 8080)

    def test_allow_private_permits_private_host(self):
        with mock.patch(_GETADDRINFO, return_value=_gai_entries("127.0.0.1")):
            _url, pinned = _validate_safe_url("http://localhost/", allow_private=True)
        assert pinned == [_PinnedAddress(family=socket.AF_INET, ip="127.0.0.1")]

    def test_allowlist_rejects_unlisted_host(self, monkeypatch):
        monkeypatch.setenv("AIWIKI_SAFE_FETCH_HOST_ALLOWLIST", "example.com, foo.bar")
        with pytest.raises(FetchPolicyError, match="not in allowlist"):
            _validate_safe_url("http://evil.example/", enforce_allowlist=True)

    def test_allowlist_accepts_listed_host_case_insensitively(self, monkeypatch):
        monkeypatch.setenv("AIWIKI_SAFE_FETCH_HOST_ALLOWLIST", "Example.COM")
        with mock.patch(_GETADDRINFO, return_value=_gai_entries(PUBLIC_V4)):
            url, _pinned = _validate_safe_url("http://example.com/", enforce_allowlist=True)
        assert url == "http://example.com/"

    def test_empty_allowlist_does_not_constrain(self):
        with mock.patch(_GETADDRINFO, return_value=_gai_entries(PUBLIC_V4)):
            url, _pinned = _validate_safe_url("http://anything.example/", enforce_allowlist=True)
        assert url == "http://anything.example/"


class TestResolveAndCheckHost:
    def test_returns_pinned_addresses(self):
        with mock.patch(_GETADDRINFO, return_value=_gai_entries(PUBLIC_V4)):
            pinned = _resolve_and_check_host("example.com", 80, allow_private=False)
        assert pinned == [_PinnedAddress(family=socket.AF_INET, ip=PUBLIC_V4)]


class TestIsPrivateAddress:
    def test_true_for_private_host(self):
        with mock.patch(_GETADDRINFO, return_value=_gai_entries("10.0.0.1")):
            assert _is_private_address("internal.example") is True

    def test_false_for_public_host(self):
        with mock.patch(_GETADDRINFO, return_value=_gai_entries(PUBLIC_V4)):
            assert _is_private_address("example.com") is False

    def test_propagates_dns_failure(self):
        with mock.patch(_GETADDRINFO, side_effect=socket.gaierror("boom")):
            with pytest.raises(FetchPolicyError, match="DNS resolution failed"):
                _is_private_address("nope.example")


class TestSafeFetch:
    def test_happy_path_returns_body_final_url_and_default_user_agent(self):
        opener = _FakeOpener([_FakeResponse([b"hello ", b"world"], "http://example.com/page")])
        body, final_url = _run_fetch(
            opener,
            {"example.com": [PUBLIC_V4]},
            url="http://example.com/page",
            max_bytes=1024,
            timeout=5.0,
        )
        assert body == b"hello world"
        assert final_url == "http://example.com/page"
        assert len(opener.requests) == 1
        headers = _header_dict(opener.requests[0])
        assert headers["user-agent"] == "aiwiki/0.1 (+https://local)"

    def test_max_bytes_exceeded_raises(self):
        opener = _FakeOpener([_FakeResponse([b"x" * 10], "http://example.com/")])
        with pytest.raises(FetchPolicyError, match="exceeds max_bytes"):
            _run_fetch(
                opener,
                {"example.com": [PUBLIC_V4]},
                url="http://example.com/",
                max_bytes=4,
                timeout=5.0,
            )

    def test_same_host_redirect_preserves_authorization(self):
        opener = _FakeOpener([
            _redirect("/b"),
            _FakeResponse([b"ok"], "http://example.com/b"),
        ])
        body, final_url = _run_fetch(
            opener,
            {"example.com": [PUBLIC_V4]},
            url="http://example.com/a",
            max_bytes=100,
            timeout=5.0,
            headers={"Authorization": "Bearer token"},
        )
        assert body == b"ok"
        assert final_url == "http://example.com/b"
        assert len(opener.requests) == 2
        assert opener.requests[1].full_url == "http://example.com/b"
        assert _header_dict(opener.requests[1])["authorization"] == "Bearer token"

    def test_cross_host_redirect_strips_sensitive_headers(self):
        opener = _FakeOpener([
            _redirect("http://b.example/landing"),
            _FakeResponse([b"ok"], "http://b.example/landing"),
        ])
        body, _final_url = _run_fetch(
            opener,
            {"a.example": [PUBLIC_V4], "b.example": [PUBLIC_V4_B]},
            url="http://a.example/start",
            max_bytes=100,
            timeout=5.0,
            headers={
                "Authorization": "Bearer token",
                "X-API-Key": "secret",
                "Cookie": "session=abc",
                "X-Keep": "yes",
            },
        )
        assert body == b"ok"
        assert len(opener.requests) == 2
        first = _header_dict(opener.requests[0])
        assert {"authorization", "x-api-key", "cookie", "x-keep"} <= set(first)
        second = _header_dict(opener.requests[1])
        assert "authorization" not in second
        assert "x-api-key" not in second
        assert "cookie" not in second
        assert second["x-keep"] == "yes"

    def test_too_many_redirects_raises(self):
        opener = _FakeOpener([_redirect("/2"), _redirect("/3")])
        with pytest.raises(FetchPolicyError, match="too many redirects"):
            _run_fetch(
                opener,
                {"example.com": [PUBLIC_V4]},
                url="http://example.com/1",
                max_bytes=100,
                timeout=5.0,
                max_redirects=1,
            )

    def test_redirect_to_private_host_rejected_on_revalidation(self):
        opener = _FakeOpener([_redirect("http://internal.example/")])
        mapping = {"example.com": [PUBLIC_V4], "internal.example": ["10.0.0.9"]}
        with pytest.raises(FetchPolicyError, match="private/link-local"):
            _run_fetch(
                opener,
                mapping,
                url="http://example.com/",
                max_bytes=100,
                timeout=5.0,
            )

    def test_redirect_without_location_reraises_http_error(self):
        opener = _FakeOpener([_redirect(None, code=301)])
        with pytest.raises(HTTPError):
            _run_fetch(
                opener,
                {"example.com": [PUBLIC_V4]},
                url="http://example.com/",
                max_bytes=100,
                timeout=5.0,
            )

    def test_non_redirect_http_error_reraises(self):
        opener = _FakeOpener([HTTPError("http://example.com/", 404, "Not Found", {}, None)])
        with pytest.raises(HTTPError):
            _run_fetch(
                opener,
                {"example.com": [PUBLIC_V4]},
                url="http://example.com/",
                max_bytes=100,
                timeout=5.0,
            )

    def test_post_passes_data_method_and_headers_through(self):
        opener = _FakeOpener([_FakeResponse([b"{}"], "http://example.com/api")])
        body, _final_url = _run_fetch(
            opener,
            {"example.com": [PUBLIC_V4]},
            url="http://example.com/api",
            method="POST",
            data=b"payload",
            headers={"Content-Type": "application/json", "User-Agent": "custom/1.0"},
            max_bytes=100,
            timeout=5.0,
        )
        assert body == b"{}"
        req = opener.requests[0]
        assert req.data == b"payload"
        assert req.method == "POST"
        headers = _header_dict(req)
        assert headers["content-type"] == "application/json"
        # A caller-supplied User-Agent must not be overwritten by the default.
        assert headers["user-agent"] == "custom/1.0"

    def test_safe_fetch_enforces_allowlist_env(self, monkeypatch):
        monkeypatch.setenv("AIWIKI_SAFE_FETCH_HOST_ALLOWLIST", "allowed.example")
        opener = _FakeOpener([])
        with pytest.raises(FetchPolicyError, match="not in allowlist"):
            _run_fetch(
                opener,
                {"blocked.example": [PUBLIC_V4]},
                url="http://blocked.example/",
                max_bytes=10,
                timeout=1.0,
            )


class TestPinnedConnections:
    def test_http_connect_dials_pinned_ip(self):
        conn = _PinnedHTTPConnection("example.com", _pinned_ips=[PUBLIC_V4])
        fake_sock = mock.Mock()
        with mock.patch(_CREATE_CONNECTION, return_value=fake_sock) as mocked:
            conn.connect()
        assert conn.sock is fake_sock
        assert mocked.call_args[0][0] == (PUBLIC_V4, 80)

    def test_http_connect_fails_over_to_second_ip(self):
        conn = _PinnedHTTPConnection("example.com", _pinned_ips=[PUBLIC_V4, PUBLIC_V4_B])
        fake_sock = mock.Mock()
        with mock.patch(_CREATE_CONNECTION, side_effect=[OSError("refused"), fake_sock]) as mocked:
            conn.connect()
        assert conn.sock is fake_sock
        assert mocked.call_count == 2
        assert mocked.call_args[0][0] == (PUBLIC_V4_B, 80)

    def test_http_connect_all_ips_fail_raises_last_error(self):
        conn = _PinnedHTTPConnection("example.com", _pinned_ips=[PUBLIC_V4, PUBLIC_V4_B])
        with mock.patch(_CREATE_CONNECTION, side_effect=OSError("down")):
            with pytest.raises(OSError, match="down"):
                conn.connect()

    def test_http_connect_without_pinned_ips_raises(self):
        conn = _PinnedHTTPConnection("example.com", _pinned_ips=[])
        with pytest.raises(FetchPolicyError, match="missing pinned IPs"):
            conn.connect()

    def test_http_connect_tunnels_when_configured(self):
        conn = _PinnedHTTPConnection("example.com", _pinned_ips=[PUBLIC_V4])
        conn._tunnel_host = "proxy.example"
        conn._tunnel = mock.Mock()
        with mock.patch(_CREATE_CONNECTION, return_value=mock.Mock()):
            conn.connect()
        conn._tunnel.assert_called_once_with()

    def test_https_connect_wraps_socket_with_tls(self):
        context = mock.Mock()
        wrapped = mock.Mock(name="tls_sock")
        context.wrap_socket.return_value = wrapped
        conn = _PinnedHTTPSConnection("example.com", context=context, _pinned_ips=[PUBLIC_V4])
        raw = mock.Mock(name="raw_sock")
        with mock.patch(_CREATE_CONNECTION, return_value=raw):
            conn.connect()
        context.wrap_socket.assert_called_once_with(raw, server_hostname="example.com")
        assert conn.sock is wrapped

    def test_https_connect_tunnels_before_wrapping(self):
        context = mock.Mock()
        conn = _PinnedHTTPSConnection("example.com", context=context, _pinned_ips=[PUBLIC_V4])
        tunneled = mock.Mock(name="tunneled_sock")

        def _fake_tunnel():
            conn.sock = tunneled

        conn._tunnel_host = "proxy.example"
        conn._tunnel = mock.Mock(side_effect=_fake_tunnel)
        with mock.patch(_CREATE_CONNECTION, return_value=mock.Mock(name="raw_sock")):
            conn.connect()
        conn._tunnel.assert_called_once_with()
        context.wrap_socket.assert_called_once_with(tunneled, server_hostname="example.com")

    def test_https_connect_all_ips_fail_raises_last_error(self):
        conn = _PinnedHTTPSConnection("example.com", context=mock.Mock(), _pinned_ips=[PUBLIC_V4])
        with mock.patch(_CREATE_CONNECTION, side_effect=OSError("down")):
            with pytest.raises(OSError, match="down"):
                conn.connect()

    def test_https_connect_without_pinned_ips_raises(self):
        conn = _PinnedHTTPSConnection("example.com", context=mock.Mock(), _pinned_ips=[])
        with pytest.raises(FetchPolicyError, match="missing pinned IPs"):
            conn.connect()


class TestPinnedHandlers:
    def test_http_handler_builds_pinned_connection(self):
        handler = _PinnedHTTPHandler([PUBLIC_V4])
        conn = handler._make_connection("example.com")
        assert isinstance(conn, _PinnedHTTPConnection)
        assert conn._pinned_ips == [PUBLIC_V4]

    def test_https_handler_builds_pinned_connection(self):
        handler = _PinnedHTTPSHandler([PUBLIC_V4], context=mock.Mock())
        conn = handler._make_connection("example.com")
        assert isinstance(conn, _PinnedHTTPSConnection)
        assert conn._pinned_ips == [PUBLIC_V4]

    def test_no_redirect_handler_declines_redirects(self):
        handler = _NoRedirectHandler()
        assert handler.redirect_request(None, None, 302, "Found", {}, "http://example.com/") is None


class TestSafeResolveWithin:
    def test_inside_path_ok(self, tmp_path):
        root = tmp_path / "root"
        target = root / "sub" / "file.txt"
        target.parent.mkdir(parents=True)
        target.touch()
        assert safe_resolve_within(target, root) == target.resolve()

    def test_root_itself_ok(self, tmp_path):
        assert safe_resolve_within(tmp_path, tmp_path) == tmp_path.resolve()

    def test_outside_path_raises(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside.txt"
        outside.touch()
        with pytest.raises(PathOutsideWorkspaceError, match="not within"):
            safe_resolve_within(outside, root)

    def test_symlink_escape_raises(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        link = root / "link"
        link.symlink_to(outside)
        with pytest.raises(PathOutsideWorkspaceError, match="not within"):
            safe_resolve_within(link / "file.txt", root)
