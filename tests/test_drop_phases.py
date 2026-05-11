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


def _tiny_png() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z3ioAAAAASUVORK5CYII="
    )


if __name__ == "__main__":
    unittest.main()
