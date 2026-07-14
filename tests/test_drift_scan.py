"""Tests for ``aiwiki.drift_scan`` (P3 / M8.3)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiwiki.app_utils import compiled_source_sha
from aiwiki.drift_scan import (
    DRIFT_AGING_REL_PATH,
    STALE_JUDGMENT_DAYS_DEFAULT,
    drift_scan,
)
from aiwiki.signals.collector import SIGNALS_REL_PATH
from aiwiki.signals.schema import validate


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _judgment_md(
    *,
    judgment_id: str,
    last_reviewed: str = "2026-04-15T01:51:03+00:00",
    citations: list[str] | None = None,
    citation_snapshots: list[str] | None = None,
    protocol: str = "general",
) -> str:
    parts: list[str] = [
        "---",
        f'id: "{judgment_id}"',
        'kind: "judgment"',
        f'protocol: "{protocol}"',
        f'last_reviewed: "{last_reviewed}"',
    ]
    if citations is not None:
        parts.append("citations:")
        for c in citations:
            parts.append(f'  - "{c}"')
    if citation_snapshots is not None:
        parts.append("citation_snapshots:")
        for s in citation_snapshots:
            parts.append(f'  - "{s}"')
    parts.append("---")
    parts.append(f"# {judgment_id}\n\nbody.\n")
    return "\n".join(parts) + "\n"


def _elixir_md(
    *,
    elixir_id: str,
    derived_from: list[str] | None = None,
    citations: list[str] | None = None,
    citation_snapshots: list[str] | None = None,
    protocol: str = "general",
) -> str:
    parts: list[str] = [
        "---",
        f'id: "{elixir_id}"',
        'kind: "elixir"',
        f'protocol: "{protocol}"',
    ]
    if derived_from is not None:
        parts.append("derived_from:")
        for d in derived_from:
            parts.append(f'  - "{d}"')
    if citations is not None:
        parts.append("citations:")
        for c in citations:
            parts.append(f'  - "{c}"')
    if citation_snapshots is not None:
        parts.append("citation_snapshots:")
        for s in citation_snapshots:
            parts.append(f'  - "{s}"')
    parts.append("---")
    parts.append(f"# {elixir_id}\n\nbody.\n")
    return "\n".join(parts) + "\n"


def _source_md(slug: str, body: str = "content") -> str:
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return (
        "---\n"
        f'id: "{slug}"\n'
        'kind: "source"\n'
        f'source_sha256: "{sha}"\n'
        "---\n"
        f"# {slug}\n\n{body}\n"
    )


def _read_signals(root: Path) -> list[dict]:
    p = root / SIGNALS_REL_PATH
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


class DriftScanStaleJudgmentsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_judgments_no_findings(self) -> None:
        result = drift_scan(self.root, now="2026-10-01T00:00:00+00:00")
        self.assertEqual(result["stale_judgments"], [])
        self.assertEqual(result["signals_appended"], 0)
        # state file always written
        self.assertTrue((self.root / DRIFT_AGING_REL_PATH).is_file())

    def test_fresh_judgment_not_flagged(self) -> None:
        _write(
            self.root / "wiki/judgments/judgment-fresh.md",
            _judgment_md(judgment_id="judgment-fresh", last_reviewed="2026-09-01T00:00:00+00:00"),
        )
        result = drift_scan(self.root, now="2026-10-01T00:00:00+00:00")
        self.assertEqual(result["stale_judgments"], [])
        self.assertEqual(result["signals_appended"], 0)

    def test_stale_judgment_emits_signal(self) -> None:
        _write(
            self.root / "wiki/judgments/judgment-stale.md",
            _judgment_md(judgment_id="judgment-stale", last_reviewed="2025-01-01T00:00:00+00:00"),
        )
        result = drift_scan(self.root, now="2026-10-01T00:00:00+00:00")
        self.assertEqual(len(result["stale_judgments"]), 1)
        finding = result["stale_judgments"][0]
        self.assertEqual(finding["judgment_id"], "judgment-stale")
        self.assertEqual(finding["threshold_days"], STALE_JUDGMENT_DAYS_DEFAULT)
        self.assertGreater(finding["days_since_review"], STALE_JUDGMENT_DAYS_DEFAULT)
        signals = _read_signals(self.root)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["kind"], "drift")
        self.assertEqual(signals[0]["severity"], "medium")
        self.assertEqual(signals[0]["scope"]["judgment_refs"], ["judgment-stale"])
        self.assertTrue(validate(signals[0]).ok)

    def test_stale_judgment_idempotent(self) -> None:
        _write(
            self.root / "wiki/judgments/judgment-stale.md",
            _judgment_md(judgment_id="judgment-stale", last_reviewed="2025-01-01T00:00:00+00:00"),
        )
        first = drift_scan(self.root, now="2026-10-01T00:00:00+00:00")
        second = drift_scan(self.root, now="2026-10-02T00:00:00+00:00")
        self.assertEqual(first["signals_appended"], 1)
        self.assertEqual(second["signals_appended"], 0, "dedupe must suppress identical drift")
        self.assertEqual(len(_read_signals(self.root)), 1)

    def test_unknown_protocol_falls_back_to_general(self) -> None:
        _write(
            self.root / "wiki/judgments/judgment-x.md",
            _judgment_md(
                judgment_id="judgment-x",
                last_reviewed="2024-01-01T00:00:00+00:00",
                protocol="totally-unknown",
            ),
        )
        result = drift_scan(self.root, now="2026-10-01T00:00:00+00:00")
        self.assertEqual(result["stale_judgments"][0]["protocol"], "general")


class DriftScanChangedEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.recent = "2026-09-15T00:00:00+00:00"
        self.now = "2026-10-01T00:00:00+00:00"
        # Host env (e.g. AIWIKI_STALE_JUDGMENT_DAYS=1) must not shrink the stale window for these cases.
        self._prev_stale_judgment_days = os.environ.pop("AIWIKI_STALE_JUDGMENT_DAYS", None)

    def tearDown(self) -> None:
        if self._prev_stale_judgment_days is not None:
            os.environ["AIWIKI_STALE_JUDGMENT_DAYS"] = self._prev_stale_judgment_days
        self._tmp.cleanup()

    def _write_source(self, slug: str, body: str = "content") -> tuple[str, str]:
        rel = f"wiki/sources/{slug}.md"
        text = _source_md(slug, body)
        _write(self.root / rel, text)
        return rel, compiled_source_sha(text)

    def test_evidence_unchanged_no_drift(self) -> None:
        rel, digest = self._write_source("source-a")
        _write(
            self.root / "wiki/judgments/judgment-clean.md",
            _judgment_md(
                judgment_id="judgment-clean",
                last_reviewed=self.recent,
                citations=[rel],
                citation_snapshots=[f"{rel}#{digest}"],
            ),
        )
        result = drift_scan(self.root, now=self.now)
        self.assertEqual(result["changed_evidence"], [])
        self.assertEqual(result["signals_appended"], 0)

    def test_evidence_drifted_emits_high_signal(self) -> None:
        rel, digest = self._write_source("source-a", "original")
        _write(
            self.root / "wiki/judgments/judgment-drift.md",
            _judgment_md(
                judgment_id="judgment-drift",
                last_reviewed=self.recent,
                citations=[rel],
                citation_snapshots=[f"{rel}#{digest}"],
            ),
        )
        # mutate the source
        _write(self.root / rel, _source_md("source-a", "MUTATED"))
        result = drift_scan(self.root, now=self.now)
        self.assertEqual(len(result["changed_evidence"]), 1)
        finding = result["changed_evidence"][0]
        self.assertEqual(finding["asset_id"], "judgment-drift")
        self.assertEqual(finding["asset_kind"], "judgment")
        self.assertEqual(finding["drifted_paths"], [rel])
        signals = _read_signals(self.root)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["kind"], "drift")
        self.assertEqual(signals[0]["severity"], "high")
        self.assertIn(rel, signals[0]["evidence_refs"])

    def test_evidence_path_disappeared_flagged_as_stale(self) -> None:
        rel, digest = self._write_source("source-a")
        _write(
            self.root / "wiki/judgments/judgment-missing-evi.md",
            _judgment_md(
                judgment_id="judgment-missing-evi",
                last_reviewed=self.recent,
                citations=[rel],
                citation_snapshots=[f"{rel}#{digest}"],
            ),
        )
        (self.root / rel).unlink()
        result = drift_scan(self.root, now=self.now)
        self.assertEqual(len(result["changed_evidence"]), 1)
        self.assertIn(rel, result["changed_evidence"][0]["stale_paths"])

    def test_no_citation_snapshots_skipped(self) -> None:
        rel, _ = self._write_source("source-a")
        _write(
            self.root / "wiki/judgments/judgment-noanchor.md",
            _judgment_md(
                judgment_id="judgment-noanchor",
                last_reviewed=self.recent,
                citations=[rel],
                citation_snapshots=[],
            ),
        )
        result = drift_scan(self.root, now=self.now)
        self.assertEqual(result["changed_evidence"], [])


class DriftScanDependencyBreakTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.now = "2026-10-01T00:00:00+00:00"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_elixir_with_existing_dependency_no_break(self) -> None:
        _write(
            self.root / "wiki/judgments/judgment-base.md",
            _judgment_md(judgment_id="judgment-base", last_reviewed="2026-09-01T00:00:00+00:00"),
        )
        _write(
            self.root / "wiki/elixirs/elixir-ok.md",
            _elixir_md(elixir_id="elixir-ok", derived_from=["wiki/judgments/judgment-base.md"]),
        )
        result = drift_scan(self.root, now=self.now)
        self.assertEqual(result["dependency_breaks"], [])

    def test_elixir_with_missing_judgment_emits_break(self) -> None:
        _write(
            self.root / "wiki/elixirs/elixir-broken.md",
            _elixir_md(
                elixir_id="elixir-broken",
                derived_from=["wiki/judgments/judgment-gone.md"],
            ),
        )
        result = drift_scan(self.root, now=self.now)
        self.assertEqual(len(result["dependency_breaks"]), 1)
        finding = result["dependency_breaks"][0]
        self.assertEqual(finding["elixir_id"], "elixir-broken")
        self.assertEqual(finding["missing_dependencies"], ["wiki/judgments/judgment-gone.md"])
        signals = _read_signals(self.root)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["kind"], "elixir_dependency_break")
        self.assertEqual(signals[0]["severity"], "high")
        self.assertEqual(signals[0]["scope"]["elixir_refs"], ["elixir-broken"])

    def test_dependency_break_idempotent(self) -> None:
        _write(
            self.root / "wiki/elixirs/elixir-broken.md",
            _elixir_md(
                elixir_id="elixir-broken",
                derived_from=["wiki/judgments/judgment-gone.md"],
            ),
        )
        first = drift_scan(self.root, now=self.now)
        second = drift_scan(self.root, now="2026-10-02T00:00:00+00:00")
        self.assertEqual(first["signals_appended"], 1)
        self.assertEqual(second["signals_appended"], 0)


class DriftScanIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_aging_state_file_written_with_warnings(self) -> None:
        _write(
            self.root / "wiki/judgments/judgment-stale.md",
            _judgment_md(judgment_id="judgment-stale", last_reviewed="2024-01-01T00:00:00+00:00"),
        )
        drift_scan(self.root, now="2026-10-01T00:00:00+00:00")
        state_path = self.root / DRIFT_AGING_REL_PATH
        self.assertTrue(state_path.is_file())
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["version"], 1)
        self.assertEqual(state["stale_threshold_days"], STALE_JUDGMENT_DAYS_DEFAULT)
        self.assertEqual(len(state["warnings"]), 1)
        self.assertEqual(state["warnings"][0]["kind"], "judgment-stale")

    def test_runtime_history_anchor_appended(self) -> None:
        _write(
            self.root / "wiki/judgments/judgment-stale.md",
            _judgment_md(judgment_id="judgment-stale", last_reviewed="2024-01-01T00:00:00+00:00"),
        )
        drift_scan(self.root, now="2026-10-01T00:00:00+00:00")
        history_path = self.root / ".aiwiki/state/runtime-history.jsonl"
        self.assertTrue(history_path.is_file())
        rows = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(any(r.get("event_type") == "drift-scan" for r in rows))
        # signal source_event_ref must point at the runtime-history line we just wrote
        signals = _read_signals(self.root)
        self.assertEqual(len(signals), 1)
        ref = signals[0]["source_event_ref"]
        self.assertIn(".aiwiki/state/runtime-history.jsonl#L", ref)

    def test_shell_drift_warnings_merges_aging_state(self) -> None:
        from aiwiki.app_shell.surfaces import shell_drift_warnings

        _write(
            self.root / "wiki/judgments/judgment-stale.md",
            _judgment_md(judgment_id="judgment-stale", last_reviewed="2024-01-01T00:00:00+00:00"),
        )
        drift_scan(self.root, now="2026-10-01T00:00:00+00:00")
        aging = json.loads((self.root / DRIFT_AGING_REL_PATH).read_text(encoding="utf-8"))
        warnings = shell_drift_warnings(
            memory={},
            judgment_assets={},
            compile_state={"drift_warnings": [{"kind": "compile-side", "path": "x", "message": "x"}]},
            aging_state=aging,
        )
        kinds = {w["kind"] for w in warnings}
        self.assertIn("compile-side", kinds)
        self.assertIn("judgment-stale", kinds)

    def test_shell_drift_warnings_dedup_and_cap(self) -> None:
        from aiwiki.app_shell.surfaces import shell_drift_warnings

        # 12 distinct warnings → cap at 8
        compile_warnings = [
            {"kind": "compile-side", "path": f"p{i}", "message": f"m{i}"} for i in range(12)
        ]
        warnings = shell_drift_warnings(
            memory={},
            judgment_assets={},
            compile_state={"drift_warnings": compile_warnings},
            aging_state={"warnings": [compile_warnings[0]]},  # duplicate
        )
        self.assertEqual(len(warnings), 8)


class DriftScanEnvOverrideTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_threshold_env_override(self) -> None:
        import os

        _write(
            self.root / "wiki/judgments/judgment-recent.md",
            _judgment_md(
                judgment_id="judgment-recent",
                last_reviewed="2026-09-15T00:00:00+00:00",
            ),
        )
        os.environ["AIWIKI_STALE_JUDGMENT_DAYS"] = "10"
        try:
            result = drift_scan(self.root, now="2026-10-01T00:00:00+00:00")
        finally:
            os.environ.pop("AIWIKI_STALE_JUDGMENT_DAYS", None)
        self.assertEqual(len(result["stale_judgments"]), 1)
        self.assertEqual(result["stale_judgments"][0]["threshold_days"], 10)


if __name__ == "__main__":
    unittest.main()
