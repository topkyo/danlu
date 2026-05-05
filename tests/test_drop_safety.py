from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_utils import FetchPolicyError, PathOutsideWorkspaceError
from aiwiki.drop import (
    _LOCAL_IMAGE_MAX_BYTES,
    _LOCAL_PDF_MAX_BYTES,
    _repo_tree,
    _resolve_asset_url,
    drop_image,
    drop_pdf,
    drop_repo,
    drop_url,
)


class DropSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_drop_url_rejects_private_host(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "private"):
            drop_url(self.root, "http://127.0.0.1/")

    def test_drop_url_rejects_file_url_outside_workspace(self) -> None:
        with self.assertRaises((PathOutsideWorkspaceError, RuntimeError)):
            drop_url(self.root, "file:///etc/passwd")

    def test_drop_pdf_rejects_absolute_path_outside_workspace(self) -> None:
        with self.assertRaises(PathOutsideWorkspaceError):
            drop_pdf(self.root, "/etc/passwd")

    def test_drop_repo_rejects_absolute_path_outside_workspace(self) -> None:
        with self.assertRaises(PathOutsideWorkspaceError):
            drop_repo(self.root, "/etc")

    def test_repo_tree_skips_symlink(self) -> None:
        repo = self.root / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("# ok\n", encoding="utf-8")
        (repo / "passwd-link").symlink_to(Path("/etc/passwd"))

        tree = _repo_tree(repo, max_files=10)

        self.assertIn("README.md", tree)
        self.assertNotIn("passwd-link", tree)

    def test_resolve_asset_url_file_outside_workspace_rejected(self) -> None:
        with self.assertRaises(PathOutsideWorkspaceError):
            _resolve_asset_url("file:///etc/passwd", root=self.root)

    def test_resolve_asset_url_file_requires_file_base_or_root(self) -> None:
        with self.assertRaises(FetchPolicyError):
            _resolve_asset_url("https://example.com/page", "file:///etc/passwd")

    def test_drop_pdf_rejects_oversized_local_file(self) -> None:
        source = self.root / "too-large.pdf"
        source.write_bytes(b"%PDF-1.4\n" + b"x" * (_LOCAL_PDF_MAX_BYTES + 1))

        with patch("aiwiki.drop._extract_pdf_text", return_value="should not run") as extract:
            with self.assertRaisesRegex(ValueError, "PDF asset exceeds size limit"):
                drop_pdf(self.root, str(source))

        extract.assert_not_called()
        self.assertEqual(list((self.root / "raw" / "inbox").glob("*.md")), [])

    def test_drop_pdf_rejects_non_pdf_magic(self) -> None:
        source = self.root / "not-a-pdf.pdf"
        source.write_bytes(b"\x00\x00\x00not-a-pdf")

        with patch("aiwiki.drop._extract_pdf_text", return_value="should not run") as extract:
            with self.assertRaisesRegex(ValueError, "magic bytes missing"):
                drop_pdf(self.root, str(source))

        extract.assert_not_called()

    def test_drop_pdf_happy_path_within_limits(self) -> None:
        source = self.root / "ok.pdf"
        source.write_bytes(b"%PDF-1.4\n%trailer\n")

        with patch("aiwiki.drop._extract_pdf_text", return_value="ok") as extract:
            result = drop_pdf(self.root, str(source), title="Small PDF")

        extract.assert_called_once()
        note = (self.root / result["note_path"]).read_text(encoding="utf-8")
        self.assertIn("ok", note)

    def test_drop_image_rejects_oversized_local_file(self) -> None:
        source = self.root / "too-large.png"
        source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * (_LOCAL_IMAGE_MAX_BYTES + 1))

        with patch("aiwiki.drop._detect_mime_type", return_value="image/png"):
            with patch("aiwiki.drop._extract_image_text", return_value="should not run") as extract:
                with patch("aiwiki.drop._analyze_image_asset") as analyze:
                    with self.assertRaisesRegex(ValueError, "image asset exceeds size limit"):
                        drop_image(self.root, str(source), enable_vision=True)

        extract.assert_not_called()
        analyze.assert_not_called()

    def test_drop_image_rejects_unsupported_mime(self) -> None:
        source = self.root / "payload.bin"
        source.write_bytes(b"not an image")

        with patch("aiwiki.drop._detect_mime_type", return_value="application/octet-stream"):
            with patch("aiwiki.drop._extract_image_text", return_value="should not run") as extract:
                with patch("aiwiki.drop._analyze_image_asset") as analyze:
                    with self.assertRaises(ValueError) as ctx:
                        drop_image(self.root, str(source), enable_vision=True)

        extract.assert_not_called()
        analyze.assert_not_called()
        message = str(ctx.exception)
        self.assertIn("Unsupported image MIME type: application/octet-stream", message)
        for allowed in ("image/gif", "image/jpeg", "image/png", "image/svg+xml", "image/webp"):
            self.assertIn(allowed, message)

    def test_drop_repo_rejects_invalid_max_files(self) -> None:
        repo = self.root / "repo"
        repo.mkdir()
        for max_files in (0, -1, 1001, "10"):
            with self.subTest(max_files=max_files):
                with patch("aiwiki.drop._repo_snapshot", return_value={}) as snapshot:
                    with self.assertRaisesRegex(ValueError, "max_files must be 1..1000"):
                        drop_repo(self.root, str(repo), max_files=max_files)  # type: ignore[arg-type]
                    snapshot.assert_not_called()

    def test_drop_repo_accepts_valid_max_files(self) -> None:
        repo = self.root / "repo"
        repo.mkdir()
        with patch(
            "aiwiki.drop._repo_snapshot",
            return_value={
                "name": "repo",
                "commit": "abc123",
                "origin": "",
                "readme": "ok",
                "tree": ["- `README.md`"],
                "files": [],
            },
        ) as snapshot:
            result = drop_repo(self.root, str(repo), max_files=10)

        snapshot.assert_called_once_with(repo, max_files=10)
        self.assertEqual(result["material"], "repo")
