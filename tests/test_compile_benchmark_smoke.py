import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "compile_benchmark.py"


class CompileBenchmarkSmokeTests(unittest.TestCase):
    def test_compile_benchmark_runs_with_small_fixture(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--fixture-count", "5", "--iterations", "1"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("timings_ms", payload)
        self.assertIn("cold", payload["timings_ms"])
        self.assertIn("warm", payload["timings_ms"])
        self.assertIn("median", payload["timings_ms"]["cold"])
        self.assertEqual(payload["fixture_count"], 5)

    def test_compile_benchmark_warm_not_catastrophically_slower_than_cold(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--fixture-count", "5", "--iterations", "1"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        cold_ms = payload["timings_ms"]["cold"]["median"]
        warm_ms = payload["timings_ms"]["warm"]["median"]
        self.assertLess(warm_ms, max(cold_ms * 50, 5000.0))


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(CompileBenchmarkSmokeTests))
    return suite
