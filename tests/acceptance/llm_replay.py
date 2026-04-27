from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from aiwiki.llm import CompletionResult, LLMError
from aiwiki.runner.interfaces import SupportsComplete


def compute_prompt_hash(system_prompt: str, user_prompt: str) -> str:
    return hashlib.sha256((system_prompt + "\n" + user_prompt).encode("utf-8")).hexdigest()[:16]


class ReplayBackend:
    def __init__(self, case_dir: Path) -> None:
        self.case_dir = case_dir
        response_dir = case_dir / "backend_responses"
        self._responses = sorted(
            (json.loads(path.read_text(encoding="utf-8")) for path in response_dir.glob("*.json")),
            key=lambda response: int(response["sequence"]),
        )
        self._call_count = 0

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        call_number = self._call_count + 1
        if self._call_count >= len(self._responses):
            raise RuntimeError(f"ReplayBackend: no more recorded responses (got call #{call_number})")

        recorded = self._responses[self._call_count]
        self._call_count += 1

        expected_hash = compute_prompt_hash(system_prompt, user_prompt)
        recorded_hash = recorded["prompt_hash"]
        if recorded_hash != expected_hash:
            raise RuntimeError(
                f"ReplayBackend: prompt_hash mismatch at call #{call_number}: "
                f"expected={expected_hash}, got={recorded_hash}"
            )

        if recorded.get("response_text") == "" and "failure" in recorded:
            raise LLMError(str(recorded["failure"]))

        usage = recorded.get("usage", {})
        return CompletionResult(
            text=str(recorded["response_text"]),
            response_id=str(recorded["response_id"]),
            usage=usage if isinstance(usage, dict) else {},
        )


class RecordingBackend:
    def __init__(self, case_dir: Path, real_client: SupportsComplete, backend: str, model: str) -> None:
        self.case_dir = case_dir
        self.real_client = real_client
        self.backend = backend
        self.model = model
        self._call_count = 0

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        self._call_count += 1
        result = self.real_client.complete(system_prompt, user_prompt)
        prompt_hash = compute_prompt_hash(system_prompt, user_prompt)

        response_dir = self.case_dir / "backend_responses"
        response_dir.mkdir(parents=True, exist_ok=True)
        response_path = response_dir / f"{self._call_count:04d}-{prompt_hash}.json"
        payload: dict[str, Any] = {
            "sequence": self._call_count,
            "prompt_hash": prompt_hash,
            "backend": self.backend,
            "model": self.model,
            "response_text": result.text,
            "response_id": result.response_id,
            "usage": result.usage,
        }
        response_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result


def inject_replay_client(monkeypatch, case_dir: Path) -> None:
    """让 aiwiki.runner.clients.create_client 在被调用时返回 ReplayBackend(case_dir)."""
    backend = ReplayBackend(case_dir)

    def _fake_create_client(root, timeout_seconds=None):
        del root
        del timeout_seconds
        return backend

    monkeypatch.setattr("aiwiki.runner.clients.create_client", _fake_create_client)


def inject_recording_client(monkeypatch, case_dir: Path) -> None:
    """让 create_client 返回 RecordingBackend 包装真实 backend；要求显式 AIWIKI_LLM_BACKEND + AIWIKI_LLM_MODEL env."""
    import os

    backend = os.environ.get("AIWIKI_LLM_BACKEND", "")
    model = os.environ.get("AIWIKI_LLM_MODEL", "")
    if not backend or not model:
        raise RuntimeError("Recording mode requires AIWIKI_LLM_BACKEND and AIWIKI_LLM_MODEL to be set explicitly")

    from aiwiki.runner.clients import create_client as real_create_client

    def _fake_create_client(root, timeout_seconds=None):
        real = real_create_client(root, timeout_seconds=timeout_seconds)
        return RecordingBackend(case_dir, real, backend=backend, model=model)

    monkeypatch.setattr("aiwiki.runner.clients.create_client", _fake_create_client)
