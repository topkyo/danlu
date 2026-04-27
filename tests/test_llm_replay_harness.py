from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from aiwiki.llm import CompletionResult, LLMError
from tests.acceptance.llm_replay import (
    RecordingBackend,
    ReplayBackend,
    compute_prompt_hash,
    inject_recording_client,
    inject_replay_client,
)


def _write_response(
    case_dir: Path,
    *,
    sequence: int,
    system_prompt: str,
    user_prompt: str,
    response_text: str = "recorded text",
    response_id: str = "recorded-id",
    usage: dict[str, object] | None = None,
    prompt_hash: str | None = None,
    failure: str | None = None,
) -> Path:
    actual_hash = prompt_hash or compute_prompt_hash(system_prompt, user_prompt)
    response_dir = case_dir / "backend_responses"
    response_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "sequence": sequence,
        "prompt_hash": actual_hash,
        "backend": "codex-cli",
        "model": "gpt-5-codex",
        "response_text": response_text,
        "response_id": response_id,
        "usage": usage or {},
    }
    if failure is not None:
        payload["failure"] = failure
    path = response_dir / f"{sequence:04d}-{actual_hash}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@dataclass
class StubClient:
    result: CompletionResult

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt
        del user_prompt
        return self.result


class _MonkeyPatch:
    def __init__(self) -> None:
        self._patches = []

    def setattr(self, target: str, value) -> None:
        patcher = patch(target, value)
        patcher.start()
        self._patches.append(patcher)

    def stop(self) -> None:
        for patcher in reversed(self._patches):
            patcher.stop()
        self._patches.clear()


class LLMReplayHarnessTests(unittest.TestCase):
    def test_compute_prompt_hash_deterministic(self) -> None:
        first = compute_prompt_hash("system", "user")
        second = compute_prompt_hash("system", "user")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)
        self.assertLessEqual(set(first), set("0123456789abcdef"))

    def test_compute_prompt_hash_distinguishes_inputs(self) -> None:
        baseline = compute_prompt_hash("system", "user")

        self.assertNotEqual(compute_prompt_hash("other system", "user"), baseline)
        self.assertNotEqual(compute_prompt_hash("system", "other user"), baseline)

    def test_replay_backend_returns_recorded_response(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            case_dir = Path(tempdir)
            _write_response(
                case_dir,
                sequence=1,
                system_prompt="system",
                user_prompt="user",
                response_text="hello",
                response_id="resp-1",
                usage={"total_tokens": 7},
            )

            result = ReplayBackend(case_dir).complete("system", "user")

        self.assertEqual(result, CompletionResult(text="hello", response_id="resp-1", usage={"total_tokens": 7}))

    def test_replay_backend_validates_prompt_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            case_dir = Path(tempdir)
            _write_response(case_dir, sequence=1, system_prompt="system", user_prompt="user", prompt_hash="0" * 16)

            with self.assertRaisesRegex(RuntimeError, "prompt_hash mismatch"):
                ReplayBackend(case_dir).complete("system", "user")

    def test_replay_backend_exhausts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            case_dir = Path(tempdir)
            _write_response(case_dir, sequence=1, system_prompt="system", user_prompt="user")
            backend = ReplayBackend(case_dir)

            backend.complete("system", "user")
            with self.assertRaisesRegex(RuntimeError, "no more recorded responses"):
                backend.complete("system", "user")

    def test_replay_backend_failure_response(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            case_dir = Path(tempdir)
            _write_response(case_dir, sequence=1, system_prompt="system", user_prompt="user", response_text="", failure="timeout")

            with self.assertRaisesRegex(LLMError, "timeout"):
                ReplayBackend(case_dir).complete("system", "user")

    def test_replay_backend_orders_by_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            case_dir = Path(tempdir)
            _write_response(case_dir, sequence=2, system_prompt="system-2", user_prompt="user-2", response_text="second")
            _write_response(case_dir, sequence=1, system_prompt="system-1", user_prompt="user-1", response_text="first")
            backend = ReplayBackend(case_dir)

            self.assertEqual(backend.complete("system-1", "user-1").text, "first")
            self.assertEqual(backend.complete("system-2", "user-2").text, "second")

    def test_recording_backend_writes_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            case_dir = Path(tempdir)
            result = CompletionResult(text="new text", response_id="new-id", usage={"prompt_tokens": 3})
            backend = RecordingBackend(case_dir, StubClient(result), backend="codex-cli", model="gpt-5-codex")

            backend.complete("system", "user")
            prompt_hash = compute_prompt_hash("system", "user")
            payload = json.loads((case_dir / "backend_responses" / f"0001-{prompt_hash}.json").read_text(encoding="utf-8"))

        self.assertEqual(
            payload,
            {
                "sequence": 1,
                "prompt_hash": prompt_hash,
                "backend": "codex-cli",
                "model": "gpt-5-codex",
                "response_text": "new text",
                "response_id": "new-id",
                "usage": {"prompt_tokens": 3},
            },
        )

    def test_recording_backend_passthrough(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = CompletionResult(text="new text", response_id="new-id", usage={})
            backend = RecordingBackend(Path(tempdir), StubClient(result), backend="codex-cli", model="gpt-5-codex")

            self.assertIs(backend.complete("system", "user"), result)

    def test_inject_replay_client_monkeypatches_create_client(self) -> None:
        monkeypatch = _MonkeyPatch()
        try:
            with tempfile.TemporaryDirectory() as tempdir:
                case_dir = Path(tempdir)
                _write_response(case_dir, sequence=1, system_prompt="system", user_prompt="user", response_text="patched")

                inject_replay_client(monkeypatch, case_dir)
                from aiwiki.runner.clients import create_client

                self.assertEqual(create_client(case_dir).complete("system", "user").text, "patched")
        finally:
            monkeypatch.stop()

    def test_inject_recording_client_requires_env(self) -> None:
        monkeypatch = _MonkeyPatch()
        try:
            with tempfile.TemporaryDirectory() as tempdir:
                with patch.dict(os.environ, {"AIWIKI_LLM_MODEL": "gpt-5-codex"}, clear=True):
                    with self.assertRaisesRegex(RuntimeError, "AIWIKI_LLM_BACKEND"):
                        inject_recording_client(monkeypatch, Path(tempdir))
        finally:
            monkeypatch.stop()


if __name__ == "__main__":
    unittest.main()
