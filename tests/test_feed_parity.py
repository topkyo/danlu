from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from aiwiki.app_shell.summary import _build_recent_raw_inputs, build_shell_summary
from aiwiki.app_state import runtime_history_path
from aiwiki.today_feed import build_today_feed

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_runtime_history(root: Path, events: list[dict[str, object]]) -> None:
    path = runtime_history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events), encoding="utf-8")


class TestFeedParity(unittest.TestCase):
    def test_recent_raw_inputs_includes_drop_history(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            events = [
                {
                    "event_type": "raw-added",
                    "stored_path": "raw/inbox/a.md",
                    "original_path": "https://e.com/a",
                    "source_type": "url",
                    "title": "A",
                    "occurred_at": "2026-05-06T08:00:00+00:00",
                    "protocol": "general",
                },
                {
                    "event_type": "raw-added",
                    "stored_path": "raw/inbox/b.md",
                    "original_path": "/tmp/b.pdf",
                    "source_type": "pdf",
                    "title": "B",
                    "occurred_at": "2026-05-06T09:00:00+00:00",
                    "protocol": "research",
                },
            ]
            _write_runtime_history(root, events)

            summary = build_shell_summary(root)

            self.assertEqual(len(summary["recent_raw_inputs"]), 2)
            self.assertEqual(
                summary["recent_raw_inputs"][0],
                {
                    "stored_path": "raw/inbox/b.md",
                    "original_path": "/tmp/b.pdf",
                    "source_type": "pdf",
                    "title": "B",
                    "occurred_at": "2026-05-06T09:00:00+00:00",
                    "protocol": "research",
                },
            )
            self.assertEqual(summary["recent_raw_inputs"][1]["stored_path"], "raw/inbox/a.md")

    def test_recent_raw_inputs_empty_when_no_history(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            summary = build_shell_summary(root)
            self.assertEqual(summary["recent_raw_inputs"], [])

    def test_recent_raw_inputs_corrupt_history_fail_soft(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            path = runtime_history_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"{not valid json\n")

            self.assertEqual(_build_recent_raw_inputs(root, limit=8), [])

    def test_recent_raw_inputs_limit_8(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            events = [
                {
                    "event_type": "raw-added",
                    "stored_path": f"raw/inbox/{idx}.md",
                    "original_path": f"https://e.com/{idx}",
                    "source_type": "url",
                    "title": f"Item {idx}",
                    "occurred_at": f"2026-05-06T{idx:02d}:00:00+00:00",
                    "protocol": "general",
                }
                for idx in range(12)
            ]
            _write_runtime_history(root, events)

            raw_inputs = _build_recent_raw_inputs(root, limit=8)

            self.assertEqual(len(raw_inputs), 8)
            self.assertEqual(raw_inputs[0]["stored_path"], "raw/inbox/11.md")
            self.assertEqual(raw_inputs[-1]["stored_path"], "raw/inbox/4.md")

    def test_recent_raw_inputs_filters_non_raw_added(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            _write_runtime_history(
                root,
                [
                    {"event_type": "compile-finished", "stored_path": "raw/inbox/no.md"},
                    {
                        "event_type": "raw-added",
                        "stored_path": "raw/inbox/yes.md",
                        "occurred_at": "2026-05-06T09:00:00+00:00",
                    },
                ],
            )

            raw_inputs = _build_recent_raw_inputs(root, limit=8)

            self.assertEqual(len(raw_inputs), 1)
            self.assertEqual(raw_inputs[0]["stored_path"], "raw/inbox/yes.md")

    def test_today_feed_renders_raw_input_today(self) -> None:
        summary = {
            "generated_at": "2026-05-06T10:00:00+00:00",
            "recent_raw_inputs": [
                {
                    "stored_path": "raw/inbox/x.md",
                    "original_path": "https://e.com",
                    "title": "X",
                    "occurred_at": "2026-05-06T09:00:00+00:00",
                    "source_type": "url",
                    "protocol": "general",
                }
            ],
        }

        feed = build_today_feed(summary)

        raw_entries = [entry for entry in feed if entry.target == "raw/inbox/x.md"]
        self.assertGreaterEqual(len(raw_entries), 1)
        self.assertEqual(raw_entries[0].kind, "action")
        self.assertIn("已投料", raw_entries[0].title)

    def test_today_feed_skips_yesterday_raw_input(self) -> None:
        summary = {
            "generated_at": "2026-05-06T10:00:00+00:00",
            "recent_raw_inputs": [
                {
                    "stored_path": "raw/inbox/x.md",
                    "title": "X",
                    "occurred_at": "2026-05-05T09:00:00+00:00",
                }
            ],
        }

        feed = build_today_feed(summary)

        self.assertFalse(any(entry.target == "raw/inbox/x.md" for entry in feed))

    def test_today_feed_skips_raw_input_missing_stored_path(self) -> None:
        summary = {
            "generated_at": "2026-05-06T10:00:00+00:00",
            "recent_raw_inputs": [
                {
                    "stored_path": "",
                    "title": "X",
                    "occurred_at": "2026-05-06T09:00:00+00:00",
                }
            ],
        }

        feed = build_today_feed(summary)

        self.assertFalse(any("已投料" in entry.title for entry in feed))

    def test_extract_primary_path_recognizes_note_path(self) -> None:
        content = (PROJECT_ROOT / ".obsidian/plugins/furnace-product-shell/src/plugin_helpers.js").read_text(
            encoding="utf-8"
        )
        match = re.search(r"const\s+candidateKeys\s*=\s*\[(?P<body>.*?)\]", content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group("body") if match else ""
        for key in ('"note_path"', '"stored_path"', '"asset_path"'):
            self.assertIn(key, body)

    def test_reconcile_pending_includes_recent_raw_inputs(self) -> None:
        content = (PROJECT_ROOT / ".obsidian/plugins/furnace-product-shell/src/plugin.js").read_text(encoding="utf-8")
        match = re.search(r"reconcilePendingSubmissions\(summary\) \{(?P<body>.*?)\n  \}\n\n  async runUniversalInputCommand", content, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group("body") if match else ""
        self.assertIn("recent_raw_inputs", body)
        self.assertIn('target = "raw"', body)
        self.assertIn("stored_path", body)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    return loader.loadTestsFromTestCase(TestFeedParity)
