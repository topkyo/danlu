import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from aiwiki.app_execution import append_execution_receipt_history
from aiwiki.drop import drop_url
from aiwiki.execution.runtime_surfaces import nightly_health


@contextmanager
def _fake_lock():
    yield


class LockCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.addCleanup(self.tempdir.cleanup)

    def test_drop_url_takes_write_lock(self):
        called = MagicMock(side_effect=lambda root: _fake_lock())
        with patch("aiwiki.drop.runtime_write_lock", called):
            with patch(
                "aiwiki.drop._fetch_url",
                return_value={
                    "title": "t",
                    "text": "x",
                    "final_url": "https://e.test/",
                    "image_urls": [],
                    "content_type": "text/html",
                    "status": "200",
                    "browser_backend": "",
                    "description": "",
                    "extraction_mode": "plain-text",
                },
            ):
                try:
                    drop_url(self.root, "https://example.test/")
                except Exception:
                    pass
        called.assert_called_with(self.root)

    def test_nightly_health_takes_write_lock(self):
        called = MagicMock(side_effect=lambda root: _fake_lock())
        with patch("aiwiki.execution.runtime_surfaces.runtime_write_lock", called):
            try:
                nightly_health(self.root)
            except Exception:
                pass
        called.assert_called_with(self.root)

    def test_append_execution_receipt_history_takes_write_lock(self):
        called = MagicMock(side_effect=lambda root: _fake_lock())
        with patch("aiwiki.app_utils.runtime_write_lock", called):
            try:
                append_execution_receipt_history(self.root, {"id": "x"})
            except Exception:
                pass
        called.assert_called_with(self.root)
