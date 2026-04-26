from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.execution.audit_preview import (
    append_universal_audit_record,
    backfill_universal_audit_stream,
    preview_universal_audit_stream,
)


class AuditPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_jsonl(self, relative: str, records: list[dict[str, object]]) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )

    def test_preview_normalizes_existing_audit_sources_without_writing(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/execution-receipts.jsonl",
            [
                {
                    "kind": "execution-receipt",
                    "operation": "apply",
                    "action_id": "act-1",
                    "applied_at": "2026-04-26T10:00:00+00:00",
                    "trace_id": "trace-exec",
                    "subject_kind": "machine_memory_action",
                    "subject_id": "act-1",
                    "revert_supported": True,
                }
            ],
        )
        self._write_jsonl(
            ".aiwiki/logs/llm-receipts.jsonl",
            [
                {
                    "kind": "llm-receipt",
                    "status": "ok",
                    "run_id": "run-1",
                    "created_at": "2026-04-26T10:01:00+00:00",
                }
            ],
        )
        self._write_jsonl(
            ".aiwiki/state/runtime-history.jsonl",
            [
                {
                    "event_type": "nightly",
                    "recorded_at": "2026-04-26T10:02:00+00:00",
                    "trace_id": "trace-runtime",
                }
            ],
        )
        age_path = self.root / ".aiwiki/state/protocol_learnings_age.json"
        age_path.parent.mkdir(parents=True, exist_ok=True)
        age_path.write_text(
            json.dumps(
                {
                    "apply": True,
                    "run_at": "2026-04-26T10:03:00+00:00",
                    "aged_ids": ["old-active"],
                    "aged": [{"learning_id": "old-active"}],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        source_snapshots = {
            relative: (self.root / relative).read_text(encoding="utf-8")
            for relative in (
                ".aiwiki/state/execution-receipts.jsonl",
                ".aiwiki/logs/llm-receipts.jsonl",
                ".aiwiki/state/runtime-history.jsonl",
                ".aiwiki/state/protocol_learnings_age.json",
            )
        }

        result = preview_universal_audit_stream(self.root)
        repeat = preview_universal_audit_stream(self.root)

        self.assertFalse(result["side_effects_allowed"])
        self.assertFalse(result["audit_stream_exists"])
        self.assertEqual(result["audit_stream_path"], ".aiwiki/state/audit.jsonl")
        self.assertEqual(result["scanned_count"], 4)
        self.assertEqual(result["returned_count"], 4)
        self.assertEqual(
            result["source_counts"],
            {
                "execution_receipts": 1,
                "llm_receipts": 1,
                "runtime_history": 1,
                "protocol_learnings_age": 1,
            },
        )
        self.assertEqual(result["records"], repeat["records"])
        records = {record["source_stream"]: record for record in result["records"]}
        self.assertEqual(records["execution_receipts"]["event_type"], "apply")
        self.assertEqual(records["execution_receipts"]["source_ref"], ".aiwiki/state/execution-receipts.jsonl#L1")
        self.assertEqual(records["execution_receipts"]["trace_id"], "trace-exec")
        self.assertEqual(records["execution_receipts"]["subject"], {"kind": "machine_memory_action", "id": "act-1"})
        self.assertTrue(records["execution_receipts"]["revert_supported"])
        self.assertEqual(records["llm_receipts"]["event_type"], "ok")
        self.assertEqual(records["runtime_history"]["event_type"], "nightly")
        self.assertEqual(records["protocol_learnings_age"]["event_type"], "protocol_learnings_age")
        self.assertFalse((self.root / ".aiwiki/state/audit.jsonl").exists())
        for relative, before in source_snapshots.items():
            self.assertEqual((self.root / relative).read_text(encoding="utf-8"), before)

    def test_preview_limit_caps_returned_records_not_scan_count(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/execution-receipts.jsonl",
            [
                {"operation": "apply", "action_id": "act-1"},
                {"operation": "revert", "action_id": "act-2"},
            ],
        )
        self._write_jsonl(".aiwiki/state/runtime-history.jsonl", [{"event_type": "nightly"}])

        result = preview_universal_audit_stream(self.root, limit=2)

        self.assertEqual(result["scanned_count"], 3)
        self.assertEqual(result["returned_count"], 2)
        self.assertEqual([record["source_ref"] for record in result["records"]], [
            ".aiwiki/state/execution-receipts.jsonl#L1",
            ".aiwiki/state/execution-receipts.jsonl#L2",
        ])

    def test_preview_rejects_non_positive_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "limit must be a positive integer"):
            preview_universal_audit_stream(self.root, limit=0)

    def test_backfill_appends_missing_records_idempotently(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/execution-receipts.jsonl",
            [
                {
                    "operation": "apply",
                    "action_id": "act-1",
                    "applied_at": "2026-04-26T10:00:00+00:00",
                    "revert_supported": True,
                },
                {
                    "operation": "revert",
                    "action_id": "act-2",
                    "applied_at": "2026-04-26T10:01:00+00:00",
                },
            ],
        )
        source_before = (self.root / ".aiwiki/state/execution-receipts.jsonl").read_text(encoding="utf-8")

        dry_run = backfill_universal_audit_stream(self.root, limit=10, apply=False)
        self.assertEqual(dry_run["appended_count"], 0)
        self.assertEqual(dry_run["skipped_existing_count"], 0)
        self.assertFalse((self.root / ".aiwiki/state/audit.jsonl").exists())

        first = backfill_universal_audit_stream(self.root, limit=10, apply=True)
        second = backfill_universal_audit_stream(self.root, limit=10, apply=True)

        self.assertEqual(first["appended_count"], 2)
        self.assertEqual(first["skipped_existing_count"], 0)
        self.assertEqual(second["appended_count"], 0)
        self.assertEqual(second["skipped_existing_count"], 2)
        audit_records = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/audit.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(audit_records), 2)
        self.assertEqual(len({record["audit_event_id"] for record in audit_records}), 2)
        self.assertEqual((self.root / ".aiwiki/state/execution-receipts.jsonl").read_text(encoding="utf-8"), source_before)

    def test_backfill_skips_records_already_written_by_direct_append(self) -> None:
        source_record = {
            "operation": "apply",
            "action_id": "act-direct",
            "applied_at": "2026-04-26T10:00:00+00:00",
            "trace_id": "trace-direct",
            "subject_kind": "machine_memory_action",
            "subject_id": "act-direct",
            "revert_supported": True,
        }
        self._write_jsonl(".aiwiki/state/execution-receipts.jsonl", [source_record])
        source_before = (self.root / ".aiwiki/state/execution-receipts.jsonl").read_text(encoding="utf-8")

        direct = append_universal_audit_record(
            self.root,
            source_stream="execution_receipts",
            source_ref=".aiwiki/state/execution-receipts.jsonl#L1",
            document=source_record,
        )
        preview = preview_universal_audit_stream(self.root, limit=10)
        backfill = backfill_universal_audit_stream(self.root, limit=10, apply=True)

        self.assertEqual(direct["status"], "appended")
        self.assertEqual(preview["records"][0]["audit_event_id"], direct["record"]["audit_event_id"])
        self.assertEqual(backfill["appended_count"], 0)
        self.assertEqual(backfill["skipped_existing_count"], 1)
        audit_records = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(audit_records, [direct["record"]])
        self.assertEqual((self.root / ".aiwiki/state/execution-receipts.jsonl").read_text(encoding="utf-8"), source_before)
