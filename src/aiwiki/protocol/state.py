"""Protocol state I/O helpers extracted from app_protocol."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from ..state.constants import DEFAULT_PROTOCOL
from ..state.io import load_json_document_strict
from ..utils.io import atomic_write_text
from ..utils.path import relative_path
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
