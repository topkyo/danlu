from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from aiwiki.app_utils import FetchPolicyError, _PinnedAddress, safe_fetch


class SafeFetchCloseTests(unittest.TestCase):
    def _mock_response(self, *, chunks: list[bytes] | None = None, read_side_effect=None):
        resp = MagicMock()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        resp.geturl = MagicMock(return_value="http://example.com/data")
        if read_side_effect is not None:
            resp.read = MagicMock(side_effect=read_side_effect)
        elif chunks is not None:
            iter_chunks = iter(chunks)

            def _read(_size: int) -> bytes:
                try:
                    return next(iter_chunks)
                except StopIteration:
                    return b""

            resp.read = _read
        else:
            resp.read = MagicMock(return_value=b"")
        return resp

    def _patch_opener(self, resp):
        opener = MagicMock()
        opener.open = MagicMock(return_value=resp)
        return patch("urllib.request.build_opener", return_value=opener)

    def test_normal_path_closes_response(self) -> None:
        resp = self._mock_response(chunks=[b"hello", b"world"])
        with self._patch_opener(resp), patch(
            "aiwiki.app_utils._validate_safe_url",
            side_effect=lambda url, **kw: (url, [_PinnedAddress(2, "93.184.216.34")]),
        ):
            data, final = safe_fetch("http://example.com/data", max_bytes=1024, timeout=5, allow_private=True)

        self.assertEqual(data, b"helloworld")
        self.assertEqual(final, "http://example.com/data")
        self.assertTrue(resp.__exit__.called)

    def test_max_bytes_truncate_closes_response(self) -> None:
        resp = self._mock_response(chunks=[b"a" * 200])
        with self._patch_opener(resp), patch(
            "aiwiki.app_utils._validate_safe_url",
            side_effect=lambda url, **kw: (url, [_PinnedAddress(2, "93.184.216.34")]),
        ):
            with self.assertRaises(FetchPolicyError):
                safe_fetch("http://example.com/data", max_bytes=10, timeout=5, allow_private=True)

        self.assertTrue(resp.__exit__.called)

    def test_read_error_closes_response(self) -> None:
        resp = self._mock_response(read_side_effect=OSError("conn reset"))
        with self._patch_opener(resp), patch(
            "aiwiki.app_utils._validate_safe_url",
            side_effect=lambda url, **kw: (url, [_PinnedAddress(2, "93.184.216.34")]),
        ):
            with self.assertRaises(OSError):
                safe_fetch("http://example.com/data", max_bytes=1024, timeout=5, allow_private=True)

        self.assertTrue(resp.__exit__.called)


if __name__ == "__main__":
    unittest.main()
