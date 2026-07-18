"""Machine-memory action state I/O.

Extracted from the legacy app_state hub. Owned by the memory layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..app_state_paths import machine_memory_action_state_path
from ..state.collections import normalize_versioned_record_list_state
from ..state.io import CorruptStateError, load_json_document, load_json_document_strict
from ..utils.io import atomic_write_text, runtime_write_operation


def default_machine_memory_action_state() -> dict[str, Any]:
    return {"version": 1, "actions": []}


def load_machine_memory_action_state(root: Path) -> dict[str, Any]:
    document = load_json_document(machine_memory_action_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_machine_memory_action_state,
        list_key="actions",
    )


def load_machine_memory_action_state_strict(root: Path) -> dict[str, Any]:
    """Strict variant for execution paths that write the state back.

    Raises `CorruptStateError` on any structural fault (parse failure,
    non-object top-level, non-list `actions`, non-object action items,
    non-int `version`) instead of silently returning the default empty
    state. Use at every read-then-write call site so a corrupt file does
    not get silently overwritten with an empty actions list (= data loss).

    Missing file is the only soft case: returns the default state, since
    the first writer is allowed to materialise it.
    """
    path = machine_memory_action_state_path(root)
    if not path.exists():
        return default_machine_memory_action_state()
    document = load_json_document_strict(path)
    if not isinstance(document, dict):
        raise CorruptStateError(
            path=path,
            reason=f"expected top-level object, got {type(document).__name__}",
        )
    actions = document.get("actions")
    if not isinstance(actions, list):
        raise CorruptStateError(
            path=path,
            reason=f"expected `actions` list, got {type(actions).__name__}",
        )
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise CorruptStateError(
                path=path,
                reason=f"expected `actions[{index}]` to be an object, got {type(action).__name__}",
            )
    if "version" in document:
        raw_version = document["version"]
        if isinstance(raw_version, bool) or not isinstance(raw_version, int):
            raise CorruptStateError(
                path=path,
                reason=f"expected integer `version`, got {raw_version!r}",
            )
        version = raw_version
    else:
        version = 1
    return {"version": version, "actions": list(actions)}


@runtime_write_operation
def save_machine_memory_action_state(root: Path, document: dict[str, Any]) -> None:
    atomic_write_text(machine_memory_action_state_path(root), json.dumps(document, indent=2, sort_keys=True) + "\n")
