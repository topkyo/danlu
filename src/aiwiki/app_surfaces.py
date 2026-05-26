"""Compatibility exports for dashboard and shell-facing render surfaces.

OWNER STATUS: legacy compatibility layer. Surface implementations live in
``aiwiki.render.*`` or ``aiwiki.memory.*`` modules.
"""

from __future__ import annotations

from .memory.execution_surfaces import (
    render_execution_audit,
    render_execution_audit_html,
    render_execution_center,
    render_execution_center_html,
)
from .memory.graph import render_machine_memory_graph_html
from .render.cognitive_history import render_cognitive_history
from .render.compile_status import render_compile_status
from .render.furnace_center import render_furnace_center, render_furnace_center_html
from .render.judgment_assets import render_judgment_assets
from .render.review_center import render_review_center_html

__all__ = [
    "render_cognitive_history",
    "render_compile_status",
    "render_execution_audit",
    "render_execution_audit_html",
    "render_execution_center",
    "render_execution_center_html",
    "render_furnace_center",
    "render_furnace_center_html",
    "render_judgment_assets",
    "render_machine_memory_graph_html",
    "render_review_center_html",
]
