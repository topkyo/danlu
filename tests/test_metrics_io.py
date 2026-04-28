from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki import metrics_io
from aiwiki.metrics import compute_review_closure_rate
from aiwiki.metrics_io import build_metrics_snapshot


class MetricsIOTests(unittest.TestCase):
    def test_empty_vault_returns_empty_snapshot_tuples(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tempdir:
            snapshot = build_metrics_snapshot(Path(tempdir), now_iso="2026-04-27T00:00:00Z")

        self.assertEqual(snapshot.wiki_pages, ())
        # M7.3 Stage A: review_counts now reflects backlog; empty vault still
        # has no decisions/judgments folders, so counts are zero rather than ().
        self.assertEqual(dict(snapshot.review_counts), {"pending_decisions": 0, "pending_judgments": 0})
        self.assertEqual(snapshot.receipts, ())
        self.assertEqual(snapshot.proposals, ())
        self.assertEqual(snapshot.outputs, ())

    def test_reader_handles_glob_errors_as_empty(self) -> None:
        class BadPath:
            def __truediv__(self, _value: str) -> "BadPath":
                return self

            def exists(self) -> bool:
                return True

            def glob(self, _pattern: str) -> list[Path]:
                raise OSError("boom")

        self.assertEqual(list(metrics_io._read_wiki_pages(BadPath())), [])
        self.assertEqual(list(metrics_io._read_outputs(BadPath())), [])
        self.assertEqual(metrics_io._receipt_json_paths(BadPath()), [])

    def test_wiki_page_frontmatter_is_parsed(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            path = root / "wiki" / "sources" / "page.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                "---\nsource_url: https://example.com\ncaptured_at: 2026-04-20T00:00:00Z\nderived_from:\n  - raw/a.md\nupdated_at: 2026-04-21T00:00:00Z\n---\n# Page\n",
                encoding="utf-8",
            )

            snapshot = build_metrics_snapshot(root, now_iso="2026-04-27T00:00:00Z")

        self.assertEqual(len(snapshot.wiki_pages), 1)
        page = snapshot.wiki_pages[0]
        self.assertEqual(page.path, "wiki/sources/page.md")
        self.assertTrue(page.has_source_url)
        self.assertTrue(page.has_captured_at)
        self.assertTrue(page.has_derived_from)
        self.assertEqual(page.updated_at, "2026-04-21T00:00:00Z")

    def test_damaged_frontmatter_still_yields_incomplete_page(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            path = root / "wiki" / "sources" / "bad.md"
            path.parent.mkdir(parents=True)
            path.write_text("---\nnot yaml\n# Page\n", encoding="utf-8")

            snapshot = build_metrics_snapshot(root, now_iso="2026-04-27T00:00:00Z")

        self.assertEqual(len(snapshot.wiki_pages), 1)
        page = snapshot.wiki_pages[0]
        self.assertFalse(page.has_source_url)
        self.assertFalse(page.has_captured_at)
        self.assertFalse(page.has_derived_from)

    def test_now_iso_default_uses_clock_module(self) -> None:
        from datetime import datetime, timezone
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tempdir:
            with patch("aiwiki.clock.utc_now", return_value=datetime(2026, 4, 27, tzinfo=timezone.utc)):
                snapshot = build_metrics_snapshot(Path(tempdir))

        self.assertEqual(snapshot.now_iso, "2026-04-27T00:00:00+00:00")

    def test_custom_now_iso_and_stale_threshold_are_passed_through(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tempdir:
            snapshot = build_metrics_snapshot(Path(tempdir), now_iso="2026-01-01T00:00:00Z", stale_threshold_days=9)

        self.assertEqual(snapshot.now_iso, "2026-01-01T00:00:00Z")
        self.assertEqual(snapshot.stale_threshold_days, 9)

    def test_receipts_directory_missing_returns_empty_tuple(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "output" / "control").mkdir(parents=True)
            snapshot = build_metrics_snapshot(root, now_iso="2026-04-27T00:00:00Z")

        self.assertEqual(snapshot.receipts, ())

    def test_reads_execution_receipt_json_and_history_jsonl(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            receipt_dir = root / "output" / "control" / "execution-receipts"
            receipt_dir.mkdir(parents=True)
            (receipt_dir / "a.json").write_text(
                json.dumps({"operation": "apply", "subject_kind": "judgment", "subject_id": "j1", "target_file": "wiki/judgments/j1.md", "applied_at": "2026-04-20T00:00:00Z"}),
                encoding="utf-8",
            )
            (receipt_dir / "bad.json").write_text("not-json", encoding="utf-8")
            history = root / ".aiwiki" / "state" / "execution-receipts.jsonl"
            history.parent.mkdir(parents=True)
            history.write_text(
                "\nnot-json\n[]\n"
                + json.dumps({"operation": "close", "subject_kind": "review", "subject_id": "r1", "applied_at": "2026-04-21T00:00:00Z"})
                + "\n",
                encoding="utf-8",
            )

            snapshot = build_metrics_snapshot(root, now_iso="2026-04-27T00:00:00Z")

        self.assertEqual(len(snapshot.receipts), 2)
        self.assertEqual(snapshot.receipts[0].target_subject_id, "wiki/judgments/j1.md")

    def test_receipt_history_dedupes_receipt_path(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            receipt_dir = root / "output" / "control" / "execution-receipts"
            receipt_dir.mkdir(parents=True)
            rel_path = "output/control/execution-receipts/a.json"
            payload = {"operation": "apply", "subject_kind": "judgment", "subject_id": "j1", "receipt_path": rel_path}
            (receipt_dir / "a.json").write_text(json.dumps(payload), encoding="utf-8")
            history = root / ".aiwiki" / "state" / "execution-receipts.jsonl"
            history.parent.mkdir(parents=True)
            history.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            snapshot = build_metrics_snapshot(root, now_iso="2026-04-27T00:00:00Z")

        self.assertEqual(len(snapshot.receipts), 1)

    def test_reads_outputs_and_proposals(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            output = root / "output" / "packs" / "report.md"
            output.parent.mkdir(parents=True)
            output.write_text("---\nderived_from:\n  - wiki/sources/a.md\ngenerated_at: 2026-04-20T00:00:00Z\n---\n# Report\n", encoding="utf-8")
            control_output = root / "output" / "control" / "ignored.md"
            control_output.parent.mkdir(parents=True)
            control_output.write_text("# Ignore\n", encoding="utf-8")
            state = root / ".aiwiki" / "state" / "l3-proposals.json"
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps({"proposals": [{"proposal_id": "p1", "state": "accepted", "created_at": "c", "accepted_at": "d"}]}), encoding="utf-8")

            snapshot = build_metrics_snapshot(root, now_iso="2026-04-27T00:00:00Z")

        self.assertEqual(len(snapshot.outputs), 1)
        self.assertEqual(snapshot.outputs[0].derived_from, ["wiki/sources/a.md"])
        self.assertEqual(len(snapshot.proposals), 1)
        self.assertEqual(snapshot.proposals[0].status, "accepted")

    def test_reads_markdown_proposal_and_scalar_output_derived_from(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            proposal = root / "output" / "_proposals" / "judge" / "p2.md"
            proposal.parent.mkdir(parents=True)
            proposal.write_text("---\nproposal_id: p2\nstate: candidate\ncreated_at: c\n---\n# Proposal\n", encoding="utf-8")
            output = root / "output" / "report.md"
            output.write_text("---\nderived_from: wiki/sources/a.md\ncreated_at: g\n---\n# Report\n", encoding="utf-8")

            snapshot = build_metrics_snapshot(root, now_iso="2026-04-27T00:00:00Z")

        self.assertEqual(snapshot.proposals[0].proposal_id, "p2")
        self.assertEqual(snapshot.proposals[0].status, "pending")
        report = next(output for output in snapshot.outputs if output.path == "output/report.md")
        self.assertEqual(report.derived_from, ["wiki/sources/a.md"])
        self.assertEqual(report.generated_at, "g")

    def test_safe_relative_path_handles_outside_path(self) -> None:
        self.assertTrue(metrics_io._safe_relative_path(Path("/tmp/root"), Path("/other/file.md")).endswith("/other/file.md"))

    def test_review_counts_reads_pending_decisions_and_judgments(self) -> None:
        """M7.3 Stage A: _read_review_counts no longer stub; reflects backlog."""

        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            decisions_dir = root / "wiki" / "decisions"
            judgments_dir = root / "wiki" / "judgments"
            decisions_dir.mkdir(parents=True)
            judgments_dir.mkdir(parents=True)
            (decisions_dir / "d1.md").write_text(
                "---\nkind: decision\ntitle: D1\nstatus: proposed\n---\nbody\n",
                encoding="utf-8",
            )
            (decisions_dir / "d2.md").write_text(
                "---\nkind: decision\ntitle: D2\nstatus: accepted\nreviewed_at: 2026-04-01T00:00:00Z\n---\nbody\n",
                encoding="utf-8",
            )
            (judgments_dir / "j1.md").write_text(
                "---\nkind: judgment\ntitle: J1\nstatus: tentative\n---\nbody\n",
                encoding="utf-8",
            )

            snapshot = build_metrics_snapshot(root, now_iso="2026-04-27T00:00:00Z")

        counts = dict(snapshot.review_counts)
        self.assertIn("pending_decisions", counts)
        self.assertIn("pending_judgments", counts)
        self.assertEqual(counts["pending_decisions"], 1)
        self.assertEqual(counts["pending_judgments"], 1)

    def test_page_review_history_counts_as_review_closure_activity(self) -> None:
        """Round 11: review-page writes page metadata, not execution receipts."""

        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            judgments_dir = root / "wiki" / "judgments"
            judgments_dir.mkdir(parents=True)
            (judgments_dir / "j1.md").write_text(
                "---\n"
                "id: judgment-1\n"
                "kind: judgment\n"
                "title: J1\n"
                "status: confirmed\n"
                "reviewed_at: 2026-04-26T00:00:00Z\n"
                "---\nbody\n",
                encoding="utf-8",
            )
            (judgments_dir / "j2.md").write_text(
                "---\n"
                "id: judgment-2\n"
                "kind: judgment\n"
                "title: J2\n"
                "status: tracking\n"
                "reviewed_at: 2026-04-26T00:00:00Z\n"
                "---\nbody\n",
                encoding="utf-8",
            )

            snapshot = build_metrics_snapshot(root, now_iso="2026-04-27T00:00:00Z")

        review_receipts = [receipt for receipt in snapshot.receipts if receipt.subject_kind == "review"]
        self.assertEqual(len(review_receipts), 1)
        self.assertEqual(review_receipts[0].operation, "approve")
        self.assertEqual(review_receipts[0].subject_id, "judgment-1")
        metric = compute_review_closure_rate(snapshot)
        self.assertEqual(metric.value, 0.5)
        self.assertEqual(metric.sample_size, 2)


if __name__ == "__main__":
    unittest.main()
