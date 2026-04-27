from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aiwiki import metrics_history


class MetricsHistoryTests(unittest.TestCase):
    def test_append_snapshot_creates_file_and_directory(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            metrics_history.append_snapshot(
                root,
                "2026-04-28T12:00:00Z",
                {"provenance_completeness": 0.9},
            )
            path = metrics_history.history_path(root)
            self.assertTrue(path.exists())
            line = path.read_text(encoding="utf-8").splitlines()[0]
            record = json.loads(line)
            self.assertEqual(record["ts"], "2026-04-28T12:00:00Z")
            self.assertEqual(record["metrics"], {"provenance_completeness": 0.9})

    def test_append_snapshot_is_append_only(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            metrics_history.append_snapshot(root, "2026-04-28T12:00:00Z", {"a": 1.0})
            metrics_history.append_snapshot(root, "2026-04-28T13:00:00Z", {"a": 2.0})
            lines = metrics_history.history_path(root).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)

    def test_find_baseline_returns_none_when_file_missing(self) -> None:
        with TemporaryDirectory() as tempdir:
            self.assertIsNone(
                metrics_history.find_baseline(Path(tempdir), "2026-04-28T12:00:00Z", 7)
            )

    def test_find_baseline_returns_none_when_no_sample_old_enough(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            # Sample is "now" — well within the 7d window, so it does NOT
            # qualify as a baseline.
            metrics_history.append_snapshot(root, "2026-04-28T12:00:00Z", {"a": 1.0})
            self.assertIsNone(
                metrics_history.find_baseline(root, "2026-04-28T12:00:00Z", 7)
            )

    def test_find_baseline_returns_most_recent_qualifying_sample(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            # 30d ago, 10d ago, today
            metrics_history.append_snapshot(root, "2026-03-29T12:00:00Z", {"a": 1.0})
            metrics_history.append_snapshot(root, "2026-04-18T12:00:00Z", {"a": 2.0})
            metrics_history.append_snapshot(root, "2026-04-28T12:00:00Z", {"a": 3.0})

            # 7d window: 10d-old sample qualifies; pick the more recent.
            result = metrics_history.find_baseline(root, "2026-04-28T12:00:00Z", 7)
            self.assertIsNotNone(result)
            assert result is not None  # narrow for type checker
            ts, metrics = result
            self.assertEqual(ts, "2026-04-18T12:00:00Z")
            self.assertEqual(metrics, {"a": 2.0})

            # 30d window: only 30d-old sample qualifies.
            result30 = metrics_history.find_baseline(root, "2026-04-28T12:00:00Z", 30)
            self.assertIsNotNone(result30)
            assert result30 is not None
            ts30, metrics30 = result30
            self.assertEqual(ts30, "2026-03-29T12:00:00Z")
            self.assertEqual(metrics30, {"a": 1.0})

    def test_find_baseline_skips_malformed_lines(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            path = metrics_history.history_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "not-json\n"
                + json.dumps({"ts": "bad-ts", "metrics": {"a": 1.0}})
                + "\n"
                + json.dumps({"ts": "2026-03-29T12:00:00Z", "metrics": {"a": 2.0}})
                + "\n",
                encoding="utf-8",
            )
            result = metrics_history.find_baseline(root, "2026-04-28T12:00:00Z", 7)
            self.assertIsNotNone(result)
            assert result is not None
            ts, metrics = result
            self.assertEqual(ts, "2026-03-29T12:00:00Z")
            self.assertEqual(metrics, {"a": 2.0})

    def test_format_delta_block_no_baseline(self) -> None:
        block = metrics_history.format_delta_block(
            window_label="7d",
            baseline=None,
            current={"a": 1.0},
        )
        self.assertEqual(block, "# delta 7d: no baseline within window")

    def test_format_delta_block_with_baseline(self) -> None:
        block = metrics_history.format_delta_block(
            window_label="7d",
            baseline=("2026-04-21T12:00:00Z", {"a": 0.5, "b": 1.0}),
            current={"a": 0.8, "b": 1.0},
        )
        self.assertIn("# delta vs 2026-04-21T12:00:00Z (7d ago baseline)", block)
        self.assertIn("a: 0.5 → 0.8 (+0.3)", block)
        self.assertIn("b: 1 → 1 (+0)", block)


if __name__ == "__main__":
    unittest.main()
