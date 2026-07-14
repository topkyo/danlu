"""Product Shell summary, rendering and control surfaces.

Subpackage façade — re-exports all symbols for backward compatibility,
including indirect mock seams (utc_now, load_llm_receipt_history).
"""
from __future__ import annotations

import sys
import types

from aiwiki.app_state import load_llm_receipt_history
from aiwiki.app_utils import utc_now

from . import helpers as _helpers
from . import meta as _meta
from . import rendering as _rendering
from . import summary as _summary
from .controls import (
    l3_proposal_control_object,
    rewrite_control_object,
    rewrite_control_objects_for_paths,
    rewrite_followup_action,
    rewrite_followup_actions_for_controls,
    rewrite_followup_payload_for_paths,
    shell_action_control_objects,
    shell_archive_control_objects,
    shell_execution_controls,
    shell_review_controls,
)
from .helpers import _build_llm_rerun_command, _first_non_empty, _latest_llm_receipt
from .meta import (
    shell_capabilities,
    shell_curated_page_roots,
    shell_links,
    shell_protocol_state,
    shell_search,
    shell_status_dashboard,
    write_shell_summary,
)
from .rendering import render_product_shell_html
from .summary import _build_knowledge_stats, _build_metrics_summary, build_shell_summary
from .surfaces import (
    shell_dashboard,
    shell_drift_warnings,
    shell_latest_llm_run,
    shell_latest_shell_sync_run,
    shell_llm_health,
    shell_recent_receipts,
    shell_recent_runs,
    shell_search_results,
    shell_suggested_next_actions,
)

_meta.build_shell_summary = build_shell_summary
_meta.render_product_shell_html = render_product_shell_html


class _CompatModule(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if name == "utc_now":
            _summary.utc_now = value
        elif name == "load_llm_receipt_history":
            _helpers.load_llm_receipt_history = value


sys.modules[__name__].__class__ = _CompatModule

__all__ = [
    "utc_now",
    "load_llm_receipt_history",
    "_latest_llm_receipt",
    "_first_non_empty",
    "_build_llm_rerun_command",
    "shell_recent_runs",
    "shell_latest_shell_sync_run",
    "shell_recent_receipts",
    "shell_latest_llm_run",
    "shell_llm_health",
    "shell_search_results",
    "shell_drift_warnings",
    "shell_suggested_next_actions",
    "shell_dashboard",
    "shell_review_controls",
    "l3_proposal_control_object",
    "rewrite_control_object",
    "rewrite_control_objects_for_paths",
    "rewrite_followup_action",
    "rewrite_followup_actions_for_controls",
    "rewrite_followup_payload_for_paths",
    "shell_action_control_objects",
    "shell_archive_control_objects",
    "shell_execution_controls",
    "shell_links",
    "shell_curated_page_roots",
    "shell_capabilities",
    "shell_protocol_state",
    "shell_status_dashboard",
    "shell_search",
    "write_shell_summary",
    "_build_knowledge_stats",
    "_build_metrics_summary",
    "build_shell_summary",
    "render_product_shell_html",
]
