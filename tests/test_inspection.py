from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.inspection import (
    find_planner_decisions_for_signal,
    find_signal_by_id,
    read_planner_decisions,
    read_signals,
)


class InspectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_jsonl(self, relative_path: str, records: list[dict[str, object]]) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )

    @staticmethod
    def _signal(
        signal_id: str,
        *,
        kind: str,
        trace_id: str,
        emitted_at: str,
        severity: str = "medium",
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "signal_id": signal_id,
            "dedupe_key": f"{kind}:research:runtime_history:{signal_id}",
            "kind": kind,
            "scope": {
                "protocol": "research",
                "source_ids": [],
                "concept_slugs": [],
                "elixir_refs": [],
                "judgment_refs": [],
            },
            "severity": severity,
            "evidence_refs": [],
            "emitted_at": emitted_at,
            "emitted_by": "compile",
            "source_kind": "runtime_history",
            "source_event_ref": ".aiwiki/state/runtime-history.jsonl#L1",
            "trace_id": trace_id,
        }

    @staticmethod
    def _planner(
        signal_id: str,
        *,
        decision: str,
        trace_id: str,
        decided_at: str,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "signal_id": signal_id,
            "dedupe_key": f"{signal_id}:observe_only",
            "trace_id": trace_id,
            "decision": decision,
            "mode": "observe_only",
            "reason_codes": ["review_feedback_routine"],
            "budget_used": {},
            "locks_acquired": [],
            "primitive_refs": [],
            "side_effects_allowed": False,
            "decided_at": decided_at,
        }

    def test_read_signals_returns_empty_when_file_missing(self) -> None:
        self.assertEqual(read_signals(self.root), [])

    def test_read_signals_filters_by_kind(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal("sig-20260424-kind0001", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440000", emitted_at="2026-04-24T10:00:00Z"),
                self._signal("sig-20260424-kind0002", kind="review_feedback", trace_id="550e8400-e29b-41d4-a716-446655440001", emitted_at="2026-04-24T10:01:00Z"),
            ],
        )

        items = read_signals(self.root, kind="drift")
        self.assertEqual([item["signal_id"] for item in items], ["sig-20260424-kind0001"])

    def test_read_signals_filters_by_trace_id(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal("sig-20260424-trace001", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440000", emitted_at="2026-04-24T10:00:00Z"),
                self._signal("sig-20260424-trace002", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440001", emitted_at="2026-04-24T10:01:00Z"),
            ],
        )

        items = read_signals(self.root, trace_id="550e8400-e29b-41d4-a716-446655440001")
        self.assertEqual([item["signal_id"] for item in items], ["sig-20260424-trace002"])

    def test_read_signals_filters_by_since(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal("sig-20260424-since001", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440000", emitted_at="2026-04-24T09:59:59Z"),
                self._signal("sig-20260424-since002", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440000", emitted_at="2026-04-24T10:00:00Z"),
            ],
        )

        items = read_signals(self.root, since="2026-04-24T10:00:00Z")
        self.assertEqual([item["signal_id"] for item in items], ["sig-20260424-since002"])

    def test_read_signals_applies_limit(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal("sig-20260424-limit001", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440000", emitted_at="2026-04-24T10:00:00Z"),
                self._signal("sig-20260424-limit002", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440000", emitted_at="2026-04-24T10:00:01Z"),
                self._signal("sig-20260424-limit003", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440000", emitted_at="2026-04-24T10:00:02Z"),
            ],
        )

        items = read_signals(self.root, limit=2)
        self.assertEqual(len(items), 2)
        self.assertEqual([item["signal_id"] for item in items], ["sig-20260424-limit003", "sig-20260424-limit002"])

    def test_read_signals_returns_recent_first(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal("sig-20260424-order001", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440000", emitted_at="2026-04-24T10:00:00Z"),
                self._signal("sig-20260424-order003", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440000", emitted_at="2026-04-24T10:00:03Z"),
                self._signal("sig-20260424-order002", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440000", emitted_at="2026-04-24T10:00:02Z"),
            ],
        )

        items = read_signals(self.root)
        self.assertEqual(
            [item["signal_id"] for item in items],
            ["sig-20260424-order003", "sig-20260424-order002", "sig-20260424-order001"],
        )

    def test_find_signal_by_id_returns_none_when_missing(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal("sig-20260424-find0001", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440000", emitted_at="2026-04-24T10:00:00Z")
            ],
        )

        self.assertIsNone(find_signal_by_id(self.root, "sig-20260424-not-found"))

    def test_find_signal_by_id_returns_record(self) -> None:
        target = self._signal(
            "sig-20260424-find0002",
            kind="runtime_failure",
            trace_id="550e8400-e29b-41d4-a716-446655440000",
            emitted_at="2026-04-24T10:00:00Z",
        )
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal("sig-20260424-find0001", kind="drift", trace_id="550e8400-e29b-41d4-a716-446655440000", emitted_at="2026-04-24T09:59:00Z"),
                target,
            ],
        )

        found = find_signal_by_id(self.root, "sig-20260424-find0002")
        self.assertIsNotNone(found)
        self.assertEqual(found["kind"], "runtime_failure")

    def test_find_planner_decisions_for_signal(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [
                self._planner("sig-20260424-pfind0001", decision="enqueue-light", trace_id="550e8400-e29b-41d4-a716-446655440000", decided_at="2026-04-24T10:00:00Z"),
                self._planner("sig-20260424-pfind0002", decision="enqueue-heavy", trace_id="550e8400-e29b-41d4-a716-446655440000", decided_at="2026-04-24T10:00:01Z"),
            ],
        )

        items = find_planner_decisions_for_signal(self.root, "sig-20260424-pfind0002")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["decision"], "enqueue-heavy")

    def test_read_planner_decisions_filters_by_decision(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [
                self._planner("sig-20260424-pdec0001", decision="enqueue-light", trace_id="550e8400-e29b-41d4-a716-446655440000", decided_at="2026-04-24T10:00:00Z"),
                self._planner("sig-20260424-pdec0002", decision="enqueue-heavy", trace_id="550e8400-e29b-41d4-a716-446655440000", decided_at="2026-04-24T10:00:01Z"),
            ],
        )

        items = read_planner_decisions(self.root, decision="enqueue-heavy")
        self.assertEqual([item["signal_id"] for item in items], ["sig-20260424-pdec0002"])

    def test_read_planner_decisions_filters_by_signal_id(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [
                self._planner("sig-20260424-psid0001", decision="enqueue-light", trace_id="550e8400-e29b-41d4-a716-446655440000", decided_at="2026-04-24T10:00:00Z"),
                self._planner("sig-20260424-psid0002", decision="enqueue-heavy", trace_id="550e8400-e29b-41d4-a716-446655440000", decided_at="2026-04-24T10:00:01Z"),
            ],
        )

        items = read_planner_decisions(self.root, signal_id="sig-20260424-psid0001")
        self.assertEqual([item["signal_id"] for item in items], ["sig-20260424-psid0001"])

    def test_read_planner_decisions_returns_empty_when_file_missing(self) -> None:
        self.assertEqual(read_planner_decisions(self.root), [])

    def test_read_planner_decisions_filters_by_trace_id(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [
                self._planner("sig-20260424-ptrace0001", decision="enqueue-light", trace_id="550e8400-e29b-41d4-a716-446655440000", decided_at="2026-04-24T10:00:00Z"),
                self._planner("sig-20260424-ptrace0002", decision="enqueue-heavy", trace_id="550e8400-e29b-41d4-a716-446655440001", decided_at="2026-04-24T10:00:01Z"),
            ],
        )

        items = read_planner_decisions(self.root, trace_id="550e8400-e29b-41d4-a716-446655440001")
        self.assertEqual([item["signal_id"] for item in items], ["sig-20260424-ptrace0002"])

    def test_read_signals_invalid_since_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            read_signals(self.root, since="bad-since")

    def test_read_signals_invalid_limit_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            read_signals(self.root, limit=0)

    def test_read_planner_decisions_returns_recent_first_and_since(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [
                self._planner("sig-20260424-psince0001", decision="ignore", trace_id="550e8400-e29b-41d4-a716-446655440000", decided_at="2026-04-24T09:59:59Z"),
                self._planner("sig-20260424-psince0002", decision="enqueue-light", trace_id="550e8400-e29b-41d4-a716-446655440000", decided_at="2026-04-24T10:00:00Z"),
                self._planner("sig-20260424-psince0003", decision="enqueue-heavy", trace_id="550e8400-e29b-41d4-a716-446655440000", decided_at="2026-04-24T10:00:01Z"),
            ],
        )

        items = read_planner_decisions(self.root, since="2026-04-24T10:00:00Z")
        self.assertEqual(
            [item["signal_id"] for item in items],
            ["sig-20260424-psince0003", "sig-20260424-psince0002"],
        )

    def test_read_signals_invalid_jsonl_raises_value_error(self) -> None:
        path = self.root / ".aiwiki/state/signals.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{bad\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Invalid JSONL"):
            read_signals(self.root)

    def test_read_planner_decisions_non_object_jsonl_raises_value_error(self) -> None:
        path = self.root / ".aiwiki/state/planner-log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "expected object record"):
            read_planner_decisions(self.root)


if __name__ == "__main__":
    unittest.main()
