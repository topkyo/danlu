#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

import pytest

from aiwiki.config import LLMConfig
from aiwiki.llm import CompletionResult, LLMError
from tests.acceptance.case_runner import _copy_case_and_fix_clock_from, _run_cli
from tests.acceptance.llm_replay import compute_prompt_hash

FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "acceptance"

COMMANDS: dict[str, list[str]] = {
    "M6.1b/case_happy_run_ask": ["run-ask", "deterministic source-a", "--format", "report"],
    "M6.1b/case_backend_failure": ["run-ask", "what is source-a", "--format", "report"],
}


class CapturingBackend:
    def __init__(self, case_dir: Path, root: Path | None = None) -> None:
        self.case_dir = case_dir
        self.root = root
        self.response_dir = case_dir / "backend_responses"
        self._responses: list[tuple[Path, dict[str, Any]]] = [
            (path, json.loads(path.read_text(encoding="utf-8"))) for path in self.response_dir.glob("*.json")
        ]
        self._responses.sort(key=lambda item: int(item[1]["sequence"]))
        first_response = self._responses[0][1] if self._responses else {}
        backend = str(first_response.get("backend") or "replay")
        model = str(first_response.get("model") or "replay-model")
        self.config = LLMConfig(backend=backend, backend_requested=backend, model=model, model_requested=model)
        self._call_count = 0
        self.diffs: list[tuple[int, str, str, Path, Path]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        call_number = self._call_count + 1
        if self._call_count >= len(self._responses):
            raise RuntimeError(f"CapturingBackend: no more recorded responses (got call #{call_number})")

        old_path, recorded = self._responses[self._call_count]
        self._call_count += 1

        old_hash = str(recorded["prompt_hash"])
        new_hash = compute_prompt_hash(system_prompt, user_prompt)
        sequence = int(recorded["sequence"])

        payload = dict(recorded)
        payload["prompt_hash"] = new_hash
        new_path = self.response_dir / f"{sequence:04d}-{new_hash}.json"

        if old_path != new_path and old_path.exists():
            old_path.unlink()
        new_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.diffs.append((sequence, old_hash, new_hash, old_path, new_path))

        if payload.get("response_text") == "" and "failure" in payload:
            raise LLMError(str(payload["failure"]))

        usage = payload.get("usage", {})
        raw_response_path: str | None = None
        if self.root is not None:
            from aiwiki.llm import _write_raw_response

            raw_response_path = _write_raw_response(self.root, str(payload["response_text"]))
        return CompletionResult(
            text=str(payload["response_text"]),
            response_id=str(payload["response_id"]),
            usage=usage if isinstance(usage, dict) else {},
            raw_response_path=raw_response_path,
        )

    def assert_all_consumed(self) -> None:
        if self._call_count != len(self._responses):
            raise RuntimeError(f"CapturingBackend: consumed {self._call_count} of {len(self._responses)} recorded responses")


def _parse_case(raw: str) -> tuple[str, str]:
    case = raw.strip().strip("/")
    if case not in COMMANDS:
        raise SystemExit("unsupported case, add explicit dispatch")
    parts = Path(case).parts
    if len(parts) != 2:
        raise SystemExit("--case must look like M6.1b/case_name")
    return parts[0], parts[1]


def refresh_case(case_arg: str) -> list[tuple[int, str, str, Path, Path]]:
    group, case_name = _parse_case(case_arg)
    case_rel = f"{group}/{case_name}"
    fixture_case = FIXTURE_ROOT / group / case_name
    if not fixture_case.exists():
        raise SystemExit(f"case does not exist: {fixture_case}")

    with tempfile.TemporaryDirectory(prefix="aiwiki-acceptance-refresh-") as tmp:
        with pytest.MonkeyPatch.context() as monkeypatch:
            case, vault = _copy_case_and_fix_clock_from(group, case_name, Path(tmp), monkeypatch)
            holder: dict[str, CapturingBackend] = {}

            def _fake_create_client(root: str | Path, timeout_seconds: int | None = None) -> CapturingBackend:
                del timeout_seconds
                if "backend" not in holder:
                    holder["backend"] = CapturingBackend(case, Path(root))
                return holder["backend"]

            monkeypatch.setattr("aiwiki.runner.clients.create_client", _fake_create_client)
            monkeypatch.setattr("aiwiki.runner.workflows.create_client", _fake_create_client)

            try:
                _run_cli(vault, COMMANDS[case_rel])
            except SystemExit as exc:
                if case_rel != "M6.1b/case_backend_failure" or exc.code != 1:
                    raise

            backend = holder.get("backend")
            if backend is None:
                raise RuntimeError("CapturingBackend was not called")
            backend.assert_all_consumed()
            return backend.diffs


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh acceptance backend_response prompt_hash fixtures.")
    parser.add_argument("--case", required=True, help="Case path relative to tests/fixtures/acceptance, e.g. M6.1b/case_happy_run_ask")
    args = parser.parse_args()

    diffs = refresh_case(args.case)
    for sequence, old_hash, new_hash, old_path, new_path in diffs:
        print(f"{args.case} #{sequence:04d}: {old_hash} -> {new_hash} ({old_path.name} -> {new_path.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
