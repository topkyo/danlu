from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.acceptance.case_runner import (
    TRACE_ID,
    _copy_case_and_fix_clock_from,
    _run_cli,
    _run_drift_scan,
    _run_drop_url,
    _run_l3_proposal_apply_revert,
    _run_lane_apply,
    _run_observe_setup,
)
from tests.acceptance.llm_replay import inject_replay_client

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "acceptance" / "M6.1"
REFRESH = os.environ.get("AIWIKI_ACCEPTANCE_REFRESH") == "1"


def _load_jsonl(path: Path) -> list[dict[str, object]]:  # pragma: no cover - exercised by explicit pytest acceptance gate
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_golden(path: Path) -> bytes:  # pragma: no cover - exercised by explicit pytest acceptance gate
    return path.read_bytes()


# M6.7.1 acceptance determinism: real elapsed-time fields legitimately vary
# across runs (clock granularity, CPU jitter). They are still produced by
# production code (no fake values) but must be normalized BEFORE byte compare
# so byte-frozen goldens stay stable. All other receipt fields remain strict.
_DYNAMIC_RECEIPT_FIELDS: tuple[str, ...] = ("duration_ms", "applied_at", "occurred_at")
_NORMALIZED_JSONL_SUFFIXES: tuple[str, ...] = (
    ".aiwiki/logs/llm-receipts.jsonl",
    ".aiwiki/logs/runs.jsonl",
    ".aiwiki/state/audit.jsonl",
    ".aiwiki/state/execution-receipts.jsonl",
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


def _run_b1_chain(vault: Path) -> tuple[bytes, bytes, bytes]:  # pragma: no cover - explicit pytest acceptance gate
    return _run_observe_setup(vault)


def test_happy_run_ask_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case, vault = _copy_case_and_fix_clock_from("M6.1b", "case_happy_run_ask", tmp_path, monkeypatch)
    inject_replay_client(monkeypatch, case)

    out = _run_cli(vault, ["run-ask", "deterministic source-a", "--format", "report"])
    payload = json.loads(out)

    _write_or_compare(case / "expected" / "stdout" / "01-run-ask.json", out)
    if not REFRESH:
        assert payload["backend_requested"] == "opencode-api"
        assert payload["backend_effective"] == "opencode-api"
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
    assert receipt["backend_effective"] == "opencode-api"
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
    assert [record["event_type"] for record in audit] == ["query", "success", "run-ask"]
    assert [record["source_stream"] for record in audit] == ["runtime_history", "llm_receipts", "execution_receipts"]
    assert audit[-2]["subject"] == {"kind": "success", "id": ""}
    assert audit[-2]["raw_response_path"] == raw_response_path
    assert audit[-1]["subject"] == {"kind": "output-artifact", "id": "ask-output-reports-deterministic-source-a"}

    execution_receipts = _load_jsonl(vault / ".aiwiki" / "state" / "execution-receipts.jsonl")
    assert len(execution_receipts) == 1
    execution_receipt = execution_receipts[0]
    assert execution_receipt["operation"] == "run-ask"
    assert execution_receipt["status"] == "success"
    assert execution_receipt["target_file"] == payload["path"]
    assert execution_receipt["primary_path"] == payload["path"]
    assert (vault / str(execution_receipt["receipt_path"])).exists()

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
            ".aiwiki/state/execution-receipts.jsonl",
        ],
    )

    audit_text = (vault / ".aiwiki" / "state" / "audit.jsonl").read_text(encoding="utf-8")
    assert "lane_judge" not in audit_text
    assert "auto_judge" not in audit_text
    assert "l3-proposal-accept" not in audit_text

    if REFRESH:
        pytest.fail("Goldens refreshed; rerun without AIWIKI_ACCEPTANCE_REFRESH to verify.")


def test_w2_compounding_rank_and_suggest_acceptance(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W2: seeded confirmed judgment + settled elixir rank into ask; used_refs written; compound_suggest stays scarce until multi-turn."""
    case, vault = _copy_case_and_fix_clock_from("W2", "case_compounding_rank_suggest", tmp_path, monkeypatch)
    inject_replay_client(monkeypatch, case)
    stdout_dir = case / "expected" / "stdout"

    _run_cli(vault, ["compile"])
    out1 = _run_cli(
        vault,
        ["run-ask", "compounding rank acceptance", "--format", "report"],
    )
    payload1 = json.loads(out1)
    _write_or_compare(stdout_dir / "01-run-ask.json", out1)

    machine_query = payload1.get("machine_memory_query", {})
    ranked_judgments = list(machine_query.get("ranked_judgment_ids") or [])
    ranked_elixirs = list(machine_query.get("ranked_elixir_ids") or [])
    used_refs = list(payload1.get("used_refs") or [])

    assert "compounding-thesis" in ranked_judgments
    assert "compounding-elixir" in ranked_elixirs
    assert "wiki/judgments/compounding-thesis.md" in used_refs
    assert "wiki/elixirs/compounding-elixir.md" in used_refs

    report_path = vault / str(payload1["path"])
    assert report_path.is_file()
    report_text = report_path.read_text(encoding="utf-8")
    assert "used_refs:" in report_text
    assert "wiki/judgments/compounding-thesis.md" in report_text
    assert "wiki/elixirs/compounding-elixir.md" in report_text

    summary1 = json.loads((vault / "output" / "control" / "shell-summary.json").read_text(encoding="utf-8"))
    compound1 = summary1.get("compound_suggest") or {}
    assert compound1.get("available") is False
    assert int(compound1.get("count") or 0) == 0

    out2 = _run_cli(
        vault,
        ["run-ask", "compounding rank acceptance", "--format", "report", "--no-cache"],
    )
    _write_or_compare(stdout_dir / "02-run-ask-follow-up.json", out2)

    summary2 = json.loads((vault / "output" / "control" / "shell-summary.json").read_text(encoding="utf-8"))
    compound2 = summary2.get("compound_suggest") or {}
    assert compound2.get("available") is True
    suggest_count = int(compound2.get("count") or 0)
    assert 1 <= suggest_count <= int(compound2.get("max_items") or 3)
    for item in compound2.get("items") or []:
        assert str(item.get("action") or "") in {"file-back-judgment", "alchemy-start"}

    _assert_files_byte_equal(
        vault,
        case / "expected",
        [
            ".aiwiki/logs/llm-receipts.jsonl",
            ".aiwiki/logs/runs.jsonl",
            ".aiwiki/state/audit.jsonl",
            ".aiwiki/state/execution-receipts.jsonl",
        ],
    )

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
    execute_records = [record for record in planner if record.get("mode") == "execute"]
    assert execute_records
    assert all(isinstance(record["dedupe_key"], str) and record["dedupe_key"] for record in execute_records)

    auto = json.loads(out3)
    assert auto["dry_run"] is True
    assert auto["side_effects_allowed"] is False
    assert auto.get("status") == "ok"
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
    before_today = _snapshot_paths(vault, ("output/control", ".aiwiki/state", ".aiwiki/staging", "wiki"))
    shell_summary_path = vault / "output/control/shell-summary.json"
    shell_summary_before = _read_optional_bytes(shell_summary_path)
    out4 = _run_cli(vault, ["today"])
    after_today = _snapshot_paths(vault, ("output/control", ".aiwiki/state", ".aiwiki/staging", "wiki"))
    assert after_today == before_today
    assert _read_optional_bytes(shell_summary_path) == shell_summary_before

    signals_first = (vault / ".aiwiki/state/signals.jsonl").read_bytes()
    planner_first = (vault / ".aiwiki/state/planner-log.jsonl").read_bytes()

    out1b, out2b, out3b = _run_b1_chain(vault)
    before_today2 = _snapshot_paths(vault, ("output/control", ".aiwiki/state", ".aiwiki/staging", "wiki"))
    out4b = _run_cli(vault, ["today"])
    after_today2 = _snapshot_paths(vault, ("output/control", ".aiwiki/state", ".aiwiki/staging", "wiki"))

    assert (vault / ".aiwiki/state/signals.jsonl").read_bytes() == signals_first
    assert (vault / ".aiwiki/state/planner-log.jsonl").read_bytes() == planner_first
    assert out4b == out4
    assert before_today2 == after_today2
    assert _read_optional_bytes(shell_summary_path) == shell_summary_before

    assert json.loads(out1b)["new_count"] == 0
    assert json.loads(out2b)["new_count"] == 0
    out1c, out2c, out3c = _run_b1_chain(vault)
    out4c = _run_cli(vault, ["today"])
    assert json.loads(out1c)["new_count"] == 0
    assert json.loads(out2c)["new_count"] == 0
    assert out4c == out4b
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
    out4 = _run_lane_apply(
        vault,
        lane="heavy",
        primitives=["review", "distill", "propose"],
        note="M6.1 heavy primitives",
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
    assert "distill_history" in (vault / ".aiwiki/staging/elixirs/elixir-b3.md").read_text(encoding="utf-8")
    assert (vault / ".aiwiki/state/l3-proposals.json").exists()
    assert list((vault / ".aiwiki/staging/proposals/prompt").glob("*.md"))
    assert not list((vault / ".aiwiki/staging/proposals/policy").glob("*.md"))
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
    out4 = _run_lane_apply(
        vault,
        lane="heavy",
        primitives=["review", "distill", "propose"],
        note="M6.1 heavy primitives",
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
    assert receipt["backend_effective"] == "opencode-api"
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
    """B4: bare aiwiki drop <payload> routes into the typed markdown handler."""
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
    """B4 guardrail: acceptance goldens must not contain Stop Line violation keywords.

    Exception: `D/case_l3_proposal_apply_revert/` deliberately exercises the L3
    governance lane (create → apply → revert), so `l3-proposal-apply` is the
    expected event/receipt name there, not a Stop Line violation. The case is
    explicitly opt-in (not part of any nightly happy path) and remains covered
    by `lane_judge` / `auto_judge` / `l3-proposal-accept` / `hidden_backend`
    bans, which represent actual policy breaches.
    """
    forbidden = ["lane_judge", "auto_judge", "l3-proposal-accept", "l3-proposal-apply", "hidden_backend"]
    fixtures_root = Path(__file__).parent / "fixtures" / "acceptance"
    exempt_l3_apply_case = "D/case_l3_proposal_apply_revert"

    def _check(path: Path) -> None:
        rel = path.relative_to(fixtures_root).as_posix()
        is_l3_apply_case = rel == exempt_l3_apply_case or rel.startswith(exempt_l3_apply_case + "/")
        text = path.read_text(encoding="utf-8", errors="replace")
        for term in forbidden:
            if term == "l3-proposal-apply" and is_l3_apply_case:
                continue
            assert term not in text, f"Stop Line violation in {path}: {term}"

    for golden in fixtures_root.glob("**/expected/files/*.golden"):
        _check(golden)

    for stdout_file in fixtures_root.glob("**/expected/stdout/*.json"):
        _check(stdout_file)


def test_light_primitives_compile_lint_acceptance(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, vault = _copy_case_and_fix_clock("case_light_primitives_compile_lint", tmp_path, monkeypatch)
    stdout_dir = case / "expected" / "stdout"
    out1, out2, out3 = _run_b1_chain(vault)
    out4 = _run_lane_apply(
        vault,
        lane="light",
        primitives=["compile", "lint"],
        note="M6.1 light compile+lint",
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
    out4 = _run_lane_apply(
        vault,
        lane="light",
        primitives=["nightly"],
        note="M6.1 light nightly",
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

    out = _run_cli(vault, ["advanced", "metrics"]).decode("utf-8")
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

    out_json = _run_cli(vault, ["advanced", "metrics", "--json"])
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


def _trace_collect_parent_ids(node: dict[str, object]) -> set[str]:  # pragma: no cover - explicit gate
    """Recursively gather every ``id`` reachable through ``parents`` edges."""
    seen: set[str] = set()
    stack: list[dict[str, object]] = list(node.get("parents", []) or [])  # type: ignore[arg-type]
    while stack:
        cur = stack.pop()
        if not isinstance(cur, dict):
            continue
        node_id = cur.get("id")
        if isinstance(node_id, str):
            seen.add(node_id)
        nested = cur.get("parents") or []
        if isinstance(nested, list):
            stack.extend(nested)
    return seen


def test_elixir_stage3_compounding(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-3 acceptance: end-to-end Stage-3 compounding (promote-old → start/distill/finalize/promote-new → trace).

    Seeded with a hand-crafted minimal corpus (mirrors M6.1 case_heavy_primitives
    pattern) so the chain stays deterministic without exercising the ``ask_question``
    path (which leaks host wall-clock into cache.db, planner-state, machine-memory).

    Verifies invariants from ``docs/Furnace Next Direction Post-P4.md`` Gap P1:
    - new elixir ``derived_from`` contains both the pre-seeded settled elixir
      reference AND a ``wiki/derived/`` anchor;
    - promote receipt's bundle exposes ``counter_evidence`` + dual sha256 anchors;
    - upward trace from the new elixir reaches the pre-seeded old elixir.
    """
    case, vault = _copy_case_and_fix_clock_from("D3", "case_elixir_stage3_compounding", tmp_path, monkeypatch)

    elixir_old = "elixir-d3-old"

    out_start = _run_cli(
        vault,
        [
            "alchemy-start",
            "corpus-d3-new",
            "--topic",
            "D3 compounding",
            "--include-elixir",
            elixir_old,
        ],
    )
    _write_or_compare(case / "expected" / "stdout" / "01-alchemy-start.json", out_start)
    start_payload = json.loads(out_start)
    elixir_new = str(start_payload["elixir_id"])
    if not REFRESH:
        derived_at_start = list(start_payload.get("derived_from") or [])
        assert f"wiki/elixirs/{elixir_old}.md" in derived_at_start, derived_at_start
        assert any(
            isinstance(ref, str) and ref.startswith("wiki/derived/") for ref in derived_at_start
        ), derived_at_start

    out_distill = _run_cli(
        vault,
        [
            "alchemy-distill",
            elixir_new,
            "--question",
            "How does compounding tighten the thesis?",
            "--include-elixir",
            elixir_old,
        ],
    )
    _write_or_compare(case / "expected" / "stdout" / "02-alchemy-distill.json", out_distill)

    out_finalize = _run_cli(vault, ["alchemy-finalize", "--elixir-id", elixir_new])
    _write_or_compare(case / "expected" / "stdout" / "03-alchemy-finalize.json", out_finalize)

    out_promote = _run_cli(vault, ["alchemy-promote", "--elixir-id", elixir_new])
    _write_or_compare(case / "expected" / "stdout" / "04-alchemy-promote.json", out_promote)
    if not REFRESH:
        promote_payload = json.loads(out_promote)
        assert promote_payload.get("elixir_state") == "settled"

    out_trace = _run_cli(
        vault,
        ["trace", elixir_new, "--direction", "up", "--depth", "3", "--json"],
    )
    _write_or_compare(case / "expected" / "stdout" / "05-trace-up.json", out_trace)
    if not REFRESH:
        trace_payload = json.loads(out_trace)
        assert trace_payload.get("id") == elixir_new
        parent_ids = _trace_collect_parent_ids(trace_payload)
        assert elixir_old in parent_ids, f"trace did not reach old elixir: {parent_ids}"

    if not REFRESH:
        from aiwiki.app_utils import parse_frontmatter

        settled_path = vault / "wiki" / "elixirs" / f"{elixir_new}.md"
        assert settled_path.is_file()
        settled_fm = parse_frontmatter(settled_path.read_text(encoding="utf-8"))
        derived_settled = list(settled_fm.get("derived_from") or [])
        assert f"wiki/elixirs/{elixir_old}.md" in derived_settled, derived_settled
        assert any(
            isinstance(ref, str) and ref.startswith("wiki/derived/") for ref in derived_settled
        ), derived_settled

        receipts = _load_jsonl(vault / ".aiwiki" / "state" / "execution-receipts.jsonl")
        promote_receipts = [
            r
            for r in receipts
            if isinstance(r, dict)
            and r.get("subject_kind") == "elixir_promotion"
            and r.get("subject_id") == elixir_new
        ]
        assert promote_receipts, "no elixir_promotion receipt for new elixir"
        bundle = promote_receipts[-1].get("bundle")
        assert isinstance(bundle, dict)
        assert bundle.get("counter_evidence")
        assert bundle.get("primary_path_sha256")
        assert bundle.get("secondary_path_sha256")

    _assert_files_byte_equal(
        vault,
        case / "expected",
        [
            ".aiwiki/state/execution-receipts.jsonl",
            ".aiwiki/state/audit.jsonl",
            ".aiwiki/state/runtime-history.jsonl",
        ],
    )

    if REFRESH:
        pytest.fail("Goldens refreshed; rerun without AIWIKI_ACCEPTANCE_REFRESH=1 to verify byte-stable.")


def test_file_back_judgment_preserves_derived_promoted_to(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: judgment/decision file-back must not overwrite a wiki/derived/ promoted_to anchor."""
    _case, vault = _copy_case_and_fix_clock_from("D3", "case_elixir_stage3_compounding", tmp_path, monkeypatch)

    report_ref = "output/reports/d3-old.md"
    expected_derived = "wiki/derived/derived-d3-old.md"
    report_path = vault / report_ref
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "---\nprotocol: general\n---\n\n# D3 old report\n\nSeed report for file-back regression.\n",
        encoding="utf-8",
    )

    _run_cli(vault, ["file-back", report_ref, "--kind", "judgment", "--title", "D3 old review"])

    candidates_state = json.loads(
        (vault / ".aiwiki" / "state" / "output-candidates.json").read_text(encoding="utf-8")
    )
    matched = [
        candidate
        for candidate in candidates_state.get("candidates", [])
        if candidate.get("artifact_ref") == report_ref
    ]
    assert len(matched) == 1, candidates_state
    promoted_to = str(matched[0].get("promoted_to") or "")
    assert promoted_to.startswith("wiki/derived/"), promoted_to
    assert promoted_to == expected_derived, promoted_to

    judgment_dir = vault / "wiki" / "judgments"
    assert judgment_dir.is_dir(), "file-back should create wiki/judgments/"
    assert any(judgment_dir.glob("*.md")), "file-back should write a judgment page"

    out_start = _run_cli(
        vault,
        [
            "alchemy-start",
            "corpus-d3-old",
            "--topic",
            "D3 file-back anchor check",
        ],
    )
    start_payload = json.loads(out_start)
    assert start_payload.get("elixir_state") == "draft"
    derived_from = list(start_payload.get("derived_from") or [])
    assert expected_derived in derived_from, derived_from

    elixir_id = str(start_payload["elixir_id"])
    _run_cli(
        vault,
        [
            "alchemy-distill",
            elixir_id,
            "--question",
            "Does the derived anchor still hold after file-back?",
        ],
    )
    _run_cli(vault, ["alchemy-finalize", "--elixir-id", elixir_id])
    out_promote = _run_cli(vault, ["alchemy-promote", "--elixir-id", elixir_id])
    promote_payload = json.loads(out_promote)
    assert promote_payload.get("elixir_state") == "settled"


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


def test_drift_scan_three_scanners(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B acceptance: drift_scan emits stale / changed-evidence / dependency-break findings.

    Function-level (non-CLI) deterministic fixture covering all three scanners in
    `aiwiki.drift_scan.drift_scan`. Asserts byte-stable artifacts for
    `drift-aging.json` (overwrite), `signals.jsonl` (append), `runtime-history.jsonl`
    (append), and the mirrored `audit.jsonl` record.

    Fixture seeds (see `tests/fixtures/acceptance/B/case_drift_scan/root/`):
    - `wiki/judgments/jud-stale.md` — `last_reviewed=2025-10-01` (208d before
      FIXED_NOW=2026-04-27, past 180d STALE_JUDGMENT_DAYS_DEFAULT).
    - `wiki/elixirs/elixir-changed.md` — citation_snapshots with a wrong digest
      for `raw/evidence.md` (drifted) + a snapshot pointing at `raw/missing.md`
      that does not exist on disk (stale_paths).
    - `wiki/elixirs/elixir-broken.md` — `derived_from` references a judgment
      path that does not exist on disk (dependency break).
    """
    case, vault = _copy_case_and_fix_clock_from("B", "case_drift_scan", tmp_path, monkeypatch)

    result = _run_drift_scan(vault, monkeypatch, now="2026-04-27T00:00:00Z")

    if not REFRESH:
        assert len(result["stale_judgments"]) >= 1, result
        assert any(f["judgment_id"] == "jud-stale" for f in result["stale_judgments"])
        assert len(result["changed_evidence"]) >= 1, result
        changed = result["changed_evidence"][0]
        assert changed["asset_id"] == "elixir-changed"
        assert "raw/evidence.md" in changed["drifted_paths"]
        assert "raw/missing.md" in changed["stale_paths"]
        assert len(result["dependency_breaks"]) >= 1, result
        assert result["dependency_breaks"][0]["elixir_id"] == "elixir-broken"
        assert result["signals_appended"] >= 3
        assert result["errors"] == []

    _assert_files_byte_equal(
        vault,
        case / "expected",
        [
            ".aiwiki/state/drift-aging.json",
            ".aiwiki/state/signals.jsonl",
            ".aiwiki/state/runtime-history.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
    )

    if REFRESH:
        pytest.fail("Goldens refreshed; rerun without AIWIKI_ACCEPTANCE_REFRESH=1 to verify byte-stable.")


def test_drop_url_writes_raw_note_and_logs(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C: drop_url end-to-end fixture.

    Asserts byte-stable artifacts for url-drop materialization:
    - raw/inbox/<slug>.md (frontmatter + sections)
    - .aiwiki/state/runtime-history.jsonl (raw-added event)
    - .aiwiki/state/audit.jsonl (auto-mirrored from runtime-history)

    External boundary `_fetch_url` is stubbed by `_run_drop_url` via the default
    fetched payload (image_urls=[] keeps asset download path out of scope; safety
    reject / rollback paths are covered by existing unit tests).
    """
    case, vault = _copy_case_and_fix_clock_from("C", "case_drop_url", tmp_path, monkeypatch)
    result = _run_drop_url(vault, monkeypatch, url="https://example.com/agents")

    assert result["material"] == "url"
    assert result["final_url"] == "https://example.com/agents"
    assert result["asset_paths"] == []
    assert result["note_path"].startswith("raw/inbox/")
    assert result["note_path"].endswith(".md")

    _assert_files_byte_equal(
        vault,
        case / "expected",
        [
            result["note_path"],
            ".aiwiki/state/runtime-history.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
    )

    if REFRESH:
        pytest.fail("Goldens refreshed; rerun without AIWIKI_ACCEPTANCE_REFRESH=1 to verify byte-stable.")


def test_l3_proposal_apply_then_revert(  # pragma: no cover - explicit pytest acceptance gate
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D: L3 proposal create → apply → revert three-step chain.

    Function-level (not CLI) to exercise the L3 governance lane explicitly,
    isolated from nightly happy paths. `_run_l3_proposal_apply_revert` calls
    `create_l3_proposal`, `apply_l3_proposal`, then `revert_l3_proposal`
    against `prompts/test-prompt.md`. After revert the target bytes are
    restored to the original seed, and two execution receipts plus matching
    runtime-history / audit entries exist.

    `aiwiki.execution.l3_proposals.utc_now` is patched by
    `_copy_case_and_fix_clock_from` (module-local binding via
    `from aiwiki.app_utils import utc_now`). `_unique_l3_action_id` is
    suffix-stable from `proposal_id`, so receipt paths are deterministic.
    This case is the documented exception to the `l3-proposal-apply`
    stop-line scan in `test_acceptance_no_stop_line_violations`.
    """
    case, vault = _copy_case_and_fix_clock_from(
        "D", "case_l3_proposal_apply_revert", tmp_path, monkeypatch
    )
    apply_result, revert_result = _run_l3_proposal_apply_revert(vault)

    assert apply_result["state"] == "accepted"
    assert apply_result["proposal_id"] == "prop-test-prompt"
    assert apply_result["receipt_path"].endswith("l3-proposal-apply-prop-test-prompt.json")

    assert revert_result["state"] == "reverted"
    assert revert_result["proposal_id"] == "prop-test-prompt"
    assert revert_result["receipt_path"].endswith("l3-proposal-revert-prop-test-prompt.json")

    # Contract hash invariants: revert restores byte-equality (restored_hash ==
    # apply.before_hash) and the applied state was a real change (after_hash !=
    # restored_hash). Asserting on the function return values (not just goldens)
    # makes regressions diagnose-able without diffing 7 files.
    assert revert_result["restored_hash"] == apply_result["before_hash"]
    assert apply_result["after_hash"] != revert_result["restored_hash"]

    # Target restored to original bytes after revert.
    assert (vault / "prompts" / "test-prompt.md").read_text(encoding="utf-8") == "Original prompt body.\n"

    _assert_files_byte_equal(
        vault,
        case / "expected",
        [
            "prompts/test-prompt.md",
            ".aiwiki/state/l3-proposals.json",
            ".aiwiki/state/execution-receipts/l3-proposal-apply-prop-test-prompt.json",
            ".aiwiki/state/execution-receipts/l3-proposal-revert-prop-test-prompt.json",
            ".aiwiki/state/runtime-history.jsonl",
            ".aiwiki/state/audit.jsonl",
        ],
    )

    if REFRESH:
        pytest.fail("Goldens refreshed; rerun without AIWIKI_ACCEPTANCE_REFRESH=1 to verify byte-stable.")
