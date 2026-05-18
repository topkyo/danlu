"""Machine-memory query and render surfaces facade.

OWNER STATUS: facade. DO NOT ADD LOGIC HERE.
New code must import from `aiwiki.memory.*` (primary owner) directly.
This file exists only to preserve external import paths and test patch seams.

All renderers have been extracted to the ``aiwiki.memory`` package
(EP-017B steps 1-4). This module now acts as a thin facade that
re-exports public/tested symbols from the submodules plus legacy query
helpers from :mod:`aiwiki.app_memory_query`. Private query helpers owned
by :mod:`aiwiki.app_memory_query` stay on that owner module instead of
being re-exported through this facade. External callers and test
``patch('aiwiki.app_memory_surfaces.<name>')`` seams continue to resolve
against the remaining public re-export bindings.
"""

from __future__ import annotations

# EP-011 legacy re-exports: public/tested machine-memory query helpers live
# in ``aiwiki.app_memory_query``. Monkey-patch seams targeting
# ``aiwiki.app_memory_surfaces.<name>`` bind against this facade. Private
# underscore helpers must be imported from their owner module directly.
from .app_memory_query import (  # noqa: F401
    build_machine_memory_adjacency,
    build_machine_memory_query_routes,
    concept_page_snapshot,
    fallback_query_route_config,
    machine_memory_node_metadata,
    ranked_machine_memory_anchor_nodes,
    recent_execution_dry_runs,
    record_query_route_telemetry,
    render_machine_memory_route,
    select_machine_memory_query_strategy,
    shortest_machine_memory_path,
)

# EP-017B step 4: execution center / audit + concept quality / rewrite
# proposal renderers extracted to ``aiwiki.memory.execution_surfaces``.
from .memory.execution_surfaces import (  # noqa: F401
    build_execution_audit_snapshot,
    collect_execution_consistency_signals,
    concept_rewrite_proposal_digest,
    reconcile_concept_rewrite_proposals,
    render_concept_quality,
    render_concept_rewrite_index,
    render_concept_rewrite_proposal_page,
    render_execution_audit,
    render_execution_audit_html,
    render_execution_center,
    render_execution_center_html,
    render_execution_proposal_page,
)

# EP-017B step 1: graph/query/transition/history surfaces extracted to
# ``aiwiki.memory.graph``.
from .memory.graph import (  # noqa: F401
    _build_machine_memory_query_json,
    _judgment_relation_edge_signatures,
    append_machine_memory_history,
    build_machine_memory_query,
    render_machine_memory_graph_html,
    summarize_machine_memory_transition,
)

# EP-017B step 3: status / health / index / actions / repair-plan renderers
# extracted to ``aiwiki.memory.status``.
from .memory.status import (  # noqa: F401
    render_drift_report,
    render_graph_health,
    render_machine_memory_actions,
    render_machine_memory_index,
    render_machine_memory_repair_plan,
)

# EP-017B step 2: topology slice renderer extracted to
# ``aiwiki.memory.topology``.
from .memory.topology import render_machine_memory_topology  # noqa: F401
