"""Backward-compatibility re-export facade for machine-memory graph surfaces.

EP-017B step 2: the monolith has been split into four cohesive modules:
- ``memory.graph_render`` — relation label/style tables + graph HTML renderer
- ``memory.graph_anchors`` — report anchor index + per-report subgraph
- ``memory.graph_query`` — machine-memory query / traversal
- ``memory.graph_transition`` — transition diff + history append

This module re-exports the previously public names so existing
``from aiwiki.memory.graph import X`` call sites continue to work. New code
should import directly from the owner modules. The stale
``build_machine_memory_query_routes`` re-export (originally forwarded to
``app_memory_query``) was removed in this step; its real owner is
``app_memory_query``.
"""

from __future__ import annotations

from .graph_anchors import (  # noqa: F401
    ReportSubgraphError,
    build_report_subgraph,
    collect_report_anchors,
    render_report_subgraph_markdown,
    report_memory_anchor_ids,
)
from .graph_query import build_machine_memory_query  # noqa: F401
from .graph_render import (  # noqa: F401
    RELATION_LABELS,
    relation_label,
    relation_style,
    render_machine_memory_graph_html,
)
from .graph_transition import (  # noqa: F401
    append_machine_memory_history,
    summarize_machine_memory_transition,
)
