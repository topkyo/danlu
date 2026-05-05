from __future__ import annotations

import socket
import unittest
import urllib.error
from unittest.mock import patch

import aiwiki.app_utils as utils
from aiwiki.app_utils import _PinnedAddress, safe_fetch


class RawSocketResponse:
    def __init__(self, body: bytes = b"ok") -> None:
        self._payload = b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
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


if __name__ == "__main__":
    unittest.main()
