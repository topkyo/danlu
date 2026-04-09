from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


class LocalWorktreeScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.script = self.project_root / "scripts" / "configure_local_worktree.sh"
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test User")
        self._write(".obsidian/app.json", '{"ok": true}\n')
        self._write("wiki/indexes/compile-status.md", "base\n")
        self._write("wiki/indexes/review-queue.md", "base\n")
        self._git("add", ".obsidian/app.json", "wiki/indexes/compile-status.md", "wiki/indexes/review-queue.md")
        self._git("commit", "-qm", "init")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write(self, relative: str, content: str) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def _run_script(self, *args: str) -> str:
        return subprocess.run(
            ["bash", str(self.script), "--repo-root", str(self.repo), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def test_apply_and_undo_manage_skip_worktree_and_excludes(self) -> None:
        self._write(".obsidian/app.json", '{"changed": true}\n')
        self._write("wiki/indexes/compile-status.md", "changed\n")
        self._write("raw/demo.md", "hello\n")
        self._write(".obsidian/appearance.json", '{"theme": "light"}\n')
        self._write("本地脑图.canvas", "{}\n")

        before = self._git("status", "--short")
        self.assertIn(".obsidian/app.json", before)
        self.assertIn("wiki/indexes/compile-status.md", before)
        self.assertIn("raw/", before)
        self.assertIn(".obsidian/appearance.json", before)

        self._run_script("--apply")

        skip_lines = self._git("ls-files", "-v", "--", ".obsidian/app.json", "wiki/indexes/compile-status.md")
        self.assertIn("S .obsidian/app.json", skip_lines)
        self.assertIn("S wiki/indexes/compile-status.md", skip_lines)

        exclude_text = (self.repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertIn("# >>> aiwiki-local-worktree >>>", exclude_text)
        self.assertIn("raw/", exclude_text)
        self.assertIn(".obsidian/appearance.json", exclude_text)
        self.assertIn("*.canvas", exclude_text)

        after_apply = self._git("status", "--short")
        self.assertNotIn(".obsidian/app.json", after_apply)
        self.assertNotIn("wiki/indexes/compile-status.md", after_apply)
        self.assertNotIn("raw/", after_apply)
        self.assertNotIn(".obsidian/appearance.json", after_apply)
        self.assertNotIn(".canvas", after_apply)

        status_output = self._run_script("--status")
        self.assertIn("exclude_block=present", status_output)
        self.assertIn(".obsidian/app.json: skip-worktree", status_output)
        self.assertIn("wiki/indexes/compile-status.md: skip-worktree", status_output)

        self._run_script("--undo")

        after_undo = self._git("status", "--short")
        self.assertIn(".obsidian/app.json", after_undo)
        self.assertIn("wiki/indexes/compile-status.md", after_undo)
        self.assertIn("raw/", after_undo)
        self.assertIn(".obsidian/appearance.json", after_undo)

        undo_exclude_text = (self.repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertNotIn("# >>> aiwiki-local-worktree >>>", undo_exclude_text)
        self.assertNotIn("raw/", undo_exclude_text)

        undo_status = self._run_script("--status")
        self.assertIn("exclude_block=absent", undo_status)
        self.assertIn(".obsidian/app.json: tracked", undo_status)


if __name__ == "__main__":
    unittest.main()
