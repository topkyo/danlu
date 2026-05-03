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
    "userIgnoreFilters": [
        "wiki/derived/",
        "wiki/decisions/",
        "wiki/judgments/",
        "wiki/elixirs/",
        "wiki/sources/",
        "wiki/concepts/",
        "schema/",
        "output/control/",
        "output/graph/",
        "output/review/",
        "output/slides/",
        "output/figures/",
        "output/_proposals/",
        ".aiwiki/",
    ],
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
        "locale": "zh",
        "recentRunsLimit": 8,
        "showHtmlShortcuts": True,
    },
    "recentRuns": [],
}

FOLDER_LABEL_SNIPPET_NAME = "danlu-zh-folders"

DEFAULT_OBSIDIAN_APPEARANCE = {
    "enabledCssSnippets": [FOLDER_LABEL_SNIPPET_NAME],
}

FOLDER_LABEL_OVERRIDES: tuple[tuple[str, str], ...] = (
    ("raw", "原料 raw"),
    ("output", "报告"),
    ("schema", "规则 schema"),
    ("scripts", "脚本 scripts"),
    ("prompts", "提示词 prompts"),
    ("raw/inbox", "收件箱 inbox"),
    ("raw/assets", "附件 assets"),
    ("raw/normalized", "标准化 normalized"),
    ("wiki/sources", "来源 sources"),
    ("wiki/concepts", "概念 concepts"),
    ("wiki/derived", "派生 derived"),
    ("wiki/decisions", "决策 decisions"),
    ("wiki/judgments", "判断 judgments"),
    ("wiki/indexes", "索引 indexes"),
    ("wiki/execution-proposals", "执行提案 execution-proposals"),
    ("wiki/rewrite-proposals", "改写提案 rewrite-proposals"),
    ("output/agents", "智能体 agents"),
    ("output/control", "控制面板 control"),
    ("output/control/execution-bundles", "执行包 execution-bundles"),
    ("output/control/execution-receipts", "执行回执 execution-receipts"),
    ("output/graph", "图谱 graph"),
    ("output/lint", "检查 lint"),
    ("output/packs", "输出包 packs"),
    ("output/packs/review", "审阅包 review"),
    ("output/packs/decision-memos", "决策备忘 decision-memos"),
    ("output/packs/sop-drafts", "SOP 草稿 sop-drafts"),
    ("output/pilots", "协议评分 pilots"),
    ("output/reports", "全部报告"),
    ("output/review", "审阅 review"),
    ("output/figures", "图表 figures"),
    ("output/slides", "幻灯片 slides"),
    ("schema/protocols", "协议 protocols"),
    ("schema/policies", "策略 policies"),
    ("schema/protocols/research", "研发协议 research"),
    ("schema/protocols/general", "通用协议 general"),
    ("schema/protocols/investing", "投资协议 investing"),
    ("schema/protocols/product", "产品协议 product"),
    ("schema/protocols/ops", "运维协议 ops"),
)

USER_HIDDEN_FOLDER_PATHS: tuple[str, ...] = (
    "raw",
    "wiki",
    "schema",
    "scripts",
    "prompts",
    "output/_candidates",
    "output/_proposals",
    "output/agents",
    "output/control",
    "output/figures",
    "output/graph",
    "output/lint",
    "output/packs",
    "output/pilots",
    "output/review",
    "output/slides",
)


def _folder_label_selectors(path: str) -> tuple[str, ...]:
    return (
        f'.nav-folder[data-path="{path}"] > .nav-folder-title > .nav-folder-title-content',
        f'.nav-folder-title[data-path="{path}"] > .nav-folder-title-content',
        f'.tree-item[data-path="{path}"] > .tree-item-self > .tree-item-inner',
        f'.tree-item-self[data-path="{path}"] > .tree-item-inner',
    )


def _folder_container_selectors(path: str) -> tuple[str, ...]:
    return (
        f'.nav-folder[data-path="{path}"]',
        f'.tree-item[data-path="{path}"]',
        f'.nav-folder-title[data-path="{path}"]',
        f'.tree-item-self[data-path="{path}"]',
    )


def _render_folder_label_snippet() -> str:
    lines = [
        "/*",
        " * 炼丹炉 vault — 文件浏览器用户视图",
        " * 保留运行时英文路径不变；普通用户默认只看报告，其余运行时分层从文件树隐藏。",
        " * 同时兼容旧结构（data-path 在父级）和新结构（data-path 在 title/self）两种 DOM。",
        " */",
        "",
    ]
    lines.extend(
        [
            "/* 默认隐藏 runtime / operator folders；Product Shell 和更多工具仍可打开对应页面。 */",
        ]
    )
    for path in USER_HIDDEN_FOLDER_PATHS:
        lines.extend(
            [
                f"/* hide {path} from the daily file tree */",
                ",\n".join(_folder_container_selectors(path)) + " {",
                "  display: none !important;",
                "}",
                "",
            ]
        )
    for path, label in FOLDER_LABEL_OVERRIDES:
        selectors = _folder_label_selectors(path)
        pseudo_selectors = tuple(f"{selector}::after" for selector in selectors)
        lines.extend(
            [
                f"/* {path} -> {label} */",
                ",\n".join(selectors) + " {",
                "  font-size: 0 !important;",
                "}",
                ",\n".join(pseudo_selectors) + " {",
                f'  content: "{label}";',
                "  font-size: var(--nav-item-size, 13px) !important;",
                "}",
                "",
            ]
        )
    return "\n".join(lines)


def _default_workspace_document() -> dict[str, Any]:
    return {
        "active": "main-furnace-center",
        "lastOpenFiles": [
            "wiki/indexes/furnace-center.md",
            "HOME.md",
            "README.md",
            "wiki/indexes/Outputs.md",
            "wiki/indexes/judgment-assets.md",
            "wiki/indexes/review-center.md",
            "wiki/indexes/execution-center.md",
            "output/control/shell-summary.json",
        ],
        "left": {
            "collapsed": True,
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
                            "id": "left-bookmarks",
                            "state": {
                                "icon": "lucide-bookmark",
                                "state": {},
                                "title": "书签",
                                "type": "bookmarks",
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
            "width": 260,
        },
        "left-ribbon": {
            "hiddenItems": {
                "bases:新建数据库": False,
                "canvas:新建白板": False,
                "command-palette:打开命令面板": False,
                "furnace-product-shell:Open Furnace Center": False,
                "furnace-product-shell:打开炉心面板": False,
                "furnace-product-shell:Refresh Furnace Shell": False,
                "furnace-product-shell:刷新炼丹炉 Shell": False,
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
                            "id": "main-furnace-center",
                            "state": {
                                "icon": "flask-conical",
                                "state": {},
                                "title": "炼丹炉",
                                "type": "furnace-product-shell-furnace-center",
                            },
                            "type": "leaf",
                        },
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
                    "currentTab": 0,
                    "id": "main-tabs",
                    "type": "tabs",
                }
            ],
            "direction": "vertical",
            "id": "main-root",
            "type": "split",
        },
        "right": {
            "collapsed": True,
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
                    ],
                    "currentTab": 0,
                    "id": "right-tabs",
                    "type": "tabs",
                }
            ],
            "direction": "horizontal",
            "id": "right-root",
            "type": "split",
            "width": 280,
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
                "- 日常入口：打开 Obsidian -> 主区 Product Shell（`HOME.md` 只保留说明和关键链接；CLI 作为备用/脚本入口）",
                "- 左侧文件树是用户视图：默认只保留报告入口；`raw/wiki/schema/output` 的完整分层仍由 runtime 管理。",
                "- Obsidian 与 CLI 共用同一个 runtime / state，遵守 `single writer, many readers`。",
                "- Product Shell 默认界面语言为中文，可在插件设置里切到 English。",
                "- LLM 现在不再做 `auto` 解析；请在 Product Shell 设置或环境变量里显式设置 `AIWIKI_LLM_BACKEND`。",
                "- 当前 Product Shell 暴露的可选 backend 是 `codex-cli / nvidia-nim-api / copilot-cli / claude-cli`。",
                "- 若选择 `codex-cli` 且未显式设 model，effective model 默认 `gpt-5.5`。",
                "- 若选择 `nvidia-nim-api` 且模型留空，会按 `Kimi K2.5 -> GLM-5.1 -> MiniMax` 依次尝试；key 默认走 `AIWIKI_NVIDIA_NIM_API_KEY`。",
                "",
                "## 备用 CLI / 脚本入口",
                "",
                "```bash",
                "./scripts/aiwiki-launcher.sh shell-status",
                "./scripts/aiwiki-launcher.sh compile",
                "./scripts/aiwiki-launcher.sh drop note --title \"晨间观察\" --text \"记录今天的新线索\"",
                "./scripts/aiwiki-launcher.sh ask \"今天最重要的变化是什么？\" --format report",
                "./scripts/aiwiki-launcher.sh nightly",
                "```",
                "",
                "## 工作流",
                "",
                "1. 默认在 Obsidian 中工作：主区 Product Shell 是日常入口，`HOME.md` 只做说明和关键链接。",
                "2. 投料从 Product Shell 输入框或 CLI / agent 的 `drop url / drop pdf / drop image / drop repo / drop note` 开始；不要从文件树理解 runtime 分层。",
                "3. 提问也有两个入口：Obsidian Product Shell 的 `Ask`，以及 `./scripts/aiwiki-launcher.sh ask ...`。",
                "4. `compile / nightly / apply / revert` 这类写操作不要双开；同一时刻只保留一个写入口。",
                "",
                "## Runtime 目录职责",
                "",
                "- `raw/`：原料",
                "- `wiki/`：来源、概念、判断、决策、索引",
                "- `output/`：报告、图表、HTML 控制面、审计产物",
                "- `schema/`：运行时规则和协议",
                "- `.aiwiki/`：状态、缓存、日志",
                "- 普通用户文件树默认只露出 `output/reports/`，其余目录由 Product Shell、更多工具和 CLI 间接打开。",
                "- `raw / wiki / output / schema` 这些英文目录名是 runtime contract；中文化通过工作台导航和说明完成，不建议直接重命名路径。",
                "",
                "## 备注",
                "",
                "- 这个 vault 通过 `scripts/aiwiki-launcher.sh` 回到 runtime 执行，不要求 vault 自己包含 `src/aiwiki/`。",
                "- `.html` 控制面（如 `output/graph/machine-memory.html`）会交给系统默认浏览器打开。",
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
                "# 炼丹炉",
                "",
                "这是炼丹炉在 Obsidian 里的产品入口。默认从主区的 Product Shell 开始：投料、提问、看 Today、打开报告；其他治理和调试入口收在更多工具。",
                "",
                "## 日常路径",
                "",
                "1. 在 Product Shell 输入框里投 URL / 文件 / 图片，或直接问一个问题。",
                "2. 看 Today：报告点 `Open`，审阅点 `Open Review`，命令先 `Copy command`。",
                "3. 把有价值的报告回流为判断、决策或金丹。",
                "4. 需要排障时再展开更多工具；不要先从目录结构开始工作。",
                "",
                "左侧文件树是用户视图：日常只需要报告。`raw/wiki/schema` 和 `output/` 的其他产物仍存在，但默认不作为用户入口。",
                "",
                "## 首屏模型",
                "",
                "- 输入端：Ask / Drop / Capture Note",
                "- 输出端：Today / Today's Reports / Previous Reports",
                "- 更多工具：审阅、执行、运行记录、指标、LLM 状态",
                "",
                "## 关键入口",
                "",
                "- [[README|使用说明]]",
                "- [[wiki/indexes/furnace-center|炉心面板索引]]",
                "- [[wiki/indexes/Outputs|输出面板]]",
                "- [[wiki/indexes/judgment-assets|判断资产]]",
                "- [[docs/Furnace Product Shell|Product Shell 设计]]",
                "- [[docs/Furnace Agent Architecture|炼丹炉 Agent 架构]]",
                "- [[docs/Furnace Evolution Mechanics|进化机制]]",
                "- [[docs/Furnace Elixir|金丹机制]]",
                "",
                "## 备用命令",
                "",
                "```bash",
                "./scripts/aiwiki-launcher.sh shell-status",
                "./scripts/aiwiki-launcher.sh compile",
                "./scripts/aiwiki-launcher.sh ask \"总结今天的关键变化\" --format report",
                "./scripts/aiwiki-launcher.sh nightly",
                "```",
                "",
                "写操作遵守单写约束：不要同时在 Obsidian 和终端里各跑一个 `compile / nightly / apply / revert`。",
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
            'if [ ! -f "$RUNTIME_ROOT/src/aiwiki/cli/__main__.py" ]; then',
            '  echo "error: runtime root does not look like an aiwiki repo: $RUNTIME_ROOT" >&2',
            "  exit 1",
            "fi",
            "",
            'cd "$RUNTIME_ROOT"',
            'for candidate in "$HOME/.local/bin" "$HOME/.local/npm/bin" "$HOME/bin"; do',
            '  if [ -d "$candidate" ]; then',
            '    case ":${PATH:-}:" in',
            '      *":$candidate:"*) ;;',
            '      *) PATH="$candidate${PATH:+:$PATH}" ;;',
            "    esac",
            "  fi",
            "done",
            "export PATH",
            'PLUGIN_DATA="$VAULT_ROOT/.obsidian/plugins/furnace-product-shell/data.json"',
            'if [ -f "$PLUGIN_DATA" ]; then',
            "  while IFS= read -r line; do",
            '    [ -n "$line" ] || continue',
            '    export "$line"',
            "  done < <(",
            '    python3 - "$PLUGIN_DATA" <<\'PY\'',
            "import json",
            "import os",
            "import sys",
            "from pathlib import Path",
            "",
            "path = Path(sys.argv[1])",
            "try:",
            '    payload = json.loads(path.read_text(encoding="utf-8"))',
            "except Exception:",
            "    raise SystemExit(0)",
            'settings = payload.get("settings", {}) if isinstance(payload, dict) else {}',
            "if not isinstance(settings, dict):",
            "    raise SystemExit(0)",
            "mapping = {",
            '    "AIWIKI_LLM_BACKEND": settings.get("llmBackend", ""),',
            '    "AIWIKI_LLM_MODEL": settings.get("llmModel", ""),',
            '    "AIWIKI_NVIDIA_NIM_API_KEY": settings.get("llmNvidiaNimApiKey", ""),',
            '    "AIWIKI_NVIDIA_NIM_BASE_URL": settings.get("llmNvidiaNimBaseUrl", ""),',
            "}",
            "for env_name, value in mapping.items():",
            "    if os.environ.get(env_name):",
            "        continue",
            "    if isinstance(value, str) and value.strip():",
            '        print(f"{env_name}={value.strip()}")',
            "PY",
            "  )",
            "fi",
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
