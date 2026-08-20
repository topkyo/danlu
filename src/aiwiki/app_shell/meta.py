from __future__ import annotations

from pathlib import Path

from ..protocol.state import load_protocol_state
from ..protocol.types import ProtocolState
from ..render.paths import (
    product_shell_html_path,
    shell_summary_path,
)
from ..state.constants import DEFAULT_PROTOCOL
from ..utils.io import (
    runtime_write_operation,
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from ..utils.path import relative_path
from .types import ShellSummary


def shell_links(root: Path) -> dict[str, str]:
    """Paths the Shell actually reads (persisted thin summary + openOutputsHub)."""
    return {
        "summary_path": relative_path(root, shell_summary_path(root)),
        "furnace_center_markdown": "wiki/indexes/furnace-center.md",
    }


def shell_curated_page_roots(root: Path) -> dict[str, str]:
    """Return repo-relative prefixes for curated-page categories.

    Exposed in ShellSummary as the single source of truth for which path
    prefixes count as "curated pages" (decisions / judgments). The plugin
    reads this instead of hardcoding `wiki/decisions/` / `wiki/judgments/`
    so that CLI remains authoritative and the plugin stays a thin client.

    Values are repo-relative directory prefixes ending in "/". They are
    NOT vault-absolute paths: the plugin resolves the active file's
    repo-relative path and checks `startswith(prefix)`.
    """
    _ = root  # kept in signature for symmetry with other shell_* helpers
    return {
        "decisions": "wiki/decisions/",
        "judgments": "wiki/judgments/",
    }


def shell_protocol_state(root: Path) -> ProtocolState:
    state = load_protocol_state(root)
    return {
        "active_protocol": str(state.get("active_protocol") or DEFAULT_PROTOCOL),
        "available_protocols": [DEFAULT_PROTOCOL],
        "protocols": list(state.get("protocols", [])) if isinstance(state.get("protocols"), list) else [],
        "state_path": str(state.get("state_path") or ""),
    }


@runtime_write_operation
def write_shell_summary(root: Path, summary: ShellSummary | None = None) -> ShellSummary:
    from .rendering import render_product_shell_html
    from .summary import build_shell_summary, thin_shell_summary_for_persist

    summary = summary or build_shell_summary(root)
    persisted = thin_shell_summary_for_persist(summary)
    write_json_document_if_changed_ignoring_generated_timestamps(shell_summary_path(root), persisted)
    write_if_changed_ignoring_timestamps(product_shell_html_path(root), render_product_shell_html(persisted))
    return persisted
