from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.drop import (
    _LOCAL_PDF_MAX_BYTES,
    _cleanup_tmp_dir,
    _rollback_created_paths,
    _snapshot_append_files,
    _truncate_append_files,
    drop_image,
    drop_pdf,
    drop_repo,
    drop_url,
)


class DropPhaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _raw_notes(self) -> list[Path]:
        return list((self.root / "raw" / "inbox").glob("*.md"))

    def _asset_files(self) -> list[Path]:
        return [p for p in (self.root / "raw" / "assets").glob("*") if p.is_file()]

    def _runtime_history(self) -> list[dict[str, object]]:
        path = self.root / ".aiwiki/state/runtime-history.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _wiki_log_text(self) -> str:
        path = self.root / "wiki/indexes/log.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def test_drop_url_collect_failure_does_not_write_raw(self) -> None:
        with patch("aiwiki.drop._fetch_url", side_effect=RuntimeError("fetch boom")):
            with self.assertRaisesRegex(RuntimeError, "fetch boom"):
                drop_url(self.root, "https://example.test/page")

        self.assertEqual(self._raw_notes(), [])
        self.assertEqual(self._asset_files(), [])
        self.assertEqual(self._runtime_history(), [])
        self.assertNotIn("url-drop", self._wiki_log_text())

    def test_drop_url_inline_image_failure_is_non_fatal_and_logged_after_materialize(self) -> None:
        fetched = {
            "title": "Page",
            "final_url": "https://example.test/page",
            "content_type": "text/html",
            "status": "200",
            "browser_backend": "",
            "extraction_mode": "readability",
            "description": "",
            "image_urls": ["https://example.test/broken.png"],
            "text": "body",
        }

        with patch("aiwiki.drop._fetch_url", return_value=fetched):
            with patch("aiwiki.drop.safe_fetch", side_effect=RuntimeError("image boom")):
                result = drop_url(self.root, "https://example.test/page")

        self.assertTrue((self.root / result["note_path"]).exists())
        events = [
            json.loads(line)
            for line in (self.root / ".aiwiki/logs/runs.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(events[-1]["event"], "url_image_download_skipped")
        self.assertEqual(events[-1]["reason"], "image boom")
        self.assertEqual(events[-1]["url"], "https://example.test/broken.png")
        self.assertEqual(events[-1]["error_type"], "RuntimeError")

    def test_drop_url_skip_events_inside_lock(self) -> None:
        timeline: list[str] = []
        fetched = {
            "title": "Page",
            "final_url": "https://example.test/page",
            "content_type": "text/html",
            "status": "200",
            "browser_backend": "",
            "extraction_mode": "readability",
            "description": "",
            "image_urls": ["https://example.test/broken.png"],
            "text": "body",
        }

        class RecordingLock:
            def __enter__(self) -> None:
                timeline.append("lock-enter")

            def __exit__(self, exc_type, exc, tb) -> None:
                timeline.append("lock-exit")

        def fake_append(root: Path, event: dict[str, object]) -> None:
            del root, event
            timeline.append("append-event")

        with patch("aiwiki.drop._fetch_url", return_value=fetched):
            with patch("aiwiki.drop.safe_fetch", side_effect=RuntimeError("image boom")):
                with patch("aiwiki.drop.runtime_write_lock", return_value=RecordingLock()):
                    with patch("aiwiki.drop._append_run_event", side_effect=fake_append):
                        drop_url(self.root, "https://example.test/page")

        self.assertEqual(timeline, ["lock-enter", "append-event", "lock-exit"])

    def test_drop_pdf_collect_failure_network_does_not_write_raw(self) -> None:
        with patch("aiwiki.drop.safe_fetch", side_effect=RuntimeError("network boom")):
            with self.assertRaisesRegex(RuntimeError, "network boom"):
                drop_pdf(self.root, "https://example.test/paper.pdf")
        self.assertEqual(self._raw_notes(), [])
        self.assertEqual(self._asset_files(), [])

    def test_drop_pdf_validate_failure_size_does_not_write_raw(self) -> None:
        source = self.root / "huge.pdf"
        source.write_bytes(b"%PDF-1.4\n" + b"x" * (_LOCAL_PDF_MAX_BYTES + 1))
        with patch("aiwiki.drop._extract_pdf_text", return_value="should not run") as extract:
            with self.assertRaisesRegex(ValueError, "PDF asset exceeds size limit"):
                drop_pdf(self.root, str(source))
        extract.assert_not_called()
        self.assertEqual(self._raw_notes(), [])
        self.assertEqual(self._asset_files(), [])

    def test_drop_pdf_validate_failure_magic_does_not_write_raw(self) -> None:
        source = self.root / "bad.pdf"
        source.write_bytes(b"not pdf")
        with patch("aiwiki.drop._extract_pdf_text", return_value="should not run") as extract:
            with self.assertRaisesRegex(ValueError, "magic bytes missing"):
                drop_pdf(self.root, str(source))
        extract.assert_not_called()
        self.assertEqual(self._raw_notes(), [])
        self.assertEqual(self._asset_files(), [])

    def test_drop_pdf_materialize_asset_write_failure_rolls_back(self) -> None:
        source = self.root / "ok.pdf"
        source.write_bytes(b"%PDF-1.4\n")
        with patch("aiwiki.drop._extract_pdf_text", return_value="text"):
            with patch("aiwiki.drop.atomic_copy_file", side_effect=RuntimeError("copy boom")):
                with self.assertRaisesRegex(RuntimeError, "copy boom"):
                    drop_pdf(self.root, str(source), title="Paper")
        self.assertEqual(self._raw_notes(), [])
        self.assertEqual(self._asset_files(), [])

    def test_drop_pdf_history_failure_truncates_log(self) -> None:
        source = self.root / "ok.pdf"
        source.write_bytes(b"%PDF-1.4\n")
        log_path = self.root / "wiki" / "indexes" / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("# existing\n\n", encoding="utf-8")
        before = log_path.stat().st_size

        with patch("aiwiki.drop._extract_pdf_text", return_value="text"):
            with patch("aiwiki.drop._append_raw_added_history", side_effect=RuntimeError("history boom")):
                with self.assertRaisesRegex(RuntimeError, "history boom"):
                    drop_pdf(self.root, str(source), title="Paper")

        self.assertEqual(log_path.stat().st_size, before)
        self.assertEqual(log_path.read_text(encoding="utf-8"), "# existing\n\n")
        self.assertEqual(self._raw_notes(), [])
        self.assertEqual(self._asset_files(), [])

    def test_drop_pdf_history_failure_removes_log_when_absent(self) -> None:
        source = self.root / "ok.pdf"
        source.write_bytes(b"%PDF-1.4\n")
        log_path = self.root / "wiki" / "indexes" / "log.md"
        self.assertFalse(log_path.exists())

        with patch("aiwiki.drop._extract_pdf_text", return_value="text"):
            with patch("aiwiki.drop._append_raw_added_history", side_effect=RuntimeError("history boom")):
                with self.assertRaisesRegex(RuntimeError, "history boom"):
                    drop_pdf(self.root, str(source), title="Paper")

        self.assertFalse(log_path.exists())
        self.assertEqual(self._raw_notes(), [])
        self.assertEqual(self._asset_files(), [])

    def test_drop_image_collect_failure_cleans_tmp(self) -> None:
        source = self.root / "img.png"
        source.write_bytes(_tiny_png())
        before = set(Path(tempfile.gettempdir()).glob("aiwiki-drop-image-*"))

        with patch("aiwiki.drop._detect_mime_type", side_effect=RuntimeError("mime boom")):
            with self.assertRaisesRegex(RuntimeError, "mime boom"):
                drop_image(self.root, str(source), enable_vision=False)

        after = set(Path(tempfile.gettempdir()).glob("aiwiki-drop-image-*"))
        self.assertEqual(after - before, set())

    def test_drop_image_ocr_failure_is_non_fatal(self) -> None:
        source = self.root / "img.png"
        source.write_bytes(_tiny_png())
        with patch("aiwiki.drop._detect_mime_type", return_value="image/png"):
            with patch("aiwiki.drop._extract_image_text", return_value=""):
                result = drop_image(self.root, str(source), enable_vision=False)
        self.assertTrue((self.root / result["note_path"]).exists())
        self.assertFalse(result["ocr_text_present"])

    def test_drop_image_vision_failure_is_non_fatal(self) -> None:
        source = self.root / "img.png"
        source.write_bytes(_tiny_png())
        failing_client = type(
            "FailingClient",
            (),
            {
                "config": type("Config", (), {"backend": "codex-cli"})(),
                "analyze_image": lambda self, system_prompt, user_prompt, image_path: (_ for _ in ()).throw(RuntimeError("boom")),
            },
        )()
        with patch("aiwiki.drop._detect_mime_type", return_value="image/png"):
            result = drop_image(self.root, str(source), client=failing_client)
        self.assertTrue((self.root / result["note_path"]).exists())
        self.assertEqual(result["vision_status"], "failed")

    def test_drop_repo_clone_failure_does_not_write_raw(self) -> None:
        with patch.dict("os.environ", {"AIWIKI_ALLOW_REMOTE_REPO_DROP": "1"}, clear=False):
            with patch("aiwiki.drop._clone_repo", side_effect=RuntimeError("clone boom")):
                with self.assertRaisesRegex(RuntimeError, "clone boom"):
                    drop_repo(self.root, "https://example.test/repo.git")
        self.assertEqual(self._raw_notes(), [])
        self.assertEqual(self._runtime_history(), [])

    def test_drop_repo_clone_failure_cleans_tmp(self) -> None:
        before = set(Path(tempfile.gettempdir()).glob("aiwiki-repo-*"))

        with patch.dict("os.environ", {"AIWIKI_ALLOW_REMOTE_REPO_DROP": "1"}, clear=False):
            with patch("aiwiki.drop._clone_repo", side_effect=RuntimeError("clone boom")):
                with self.assertRaisesRegex(RuntimeError, "clone boom"):
                    drop_repo(self.root, "https://example.test/repo.git")

        after = set(Path(tempfile.gettempdir()).glob("aiwiki-repo-*"))
        self.assertEqual(after - before, set())

    def test_drop_repo_materialize_note_write_failure_does_not_append_logs(self) -> None:
        repo = self.root / "repo"
        repo.mkdir()
        with patch(
            "aiwiki.drop._repo_snapshot",
            return_value={"name": "repo", "commit": "", "origin": "", "readme": "ok", "tree": [], "files": []},
        ):
            with patch("aiwiki.drop._write_text", side_effect=RuntimeError("write boom")):
                with self.assertRaisesRegex(RuntimeError, "write boom"):
                    drop_repo(self.root, str(repo))
        self.assertEqual(self._runtime_history(), [])
        self.assertNotIn("repo-drop", self._wiki_log_text())

    def test_slow_io_happens_before_drop_url_lock(self) -> None:
        timeline: list[str] = []
        fetched = {
            "title": "Page",
            "final_url": "https://example.test/page",
            "content_type": "text/html",
            "status": "200",
            "browser_backend": "",
            "extraction_mode": "readability",
            "description": "",
            "image_urls": [],
            "text": "body",
        }

        class RecordingLock:
            def __enter__(self) -> None:
                timeline.append("lock-enter")

            def __exit__(self, exc_type, exc, tb) -> None:
                timeline.append("lock-exit")

        def fake_fetch(url: str, *, root: Path) -> dict[str, object]:
            del url, root
            timeline.append("fetch")
            return fetched

        with patch("aiwiki.drop._fetch_url", side_effect=fake_fetch):
            with patch("aiwiki.drop.runtime_write_lock", return_value=RecordingLock()):
                drop_url(self.root, "https://example.test/page")

        self.assertEqual(timeline[:2], ["fetch", "lock-enter"])

    def test_truncate_append_files_logs_warning_on_oserror(self) -> None:
        log_path = self.root / "wiki" / "indexes" / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("seed\nrollback-target\n", encoding="utf-8")
        snapshots = {log_path: (True, 4)}  # truncate to "seed"

        original_open = Path.open

        def raising_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            if self == log_path and "rb+" in args:
                raise OSError("simulated truncate failure")
            return original_open(self, *args, **kwargs)

        with patch.object(Path, "open", raising_open):
            with self.assertLogs("aiwiki.drop", level="WARNING") as captured:
                _truncate_append_files(snapshots)

        self.assertTrue(
            any("drop rollback truncate failed" in line for line in captured.output),
            captured.output,
        )
        # file still on disk because truncate failed; best-effort, no re-raise
        self.assertEqual(log_path.read_text(encoding="utf-8"), "seed\nrollback-target\n")

    def test_rollback_created_paths_logs_warning_on_unlink_failure(self) -> None:
        victim = self.root / "raw" / "inbox" / "victim.md"
        victim.parent.mkdir(parents=True, exist_ok=True)
        victim.write_text("payload", encoding="utf-8")

        original_unlink = Path.unlink

        def raising_unlink(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            if self == victim:
                raise OSError("simulated unlink failure")
            return original_unlink(self, *args, **kwargs)

        with patch.object(Path, "unlink", raising_unlink):
            with self.assertLogs("aiwiki.drop", level="WARNING") as captured:
                _rollback_created_paths([victim])

        self.assertTrue(
            any("drop rollback unlink failed" in line for line in captured.output),
            captured.output,
        )
        # best-effort: file stays on disk, no re-raise propagated to caller
        self.assertTrue(victim.exists())

    def test_cleanup_tmp_dir_logs_warning_on_rmtree_failure(self) -> None:
        tmp_dir = self.root / "drop-tmp-probe"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        (tmp_dir / "scratch.bin").write_bytes(b"payload")

        def raising_rmtree(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise OSError("simulated rmtree failure")

        with patch("aiwiki.drop.shutil.rmtree", side_effect=raising_rmtree):
            with self.assertLogs("aiwiki.drop", level="WARNING") as captured:
                _cleanup_tmp_dir(tmp_dir)

        self.assertTrue(
            any("drop tmp cleanup failed" in line for line in captured.output),
            captured.output,
        )

    def test_cleanup_tmp_dir_silent_when_already_absent(self) -> None:
        tmp_dir = self.root / "never-created"
        # FileNotFoundError must be swallowed without warning (expected case)
        with self.assertNoLogs("aiwiki.drop", level="WARNING"):
            _cleanup_tmp_dir(tmp_dir)

    def test_snapshot_append_files_skips_path_on_stat_oserror(self) -> None:
        log_path = self.root / "wiki" / "indexes" / "log.md"
        history_path = self.root / ".aiwiki/state/runtime-history.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("seed\n", encoding="utf-8")
        history_path.write_text("{}\n", encoding="utf-8")

        original_exists = Path.exists

        def raising_exists(self):  # type: ignore[no-untyped-def]
            if self == log_path:
                raise OSError("simulated stat failure")
            return original_exists(self)

        with patch.object(Path, "exists", raising_exists):
            with self.assertLogs("aiwiki.drop", level="WARNING") as captured:
                snapshots = _snapshot_append_files(self.root)

        self.assertNotIn(log_path, snapshots)
        self.assertIn(history_path, snapshots)
        self.assertTrue(
            any("drop rollback snapshot stat failed" in line for line in captured.output),
            captured.output,
        )


def _tiny_png() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z3ioAAAAASUVORK5CYII="
    )


if __name__ == "__main__":
    unittest.main()
