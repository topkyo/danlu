"""Protocol state I/O helpers extracted from app_protocol."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ..state.constants import DEFAULT_PROTOCOL
from ..state.io import load_json_document_strict
from ..utils.io import atomic_write_text, runtime_write_operation, write_if_changed
from ..utils.path import relative_path
from ..utils.time import utc_now
from .descriptors import protocol_descriptor
from .scaffold import available_protocols, ensure_protocol_scaffold
from .types import ProtocolState


def protocol_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "protocol.json"


def default_protocol_state() -> ProtocolState:
    return {"version": 1, "active_protocol": DEFAULT_PROTOCOL}


def load_protocol_state(root: Path) -> ProtocolState:
    ensure_protocol_scaffold(root)
    path = protocol_state_path(root)
    state = load_json_document_strict(path) if path.exists() else default_protocol_state()
    available = available_protocols(root)
    active = str(state.get("active_protocol") or DEFAULT_PROTOCOL)
    if active != DEFAULT_PROTOCOL:
        active = DEFAULT_PROTOCOL
    normalized = {"version": 1, "active_protocol": active}
    if state != normalized:
        atomic_write_text(path, json.dumps(normalized, indent=2, sort_keys=True) + "\n")
    return cast(
        ProtocolState,
        {
            **normalized,
            "available_protocols": available,
            "protocols": [protocol_descriptor(root, slug) for slug in available],
            "state_path": relative_path(root, path),
        },
    )


def resolve_protocol(root: Path, protocol: str | None = None) -> str:
    state = load_protocol_state(root)
    if protocol is None:
        return str(state.get("active_protocol") or DEFAULT_PROTOCOL)
    candidate = protocol.strip().lower()
    if candidate != DEFAULT_PROTOCOL:
        raise ValueError(f"Unknown protocol: {protocol}. Only '{DEFAULT_PROTOCOL}' is supported.")
    return candidate


@runtime_write_operation
def set_active_protocol(root: Path, protocol: str) -> dict[str, Any]:
    from ..lifecycle.knowledge import load_knowledge_lifecycle_state
    from ..render.paths import append_wiki_log
    from ..render.protocols import render_protocols_dashboard

    candidate = protocol.strip().lower()
    if candidate != DEFAULT_PROTOCOL:
        raise ValueError(f"Unknown protocol: {protocol}. Only '{DEFAULT_PROTOCOL}' is supported.")
    active = resolve_protocol(root, protocol)
    path = protocol_state_path(root)
    atomic_write_text(path, json.dumps({"version": 1, "active_protocol": active}, indent=2, sort_keys=True) + "\n")
    state = load_protocol_state(root)
    write_if_changed(
        root / "wiki" / "indexes" / "protocols.md",
        render_protocols_dashboard(
            root,
            utc_now(),
            knowledge_lifecycle=load_knowledge_lifecycle_state(root),
        ),
    )
    append_wiki_log(
        root,
        "protocol",
        "switch active protocol",
        [
            f"active_protocol: `{active}`",
            f"state_path: `{state['state_path']}`",
        ],
    )
    return state
