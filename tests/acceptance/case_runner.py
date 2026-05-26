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
    monkeypatch.setattr("aiwiki.execution.l3_proposals.utc_now", lambda: FIXED_NOW.isoformat())
    # `create_l3_proposal` honors AIWIKI_DISABLE_AUTOMATION via autonomy_policy and
    # short-circuits to status=skipped when set. Acceptance fixtures must not be
    # host-env sensitive — clear it so the kill switch never silently skews goldens.
    monkeypatch.delenv("AIWIKI_DISABLE_AUTOMATION", raising=False)
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


def _run_drift_scan(  # pragma: no cover - exercised by explicit pytest acceptance gate
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    now: str = "2026-04-27T00:00:00Z",
) -> dict:
    """Direct function-level invocation of `drift_scan` for B acceptance fixture.

    Avoids the CLI because `drift_scan` has no CLI entry point and exercising
    it through the `nightly` workflow would drag in unrelated determinism risks
    (today-feed, aging-report rendering, planner-state). Returns the structured
    summary dict; byte-stable artifacts are asserted via `_assert_files_byte_equal`.

    `uuid` is the global stdlib module — patching `aiwiki.drift_scan.uuid.uuid4`
    technically mutates the shared `uuid` module attribute. `monkeypatch` undoes
    the change on test teardown, so the leak window is the rest of THIS test;
    it never bleeds into other tests. Counter starts at 1000 to keep trace_id
    values visually distinct from the collector counter (which starts at 1) for
    debugging, even though `_new_signal_id` only consumes the first 12 hex of
    `uuid.uuid4().hex` — small ints all flatten to `sig-YYYYMMDD-000000000000`.
    `_new_signal_id` derives the day prefix from `aiwiki.drift_scan.clock.utc_now`
    so we pin that to FIXED_NOW for stable suffix-day prefixes.
    Also clear `AIWIKI_STALE_JUDGMENT_DAYS`, which is host-env tunable and would
    otherwise shift `stale_threshold_days` in the goldens.
    """
    from aiwiki.drift_scan import drift_scan

    monkeypatch.delenv("AIWIKI_STALE_JUDGMENT_DAYS", raising=False)
    drift_uuids = itertools.count(1000)
    monkeypatch.setattr(
        "aiwiki.drift_scan.uuid.uuid4",
        lambda: uuid.UUID(int=next(drift_uuids), version=4),
    )
    monkeypatch.setattr("aiwiki.drift_scan.clock.utc_now", lambda: FIXED_NOW)
    return drift_scan(vault, now=now)


_DEFAULT_DROP_URL_FETCHED: dict = {
    "title": "Agent Architecture Survey",
    "final_url": "https://example.com/agents",
    "content_type": "text/html",
    "status": "200",
    "browser_backend": "",
    "extraction_mode": "readability",
    "description": "A survey of agent runtime tradeoffs.",
    "image_urls": [],
    "text": "Agents coordinate tools, planning, and memory.",
}


def _run_drop_url(  # pragma: no cover - exercised by explicit pytest acceptance gate
    vault: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str,
    title: str | None = None,
    fetched: dict | None = None,
) -> dict:
    """Direct function-level invocation of `drop_url` for C acceptance fixture.

    Avoids the CLI to keep the byte-stable surface focused on `drop_url`'s own
    materialization (raw note + wiki/sources/log + runtime-history + audit
    mirror). `_fetch_url` is the only external boundary; everything else is
    local. `utc_now` is already patched by `_copy_case_and_fix_clock_from`
    across `aiwiki.drop`, `aiwiki.render.paths`, and `aiwiki.app_utils`.
    `_timestamped_stem` is slugify-only (no real timestamp), so `note_path`
    is stem-stable from `title`.
    """
    from aiwiki.drop import drop_url

    payload = dict(_DEFAULT_DROP_URL_FETCHED if fetched is None else fetched)
    monkeypatch.setattr("aiwiki.drop._fetch_url", lambda u, root=None: payload)
    return drop_url(vault, url, title=title)


def _run_l3_proposal_apply_revert(  # pragma: no cover - exercised by explicit pytest acceptance gate
    vault: Path,
    *,
    target_file: str = "prompts/test-prompt.md",
    new_content: str = "Revised prompt body.",
    proposal_id: str = "prop-test-prompt",
    kind: str = "prompt_proposal",
) -> tuple[dict, dict]:
    """Direct function-level invocation of L3 proposal create→apply→revert chain.

    Function-level (not CLI) to avoid conflict with existing acceptance stop-line
    assertions that `l3-proposal-apply` does not appear in audit during nightly
    happy paths. This isolated fixture exercises the governance lane explicitly.

    `_unique_l3_action_id` derives action_id from `{prefix}-{proposal_id}` +
    next-available suffix (not time-based), so receipt paths are deterministic.
    `utc_now` is already patched by `_copy_case_and_fix_clock_from` for
    `aiwiki.app_utils` (used inside l3_proposals.py via `from aiwiki.app_utils
    import utc_now`).
    """
    from aiwiki.execution.l3_proposals import (
        accept_l3_proposal,
        apply_l3_proposal,
        create_l3_proposal,
        revert_l3_proposal,
    )

    create_l3_proposal(
        vault,
        kind=kind,
        target_file=target_file,
        content=new_content,
        proposal_id=proposal_id,
        rationale="acceptance fixture",
        pattern="manual_fixture",
    )
    accept_l3_proposal(vault, proposal_id, note="acceptance human accept")
    apply_result = apply_l3_proposal(vault, proposal_id, note="acceptance apply")
    # apply_result["receipt_path"] is relative; revert resolves by stem/path/action_id.
    action_id = apply_result.get("action_id") or apply_result.get("receipt_path", "")
    revert_result = revert_l3_proposal(vault, action_id, note="acceptance revert")
    return apply_result, revert_result
