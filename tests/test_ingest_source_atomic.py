"""R94.2 — `ingest_source` writes raw/ atomically (no partial files on crash)."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import load_manifest
from aiwiki.content.io import ingest_source, sync_manifest_with_raw
from aiwiki.runner.automation import inbox_snapshot


class IngestSourceAtomicTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.root = self.tmp_path / "wk"
        self.root.mkdir()
        ensure_layout(self.root)
        self.inbox = self.root / "raw" / "inbox"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @staticmethod
    def _fetched_example() -> dict[str, object]:
        return {
            "title": "Example Domain",
            "final_url": "https://example.com/",
            "content_type": "text/html",
            "status": "200",
            "browser_backend": "",
            "extraction_mode": "bs4-main-content",
            "description": "",
            "image_urls": [],
            "text": "Example Domain\nThis domain is for use in illustrative examples in documents.",
        }

    def test_ingest_url_writes_atomically(self) -> None:
        with patch("aiwiki.drop._fetch_url", return_value=self._fetched_example()):
            entry = ingest_source(self.root, "https://example.com/post", title="Post")
        stored = self.root / entry["stored_path"]
        self.assertTrue(stored.is_file())
        text = stored.read_text(encoding="utf-8")
        self.assertIn("Example Domain", text)
        self.assertNotIn("https://example.com/post", text)
        manifest = load_manifest(self.root)
        self.assertEqual(manifest["entries"][0]["ingest_metadata"]["original_url"], "https://example.com/post")
        leftovers = [p.name for p in self.inbox.iterdir() if ".tmp." in p.name]
        self.assertEqual(leftovers, [])

    def test_ingest_url_replace_failure_leaves_no_partial(self) -> None:
        with patch("aiwiki.drop._fetch_url", return_value=self._fetched_example()):
            with patch("aiwiki.app_utils.os.replace", side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    ingest_source(self.root, "https://example.com/x", title="X")
        files = list(self.inbox.iterdir())
        self.assertEqual(files, [], f"unexpected files: {[p.name for p in files]}")

    def test_ingest_url_fetch_failure_leaves_no_partial(self) -> None:
        with patch("aiwiki.drop._fetch_url", side_effect=RuntimeError("network boom")):
            with self.assertRaises(RuntimeError):
                ingest_source(self.root, "https://example.com/x", title="X")
        files = list(self.inbox.iterdir())
        self.assertEqual(files, [], f"unexpected files: {[p.name for p in files]}")

    def test_ingest_local_file_atomic_copy(self) -> None:
        src = self.tmp_path / "input.md"
        payload = "# Hello\n\nbody bytes 字节\n"
        src.write_text(payload, encoding="utf-8")

        entry = ingest_source(self.root, str(src), title="Input")
        stored = self.root / entry["stored_path"]
        self.assertTrue(stored.is_file())
        self.assertEqual(stored.read_text(encoding="utf-8"), payload)
        leftovers = [p.name for p in self.inbox.iterdir() if ".tmp." in p.name]
        self.assertEqual(leftovers, [])

    def test_ingest_local_file_replace_failure_leaves_no_partial(self) -> None:
        src = self.tmp_path / "input.bin"
        src.write_bytes(b"\x00\x01\x02payload")

        with patch("aiwiki.app_utils.os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                ingest_source(self.root, str(src), title="Bin")

        files = list(self.inbox.iterdir())
        self.assertEqual(files, [], f"unexpected files: {[p.name for p in files]}")

    def test_ingest_local_file_byte_identical(self) -> None:
        src = self.tmp_path / "image.bin"
        payload = bytes(range(256)) * 8  # 2 KiB binary, all byte values
        src.write_bytes(payload)

        entry = ingest_source(self.root, str(src), title="Bin")
        stored = self.root / entry["stored_path"]
        self.assertEqual(stored.read_bytes(), payload)

    def test_sync_manifest_skips_orphan_tmp(self) -> None:
        # Simulate a crash leaving a tmp file in raw/inbox/ following the
        # strict atomic_write tmp convention: <name>.tmp.<pid>.<ns>.
        orphan = self.inbox / "leftover.md.tmp.12345.999"
        orphan.write_text("partial garbage", encoding="utf-8")

        manifest = sync_manifest_with_raw(self.root)
        self.assertEqual(manifest["entries"], [])

        # Persisted manifest also empty.
        persisted = load_manifest(self.root)
        self.assertEqual(persisted["entries"], [])

        # Now ingest a real source; orphan still must not be registered.
        real = self.tmp_path / "real.md"
        real.write_text("# real\n", encoding="utf-8")
        ingest_source(self.root, str(real), title="Real")

        manifest_after = load_manifest(self.root)
        stored_paths = {e["stored_path"] for e in manifest_after["entries"]}
        self.assertNotIn("raw/inbox/leftover.md.tmp.12345.999", stored_paths)
        self.assertEqual(len(manifest_after["entries"]), 1)

    def test_sync_manifest_does_not_skip_legitimate_dot_tmp_dot_filenames(self) -> None:
        # Strict regex: trailing `.tmp.<digits>.<digits>` only. A user file
        # whose name happens to contain ".tmp." in the middle must still be
        # registered as a fact source.
        legit = self.inbox / "report.tmp.notes.md"
        legit.write_text("# legit user file\n", encoding="utf-8")

        manifest = sync_manifest_with_raw(self.root)
        stored_paths = {e["stored_path"] for e in manifest["entries"]}
        self.assertIn("raw/inbox/report.tmp.notes.md", stored_paths)

    def test_inbox_snapshot_skips_orphan_tmp(self) -> None:
        # Real file + orphan tmp; snapshot digest should depend only on the
        # real file. Adding the orphan after the first snapshot must not
        # change the digest.
        real = self.inbox / "real.md"
        real.write_text("real\n", encoding="utf-8")
        snap_before = inbox_snapshot(self.root)

        orphan = self.inbox / "real.md.tmp.99999.123456"
        orphan.write_text("partial", encoding="utf-8")
        snap_after = inbox_snapshot(self.root)

        self.assertEqual(snap_before["digest"], snap_after["digest"])
        snap_paths = {f["path"] for f in snap_after["files"]}
        self.assertNotIn("raw/inbox/real.md.tmp.99999.123456", snap_paths)


if __name__ == "__main__":
    unittest.main()
