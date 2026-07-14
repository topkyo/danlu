"""Lint and nightly health helpers extracted from app_compile.

Subpackage façade — re-exports all symbols for backward compatibility.
"""
from __future__ import annotations

import sys
import types

from . import core as _core
from .core import (
    _LINT_REPORT_KEEP,
    Finding,
    _LintContext,
    _rotate_lint_reports,
    _start_lint_context,
    _write_lint_report,
    datetime,
    lint_wiki,
    pending_source_summary_ids,
)
from .nightly import (
    refresh_nightly_planner_execution_state,
    write_nightly_health,
)
from .phases import (
    _lint_curated_phase,
    _lint_governance_phase,
    _lint_layout_phase,
    _lint_runtime_phase,
)
from .repair import render_repair_backlog


class _CompatModule(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if name == "datetime":
            _core.datetime = value


sys.modules[__name__].__class__ = _CompatModule

__all__ = [
    "_LINT_REPORT_KEEP",
    "Finding",
    "pending_source_summary_ids",
    "lint_wiki",
    "_LintContext",
    "_start_lint_context",
    "_rotate_lint_reports",
    "_write_lint_report",
    "datetime",
    "_lint_layout_phase",
    "_lint_runtime_phase",
    "_lint_governance_phase",
    "_lint_curated_phase",
    "render_repair_backlog",
    "write_nightly_health",
    "refresh_nightly_planner_execution_state",
]
