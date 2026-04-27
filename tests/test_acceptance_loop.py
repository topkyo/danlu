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


class _FixedDateTime(datetime):  # pragma: no cover - exercised by explicit pytest acceptance gate
    @classmethod
    def now(cls, tz: timezone | None = None) -> datetime:
        return FIXED_NOW if tz is not None else FIXED_NOW.replace(tzinfo=None)


def _run_cli(root: Path, args: list[str]) -> bytes:  # pragma: no cover - exercised by explicit pytest acceptance gate
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
        code = main(["--root", str(root), *args])
    assert code == 0, stderr.getvalue()
    return stdout.getvalue().encode("utf-8")


def _load_jsonl(path: Path) -> list[dict[str, object]]:  # pragma: no cover - exercised by explicit pytest acceptance gate
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_golden(path: Path) -> bytes:  # pragma: no cover - exercised by explicit pytest acceptance gate
    return path.read_bytes()


def _write_or_compare(path: Path, actual: bytes) -> None:  # pragma: no cover - exercised by explicit pytest acceptance gate
    if REFRESH:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(actual)
        return
    assert actual == _load_golden(path)


def _assert_files_byte_equal(root: Path, expected_dir: Path, relpaths: list[str]) -> None:  # pragma: no cover - explicit gate
    for rel in relpaths:
        golden = expected_dir / "files" / f"{rel.replace('/', '__')}.golden"
        _write_or_compare(golden, (root / rel).read_bytes())


def _copy_case_and_fix_clock(  # pragma: no cover - exercised by explicit pytest acceptance gate
    case_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    case = FIXTURE_ROOT / case_name
    vault = tmp_path / "vault"
    shutil.copytree(case / "root", vault)
    monkeypatch.setattr("aiwiki.clock.utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr("aiwiki.runner.alchemy.utc_now", lambda: FIXED_NOW.isoformat())
    monkeypatch.setattr("aiwiki.app_utils.utc_now", lambda: FIXED_NOW.isoformat())
    monkeypatch.setattr("aiwiki.app_linting.datetime", _FixedDateTime)
    uuids = itertools.count(1)
    monkeypatch.setattr("aiwiki.signals.collector.uuid.uuid4", lambda: uuid.UUID(int=next(uuids)))
    return case, vault


def _run_b1_chain(vault: Path) -> tuple[bytes, bytes, bytes]:  # pragma: no cover - explicit pytest acceptance gate
    return (
        _run_cli(vault, ["signals-replay", "--source", "runtime_history", "--source", "llm_receipt", "--trace-id", TRACE_ID]),
        _run_cli(vault, ["planner-log-replay", "--execute"]),
        _run_cli(vault, ["alchemy", "auto", "--dry-run", "--scope", "all"]),
    )


def _assert_lane_receipt_fields(receipts: list[dict[str, object]], primitives: list[str]) -> None:
    assert [record["primitive"] for record in receipts] == primitives
    for record in receipts:
        assert record["kind"] == "execution-receipt"
        assert record["generated_by"] == "aiwiki-alchemy-lane"
        assert record["operation"] == "alchemy-lane-primitive"
        assert record["audit_stream"] == "execution_receipts"
        assert record["audit_event"] == "execution_receipt_history_append"


def test_m61_b1_execute_mode_auto_dry_run_acceptance(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, vault = _copy_case_and_fix_clock("case_auto_dry_run", tmp_path, monkeypatch)

    stdout_dir = case / "expected" / "stdout"
    out1, out2, out3 = _run_b1_chain(vault)

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


def test_light_primitives_compile_lint_acceptance(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, vault = _copy_case_and_fix_clock("case_light_primitives_compile_lint", tmp_path, monkeypatch)
    stdout_dir = case / "expected" / "stdout"
    out1, out2, out3 = _run_b1_chain(vault)
    out4 = _run_cli(
        vault,
        [
            "alchemy",
            "light",
            "all",
            "--apply",
            "--primitive",
            "compile",
            "--primitive",
            "lint",
            "--note",
            "M6.1 light compile+lint",
        ],
    )

    _write_or_compare(stdout_dir / "01-signals-replay.json", out1)
    _write_or_compare(stdout_dir / "02-planner-log-replay.json", out2)
    _write_or_compare(stdout_dir / "03-alchemy-auto-dry-run.json", out3)
    if not REFRESH:
        assert json.loads(out4)["primitives"] == ["compile", "lint"]
        assert json.loads(out4)["lane"] == "light"

    receipts = _load_jsonl(vault / ".aiwiki/state/execution-receipts.jsonl")
    _assert_lane_receipt_fields(receipts, ["compile", "lint"])

    audit = _load_jsonl(vault / ".aiwiki/state/audit.jsonl")
    assert [record["event_type"] for record in audit] == [
        "alchemy-lane-started",
        "alchemy-lane-primitive",
        "alchemy-lane-primitive",
        "alchemy-lane-completed",
    ]
    assert [record["subject"]["id"] for record in audit] == ["light:all", "light:all:compile", "light:all:lint", "light:all"]
    llm_receipts = _load_jsonl(vault / ".aiwiki/logs/llm-receipts.jsonl")
    assert len(llm_receipts) == 1 and llm_receipts[0]["status"] == "failed"

    _assert_files_byte_equal(
        vault,
        case / "expected",
        [
            ".aiwiki/state/signals.jsonl",
            ".aiwiki/state/planner-log.jsonl",
            ".aiwiki/state/execution-receipts.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
    )
    if REFRESH:
        pytest.fail("Goldens refreshed; rerun without AIWIKI_ACCEPTANCE_REFRESH to verify.")


def test_light_primitives_nightly_acceptance(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, vault = _copy_case_and_fix_clock("case_light_primitives_nightly", tmp_path, monkeypatch)
    stdout_dir = case / "expected" / "stdout"
    out1, out2, out3 = _run_b1_chain(vault)
    out4 = _run_cli(
        vault,
        ["alchemy", "light", "all", "--apply", "--primitive", "nightly", "--note", "M6.1 light nightly"],
    )

    _write_or_compare(stdout_dir / "01-signals-replay.json", out1)
    _write_or_compare(stdout_dir / "02-planner-log-replay.json", out2)
    _write_or_compare(stdout_dir / "03-alchemy-auto-dry-run.json", out3)
    if not REFRESH:
        payload = json.loads(out4)
        assert payload["primitives"] == ["nightly"]
        assert payload["lane"] == "light"

    receipts = _load_jsonl(vault / ".aiwiki/state/execution-receipts.jsonl")
    _assert_lane_receipt_fields(receipts, ["nightly"])
    audit = _load_jsonl(vault / ".aiwiki/state/audit.jsonl")
    assert [record["event_type"] for record in audit] == [
        "alchemy-lane-started",
        "nightly",
        "alchemy-lane-primitive",
        "alchemy-lane-completed",
    ]
    assert [record["subject"]["id"] for record in audit] == ["light:all", "", "light:all:nightly", "light:all"]
    assert len(_load_jsonl(vault / ".aiwiki/logs/llm-receipts.jsonl")) == 1

    b2a_receipts = _load_jsonl(FIXTURE_ROOT / "case_light_primitives_compile_lint/expected/files/.aiwiki__state__execution-receipts.jsonl.golden")
    b2a_audit = _load_jsonl(FIXTURE_ROOT / "case_light_primitives_compile_lint/expected/files/.aiwiki__state__audit.jsonl.golden")
    assert set(b2a_receipts[0]) == set(receipts[0])
    stable = {"kind", "generated_by", "operation", "audit_stream", "audit_event", "lane", "scope", "status", "version"}
    assert {key: b2a_receipts[0][key] for key in stable} == {key: receipts[0][key] for key in stable}
    assert {record["event_type"] for record in b2a_audit} == {"alchemy-lane-started", "alchemy-lane-primitive", "alchemy-lane-completed"}
    assert {record["event_type"] for record in audit if record["event_type"] != "nightly"} == {
        "alchemy-lane-started",
        "alchemy-lane-primitive",
        "alchemy-lane-completed",
    }

    _assert_files_byte_equal(
        vault,
        case / "expected",
        [
            ".aiwiki/state/signals.jsonl",
            ".aiwiki/state/planner-log.jsonl",
            ".aiwiki/state/execution-receipts.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
    )
    if REFRESH:
        pytest.fail("Goldens refreshed; rerun without AIWIKI_ACCEPTANCE_REFRESH to verify.")
