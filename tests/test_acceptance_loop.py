from __future__ import annotations

import io
import itertools
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from aiwiki.cli import main

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "acceptance" / "M6.1"
TRACE_ID = "550e8400-e29b-41d4-a716-446655440000"
FIXED_NOW = datetime(2026, 4, 27, 0, 0, 0, tzinfo=timezone.utc)
REFRESH = os.environ.get("AIWIKI_ACCEPTANCE_REFRESH") == "1"


def _run_cli(root: Path, args: list[str]) -> bytes:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
        code = main(["--root", str(root), *args])
    assert code == 0, stderr.getvalue()
    return stdout.getvalue().encode("utf-8")


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_golden(path: Path) -> bytes:
    return path.read_bytes()


def _write_or_compare(path: Path, actual: bytes) -> None:
    if REFRESH:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(actual)
        return
    assert actual == _load_golden(path)


def _assert_files_byte_equal(root: Path, expected_dir: Path, relpaths: list[str]) -> None:
    for rel in relpaths:
        golden = expected_dir / "files" / f"{rel.replace('/', '__')}.golden"
        _write_or_compare(golden, (root / rel).read_bytes())


def test_m61_b1_execute_mode_auto_dry_run_acceptance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case = FIXTURE_ROOT / "case_auto_dry_run"
    vault = tmp_path / "vault"
    shutil.copytree(case / "root", vault)
    monkeypatch.setattr("aiwiki.clock.utc_now", lambda: FIXED_NOW)
    uuids = itertools.count(1)
    monkeypatch.setattr("aiwiki.signals.collector.uuid.uuid4", lambda: uuid.UUID(int=next(uuids)))

    stdout_dir = case / "expected" / "stdout"
    out1 = _run_cli(vault, ["signals-replay", "--source", "runtime_history", "--source", "llm_receipt", "--trace-id", TRACE_ID])
    out2 = _run_cli(vault, ["planner-log-replay", "--execute"])
    out3 = _run_cli(vault, ["alchemy", "auto", "--dry-run", "--scope", "all"])

    _write_or_compare(stdout_dir / "01-signals-replay.json", out1)
    _write_or_compare(stdout_dir / "02-planner-log-replay.json", out2)
    _write_or_compare(stdout_dir / "03-alchemy-auto-dry-run.json", out3)

    signals = _load_jsonl(vault / ".aiwiki/state/signals.jsonl")
    assert signals
    assert {record["trace_id"] for record in signals} == {TRACE_ID}

    planner = _load_jsonl(vault / ".aiwiki/state/planner-log.jsonl")
    assert planner
    assert all(record["mode"] == "execute" for record in planner)
    assert all(isinstance(record["dedupe_key"], str) and record["dedupe_key"] for record in planner)

    auto = json.loads(out3)
    assert auto["dry_run"] is True
    assert auto["side_effects_allowed"] is False
    assert auto["applied_count"] == 0
    assert not (vault / ".aiwiki/state/execution-receipts.jsonl").exists()
    assert not (vault / ".aiwiki/state/audit.jsonl").exists()

    _assert_files_byte_equal(
        vault,
        case / "expected",
        [".aiwiki/state/signals.jsonl", ".aiwiki/state/planner-log.jsonl"],
    )
    if REFRESH:
        pytest.fail("Goldens refreshed; rerun without AIWIKI_ACCEPTANCE_REFRESH to verify.")
