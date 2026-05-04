from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_utils import FetchPolicyError, PathOutsideWorkspaceError
from aiwiki.drop import _repo_tree, _resolve_asset_url, drop_pdf, drop_repo, drop_url


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
