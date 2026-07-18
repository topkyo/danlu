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

TRACE_ID = "550e8400-e29b-41d4-a716-446655440000"

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
    # Git checkout mtimes are "now"; pin vault files so sync_manifest/compile
    # provenance fields stay deterministic across hosts and facade cleanups.
    fixed_epoch = FIXED_NOW.timestamp()
    for path in vault.rglob("*"):
        if path.is_file():
            os.utime(path, (fixed_epoch, fixed_epoch))
    monkeypatch.setattr("aiwiki.clock.utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr("aiwiki.runner.alchemy.utc_now", lambda: FIXED_NOW.isoformat())
    monkeypatch.setattr("aiwiki.execution.alchemy.utc_now", lambda: FIXED_NOW.isoformat())
    monkeypatch.setattr("aiwiki.utils.time.utc_now", lambda: FIXED_NOW.isoformat())
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
    monkeypatch.setattr("aiwiki.execution.receipts.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.execution.alchemy.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.execution.audit_preview.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.memory.action_core.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.app_linting.datetime", _FixedDateTime)
    monkeypatch.setattr("aiwiki.utils.text.datetime", _FixedDateTime)
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
    across `aiwiki.drop`, `aiwiki.render.paths`, and `aiwiki.utils.time`.
    `_timestamped_stem` is slugify-only (no real timestamp), so `note_path`
    is stem-stable from `title`.
    """
    from aiwiki.drop import drop_url

    payload = dict(_DEFAULT_DROP_URL_FETCHED if fetched is None else fetched)
    monkeypatch.setattr("aiwiki.drop._fetch_url", lambda u, root=None: payload)
    return drop_url(vault, url, title=title)


def _json_stdout(payload: object) -> bytes:  # pragma: no cover - exercised by explicit pytest acceptance gate
    return (json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _observe_signal_counts(result: dict) -> dict:  # pragma: no cover - exercised by explicit pytest acceptance gate
    return {
        "status": str(result.get("status") or ""),
        "path": str(result.get("signals_path") or ".aiwiki/state/signals.jsonl"),
        "scanned_count": int(result.get("scanned_count") or 0),
        "new_count": int(result.get("new_count") or 0),
        "duplicate_count": int(result.get("duplicate_count") or 0),
        "unmapped_count": int(result.get("unmapped_count") or 0),
        "invalid_count": int(result.get("invalid_count") or 0),
        "emitted_by_kind": dict(result.get("emitted_by_kind") or {}),
    }


def _observe_planner_counts(result: dict) -> dict:  # pragma: no cover - exercised by explicit pytest acceptance gate
    return {
        "status": str(result.get("status") or ""),
        "path": str(result.get("log_path") or ".aiwiki/state/planner-log.jsonl"),
        "scanned_count": int(result.get("scanned_count") or 0),
        "new_count": int(result.get("new_count") or 0),
        "duplicate_count": int(result.get("duplicate_count") or 0),
        "invalid_count": int(result.get("invalid_count") or 0),
        "emitted_by_decision": dict(result.get("emitted_by_decision") or {}),
    }


def _build_alchemy_auto_preview(  # pragma: no cover - exercised by explicit pytest acceptance gate
    vault: Path,
    *,
    scope: str = "all",
    lanes: tuple[str, ...] = ("heavy", "light"),
) -> dict:
    from aiwiki.planner import preview_alchemy_lane
    from aiwiki.runner.alchemy_support import auto_primitives_for_lane, auto_skip_reason

    lane_results: list[dict] = []
    skipped: list[dict[str, str]] = []
    ready_count = 0
    for lane in lanes:
        plan = preview_alchemy_lane(
            vault,
            lane=lane,
            scope=scope,
            decision_mode="execute",
            allow_current_writer_lock=True,
        )
        selected_primitives = auto_primitives_for_lane(lane, plan, requested_primitives=[])
        reason = auto_skip_reason(plan, selected_primitives)
        status = "skipped" if reason else "ready"
        if reason:
            skipped.append({"lane": lane, "reason": reason})
        else:
            ready_count += 1
        lane_results.append(
            {
                "lane": lane,
                "status": status,
                "reason": reason,
                "plan_status": str(plan.get("status") or ""),
                "selected_count": int(plan.get("selected_count") or 0),
                "selected_primitives": selected_primitives,
                "budget_exceeded": bool(plan.get("budget", {}).get("exceeded"))
                if isinstance(plan.get("budget"), dict)
                else False,
            }
        )
    return {
        "status": "preview",
        "mode": "dry_run",
        "dry_run": True,
        "side_effects_allowed": False,
        "scope": scope,
        "decision_mode": "execute",
        "lanes": list(lanes),
        "ready_count": ready_count,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "lane_results": lane_results,
    }


def _run_observe_setup(
    vault: Path,
) -> tuple[bytes, bytes, bytes]:  # pragma: no cover - exercised by explicit pytest acceptance gate
    """Function-level setup replacing deleted signals/planner/alchemy-auto CLI."""

    from aiwiki.planner import write_planner_log
    from aiwiki.signals import collect_signals
    from aiwiki.utils.time import utc_now

    signals_result = collect_signals(
        vault,
        sources=["runtime_history", "llm_receipt"],
        trace_id=TRACE_ID,
    )
    planner_execute = write_planner_log(vault, mode="execute")

    preview_signals = collect_signals(
        vault,
        sources=["runtime_history", "llm_receipt"],
        trace_id=TRACE_ID,
    )
    planner_observe = write_planner_log(vault, mode="observe_only")
    planner_execute_preview = write_planner_log(vault, mode="execute")
    preview_result = {
        "status": "ok",
        "generated_at": utc_now(),
        "mode": "observe_and_dry_run",
        "dry_run": True,
        "side_effects_allowed": False,
        "scope": "all",
        "signals": _observe_signal_counts(preview_signals),
        "planner": {
            "observe": _observe_planner_counts(planner_observe),
            "execute": _observe_planner_counts(planner_execute_preview),
        },
        "auto_preview": _build_alchemy_auto_preview(vault),
    }
    return (
        _json_stdout(signals_result),
        _json_stdout(planner_execute),
        _json_stdout(preview_result),
    )


def _run_lane_apply(  # pragma: no cover - exercised by explicit pytest acceptance gate
    vault: Path,
    *,
    lane: str,
    primitives: list[str],
    note: str,
) -> bytes:
    """Apply alchemy lane primitives without the deleted ``alchemy <lane>`` CLI."""

    from aiwiki.runner.alchemy import run_alchemy_lane_apply

    result = run_alchemy_lane_apply(
        vault,
        lane=lane,
        scope="all",
        primitives=primitives,
        note=note,
        allow_current_writer_lock=True,
    )
    return _json_stdout(result)


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
    `aiwiki.utils.time` (used inside l3_proposals.py via `from aiwiki.utils.time
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
