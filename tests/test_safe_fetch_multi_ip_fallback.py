from __future__ import annotations

import socket
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

import aiwiki.app_utils as utils
from aiwiki.app_utils import _PinnedAddress, safe_fetch


class RawSocketResponse:
    def __init__(self, body: bytes = b"ok", *, status: int = 200, headers: dict[str, str] | None = None) -> None:
        reason = "Found" if 300 <= status < 400 else "OK"
        header_lines = [f"HTTP/1.1 {status} {reason}".encode("ascii")]
        for key, value in (headers or {}).items():
            header_lines.append(f"{key}: {value}".encode("ascii"))
        header_lines.append(b"Content-Length: " + str(len(body)).encode("ascii"))
        self._payload = b"\r\n".join(header_lines) + b"\r\n\r\n" + body
        self._offset = 0

    def makefile(self, mode: str, *args, **kwargs):
        del mode, args, kwargs
        return self

    def sendall(self, data: bytes) -> None:
        del data

    def recv(self, size: int) -> bytes:
        if self._offset >= len(self._payload):
            return b""
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._payload) - self._offset
        return self.recv(size)

    def readinto(self, buffer) -> int:
        chunk = self.recv(len(buffer))
        buffer[: len(chunk)] = chunk
        return len(chunk)

    def readline(self, limit: int = -1) -> bytes:
        if self._offset >= len(self._payload):
            return b""
        end = self._payload.find(b"\n", self._offset)
        if end == -1:
            end = len(self._payload) - 1
        end += 1
        if limit is not None and limit >= 0:
            end = min(end, self._offset + limit)
        chunk = self._payload[self._offset : end]
        self._offset = end
        return chunk

    def close(self) -> None:
        return None

    def flush(self) -> None:
        return None


class SafeFetchMultiIpFallbackTests(unittest.TestCase):
    def _patch_validate(self, pinned_ips: list[str]):
        pinned = [_PinnedAddress(socket.AF_INET6 if ":" in ip else socket.AF_INET, ip) for ip in pinned_ips]

        def fake_validate(url: str, **kwargs):
            del kwargs
            return url, pinned

        return patch.object(utils, "_validate_safe_url", side_effect=fake_validate)

    def test_first_ip_unreachable_falls_back_to_second(self) -> None:
        attempts: list[tuple[str, int]] = []

        def fake_create_connection(address, timeout=None, source_address=None):
            del timeout, source_address
            attempts.append(address)
            if len(attempts) == 1:
                raise OSError("conn refused")
            return RawSocketResponse(b"ok")

        with self._patch_validate(["1.2.3.4", "5.6.7.8"]), patch.object(
            socket, "create_connection", side_effect=fake_create_connection
        ):
            body, final_url = safe_fetch("http://example.com/data", max_bytes=100, timeout=5)

        self.assertEqual(body, b"ok")
        self.assertEqual(final_url, "http://example.com/data")
        self.assertGreaterEqual(len(attempts), 2)
        self.assertEqual(attempts[0][0], "1.2.3.4")
        self.assertEqual(attempts[1][0], "5.6.7.8")

    def test_all_ips_unreachable_raises_urlerror(self) -> None:
        attempts: list[tuple[str, int]] = []

        def fake_create_connection(address, timeout=None, source_address=None):
            del timeout, source_address
            attempts.append(address)
            raise OSError(f"unreachable {address[0]}")

        with self._patch_validate(["1.2.3.4", "5.6.7.8", "9.10.11.12"]), patch.object(
            socket, "create_connection", side_effect=fake_create_connection
        ):
            with self.assertRaises(urllib.error.URLError) as ctx:
                safe_fetch("http://example.com/data", max_bytes=100, timeout=5)

        self.assertEqual([address[0] for address in attempts], ["1.2.3.4", "5.6.7.8", "9.10.11.12"])
        self.assertIsInstance(ctx.exception.reason, OSError)
        self.assertIn("9.10.11.12", str(ctx.exception.reason))

    def test_single_ip_unchanged_behavior(self) -> None:
        attempts: list[tuple[str, int]] = []

        def fake_create_connection(address, timeout=None, source_address=None):
            del timeout, source_address
            attempts.append(address)
            return RawSocketResponse(b"single")

        with self._patch_validate(["1.2.3.4"]), patch.object(socket, "create_connection", side_effect=fake_create_connection):
            body, final_url = safe_fetch("http://example.com/data", max_bytes=100, timeout=5)

        self.assertEqual(body, b"single")
        self.assertEqual(final_url, "http://example.com/data")
        self.assertEqual([address[0] for address in attempts], ["1.2.3.4"])

    def test_ip_order_preserved(self) -> None:
        attempts: list[tuple[str, int]] = []

        def fake_create_connection(address, timeout=None, source_address=None):
            del timeout, source_address
            attempts.append(address)
            raise OSError(f"unreachable {address[0]}")

        with self._patch_validate(["2001:db8::1", "1.2.3.4"]), patch.object(
            socket, "create_connection", side_effect=fake_create_connection
        ):
            with self.assertRaises(urllib.error.URLError):
                safe_fetch("http://example.com/data", max_bytes=100, timeout=5)

        self.assertEqual([address[0] for address in attempts], ["2001:db8::1", "1.2.3.4"])

    def test_https_first_ip_fails_second_succeeds_wrap_once(self) -> None:
        attempts: list[tuple[str, int]] = []
        second_sock = RawSocketResponse(b"secure")
        wrapped_sock = RawSocketResponse(b"secure")

        def fake_create_connection(address, timeout=None, source_address=None):
            del timeout, source_address
            attempts.append(address)
            if len(attempts) == 1:
                raise OSError("conn refused")
            return second_sock

        def fake_wrap_socket(sock, server_hostname=None):
            del server_hostname
            return wrapped_sock

        wrap_mock = MagicMock(side_effect=fake_wrap_socket)
        with (
            self._patch_validate(["1.2.3.4", "5.6.7.8"]),
            patch.object(socket, "create_connection", side_effect=fake_create_connection),
            patch("ssl.SSLContext.wrap_socket", new=wrap_mock),
        ):
            body, final_url = safe_fetch("https://example.com/path", max_bytes=100, timeout=5)

        self.assertEqual(body, b"secure")
        self.assertEqual(final_url, "https://example.com/path")
        self.assertEqual([address[0] for address in attempts], ["1.2.3.4", "5.6.7.8"])
        self.assertEqual(wrap_mock.call_count, 1)
        self.assertIs(wrap_mock.call_args.args[0], second_sock)
        self.assertEqual(wrap_mock.call_args.kwargs["server_hostname"], "example.com")

    def test_redirect_rebuilds_ip_list(self) -> None:
        attempts: list[tuple[str, int]] = []

        def fake_resolve(host: str, port: int | None, *, allow_private: bool):
            del port, allow_private
            if host == "a.com":
                return [_PinnedAddress(socket.AF_INET, "1.1.1.1")]
            if host == "b.com":
                return [_PinnedAddress(socket.AF_INET, "2.2.2.2"), _PinnedAddress(socket.AF_INET, "3.3.3.3")]
            raise AssertionError(f"unexpected host {host}")

        def fake_create_connection(address, timeout=None, source_address=None):
            del timeout, source_address
            attempts.append(address)
            if address[0] == "1.1.1.1":
                return RawSocketResponse(status=302, headers={"Location": "http://b.com/"})
            if address[0] == "2.2.2.2":
                raise OSError("redirect target first IP down")
            if address[0] == "3.3.3.3":
                return RawSocketResponse(b"redirect-ok")
            raise AssertionError(f"unexpected connect {address}")

        with patch.object(utils, "_resolve_and_check_host", side_effect=fake_resolve), patch.object(
            socket, "create_connection", side_effect=fake_create_connection
        ):
            body, final_url = safe_fetch("http://a.com/start", max_bytes=100, timeout=5)

        self.assertEqual(body, b"redirect-ok")
        self.assertEqual(final_url, "http://b.com/")
        self.assertEqual([address[0] for address in attempts], ["1.1.1.1", "2.2.2.2", "3.3.3.3"])


if __name__ == "__main__":
    unittest.main()
