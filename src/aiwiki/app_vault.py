"""Vault bootstrap helpers for new 炼丹炉 workspaces."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

from .app_compile import shell_status
from .app_protocol import ensure_layout
from .app_utils import render_json_document, write_if_changed

PLUGIN_ID = "furnace-product-shell"

DEFAULT_OBSIDIAN_APP = {
    "alwaysUpdateLinks": True,
    "attachmentFolderPath": "raw/assets",
    "defaultViewMode": "preview",
    "newFileFolderPath": "raw/inbox",
    "newFileLocation": "folder",
    "promptDelete": False,
    "showInlineTitle": True,
    "showUnsupportedFiles": True,
    "useMarkdownLinks": True,
}

DEFAULT_OBSIDIAN_CORE_PLUGINS = {
    "audio-recorder": False,
    "backlink": True,
    "bases": True,
    "bookmarks": True,
    "canvas": True,
    "command-palette": True,
    "daily-notes": False,
    "editor-status": False,
    "file-explorer": True,
    "file-recovery": False,
    "footnotes": False,
    "global-search": True,
    "graph": True,
    "markdown-importer": False,
    "note-composer": False,
    "outline": True,
    "outgoing-link": True,
    "page-preview": True,
    "properties": True,
    "publish": False,
    "random-note": False,
    "slash-command": False,
    "slides": False,
    "switcher": True,
    "sync": False,
    "tag-pane": False,
    "templates": False,
    "webviewer": False,
    "word-count": False,
    "workspaces": True,
    "zk-prefixer": False,
}

DEFAULT_PLUGIN_DATA = {
    "settings": {
        "defaultAskFormat": "report",
        "defaultAskMode": "ask",
        "launcherPath": "scripts/aiwiki-launcher.sh",
        "recentRunsLimit": 8,
        "showHtmlShortcuts": True,
    },
    "recentRuns": [],
}


def _default_workspace_document() -> dict[str, Any]:
    return {
        "active": "home-leaf",
        "lastOpenFiles": [
            "HOME.md",
            "README.md",
            "wiki/indexes/furnace-center.md",
            "output/control/shell-summary.json",
        ],
        "left": {
            "children": [
                {
                    "children": [
                        {
                            "id": "left-files",
                            "state": {
                                "icon": "lucide-folder-closed",
                                "state": {"autoReveal": False, "sortOrder": "alphabetical"},
                                "title": "文件列表",
                                "type": "file-explorer",
                            },
                            "type": "leaf",
                        },
                        {
                            "id": "left-search-raw",
                            "state": {
                                "icon": "lucide-search",
                                "state": {
                                    "collapseAll": False,
                                    "explainSearch": False,
                                    "extraContext": False,
                                    "matchingCase": False,
                                    "query": 'path:"raw/inbox"',
                                    "sortOrder": "alphabetical",
                                },
                                "title": "原料搜索",
                                "type": "search",
                            },
                            "type": "leaf",
                        },
                        {
                            "id": "left-search-wiki",
                            "state": {
                                "icon": "lucide-search",
                                "state": {
                                    "collapseAll": False,
                                    "explainSearch": False,
                                    "extraContext": False,
                                    "matchingCase": False,
                                    "query": 'path:"wiki"',
                                    "sortOrder": "alphabetical",
                                },
                                "title": "知识搜索",
                                "type": "search",
                            },
                            "type": "leaf",
                        },
                        {
                            "id": "left-search-output",
                            "state": {
                                "icon": "lucide-search",
                                "state": {
                                    "collapseAll": False,
                                    "explainSearch": False,
                                    "extraContext": False,
                                    "matchingCase": False,
                                    "query": 'path:"output"',
                                    "sortOrder": "alphabetical",
                                },
                                "title": "输出搜索",
                                "type": "search",
                            },
                            "type": "leaf",
                        },
                    ],
                    "id": "left-tabs",
                    "type": "tabs",
                }
            ],
            "direction": "horizontal",
            "id": "left-root",
            "type": "split",
            "width": 320,
        },
        "left-ribbon": {
            "hiddenItems": {
                "bases:新建数据库": False,
                "canvas:新建白板": False,
                "command-palette:打开命令面板": False,
                "furnace-product-shell:Open Furnace Center": False,
                "furnace-product-shell:Refresh Furnace Shell": False,
                "graph:查看关系图谱": False,
                "switcher:打开快速切换": False,
                "workspaces:管理工作区布局": False,
            }
        },
        "main": {
            "children": [
                {
                    "children": [
                        {
                            "id": "home-leaf",
                            "state": {
                                "icon": "lucide-file",
                                "state": {"file": "HOME.md", "mode": "preview", "source": False},
                                "title": "HOME",
                                "type": "markdown",
                            },
                            "type": "leaf",
                        }
                    ],
                    "id": "main-tabs",
                    "type": "tabs",
                }
            ],
            "direction": "vertical",
            "id": "main-root",
            "type": "split",
        },
        "right": {
            "children": [
                {
                    "children": [
                        {
                            "id": "right-outline",
                            "state": {
                                "icon": "lucide-list",
                                "state": {
                                    "file": "HOME.md",
                                    "followCursor": False,
                                    "searchQuery": "",
                                    "showSearch": False,
                                },
                                "title": "HOME 的大纲",
                                "type": "outline",
                            },
                            "type": "leaf",
                        },
                        {
                            "id": "right-backlinks",
                            "state": {
                                "icon": "links-coming-in",
                                "state": {
                                    "backlinkCollapsed": False,
                                    "collapseAll": False,
                                    "extraContext": False,
                                    "searchQuery": "",
                                    "showSearch": False,
                                    "sortOrder": "alphabetical",
                                    "unlinkedCollapsed": True,
                                },
                                "title": "反向链接",
                                "type": "backlink",
                            },
                            "type": "leaf",
                        },
                        {
                            "id": "right-furnace-center",
                            "state": {
                                "icon": "flask-conical",
                                "state": {},
                                "title": "Furnace Center",
                                "type": "furnace-product-shell-furnace-center",
                            },
                            "type": "leaf",
                        },
                    ],
                    "currentTab": 2,
                    "id": "right-tabs",
                    "type": "tabs",
                }
            ],
            "direction": "horizontal",
            "id": "right-root",
            "type": "split",
            "width": 300,
        },
    }


def _render_vault_readme(runtime_root: Path) -> str:
    runtime = str(runtime_root.resolve())
    return (
        "\n".join(
            [
                "# 炼丹炉 Vault",
                "",
                "这是一个新的炼丹炉工作区（Obsidian vault）。",
                "",
                f"- 当前绑定的 runtime root：`{runtime}`",
                "- 当前 vault root：本目录",
                "- 日常入口：`HOME.md` + Product Shell 插件 + `scripts/aiwiki-launcher.sh`",
                "- Obsidian 与 CLI 共用同一个 runtime / state，遵守 `single writer, many readers`。",
                "",
                "## 常用命令",
                "",
                "```bash",
                "./scripts/aiwiki-launcher.sh shell-status",
                "./scripts/aiwiki-launcher.sh compile",
                "./scripts/aiwiki-launcher.sh drop-note --title \"晨间观察\" --text \"记录今天的新线索\"",
                "./scripts/aiwiki-launcher.sh ask \"今天最重要的变化是什么？\" --format report",
                "./scripts/aiwiki-launcher.sh nightly",
                "```",
                "",
                "## 工作流",
                "",
                "1. 投料可以走两条路：在 Obsidian 里直接整理 `raw/inbox/`，或在 CLI / agent 中使用 `drop-url / drop-pdf / drop-image / drop-repo / drop-note`。",
                "2. 提问也有两个入口：Obsidian Product Shell 的 `Ask`，以及 `./scripts/aiwiki-launcher.sh ask ...`。",
                "3. `compile / nightly / apply / revert` 这类写操作不要双开；同一时刻只保留一个写入口。",
                "4. 在 Obsidian 里打开 `HOME.md` 或 `Furnace Center`，再进入 `Review / Execution / Graph`。",
                "",
                "## 目录职责",
                "",
                "- `raw/`：原料",
                "- `wiki/`：来源、概念、判断、决策、索引",
                "- `output/`：报告、图表、HTML 控制面、审计产物",
                "- `schema/`：运行时规则和协议",
                "- `.aiwiki/`：状态、缓存、日志",
                "",
                "## 备注",
                "",
                "- 这个 vault 通过 `scripts/aiwiki-launcher.sh` 回到 runtime 执行，不要求 vault 自己包含 `src/aiwiki/`。",
                "- 如果 runtime root 迁移了，重新创建 launcher 或更新脚本里的 `RUNTIME_ROOT` 即可。",
                "",
            ]
        )
        + "\n"
    )


def _render_vault_home() -> str:
    return (
        "\n".join(
            [
                "---",
                'title: "炼丹炉工作台"',
                'kind: "dashboard"',
                "---",
                "",
                "# 炼丹炉工作台",
                "",
                "这是一个新建的炼丹炉 vault。Obsidian Product Shell 与 `scripts/aiwiki-launcher.sh` 是同一 runtime 的两个入口。",
                "",
                "- [[README|使用说明]]",
                "- [[wiki/indexes/furnace-center|炉心面板]]",
                "- [[wiki/indexes/review-center|审阅中心]]",
                "- [[wiki/indexes/execution-center|执行中心]]",
                "- [[wiki/indexes/graph-view|图谱视图]]",
                "- [[wiki/indexes/protocols|协议总览]]",
                "",
                "## 第一步",
                "",
                "1. 先点 Product Shell 里的 `Refresh` 或运行 `./scripts/aiwiki-launcher.sh shell-status`。",
                "2. 投料可以走 Obsidian 或 CLI：直接把材料放进 `raw/inbox/`，或使用 `drop-note / drop-url / drop-pdf / drop-image / drop-repo`。",
                "3. 提问可以走 Product Shell 的 `Ask`，也可以走 `./scripts/aiwiki-launcher.sh ask ...`。",
                "4. 运行 `compile`，再从 `Ask / Review / Execution` 开始当天工作。",
                "5. 写操作遵守单写约束：不要同时在 Obsidian 和终端里各跑一个写命令。",
                "",
                "## 路径职责",
                "",
                "- `raw/inbox/`：输入材料",
                "- `wiki/sources/`：来源页",
                "- `wiki/concepts/`：概念页",
                "- `wiki/judgments/` / `wiki/decisions/`：判断与决策",
                "- `output/`：报告、图表、HTML 面板与执行回执",
                "",
                "## 日常命令",
                "",
                "```bash",
                "./scripts/aiwiki-launcher.sh compile",
                "./scripts/aiwiki-launcher.sh ask \"总结今天的关键变化\" --format report",
                "./scripts/aiwiki-launcher.sh nightly",
                "```",
                "",
            ]
        )
        + "\n"
    )


def _render_launcher_script(runtime_root: Path) -> str:
    quoted_runtime = shlex.quote(str(runtime_root.resolve()))
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            'SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
            'VAULT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"',
            f"RUNTIME_ROOT={quoted_runtime}",
            "",
            'if [ ! -f "$RUNTIME_ROOT/src/aiwiki/cli.py" ]; then',
            '  echo "error: runtime root does not look like an aiwiki repo: $RUNTIME_ROOT" >&2',
            "  exit 1",
            "fi",
            "",
            'cd "$RUNTIME_ROOT"',
            'export PYTHONPATH="$RUNTIME_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"',
            'exec python3 -m aiwiki.cli --root "$VAULT_ROOT" "$@"',
            "",
        ]
    )


def _plugin_template_paths(runtime_root: Path) -> dict[str, Path]:
    plugin_root = runtime_root / ".obsidian" / "plugins" / PLUGIN_ID
    return {
        "manifest": plugin_root / "manifest.json",
        "main": plugin_root / "main.js",
        "styles": plugin_root / "styles.css",
    }


def _validate_runtime_root(runtime_root: Path) -> None:
    required = [
        runtime_root / "src" / "aiwiki" / "cli.py",
        runtime_root / ".obsidian" / "plugins" / PLUGIN_ID / "main.js",
        runtime_root / ".obsidian" / "plugins" / PLUGIN_ID / "manifest.json",
        runtime_root / ".obsidian" / "plugins" / PLUGIN_ID / "styles.css",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        joined = ", ".join(missing)
        raise FileNotFoundError(f"runtime root is missing required vault template assets: {joined}")


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
        "scripts/aiwiki-launcher.sh": _render_launcher_script(runtime_root),
    }
    for relative, content in managed_text_files.items():
        path = target_root / relative
        if write_if_changed(path, content):
            written_files.append(relative)

    launcher_path = target_root / "scripts" / "aiwiki-launcher.sh"
    current_mode = launcher_path.stat().st_mode
    os.chmod(launcher_path, current_mode | 0o111)

    json_files: dict[str, dict[str, Any]] = {
        ".obsidian/app.json": DEFAULT_OBSIDIAN_APP,
        ".obsidian/core-plugins.json": DEFAULT_OBSIDIAN_CORE_PLUGINS,
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

    for label, source in _plugin_template_paths(runtime_root).items():
        relative = {
            "manifest": f".obsidian/plugins/{PLUGIN_ID}/manifest.json",
            "main": f".obsidian/plugins/{PLUGIN_ID}/main.js",
            "styles": f".obsidian/plugins/{PLUGIN_ID}/styles.css",
        }[label]
        destination = target_root / relative
        if write_if_changed(destination, source.read_text(encoding="utf-8")):
            written_files.append(relative)

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
