from __future__ import annotations

import socket
import threading
import unittest
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError

import aiwiki.app_utils as utils
from aiwiki.app_utils import FetchPolicyError, _is_private_address, _validate_safe_url, safe_fetch


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/ok":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"hello")
        elif self.path == "/large":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"x" * 20)
        elif self.path == "/missing":
            self.send_response(404)
            self.end_headers()
        elif self.path == "/redirect-private":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1/private")
            self.end_headers()
        elif self.path == "/loop":
            self.send_response(302)
            self.send_header("Location", "/loop")
            self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"fallback")

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path == "/post":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(self.headers.get("Authorization", "").encode("utf-8") + b"\n" + body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_args):
        return


class SafeFetchTests(unittest.TestCase):
    def _mock_dns(self, host: str):
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        return patch.object(socket, "getaddrinfo", return_value=[(family, None, None, None, (host, 0))])

    def test_is_private_address_ip_literals(self) -> None:
        cases = [
            ("127.0.0.1", True),
            ("10.0.0.1", True),
            ("169.254.1.1", True),
            ("172.16.0.1", True),
            ("192.168.1.1", True),
            ("8.8.8.8", False),
            ("::1", True),
            ("fe80::1", True),
            ("2001:db8::1", False),
            ("::ffff:127.0.0.1", True),  # IPv4-mapped IPv6 must collapse to IPv4 private
            ("::ffff:10.0.0.1", True),
            ("::ffff:8.8.8.8", False),
        ]
        for host, expected in cases:
            with self.subTest(host=host), self._mock_dns(host):
                self.assertIs(_is_private_address(host), expected)

    def test_validate_safe_url_rejects_bad_schemes(self) -> None:
        with self.assertRaises(FetchPolicyError):
            _validate_safe_url("ftp://example.com/file")
        with self.assertRaises(FetchPolicyError):
            _validate_safe_url("file:///tmp/file")

    def test_validate_safe_url_policy(self) -> None:
        def fake_resolve(host, port, *, allow_private):
            if host in {"localhost", "127.0.0.1"} and not allow_private:
                raise FetchPolicyError(f"private/link-local host rejected: {host}")
            return [utils._PinnedAddress(socket.AF_INET, "93.184.216.34")]

        with patch.object(utils, "_resolve_and_check_host", side_effect=fake_resolve):
            self.assertEqual(_validate_safe_url("https://example.com/a")[0], "https://example.com/a")
            with self.assertRaises(FetchPolicyError):
                _validate_safe_url("http://localhost/")
            with self.assertRaises(FetchPolicyError):
                _validate_safe_url("http:///missing")
            self.assertEqual(_validate_safe_url("http://127.0.0.1/", allow_private=True)[0], "http://127.0.0.1/")

    def _server(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, f"http://127.0.0.1:{server.server_port}"

    def test_safe_fetch_happy_path(self) -> None:
        server, thread, base_url = self._server()
        try:
            body, final_url = safe_fetch(f"{base_url}/ok", max_bytes=10, timeout=2, allow_private=True)
        finally:
            server.shutdown()
            thread.join(timeout=2)
        self.assertEqual(body, b"hello")
        self.assertEqual(final_url, f"{base_url}/ok")

    def test_safe_fetch_max_bytes(self) -> None:
        server, thread, base_url = self._server()
        try:
            with self.assertRaises(FetchPolicyError):
                safe_fetch(f"{base_url}/large", max_bytes=5, timeout=2, allow_private=True)
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_safe_fetch_4xx(self) -> None:
        server, thread, base_url = self._server()
        try:
            with self.assertRaises(HTTPError):
                safe_fetch(f"{base_url}/missing", max_bytes=100, timeout=2, allow_private=True)
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_safe_fetch_redirect_revalidates_private(self) -> None:
        server, thread, base_url = self._server()
        try:
            with patch.object(utils, "_is_private_address", side_effect=lambda host: host == "127.0.0.1"):
                with self.assertRaises(FetchPolicyError):
                    safe_fetch(f"{base_url}/redirect-private", max_bytes=100, timeout=2, allow_private=False)
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_safe_fetch_max_redirects(self) -> None:
        server, thread, base_url = self._server()
        try:
            with self.assertRaises(FetchPolicyError):
                safe_fetch(f"{base_url}/loop", max_bytes=100, timeout=2, allow_private=True, max_redirects=1)
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_safe_fetch_timeout(self) -> None:
        class SlowOpener:
            def open(self, *_args, **_kwargs):
                raise TimeoutError("timed out")

        with patch.object(urllib.request, "build_opener", return_value=SlowOpener()), patch.object(
            utils, "_resolve_and_check_host", return_value=[utils._PinnedAddress(socket.AF_INET, "93.184.216.34")]
        ):
            with self.assertRaises(TimeoutError):
                safe_fetch("http://example.com/", max_bytes=100, timeout=0.001, allow_private=True)

    def test_safe_fetch_post_carries_body_and_headers(self) -> None:
        server, thread, base_url = self._server()
        try:
            body, _ = safe_fetch(
                f"{base_url}/post",
                method="POST",
                data=b"payload",
                headers={"Authorization": "Bearer secret"},
                max_bytes=100,
                timeout=2,
                allow_private=True,
            )
        finally:
            server.shutdown()
            thread.join(timeout=2)
        self.assertEqual(body, b"Bearer secret\npayload")

    def test_safe_fetch_redirect_strips_auth_on_host_change(self) -> None:
        captured = []

        class RedirectingOpener:
            def open(self, req, timeout):
                del timeout
                captured.append(req)
                if len(captured) == 1:
                    raise HTTPError(
                        req.full_url,
                        HTTPStatus.FOUND,
                        "Found",
                        {"Location": "http://other.example.com/next"},
                        None,
                    )
                return RawResponse(req.full_url, b"ok")

        with patch.object(urllib.request, "build_opener", return_value=RedirectingOpener()), patch.object(
            utils, "_resolve_and_check_host", return_value=[utils._PinnedAddress(socket.AF_INET, "93.184.216.34")]
        ):
            safe_fetch(
                "http://example.com/start",
                headers={"Authorization": "Bearer secret", "x-api-key": "key", "Cookie": "a=b"},
                max_bytes=100,
                timeout=2,
            )

        second_headers = {key.lower(): value for key, value in captured[1].headers.items()}
        self.assertNotIn("authorization", second_headers)
        self.assertNotIn("x-api-key", second_headers)
        self.assertNotIn("cookie", second_headers)

    def test_safe_fetch_redirect_keeps_auth_on_same_host(self) -> None:
        captured = []

        class RedirectingOpener:
            def open(self, req, timeout):
                del timeout
                captured.append(req)
                if len(captured) == 1:
                    raise HTTPError(req.full_url, HTTPStatus.FOUND, "Found", {"Location": "/next"}, None)
                return RawResponse(req.full_url, b"ok")

        with patch.object(urllib.request, "build_opener", return_value=RedirectingOpener()), patch.object(
            utils, "_resolve_and_check_host", return_value=[utils._PinnedAddress(socket.AF_INET, "93.184.216.34")]
        ):
            safe_fetch(
                "http://example.com/start",
                headers={"Authorization": "Bearer secret", "x-api-key": "key", "Cookie": "a=b"},
                max_bytes=100,
                timeout=2,
            )

        second_headers = {key.lower(): value for key, value in captured[1].headers.items()}
        self.assertEqual(second_headers["authorization"], "Bearer secret")
        self.assertEqual(second_headers["x-api-key"], "key")
        self.assertEqual(second_headers["cookie"], "a=b")


class RawResponse:
    def __init__(self, url: str, body: bytes) -> None:
        self.url = url
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False

    def read(self, _size: int = -1) -> bytes:
        body = self.body
        self.body = b""
        return body

    def geturl(self) -> str:
        return self.url
