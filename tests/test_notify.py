from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from aiwiki.notify import notify_report_generated


class FakeHTTPResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def getcode(self) -> int:
        return self.status_code

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type
        del exc
        del tb
        return False


class NotifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        self.artifact = {
            "path": "output/reports/investing/market-brief.md",
            "title": "Market Brief",
            "protocol": "investing",
            "format": "markdown",
            "created_at": "2026-04-27T10:30:00+00:00",
        }

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _audit_path(self) -> Path:
        return self.root / ".aiwiki/state/audit.jsonl"

    def _read_audit(self) -> list[dict[str, object]]:
        path = self._audit_path()
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_no_config_no_op(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("aiwiki.notify.urllib.request.urlopen") as urlopen:
            notify_report_generated(self.root, self.artifact)

        urlopen.assert_not_called()
        self.assertEqual(self._read_audit(), [])

    def test_feishu_success_post_schema(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(http_request, timeout: int):
            captured["timeout"] = timeout
            captured["url"] = http_request.full_url
            captured["body"] = json.loads(http_request.data.decode("utf-8"))
            return FakeHTTPResponse(200)

        env = {
            "AIWIKI_NOTIFY_FEISHU_WEBHOOK_URL": "https://example.com/feishu",
            "AIWIKI_NOTIFY_ENABLED_CHANNELS": "feishu",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "aiwiki.notify.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ) as urlopen:
            notify_report_generated(self.root, self.artifact)

        urlopen.assert_called_once()
        self.assertEqual(captured["url"], "https://example.com/feishu")
        self.assertEqual(
            captured["body"],
            {
                "msg_type": "text",
                "content": {"text": "[investing] Market Brief — markdown — 2026-04-27 10:30"},
            },
        )
        self.assertIn("investing", captured["body"]["content"]["text"])
        self.assertIn("Market Brief", captured["body"]["content"]["text"])
        self.assertEqual(self._read_audit(), [])

    def test_wecom_success_post_schema(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(http_request, timeout: int):
            del timeout
            captured["url"] = http_request.full_url
            captured["body"] = json.loads(http_request.data.decode("utf-8"))
            return FakeHTTPResponse(200)

        env = {
            "AIWIKI_NOTIFY_WECOM_WEBHOOK_URL": "https://example.com/wecom",
            "AIWIKI_NOTIFY_ENABLED_CHANNELS": "wecom",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "aiwiki.notify.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ) as urlopen:
            notify_report_generated(self.root, self.artifact)

        urlopen.assert_called_once()
        self.assertEqual(captured["url"], "https://example.com/wecom")
        self.assertEqual(
            captured["body"],
            {"msgtype": "text", "text": {"content": "[investing] Market Brief — markdown — 2026-04-27 10:30"}},
        )
        self.assertIn("investing", captured["body"]["text"]["content"])
        self.assertIn("Market Brief", captured["body"]["text"]["content"])
        self.assertEqual(self._read_audit(), [])

    def test_http_500_records_notify_failed(self) -> None:
        http_error = urllib.error.HTTPError(
            url="https://example.com/feishu",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=io.BytesIO(b"server error"),
        )
        env = {
            "AIWIKI_NOTIFY_FEISHU_WEBHOOK_URL": "https://example.com/feishu",
            "AIWIKI_NOTIFY_ENABLED_CHANNELS": "feishu",
        }

        with patch.dict(os.environ, env, clear=True), patch(
            "aiwiki.notify.urllib.request.urlopen",
            side_effect=http_error,
        ):
            notify_report_generated(self.root, self.artifact)

        records = self._read_audit()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["event_type"], "notify_failed")
        self.assertEqual(record["channel"], "feishu")
        self.assertEqual(record["reason"], "http_status")
        self.assertEqual(record["status_code"], 500)
        self.assertEqual(record["error_type"], "HTTPError")
        self.assertEqual(
            record["subject"],
            {
                "kind": "output_report",
                "path": "output/reports/investing/market-brief.md",
                "protocol": "investing",
                "title": "Market Brief",
            },
        )
        self.assertFalse(record["revert_supported"])
        self.assertNotIn("https://example.com", json.dumps(record, ensure_ascii=False, sort_keys=True))

    def test_network_error_records_notify_failed(self) -> None:
        env = {
            "AIWIKI_NOTIFY_FEISHU_WEBHOOK_URL": "https://example.com/feishu",
            "AIWIKI_NOTIFY_ENABLED_CHANNELS": "feishu",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "aiwiki.notify.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            notify_report_generated(self.root, self.artifact)

        records = self._read_audit()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["event_type"], "notify_failed")
        self.assertEqual(record["reason"], "network_error")
        self.assertIsNone(record["status_code"])
        self.assertEqual(record["error_type"], "URLError")

    def test_enabled_channel_with_empty_url_no_op(self) -> None:
        env = {"AIWIKI_NOTIFY_ENABLED_CHANNELS": "feishu"}
        with patch.dict(os.environ, env, clear=True), patch("aiwiki.notify.urllib.request.urlopen") as urlopen:
            notify_report_generated(self.root, self.artifact)

        urlopen.assert_not_called()
        self.assertEqual(self._read_audit(), [])

    def test_audit_does_not_leak_webhook_url(self) -> None:
        env = {
            "AIWIKI_NOTIFY_FEISHU_WEBHOOK_URL": "https://test.example.com/SECRET-TOKEN-123",
            "AIWIKI_NOTIFY_ENABLED_CHANNELS": "feishu",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "aiwiki.notify.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            notify_report_generated(self.root, self.artifact)

        audit_text = self._audit_path().read_text(encoding="utf-8")
        self.assertNotIn("SECRET-TOKEN-123", audit_text)
        self.assertNotIn("test.example.com", audit_text)


if __name__ == "__main__":
    unittest.main()
