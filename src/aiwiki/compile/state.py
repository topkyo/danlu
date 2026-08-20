"""Compile state helpers extracted from the legacy app_state hub."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..state.io import load_json_document, save_json_document
from ..state.paths import compile_state_path
from .types import COMPILE_STATE_DICT_LIST_KEYS, COMPILE_STATE_SCALAR_DEFAULTS, COMPILE_STATE_STR_LIST_KEYS


def default_compile_state() -> dict[str, Any]:
    return {
        **COMPILE_STATE_SCALAR_DEFAULTS,
        **{key: [] for key in COMPILE_STATE_STR_LIST_KEYS},
        **{key: [] for key in COMPILE_STATE_DICT_LIST_KEYS},
    }


def load_compile_state(root: Path) -> dict[str, Any]:
    """Strict-ish loader: any malformed list key resets the whole document.

    Key set is table-driven from ``compile.types`` registries so adding a
    dirty/clean pair cannot silently desync defaults from validation.
    """
    document = load_json_document(compile_state_path(root))
    if not isinstance(document, dict):
        return default_compile_state()
    str_lists: dict[str, list[Any]] = {}
    for key in COMPILE_STATE_STR_LIST_KEYS:
        value = document.get(key, [])
        if not isinstance(value, list):
            return default_compile_state()
        str_lists[key] = value
    dict_lists: dict[str, list[Any]] = {}
    for key in COMPILE_STATE_DICT_LIST_KEYS:
        value = document.get(key, [])
        if not isinstance(value, list):
            return default_compile_state()
        dict_lists[key] = value
    return {
        "version": int(document.get("version", 1) or 1),
        "compiled_at": str(document.get("compiled_at") or ""),
        "manifest_entry_count": int(document.get("manifest_entry_count", 0) or 0),
        **{key: [str(item) for item in items if str(item)] for key, items in str_lists.items()},
        "machine_memory_core_reused": bool(document.get("machine_memory_core_reused", False)),
        **{key: [item for item in items if isinstance(item, dict)] for key, items in dict_lists.items()},
    }


def save_compile_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(compile_state_path(root), document)
