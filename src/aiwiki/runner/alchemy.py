"""Alchemy lifecycle wrappers and (in later batches) scoped primitives, lane orchestration, auto scheduler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiwiki.app_utils import runtime_write_lock, runtime_write_operation


def run_alchemy_legacy_migration_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from aiwiki.execution.alchemy import preview_legacy_elixir_migration

    return preview_legacy_elixir_migration(root, limit=limit)


def run_alchemy_legacy_migration_apply(root: Path, *, limit: int = 50, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy import apply_legacy_elixir_migration

    return apply_legacy_elixir_migration(root, limit=limit, note=note)


def run_alchemy_superseded_cleanup_preview(root: Path, *, limit: int = 50) -> dict[str, Any]:
    from aiwiki.execution.alchemy import preview_superseded_elixir_cleanup

    return preview_superseded_elixir_cleanup(root, limit=limit)


def run_alchemy_superseded_cleanup_apply(root: Path, *, limit: int = 50, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy import apply_superseded_elixir_cleanup

    return apply_superseded_elixir_cleanup(root, limit=limit, note=note)


@runtime_write_operation
def run_alchemy_start(
    root: Path,
    corpus_id: str,
    topic: str,
    *,
    protocol: str | None = None,
    include_elixir_ids: list[str] | None = None,
) -> dict[str, Any]:
    from aiwiki.execution.alchemy import start_elixir

    return start_elixir(root, corpus_id, protocol=protocol, topic=topic, include_elixir_ids=include_elixir_ids)


@runtime_write_operation
def run_alchemy_distill(root: Path, elixir_id: str, question: str, include_elixir_ids: list[str] | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy import distill_elixir

    return distill_elixir(root, elixir_id, question=question, include_elixir_ids=include_elixir_ids)


@runtime_write_operation
def run_alchemy_finalize(root: Path, *, elixir_id: str) -> dict[str, Any]:
    from aiwiki.execution.alchemy import finalize_elixir

    return finalize_elixir(root, elixir_id=elixir_id)


@runtime_write_operation
def run_alchemy_promote(root: Path, *, elixir_id: str, note: str | None = None) -> dict[str, Any]:
    from aiwiki.execution.alchemy import promote_elixir

    return promote_elixir(root, elixir_id=elixir_id, note=note)


def run_alchemy_revert(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    from aiwiki.execution.alchemy import revert_elixir

    with runtime_write_lock(root):
        return revert_elixir(root, elixir_id=elixir_id, note=note)


def run_alchemy_demote(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    from aiwiki.execution.alchemy import demote_elixir

    with runtime_write_lock(root):
        return demote_elixir(root, elixir_id=elixir_id, note=note)
