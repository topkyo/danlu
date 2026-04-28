from __future__ import annotations

import json
from argparse import _SubParsersAction
from pathlib import Path

import pytest

from aiwiki.app_compile import compile_wiki
from aiwiki.app_content import ingest_source
from aiwiki.app_protocol import ensure_layout
from aiwiki.cli import build_parser
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
    run_compile_parser = subparsers_action.choices["run-compile"]
    limit_action = next(action for action in run_compile_parser._actions if "--limit" in action.option_strings)

    assert "fail-fast" in limit_action.help
