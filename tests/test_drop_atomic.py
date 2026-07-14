"""R95.2 — drop.py raw note + asset writes use atomic_write_* helpers.

Covers: tmp pattern matches `is_atomic_write_tmp_path`, write failure
leaves no orphan, fsync=True for raw fact layer, asset bytes path also
atomic.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_utils import is_atomic_write_tmp_path
from aiwiki.drop import _write_bytes, _write_text, drop_image, drop_note


class DropAtomicWriteTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.root = self.tmp_path / "wk"
        self.root.mkdir()
        ensure_layout(self.root)
        self.inbox = self.root / "raw" / "inbox"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_drop_note_writes_atomically_no_tmp_residue(self) -> None:
        result = drop_note(self.root, text="hello body 字节\n", title="Hello")
        stored = self.root / result["note_path"]
        self.assertTrue(stored.is_file())
        # No tmp leftover after success.
        leftovers = [p.name for p in self.inbox.iterdir() if ".tmp." in p.name]
        self.assertEqual(leftovers, [])

    def test_drop_note_replace_failure_leaves_no_partial(self) -> None:
        with patch("aiwiki.app_utils.os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                drop_note(self.root, text="payload", title="Boom")
        # atomic_write_text cleans up tmp on failure → inbox empty.
        files = list(self.inbox.iterdir())
        self.assertEqual(files, [], f"unexpected files: {[p.name for p in files]}")

    def test_drop_note_routes_through_atomic_write_text_with_fsync(self) -> None:
        # Spy without breaking call: forward to real implementation but
        # capture the call signature.
        from aiwiki.app_utils import atomic_write_text as real_awt

        seen_kwargs: list[dict] = []

        def spy(path: Path, content: str, **kwargs: object) -> None:
            seen_kwargs.append(kwargs)
            real_awt(path, content, **kwargs)

        with patch("aiwiki.drop.atomic_write_text", side_effect=spy) as mock_awt:
            drop_note(self.root, text="x", title="X")

        mock_awt.assert_called()
        # First call writes the raw note; must use fsync=True.
        first_kwargs = seen_kwargs[0]
        self.assertEqual(first_kwargs.get("fsync"), True)

    def test_write_text_helper_uses_strict_atomic_tmp_pattern(self) -> None:
        # Direct unit test on _write_text: intercept os.replace so the tmp
        # is not consumed; verify the tmp path matches is_atomic_write_tmp_path.
        target = self.inbox / "probe.md"
        captured: list[Path] = []

        def fake_replace(src: str, dst: str) -> None:
            captured.append(Path(src))
            raise OSError("intercepted")

        with patch("aiwiki.app_utils.os.replace", side_effect=fake_replace):
            with self.assertRaises(OSError):
                _write_text(target, "content")

        self.assertEqual(len(captured), 1)
        tmp_path = captured[0]
        self.assertTrue(
            is_atomic_write_tmp_path(tmp_path),
            f"tmp path {tmp_path.name} does not match strict atomic pattern",
        )

    def test_write_bytes_helper_uses_strict_atomic_tmp_pattern(self) -> None:
        target = self.inbox / "asset.bin"
        captured: list[Path] = []

        def fake_replace(src: str, dst: str) -> None:
            captured.append(Path(src))
            raise OSError("intercepted")

        with patch("aiwiki.app_utils.os.replace", side_effect=fake_replace):
            with self.assertRaises(OSError):
                _write_bytes(target, b"\x00\x01\x02")

        self.assertEqual(len(captured), 1)
        self.assertTrue(is_atomic_write_tmp_path(captured[0]))

    def test_write_bytes_round_trips_arbitrary_payload(self) -> None:
        target = self.inbox / "asset.bin"
        payload = bytes(range(256)) * 4  # 1 KiB, all byte values
        _write_bytes(target, payload)
        self.assertEqual(target.read_bytes(), payload)

    # ---------- asset copy paths (BLOCK from R95.2 review) ----------

    # Minimal valid PNG (1x1 transparent) so `file --mime-type` returns image/png.
    _MINIMAL_PNG = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def _make_local_image(self, payload: bytes | None = None) -> Path:
        # Source must live inside root for safe_resolve_within.
        src = self.root / "incoming" / "pic.png"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(payload if payload is not None else self._MINIMAL_PNG)
        return src

    def test_drop_image_local_copy_succeeds_and_no_tmp_residue(self) -> None:
        src = self._make_local_image()
        result = drop_image(self.root, str(src), enable_vision=False)
        asset_rel = result["asset_path"]
        asset_path = self.root / asset_rel
        self.assertTrue(asset_path.is_file())
        self.assertEqual(asset_path.read_bytes(), src.read_bytes())
        asset_dir = self.root / "raw" / "assets"
        leftovers = [p.name for p in asset_dir.iterdir() if ".tmp." in p.name]
        self.assertEqual(leftovers, [])

    def test_drop_image_local_copy_replace_failure_leaves_no_partial(self) -> None:
        src = self._make_local_image()
        with patch("aiwiki.app_utils.os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                drop_image(self.root, str(src), enable_vision=False)
        asset_dir = self.root / "raw" / "assets"
        # Either dir not created or has no real asset file.
        if asset_dir.exists():
            files = list(asset_dir.iterdir())
            self.assertEqual(files, [], f"unexpected files: {[p.name for p in files]}")

    def test_drop_image_local_copy_uses_strict_atomic_tmp_pattern(self) -> None:
        src = self._make_local_image()
        captured: list[Path] = []

        def fake_replace(s: str, d: str) -> None:
            captured.append(Path(s))
            raise OSError("intercepted")

        with patch("aiwiki.app_utils.os.replace", side_effect=fake_replace):
            with self.assertRaises(OSError):
                drop_image(self.root, str(src), enable_vision=False)

        self.assertGreaterEqual(len(captured), 1)
        # The asset tmp must match strict pattern.
        asset_tmp = next(
            (p for p in captured if "raw/assets" in str(p) or "raw\\assets" in str(p)),
            None,
        )
        self.assertIsNotNone(asset_tmp, f"no raw/assets tmp captured: {captured}")
        self.assertTrue(
            is_atomic_write_tmp_path(asset_tmp),
            f"asset tmp {asset_tmp.name} not strict atomic pattern",
        )


if __name__ == "__main__":
    unittest.main()
