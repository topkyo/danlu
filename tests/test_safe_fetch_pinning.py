from __future__ import annotations

import os
import socket
import unittest
from http import HTTPStatus
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from aiwiki.app_utils import FetchPolicyError, _validate_safe_url, safe_fetch


class SafeFetchPinningTests(unittest.TestCase):
    def _dns(self, ip: str, family: int = socket.AF_INET):
        return [(family, socket.SOCK_STREAM, 6, "", (ip, 443 if family == socket.AF_INET6 else 80))]

    def _response(self, url: str = "http://example.com/data", body: bytes = b"ok"):
        resp = MagicMock()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        resp.geturl = MagicMock(return_value=url)
        chunks = iter([body, b""])
        resp.read = MagicMock(side_effect=lambda _size: next(chunks))
        return resp

    def _fake_http_response(self, *args, **kwargs):
        del args, kwargs
        return self._response()

    def test_dns_returns_private_rejected(self) -> None:
        with patch.object(socket, "getaddrinfo", return_value=self._dns("127.0.0.1")):
            with self.assertRaisesRegex(FetchPolicyError, "private/link-local"):
                _validate_safe_url("http://example.com/data")

    def test_dns_returns_public_pinned(self) -> None:
        with patch.object(socket, "getaddrinfo", return_value=self._dns("93.184.216.34")):
            url, pinned = _validate_safe_url("http://example.com/data")

        self.assertEqual(url, "http://example.com/data")
        self.assertEqual(pinned[0].ip, "93.184.216.34")

    def test_dns_rebinding_attempt_uses_first_pinned_ip(self) -> None:
        connected: list[tuple[str, int]] = []

        def fake_getaddrinfo(host, port):
            del host
            return self._dns("93.184.216.34") if port == 80 else self._dns("127.0.0.1")

        def fake_create_connection(address, timeout=None, source_address=None):
            del timeout, source_address
            connected.append(address)
            raise OSError("stop before network")

        with (
            patch.object(socket, "getaddrinfo", side_effect=fake_getaddrinfo),
            patch.object(socket, "create_connection", side_effect=fake_create_connection),
        ):
            with self.assertRaises(OSError):
                safe_fetch("http://example.com/data", max_bytes=100, timeout=5, allow_private=False)

        self.assertEqual(connected[0][0], "93.184.216.34")

    def test_https_sni_preserved(self) -> None:
        server_names: list[str] = []

        def fake_create_connection(address, timeout=None, source_address=None):
            del address, timeout, source_address
            return MagicMock()

        def fake_wrap_socket(self, sock, server_hostname=None):
            del self
            server_names.append(server_hostname)
            return sock

        with patch.object(socket, "create_connection", side_effect=fake_create_connection), patch(
            "ssl.SSLContext.wrap_socket", new=fake_wrap_socket
        ):
            conn = __import__("aiwiki.app_utils", fromlist=["_PinnedHTTPSConnection"])._PinnedHTTPSConnection(
                "example.com", 443, _pinned_ip="93.184.216.34"
            )
            conn.connect()

        self.assertEqual(server_names[-1], "example.com")

    def test_allowlist_unset_allows(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch.object(socket, "getaddrinfo", return_value=self._dns("93.184.216.34")):
            url, _ = _validate_safe_url("http://anything.example/data")
        self.assertEqual(url, "http://anything.example/data")

    def test_allowlist_match(self) -> None:
        with (
            patch.dict(os.environ, {"AIWIKI_SAFE_FETCH_HOST_ALLOWLIST": "example.com,api.foo.com"}, clear=True),
            patch.object(socket, "getaddrinfo", return_value=self._dns("93.184.216.34")),
        ):
            url, _ = _validate_safe_url("http://example.com/data", enforce_allowlist=True)
        self.assertEqual(url, "http://example.com/data")

    def test_allowlist_mismatch_rejects(self) -> None:
        with patch.dict(os.environ, {"AIWIKI_SAFE_FETCH_HOST_ALLOWLIST": "example.com"}, clear=True):
            with self.assertRaisesRegex(FetchPolicyError, "host not in allowlist"):
                _validate_safe_url("http://evil.com/data", enforce_allowlist=True)

    def test_allowlist_redirect_blocks_cross(self) -> None:
        class RedirectingOpener:
            def open(self, req, timeout):
                del timeout
                raise HTTPError(req.full_url, HTTPStatus.FOUND, "Found", {"Location": "http://evil.com/next"}, None)

        with (
            patch.dict(os.environ, {"AIWIKI_SAFE_FETCH_HOST_ALLOWLIST": "example.com"}, clear=True),
            patch.object(socket, "getaddrinfo", return_value=self._dns("93.184.216.34")),
            patch("urllib.request.build_opener", return_value=RedirectingOpener()),
        ):
            with self.assertRaisesRegex(FetchPolicyError, "host not in allowlist"):
                safe_fetch("http://example.com/start", max_bytes=100, timeout=5)

    def test_proxy_env_ignored(self) -> None:
        connected: list[tuple[str, int]] = []

        def fake_create_connection(address, timeout=None, source_address=None):
            del timeout, source_address
            connected.append(address)
            raise OSError("stop before network")

        with (
            patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:8080"}, clear=True),
            patch.object(socket, "getaddrinfo", return_value=self._dns("93.184.216.34")),
            patch.object(socket, "create_connection", side_effect=fake_create_connection),
        ):
            with self.assertRaises(OSError):
                safe_fetch("http://example.com/data", max_bytes=100, timeout=5, allow_private=False)

        self.assertEqual(connected[0][0], "93.184.216.34")

    def test_validate_safe_url_default_skips_allowlist(self) -> None:
        """drop.py browser renderer guard path must not be affected by allowlist env."""
        with (
            patch.dict(
                os.environ,
                {"AIWIKI_SAFE_FETCH_HOST_ALLOWLIST": "only-this.com"},
                clear=True,
            ),
            patch.object(socket, "getaddrinfo", return_value=self._dns("93.184.216.34")),
        ):
            # Default enforce_allowlist=False (drop.py path) must not raise on
            # non-allowlisted host.
            normalized, pinned = _validate_safe_url("http://example.com/data")
            self.assertEqual(normalized, "http://example.com/data")
            self.assertEqual(pinned[0].ip, "93.184.216.34")

    def test_validate_safe_url_enforce_allowlist_rejects(self) -> None:
        with (
            patch.dict(
                os.environ,
                {"AIWIKI_SAFE_FETCH_HOST_ALLOWLIST": "only-this.com"},
                clear=True,
            ),
            patch.object(socket, "getaddrinfo", return_value=self._dns("93.184.216.34")),
        ):
            with self.assertRaises(FetchPolicyError):
                _validate_safe_url("http://example.com/data", enforce_allowlist=True)


if __name__ == "__main__":
    unittest.main()
