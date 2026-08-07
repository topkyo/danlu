"""Offline tests for aiwiki.vault.plugin and aiwiki.vault.bootstrap."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from aiwiki.vault.bootstrap import bootstrap_new_vault
from aiwiki.vault.plugin import sync_product_shell_plugin
from aiwiki.vault.templates import FOLDER_LABEL_SNIPPET_NAME, PLUGIN_ID

MAIN_JS = "// fake bundle\nconst PRIORITY = { elixir: 4, action: 5 };\n"
MANIFEST_JSON = '{\n  "id": "furnace-product-shell"\n}\n'
STYLES_CSS = "/* fake styles */\n"
# Trivial stand-in for the real build.sh; the real build is exercised in the
# real repo. The marker proves sync actually ran the build before copying.
BUILD_SH = "#!/usr/bin/env bash\ntouch .build-marker\nexit 0\n"

PLUGIN_REL = f".obsidian/plugins/{PLUGIN_ID}"
RELEASE_RELATIVES = {
    f"{PLUGIN_REL}/manifest.json",
    f"{PLUGIN_REL}/main.js",
    f"{PLUGIN_REL}/styles.css",
}


def _make_fake_runtime_root(base: Path) -> Path:
    runtime_root = base / "runtime"
    (runtime_root / "src" / "aiwiki" / "cli").mkdir(parents=True)
    (runtime_root / "src" / "aiwiki" / "cli" / "__init__.py").write_text("", encoding="utf-8")
    (runtime_root / "src" / "aiwiki" / "cli" / "__main__.py").write_text("", encoding="utf-8")
    plugin_dir = runtime_root / ".obsidian" / "plugins" / PLUGIN_ID
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "main.js").write_text(MAIN_JS, encoding="utf-8")
    (plugin_dir / "manifest.json").write_text(MANIFEST_JSON, encoding="utf-8")
    (plugin_dir / "styles.css").write_text(STYLES_CSS, encoding="utf-8")
    (plugin_dir / "build.sh").write_text(BUILD_SH, encoding="utf-8")
    return runtime_root


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    return _make_fake_runtime_root(tmp_path)


@pytest.fixture()
def target_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


def test_sync_copies_release_files_and_preserves_data_json(runtime_root: Path, target_vault: Path) -> None:
    plugin_dir = target_vault / ".obsidian" / "plugins" / PLUGIN_ID
    plugin_dir.mkdir(parents=True)
    data_json = plugin_dir / "data.json"
    data_json.write_text('{"settings": {"apiKey": "user-secret"}}\n', encoding="utf-8")

    result = sync_product_shell_plugin(runtime_root, target_vault)

    assert result["status"] == "ok"
    assert result["plugin_id"] == PLUGIN_ID
    assert result["vault_root"] == str(target_vault.resolve())
    assert result["runtime_root"] == str(runtime_root.resolve())
    assert result["changed_files"] == sorted(RELEASE_RELATIVES)
    assert result["preserved_files"] == [f"{PLUGIN_REL}/data.json"]
    assert set(result["source_hashes"]) == RELEASE_RELATIVES
    assert result["source_hashes"][f"{PLUGIN_REL}/main.js"] == hashlib.sha256(MAIN_JS.encode("utf-8")).hexdigest()

    assert (plugin_dir / "main.js").read_text(encoding="utf-8") == MAIN_JS
    assert (plugin_dir / "manifest.json").read_text(encoding="utf-8") == MANIFEST_JSON
    assert (plugin_dir / "styles.css").read_text(encoding="utf-8") == STYLES_CSS
    # data.json may hold user-specific API keys and must survive the sync.
    assert data_json.read_text(encoding="utf-8") == '{"settings": {"apiKey": "user-secret"}}\n'
    # The bundle build ran (in the plugin dir) before files were copied.
    assert (runtime_root / ".obsidian" / "plugins" / PLUGIN_ID / ".build-marker").exists()


def test_sync_fails_loud_when_target_vault_missing(runtime_root: Path, tmp_path: Path) -> None:
    missing = tmp_path / "no-such-vault"
    with pytest.raises(FileNotFoundError, match="target vault does not exist"):
        sync_product_shell_plugin(runtime_root, missing)


def test_sync_fails_loud_when_runtime_assets_missing(tmp_path: Path, target_vault: Path) -> None:
    empty_root = tmp_path / "empty-runtime"
    empty_root.mkdir()
    with pytest.raises(FileNotFoundError, match="missing required vault template assets"):
        sync_product_shell_plugin(empty_root, target_vault)


def test_sync_fails_loud_when_build_script_missing(tmp_path: Path, target_vault: Path) -> None:
    runtime_root = _make_fake_runtime_root(tmp_path)
    (runtime_root / ".obsidian" / "plugins" / PLUGIN_ID / "build.sh").unlink()
    with pytest.raises(FileNotFoundError, match="build.sh"):
        sync_product_shell_plugin(runtime_root, target_vault)


def test_sync_raises_runtime_error_when_build_fails(
    runtime_root: Path, target_vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["bash", "build.sh"], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match=r"Product Shell bundle build failed.*build\.sh"):
        sync_product_shell_plugin(runtime_root, target_vault)


def test_sync_raises_runtime_error_when_build_cannot_start(
    runtime_root: Path, target_vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("bash not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match=r"Product Shell bundle build failed.*build\.sh"):
        sync_product_shell_plugin(runtime_root, target_vault)


def test_second_sync_with_unchanged_sources_changes_nothing(runtime_root: Path, target_vault: Path) -> None:
    first = sync_product_shell_plugin(runtime_root, target_vault)
    assert first["changed_files"] == sorted(RELEASE_RELATIVES)

    second = sync_product_shell_plugin(runtime_root, target_vault)
    assert second["status"] == "ok"
    assert second["changed_files"] == []
    assert second["source_hashes"] == first["source_hashes"]


def test_bootstrap_new_vault_creates_promised_layout(runtime_root: Path, tmp_path: Path) -> None:
    target = tmp_path / "new-vault"
    result = bootstrap_new_vault(runtime_root, target)

    assert result["status"] == "ok"
    assert result["plugin_id"] == PLUGIN_ID
    assert result["vault_root"] == str(target.resolve())
    assert result["launcher_path"] == "scripts/aiwiki-launcher.sh"
    assert result["written_files"] == sorted(result["written_files"])

    for relative_dir in ("raw/inbox", "wiki/sources", "schema", "output/control", ".aiwiki"):
        assert (target / relative_dir).is_dir(), relative_dir

    expected_files = [
        "README.md",
        "HOME.md",
        "wiki/indexes/README.md",
        "scripts/aiwiki-launcher.sh",
        f".obsidian/snippets/{FOLDER_LABEL_SNIPPET_NAME}.css",
        ".obsidian/appearance.json",
        ".obsidian/app.json",
        ".obsidian/core-plugins.json",
        ".obsidian/graph.json",
        ".obsidian/workspace.json",
        ".obsidian/community-plugins.json",
        f"{PLUGIN_REL}/data.json",
        f"{PLUGIN_REL}/main.js",
        f"{PLUGIN_REL}/manifest.json",
        f"{PLUGIN_REL}/styles.css",
    ]
    for relative in expected_files:
        assert (target / relative).is_file(), relative
        assert relative in result["written_files"], relative

    launcher = target / "scripts" / "aiwiki-launcher.sh"
    assert os.access(launcher, os.X_OK)
    assert (target / f"{PLUGIN_REL}/main.js").read_text(encoding="utf-8") == MAIN_JS

    workspace = json.loads((target / ".obsidian" / "workspace.json").read_text(encoding="utf-8"))
    last_open = workspace.get("lastOpenFiles", [])
    assert "wiki/indexes/review-queue.md" in last_open
    assert not any("Outputs.md" in entry for entry in last_open)


def test_bootstrap_refuses_non_empty_target_without_force(runtime_root: Path, tmp_path: Path) -> None:
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "existing.md").write_text("keep me\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already exists and is not empty"):
        bootstrap_new_vault(runtime_root, target)


def test_bootstrap_force_allows_non_empty_target(runtime_root: Path, tmp_path: Path) -> None:
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "existing.md").write_text("keep me\n", encoding="utf-8")
    result = bootstrap_new_vault(runtime_root, target, force=True)
    assert result["status"] == "ok"
    assert (target / "existing.md").read_text(encoding="utf-8") == "keep me\n"
    assert (target / f"{PLUGIN_REL}/main.js").is_file()


def test_bootstrap_refuses_file_target_even_with_force(runtime_root: Path, tmp_path: Path) -> None:
    target = tmp_path / "a-file"
    target.write_text("not a dir\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="not a directory"):
        bootstrap_new_vault(runtime_root, target, force=True)
