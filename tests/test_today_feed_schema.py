"""Validate build_today_feed() output against schema/today-feed.json."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from aiwiki.cli.dispatch_helpers import _today_feed_to_json
from aiwiki.today_feed import FeedEntry, build_today_feed, priority_for_kind

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schema" / "today-feed.json"


def _validate_entry(entry: FeedEntry, schema: dict) -> None:
    payload = {
        "kind": entry.kind,
        "title": entry.title,
        "summary": entry.summary,
        "target": entry.target,
        "timestamp": entry.timestamp,
        "priority": priority_for_kind(entry.kind),
        "protocol": entry.protocol,
    }

    required = set(schema.get("required") or [])
    for key in required:
        if key not in payload or payload[key] in ("", None):
            raise AssertionError(f"missing required field {key!r} in {payload!r}")

    kind_enum = schema["properties"]["kind"]["enum"]
    if payload["kind"] not in kind_enum:
        raise AssertionError(f"invalid kind {payload['kind']!r}")

    priority_schema = schema["properties"]["priority"]
    minimum = priority_schema.get("minimum", 1)
    maximum = priority_schema.get("maximum", 6)
    if not minimum <= payload["priority"] <= maximum:
        raise AssertionError(f"priority out of range: {payload['priority']}")


class TodayFeedSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_fixture_entries_match_schema(self) -> None:
        summary = {
            "generated_at": "2026-05-13T10:00:00Z",
            "active_protocol": "investing",
            "review_backlog_counts": {"pending_judgments": 1},
            "counter_evidence_pages": [],
            "drift_warnings": [],
            "review_controls": {"l3_proposals": []},
            "l3_proposals": [{"proposal_id": "p1", "needs_attention": True}],
            "recent_outputs": [
                {
                    "path": "output/reports/r.md",
                    "title": "报告",
                    "summary": "摘要",
                    "generated_at": "2026-05-13T09:00:00Z",
                }
            ],
            "recent_receipts": [],
            "suggested_next_actions": [],
            "metrics_history_delta": {"available": False},
            "today_snooze": {"items": []},
        }
        feed = build_today_feed(summary)
        self.assertGreaterEqual(len(feed), 2)
        for entry in feed:
            _validate_entry(entry, self.schema)
        serialized = _today_feed_to_json(feed, summary)
        sections = [value for value in serialized.values() if isinstance(value, list)]
        serialized_entries = [entry for section in sections for entry in section if isinstance(entry, dict)]
        self.assertGreaterEqual(len(serialized_entries), 2)
        required = set(self.schema.get("required") or [])
        for entry in serialized_entries:
            missing = {key for key in required if key not in entry or entry[key] in ("", None)}
            self.assertFalse(missing, f"missing required fields {missing!r} in {entry!r}")

    def test_empty_summary_returns_no_entries(self) -> None:
        self.assertEqual(build_today_feed({}), [])


if __name__ == "__main__":
    unittest.main()
