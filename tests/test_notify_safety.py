from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.notify import notify_report_generated


class NotifySafetyTests(unittest.TestCase):
    def test_webhook_uses_safe_fetch(self) -> None:
        artifact = {
            "path": "output/reports/investing/report.md",
            "title": "Report",
            "protocol": "investing",
            "format": "markdown",
            "created_at": "2026-04-27T10:30:00+00:00",
        }
        env = {
            "AIWIKI_NOTIFY_FEISHU_WEBHOOK_URL": "https://example.com/feishu",
            "AIWIKI_NOTIFY_ENABLED_CHANNELS": "feishu",
        }

        with tempfile.TemporaryDirectory() as tempdir, patch.dict(os.environ, env, clear=True), patch(
            "aiwiki.notify.safe_fetch",
            return_value=(b"ok", "https://example.com/feishu"),
        ) as mock_fetch:
            notify_report_generated(Path(tempdir), artifact)

        mock_fetch.assert_called_once()
        self.assertEqual(mock_fetch.call_args.args[0], "https://example.com/feishu")
        call_kwargs = mock_fetch.call_args.kwargs
        self.assertEqual(call_kwargs["method"], "POST")
        self.assertEqual(call_kwargs["max_bytes"], 1 * 1024 * 1024)
        self.assertEqual(call_kwargs["timeout"], 5)


if __name__ == "__main__":
    unittest.main()
