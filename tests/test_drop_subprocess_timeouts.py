"""R93.3-INGEST-SUBPROCESS-TIMEOUTS: drop.py subprocess timeout fallbacks."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki import drop


def _timeout_exc(cmd: list[str]) -> subprocess.TimeoutExpired:
    return subprocess.TimeoutExpired(cmd=cmd, timeout=1.0)


class DetectMimeTypeTimeoutTest(unittest.TestCase):
    def test_returns_default_mime_on_timeout(self) -> None:
        with patch.object(
            drop.subprocess,
            "run",
            side_effect=_timeout_exc(["file", "--brief", "--mime-type"]),
        ):
            self.assertEqual(
                drop._detect_mime_type(Path("/nonexistent")),
                "application/octet-stream",
            )


class ExtractImageTextTimeoutTest(unittest.TestCase):
    def test_returns_empty_string_on_timeout(self) -> None:
        with patch.object(drop.shutil, "which", return_value="/usr/bin/tesseract"):
            with patch.object(
                drop.subprocess,
                "run",
                side_effect=_timeout_exc(["tesseract"]),
            ):
                self.assertEqual(drop._extract_image_text(Path("/nonexistent")), "")


class GitOutputTimeoutTest(unittest.TestCase):
    def test_returns_empty_string_on_timeout(self) -> None:
        with patch.object(
            drop.subprocess,
            "run",
            side_effect=_timeout_exc(["git", "-C", "/x", "rev-parse", "HEAD"]),
        ):
            self.assertEqual(
                drop._git_output(Path("/nonexistent"), ["rev-parse", "HEAD"]),
                "",
            )


class ExtractPdfTextTimeoutTest(unittest.TestCase):
    def test_raises_runtime_error_on_timeout(self) -> None:
        with patch.object(
            drop.subprocess,
            "run",
            side_effect=_timeout_exc(["pdftotext"]),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                drop._extract_pdf_text(Path("/nonexistent"))
            self.assertIn("timed out", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
