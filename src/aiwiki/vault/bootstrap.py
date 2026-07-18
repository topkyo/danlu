"""Vault initialization helpers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..execution.runtime_surfaces import shell_status
from ..protocol.scaffold import ensure_layout
from ..utils.io import render_json_document, write_if_changed
from ..vault_obsidian_graph import DEFAULT_OBSIDIAN_GRAPH
from .plugin import _validate_runtime_root, sync_product_shell_plugin
from .templates import (
    DEFAULT_OBSIDIAN_APP,
    DEFAULT_OBSIDIAN_APPEARANCE,
    DEFAULT_OBSIDIAN_CORE_PLUGINS,
    DEFAULT_PLUGIN_DATA,
    FOLDER_LABEL_SNIPPET_NAME,
    PLUGIN_ID,
    _default_workspace_document,
    _render_folder_label_snippet,
    _render_indexes_readme,
    _render_launcher_script,
    _render_vault_home,
    _render_vault_readme,
)


def _ensure_target_is_safe(target_root: Path, *, force: bool) -> None:
    if not target_root.exists():
        return
    if not target_root.is_dir():
        raise FileExistsError(f"target path exists and is not a directory: {target_root}")
    has_entries = any(target_root.iterdir())
    if has_entries and not force:
        raise FileExistsError(f"target vault already exists and is not empty: {target_root}")

def _write_json(path: Path, payload: dict[str, Any] | list[Any]) -> bool:
    if isinstance(payload, dict):
        return write_if_changed(path, render_json_document(payload))
    text = render_json_document({"items": payload})
    return write_if_changed(path, text.replace('{\n  "items": ', "").rstrip("}\n") + "\n")

def bootstrap_new_vault(runtime_root: Path, target_root: Path, *, force: bool = False) -> dict[str, Any]:
    runtime_root = runtime_root.resolve()
    target_root = target_root.resolve()
    _validate_runtime_root(runtime_root)
    _ensure_target_is_safe(target_root, force=force)

    ensure_layout(target_root)
    written_files: list[str] = []

    managed_text_files = {
        "README.md": _render_vault_readme(runtime_root),
        "HOME.md": _render_vault_home(),
        "wiki/indexes/README.md": _render_indexes_readme(),
        "scripts/aiwiki-launcher.sh": _render_launcher_script(runtime_root),
        f".obsidian/snippets/{FOLDER_LABEL_SNIPPET_NAME}.css": _render_folder_label_snippet(),
    }
    for relative, content in managed_text_files.items():
        path = target_root / relative
        if write_if_changed(path, content):
            written_files.append(relative)

    launcher_path = target_root / "scripts" / "aiwiki-launcher.sh"
    current_mode = launcher_path.stat().st_mode
    os.chmod(launcher_path, current_mode | 0o111)

    json_files: dict[str, dict[str, Any]] = {
        ".obsidian/appearance.json": DEFAULT_OBSIDIAN_APPEARANCE,
        ".obsidian/app.json": DEFAULT_OBSIDIAN_APP,
        ".obsidian/core-plugins.json": DEFAULT_OBSIDIAN_CORE_PLUGINS,
        ".obsidian/graph.json": DEFAULT_OBSIDIAN_GRAPH,
        ".obsidian/workspace.json": _default_workspace_document(),
        f".obsidian/plugins/{PLUGIN_ID}/data.json": DEFAULT_PLUGIN_DATA,
    }
    for relative, payload in json_files.items():
        path = target_root / relative
        if write_if_changed(path, render_json_document(payload)):
            written_files.append(relative)

    community_plugins_path = target_root / ".obsidian" / "community-plugins.json"
    community_plugins_text = '[\n  "furnace-product-shell"\n]\n'
    if write_if_changed(community_plugins_path, community_plugins_text):
        written_files.append(".obsidian/community-plugins.json")

    plugin_sync = sync_product_shell_plugin(runtime_root, target_root)
    written_files.extend(plugin_sync["changed_files"])

    summary = shell_status(target_root)
    return {
        "status": "ok",
        "vault_root": str(target_root),
        "runtime_root": str(runtime_root),
        "launcher_path": "scripts/aiwiki-launcher.sh",
        "plugin_id": PLUGIN_ID,
        "written_files": sorted(written_files),
        "active_protocol": str(summary.get("active_protocol") or "general"),
        "shell_summary_path": "output/control/shell-summary.json",
    }
