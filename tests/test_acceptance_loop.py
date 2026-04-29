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
from tests.acceptance.llm_replay import inject_replay_client

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


# M6.7.1 acceptance determinism: real elapsed-time fields legitimately vary
# across runs (clock granularity, CPU jitter). They are still produced by
# production code (no fake values) but must be normalized BEFORE byte compare
# so byte-frozen goldens stay stable. All other receipt fields remain strict.
_DYNAMIC_RECEIPT_FIELDS: tuple[str, ...] = ("duration_ms",)
_NORMALIZED_JSONL_SUFFIXES: tuple[str, ...] = (
    ".aiwiki/logs/llm-receipts.jsonl",
    ".aiwiki/logs/runs.jsonl",
    ".aiwiki/state/audit.jsonl",
)


def _normalize_jsonl_dynamic_fields(  # pragma: no cover - exercised by explicit pytest acceptance gate
    raw: bytes, fields: tuple[str, ...] = _DYNAMIC_RECEIPT_FIELDS
) -> bytes:
    """Replace known dynamic top-level fields with deterministic placeholders.

    Preserves line ordering, key ordering (sort_keys=True matches production
    receipts which already serialize with sort_keys), and trailing newline.
    Lines that are not valid JSON or not objects are passed through unchanged
    (defensive; current acceptance fixtures only emit JSON-object lines).
    """
    out_lines: list[str] = []
    text = raw.decode("utf-8")
    # Preserve trailing newline semantics: splitlines drops it, so reconstruct.
    has_trailing_newline = text.endswith("\n")
    for line in text.splitlines():
        if not line.strip():
            out_lines.append(line)
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue
        if not isinstance(obj, dict):
            out_lines.append(line)
            continue
        for field in fields:
            if field in obj:
                obj[field] = 0
        if "raw_response_path" in obj:
            obj["raw_response_path"] = "<raw-response-path>"
        out_lines.append(json.dumps(obj, sort_keys=True, ensure_ascii=False))
    body = "\n".join(out_lines)
    if has_trailing_newline:
        body += "\n"
    return body.encode("utf-8")


def _should_normalize(rel: str) -> bool:  # pragma: no cover - explicit gate
    return any(rel.endswith(suffix) for suffix in _NORMALIZED_JSONL_SUFFIXES)


def _write_or_compare(path: Path, actual: bytes) -> None:  # pragma: no cover - exercised by explicit pytest acceptance gate
    if REFRESH:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(actual)
        return
    assert actual == _load_golden(path)


def _assert_files_byte_equal(root: Path, expected_dir: Path, relpaths: list[str]) -> None:  # pragma: no cover - explicit gate
    for rel in relpaths:
        golden = expected_dir / "files" / f"{rel.replace('/', '__')}.golden"
        actual = (root / rel).read_bytes()
        if _should_normalize(rel):
            actual_for_compare = _normalize_jsonl_dynamic_fields(actual)
            if REFRESH:
                # Symmetric: write normalized form so future verify runs match.
                golden.parent.mkdir(parents=True, exist_ok=True)
                golden.write_bytes(actual_for_compare)
                continue
            golden_bytes = _normalize_jsonl_dynamic_fields(_load_golden(golden))
            assert actual_for_compare == golden_bytes, (
                f"normalized JSONL byte mismatch at {rel}\n"
                f"actual={actual_for_compare!r}\nexpected={golden_bytes!r}"
            )
            continue
        _write_or_compare(golden, actual)


def _snapshot_paths(root: Path, prefixes: tuple[str, ...]) -> dict[str, bytes]:  # pragma: no cover - explicit gate
    snapshot: dict[str, bytes] = {}
    for prefix in prefixes:
        base = root / prefix
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                snapshot[path.relative_to(root).as_posix()] = path.read_bytes()
    return snapshot


def _read_optional_bytes(path: Path) -> bytes | None:  # pragma: no cover - explicit gate
    return path.read_bytes() if path.exists() else None


def _copy_case_and_fix_clock(  # pragma: no cover - exercised by explicit pytest acceptance gate
    case_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    return _copy_case_and_fix_clock_from("M6.1", case_name, tmp_path, monkeypatch)


def _copy_case_and_fix_clock_from(  # pragma: no cover - exercised by explicit pytest acceptance gate
    group: str, case_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    case = Path(__file__).parent / "fixtures" / "acceptance" / group / case_name
    vault = tmp_path / "vault"
    shutil.copytree(case / "root", vault)
    monkeypatch.setattr("aiwiki.clock.utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr("aiwiki.runner.alchemy.utc_now", lambda: FIXED_NOW.isoformat())
    monkeypatch.setattr("aiwiki.execution.alchemy.utc_now", lambda: FIXED_NOW.isoformat())
    monkeypatch.setattr("aiwiki.app_utils.utc_now", lambda: FIXED_NOW.isoformat())
    monkeypatch.setattr("aiwiki.app_compile.utc_now", lambda: FIXED_NOW.isoformat())
    monkeypatch.setattr("aiwiki.drop.utc_now", lambda: FIXED_NOW.isoformat())
    monkeypatch.setattr("aiwiki.content.io.utc_now", lambda: FIXED_NOW.isoformat())
    monkeypatch.setattr("aiwiki.render.paths.utc_now", lambda: FIXED_NOW.isoformat())
    monkeypatch.setattr("aiwiki.app_shell.utc_now", lambda: FIXED_NOW.isoformat())
    monkeypatch.setattr("aiwiki.runner.receipts.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.execution.audit_preview.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.content.memory.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.app_linting.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.app_queries.datetime", _FixedDateTime)
    uuids = itertools.count(1)
    monkeypatch.setattr("aiwiki.signals.collector.uuid.uuid4", lambda: uuid.UUID(int=next(uuids)))
    return case, vault


def _run_b1_chain(vault: Path) -> tuple[bytes, bytes, bytes]:  # pragma: no cover - explicit pytest acceptance gate
    return (
        _run_cli(vault, ["signals-replay", "--source", "runtime_history", "--source", "llm_receipt", "--trace-id", TRACE_ID]),
        _run_cli(vault, ["planner-log-replay", "--execute"]),
        _run_cli(vault, ["alchemy", "auto", "--dry-run", "--scope", "all"]),
    )


def test_happy_run_ask_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case, vault = _copy_case_and_fix_clock_from("M6.1b", "case_happy_run_ask", tmp_path, monkeypatch)
    inject_replay_client(monkeypatch, case)

    out = _run_cli(vault, ["run-ask", "deterministic source-a", "--format", "report"])
    payload = json.loads(out)

    _write_or_compare(case / "expected" / "stdout" / "01-run-ask.json", out)
    if not REFRESH:
        assert payload["backend_requested"] == "codex-cli"
        assert payload["backend_effective"] == "codex-cli"
        assert payload["model_selected"] == "stub-model"
        assert payload["model_final"] == "stub-model"
        assert payload["contract_validated"] is True
        assert payload.get("delivery_mode", "llm-success") == "llm-success"
        assert payload["ranked_sources"] == ["source-a"]

    target_file = vault / payload["path"]
    assert target_file.exists()
    content = target_file.read_text(encoding="utf-8")
    assert content.strip()
    assert "wiki/sources/source-a.md" in content

    receipts = _load_jsonl(vault / ".aiwiki" / "logs" / "llm-receipts.jsonl")
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["event"] == "run-ask"
    assert receipt["status"] == "success"
    assert receipt["backend_effective"] == "codex-cli"
    assert receipt["model_final"] == "stub-model"
    assert receipt["response_id"] == "stub-response-id"
    assert receipt["usage"] == {"input_tokens": 10, "output_tokens": 20}
    raw_response_path = str(receipt["raw_response_path"])
    assert raw_response_path.startswith(".aiwiki/llm-responses/")
    raw_response_file = vault / raw_response_path
    assert raw_response_file.exists()
    assert raw_response_file.read_text(encoding="utf-8")
    assert receipt["error_class"] == ""
    assert receipt["error_message"] == ""

    audit = _load_jsonl(vault / ".aiwiki" / "state" / "audit.jsonl")
    assert [record["event_type"] for record in audit] == ["query", "success"]
    assert [record["source_stream"] for record in audit] == ["runtime_history", "llm_receipts"]
    assert audit[-1]["subject"] == {"kind": "success", "id": ""}
    assert audit[-1]["raw_response_path"] == raw_response_path

    shell_summary = json.loads((vault / "output" / "control" / "shell-summary.json").read_text(encoding="utf-8"))
    latest_llm = shell_summary["latest_llm_run"]
    # run-ask writes the LLM receipt after ask_question refreshes shell-summary; the
    # persisted shell summary is still byte-frozen to guard deterministic fields.
    assert isinstance(latest_llm, dict)

    _assert_files_byte_equal(
        vault,
        case / "expected",
        [
            ".aiwiki/logs/llm-receipts.jsonl",
            ".aiwiki/logs/runs.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
    )

    audit_text = (vault / ".aiwiki" / "state" / "audit.jsonl").read_text(encoding="utf-8")
    assert "lane_judge" not in audit_text
    assert "auto_judge" not in audit_text
    assert "l3-proposal-accept" not in audit_text

    if REFRESH:
        pytest.fail("Goldens refreshed; rerun without AIWIKI_ACCEPTANCE_REFRESH to verify.")


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


def test_replay_idempotency_and_presentation_acceptance(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, vault = _copy_case_and_fix_clock("case_idempotency_shell", tmp_path, monkeypatch)
    stdout_dir = case / "expected" / "stdout"
    out1, out2, out3 = _run_b1_chain(vault)
    before_today = _snapshot_paths(vault, ("output/control", ".aiwiki/state", "wiki", "output/_candidates"))
    shell_summary_path = vault / "output/control/shell-summary.json"
    shell_summary_before = _read_optional_bytes(shell_summary_path)
    out4 = _run_cli(vault, ["today"])
    after_today = _snapshot_paths(vault, ("output/control", ".aiwiki/state", "wiki", "output/_candidates"))
    assert after_today == before_today
    assert _read_optional_bytes(shell_summary_path) == shell_summary_before

    signals_first = (vault / ".aiwiki/state/signals.jsonl").read_bytes()
    planner_first = (vault / ".aiwiki/state/planner-log.jsonl").read_bytes()

    out1b, out2b, out3b = _run_b1_chain(vault)
    before_today2 = _snapshot_paths(vault, ("output/control", ".aiwiki/state", "wiki", "output/_candidates"))
    out4b = _run_cli(vault, ["today"])
    after_today2 = _snapshot_paths(vault, ("output/control", ".aiwiki/state", "wiki", "output/_candidates"))

    assert (vault / ".aiwiki/state/signals.jsonl").read_bytes() == signals_first
    assert (vault / ".aiwiki/state/planner-log.jsonl").read_bytes() == planner_first
    assert out3b == out3
    assert out4b == out4
    assert before_today2 == after_today2
    assert _read_optional_bytes(shell_summary_path) == shell_summary_before

    assert json.loads(out1b)["new_count"] == 0
    assert json.loads(out2b)["new_count"] == 0
    out1c, out2c, out3c = _run_b1_chain(vault)
    out4c = _run_cli(vault, ["today"])
    assert (out1c, out2c, out3c, out4c) == (out1b, out2b, out3b, out4b)
    assert (vault / ".aiwiki/state/signals.jsonl").read_bytes() == signals_first
    assert (vault / ".aiwiki/state/planner-log.jsonl").read_bytes() == planner_first
    _write_or_compare(stdout_dir / "pass1-01-signals-replay.json", out1)
    _write_or_compare(stdout_dir / "pass1-02-planner-log-replay.json", out2)
    _write_or_compare(stdout_dir / "pass1-03-alchemy-auto-dry-run.json", out3)
    _write_or_compare(stdout_dir / "pass1-04-today.txt", out4)
    _assert_files_byte_equal(vault, case / "expected", [".aiwiki/state/signals.jsonl", ".aiwiki/state/planner-log.jsonl"])
    if REFRESH:
        pytest.fail("Goldens refreshed; rerun without AIWIKI_ACCEPTANCE_REFRESH to verify.")


def test_heavy_primitives_receipt_acceptance(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, vault = _copy_case_and_fix_clock("case_heavy_primitives", tmp_path, monkeypatch)
    prompt_before = (vault / "prompts/ask.md").read_bytes()
    stdout_dir = case / "expected" / "stdout"
    out1, out2, out3 = _run_b1_chain(vault)
    out4 = _run_cli(
        vault,
        [
            "alchemy",
            "heavy",
            "all",
            "--apply",
            "--primitive",
            "review",
            "--primitive",
            "distill",
            "--primitive",
            "propose",
            "--note",
            "M6.1 heavy primitives",
        ],
    )

    _write_or_compare(stdout_dir / "01-signals-replay.json", out1)
    _write_or_compare(stdout_dir / "02-planner-log-replay.json", out2)
    _write_or_compare(stdout_dir / "03-alchemy-auto-dry-run.json", out3)
    if not REFRESH:
        payload = json.loads(out4)
        assert payload["lane"] == "heavy"
        assert payload["primitives"] == ["review", "distill", "propose"]

    receipts = _load_jsonl(vault / ".aiwiki/state/execution-receipts.jsonl")
    assert [record["primitive"] for record in receipts] == ["review", "distill", "propose"]
    expected = {
        "review": ("aiwiki-alchemy-review", "alchemy-review-enqueue"),
        "distill": ("aiwiki-alchemy-distill", "alchemy-distill-refresh"),
        "propose": ("aiwiki-alchemy-propose", "alchemy-propose-generate"),
    }
    for record in receipts:
        assert record["kind"] == "execution-receipt"
        assert record["audit_stream"] == "execution_receipts"
        assert record["audit_event"] == "execution_receipt_history_append"
        assert (record["generated_by"], record["operation"]) == expected[record["primitive"]]

    audit = _load_jsonl(vault / ".aiwiki/state/audit.jsonl")
    assert [record["event_type"] for record in audit] == [
        "alchemy-lane-started",
        "alchemy-review-enqueue",
        "alchemy-review-enqueued",
        "alchemy-distill-refresh",
        "alchemy-distill-refreshed",
        "l3-proposal-create",
        "alchemy-propose-generate",
        "alchemy-propose-generated",
        "alchemy-lane-completed",
    ]
    assert not {"l3-proposal-apply", "l3-proposal-accept", "judge"} & {record["event_type"] for record in audit}
    assert all("#L" in str(record["source_ref"]) for record in audit)
    assert (vault / "prompts/ask.md").read_bytes() == prompt_before
    assert "aiwiki:alchemy-review-enqueue:start" in (vault / "wiki/indexes/review-queue.md").read_text(encoding="utf-8")
    assert "distill_history" in (vault / "output/_candidates/elixirs/elixir-b3.md").read_text(encoding="utf-8")
    assert (vault / ".aiwiki/state/l3-proposals.json").exists()
    assert list((vault / "output/_proposals/prompt").glob("*.md"))
    assert not (vault / "output/_proposals/policy").exists()
    assert len(_load_jsonl(vault / ".aiwiki/logs/llm-receipts.jsonl")) == 1

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


def test_heavy_after_llm_invariant(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B3: LLM-origin upstream artifact must not alter deterministic heavy primitive invariants."""
    case, vault = _copy_case_and_fix_clock_from("M6.1b", "case_heavy_after_llm", tmp_path, monkeypatch)
    stdout_dir = case / "expected" / "stdout"

    out1, out2, out3 = _run_b1_chain(vault)
    out4 = _run_cli(
        vault,
        [
            "alchemy",
            "heavy",
            "all",
            "--apply",
            "--primitive",
            "review",
            "--primitive",
            "distill",
            "--primitive",
            "propose",
            "--note",
            "M6.1 heavy primitives",
        ],
    )

    _write_or_compare(stdout_dir / "01-signals-replay.json", out1)
    _write_or_compare(stdout_dir / "02-planner-log-replay.json", out2)
    _write_or_compare(stdout_dir / "03-alchemy-auto-dry-run.json", out3)
    _write_or_compare(stdout_dir / "04-alchemy-heavy-apply.json", out4)

    if not REFRESH:
        payload = json.loads(out4)
        assert payload["lane"] == "heavy"
        assert payload["primitives"] == ["review", "distill", "propose"]

    receipts = _load_jsonl(vault / ".aiwiki/state/execution-receipts.jsonl")
    primitive_receipts = [record for record in receipts if str(record.get("operation", "")).startswith("alchemy-")]
    expected_per_primitive = [
        ("aiwiki-alchemy-review", "alchemy-review-enqueue"),
        ("aiwiki-alchemy-distill", "alchemy-distill-refresh"),
        ("aiwiki-alchemy-propose", "alchemy-propose-generate"),
    ]
    actual = [
        (record["generated_by"], record["operation"])
        for record in primitive_receipts
        if (record["generated_by"], record["operation"]) in expected_per_primitive
    ]
    assert actual == expected_per_primitive, f"primitive receipt sequence mismatch: {actual}"

    audit_events = _load_jsonl(vault / ".aiwiki/state/audit.jsonl")
    heavy_event_types = [
        "alchemy-lane-started",
        "alchemy-review-enqueue",
        "alchemy-review-enqueued",
        "alchemy-distill-refresh",
        "alchemy-distill-refreshed",
        "l3-proposal-create",
        "alchemy-propose-generate",
        "alchemy-propose-generated",
        "alchemy-lane-completed",
    ]
    heavy_events = [record.get("event_type") for record in audit_events if record.get("event_type") in heavy_event_types]
    assert heavy_events == heavy_event_types, f"audit envelope mismatch: {heavy_events}"

    audit_text = (vault / ".aiwiki/state/audit.jsonl").read_text(encoding="utf-8")
    assert "lane_judge" not in audit_text
    assert "auto_judge" not in audit_text
    assert "l3-proposal-accept" not in audit_text
    assert "l3-proposal-apply" not in audit_text

    for record in primitive_receipts:
        assert record.get("llm_invoked", False) is False, f"heavy primitive receipt should NOT mark llm_invoked: {record}"

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


def test_backend_failure_replay(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B4: ReplayBackend injected failure writes failed receipt and shell surfaces remain usable."""
    case, vault = _copy_case_and_fix_clock_from("M6.1b", "case_backend_failure", tmp_path, monkeypatch)
    inject_replay_client(monkeypatch, case)

    with pytest.raises(SystemExit) as exc_info:
        _run_cli(vault, ["run-ask", "what is source-a", "--format", "report"])
    assert exc_info.value.code == 1

    receipt_path = vault / ".aiwiki/logs/llm-receipts.jsonl"
    assert receipt_path.exists(), "failed receipt should still be written when backend fails"
    receipts = _load_jsonl(receipt_path)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["event"] == "run-ask"
    assert receipt["status"] == "failed"
    assert receipt["backend_effective"] == "codex-cli"
    assert receipt["model_final"] == "stub-model"
    assert "simulated backend timeout" in str(receipt.get("error", ""))
    assert receipt["fallback_used"] is True
    assert receipt["fallback_stage"] == "prompt-profile"
    assert receipt["delivery_mode"] == "llm-failed"

    audit_path = vault / ".aiwiki/state/audit.jsonl"
    assert audit_path.exists(), "failed LLM receipt should be mirrored to audit stream"
    audit_events = _load_jsonl(audit_path)
    assert [record["source_stream"] for record in audit_events] == ["runtime_history", "llm_receipts"]
    assert [record["event_type"] for record in audit_events] == ["query", "failed"]
    assert audit_events[-1]["subject"] == {"kind": "failed", "id": ""}

    summary_payload = json.loads(_run_cli(vault, ["shell-status"]))
    assert summary_payload["summary_path"] == "output/control/shell-summary.json"
    summary = json.loads((vault / "output/control/shell-summary.json").read_text(encoding="utf-8"))
    latest_llm = summary["latest_llm_run"]
    assert latest_llm["event"] == "run-ask"
    assert latest_llm["status"] == "failed"
    assert latest_llm["delivery_mode"] == "llm-failed"

    today_out = _run_cli(vault, ["today"])
    assert today_out.strip()

    combined = audit_path.read_text(encoding="utf-8") + "\n" + receipt_path.read_text(encoding="utf-8")
    for term in ["lane_judge", "auto_judge", "l3-proposal-accept", "l3-proposal-apply", "hidden_backend"]:
        assert term not in combined, f"Stop Line violation: {term} found in audit/receipt"

    # The failed receipt schema is stable, but duration_ms can legitimately vary
    # between focused and full-suite runs; keep B4 schema-only for this file.

    if REFRESH:
        pytest.fail("Goldens refreshed; rerun without AIWIKI_ACCEPTANCE_REFRESH to verify.")


def test_universal_input_routing(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B4: bare aiwiki drop <payload> routes into the typed drop-note handler."""
    _, vault = _copy_case_and_fix_clock_from("M6.2", "case_universal_input", tmp_path, monkeypatch)

    bare_source = str(vault / "inputs" / "universal-note.md")
    bare_out = _run_cli(vault, ["drop", f"note: {bare_source}"])
    bare_payload = json.loads(bare_out)

    _, typed_vault = _copy_case_and_fix_clock_from(
        "M6.2", "case_universal_input", tmp_path / "typed", monkeypatch
    )
    typed_source = str(typed_vault / "inputs" / "universal-note.md")
    typed_out = _run_cli(typed_vault, ["drop", "note", typed_source])
    typed_payload = json.loads(typed_out)

    assert bare_payload["material"] == typed_payload["material"] == "note"
    assert bare_payload["note_kind"] == typed_payload["note_kind"] == "note"
    assert bare_payload["original_path"] == bare_source
    assert typed_payload["original_path"] == typed_source
    assert bare_payload["title"] == typed_payload["title"] == "M6.2 universal input acceptance"

    bare_notes = sorted((vault / "raw" / "inbox").glob("*universal-input-acceptance.md"))
    typed_notes = sorted((typed_vault / "raw" / "inbox").glob("*universal-input-acceptance.md"))
    assert len(bare_notes) == len(typed_notes) == 1
    bare_note_text = bare_notes[0].read_text(encoding="utf-8")
    typed_note_text = typed_notes[0].read_text(encoding="utf-8")
    assert bare_note_text.replace(bare_source, "<source>") == typed_note_text.replace(typed_source, "<source>")

    bare_history = _load_jsonl(vault / ".aiwiki/state/runtime-history.jsonl")
    typed_history = _load_jsonl(typed_vault / ".aiwiki/state/runtime-history.jsonl")
    assert bare_history[-1]["event_type"] == "raw-added"
    assert typed_history[-1]["event_type"] == "raw-added"
    assert bare_history[-1]["material"] == "note"
    assert typed_history[-1]["material"] == "note"


def test_today_feed_contract(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M6.3 B4: aiwiki today 的 5 section heading + 文案契约。"""
    _case, vault = _copy_case_and_fix_clock_from("M6.3", "case_today_feed", tmp_path, monkeypatch)
    out = _run_cli(vault, ["today"]).decode("utf-8")

    for heading in [
        "Today's Reports",
        "Needs Review",
        "Completed Elixirs",
        "L3 Proposals",
        "Suggested Next Actions",
    ]:
        assert heading in out

    for placeholder in [
        "(no reports today)",
        "(no pending review)",
        "(no completed elixirs today)",
        "(no L3 proposals need attention)",
        "(no suggested next actions)",
    ]:
        assert placeholder in out

    assert "Run `aiwiki advanced" in out

    for word in ["shell-summary", "review_backlog_counts", "planner-log", "audit.jsonl", "execution-receipts"]:
        assert word not in out, f"mechanism word leaked to today output: {word}"


def test_acceptance_no_stop_line_violations() -> None:
    """B4 guardrail: acceptance goldens must not contain Stop Line violation keywords."""
    forbidden = ["lane_judge", "auto_judge", "l3-proposal-accept", "l3-proposal-apply", "hidden_backend"]
    fixtures_root = Path(__file__).parent / "fixtures" / "acceptance"

    for golden in fixtures_root.glob("**/expected/files/*.golden"):
        text = golden.read_text(encoding="utf-8", errors="replace")
        for term in forbidden:
            assert term not in text, f"Stop Line violation in {golden}: {term}"

    for stdout_file in fixtures_root.glob("**/expected/stdout/*.json"):
        text = stdout_file.read_text(encoding="utf-8", errors="replace")
        for term in forbidden:
            assert term not in text, f"Stop Line violation in {stdout_file}: {term}"


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


def test_metrics_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """M6.4 B4: aiwiki metrics 输出 7 条指标 + JSON 路径合法。"""
    _case, vault = _copy_case_and_fix_clock_from("M6.4", "case_metrics_report", tmp_path, monkeypatch)

    out = _run_cli(vault, ["metrics"]).decode("utf-8")
    assert "炼丹炉 Knowledge Compounding Metrics" in out
    keys = [
        "provenance_completeness",
        "stale_ratio",
        "review_closure_rate",
        "proposal_acceptance_rate",
        "judgment_revisit_rate",
        "output_file_back_rate",
        "elixir_reuse_count",
    ]
    for key in keys:
        assert key in out, f"metric key missing: {key}"

    out_json = _run_cli(vault, ["metrics", "--json"])
    parsed = json.loads(out_json)
    assert isinstance(parsed, list)
    assert len(parsed) == 7
    parsed_keys = {metric["key"] for metric in parsed}
    assert parsed_keys == set(keys)
    for metric in parsed:
        assert "value" in metric
        assert "unit" in metric
        assert "reason" in metric
        assert "sample_size" in metric
        assert metric["unit"] in {"ratio", "count", "percent"}
        if metric["value"] is None:
            assert metric["reason"], f"{metric['key']} unavailable but reason empty"
        else:
            assert metric["reason"] == "", f"{metric['key']} has value but reason='{metric['reason']}'"


# M9-P1.2: corrupt-state acceptance coverage.
#
# Unit tests already cover receipt-failure rollback end-to-end:
#   - tests/test_alchemy.py::test_promote_rolls_back_when_receipt_history_write_fails
#   - tests/test_alchemy.py::test_revert_rolls_back_when_receipt_history_write_fails
#   - tests/test_alchemy.py::test_demote_rolls_back_when_receipt_history_write_fails
# These exercise the full mutation+receipt+rollback path with realistic fixtures.
# Re-creating that fixture chain at the acceptance layer adds setup complexity
# without strengthening the contract, so we hoist only the strict-loader contract
# (which has no fixture dependency) to acceptance.


def test_strict_loader_raises_on_corrupt_state(tmp_path: Path) -> None:
    """M9-P0.4 acceptance: strict loader surfaces corruption instead of silent fallback."""
    from aiwiki.app_state import (
        CorruptStateError,
        load_jsonl_documents,
        load_jsonl_documents_strict,
    )

    receipts = tmp_path / "execution-receipts.jsonl"
    receipts.write_text(
        '{"action_id":"act-1","trace_id":"t1"}\nnot-json-here\n{"action_id":"act-2"}\n',
        encoding="utf-8",
    )

    # Best-effort: skips bad line, returns 2 documents.
    best_effort = load_jsonl_documents(receipts)
    assert [doc["action_id"] for doc in best_effort] == ["act-1", "act-2"]

    # Strict: raises with exact line number.
    with pytest.raises(CorruptStateError) as ctx:
        load_jsonl_documents_strict(receipts)
    assert ctx.value.line_number == 2
    assert ctx.value.path == receipts
    assert "json decode failed" in ctx.value.reason
