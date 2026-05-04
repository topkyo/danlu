from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aiwiki.app_utils import PathOutsideWorkspaceError, safe_resolve_within


class SafeResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_allows_child(self) -> None:
        child = self.root / "sub" / "file.txt"
        child.parent.mkdir()
        child.write_text("ok", encoding="utf-8")

        self.assertEqual(safe_resolve_within(child, self.root), child.resolve())

    def test_allows_root(self) -> None:
        self.assertEqual(safe_resolve_within(self.root, self.root), self.root.resolve())

    def test_rejects_parent_escape(self) -> None:
        with self.assertRaises(PathOutsideWorkspaceError):
            safe_resolve_within(self.root / "..", self.root)

    def test_rejects_absolute_escape(self) -> None:
        with self.assertRaises(PathOutsideWorkspaceError):
            safe_resolve_within(Path("/etc/passwd"), self.root)

    def test_rejects_symlink_escape(self) -> None:
        outside = self.root.parent / "outside-safe-resolve.txt"
        outside.write_text("secret", encoding="utf-8")
        link = self.root / "link"
        link.symlink_to(outside)

        with self.assertRaises(PathOutsideWorkspaceError):
            safe_resolve_within(link, self.root)

    def test_root_need_not_exist(self) -> None:
        root = self.root / "missing-root"
        child = root / "sub" / "future.txt"

        self.assertEqual(safe_resolve_within(child, root), child.resolve())
