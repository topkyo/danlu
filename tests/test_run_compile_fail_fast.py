from __future__ import annotations

import json
from argparse import _SubParsersAction
from pathlib import Path

import pytest

from aiwiki.app_compile import compile_wiki
from aiwiki.app_protocol import ensure_layout
from aiwiki.cli import build_parser
from aiwiki.content.io import ingest_source
from aiwiki.llm import CompletionResult, LLMError
from aiwiki.runner import run_compile


def _seed_vault(root: Path) -> None:
    ensure_layout(root)
    for name in ("compile.md", "ask.md", "lint.md"):
        (root / "prompts" / name).write_text(f"{name} fixture\n", encoding="utf-8")
    for name in ("index.md", "citations.md", "conflicts.md", "writeback.md", "taxonomy.md"):
        (root / "schema" / name).write_text(f"# {name}\n\nschema fixture\n", encoding="utf-8")
    for name in ("index.md", "taxonomy.md", "query.md", "review.md", "nightly.md", "decision.md", "judgment.md"):
        path = root / "schema" / "protocols" / "general" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n\nprotocol fixture\n", encoding="utf-8")


def _ingest_pending_sources(root: Path, count: int) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for index in range(count):
        source = root / f"sample-{index}.md"
        source.write_text(
            f"# Transformer Scaling {index}\n\nTransformers benefit from scale. Inference costs rise.\n",
            encoding="utf-8",
        )
        entries.append(ingest_source(root, str(source), title=f"Transformer Scaling {index}"))
    compile_wiki(root)
    return entries


class _QueuedCompileClient:
    config = type("Config", (), {"model": "stub-model", "backend": "stub-backend"})()

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt
        del user_prompt
        return CompletionResult(text=self._responses.pop(0), response_id="resp-ok", usage={})


class _FailingCompileClient:
    config = type("Config", (), {"model": "stub-model", "backend": "stub-backend"})()

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt
        del user_prompt
        raise LLMError("boom")


def test_run_compile_records_attempted_succeeded_when_all_pass(tmp_path: Path) -> None:
    _seed_vault(tmp_path)
    entries = _ingest_pending_sources(tmp_path, 3)
    responses = []
    for entry in entries:
        page = tmp_path / "wiki" / "sources" / f"{entry['id']}.md"
        responses.append(
            page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                f"- Compiled synthesis for {entry['title']} remains grounded in the source.",
            )
        )

    result = run_compile(tmp_path, client=_QueuedCompileClient(responses), limit=3)

    assert result["attempted_pages"] == 3
    assert result["succeeded_pages"] == 3
    assert result["failed_pages"] == 0
    assert result["remaining_pages"] == 0


def test_run_compile_records_failed_remaining_on_first_failure(tmp_path: Path) -> None:
    _seed_vault(tmp_path)
    _ingest_pending_sources(tmp_path, 3)

    with pytest.raises(LLMError, match="boom"):
        run_compile(tmp_path, client=_FailingCompileClient(), limit=3)

    receipts = [
        json.loads(line)
        for line in (tmp_path / ".aiwiki" / "logs" / "llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    summary = receipts[-1]
    assert summary["event"] == "run-compile-summary"
    assert summary["status"] == "failed"
    assert summary["attempted_pages"] == 1
    assert summary["succeeded_pages"] == 0
    assert summary["failed_pages"] == 1
    assert summary["remaining_pages"] == 2


def test_run_compile_help_documents_fail_fast() -> None:
    parser = build_parser()
    subparsers_action = next(action for action in parser._actions if isinstance(action, _SubParsersAction))
    advanced_parser = subparsers_action.choices["advanced"]
    advanced_action = next(
        action for action in advanced_parser._actions if isinstance(action, _SubParsersAction)
    )
    run_compile_parser = advanced_action.choices["run-compile"]
    limit_action = next(action for action in run_compile_parser._actions if "--limit" in action.option_strings)

    assert "fail-fast" in limit_action.help


def _load_failure_receipt_files(root: Path) -> list[dict[str, object]]:
    receipt_dir = root / "output" / "control" / "execution-receipts"
    if not receipt_dir.exists():
        return []
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(receipt_dir.glob("run-compile-*.json"))
    ]


def test_fail_fast_writes_per_job_receipt_for_source_page(tmp_path: Path) -> None:
    """F-INV-NEW-2: source-page fail-fast must drop a per-job JSON receipt
    under output/control/execution-receipts/ so vault operators can grep a
    single failed compile back to disk (not only the JSONL stream)."""
    _seed_vault(tmp_path)
    _ingest_pending_sources(tmp_path, 1)

    with pytest.raises(LLMError, match="boom"):
        run_compile(tmp_path, client=_FailingCompileClient(), limit=1)

    receipts = _load_failure_receipt_files(tmp_path)
    assert len(receipts) == 1, "exactly one per-job receipt expected on single-page fail-fast"
    rcpt = receipts[0]
    assert rcpt["version"] == 1
    assert rcpt["kind"] == "execution-receipt"
    assert rcpt["generated_by"] == "aiwiki-run-compile"
    assert rcpt["operation"] == "compile"
    assert rcpt["status"] == "failed"
    assert rcpt["subject_kind"] == "source_page"
    assert rcpt["subject_id"], "subject_id must be the manifest entry id"
    assert rcpt["target_file"].startswith("wiki/sources/")
    assert rcpt["source"].startswith("raw/inbox/")
    assert rcpt["error_class"]
    assert rcpt["error_message"] == "boom"
    assert rcpt["revert_supported"] is False
    assert rcpt["receipt_path"].startswith("output/control/execution-receipts/run-compile-")
    assert rcpt["action_id"].startswith("run-compile-")
    assert isinstance(rcpt["llm_audit"], dict)

    jsonl_lines = (tmp_path / ".aiwiki" / "logs" / "llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()
    failed_records = [json.loads(line) for line in jsonl_lines if line.strip() and "\"status\": \"failed\"" in line]
    assert any(r.get("receipt_path", "").startswith("output/control/execution-receipts/run-compile-") for r in failed_records), (
        "JSONL fail record must cross-reference the per-job receipt path"
    )


def test_fail_fast_does_not_write_receipt_on_success(tmp_path: Path) -> None:
    """Success path must not pollute output/control/execution-receipts/ with
    run-compile-*.json — keep the addition strictly limited to fail-fast so
    acceptance fixtures and vault footprint stay stable."""
    _seed_vault(tmp_path)
    entries = _ingest_pending_sources(tmp_path, 2)
    responses = []
    for entry in entries:
        page = tmp_path / "wiki" / "sources" / f"{entry['id']}.md"
        responses.append(
            page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                f"- Compiled synthesis for {entry['title']} remains grounded in the source.",
            )
        )

    result = run_compile(tmp_path, client=_QueuedCompileClient(responses), limit=2)

    assert result["succeeded_pages"] == 2
    assert _load_failure_receipt_files(tmp_path) == []


class _ReceiptDirAsFileClient:
    """Client that fails after we sabotage the receipts dir so write_receipt
    fails too — used to prove the helper never masks the original LLMError."""

    config = type("Config", (), {"model": "stub-model", "backend": "stub-backend"})()

    def __init__(self, root: Path) -> None:
        self._root = root

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt
        del user_prompt
        # Sabotage: place a regular file where the receipts directory should be.
        sabotage = self._root / "output" / "control" / "execution-receipts"
        sabotage.parent.mkdir(parents=True, exist_ok=True)
        if not sabotage.exists():
            sabotage.write_text("blocker", encoding="utf-8")
        raise LLMError("boom-with-bad-receipt-dir")


def test_fail_fast_receipt_write_failure_does_not_mask_original_exception(
    tmp_path: Path,
) -> None:
    """If per-job receipt write itself errors, the original LLMError must
    still be the visible failure (best-effort write, never mask)."""
    _seed_vault(tmp_path)
    _ingest_pending_sources(tmp_path, 1)

    with pytest.raises(LLMError, match="boom-with-bad-receipt-dir"):
        run_compile(tmp_path, client=_ReceiptDirAsFileClient(tmp_path), limit=1)

    # No JSON receipt files exist (directory is sabotaged), and the JSONL
    # record either has empty receipt_path or skipped it — but the run
    # itself raised the LLMError, which is the invariant we care about.
    assert _load_failure_receipt_files(tmp_path) == []


@pytest.mark.parametrize(
    "subject_kind,extra",
    [
        ("source_page", None),
        ("concept_page", {"source_pages": ["src-a", "src-b"]}),
        (
            "concept_rewrite_proposal",
            {
                "source_pages": ["src-a"],
                "concept_page": "wiki/concepts/foo.md",
                "quality_priority": "high",
                "quality_issues": ["short-summary"],
            },
        ),
    ],
)
def test_write_run_compile_failure_receipt_covers_all_fail_fast_branches(
    tmp_path: Path,
    subject_kind: str,
    extra: dict[str, object] | None,
) -> None:
    """F-INV-NEW-2: directly exercise the helper on each subject_kind to
    prove the 3-way symmetry of source / concept / rewrite fail-fast
    branches (full e2e for concept and rewrite stages would require very
    expensive vault scaffolding; the helper is the actual write code path)."""
    from aiwiki.runner.workflows import _write_run_compile_failure_receipt

    ensure_layout(tmp_path)
    exc = LLMError("boom-branch")
    receipt_rel = _write_run_compile_failure_receipt(
        tmp_path,
        subject_kind=subject_kind,
        subject_id="subject-x",
        target_file=f"wiki/{subject_kind}/subject-x.md",
        source="raw/inbox/x.md" if subject_kind == "source_page" else "",
        item_audit={"model_selected": "stub", "fallback_stages": []},
        item_result=None,
        exc=exc,
        started_at_ms=1_700_000_000_000,
        duration_ms=4321,
        used_profile="default",
        item_retry_profile="",
        fallback_stages=["model-chain"],
        fallback_reason="upstream timeout",
        extra=extra,
    )
    assert receipt_rel.startswith("output/control/execution-receipts/run-compile-")
    receipt = json.loads((tmp_path / receipt_rel).read_text(encoding="utf-8"))
    assert receipt["subject_kind"] == subject_kind
    assert receipt["subject_id"] == "subject-x"
    assert receipt["status"] == "failed"
    assert receipt["error_message"] == "boom-branch"
    assert receipt["fallback_stages"] == ["model-chain"]
    assert receipt["fallback_reason"] == "upstream timeout"
    assert receipt["duration_ms"] == 4321
    if extra:
        for key, value in extra.items():
            assert receipt[key] == value


