"""Obsidian plugin release sync helpers."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..utils.io import write_if_changed
from .templates import PLUGIN_ID


def _plugin_template_paths(runtime_root: Path) -> dict[str, Path]:
    plugin_root = runtime_root / ".obsidian" / "plugins" / PLUGIN_ID
    return {
        "manifest": plugin_root / "manifest.json",
        "main": plugin_root / "main.js",
        "styles": plugin_root / "styles.css",
    }

def _validate_runtime_root(runtime_root: Path) -> None:
    required = [
        runtime_root / "src" / "aiwiki" / "cli" / "__init__.py",
        runtime_root / "src" / "aiwiki" / "cli" / "__main__.py",
        runtime_root / ".obsidian" / "plugins" / PLUGIN_ID / "main.js",
        runtime_root / ".obsidian" / "plugins" / PLUGIN_ID / "manifest.json",
        runtime_root / ".obsidian" / "plugins" / PLUGIN_ID / "styles.css",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        joined = ", ".join(missing)
        raise FileNotFoundError(f"runtime root is missing required vault template assets: {joined}")

def _plugin_release_targets(target_root: Path) -> dict[str, Path]:
    return {
        "manifest": target_root / ".obsidian" / "plugins" / PLUGIN_ID / "manifest.json",
        "main": target_root / ".obsidian" / "plugins" / PLUGIN_ID / "main.js",
        "styles": target_root / ".obsidian" / "plugins" / PLUGIN_ID / "styles.css",
    }

def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def sync_product_shell_plugin(runtime_root: Path, target_root: Path) -> dict[str, Any]:
    """Sync the generated Obsidian plugin release files into an existing vault.

    Only release files are managed here. The local plugin ``data.json`` is
    deliberately preserved because it may contain user-specific API keys.
    """

    runtime_root = runtime_root.resolve()
    target_root = target_root.resolve()
    _validate_runtime_root(runtime_root)
    if not target_root.exists() or not target_root.is_dir():
        raise FileNotFoundError(f"target vault does not exist or is not a directory: {target_root}")

    source_paths = _plugin_template_paths(runtime_root)
    target_paths = _plugin_release_targets(target_root)
    changed_files: list[str] = []
    source_hashes: dict[str, str] = {}

    for label, source in source_paths.items():
        relative = {
            "manifest": f".obsidian/plugins/{PLUGIN_ID}/manifest.json",
            "main": f".obsidian/plugins/{PLUGIN_ID}/main.js",
            "styles": f".obsidian/plugins/{PLUGIN_ID}/styles.css",
        }[label]
        content = source.read_text(encoding="utf-8")
        source_hashes[relative] = _sha256_text(content)
        if write_if_changed(target_paths[label], content):
            changed_files.append(relative)

    return {
        "status": "ok",
        "vault_root": str(target_root),
        "runtime_root": str(runtime_root),
        "plugin_id": PLUGIN_ID,
        "changed_files": sorted(changed_files),
        "preserved_files": [f".obsidian/plugins/{PLUGIN_ID}/data.json"],
        "source_hashes": source_hashes,
    }
