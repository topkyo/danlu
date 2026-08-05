"""Compat re-export — prefer ``aiwiki.corpus.ranks``."""

from __future__ import annotations

from aiwiki.corpus.ranks import action_priority_rank, action_status_rank  # noqa: F401

__all__ = ["action_priority_rank", "action_status_rank"]
