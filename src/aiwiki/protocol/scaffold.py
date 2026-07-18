"""Layout and protocol scaffold initialization helpers extracted from app_protocol."""

from __future__ import annotations

import json
from pathlib import Path

from ..state.constants import DEFAULT_PROTOCOL
from ..utils.io import atomic_write_text
from .descriptors import (
    render_protocol_library_index,
    render_protocol_overview,
    render_protocol_section,
)
from .runtime_schema import default_protocol_runtime_schema, protocol_runtime_schema_path
from .templates import (
    DEFAULT_DASHBOARD_FILES,
    DEFAULT_SCHEMA_FILES,
    LAYOUT_DIRS,
    PROTOCOL_SECTION_FILES,
)


def ensure_layout(root: Path) -> None:
    for relative in LAYOUT_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)
    ensure_runtime_schema(root)
    ensure_protocol_scaffold(root)
    ensure_runtime_dashboards(root)
    from ..vault_obsidian_graph import sync_obsidian_native_graph_config

    sync_obsidian_native_graph_config(root)


def ensure_runtime_schema(root: Path) -> None:
    for relative, content in DEFAULT_SCHEMA_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            atomic_write_text(path, content)


def ensure_runtime_dashboards(root: Path, *, overwrite: bool = False) -> None:
    for relative, content in DEFAULT_DASHBOARD_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if overwrite or not path.exists():
            atomic_write_text(path, content)


def ensure_protocol_scaffold(root: Path) -> None:
    base = root / "schema" / "protocols"
    base.mkdir(parents=True, exist_ok=True)
    index_path = base / "index.md"
    if not index_path.exists():
        atomic_write_text(index_path, render_protocol_library_index())
    slug = DEFAULT_PROTOCOL
    runtime_schema = protocol_runtime_schema_path(root, slug)
    runtime_schema.parent.mkdir(parents=True, exist_ok=True)
    if not runtime_schema.exists():
        atomic_write_text(
            runtime_schema,
            json.dumps(default_protocol_runtime_schema(slug), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    overview = base / slug / "index.md"
    overview.parent.mkdir(parents=True, exist_ok=True)
    if not overview.exists():
        atomic_write_text(overview, render_protocol_overview(slug))
    for section in PROTOCOL_SECTION_FILES:
        path = base / slug / f"{section}.md"
        if not path.exists():
            atomic_write_text(path, render_protocol_section(slug, section))
    from .state import default_protocol_state, protocol_state_path

    state = protocol_state_path(root)
    if not state.exists():
        atomic_write_text(state, json.dumps(default_protocol_state(), indent=2, sort_keys=True) + "\n")


def available_protocols(root: Path) -> list[str]:
    ensure_protocol_scaffold(root)
    return [DEFAULT_PROTOCOL]
