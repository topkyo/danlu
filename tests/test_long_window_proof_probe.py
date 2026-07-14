from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import date
from pathlib import Path


def _load_probe():
    path = Path(__file__).resolve().parents[1] / "scripts" / "long_window_proof_probe.py"
    spec = importlib.util.spec_from_file_location("long_window_proof_probe", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


probe = _load_probe()


class LongWindowProofProbeTests(unittest.TestCase):
    def test_evaluate_not_yet_without_days(self) -> None:
        report = probe.evaluate([], window=14)
        self.assertEqual(report["status"], "not-yet")
        self.assertEqual(report["pass_days"], 0)

    def test_evaluate_pass_when_span_and_count_enough(self) -> None:
        days = [date(2026, 5, i) for i in range(1, 15)]
        report = probe.evaluate(days, window=14)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["span_days"], 14)

    def test_collect_ignores_non_pass(self) -> None:
        root = Path("/tmp/aiwiki-long-window-probe-test")
        if root.exists():
            for path in sorted(root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                else:
                    path.rmdir()
        gate = root / "output" / "control" / "maturity-gate"
        gate.mkdir(parents=True)
        (gate / "run-20260501T000000Z.json").write_text(
            json.dumps({"status": "warn", "generated_at": "2026-05-01T00:00:00Z"}),
            encoding="utf-8",
        )
        (gate / "run-20260502T000000Z.json").write_text(
            json.dumps({"status": "pass", "generated_at": "2026-05-02T00:00:00Z"}),
            encoding="utf-8",
        )
        try:
            days = probe.collect_receipt_days(root)
            self.assertEqual(days, [date(2026, 5, 2)])
        finally:
            for path in sorted(root.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                else:
                    path.rmdir()


if __name__ == "__main__":
    unittest.main()
