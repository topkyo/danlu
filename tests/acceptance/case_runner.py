from __future__ import annotations

import io
import itertools
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from aiwiki.cli import main

FIXED_NOW = datetime(2026, 4, 27, 0, 0, 0, tzinfo=timezone.utc)

# Frozen acceptance goldens assume `LLMConfig.from_env()` fails with the deterministic
# `_missing_backend_message` from an unset explicit backend (see `expected/files/*.golden`).
# Host shells exporting `AIWIKI_LLM_BACKEND` or NVIDIA credentials change resolution,
# probe behavior, and hint strings — strip those keys only for in-process CLI runs.
_ACCEPTANCE_HOST_LLM_ENV_KEYS: tuple[str, ...] = (
    "AIWIKI_LLM_BACKEND",
    "AIWIKI_LLM_MODEL",
    "AIWIKI_NVIDIA_NIM_API_KEY",
    "NVIDIA_NIM_API_KEY",
)


class _FixedDateTime(datetime):  # pragma: no cover - exercised by explicit pytest acceptance gate
    @classmethod
    def now(cls, tz: timezone | None = None) -> datetime:
        return FIXED_NOW if tz is not None else FIXED_NOW.replace(tzinfo=None)


def _run_cli(root: Path, args: list[str]) -> bytes:  # pragma: no cover - exercised by explicit pytest acceptance gate
    restored: dict[str, str | None] = {}
    for key in _ACCEPTANCE_HOST_LLM_ENV_KEYS:
        restored[key] = os.environ.pop(key, None)
    try:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            code = main(["--root", str(root), *args])
        assert code == 0, stderr.getvalue()
        return stdout.getvalue().encode("utf-8")
    finally:
        for key, prior in restored.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior


def _copy_case_and_fix_clock_from(  # pragma: no cover - exercised by explicit pytest acceptance gate
    group: str, case_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    case = Path(__file__).resolve().parent.parent / "fixtures" / "acceptance" / group / case_name
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
    monkeypatch.setattr("aiwiki.app_execution.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.execution.alchemy.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.execution.audit_preview.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.content.memory.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.app_linting.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.app_queries.datetime", _FixedDateTime)
    uuids = itertools.count(1)
    monkeypatch.setattr("aiwiki.signals.collector.uuid.uuid4", lambda: uuid.UUID(int=next(uuids)))
    return case, vault
